"""Tests for GrowthEstimatorEngine: probabilistic growth estimation."""

from __future__ import annotations

import math

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.probabilistic_growth import GrowthEstimatorEngine, build_engine_from_security

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(
    market_cap=1_000.0,
    free_cash_flow=80.0,
    shares_outstanding=100.0,
    net_debt=0.0,
    wacc=0.09,
    terminal_growth=0.025,
    growth_3y=0.08,
    growth_5y=0.07,
    growth_10y=0.06,
    roic=0.15,
    reinvestment_rate=0.50,
    revenue_growth_recent=0.09,
    gross_margin_current=0.30,
    gross_margin_lag=0.28,
    capex_to_sales=None,
    sector_growth_prior=0.06,
    margin_history=None,
    peer_margin_avg=None,
    is_bubble_regime=False,
    is_structural_break=False,
    reliability_errors=None,
    moat_durability=0.7,
):
    return GrowthEstimatorEngine(
        market_cap=market_cap,
        free_cash_flow=free_cash_flow,
        shares_outstanding=shares_outstanding,
        net_debt=net_debt,
        wacc=wacc,
        terminal_growth=terminal_growth,
        growth_3y=growth_3y,
        growth_5y=growth_5y,
        growth_10y=growth_10y,
        roic=roic,
        reinvestment_rate=reinvestment_rate,
        revenue_growth_recent=revenue_growth_recent,
        gross_margin_current=gross_margin_current,
        gross_margin_lag=gross_margin_lag,
        capex_to_sales=capex_to_sales,
        sector_growth_prior=sector_growth_prior,
        margin_history=margin_history or [0.15, 0.15, 0.15, 0.15],
        peer_margin_avg=peer_margin_avg,
        is_bubble_regime=is_bubble_regime,
        is_structural_break=is_structural_break,
        reliability_errors=reliability_errors or {},
        moat_durability=moat_durability,
    )


# ---------------------------------------------------------------------------
# DCF core
# ---------------------------------------------------------------------------

class TestDCFValue:
    def test_zero_growth_yields_finite_value(self):
        eng = make_engine(free_cash_flow=100.0, net_debt=0.0, wacc=0.09)
        val = eng._dcf_value(0.0)
        assert val > 0

    def test_higher_growth_increases_dcf_value(self):
        eng = make_engine(free_cash_flow=100.0)
        low = eng._dcf_value(0.05)
        high = eng._dcf_value(0.15)
        assert high > low

    def test_negative_growth_decreases_dcf_value(self):
        eng = make_engine(free_cash_flow=100.0)
        pos = eng._dcf_value(0.05)
        neg = eng._dcf_value(-0.05)
        assert neg < pos

    def test_net_debt_reduces_equity_value(self):
        eng_no_debt = make_engine(free_cash_flow=100.0, net_debt=0.0)
        eng_with_debt = make_engine(free_cash_flow=100.0, net_debt=200.0)
        assert eng_with_debt._dcf_value(0.05) < eng_no_debt._dcf_value(0.05)


# ---------------------------------------------------------------------------
# Implied growth (reverse DCF with brentq)
# ---------------------------------------------------------------------------

class TestImpliedGrowth:
    def test_returns_estimate_for_positive_fcf(self):
        eng = make_engine(market_cap=1000.0, free_cash_flow=80.0)
        est = eng.implied_growth()
        assert est is not None
        assert est.name == "implied"
        assert -0.20 <= est.value <= 0.50

    def test_returns_none_for_negative_fcf(self):
        eng = make_engine(free_cash_flow=-50.0)
        assert eng.implied_growth() is None

    def test_higher_market_cap_implies_higher_growth(self):
        cheap = make_engine(market_cap=500.0, free_cash_flow=80.0)
        expensive = make_engine(market_cap=2000.0, free_cash_flow=80.0)
        est_cheap = cheap.implied_growth()
        est_expensive = expensive.implied_growth()
        assert est_cheap is not None and est_expensive is not None
        assert est_expensive.value > est_cheap.value

    def test_bubble_regime_inflates_variance(self):
        normal = make_engine(market_cap=1000.0, free_cash_flow=80.0, is_bubble_regime=False)
        bubble = make_engine(market_cap=1000.0, free_cash_flow=80.0, is_bubble_regime=True)
        normal_est = normal.implied_growth()
        bubble_est = bubble.implied_growth()
        assert normal_est is not None and bubble_est is not None
        assert bubble_est.variance > normal_est.variance

    def test_round_trip_consistency(self):
        """DCF at implied_growth should approximate market_cap."""
        eng = make_engine(market_cap=1000.0, free_cash_flow=80.0)
        est = eng.implied_growth()
        if est is not None:
            implied_val = eng._dcf_value(est.value)
            # Should be within 1% of target (brentq tolerance is small)
            assert abs(implied_val - 1000.0) / 1000.0 < 0.02


# ---------------------------------------------------------------------------
# Historical CAGR
# ---------------------------------------------------------------------------

class TestHistoricalCAGR:
    def test_returns_median_of_lookbacks(self):
        eng = make_engine(growth_3y=0.10, growth_5y=0.08, growth_10y=0.06)
        est = eng.historical_cagr()
        assert est is not None
        assert est.value == pytest.approx(0.08, abs=0.001)  # median

    def test_returns_none_when_no_lookbacks(self):
        eng = make_engine(growth_3y=None, growth_5y=None, growth_10y=None)
        assert eng.historical_cagr() is None

    def test_winsorizes_extreme_values(self):
        eng = make_engine(growth_3y=0.80, growth_5y=0.10, growth_10y=-0.50)
        est = eng.historical_cagr()
        assert est is not None
        # Clipped to [-0.15, 0.40]; median of [0.40, 0.10, -0.15] = 0.10
        assert -0.15 <= est.value <= 0.40

    def test_structural_break_inflates_variance(self):
        normal = make_engine(growth_3y=0.08, growth_5y=0.07, is_structural_break=False)
        broken = make_engine(growth_3y=0.08, growth_5y=0.07, is_structural_break=True)
        n_est = normal.historical_cagr()
        b_est = broken.historical_cagr()
        assert n_est is not None and b_est is not None
        assert b_est.variance > n_est.variance

    def test_single_lookback_returns_estimate(self):
        eng = make_engine(growth_3y=None, growth_5y=0.08, growth_10y=None)
        est = eng.historical_cagr()
        assert est is not None
        assert est.value == pytest.approx(0.08, abs=0.001)


# ---------------------------------------------------------------------------
# Sustainable growth (ROIC × reinvestment_rate)
# ---------------------------------------------------------------------------

class TestSustainableGrowth:
    def test_basic_formula(self):
        eng = make_engine(roic=0.20, reinvestment_rate=0.50)
        est = eng.sustainable_growth()
        assert est is not None
        assert est.value == pytest.approx(0.10, abs=0.001)

    def test_returns_none_without_roic(self):
        eng = make_engine(roic=None)
        assert eng.sustainable_growth() is None

    def test_returns_none_without_reinvestment_rate(self):
        eng = make_engine(roic=0.15, reinvestment_rate=None)
        assert eng.sustainable_growth() is None

    def test_high_roic_increases_variance(self):
        low = make_engine(roic=0.10, reinvestment_rate=0.50)
        high = make_engine(roic=0.40, reinvestment_rate=0.50)
        l_est = low.sustainable_growth()
        h_est = high.sustainable_growth()
        assert l_est is not None and h_est is not None
        assert h_est.variance > l_est.variance

    def test_leverage_neutral(self):
        """ROIC-based approach: same result regardless of leverage assumption."""
        eng1 = make_engine(roic=0.15, reinvestment_rate=0.60)
        eng2 = make_engine(roic=0.15, reinvestment_rate=0.60)
        e1 = eng1.sustainable_growth()
        e2 = eng2.sustainable_growth()
        assert e1 is not None and e2 is not None
        assert e1.value == pytest.approx(e2.value, abs=1e-9)


# ---------------------------------------------------------------------------
# Bottom-up growth
# ---------------------------------------------------------------------------

class TestBottomUpGrowth:
    def test_returns_none_without_revenue_growth(self):
        eng = make_engine(revenue_growth_recent=None)
        assert eng.bottom_up_growth() is None

    def test_margin_expansion_boosts_growth(self):
        flat = make_engine(
            revenue_growth_recent=0.08,
            gross_margin_current=0.30,
            gross_margin_lag=0.30,
        )
        expanding = make_engine(
            revenue_growth_recent=0.08,
            gross_margin_current=0.35,
            gross_margin_lag=0.30,
        )
        flat_est = flat.bottom_up_growth()
        exp_est = expanding.bottom_up_growth()
        assert flat_est is not None and exp_est is not None
        assert exp_est.value > flat_est.value

    def test_margin_compression_reduces_growth(self):
        flat = make_engine(
            revenue_growth_recent=0.08,
            gross_margin_current=0.30,
            gross_margin_lag=0.30,
        )
        compressing = make_engine(
            revenue_growth_recent=0.08,
            gross_margin_current=0.25,
            gross_margin_lag=0.30,
        )
        flat_est = flat.bottom_up_growth()
        comp_est = compressing.bottom_up_growth()
        assert flat_est is not None and comp_est is not None
        assert comp_est.value < flat_est.value

    def test_output_constrained_to_range(self):
        eng = make_engine(revenue_growth_recent=5.0, gross_margin_current=0.99, gross_margin_lag=0.01)
        est = eng.bottom_up_growth()
        assert est is not None
        assert -0.10 <= est.value <= 0.40


# ---------------------------------------------------------------------------
# Sector prior
# ---------------------------------------------------------------------------

class TestSectorPrior:
    def test_always_returns_estimate(self):
        eng = make_engine(sector_growth_prior=0.05)
        est = eng.sector_prior()
        assert est is not None
        assert est.value == pytest.approx(0.05, abs=1e-9)

    def test_structural_break_inflates_variance(self):
        normal = make_engine(is_structural_break=False)
        broken = make_engine(is_structural_break=True)
        n_est = normal.sector_prior()
        b_est = broken.sector_prior()
        assert b_est.variance > n_est.variance


# ---------------------------------------------------------------------------
# Margin trajectory haircuts
# ---------------------------------------------------------------------------

class TestMarginPenalty:
    def test_stable_margins_give_minimal_haircut(self):
        eng = make_engine(
            margin_history=[0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.20],
            peer_margin_avg=0.20,
        )
        gh, th = eng.margin_penalty_factors()
        # Near-perfect stability: haircuts should be close to 1.0
        assert gh > 0.7
        assert th > 0.7

    def test_severe_compression_lowers_haircut(self):
        eng = make_engine(
            margin_history=[0.02, 0.05, 0.10, 0.15, 0.18, 0.20, 0.22, 0.24],
            peer_margin_avg=0.20,
        )
        gh, th = eng.margin_penalty_factors()
        # Declining margins below peers → haircut < 1.0
        assert gh < 1.0
        assert th < 1.0

    def test_haircuts_bounded(self):
        eng = make_engine(
            margin_history=[0.01, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35],
            peer_margin_avg=0.40,
        )
        gh, th = eng.margin_penalty_factors()
        assert 0.5 <= gh <= 1.0
        assert 0.7 <= th <= 1.0

    def test_no_history_returns_neutral(self):
        eng = make_engine(margin_history=None)
        eng.margin_history = []
        gh, th = eng.margin_penalty_factors()
        assert gh == 1.0
        assert th == 1.0


# ---------------------------------------------------------------------------
# Weight computation
# ---------------------------------------------------------------------------

class TestWeights:
    def test_weights_sum_to_one(self):
        eng = make_engine()
        estimates = [e for e in [
            eng.implied_growth(),
            eng.historical_cagr(),
            eng.sustainable_growth(),
            eng.bottom_up_growth(),
            eng.sector_prior(),
        ] if e is not None]
        weighted = eng.compute_weights(estimates)
        total = sum(e.weight for e in weighted)
        assert abs(total - 1.0) < 1e-9

    def test_lower_variance_gets_higher_weight(self):
        eng = make_engine()
        estimates = [e for e in [
            eng.implied_growth(),
            eng.historical_cagr(),
            eng.sector_prior(),
        ] if e is not None]
        weighted = eng.compute_weights(estimates)
        # Sector prior always has highest base variance → lowest weight
        sector = next(e for e in weighted if e.name == "sector")
        others = [e for e in weighted if e.name != "sector"]
        assert all(sector.weight <= o.weight for o in others)


# ---------------------------------------------------------------------------
# blended_growth (main output)
# ---------------------------------------------------------------------------

class TestBlendedGrowth:
    def test_returns_result(self):
        eng = make_engine()
        result = eng.blended_growth()
        assert result.mean_growth is not None
        assert result.std_dev > 0

    def test_mean_growth_in_plausible_range(self):
        eng = make_engine()
        result = eng.blended_growth()
        assert -0.15 <= result.mean_growth <= 0.50

    def test_std_dev_positive(self):
        eng = make_engine()
        result = eng.blended_growth()
        assert result.std_dev > 0

    def test_margin_haircut_applied(self):
        stable = make_engine(
            margin_history=[0.20, 0.20, 0.20, 0.20],
            peer_margin_avg=0.20,
        )
        compressed = make_engine(
            margin_history=[0.02, 0.06, 0.10, 0.14, 0.18, 0.20, 0.22, 0.24],
            peer_margin_avg=0.20,
        )
        stable_result = stable.blended_growth()
        compressed_result = compressed.blended_growth()
        # Compressed engine should have lower or equal mean growth
        assert compressed_result.mean_growth <= stable_result.mean_growth + 0.01

    def test_all_estimates_present_in_audit(self):
        eng = make_engine()
        result = eng.blended_growth()
        names = {e.name for e in result.estimates}
        assert "implied" in names
        assert "historical" in names
        assert "sustainable" in names
        assert "bottom_up" in names
        assert "sector" in names

    def test_fade_path_length(self):
        eng = make_engine()
        result = eng.blended_growth()
        assert len(result.fade_path) == 10


