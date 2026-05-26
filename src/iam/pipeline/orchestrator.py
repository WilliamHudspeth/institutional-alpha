"""Pipeline orchestrator.

v0.2.0-alpha covers Stages 1-4: the valuation core. Macro overlay (5-6) and
verdict + peer ranking (7) ship in v0.2.0-beta and v0.2.0 respectively.

The pipeline philosophy: each stage either supports or contradicts the
previous one. The output isn't a single score — it's a structured argument
the user can examine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from iam.data.security import Security
from iam.data.macro import MacroConditions
from iam.valuation import (
    ReverseDCF, RelativeValuation, FCFEDCF, FCFEAssumptions, SOTP,
    Triangulator, ValuationResult, TriangulationResult,
)
from iam.pipeline.macro import MacroOverlay


@dataclass
class PipelineReport:
    """The full output of a v0.2.0-alpha pipeline run."""
    ticker: str
    reverse_dcf: ValuationResult
    relative: ValuationResult
    intrinsic: ValuationResult
    triangulation: TriangulationResult

    # Convenience: where the cluster center implies the stock should be.
    implied_move_pct: Optional[float] = None
    summary: str = ""

    def explain(self) -> str:
        """Pretty-print the full pipeline output."""
        lines = [f"=== {self.ticker} | Valuation Pipeline (Stages 1-4) ===", ""]

        lines.append("STAGE 1 — Reverse DCF (what does the market expect?)")
        lines.append(f"  {self.reverse_dcf.verdict_text}")
        lines.append(f"  confidence: {self.reverse_dcf.confidence:.2f}")
        if self.reverse_dcf.implied:
            ie = self.reverse_dcf.implied
            if ie.implied_revenue_growth is not None:
                lines.append(f"  implied FCFE growth: {ie.implied_revenue_growth*100:.1f}%")
            if ie.growth_vs_history_max is not None:
                lines.append(f"  implied vs history peak: {ie.growth_vs_history_max:.2f}x")
        lines.append("")

        lines.append("STAGE 2 — Relative Valuation (do peers/history agree?)")
        lines.append(f"  {self.relative.verdict_text}")
        lines.append(f"  confidence: {self.relative.confidence:.2f}")
        if self.relative.fair_value_to_price is not None:
            lines.append(f"  implied move: {self.relative.fair_value_to_price*100:+.1f}%")
        lines.append("")

        lines.append("STAGE 3 — Intrinsic DCF (independent build-up)")
        lines.append(f"  {self.intrinsic.verdict_text}")
        lines.append(f"  confidence: {self.intrinsic.confidence:.2f}")
        if self.intrinsic.fair_value_to_price is not None:
            lines.append(f"  implied move: {self.intrinsic.fair_value_to_price*100:+.1f}%")
        lines.append("")

        lines.append(f"STAGE 4 — Triangulation: {self.triangulation.verdict.upper()}")
        if self.triangulation.cluster_members:
            members = ", ".join(m.value for m in self.triangulation.cluster_members)
            lines.append(f"  cluster: {members}")
        if self.triangulation.outliers:
            outliers = ", ".join(m.value for m in self.triangulation.outliers)
            lines.append(f"  outlier(s): {outliers}")
        if self.triangulation.spread is not None:
            lines.append(f"  spread across methods: {self.triangulation.spread:.1%}")
        if self.implied_move_pct is not None:
            lines.append(f"  triangulated implied move: {self.implied_move_pct*100:+.1f}%")
        lines.append(f"  confidence: {self.triangulation.confidence:.2f}")
        for note in self.triangulation.notes:
            lines.append(f"  • {note}")
        lines.append("")

        lines.append(f"SUMMARY: {self.summary}")
        return "\n".join(lines)


class ValuationPipeline:
    """Orchestrates Stages 1-5 of the pipeline.

    Usage:
        report = ValuationPipeline().run(security)
        print(report.explain())

    With macro:
        macro = MacroConditions(real_rate_trend=1.0, pmi_direction=45)
        report = ValuationPipeline().run(security, macro=macro)
    """

    def __init__(
        self,
        reverse_dcf: Optional[ReverseDCF] = None,
        relative: Optional[RelativeValuation] = None,
        intrinsic: Optional[FCFEDCF] = None,
        sotp: Optional[SOTP] = None,
        triangulator: Optional[Triangulator] = None,
        macro_overlay: Optional[MacroOverlay] = None,
        use_sotp_when_segments_available: bool = True,
    ):
        self.reverse_dcf = reverse_dcf or ReverseDCF()
        self.relative = relative or RelativeValuation()
        self.intrinsic_dcf = intrinsic or FCFEDCF()
        self.sotp = sotp or SOTP()
        self.triangulator = triangulator or Triangulator()
        self.macro_overlay = macro_overlay or MacroOverlay()
        self.use_sotp = use_sotp_when_segments_available

    def run(
        self,
        security: Security,
        fcfe_assumptions: Optional[FCFEAssumptions] = None,
        macro: Optional[MacroConditions] = None,
    ) -> PipelineReport:
        # Stage 1: what does the market expect?
        rev = self.reverse_dcf.compute(security)

        # Stage 2: do peers/history support those expectations?
        rel = self.relative.compute(security)

        # Stage 3: independent intrinsic build-up.
        # Check native fundamentals for segments
        has_segments = bool(security.fundamentals.segments)
        
        if self.use_sotp and has_segments:
            intr = self.sotp.compute(security)
            # If SOTP failed (returns 0 confidence), fall back to FCFE.
            if intr.confidence == 0.0:
                intr = self.intrinsic_dcf.compute(security, fcfe_assumptions)
        else:
            intr = self.intrinsic_dcf.compute(security, fcfe_assumptions)

        # Stage 4: triangulate.
        tri = self.triangulator.triangulate(rev, rel, intr)

        # Build summary
        implied_move = tri.cluster_center
        summary = self._build_summary(rev, rel, intr, tri)

        report = PipelineReport(
            ticker=security.ticker,
            reverse_dcf=rev,
            relative=rel,
            intrinsic=intr,
            triangulation=tri,
            implied_move_pct=implied_move,
            summary=summary,
        )

        # Stage 5: Apply macro overlay if provided
        if macro:
            report = self.macro_overlay.apply(report, security, macro)

        return report

    @staticmethod
    def _build_summary(
        rev: ValuationResult,
        rel: ValuationResult,
        intr: ValuationResult,
        tri: TriangulationResult,
    ) -> str:
        if tri.verdict == "no_data":
            return "Insufficient data across all methods — no verdict."

        if tri.verdict == "single_method":
            method = tri.cluster_members[0].value if tri.cluster_members else "single method"
            return f"Only {method} produced a result — verdict is low confidence."

        if tri.verdict == "agree":
            move = tri.cluster_center * 100 if tri.cluster_center is not None else 0
            direction = "upside" if move > 5 else ("downside" if move < -5 else "fair value")
            return (
                f"All three methods agree — {direction} of ~{abs(move):.0f}%. "
                f"High-conviction setup."
            )

        if tri.verdict == "two_of_three":
            move = tri.cluster_center * 100 if tri.cluster_center is not None else 0
            outlier = tri.outliers[0].value if tri.outliers else "one method"
            return (
                f"Two methods cluster at ~{move:+.0f}% — but {outlier} disagrees. "
                f"Worth investigating what the outlier sees that the others miss."
            )

        # disagree
        return (
            "Methods disagree materially — no clear verdict. "
            "The disagreement itself is the signal: dig into which method's "
            "assumptions are most contestable."
        )
