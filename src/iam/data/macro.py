"""Macroeconomic data structures for the IAM framework."""

from dataclasses import dataclass
from typing import Optional

@dataclass
class MacroConditions:
    """Current macroeconomic regime indicators."""
    real_rate_trend: Optional[float] = None       # e.g., +1.0 for rising, -1.0 for falling
    liquidity_conditions: Optional[float] = None  # Normalized liquidity index (z-score)
    credit_spread_hy_oas: Optional[float] = None  # High Yield Option-Adjusted Spread (in %)
    yield_curve_slope: Optional[float] = None     # 10y - 2y spread (in bps or %)
    pmi_direction: Optional[float] = None         # > 50 expanding, < 50 contracting
    dollar_strength_dxy: Optional[float] = None   # DXY momentum/trend
