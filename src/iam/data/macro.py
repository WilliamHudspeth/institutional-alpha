"""MacroConditions — structured macro inputs for the pipeline's macro overlay.

Distinct from MacroContext (which lives on Security and drives MacroRegimeFactor):
  - MacroContext is a string-tagged snapshot attached to a security.
  - MacroConditions is a numeric snapshot passed to ValuationPipeline.run()
    so the macro overlay can apply quantitative adjustments.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MacroConditions:
    """Numeric macro snapshot passed to ValuationPipeline.run().

    real_rate_trend: annualised change in real 10y rate; positive = rates rising.
    liquidity_delta: change in liquidity index; positive = looser.
    credit_spread_hy: current HY spread level (e.g. 0.035 = 3.5%).
    yield_curve_slope: 10y minus 2y yield in decimal (negative = inverted).
    """
    real_rate_trend: float = 0.0
    liquidity_delta: float = 0.0
    credit_spread_hy: float = 0.035
    yield_curve_slope: float = 0.005
