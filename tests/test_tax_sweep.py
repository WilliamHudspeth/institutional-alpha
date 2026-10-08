"""Failing-first test suite for tax-sweep task.

Verifies:
1. beta.py relevers with company_marginal_tax(sec)[0] and records provenance.
2. orchestrator.py SOTP block uses marginal rate when not supplied, and skips when
   market cap is missing and debt > 0.
3. engine/damodaran.py uses marginal rate when not supplied, and returns insufficient data
   result when market cap is missing with debt present.
4. data/damodaran.py relever_beta requires tax_rate (raises TypeError if omitted).
5. damodaran_defaults.py CompanyProfile tax_rate and rf cannot silently default to 21% / 4.30%.
6. expectations_battlefield.py market_tax_rate and intrinsic_tax_rate default to None and format as 'n/a'.
"""

from unittest.mock import patch

import pytest

from iam.data.damodaran import DamodaranProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.engine.damodaran import DamodaranEngine
from iam.pipeline.orchestrator import ValuationPipeline
from iam.valuation.beta import get_custom_beta_for_intrinsic, relever_beta, unlever_beta
from iam.valuation.country_tax import company_marginal_tax
from iam.valuation.damodaran_defaults import CompanyProfile, DamodaranUniverse, build_ke_for_company
from iam.valuation.expectations_battlefield import ExpectationBattlefieldExplicit
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


# --- Site 1: valuation/beta.py ---------------------------------------------


def test_site1_beta_relevers_with_marginal_tax():
    # Germany has 29.93% statutory rate in Damodaran Apr 2026 table
    sec = Security(
        ticker="SAP",
        revenue_mix={"Germany": 1.0},
        fundamentals=Fundamentals(total_debt=100.0, interest_expense_ttm=5.0),
        market=MarketData(price=100.0, market_cap=1000.0, beta=1.2),
    )
    marginal_rate, marginal_source = company_marginal_tax(sec)
    assert marginal_rate == pytest.approx(0.2993)

    beta_custom = get_custom_beta_for_intrinsic(sec)

    expected_unlev = unlever_beta(1.2, 0.0, marginal_rate)
    # debt_mv with coupon 5% and market rate 7.5%, maturity 5:
    debt_mv = sec.qualitative["debt_market_value"]
    current_de = debt_mv / 1000.0
    expected_relev = relever_beta(expected_unlev, current_de, marginal_rate)

    assert beta_custom == pytest.approx(expected_relev, rel=1e-5)
    assumptions = " | ".join(sec.qualitative["beta_assumptions"])
    assert f"tax_rate={marginal_rate:.1%} ({marginal_source})" in assumptions
    assert "21.0%" not in assumptions


# --- Site 2: pipeline/orchestrator.py SOTP block ---------------------------


def test_site2_sotp_uses_marginal_rate_when_unsupplied(offline):
    sec = Security(
        ticker="SAP",
        revenue_mix={"Germany": 1.0},
        fundamentals=Fundamentals(
            fcf_ttm=100,
            net_income_ttm=100,
            shares_outstanding=10,
            total_debt=100,
            segments=[
                Segment(
                    name="Enterprise",
                    revenue=1000,
                    ebit=200,
                    unlevered_beta=1.0,
                    tax_rate=0.2993,
                    growth_rate=0.04,
                    fcfe=150,
                )
            ],
        ),
        market=MarketData(price=20.0, market_cap=2000),
    )
    report = ValuationPipeline().run(sec)
    notes = report.intrinsic.notes
    assert any("Tax rate: 29.9%" in n for n in notes)
    assert any("revenue-weighted" in n for n in notes)
    assert not any("model default: US statutory federal rate" in n for n in notes)


