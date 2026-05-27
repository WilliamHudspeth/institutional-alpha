"""Tests for the historical backtest harness."""

import pytest

# Skip all tests in this module if pandas is not installed
pd = pytest.importorskip("pandas")

from iam.data.security import Security
from tests.harness import BacktestHarness


def test_backtest_harness_run():
    data = [
        (Security(ticker="A"), 0.05),
        (Security(ticker="B"), -0.02),
        (Security(ticker="C"), 0.10)
    ]
    harness = BacktestHarness(data)
    df = harness.run()
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert "ticker" in df.columns
    assert "forward_return" in df.columns
    assert "composite" in df.columns


def test_backtest_harness_ic():
    data = [(Security(ticker=f"S{i}"), float(i)) for i in range(10)]
    harness = BacktestHarness(data)
    ics = harness.calculate_ic()
    
    assert isinstance(ics, pd.Series)
    assert "composite" in ics.index


def test_backtest_quantile_spread():
    data = [(Security(ticker=f"T{i}"), float(i)) for i in range(10)]
    harness = BacktestHarness(data)
    
    # We use the forward_return column itself to test the spread math
    # 0-9 values. Top half (5-9) mean = 7. Bottom half (0-4) mean = 2. Spread = 5.0
    spread = harness.quantile_spread(factor="forward_return", q=2) 
    assert spread == pytest.approx(5.0)