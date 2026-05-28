"""Expectations difficulty factor.

The market price encodes implied growth, ROIC, and margins. This factor
penalizes prices that require performance the business has never demonstrated.

Inverted convention: *easier* expectations score *higher*.

The growth sub-component delegates to ``iam.valuation.ReverseDCF`` so the
math here matches the v0.2.0 pipeline. The factor's role is to convert that
expectations vector into a [-1, 1] cross-sectional score.
"""

from __future__ import annotations

from iam.data.security import Security
from iam.factors.base import Factor, FactorContribution
from iam.valuation import ReverseDCF


class ExpectationsDifficultyFactor(Factor):
    name = "expectations_difficulty"

    def __init__(self, reverse_dcf: ReverseDCF | None = None):
        self._reverse_dcf = reverse_dcf or ReverseDCF()

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        growth_score = self._growth_difficulty(security)
        if growth_score is None:
            confidence *= 0.6
            notes.append("Growth difficulty inputs missing (need price, FCF, history).")
        else:
            components["growth_difficulty"] = growth_score

        roic_score = self._roic_difficulty(security)
        if roic_score is None:
            confidence *= 0.75
            notes.append("ROIC difficulty stubbed (needs industry-peak dataset).")
        else:
            components["roic_difficulty"] = roic_score

        margin_score = self._margin_difficulty(security)
        if margin_score is None:
            confidence *= 0.85
            notes.append("Margin difficulty inputs missing.")
        else:
            components["margin_difficulty"] = margin_score

        value = self.weighted_average(
            {
                "g": (components.get("growth_difficulty"), 0.40),
                "r": (components.get("roic_difficulty"), 0.35),
                "m": (components.get("margin_difficulty"), 0.25),
            }
        )

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )

    def _growth_difficulty(self, security: Security):
        """Compare price-implied growth to the business's historical peak.

        Inverted: low implied vs. peak = easy = high score. High implied
        vs. peak = hard = low score.

        Mapping:
          vs_max<=0   (market implies decline) -> +1.0 (easiest)
          vs_max=0.5  (easy)    -> +0.75
          vs_max=1.0  (peak)    ->   0.0
          vs_max=1.5  (stretch) -> -0.75
          vs_max=2.0  (heroic)  -> -1.0
        """
        result = self._reverse_dcf.compute(security)
        if result.implied is None:
            return None
        vs_max = result.implied.growth_vs_history_max
        if vs_max is None:
            return None
        if vs_max <= 0:
            return 1.0
        return self.clamp((1.0 - vs_max) * 1.5)

    def _roic_difficulty(self, security: Security):
        """STUB: requires industry peak ROIC dataset."""
        return None

    def _margin_difficulty(self, security: Security):
        """Uses peak historical operating margin as the ceiling."""
        f = security.fundamentals
        if not f.operating_margin_history or not f.operating_margin:
            return None
        peak = max(f.operating_margin_history)
        if peak <= 0:
            return None
        ratio = f.operating_margin / peak
        return self.clamp(-(ratio - 0.9) * 2.0)
