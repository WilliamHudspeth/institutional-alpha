"""Core data classes for the IAM framework.

All fields default to None (or empty list/dict) so that a Security can be
constructed with minimal data; factors and valuation methods reduce confidence
when inputs are absent rather than hard-failing.

Conventions:
  - Monetary values: raw currency units (same scale as market_cap / price)
  - Percentages: decimal form (0.15 = 15%)
  - Historical lists: most-recent-first (index 0 = newest)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class Assumption:
    """A single named assumption underpinning a valuation thesis."""
    name: str
    value: Union[float, str]
    rationale: str = ""
    source: str = "model"  # "model" | "consensus" | "user"


@dataclass
class Thesis:
    """A labelled valuation scenario (e.g. bull, base, bear)."""
    label: str
    assumptions: list[Assumption] = field(default_factory=list)
    fair_value_low: Optional[float] = None
    fair_value_high: Optional[float] = None
    narrative: str = ""

    def __post_init__(self) -> None:
        if self.fair_value_low is not None and self.fair_value_high is not None:
            if self.fair_value_low > self.fair_value_high:
                raise ValueError(
                    f"Thesis '{self.label}': fair_value_low ({self.fair_value_low}) "
                    f"must not exceed fair_value_high ({self.fair_value_high})"
                )

@dataclass
class MacroContext:
    """Macro-environment inputs consumed by MacroRegimeFactor and MacroOverlay."""

    # Rates & yields
    real_rate_10y: Optional[float] = None            # real 10Y rate (decimal)
    real_rate_trend: Optional[str] = None            # "falling" | "flat" | "rising"
    yield_curve_slope_10y_2y: Optional[float] = None # 10Y - 2Y in decimal (e.g. 0.005 = 50bps)

    # Credit
    credit_spread_hy: Optional[float] = None         # HY spread, decimal (0.035 = 350bps)

    # Liquidity / volatility
    liquidity_index: Optional[float] = None          # normalized [-1, 1]

    # Activity
    pmi_direction: Optional[str] = None              # "expanding" | "contracting"

    # Currency
    dxy_trend: Optional[str] = None                  # "falling" | "flat" | "rising"
    
    # Valuation
    erp: Optional[float] = None                      # Equity Risk Premium (decimal)


@dataclass
class Fundamentals:
    """Financial statement and quality metrics for a single security."""

    # Revenue
    revenue_ttm: Optional[float] = None
    revenue_history: list[float] = field(default_factory=list)  # most-recent-first

    # Margins
    gross_margin: Optional[float] = None
    gross_margin_history: list[float] = field(default_factory=list)
    operating_margin: Optional[float] = None
    operating_margin_history: list[float] = field(default_factory=list)

    # Profitability
    net_income_ttm: Optional[float] = None
    ebitda_ttm: Optional[float] = None

    # Cash flow
    fcf_ttm: Optional[float] = None
    fcf_history: list[float] = field(default_factory=list)
    capex_ttm: Optional[float] = None

    # Returns & quality
    roic_history: list[float] = field(default_factory=list)
    incremental_roic: Optional[float] = None
    accruals_ratio: Optional[float] = None           # Sloan accrual ratio

    # Stock-based compensation
    sbc_ttm: Optional[float] = None

    # Balance sheet
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    current_ratio: Optional[float] = None
    interest_expense_ttm: Optional[float] = None
    debt_maturity_within_24m: Optional[float] = None

    # Share count
    shares_outstanding: Optional[float] = None
    shares_outstanding_history: list[float] = field(default_factory=list)

    # Earnings quality
    one_time_adjustments_count_5y: Optional[int] = None

    # Segments (used by SOTP; import avoided to keep circular-free at runtime)
    segments: list = field(default_factory=list)  # list[Segment] from iam.valuation.sotp


@dataclass
class MarketData:
    """Market price, valuation multiples, positioning, and sentiment data."""

    # Price & cap
    price: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None

    # Valuation multiples
    pe_ttm: Optional[float] = None
    pe_forward: Optional[float] = None
    pe_history: list[float] = field(default_factory=list)  # most-recent-first
    ev_ebitda: Optional[float] = None
    sector_ev_ebitda_median: Optional[float] = None
    fcf_yield: Optional[float] = None
    ev_sales: Optional[float] = None

    # Peer comparisons
    peer_ev_sales_median: Optional[float] = None
    peer_fcf_yields: list[float] = field(default_factory=list)

    # Positioning
    hedge_fund_ownership_pct: Optional[float] = None
    retail_ownership_pct: Optional[float] = None
    short_interest_pct_float: Optional[float] = None
    passive_index_ownership_pct: Optional[float] = None

    # Options
    options_call_put_skew: Optional[float] = None

    # Sentiment & momentum
    analyst_revisions_breadth_30d: Optional[float] = None  # [-1, 1]
    earnings_surprise_history: list[float] = field(default_factory=list)
    news_sentiment_delta: Optional[float] = None           # [-1, 1]
    price_history: list[float] = field(default_factory=list)  # daily closes, most-recent-first


@dataclass
class Security:
    """Top-level container passed to every factor and valuation method.

    ``qualitative`` is a free-form dict for user-supplied inputs that don't
    belong in structured financial data: reflexivity scores, runway estimates,
    FCFE forecast assumptions, SOTP segments, etc. Keys are documented in
    docs/factors.md.
    """

    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    fundamentals: Fundamentals = field(default_factory=Fundamentals)
    market: MarketData = field(default_factory=MarketData)
    macro: Optional[MacroContext] = None
    qualitative: dict[str, Any] = field(default_factory=dict)
    theses: list[Thesis] = field(default_factory=list)


def show_spread(security: Security) -> str:
    """Return a plain-text summary of the theses attached to a Security.

    Single thesis: shows label, fair-value range, and narrative.
    Multiple theses: shows each, then appends a spread line. Flags the spread
    as 'wide' when it exceeds 30% of the range midpoint.
    """
    theses = security.theses
    if not theses:
        return "No theses attached."

    lines: list[str] = []
    for t in theses:
        lines.append(f"Thesis: {t.label}")
        lo = f"{t.fair_value_low:.2f}" if t.fair_value_low is not None else "--"
        hi = f"{t.fair_value_high:.2f}" if t.fair_value_high is not None else "--"
        lines.append(f"  Fair value range: {lo} - {hi}")
        if t.narrative:
            lines.append(f"  {t.narrative}")

    if len(theses) > 1:
        highs = [t.fair_value_high for t in theses if t.fair_value_high is not None]
        lows = [t.fair_value_low for t in theses if t.fair_value_low is not None]
        if highs and lows:
            top = max(highs)
            bottom = min(lows)
            if top < bottom:
                return "\n".join(lines)
            spread = top - bottom
            midpoint = (top + bottom) / 2
            lines.append("")
            flag = ""
            if midpoint > 0 and spread > 0.30 * midpoint:
                flag = " [wide]"
            lines.append(f"Spread: {spread:.2f} (high {top:.2f} - low {bottom:.2f}){flag}")

    return "\n".join(lines)
