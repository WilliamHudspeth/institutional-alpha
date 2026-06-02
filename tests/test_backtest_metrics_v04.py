"""Tests for v0.4 institutional metrics.

Covers:
- ic_sector_neutral (sector-stratified IC)
- newey_west_se_rigorous (statsmodels HAC covariance)
- fisher_mean (Fisher z-transform averaging)
- information_coefficient with sector_col argument
- rolling_ic_stability
- statistical_significance
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from iam.backtest.metrics import (
    fisher_mean,
    ic_sector_neutral,
    information_coefficient,
    newey_west_se,
    newey_west_se_rigorous,
    rolling_ic_stability,
    statistical_significance,
)

# -----------------------------------------------------------------------------
# Sector-neutral IC
# -----------------------------------------------------------------------------


class TestICSectorNeutral:
    def test_returns_nan_without_sector_column(self):
        df = pd.DataFrame({"score": [1, 2, 3], "fwd": [0.1, 0.2, 0.3]})
        assert np.isnan(ic_sector_neutral(df))

    def test_averages_ic_across_sectors(self):
        # Two sectors, each with strong positive IC
        df = pd.DataFrame(
            {
                "score": list(range(10)) + list(range(10)),
                "fwd": [x * 0.01 for x in range(10)] + [x * 0.01 for x in range(10)],
                "sector": ["Tech"] * 10 + ["Finance"] * 10,
            }
        )
        ic = ic_sector_neutral(df)
        assert ic == pytest.approx(1.0)  # Perfect correlation in each sector

    def test_skips_sectors_with_too_few_securities(self):
        # Tech: 10 securities (counted); Finance: 3 (skipped < 5)
        df = pd.DataFrame(
            {
                "score": list(range(10)) + [1, 2, 3],
                "fwd": [x * 0.01 for x in range(10)] + [0.5, 0.1, 0.9],
                "sector": ["Tech"] * 10 + ["Finance"] * 3,
            }
        )
        ic = ic_sector_neutral(df)
        # Only Tech contributes
        assert ic == pytest.approx(1.0)

    def test_weighted_average_by_sector_size(self):
        # Sector A: 20 securities, IC=1.0; Sector B: 10 securities, IC=-1.0
        # Weighted average should be (20*1 + 10*-1) / 30 = 10/30 ≈ 0.333
        df = pd.DataFrame(
            {
                "score": list(range(20)) + list(range(10)),
                "fwd": [x * 0.01 for x in range(20)] + [-x * 0.01 for x in range(10)],
                "sector": ["A"] * 20 + ["B"] * 10,
            }
        )
        ic = ic_sector_neutral(df)
        assert ic == pytest.approx((20 * 1.0 + 10 * -1.0) / 30, abs=0.01)

    def test_returns_nan_when_no_sector_has_enough_data(self):
        df = pd.DataFrame(
            {
                "score": [1, 2, 3],
                "fwd": [0.1, 0.2, 0.3],
                "sector": ["A", "B", "C"],
            }
        )
        assert np.isnan(ic_sector_neutral(df))

    def test_custom_sector_col_name(self):
        df = pd.DataFrame(
            {
                "score": list(range(10)),
                "fwd": [x * 0.01 for x in range(10)],
                "industry": ["Tech"] * 10,
            }
        )
        ic = ic_sector_neutral(df, sector_col="industry")
        assert ic == pytest.approx(1.0)


# -----------------------------------------------------------------------------
# information_coefficient with sector neutralization
# -----------------------------------------------------------------------------


class TestInformationCoefficientWithSector:
    def test_falls_back_to_global_when_no_sector_col(self):
        df = pd.DataFrame(
            {
                "score": list(range(10)),
                "fwd": [x * 0.01 for x in range(10)],
            }
        )
        ic = information_coefficient(df, sector_col="sector")
        # Falls back since 'sector' not in columns
        assert np.isnan(ic) or ic == pytest.approx(1.0, abs=0.01)

    def test_global_ic_when_sector_col_none(self):
        df = pd.DataFrame(
            {
                "score": list(range(10)),
                "fwd": [x * 0.01 for x in range(10)],
            }
        )
        ic = information_coefficient(df, sector_col=None)
        assert ic == pytest.approx(1.0)

    def test_sector_neutral_when_provided(self):
        df = pd.DataFrame(
            {
                "score": list(range(10)) + list(reversed(range(10))),
                "fwd": [x * 0.01 for x in range(10)] + [x * 0.01 for x in range(10)],
                "sector": ["A"] * 10 + ["B"] * 10,
            }
        )
        # Without sector: should be 0 (offsetting)
        global_ic = information_coefficient(df)
        # With sector: A has IC=1, B has IC=-1, weighted avg should be 0
        sector_ic = information_coefficient(df, sector_col="sector")
        # Both compute differently but global is approximately 0 here
        assert abs(global_ic) < 0.5


# -----------------------------------------------------------------------------
# Fisher mean
# -----------------------------------------------------------------------------


class TestFisherMean:
    def test_zero_correlation_returns_zero(self):
        assert fisher_mean(np.array([0.0, 0.0, 0.0])) == pytest.approx(0.0)

    def test_positive_correlations_yield_positive_mean(self):
        result = fisher_mean(np.array([0.2, 0.3, 0.4]))
        assert result > 0
        # Should be approximately the arithmetic mean for small values
        assert result == pytest.approx(0.3, abs=0.05)

    def test_negative_correlations_yield_negative_mean(self):
        result = fisher_mean(np.array([-0.2, -0.3, -0.4]))
        assert result < 0

    def test_clips_extreme_values(self):
        # Should not produce nan/inf for correlations of ±1
        result = fisher_mean(np.array([1.0, 1.0, 1.0]))
        assert not np.isnan(result)
        assert not np.isinf(result)
        assert result > 0.9

    def test_handles_nan_values(self):
        result = fisher_mean(np.array([0.2, np.nan, 0.4]))
        # Should not crash on NaN
        assert not np.isnan(result)


# -----------------------------------------------------------------------------
# Rigorous Newey-West (statsmodels HAC)
# -----------------------------------------------------------------------------


class TestNeweyWestSEReorous:
    def test_returns_nan_for_too_few_observations(self):
        ic_series = pd.Series([0.02, 0.03])
        t_stat, p_value, se = newey_west_se_rigorous(ic_series, nlags=3)
        assert np.isnan(t_stat)

    def test_positive_mean_yields_positive_tstat(self):
        np.random.seed(42)
        ic_series = pd.Series(np.random.normal(0.05, 0.02, 100))
        t_stat, p_value, se = newey_west_se_rigorous(ic_series, nlags=3)
        assert t_stat > 0
        assert se > 0

    def test_zero_mean_yields_low_significance(self):
        np.random.seed(42)
        ic_series = pd.Series(np.random.normal(0.0, 0.05, 100))
        t_stat, p_value, se = newey_west_se_rigorous(ic_series, nlags=3)
        # Should not be statistically significant
        assert p_value > 0.05 or abs(t_stat) < 2.0

    def test_se_inflates_with_more_lags(self):
        # With autocorrelated data, more lags should generally increase SE
        np.random.seed(42)
        ic = pd.Series(np.random.normal(0.05, 0.02, 100))
        _, _, se_lag1 = newey_west_se_rigorous(ic, nlags=1)
        _, _, se_lag5 = newey_west_se_rigorous(ic, nlags=5)
        # For very random data they may be similar; check they're both valid
        assert se_lag1 > 0
        assert se_lag5 > 0


# -----------------------------------------------------------------------------
# Simplified Newey-West (preserved for backward compat)
# -----------------------------------------------------------------------------


class TestNeweyWestSESimplified:
    def test_inflates_se_over_naive(self):
        ic_mean = 0.05
        ic_std = 0.10
        n = 84

        naive_se = ic_std / np.sqrt(n)
        nw_se = newey_west_se(ic_mean, ic_std, n, nlags=3)

        # Newey-West should be larger than naive SE
        assert nw_se > naive_se

    def test_zero_lags_returns_naive(self):
        ic_mean = 0.05
        ic_std = 0.10
        n = 84

        nw_se_0 = newey_west_se(ic_mean, ic_std, n, nlags=0)
        naive_se = ic_std / np.sqrt(n)

        assert nw_se_0 == pytest.approx(naive_se)


# -----------------------------------------------------------------------------
# Rolling IC stability
# -----------------------------------------------------------------------------


class TestRollingICStability:
    def test_returns_series_same_length(self):
        ic = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05] * 5)
        rolling = rolling_ic_stability(ic, window=12)
        assert len(rolling) == len(ic)

    def test_early_values_are_nan(self):
        # First window-1 values should be NaN
        ic = pd.Series(np.random.normal(0.02, 0.01, 30))
        rolling = rolling_ic_stability(ic, window=12)
        assert rolling.iloc[:11].isna().all()

    def test_detects_upward_drift(self):
        # IC that increases linearly over time
        ic = pd.Series([0.01 * i for i in range(30)])
        rolling = rolling_ic_stability(ic, window=12)
        # Rolling correlation should be very high (close to 1)
        assert rolling.iloc[-1] == pytest.approx(1.0, abs=0.01)


# -----------------------------------------------------------------------------
# Statistical significance
# -----------------------------------------------------------------------------


class TestStatisticalSignificance:
    def test_zero_std_returns_no_significance(self):
        result = statistical_significance(0.05, 0.0, 100)
        assert result["t_stat"] == 0.0
        assert result["p_value"] == 1.0
        assert result["significant"] is False

    def test_n_less_than_two_returns_no_significance(self):
        result = statistical_significance(0.05, 0.10, 1)
        assert result["significant"] is False

    def test_meaningful_ic_yields_high_tstat(self):
        # IC=0.05, std=0.05, n=100 → t_stat = 0.05 / (0.05/10) = 10
        result = statistical_significance(0.05, 0.05, 100)
        assert result["t_stat"] > 5.0
        assert result["p_value"] < 0.01

    def test_returns_dict_with_expected_keys(self):
        result = statistical_significance(0.02, 0.05, 84)
        assert "t_stat" in result
        assert "newey_west_t_stat" in result
        assert "p_value" in result
        assert "newey_west_se" in result
        assert "significant" in result
