"""Tests for the Damodaran Laws constraint layer (iam.laws).

The laws are *consistency checks that flag fragile analyses* — they never
invent numbers. Each law is tested across its PASS / FLAG / VIOLATION /
NOT_EVALUATED paths, and the aggregate report is tested for the conviction
multiplier the verdict layer consumes.

Expected values are derived from the documented module constants so the
assertions stay exact (no magic numbers in tests either).
"""

from __future__ import annotations

from iam.data.security import Fundamentals, Security
from iam.laws import DamodaranLawRegistry, excess_return_fade_path, fade_adjusted_growth
from iam.laws import registry as reg
from iam.laws.fade import DEFAULT_FADE_YEARS, TERMINAL_EXCESS_RETENTION
from iam.laws.types import (
    FLAG_PENALTY,
    MIN_CONVICTION_MULTIPLIER,
    VIOLATION_PENALTY,
    LawReport,
    LawStatus,
)
from iam.valuation.types import ImpliedExpectations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _security(
    *,
    operating_margin_history: list[float] | None = None,
    roic_history: list[float] | None = None,
    revenue_history: list[float] | None = None,
    fcf_ttm: float | None = None,
    net_income_ttm: float | None = None,
    qualitative: dict | None = None,
) -> Security:
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            operating_margin_history=operating_margin_history or [],
            roic_history=roic_history or [],
            revenue_history=revenue_history or [],
            fcf_ttm=fcf_ttm,
            net_income_ttm=net_income_ttm,
        ),
        qualitative=qualitative or {},
    )


def _assumptions(
    high_growth: float = 0.08,
    terminal_growth: float = 0.025,
    discount_rate: float = 0.09,
    high_growth_years: float = 10.0,
) -> dict[str, float]:
    """Mirror the assumptions dict shape FCFEDCF puts on its ValuationResult."""
    return {
        "high_growth": high_growth,
        "terminal_growth": terminal_growth,
        "high_growth_years": high_growth_years,
        "discount_rate": discount_rate,
        "roe": 0.15,
    }


def _check(report: LawReport, number: int):
    return next(c for c in report.checks if c.number == number)


# ===========================================================================
# Fade helpers (Law 4 machinery)
# ===========================================================================


class TestFadeCurves:
    def test_fade_path_glides_to_retained_excess(self):
        """30% ROIC vs 9% WACC fades linearly to WACC + 10% of the excess."""
        path = excess_return_fade_path(0.30, 0.09)
        assert len(path) == DEFAULT_FADE_YEARS + 1
        assert path[0] == 0.30
        expected_terminal = 0.09 + TERMINAL_EXCESS_RETENTION * (0.30 - 0.09)
        assert abs(path[-1] - expected_terminal) < 1e-12
        # Monotonically declining
        assert all(a >= b for a, b in zip(path, path[1:]))

    def test_no_excess_means_flat_path(self):
        path = excess_return_fade_path(0.08, 0.09)
        assert path == [0.08] * (DEFAULT_FADE_YEARS + 1)

    def test_zero_years_returns_today(self):
        assert excess_return_fade_path(0.30, 0.09, years=0) == [0.30]

    def test_fade_adjusted_growth_uses_terminal_roic(self):
        faded_g = fade_adjusted_growth(0.30, 0.09, reinvestment_rate=0.5)
        terminal_roic = excess_return_fade_path(0.30, 0.09)[-1]
        assert faded_g is not None
        assert abs(faded_g - terminal_roic * 0.5) < 1e-12

    def test_fade_adjusted_growth_rejects_negative_reinvestment(self):
        assert fade_adjusted_growth(0.30, 0.09, reinvestment_rate=-0.1) is None


# ===========================================================================
# LAW 1 — narrative must match numbers
# ===========================================================================


