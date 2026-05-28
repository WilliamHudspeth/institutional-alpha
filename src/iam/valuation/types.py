"""Shared types used across all valuation methods.

The central insight: every valuation method — reverse DCF, relative, SOTP/FCFE —
produces an answer to the same question: *what does this method say the
equity is worth?* Returning a consistent shape makes triangulation tractable
and forces each method to be explicit about its uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Method(str, Enum):
    """Which valuation method produced a result."""

    REVERSE_DCF = "reverse_dcf"
    RELATIVE = "relative"
    INTRINSIC = "intrinsic"  # SOTP + FCFE DCF


@dataclass
class ImpliedExpectations:
    """The output of a reverse DCF. The set of operating assumptions the
    *current market price* implicitly demands the business deliver.

    These aren't forecasts — they're what the market is implicitly forecasting.
    The whole point of reverse DCF is to make those implicit assumptions
    explicit so you can ask: are they plausible?
    """

    implied_revenue_growth: float | None = None  # 5-10y CAGR
    implied_operating_margin: float | None = None  # steady-state
    implied_roic: float | None = None  # steady-state
    implied_terminal_growth: float | None = None
    implied_reinvestment_rate: float | None = None
    discount_rate_assumed: float | None = None

    # How does this compare to what the business has actually done?
    growth_vs_history_max: float | None = None  # implied / 5y peak
    margin_vs_history_peak: float | None = None
    roic_vs_industry_peak: float | None = None


@dataclass
class ValuationResult:
    """The standard output of any single valuation method.

    All three pipeline stages produce one of these, which lets Stage 4
    (triangulation) compare them like-for-like.
    """

    method: Method
    fair_value_per_share: float | None = None  # the headline number
    fair_value_to_price: float | None = None  # fair / current price - 1
    confidence: float = 1.0  # in [0, 1]

    # Sub-results that the method computed along the way — useful for audit.
    components: dict[str, float] = field(default_factory=dict)
    assumptions: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # Reverse DCF specifically populates this; other methods leave it None.
    implied: ImpliedExpectations | None = None

    # Each method should populate a one-line plain-English summary.
    verdict_text: str = ""

    @property
    def is_bullish(self) -> bool | None:
        """True if fair value > price, False if <, None if can't tell."""
        if self.fair_value_to_price is None:
            return None
        return self.fair_value_to_price > 0


@dataclass
class TriangulationResult:
    """The output of Stage 4. Tells you whether the three methods agree,
    where the cluster sits, and how confident the verdict is."""

    cluster_center: float | None = None  # fair_value_to_price of cluster
    cluster_members: list[Method] = field(default_factory=list)
    outliers: list[Method] = field(default_factory=list)
    spread: float | None = None  # max - min across all three
    confidence: float = 0.0  # in [0, 1]
    verdict: str = ""  # "agree" | "two_of_three" | "disagree"
    notes: list[str] = field(default_factory=list)
