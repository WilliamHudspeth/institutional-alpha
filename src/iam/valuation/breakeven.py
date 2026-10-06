"""Two-variable break-even: Yr1-5 FCFE growth x steady-state operating margin.

Mirrors the owner's valuation paper section 2.1 table (margins 40-48% around
44.1%). Every cell is valued with Stage 1's own ``_present_value_two_stage`` at
the consensus Ke the report used, with the report's horizon, terminal growth and
ROE. The base cash flow scales with margin:

    base_ni(margin) = base_ni_stage1 x margin / base_margin

The break-even contour is, for each margin column, the growth at which value
equals price (bracket on the grid, then bisection, as ``value_grid`` does). At
the base margin the problem is exactly Stage 1's, so that column's growth equals
Stage 1's implied growth. Missing inputs give ``(None, reason)``; nothing is
defaulted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from iam.engine.market_implied import _present_value_two_stage
from iam.valuation.types import ValuationResult

# Axes mirror the owner's table: margins 40-48% around a 44.1% base, i.e. base +/- 4pp in 1pp steps
# (the base margin is the centre column). Growth is the Stage 1 implied growth +/- 8pp.
MARGIN_HALF_WIDTH_PP = 4
MARGIN_STEP = 0.01
GROWTH_HALF_WIDTH = 0.08
GROWTH_STEPS = 9  # 2pp steps across +/- 8pp
# Growth must stay above terminal growth; this is the minimum gap kept above it.
GROWTH_FLOOR_ABOVE_TERMINAL = 0.005
# Bisection stops at the exact root or bracket collapse; a hit must be within 0.1% of price.
PRICE_TOLERANCE = 1e-3
MAX_BISECTIONS = 100


@dataclass
class BreakEven:
    growths: list[float]  # rows
    margins: list[float]  # columns
    values: list[list[float | None]]  # values[i][j] at growths[i], margins[j]
    contour: list[tuple[float, float]]  # (margin, break-even growth) where value == price
    base: tuple[float, float, float]  # (stage 1 implied growth, base margin, value there)
    price: float
    ke: float
    base_margin: float
    base_ni: float
    n: int
    terminal_growth: float
    roe: float


def _value(base_ni: float, g: float, n: int, gt: float, r: float, roe: float) -> float | None:
    v = _present_value_two_stage(base_ni, g, n, gt, r, roe)
    return v if math.isfinite(v) and v > 0 else None


def _solve_growth(
    f,
    lo: float,
    hi: float,
    price: float,
) -> float | None:
    """Bisect for ``f(g) == price`` on ``[lo, hi]``; ``f`` may return None (no value)."""
    v_lo, v_hi = f(lo), f(hi)
    if v_lo is None or v_hi is None:
        return None
    s_lo = v_lo - price
    for _ in range(MAX_BISECTIONS):
        mid = (lo + hi) / 2.0
        v_mid = f(mid)
        if v_mid is None:
            return None
        s_mid = v_mid - price
        if s_mid == 0.0 or hi - lo < 1e-12:
            return mid
        if (s_mid < 0) == (s_lo < 0):
            lo, s_lo = mid, s_mid
        else:
            hi = mid
    mid = (lo + hi) / 2.0
    v_mid = f(mid)
    if v_mid is not None and abs(v_mid - price) / price < PRICE_TOLERANCE:
        return mid
    return None


def build_breakeven(
    stage1: ValuationResult | None,
    *,
    price: float | None,
    base_margin: float | None,
    ke: float | None,
) -> tuple[BreakEven | None, str | None]:
    """Build the growth x margin grid and break-even contour, or ``(None, reason)``."""
    if base_margin is None or base_margin <= 0:
        return None, "break-even needs a positive operating margin"
    if price is None or price <= 0:
        return None, "break-even needs a market price"
    if ke is None or ke <= 0:
        return None, "break-even needs the Stage 1 consensus Ke"
    a = getattr(stage1, "assumptions", None) or {}
    implied = getattr(stage1, "implied", None)
    g0 = getattr(implied, "implied_revenue_growth", None)
    base_ni = a.get("base_ni_per_share")
    if g0 is None or not base_ni or base_ni <= 0:
        return None, "break-even needs the Stage 1 implied growth and base earnings per share"
    if any(a.get(k) is None for k in ("high_growth_years", "terminal_growth", "roe")):
        return None, "break-even needs the Stage 1 horizon, terminal growth and ROE"

    n, gt, roe = int(a["high_growth_years"]), float(a["terminal_growth"]), float(a["roe"])
    base_ni = float(base_ni)

    g_lo = max(g0 - GROWTH_HALF_WIDTH, gt + GROWTH_FLOOR_ABOVE_TERMINAL)
    g_hi = max(g0 + GROWTH_HALF_WIDTH, g_lo + MARGIN_STEP)
    growths = [g_lo + (g_hi - g_lo) * i / (GROWTH_STEPS - 1) for i in range(GROWTH_STEPS)]
    margins = [
        base_margin + k * MARGIN_STEP
        for k in range(-MARGIN_HALF_WIDTH_PP, MARGIN_HALF_WIDTH_PP + 1)
        if base_margin + k * MARGIN_STEP > 0
    ]

    def ni_at(margin: float) -> float:
        return base_ni * margin / base_margin

    values = [[_value(ni_at(m), g, n, gt, ke, roe) for m in margins] for g in growths]

    contour: list[tuple[float, float]] = []
    for j, m in enumerate(margins):
        col = [(growths[i], values[i][j]) for i in range(len(growths)) if values[i][j] is not None]
        for (ga, va), (gb, vb) in zip(col, col[1:]):
            if va is None or vb is None:
                continue
            if min(va, vb) <= price <= max(va, vb):
                g = _solve_growth(lambda x, m=m: _value(ni_at(m), x, n, gt, ke, roe), ga, gb, price)
                if g is not None:
                    contour.append((m, g))
                    break

    base_v = _value(base_ni, g0, n, gt, ke, roe)
    if base_v is None:
        return None, "break-even base case did not converge"
    return (
        BreakEven(
            growths=growths,
            margins=margins,
            values=values,
            contour=contour,
            base=(float(g0), base_margin, base_v),
            price=price,
            ke=ke,
            base_margin=base_margin,
            base_ni=base_ni,
            n=n,
            terminal_growth=gt,
            roe=roe,
        ),
        None,
    )
