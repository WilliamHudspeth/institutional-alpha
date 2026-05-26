from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from iam.data.security import Security
from iam.data.macro import MacroConditions
from iam.valuation import (
    ReverseDCF, RelativeValuation, FCFEDCF, FCFEAssumptions, 
    SOTP, Triangulator, ValuationResult, TriangulationResult
)
from iam.pipeline.macro import MacroOverlay
from iam.pipeline.verdict import VerdictResult, VerdictGenerator

@dataclass
class PipelineReport:
    """The full output of a v0.2.0-alpha pipeline run."""
    ticker: str
    reverse_dcf: ValuationResult
    relative: ValuationResult
    intrinsic: ValuationResult
    triangulation: TriangulationResult
    implied_move_pct: Optional[float] = None
    summary: str = ""
    final_verdict: Optional[VerdictResult] = None

    def explain(self) -> str:
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
        lines.append("")
        
        lines.append(f"STAGE 4 — Triangulation: {self.triangulation.verdict.upper()}")
        lines.append(f"  confidence: {self.triangulation.confidence:.2f}")
        for note in self.triangulation.notes:
            lines.append(f"  • {note}")
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
        self.reverse_dcf = ReverseDCF()
        self.relative = RelativeValuation()
        self.intrinsic_dcf = FCFEDCF()
        self.sotp = SOTP()
        self.triangulator = Triangulator()
        self.macro_overlay = MacroOverlay()
        self.use_sotp = use_sotp_when_segments_available

    def run(self, security: Security, fcfe_assumptions: Optional[FCFEAssumptions] = None, macro: Optional[MacroConditions] = None) -> PipelineReport:
        rev = self.reverse_dcf.compute(security)
        rel = self.relative.compute(security)
        
        has_segments = bool(security.fundamentals.segments)
        if self.use_sotp and has_segments:
            intr = self.sotp.compute(security)
            if intr.confidence == 0.0:
                intr = self.intrinsic_dcf.compute(security, fcfe_assumptions)
        else:
            intr = self.intrinsic_dcf.compute(security, fcfe_assumptions)
            
        tri = self.triangulator.triangulate(rev, rel, intr)
        
        implied_move = tri.cluster_center
        summary = self._build_summary(rev, rel, intr, tri)
        
        report = PipelineReport(
            ticker=security.ticker,
            reverse_dcf=rev,
            relative=rel,
            intrinsic=intr,
            triangulation=tri,
            implied_move_pct=implied_move,
            summary=summary
        )
        
        if macro:
            report = self.macro_overlay.apply(report, security, macro)
            
        verdict_gen = VerdictGenerator()
        report.final_verdict = verdict_gen.generate(tri, rel, security)
        
        return report

    @staticmethod
    def _build_summary(rev: ValuationResult, rel: ValuationResult, intr: ValuationResult, tri: TriangulationResult) -> str:
        if tri.verdict == "no_data":
            return "Insufficient data across all methods — no verdict."
        if tri.verdict == "single_method":
            method = tri.cluster_members[0].value if tri.cluster_members else "single method"
            return f"Only {method} produced a result — verdict is low confidence."
        return "Verdict generated."
