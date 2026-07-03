"""Phase 2 specs: Monte Carlo DCF, macro regimes, regime-aware overlay wiring,
Damodaran law registry, battlefield scenario rows, and orchestrator attachment."""

from unittest.mock import MagicMock

from iam.data.macro import (
    RATE_HIKE_SHOCK,
    RECESSION_SHOCK,
    STAGFLATION_SHOCK,
    MacroConditions,
)
from iam.data.security import Fundamentals, MarketData, Security
from iam.laws import DamodaranLawRegistry
from iam.laws.types import LawStatus
from iam.lenses.base import two_stage_pv
from iam.pipeline.battlefield import (
    ParamVector,
    rows_from_scenario_matrix,
    two_stage_fcfe_value,
)
from iam.pipeline.macro import MacroOverlay
from iam.pipeline.macro_regimes import (
    MacroRegime,
    MacroRegimeClassifier,
    regime_conditional_wacc,
    yield_curve_duration_risk,
)
from iam.thesis.scenarios import ScenarioAssumptions, ScenarioMatrix, ValuationScenario
from iam.valuation.monte_carlo import MonteCarloDCF

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _rich_security(ticker: str = "MC") -> Security:
    return Security(
        ticker=ticker,
        fundamentals=Fundamentals(
            fcf_ttm=100.0,
            shares_outstanding=10.0,
            net_income_ttm=120.0,
            operating_margin=0.25,
            gross_margin=0.55,
            revenue_history=[1000.0, 900.0, 820.0, 760.0],
            roic_history=[0.15, 0.14, 0.16],
            operating_margin_history=[0.25, 0.24, 0.26, 0.25],
            fcf_history=[100.0, 95.0, 90.0, 88.0],
        ),
        market=MarketData(price=100.0),
        qualitative={
            "forecast_growth": 0.08,
            "forecast_discount_rate": 0.09,
            "forecast_terminal_growth": 0.025,
        },
    )


# ---------------------------------------------------------------------------
# MonteCarloDCF
# ---------------------------------------------------------------------------


def test_monte_carlo_percentiles_are_ordered():
    dist = MonteCarloDCF(n_samples=500).run(_rich_security())
    p = dist.percentiles
    assert set(p.keys()) == {5, 25, 50, 75, 95}
    assert p[5] <= p[25] <= p[50] <= p[75] <= p[95]
    assert dist.confidence > 0


def test_monte_carlo_is_seeded_and_reproducible():
    a = MonteCarloDCF(n_samples=300, seed=42).run(_rich_security())
    b = MonteCarloDCF(n_samples=300, seed=42).run(_rich_security())
    assert a.percentiles == b.percentiles
    assert a.prob_upside == b.prob_upside


def test_monte_carlo_median_brackets_deterministic_dcf():
    sec = _rich_security()
    deterministic = two_stage_pv(10.0, 0.08, 10, 0.025, 0.09)
    dist = MonteCarloDCF(n_samples=2000).run(sec)
    assert deterministic is not None
    # Median of the sampled cloud should sit near the base-case DCF.
    assert 0.7 * deterministic < dist.percentiles[50] < 1.3 * deterministic


def test_monte_carlo_prob_upside_in_unit_interval():
    dist = MonteCarloDCF(n_samples=500).run(_rich_security())
    assert dist.prob_upside is not None
    assert 0.0 <= dist.prob_upside <= 1.0
    # Base case (~239 fair vs 100 price) is deeply bullish.
    assert dist.prob_upside > 0.5


def test_monte_carlo_degrades_without_cash_flow():
    dist = MonteCarloDCF().run(Security(ticker="EMPTY"))
    assert dist.confidence == 0.0
    assert dist.percentiles == {}
    assert dist.prob_upside is None


def test_monte_carlo_missing_margin_reduces_confidence():
    sec = _rich_security()
    sec.fundamentals.operating_margin = None
    dist = MonteCarloDCF(n_samples=300).run(sec)
    assert dist.percentiles
    assert dist.confidence < 1.0
    assert any("margin" in n.lower() for n in dist.notes)


# ---------------------------------------------------------------------------
# Macro regime classifier
# ---------------------------------------------------------------------------


