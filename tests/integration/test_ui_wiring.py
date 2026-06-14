import os

import pandas as pd
import pytest

from iam.backtest.multiple_testing import compute_validation_metrics
from iam.engine.composite import DEFAULT_WEIGHTS
from iam.portfolio import Portfolio, Position


def test_portfolio_analytics_integration():
    # Create a dummy portfolio
    positions = [
        Position(
            ticker="AAPL",
            name="Apple",
            quantity=100,
            entry_price=150,
            current_price=180,
            weight=0.4,
        ),
        Position(
            ticker="MSFT",
            name="Microsoft",
            quantity=150,
            entry_price=300,
            current_price=350,
            weight=0.6,
        ),
    ]
    portfolio = Portfolio(positions=positions)

    # Verify we can compute basic metrics
    hhi = portfolio.concentration_herfindahl()
    assert 0 <= hhi <= 1.0

    # Verify factor exposures
    # Note: This requires scores for the tickers
    # dummy_scores = {"AAPL": {"quality": 0.5, "value": -0.2}, "MSFT": {"quality": 0.8, "value": 0.1}}
    # In practice, we'd use PortfolioAnalyzer
    # exposures = PortfolioAnalyzer.compute_factor_exposures(portfolio, dummy_scores)
    # assert exposures is not None


def test_backtest_results_integration():
    # Path to real backtest data
    csv_path = "data/results/ic/ic_horizon_1m.csv"
    if not os.path.exists(csv_path):
        pytest.skip("Backtest result CSV not found")

    df = pd.read_csv(csv_path)
    factor_names = list(DEFAULT_WEIGHTS.keys())

    # Verify we can compute integrity metrics
    # Note: compute_validation_metrics might fail if the CSV format doesn't match exactly
    try:
        val = compute_validation_metrics(df, factor_names)
        assert hasattr(val, "pbo")
        assert hasattr(val, "dsr")
    except Exception as e:
        pytest.fail(f"Failed to compute validation metrics: {e}")
