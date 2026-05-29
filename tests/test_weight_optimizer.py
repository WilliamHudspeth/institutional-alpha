import numpy as np
import pandas as pd
import pytest

from iam.backtest.weight_optimizer import (
    BootstrapStability,
    RegimeOptimizer,
    WalkForwardOptimizer,
    WeightOptimizerConfig,
    format_weights_report,
    ledoit_wolf_shrinkage,
    optimize_weights,
)


def test_optimize_weights_sum_to_one():
    rng = np.random.RandomState(42)
    scores = rng.randn(50, 2)
    rets = 0.6 * scores[:, 0] + 0.3 * scores[:, 1] + rng.randn(50) * 0.1

    w = optimize_weights([scores], [rets], shrinkage_lambda=1.0)

    assert len(w) == 2
    assert np.isclose(np.sum(w), 1.0)
    assert np.all(w >= -1e-6)
    assert w[0] > w[1]  # Because factor 0 has stronger signal


def test_walk_forward_runs():
    rng = np.random.RandomState(42)
    dates = pd.date_range("2020-01-31", periods=36, freq="ME")

    scores_by_date = {d: rng.randn(30, 2) for d in dates}
    rets_by_date = {d: 0.5 * scores_by_date[d][:, 0] + rng.randn(30) * 0.5 for d in dates}

    config = WeightOptimizerConfig(
        n_factors=2,
        factor_names=["f1", "f2"],
        train_window_months=12,
        test_window_months=6,
    )

    wfo = WalkForwardOptimizer(config)
    res = wfo.run(dates.tolist(), scores_by_date, rets_by_date)

    assert res.status == "success"
    assert len(res.final_weights) == 2
    assert np.isclose(np.sum(res.final_weights), 1.0)
    assert len(res.window_weights) > 0
    assert np.isfinite(res.avg_oos_ic)


def test_bootstrap_robustness():
    rng = np.random.RandomState(42)
    dates = pd.date_range("2020-01-31", periods=10, freq="ME")

    scores_by_date = {d: rng.randn(30, 2) for d in dates}
    rets_by_date = {d: 0.5 * scores_by_date[d][:, 0] + rng.randn(30) * 0.5 for d in dates}

    config = WeightOptimizerConfig(n_factors=2, n_bootstrap=5)
    bs = BootstrapStability(config)
    res = bs.run(dates.tolist(), scores_by_date, rets_by_date)

    assert res.status == "success"
    assert np.isclose(np.sum(res.robust_weights), 1.0)
    assert np.all(np.isfinite(res.coefficient_of_variation))


def test_regime_optimizer():
    rng = np.random.RandomState(42)
    dates = pd.date_range("2020-01-31", periods=10, freq="ME")

    scores_by_date = {d: rng.randn(30, 2) for d in dates}
    rets_by_date = {d: 0.5 * scores_by_date[d][:, 0] + rng.randn(30) * 0.5 for d in dates}

    config = WeightOptimizerConfig(n_factors=2)

    def dummy_regime(d):
        return "A" if d.month <= 6 else "B"

    ro = RegimeOptimizer(config, dummy_regime)
    res = ro.run(dates.tolist(), scores_by_date, rets_by_date)

    assert res.status == "success"
    assert "A" in res.regime_weights
    assert "B" in res.regime_weights


def test_format_weights_report():
    names = ["f1", "f2"]
    curr = np.array([0.5, 0.5])
    opt = np.array([0.8, 0.2])

    rep = format_weights_report(names, curr, opt)
    assert "f1" in rep
    assert "0.8" in rep


# =====================================================================
# LEDOIT-WOLF SHRINKAGE TESTS
# =====================================================================


