"""Expectations difficulty factor.

The market price encodes implied growth, ROIC, and margins. This factor
penalizes prices that require performance the business has never demonstrated.

Inverted convention: *easier* expectations score *higher*.
"""

from __future__ import annotations

from iam.factors.base import Factor, FactorContribution
from iam.data.security import Security


class ExpectationsDifficultyFactor(Factor):
    name = "expectations_difficulty"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        # --- 1. Implied growth / historical max growth ---
        growth_score = self._growth_difficulty(security)
        if growth_score is None:
            confidence *= 0.6
            notes.append("Growth difficulty inputs missing.")
        else:
            components["growth_difficulty"] = growth_score

        # --- 2. Implied ROIC / industry peak ROIC ---
        roic_score = self._roic_difficulty(security)
        if roic_score is None:
            confidence *= 0.75
            notes.append("ROIC difficulty inputs missing.")
        else:
            components["roic_difficulty"] = roic_score

        # --- 3. Implied margin / historical peak margin ---
        margin_score = self._margin_difficulty(security)
        if margin_score is None:
            confidence *= 0.85
            notes.append("Margin difficulty inputs missing.")
        else:
            components["margin_difficulty"] = margin_score

        value = self.weighted_average({
            "g": (components.get("growth_difficulty"), 0.40),
            "r": (components.get("roic_difficulty"),   0.35),
            "m": (components.get("margin_difficulty"), 0.25),
        })

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )

    def _growth_difficulty(self, security: Security) -> float | None:
        """Compares price-implied growth to the maximum the business has
        ever realized over a rolling window.

        STUB: implement reverse DCF to extract implied growth.
        """
        return None

    def _roic_difficulty(self, security: Security) -> float | None:
        """Compare implied ROIC to the industry's historical peak.

        Requires 'implied_roic' and 'industry_peak_roic' to be passed via
        security.qualitative.
        
        Inverted: low implied vs peak = easy expectations = high score.
        """
        q = security.qualitative
        implied_roic = q.get("implied_roic")
        peak_roic = q.get("industry_peak_roic")

        if implied_roic is None or peak_roic is None or peak_roic <= 0:
            return None

        ratio = implied_roic / peak_roic
        
        # Mapping the difficulty:
        # ratio <= 0.5 (demanding half of peak) -> +1.0 (easiest)
        # ratio == 1.0 (demanding absolute peak) -> 0.0 (fair but tough)
        # ratio >= 1.5 (demanding 50% above peak) -> -1.0 (heroic/impossible)
        return self.clamp((1.0 - ratio) * 2.0)

    def _margin_difficulty(self, security: Security) -> float | None:
        """Uses peak historical operating margin as the ceiling.

        Simplified proxy: if forward earnings imply margins above the 5y peak,
        penalize.
        """
        f = security.fundamentals
        if not f.operating_margin_history or not f.operating_margin:
            return None
        peak = max(f.operating_margin_history)
        if peak <= 0:
            return None
        ratio = f.operating_margin / peak
        # ratio < 0.7 -> easy (+0.5), ratio ~ 1.0 -> neutral, > 1.2 -> hard (-0.8)
        return self.clamp(-(ratio - 0.9) * 2.0)