def test_regime_stagflation():
    macro = MacroConditions(rate_change=0.0075, pmi=45.0, inflation_rate=0.05)
    result = MacroRegimeClassifier().classify(macro)
    assert result.regime is MacroRegime.STAGFLATION
    assert result.shock is STAGFLATION_SHOCK
    assert result.shock_multiplier > 1.0
    assert result.wacc_premium > 0


def test_regime_tightening():
    macro = MacroConditions(rate_change=0.0050, pmi=55.0)
    result = MacroRegimeClassifier().classify(macro)
    assert result.regime is MacroRegime.TIGHTENING
    assert result.shock is RATE_HIKE_SHOCK
    assert result.shock_multiplier == 1.0


def test_regime_easing():
    macro = MacroConditions(rate_change=-0.0050)
    result = MacroRegimeClassifier().classify(macro)
    assert result.regime is MacroRegime.EASING
    assert result.shock is RECESSION_SHOCK
    assert result.wacc_premium < 0


def test_regime_neutral():
    result = MacroRegimeClassifier().classify(MacroConditions(rate_change=0.0))
    assert result.regime is MacroRegime.NEUTRAL
    assert result.shock_multiplier == 1.0
    assert result.wacc_premium == 0.0


def test_regime_conditional_wacc():
    assert regime_conditional_wacc(0.09, MacroRegime.STAGFLATION) == 0.09 + 0.015
    assert regime_conditional_wacc(0.09, MacroRegime.TIGHTENING) == 0.09 + 0.005
    assert regime_conditional_wacc(0.09, MacroRegime.EASING) == 0.09 - 0.005
    assert regime_conditional_wacc(0.09, MacroRegime.NEUTRAL) == 0.09


def test_yield_curve_duration_risk():
    assert yield_curve_duration_risk(None, 2.0) is None
    assert yield_curve_duration_risk(0.005, None) is None
    # Deep inversion + fully duration-bound = maximum risk.
    assert yield_curve_duration_risk(-0.01, 3.0) == 1.0
    # Steep curve = no risk regardless of duration.
    assert yield_curve_duration_risk(0.01, 3.0) == 0.0
    # Flat curve, mid-duration name.
    mid = yield_curve_duration_risk(0.0, 1.5)
    assert mid is not None and 0.0 < mid < 1.0


# ---------------------------------------------------------------------------
# Regime-aware overlay wiring (ahead of elasticity scaling)
# ---------------------------------------------------------------------------


def _overlay_with_unmeasurable_elasticity() -> MacroOverlay:
    scorer = MagicMock()
    scorer.profile.return_value = MagicMock(confidence=0.0)
    overlay = MacroOverlay(intrinsic_dcf=MagicMock(), elasticity_scorer=scorer)
    overlay.stress_engine = MagicMock()
    overlay.stress_engine.run_stress_test.return_value = MagicMock(notes=[])
    return overlay


def test_overlay_reports_regime_in_summary():
    report = MagicMock()
    report.summary = ""
    overlay = _overlay_with_unmeasurable_elasticity()
    overlay.apply(report, _rich_security(), MacroConditions(rate_change=0.0025, pmi=55.0))
    assert "[MACRO REGIME]" in report.summary
    assert "TIGHTENING" in report.summary


def test_stagflation_multiplier_tightens_gate_before_elasticity():
    """45bps raw: below the 50bps gate in tightening, above it in stagflation."""
    tightening = MagicMock()
    tightening.summary = ""
    overlay = _overlay_with_unmeasurable_elasticity()
    overlay.apply(tightening, _rich_security(), MacroConditions(rate_change=0.0045, pmi=55.0))
    assert "within tolerance" in tightening.summary

    stagflation = MagicMock()
    stagflation.summary = ""
    overlay = _overlay_with_unmeasurable_elasticity()
    overlay.apply(stagflation, _rich_security(), MacroConditions(rate_change=0.0045, pmi=45.0))
    assert "MACRO OVERLAY TRIGGERED" in stagflation.summary
    assert "Stagflation" in stagflation.summary


def test_overlay_applies_regime_shock_when_triggered():
    report = MagicMock()
    report.summary = ""
    overlay = _overlay_with_unmeasurable_elasticity()
    overlay.apply(report, _rich_security(), MacroConditions(rate_change=-0.0100, pmi=48.0))
    shock = overlay.stress_engine.run_stress_test.call_args[0][1]
    assert shock is RECESSION_SHOCK  # easing regime, unscaled (no elasticity)


