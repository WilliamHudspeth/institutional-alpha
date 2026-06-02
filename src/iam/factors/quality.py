"""Quality factor.

The single biggest missing feature from typical public valuation models.
Persistent quality (high ROIC, stable margins, high FCF conversion) commands
a structural premium that pure cheap/expensive screens systematically miss.
"""

from __future__ import annotations

import statistics

from iam.data.security import Security
from iam.factors.base import Factor, FactorContribution


class QualityFactor(Factor):
    name = "quality"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        f = security.fundamentals

        # --- ROIC persistence ---
        if len(f.roic_history) >= 3:
            mean_roic = statistics.mean(f.roic_history)
            stdev = statistics.pstdev(f.roic_history) if len(f.roic_history) > 1 else 0
            # high mean + low variance is the win
            level_score = self.clamp((mean_roic - 0.10) / 0.10)  # 10% = neutral, 20%+ = great
            stability_score = self.clamp(1 - (stdev / 0.08))  # 8% stdev ~ neutral
            components["roic_persistence"] = (level_score + stability_score) / 2
        else:
            confidence *= 0.7
            notes.append("ROIC history too short for persistence.")

        # --- Margin stability (gross + operating averaged) ---
        gm_stability = self._margin_stability(f.gross_margin_history)
        om_stability = self._margin_stability(f.operating_margin_history)
        if gm_stability is not None:
            components["gross_margin_stability"] = gm_stability
        else:
            confidence *= 0.85
        if om_stability is not None:
            components["operating_margin_stability"] = om_stability
        else:
            confidence *= 0.9

        # --- FCF conversion (FCF / Net Income) ---
        if f.fcf_ttm is not None and f.net_income_ttm and f.net_income_ttm > 0:
            conversion = f.fcf_ttm / f.net_income_ttm
            # >1.0 great, 0.7-1.0 fine, <0.5 red flag
            components["fcf_conversion"] = self.clamp((conversion - 0.7) * 2)
        else:
            confidence *= 0.85
            notes.append("FCF conversion unavailable.")

        # --- Balance sheet strength (light proxy; full version in leverage penalty) ---
        if f.ebitda_ttm and f.total_debt is not None and f.cash_and_equivalents is not None:
            net_debt = f.total_debt - f.cash_and_equivalents
            nd_ebitda = net_debt / f.ebitda_ttm if f.ebitda_ttm else None
            if nd_ebitda is not None:
                # negative net debt (cash > debt) is best
                components["balance_sheet_strength"] = self.clamp(-(nd_ebitda - 1.0) / 2.0)

        # --- Dilution control (shares trend) ---
        if len(f.shares_outstanding_history) >= 3:
            recent = f.shares_outstanding_history[0]
            older = f.shares_outstanding_history[-1]
            if older > 0:
                annual_dilution = (
                    (recent / older) ** (1 / (len(f.shares_outstanding_history) - 1))
                ) - 1
                # +5%/yr = bad, 0 = neutral, -2%/yr (buybacks) = great
                components["dilution_control"] = self.clamp(-annual_dilution * 20)

        # --- Reinvestment efficiency (incremental ROIC if available) ---
        if f.incremental_roic is not None:
            components["reinvestment_efficiency"] = self.clamp((f.incremental_roic - 0.10) / 0.10)

        value = self.weighted_average(
            {
                "roic": (components.get("roic_persistence"), 0.25),
                "gm": (components.get("gross_margin_stability"), 0.15),
                "fcfc": (components.get("fcf_conversion"), 0.20),
                "bs": (components.get("balance_sheet_strength"), 0.10),
                "om": (components.get("operating_margin_stability"), 0.10),
                "dil": (components.get("dilution_control"), 0.05),
                "rein": (components.get("reinvestment_efficiency"), 0.15),
            }
        )

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )

    @staticmethod
    def _margin_stability(history: list[float]) -> float | None:
        if len(history) < 3:
            return None
        stdev = statistics.pstdev(history) if len(history) > 1 else 0
        # 2% stdev = neutral, 0.5% = excellent, 5%+ = poor
        return Factor.clamp(1 - (stdev / 0.025))