class TestLaw1NarrativeMatchesNumbers:
    def test_not_evaluated_without_margin_history(self):
        report = DamodaranLawRegistry().evaluate(_security(), _assumptions(high_growth=0.20))
        assert _check(report, 1).status is LawStatus.NOT_EVALUATED

    def test_modest_growth_passes_without_interrogation(self):
        sec = _security(operating_margin_history=[0.25, 0.22, 0.20, 0.18])
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.08))
        assert _check(report, 1).status is LawStatus.PASS

    def test_high_growth_expanding_margins_without_moat_flags(self):
        """The moat story is being assumed, not told — flag it."""
        sec = _security(operating_margin_history=[0.30, 0.25, 0.22, 0.20])
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.20))
        check = _check(report, 1)
        assert check.status is LawStatus.FLAG
        assert "moat" in check.narrative.lower()

    def test_high_growth_expanding_margins_with_moat_passes(self):
        sec = _security(
            operating_margin_history=[0.30, 0.25, 0.22, 0.20],
            qualitative={"moat": "network effects in payments"},
        )
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.20))
        assert _check(report, 1).status is LawStatus.PASS

    def test_high_growth_contracting_margins_is_reinvestment_story(self):
        sec = _security(operating_margin_history=[0.15, 0.20, 0.22, 0.24])
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.20))
        check = _check(report, 1)
        assert check.status is LawStatus.PASS
        assert "reinvestment" in check.narrative.lower()


# ===========================================================================
# LAW 2 — growth requires reinvestment
# ===========================================================================


class TestLaw2GrowthRequiresReinvestment:
    def test_not_evaluated_without_roic(self):
        report = DamodaranLawRegistry().evaluate(
            _security(qualitative={"reinvestment_rate": 0.5}), _assumptions()
        )
        assert _check(report, 2).status is LawStatus.NOT_EVALUATED

    def test_supported_growth_passes(self):
        """g=8% vs sustainable 20% ROIC x 50% reinvestment = 10% -> pass."""
        sec = _security(roic_history=[0.20, 0.20, 0.20], qualitative={"reinvestment_rate": 0.5})
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.08))
        check = _check(report, 2)
        assert check.status is LawStatus.PASS
        assert abs(check.components["sustainable_growth"] - 0.10) < 1e-12

    def test_unsupported_growth_flags(self):
        """g=15% vs sustainable 10%: 5pp gap is inside the violation band but
        above the flag tolerance."""
        sec = _security(roic_history=[0.20, 0.20, 0.20], qualitative={"reinvestment_rate": 0.5})
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.15))
        assert _check(report, 2).status is LawStatus.FLAG

    def test_impossible_growth_violates(self):
        """g=25% vs sustainable 10%: a 15pp gap cannot be funded."""
        sec = _security(roic_history=[0.20, 0.20, 0.20], qualitative={"reinvestment_rate": 0.5})
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.25))
        check = _check(report, 2)
        assert check.status is LawStatus.VIOLATION
        gap = 0.25 - 0.10
        assert abs(check.components["growth_gap"] - gap) < 1e-12

    def test_reinvestment_estimated_from_fcf_conversion(self):
        """Without an explicit rate, 1 - FCF/NI proxies reinvestment (here 40%)."""
        sec = _security(roic_history=[0.20], fcf_ttm=60.0, net_income_ttm=100.0)
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.06))
        check = _check(report, 2)
        assert check.status is LawStatus.PASS
        assert abs(check.components["reinvestment_rate"] - 0.40) < 1e-12
        assert any("estimated" in n.lower() for n in check.notes)

    def test_reinvestment_falls_back_to_market_implied(self):
        sec = _security(roic_history=[0.20])
        implied = ImpliedExpectations(implied_reinvestment_rate=0.5)
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.08), implied)
        check = _check(report, 2)
        assert check.status is LawStatus.PASS
        assert any("market" in n.lower() for n in check.notes)


# ===========================================================================
# LAW 3 — terminal growth <= risk-free rate
# ===========================================================================


