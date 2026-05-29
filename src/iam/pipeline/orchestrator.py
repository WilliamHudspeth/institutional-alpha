from __future__ import annotations

from dataclasses import dataclass

from iam.data.macro import MacroConditions
from iam.data.security import Security
from iam.pipeline.macro import MacroOverlay
from iam.pipeline.verdict import VerdictGenerator, VerdictResult
from iam.valuation import (
    FCFEDCF,
    SOTP,
    FCFEAssumptions,
    RelativeValuation,
    ReverseDCF,
    TriangulationResult,
    Triangulator,
    ValuationResult,
)


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
    """Print the typographic assumption summary (delegates to format_assumption_table)."""
    print(format_assumption_table(forecast_growth, wacc, terminal_growth, horizon))
    print()


@dataclass
class PipelineReport:
    """The full output of a v0.2.0-alpha pipeline run."""

    ticker: str
    reverse_dcf: ValuationResult
    relative: ValuationResult
    intrinsic: ValuationResult
    triangulation: TriangulationResult
    implied_move_pct: float | None = None
    summary: str = ""
    final_verdict: VerdictResult | None = None
    synthesis_upside: float | None = None  # Multi-lens synthesis weighted implied move
    business_reality: ValuationResult | None = None
    battlefield: BattlefieldReport | None = None
    drift: ThesisDriftReport | None = None

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
            lines.append(f"> Verdict: {self.reverse_dcf.verdict_text}")
            lines.append(f"> Confidence: {self.reverse_dcf.confidence:.2f}")
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

            lines.append(EXPLAIN_STAGE_4)
            lines.append(f"> Verdict: {self.triangulation.verdict.upper()}")
            lines.append(f"> Confidence: {self.triangulation.confidence:.2f}")
            for note in self.triangulation.notes:
                lines.append(f"> • {note}")
            lines.append("")

            lines.append(EXPLAIN_STAGE_5)
            lines.append("> (Macro check details are summarized below if triggered)")
            lines.append("")

            lines.append(EXPLAIN_STAGE_6)
            lines.append(f"> Summary: {self.summary}")
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
        lines.append(f"  {self.reverse_dcf.verdict_text}")
        lines.append(f"  confidence: {self.reverse_dcf.confidence:.2f}")
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

        if self.business_reality:
            lines.append(
                "STAGE 3b — Business Reality Engine (Operational Durability & Consistency)"
            )
            lines.append(f"  {self.business_reality.verdict_text}")
            lines.append("")

        lines.append(f"STAGE 4 — Triangulation: {self.triangulation.verdict.upper()}")
        lines.append(f"  confidence: {self.triangulation.confidence:.2f}")
        for note in self.triangulation.notes:
            lines.append(f"  • {note}")
        lines.append("")

        lines.append(f"SUMMARY: {self.summary}")
        lines.append("")

        if self.battlefield:
            lines.append("STAGE 8 — VALUATION BATTLEFIELD VIEW")
            lines.append(f"{self.battlefield.verdict_text}")
            lines.append("")

        if self.drift:
            lines.append("STAGE 9 — THESIS OPERATIONAL DRIFT AUDIT")
            lines.append(f"  Overall Fragility Score: {self.drift.overall_fragility * 100:.1f}%")
            if self.drift.drift_warnings:
                for w in self.drift.drift_warnings:
                    lines.append(f"    ⚠️ {w}")
            else:
                lines.append(
                    "    ✅ No active operational assumption drift detected across theses."
                )
            lines.append("")

        if self.final_verdict:
            lines.append("=" * 60)
            lines.append(f"STAGE 7 — FINAL VERDICT: {self.final_verdict.rating}")
            lines.append("=" * 60)
            for note in self.final_verdict.notes:
                lines.append(f" • {note}")

        return "\n".join(lines)


class ValuationPipeline:
    def __init__(self, use_sotp_when_segments_available: bool = True):
        self.reverse_dcf = ReverseDCF()
        self.relative = RelativeValuation()
        self.intrinsic_dcf = FCFEDCF()
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
            ebit = f.revenue_ttm * f.operating_margin
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
        original_r = self.reverse_dcf.r

        if wacc_info:
            dynamic_wacc = wacc_info["wacc"]
            rating = wacc_info["rating"]

            self.reverse_dcf.r = dynamic_wacc

            if security.qualitative is None:
                security.qualitative = {}
            security.qualitative["wacc_override"] = dynamic_wacc
            security.qualitative["wacc_info"] = wacc_info
            wacc_note = f"Dynamic WACC applied: {dynamic_wacc:.2%} (Rating: {rating})"

        # Stage 1: Reverse DCF
        reverse_dcf_res = self.reverse_dcf.compute(security)

        if wacc_info:
            self.reverse_dcf.r = original_r

        # Stage 2: Relative Valuation
        relative_res = self.relative.compute(security)

        # Stage 3: Intrinsic DCF / SOTP
        if (
            self.use_sotp
            and security.fundamentals
            and getattr(security.fundamentals, "segments", None)
        ):
            intrinsic_res = self.sotp.compute(security)
        else:
            intrinsic_res = self.intrinsic_dcf.compute(security, fcfe_assumptions)

        if wacc_info and wacc_note:
            intrinsic_res.notes.append(wacc_note)

        # Stage 3b: Business Reality Audit (Engine 3)
        g = intrinsic_res.assumptions.get("high_growth", 0.10)
        tg = intrinsic_res.assumptions.get("terminal_growth", 0.025)
        discount = intrinsic_res.assumptions.get("discount_rate", 0.09)
        roe = intrinsic_res.assumptions.get("roe", 0.15)

        from iam.valuation.business_reality import BusinessRealityEngine

        business_reality_res = BusinessRealityEngine.compute(
            security=security,
            forecast_growth=g,
            terminal_growth=tg,
            discount_rate=discount,
            roe=roe,
        )

        # Penalize intrinsic DCF confidence based on business reality and Damodaran checks
        intrinsic_res.confidence = float(intrinsic_res.confidence * business_reality_res.confidence)

        # Stage 4: Triangulation
        triangulation_res = self.triangulator.triangulate(
            reverse_dcf_res, relative_res, intrinsic_res
        )

        report = PipelineReport(
            ticker=security.ticker,
            reverse_dcf=reverse_dcf_res,
            relative=relative_res,
            intrinsic=intrinsic_res,
            triangulation=triangulation_res,
            implied_move_pct=triangulation_res.cluster_center,
            summary=triangulation_res.verdict,
            business_reality=business_reality_res,
        )

        # Stages 8 & 9: Valuation Battlefield & Thesis Drift Detection
        from iam.thesis.battlefield import ValuationBattlefield
        from iam.thesis.drift import ThesisDriftDetector

        report.battlefield = ValuationBattlefield.generate_battlefield(security, report)
        report.drift = ThesisDriftDetector.detect_drift(security)

        # Stages 5 & 6: Macro Overlay
        if macro:
            report = self.macro_overlay.apply(report, security, macro)
            if report.intrinsic.fair_value_per_share != intrinsic_res.fair_value_per_share:
                report.triangulation = self.triangulator.triangulate(
                    report.reverse_dcf, report.relative, report.intrinsic
                )
                report.implied_move_pct = report.triangulation.cluster_center

        # Stage 7: Verdict (with optional Master Arbitration Layer)
        report.synthesis_upside = synthesis_upside
        report.final_verdict = VerdictGenerator().generate(
            report.triangulation,
            report.relative,
            security,
            synthesis_upside=synthesis_upside,
        )

        return report
