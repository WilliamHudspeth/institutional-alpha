"""Stage 5/6: elasticity-aware, threshold-gated macro overlay.

The original overlay applied uniform rate/growth shocks and gated purely on
the size of the rate move. This version reasons about *why* a specific
business is fragile (ROADMAP, "The Core Enhancement: Theory-First Stress
Testing"): it scales the raw macro shock by the business's measured rate and
growth elasticity before gating and re-pricing, and runs the
``DurabilityStressEngine`` to estimate how far conviction should drift.

A duration-bound business (rate elasticity ≈ 2) therefore triggers the
overlay on a smaller raw rate move than a short-duration one, and a fragile
business loses more conviction for the same value hit than a durable one.

When the elasticity profile cannot be computed (confidence 0 / missing
inputs), the overlay degrades gracefully to the original flat-shock
behavior — same gate, same re-pricing, no conviction drift.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from iam.data.macro import MacroConditions, MacroShock
from iam.data.security import Security
from iam.elasticity import DurabilityStressEngine, ElasticityScorer, StressScenario
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.types import ValuationResult

if TYPE_CHECKING:
    from iam.pipeline.orchestrator import PipelineReport


class MacroOverlay:
    """Threshold-gated, elasticity-aware macro overlay for the pipeline."""

    def __init__(
        self,
        intrinsic_dcf: FCFEDCF,
        rate_shock_threshold_bps: float = 50.0,
        durability_stress_engine: DurabilityStressEngine | None = None,
        elasticity_scorer: ElasticityScorer | None = None,
    ):
        self.rate_shock_threshold_bps = rate_shock_threshold_bps
        self.stress_engine = MacroStressEngine(intrinsic_dcf)
        self.durability_stress = durability_stress_engine or DurabilityStressEngine()
        self.elasticity_scorer = elasticity_scorer or ElasticityScorer()

    def apply(
        self, report: PipelineReport, security: Security, macro: MacroConditions
    ) -> PipelineReport:
        raw_rate_shock_bps = macro.rate_change * 10000.0

        # Elasticity-aware gate: a duration-bound business feels a 25bps move
        # like a 50bps one. Fall back to the raw shock when unmeasurable.
        profile = self.elasticity_scorer.profile(security)
        rate_elasticity = profile.rate_elasticity if profile.confidence > 0 else None
        growth_elasticity = profile.growth_elasticity if profile.confidence > 0 else None

        if rate_elasticity is not None:
            effective_rate_shock_bps = raw_rate_shock_bps * rate_elasticity
            report.summary += (
                f"\n[MACRO OVERLAY]: Effective rate shock {effective_rate_shock_bps:.1f} bps "
                f"(raw {raw_rate_shock_bps:.1f} bps x rate elasticity {rate_elasticity:.2f})."
            )
        else:
            effective_rate_shock_bps = raw_rate_shock_bps

        if abs(effective_rate_shock_bps) >= self.rate_shock_threshold_bps:
            shock = self._map_to_shock(macro)
            scaled_shock = self._scale_shock(shock, rate_elasticity, growth_elasticity)

            report.summary += (
                f"\n[MACRO OVERLAY TRIGGERED]: Rate shock of {effective_rate_shock_bps:.1f} bps "
                f"detected (exceeds {self.rate_shock_threshold_bps} bps threshold)."
            )
            report.summary += f"\n  -> Applying {scaled_shock.name} scenario."

            stressed_intrinsic = self.stress_engine.run_stress_test(security, scaled_shock)

            report.intrinsic = stressed_intrinsic
            report.intrinsic.notes.append(
                f"Macro Overlay triggered: {scaled_shock.name} scenario applied."
            )

            # Theory-first stress report: re-price with the durability engine
            # and estimate how far conviction should drift on this name.
            response = self.durability_stress.run(
                security,
                StressScenario(
                    name=scaled_shock.name,
                    growth_shock_pct=scaled_shock.growth_shock_pct,
                    rate_shock_bps=scaled_shock.rate_shock_bps,
                ),
            )
            report.stress_response = response
            if response.narrative:
                report.summary += f"\n  -> {response.narrative}"

        else:
            report.summary += (
                f"\n[MACRO OVERLAY]: Rate shift of {effective_rate_shock_bps:.1f} bps is within "
                f"tolerance ({self.rate_shock_threshold_bps} bps). No recalculation triggered."
            )

        return report

    @staticmethod
    def _scale_shock(
        shock: MacroShock,
        rate_elasticity: float | None,
        growth_elasticity: float | None,
    ) -> MacroShock:
        """Scale a named macro shock by the business's response functions.

        Unmeasured elasticities leave their leg of the shock untouched (flat
        behavior), so the overlay never invents sensitivity it didn't measure.
        """
        if rate_elasticity is None and growth_elasticity is None:
            return shock
        scaled = replace(
            shock,
            name=f"{shock.name} (elasticity-scaled)",
            rate_shock_bps=shock.rate_shock_bps
            * (rate_elasticity if rate_elasticity is not None else 1.0),
            growth_shock_pct=shock.growth_shock_pct
            * (growth_elasticity if growth_elasticity is not None else 1.0),
        )
        return scaled

    def _map_to_shock(self, cond: MacroConditions) -> MacroShock:
        from iam.data.macro import RATE_HIKE_SHOCK, RECESSION_SHOCK, STAGFLATION_SHOCK

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

        orig_wacc = qualitative.get("forecast_discount_rate", 0.09)
        orig_growth = qualitative.get("forecast_growth", 0.08)

        stressed_wacc = orig_wacc + (shock.rate_shock_bps / 10000.0)
        stressed_growth = orig_growth + shock.growth_shock_pct

        stressed_assumptions = FCFEAssumptions(
            discount_rate=stressed_wacc,
            high_growth=stressed_growth,
            terminal_growth=qualitative.get("forecast_terminal_growth", 0.025),
        )

        return self.dcf.compute(security, stressed_assumptions)
