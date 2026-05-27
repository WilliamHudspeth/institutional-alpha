from __future__ import annotations
from typing import TYPE_CHECKING
from iam.data.security import Security
from iam.data.macro import MacroConditions
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions

if TYPE_CHECKING:
    from iam.pipeline.orchestrator import PipelineReport

class MacroOverlay:
    '''Threshold-gated macro overlay for the Valuation Pipeline.'''
    
    def __init__(self, rate_shock_threshold_bps: float = 50.0):
        self.rate_shock_threshold_bps = rate_shock_threshold_bps
        self.dcf_engine = FCFEDCF()

    def apply(self, report: PipelineReport, security: Security, macro: MacroConditions) -> PipelineReport:
        # 1. Check if the threshold is breached
        if abs(macro.rate_shock_bps) >= self.rate_shock_threshold_bps:
            direction = 'Rising' if macro.rate_shock_bps > 0 else 'Falling'
            shock_pct = macro.rate_shock_bps / 10000.0  # Convert bps to decimal
            
            report.summary += f"\n[MACRO OVERLAY TRIGGERED]: {direction} rate shock of {macro.rate_shock_bps} bps detected (exceeds {self.rate_shock_threshold_bps} bps threshold)."
            
            # 2. Structurally alter assumptions (e.g., raise WACC by the shock amount)
            qualitative = security.qualitative or {}
            base_wacc = qualitative.get('forecast_discount_rate', 0.09)
            new_wacc = base_wacc + shock_pct
            
            stressed_assumptions = FCFEAssumptions(
                discount_rate=new_wacc,
                high_growth=qualitative.get('forecast_growth', 0.08),
                terminal_growth=qualitative.get('forecast_terminal_growth', 0.025)
            )
            
            report.summary += f"\n  -> Forcing Intrinsic DCF recalculation with stressed WACC: {new_wacc:.1%}"
            
            # 3. Force the recalculation
            stressed_intrinsic = self.dcf_engine.compute(security, stressed_assumptions)
            
            # 4. Overwrite the report's intrinsic result
            report.intrinsic = stressed_intrinsic
            
        else:
            report.summary += f"\n[MACRO OVERLAY]: Rate shift of {macro.rate_shock_bps} bps is within tolerance ({self.rate_shock_threshold_bps} bps). No recalculation triggered."

        return report
