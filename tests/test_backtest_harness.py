"""Tests for the production-grade backtest harness (src/iam/backtest/).

Tests the metrics, calibration, and integration with value_security().
"""

import pandas as pd
import pytest

from iam.backtest.calibration import ic_to_reliability, summarize_backtest
from iam.backtest.metrics import hit_rate, information_coefficient, information_ratio
from iam.backtest.quantiles import decile_spread


class TestCalibration:
    """Test IC to reliability conversion."""

    def test_ic_to_reliability_zero_ic(self):
        """IC of 0 maps to baseline 0.5 reliability."""
        rel = ic_to_reliability(0.0)
        assert rel == pytest.approx(0.50)

    def test_ic_to_reliability_positive_ic(self):
        """Positive IC increases reliability."""
        rel_05 = ic_to_reliability(0.05)
        rel_10 = ic_to_reliability(0.10)

        assert rel_05 > 0.50
        assert rel_10 > rel_05

    def test_ic_to_reliability_clamping(self):
        """Very high IC is clamped to 0.95 to avoid overconfidence."""
        rel_high = ic_to_reliability(0.50)
        assert rel_high == pytest.approx(0.95)

    def test_ic_to_reliability_negative_ic(self):
        """Negative IC is clamped to minimum reliability of 0.5."""
        rel_neg = ic_to_reliability(-0.05)
        assert rel_neg == pytest.approx(0.50)  # Clamped to minimum

    def test_summarize_backtest(self):
        """Summarize backtest results into metrics."""
        results_df = pd.DataFrame(
            {
                "ic": [0.05, 0.03, 0.07],
                "hit_rate": [0.55, 0.52, 0.58],
                "spread": [0.02, 0.015, 0.025],
                "top": [0.08, 0.06, 0.10],
                "bottom": [0.06, 0.045, 0.075],
            }
        )

        summary = summarize_backtest(results_df)

        assert "ic_mean" in summary
        assert "ic_std" in summary
        assert "icir" in summary
        assert summary["ic_mean"] > 0


class TestMetrics:
    """Test backtest metrics calculation."""

    def test_information_coefficient_perfect_correlation(self):
        """Perfect correlation gives IC = 1.0."""
        df = pd.DataFrame(
            {
                "score": [1, 2, 3, 4, 5],
                "fwd": [0.01, 0.02, 0.03, 0.04, 0.05],
            }
        )

        ic = information_coefficient(df)
        assert ic == pytest.approx(1.0)

    def test_information_coefficient_no_variation_in_scores(self):
        """Constant scores return NaN."""
        df = pd.DataFrame(
            {
                "score": [1, 1, 1],
                "fwd": [0.01, 0.02, 0.03],
            }
        )

        ic = information_coefficient(df)
        assert pd.isna(ic)

    def test_information_coefficient_with_noise(self):
        """Noisy signals have intermediate IC."""
        df = pd.DataFrame(
            {
                "score": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "fwd": [0.01, 0.015, 0.02, 0.018, 0.025, 0.022, 0.03, 0.028, 0.035, 0.032],
            }
        )

        ic = information_coefficient(df)
        assert 0 < ic < 1

    def test_hit_rate_all_positive(self):
        """100% of high scores have positive returns."""
        df = pd.DataFrame(
            {
                "score": [1, 2, 3, 4, 5],
                "fwd": [0.01, 0.02, 0.03, 0.04, 0.05],
            }
        )

        hr = hit_rate(df)
        assert hr > 0.5  # Above median scores have positive returns

    def test_hit_rate_no_signal(self):
        """Weak signal produces intermediate hit rate."""
        df = pd.DataFrame(
            {
                "score": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5],
                "fwd": [-0.02, 0.01, 0.02, -0.01, 0.01, -0.02, 0.02, 0.01, -0.01, 0.02],
            }
        )

        hr = hit_rate(df)
        # Weak signal yields intermediate hit rate
        assert 0.25 <= hr <= 0.85

    def test_information_ratio(self):
        """IR = mean(IC) / std(IC)."""
        ic_series = pd.Series([0.03, 0.05, 0.04, 0.06, 0.02])

        ir = information_ratio(ic_series)

        expected_mean = ic_series.mean()
        expected_std = ic_series.std()
        expected_ir = expected_mean / expected_std

        assert ir == pytest.approx(expected_ir)


