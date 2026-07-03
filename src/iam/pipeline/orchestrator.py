from __future__ import annotations

import logging
from dataclasses import dataclass

from iam.data.macro import MacroConditions
from iam.data.security import Security
from iam.elasticity.types import StressResponse
from iam.engine.market_implied import MarketImpliedEngine
from iam.laws import DamodaranLawRegistry
from iam.laws.types import LawReport
from iam.pipeline.macro import MacroOverlay
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
    logger.info("\n" + format_assumption_table(forecast_growth, wacc, terminal_growth, horizon) + "\n")


@dataclass
class PipelineReport:
    """The full output of a v0.2.0-alpha pipeline run."""

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


class ValuationPipeline:
    def __init__(self, use_sotp_when_segments_available: bool = True):
        self.market_implied_engine = MarketImpliedEngine()
        self.relative = RelativeValuation()
        self.intrinsic_dcf = FCFEDCF()
        self.monte_carlo = MonteCarloDCF()
        self.sotp = SOTP()
        self.triangulator = Triangulator()
        self.macro_overlay = MacroOverlay(self.intrinsic_dcf)
        self.use_sotp = use_sotp_when_segments_available

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

        # Stage 4: Triangulation
        triangulation_res = self.triangulator.triangulate(
            market_implied_engine_res, relative_res, intrinsic_res
        )

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
        )

        if monte_carlo_res.percentiles:
            report.summary += f"\n[MONTE CARLO]: {monte_carlo_res.narrative}"

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

        # Stage 7: Verdict (with optional Master Arbitration Layer)
        report.synthesis_upside = synthesis_upside
        report.final_verdict = VerdictGenerator().generate(
            report.triangulation,
            report.relative,
            security,
            synthesis_upside=synthesis_upside,
            law_report=report.law_report,
            stress_response=report.stress_response,
            drift_report=report.drift_report,
            mismatch_score=report.battlefield.expectation_mismatch_score
            if report.battlefield
            else None,
        )

        return report
