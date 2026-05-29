"""Durability scoring: how much cash flow survives if growth stalls.

STATUS: framework stub. ``DurabilityScorer.score`` raises NotImplementedError.
The docstring below is the implementation spec; ``tests/test_elasticity.py``
encodes it as assertions.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.elasticity.types import DurabilityScore

# --- Specification constants (the implementation MUST use these) ------------

# Weight on recurring-revenue share when it is supplied.
RECURRING_WEIGHT = 0.5
# Combined weight on the two volatility-derived sub-scores (split evenly).
STABILITY_WEIGHT = 0.5
# CV at which a margin/FCF series is treated as maximally unstable (-> 0.0).
MARGIN_STABILITY_SCALE = 1.0
FCF_STABILITY_SCALE = 1.0
# Neutral fallback used for a sub-score whose series is too sparse to measure.
NEUTRAL_SUBSCORE = 0.5


class DurabilityScorer:
    """Estimate the fraction of FCFE that persists in a no-growth world.

    The score blends three signals derived purely from the ``Security`` (no
    I/O, no mutation — same contract as ``iam.lenses.base.BaseLens``):

      1. **Recurring share** — ``security.qualitative['recurring_revenue_pct']``
         (decimal 0..1) when present. Directly proxies the cash-flow floor.
      2. **Margin stability** — ``stability_from_series`` over
         ``fundamentals.operating_margin_history`` with
         ``MARGIN_STABILITY_SCALE``. Stable margins => durable economics.
      3. **FCF stability** — ``stability_from_series`` over
         ``fundamentals.fcf_history`` with ``FCF_STABILITY_SCALE``.

    Blending rule
    -------------
    Let ``stab = mean(margin_stability, fcf_stability)`` where each missing
    sub-score falls back to ``NEUTRAL_SUBSCORE``.

      * If ``recurring_revenue_pct`` is present (call it ``r``, clamped to
        [0, 1])::

            score = RECURRING_WEIGHT * r + STABILITY_WEIGHT * stab

      * Otherwise::

            score = stab

    The final ``score`` is clamped to [0, 1].

    Confidence
    ----------
    Start at 1.0 and multiply by 0.6 for each of these that is missing:
    recurring share, a usable operating_margin_history (>= 2 points), a usable
    fcf_history (>= 2 points). If *all three* signals are absent, return
    ``score=None`` with ``confidence=0.0`` and an explanatory note.

    Components
    ----------
    Populate ``components`` with whichever of these were computed:
    ``recurring_revenue_pct``, ``margin_stability``, ``fcf_stability``,
    ``stability``.
    """

    def score(self, security: Security) -> DurabilityScore:
        raise NotImplementedError(
            "DurabilityScorer.score is a framework stub — implement per the "
            "class docstring spec until tests/test_elasticity.py passes."
        )
