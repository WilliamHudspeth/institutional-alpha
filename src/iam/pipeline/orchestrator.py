from __future__ import annotations

import logging
from dataclasses import dataclass

from iam.data.macro import MacroConditions
from iam.data.security import Security
from iam.elasticity.types import StressResponse
from iam.engine.growth_estimator import (
    GrowthEstimateResult,
    GrowthQuestionnaire,
    QuestionnaireGrowthEngine,
)
from iam.engine.market_implied import MarketImpliedEngine
from iam.laws import DamodaranLawRegistry
from iam.laws.types import LawReport
from iam.lenses.base import LensResult
from iam.lenses.synthesis import synthesize_lenses
from iam.pipeline.macro import MacroOverlay
from iam.plugins.manager import PluginManager, get_plugin_manager
from iam.pipeline.verdict import VerdictGenerator, VerdictResult
from iam.thesis.drift import DriftReport
from iam.valuation import (
    FCFEDCF,
    SOTP,
    FCFEAssumptions,
    RelativeValuation,
    TriangulationResult,
    Triangulator,
    ValuationResult,
)
from iam.valuation.expectations_battlefield import (
    ExpectationBattlefieldExplicit,
    ExpectationsBattlefieldEngine,
    Scenario,
    ScenarioDistribution,
)
from iam.valuation.monte_carlo import MonteCarloDCF, MonteCarloDistribution

logger = logging.getLogger(__name__)


def format_assumption_table(
    forecast_growth: float,
    wacc: float,
    terminal_growth: float = 0.025,
    horizon: int = 10,
) -> str:
    """Build a typographic assumption summary as a string (no printing).

    Args:
        forecast_growth: Explicit forecast growth rate (e.g., 0.12 for 12%)
        wacc: Weighted average cost of capital (discount rate)
        terminal_growth: Perpetuity growth rate (default 2.5%)
        horizon: DCF projection horizon in years (default 10)

    Returns:
        Formatted string with bracketed section header and aligned colons.
    """
    lines = [
        " [ CORE ASSUMPTIONS ]",
        f"   • Forecast Growth : {forecast_growth * 100:.1f}%",
        f"   • Terminal Growth : {terminal_growth * 100:.1f}%",
        f"   • Discount Rate   : {wacc * 100:.2f}%",
        f"   • DCF Horizon     : {horizon} years",
    ]
    return "\n".join(lines)


def print_assumption_table(
    forecast_growth: float,
    wacc: float,
    terminal_growth: float = 0.025,
    horizon: int = 10,
) -> None:
    """Log the typographic assumption summary (delegates to format_assumption_table)."""
    logger.info(
        "\n" + format_assumption_table(forecast_growth, wacc, terminal_growth, horizon) + "\n"
    )


