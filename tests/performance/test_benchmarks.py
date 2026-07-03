"""Performance benchmarks with hard SLA assertions.

Uses pytest-benchmark to time key code paths and fails the test outright if
the measured mean duration exceeds the documented SLA:

- Cache lookup (warm `DamodaranProvider.resolve_erp` lru_cache hit): < 1ms
- Full valuation pipeline run (`ValuationPipeline().run()`): < 10s

Run with: pytest tests/performance/ -v
"""

from __future__ import annotations

from iam.data.damodaran import DamodaranProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline import ValuationPipeline
from iam.valuation.probabilistic_growth import GrowthEstimatorEngine

CACHE_LOOKUP_SLA_SECONDS = 0.001
PIPELINE_RUN_SLA_SECONDS = 10.0


def test_monte_carlo_runtime(benchmark):
    # Benchmark the probabilistic growth engine
    def run_engine():
        engine = GrowthEstimatorEngine(
            market_cap=2000000,
            free_cash_flow=100000,
            shares_outstanding=15000,
            net_debt=50000,
            wacc=0.09,
            growth_3y=0.15,
            growth_5y=0.12,
            growth_10y=0.10,
            roic=0.20,
            reinvestment_rate=0.4,
        )
        return engine.blended_growth()

    result = benchmark(run_engine)
    assert result.mean_growth is not None


def test_cache_lookup_sla(benchmark):
    """A warm cache lookup must resolve in under 1ms.

    `DamodaranProvider.resolve_erp` is `@lru_cache`-backed; the first call
    populates the cache, and every call thereafter is a pure in-memory
    dict lookup, which is the cache-hit path this SLA protects.
    """
    DamodaranProvider.resolve_erp("US")  # warm the cache

    result = benchmark(DamodaranProvider.resolve_erp, "US")

    assert result == DamodaranProvider.resolve_erp("US")
    assert benchmark.stats.stats.mean < CACHE_LOOKUP_SLA_SECONDS, (
        f"Cache lookup mean {benchmark.stats.stats.mean * 1000:.4f}ms "
        f"exceeds {CACHE_LOOKUP_SLA_SECONDS * 1000:.1f}ms SLA"
    )


def _build_pipeline_security() -> Security:
    return Security(
        ticker="BENCH",
        fundamentals=Fundamentals(
            fcf_ttm=2800,
            shares_outstanding=1000,
            net_income_ttm=3500,
            revenue_history=[10000, 8500, 7200, 6100, 5200],
            roic_history=[0.18, 0.17, 0.16],
            operating_margin_history=[0.30, 0.25, 0.22, 0.20],
        ),
        market=MarketData(
            price=180,
            pe_ttm=75,
            ev_ebitda=50,
            pe_history=[60, 55, 50, 70, 80, 65, 55, 45, 40, 35],
            sector_ev_ebitda_median=22,
            fcf_yield=0.016,
            peer_fcf_yields=[0.03, 0.025, 0.04],
        ),
        qualitative={"forecast_growth": 0.18, "forecast_discount_rate": 0.10},
    )


def test_full_pipeline_run_sla(benchmark):
    """A full ValuationPipeline.run() must complete in under 10 seconds."""
    sec = _build_pipeline_security()

    report = benchmark(ValuationPipeline().run, sec)

    assert report.triangulation is not None
    assert benchmark.stats.stats.mean < PIPELINE_RUN_SLA_SECONDS, (
        f"Pipeline run mean {benchmark.stats.stats.mean:.3f}s "
        f"exceeds {PIPELINE_RUN_SLA_SECONDS:.1f}s SLA"
    )
