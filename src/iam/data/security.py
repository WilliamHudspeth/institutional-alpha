"""Core data model: Security, Fundamentals, MarketData, MacroContext.

These are plain dataclasses — no validation, no magic. The framework is
deliberately data-source agnostic: populate the fields from whatever
provider you wire in (yfinance, FMP, Bloomberg, hand-typed).

All list fields follow a most-recent-first convention (index 0 = TTM/current,
index -1 = oldest available) to match how most data providers return history.

Fields are Optional[float] so you can construct a Security with only the
data you have and the factor system degrades gracefully on missing inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Fundamentals:
    # --- Income statement ---
    revenue_ttm: Optional[float] = None
    revenue_history: list[float] = field(default_factory=list)   # most-recent-first
    gross_margin: Optional[float] = None
    gross_margin_history: list[float] = field(default_factory=list)
    operating_margin: Optional[float] = None
    operating_margin_history: list[float] = field(default_factory=list)
    net_income_ttm: Optional[float] = None
    ebitda_ttm: Optional[float] = None
    interest_expense_ttm: Optional[float] = None

    # --- Cash flow ---
    fcf_ttm: Optional[float] = None
    fcf_history: list[float] = field(default_factory=list)
    capex_ttm: Optional[float] = None
    sbc_ttm: Optional[float] = None                              # stock-based compensation

    # --- Balance sheet ---
    total_debt: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    debt_maturity_within_24m: Optional[float] = None             # debt due in <2 years
    current_ratio: Optional[float] = None

    # --- Returns and reinvestment ---
    roic_history: list[float] = field(default_factory=list)
    incremental_roic: Optional[float] = None

    # --- Share count ---
    shares_outstanding: Optional[float] = None
    shares_outstanding_history: list[float] = field(default_factory=list)  # most-recent-first

    # --- Earnings quality inputs ---
    accruals_ratio: Optional[float] = None                       # Sloan accrual ratio
    one_time_adjustments_count_5y: Optional[int] = None

    # --- Multi-segment data (used by SOTP) ---
    segments: Optional[list] = None


@dataclass
class MarketData:
    # --- Price / valuation ---
    price: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    pe_ttm: Optional[float] = None
    pe_forward: Optional[float] = None
    pe_history: list[float] = field(default_factory=list)        # monthly, most-recent-first
    ev_ebitda: Optional[float] = None
    ev_sales: Optional[float] = None

    # --- FCF / yield ---
    fcf_yield: Optional[float] = None

    # --- Relative valuation benchmarks ---
    sector_ev_ebitda_median: Optional[float] = None
    peer_ev_sales_median: Optional[float] = None
    peer_fcf_yields: list[float] = field(default_factory=list)

    # --- Positioning / crowding ---
    hedge_fund_ownership_pct: Optional[float] = None
    retail_ownership_pct: Optional[float] = None
    short_interest_pct_float: Optional[float] = None
    options_call_put_skew: Optional[float] = None
    passive_index_ownership_pct: Optional[float] = None

    # --- Sentiment ---
    analyst_revisions_breadth_30d: Optional[float] = None        # in [-1, 1]
    earnings_surprise_history: list[float] = field(default_factory=list)
    news_sentiment_delta: Optional[float] = None                 # in [-1, 1]

    # --- Price history (for momentum) ---
    price_history: list[float] = field(default_factory=list)     # daily, most-recent-first


@dataclass
class MacroContext:
    """Macro snapshot attached to a Security — drives MacroRegimeFactor.

    String-tagged fields ("rising", "flat", "falling") keep the factor's
    regime logic readable; see MacroConditions in iam.data.macro for the
    numeric variant used by the pipeline's macro overlay.
    """
    real_rate_10y: Optional[float] = None
    real_rate_trend: Optional[str] = None          # "rising" | "flat" | "falling"
    liquidity_index: Optional[float] = None        # normalized, ~[-1, 1]
    credit_spread_hy: Optional[float] = None       # e.g. 0.035 = 3.5%
    yield_curve_slope_10y_2y: Optional[float] = None
    pmi_direction: Optional[str] = None            # "expanding" | "contracting"
    dxy_trend: Optional[str] = None                # "rising" | "flat" | "falling"


@dataclass
class Security:
    """The top-level container for everything the framework knows about an equity.

    Pass this to ``iam.score()`` or ``ValuationPipeline().run()``.
    """
    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    fundamentals: Fundamentals = field(default_factory=Fundamentals)
    market: MarketData = field(default_factory=MarketData)
    macro: MacroContext = field(default_factory=MacroContext)
    qualitative: dict = field(default_factory=dict)
