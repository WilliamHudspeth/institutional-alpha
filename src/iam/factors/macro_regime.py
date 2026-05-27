"""Macro regime factor.

Whether the current regime is favorable for the *style* of the security.
Default implementation here treats the regime as an additive factor; an
alternative implementation that re-weights other factors lives in
``engine.composite`` (see ``MacroReweighter``).
"""

from __future__ import annotations

from iam.factors.base import Factor, FactorContribution
from iam.data.security import Security


class MacroRegimeFactor(Factor):
    name = "macro_regime"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0
        mc = security.macro

        if mc is None:
            return FactorContribution(
                name=self.name, value=0.0, confidence=0.0,
                notes=["No macro context provided."],
            )

        # Real rates — falling = supportive of duration; rising = headwind
        if mc.real_rate_trend:
            components["real_rate_regime"] = {
                "falling": 0.7, "flat": 0.0, "rising": -0.7,
            }.get(mc.real_rate_trend, 0.0)
        else:
            confidence *= 0.85

        # Liquidity index — already normalized [-1, 1] by assumption
        if mc.liquidity_index is not None:
            components["liquidity_conditions"] = self.clamp(mc.liquidity_index)

        # Credit spreads — tighter = bullish, wider = bearish
        if mc.credit_spread_hy is not None:
            # 3% = neutral, 6%+ = stress, 2.5% = euphoria
            components["credit_spreads"] = self.clamp(-(mc.credit_spread_hy - 0.035) * 30)

        # Yield curve slope — inversion = recession signal
        if mc.yield_curve_slope_10y_2y is not None:
            components["yield_curve"] = self.clamp(mc.yield_curve_slope_10y_2y * 50)

        # PMI direction
        if mc.pmi_direction:
            components["pmi_direction"] = {
                "expanding": 0.6, "contracting": -0.6,
            }.get(mc.pmi_direction, 0.0)

        # Dollar strength
        if mc.dxy_trend:
            # Strong dollar mixed: bearish for multinationals & EM, bullish for domestics
            # Default: weak USD slightly bullish for risk
            components["dollar_strength"] = {
                "falling": 0.3, "flat": 0.0, "rising": -0.3,
            }.get(mc.dxy_trend, 0.0)

        value = self.weighted_average({
            "rates":  (components.get("real_rate_regime"),    0.25),
            "liq":    (components.get("liquidity_conditions"), 0.20),
            "credit": (components.get("credit_spreads"),       0.15),
            "curve":  (components.get("yield_curve"),          0.15),
            "pmi":    (components.get("pmi_direction"),        0.15),
            "dxy":    (components.get("dollar_strength"),      0.10),
        })

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )
