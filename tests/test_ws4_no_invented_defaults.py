"""Invented defaults must not reach the screen.

Silent fills (``x or 0.10``) become None / flagged; documented model
assumptions stay but are labelled with their source.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from iam import Fundamentals, MarketData, Security, ValuationPipeline
from iam.data.macro import MacroShock
from iam.pipeline.battlefield import intrinsic_vector_from_assumptions
from iam.pipeline.macro import MacroStressEngine
from iam.ui.menu import fmt_pct_or_na, format_assumption_lines
from iam.valuation.beta import get_custom_beta_for_intrinsic
from iam.valuation.fcfe_dcf import FCFEDCF
from iam.valuation.profile_builder import _sector_margin_default, build_company_profile
from iam.valuation.sotp import Segment


@pytest.fixture
def offline():
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=RuntimeError("offline"),
        ),
    ):
        yield


# --- profile_builder -------------------------------------------------------


def _bare_security(**fund) -> Security:
    return Security(
        ticker="X",
        sector="Technology",
        fundamentals=Fundamentals(**fund),
        market=MarketData(price=10.0),
    )


def test_profile_missing_roe_roic_are_none_not_invented():
    p = build_company_profile(_bare_security())
    assert p.roe is None and p.roic is None
    assert any("roe unavailable" in m for m in p.missing_inputs)
    assert any("roic unavailable" in m for m in p.missing_inputs)


def test_profile_missing_op_margin_is_flagged_not_silently_ten_percent():
    p = build_company_profile(_bare_security())
    assert p.op_margin == _sector_margin_default("Technology")  # not the old 0.10
    assert any("op_margin unavailable" in m for m in p.missing_inputs)


def test_profile_reported_zero_is_kept():
    p = build_company_profile(_bare_security(operating_margin=0.0, roic_history=[0.0, 0.0, 0.0]))
    assert p.op_margin == 0.0  # old code turned a real 0 into 0.10
    assert p.roe == 0.0  # old code turned a real 0 into 0.12
    assert not any("op_margin unavailable" in m for m in p.missing_inputs)


# --- macro stress ----------------------------------------------------------

SHOCK = MacroShock(name="t", rate_shock_bps=100, growth_shock_pct=-0.01, inflation_shock_pct=0.0)


def _fcfe_security(**qual) -> Security:
    return Security(
        ticker="T",
        fundamentals=Fundamentals(fcf_ttm=1000, net_income_ttm=1000, shares_outstanding=100),
        market=MarketData(price=50.0),
        qualitative=dict(qual),
    )


def test_stress_on_model_defaults_is_flagged_and_confidence_cut():
    res = MacroStressEngine(FCFEDCF()).run_stress_test(_fcfe_security(), SHOCK)
    assert res.confidence == pytest.approx(0.7)
    assert any("model-default" in n for n in res.notes)


def test_stress_with_supplied_assumptions_is_not_flagged():
    sec = _fcfe_security(
        forecast_growth=0.05, forecast_discount_rate=0.09, forecast_terminal_growth=0.02
    )
    res = MacroStressEngine(FCFEDCF()).run_stress_test(sec, SHOCK)
    assert res.confidence == pytest.approx(1.0)
    assert not any("model-default" in n for n in res.notes)


# --- menu / gui formatting -------------------------------------------------


def test_fmt_pct_or_na():
    assert fmt_pct_or_na(None) == "n/a"
    assert fmt_pct_or_na(0.0912) == "9.12%"


def test_menu_assumption_lines_label_sources_and_do_not_invent_wacc():
    txt = format_assumption_lines({}, 0.08, growth_from_user=False)
    assert "9.00%" not in txt  # old code printed a fixed 9% WACC
    assert "computed by the pipeline" in txt
    assert "model default" in txt
    user = format_assumption_lines({"forecast_discount_rate": 0.11}, 0.13, growth_from_user=True)
    assert "11.00% (supplied)" in user and "user input" in user


# --- SOTP branch -----------------------------------------------------------


def _sotp_security(**qual) -> Security:
    seg = Segment(
        name="A",
        revenue=1000,
        ebit=200,
        unlevered_beta=1.0,
        tax_rate=0.21,
        growth_rate=0.04,
        fcfe=150,
    )
    f = Fundamentals(fcf_ttm=150, net_income_ttm=150, shares_outstanding=100, total_debt=100)
    f.segments = [seg]  # type: ignore[attr-defined]
    return Security(
        ticker="S",
        fundamentals=f,
        market=MarketData(price=20.0, market_cap=2000),
        qualitative=qual,
    )


def test_sotp_does_not_invent_growth_or_roe(offline):
    report = ValuationPipeline().run(_sotp_security())
    a = report.intrinsic.assumptions
    assert "high_growth" not in a and "roe" not in a
    assert "cost_of_equity" in a
    vec = intrinsic_vector_from_assumptions(a)
    assert vec.growth is None and vec.roe is None
    assert any("Tax rate: 25.0%" in n and "United States" in n for n in report.intrinsic.notes)


def test_sotp_uses_supplied_tax_rate(offline):
    report = ValuationPipeline().run(_sotp_security(tax_rate=0.30))
    assert any("Tax rate: 30.0% (supplied)" in n for n in report.intrinsic.notes)


# --- beta ------------------------------------------------------------------


def test_beta_lists_default_assumptions():
    sec = Security(
        ticker="B",
        fundamentals=Fundamentals(total_debt=100, interest_expense_ttm=5),
        market=MarketData(price=10, market_cap=1000, beta=1.2),
    )
    get_custom_beta_for_intrinsic(sec)
    used = " | ".join(sec.qualitative["beta_assumptions"])
    assert "tax_rate=25.0%" in used and "pre_tax_cost_debt=7.5%" in used


def test_beta_without_market_cap_does_not_relever_on_invented_equity():
    sec = Security(
        ticker="B",
        fundamentals=Fundamentals(total_debt=100, interest_expense_ttm=5),
        market=MarketData(price=10, beta=1.2),
    )
    # old code used equity=1.0 -> D/E ~ 100 -> an absurd beta
    assert get_custom_beta_for_intrinsic(sec) == pytest.approx(1.2)
    assert any("market cap unavailable" in n for n in sec.qualitative["beta_assumptions"])
