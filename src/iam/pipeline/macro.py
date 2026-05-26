from __future__ import annotations
from typing import TYPE_CHECKING
from iam.data.security import Security
from iam.data.macro import MacroConditions

if TYPE_CHECKING:
    # This import only happens during type checking, not at runtime
    from iam.pipeline.orchestrator import PipelineReport

class MacroOverlay:
    def apply(self, report: PipelineReport, security: Security, macro: MacroConditions) -> PipelineReport:
        # Example logic: Penalize high-duration growth stocks (e.g., low FCF yield) if rates rise
        if macro.real_rate_trend > 0 and report.intrinsic.fair_value_to_price is not None:
            if report.intrinsic.fair_value_to_price > 0.10: # High valuation
                report.summary += " [Macro: Rates rising, throttling growth valuation]"
                report.implied_move_pct = report.implied_move_pct * 0.8
        return report
