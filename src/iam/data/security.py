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

from dataclasses import dataclass, field, replace
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

    # Risk
    beta: Optional[float] = None                           # equity beta vs market index

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

    ``revenue_mix`` is optional: a dict mapping region/country codes to revenue
    weights. Used by GroundTruthProvider for blended ERP calculation.
    """

    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country_iso: str = "US"
    fundamentals: Fundamentals = field(default_factory=Fundamentals)
    market: MarketData = field(default_factory=MarketData)
    macro: Optional[MacroContext] = None
    qualitative: dict[str, Any] = field(default_factory=dict)
    theses: list[Thesis] = field(default_factory=list)
    revenue_mix: dict[str, float] = field(default_factory=dict)

    def normalized_mix(self) -> dict[str, float]:
        """Return revenue_mix normalized to percentages that sum to 1.0.

        Handles both decimal (0.64) and percentage (64) formats.
        Accepts country codes (US, CN), region names (north_america, europe),
        and region aliases (NA, APAC).

        Returns:
            Dict mapping normalized tokens to decimal weights (0-1)

        Raises:
            ValueError: If revenue_mix sums to zero
        """
        if not self.revenue_mix:
            return {}

        total = sum(self.revenue_mix.values())
        if total == 0:
            raise ValueError(f"{self.ticker}: revenue_mix sums to zero")

        # Detect if user entered percentages (sum > 1.5) or decimals (sum <= 1.5)
        scale = 100.0 if total > 1.5 else 1.0
        scaled = {k.lower(): v / scale for k, v in self.revenue_mix.items()}

        # Re-normalize to ensure sum = 1.0 (handles floating point errors)
        scaled_sum = sum(scaled.values())
        return {k: v / scaled_sum for k, v in scaled.items()}


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


def apply_scenario(base: Security, revenue_mix_delta: dict[str, float]) -> Security:
    """Create a new Security with adjusted revenue mix for scenario analysis.

    This function implements immutable scenario construction: it takes a base
    Security and applies a delta to the revenue_mix, returning a new Security
    object with the adjusted mix. The base is never mutated.

    Args:
        base: Base Security with existing revenue_mix
        revenue_mix_delta: Dict with adjustments (e.g., {"US": +0.05, "CN": -0.05})

    Returns:
        New Security with updated revenue_mix (normalized to sum to 1.0)

    Example:
        >>> base = Security(ticker="NVDA", revenue_mix={"US": 0.44, "CN": 0.25})
        >>> bull = apply_scenario(base, {"US": +0.10, "CN": -0.10})
        >>> bull.normalized_mix()
        {"us": 0.563, "cn": 0.154, ...}
    """
    current_mix = base.normalized_mix().copy()

    # Apply delta
    for key, delta in revenue_mix_delta.items():
        key_lower = key.lower()
        current_mix[key_lower] = max(0, current_mix.get(key_lower, 0) + delta)

    # Re-normalize
    total = sum(current_mix.values())
    if total <= 0:
        raise ValueError(f"Revenue mix sums to zero after scenario application: {current_mix}")

    normalized = {k: v / total for k, v in current_mix.items()}

    # Return new Security with updated revenue_mix
    return replace(base, revenue_mix=normalized)