class TestLaw3TerminalGrowthCeiling:
    def test_safe_terminal_growth_passes(self):
        report = DamodaranLawRegistry().evaluate(_security(), _assumptions(terminal_growth=0.025))
        assert _check(report, 3).status is LawStatus.PASS

    def test_terminal_growth_above_rf_violates(self):
        report = DamodaranLawRegistry().evaluate(_security(), _assumptions(terminal_growth=0.05))
        check = _check(report, 3)
        assert check.status is LawStatus.VIOLATION
        assert check.components["risk_free_rate"] == reg.DEFAULT_RISK_FREE

    def test_terminal_growth_at_ceiling_flags(self):
        """Within the ceiling band below rf: legal but with zero headroom."""
        rf = reg.DEFAULT_RISK_FREE
        report = DamodaranLawRegistry().evaluate(
            _security(), _assumptions(terminal_growth=rf - 0.001)
        )
        assert _check(report, 3).status is LawStatus.FLAG

    def test_respects_user_supplied_risk_free_rate(self):
        sec = _security(qualitative={"risk_free_rate": 0.06})
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(terminal_growth=0.05))
        assert _check(report, 3).status is LawStatus.PASS


# ===========================================================================
# LAW 4 — excess returns fade
# ===========================================================================


class TestLaw4ExcessReturnsFade:
    def test_not_evaluated_without_roic(self):
        report = DamodaranLawRegistry().evaluate(_security(), _assumptions())
        assert _check(report, 4).status is LawStatus.NOT_EVALUATED

    def test_modest_excess_returns_pass(self):
        sec = _security(roic_history=[0.11])
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.08))
        assert _check(report, 4).status is LawStatus.PASS

    def test_high_excess_flat_growth_long_horizon_flags(self):
        """18% ROIC (+9pp excess) with 13% growth flat for 10y assumes no fade."""
        sec = _security(roic_history=[0.18])
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.13))
        check = _check(report, 4)
        assert check.status is LawStatus.FLAG
        assert "faded_terminal_roic" in check.components

    def test_extreme_perpetual_moat_violates(self):
        """25% ROIC (+16pp excess) and 18% growth flat for a decade."""
        sec = _security(roic_history=[0.25])
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.18))
        assert _check(report, 4).status is LawStatus.VIOLATION

    def test_short_horizon_limits_fade_risk(self):
        sec = _security(roic_history=[0.25])
        report = DamodaranLawRegistry().evaluate(
            sec, _assumptions(high_growth=0.18, high_growth_years=5.0)
        )
        assert _check(report, 4).status is LawStatus.PASS

    def test_roic_falls_back_to_market_implied(self):
        implied = ImpliedExpectations(implied_roic=0.25)
        report = DamodaranLawRegistry().evaluate(
            _security(), _assumptions(high_growth=0.18), implied
        )
        check = _check(report, 4)
        assert check.status is LawStatus.VIOLATION
        assert any("implied" in n.lower() for n in check.notes)


# ===========================================================================
# LAW 5 — risk is not double-counted
# ===========================================================================


