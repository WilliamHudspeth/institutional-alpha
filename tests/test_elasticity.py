"""Spec + regression tests for the Durability + Elasticity Scoring Layer.

Two tiers:

  * ``TestMathUtils`` exercises the pure-math helpers and pins the numeric
    primitives.
  * The scorer/engine tests encode the implementation spec from the class
    docstrings in ``iam.elasticity.{durability,elasticity,stress}``. Keep them
    green; do not change the public type signatures without updating them.

Expected values are derived with the same shared helpers the implementation
must use (``two_stage_pv``, ``math_utils``) so the assertions stay exact.
"""

from __future__ import annotations

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.elasticity import (
    DurabilityScorer,
    DurabilityStressEngine,
    ElasticityScorer,
    StressScenario,
)
from iam.elasticity import durability as dur_mod
from iam.elasticity.types import DurabilityScore, ElasticityProfile
from iam.lenses.base import two_stage_pv

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_security(
    *,
    fcf_ttm: float | None = 500.0,
    shares: float | None = 100.0,
    price: float | None = 100.0,
    gross_margin: float | None = None,
    operating_margin: float | None = None,
    operating_margin_history: list[float] | None = None,
    fcf_history: list[float] | None = None,
    qualitative: dict | None = None,
) -> Security:
    f = Fundamentals(
        fcf_ttm=fcf_ttm,
        shares_outstanding=shares,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        operating_margin_history=operating_margin_history or [],
        fcf_history=fcf_history or [],
    )
    m = MarketData(price=price)
    return Security(ticker="TEST", fundamentals=f, market=m, qualitative=qualitative or {})


# ===========================================================================
# Tier 1: math_utils (implemented — should pass immediately)
# ===========================================================================


class TestMathUtils:
    def test_clamp(self):
        from iam.elasticity.math_utils import clamp

        assert clamp(5, 0, 1) == 1
        assert clamp(-5, 0, 1) == 0
        assert clamp(0.5, 0, 1) == 0.5

    def test_mean_and_pstdev(self):
        from iam.elasticity.math_utils import mean, pstdev

        assert mean([]) is None
        assert mean([2, 4]) == pytest.approx(3.0)
        assert pstdev([5]) is None
        assert pstdev([1, 1, 1]) == pytest.approx(0.0)
        assert pstdev([0, 2]) == pytest.approx(1.0)

    def test_coefficient_of_variation(self):
        from iam.elasticity.math_utils import coefficient_of_variation as cv

        assert cv([5]) is None  # too few points
        assert cv([0, 0]) is None  # zero mean
        assert cv([1, 1, 1]) == pytest.approx(0.0)
        # straddling zero still defined via |mean|
        assert cv([-1, 3]) == pytest.approx(pytest.approx(2.0 / 1.0))

    def test_stability_from_series(self):
        from iam.elasticity.math_utils import stability_from_series as stab

        assert stab([5], 1.0) is None
        assert stab([1, 1, 1], 1.0) == pytest.approx(1.0)  # zero dispersion = max stable
        # CV >= scale clamps stability to 0
        assert stab([0.1, 10.0], 0.1) == pytest.approx(0.0)
        # a moderately volatile series lands strictly between 0 and 1
        s = stab([0.20, 0.18, 0.22], 1.0)
        assert s is not None and 0.0 < s < 1.0


# ===========================================================================
# Tier 2: DurabilityScorer (spec — fails until implemented)
# ===========================================================================