@dataclass
class PipelineReport:
    """The full output of a v0.4.0-rc1 pipeline run."""

    ticker: str
    market_implied_engine: ValuationResult
    relative: ValuationResult
    intrinsic: ValuationResult
    triangulation: TriangulationResult
    implied_move_pct: float | None = None
    summary: str = ""
    final_verdict: VerdictResult | None = None
    synthesis_upside: float | None = None  # Multi-lens synthesis weighted implied move
    law_report: LawReport | None = None  # Damodaran-law consistency checks
    stress_response: StressResponse | None = None  # Elasticity-aware macro stress
    battlefield: ExpectationBattlefieldExplicit | None = None
    drift_report: DriftReport | None = None
    monte_carlo: MonteCarloDistribution | None = None  # sampled fair-value distribution
    justified_premium: JustifiedPremiumResult | None = None  # Relative Reality gap
    growth_estimate: GrowthEstimateResult | None = None  # questionnaire-based growth vs. Stage 1
    plugin_lenses: list[LensResult] | None = None  # registered IA_LensPlugin outputs
    plugin_factors: dict[str, dict] | None = None  # registered IA_FactorPlugin outputs

    def explain(self, verbose: bool = False) -> str:
        if verbose:
            from iam.pipeline.verdict import (
                EXPLAIN_STAGE_1,
                EXPLAIN_STAGE_2,
                EXPLAIN_STAGE_3,
                EXPLAIN_STAGE_4,
                EXPLAIN_STAGE_5,
                EXPLAIN_STAGE_6,
                EXPLAIN_STAGE_7,
            )

            lines = [f"=== {self.ticker} | Valuation Pipeline Report ===", ""]

            lines.append(EXPLAIN_STAGE_1)
            lines.append(f"> Verdict: {self.market_implied_engine.verdict_text}")
            lines.append(f"> Confidence: {self.market_implied_engine.confidence:.2f}")
            lines.append("")

            if self.growth_estimate:
                lines.append("### Questionnaire Growth Estimate (Fundamental vs. Reverse DCF)")
                lines.append(f"> {self.growth_estimate.narrative}")
                if self.growth_estimate.gap_verdict:
                    lines.append(f"> {self.growth_estimate.gap_verdict}")
                lines.append("")

            lines.append(EXPLAIN_STAGE_2)
            lines.append(f"> Verdict: {self.relative.verdict_text}")
            lines.append(f"> Confidence: {self.relative.confidence:.2f}")
            lines.append("")

            lines.append(EXPLAIN_STAGE_3)
            lines.append(f"> Verdict: {self.intrinsic.verdict_text}")
            lines.append(f"> Confidence: {self.intrinsic.confidence:.2f}")
            for note in self.intrinsic.notes:
                lines.append(f"> • {note}")
            lines.append("")

            if self.monte_carlo and self.monte_carlo.percentiles:
                lines.append("### Monte Carlo — Fair-Value Distribution")
                lines.append(f"> {self.monte_carlo.narrative}")
                lines.append("")

            lines.append(EXPLAIN_STAGE_4)
            lines.append(f"> Verdict: {self.triangulation.verdict.upper()}")
            lines.append(f"> Confidence: {self.triangulation.confidence:.2f}")
            for note in self.triangulation.notes:
                lines.append(f"> • {note}")
            lines.append("")

            if self.battlefield:
                lines.append(self.battlefield.summary())

            if self.drift_report:
                lines.append("### Thesis Drift Detector — Registered Constraints")
                lines.append(f"> Breaches: {len(self.drift_report.breaches)}")
                for note in self.drift_report.notes():
                    lines.append(f"> • {note}")
                lines.append("")

            lines.append(EXPLAIN_STAGE_5)
            lines.append("> (Macro check details are summarized below if triggered)")
            lines.append("")

            lines.append(EXPLAIN_STAGE_6)
            lines.append(f"> Summary: {self.summary}")
            lines.append("")

            if self.law_report:
                lines.append("### Damodaran Laws — Consistency Checks")
                lines.append(f"> {self.law_report.narrative}")
                for check in self.law_report.violations + self.law_report.flags:
                    lines.append(f"> • LAW {check.number}: {check.narrative}")
                lines.append("")

            if self.final_verdict:
                lines.append(EXPLAIN_STAGE_7)
                lines.append(f"> VERDICT: {self.final_verdict.rating}")
                lines.append(f"> Confidence Band: {self.final_verdict.confidence_band}")
                for note in self.final_verdict.notes:
                    lines.append(f"> • {note}")

            return "\n".join(lines)

        # Non-verbose (original) output
        lines = [f"=== {self.ticker} | Valuation Pipeline (Stages 1-4) ===", ""]
        lines.append("STAGE 1 — Reverse DCF (what does the market expect?)")
        lines.append(f"  {self.market_implied_engine.verdict_text}")
        lines.append(f"  confidence: {self.market_implied_engine.confidence:.2f}")
        lines.append("")

        if self.growth_estimate:
            lines.append("STAGE 1b — Questionnaire Growth Estimate (fundamental vs. market-implied)")
            lines.append(f"  {self.growth_estimate.narrative}")
            if self.growth_estimate.gap_verdict:
                lines.append(f"  {self.growth_estimate.gap_verdict}")
            lines.append("")

        lines.append("STAGE 2 — Relative Valuation (do peers/history agree?)")
        lines.append(f"  {self.relative.verdict_text}")
        lines.append(f"  confidence: {self.relative.confidence:.2f}")
        lines.append("")

        lines.append("STAGE 3 — Intrinsic DCF (independent build-up)")
        lines.append(f"  {self.intrinsic.verdict_text}")
        lines.append(f"  confidence: {self.intrinsic.confidence:.2f}")
        for note in self.intrinsic.notes:
            lines.append(f"  • {note}")
        lines.append("")

        if self.monte_carlo and self.monte_carlo.percentiles:
            lines.append("STAGE 3b — MONTE CARLO DISTRIBUTION")
            lines.append(f"  {self.monte_carlo.narrative}")
            lines.append("")

        lines.append(f"STAGE 4 — Triangulation: {self.triangulation.verdict.upper()}")
        lines.append(f"  confidence: {self.triangulation.confidence:.2f}")
        for note in self.triangulation.notes:
            lines.append(f"  • {note}")
        lines.append("")

        if self.battlefield:
            lines.append("STAGE 4b — VALUATION BATTLEFIELD")
            lines.append(f"  Key Disagreement: {self.battlefield.primary_disagreement}")
            lines.append(f"  Mismatch Score: {self.battlefield.expectation_mismatch_score:.0f}/100")
            lines.append("")

        if self.drift_report:
            lines.append(f"THESIS DRIFT — {len(self.drift_report.breaches)} breaches detected")
            for note in self.drift_report.notes():
                lines.append(f"  • {note}")
            lines.append("")

        if self.law_report:
            lines.append(f"DAMODARAN LAWS — {self.law_report.narrative}")
            for check in self.law_report.violations + self.law_report.flags:
                lines.append(f"  • LAW {check.number}: {check.narrative}")
            lines.append("")

        lines.append(f"SUMMARY: {self.summary}")

        if self.final_verdict:
            lines.append("=" * 60)
            lines.append(f"STAGE 7 — FINAL VERDICT: {self.final_verdict.rating}")
            lines.append("=" * 60)
            for note in self.final_verdict.notes:
                lines.append(f" • {note}")

        return "\n".join(lines)


