"""Factor weight optimization via walk-forward, bootstrap, and regime analysis.

Optimizes factor weights to maximize average Spearman rank IC between
composite scores and forward returns. All optimizations enforce:
- Sum-to-one constraint (weights sum to 1.0)
- Non-negativity (all weights >= 0)
- Bayesian shrinkage toward prior (DEFAULT_WEIGHTS)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, minimize

logger = logging.getLogger(__name__)


@dataclass
class WeightOptimizerConfig:
    n_factors: int = 10
    factor_names: list[str] = field(default_factory=list)
    prior_weights: np.ndarray | None = None
    shrinkage_lambda: float = 0.7
    train_window_months: int = 60
    test_window_months: int = 12
    n_bootstrap: int = 100
    max_iter: int = 500
    tol: float = 1e-6


@dataclass
class WalkForwardResult:
    status: str
    final_weights: np.ndarray
    avg_oos_ic: float
    std_oos_ic: float
    window_weights: list[np.ndarray]
    window_oos_ics: list[float]
    weight_names: list[str]


@dataclass
class BootstrapResult:
    status: str
    robust_weights: np.ndarray
    weight_std: np.ndarray
    coefficient_of_variation: np.ndarray
    weight_names: list[str]


@dataclass
class RegimeResult:
    status: str
    regime_weights: dict[str, np.ndarray]
    regime_counts: dict[str, int]
    weight_names: list[str]


def _objective(
    weights: np.ndarray,
    factor_scores_list: list[np.ndarray],
    returns_list: list[np.ndarray],
) -> float:
    """Negative average IC across all dates."""
    ics = []
    for scores, rets in zip(factor_scores_list, returns_list):
        if len(rets) < 2:
            continue
        composite = scores @ weights
        if np.std(composite) == 0 or np.std(rets) == 0:
            continue
        ic = np.corrcoef(composite, rets)[0, 1]
        if not np.isnan(ic):
            ics.append(ic)
            
    if not ics:
        return 0.0
    return -np.mean(ics)


def optimize_weights(
    factor_scores_list: list[np.ndarray],
    returns_list: list[np.ndarray],
    prior_weights: np.ndarray | None = None,
    shrinkage_lambda: float = 0.7,
    max_iter: int = 500,
    tol: float = 1e-6,
) -> np.ndarray:
    if not factor_scores_list:
        if prior_weights is not None:
            return prior_weights.copy()
        return np.array([])

    n_factors = factor_scores_list[0].shape[1]
    
    if prior_weights is None:
        prior_weights = np.ones(n_factors) / n_factors
        
    x0 = prior_weights.copy()
    
    bounds = Bounds(0.0, 1.0)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    
    res = minimize(
        _objective,
        x0,
        args=(factor_scores_list, returns_list),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": max_iter, "ftol": tol},
    )
    
    w_opt = res.x
    w_final = shrinkage_lambda * w_opt + (1.0 - shrinkage_lambda) * prior_weights
    
    # Ensure it sums exactly to 1
    w_sum = np.sum(w_final)
    if w_sum > 0:
        w_final /= w_sum
        
    return w_final


class WalkForwardOptimizer:
    def __init__(self, config: WeightOptimizerConfig):
        self.config = config

    def run(
        self,
        dates: list[pd.Timestamp],
        factor_scores_by_date: dict[pd.Timestamp, np.ndarray],
        returns_by_date: dict[pd.Timestamp, np.ndarray],
    ) -> WalkForwardResult:
        if len(dates) < self.config.train_window_months + self.config.test_window_months:
            return WalkForwardResult(
                status="failed: not enough dates",
                final_weights=np.array([]),
                avg_oos_ic=0.0,
                std_oos_ic=0.0,
                window_weights=[],
                window_oos_ics=[],
                weight_names=self.config.factor_names,
            )

        window_weights = []
        window_oos_ics = []
        
        step = self.config.test_window_months
        n = len(dates)
        
        for i in range(0, n - self.config.train_window_months - self.config.test_window_months + 1, step):
            train_dates = dates[i : i + self.config.train_window_months]
            test_dates = dates[i + self.config.train_window_months : i + self.config.train_window_months + self.config.test_window_months]
            
            train_scores = [factor_scores_by_date[d] for d in train_dates if d in factor_scores_by_date]
            train_rets = [returns_by_date[d] for d in train_dates if d in returns_by_date]
            
            w_opt = optimize_weights(
                train_scores,
                train_rets,
                prior_weights=self.config.prior_weights,
                shrinkage_lambda=self.config.shrinkage_lambda,
                max_iter=self.config.max_iter,
                tol=self.config.tol,
            )
            
            test_scores = [factor_scores_by_date[d] for d in test_dates if d in factor_scores_by_date]
            test_rets = [returns_by_date[d] for d in test_dates if d in returns_by_date]
            
            ics = []
            for scores, rets in zip(test_scores, test_rets):
                if len(rets) < 2:
                    continue
                comp = scores @ w_opt
                if np.std(comp) == 0 or np.std(rets) == 0:
                    continue
                ic = np.corrcoef(comp, rets)[0, 1]
                if not np.isnan(ic):
                    ics.append(ic)
                    
            if ics:
                window_oos_ics.append(float(np.mean(ics)))
                window_weights.append(w_opt)

        if not window_weights:
            return WalkForwardResult(
                status="failed: no valid windows",
                final_weights=np.array([]),
                avg_oos_ic=0.0,
                std_oos_ic=0.0,
                window_weights=[],
                window_oos_ics=[],
                weight_names=self.config.factor_names,
            )

        final_weights = np.median(window_weights, axis=0)
        final_weights /= np.sum(final_weights)

        return WalkForwardResult(
            status="success",
            final_weights=final_weights,
            avg_oos_ic=float(np.mean(window_oos_ics)),
            std_oos_ic=float(np.std(window_oos_ics)),
            window_weights=window_weights,
            window_oos_ics=window_oos_ics,
            weight_names=self.config.factor_names,
        )


class BootstrapStability:
    def __init__(self, config: WeightOptimizerConfig):
        self.config = config

    def run(
        self,
        dates: list[pd.Timestamp],
        factor_scores_by_date: dict[pd.Timestamp, np.ndarray],
        returns_by_date: dict[pd.Timestamp, np.ndarray],
    ) -> BootstrapResult:
        if not dates:
            return BootstrapResult(
                status="failed: no dates",
                robust_weights=np.array([]),
                weight_std=np.array([]),
                coefficient_of_variation=np.array([]),
                weight_names=self.config.factor_names,
            )

        n = len(dates)
        weights = []
        
        # Use a local RandomState for reproducible bootstrap if seeded globally, 
        # but standard random choice works fine too.
        rng = np.random.RandomState()
        
        for _ in range(self.config.n_bootstrap):
            idx = rng.choice(n, size=n, replace=True)
            sampled_dates = [dates[i] for i in idx]
            
            scores = [factor_scores_by_date[d] for d in sampled_dates if d in factor_scores_by_date]
            rets = [returns_by_date[d] for d in sampled_dates if d in returns_by_date]
            
            w = optimize_weights(
                scores,
                rets,
                prior_weights=self.config.prior_weights,
                shrinkage_lambda=self.config.shrinkage_lambda,
                max_iter=self.config.max_iter,
                tol=self.config.tol,
            )
            weights.append(w)
            
        if not weights:
            return BootstrapResult(
                status="failed: bootstrap optimization failed",
                robust_weights=np.array([]),
                weight_std=np.array([]),
                coefficient_of_variation=np.array([]),
                weight_names=self.config.factor_names,
            )
            
        weights_arr = np.array(weights)
        robust_w = np.median(weights_arr, axis=0)
        if np.sum(robust_w) > 0:
            robust_w /= np.sum(robust_w)
            
        w_std = np.std(weights_arr, axis=0)
        cv = np.zeros_like(w_std)
        mask = robust_w > 1e-6
        cv[mask] = w_std[mask] / robust_w[mask]
        
        return BootstrapResult(
            status="success",
            robust_weights=robust_w,
            weight_std=w_std,
            coefficient_of_variation=cv,
            weight_names=self.config.factor_names,
        )


class RegimeOptimizer:
    def __init__(self, config: WeightOptimizerConfig, regime_func: Callable[[pd.Timestamp], str]):
        self.config = config
        self.regime_func = regime_func

    def run(
        self,
        dates: list[pd.Timestamp],
        factor_scores_by_date: dict[pd.Timestamp, np.ndarray],
        returns_by_date: dict[pd.Timestamp, np.ndarray],
    ) -> RegimeResult:
        regime_to_dates = {}
        for d in dates:
            r = self.regime_func(d)
            if r not in regime_to_dates:
                regime_to_dates[r] = []
            regime_to_dates[r].append(d)
            
        regime_weights = {}
        regime_counts = {}
        
        for r, r_dates in regime_to_dates.items():
            scores = [factor_scores_by_date[d] for d in r_dates if d in factor_scores_by_date]
            rets = [returns_by_date[d] for d in r_dates if d in returns_by_date]
            
            if len(scores) < 3:
                continue
                
            w = optimize_weights(
                scores,
                rets,
                prior_weights=self.config.prior_weights,
                shrinkage_lambda=self.config.shrinkage_lambda,
                max_iter=self.config.max_iter,
                tol=self.config.tol,
            )
            regime_weights[r] = w
            regime_counts[r] = len(r_dates)
            
        status = "success" if regime_weights else "failed: no regimes had enough data"
        
        return RegimeResult(
            status=status,
            regime_weights=regime_weights,
            regime_counts=regime_counts,
            weight_names=self.config.factor_names,
        )


def format_weights_report(
    weight_names: list[str],
    current_weights: np.ndarray,
    optimized_weights: np.ndarray,
) -> str:
    lines = [
        f"{'Factor':<25} | {'Current':>8} | {'Optimized':>9} | {'Delta':>8}",
        "-" * 57,
    ]
    for name, curr, opt in zip(weight_names, current_weights, optimized_weights):
        delta = opt - curr
        lines.append(f"{name:<25} | {curr:8.4f} | {opt:9.4f} | {delta:+8.4f}")
    return "\n".join(lines)