class TestLaw5RiskNotDoubleCounted:
    def test_not_evaluated_without_revenue_history(self):
        report = DamodaranLawRegistry().evaluate(_security(), _assumptions())
        assert _check(report, 5).status is LawStatus.NOT_EVALUATED

    def test_consistent_assumptions_pass(self):
        # ~12% historical CAGR, 10% forecast, baseline WACC: nothing doubled.
        sec = _security(revenue_history=[140.0, 125.0, 112.0, 100.0])
        report = DamodaranLawRegistry().evaluate(
            sec, _assumptions(high_growth=0.10, discount_rate=0.09)
        )
        assert _check(report, 5).status is LawStatus.PASS

    def test_elevated_wacc_and_haircut_growth_flags(self):
        """Risk priced in the rate AND the cash flows: ~12% history cut to 4%
        forecast while WACC carries a 300bps premium."""
        sec = _security(revenue_history=[140.0, 125.0, 112.0, 100.0])
        report = DamodaranLawRegistry().evaluate(
            sec, _assumptions(high_growth=0.04, discount_rate=0.12)
        )
        check = _check(report, 5)
        assert check.status is LawStatus.FLAG
        assert "double-counted" in check.narrative.lower()

    def test_depressed_wacc_and_heroic_growth_flags(self):
        """Optimism doubled: ~5% history forecast at 15% on a 6% WACC."""
        sec = _security(revenue_history=[115.0, 110.0, 105.0, 100.0])
        report = DamodaranLawRegistry().evaluate(
            sec, _assumptions(high_growth=0.15, discount_rate=0.06)
        )
        assert _check(report, 5).status is LawStatus.FLAG

    def test_elevated_wacc_alone_passes(self):
        """High discount rate with growth near history is one risk channel only."""
        sec = _security(revenue_history=[140.0, 125.0, 112.0, 100.0])
        report = DamodaranLawRegistry().evaluate(
            sec, _assumptions(high_growth=0.11, discount_rate=0.13)
        )
        assert _check(report, 5).status is LawStatus.PASS


# ===========================================================================
# Aggregate report
# ===========================================================================


class TestLawReport:
    def test_all_laws_always_reported(self):
        report = DamodaranLawRegistry().evaluate(_security(), _assumptions())
        assert [c.number for c in report.checks] == [1, 2, 3, 4, 5]

    def test_clean_report_has_full_conviction(self):
        sec = _security(
            operating_margin_history=[0.20, 0.20, 0.20, 0.20],
            roic_history=[0.15, 0.15, 0.15],
            revenue_history=[120.0, 110.0, 100.0],
            qualitative={"reinvestment_rate": 0.6},
        )
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.08))
        assert not report.flags and not report.violations
        assert report.conviction_multiplier == 1.0

    def test_conviction_multiplier_matches_documented_penalties(self):
        """Aggressive analysis: Law 2 violated, Laws 3 (ceiling) + 4 flagged."""
        rf = reg.DEFAULT_RISK_FREE
        sec = _security(
            roic_history=[0.18, 0.18, 0.18],
            qualitative={"reinvestment_rate": 0.5},
        )
        report = DamodaranLawRegistry().evaluate(
            sec, _assumptions(high_growth=0.20, terminal_growth=rf - 0.001)
        )
        assert len(report.violations) == 1  # Law 2: 20% vs 9% sustainable
        assert len(report.flags) == 2  # Law 3 ceiling, Law 4 no-fade
        expected = 1.0 - VIOLATION_PENALTY - 2 * FLAG_PENALTY
        assert abs(report.conviction_multiplier - expected) < 1e-12

    def test_conviction_multiplier_is_floored(self):
        report = LawReport()
        report.checks = (
            DamodaranLawRegistry()
            .evaluate(
                _security(
                    roic_history=[0.30],
                    qualitative={"reinvestment_rate": 0.1},
                ),
                _assumptions(high_growth=0.35, terminal_growth=0.06),
            )
            .checks
        )
        assert report.conviction_multiplier >= MIN_CONVICTION_MULTIPLIER

    def test_narrative_names_violated_laws(self):
        sec = _security(roic_history=[0.20, 0.20], qualitative={"reinvestment_rate": 0.5})
        report = DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.25))
        assert "VIOLATED" in report.narrative
        assert "growth_requires_reinvestment" in report.narrative

    def test_security_never_mutated(self):
        sec = _security(
            roic_history=[0.20],
            revenue_history=[120.0, 110.0, 100.0],
            qualitative={"reinvestment_rate": 0.5},
        )
        before_q = dict(sec.qualitative)
        before_roic = list(sec.fundamentals.roic_history)
        DamodaranLawRegistry().evaluate(sec, _assumptions(high_growth=0.25))
        assert sec.qualitative == before_q
        assert sec.fundamentals.roic_history == before_roic