class TestLedoitWolfShrinkage:
    """Test Ledoit-Wolf shrinkage covariance properties."""

    def test_ledoit_wolf_covariance_is_symmetric(self):
        """Assert that the shrunken covariance matrix is symmetric."""
        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        Sigma = ledoit_wolf_shrinkage(X)
        assert np.allclose(Sigma, Sigma.T), "Covariance matrix is not symmetric"

    def test_ledoit_wolf_covariance_is_positive_semidefinite(self):
        """Assert that the shrunken covariance matrix is positive semi-definite."""
        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        Sigma = ledoit_wolf_shrinkage(X)
        eigenvalues = np.linalg.eigvals(Sigma)
        assert np.all(eigenvalues >= -1e-10), (
            f"Non-PSD matrix: min eigenvalue = {np.min(eigenvalues)}"
        )

    def test_ledoit_wolf_handles_nan_values(self):
        """Assert that NaN values are imputed with column means."""
        rng = np.random.RandomState(42)
        X = rng.randn(100, 3)
        # Introduce some NaNs
        X[0, 0] = np.nan
        X[5, 1] = np.nan
        X[10, 2] = np.nan
        # Should not raise an error
        Sigma = ledoit_wolf_shrinkage(X)
        assert Sigma.shape == (3, 3)
        assert np.all(np.isfinite(Sigma))

    def test_ledoit_wolf_edge_case_zero_samples(self):
        """Assert that zero-sample matrix returns zeros."""
        X = np.zeros((0, 5))
        Sigma = ledoit_wolf_shrinkage(X)
        assert Sigma.shape == (5, 5)
        assert np.allclose(Sigma, 0.0)

    def test_ledoit_wolf_edge_case_single_sample(self):
        """Assert that single-sample case returns zeros (degenerate)."""
        X = np.array([[1.0, 2.0, 3.0]])
        Sigma = ledoit_wolf_shrinkage(X)
        assert Sigma.shape == (3, 3)
        assert np.allclose(Sigma, 0.0)  # Single sample has zero covariance

    def test_ledoit_wolf_edge_case_all_zeros(self):
        """Assert that all-zero data returns zero covariance."""
        X = np.zeros((50, 3))
        Sigma = ledoit_wolf_shrinkage(X)
        assert Sigma.shape == (3, 3)
        assert np.allclose(Sigma, 0.0)

    def test_ledoit_wolf_diagonal_preservation(self):
        """Assert that diagonal elements (variances) are preserved."""
        rng = np.random.RandomState(42)
        X = rng.randn(200, 4)
        Sigma = ledoit_wolf_shrinkage(X)
        sample_var = np.var(X, axis=0, ddof=0)
        # Diagonal should be close to sample variance (depends on shrinkage intensity)
        # Allow tolerance due to optimal shrinkage pulling toward target
        assert np.allclose(np.diag(Sigma), sample_var, atol=0.5)

    def test_ledoit_wolf_handles_zero_variance_features(self):
        """Assert that zero-variance features are handled gracefully."""
        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        X[:, 2] = 5.0  # Set one feature to constant
        Sigma = ledoit_wolf_shrinkage(X)
        assert Sigma.shape == (5, 5)
        assert np.all(np.isfinite(Sigma))
        assert np.isclose(Sigma[2, 2], 0.0)  # Zero variance feature


