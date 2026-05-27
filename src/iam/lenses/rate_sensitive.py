"""Rate Sensitive Valuation Lens."""

from __future__ import annotations

from typing import Optional

from iam.data.security import Security
from iam.lenses.base import BaseLens, LensResult, two_stage_pv


class RateSensitiveLens(BaseLens):
    """Lens for rate-sensitive assets.
    
    Treats real_rate_10y + 5.5% as the full discount rate (cost of equity only).
    Projects 10 years of cash flows, then a standard terminal growth.
    """
    
    name = "rate_sensitive"

    def compute(self, security: Security) -> LensResult:
        m = security.market
        f = security.fundamentals
        q = security.qualitative
        
        # Rule 3: WACC = real_rate_10y + 5.5%
        # Fallback: 9% (= ~3.5% real rate + 5.5% ERP) when macro is absent.
        real_rate = None
        if security.macro is not None and security.macro.real_rate_10y is not None:
            real_rate = security.macro.real_rate_10y
        if real_rate is None:
            real_rate = q.get("real_rate_10y")
        wacc = (real_rate + 0.055) if real_rate is not None else 0.09
        
        # Rule 1: 10 years projection for all three
        n = 10
        g_high = q.get("forecast_growth", 0.08)
        g_terminal = q.get("forecast_terminal_growth", 0.025)
        
        if m.price is None or f.fcf_ttm is None or f.shares_outstanding is None or f.shares_outstanding == 0:
            return LensResult(
                lens_name=self.name, fair_value_low=None, fair_value_high=None,
                implied_move_pct=None, confidence=0.0,
                narrative="Missing required pricing or cash flow data for rate-sensitive lens."
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
            lens_name=self.name, fair_value_low=low_pv, fair_value_high=high_pv,
            implied_move_pct=implied_move,
            confidence=0.85 if real_rate is not None else 0.65,
            narrative=f"WACC {wacc*100:.1f}% ({'real rate + 5.5% ERP' if real_rate is not None else 'default fallback'}).",
            assumptions={"wacc": wacc, "wacc_low": wacc + 0.01, "wacc_high": wacc - 0.01, "g_high": g_high, "g_terminal": g_terminal, "n": float(n)}
        )