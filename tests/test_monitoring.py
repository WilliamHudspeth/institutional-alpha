from datetime import datetime, timedelta

import pytest

from iam import audit as audit_module
from iam.monitoring import MonitoringQueries, MonitoringRecorder
from iam.monitoring.models import (
    AssumptionForecastQueryFilter,
    AssumptionType,
    FactorAlphaQueryFilter,
    FactorType,
    SectorPerformanceQueryFilter,
    SectorType,
    ValuationAccuracyQueryFilter,
)


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Redirect the audit JSONL log to a tmp dir so tests never touch ~/.iam/."""
    monkeypatch.setattr(audit_module, "_LOG_PATH", tmp_path / "audit.jsonl")
    yield


@pytest.fixture
def recorder():
    return MonitoringRecorder()


@pytest.fixture
def queries():
    return MonitoringQueries()


# --- Factor Alpha ---------------------------------------------------------


def test_factor_alpha_record_and_list_roundtrip(recorder, queries):
    recorder.factor_alpha.record(
        factor=FactorType.QUALITY,
        security_id="AAPL",
        sector=SectorType.INFORMATION_TECHNOLOGY,
        as_of=datetime(2026, 1, 1),
        factor_score=1.5,
        forward_return_21d=0.03,
        benchmark_return_21d=0.01,
    )
    records = queries.factor_alpha._load_records()
    assert len(records) == 1
    assert records[0].security_id == "AAPL"
    assert records[0].factor == FactorType.QUALITY


def test_factor_alpha_score_out_of_range_rejected(recorder):
    with pytest.raises(ValueError):
        recorder.factor_alpha.record(
            factor=FactorType.QUALITY,
            security_id="AAPL",
            sector=SectorType.INFORMATION_TECHNOLOGY,
            as_of=datetime(2026, 1, 1),
            factor_score=11.0,
        )


def test_factor_alpha_compute_ic_positive_relationship(recorder, queries):
    for i in range(10):
        recorder.factor_alpha.record(
            factor=FactorType.MOMENTUM,
            security_id=f"T{i}",
            sector=SectorType.ENERGY,
            as_of=datetime(2026, 1, 1) + timedelta(days=i),
            factor_score=float(i),
            forward_return_21d=float(i) * 0.01,
        )
    ic = queries.factor_alpha.compute_ic(
        FactorAlphaQueryFilter(factor=FactorType.MOMENTUM), horizon="21d"
    )
    assert ic == pytest.approx(1.0)


def test_factor_alpha_compute_ic_insufficient_data_returns_none(queries):
    assert queries.factor_alpha.compute_ic(FactorAlphaQueryFilter(factor=FactorType.VALUE)) is None


def test_factor_alpha_aggregate_computes_ics_and_excess_returns(recorder, queries):
    for i in range(5):
        recorder.factor_alpha.record(
            factor=FactorType.SIZE,
            security_id=f"T{i}",
            sector=SectorType.FINANCIALS,
            as_of=datetime(2026, 1, 1) + timedelta(days=i),
            factor_score=float(i),
            forward_return_21d=0.05,
            benchmark_return_21d=0.02,
        )
    agg = queries.factor_alpha.aggregate(FactorAlphaQueryFilter(factor=FactorType.SIZE))
    assert agg.n_observations == 5
    assert agg.mean_excess_return_21d == pytest.approx(0.03)


def test_factor_alpha_aggregate_empty_returns_zero_observations(queries):
    agg = queries.factor_alpha.aggregate(FactorAlphaQueryFilter(factor=FactorType.CUSTOM))
    assert agg.n_observations == 0
    assert agg.ic_21d is None


def test_factor_alpha_detect_alpha_decay_handles_month_end_dates(recorder, queries):
    """Regression: naive `datetime.replace(month=...)` blows up on day-29/30/31 dates
    in shorter months. Anchor `as_of` on the 31st so this can't silently pass."""
    base = datetime(2026, 1, 31)
    for i in range(15):
        recorder.factor_alpha.record(
            factor=FactorType.VOLATILITY,
            security_id=f"T{i}",
            sector=SectorType.UTILITIES,
            as_of=base + timedelta(days=i * 5),
            factor_score=float(i % 5),
            forward_return_21d=0.01 * (i % 5),
        )
    windows = queries.factor_alpha.detect_alpha_decay(
        FactorType.VOLATILITY, window_months=12, step_months=3
    )
    assert isinstance(windows, list)


