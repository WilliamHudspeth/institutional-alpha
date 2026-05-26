"""Earnings quality factor.

Differentiate real FCF from accounting FCF. Particularly important for
software, serial acquirers, and aggressive accruers.
"""

from __future__ import annotations

from iam.factors.base import Factor, FactorContribution
from iam.data.security import Security


class EarningsQualityFactor(Factor):
    name = "earnings_quality"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        f = security.fundamentals

        # Accruals ratio — lower = better
        if f.accruals_ratio is not None:
            # Sloan accrual: -0.05 to +0.05 typical; high accruals = poor quality
            components["accruals_ratio"] = self.clamp(-f.accruals_ratio * 10)
        else:
            confidence *= 0.85

        # SBC as % of revenue — high SBC inflates non-GAAP FCF
        if f.sbc_ttm is not None and f.revenue_ttm and f.revenue_ttm > 0:
            sbc_pct = f.sbc_ttm / f.revenue_ttm
            # <2% great, 5% neutral, 15%+ bad
            components["sbc_pct_revenue"] = self.clamp(-(sbc_pct - 0.05) * 10)
        else:
            confidence *= 0.85

        # Cash conversion = FCF / Net Income
        if f.fcf_ttm is not None and f.net_income_ttm and f.net_income_ttm > 0:
            cash_conv = f.fcf_ttm / f.net_income_ttm
            components["cash_conversion"] = self.clamp((cash_conv - 0.8) * 2)

        # Capex authenticity — flag if capex is suspiciously low
        if f.capex_ttm is not None and f.revenue_ttm and f.revenue_ttm > 0:
            capex_intensity = f.capex_ttm / f.revenue_ttm
            if capex_intensity < 0.005:
                components["capex_authenticity"] = -0.3
                notes.append("Capex intensity unusually low — verify accounting.")
            else:
                components["capex_authenticity"] = 0.0

        # One-time adjustments frequency
        if f.one_time_adjustments_count_5y is not None:
            components["one_time_adjustments"] = self.clamp(-(f.one_time_adjustments_count_5y - 2) * 0.3)

        # --- NEW: Working Capital Quality ---
        wc_score = self._working_capital_quality(security)
        if wc_score is not None:
            components["wc_quality"] = wc_score
            if wc_score < 0:
                notes.append("Negative working capital trends detected — potential FCF inflation.")
        else:
            confidence *= 0.90

        # Updated weights to include Working Capital (assigned 15% weight)
        value = self.weighted_average({
            "acc":   (components.get("accruals_ratio"),         0.20),
            "sbc":   (components.get("sbc_pct_revenue"),        0.15),
            "conv":  (components.get("cash_conversion"),        0.20),
            "capex": (components.get("capex_authenticity"),     0.15),
            "ot":    (components.get("one_time_adjustments"),   0.15),
            "wc":    (components.get("wc_quality"),             0.15),
        })

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )

    def _working_capital_quality(self, security: Security) -> float | None:
        """Penalizes FCF that is artificially inflated by draining working capital."""
        f = security.fundamentals
        if f.change_in_working_capital is None or f.revenue_ttm is None or f.revenue_ttm <= 0:
            return None

        # Change in WC as a % of revenue
        wc_margin = f.change_in_working_capital / f.revenue_ttm

        if wc_margin < -0.05:
            # Draining WC by >5% of revenue is a massive red flag
            return -1.0
        elif wc_margin < 0.0:
            return -0.5
        elif wc_margin < 0.05:
            return 0.5
        else:
            return 1.0
