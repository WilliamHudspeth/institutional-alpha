from __future__ import annotations
from typing import TYPE_CHECKING
from iam.data.security import Security
from iam.data.macro import MacroConditions, MacroShock
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.types import ValuationResult

if TYPE_CHECKING:
    from iam.pipeline.orchestrator import PipelineReport

class MacroOverlay:
    '''Threshold-gated macro overlay for the Valuation Pipeline.'''
    
    def __init__(self, intrinsic_dcf: FCFEDCF, rate_shock_threshold_bps: float = 50.0):
        self.rate_shock_threshold_bps = rate_shock_threshold_bps
        self.stress_engine = MacroStressEngine(intrinsic_dcf)

    def apply(self, report: PipelineReport, security: Security, macro: MacroConditions) -> PipelineReport:
        # 1. Check if the threshold is breached
        if abs(macro.rate_shock_bps) >= self.rate_shock_threshold_bps:
            shock = self._map_to_shock(macro)
            
            report.summary += f"\n[MACRO OVERLAY TRIGGERED]: Rate shock of {macro.rate_shock_bps} bps detected (exceeds {self.rate_shock_threshold_bps} bps threshold)."
            report.summary += f"\n  -> Applying {shock.name} scenario."
            
            # Recalculate intrinsic value under stress
            stressed_intrinsic = self.stress_engine.run_stress_test(security, shock)
            
            # Overwrite the report's intrinsic result
            report.intrinsic = stressed_intrinsic
            if not hasattr(report, 'notes'):
                report.notes = []
            report.notes.append(f"Macro Overlay triggered: {shock.name} scenario applied.")
            
        else:
            report.summary += f"\n[MACRO OVERLAY]: Rate shift of {macro.rate_shock_bps} bps is within tolerance ({self.rate_shock_threshold_bps} bps). No recalculation triggered."

        return report

    def _map_to_shock(self, cond: MacroConditions) -> MacroShock:
        from iam.data.macro import STAGFLATION_SHOCK, RECESSION_SHOCK, RATE_HIKE_SHOCK
        # Dynamic scenario selection based on macro inputs
        if cond.rate_shock_bps > 0:
            if cond.pmi_direction < 50.0:
                return STAGFLATION_SHOCK
            return RATE_HIKE_SHOCK
        return RECESSION_SHOCK

class MacroStressEngine:
    def __init__(self, intrinsic_dcf: FCFEDCF):
        self.dcf = intrinsic_dcf

    def run_stress_test(self, security: Security, shock: MacroShock) -> ValuationResult:
        qualitative = security.qualitative or {}
        
        # 1. Capture original WACC and growth
        orig_wacc = qualitative.get('forecast_discount_rate', 0.09)
        orig_growth = qualitative.get('forecast_growth', 0.08)
        
        # 2. Apply the shock
        # Rate shock affects WACC; growth shock affects FCF projections
        stressed_wacc = orig_wacc + (shock.rate_shock_bps / 10000.0)
        stressed_growth = orig_growth + shock.growth_shock_pct
        
        # 3. Recalculate DCF using existing FCFEAssumptions
        stressed_assumptions = FCFEAssumptions(
            discount_rate=stressed_wacc,
            high_growth=stressed_growth,
            terminal_growth=qualitative.get('forecast_terminal_growth', 0.025)
        )
        
        return self.dcf.compute(security, stressed_assumptions)
