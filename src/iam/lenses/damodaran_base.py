"""Damodaran base lens: plain two-stage DCF with stable default assumptions."""

from __future__ import annotations

from iam.data.security import Security
from iam.lenses.base import BaseLens, LensResult, two_stage_pv

DEFAULT_WACC = 0.09
DEFAULT_GROWTH = 0.08
DEFAULT_TERMINAL_GROWTH = 0.025
HIGH_GROWTH_YEARS = 10


class DamodaranBaseLens(BaseLens):
    """Plain two-stage DCF with Damodaran-style stable assumptions.

    WACC: 9% (fixed, not rate-adjusted).
    Terminal growth: 2.5% (GDP steady-state).
    High-growth period: 10 years.
    Growth rate from security.qualitative['forecast_growth'] or default 8%.
    Fair value range uses WACC ± 1%.
    """

    name = "damodaran_base"

    def compute(self, security: Security) -> LensResult:
        m = security.market
        f = security.fundamentals
        q = security.qualitative

        if m.price is None or f.fcf_ttm is None or f.shares_outstanding is None or f.shares_outstanding == 0:
            return LensResult(
                lens_name=self.name,
                fair_value_low=None, fair_value_high=None,
                implied_move_pct=None, confidence=0.0,
                narrative="Missing required pricing or cash flow data.",
            )

        fcfe0 = f.fcf_ttm / f.shares_outstanding
        if fcfe0 <= 0:
            return LensResult(
                lens_name=self.name,
                fair_value_low=None, fair_value_high=None,
                implied_move_pct=None, confidence=0.2,
                narrative="Base FCFE non-positive; Damodaran base lens skipped.",
            )

        g_high = q.get("forecast_growth", DEFAULT_GROWTH)
        g_terminal = q.get("forecast_terminal_growth", DEFAULT_TERMINAL_GROWTH)
        wacc = DEFAULT_WACC

        mid_pv = two_stage_pv(fcfe0, g_high, HIGH_GROWTH_YEARS, g_terminal, wacc)
        low_pv = two_stage_pv(fcfe0, g_high, HIGH_GROWTH_YEARS, g_terminal, wacc + 0.01)
        high_pv = two_stage_pv(fcfe0, g_high, HIGH_GROWTH_YEARS, g_terminal, wacc - 0.01)

        if mid_pv is None or low_pv is None or high_pv is None:
            return LensResult(
                lens_name=self.name,
                fair_value_low=None, fair_value_high=None,
                implied_move_pct=None, confidence=0.0,
                narrative="Bad assumptions: discount rate <= terminal growth.",
            )

        implied_move = (mid_pv / m.price) - 1.0

        pct = implied_move * 100
        direction = "upside" if pct >= 0 else "downside"
        narrative = (
            f"Damodaran base DCF: WACC {wacc:.0%}, terminal growth {g_terminal:.1%}, "
            f"forecast growth {g_high:.0%}. "
            f"Midpoint implies {abs(pct):.1f}% {direction}."
        )

        return LensResult(
            lens_name=self.name,
            fair_value_low=low_pv,
            fair_value_high=high_pv,
            implied_move_pct=implied_move,
            confidence=0.85,
            narrative=narrative,
            assumptions={
                "wacc": wacc,
                "g_high": g_high,
                "g_terminal": g_terminal,
                "high_growth_years": float(HIGH_GROWTH_YEARS),
            },
        )