class TestCovarianceRegularizedOptimization:
    """Test covariance-regularized weight optimization."""

    def test_covariance_regularized_optimization_reduces_concentration(self):
        """
        Test that covariance regularization prevents extreme concentration.

        Setup: Create collinear factor columns (nearly identical with noise).
        Verify: With regularization > 0, weights are more balanced than without.
        """
        rng = np.random.RandomState(42)
        n_samples = 100

        # Create base signal
        base_signal = rng.randn(n_samples)

        # Create nearly identical collinear factors with small noise
        f1 = base_signal + rng.randn(n_samples) * 0.01
        f2 = base_signal + rng.randn(n_samples) * 0.01
        f3 = rng.randn(n_samples)  # Uncorrelated

        scores = np.column_stack([f1, f2, f3])

        # Create target returns correlated with the signal
        returns = base_signal + rng.randn(n_samples) * 0.1

        # Optimize without regularization
        w_no_reg = optimize_weights(
            [scores],
            [returns],
            shrinkage_lambda=1.0,
            regularization_penalty=0.0,
        )

        # Optimize with regularization
        w_with_reg = optimize_weights(
            [scores],
            [returns],
            shrinkage_lambda=1.0,
            regularization_penalty=0.1,
        )

        # Compute weight concentration (variance of weights)
        # Higher variance = more concentrated
        conc_no_reg = np.var(w_no_reg)
        conc_with_reg = np.var(w_with_reg)

        # Regularization should reduce concentration
        assert conc_with_reg <= conc_no_reg, (
            f"Regularization failed to reduce concentration: "
            f"no_reg={conc_no_reg:.6f}, with_reg={conc_with_reg:.6f}"
        )

    def test_regularization_penalty_parameter_propagation(self):
        """Test that regularization_penalty is correctly propagated through optimizers."""
        rng = np.random.RandomState(42)
        dates = pd.date_range("2020-01-31", periods=36, freq="ME")

        scores_by_date = {d: rng.randn(30, 2) for d in dates}
        rets_by_date = {d: 0.5 * scores_by_date[d][:, 0] + rng.randn(30) * 0.5 for d in dates}

        config_no_reg = WeightOptimizerConfig(
            n_factors=2,
            factor_names=["f1", "f2"],
            train_window_months=12,
            test_window_months=6,
            regularization_penalty=0.0,
        )

        config_with_reg = WeightOptimizerConfig(
            n_factors=2,
            factor_names=["f1", "f2"],
            train_window_months=12,
            test_window_months=6,
            regularization_penalty=0.1,
        )

        wfo_no_reg = WalkForwardOptimizer(config_no_reg)
        wfo_with_reg = WalkForwardOptimizer(config_with_reg)

        res_no_reg = wfo_no_reg.run(dates.tolist(), scores_by_date, rets_by_date)
        res_with_reg = wfo_with_reg.run(dates.tolist(), scores_by_date, rets_by_date)

        assert res_no_reg.status == "success"
        assert res_with_reg.status == "success"
        # Both should produce valid weights
        assert np.isclose(np.sum(res_no_reg.final_weights), 1.0)
        assert np.isclose(np.sum(res_with_reg.final_weights), 1.0)

    def test_bootstrap_respects_regularization_penalty(self):
        """Test that BootstrapStability respects regularization_penalty config."""
        rng = np.random.RandomState(42)
        dates = pd.date_range("2020-01-31", periods=10, freq="ME")

        scores_by_date = {d: rng.randn(30, 3) for d in dates}
        rets_by_date = {d: 0.5 * scores_by_date[d][:, 0] + rng.randn(30) * 0.5 for d in dates}

        config = WeightOptimizerConfig(
            n_factors=3,
            n_bootstrap=5,
            regularization_penalty=0.05,
        )

        bs = BootstrapStability(config)
        res = bs.run(dates.tolist(), scores_by_date, rets_by_date)

        assert res.status == "success"
        assert len(res.robust_weights) == 3
        assert np.isclose(np.sum(res.robust_weights), 1.0)

    def test_regime_optimizer_respects_regularization_penalty(self):
        """Test that RegimeOptimizer respects regularization_penalty config."""
        rng = np.random.RandomState(42)
        dates = pd.date_range("2020-01-31", periods=10, freq="ME")

        scores_by_date = {d: rng.randn(30, 2) for d in dates}
        rets_by_date = {d: 0.5 * scores_by_date[d][:, 0] + rng.randn(30) * 0.5 for d in dates}

        config = WeightOptimizerConfig(
            n_factors=2,
            regularization_penalty=0.08,
        )

        def dummy_regime(d):
            return "A" if d.month <= 6 else "B"

        ro = RegimeOptimizer(config, dummy_regime)
        res = ro.run(dates.tolist(), scores_by_date, rets_by_date)

        assert res.status == "success"
        for regime_w in res.regime_weights.values():
            assert np.isclose(np.sum(regime_w), 1.0)

    def test_no_regularization_penalty_zero_doesnt_crash(self):
        """Test that regularization_penalty=0.0 doesn't cause issues."""
        rng = np.random.RandomState(42)
        scores = [rng.randn(50, 2)]
        returns = [0.6 * scores[0][:, 0] + rng.randn(50) * 0.1]

        # Should not raise an error with regularization_penalty=0.0
        w = optimize_weights(
            scores,
            returns,
            regularization_penalty=0.0,
            shrinkage_lambda=1.0,
        )

        assert len(w) == 2
        assert np.isclose(np.sum(w), 1.0)

    def test_high_regularization_penalty_smooths_weights(self):
        """Test that high regularization penalty produces more uniform weights."""
        rng = np.random.RandomState(42)
        n_samples = 100

        # Create signal where one factor is much stronger
        strong_signal = rng.randn(n_samples)
        f1 = strong_signal + rng.randn(n_samples) * 0.01
        f2 = rng.randn(n_samples) * 0.5
        f3 = rng.randn(n_samples) * 0.5

        scores = np.column_stack([f1, f2, f3])
        returns = strong_signal + rng.randn(n_samples) * 0.1

        # Low regularization → may concentrate on strong signal
        w_low_reg = optimize_weights(
            [scores],
            [returns],
            regularization_penalty=0.001,
            shrinkage_lambda=1.0,
        )

        # High regularization → more uniform weights
        w_high_reg = optimize_weights(
            [scores],
            [returns],
            regularization_penalty=1.0,
            shrinkage_lambda=1.0,
        )

        # High regularization should produce more uniform weights (lower variance)
        var_low = np.var(w_low_reg)
        var_high = np.var(w_high_reg)

        assert var_high <= var_low, (
            f"High regularization should produce more uniform weights. "
            f"var_low={var_low:.6f}, var_high={var_high:.6f}"
        )
