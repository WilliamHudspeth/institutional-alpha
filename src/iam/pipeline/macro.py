"""Stage 5: Macro Regime Overlay.

Acts as a filter on top of the valuation core (Stages 1-4). Evaluates whether 
the current macro regime acts as a headwind or tailwind for the specific 
security, adjusting confidence or flagging regime-incompatible valuations.
"""

from iam.data.security import Security
from iam.data.macro import MacroConditions
from iam.pipeline.orchestrator import PipelineReport

class MacroOverlay:
    """Evaluates pipeline outputs against prevailing macro regimes."""

    def apply(self, report: PipelineReport, security: Security, macro: MacroConditions) -> PipelineReport:
        notes = []
        confidence_multiplier = 1.0
        m = security.market
        f = security.fundamentals

        # 1. Real Rate Regime vs. High Duration (High Multiple)
        if macro.real_rate_trend and macro.real_rate_trend > 0:
            if m.pe_ttm and m.pe_ttm > 40:
                confidence_multiplier *= 0.80
                notes.append("Macro Headwind: High-multiple duration risk in a rising real-rate regime.")

        # 2. Credit Spreads vs. Leverage
        if macro.credit_spread_hy_oas and macro.credit_spread_hy_oas > 5.0:  # e.g., >500 bps
            net_debt = (f.total_debt or 0) - (f.cash_and_equivalents or 0)
            if net_debt > 0 and (f.ebitda_ttm and (net_debt / f.ebitda_ttm) > 3.0):
                confidence_multiplier *= 0.75
                notes.append("Macro Headwind: Elevated credit spreads constrain refinancing for levered balance sheets.")

        # 3. PMI Contraction vs. Cyclicality
        if macro.pmi_direction and macro.pmi_direction < 50:
            # Assuming cyclicals are tagged in security.qualitative or inferred via sector
            if security.sector in ["Industrials", "Materials", "Consumer Discretionary"]:
                confidence_multiplier *= 0.85
                notes.append("Macro Headwind: Contracting PMI generally compresses cyclical operating margins.")

        # Apply adjustments to the existing report
        if notes:
            report.triangulation.confidence *= confidence_multiplier
            report.triangulation.notes.append("--- Stage 5: Macro Overlay Applied ---")
            report.triangulation.notes.extend(notes)
            report.summary += f" (Note: Triangulation confidence reduced to {report.triangulation.confidence:.2f} due to macro headwinds)."

        return report
