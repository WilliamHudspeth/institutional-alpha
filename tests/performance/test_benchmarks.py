from iam.valuation.probabilistic_growth import GrowthEstimatorEngine


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
