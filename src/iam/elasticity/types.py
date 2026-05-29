"""Data contracts for the Durability + Elasticity Scoring Layer.

These dataclasses are the *stable* part of the framework. They mirror the
conventions used by ``iam.lenses.base.LensResult`` and
``iam.valuation.types.ValuationResult``:

  * every score is accompanied by a ``confidence`` in [0, 1];
  * a ``components`` dict captures the sub-values that fed the headline number
    (for audit / display), keyed by short snake_case names;
  * a ``narrative`` gives a plain-English one-liner;
  * ``notes`` collects any caveats raised while scoring.

Scores are ``None`` when the inputs are too sparse to compute them — callers
must degrade gracefully rather than treating a missing score as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DurabilityScore:
    """How much of a business's cash flow survives if growth stalls.

    ``score`` is in [0, 1]: the estimated fraction of current FCFE that
    persists in a no-growth, stressed world. 1.0 = bond-like, fully recurring;
    0.0 = entirely transactional / cyclical with no floor.
    """

    score: float | None  # in [0, 1], or None if uncomputable
    confidence: float  # in [0, 1]
    components: dict[str, float] = field(default_factory=dict)
    narrative: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class ElasticityProfile:
    """How sharply a business re-prices under growth and rate stress.

    ``growth_elasticity`` is in [0, 2]: the multiple by which FCFE contracts
    relative to a revenue/growth shock. 1.0 = proportional (pure variable
    cost); >1.0 = operating leverage amplifies the hit; <1.0 = cushioned.

    ``rate_elasticity`` is in [0, 3]: the magnitude of the fair-value swing
    (as a multiple of a baseline 50bps DCF sensitivity) per 50bps rate move.
    Long-duration cash flows score high; short-lived flows score low.
    """

    growth_elasticity: float | None  # in [0, 2], or None
    rate_elasticity: float | None  # in [0, 3], or None
    confidence: float  # in [0, 1]
    components: dict[str, float] = field(default_factory=dict)
    narrative: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class StressScenario:
    """A named macro stress to apply.

    Shocks are *additive* to the baseline assumptions, matching the convention
    in ``iam.data.macro.MacroShock``:

      * ``growth_shock_pct``: change to the high-growth rate, in decimal
        (e.g. -0.05 = "growth drops 5 percentage points").
      * ``rate_shock_bps``: change to the discount rate, in basis points
        (e.g. +50.0 = "rates rise 50bps").
    """

    name: str
    growth_shock_pct: float = 0.0
    rate_shock_bps: float = 0.0


@dataclass
class StressResponse:
    """The output of :meth:`DurabilityStressEngine.run`.

    Ties the durability and elasticity diagnostics to a concrete re-priced
    fair value and an estimated conviction drift, so the synthesis layer can
    surface an *elasticity-aware* stress report rather than a flat shock.
    """

    scenario: StressScenario
    base_fair_value: float | None
    stressed_fair_value: float | None
    value_change_pct: float | None  # stressed / base - 1
    durability: DurabilityScore
    elasticity: ElasticityProfile
    conviction_drift: float | None  # in [0, 1]; how far conviction should fall
    narrative: str = ""
    notes: list[str] = field(default_factory=list)
