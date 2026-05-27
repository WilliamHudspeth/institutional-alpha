"""Stage 3a: FCFE DCF (forward-built, independent of market price).

Where reverse DCF takes price as given and solves for growth, this builds
fair value bottom-up from forecast growth, margin, and reinvestment
assumptions. Two-stage Gordon structure for parity with the reverse DCF.

The assumptions here should come from analyst estimates, management
guidance, or the user's own thesis — *not* from the current price. The
whole point is to have an independent triangulation point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from iam.data.security import Security
from iam.valuation.types import Method, ValuationResult


@dataclass
class FCFEAssumptions:
    """The explicit forecast inputs for the FCFE DCF.

    These should come from outside the model — analyst consensus,
    management guidance, your own bottom-up. The model's job is to compute
    a fair value *given* these inputs, not to invent them.
    """
    high_growth: float          # FCFE CAGR during forecast period
    terminal_growth: float = 0.025
    high_growth_years: int = 10
    discount_rate: float = 0.09


class FCFEDCF:
    """Stage 3a — independent FCFE-discount intrinsic value.

    If the security has analyst-provided or user-provided forecast assumptions
    on ``security.qualitative`` (keys: ``forecast_growth``,
    ``forecast_terminal_growth``, ``forecast_discount_rate``), those are used.
    Otherwise the model degrades gracefully with default assumptions and
    a confidence penalty.
    """

    def __init__(self, default_assumptions: Optional[FCFEAssumptions] = None):
        self.defaults = default_assumptions or FCFEAssumptions(high_growth=0.08)

    def compute(
        self,
        security: Security,
        assumptions: Optional[FCFEAssumptions] = None,
    ) -> ValuationResult:
        m = security.market
        f = security.fundamentals
        notes: list[str] = []
        confidence = 1.0

        if m.price is None or f.fcf_ttm is None or f.shares_outstanding is None:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.0,
                notes=["FCFE DCF requires price, FCF TTM, and shares outstanding."],
                verdict_text="Insufficient data for intrinsic DCF.",
            )

        # Resolve assumptions: explicit > qualitative dict > defaults.
        assumed = assumptions or self._resolve_assumptions(security)
        if assumptions is None and not self._has_explicit_assumptions(security):
            confidence *= 0.7
            notes.append(
                "using model defaults — supply assumptions for a tailored estimate."
            )

        fcfe0 = f.fcf_ttm / f.shares_outstanding
        if fcfe0 <= 0:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.3,
                notes=["Base FCFE is non-positive; FCFE DCF unreliable."],
                verdict_text="Base FCFE non-positive; method skipped.",
            )

        if assumed.discount_rate <= assumed.terminal_growth:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.0,
                notes=["Discount rate must exceed terminal growth."],
                verdict_text="Bad assumptions: r <= g_terminal.",
            )

        # Two-stage PV
        pv = 0.0
        fcfe_t = fcfe0
        for t in range(1, assumed.high_growth_years + 1):
            fcfe_t = fcfe0 * ((1 + assumed.high_growth) ** t)
            pv += fcfe_t / ((1 + assumed.discount_rate) ** t)

        fcfe_n_plus_1 = fcfe_t * (1 + assumed.terminal_growth)
        terminal_value = fcfe_n_plus_1 / (assumed.discount_rate - assumed.terminal_growth)
        pv += terminal_value / ((1 + assumed.discount_rate) ** assumed.high_growth_years)

        fair_value_to_price = (pv / m.price) - 1
        # Clamp to avoid runaway numbers from bad inputs.
        fair_value_to_price = max(-0.9, min(3.0, fair_value_to_price))

        verdict = self._verdict_text(fair_value_to_price, assumed.high_growth)

        return ValuationResult(
            method=Method.INTRINSIC,
            fair_value_per_share=pv,
            fair_value_to_price=fair_value_to_price,
            confidence=confidence,
            components={
                "base_fcfe_per_share": fcfe0,
                "terminal_value_per_share": terminal_value / ((1 + assumed.discount_rate) ** assumed.high_growth_years),
            },
            assumptions={
                "high_growth": assumed.high_growth,
                "terminal_growth": assumed.terminal_growth,
                "high_growth_years": float(assumed.high_growth_years),
                "discount_rate": assumed.discount_rate,
            },
            notes=notes,
            verdict_text=verdict,
        )

    @staticmethod
    def _has_explicit_assumptions(security: Security) -> bool:
        return "forecast_growth" in security.qualitative

    def _resolve_assumptions(self, security: Security) -> FCFEAssumptions:
        q = security.qualitative
        return FCFEAssumptions(
            high_growth=q.get("forecast_growth", self.defaults.high_growth),
            terminal_growth=q.get("forecast_terminal_growth", self.defaults.terminal_growth),
            high_growth_years=int(q.get("forecast_high_growth_years", self.defaults.high_growth_years)),
            discount_rate=q.get("forecast_discount_rate", self.defaults.discount_rate),
        )

    @staticmethod
    def _verdict_text(ratio: float, g: float) -> str:
        pct = ratio * 100
        g_pct = g * 100
        if ratio > 0.30:
            return f"Intrinsic DCF (assuming {g_pct:.0f}% growth) implies ~{pct:+.0f}% upside."
        if ratio > 0.10:
            return f"Intrinsic DCF (assuming {g_pct:.0f}% growth) implies modest upside ({pct:+.0f}%)."
        if ratio > -0.10:
            return f"Intrinsic DCF (assuming {g_pct:.0f}% growth) suggests fair value near current price ({pct:+.0f}%)."
        if ratio > -0.30:
            return f"Intrinsic DCF (assuming {g_pct:.0f}% growth) implies modest downside ({pct:+.0f}%)."
        return f"Intrinsic DCF (assuming {g_pct:.0f}% growth) implies material downside ({pct:+.0f}%)."
