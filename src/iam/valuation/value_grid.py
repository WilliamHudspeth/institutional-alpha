"""A real growth x discount-rate value grid built from the pipeline's own inputs.

Every number comes from the FCFE build-up that produced the intrinsic value
(base earnings per share, horizon, terminal growth, ROE) and from the reverse
DCF (the market-implied growth and discount rate). Nothing here has a default
or a demo fallback: if the inputs are missing, ``build_value_grid`` returns
``None`` and callers show "n/a".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from iam.valuation.reverse_dcf import _present_value_two_stage


@dataclass
class ValueGrid:
    growths: list[float]  # x axis
    rates: list[float]  # y axis (discount rate)
    values: list[list[float | None]]  # values[i][j] at rates[i], growths[j]; None = no convergence
    base: tuple[float, float, float]  # (growth, rate, value) of our base case
    market: tuple[float, float] | None  # (growth, rate) the price implies, if known
    price: float | None
    base_ni: float | None = None
    n: int | None = None
    gt: float | None = None
    roe: float | None = None

    def finite_values(self) -> list[float]:
        return [v for row in self.values for v in row if v is not None]


def _pv(base_ni: float, g: float, n: int, gt: float, r: float, roe: float) -> float | None:
    v = _present_value_two_stage(base_ni=base_ni, g_high=g, n=n, g_terminal=gt, r=r, roe=roe)
    return v if math.isfinite(v) and v > 0 else None


def _axis(center: float, half_width: float, steps: int, extra: float | None) -> list[float]:
    lo, hi = center - half_width, center + half_width
    if extra is not None:
        lo, hi = min(lo, extra - 0.01), max(hi, extra + 0.01)
    return [lo + (hi - lo) * i / (steps - 1) for i in range(steps)]


def fair_value_frontier(grid: ValueGrid) -> list[tuple[float, float]] | None:
    """Compute the curve in (growth, discount-rate) space where intrinsic value equals market price.

    For each discount-rate row, brackets the crossing between adjacent grid cells
    (skipping None cells), then solves exactly with _pv by bisection inside the bracket.
    Returns None when grid.price is None, invalid, or no row crosses.
    """
    if grid.price is None or grid.price <= 0:
        return None
    if grid.base_ni is None or grid.n is None or grid.gt is None or grid.roe is None:
        return None

    price = grid.price
    tol = 1e-4  # 0.01% tolerance
    max_iter = 60
    points: list[tuple[float, float]] = []

    for i, r in enumerate(grid.rates):
        row = grid.values[i]
        valid = [(grid.growths[j], row[j]) for j in range(len(grid.growths)) if row[j] is not None]
        if len(valid) < 2:
            continue

        for (g1, v1), (g2, v2) in zip(valid, valid[1:]):
            if v1 is None or v2 is None:
                continue
            if min(v1, v2) <= price <= max(v1, v2):
                lo, hi = min(g1, g2), max(g1, g2)
                v_lo = _pv(grid.base_ni, lo, grid.n, grid.gt, r, grid.roe)
                v_hi = _pv(grid.base_ni, hi, grid.n, grid.gt, r, grid.roe)
                if v_lo is None or v_hi is None:
                    continue

                if abs(v_lo - price) / price < tol:
                    points.append((lo, r))
                    break
                if abs(v_hi - price) / price < tol:
                    points.append((hi, r))
                    break

                increasing = v_hi >= v_lo
                g_cross: float | None = None
                for _ in range(max_iter):
                    mid = (lo + hi) / 2.0
                    v_mid = _pv(grid.base_ni, mid, grid.n, grid.gt, r, grid.roe)
                    if v_mid is None:
                        break
                    if abs(v_mid - price) / price < tol:
                        g_cross = mid
                        break
                    if (v_mid < price) if increasing else (v_mid > price):
                        lo = mid
                    else:
                        hi = mid
                else:
                    mid = (lo + hi) / 2.0
                    v_mid = _pv(grid.base_ni, mid, grid.n, grid.gt, r, grid.roe)
                    if v_mid is not None and abs(v_mid - price) / price < 1e-3:
                        g_cross = mid

                if g_cross is not None:
                    points.append((g_cross, r))
                    break

    return points if points else None


def build_value_grid(report, price: float | None = None, steps: int = 9) -> ValueGrid | None:
    """Build the grid from a PipelineReport, or return None if inputs are missing."""
    intrinsic = getattr(report, "intrinsic", None)
    comps = getattr(intrinsic, "components", None) or {}
    a = getattr(intrinsic, "assumptions", None) or {}
    base_ni = comps.get("base_ni_per_share")
    need = ("high_growth", "high_growth_years", "discount_rate", "terminal_growth", "roe")
    if not base_ni or any(a.get(k) is None for k in need):
        return None

    g0, r0 = float(a["high_growth"]), float(a["discount_rate"])
    gt, roe = float(a["terminal_growth"]), float(a["roe"])
    n = int(a["high_growth_years"])

    if price is None:
        fv = getattr(intrinsic, "fair_value_per_share", None)
        up = getattr(intrinsic, "fair_value_to_price", None)
        if fv and up is not None and up > -1:
            price = fv / (1 + up)

    market = None
    mie = getattr(report, "market_implied_engine", None)
    implied = getattr(mie, "implied", None) if mie else None
    if implied is not None and implied.implied_revenue_growth is not None:
        market = (
            float(implied.implied_revenue_growth),
            float(implied.discount_rate_assumed if implied.discount_rate_assumed else r0),
        )

    growths = _axis(g0, 0.06, steps, market[0] if market else None)
    rates = _axis(r0, 0.02, steps, market[1] if market else None)
    rates = [r for r in rates if r > gt + 0.005] or [r0]
    values = [[_pv(base_ni, g, n, gt, r, roe) for g in growths] for r in rates]
    base_v = _pv(base_ni, g0, n, gt, r0, roe)
    if base_v is None:
        return None
    return ValueGrid(
        growths,
        rates,
        values,
        (g0, r0, base_v),
        market,
        price,
        base_ni=float(base_ni),
        n=n,
        gt=gt,
        roe=roe,
    )