def test_factor_alpha_compute_ics_by_sector_covers_all_sectors(recorder, queries):
    result = queries.factor_alpha.compute_ics_by_sector(FactorAlphaQueryFilter(factor=FactorType.QUALITY))
    assert set(result.keys()) == set(SectorType)


# --- Valuation Accuracy ----------------------------------------------------


def test_valuation_accuracy_record_and_properties(recorder, queries):
    recorder.valuation_accuracy.record(
        security_id="MSFT",
        sector=SectorType.INFORMATION_TECHNOLOGY,
        valuation_date=datetime(2026, 1, 1),
        realized_date=datetime(2026, 4, 1),
        fair_value=110.0,
        realized_price=100.0,
        confidence_band_low=95.0,
        confidence_band_high=115.0,
        monte_carlo_percentiles={5: 90.0, 50: 108.0, 95: 130.0},
    )
    records = queries.valuation_accuracy.list()
    assert len(records) == 1
    r = records[0]
    assert r.absolute_error == pytest.approx(10.0)
    assert r.within_confidence_band is True
    assert r.within_monte_carlo_range is True
    # Monte Carlo percentile keys must survive the JSON string-key round trip as ints.
    assert set(r.monte_carlo_percentiles.keys()) == {5, 50, 95}


def test_valuation_accuracy_aggregate_hit_rates(recorder, queries):
    recorder.valuation_accuracy.record(
        security_id="A", sector=SectorType.HEALTH_CARE,
        valuation_date=datetime(2026, 1, 1), realized_date=datetime(2026, 2, 1),
        fair_value=100.0, realized_price=100.0,
        confidence_band_low=90.0, confidence_band_high=110.0,
    )
    recorder.valuation_accuracy.record(
        security_id="B", sector=SectorType.HEALTH_CARE,
        valuation_date=datetime(2026, 1, 1), realized_date=datetime(2026, 2, 1),
        fair_value=100.0, realized_price=200.0,
        confidence_band_low=90.0, confidence_band_high=110.0,
    )
    agg = queries.valuation_accuracy.aggregate(ValuationAccuracyQueryFilter(sector=SectorType.HEALTH_CARE))
    assert agg.n_observations == 2
    assert agg.hit_rate_confidence_band == pytest.approx(0.5)


def test_valuation_accuracy_rejects_non_positive_price():
    from iam.monitoring.models import ValuationAccuracyRecord
    with pytest.raises(ValueError):
        ValuationAccuracyRecord(
            security_id="X", valuation_date=datetime(2026, 1, 1), realized_date=datetime(2026, 2, 1),
            fair_value=0.0, realized_price=100.0,
        )


# --- Sector Performance -----------------------------------------------------


def test_sector_performance_record_and_latest(recorder, queries):
    recorder.sector_performance.record(
        sector=SectorType.ENERGY,
        as_of=datetime(2026, 1, 1),
        period_start=datetime(2025, 10, 1),
        period_end=datetime(2026, 1, 1),
        mean_absolute_error=5.0,
        n_valuation_observations=20,
    )
    recorder.sector_performance.record(
        sector=SectorType.ENERGY,
        as_of=datetime(2026, 2, 1),
        period_start=datetime(2025, 11, 1),
        period_end=datetime(2026, 2, 1),
        mean_absolute_error=3.0,
        n_valuation_observations=25,
    )
    latest = queries.sector_performance.latest(SectorType.ENERGY)
    assert latest is not None
    assert latest.mean_absolute_error == pytest.approx(3.0)


def test_sector_performance_latest_returns_none_when_absent(queries):
    assert queries.sector_performance.latest(SectorType.REAL_ESTATE) is None


def test_sector_performance_rank_sectors_ascending_by_error(recorder, queries):
    recorder.sector_performance.record(
        sector=SectorType.MATERIALS, as_of=datetime(2026, 1, 1),
        period_start=datetime(2025, 10, 1), period_end=datetime(2026, 1, 1),
        mean_absolute_error=8.0,
    )
    recorder.sector_performance.record(
        sector=SectorType.INDUSTRIALS, as_of=datetime(2026, 1, 1),
        period_start=datetime(2025, 10, 1), period_end=datetime(2026, 1, 1),
        mean_absolute_error=2.0,
    )
    ranked = queries.sector_performance.rank_sectors(metric="mean_absolute_error", ascending=True)
    sectors_in_order = [s for s, _ in ranked.ranked_sectors]
    assert sectors_in_order.index(SectorType.INDUSTRIALS) < sectors_in_order.index(SectorType.MATERIALS)


