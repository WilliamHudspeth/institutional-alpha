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

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Assumption(BaseModel):
    """A single named assumption underpinning a valuation thesis."""

    name: str
    value: float | str
    rationale: str = ""
    source: str = "model"  # "model" | "consensus" | "user"


class Thesis(BaseModel):
    """A labelled valuation scenario (e.g. bull, base, bear)."""

    label: str
    assumptions: list[Assumption] = Field(default_factory=list)
    fair_value_low: float | None = None
    fair_value_high: float | None = None
    narrative: str = ""

    @model_validator(mode="after")
    def validate_fair_value_range(self) -> Thesis:
        if self.fair_value_low is not None and self.fair_value_high is not None:
            if self.fair_value_low > self.fair_value_high:
                raise ValueError(
                    f"Thesis '{self.label}': fair_value_low ({self.fair_value_low}) "
                    f"must not exceed fair_value_high ({self.fair_value_high})"
                )
        return self


class MacroContext(BaseModel):
    """Macro-environment inputs consumed by MacroRegimeFactor and MacroOverlay."""

    # Rates & yields
    real_rate_10y: float | None = None  # real 10Y rate (decimal)
    real_rate_trend: str | None = None  # "falling" | "flat" | "rising"
    yield_curve_slope_10y_2y: float | None = None  # 10Y - 2Y in decimal (e.g. 0.005 = 50bps)

    # Credit
    credit_spread_hy: float | None = None  # HY spread, decimal (0.035 = 350bps)

    # Liquidity / volatility
    liquidity_index: float | None = None  # normalized [-1, 1]

    # Activity
    pmi_direction: str | None = None  # "expanding" | "contracting"

    # Currency
    dxy_trend: str | None = None  # "falling" | "flat" | "rising"

    # Valuation
    erp: float | None = None  # Equity Risk Premium (decimal)


class Fundamentals(BaseModel):
    """Financial statement and quality metrics for a single security."""

    # Revenue
    revenue_ttm: float | None = None
    revenue_history: list[float] = Field(default_factory=list)  # most-recent-first

    # Margins
    gross_margin: float | None = None
    gross_margin_history: list[float] = Field(default_factory=list)
    operating_margin: float | None = None
    operating_margin_history: list[float] = Field(default_factory=list)

    # Profitability
    net_income_ttm: float | None = None
    ebitda_ttm: float | None = None

    # Cash flow
    fcf_ttm: float | None = None
    fcf_history: list[float] = Field(default_factory=list)
    capex_ttm: float | None = None

    # Returns & quality
    roic_history: list[float] = Field(default_factory=list)
    incremental_roic: float | None = None
    accruals_ratio: float | None = None  # Sloan accrual ratio

    # Stock-based compensation
    sbc_ttm: float | None = None
    change_in_working_capital: float | None = None

    # Balance sheet
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    current_ratio: float | None = None
    interest_expense_ttm: float | None = None
    debt_maturity_within_24m: float | None = None

    # Share count
    shares_outstanding: float | None = None
    shares_outstanding_history: list[float] = Field(default_factory=list)

    # Earnings quality
    one_time_adjustments_count_5y: int | None = None

    # Segments (used by SOTP; import avoided to keep circular-free at runtime)
    segments: list = Field(default_factory=list)  # list[Segment] from iam.valuation.sotp


class MarketData(BaseModel):
    """Market price, valuation multiples, positioning, and sentiment data."""

    # Price & cap
    price: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None

    # Valuation multiples
    pe_ttm: float | None = None
    pe_forward: float | None = None
    pe_history: list[float] = Field(default_factory=list)  # most-recent-first
    ev_ebitda: float | None = None
    sector_ev_ebitda_median: float | None = None
    fcf_yield: float | None = None
    ev_sales: float | None = None

    # Peer comparisons
    peer_ev_sales_median: float | None = None
    peer_fcf_yields: list[float] = Field(default_factory=list)

    # Positioning
    hedge_fund_ownership_pct: float | None = None
    retail_ownership_pct: float | None = None
    short_interest_pct_float: float | None = None
    passive_index_ownership_pct: float | None = None

    # Options
    options_call_put_skew: float | None = None

    # Risk
    beta: float | None = None  # equity beta vs market index

    # Sentiment & momentum
    analyst_revisions_breadth_30d: float | None = None  # [-1, 1]
    earnings_surprise_history: list[float] = Field(default_factory=list)
    news_sentiment_delta: float | None = None  # [-1, 1]
    price_history: list[float] = Field(default_factory=list)  # daily closes, most-recent-first


class Security(BaseModel):
    """Top-level container passed to every factor and valuation method.

    ``qualitative`` is a free-form dict for user-supplied inputs that don't
    belong in structured financial data: reflexivity scores, runway estimates,
    FCFE forecast assumptions, SOTP segments, etc. Keys are documented in
    docs/factors.md.

    ``revenue_mix`` is optional: a dict mapping region/country codes to revenue
    weights. Used by GroundTruthProvider for blended ERP calculation.
    """

    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    country_iso: str = "US"
    fundamentals: Fundamentals = Field(default_factory=Fundamentals)
    market: MarketData = Field(default_factory=MarketData)
    macro: MacroContext | None = None
    qualitative: dict[str, Any] = Field(default_factory=dict)
    theses: list[Thesis] = Field(default_factory=list)
    revenue_mix: dict[str, float] = Field(default_factory=dict)

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
    return base.model_copy(update={"revenue_mix": normalized})