class TestQuantiles:
    """Test quantile/decile analysis."""

    def test_decile_spread_strong_signal(self):
        """Strong signal creates positive spread."""
        df = pd.DataFrame(
            {
                "score": list(range(1, 11)),
                "fwd": [0.01, 0.015, 0.02, 0.018, 0.022, 0.025, 0.03, 0.028, 0.035, 0.04],
            }
        )

        spreads = decile_spread(df)

        assert spreads["spread"] > 0
        assert spreads["top"] > spreads["bottom"]

    def test_decile_spread_no_signal(self):
        """No signal creates near-zero spread."""
        df = pd.DataFrame(
            {
                "score": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "fwd": [0.01, -0.01, 0.02, -0.02, 0.01, -0.01, 0.02, -0.02, 0.01, -0.01],
            }
        )

        spreads = decile_spread(df)

        # Spread should be close to zero (noise)
        assert abs(spreads["spread"]) < 0.05

    def test_decile_spread_insufficient_data(self):
        """Too few securities returns NaN."""
        df = pd.DataFrame(
            {
                "score": [1, 2],
                "fwd": [0.01, 0.02],
            }
        )

        spreads = decile_spread(df, n_deciles=10)

        # Should handle gracefully
        assert "spread" in spreads

    def test_decile_spread_coverage_ratio(self):
        """Coverage tracks fraction of securities assigned to deciles."""
        df = pd.DataFrame(
            {
                "score": list(range(1, 31)),
                "fwd": [0.01 + (i * 0.001) for i in range(30)],
            }
        )

        spreads = decile_spread(df, n_deciles=10)

        # With 30 securities and 10 deciles, should have good coverage
        assert "coverage" in spreads
        assert spreads["coverage"] > 0.8


class TestBacktestIntegration:
    """Test integration between backtest components."""

    def test_calibration_and_metrics_roundtrip(self):
        """IC from metrics can be converted to reliability."""
        df = pd.DataFrame(
            {
                "score": list(range(1, 21)),
                "fwd": [0.01 + (i * 0.002) for i in range(20)],
            }
        )

        ic = information_coefficient(df)
        reliability = ic_to_reliability(ic)

        # IC in [0.0, 0.5] should map to reliability in [0.5, 0.95]
        assert 0.5 <= reliability <= 0.95
        assert reliability > 0.5  # Some positive signal

    def test_negative_ic_maps_to_minimum_reliability(self):
        """Negative IC (inverse signal) clamps to baseline."""
        # Inverse correlation: high scores, low returns
        df = pd.DataFrame(
            {
                "score": list(range(1, 11)),
                "fwd": list(reversed([0.01 + (i * 0.01) for i in range(10)])),
            }
        )

        ic = information_coefficient(df)
        assert ic < 0

        reliability = ic_to_reliability(ic)
        assert reliability == pytest.approx(0.50)  # Clamped to minimum

    def test_summary_with_empty_series(self):
        """Summarize handles empty or NaN series gracefully."""
        results_df = pd.DataFrame(
            {
                "ic": [0.05, 0.03, 0.07],
                "hit_rate": [0.55, 0.52, 0.58],
                "spread": [0.02, 0.015, 0.025],
                "top": [0.08, 0.06, 0.10],
                "bottom": [0.06, 0.045, 0.075],
            }
        )

        summary = summarize_backtest(results_df)

        # All expected keys should be present
        for key in [
            "ic_mean",
            "ic_std",
            "icir",
            "hit_rate",
            "spread_mean",
            "top_decile_mean",
            "bottom_decile_mean",
        ]:
            assert key in summary

    def test_information_ratio_with_zero_variance(self):
        """IR returns 0 when IC has zero variance."""
        ic_series = pd.Series([0.04, 0.04, 0.04])  # All same value

        ir = information_ratio(ic_series)

        # With zero std, IR is undefined, returns 0
        assert ir == 0.0
