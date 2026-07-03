"""Regression tests for known edge cases in fundamentals data.

Each test pins down behavior for an input shape that has previously caused
(or could plausibly cause) a crash or silently-wrong result: zero revenue
(division-by-zero risk), NaN numeric fields (propagation risk), and extreme
leverage (penalty-scaling / overflow risk). These guard against future
changes reintroducing those failure modes.
"""

from __future__ import annotations

import math

from iam.data.security import Fundamentals, MarketData, Security
from iam.factors.earnings_quality import EarningsQualityFactor
from iam.pipeline import ValuationPipeline
from iam.pipeline.verdict import VerdictGenerator
from iam.valuation.types import TriangulationResult

from unittest.mock import MagicMock


# --------------------------------------------------------------------------- #
# 1. Zero revenue
# --------------------------------------------------------------------------- #


def test_zero_revenue_does_not_raise_zero_division_in_earnings_quality():
    """revenue_ttm=0 must not raise ZeroDivisionError in ratio computations
    (sbc_pct_revenue, capex_intensity) that divide by revenue."""
    sec = Security(
        ticker="ZEROREV",
        fundamentals=Fundamentals(
            revenue_ttm=0.0,
            sbc_ttm=100.0,
            capex_ttm=50.0,
            fcf_ttm=1000.0,
            net_income_ttm=800.0,
            shares_outstanding=100.0,
        ),
        market=MarketData(price=50),
    )

    contribution = EarningsQualityFactor().compute(sec)

    # Guarded by `revenue_ttm > 0` checks -- ratios keyed off revenue must be
    # skipped entirely (not computed as inf/nan) when revenue is zero.
    assert "sbc_pct_revenue" not in contribution.components
    assert "capex_authenticity" not in contribution.components
    assert 0.0 <= contribution.confidence <= 1.0


def test_zero_revenue_security_completes_full_pipeline_without_crash():
    """A security with zero revenue must produce a full pipeline report,
    never raise, and never leak inf/nan into the final verdict inputs."""
    sec = Security(
        ticker="ZEROREV",
        fundamentals=Fundamentals(
            revenue_ttm=0.0,
            fcf_ttm=1000.0,
            shares_outstanding=100.0,
            revenue_history=[0.0, 0.0, 0.0],
        ),
        market=MarketData(price=50),
        qualitative={"forecast_growth": 0.05, "forecast_discount_rate": 0.09},
    )

    report = ValuationPipeline().run(sec)

    assert report.ticker == "ZEROREV"
    assert report.triangulation.verdict in (
        "agree",
        "two_of_three",
        "disagree",
        "single_method",
        "no_data",
    )
    assert not math.isnan(report.triangulation.confidence)
    assert not math.isinf(report.triangulation.confidence)


# --------------------------------------------------------------------------- #
# 2. NaN numeric fields
# --------------------------------------------------------------------------- #


def test_nan_leverage_inputs_skip_penalty_instead_of_crashing():
    """NaN total_debt / ebitda_ttm must not raise and must not be treated as
    a >=4.0x leverage breach (NaN comparisons are always False in Python;
    the risk-penalty block relies on that to stay a no-op for NaN)."""
    generator = VerdictGenerator()
    sec = Security(
        ticker="NANLEV",
        fundamentals=Fundamentals(
            total_debt=float("nan"),
            ebitda_ttm=float("nan"),
        ),
    )
    tri = TriangulationResult(
        verdict="agree",
        confidence=0.9,
        cluster_center=0.20,
        cluster_members=[],
        outliers=[],
        notes=[],
    )
    rel_mock = MagicMock()
    rel_mock.fair_value_to_price = 0.10

    result = generator.generate(tri, rel_mock, sec)

    assert result.rating == "BUY"
    assert result.confidence_band == "HIGH"  # not downgraded by an unfireable NaN check
    assert not any("High leverage" in n for n in result.notes)


def test_nan_fundamentals_do_not_crash_full_pipeline():
    """A security with NaN scattered through its fundamentals/market data
    must still produce a report rather than raising."""
    sec = Security(
        ticker="NANFIELDS",
        fundamentals=Fundamentals(
            revenue_ttm=float("nan"),
            fcf_ttm=1000.0,
            net_income_ttm=float("nan"),
            total_debt=float("nan"),
            ebitda_ttm=2000.0,
            shares_outstanding=100.0,
        ),
        market=MarketData(price=50, pe_ttm=float("nan")),
        qualitative={"forecast_growth": 0.05, "forecast_discount_rate": 0.09},
    )

    report = ValuationPipeline().run(sec)  # must not raise

    assert report.ticker == "NANFIELDS"
    assert report.triangulation is not None


# --------------------------------------------------------------------------- #
# 3. Extreme leverage (100x Debt/EBITDA)
# --------------------------------------------------------------------------- #


def test_extreme_100x_leverage_downgrades_conviction_without_crash():
    """100x Debt/EBITDA is far past the 4.0x risk-penalty threshold. The
    penalty must still fire exactly once (one band downgrade), not raise,
    and not produce a runaway/negative confidence band."""
    generator = VerdictGenerator()
    sec = Security(
        ticker="LEV100X",
        fundamentals=Fundamentals(total_debt=10_000.0, ebitda_ttm=100.0),  # 100x
    )
    tri = TriangulationResult(
        verdict="agree",
        confidence=0.9,
        cluster_center=0.25,
        cluster_members=[],
        outliers=[],
        notes=[],
    )
    rel_mock = MagicMock()
    rel_mock.fair_value_to_price = 0.15

    result = generator.generate(tri, rel_mock, sec)

    assert result.rating == "BUY"
    assert result.confidence_band == "MEDIUM"  # downgraded exactly one level from HIGH
    assert any("High leverage detected" in n for n in result.notes)
    assert any("100.0x" in n for n in result.notes)


def test_extreme_100x_leverage_full_pipeline_produces_finite_verdict():
    """The full pipeline on a 100x-levered security must complete and every
    numeric output on the final verdict path must be finite."""
    sec = Security(
        ticker="LEV100X",
        fundamentals=Fundamentals(
            fcf_ttm=2800.0,
            shares_outstanding=1000.0,
            ebitda_ttm=100.0,
            total_debt=10_000.0,  # 100x EBITDA
            revenue_history=[10000, 8500, 7200, 6100, 5200],
        ),
        market=MarketData(price=180),
        qualitative={"forecast_growth": 0.10, "forecast_discount_rate": 0.09},
    )

    report = ValuationPipeline().run(sec)  # must not raise

    assert report.final_verdict is not None
    assert not math.isnan(report.triangulation.confidence)
    assert not math.isinf(report.triangulation.confidence)
    assert report.final_verdict.rating in ("BUY", "SELL", "HOLD", "INCONCLUSIVE")