class TestDurabilityScorer:
    def test_all_data_missing_returns_none(self):
        result = DurabilityScorer().score(Security(ticker="EMPTY"))
        assert isinstance(result, DurabilityScore)
        assert result.score is None
        assert result.confidence == 0.0

    def test_recurring_only_blend(self):
        # recurring=0.8, no margin/fcf history -> stab = mean(0.5, 0.5) = 0.5
        # score = 0.5*0.8 + 0.5*0.5 = 0.65
        sec = _make_security(qualitative={"recurring_revenue_pct": 0.8})
        result = DurabilityScorer().score(sec)
        assert result.score == pytest.approx(0.65)
        # confidence: 1.0 * 0.6 (no margin hist) * 0.6 (no fcf hist) = 0.36
        assert result.confidence == pytest.approx(0.36)

    def test_score_clamped_to_unit_interval(self):
        sec = _make_security(
            qualitative={"recurring_revenue_pct": 1.0},
            operating_margin_history=[0.30, 0.30, 0.30],
            fcf_history=[100.0, 100.0, 100.0],
        )
        result = DurabilityScorer().score(sec)
        assert result.score is not None
        assert 0.0 <= result.score <= 1.0

    def test_stable_margins_beat_volatile_margins(self):
        common = {"recurring_revenue_pct": 0.5}
        stable = _make_security(
            qualitative=common, operating_margin_history=[0.20, 0.20, 0.21, 0.20]
        )
        volatile = _make_security(
            qualitative=common, operating_margin_history=[0.05, 0.40, 0.02, 0.38]
        )
        s_stable = DurabilityScorer().score(stable)
        s_volatile = DurabilityScorer().score(volatile)
        assert s_stable.score is not None and s_volatile.score is not None
        assert s_stable.score > s_volatile.score

    def test_uses_spec_constants(self):
        # Guard against silent drift of the documented weights.
        assert dur_mod.RECURRING_WEIGHT + dur_mod.STABILITY_WEIGHT == pytest.approx(1.0)


# ===========================================================================
# Tier 2: ElasticityScorer (spec — fails until implemented)
# ===========================================================================


class TestElasticityScorer:
    def test_growth_elasticity_from_operating_leverage(self):
        # opex_ratio = 0.6 - 0.2 = 0.4 -> growth_elasticity = 1.4
        sec = _make_security(gross_margin=0.6, operating_margin=0.2)
        result = ElasticityScorer().profile(sec)
        assert isinstance(result, ElasticityProfile)
        assert result.growth_elasticity == pytest.approx(1.4)

    def test_higher_fixed_cost_raises_growth_elasticity(self):
        low = _make_security(gross_margin=0.5, operating_margin=0.4)  # opex 0.1 -> 1.1
        high = _make_security(gross_margin=0.8, operating_margin=0.1)  # opex 0.7 -> 1.7
        r_low = ElasticityScorer().profile(low)
        r_high = ElasticityScorer().profile(high)
        assert r_high.growth_elasticity > r_low.growth_elasticity

    def test_growth_elasticity_none_when_margins_missing(self):
        sec = _make_security(qualitative={"forecast_growth": 0.0})
        result = ElasticityScorer().profile(sec)
        assert result.growth_elasticity is None
        # rate elasticity still computable -> confidence reduced once (×0.7)
        assert result.confidence == pytest.approx(0.7)

    def test_rate_elasticity_baseline_is_unity_for_zero_growth(self):
        # Baseline is defined as the g=0 stream, so a no-growth name scores 1.0.
        sec = _make_security(
            gross_margin=0.5,
            operating_margin=0.3,
            qualitative={"forecast_growth": 0.0},
        )
        result = ElasticityScorer().profile(sec)
        assert result.rate_elasticity == pytest.approx(1.0, abs=1e-6)
        assert result.confidence == pytest.approx(1.0)

    def test_rate_elasticity_rises_with_duration(self):
        short = _make_security(
            gross_margin=0.5, operating_margin=0.3, qualitative={"forecast_growth": 0.0}
        )
        long = _make_security(
            gross_margin=0.5, operating_margin=0.3, qualitative={"forecast_growth": 0.15}
        )
        r_short = ElasticityScorer().profile(short)
        r_long = ElasticityScorer().profile(long)
        assert r_long.rate_elasticity > r_short.rate_elasticity

    def test_rate_elasticity_clamped(self):
        sec = _make_security(
            gross_margin=0.5, operating_margin=0.3, qualitative={"forecast_growth": 0.30}
        )
        result = ElasticityScorer().profile(sec)
        assert result.rate_elasticity is not None
        assert 0.0 <= result.rate_elasticity <= 3.0


# ===========================================================================
# Tier 2: DurabilityStressEngine (spec — fails until implemented)
# ===========================================================================


class _FixedDurability(DurabilityScorer):
    """Test double: returns a preset durability score."""

    def __init__(self, score: float | None) -> None:
        self._score = score

    def score(self, security):  # type: ignore[override]
        return DurabilityScore(score=self._score, confidence=1.0, narrative="fixed")


