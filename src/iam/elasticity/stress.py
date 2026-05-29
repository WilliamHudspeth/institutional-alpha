"""Theory-first stress engine.

Combines durability + elasticity diagnostics with a numeric re-pricing to
produce an *elasticity-aware* stress response: not "value drops 5% if rates
rise 50bps" but "this business is duration-bound; the move has 3x the baseline
impact and conviction should fall hard."

STATUS: framework stub. ``DurabilityStressEngine.run`` raises
NotImplementedError. The docstring below is the implementation spec;
``tests/test_elasticity.py`` encodes it as assertions.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.elasticity.durability import DurabilityScorer
from iam.elasticity.elasticity import ElasticityScorer
from iam.elasticity.types import StressResponse, StressScenario

# --- Specification constants ------------------------------------------------

DEFAULT_WACC = 0.09
DEFAULT_GROWTH = 0.08
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_HIGH_GROWTH_YEARS = 10

# Conviction-drift tuning: how a 100% value loss maps to conviction loss when
# the business is maximally fragile (durability 0). Drift is dampened by
# durability — durable businesses keep conviction even when price-stressed.
MAX_CONVICTION_DRIFT = 1.0


class DurabilityStressEngine:
    """Re-price a valuation under a stress scenario and estimate conviction
    drift, weighting the raw shock by the business's measured fragility.

    Construction allows injecting custom scorers (useful for testing); the
    defaults are the standard implementations.

    run() spec
    ----------
    Given a ``Security`` and a ``StressScenario``:

      1. Score durability and elasticity once via the injected scorers.
      2. Compute ``base_fair_value`` and ``stressed_fair_value`` with the
         shared ``two_stage_pv`` helper on the per-share FCFE base
         (``fundamentals.fcf_ttm / fundamentals.shares_outstanding``), reading
         WACC/growth/terminal from ``qualitative`` with the module defaults.
         The stressed run applies the scenario's additive shocks:
             stressed_growth = growth + scenario.growth_shock_pct
             stressed_wacc   = wacc + scenario.rate_shock_bps / 10000
      3. ``value_change_pct = stressed_fair_value / base_fair_value - 1`` (None
         if either value is None or base is 0).
      4. **Conviction drift** — the headline insight. A given value loss should
         erode conviction *more* for fragile businesses and *less* for durable
         ones::

             raw_loss = max(0, -value_change_pct)      # only downside counts
             fragility = 1 - durability.score          # 1=fragile, 0=durable
             conviction_drift = clamp(
                 raw_loss * fragility * MAX_CONVICTION_DRIFT, 0, 1
             )

         If durability.score is None, treat fragility as 1.0 (assume fragile)
         and add an explanatory note. If value_change_pct is None,
         conviction_drift is None.
      5. Build a plain-English ``narrative`` summarizing the move, the rate/
         growth elasticity, and the resulting drift.

    The Security is never mutated.
    """

    def __init__(
        self,
        durability_scorer: DurabilityScorer | None = None,
        elasticity_scorer: ElasticityScorer | None = None,
    ) -> None:
        self.durability_scorer = durability_scorer or DurabilityScorer()
        self.elasticity_scorer = elasticity_scorer or ElasticityScorer()

    def run(self, security: Security, scenario: StressScenario) -> StressResponse:
        raise NotImplementedError(
            "DurabilityStressEngine.run is a framework stub — implement per the "
            "class docstring spec until tests/test_elasticity.py passes."
        )
