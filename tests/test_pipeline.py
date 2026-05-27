"""Tests for the v0.2.0-alpha valuation pipeline."""

import pytest

from iam import Security, Fundamentals, MarketData, ValuationPipeline
from iam.valuation import (
    ReverseDCF, RelativeValuation, FCFEDCF, FCFEAssumptions, Triangulator,
    Method,
)
from iam.valuation.reverse_dcf import _present_value_two_stage, _solve_implied_growth


# ---------------------------------------------------------------------------
# Reverse DCF math
# ---------------------------------------------------------------------------

def test_pv_two_stage_at_zero_growth():
    """At zero high-growth and 0% terminal, PV reduces to a perpetuity."""
    pv = _present_value_two_stage(base_ni=10, g_high=0.0, n=10, g_terminal=0.0, r=0.10, roe=0.15)
    # Because g_high and g_terminal are 0, reinvestment is 0.
    # Terminal at end of year 10: 10/0.10 = 100, discounted back: 100/1.1^10 ~ 38.55
    # Sum ~ 100
    assert 95 < pv < 105


def test_pv_increases_with_growth():
    """Higher growth -> higher PV, monotonically."""
    pvs = []
    for g in [0.0, 0.05, 0.10, 0.15]:
        pvs.append(_present_value_two_stage(10, g, 10, 0.025, 0.09, 0.20)) # High ROE to limit reinvestment penalty
    assert pvs == sorted(pvs)
    assert all(pvs[i] < pvs[i + 1] for i in range(len(pvs) - 1))


def test_solve_implied_growth_roundtrip():
    """Solve for g such that PV == target, then verify the solution."""
    target = 250.0
    g = _solve_implied_growth(target_price=target, base_ni=10, n=10, g_terminal=0.025, r=0.09, roe=0.15)
    assert g is not None
    pv = _present_value_two_stage(10, g, 10, 0.025, 0.09, 0.15)
    assert abs(pv - target) / target < 0.01


def test_reverse_dcf_implausibly_high_price_returns_none():
    """If the price requires >60% growth, the solver should fail gracefully."""
    g = _solve_implied_growth(target_price=100_000, base_ni=1, n=10, g_terminal=0.025, r=0.09, roe=0.15)
    assert g is None


# ---------------------------------------------------------------------------
# Reverse DCF integration
# ---------------------------------------------------------------------------

def test_reverse_dcf_basic_run():
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            fcf_ttm=1000,
            shares_outstanding=100,
            revenue_history=[1200, 1100, 1000, 900, 800],
        ),
        market=MarketData(price=180),
    )
    result = ReverseDCF().compute(sec)
    assert result.method == Method.REVERSE_DCF
    assert result.implied is not None
    assert result.implied.implied_revenue_growth is not None
    # Should also have computed growth_vs_history_max
    assert result.implied.growth_vs_history_max is not None


def test_reverse_dcf_negative_fcfe_skipped():
    sec = Security(
        ticker="LOSS",
        fundamentals=Fundamentals(net_income_ttm=-500, fcf_ttm=-500, shares_outstanding=100),
        market=MarketData(price=50),
    )
    result = ReverseDCF().compute(sec)
    assert result.confidence < 0.5
    assert "non-positive" in result.verdict_text.lower()


# ---------------------------------------------------------------------------
# Relative valuation
# ---------------------------------------------------------------------------

def test_relative_valuation_with_all_signals():
    sec = Security(
        ticker="REL",
        market=MarketData(
            price=100,
            pe_ttm=15,
            pe_history=[14, 16, 18, 20, 22, 24, 18, 16, 14, 12,
                        14, 16, 18, 20, 22, 24, 18, 16, 14, 12,
                        14, 16, 18, 20],
            ev_ebitda=10,
            sector_ev_ebitda_median=15,
            fcf_yield=0.06,
            peer_fcf_yields=[0.04, 0.045, 0.05, 0.055],
        ),
    )
    result = RelativeValuation().compute(sec)
    # Stock looks cheap on all three signals -> positive ratio
    assert result.fair_value_to_price > 0.05
    assert result.confidence > 0.5


def test_relative_valuation_no_inputs():
    sec = Security(ticker="EMPTY", market=MarketData(price=50))
    result = RelativeValuation().compute(sec)
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# FCFE DCF
# ---------------------------------------------------------------------------

def test_fcfe_dcf_basic_run():
    sec = Security(
        ticker="DCF",
        fundamentals=Fundamentals(fcf_ttm=1000, shares_outstanding=100),
        market=MarketData(price=150),
        qualitative={"forecast_growth": 0.10, "forecast_discount_rate": 0.09},
    )
    result = FCFEDCF().compute(sec)
    assert result.method == Method.INTRINSIC
    assert result.fair_value_per_share is not None
    assert result.fair_value_per_share > 0
    # Confidence shouldn't be penalized since we provided explicit assumptions
    assert result.confidence == 1.0


