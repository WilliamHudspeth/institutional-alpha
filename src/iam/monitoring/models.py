"""
Data models for Performance Monitoring.

Uses Pydantic for validated records, matching the codebase conventions.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FactorType(str, Enum):
    """Enumeration of factor types for alpha tracking."""

    QUALITY = "quality_score"
    VALUE = "value_score"
    MOMENTUM = "momentum_score"
    SIZE = "size_score"
    VOLATILITY = "volatility_score"
    CUSTOM = "custom"


class SectorType(str, Enum):
    """GICS sector classification for sector-sliced performance."""

    ENERGY = "Energy"
    MATERIALS = "Materials"
    INDUSTRIALS = "Industrials"
    CONSUMER_DISCRETIONARY = "Consumer Discretionary"
    CONSUMER_STAPLES = "Consumer Staples"
    HEALTH_CARE = "Health Care"
    FINANCIALS = "Financials"
    INFORMATION_TECHNOLOGY = "Information Technology"
    COMMUNICATION_SERVICES = "Communication Services"
    UTILITIES = "Utilities"
    REAL_ESTATE = "Real Estate"
    UNKNOWN = "Unknown"


class AssumptionType(str, Enum):
    """Types of valuation assumptions to track."""

    REVENUE_GROWTH = "revenue_growth"
    EBITDA_MARGIN = "ebitda_margin"
    CAPEX_TO_REVENUE = "capex_to_revenue"
    WORKING_CAPITAL_CHANGE = "working_capital_change"
    TAX_RATE = "tax_rate"
    WACC = "wacc"
    TERMINAL_GROWTH = "terminal_growth"
    SHARE_COUNT = "share_count"
    CUSTOM = "custom"


class FactorAlphaRecord(BaseModel):
    """
    Records realized forward returns attributable to a factor's score.

    Used to track whether a factor's alpha has decayed over time.
    """

    factor: FactorType
    security_id: str
    sector: SectorType = SectorType.UNKNOWN
    as_of: datetime
    factor_score: float = Field(..., description="The factor score at observation time")
    forward_return_1d: float | None = Field(None, description="1-day forward return")
    forward_return_5d: float | None = Field(None, description="5-day forward return")
    forward_return_21d: float | None = Field(None, description="21-day forward return")
    forward_return_63d: float | None = Field(None, description="63-day forward return")
    benchmark_return_1d: float | None = Field(None, description="Benchmark 1-day return")
    benchmark_return_5d: float | None = Field(None, description="Benchmark 5-day return")
    benchmark_return_21d: float | None = Field(None, description="Benchmark 21-day return")
    benchmark_return_63d: float | None = Field(None, description="Benchmark 63-day return")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("factor_score")
    @classmethod
    def validate_factor_score(cls, v: float) -> float:
        if not (-10 <= v <= 10):
            raise ValueError("factor_score must be in range [-10, 10]")
        return v


class ValuationAccuracyRecord(BaseModel):
    """
    Records the accuracy of a PipelineReport's fair value estimate vs. realized price.

    Tracks whether realized outcome fell inside the report's confidence band
    or Monte Carlo percentile range.
    """

    security_id: str
    sector: SectorType = SectorType.UNKNOWN
    valuation_date: datetime
    realized_date: datetime
    fair_value: float = Field(..., gt=0, description="PipelineReport fair value estimate")
    realized_price: float = Field(..., gt=0, description="Actual market price at realized_date")
    confidence_band_low: float | None = Field(None, description="Lower bound of confidence band")
    confidence_band_high: float | None = Field(None, description="Upper bound of confidence band")
    monte_carlo_percentiles: dict[int, float] = Field(
        default_factory=dict,
        description="Monte Carlo percentile estimates (e.g., {10: 95.0, 50: 105.0, 90: 115.0})",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def absolute_error(self) -> float:
        """Absolute valuation error: |fair_value - realized_price|"""
        return abs(self.fair_value - self.realized_price)

    @property
    def relative_error(self) -> float:
        """Relative valuation error: (fair_value - realized_price) / realized_price"""
        return (self.fair_value - self.realized_price) / self.realized_price

    @property
    def within_confidence_band(self) -> bool | None:
        """Whether realized price fell within the confidence band"""
        if self.confidence_band_low is None or self.confidence_band_high is None:
            return None
        return self.confidence_band_low <= self.realized_price <= self.confidence_band_high

    @property
    def within_monte_carlo_range(self) -> bool | None:
        """Whether realized price fell within Monte Carlo percentile range (5th-95th)"""
        if not self.monte_carlo_percentiles:
            return None
        p5 = self.monte_carlo_percentiles.get(5)
        p95 = self.monte_carlo_percentiles.get(95)
        if p5 is None or p95 is None:
            return None
        return p5 <= self.realized_price <= p95

    @property
    def realized_percentile(self) -> float | None:
        """What percentile the realized price corresponds to in the Monte Carlo distribution"""
        if not self.monte_carlo_percentiles:
            return None
        sorted_pcts = sorted(self.monte_carlo_percentiles.items())
        for pct, val in sorted_pcts:
            if self.realized_price <= val:
                return float(pct)
        return 100.0


class SectorPerformanceRecord(BaseModel):
    """
    Aggregated performance metrics sliced by sector.

    Can be used to answer: how does factor/model performance differ by sector?
    """

    sector: SectorType
    as_of: datetime
    period_start: datetime
    period_end: datetime

    # Factor alpha metrics
    factor_quality_ic: float | None = Field(None, description="Quality factor IC")
    factor_value_ic: float | None = Field(None, description="Value factor IC")
    factor_momentum_ic: float | None = Field(None, description="Momentum factor IC")
    factor_size_ic: float | None = Field(None, description="Size factor IC")
    factor_volatility_ic: float | None = Field(None, description="Volatility factor IC")

    # Valuation accuracy metrics
    mean_absolute_error: float | None = Field(None, description="Mean absolute valuation error")
    mean_relative_error: float | None = Field(None, description="Mean relative valuation error")
    median_relative_error: float | None = Field(None, description="Median relative valuation error")
    hit_rate_confidence_band: float | None = Field(
        None, description="Fraction within confidence band"
    )
    hit_rate_monte_carlo: float | None = Field(
        None, description="Fraction within Monte Carlo 5th-95th percentile"
    )

    # Sample sizes
    n_factor_observations: int = 0
    n_valuation_observations: int = 0

    metadata: dict[str, Any] = Field(default_factory=dict)


class AssumptionForecastRecord(BaseModel):
    """
    Records forecast vs. actual for a valuation assumption.

    Enables tracking assumption forecast accuracy over time.
    """

    security_id: str
    sector: SectorType = SectorType.UNKNOWN
    assumption_type: AssumptionType
    valuation_date: datetime
    realized_date: datetime
    forecast_value: float = Field(..., description="The assumption value used in valuation")
    realized_value: float = Field(..., description="What actually occurred")
    forecast_horizon_days: int = Field(..., gt=0, description="Days between valuation and realization")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def absolute_error(self) -> float:
        """Absolute forecast error"""
        return abs(self.forecast_value - self.realized_value)

    @property
    def relative_error(self) -> float:
        """Relative forecast error"""
        if self.realized_value == 0:
            return float("inf")
        return (self.forecast_value - self.realized_value) / self.realized_value

    @property
    def directional_accuracy(self) -> bool:
        """Whether forecast direction matched realized direction (both positive or both negative)"""
        return (self.forecast_value > 0) == (self.realized_value > 0)


class FactorAlphaQueryFilter(BaseModel):
    """Filter for FactorAlphaQuery lookups. Unset fields are unconstrained."""

    security_id: str | None = None
    factor: FactorType | None = None
    sector: SectorType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class FactorAlphaAggregate(BaseModel):
    """Aggregated factor alpha statistics over a filtered set of observations."""

    factor: FactorType
    n_observations: int = 0
    ic_1d: float | None = None
    ic_5d: float | None = None
    ic_21d: float | None = None
    ic_63d: float | None = None
    mean_excess_return_1d: float | None = None
    mean_excess_return_5d: float | None = None
    mean_excess_return_21d: float | None = None
    mean_excess_return_63d: float | None = None
    median_excess_return_21d: float | None = None


class ValuationAccuracyQueryFilter(BaseModel):
    """Filter for ValuationAccuracyQuery lookups. Unset fields are unconstrained."""

    security_id: str | None = None
    sector: SectorType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class ValuationAccuracyAggregate(BaseModel):
    """Aggregated valuation accuracy statistics over a filtered set of observations."""

    sector: SectorType | None = None
    n_observations: int = 0
    mean_absolute_error: float | None = None
    mean_relative_error: float | None = None
    median_relative_error: float | None = None
    hit_rate_confidence_band: float | None = None
    hit_rate_monte_carlo: float | None = None


class SectorPerformanceQueryFilter(BaseModel):
    """Filter for SectorPerformanceQuery lookups. Unset fields are unconstrained."""

    sector: SectorType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class SectorPerformanceAggregate(BaseModel):
    """Cross-sector comparison built from each sector's latest performance snapshot."""

    metric: str
    ascending: bool
    ranked_sectors: list[tuple[SectorType, float]] = Field(default_factory=list)


class AssumptionForecastQueryFilter(BaseModel):
    """Filter for AssumptionForecastQuery lookups. Unset fields are unconstrained."""

    security_id: str | None = None
    sector: SectorType | None = None
    assumption_type: AssumptionType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class AssumptionForecastAggregate(BaseModel):
    """Aggregated assumption forecast accuracy statistics over a filtered set of observations."""

    assumption_type: AssumptionType | None = None
    n_observations: int = 0
    mean_absolute_error: float | None = None
    mean_relative_error: float | None = None
    median_relative_error: float | None = None
    directional_accuracy_rate: float | None = None
