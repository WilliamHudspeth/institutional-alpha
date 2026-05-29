"""Durability scoring: how much cash flow survives if growth stalls.

STATUS: framework stub. ``DurabilityScorer.score`` raises NotImplementedError.
The docstring below is the implementation spec; ``tests/test_elasticity.py``
encodes it as assertions.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.elasticity.math_utils import clamp, mean, stability_from_series
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
        f = security.fundamentals
        q = security.qualitative or {}
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        # Signal 1: Recurring revenue share
        recurring = q.get("recurring_revenue_pct")
        if recurring is not None:
            recurring = clamp(float(recurring), 0.0, 1.0)
            components["recurring_revenue_pct"] = recurring
        else:
            confidence *= 0.6
            notes.append("No recurring_revenue_pct in qualitative.")

        # Signal 2: Margin stability
        margin_stability = stability_from_series(f.operating_margin_history, MARGIN_STABILITY_SCALE)
        if margin_stability is not None:
            components["margin_stability"] = margin_stability
        else:
            confidence *= 0.6
            notes.append("Insufficient operating_margin_history (< 2 points).")

        # Signal 3: FCF stability
        fcf_stability = stability_from_series(f.fcf_history, FCF_STABILITY_SCALE)
        if fcf_stability is not None:
            components["fcf_stability"] = fcf_stability
        else:
            confidence *= 0.6
            notes.append("Insufficient fcf_history (< 2 points).")

        # If all three signals are absent, return None score
        if recurring is None and margin_stability is None and fcf_stability is None:
            return DurabilityScore(
                score=None,
                confidence=0.0,
                components=components,
                narrative="All three durability signals absent.",
                notes=notes,
            )

        # Blending rule: compute stability as mean of the two volatility scores
        margin_s = margin_stability if margin_stability is not None else NEUTRAL_SUBSCORE
        fcf_s = fcf_stability if fcf_stability is not None else NEUTRAL_SUBSCORE
        stab = mean([margin_s, fcf_s])
        assert stab is not None
        components["stability"] = stab

        # Final score blending
        if recurring is not None:
            score = RECURRING_WEIGHT * recurring + STABILITY_WEIGHT * stab
        else:
            score = stab

        score = clamp(score, 0.0, 1.0)

        narrative = f"Durability score: {score:.2f}"
        if recurring is not None:
            narrative += f" (recurring {recurring:.0%} + stability {stab:.2f})"
        else:
            narrative += f" (stability {stab:.2f} only)"

        return DurabilityScore(
            score=score,
            confidence=confidence,
            components=components,
            narrative=narrative,
            notes=notes,
        )
