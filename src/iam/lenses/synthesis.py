"""Synthesis engine for valuation lenses.

Lenses are blended into a single weighted price target. Each lens contributes
in proportion to its own ``confidence``. Optionally, an empirically-calibrated
*reliability* weight (from the backtest IC calibration) further scales each
lens's contribution — closing the loop between the historical IC measured in
``iam.backtest`` and the live verdict.

Reliability wiring (the important part):

  - Reliabilities are keyed by *signal* (``cost_of_equity``, ``fcfe_upside``,
    ``relative_value``), not by lens. ``_LENS_TO_SIGNAL`` is the explicit,
    reviewable mapping from a lens to the signal whose calibration governs it.
    A lens with no mapping falls back to ``_DEFAULT_RELIABILITY``.

  - The wiring is a strict no-op until a genuine calibration exists: passing
    ``reliabilities=None`` reproduces the legacy behaviour exactly, and passing
    *uniform* reliabilities (the loader's safe defaults) leaves the weighted
    average unchanged because a constant factor cancels in a normalised mean.
    It only moves the output once per-signal weights actually diverge — i.e.
    after a real empirical IC run populates the calibration file.

  - Do not make reliability-weighting default-on until you've validated that
    empirical weights improve IC. The call sites gate activation behind
    ``is_empirical_calibration()`` for exactly this reason.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from iam.lenses.base import LensResult

# Explicit lens -> calibrated-signal mapping. No magic: a lens is governed by
# the signal whose historical IC most directly measures what the lens prices.
# Edit deliberately; an unmapped lens uses _DEFAULT_RELIABILITY.
_LENS_TO_SIGNAL: dict[str, str] = {
    "platform_compounder": "fcfe_upside",
    "rate_sensitive": "cost_of_equity",
    "expectations_difficulty": "cost_of_equity",
    "damodaran": "fcfe_upside",
    "business_reality": "relative_value",
}

# Institutional baseline used when a lens maps to no calibrated signal, or when
# the calibration file omits that signal. Matches reliability_loader._DEFAULTS.
_DEFAULT_RELIABILITY = 0.70


@dataclass
class SynthesisResult:
    weighted_fair_value_low: float | None
    weighted_fair_value_high: float | None
    weighted_implied_move_pct: float | None
    narratives: list[str]


def _effective_confidence(lens: LensResult, reliabilities: dict[str, float] | None) -> float:
    """Lens confidence, optionally scaled by its calibrated reliability.

    ``reliabilities=None`` returns raw confidence (legacy behaviour).
    """
    if reliabilities is None:
        return lens.confidence
    signal = _LENS_TO_SIGNAL.get(lens.lens_name, lens.lens_name)
    return lens.confidence * reliabilities.get(signal, _DEFAULT_RELIABILITY)


def synthesize_lenses(
    lenses: Sequence[LensResult],
    reliabilities: dict[str, float] | None = None,
) -> SynthesisResult:
    """Combine multiple LensResult outputs into a weighted summary.

    Diagnostic lenses (where ``implied_move_pct`` is None) are skipped for the
    weighted fair value calculation but their narratives are preserved.

    Args:
        lenses: the lens outputs to blend.
        reliabilities: optional ``{signal: weight}`` map from the IC
            calibration. ``None`` (default) preserves legacy confidence-only
            weighting; see module docstring for the no-op guarantee.
    """
    # Rule 5: diagnostic lenses are skipped in the weighted average
    valid_lenses = [
        l
        for l in lenses
        if l.fair_value_low is not None
        and l.fair_value_high is not None
        and l.implied_move_pct is not None
        and l.confidence > 0
    ]

    narratives = [f"{l.lens_name.upper()}: {l.narrative}" for l in lenses]

    # Precompute (lens, effective_weight) so reliability scaling is applied
    # consistently across all three weighted aggregates.
    weighted = [(l, _effective_confidence(l, reliabilities)) for l in valid_lenses]
    total_w = sum(w for _, w in weighted)

    if not weighted or total_w == 0:
        return SynthesisResult(
            weighted_fair_value_low=None,
            weighted_fair_value_high=None,
            weighted_implied_move_pct=None,
            narratives=narratives,
        )

    weighted_low = sum((l.fair_value_low or 0.0) * w for l, w in weighted) / total_w
    weighted_high = sum((l.fair_value_high or 0.0) * w for l, w in weighted) / total_w
    weighted_move = sum((l.implied_move_pct or 0.0) * w for l, w in weighted) / total_w

    return SynthesisResult(
        weighted_fair_value_low=weighted_low,
        weighted_fair_value_high=weighted_high,
        weighted_implied_move_pct=weighted_move,
        narratives=narratives,
    )
