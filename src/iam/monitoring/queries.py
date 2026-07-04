"""
Query and aggregation layer for Performance Monitoring.

Provides query classes for each of the four monitoring capabilities
with time-windowed aggregations, decay detection, sector slicing,
and forecast error statistics.
"""

from datetime import datetime

import numpy as np
import pandas as pd

from iam.audit import AuditLog
from iam.monitoring.models import (
    AssumptionForecastAggregate,
    AssumptionForecastQueryFilter,
    AssumptionForecastRecord,
    AssumptionType,
    FactorAlphaAggregate,
    FactorAlphaQueryFilter,
    FactorAlphaRecord,
    FactorType,
    SectorPerformanceAggregate,
    SectorPerformanceQueryFilter,
    SectorPerformanceRecord,
    SectorType,
    ValuationAccuracyAggregate,
    ValuationAccuracyQueryFilter,
    ValuationAccuracyRecord,
)

_FACTOR_ALPHA_CORE_FIELDS = {
    "factor", "ticker", "sector", "as_of", "factor_score",
    "forward_return_1d", "forward_return_5d", "forward_return_21d", "forward_return_63d",
    "benchmark_return_1d", "benchmark_return_5d", "benchmark_return_21d", "benchmark_return_63d",
}
_VALUATION_ACCURACY_CORE_FIELDS = {
    "ticker", "sector", "valuation_date", "realized_date", "fair_value", "realized_price",
    "absolute_error", "relative_error", "within_confidence_band", "within_monte_carlo_range",
    "realized_percentile", "confidence_band_low", "confidence_band_high", "monte_carlo_percentiles",
}
_SECTOR_PERFORMANCE_CORE_FIELDS = {
    "sector", "as_of", "period_start", "period_end",
    "factor_quality_ic", "factor_value_ic", "factor_momentum_ic", "factor_size_ic",
    "factor_volatility_ic", "mean_absolute_error", "mean_relative_error", "median_relative_error",
    "hit_rate_confidence_band", "hit_rate_monte_carlo", "n_factor_observations", "n_valuation_observations",
}
_ASSUMPTION_FORECAST_CORE_FIELDS = {
    "ticker", "sector", "assumption_type", "valuation_date", "realized_date",
    "forecast_value", "realized_value", "absolute_error", "relative_error",
    "directional_accuracy", "forecast_horizon_days",
}


def _extra_metadata(event: dict, core_fields: set[str]) -> dict:
    return {k: v for k, v in event.items() if k not in core_fields and k not in {"id", "ts", "event", "user"}}


def _safe_mean(vals: list) -> float | None:
    clean = [v for v in vals if v is not None]
    return float(np.mean(clean)) if clean else None


def _safe_median(vals: list) -> float | None:
    clean = [v for v in vals if v is not None]
    return float(np.median(clean)) if clean else None


class FactorAlphaQuery:
    """
    Query and aggregation for factor alpha records.

    Provides time-windowed IC calculations, alpha decay detection,
    and sector-sliced factor performance.
    """

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def _load_records(self, filter_: FactorAlphaQueryFilter | None = None) -> list[FactorAlphaRecord]:
        """Load factor alpha records from audit log."""
        events = self._audit_log.query(
            event_type="factor_alpha_observation",
            start_time=filter_.start_time if filter_ else None,
            end_time=filter_.end_time if filter_ else None,
            ticker=filter_.security_id if filter_ else None,
            factor=filter_.factor.value if filter_ and filter_.factor else None,
            sector=filter_.sector.value if filter_ and filter_.sector else None,
        )
        records = []
        for event in events:
            records.append(FactorAlphaRecord(
                factor=FactorType(event["factor"]),
                security_id=event["ticker"],
                sector=SectorType(event["sector"]),
                as_of=datetime.fromisoformat(event["as_of"]),
                factor_score=event["factor_score"],
                forward_return_1d=event.get("forward_return_1d"),
                forward_return_5d=event.get("forward_return_5d"),
                forward_return_21d=event.get("forward_return_21d"),
                forward_return_63d=event.get("forward_return_63d"),
                benchmark_return_1d=event.get("benchmark_return_1d"),
                benchmark_return_5d=event.get("benchmark_return_5d"),
                benchmark_return_21d=event.get("benchmark_return_21d"),
                benchmark_return_63d=event.get("benchmark_return_63d"),
                metadata=_extra_metadata(event, _FACTOR_ALPHA_CORE_FIELDS),
            ))
        return records

    def compute_ic(
        self,
        filter_: FactorAlphaQueryFilter | None = None,
        horizon: str = "21d",
    ) -> float | None:
        """
        Compute Information Coefficient (Spearman rank correlation)
        between factor scores and forward returns.
        """
        records = self._load_records(filter_)
        if len(records) < 2:
            return None

        forward_col = f"forward_return_{horizon}"
        factor_scores = [r.factor_score for r in records]
        forward_returns = [getattr(r, forward_col) for r in records]

        valid_pairs = [(f, ret) for f, ret in zip(factor_scores, forward_returns, strict=False) if ret is not None]
        if len(valid_pairs) < 2:
            return None

        factor_vals, return_vals = zip(*valid_pairs, strict=False)
        if len(set(factor_vals)) < 2 or len(set(return_vals)) < 2:
            # Correlation is undefined with zero variance on either side;
            # np.corrcoef would silently return NaN.
            return None
        return float(np.corrcoef(
            pd.Series(factor_vals).rank(),
            pd.Series(return_vals).rank(),
        )[0, 1])

    def compute_ics_by_sector(
        self,
        filter_: FactorAlphaQueryFilter | None = None,
        horizon: str = "21d",
    ) -> dict[SectorType, float | None]:
        """Compute IC for each sector."""
        if filter_ and filter_.sector:
            return {filter_.sector: self.compute_ic(filter_, horizon)}

        result = {}
        for sector in SectorType:
            sector_filter = FactorAlphaQueryFilter(
                sector=sector,
                start_time=filter_.start_time if filter_ else None,
                end_time=filter_.end_time if filter_ else None,
                factor=filter_.factor if filter_ else None,
            )
            result[sector] = self.compute_ic(sector_filter, horizon)
        return result

    def detect_alpha_decay(
        self,
        factor: FactorType,
        window_months: int = 12,
        step_months: int = 3,
        horizon: str = "21d",
    ) -> list[tuple[datetime, datetime, float | None]]:
        """
        Detect alpha decay by computing rolling IC over time windows.

        Returns list of (window_start, window_end, ic) tuples.
        """
        end_time = datetime.now()
        start_time = (pd.Timestamp(end_time) - pd.DateOffset(months=window_months)).to_pydatetime()

        filter_ = FactorAlphaQueryFilter(factor=factor, start_time=start_time, end_time=end_time)
        records = self._load_records(filter_)
        if len(records) < 10:
            return []

        df = pd.DataFrame([{
            "as_of": r.as_of,
            "factor_score": r.factor_score,
            "forward_return": getattr(r, f"forward_return_{horizon}"),
        } for r in records if getattr(r, f"forward_return_{horizon}") is not None])

        if df.empty:
            return []

        df = df.sort_values("as_of")
        results = []

        current_start = start_time
        while current_start < end_time:
            current_end = min(
                (pd.Timestamp(current_start) + pd.DateOffset(months=step_months)).to_pydatetime(),
                end_time,
            )
            window_df = df[(df["as_of"] >= current_start) & (df["as_of"] < current_end)]
            if len(window_df) >= 2 and window_df["factor_score"].nunique() > 1 and window_df["forward_return"].nunique() > 1:
                ic = float(np.corrcoef(
                    window_df["factor_score"].rank(),
                    window_df["forward_return"].rank(),
                )[0, 1])
            else:
                ic = None
            results.append((current_start, current_end, ic))
            current_start = current_end

        return results

    def aggregate(
        self,
        filter_: FactorAlphaQueryFilter | None = None,
    ) -> FactorAlphaAggregate:
        """Aggregate factor alpha statistics."""
        records = self._load_records(filter_)
        if not records:
            return FactorAlphaAggregate(
                factor=filter_.factor if filter_ else FactorType.QUALITY,
                n_observations=0,
            )

        factor = filter_.factor if filter_ else records[0].factor

        def excess_return(record: FactorAlphaRecord, horizon: str) -> float | None:
            fwd = getattr(record, f"forward_return_{horizon}")
            bench = getattr(record, f"benchmark_return_{horizon}")
            if fwd is not None and bench is not None:
                return fwd - bench
            return None

        return FactorAlphaAggregate(
            factor=factor,
            n_observations=len(records),
            ic_1d=self.compute_ic(filter_, "1d"),
            ic_5d=self.compute_ic(filter_, "5d"),
            ic_21d=self.compute_ic(filter_, "21d"),
            ic_63d=self.compute_ic(filter_, "63d"),
            mean_excess_return_1d=_safe_mean([excess_return(r, "1d") for r in records]),
            mean_excess_return_5d=_safe_mean([excess_return(r, "5d") for r in records]),
            mean_excess_return_21d=_safe_mean([excess_return(r, "21d") for r in records]),
            mean_excess_return_63d=_safe_mean([excess_return(r, "63d") for r in records]),
            median_excess_return_21d=_safe_median([excess_return(r, "21d") for r in records]),
        )