def test_site2_sotp_skips_when_market_cap_missing_and_debt_positive(offline):
    sec = Security(
        ticker="SAP",
        revenue_mix={"Germany": 1.0},
        fundamentals=Fundamentals(
            fcf_ttm=100,
            net_income_ttm=100,
            shares_outstanding=10,
            total_debt=100,  # debt > 0
            segments=[
                Segment(
                    name="Enterprise",
                    revenue=1000,
                    ebit=200,
                    unlevered_beta=1.0,
                    tax_rate=0.2993,
                    growth_rate=0.04,
                    fcfe=150,
                )
            ],
        ),
        market=MarketData(price=20.0, market_cap=None),  # market_cap is missing
    )
    report = ValuationPipeline().run(sec)
    assert report.intrinsic.fair_value_per_share is None
    assert any("insufficient data: market cap unavailable" in n for n in report.intrinsic.notes)


# --- Site 3: engine/damodaran.py -------------------------------------------


def test_site3_engine_uses_marginal_tax_and_handles_missing_market_cap():
    engine = DamodaranEngine()
    sec = Security(
        ticker="SAP",
        revenue_mix={"Germany": 1.0},
        fundamentals=Fundamentals(
            fcf_ttm=100,
            shares_outstanding=10,
            total_debt=100,
        ),
        market=MarketData(price=20.0, market_cap=1000.0),
        qualitative={
            "segments": [
                Segment(
                    name="Enterprise",
                    revenue=1000,
                    ebit=200,
                    unlevered_beta=1.0,
                    tax_rate=0.2993,
                    growth_rate=0.04,
                    fcfe=150,
                )
            ]
        },
    )
    res = engine.compute(sec)
    # D/E = 100 / 1000 = 0.1
    # Marginal rate = 0.2993
    # beta_l = 1.0 * (1 + (1 - 0.2993) * 0.1) = 1.07007
    # ke = 0.04 + 1.07007 * 0.05 = 0.0935035
    assert res.assumptions["wacc"] == pytest.approx(0.0935035, rel=1e-5)

    # Missing market cap with debt present -> return insufficient data result
    sec_no_mcap = Security(
        ticker="SAP",
        revenue_mix={"Germany": 1.0},
        fundamentals=Fundamentals(
            fcf_ttm=100,
            shares_outstanding=10,
            total_debt=100,
        ),
        market=MarketData(price=20.0, market_cap=None),
        qualitative=dict(sec.qualitative),
    )
    res_no_mcap = engine.compute(sec_no_mcap)
    assert res_no_mcap.fair_value_low is None
    assert res_no_mcap.fair_value_high is None
    assert res_no_mcap.confidence == 0.0


# --- Site 4: data/damodaran.py relever_beta ---------------------------------


def test_site4_relever_beta_requires_tax_rate():
    with pytest.raises(TypeError):
        # Calling without tax_rate must raise TypeError
        DamodaranProvider.relever_beta(1.0, 0.5)  # type: ignore[call-arg]


# --- Site 5: valuation/damodaran_defaults.py CompanyProfile -----------------


def test_site5_company_profile_no_silent_21_percent_tax_or_rf():
    uni = DamodaranUniverse(
        us_erp=0.05,
        region_erps={"Americas": 0.05},
        sector_beta_u={"Software": 1.0},
    )
    profile = CompanyProfile("X", "Software", {"Americas": 1.0})
    assert profile.tax_rate is None
    assert profile.rf is None
    # Consumer must resolve explicitly; cannot build Ke with None
    with pytest.raises(ValueError):
        build_ke_for_company(profile, uni)


# --- Site 6: valuation/expectations_battlefield.py -------------------------


def test_site6_expectations_battlefield_na_for_unknown_tax_rate():
    bf = ExpectationBattlefieldExplicit(
        market_growth=0.10,
        intrinsic_growth=0.05,
        market_margin=0.20,
        intrinsic_margin=0.25,
        market_roic=0.12,
        intrinsic_roic=0.10,
        growth_overlap=0.5,
        alignment_score=60,
        primary_disagreement="Growth",
        expectation_mismatch_score=50,
    )
    assert bf.market_tax_rate is None
    assert bf.intrinsic_tax_rate is None
    summary_text = bf.summary()
    assert "Tax Rate" in summary_text
    assert "Market:    n/a" in summary_text
    assert "Intrinsic: n/a" in summary_text


