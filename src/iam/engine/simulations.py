"""Simulation mathematical logic extracted from UI components.

This module provides the grid generation functions for the DCF terrain and
fragility surfaces, separating calculation from rendering.
"""

import math
import random


def saddle_demo_grid(n: int = 16) -> list[list[float]]:
    g = []
    for i in range(n):
        row = []
        for j in range(n):
            x = (j / (n - 1)) * 2 - 1
            y = (i / (n - 1)) * 2 - 1
            row.append(x * x - y * y)  # classic saddle
        g.append(row)
    return g


def dcf_terrain_grid(
    base_value: float, growth: float, discount: float, n: int = 16
) -> list[list[float]]:
    """Synthetic-but-plausible DCF value surface over growth × discount.

    Value rises with growth, falls steeply as discount approaches growth
    (Gordon-style sensitivity).
    """
    g = []
    g_lo, g_hi = max(-0.02, growth - 0.08), growth + 0.08
    d_lo, d_hi = max(0.04, discount - 0.05), discount + 0.05
    for i in range(n):
        d = d_lo + (d_hi - d_lo) * i / (n - 1)
        row = []
        for j in range(n):
            gr = g_lo + (g_hi - g_lo) * j / (n - 1)
            spread = max(0.005, d - gr)  # Gordon growth denominator
            val = base_value * (1.0 + gr) / spread
            row.append(val)
        g.append(row)
    return g


def fragility_grid(dcf_grid: list[list[float]]) -> list[list[float]]:
    """Gradient-magnitude surface from a value grid: steep = fragile."""
    n = len(dcf_grid)
    m = len(dcf_grid[0]) if n else 0
    out = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            dx = abs(dcf_grid[i][min(j + 1, m - 1)] - dcf_grid[i][max(j - 1, 0)])
            dy = abs(dcf_grid[min(i + 1, n - 1)][j] - dcf_grid[max(i - 1, 0)][j])
            out[i][j] = math.hypot(dx, dy)
    return out


def simulate_price_tick(current_price: float, volatility: float = 0.004) -> float:
    """Simulate a single live price tick using a Gaussian random walk."""
    return max(1.0, current_price + random.gauss(0, current_price * volatility))
