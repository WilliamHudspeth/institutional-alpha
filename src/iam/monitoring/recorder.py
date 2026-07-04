"""
Passive recording layer for Performance Monitoring.

Provides recorder classes for each of the four monitoring capabilities.
Uses the existing iam.audit.AuditLog for append-only logging.
"""

from datetime import datetime
from typing import Any

from iam.audit import AuditLog
from iam.monitoring.models import (
    AssumptionForecastRecord,
    AssumptionType,
    FactorAlphaRecord,
    FactorType,
    SectorPerformanceRecord,
    SectorType,
    ValuationAccuracyRecord,
)


class FactorAlphaRecorder:
    """
    Records factor alpha observations.

    Tracks realized forward returns attributable to each factor's score
    over time to detect alpha decay.
    """

    EVENT_TYPE = "factor_alpha_observation"

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def record(
        self,
        factor: FactorType,
        security_id: str,
        sector: SectorType,
        as_of: datetime,
        factor_score: float,
        forward_return_1d: float | None = None,
        forward_return_5d: float | None = None,
        forward_return_21d: float | None = None,
        forward_return_63d: float | None = None,
        benchmark_return_1d: float | None = None,
        benchmark_return_5d: float | None = None,
        benchmark_return_21d: float | None = None,
        benchmark_return_63d: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FactorAlphaRecord:
        """Record a factor alpha observation."""
        record = FactorAlphaRecord(
            factor=factor,
            security_id=security_id,
            sector=sector,
            as_of=as_of,
            factor_score=factor_score,
            forward_return_1d=forward_return_1d,
            forward_return_5d=forward_return_5d,
            forward_return_21d=forward_return_21d,
            forward_return_63d=forward_return_63d,
            benchmark_return_1d=benchmark_return_1d,
            benchmark_return_5d=benchmark_return_5d,
            benchmark_return_21d=benchmark_return_21d,
            benchmark_return_63d=benchmark_return_63d,
            metadata=metadata or {},
        )
        self._audit_log.record(
            self.EVENT_TYPE,
            ticker=security_id,
            factor=factor.value,
            sector=sector.value,
            as_of=as_of.isoformat(),
            factor_score=factor_score,
            forward_return_1d=forward_return_1d,
            forward_return_5d=forward_return_5d,
            forward_return_21d=forward_return_21d,
            forward_return_63d=forward_return_63d,
            benchmark_return_1d=benchmark_return_1d,
            benchmark_return_5d=benchmark_return_5d,
            benchmark_return_21d=benchmark_return_21d,
            benchmark_return_63d=benchmark_return_63d,
            **record.metadata,
        )
        return record


class ValuationAccuracyRecorder:
    """
    Records valuation accuracy observations.

    Tracks PipelineReport fair value estimates vs. realized prices,
    including confidence band and Monte Carlo percentile coverage.
    """

    EVENT_TYPE = "valuation_accuracy_observation"

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def record(
        self,
        security_id: str,
        sector: SectorType,
        valuation_date: datetime,
        realized_date: datetime,
        fair_value: float,
        realized_price: float,
        confidence_band_low: float | None = None,
        confidence_band_high: float | None = None,
        monte_carlo_percentiles: dict[int, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ValuationAccuracyRecord:
        """Record a valuation accuracy observation."""
        record = ValuationAccuracyRecord(
            security_id=security_id,
            sector=sector,
            valuation_date=valuation_date,
            realized_date=realized_date,
            fair_value=fair_value,
            realized_price=realized_price,
            confidence_band_low=confidence_band_low,
            confidence_band_high=confidence_band_high,
            monte_carlo_percentiles=monte_carlo_percentiles or {},
            metadata=metadata or {},
        )
        self._audit_log.record(
            self.EVENT_TYPE,
            ticker=security_id,
            sector=sector.value,
            valuation_date=valuation_date.isoformat(),
            realized_date=realized_date.isoformat(),
            fair_value=fair_value,
            realized_price=realized_price,
            absolute_error=record.absolute_error,
            relative_error=record.relative_error,
            within_confidence_band=record.within_confidence_band,
            within_monte_carlo_range=record.within_monte_carlo_range,
            realized_percentile=record.realized_percentile,
            confidence_band_low=confidence_band_low,
            confidence_band_high=confidence_band_high,
            monte_carlo_percentiles=monte_carlo_percentiles or {},
            **record.metadata,
        )
        return record


class SectorPerformanceRecorder:
    """
    Records aggregated sector performance metrics.

    Computes and stores factor ICs and valuation accuracy metrics
    sliced by sector over a given period.
    """

    EVENT_TYPE = "sector_performance_snapshot"

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def record(
        self,
        sector: SectorType,
        as_of: datetime,
        period_start: datetime,
        period_end: datetime,
        factor_quality_ic: float | None = None,
        factor_value_ic: float | None = None,
        factor_momentum_ic: float | None = None,
        factor_size_ic: float | None = None,
        factor_volatility_ic: float | None = None,
        mean_absolute_error: float | None = None,
        mean_relative_error: float | None = None,
        median_relative_error: float | None = None,
        hit_rate_confidence_band: float | None = None,
        hit_rate_monte_carlo: float | None = None,
        n_factor_observations: int = 0,
        n_valuation_observations: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> SectorPerformanceRecord:
        """Record a sector performance snapshot."""
        record = SectorPerformanceRecord(
            sector=sector,
            as_of=as_of,
            period_start=period_start,
            period_end=period_end,
            factor_quality_ic=factor_quality_ic,
            factor_value_ic=factor_value_ic,
            factor_momentum_ic=factor_momentum_ic,
            factor_size_ic=factor_size_ic,
            factor_volatility_ic=factor_volatility_ic,
            mean_absolute_error=mean_absolute_error,
            mean_relative_error=mean_relative_error,
            median_relative_error=median_relative_error,
            hit_rate_confidence_band=hit_rate_confidence_band,
            hit_rate_monte_carlo=hit_rate_monte_carlo,
            n_factor_observations=n_factor_observations,
            n_valuation_observations=n_valuation_observations,
            metadata=metadata or {},
        )
        self._audit_log.record(
            self.EVENT_TYPE,
            sector=sector.value,
            as_of=as_of.isoformat(),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            factor_quality_ic=factor_quality_ic,
            factor_value_ic=factor_value_ic,
            factor_momentum_ic=factor_momentum_ic,
            factor_size_ic=factor_size_ic,
            factor_volatility_ic=factor_volatility_ic,
            mean_absolute_error=mean_absolute_error,
            mean_relative_error=mean_relative_error,
            median_relative_error=median_relative_error,
            hit_rate_confidence_band=hit_rate_confidence_band,
            hit_rate_monte_carlo=hit_rate_monte_carlo,
            n_factor_observations=n_factor_observations,
            n_valuation_observations=n_valuation_observations,
            **record.metadata,
        )
        return record


class AssumptionForecastRecorder:
    """
    Records assumption forecast accuracy observations.

    Tracks forecast vs. actual for valuation assumptions
    (growth rates, margins, WACC, etc.) over time.
    """

    EVENT_TYPE = "assumption_forecast_observation"

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def record(
        self,
        security_id: str,
        sector: SectorType,
        assumption_type: AssumptionType,
        valuation_date: datetime,
        realized_date: datetime,
        forecast_value: float,
        realized_value: float,
        forecast_horizon_days: int,
        metadata: dict[str, Any] | None = None,
    ) -> AssumptionForecastRecord:
        """Record an assumption forecast accuracy observation."""
        record = AssumptionForecastRecord(
            security_id=security_id,
            sector=sector,
            assumption_type=assumption_type,
            valuation_date=valuation_date,
            realized_date=realized_date,
            forecast_value=forecast_value,
            realized_value=realized_value,
            forecast_horizon_days=forecast_horizon_days,
            metadata=metadata or {},
        )
        self._audit_log.record(
            self.EVENT_TYPE,
            ticker=security_id,
            sector=sector.value,
            assumption_type=assumption_type.value,
            valuation_date=valuation_date.isoformat(),
            realized_date=realized_date.isoformat(),
            forecast_value=forecast_value,
            realized_value=realized_value,
            absolute_error=record.absolute_error,
            relative_error=record.relative_error,
            directional_accuracy=record.directional_accuracy,
            forecast_horizon_days=forecast_horizon_days,
            **record.metadata,
        )
        return record


class MonitoringRecorder:
    """Facade bundling the four Performance Monitoring recorders onto one AuditLog."""

    def __init__(self, audit_log: AuditLog | None = None):
        audit_log = audit_log or AuditLog()
        self.factor_alpha = FactorAlphaRecorder(audit_log)
        self.valuation_accuracy = ValuationAccuracyRecorder(audit_log)
        self.sector_performance = SectorPerformanceRecorder(audit_log)
        self.assumption_forecast = AssumptionForecastRecorder(audit_log)
