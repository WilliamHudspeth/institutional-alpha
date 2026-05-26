"""Reinvestment runway factor.

Can capital still be deployed at attractive incremental returns? Crucial
for compounders in software, AI, semis, luxury, and platform businesses.

Mostly qualitative — TAM and adjacency potential are not easily extracted
from financials.
"""

from __future__ import annotations

from iam.factors.base import Factor, FactorContribution
from iam.data.security import Security


class RunwayFactor(Factor):
    name = "reinvestment_runway"

    QUALITATIVE_KEYS = [
        ("tam_remaining",              0.30),
        ("geographic_expansion",       0.15),
        ("adjacency_potential",        0.15),
        ("recurring_revenue_mix",      0.10),
    ]

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        f = security.fundamentals

        # Incremental ROIC (quantitative)
        if f.incremental_roic is not None:
            # >20% = great, 10% = neutral, <5% = bad
            components["incremental_roic"] = self.clamp((f.incremental_roic - 0.10) / 0.10)
        else:
            confidence *= 0.85

        parts = {"iroic": (components.get("incremental_roic"), 0.30)}
        for key, weight in self.QUALITATIVE_KEYS:
            raw = security.qualitative.get(key)
            if raw is None:
                confidence *= 0.9
                continue
            score = self.clamp(raw * 2 - 1)
            components[key] = score
            parts[key] = (score, weight)

        value = self.weighted_average(parts)

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )
