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
from iam.valuation.beta import get_custom_beta_for_intrinsic
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
    roe: float = 0.15           # Return on Equity for reinvestment constraint (g / ROE)


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

        # CAPM discount rate (opt-in): if risk_free_rate and equity_risk_premium
        # are supplied, compute cost of equity from the Damodaran relevered beta.
        # This overrides whatever discount_rate was resolved above.
        q = security.qualitative
        rfr = q.get("risk_free_rate")
        erp = q.get("equity_risk_premium")
        if rfr is not None and erp is not None:
            beta = get_custom_beta_for_intrinsic(security)
            assumed.discount_rate = float(rfr) + beta * float(erp)
            notes.append(
                f"CAPM discount rate: {rfr:.3f} + {beta:.4f} × {erp:.3f} = {assumed.discount_rate:.4f} "
                f"(relevered beta, Stage 3)"
            )

        # To enforce the Reinvestment Rate constraint (g = Reinvestment Rate * ROE),
        # we base cash flows on Net Income, then subtract the reinvestment required
        # to achieve the assumed growth rate.
        ni = f.net_income_ttm if f.net_income_ttm and f.net_income_ttm > 0 else f.fcf_ttm
        if ni is None or ni <= 0:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.3,
                notes=["Base Net Income/FCFE is non-positive; FCFE DCF unreliable."],
                verdict_text="Base cash flow non-positive; method skipped.",
            )
            
        ni_per_share = ni / f.shares_outstanding

        if assumed.discount_rate <= assumed.terminal_growth:
            return ValuationResult(
                method=Method.INTRINSIC, confidence=0.0,
                notes=["Discount rate must exceed terminal growth."],
                verdict_text="Bad assumptions: r <= g_terminal.",
            )

        # Enforce Equity Reinvestment Rate (ERR) constraint: ERR = g / ROE
        # Cap ERR at 1.0 (100%) to prevent negative cash flows in high growth
        err_high = min(assumed.high_growth / assumed.roe, 1.0) if assumed.roe > 0 else 1.0
        err_term = min(assumed.terminal_growth / assumed.roe, 1.0) if assumed.roe > 0 else 1.0

        # Two-stage PV
        pv = 0.0
        ni_t = ni_per_share
        
        for t in range(1, assumed.high_growth_years + 1):
            ni_t = ni_t * (1 + assumed.high_growth)
            fcfe_t = ni_t * (1 - err_high)
            pv += fcfe_t / ((1 + assumed.discount_rate) ** t)

        ni_n_plus_1 = ni_t * (1 + assumed.terminal_growth)
        fcfe_n_plus_1 = ni_n_plus_1 * (1 - err_term)
        
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
                "base_ni_per_share": ni_per_share,
                "reinvestment_rate_high": err_high,
                "reinvestment_rate_term": err_term,
                "terminal_value_per_share": terminal_value / ((1 + assumed.discount_rate) ** assumed.high_growth_years),
            },
            assumptions={
                "high_growth": assumed.high_growth,
                "terminal_growth": assumed.terminal_growth,
                "high_growth_years": float(assumed.high_growth_years),
                "discount_rate": assumed.discount_rate,
                "roe": assumed.roe,
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
            roe=q.get("forecast_roe", self.defaults.roe),
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
