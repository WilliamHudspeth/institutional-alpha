"""Tests for the portfolio module: Kelly sizing, risk parity, sector
rotation, and macro hedge recommendations.

Follows the table-driven pattern established by ``tests/test_elasticity.py``
and ``tests/test_weight_optimizer.py``: named scenarios, edge-case coverage,
``pytest.approx`` for float comparisons.
"""

from __future__ import annotations

import numpy as np
import pytest

from iam.elasticity.types import ElasticityProfile
from iam.pipeline.macro_regimes import MacroRegime, MacroRegimeAssessment, MacroShock
from iam.portfolio import (
    HedgeRecommendation,
    MacroHedgeEngine,
    PositionSizer,
    SectorRotationEngine,
)
from iam.portfolio.optimizer import OptimizationConstraints
from iam.portfolio.types import Portfolio, Position

# ===========================================================================
# Test helpers
# ===========================================================================

_DEFAULT_CONSTRAINTS = OptimizationConstraints(
    min_position_size=0.01, max_position_size=0.15, target_gross_exposure=1.0
)


def _approx_weights(expected: dict[str, float]) -> dict[str, float]:
    return {k: pytest.approx(v, abs=1e-4) for k, v in expected.items()}


# ===========================================================================
# Feature 1: Kelly Criterion Position Sizing
# ===========================================================================