class ValuationAccuracyQuery:
    """
    Query and aggregation for valuation accuracy records.

    Tracks PipelineReport fair value estimates vs. realized prices.
    """

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def _load_records(
        self, filter_: ValuationAccuracyQueryFilter | None = None
    ) -> list[ValuationAccuracyRecord]:
        events = self._audit_log.query(
            event_type="valuation_accuracy_observation",
            start_time=filter_.start_time if filter_ else None,
            end_time=filter_.end_time if filter_ else None,
            ticker=filter_.security_id if filter_ else None,
            sector=filter_.sector.value if filter_ and filter_.sector else None,
        )
        records = []
        for event in events:
            records.append(ValuationAccuracyRecord(
                security_id=event["ticker"],
                sector=SectorType(event["sector"]),
                valuation_date=datetime.fromisoformat(event["valuation_date"]),
                realized_date=datetime.fromisoformat(event["realized_date"]),
                fair_value=event["fair_value"],
                realized_price=event["realized_price"],
                confidence_band_low=event.get("confidence_band_low"),
                confidence_band_high=event.get("confidence_band_high"),
                monte_carlo_percentiles={
                    int(k): v for k, v in (event.get("monte_carlo_percentiles") or {}).items()
                },
                metadata=_extra_metadata(event, _VALUATION_ACCURACY_CORE_FIELDS),
            ))
        return records

    def list(self, filter_: ValuationAccuracyQueryFilter | None = None) -> list[ValuationAccuracyRecord]:
        return self._load_records(filter_)

    def aggregate(
        self, filter_: ValuationAccuracyQueryFilter | None = None
    ) -> ValuationAccuracyAggregate:
        records = self._load_records(filter_)
        if not records:
            return ValuationAccuracyAggregate(
                sector=filter_.sector if filter_ else None,
                n_observations=0,
            )

        band_hits = [r.within_confidence_band for r in records if r.within_confidence_band is not None]
        mc_hits = [r.within_monte_carlo_range for r in records if r.within_monte_carlo_range is not None]

        return ValuationAccuracyAggregate(
            sector=filter_.sector if filter_ else None,
            n_observations=len(records),
            mean_absolute_error=_safe_mean([r.absolute_error for r in records]),
            mean_relative_error=_safe_mean([r.relative_error for r in records]),
            median_relative_error=_safe_median([r.relative_error for r in records]),
            hit_rate_confidence_band=_safe_mean(band_hits) if band_hits else None,
            hit_rate_monte_carlo=_safe_mean(mc_hits) if mc_hits else None,
        )


