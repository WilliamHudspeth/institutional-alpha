"""Tests for per-factor performance tracking and stability analysis."""

import numpy as np
import pandas as pd
import pytest

from iam.backtest.factor_performance import (
    FactorMetrics,
    compute_factor_correlations,
    compute_factor_ic,
    decompose_backtest_by_factor,
    generate_factor_report,
    identify_regime_dependent_factors,
)


class TestComputeFactorIC:
    """Tests for Information Coefficient calculation."""

    def test_perfect_correlation(self):
        """IC should be 1.0 when factor is perfectly correlated with returns."""
        scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=[0, 1, 2, 3, 4])
        returns = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=[0, 1, 2, 3, 4])

        ic = compute_factor_ic(scores, returns)
        assert ic == pytest.approx(1.0, abs=0.01)

    def test_inverse_correlation(self):
        """IC should be -1.0 when factor is inversely correlated with returns."""
        scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=[0, 1, 2, 3, 4])
        returns = pd.Series([5.0, 4.0, 3.0, 2.0, 1.0], index=[0, 1, 2, 3, 4])

        ic = compute_factor_ic(scores, returns)
        assert ic == pytest.approx(-1.0, abs=0.01)

    def test_weak_correlation(self):
        """IC should be moderate when factor has moderate correlation with returns."""
        np.random.seed(42)
        n = 20
        scores = np.arange(n) + np.random.randn(n) * 2
        returns = scores * 0.3 + np.random.randn(n) * 2  # Weak but nonzero correlation

        scores_series = pd.Series(scores, index=range(n))
        returns_series = pd.Series(returns, index=range(n))

        ic = compute_factor_ic(scores_series, returns_series)
        assert 0.1 < ic < 0.7  # Should be moderate correlation

    def test_handles_nan_values(self):
        """Should gracefully handle NaN values."""
        scores = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0], index=[0, 1, 2, 3, 4])
        returns = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0], index=[0, 1, 2, 3, 4])

        ic = compute_factor_ic(scores, returns)
        assert not np.isnan(ic)  # Should compute with remaining values

    def test_returns_nan_on_insufficient_data(self):
        """Should return NaN if fewer than 2 valid data points."""
        scores = pd.Series([1.0], index=[0])
        returns = pd.Series([1.0], index=[0])

        ic = compute_factor_ic(scores, returns)
        assert np.isnan(ic)


class TestDecomposeByFactor:
    """Tests for decomposing backtest IC into factor contributions."""

    def test_single_factor_decomposition(self):
        """Should correctly decompose IC for a single factor."""
        # Create backtest results with forward returns per ticker
        dates = pd.date_range("2024-01-01", periods=3, freq="MS")
        tickers = ["AAPL", "GOOGL", "MSFT"]

        # Each row is a date, each column is a ticker's forward return
        backtest = pd.DataFrame(
            {
                "AAPL": [0.05, 0.08, 0.02],
                "GOOGL": [0.06, 0.10, 0.03],
                "MSFT": [0.07, 0.09, 0.04],
            },
            index=dates,
        )

        # Create factor rankings (tickers × dates)
        factor_rankings = {
            "value": pd.DataFrame(
                {
                    dates[0]: [1.0, 2.0, 3.0],
                    dates[1]: [2.0, 1.0, 3.0],
                    dates[2]: [3.0, 2.0, 1.0],
                },
                index=tickers,
            ),
        }

        metrics = decompose_backtest_by_factor(backtest, factor_rankings)

        assert "value" in metrics
        assert metrics["value"].factor_name == "value"
        assert metrics["value"].ic_std > 0
        assert 0 <= metrics["value"].hit_rate <= 1

    def test_multiple_factors(self):
        """Should handle multiple factors simultaneously."""
        dates = pd.date_range("2024-01-01", periods=4, freq="MS")
        tickers = ["AAPL", "GOOGL", "MSFT"]

        backtest = pd.DataFrame(
            {
                "AAPL": [0.05, 0.08, 0.02, 0.06],
                "GOOGL": [0.06, 0.10, 0.03, 0.07],
                "MSFT": [0.07, 0.09, 0.04, 0.05],
            },
            index=dates,
        )

        factor_rankings = {
            "value": pd.DataFrame(
                {
                    dates[0]: [1.0, 2.0, 3.0],
                    dates[1]: [2.0, 1.0, 3.0],
                    dates[2]: [3.0, 2.0, 1.0],
                    dates[3]: [1.0, 3.0, 2.0],
                },
                index=tickers,
            ),
            "quality": pd.DataFrame(
                {
                    dates[0]: [3.0, 1.0, 2.0],
                    dates[1]: [2.0, 3.0, 1.0],
                    dates[2]: [1.0, 2.0, 3.0],
                    dates[3]: [3.0, 1.0, 2.0],
                },
                index=tickers,
            ),
        }

        metrics = decompose_backtest_by_factor(backtest, factor_rankings)

        assert len(metrics) == 2
        assert "value" in metrics
        assert "quality" in metrics

    def test_missing_dates(self):
        """Should gracefully handle mismatched dates between factors and backtest."""
        dates1 = pd.date_range("2024-01-01", periods=3, freq="MS")
        dates2 = pd.date_range("2024-02-01", periods=3, freq="MS")

        backtest = pd.DataFrame(
            {"ic": [0.1, 0.15, 0.05]},
            index=dates1,
        )

        factor_rankings = {
            "value": pd.DataFrame(
                {
                    "AAPL": [1.0, 2.0, 3.0],
                    "GOOGL": [2.0, 1.0, 2.0],
                    "MSFT": [3.0, 3.0, 1.0],
                },
                index=dates2,
            ).T,
        }

        metrics = decompose_backtest_by_factor(backtest, factor_rankings)

        # Should return empty dict if no overlapping dates
        assert len(metrics) == 0


