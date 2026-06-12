"""Expectations Difficulty Diagnostic Lens."""

from __future__ import annotations

from iam.data.security import Security
from iam.engine.market_implied import MarketImpliedEngine
from iam.lenses.base import BaseLens, LensResult


class ExpectationsDifficultyLens(BaseLens):
    """Diagnostic lens for expectations difficulty.

    Uses MarketImpliedEngine to compute what growth is implied by the current price,
    and compares it to the company's historical peak growth.
    """

    name = "expectations_difficulty"

    def compute(self, security: Security) -> LensResult:
        # Rule 1: 10 years projection for all three
        rev_dcf = MarketImpliedEngine(high_growth_years=10).compute(security)

        narrative = "Could not compute expectations difficulty (likely missing inputs)."
        conf = rev_dcf.confidence
        implied_g = None
        growth_vs_max = None

        if rev_dcf.implied:
            implied_g = rev_dcf.implied.implied_revenue_growth
            growth_vs_max = rev_dcf.implied.growth_vs_history_max

            if implied_g is not None:
                if growth_vs_max is not None:
                    narrative = f"Current price implies {implied_g * 100:.1f}% annual growth ({growth_vs_max * 100:.0f}% of historical peak)."
                else:
                    narrative = f"Current price implies {implied_g * 100:.1f}% annual growth."

        # Rule 5: purely diagnostic. fair_value_low, fair_value_high, implied_move_pct all None.
        return LensResult(
            lens_name=self.name,
            fair_value_low=None,
            fair_value_high=None,
            implied_move_pct=None,
            confidence=conf,
            narrative=narrative,
            assumptions={
                "implied_growth": implied_g if implied_g is not None else 0.0,
                "growth_vs_max": growth_vs_max if growth_vs_max is not None else 0.0,
            },
        )

