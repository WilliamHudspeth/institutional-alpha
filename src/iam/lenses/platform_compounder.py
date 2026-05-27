"""Platform Compounder Valuation Lens."""

from __future__ import annotations

from typing import Optional

from iam.data.security import Security
from iam.lenses.base import BaseLens, LensResult, two_stage_pv


class PlatformCompounderLens(BaseLens):
    """Lens for platform compounders.
    
    Adjusts terminal growth based on observed margin expansion.
    Caps terminal growth at 4%.
    """
    
    name = "platform_compounder"

    def compute(self, security: Security) -> LensResult:
        m = security.market
        f = security.fundamentals
        q = security.qualitative
        
        n = 10  # Rule 1: 10 years projection
        wacc = q.get("forecast_discount_rate", 0.09)
        g_high = q.get("forecast_growth", 0.12)
        base_g_terminal = q.get("forecast_terminal_growth", 0.025)
        
        # Calculate margin expansion if data is available (most-recent first assumption)
        margin_expansion_annual = 0.0
        if hasattr(f, "operating_margin_history") and f.operating_margin_history and len(f.operating_margin_history) >= 2:
            margins = f.operating_margin_history
            years = len(margins) - 1
            margin_expansion_annual = (margins[0] - margins[-1]) / years
        
        # Rule 4: Platform compounder adjustment
        if margin_expansion_annual <= 0.0:
            adj = 0.0
        elif margin_expansion_annual < 0.01:
            adj = 0.0025
        elif margin_expansion_annual <= 0.03:
            adj = 0.0050
        else:
            adj = 0.0075
            
        g_terminal = min(0.04, base_g_terminal + adj)
        
        expansion_pct = margin_expansion_annual * 100
        narrative = (
            f"Observed {expansion_pct:.1f}%/yr margin expansion. "
            f"Applied +{adj*100:.2f}% terminal growth adjustment (capped at 4%)."
        )
        
        if m.price is None or f.fcf_ttm is None or f.shares_outstanding is None or f.shares_outstanding == 0:
            return LensResult(
                lens_name=self.name, fair_value_low=None, fair_value_high=None,
                implied_move_pct=None, confidence=0.0,
                narrative="Missing required pricing or cash flow data."
            )

        fcfe0 = f.fcf_ttm / f.shares_outstanding
        if fcfe0 <= 0:
            return LensResult(
                lens_name=self.name, fair_value_low=None, fair_value_high=None,
                implied_move_pct=None, confidence=0.0,
                narrative="Base FCFE is non-positive; cannot value via DCF."
            )

        mid_pv = two_stage_pv(fcfe0, g_high, n, g_terminal, wacc)
        # Rule 2: WACC sensitivity ± 1%
        low_pv = two_stage_pv(fcfe0, g_high, n, g_terminal, wacc + 0.01)
        high_pv = two_stage_pv(fcfe0, g_high, n, g_terminal, wacc - 0.01)
        
        implied_move = (mid_pv / m.price) - 1.0 if mid_pv is not None and m.price > 0 else None
            
        return LensResult(
            lens_name=self.name, fair_value_low=low_pv, fair_value_high=high_pv, implied_move_pct=implied_move, 
            confidence=0.80 if margin_expansion_annual > 0.0 else 0.55,
            narrative=narrative,
            assumptions={"wacc": wacc, "g_high": g_high, "base_g_terminal": base_g_terminal, "g_terminal": g_terminal, "margin_expansion_annual": margin_expansion_annual, "n": float(n)}
        )