def _coerce_optional_float(value) -> float | None:
    """Best-effort float coercion for loosely-typed plugin output values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plugin_output_to_lens_result(plugin_name: str, raw) -> LensResult | None:
    """Convert an IA_LensPlugin.analyze() dict into a LensResult.

    Plugins are third-party code, so the shape is validated defensively.
    Returns None (and logs) when the output carries nothing the synthesis
    machinery can use — i.e. neither a narrative nor an implied move.
    """
    if not isinstance(raw, dict):
        logger.warning(
            "Lens plugin %s returned %s, expected dict — ignoring.",
            plugin_name,
            type(raw).__name__,
        )
        return None

    implied_move = _coerce_optional_float(raw.get("implied_move_pct"))
    narrative = raw.get("narrative")
    if implied_move is None and not narrative:
        logger.debug(
            "Lens plugin %s output has neither implied_move_pct nor narrative — skipping.",
            plugin_name,
        )
        return None

    confidence = _coerce_optional_float(raw.get("confidence"))
    confidence = 0.5 if confidence is None else min(max(confidence, 0.0), 1.0)

    notes = raw.get("notes")
    if not isinstance(notes, list):
        notes = []

    return LensResult(
        lens_name=str(raw.get("lens_name") or plugin_name),
        fair_value_low=_coerce_optional_float(raw.get("fair_value_low")),
        fair_value_high=_coerce_optional_float(raw.get("fair_value_high")),
        implied_move_pct=implied_move,
        confidence=confidence,
        narrative=str(narrative or ""),
        notes=[str(n) for n in notes],
    )


class ValuationPipeline:
    def __init__(
        self,
        use_sotp_when_segments_available: bool = True,
        plugin_manager: PluginManager | None = None,
    ):
        self.market_implied_engine = MarketImpliedEngine()
        self.relative = RelativeValuation()
        self.intrinsic_dcf = FCFEDCF()
        self.monte_carlo = MonteCarloDCF()
        self.sotp = SOTP()
        self.triangulator = Triangulator()
        self.macro_overlay = MacroOverlay(self.intrinsic_dcf)
        self.use_sotp = use_sotp_when_segments_available
        # None -> fall back to the process-wide manager at run() time, so
        # plugins registered via iam.plugins.manager.get_plugin_manager()
        # affect valuations without any extra wiring.
        self.plugin_manager = plugin_manager

    def _collect_plugin_results(
        self,
        security: Security,
        market_implied_res: ValuationResult,
        relative_res: ValuationResult,
        intrinsic_res: ValuationResult,
        triangulation_res: TriangulationResult,
    ) -> tuple[list[LensResult], dict[str, dict]]:
        """Run registered IA_LensPlugin / IA_FactorPlugin instances.

        Each plugin receives a read-oriented data payload describing the
        security and the stage results computed so far. Failures are logged
        and skipped — a broken plugin must never take down a valuation run.
        """
        manager = self.plugin_manager if self.plugin_manager is not None else get_plugin_manager()
        lens_instances = manager.create_lens_instances()
        factor_instances = manager.create_factor_instances()
        if not lens_instances and not factor_instances:
            return [], {}

        data = {
            "ticker": security.ticker,
            "security": security,
            "price": security.market.price if security.market else None,
            "fundamentals": security.fundamentals,
            "market": security.market,
            "market_implied": market_implied_res,
            "relative": relative_res,
            "intrinsic": intrinsic_res,
            "triangulation": triangulation_res,
        }

        lens_results: list[LensResult] = []
        for name, plugin in lens_instances.items():
            try:
                raw = plugin.analyze(data)
                lens_result = _plugin_output_to_lens_result(name, raw)
                if lens_result is not None:
                    lens_results.append(lens_result)
            except Exception as e:
                logger.warning("Lens plugin %s failed: %s", name, e)
                continue

        factor_results: dict[str, dict] = {}
        for name, plugin in factor_instances.items():
            try:
                raw = plugin.calculate(data)
            except Exception as e:
                logger.warning("Factor plugin %s failed: %s", name, e)
                continue
            if isinstance(raw, dict):
                factor_results[name] = raw
            else:
                logger.warning(
                    "Factor plugin %s returned %s, expected dict — ignoring.",
                    name,
                    type(raw).__name__,
                )

        return lens_results, factor_results

    @staticmethod
    def _calculate_dynamic_wacc(security: Security) -> dict | None:
        from iam.valuation.damodaran_defaults import build_wacc

        f = security.fundamentals
        m = security.market
        if not f or not m:
            return None

        ebit = None
        if getattr(f, "revenue_ttm", None) and getattr(f, "operating_margin", None):
            ebit = f.revenue_ttm * f.operating_margin  # type: ignore
        if ebit is None:
            ebit = getattr(f, "ebitda_ttm", None) or 0.0

        interest = getattr(f, "interest_expense_ttm", None) or 0.0

        d_to_e = 0.0
        total_debt = getattr(f, "total_debt", None) or 0.0
        market_cap = getattr(m, "market_cap", None) or 0.0
        if total_debt > 0 and market_cap > 0:
            d_to_e = total_debt / market_cap

        ke = 0.09
        rf = 0.043
        tax_rate = 0.21

        return build_wacc(
            ke=ke, ebit=ebit, interest_expense=interest, rf=rf, d_to_e=d_to_e, tax_rate=tax_rate
        )

    def run(
        self,
        security: Security,
        fcfe_assumptions: FCFEAssumptions | None = None,
        macro: MacroConditions | None = None,
        synthesis_upside: float | None = None,
        growth_questionnaire: GrowthQuestionnaire | None = None,
    ) -> PipelineReport:
        wacc_info = self._calculate_dynamic_wacc(security)
        wacc_note = ""
        original_r = self.market_implied_engine.r

        if wacc_info:
            dynamic_wacc = wacc_info["wacc"]
            rating = wacc_info["rating"]

            self.market_implied_engine.r = dynamic_wacc

            if security.qualitative is None:
                security.qualitative = {}
            security.qualitative["wacc_override"] = dynamic_wacc
            security.qualitative["wacc_info"] = wacc_info
            wacc_note = f"Dynamic WACC applied: {dynamic_wacc:.2%} (Rating: {rating})"

        # Stage 1: Reverse DCF
        market_implied_engine_res = self.market_implied_engine.compute(security)

        if wacc_info:
            self.market_implied_engine.r = original_r

        # Stage 1b: Questionnaire-based fundamental growth, contrasted against
        # Stage 1's market-implied growth (opt-in — only runs when the caller
        # supplies a completed questionnaire).
        growth_estimate_res = None
        if growth_questionnaire is not None:
            growth_estimate_res = QuestionnaireGrowthEngine().compute(
                security, growth_questionnaire
            )
            growth_estimate_res = QuestionnaireGrowthEngine().contrast_with_reverse_dcf(
                growth_estimate_res, market_implied_engine_res
            )

        # Stage 2: Relative Valuation
        from iam.data.providers.yfinance_adapter import build_regression_inputs

        try:
            reg_inputs = build_regression_inputs(security.ticker)
        except Exception:
            reg_inputs = None
        relative_res = self.relative.compute(security, regression_inputs=reg_inputs)

        # Stage 3: Intrinsic DCF / SOTP
        if (
            self.use_sotp
            and security.fundamentals
            and getattr(security.fundamentals, "segments", None)
        ):
            from iam.engine.damodaran import DamodaranEngine
            from iam.valuation.sotp import Segment
            from iam.valuation.types import Method

            segments_data = getattr(security.fundamentals, "segments", [])
            segments = [Segment(**s) if isinstance(s, dict) else s for s in segments_data]

            damodaran = DamodaranEngine()
            total_debt = getattr(security.fundamentals, "total_debt", 0.0) or 0.0
            market_cap = getattr(security.market, "market_cap", 1.0) or 1.0
            debt_equity = total_debt / market_cap if market_cap > 0 else 0.0
            tax_rate = 0.21  # default corporate tax rate
            cost_of_equity = damodaran.compute_cost_of_equity(
                segments, debt_to_equity=debt_equity, tax_rate=tax_rate
            )

            sotp_result = self.sotp.compute(segments, cost_of_equity)
            shares = getattr(security.fundamentals, "shares_outstanding", 1.0) or 1.0

            intrinsic_res = ValuationResult(
                method=Method.INTRINSIC,
                fair_value_per_share=sotp_result.total_ev / shares,
                notes=[
                    f"Weighted unlevered beta: {sotp_result.weighted_unlevered_beta:.3f}",
                    f"Cost of equity: {cost_of_equity:.2%}",
                ]
                + [f"{seg['name']}: ${seg['ev']:,.0f}" for seg in sotp_result.segments],
                assumptions={
                    "high_growth": 0.08,
                    "roe": 0.15,
                    "cost_of_equity": cost_of_equity,
                    "debt_equity": debt_equity,
                },
            )
        else:
            intrinsic_res = self.intrinsic_dcf.compute(security, fcfe_assumptions)

        if wacc_info and wacc_note:
            intrinsic_res.notes.append(wacc_note)

        # Stage 3b: Monte Carlo fair-value distribution around the intrinsic
        # base case (percentiles + P(upside) instead of a point estimate).
        monte_carlo_res = self.monte_carlo.run(security)

        # ML Lens Anomaly Detection for Triangulation Weighting
        try:
            from iam.ml.ml_lens import MLDiagnosticLens
            ml_res = MLDiagnosticLens().compute(security)
            if ml_res.confidence < 1.0:
                # If fundamentals are anomalous, relative valuation (comps) is less reliable
                relative_res.confidence *= ml_res.confidence
                relative_res.notes.append("Confidence reduced due to ML fundamental anomaly.")
                intrinsic_res.notes.append(f"ML Anomaly Note: {ml_res.narrative}")
        except Exception as e:
            logger.warning("ML anomaly check failed: %s", e, exc_info=True)

        # Stage 4: Triangulation
        triangulation_res = self.triangulator.triangulate(
            market_implied_engine_res, relative_res, intrinsic_res
        )

        # Stage 4a: Registered plugins (iam.plugins). Lens plugins are folded
        # into a synthesis whose weighted implied move feeds Stage 7 (below);
        # their narratives are appended to the triangulation notes so they
        # surface in explain()/reports.
        plugin_lens_results, plugin_factor_results = self._collect_plugin_results(
            security, market_implied_engine_res, relative_res, intrinsic_res, triangulation_res
        )
        plugin_synthesis_move: float | None = None
        plugin_notes: list[str] = []
        if plugin_lens_results:
            plugin_synthesis = synthesize_lenses(plugin_lens_results)
            plugin_synthesis_move = plugin_synthesis.weighted_implied_move_pct
            plugin_notes.extend(
                f"[PLUGIN {lr.lens_name}]: {lr.narrative}" for lr in plugin_lens_results
            )
        for plugin_name, factor_values in plugin_factor_results.items():
            plugin_notes.append(f"[PLUGIN FACTOR {plugin_name}]: {factor_values}")

        # Stage 4b: Valuation Battlefield
        battlefield_res = None
        if market_implied_engine_res.implied is not None and intrinsic_res.assumptions:
            try:
                # Build Intrinsic Scenarios
                int_g = intrinsic_res.assumptions.get("high_growth", 0.08)
                int_r = intrinsic_res.assumptions.get("roe", 0.15)
                int_m = getattr(security.fundamentals, "operating_margin", None) or 0.20

                intrinsic_dist = ScenarioDistribution(
                    [
                        Scenario(0.20, growth=int_g * 0.60, margin=int_m * 0.90, roic=int_r * 0.80),
                        Scenario(0.60, growth=int_g, margin=int_m, roic=int_r),
                        Scenario(0.20, growth=int_g * 1.30, margin=int_m * 1.10, roic=int_r * 1.20),
                    ]
                )

                # Build Market Scenarios
                mkt_g = market_implied_engine_res.implied.implied_revenue_growth
                mkt_r = getattr(market_implied_engine_res.implied, "implied_roic", int_r)
                mkt_m = int_m  # Assume market margin is base margin if not solved

                market_dist = ScenarioDistribution(
                    [
                        Scenario(0.20, growth=mkt_g * 0.80, margin=mkt_m * 0.95, roic=mkt_r * 0.90),  # type: ignore
                        Scenario(0.50, growth=mkt_g, margin=mkt_m, roic=mkt_r),  # type: ignore
                        Scenario(0.30, growth=mkt_g * 1.20, margin=mkt_m * 1.05, roic=mkt_r * 1.10),  # type: ignore
                    ]
                )

                battle_engine = ExpectationsBattlefieldEngine(intrinsic_dist, market_dist)
                battlefield_res = battle_engine.compute()
            except Exception as e:
                logger.warning(f"Failed to build valuation battlefield for {security.ticker}: {e}")

        # Stage 4c: Thesis Drift Detection
        from pathlib import Path

        from iam.thesis.drift import DriftDetector, load_constraints

        drift_report = None
        constraints_path = Path("data/constraints") / f"{security.ticker}.yml"
        if not constraints_path.exists():
            constraints_path = Path("data/constraints") / f"{security.ticker}.example.yml"

        if constraints_path.exists():
            try:
                _, constraints = load_constraints(constraints_path)
                detector = DriftDetector()
                from iam.reasoning.business_reality import BusinessRealityEngine

                br = BusinessRealityEngine().assess(security)
                drift_report = detector.evaluate(
                    ticker=security.ticker,
                    constraints=constraints,
                    business_reality=br,
                    fundamentals=security.fundamentals,
                )
            except Exception as e:
                logger.warning(f"Failed to evaluate thesis drift for {security.ticker}: {e}")

        report = PipelineReport(
            ticker=security.ticker,
            market_implied_engine=market_implied_engine_res,
            relative=relative_res,
            intrinsic=intrinsic_res,
            triangulation=triangulation_res,
            implied_move_pct=triangulation_res.cluster_center,
            summary=triangulation_res.verdict,
            battlefield=battlefield_res,
            drift_report=drift_report,
            monte_carlo=monte_carlo_res,
            growth_estimate=growth_estimate_res,
        )

        if monte_carlo_res.percentiles:
            report.summary += f"\n[MONTE CARLO]: {monte_carlo_res.narrative}"

        if growth_estimate_res is not None:
            report.summary += f"\n[GROWTH QUESTIONNAIRE]: {growth_estimate_res.narrative}"
            if growth_estimate_res.gap_verdict:
                report.summary += f"\n[GROWTH vs. REVERSE DCF]: {growth_estimate_res.gap_verdict}"

        # Damodaran Laws: test the assumptions Stage 3 actually used for
        # internal consistency. Violations/flags degrade the Stage 7 verdict.
        report.law_report = DamodaranLawRegistry().evaluate(
            security,
            intrinsic_res.assumptions or {},
            implied=market_implied_engine_res.implied,
        )
        report.summary += f"\n[DAMODARAN LAWS]: {report.law_report.narrative}"

        # Stages 5 & 6: Macro Overlay
        if macro:
            report = self.macro_overlay.apply(report, security, macro)
            if report.intrinsic.fair_value_per_share != intrinsic_res.fair_value_per_share:
                report.triangulation = self.triangulator.triangulate(
                    report.market_implied_engine, report.relative, report.intrinsic
                )
                report.implied_move_pct = report.triangulation.cluster_center

        # Plugin results (Stage 4a) are attached after the macro overlay so a
        # macro-driven re-triangulation cannot drop the plugin notes.
        report.plugin_lenses = plugin_lens_results or None
        report.plugin_factors = plugin_factor_results or None
        report.triangulation.notes.extend(plugin_notes)
        if plugin_lens_results or plugin_factor_results:
            report.summary += (
                f"\n[PLUGINS]: {len(plugin_lens_results)} lens / "
                f"{len(plugin_factor_results)} factor plugin(s) applied"
            )

        # Stage 7: Verdict (with optional Master Arbitration Layer)
        report.synthesis_upside = synthesis_upside
        if report.synthesis_upside is None and plugin_synthesis_move is not None:
            # No caller-supplied multi-lens synthesis: let the registered lens
            # plugins' weighted implied move drive the arbitration layer.
            report.synthesis_upside = plugin_synthesis_move
            report.summary += (
                f"\n[PLUGIN SYNTHESIS]: weighted implied move "
                f"{plugin_synthesis_move:+.1%} from lens plugin(s)"
            )

        # Relative Reality: justified premium vs actual
        try:
            from iam.valuation.justified_premium import calculate_justified_premium

            report.justified_premium = calculate_justified_premium(security)
            if report.justified_premium.premium_gap is not None:
                gap = report.justified_premium.premium_gap
                direction = "overvalued" if gap > 0 else "undervalued"
                report.summary += (
                    f"\n[JUSTIFIED PREMIUM]: {direction} vs deserved by {abs(gap):.1%}"
                )
        except Exception as e:
            logger.warning(f"Justified premium calculation failed: {e}")

        report.final_verdict = VerdictGenerator().generate(
            report.triangulation,
            report.relative,
            security,
            synthesis_upside=report.synthesis_upside,
            law_report=report.law_report,
            stress_response=report.stress_response,
            drift_report=report.drift_report,
            justified_premium=report.justified_premium,
            mismatch_score=report.battlefield.expectation_mismatch_score
            if report.battlefield
            else None,
        )

        return report
