"""Small pure-math helpers shared across the elasticity layer.

These are intentionally *implemented* (not stubbed): they are the trivial,
well-defined building blocks the scoring methods compose. Keeping them here —
tested independently — lets the durability/elasticity implementations stay
readable and lets the test suite pin the numeric primitives separately from
the (initially unimplemented) scoring logic.

All functions are side-effect free and never raise on empty/degenerate input;
they return ``None`` or a neutral value instead, consistent with the rest of
the codebase's "degrade, don't crash" convention.
"""

from __future__ import annotations

from collections.abc import Sequence


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp ``x`` to the closed interval [lo, hi]."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def mean(values: Sequence[float]) -> float | None:
    """Arithmetic mean, or None for an empty sequence."""
    if not values:
        return None
    return sum(values) / len(values)


def pstdev(values: Sequence[float]) -> float | None:
    """Population standard deviation, or None if fewer than 2 points."""
    if len(values) < 2:
        return None
    mu = sum(values) / len(values)
    var = sum((v - mu) ** 2 for v in values) / len(values)
    return var**0.5


def coefficient_of_variation(values: Sequence[float]) -> float | None:
    """Population CV = stdev / |mean|.

    Returns None when it is undefined: fewer than 2 points, or a mean of zero.
    Uses the absolute mean so a series that straddles zero still yields a
    positive, interpretable dispersion measure.
    """
    if len(values) < 2:
        return None
    mu = sum(values) / len(values)
    if mu == 0:
        return None
    sd = pstdev(values)
    if sd is None:
        return None
    return sd / abs(mu)


def stability_from_series(values: Sequence[float], scale: float) -> float | None:
    """Map a series' dispersion to a 0..1 *stability* score.

    Higher = more stable (less volatile). Defined as::

        1 - clamp(coefficient_of_variation(values) / scale, 0, 1)

    ``scale`` is the CV at which stability is considered fully eroded (maps to
    0.0). For example, ``scale=1.0`` means a series whose stdev equals its mean
    scores 0.0 stability. Returns None when CV is undefined.
    """
    cv = coefficient_of_variation(values)
    if cv is None:
        return None
    if scale <= 0:
        return None
    return 1.0 - clamp(cv / scale, 0.0, 1.0)
