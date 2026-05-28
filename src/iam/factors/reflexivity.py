"""Reflexivity factor.

Some businesses have a feedback loop between share price and fundamentals:
high equity prices give them M&A currency, attract talent via equity comp,
strengthen the narrative, and reinforce network effects via reinvestment.

NVIDIA, Tesla, Palantir, Coinbase — these benefit from reflexivity in ways
a normal DCF doesn't capture. Most sub-components here are qualitative and
expected to be supplied via ``security.qualitative``.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.factors.base import Factor, FactorContribution


class ReflexivityFactor(Factor):
    name = "reflexivity"

    QUALITATIVE_KEYS = [
        ("equity_currency_strength", 0.25),
        ("network_effect_strength", 0.25),
        ("talent_attraction", 0.20),
        ("acquisition_optionality", 0.15),
        ("narrative_reinforcement", 0.15),
    ]

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        parts = {}
        for key, weight in self.QUALITATIVE_KEYS:
            raw = security.qualitative.get(key)
            if raw is None:
                confidence *= 0.85
                notes.append(f"qualitative['{key}'] not provided")
                continue
            # qualitative inputs expected in [0, 1] -> map to [-1, 1]
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