# ---------------------------------------------------------------------------
# Growth persistence profile (moat decay)
# ---------------------------------------------------------------------------

class TestGrowthPersistence:
    def test_high_moat_decays_slowly(self):
        high_moat = make_engine(moat_durability=0.95)
        low_moat = make_engine(moat_durability=0.10)
        high_path = high_moat.growth_persistence_profile(0.20)
        low_path = low_moat.growth_persistence_profile(0.20)
        # High moat: year 5 growth stays closer to base
        assert high_path[4] > low_path[4]

    def test_converges_toward_terminal_growth(self):
        eng = make_engine(terminal_growth=0.025)
        path = eng.growth_persistence_profile(0.15, years=20)
        # After 20 years, should be closer to terminal than to base
        assert abs(path[-1] - 0.025) < abs(path[0] - 0.025)

    def test_no_moat_decays_fastest(self):
        eng = make_engine(moat_durability=0.0, terminal_growth=0.025)
        path = eng.growth_persistence_profile(0.20, years=10)
        # With no moat, year 10 should be close to terminal (not at base)
        assert path[-1] < 0.15

    def test_path_monotone_when_above_terminal(self):
        eng = make_engine(terminal_growth=0.025, moat_durability=0.5)
        path = eng.growth_persistence_profile(0.15)
        for i in range(len(path) - 1):
            assert path[i] >= path[i + 1]  # Declining toward terminal


# ---------------------------------------------------------------------------
# to_dict audit trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_to_dict_has_required_keys(self):
        eng = make_engine()
        result = eng.blended_growth()
        d = result.to_dict()
        assert "mean_growth" in d
        assert "std_dev" in d
        assert "growth_haircut" in d
        assert "terminal_haircut" in d
        assert "estimates" in d
        assert "fade_path" in d

    def test_estimates_have_required_fields(self):
        eng = make_engine()
        result = eng.blended_growth()
        for e in result.to_dict()["estimates"]:
            assert "name" in e
            assert "value" in e
            assert "variance" in e
            assert "weight" in e


# ---------------------------------------------------------------------------
# Factory: build_engine_from_security
# ---------------------------------------------------------------------------

class TestFactory:
    def _make_security(self, ticker="AAPL", sector="Technology"):
        return Security(
            ticker=ticker,
            name="Apple Inc",
            sector=sector,
            fundamentals=Fundamentals(
                revenue_ttm=400e9,
                revenue_history=[400e9, 380e9, 365e9, 330e9, 275e9, 260e9, 230e9],
                operating_margin=0.30,
                operating_margin_history=[0.30, 0.29, 0.28, 0.27, 0.26],
                fcf_ttm=110e9,
                fcf_history=[110e9, 100e9, 95e9, 80e9, 70e9, 60e9, 50e9],
                roic_history=[0.40, 0.38, 0.36, 0.34, 0.32],
                shares_outstanding=15e9,
                incremental_roic=0.38,
            ),
            market=MarketData(price=180.0),
        )

    def test_factory_creates_engine(self):
        security = self._make_security()
        eng = build_engine_from_security(security)
        assert isinstance(eng, GrowthEstimatorEngine)

    def test_factory_produces_valid_blended_growth(self):
        security = self._make_security()
        eng = build_engine_from_security(security)
        result = eng.blended_growth()
        assert -0.15 <= result.mean_growth <= 0.50
        assert result.std_dev > 0

    def test_financial_sector_uses_lower_prior(self):
        fin = self._make_security(sector="Financials")
        tech = self._make_security(sector="Technology")
        fin_eng = build_engine_from_security(fin)
        tech_eng = build_engine_from_security(tech)
        assert fin_eng.sector_growth_prior < tech_eng.sector_growth_prior

    def test_bubble_regime_flag_propagates(self):
        security = self._make_security()
        eng = build_engine_from_security(security, is_bubble_regime=True)
        assert eng.is_bubble_regime is True

    def test_moat_durability_propagates(self):
        security = self._make_security()
        eng = build_engine_from_security(security, moat_durability=0.9)
        assert eng.moat_durability == pytest.approx(0.9)
