"""Stage 1: Reverse DCF.

The pipeline's anchor. Instead of building a fair value bottom-up, we take
the current market price as given and solve for the operating performance
the market is implicitly assuming.

Two-stage Gordon growth structure:

    Price = sum_{t=1}^{N} FCFE_t / (1+r)^t  +  TV_N / (1+r)^N

Where FCFE grows at rate g_high for N years, then at g_terminal forever.
We solve for g_high given everything else.

The output is *not* a buy/sell signal. It's a set of expectations — the
thesis the rest of the pipeline tests.
"""

from __future__ import annotations

from typing import Optional

from iam.data.security import Security
from iam.valuation.types import Method, ValuationResult, ImpliedExpectations


# Reasonable defaults; can be overridden via Security or call-site.
DEFAULT_DISCOUNT_RATE = 0.09          # generalist equity cost of capital
DEFAULT_HIGH_GROWTH_YEARS = 10        # explicit forecast horizon
DEFAULT_TERMINAL_GROWTH = 0.025       # GDP-ish steady state


def _present_value_two_stage(
    base_fcfe: float,
    g_high: float,
    n: int,
    g_terminal: float,
    r: float,
) -> float:
    """PV per share of a two-stage FCFE stream."""
    if r <= g_terminal:
        # Terminal growth must be below discount rate for the model to converge.
        return float("inf")

    pv = 0.0
    fcfe_t = base_fcfe
    for t in range(1, n + 1):
        fcfe_t = base_fcfe * ((1 + g_high) ** t)
        pv += fcfe_t / ((1 + r) ** t)

    # Terminal value at end of year N
    fcfe_n_plus_1 = fcfe_t * (1 + g_terminal)
    terminal_value = fcfe_n_plus_1 / (r - g_terminal)
    pv += terminal_value / ((1 + r) ** n)

    return pv


def _solve_implied_growth(
    target_price: float,
    base_fcfe: float,
    n: int,
    g_terminal: float,
    r: float,
    lo: float = -0.20,
    hi: float = 0.60,
    tol: float = 1e-4,
    max_iter: int = 80,
) -> Optional[float]:
    """Bisection: find g_high such that PV(...) == target_price."""

    pv_lo = _present_value_two_stage(base_fcfe, lo, n, g_terminal, r)
    pv_hi = _present_value_two_stage(base_fcfe, hi, n, g_terminal, r)

    if pv_lo > target_price:
        # Even at the lowest growth, the model says the stock is worth more
        # than its price. The market is implying decline.
        return lo
    if pv_hi < target_price:
        # Even at very high growth we can't reach the price. Market is
        # implying something extreme — fail gracefully.
        return None

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        pv_mid = _present_value_two_stage(base_fcfe, mid, n, g_terminal, r)
        if abs(pv_mid - target_price) / target_price < tol:
            return mid
        if pv_mid < target_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class ReverseDCF:
    """Stage 1 of the pipeline.

    Usage:
        result = ReverseDCF().compute(security)
        result.implied.implied_revenue_growth  # what does the market expect?
    """

    def __init__(
        self,
        discount_rate: float = DEFAULT_DISCOUNT_RATE,
        high_growth_years: int = DEFAULT_HIGH_GROWTH_YEARS,
        terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    ):
        self.r = discount_rate
        self.n = high_growth_years
        self.g_terminal = terminal_growth

    def compute(self, security: Security) -> ValuationResult:
        m = security.market
        f = security.fundamentals
        notes: list[str] = []
        confidence = 1.0

        # Need a price and a current FCFE (using FCF as proxy here; full FCFE
        # would adjust for net borrowing — see the FCFE module).
        if m.price is None or f.fcf_ttm is None or f.shares_outstanding is None:
            return ValuationResult(
                method=Method.REVERSE_DCF,
                confidence=0.0,
                notes=["Reverse DCF requires price, FCF TTM, and shares outstanding."],
                verdict_text="Insufficient data for reverse DCF.",
            )

        fcfe_per_share = f.fcf_ttm / f.shares_outstanding
        if fcfe_per_share <= 0:
            return ValuationResult(
                method=Method.REVERSE_DCF,
                confidence=0.3,
                notes=["Negative or zero base FCFE — reverse DCF unreliable."],
                verdict_text="Base FCFE non-positive; method skipped.",
            )

        implied_g = _solve_implied_growth(
            target_price=m.price,
            base_fcfe=fcfe_per_share,
            n=self.n,
            g_terminal=self.g_terminal,
            r=self.r,
        )

        if implied_g is None:
            return ValuationResult(
                method=Method.REVERSE_DCF,
                confidence=0.2,
                notes=["Implied growth exceeds plausible bound (>60%)."],
                verdict_text="Market implies implausibly high growth.",
            )

        # Compare implied growth to history for context.
        growth_vs_max: Optional[float] = None
        if len(f.revenue_history) >= 4 and f.revenue_history[-1] > 0:
            # Year-over-year growth rates from history (most-recent-first).
            rates = []
            for i in range(len(f.revenue_history) - 1):
                if f.revenue_history[i + 1] > 0:
                    rates.append(f.revenue_history[i] / f.revenue_history[i + 1] - 1)
            if rates:
                peak = max(rates)
                if peak > 0:
                    growth_vs_max = implied_g / peak
        else:
            confidence *= 0.85
            notes.append("Insufficient history to compare implied growth to peak.")

        implied = ImpliedExpectations(
            implied_revenue_growth=implied_g,
            implied_terminal_growth=self.g_terminal,
            discount_rate_assumed=self.r,
            growth_vs_history_max=growth_vs_max,
        )

        # Build a plain-English verdict.
        verdict = self._verdict_text(implied_g, growth_vs_max)

        return ValuationResult(
            method=Method.REVERSE_DCF,
            # Reverse DCF doesn't produce a fair value per share — it produces
            # an expectations vector. We populate fair_value_to_price as the
            # *gap between implied and plausible* in later stages.
            fair_value_per_share=None,
            fair_value_to_price=None,
            confidence=confidence,
            implied=implied,
            assumptions={
                "discount_rate": self.r,
                "high_growth_years": float(self.n),
                "terminal_growth": self.g_terminal,
                "base_fcfe_per_share": fcfe_per_share,
            },
            components={"implied_growth": implied_g},
            notes=notes,
            verdict_text=verdict,
        )

    @staticmethod
    def _verdict_text(g: float, vs_max: Optional[float]) -> str:
        g_pct = g * 100
        base = f"Market implies ~{g_pct:.1f}% annual FCFE growth for the next decade"
        if vs_max is None:
            return base + "."
        if vs_max < 0.7:
            return base + f" — comfortably below the {1/vs_max:.1f}x peak the business has delivered."
        if vs_max < 1.0:
            return base + f" — within historical capability ({vs_max:.0%} of peak)."
        if vs_max < 1.5:
            return base + f" — moderately above the historical peak ({vs_max:.0%})."
        return base + f" — substantially above what the business has ever delivered ({vs_max:.0%} of peak)."
