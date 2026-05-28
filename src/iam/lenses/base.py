"""Base types shared by all valuation lenses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LensResult:
    """Output of a single valuation lens.

    Lenses that are purely diagnostic (e.g., expectations_difficulty) set
    fair_value_low, fair_value_high, and implied_move_pct to None.
    The synthesis engine skips them for the weighted price target.
    """

    lens_name: str
    fair_value_low: float | None  # WACC+1% scenario
    fair_value_high: float | None  # WACC-1% scenario
    implied_move_pct: float | None  # midpoint / current_price - 1
    confidence: float  # in [0, 1]
    narrative: str  # plain-English one-liner
    assumptions: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class BaseLens:
    """Abstract base for all valuation lenses.

    Subclasses implement compute() and return a LensResult.
    Lenses must not modify the Security object or call external I/O.
    """

    name: str = "unnamed"

    def compute(self, security) -> LensResult:
        raise NotImplementedError


def two_stage_pv(
    fcfe0: float,
    g_high: float,
    n: int,
    g_terminal: float,
    r: float,
) -> float | None:
    """PV per share of a two-stage FCFE stream.

    Returns None when r <= g_terminal (model would not converge).
    """
    if r <= g_terminal:
        return None
    pv = 0.0
    for t in range(1, n + 1):
        pv += fcfe0 * ((1 + g_high) ** t) / ((1 + r) ** t)
    fcfe_n = fcfe0 * ((1 + g_high) ** n)
    tv = fcfe_n * (1 + g_terminal) / (r - g_terminal)
    pv += tv / ((1 + r) ** n)
    return pv