class TestKellySizing:
    """PositionSizer.size_by_kelly() — continuous Kelly with fractional Kelly
    safety, following the same constraint-application pattern as the other
    size_by_* methods."""

    def test_half_kelly_positive_expected_return(self):
        """μ=0.10, σ=0.20 → f* = 0.10/0.04 = 2.5, half-Kelly = 1.25.
        With a single position, the raw Kelly normalises to 1.0, then
        min/max clamps, then renormalises to target_gross_exposure=1.0.
        """
        result = PositionSizer.size_by_kelly(
            tickers=["A"],
            expected_returns={"A": 0.10},
            volatilities={"A": 0.20},
            kelly_fraction=0.5,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        # Single position — always 1.0 after normalisation
        assert result["A"] == pytest.approx(1.0)

    def test_multiple_positions_relative_sizing(self):
        """Two positions with different Sharpe ratios get different weights.
        Use relaxed constraints so normalised Kelly fractions pass through
        without all hitting the max cap.
        """
        relaxed = OptimizationConstraints(
            min_position_size=0.01, max_position_size=0.90, target_gross_exposure=1.0
        )
        result = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": 0.10, "B": 0.05},
            volatilities={"A": 0.20, "B": 0.20},
            kelly_fraction=0.5,
            constraints=relaxed,
        )
        assert result["A"] > result["B"]

    def test_negative_expected_return_clamped(self):
        """Position with negative expected return gets 0 raw Kelly weight.
        After normalisation and clamping it should appear at min_position_size.
        """
        result = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": 0.10, "B": -0.05},
            volatilities={"A": 0.20, "B": 0.20},
            kelly_fraction=0.5,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        # B has negative expected return → 0 raw Kelly → min_position_size after clamp
        assert result["B"] >= _DEFAULT_CONSTRAINTS.min_position_size
        assert result["A"] > result["B"]

    def test_zero_volatility_fallback(self):
        """Zero vol should not cause division by zero; falls back to equal
        weight.
        """
        result = PositionSizer.size_by_kelly(
            tickers=["A"],
            expected_returns={"A": 0.10},
            volatilities={"A": 0.0},
            kelly_fraction=0.5,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert result["A"] == pytest.approx(1.0)

    def test_all_negative_returns_equal_fallback(self):
        """All positions have negative expected returns → all get 0 raw Kelly
        → fallback to equal weights.
        """
        result = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": -0.05, "B": -0.03},
            volatilities={"A": 0.20, "B": 0.25},
            kelly_fraction=0.5,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert result["A"] == pytest.approx(0.5)
        assert result["B"] == pytest.approx(0.5)

    def test_kelly_fraction_affects_relative_weights(self):
        """Position with μ=0 (min_position_size after clamp) gets more
        relative weight with smaller kelly_fraction because the
        positive-Kelly positions are scaled down before normalisation.
        """
        high_kelly = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": 0.10, "B": 0.0},
            volatilities={"A": 0.20, "B": 0.20},
            kelly_fraction=1.0,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        low_kelly = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": 0.10, "B": 0.0},
            volatilities={"A": 0.20, "B": 0.20},
            kelly_fraction=0.1,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        # With lower kelly_fraction, B gets relatively MORE weight
        assert high_kelly["A"] >= low_kelly["A"]

    def test_constraints_applied(self):
        """Very tight max_position_size clamps the unnormalised weights,
        and the renormalisation preserves the constraint violation to
        avoid extreme concentration on a single name.
        """
        tight = OptimizationConstraints(
            min_position_size=0.01, max_position_size=0.05, target_gross_exposure=1.0
        )
        result = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": 0.20, "B": 0.10},
            volatilities={"A": 0.10, "B": 0.20},
            kelly_fraction=1.0,
            constraints=tight,
        )
        # Both positions hit the cap → after renormalisation both ≈ 0.5.
        # The clamp prevents one from dominating.
        assert result["A"] == pytest.approx(0.5)
        assert result["B"] == pytest.approx(0.5)

    def test_single_position(self):
        """Single position always normalises to 1.0."""
        result = PositionSizer.size_by_kelly(
            tickers=["X"],
            expected_returns={"X": 0.08},
            volatilities={"X": 0.25},
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert result["X"] == pytest.approx(1.0)

    def test_missing_ticker_defaults(self):
        """Tickers not present in expected_returns/volatilities get defaults
        (0.0 expected return, 0.20 vol) and thus 0 raw Kelly weight.
        """
        result = PositionSizer.size_by_kelly(
            tickers=["A", "B"],
            expected_returns={"A": 0.10},
            volatilities={"A": 0.20},
            kelly_fraction=0.5,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        # B has defaults: μ=0 → 0 raw Kelly → will be at min_position_size
        assert result["B"] >= _DEFAULT_CONSTRAINTS.min_position_size
        assert result["A"] > result["B"]


# ===========================================================================
# Feature 2: Real Risk Parity (Equal Risk Contribution)
# ===========================================================================


class TestRiskParity:
    """PositionSizer.size_by_risk_parity() — solves for equal risk
    contribution using Ledoit-Wolf covariance and scipy SLSQP."""

    def test_fallback_below_min_assets(self):
        """Fewer than MIN_RISK_PARITY_ASSETS (3) falls back to inverse-vol."""
        result = PositionSizer.size_by_risk_parity(
            tickers=["A", "B"],
            position_returns={
                "A": [0.01, -0.02, 0.03],
                "B": [-0.01, 0.02, -0.01],
            },
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert len(result) == 2
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_three_equal_vol_uncorrelated(self):
        """Three uncorrelated equal-vol positions → roughly equal weights."""
        rng = np.random.RandomState(42)
        returns = {f"X{i}": list(rng.randn(50) * 0.02) for i in range(3)}
        result = PositionSizer.size_by_risk_parity(
            tickers=list(returns.keys()),
            position_returns=returns,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert len(result) == 3
        weights = list(result.values())
        # All weights should be roughly equal for i.i.d. data
        assert max(weights) - min(weights) < 0.15

    def test_one_high_vol_gets_lower_weight(self):
        """Position with much higher vol should get lower weight."""
        rng = np.random.RandomState(42)
        returns = {
            "LowVol": list(rng.randn(50) * 0.01),
            "HighVol": list(rng.randn(50) * 0.05),
            "MidVol": list(rng.randn(50) * 0.02),
        }
        result = PositionSizer.size_by_risk_parity(
            tickers=list(returns.keys()),
            position_returns=returns,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert result["HighVol"] < result["LowVol"]

    def test_single_ticker_fallback(self):
        """Single ticker falls back to inverse-vol (min-assets guard)."""
        result = PositionSizer.size_by_risk_parity(
            tickers=["A"],
            position_returns={"A": [0.01, -0.02, 0.03]},
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert result["A"] == pytest.approx(1.0)

    def test_fewer_than_two_observations_fallback(self):
        """Too few observations triggers fallback."""
        result = PositionSizer.size_by_risk_parity(
            tickers=["A", "B", "C"],
            position_returns={"A": [0.01], "B": [-0.01], "C": [0.02]},
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert len(result) == 3
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_weights_sum_to_one(self):
        """Resulting weights should sum to target_gross_exposure."""
        rng = np.random.RandomState(42)
        returns = {f"X{i}": list(rng.randn(60) * 0.02) for i in range(5)}
        result = PositionSizer.size_by_risk_parity(
            tickers=list(returns.keys()),
            position_returns=returns,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        assert sum(result.values()) == pytest.approx(1.0, abs=1e-4)

    def test_all_weights_non_negative(self):
        """All weights should be non-negative (bounded by scipy)."""
        rng = np.random.RandomState(42)
        returns = {f"X{i}": list(rng.randn(60) * 0.02) for i in range(4)}
        result = PositionSizer.size_by_risk_parity(
            tickers=list(returns.keys()),
            position_returns=returns,
            constraints=_DEFAULT_CONSTRAINTS,
        )
        for w in result.values():
            assert w >= 0

    def test_constraints_applied(self):
        """Constraints are accepted and applied (min/max clamping + renormalisation)."""
        tight = OptimizationConstraints(
            min_position_size=0.02, max_position_size=0.50, target_gross_exposure=1.0
        )
        rng = np.random.RandomState(42)
        returns = {f"X{i}": list(rng.randn(60) * 0.02) for i in range(4)}
        result = PositionSizer.size_by_risk_parity(
            tickers=list(returns.keys()),
            position_returns=returns,
            constraints=tight,
        )
        assert len(result) == 4
        assert sum(result.values()) == pytest.approx(1.0, abs=1e-4)
        for w in result.values():
            assert w >= tight.min_position_size - 1e-4


# ===========================================================================
# Feature 3: Sector Rotation Framework
# ===========================================================================


class TestSectorRotation:
    """SectorRotationEngine.recommend_sector_tilts() — regime-aware sector
    rotation with momentum blend."""

    def test_tightening_favors_financials_energy(self):
        """Tightening regime tilts toward Financials/Energy, away from
        Technology/Utilities."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="tightening",
            sector_momentum={},
        )
        assert tilts.get("Financials", 0) > 0
        assert tilts.get("Energy", 0) > 0
        assert tilts.get("Technology", 0) < 0
        assert tilts.get("Utilities", 0) < 0

    def test_easing_favors_tech_consumer_discretionary(self):
        """Easing regime tilts toward Technology/Consumer Discretionary."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="easing",
            sector_momentum={},
        )
        assert tilts.get("Technology", 0) > 0
        assert tilts.get("Consumer Discretionary", 0) > 0
        assert tilts.get("Financials", 0) < 0

    def test_stagflation_favors_energy_utilities_staples(self):
        """Stagflation tilts toward defensives and energy."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="stagflation",
            sector_momentum={},
        )
        assert tilts.get("Energy", 0) > 0
        assert tilts.get("Utilities", 0) > 0
        assert tilts.get("Consumer Staples", 0) > 0
        assert tilts.get("Technology", 0) < 0

    def test_neutral_regime(self):
        """Neutral regime has no regime-driven tilts."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="neutral",
            sector_momentum={},
        )
        assert tilts == {}

    def test_momentum_blend(self):
        """Momentum signal is blended with regime signal."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="neutral",
            sector_momentum={"Technology": 0.05, "Utilities": -0.03},
        )
        assert tilts.get("Technology", 0) > 0  # positive momentum
        assert tilts.get("Utilities", 0) < 0  # negative momentum

    def test_momentum_noise_below_floor_ignored(self):
        """Momentum below MOMENTUM_SIGNAL_FLOOR (0.005) is treated as noise."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="neutral",
            sector_momentum={"Technology": 0.003, "Utilities": -0.002},
        )
        assert "Technology" not in tilts
        assert "Utilities" not in tilts

    def test_tilt_clamping(self):
        """Max sector tilt should not exceed MAX_SECTOR_TILT (0.08)."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="tightening",
            sector_momentum={"Financials": 0.10},  # extreme momentum
        )
        for v in tilts.values():
            assert abs(v) <= 0.08 + 1e-6

    def test_unknown_regime(self):
        """Unknown regime uses only momentum signal."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="unknown",
            sector_momentum={"Technology": 0.04},
        )
        assert tilts.get("Technology", 0) > 0

    def test_empty_inputs(self):
        """Empty regime and empty momentum → empty result."""
        tilts = SectorRotationEngine.recommend_sector_tilts(
            regime="",
            sector_momentum={},
        )
        assert tilts == {}


# ===========================================================================
# Feature 4: Macro Hedge Recommendations
# ===========================================================================


def _make_position(ticker: str, weight: float, sector: str | None = None) -> Position:
    return Position(
        ticker=ticker,
        name=ticker,
        quantity=100,
        entry_price=50.0,
        current_price=100.0,
        weight=weight,
        sector=sector,
    )


def _make_elasticity(
    growth: float | None = None,
    rate: float | None = None,
) -> ElasticityProfile:
    return ElasticityProfile(
        growth_elasticity=growth,
        rate_elasticity=rate,
        confidence=1.0,
    )


def _neutral_regime() -> MacroRegimeAssessment:
    return MacroRegimeAssessment(
        regime=MacroRegime.NEUTRAL,
        shock=MacroShock(name="Neutral", rate_shock_bps=0.0, growth_shock_pct=0.0, inflation_shock_pct=0.0),
        wacc_premium=0.0,
        shock_multiplier=1.0,
    )


class TestMacroHedge:
    """MacroHedgeEngine.recommend_hedges() — elasticity-driven hedge
    recommendations."""

    def test_high_rate_elasticity_triggers_duration_hedge(self):
        """Portfolio with high aggregate rate elasticity gets a duration
        hedge recommendation."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.0, rate=2.5),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        assert len(hedges) >= 1
        types = {h.instrument_type for h in hedges}
        assert "duration_hedge" in types

    def test_high_growth_elasticity_triggers_index_put(self):
        """Portfolio with high aggregate growth elasticity gets an index
        put recommendation."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.8, rate=1.0),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        assert len(hedges) >= 1
        types = {h.instrument_type for h in hedges}
        assert "index_put" in types

    def test_low_elasticity_no_hedges(self):
        """Portfolio with low elasticity gets no hedge recommendations."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.0, rate=1.0),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        assert len(hedges) == 0

    def test_missing_elasticity_degrades_gracefully(self):
        """Missing elasticity data → empty recommendations."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        hedges = MacroHedgeEngine.recommend_hedges(portfolio, {}, _neutral_regime())
        assert len(hedges) == 0

    def test_easing_discounts_duration_hedge(self):
        """During easing regime, duration hedge size is discounted."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.0, rate=2.5),
        }
        easing_regime = MacroRegimeAssessment(
            regime=MacroRegime.EASING,
            shock=MacroShock(name="Easing", rate_shock_bps=-50.0, growth_shock_pct=0.02, inflation_shock_pct=0.0),
            wacc_premium=-0.005,
            shock_multiplier=1.0,
        )
        hedges_easing = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, easing_regime
        )
        hedges_neutral = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        # Easing regime should reduce the hedge size
        for h_e in hedges_easing:
            for h_n in hedges_neutral:
                if h_e.instrument_type == h_n.instrument_type:
                    assert h_e.suggested_size_pct < h_n.suggested_size_pct

    def test_multiple_hedges_possible(self):
        """Portfolio with both high rate AND growth elasticity gets both
        hedge types."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.8, rate=2.5),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        types = {h.instrument_type for h in hedges}
        assert "duration_hedge" in types
        assert "index_put" in types

    def test_hedge_sizing_formula(self):
        """Hedge size should follow the documented formula."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        # rate_el = 2.5, threshold = 1.5, excess = 1.0
        # size = 0.05 + 1.0 * 0.03 = 0.08 = 8%
        positions_elasticity = {
            "A": _make_elasticity(growth=1.0, rate=2.5),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        duration_hedges = [h for h in hedges if h.instrument_type == "duration_hedge"]
        assert len(duration_hedges) == 1
        assert duration_hedges[0].suggested_size_pct == pytest.approx(8.0, abs=0.5)

    def test_single_position(self):
        """Single position with high elasticity works."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.5, rate=1.0),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        assert len(hedges) >= 1

    def test_mixed_elasticity_data(self):
        """Some positions have elasticity, some don't — engine handles
        gracefully."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=0.6),
                _make_position("B", weight=0.4),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.0, rate=2.5),
            # B has no elasticity data
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        # Should still recommend based on A's data (weighted by 0.6)
        assert len(hedges) >= 1

    def test_output_format(self):
        """HedgeRecommendation has the expected fields."""
        portfolio = Portfolio(
            positions=[
                _make_position("A", weight=1.0),
            ]
        )
        positions_elasticity = {
            "A": _make_elasticity(growth=1.8, rate=2.5),
        }
        hedges = MacroHedgeEngine.recommend_hedges(
            portfolio, positions_elasticity, _neutral_regime()
        )
        for h in hedges:
            assert isinstance(h, HedgeRecommendation)
            assert isinstance(h.instrument_type, str)
            assert isinstance(h.rationale, str)
            assert isinstance(h.suggested_size_pct, float)
            assert h.suggested_size_pct > 0