class SectorPerformanceQuery:
    """
    Query for aggregated sector performance snapshots.

    Reads back SectorPerformanceRecorder snapshots and ranks sectors by a
    chosen metric (e.g. lowest mean_absolute_error, highest factor IC).
    """

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def _load_records(
        self, filter_: SectorPerformanceQueryFilter | None = None
    ) -> list[SectorPerformanceRecord]:
        events = self._audit_log.query(
            event_type="sector_performance_snapshot",
            start_time=filter_.start_time if filter_ else None,
            end_time=filter_.end_time if filter_ else None,
            sector=filter_.sector.value if filter_ and filter_.sector else None,
        )
        records = []
        for event in events:
            records.append(SectorPerformanceRecord(
                sector=SectorType(event["sector"]),
                as_of=datetime.fromisoformat(event["as_of"]),
                period_start=datetime.fromisoformat(event["period_start"]),
                period_end=datetime.fromisoformat(event["period_end"]),
                factor_quality_ic=event.get("factor_quality_ic"),
                factor_value_ic=event.get("factor_value_ic"),
                factor_momentum_ic=event.get("factor_momentum_ic"),
                factor_size_ic=event.get("factor_size_ic"),
                factor_volatility_ic=event.get("factor_volatility_ic"),
                mean_absolute_error=event.get("mean_absolute_error"),
                mean_relative_error=event.get("mean_relative_error"),
                median_relative_error=event.get("median_relative_error"),
                hit_rate_confidence_band=event.get("hit_rate_confidence_band"),
                hit_rate_monte_carlo=event.get("hit_rate_monte_carlo"),
                n_factor_observations=event.get("n_factor_observations", 0),
                n_valuation_observations=event.get("n_valuation_observations", 0),
                metadata=_extra_metadata(event, _SECTOR_PERFORMANCE_CORE_FIELDS),
            ))
        return records

    def list(self, filter_: SectorPerformanceQueryFilter | None = None) -> list[SectorPerformanceRecord]:
        return self._load_records(filter_)

    def latest(self, sector: SectorType) -> SectorPerformanceRecord | None:
        """Most recent snapshot for a sector, or None if never recorded."""
        records = self._load_records(SectorPerformanceQueryFilter(sector=sector))
        if not records:
            return None
        return max(records, key=lambda r: r.as_of)

    def rank_sectors(
        self, metric: str = "mean_absolute_error", ascending: bool = True
    ) -> SectorPerformanceAggregate:
        """
        Rank sectors by their latest snapshot's value for `metric`.

        `ascending=True` puts the lowest value first (appropriate for error
        metrics); pass `ascending=False` for metrics like IC where higher is better.
        """
        pairs = []
        for sector in SectorType:
            record = self.latest(sector)
            if record is None:
                continue
            value = getattr(record, metric, None)
            if value is not None:
                pairs.append((sector, value))
        pairs.sort(key=lambda p: p[1], reverse=not ascending)
        return SectorPerformanceAggregate(metric=metric, ascending=ascending, ranked_sectors=pairs)


class AssumptionForecastQuery:
    """
    Query and aggregation for assumption forecast accuracy records.

    Tracks forecast vs. actual for valuation assumptions over time.
    """

    def __init__(self, audit_log: AuditLog | None = None):
        self._audit_log = audit_log or AuditLog()

    def _load_records(
        self, filter_: AssumptionForecastQueryFilter | None = None
    ) -> list[AssumptionForecastRecord]:
        events = self._audit_log.query(
            event_type="assumption_forecast_observation",
            start_time=filter_.start_time if filter_ else None,
            end_time=filter_.end_time if filter_ else None,
            ticker=filter_.security_id if filter_ else None,
            sector=filter_.sector.value if filter_ and filter_.sector else None,
            assumption_type=filter_.assumption_type.value if filter_ and filter_.assumption_type else None,
        )
        records = []
        for event in events:
            records.append(AssumptionForecastRecord(
                security_id=event["ticker"],
                sector=SectorType(event["sector"]),
                assumption_type=AssumptionType(event["assumption_type"]),
                valuation_date=datetime.fromisoformat(event["valuation_date"]),
                realized_date=datetime.fromisoformat(event["realized_date"]),
                forecast_value=event["forecast_value"],
                realized_value=event["realized_value"],
                forecast_horizon_days=event["forecast_horizon_days"],
                metadata=_extra_metadata(event, _ASSUMPTION_FORECAST_CORE_FIELDS),
            ))
        return records

    def list(self, filter_: AssumptionForecastQueryFilter | None = None) -> list[AssumptionForecastRecord]:
        return self._load_records(filter_)

    def aggregate(
        self, filter_: AssumptionForecastQueryFilter | None = None
    ) -> AssumptionForecastAggregate:
        records = self._load_records(filter_)
        if not records:
            return AssumptionForecastAggregate(
                assumption_type=filter_.assumption_type if filter_ else None,
                n_observations=0,
            )

        rel_errors = [r.relative_error for r in records if r.realized_value != 0]

        return AssumptionForecastAggregate(
            assumption_type=filter_.assumption_type if filter_ else None,
            n_observations=len(records),
            mean_absolute_error=_safe_mean([r.absolute_error for r in records]),
            mean_relative_error=_safe_mean(rel_errors),
            median_relative_error=_safe_median(rel_errors),
            directional_accuracy_rate=_safe_mean([r.directional_accuracy for r in records]),
        )


class MonitoringQueries:
    """Facade bundling the four Performance Monitoring query surfaces onto one AuditLog."""

    def __init__(self, audit_log: AuditLog | None = None):
        audit_log = audit_log or AuditLog()
        self.factor_alpha = FactorAlphaQuery(audit_log)
        self.valuation_accuracy = ValuationAccuracyQuery(audit_log)
        self.sector_performance = SectorPerformanceQuery(audit_log)
        self.assumption_forecast = AssumptionForecastQuery(audit_log)