# ---------------------------------------------------------------------------
# Damodaran law registry
# ---------------------------------------------------------------------------


def test_law_registry_evaluates_all_five_laws():
    sec = _rich_security()
    report = DamodaranLawRegistry().evaluate(
        sec,
        {
            "high_growth": 0.08,
            "terminal_growth": 0.025,
            "discount_rate": 0.09,
            "high_growth_years": 10.0,
            "roe": 0.15,
        },
    )
    assert [c.number for c in report.checks] == [1, 2, 3, 4, 5]
    assert 0.5 <= report.conviction_multiplier <= 1.0


def test_law3_flags_terminal_growth_above_risk_free():
    sec = _rich_security()
    report = DamodaranLawRegistry().evaluate(
        sec, {"high_growth": 0.08, "terminal_growth": 0.05, "discount_rate": 0.09}
    )
    law3 = next(c for c in report.checks if c.number == 3)
    assert law3.status is LawStatus.VIOLATION


def test_law2_violation_on_unfundable_growth():
    sec = _rich_security()
    sec.qualitative["reinvestment_rate"] = 0.30  # sustainable g = 0.15 * 0.30 = 4.5%
    report = DamodaranLawRegistry().evaluate(
        sec, {"high_growth": 0.20, "terminal_growth": 0.025, "discount_rate": 0.09}
    )
    law2 = next(c for c in report.checks if c.number == 2)
    assert law2.status is LawStatus.VIOLATION
    assert law2.components["growth_gap"] > 0.08


# ---------------------------------------------------------------------------
# Battlefield: Bull/Bear/Market-implied rows from a ScenarioMatrix
# ---------------------------------------------------------------------------


def _scenario_matrix() -> ScenarioMatrix:
    matrix = ScenarioMatrix(ticker="MC")
    matrix.scenarios["Bull"] = ValuationScenario(
        name="Bull Case",
        probability=0.20,
        thesis="Share gains + margin expansion",
        expected_signals=["Beats"],
        assumptions=ScenarioAssumptions(forecast_growth=0.12, wacc=0.09, terminal_growth=0.025),
    )
    matrix.scenarios["Base"] = ValuationScenario(
        name="Base Case",
        probability=0.60,
        thesis="Steady state",
        expected_signals=["In-line"],
        assumptions=ScenarioAssumptions(forecast_growth=0.08, wacc=0.09, terminal_growth=0.025),
    )
    matrix.scenarios["Bear"] = ValuationScenario(
        name="Bear Case",
        probability=0.20,
        thesis="Fee compression",
        expected_signals=["Misses"],
        assumptions=ScenarioAssumptions(forecast_growth=0.03, wacc=0.10, terminal_growth=0.02),
    )
    return matrix


def test_battlefield_rows_from_scenario_matrix():
    market_vec = ParamVector(growth=0.10, terminal_growth=0.025, discount_rate=0.09)
    rows = rows_from_scenario_matrix(_scenario_matrix(), two_stage_fcfe_value, market_vec)
    labels = [r.label for r in rows]
    assert labels == ["Bull Case", "Base Case", "Bear Case", "Market-implied"]
    by_label = {r.label: r for r in rows}
    assert by_label["Bull Case"].value > by_label["Base Case"].value > by_label["Bear Case"].value
    # Market row is informational, not part of the probability mass.
    assert by_label["Market-implied"].probability == 0.0
    assert all(r.value > 0 for r in rows)


def test_battlefield_rows_without_market_vector():
    rows = rows_from_scenario_matrix(_scenario_matrix(), two_stage_fcfe_value)
    assert len(rows) == 3
    assert all(r.label != "Market-implied" for r in rows)


# ---------------------------------------------------------------------------
# Orchestrator attachment
# ---------------------------------------------------------------------------


def test_pipeline_report_carries_monte_carlo():
    from iam.pipeline.orchestrator import ValuationPipeline

    report = ValuationPipeline().run(_rich_security("PHASE2"))
    assert report.monte_carlo is not None
    assert report.monte_carlo.percentiles
    p = report.monte_carlo.percentiles
    assert p[5] <= p[50] <= p[95]
    assert "[MONTE CARLO]" in report.summary
    assert "MONTE CARLO" in report.explain()
    # Existing Phase-2 attachments still present.
    assert report.law_report is not None
    assert [c.number for c in report.law_report.checks] == [1, 2, 3, 4, 5]
