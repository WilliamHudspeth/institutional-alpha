"""P/E decomposition (commodity vs franchise) and the growth x margin break-even contour.

Both analyses reuse Stage 1's own value function and the consensus Ke the report used.
Nothing is defaulted: missing inputs give None plus a reason.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from iam import Fundamentals, MarketData, Security, ValuationPipeline
from iam.engine.market_implied import _present_value_two_stage, _solve_implied_growth
from iam.valuation.breakeven import build_breakeven
from iam.valuation.pe_decomposition import decompose_pe
from iam.valuation.types import ImpliedExpectations, Method, ValuationResult

# ---------------------------------------------------------------- P/E decomposition


def test_pe_decomposition_hand_computed():
    # EPS = 3355 / 100 = 33.55; Ke = 10.84%; price 1085.
    dec, reason = decompose_pe(
        net_income_ttm=3355.0,
        shares_outstanding=100.0,
        price=1085.0,
        ke=0.1084,
        ke_source="Stage 1 consensus Ke",
    )
    assert reason is None and dec is not None
    assert dec.eps == pytest.approx(33.55)
    assert dec.commodity_pe == pytest.approx(1 / 0.1084)  # 9.225x
    assert dec.steady_state_value == pytest.approx(33.55 / 0.1084)  # 309.50
    assert dec.steady_state_value == pytest.approx(309.5, abs=0.01)
    assert dec.franchise_premium == pytest.approx(1085.0 - 33.55 / 0.1084)
    assert dec.pvgo_share == pytest.approx(1 - 33.55 / 0.1084 / 1085.0)
    assert dec.pvgo_share == pytest.approx(0.7147, abs=1e-4)
    assert dec.pe == pytest.approx(1085.0 / 33.55)
    assert dec.franchise_pe == pytest.approx(dec.pe - dec.commodity_pe)
    assert dec.ke_source == "Stage 1 consensus Ke"
    assert "net_income_ttm" in dec.eps_source


@pytest.mark.parametrize(
    "kwargs, word",
    [
        (dict(net_income_ttm=-5.0), "EPS"),
        (dict(net_income_ttm=0.0), "EPS"),
        (dict(net_income_ttm=None), "EPS"),
        (dict(ke=None), "Ke"),
        (dict(ke=0.0), "Ke"),
        (dict(price=None), "price"),
        (dict(shares_outstanding=None), "EPS"),
    ],
)
def test_pe_decomposition_missing_gives_none_and_reason(kwargs, word):
    base = dict(net_income_ttm=100.0, shares_outstanding=10.0, price=50.0, ke=0.1, ke_source="test")
    base.update(kwargs)
    dec, reason = decompose_pe(**base)
    assert dec is None
    assert reason and word in reason


# ---------------------------------------------------------------- break-even

KE, N, GT, ROE, BASE_NI = 0.1084, 10, 0.043, 0.15, 10.0
PRICE = 180.0


def _stage1_implied() -> float:
    g = _solve_implied_growth(PRICE, BASE_NI, N, GT, KE, ROE)
    assert g is not None
    return g


def _stage1_result(with_assumptions: bool = True) -> ValuationResult:
    return ValuationResult(
        method=Method.REVERSE_DCF,
        implied=ImpliedExpectations(
            implied_revenue_growth=_stage1_implied(), discount_rate_assumed=KE
        ),
        assumptions=(
            {
                "discount_rate": KE,
                "high_growth_years": float(N),
                "terminal_growth": GT,
                "roe": ROE,
                "base_ni_per_share": BASE_NI,
            }
            if with_assumptions
            else {}
        ),
    )


def test_breakeven_contour_points_revaluate_to_price():
    be, reason = build_breakeven(_stage1_result(), price=PRICE, base_margin=0.441, ke=KE)
    assert reason is None and be is not None
    assert len(be.contour) >= 3
    for margin, g in be.contour:
        v = _present_value_two_stage(BASE_NI * margin / 0.441, g, N, GT, KE, ROE)
        assert abs(v - PRICE) / PRICE < 1e-3


def test_breakeven_base_margin_equals_stage1_implied_growth():
    stage1 = _stage1_result()
    be, _ = build_breakeven(stage1, price=PRICE, base_margin=0.441, ke=KE)
    assert be is not None
    base_cols = [g for m, g in be.contour if m == pytest.approx(0.441)]
    assert len(base_cols) == 1
    assert base_cols[0] == pytest.approx(stage1.implied.implied_revenue_growth, abs=1e-4)
    assert be.base[0] == pytest.approx(stage1.implied.implied_revenue_growth)
    assert be.base[1] == pytest.approx(0.441)
    assert be.base[2] == pytest.approx(PRICE, rel=1e-3)


def test_breakeven_higher_margin_needs_less_growth():
    be, _ = build_breakeven(_stage1_result(), price=PRICE, base_margin=0.441, ke=KE)
    assert be is not None
    gs = [g for _, g in sorted(be.contour)]
    assert gs == sorted(gs, reverse=True)


def test_breakeven_axes_follow_the_spec():
    g0 = _stage1_implied()
    be, _ = build_breakeven(_stage1_result(), price=PRICE, base_margin=0.441, ke=KE)
    assert be is not None
    assert be.margins[0] == pytest.approx(0.401) and be.margins[-1] == pytest.approx(0.481)
    assert all(g > GT for g in be.growths)
    assert be.growths[-1] == pytest.approx(g0 + 0.08)
    cell = be.values[2][3]
    assert cell == pytest.approx(
        _present_value_two_stage(BASE_NI * be.margins[3] / 0.441, be.growths[2], N, GT, KE, ROE)
    )


@pytest.mark.parametrize("margin", [None, 0.0, -0.1])
def test_breakeven_missing_margin_is_none_with_reason(margin):
    be, reason = build_breakeven(_stage1_result(), price=PRICE, base_margin=margin, ke=KE)
    assert be is None and reason and "margin" in reason


def test_breakeven_missing_price_ke_or_stage1():
    be, reason = build_breakeven(_stage1_result(), price=None, base_margin=0.4, ke=KE)
    assert be is None and "price" in reason
    be, reason = build_breakeven(_stage1_result(), price=PRICE, base_margin=0.4, ke=None)
    assert be is None and "Ke" in reason
    be, reason = build_breakeven(
        _stage1_result(with_assumptions=False), price=PRICE, base_margin=0.4, ke=KE
    )
    assert be is None and "Stage 1" in reason


# ---------------------------------------------------------------- pipeline wiring


def _security(**fund) -> Security:
    base = dict(
        fcf_ttm=1000,
        net_income_ttm=1000,
        shares_outstanding=100,
        operating_margin=0.30,
        revenue_history=[5000, 4500, 4000, 3500, 3000],
    )
    base.update(fund)
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(**base),
        market=MarketData(price=180, beta=1.1),
        qualitative={"forecast_growth": 0.06},
    )


def _run(sec: Security):
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=RuntimeError("offline"),
        ),
    ):
        return ValuationPipeline().run(sec)


def test_pipeline_report_carries_both_results():
    report = _run(_security())
    s1 = report.market_implied_engine
    ke = s1.assumptions["discount_rate"]
    dec = report.pe_decomposition
    assert dec is not None and report.pe_decomposition_note is None
    assert dec.ke == pytest.approx(ke)
    assert dec.eps == pytest.approx(10.0)
    assert dec.steady_state_value == pytest.approx(10.0 / ke)
    be = report.breakeven
    assert be is not None and report.breakeven_note is None
    assert be.ke == pytest.approx(ke)
    assert be.base[0] == pytest.approx(s1.implied.implied_revenue_growth)
    assert be.base_margin == pytest.approx(0.30)
    base_g = [g for m, g in be.contour if m == pytest.approx(0.30)]
    assert base_g and base_g[0] == pytest.approx(s1.implied.implied_revenue_growth, abs=1e-4)


def test_pipeline_report_none_with_reason_when_inputs_missing():
    report = _run(_security(net_income_ttm=-50, fcf_ttm=-50, operating_margin=None))
    assert report.pe_decomposition is None and report.pe_decomposition_note
    assert report.breakeven is None and report.breakeven_note


def test_pipeline_report_none_without_consensus_ke():
    sec = _security()
    sec.market.beta = None  # no regression beta: Stage 1 has no consensus Ke
    report = _run(sec)
    assert report.pe_decomposition is None and "Ke" in report.pe_decomposition_note
    assert report.breakeven is None and "Ke" in report.breakeven_note


# ---------------------------------------------------------------- GUI card html


def test_gui_card_html_shows_numbers_and_na():
    from iam.ui import gui

    dec, _ = decompose_pe(
        net_income_ttm=3355.0, shares_outstanding=100.0, price=1085.0, ke=0.1084, ke_source="s"
    )
    html = gui._pe_breakeven_html(dec, None, "no EPS", "no margin")
    assert "9.23x" in html and "$309.50" in html and "71.5%" in html
    assert "no margin" in html  # the reason shows instead of a table
    be, _ = build_breakeven(_stage1_result(), price=PRICE, base_margin=0.441, ke=KE)
    html = gui._pe_breakeven_html(None, be, "no EPS", None)
    assert "no EPS" in html and "n/a" in html
    assert "44.1%" in html and f"{_stage1_implied() * 100:.1f}%" in html


def test_ke_source_names_caller_supplied_rates_not_consensus():
    """A caller-supplied Rf/ERP drives Stage 1's Ke; the provenance must say so (Claude review)."""
    sec = _security()
    sec.qualitative = {"risk_free_rate": 0.05, "equity_risk_premium": 0.06}
    report = _run(sec)
    dec = report.pe_decomposition
    assert dec is not None
    assert dec.ke == pytest.approx(report.market_implied_engine.assumptions["discount_rate"])
    assert "caller-supplied" in dec.ke_source
    assert "consensus" not in dec.ke_source
