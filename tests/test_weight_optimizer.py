import numpy as np
import pandas as pd
import pytest

from iam.backtest.weight_optimizer import (
    WeightOptimizerConfig,
    optimize_weights,
    WalkForwardOptimizer,
    BootstrapStability,
    RegimeOptimizer,
    format_weights_report,
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
