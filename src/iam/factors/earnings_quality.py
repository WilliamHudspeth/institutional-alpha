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

        # Cash conversion = FCF / Net Income (similar to quality factor)
        if f.fcf_ttm is not None and f.net_income_ttm and f.net_income_ttm > 0:
            cash_conv = f.fcf_ttm / f.net_income_ttm
            components["cash_conversion"] = self.clamp((cash_conv - 0.8) * 2)

        # Capex authenticity — flag if capex is suspiciously low
        if f.capex_ttm is not None and f.revenue_ttm and f.revenue_ttm > 0:
            capex_intensity = f.capex_ttm / f.revenue_ttm
            # This is sector-dependent; here we just flag near-zero capex with growth
            # as suspicious. A real implementation would compare to sector norms.
            if capex_intensity < 0.005:
                components["capex_authenticity"] = -0.3
                notes.append("Capex intensity unusually low — verify accounting.")
            else:
                components["capex_authenticity"] = 0.0

        # One-time adjustments frequency
        if f.one_time_adjustments_count_5y is not None:
            # 0-2 over 5y = normal, 5+ = chronic
            components["one_time_adjustments"] = self.clamp(-(f.one_time_adjustments_count_5y - 2) * 0.3)

        value = self.weighted_average({
            "acc":   (components.get("accruals_ratio"),         0.20),
            "sbc":   (components.get("sbc_pct_revenue"),        0.20),
            "conv":  (components.get("cash_conversion"),        0.20),
            "capex": (components.get("capex_authenticity"),     0.15),
            "ot":    (components.get("one_time_adjustments"),   0.10),
        })

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )
