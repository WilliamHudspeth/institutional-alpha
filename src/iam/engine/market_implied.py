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

from iam.data.security import Security
from iam.valuation.beta import get_yahoo_beta
from iam.valuation.types import ImpliedExpectations, Method, ValuationResult

# Reasonable defaults; can be overridden via Security or call-site.
DEFAULT_DISCOUNT_RATE = 0.09  # generalist equity cost of capital
DEFAULT_HIGH_GROWTH_YEARS = 10  # explicit forecast horizon
DEFAULT_TERMINAL_GROWTH = 0.025  # GDP-ish steady state
DEFAULT_ROE = 0.15  # Return on Equity for reinvestment constraint (g / ROE)


def _present_value_two_stage(
    base_ni: float,
    g_high: float,
    n: int,
    g_terminal: float,
    r: float,
    roe: float,
) -> float:
    """PV per share of a two-stage FCFE stream."""
    if r <= g_terminal:
        # Terminal growth must be below discount rate for the model to converge.
        return float("inf")

    # Enforce Equity Reinvestment Rate (ERR) constraint: ERR = g / ROE
    # Cap ERR at 1.0 (100%) to prevent negative cash flows in high growth
    err_high = min(g_high / roe, 1.0) if roe > 0 else 1.0
    err_term = min(g_terminal / roe, 1.0) if roe > 0 else 1.0

    pv = 0.0
    ni_t = base_ni
    for t in range(1, n + 1):
        ni_t = base_ni * ((1 + g_high) ** t)
        fcfe_t = ni_t * (1 - err_high)
        pv += fcfe_t / ((1 + r) ** t)

    # Terminal value at end of year N
    ni_n_plus_1 = ni_t * (1 + g_terminal)
    fcfe_n_plus_1 = ni_n_plus_1 * (1 - err_term)
    terminal_value = fcfe_n_plus_1 / (r - g_terminal)
    pv += terminal_value / ((1 + r) ** n)

    return pv


def _solve_implied_growth(
    target_price: float,
    base_ni: float,
    n: int,
    g_terminal: float,
    r: float,
    roe: float,
    lo: float = -0.20,
    hi: float = 0.60,
    tol: float = 1e-4,
    max_iter: int = 80,
) -> float | None:
    """Bisection: find g_high such that PV(...) == target_price."""

    pv_lo = _present_value_two_stage(base_ni, lo, n, g_terminal, r, roe)
    pv_hi = _present_value_two_stage(base_ni, hi, n, g_terminal, r, roe)

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
        pv_mid = _present_value_two_stage(base_ni, mid, n, g_terminal, r, roe)
        if abs(pv_mid - target_price) / target_price < tol:
            return mid
        if pv_mid < target_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class MarketImpliedEngine:
    """Stage 1 of the pipeline.

    Usage:
        result = MarketImpliedEngine().compute(security)
        result.implied.implied_revenue_growth  # what does the market expect?
    """

    def __init__(
        self,
        discount_rate: float = DEFAULT_DISCOUNT_RATE,
        high_growth_years: int = DEFAULT_HIGH_GROWTH_YEARS,
        terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
        roe: float = DEFAULT_ROE,
    ):
        self.r = discount_rate
        self.n = high_growth_years
        self.g_terminal = terminal_growth
        self.roe = roe

    def compute(self, security: Security) -> ValuationResult:
        m = security.market
        f = security.fundamentals
        qualitative = security.qualitative or {}
        notes: list[str] = []
        confidence = 1.0

        ni = f.net_income_ttm if f.net_income_ttm and f.net_income_ttm > 0 else f.fcf_ttm
        roe = qualitative.get("forecast_roe", self.roe)

        # CAPM discount rate (opt-in): if risk_free_rate and equity_risk_premium
        # are supplied, compute cost of equity from Yahoo beta.  Otherwise use
        # the flat rate passed at construction time.
        r = self.r
        rfr = qualitative.get("risk_free_rate")
        erp = qualitative.get("equity_risk_premium")
        if rfr is not None and erp is not None:
            beta = get_yahoo_beta(security)
            r = float(rfr) + beta * float(erp)
            notes.append(
                f"CAPM discount rate: {rfr:.3f} + {beta:.4f} × {erp:.3f} = {r:.4f} "
                f"(Yahoo beta, Stage 1)"
            )

        if m.price is None or ni is None or f.shares_outstanding is None:
            return ValuationResult(
                method=Method.REVERSE_DCF,
                confidence=0.0,
                notes=["Reverse DCF requires price, Net Income (or FCF), and shares outstanding."],
                verdict_text="Insufficient data for reverse DCF.",
            )

        ni_per_share = ni / f.shares_outstanding
        if ni_per_share <= 0:
            return ValuationResult(
                method=Method.REVERSE_DCF,
                confidence=0.3,
                notes=["Negative or zero base Net Income/FCFE — reverse DCF unreliable."],
                verdict_text="Base cash flow non-positive; method skipped.",
            )

        implied_g = _solve_implied_growth(
            target_price=m.price,
            base_ni=ni_per_share,
            n=self.n,
            g_terminal=self.g_terminal,
            r=r,
            roe=roe,
        )

        if implied_g is None:
            return ValuationResult(
                method=Method.REVERSE_DCF,
                confidence=0.2,
                notes=["Implied growth exceeds plausible bound (>60%)."],
                verdict_text="Market implies implausibly high growth.",
            )

        # Compare implied growth to history for context.
        growth_vs_max: float | None = None
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

        implied_rr = min(implied_g / roe, 1.0) if roe > 0 else 1.0

        implied = ImpliedExpectations(
            implied_revenue_growth=implied_g,
            implied_terminal_growth=self.g_terminal,
            discount_rate_assumed=r,
            implied_reinvestment_rate=implied_rr,
            implied_roic=roe,  # ROE used as proxy for ROIC here
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
                "discount_rate": r,
                "high_growth_years": float(self.n),
                "terminal_growth": self.g_terminal,
                "roe": roe,
                "base_ni_per_share": ni_per_share,
            },
            components={"implied_growth": implied_g},
            notes=notes,
            verdict_text=verdict,
        )

    @staticmethod
    def _verdict_text(g: float, vs_max: float | None) -> str:
        g_pct = g * 100
        base = f"Market implies ~{g_pct:.1f}% annual FCFE growth for the next decade"
        if vs_max is None:
            return base + "."
        if vs_max < 0.7:
            return (
                base
                + f" — comfortably below the {1 / vs_max:.1f}x peak the business has delivered."
            )
        if vs_max < 1.0:
            return base + f" — within historical capability ({vs_max:.0%} of peak)."
        if vs_max < 1.5:
            return base + f" — moderately above the historical peak ({vs_max:.0%})."
        return (
            base
            + f" — substantially above what the business has ever delivered ({vs_max:.0%} of peak)."
        )
