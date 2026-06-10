"""Excess-return fade curves (Damodaran Law 4 helpers).

High ROIC attracts competition; competition compresses margins; ROIC
mean-reverts toward the cost of capital. These helpers build the explicit
glide paths the law checks reason about. They are pure functions — no I/O,
no mutation — and never raise on degenerate input.
"""

from __future__ import annotations

# Default number of years over which excess returns glide toward the cost of
# capital. Damodaran's empirical fade evidence spans 5-10 years; 8 splits the
# band and matches the platform's 10-year forecast horizon convention.
DEFAULT_FADE_YEARS = 8

# Fraction of the starting excess return assumed to *survive* the fade. Truly
# durable franchises hold a sliver of excess return in perpetuity; assuming a
# full fade to zero would double-penalise wide-moat names that Law 1 already
# interrogates.
TERMINAL_EXCESS_RETENTION = 0.10


def excess_return_fade_path(
    roic: float,
    cost_of_capital: float,
    years: int = DEFAULT_FADE_YEARS,
    terminal_retention: float = TERMINAL_EXCESS_RETENTION,
) -> list[float]:
    """Linear glide path of ROIC from today's level toward the cost of capital.

    Returns ``years + 1`` points: index 0 is today's ROIC, index ``years`` is
    the faded terminal ROIC ``cost_of_capital + terminal_retention * excess``.
    If ROIC is already at or below the cost of capital there is nothing to
    fade and the path is flat at ``roic``.
    """
    if years <= 0:
        return [roic]
    excess = roic - cost_of_capital
    if excess <= 0:
        return [roic] * (years + 1)
    terminal_roic = cost_of_capital + terminal_retention * excess
    step = (roic - terminal_roic) / years
    return [roic - step * t for t in range(years + 1)]


def fade_adjusted_growth(
    roic: float,
    cost_of_capital: float,
    reinvestment_rate: float,
    years: int = DEFAULT_FADE_YEARS,
) -> float | None:
    """Sustainable growth at the *end* of the fade path.

    ``g = ROIC × reinvestment_rate`` evaluated at the faded terminal ROIC.
    This is the growth rate a model should be converging toward by the end of
    its explicit horizon, given Law 4. Returns None when the reinvestment rate
    is not usable (negative or > 1 after clamping is the caller's concern; we
    only reject non-finite logic here by contract of pure inputs).
    """
    if reinvestment_rate < 0:
        return None
    path = excess_return_fade_path(roic, cost_of_capital, years)
    return path[-1] * reinvestment_rate
