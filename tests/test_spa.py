"""Tests for the Superior Predictive Ability (SPA) test."""

from __future__ import annotations

import numpy as np

from iam.backtest.spa import stationary_bootstrap, superior_predictive_ability


def test_stationary_bootstrap_shape_and_bounds():
    t_obs = 100
    n_boot = 50
    indices = stationary_bootstrap(t_obs, block_prob=0.1, n_boot=n_boot, seed=42)

    assert indices.shape == (n_boot, t_obs)
    assert np.min(indices) >= 0
    assert np.max(indices) < t_obs


def test_spa_rejects_null_for_genuine_outperformance():
    # 200 periods, 5 strategies
    np.random.seed(42)
    strat_returns = np.random.normal(0, 0.01, size=(200, 5))
    
    # Inject a consistently strong signal into strategy 0
    strat_returns[:, 0] += 0.005  # 0.5% alpha per period
    
    bench = np.zeros(200)

    res = superior_predictive_ability(
        strat_returns, benchmark_returns=bench, block_prob=0.1, n_boot=1000, seed=42
    )
    
    assert res["best_model_idx"] == 0
    assert res["observed_max_stat"] > 0
    assert res["reject"] is True
    assert res["spa_pvalue"] < 0.05


def test_spa_fails_to_reject_for_noise_strategies():
    # 200 periods, 50 noise strategies
    # Because we test 50 strategies, one of them will look good by pure chance.
    # The SPA test should recognize this is just noise and NOT reject the null.
    np.random.seed(42)
    strat_returns = np.random.normal(0, 0.01, size=(200, 50))
    bench = np.zeros(200)

    res = superior_predictive_ability(
        strat_returns, benchmark_returns=bench, block_prob=0.1, n_boot=1000, seed=42
    )
    
    # Even if one strategy happens to be positive, p-value should be high
    assert res["reject"] is False
    assert res["spa_pvalue"] > 0.05


def test_spa_worse_than_benchmark():
    # All strategies lose money
    np.random.seed(42)
    strat_returns = np.random.normal(-0.01, 0.01, size=(50, 3))
    
    res = superior_predictive_ability(
        strat_returns, benchmark_returns=None, block_prob=0.1, n_boot=100, seed=42
    )
    
    assert res["spa_pvalue"] == 1.0
    assert res["reject"] is False
    assert res["observed_max_stat"] < 0
