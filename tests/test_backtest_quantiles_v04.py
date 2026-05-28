"""Tests for v0.4 quantile additions: turnover and cost-adjusted spread."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from iam.backtest.quantiles import (
    decile_spread,
    quantile_turnover,
    spread_after_costs,
)

# -----------------------------------------------------------------------------
# spread_after_costs
# -----------------------------------------------------------------------------


class TestSpreadAfterCosts:
    def test_zero_turnover_preserves_spread(self):
        result = spread_after_costs(spread=0.01, turnover=0.0, cost_bps=5.0)
        assert result == pytest.approx(0.01)

    def test_full_turnover_subtracts_cost(self):
        # 100% turnover, 5 bps round trip → 0.001 cost
        # spread = 0.01, cost = 1.0 * 5/10000 * 2 = 0.001
        result = spread_after_costs(spread=0.01, turnover=1.0, cost_bps=5.0)
        assert result == pytest.approx(0.01 - 0.001)

    def test_zero_cost_preserves_spread(self):
        result = spread_after_costs(spread=0.01, turnover=0.5, cost_bps=0.0)
        assert result == pytest.approx(0.01)

    def test_nan_spread_returns_nan(self):
        result = spread_after_costs(spread=np.nan, turnover=0.5, cost_bps=5.0)
        assert np.isnan(result)

    def test_nan_turnover_returns_nan(self):
        result = spread_after_costs(spread=0.01, turnover=np.nan, cost_bps=5.0)
        assert np.isnan(result)

    def test_higher_cost_reduces_spread_more(self):
        low_cost = spread_after_costs(0.01, turnover=0.5, cost_bps=5.0)
        high_cost = spread_after_costs(0.01, turnover=0.5, cost_bps=20.0)
        assert high_cost < low_cost

    def test_can_produce_negative_spread(self):
        # Very high turnover/cost can flip the spread negative
        result = spread_after_costs(spread=0.001, turnover=1.0, cost_bps=20.0)
        assert result < 0


# -----------------------------------------------------------------------------
# quantile_turnover
# -----------------------------------------------------------------------------


class TestQuantileTurnover:
    def test_identical_scores_yield_zero_turnover(self):
        df1 = pd.DataFrame({"score": list(range(20))}, index=[f"T{i}" for i in range(20)])
        df1.index.name = "ticker"
        df2 = df1.copy()

        turnover = quantile_turnover(df1, df2, n_deciles=10)
        # All deciles same → 0% turnover
        assert turnover == pytest.approx(0.0, abs=0.01)

    def test_reversed_scores_yield_high_turnover(self):
        df1 = pd.DataFrame({"score": list(range(20))}, index=[f"T{i}" for i in range(20)])
        df1.index.name = "ticker"
        df2 = pd.DataFrame({"score": list(reversed(range(20)))}, index=[f"T{i}" for i in range(20)])
        df2.index.name = "ticker"

        turnover = quantile_turnover(df1, df2, n_deciles=10)
        # Most securities flip deciles
        assert turnover > 0.7

    def test_no_common_tickers_returns_nan(self):
        df1 = pd.DataFrame({"score": [1, 2, 3]}, index=["A", "B", "C"])
        df1.index.name = "ticker"
        df2 = pd.DataFrame({"score": [1, 2, 3]}, index=["X", "Y", "Z"])
        df2.index.name = "ticker"

        turnover = quantile_turnover(df1, df2, n_deciles=3)
        assert np.isnan(turnover)


# -----------------------------------------------------------------------------
# Integration: decile_spread + spread_after_costs
# -----------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline(self):
        np.random.seed(42)
        n = 100
        score = np.random.normal(0, 1, n)
        # Strong signal
        fwd = score * 0.1 + np.random.normal(0, 0.02, n)
        df = pd.DataFrame({"score": score, "fwd": fwd})

        result = decile_spread(df)
        adjusted = spread_after_costs(result["spread"], turnover=0.5, cost_bps=5.0)

        # Adjusted spread should be lower but still positive (strong signal)
        assert adjusted < result["spread"]
        assert adjusted > 0
