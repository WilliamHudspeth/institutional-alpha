"""Macro regime classification for the Stage 5/6 overlay.

`iam.analytics.regime` classifies rich ``RegimeIndicators`` to reweight
*factors*. This module answers a narrower valuation question from the sparse
``MacroConditions`` the pipeline actually receives: which named shock applies,
how hard should the overlay's gate lean into it, and what does the regime do
to the discount rate?

The classification deliberately mirrors the shock mapping the overlay has
always used (``MacroOverlay._map_to_shock``), so wiring the classifier in
front of the elasticity scaling changes behavior only where the regime says
it should (stagflation), never silently elsewhere:

  * rate rising + PMI contracting  -> STAGFLATION (worst case: rates up while
    growth stalls; the gate is tightened via ``shock_multiplier``)
  * rate rising                    -> TIGHTENING
  * rate falling                   -> EASING
  * rate flat                      -> NEUTRAL

All thresholds and premia are explicit module constants ("No Magic Numbers").
Pure functions of ``MacroConditions`` — no I/O, no mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from iam.data.macro import (
    RATE_HIKE_SHOCK,
    RECESSION_SHOCK,
    STAGFLATION_SHOCK,
    MacroConditions,
    MacroShock,
)
from iam.elasticity.math_utils import clamp

# PMI below this reads as a contracting economy.
PMI_CONTRACTION_CEILING = 50.0

# Additive regime premium on the discount rate (decimal). Stagflation demands
# a real risk repricing; easing gives some of the baseline premium back.
REGIME_WACC_PREMIUM: dict[str, float] = {
    "stagflation": 0.015,
    "tightening": 0.005,
    "easing": -0.005,
    "neutral": 0.0,
}

# Multiplier applied to the raw rate shock BEFORE elasticity scaling. Only
# stagflation tightens the overlay's gate: the same bps move is more damaging
# when growth is stalling at the same time.
REGIME_SHOCK_MULTIPLIER: dict[str, float] = {
    "stagflation": 1.25,
    "tightening": 1.0,
    "easing": 1.0,
    "neutral": 1.0,
}

# Yield-curve duration risk: curve stress runs 0 (steep) -> 1 (deeply
# inverted), centered at a flat curve, saturating at +/- this slope.
CURVE_STRESS_SATURATION_SLOPE = 0.01  # 100bps of 10y-2y slope
# Rate elasticity at which a business counts as fully duration-bound
# (matches iam.elasticity.elasticity.RATE_ELASTICITY_MAX).
DURATION_BOUND_ELASTICITY = 3.0


class MacroRegime(str, Enum):
    EASING = "easing"
    TIGHTENING = "tightening"
    STAGFLATION = "stagflation"
    NEUTRAL = "neutral"


@dataclass
class MacroRegimeAssessment:
    """The classifier's output, consumed by ``MacroOverlay.apply``."""

    regime: MacroRegime
    shock: MacroShock
    wacc_premium: float  # additive, decimal
    shock_multiplier: float  # applied to raw bps ahead of elasticity scaling
    narrative: str = ""
    components: dict[str, float] = field(default_factory=dict)


class MacroRegimeClassifier:
    """Classify ``MacroConditions`` into a named regime."""

    def classify(self, macro: MacroConditions) -> MacroRegimeAssessment:
        rate_change = macro.rate_change if macro.rate_change is not None else 0.0

        if rate_change > 0 and macro.pmi < PMI_CONTRACTION_CEILING:
            regime = MacroRegime.STAGFLATION
            shock = STAGFLATION_SHOCK
        elif rate_change > 0:
            regime = MacroRegime.TIGHTENING
            shock = RATE_HIKE_SHOCK
        elif rate_change < 0:
            regime = MacroRegime.EASING
            shock = RECESSION_SHOCK
        else:
            regime = MacroRegime.NEUTRAL
            shock = RECESSION_SHOCK  # preserves the legacy flat-rate mapping

        wacc_premium = REGIME_WACC_PREMIUM[regime.value]
        multiplier = REGIME_SHOCK_MULTIPLIER[regime.value]
        narrative = (
            f"Rate change {rate_change * 10000:+.0f} bps, PMI {macro.pmi:.1f}, "
            f"inflation {macro.inflation_rate:.1%} -> {regime.value} "
            f"(shock x{multiplier:.2f}, WACC premium {wacc_premium:+.2%})."
        )
        return MacroRegimeAssessment(
            regime=regime,
            shock=shock,
            wacc_premium=wacc_premium,
            shock_multiplier=multiplier,
            narrative=narrative,
            components={
                "rate_change_bps": rate_change * 10000.0,
                "pmi": macro.pmi,
                "inflation_rate": macro.inflation_rate,
                "shock_multiplier": multiplier,
                "wacc_premium": wacc_premium,
            },
        )


def regime_conditional_wacc(base_wacc: float, regime: MacroRegime) -> float:
    """Discount rate adjusted for the regime's risk repricing."""
    return base_wacc + REGIME_WACC_PREMIUM[regime.value]


def yield_curve_duration_risk(
    slope_10y_2y: float | None,
    rate_elasticity: float | None,
) -> float | None:
    """Duration risk in [0, 1]: curve stress x how duration-bound the name is.

    ``slope_10y_2y`` is decimal (0.005 = 50bps steep; negative = inverted).
    A deeply inverted curve (<= -100bps) with a fully duration-bound business
    (rate elasticity >= 3) scores 1.0; a steep curve or a short-duration
    business scores near 0. Returns None when either input is unmeasured —
    callers degrade rather than assume.
    """
    if slope_10y_2y is None or rate_elasticity is None:
        return None
    curve_stress = clamp(0.5 - slope_10y_2y / (2.0 * CURVE_STRESS_SATURATION_SLOPE), 0.0, 1.0)
    duration = clamp(rate_elasticity / DURATION_BOUND_ELASTICITY, 0.0, 1.0)
    return curve_stress * duration
