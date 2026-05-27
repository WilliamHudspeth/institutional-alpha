from dataclasses import dataclass
from typing import Optional

@dataclass
class MacroConditions:
    real_rate_trend: float = 0.0  # e.g., 1.0 for rising, -1.0 for falling
    credit_spread_change: float = 0.0
    pmi_direction: float = 50.0   # e.g., >50 expansion, <50 contraction
    
    # Threshold tracking
    rate_shock_bps: float = 0.0   # Basis point shift (e.g., 50 for +0.50%)