class TestFactorCorrelations:
    """Tests for identifying correlated/redundant factors."""

    def test_uncorrelated_factors(self):
        """Should produce low correlation for independent factors."""
        tickers = ["A", "B", "C", "D", "E"]
        dates = pd.date_range("2024-01-01", periods=10, freq="D")

        # Independent random rankings
        np.random.seed(42)
        factor_rankings = {
            "factor_a": pd.DataFrame(
                np.random.randn(10, 5),
                columns=tickers,
                index=dates,
            ),
            "factor_b": pd.DataFrame(
                np.random.randn(10, 5),
                columns=tickers,
                index=dates,
            ),
        }

        corr = compute_factor_correlations(factor_rankings)

        # Diagonal should be 1.0
        assert corr.loc["factor_a", "factor_a"] == pytest.approx(1.0)
        assert corr.loc["factor_b", "factor_b"] == pytest.approx(1.0)

        # Off-diagonal should be low (random data)
        assert abs(corr.loc["factor_a", "factor_b"]) < 0.6

    def test_highly_correlated_factors(self):
        """Should detect when factors are identical or nearly identical."""
        tickers = ["A", "B", "C", "D", "E"]
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        base_data = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])

        factor_rankings = {
            "factor_a": pd.DataFrame(
                np.tile(base_data, (10, 1)),
                columns=tickers,
                index=dates,
            ),
            "factor_b": pd.DataFrame(
                np.tile(base_data * 1.01, (10, 1)),  # Nearly identical
                columns=tickers,
                index=dates,
            ),
        }

        corr = compute_factor_correlations(factor_rankings)

        # Should be highly correlated
        assert corr.loc["factor_a", "factor_b"] > 0.95


class TestRegimeDependence:
    """Tests for identifying regime-dependent factor performance."""

    def test_regime_sensitive_factor(self):
        """Should detect when factor IC changes with macro regime."""
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")

        # Factor IC varies by regime
        ic_by_regime = [0.1] * 4 + [0.3] * 4 + [0.05] * 4
        factor_ic_series = {"value": pd.Series(ic_by_regime, index=dates)}

        # Regime changes
        regime_series = pd.Series([0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2], index=dates)

        sensitivities = identify_regime_dependent_factors(factor_ic_series, regime_series)

        assert "value" in sensitivities
        # Should be correlated with regime changes
        assert sensitivities["value"] != 0.0

    def test_regime_agnostic_factor(self):
        """Should give near-zero sensitivity for regime-independent factors."""
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")

        # Constant IC across all regimes
        ic_by_regime = [0.15] * 12
        factor_ic_series = {"quality": pd.Series(ic_by_regime, index=dates)}

        regime_series = pd.Series([0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2], index=dates)

        sensitivities = identify_regime_dependent_factors(factor_ic_series, regime_series)

        assert "quality" in sensitivities
        # Should be near zero (no regime dependence)
        assert abs(sensitivities["quality"]) < 0.3


class TestGenerateFactorReport:
    """Tests for report generation."""

    def test_report_formatting(self):
        """Should produce a properly formatted text report."""
        metrics = {
            "value": FactorMetrics(
                factor_name="value",
                ic_mean=0.12,
                ic_std=0.05,
                information_ratio=2.4,
                hit_rate=0.60,
                rolling_ic_trend=0.15,
            ),
            "quality": FactorMetrics(
                factor_name="quality",
                ic_mean=0.08,
                ic_std=0.06,
                information_ratio=1.33,
                hit_rate=0.55,
                rolling_ic_trend=-0.05,
            ),
        }

        report = generate_factor_report(metrics)

        assert "FACTOR PERFORMANCE REPORT" in report
        assert "value" in report
        assert "quality" in report
        assert "IC Mean" in report
        assert "Hit Rate" in report

    def test_report_sorts_by_ir(self):
        """Report should sort factors by Information Ratio (descending)."""
        metrics = {
            "value": FactorMetrics(
                factor_name="value",
                ic_mean=0.12,
                ic_std=0.05,
                information_ratio=2.4,
                hit_rate=0.60,
                rolling_ic_trend=0.15,
            ),
            "quality": FactorMetrics(
                factor_name="quality",
                ic_mean=0.08,
                ic_std=0.06,
                information_ratio=1.33,
                hit_rate=0.55,
                rolling_ic_trend=-0.05,
            ),
        }

        report = generate_factor_report(metrics)
        lines = report.split("\n")

        # Find the lines with factor names
        value_idx = next(
            i for i, line in enumerate(lines) if "value" in line and "IC Mean" not in line
        )
        quality_idx = next(
            i for i, line in enumerate(lines) if "quality" in line and "IC Mean" not in line
        )

        # value should come first (higher IR)
        assert value_idx < quality_idx


class TestFactorMetricsDataclass:
    """Tests for FactorMetrics dataclass."""

    def test_instantiation(self):
        """Should create FactorMetrics instances."""
        metric = FactorMetrics(
            factor_name="test_factor",
            ic_mean=0.1,
            ic_std=0.05,
            information_ratio=2.0,
            hit_rate=0.55,
            rolling_ic_trend=0.1,
        )

        assert metric.factor_name == "test_factor"
        assert metric.ic_mean == 0.1
        assert metric.information_ratio == 2.0

    def test_regime_correlation_optional(self):
        """Regime correlation should be optional."""
        metric = FactorMetrics(
            factor_name="test",
            ic_mean=0.1,
            ic_std=0.05,
            information_ratio=2.0,
            hit_rate=0.55,
            rolling_ic_trend=0.1,
        )

        assert metric.regime_correlation is None
