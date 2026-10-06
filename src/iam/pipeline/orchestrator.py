from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from iam.data.macro import MacroConditions
from iam.data.security import Security
from iam.elasticity.types import StressResponse
from iam.engine.growth_estimator import (
    GrowthEstimateResult,
    GrowthQuestionnaire,
    QuestionnaireGrowthEngine,
)
from iam.engine.market_implied import ConsensusInputs, MarketImpliedEngine
from iam.laws import DamodaranLawRegistry
from iam.laws.types import LawReport
from iam.lenses.base import LensResult
from iam.lenses.synthesis import synthesize_lenses
from iam.pipeline.battlefield import (
    BattlefieldAttribution,
    build_battlefield,
    fcfe_value_fn,
    intrinsic_vector_from_assumptions,
)
from iam.pipeline.macro import MacroOverlay
from iam.pipeline.verdict import VerdictGenerator, VerdictResult
from iam.plugins.manager import PluginManager, get_plugin_manager
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
from iam.valuation.country_risk import company_erp, us_consensus_erp
from iam.valuation.country_tax import company_marginal_tax
from iam.valuation.monte_carlo import MonteCarloDCF, MonteCarloDistribution

if TYPE_CHECKING:
    from iam.valuation.justified_premium import JustifiedPremiumResult

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
    battlefield: BattlefieldAttribution | None = None
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
                if self.drift_report.source_banner:
                    lines.append(f"> ⚠ {self.drift_report.source_banner}")
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
            lines.append(
                "STAGE 1b — Questionnaire Growth Estimate (fundamental vs. market-implied)"
            )
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
            lines.append(f"  Key Disagreement: {self.battlefield.key_disagreement}")
            if self.battlefield.value_gap_pct is not None:
                lines.append(
                    f"  Market-implied value vs ours: {self.battlefield.value_gap_pct * 100:+.1f}%"
                )
            lines.append("")

        if self.drift_report:
            lines.append(f"THESIS DRIFT — {len(self.drift_report.breaches)} breaches detected")
            if self.drift_report.source_banner:
                lines.append(f"  ! {self.drift_report.source_banner}")
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
        for name, lens_plugin in lens_instances.items():
            try:
                raw = lens_plugin.analyze(data)
                lens_result = _plugin_output_to_lens_result(name, raw)
                if lens_result is not None:
                    lens_results.append(lens_result)
            except Exception as e:
                logger.warning("Lens plugin %s failed: %s", name, e)
                continue

        factor_results: dict[str, dict] = {}
        for name, factor_plugin in factor_instances.items():
            try:
                raw = factor_plugin.calculate(data)
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
        """Reference WACC built on the intrinsic (bottom-up) cost of equity.

        Ke is the one the intrinsic stage uses: Rf + relevered industry beta x
        revenue-weighted ERP. If the caller supplied ``risk_free_rate`` /
        ``equity_risk_premium`` that explicit CAPM (regression beta) is used
        instead, as in the intrinsic stage. Returns ``None`` when no cost of
        equity can be built from real data.
        """
        from iam.data.damodaran import DamodaranProvider
        from iam.data.ground_truth import GroundTruthProvider
        from iam.valuation.damodaran_defaults import build_wacc

        f = security.fundamentals
        m = security.market
        if not f or not m:
            return None

        ebit = None
        if getattr(f, "revenue_ttm", None) and getattr(f, "operating_margin", None):
            ebit = f.revenue_ttm * f.operating_margin  # type: ignore
        if ebit is None:
            ebit = getattr(f, "ebitda_ttm", None)

        if ebit is None:
            return None

        interest = getattr(f, "interest_expense_ttm", None)
        if interest is None:
            return None

        qual = security.qualitative or {}
        caller_rf = qual.get("risk_free_rate")
        caller_erp = qual.get("equity_risk_premium")
        defaults_used: list[str] = []

        if caller_rf is not None or caller_erp is not None:
            # Explicit custom CAPM: caller values with the regression beta.
            beta = getattr(m, "beta", None)
            if beta is None:
                return None
            macro = DamodaranProvider.get_macro_state()
            if caller_rf is not None:
                rf = float(caller_rf)
                rf_source = str(qual.get("rf_source") or "caller-supplied")
            else:
                rf, rf_source = macro.risk_free_rate, macro.rf_source
            if caller_erp is not None:
                erp = float(caller_erp)
                erp_source = str(qual.get("erp_source") or "caller-supplied")
            else:
                erp, erp_source = company_erp(security)
            ke = rf + beta * erp
            d_to_e = 0.0
            total_debt = getattr(f, "total_debt", None) or 0.0
            market_cap = getattr(m, "market_cap", None) or 0.0
            if total_debt > 0 and market_cap > 0:
                d_to_e = total_debt / market_cap
            # MARGINAL rate for the after-tax cost of debt (Damodaran), not the effective one.
            tax_rate, tax_source = company_marginal_tax(security)
        else:
            profile = GroundTruthProvider().get_equity_risk_profile(security)
            if profile is None or profile.tax_rate is None or profile.debt_to_equity is None:
                return None
            rf, rf_source, erp_source = (
                profile.risk_free_rate,
                profile.rf_source,
                profile.erp_source,
            )
            ke = profile.cost_of_equity
            d_to_e = profile.debt_to_equity
            tax_rate = profile.tax_rate
            tax_source = profile.tax_source
            defaults_used.extend(profile.defaults_used)

        wacc_info = build_wacc(
            ke=ke,
            ebit=ebit,
            interest_expense=interest,
            rf=rf,
            d_to_e=d_to_e,
            tax_rate=tax_rate,
        )
        wacc_info.setdefault("defaults_used", []).extend(defaults_used)
        wacc_info["rf_source"] = rf_source
        wacc_info["erp_source"] = erp_source
        wacc_info["cost_of_equity"] = ke
        wacc_info["tax_rate"] = tax_rate
        wacc_info["tax_source"] = tax_source
        return wacc_info

    @staticmethod
    def _stage_risk_free(security: Security) -> tuple[float, str]:
        """The Rf (and its source) the valuation stages use: caller-supplied, else macro."""
        from iam.data.damodaran import DamodaranProvider
        from iam.valuation.reverse_dcf import as_rate

        qual = security.qualitative or {}
        caller = as_rate(qual.get("risk_free_rate"))
        if caller is not None:
            return caller, str(qual.get("rf_source") or "caller-supplied")
        return DamodaranProvider.get_risk_free_rate_with_source()

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

        if wacc_info:
            dynamic_wacc = wacc_info["wacc"]
            rating = wacc_info["rating"]

            if security.qualitative is None:
                security.qualitative = {}
            security.qualitative["wacc_info"] = wacc_info
            details: list[str] = [f"rating {rating}"]
            if "rf_source" in wacc_info and wacc_info["rf_source"]:
                details.append(f"rf: {wacc_info['rf_source']}")
            if wacc_info.get("tax_source"):
                details.append(
                    f"marginal tax {wacc_info['tax_rate']:.2%}: {wacc_info['tax_source']}"
                )
            if wacc_info.get("defaults_used"):
                details.extend(wacc_info["defaults_used"])
            details_str = f" ({', '.join(details)})" if details else ""
            wacc_note = (
                f"WACC (reference only; FCFE stages discount at cost of equity): "
                f"{dynamic_wacc:.2%}{details_str}"
            )

        # Caller overrides keep their meaning: this method never writes
        # risk_free_rate / equity_risk_premium. It only labels their source.
        if security.qualitative is None:
            security.qualitative = {}
        if "risk_free_rate" in security.qualitative:
            security.qualitative.setdefault("rf_source", "caller-supplied")
        if "equity_risk_premium" in security.qualitative:
            security.qualitative.setdefault("erp_source", "caller-supplied")

        # Stage 1: Reverse DCF ("what does the price imply?"). Consensus Ke =
        # Rf + regression beta x US-only ERP, handed to Stage 1 for this call
        # only so it cannot steer any other stage.
        consensus: ConsensusInputs | None = None
        if security.market and getattr(security.market, "beta", None) is not None:
            from iam.data.damodaran import DamodaranProvider

            rf, rf_source = DamodaranProvider.get_risk_free_rate_with_source()
            us_erp, us_erp_source = us_consensus_erp()
            consensus = ConsensusInputs(
                rf=rf, erp=us_erp, rf_source=rf_source, erp_source=us_erp_source
            )
        market_implied_engine_res = self.market_implied_engine.compute(security, consensus)

        if consensus is None:
            market_implied_engine_res.notes.append("CAPM skipped for lack of beta.")

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
            from iam.valuation.country_tax import company_marginal_tax
            from iam.valuation.sotp import Segment
            from iam.valuation.types import Method

            segments_data = getattr(security.fundamentals, "segments", [])
            segments = [Segment(**s) if isinstance(s, dict) else s for s in segments_data]

            damodaran = DamodaranEngine()
            total_debt = getattr(security.fundamentals, "total_debt", None)
            debt_val = float(total_debt or 0.0)
            market_cap = getattr(security.market, "market_cap", None)

            extra_notes = []
            if market_cap is not None and market_cap > 0:
                debt_equity = debt_val / float(market_cap)
            elif debt_val <= 0:
                debt_equity = 0.0
                extra_notes.append("total debt missing or zero: D/E taken as 0")
            else:
                debt_equity = None

            q = security.qualitative or {}
            if q.get("tax_rate") is not None:
                tax_rate = float(q["tax_rate"])
                tax_note = f"Tax rate: {tax_rate:.1%} (supplied)"
            else:
                tax_rate, tax_source = company_marginal_tax(security)
                tax_note = f"Tax rate: {tax_rate:.1%} ({tax_source})"

            shares = getattr(security.fundamentals, "shares_outstanding", None)
            if debt_equity is None or shares is None or shares <= 0:
                missing = (
                    "market cap unavailable"
                    if debt_equity is None
                    else "shares outstanding unavailable"
                )
                intrinsic_res = ValuationResult(
                    method=Method.INTRINSIC,
                    fair_value_per_share=None,
                    confidence=0.0,
                    notes=[f"insufficient data: {missing}"],
                    verdict_text=f"insufficient data: {missing}",
                )
            else:
                cost_of_equity = damodaran.compute_cost_of_equity(
                    segments, debt_to_equity=debt_equity, tax_rate=tax_rate
                )

                sotp_result = self.sotp.compute(segments, cost_of_equity)

                intrinsic_res = ValuationResult(
                    method=Method.INTRINSIC,
                    fair_value_per_share=sotp_result.total_ev / shares,
                    notes=[
                        f"Weighted unlevered beta: {sotp_result.weighted_unlevered_beta:.3f}",
                        f"Cost of equity: {cost_of_equity:.2%}",
                    ]
                    + [f"{seg['name']}: ${seg['ev']:,.0f}" for seg in sotp_result.segments]
                    + [tax_note]
                    + extra_notes,
                    # Only what the SOTP valuation actually used. It has no
                    # growth/ROE inputs, so none are reported (downstream readers
                    # treat missing keys as "not applicable").
                    assumptions={
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
            if ml_res.assumptions.get("evaluated", 0.0) == 1.0:
                if ml_res.assumptions.get("is_anomaly", 0.0) == 1.0:
                    # If fundamentals are anomalous, relative valuation (comps) is less reliable
                    relative_res.confidence *= ml_res.confidence
                    relative_res.notes.append("Confidence reduced due to ML fundamental anomaly.")
                    intrinsic_res.notes.append(f"ML Anomaly Note: {ml_res.narrative}")
            else:
                intrinsic_res.notes.append(ml_res.narrative)
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

        # Stage 4b: Valuation Battlefield — which single assumption explains
        # the gap between the market-implied and intrinsic lenses. Uses the
        # real FCFE maths on the two real parameter vectors; nothing invented.
        battlefield_res = None
        base_ni = (intrinsic_res.components or {}).get("base_ni_per_share")
        if market_implied_engine_res.implied is not None and intrinsic_res.assumptions and base_ni:
            try:
                value_fn = fcfe_value_fn(
                    float(base_ni),
                    int(intrinsic_res.assumptions.get("high_growth_years", 10)),
                    intrinsic_vector_from_assumptions(intrinsic_res.assumptions),
                )
                battlefield_res = build_battlefield(
                    market_implied=market_implied_engine_res,
                    intrinsic=intrinsic_res,
                    value_fn=value_fn,
                    triangulation=triangulation_res,
                )
            except Exception as e:
                logger.warning(f"Failed to build valuation battlefield for {security.ticker}: {e}")

        # Stage 4c: Thesis Drift Detection
        from iam.thesis.drift import DriftDetector, find_constraints, load_constraints

        drift_report = None
        found = find_constraints(security.ticker)
        if found is not None:
            constraints_path, source = found
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
                drift_report.source = source
                drift_report.constraints_path = str(constraints_path)
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
        # Law 3 judges terminal growth against the Rf this run used (caller-supplied
        # Rf if any, else the macro Rf), not a constant.
        law_rf, law_rf_source = self._stage_risk_free(security)
        report.law_report = DamodaranLawRegistry().evaluate(
            security,
            intrinsic_res.assumptions or {},
            implied=market_implied_engine_res.implied,
            risk_free_rate=law_rf,
            rf_source=law_rf_source,
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
            mismatch_score=report.battlefield.mismatch_score if report.battlefield else None,
        )

        return report