def test_sector_performance_filter_by_sector(recorder, queries):
    recorder.sector_performance.record(
        sector=SectorType.UTILITIES, as_of=datetime(2026, 1, 1),
        period_start=datetime(2025, 10, 1), period_end=datetime(2026, 1, 1),
    )
    recorder.sector_performance.record(
        sector=SectorType.ENERGY, as_of=datetime(2026, 1, 1),
        period_start=datetime(2025, 10, 1), period_end=datetime(2026, 1, 1),
    )
    results = queries.sector_performance.list(SectorPerformanceQueryFilter(sector=SectorType.UTILITIES))
    assert len(results) == 1
    assert results[0].sector == SectorType.UTILITIES


# --- Assumption Forecast -----------------------------------------------------


def test_assumption_forecast_record_and_properties(recorder, queries):
    recorder.assumption_forecast.record(
        security_id="GOOGL",
        sector=SectorType.COMMUNICATION_SERVICES,
        assumption_type=AssumptionType.REVENUE_GROWTH,
        valuation_date=datetime(2026, 1, 1),
        realized_date=datetime(2027, 1, 1),
        forecast_value=0.10,
        realized_value=0.07,
        forecast_horizon_days=365,
    )
    records = queries.assumption_forecast.list()
    assert len(records) == 1
    r = records[0]
    assert r.absolute_error == pytest.approx(0.03)
    assert r.directional_accuracy is True


def test_assumption_forecast_directional_accuracy_false_on_sign_flip(recorder, queries):
    recorder.assumption_forecast.record(
        security_id="X", sector=SectorType.UNKNOWN, assumption_type=AssumptionType.WACC,
        valuation_date=datetime(2026, 1, 1), realized_date=datetime(2026, 6, 1),
        forecast_value=0.08, realized_value=-0.02, forecast_horizon_days=150,
    )
    records = queries.assumption_forecast.list()
    assert records[0].directional_accuracy is False


def test_assumption_forecast_aggregate_by_type(recorder, queries):
    for forecast, realized in [(0.10, 0.09), (0.12, 0.10)]:
        recorder.assumption_forecast.record(
            security_id="Y", sector=SectorType.UNKNOWN, assumption_type=AssumptionType.EBITDA_MARGIN,
            valuation_date=datetime(2026, 1, 1), realized_date=datetime(2026, 6, 1),
            forecast_value=forecast, realized_value=realized, forecast_horizon_days=150,
        )
    agg = queries.assumption_forecast.aggregate(
        AssumptionForecastQueryFilter(assumption_type=AssumptionType.EBITDA_MARGIN)
    )
    assert agg.n_observations == 2
    assert agg.directional_accuracy_rate == pytest.approx(1.0)


def test_assumption_forecast_aggregate_empty(queries):
    agg = queries.assumption_forecast.aggregate(
        AssumptionForecastQueryFilter(assumption_type=AssumptionType.TAX_RATE)
    )
    assert agg.n_observations == 0
    assert agg.mean_absolute_error is None


# --- AuditLog.query itself ---------------------------------------------------


def test_audit_log_query_filters_by_event_type_and_field():
    from iam.audit import AuditLog

    AuditLog.record("factor_alpha_observation", ticker="AAPL", factor="quality_score")
    AuditLog.record("valuation_accuracy_observation", ticker="AAPL")
    results = AuditLog.query(event_type="factor_alpha_observation", ticker="AAPL")
    assert len(results) == 1
    assert results[0]["event"] == "factor_alpha_observation"


def test_audit_log_query_none_filters_are_unconstrained():
    from iam.audit import AuditLog

    AuditLog.record("factor_alpha_observation", ticker="AAPL")
    AuditLog.record("factor_alpha_observation", ticker="MSFT")
    results = AuditLog.query(event_type="factor_alpha_observation", ticker=None)
    assert len(results) == 2


def test_audit_log_query_time_range_excludes_out_of_range(monkeypatch):
    from iam.audit import AuditLog

    AuditLog.record("factor_alpha_observation", ticker="AAPL")
    future_start = datetime.now() + timedelta(days=1)
    results = AuditLog.query(event_type="factor_alpha_observation", start_time=future_start)
    assert results == []