# --- Review follow-ups -------------------------------------------------


def _sotp_security(shares):
    return Security(
        ticker="SAPX",
        revenue_mix={"Germany": 1.0},
        fundamentals=Fundamentals(
            fcf_ttm=100,
            net_income_ttm=100,
            shares_outstanding=shares,
            total_debt=100,
            segments=[
                Segment(
                    name="Enterprise",
                    revenue=1000,
                    ebit=200,
                    unlevered_beta=1.0,
                    tax_rate=0.2993,
                    growth_rate=0.04,
                    fcfe=150,
                )
            ],
        ),
        market=MarketData(price=20.0, market_cap=1000.0),
    )


def test_sotp_without_share_count_reports_insufficient_data_not_ev_over_one(offline):
    """`shares_outstanding or 1.0` turned the whole SOTP value into a per-share price."""
    report = ValuationPipeline().run(_sotp_security(shares=None))
    assert report.intrinsic.fair_value_per_share is None
    assert any("shares outstanding unavailable" in n for n in report.intrinsic.notes)


def test_sotp_with_share_count_still_divides_by_it(offline):
    with_shares = ValuationPipeline().run(_sotp_security(shares=10)).intrinsic
    assert with_shares.fair_value_per_share is not None
    assert with_shares.fair_value_per_share > 0


def test_engine_missing_market_cap_names_the_reason():
    sec = Security(
        ticker="ENGX",
        fundamentals=Fundamentals(fcf_ttm=100, shares_outstanding=10, total_debt=100),
        market=MarketData(price=20.0, market_cap=None),
        # DamodaranEngine reads segments from qualitative, not fundamentals.
        qualitative={
            "segments": [
                Segment(
                    name="A",
                    revenue=1000,
                    ebit=200,
                    unlevered_beta=1.0,
                    tax_rate=0.25,
                    growth_rate=0.04,
                    fcfe=150,
                )
            ]
        },
    )
    res = DamodaranEngine().compute(sec)
    assert res.confidence == 0.0
    assert "market cap unavailable" in res.narrative


def test_battlefield_unmeasured_beta_erp_terminal_are_na_and_not_ranked():
    """The engine never measures these; a zero gap must not read as 'no disagreement'."""
    bf = ExpectationBattlefieldExplicit(
        market_growth=0.10,
        intrinsic_growth=0.05,
        market_margin=0.30,
        intrinsic_margin=0.25,
        market_roic=0.20,
        intrinsic_roic=0.15,
        growth_overlap=0.5,
        alignment_score=50.0,
        primary_disagreement="Growth",
        expectation_mismatch_score=40.0,
    )
    assert bf.beta_gap is None and bf.erp_gap is None and bf.terminal_growth_gap is None
    ranked = [name for name, _ in bf.disagreement_ranking]
    assert set(ranked) == {"Growth", "Margin", "ROIC"}
    assert "Beta" not in ranked and "ERP" not in ranked and "Terminal Growth" not in ranked
    measured = ExpectationBattlefieldExplicit(
        market_growth=0.10,
        intrinsic_growth=0.05,
        market_margin=0.30,
        intrinsic_margin=0.25,
        market_roic=0.20,
        intrinsic_roic=0.15,
        growth_overlap=0.5,
        alignment_score=50.0,
        primary_disagreement="Growth",
        expectation_mismatch_score=40.0,
        market_beta=1.3,
        intrinsic_beta=1.0,
    )
    assert measured.beta_gap == pytest.approx(0.3)
    assert "Beta" in [name for name, _ in measured.disagreement_ranking]
