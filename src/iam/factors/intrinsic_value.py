"""Intrinsic value factor.

Asks: what is this asset worth on its cash flows, vs. what the market is
paying for it right now?

Default sub-components:
  - DCF residual (fair value / price - 1)
  - Reverse DCF implied growth gap
  - Owner earnings yield

This stub implements a simple FCF-yield-based proxy when full DCF inputs
aren't available, and exposes hooks for a full DCF when they are.
"""

from __future__ import annotations

from iam.factors.base import Factor, FactorContribution
from iam.data.security import Security


class IntrinsicValueFactor(Factor):
    name = "intrinsic_value"

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        # --- 1. DCF residual (placeholder: implement full DCF here) ---
        dcf_residual = self._dcf_residual(security)
        if dcf_residual is None:
            confidence *= 0.6
            notes.append("DCF inputs incomplete; skipping DCF residual.")
        else:
            components["dcf_residual"] = dcf_residual

        # --- 2. Reverse DCF implied growth gap (placeholder) ---
        reverse_gap = self._reverse_dcf_gap(security)
        if reverse_gap is None:
            confidence *= 0.7
            notes.append("Reverse DCF inputs incomplete.")
        else:
            components["reverse_dcf_gap"] = reverse_gap

        # --- 3. Owner earnings yield (FCF yield as proxy) ---
        fcf_yield_score = self._fcf_yield_score(security)
        if fcf_yield_score is None:
            confidence *= 0.7
            notes.append("FCF yield unavailable.")
        else:
            components["owner_earnings_yield"] = fcf_yield_score

        value = self.weighted_average({
            "dcf":     (components.get("dcf_residual"),       0.50),
            "reverse": (components.get("reverse_dcf_gap"),    0.30),
            "yield":   (components.get("owner_earnings_yield"), 0.20),
        })

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Sub-component implementations (stubs — replace with full models)
    # ------------------------------------------------------------------

    def _dcf_residual(self, security: Security) -> float | None:
        """Returns (fair_value / price - 1), clamped to [-1, 1].

        STUB: replace with a real two-stage or three-stage DCF.
        """
        return None  # placeholder

    def _reverse_dcf_gap(self, security: Security) -> float | None:
        """Returns a score in [-1, 1] reflecting how reasonable the
        market-implied growth rate is vs. historical realized growth.

        STUB: implement by inverting the DCF to solve for the growth rate
        that justifies the current price, then comparing to history.
        """
        return None  # placeholder

    def _fcf_yield_score(self, security: Security) -> float | None:
        """Score the FCF yield. Above 5% is bullish, below 2% is bearish."""
        m = security.market
        f = security.fundamentals
        fcf_yield = m.fcf_yield
        if fcf_yield is None and f.fcf_ttm and m.market_cap:
            fcf_yield = f.fcf_ttm / m.market_cap
        if fcf_yield is None:
            return None
        # Map: 0% -> -1, 2% -> -0.5, 5% -> 0.5, 10%+ -> 1.0
        return self.clamp((fcf_yield - 0.035) / 0.04)
