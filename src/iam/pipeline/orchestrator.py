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

    def explain(self, verbose: bool = False) -> str:
        if verbose:
            from iam.pipeline.verdict import (
                EXPLAIN_STAGE_1, EXPLAIN_STAGE_2, EXPLAIN_STAGE_3, 
                EXPLAIN_STAGE_4, EXPLAIN_STAGE_5, EXPLAIN_STAGE_6, EXPLAIN_STAGE_7
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
        self.macro_overlay = MacroOverlay(self.intrinsic_dcf)
        self.use_sotp = use_sotp_when_segments_available
        
    @staticmethod
    def _calculate_dynamic_wacc(security: Security) -> Optional[dict]:
        from iam.valuation.damodaran_defaults import build_wacc
        
        f = security.fundamentals
        m = security.market
        if not f or not m:
            return None
            
        ebit = None
        if getattr(f, 'revenue_ttm', None) and getattr(f, 'operating_margin', None):
            ebit = f.revenue_ttm * f.operating_margin
        if ebit is None:
            ebit = getattr(f, 'ebitda_ttm', None) or 0.0
            
        interest = getattr(f, 'interest_expense_ttm', None) or 0.0
        
        d_to_e = 0.0
        total_debt = getattr(f, 'total_debt', None) or 0.0
        market_cap = getattr(m, 'market_cap', None) or 0.0
        if total_debt > 0 and market_cap > 0:
            d_to_e = total_debt / market_cap
            
        ke = 0.09
        rf = 0.043
        tax_rate = 0.21
        
        return build_wacc(ke=ke, ebit=ebit, interest_expense=interest, rf=rf, d_to_e=d_to_e, tax_rate=tax_rate)

    def run(self, security: Security, fcfe_assumptions: Optional[FCFEAssumptions] = None, macro: Optional[MacroConditions] = None) -> PipelineReport:
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
            wacc_note = f"Dynamic WACC applied: {dynamic_wacc:.2%} (Rating: {rating})"

        # Stage 1: Reverse DCF
        reverse_dcf_res = self.reverse_dcf.compute(security)
        
        if wacc_info:
            self.reverse_dcf.r = original_r
            
        # Stage 2: Relative Valuation
        relative_res = self.relative.compute(security)
        
        # Stage 3: Intrinsic DCF / SOTP
        if self.use_sotp and security.fundamentals and getattr(security.fundamentals, 'segments', None):
            intrinsic_res = self.sotp.compute(security)
        else:
            intrinsic_res = self.intrinsic_dcf.compute(security, fcfe_assumptions)
            
        if wacc_info and wacc_note:
            intrinsic_res.notes.append(wacc_note)
            
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
            summary=triangulation_res.verdict
        )
        
        # Stages 5 & 6: Macro Overlay
        if macro:
            report = self.macro_overlay.apply(report, security, macro)
            if report.intrinsic.fair_value_per_share != intrinsic_res.fair_value_per_share:
                report.triangulation = self.triangulator.triangulate(
                    report.reverse_dcf, report.relative, report.intrinsic
                )
                report.implied_move_pct = report.triangulation.cluster_center
                
        # Stage 7: Verdict
        report.final_verdict = VerdictGenerator().generate(report.triangulation, report.relative, security)

        return report
