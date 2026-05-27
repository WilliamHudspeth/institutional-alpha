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
        rate_shock_bps = macro.rate_change * 10000.0
        if abs(rate_shock_bps) >= self.rate_shock_threshold_bps:
            shock = self._map_to_shock(macro)

            report.summary += f"\n[MACRO OVERLAY TRIGGERED]: Rate shock of {rate_shock_bps:.1f} bps detected (exceeds {self.rate_shock_threshold_bps} bps threshold)."
            report.summary += f"\n  -> Applying {shock.name} scenario."

            stressed_intrinsic = self.stress_engine.run_stress_test(security, shock)

            report.intrinsic = stressed_intrinsic
            if not hasattr(report, 'notes'):
                report.notes = []
            report.notes.append(f"Macro Overlay triggered: {shock.name} scenario applied.")

        else:
            report.summary += f"\n[MACRO OVERLAY]: Rate shift of {rate_shock_bps:.1f} bps is within tolerance ({self.rate_shock_threshold_bps} bps). No recalculation triggered."

        return report

    def _map_to_shock(self, cond: MacroConditions) -> MacroShock:
        from iam.data.macro import STAGFLATION_SHOCK, RECESSION_SHOCK, RATE_HIKE_SHOCK
        if cond.rate_change > 0:
            if cond.pmi < 50.0:
                return STAGFLATION_SHOCK
            return RATE_HIKE_SHOCK
        return RECESSION_SHOCK

class MacroStressEngine:
    def __init__(self, intrinsic_dcf: FCFEDCF):
        self.dcf = intrinsic_dcf

    def run_stress_test(self, security: Security, shock: MacroShock) -> ValuationResult:
        qualitative = security.qualitative or {}
        
        orig_wacc = qualitative.get('forecast_discount_rate', 0.09)
        orig_growth = qualitative.get('forecast_growth', 0.08)
        
        stressed_wacc = orig_wacc + (shock.rate_shock_bps / 10000.0)
        stressed_growth = orig_growth + shock.growth_shock_pct
        
        stressed_assumptions = FCFEAssumptions(
            discount_rate=stressed_wacc,
            high_growth=stressed_growth,
            terminal_growth=qualitative.get('forecast_terminal_growth', 0.025)
        )
        
        return self.dcf.compute(security, stressed_assumptions)
