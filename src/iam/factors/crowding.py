"""Crowding / positioning factor.

Crowded longs collapse nonlinearly; crowded shorts squeeze violently.
Convention here: *less* crowded scores higher.
"""

from __future__ import annotations

from iam.factors.base import Factor, FactorContribution
from iam.data.security import Security


class CrowdingFactor(Factor):
    name = "crowding"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        m = security.market

        # Hedge fund ownership — high = crowded
        if m.hedge_fund_ownership_pct is not None:
            # 5% = neutral, 15%+ = very crowded, <2% = uncrowded
            components["hedge_fund_ownership"] = self.clamp(-(m.hedge_fund_ownership_pct - 0.05) * 10)
        else:
            confidence *= 0.85

        # Retail ownership
        if m.retail_ownership_pct is not None:
            # High retail = often crowded/sentiment-driven
            components["retail_positioning"] = self.clamp(-(m.retail_ownership_pct - 0.20) * 4)
        else:
            confidence *= 0.9

        # Short interest — high SI is mixed signal; we treat it as positive
        # (potential squeeze) up to a point, then negative (real concern).
        if m.short_interest_pct_float is not None:
            si = m.short_interest_pct_float
            if si < 0.10:
                components["short_interest"] = self.clamp(si * 5)  # mild squeeze potential
            else:
                components["short_interest"] = self.clamp(-((si - 0.10) * 5))  # real concern

        # Call/put skew
        if m.options_call_put_skew is not None:
            # Skew >> 1 means call-heavy = euphoric/crowded long
            components["options_skew"] = self.clamp(-(m.options_call_put_skew - 1.0))

        # Passive ownership concentration
        if m.passive_index_ownership_pct is not None:
            # >25% passive = fragile to flows
            components["passive_concentration"] = self.clamp(-(m.passive_index_ownership_pct - 0.20) * 5)

        value = self.weighted_average({
            "hf":    (components.get("hedge_fund_ownership"),  0.30),
            "ret":   (components.get("retail_positioning"),    0.20),
            "si":    (components.get("short_interest"),        0.20),
            "opts":  (components.get("options_skew"),          0.15),
            "passv": (components.get("passive_concentration"), 0.15),
        })

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )
