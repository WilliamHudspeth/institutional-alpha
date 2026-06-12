"""Intrinsic value factor.

Asks: what is this asset worth on its cash flows, vs. what the market is
paying for it right now?

Sub-components:
  - DCF residual (fair value / price - 1)
  - Reverse DCF "thesis gap" — implied growth vs. the user's own forecast
  - Owner earnings yield

The DCF and reverse DCF sub-components delegate to ``iam.valuation`` (the
same code that powers the v0.2.0 pipeline). That way there's one source of
truth for the math, and contributors who improve the pipeline automatically
improve this factor too.

To keep this factor orthogonal to ExpectationsDifficultyFactor:
  - This factor's "reverse gap" compares implied growth to the user's
    *thesis* growth (forecast_growth in qualitative). It answers
    "given my view, does the market price look cheap?"
  - Expectations difficulty compares implied growth to *historical peak*.
    It answers "regardless of my view, is the market demanding more than
    the business has ever delivered?"
"""

from __future__ import annotations

from iam.data.security import Security
from iam.engine.market_implied import MarketImpliedEngine
from iam.factors.base import Factor, FactorContribution
from iam.valuation import FCFEDCF


class IntrinsicValueFactor(Factor):
    name = "intrinsic_value"

    def __init__(
        self,
        market_implied_engine: MarketImpliedEngine | None = None,
        fcfe_dcf: FCFEDCF | None = None,
    ):
        self._market_implied_engine = market_implied_engine or MarketImpliedEngine()
        self._fcfe_dcf = fcfe_dcf or FCFEDCF()

    def compute(self, security: Security) -> FactorContribution:
        components: dict[str, float] = {}
        notes: list[str] = []
        confidence = 1.0

        dcf_residual = self._dcf_residual(security)
        if dcf_residual is None:
            confidence *= 0.6
            notes.append("DCF inputs incomplete; skipping DCF residual.")
        else:
            components["dcf_residual"] = dcf_residual

        reverse_gap = self._market_implied_engine_gap(security)
        if reverse_gap is None:
            confidence *= 0.7
            notes.append("Reverse DCF inputs incomplete.")
        else:
            components["market_implied_engine_gap"] = reverse_gap

        fcf_yield_score = self._fcf_yield_score(security)
        if fcf_yield_score is None:
            confidence *= 0.7
            notes.append("FCF yield unavailable.")
        else:
            components["owner_earnings_yield"] = fcf_yield_score

        value = self.weighted_average(
            {
                "dcf": (components.get("dcf_residual"), 0.50),
                "reverse": (components.get("market_implied_engine_gap"), 0.30),
                "yield": (components.get("owner_earnings_yield"), 0.20),
            }
        )

        return FactorContribution(
            name=self.name,
            value=self.clamp(value),
            confidence=confidence,
            components=components,
            notes=notes,
        )

    def _dcf_residual(self, security: Security):
        """Fair-value / price - 1 from a forward FCFE DCF, clamped to [-1, 1].

        Requires explicit ``forecast_growth`` in ``security.qualitative``.
        Without it we'd be discounting arbitrary defaults — meaningless
        for cross-sectional comparison.
        """
        if "forecast_growth" not in security.qualitative:
            return None
        result = self._fcfe_dcf.compute(security)
        if result.fair_value_to_price is None or result.confidence == 0.0:
            return None
        return self.clamp(result.fair_value_to_price)

    def _market_implied_engine_gap(self, security: Security):
        """Score in [-1, 1] for "is the price low given my thesis growth?"

        Uses (thesis - implied) / thesis. Positive means the thesis is
        *higher* than what the market demands (cheap, bullish). Returns
        None if inputs are missing.
        """
        thesis_g = security.qualitative.get("forecast_growth")
        if thesis_g is None or thesis_g <= 0:
            return None
        result = self._market_implied_engine.compute(security)
        if result.implied is None:
            return None
        implied_g = result.implied.implied_revenue_growth
        if implied_g is None:
            return None
        gap = (thesis_g - implied_g) / thesis_g
        return self.clamp(gap)

    def _fcf_yield_score(self, security: Security):
        m = security.market
        f = security.fundamentals
        fcf_yield = m.fcf_yield
        if fcf_yield is None and f.fcf_ttm and m.market_cap:
            fcf_yield = f.fcf_ttm / m.market_cap
        if fcf_yield is None:
            return None
        return self.clamp((fcf_yield - 0.035) / 0.04)

