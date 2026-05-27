"""MacroConditions — the structured macro input for the pipeline macro overlay.

Distinct from the qualitative MacroContext on Security, which factors consume.
MacroConditions is passed explicitly to ValuationPipeline.run() for
Stage 5 / macro overlay logic.

real_rate_trend is a numeric delta so that pipeline logic can use
  ``if macro.real_rate_trend > 0`` (rising) rather than string comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MacroConditions:
    """Numeric macro-environment snapshot for pipeline overlay (Stage 5)."""

    real_rate_10y: Optional[float] = None          # real 10Y rate (decimal)
    real_rate_trend: float = 0.0                   # positive = rising, negative = falling
    yield_curve_slope_10y_2y: Optional[float] = None

    credit_spread_hy: Optional[float] = None       # HY spread, decimal
    liquidity_index: Optional[float] = None        # normalized [-1, 1]
    pmi_composite: Optional[float] = None          # e.g. 52.3
    dxy_change_3m: Optional[float] = None          # 3-month DXY % change (decimal)