class _NullElasticity(ElasticityScorer):
    """Test double: elasticity is irrelevant to the engine's value math."""

    def profile(self, security):  # type: ignore[override]
        return ElasticityProfile(
            growth_elasticity=1.0, rate_elasticity=1.0, confidence=1.0, narrative="fixed"
        )


def _expected_pv(g: float, wacc: float, fcfe0: float) -> float:
    pv = two_stage_pv(fcfe0, g, 10, 0.025, wacc)
    assert pv is not None
    return pv


class TestDurabilityStressEngine:
    def test_reprices_value_under_scenario(self):
        sec = _make_security(fcf_ttm=500.0, shares=100.0)  # fcfe0 = 5.0
        engine = DurabilityStressEngine(_FixedDurability(0.5), _NullElasticity())
        scenario = StressScenario("rate+growth", growth_shock_pct=-0.05, rate_shock_bps=50.0)
        resp = engine.run(sec, scenario)

        fcfe0 = 5.0
        exp_base = _expected_pv(0.08, 0.09, fcfe0)
        exp_stressed = _expected_pv(0.03, 0.095, fcfe0)
        assert resp.base_fair_value == pytest.approx(exp_base)
        assert resp.stressed_fair_value == pytest.approx(exp_stressed)
        assert resp.value_change_pct == pytest.approx(exp_stressed / exp_base - 1)
        assert resp.stressed_fair_value < resp.base_fair_value

    def test_conviction_drift_scales_with_fragility(self):
        sec = _make_security(fcf_ttm=500.0, shares=100.0)
        scenario = StressScenario("down", growth_shock_pct=-0.05, rate_shock_bps=50.0)

        fcfe0 = 5.0
        change = _expected_pv(0.03, 0.095, fcfe0) / _expected_pv(0.08, 0.09, fcfe0) - 1
        raw_loss = max(0.0, -change)

        durable = DurabilityStressEngine(_FixedDurability(0.9), _NullElasticity()).run(sec, scenario)
        fragile = DurabilityStressEngine(_FixedDurability(0.1), _NullElasticity()).run(sec, scenario)

        assert durable.conviction_drift == pytest.approx(raw_loss * (1 - 0.9))
        assert fragile.conviction_drift == pytest.approx(raw_loss * (1 - 0.1))
        assert fragile.conviction_drift > durable.conviction_drift

    def test_unknown_durability_assumed_fragile(self):
        sec = _make_security(fcf_ttm=500.0, shares=100.0)
        scenario = StressScenario("down", growth_shock_pct=-0.05, rate_shock_bps=50.0)
        resp = DurabilityStressEngine(_FixedDurability(None), _NullElasticity()).run(sec, scenario)

        fcfe0 = 5.0
        change = _expected_pv(0.03, 0.095, fcfe0) / _expected_pv(0.08, 0.09, fcfe0) - 1
        raw_loss = max(0.0, -change)
        # fragility treated as 1.0 -> drift == raw_loss
        assert resp.conviction_drift == pytest.approx(raw_loss)

    def test_upside_scenario_has_zero_drift(self):
        sec = _make_security(fcf_ttm=500.0, shares=100.0)
        # falling rates + faster growth -> value rises -> no conviction loss
        scenario = StressScenario("up", growth_shock_pct=0.02, rate_shock_bps=-50.0)
        resp = DurabilityStressEngine(_FixedDurability(0.5), _NullElasticity()).run(sec, scenario)
        assert resp.value_change_pct is not None and resp.value_change_pct > 0
        assert resp.conviction_drift == pytest.approx(0.0)

    def test_integration_with_real_scorers(self):
        sec = _make_security(
            fcf_ttm=500.0,
            shares=100.0,
            gross_margin=0.6,
            operating_margin=0.2,
            operating_margin_history=[0.20, 0.20, 0.21],
            fcf_history=[500.0, 480.0, 510.0],
            qualitative={"recurring_revenue_pct": 0.7, "forecast_growth": 0.08},
        )
        resp = DurabilityStressEngine().run(
            sec, StressScenario("down", growth_shock_pct=-0.05, rate_shock_bps=50.0)
        )
        assert resp.durability.score is not None
        assert resp.elasticity.growth_elasticity is not None
        assert resp.conviction_drift is not None
        assert 0.0 <= resp.conviction_drift <= 1.0
        assert resp.narrative  # non-empty plain-English summary