def test_fcfe_dcf_without_explicit_assumptions_reduces_confidence():
    sec = Security(
        ticker="DCF",
        fundamentals=Fundamentals(fcf_ttm=1000, shares_outstanding=100),
        market=MarketData(price=150),
    )
    result = FCFEDCF().compute(sec)
    # No qualitative['forecast_growth'] -> confidence should be reduced
    assert result.confidence < 1.0


def test_fcfe_higher_growth_higher_fair_value():
    """Sanity: bumping growth assumption raises fair value."""
    base = Security(
        ticker="DCF",
        fundamentals=Fundamentals(fcf_ttm=1000, shares_outstanding=100),
        market=MarketData(price=100),
    )
    low = FCFEDCF().compute(base, FCFEAssumptions(high_growth=0.05))
    high = FCFEDCF().compute(base, FCFEAssumptions(high_growth=0.15))
    assert high.fair_value_per_share > low.fair_value_per_share


# ---------------------------------------------------------------------------
# Triangulation
# ---------------------------------------------------------------------------

def test_triangulator_agreement():
    """When all three methods agree, verdict should be AGREE with high conf."""
    from iam.valuation.types import ValuationResult, ImpliedExpectations

    rev = ValuationResult(
        method=Method.REVERSE_DCF, confidence=0.9,
        implied=ImpliedExpectations(growth_vs_history_max=1.0),  # converts to 0% ratio
    )
    rel = ValuationResult(
        method=Method.RELATIVE, confidence=0.9, fair_value_to_price=0.03,
    )
    intr = ValuationResult(
        method=Method.INTRINSIC, confidence=0.9, fair_value_to_price=-0.02,
    )
    tri = Triangulator().triangulate(rev, rel, intr)
    assert tri.verdict == "agree"
    assert tri.confidence > 0.7


def test_triangulator_disagreement():
    """Three wildly different ratios -> disagree verdict."""
    from iam.valuation.types import ValuationResult, ImpliedExpectations

    rev = ValuationResult(
        method=Method.REVERSE_DCF, confidence=0.9,
        implied=ImpliedExpectations(growth_vs_history_max=2.0),  # converts to -0.5
    )
    rel = ValuationResult(
        method=Method.RELATIVE, confidence=0.9, fair_value_to_price=0.5,
    )
    intr = ValuationResult(
        method=Method.INTRINSIC, confidence=0.9, fair_value_to_price=0.0,
    )
    tri = Triangulator().triangulate(rev, rel, intr)
    assert tri.verdict in ("disagree", "two_of_three")
    assert tri.confidence < 0.7


def test_triangulator_two_of_three():
    """Two methods cluster, third is outlier."""
    from iam.valuation.types import ValuationResult, ImpliedExpectations

    rev = ValuationResult(
        method=Method.REVERSE_DCF, confidence=0.9,
        implied=ImpliedExpectations(growth_vs_history_max=1.0),  # -> ~0
    )
    rel = ValuationResult(
        method=Method.RELATIVE, confidence=0.9, fair_value_to_price=0.02,
    )
    intr = ValuationResult(
        method=Method.INTRINSIC, confidence=0.9, fair_value_to_price=0.50,
    )
    tri = Triangulator().triangulate(rev, rel, intr)
    assert tri.verdict == "two_of_three"
    assert Method.INTRINSIC in tri.outliers


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def test_full_pipeline_runs():
    sec = Security(
        ticker="FULL",
        fundamentals=Fundamentals(
            fcf_ttm=2800,
            shares_outstanding=1000,
            revenue_history=[10000, 8500, 7200, 6100, 5200],
        ),
        market=MarketData(
            price=180, pe_ttm=75, ev_ebitda=50,
            pe_history=[60, 55, 50, 70, 80, 65, 55, 45, 40, 35,
                        50, 60, 70, 80, 65, 55, 45, 40, 35, 50,
                        60, 70, 50, 45],
            sector_ev_ebitda_median=22, fcf_yield=0.016,
            peer_fcf_yields=[0.03, 0.025, 0.04],
        ),
        qualitative={"forecast_growth": 0.18, "forecast_discount_rate": 0.10},
    )
    report = ValuationPipeline().run(sec)
    assert report.ticker == "FULL"
    assert report.reverse_dcf.implied is not None
    assert report.relative.fair_value_to_price is not None
    assert report.intrinsic.fair_value_to_price is not None
    assert report.triangulation.verdict in (
        "agree", "two_of_three", "disagree", "single_method", "no_data"
    )
    # explain() should produce non-empty multiline text
    text = report.explain()
    assert "STAGE 1" in text
    assert "STAGE 4" in text


def test_empty_security_pipeline_no_crash():
    """Pipeline on a totally empty security should return low confidence, not crash."""
    report = ValuationPipeline().run(Security(ticker="EMPTY"))
    assert report.triangulation.verdict in ("no_data", "single_method", "disagree")


def test_v01_factor_scoring_still_works():
    """Make sure adding the pipeline didn't break v0.1.0 factor scoring."""
    from iam import score
    result = score(Security(ticker="LEGACY"))
    assert result.composite is not None
    assert len(result.factor_breakdown) == 10
