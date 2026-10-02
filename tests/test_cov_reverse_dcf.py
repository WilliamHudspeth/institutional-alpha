"""Behavioural tests for valuation.reverse_dcf."""

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.reverse_dcf import (
    ReverseDCF,
    _present_value_two_stage,
    _solve_implied_growth,
)
from iam.valuation.types import Method


def _sec(price=100.0, ni=1000.0, shares=100.0, hist=None, **kw) -> Security:
    return Security(
        ticker="R",
        market=MarketData(price=price, beta=kw.pop("beta", None)),
        fundamentals=Fundamentals(
            net_income_ttm=ni,
            shares_outstanding=shares,
            revenue_history=hist or [],
        ),
        **kw,
    )


class TestPresentValue:
    def test_non_convergent_returns_inf(self):
        assert _present_value_two_stage(1.0, 0.05, 5, 0.09, 0.09, 0.15) == float("inf")

    def test_zero_growth_matches_closed_form(self):
        # g_high = g_term = 0 -> perpetuity of base_ni at rate r (ERR = 0)
        pv = _present_value_two_stage(10.0, 0.0, 10, 0.0, 0.10, 0.15)
        assert pv == pytest.approx(100.0)

    def test_monotonic_in_growth(self):
        pvs = [_present_value_two_stage(5.0, g, 10, 0.025, 0.09, 0.15) for g in (0.0, 0.05, 0.10)]
        assert pvs == sorted(pvs)

    def test_nonpositive_roe_caps_reinvestment(self):
        # ROE<=0 -> ERR=100% -> zero free cash flow -> zero value
        assert _present_value_two_stage(5.0, 0.1, 5, 0.02, 0.09, 0.0) == pytest.approx(0.0)


class TestSolver:
    def test_roundtrip(self):
        target = _present_value_two_stage(5.0, 0.12, 10, 0.025, 0.09, 0.15)
        g = _solve_implied_growth(target, 5.0, 10, 0.025, 0.09, 0.15)
        assert g == pytest.approx(0.12, abs=2e-3)

    def test_price_below_floor_returns_lower_bound(self):
        assert _solve_implied_growth(1e9, 5.0, 10, 0.025, 0.09, 0.15) is None
        assert _solve_implied_growth(0.01, 5.0, 10, 0.025, 0.09, 0.15) == -0.20

    def test_unreachable_price_returns_none(self):
        assert _solve_implied_growth(1e12, 5.0, 10, 0.025, 0.09, 0.15) is None


class TestCompute:
    def test_insufficient_data(self):
        res = ReverseDCF().compute(Security(ticker="X"))
        assert res.method == Method.REVERSE_DCF
        assert res.confidence == 0.0 and res.implied is None
        assert "Insufficient" in res.verdict_text

    def test_missing_shares(self):
        res = ReverseDCF().compute(_sec(shares=None))
        assert res.confidence == 0.0

    def test_nonpositive_cash_flow(self):
        sec = _sec(ni=-5.0)
        sec.fundamentals.fcf_ttm = -1.0
        res = ReverseDCF().compute(sec)
        assert res.confidence == 0.3 and "skipped" in res.verdict_text

    def test_falls_back_to_fcf(self):
        sec = _sec(ni=None)
        sec.fundamentals.fcf_ttm = 800.0
        res = ReverseDCF().compute(sec)
        assert res.assumptions["base_ni_per_share"] == pytest.approx(8.0)

    def test_implausible_growth(self):
        res = ReverseDCF().compute(_sec(price=1e9))
        assert res.confidence == 0.2 and "implausibly" in res.verdict_text

    def test_happy_path_no_history_reduces_confidence(self):
        res = ReverseDCF().compute(_sec())
        g = res.components["implied_growth"]
        assert res.implied.implied_revenue_growth == g
        assert res.confidence == pytest.approx(0.85)
        assert res.implied.growth_vs_history_max is None
        assert any("Insufficient history" in n for n in res.notes)
        # Round-trip: implied growth reproduces the market price
        pv = _present_value_two_stage(10.0, g, 10, 0.025, 0.09, 0.15)
        assert pv == pytest.approx(100.0, rel=2e-3)
        assert res.fair_value_per_share is None

    def test_history_comparison(self):
        # most-recent-first; yoy rates are all 10%
        hist = [133.1, 121.0, 110.0, 100.0]
        res = ReverseDCF().compute(_sec(hist=hist))
        g = res.components["implied_growth"]
        assert res.confidence == 1.0
        assert res.implied.growth_vs_history_max == pytest.approx(g / 0.10)

    def test_capm_discount_rate_from_beta(self):
        q = {"risk_free_rate": 0.04, "equity_risk_premium": 0.05}
        res = ReverseDCF().compute(_sec(beta=1.2, qualitative=q))
        assert res.assumptions["discount_rate"] == pytest.approx(0.04 + 1.2 * 0.05)
        assert any("CAPM discount rate" in n for n in res.notes)

    def test_capm_default_beta_and_roe_override(self):
        q = {"risk_free_rate": 0.04, "equity_risk_premium": 0.05, "forecast_roe": 0.25}
        res = ReverseDCF().compute(_sec(qualitative=q))
        assert res.assumptions["discount_rate"] == pytest.approx(0.09)
        assert res.assumptions["roe"] == 0.25

    def test_constructor_overrides(self):
        res = ReverseDCF(discount_rate=0.1, high_growth_years=5, terminal_growth=0.03).compute(
            _sec()
        )
        assert res.assumptions["high_growth_years"] == 5.0
        assert res.implied.implied_terminal_growth == 0.03


class TestVerdictText:
    @pytest.mark.parametrize(
        "vs_max,needle",
        [
            (None, "next decade."),
            (0.5, "comfortably below the 2.0x peak"),
            (0.85, "within historical capability (85% of peak)"),
            (1.2, "moderately above the historical peak (120%)"),
            (2.0, "substantially above"),
        ],
    )
    def test_buckets(self, vs_max, needle):
        txt = ReverseDCF._verdict_text(0.123, vs_max)
        assert "~12.3%" in txt and needle in txt
