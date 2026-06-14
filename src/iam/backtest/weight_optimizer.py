"""Factor weight optimization via walk-forward, bootstrap, and regime analysis.

Optimizes factor weights to maximize average Spearman rank IC between
composite scores and forward returns. All optimizations enforce:
- Sum-to-one constraint (weights sum to 1.0)
- Non-negativity (all weights >= 0)
- Bayesian shrinkage toward prior (DEFAULT_WEIGHTS)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, minimize

from iam.backtest.cpcv import get_cpcv_splits
from iam.backtest.multiple_testing import deflated_sharpe_ratio
from iam.backtest.overfitting import probability_of_backtest_overfitting

logger = logging.getLogger(__name__)


def ledoit_wolf_shrinkage(X: np.ndarray) -> np.ndarray:
    """
    Computes the analytical Ledoit-Wolf optimal shrinkage covariance matrix.

    The estimator shrinks the sample covariance matrix S toward a constant
    correlation target F using an optimal shrinkage intensity δ ∈ [0,1]:
            Σ = (1 - δ) S + δ F

    The optimal δ is derived by minimizing the Frobenius norm between the
    true and estimated covariance (Ledoit & Wolf, 2004).

    Parameters
    ----------
    X : np.ndarray, shape (n_samples, n_features)
            Data matrix. Rows are observations, columns are features.
            NaNs are imputed with column means.

    Returns
    -------
    shrunk_cov : np.ndarray, shape (n_features, n_features)
            Shrunken covariance matrix (symmetric positive semi‑definite).
    """
    # ---------- handle edge cases and NaNs ----------
    X = X.astype(float, copy=True)
    # replace NaNs with column means
    col_means = np.nanmean(X, axis=0)
    X = np.where(np.isnan(X), col_means, X)

    n, p = X.shape
    if n == 0:
        return np.zeros((p, p))
    if n == 1:
        # degenerate case: only one observation → diagonal of sample variances (all zero)
        return np.diag(np.var(X, axis=0, ddof=0))

    # ---------- center data ----------
    Xc = X - X.mean(axis=0)  # shape (n, p)

    # ---------- sample covariance (MLE divisor n) ----------
    S = (Xc.T @ Xc) / n  # shape (p, p)

    # ---------- constant correlation target F ----------
    var = np.diag(S)  # marginal variances
    sqrt_var = np.sqrt(var)

    # handle zero‑variance features
    pos_var = var > 0
    if np.sum(pos_var) >= 2:
        idx = np.where(pos_var)[0]
        S_nz = S[np.ix_(idx, idx)]
        sqrt_nz = sqrt_var[idx]
        # correlation matrix of positive‑variance features
        R_nz = S_nz / np.outer(sqrt_nz, sqrt_nz)
        # average correlation (off‑diagonal only)
        r_bar = (np.sum(R_nz) - len(idx)) / (len(idx) * (len(idx) - 1))
    else:
        r_bar = 0.0

    # build target matrix F = (1-r_bar)*diag(var) + r_bar * (sqrt_var sqrt_var^T)
    outer_sqrt = np.outer(sqrt_var, sqrt_var)
    F = r_bar * outer_sqrt
    np.fill_diagonal(F, var)  # correct diagonal to variances

    # ---------- compute optimal shrinkage intensity δ ----------
    # d² = Frobenius norm squared of (S - F)
    d2 = np.sum((S - F) ** 2)

    # b² = average empirical variance of the entries of the sample covariance
    # Let y = Xc (centered). For each feature pair (i,j):
    #   s_ij = (1/n) Σ_t y_ti y_tj
    #   var_hat(s_ij) = (1/n) Σ_t (y_ti y_tj - s_ij)²
    #   then b² = (1/n) Σ_{i,j} var_hat(s_ij)
    M = Xc**2  # shape (n, p)
    # S2[i,j] = sample variance of the product y_i y_j
    S2 = (M.T @ M) / n - S**2
    b2 = np.sum(S2) / n

    # shrinkage intensity δ = b² / (b² + d²)	 (clipped to [0,1])
    shrinkage = b2 / (b2 + d2) if (b2 + d2) > 0 else 0.0
    shrinkage = np.clip(shrinkage, 0.0, 1.0)

    # ---------- return shrunken covariance ----------
    shrunk_cov = (1 - shrinkage) * S + shrinkage * F
    return shrunk_cov  # type: ignore


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
    regularization_penalty: float = 0.05


@dataclass
class StatisticalValidation:
    pbo_score: float | None = None
    cpcv_stability_score: float | None = None
    dsr: float | None = None
    n_trials_searched: int | None = None


@dataclass
class OptimizerResult:
    status: str
    final_weights: np.ndarray
    avg_oos_ic: float
    std_oos_ic: float
    window_weights: list[np.ndarray]
    window_oos_ics: list[float]
    weight_names: list[str]
    validation: StatisticalValidation | None = None


# Backwards compatibility alias
WalkForwardResult = OptimizerResult


@dataclass
class BootstrapResult:
    status: str
    robust_weights: np.ndarray
    weight_std: np.ndarray
    coefficient_of_variation: np.ndarray
    weight_names: list[str]
    bootstrap_weights: np.ndarray = field(default_factory=lambda: np.array([]))


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
    Sigma: np.ndarray | None = None,
    regularization_penalty: float = 0.05,
) -> float:
    """Negative average IC across all dates + weight variance penalty."""
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
        avg_ic = 0.0
    else:
        avg_ic = np.mean(ics)

    loss = -avg_ic
    if Sigma is not None and regularization_penalty > 0:
        # Regularization term: w^T * Sigma * w
        penalty = regularization_penalty * float(weights.T @ Sigma @ weights)
        loss += penalty

    return loss


def optimize_weights(
    factor_scores_list: list[np.ndarray],
    returns_list: list[np.ndarray],
    prior_weights: np.ndarray | None = None,
    shrinkage_lambda: float = 0.7,
    regularization_penalty: float = 0.05,
    max_iter: int = 500,
    tol: float = 1e-6,
    return_nfev: bool = False,
) -> np.ndarray | tuple[np.ndarray, int]:
    if not factor_scores_list:
        fallback = prior_weights.copy() if prior_weights is not None else np.array([])
        return (fallback, 0) if return_nfev else fallback

    n_factors = factor_scores_list[0].shape[1]

    if prior_weights is None:
        prior_weights = np.ones(n_factors) / n_factors

    # Concatenate all cross-sectional factor scores to compute the full sample covariance block
    try:
        X = np.concatenate(factor_scores_list, axis=0)
        Sigma = ledoit_wolf_shrinkage(X)
    except Exception as e:
        # Graceful fallback if concatenation fails due to empty dimensions
        logger.debug(f"Could not compute Ledoit-Wolf covariance: {e}")
        Sigma = None

    x0 = prior_weights.copy()

    bounds = Bounds(0.0, 1.0)
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    res = minimize(
        _objective,
        x0,
        args=(factor_scores_list, returns_list, Sigma, regularization_penalty),
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

    if return_nfev:
        return w_final, getattr(res, "nfev", 1)
    return w_final  # type: ignore


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
        total_nfev = 0

        step = self.config.test_window_months
        n = len(dates)

        for i in range(
            0, n - self.config.train_window_months - self.config.test_window_months + 1, step
        ):
            train_dates = dates[i : i + self.config.train_window_months]
            test_dates = dates[
                i + self.config.train_window_months : i
                + self.config.train_window_months
                + self.config.test_window_months
            ]

            train_scores = [
                factor_scores_by_date[d] for d in train_dates if d in factor_scores_by_date
            ]
            train_rets = [returns_by_date[d] for d in train_dates if d in returns_by_date]

            w_opt, nfev = optimize_weights(
                train_scores,
                train_rets,
                prior_weights=self.config.prior_weights,
                shrinkage_lambda=self.config.shrinkage_lambda,
                regularization_penalty=self.config.regularization_penalty,
                max_iter=self.config.max_iter,
                tol=self.config.tol,
                return_nfev=True,
            )
            total_nfev += nfev

            test_scores = [
                factor_scores_by_date[d] for d in test_dates if d in factor_scores_by_date
            ]
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
            return OptimizerResult(
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

        # Build Performance Matrix for PBO
        # Rows = time periods, Cols = candidate configurations (window_weights)
        perf_matrix = np.zeros((len(dates), len(window_weights)))
        for i, d in enumerate(dates):
            if d not in factor_scores_by_date or d not in returns_by_date:
                perf_matrix[i, :] = np.nan
                continue
            s = factor_scores_by_date[d]
            r = returns_by_date[d]
            if len(r) < 2 or np.std(r) == 0:
                perf_matrix[i, :] = np.nan
                continue

            for j, w in enumerate(window_weights):
                comp = s @ w
                if np.std(comp) == 0:
                    perf_matrix[i, j] = np.nan
                else:
                    perf_matrix[i, j] = np.corrcoef(comp, r)[0, 1]

        # Compute PBO (we need an even number of partitions, min 2)
        valid_rows = ~np.isnan(perf_matrix).all(axis=1)
        clean_matrix = perf_matrix[valid_rows]
        n_partitions = min(16, len(clean_matrix) // 2)
        if n_partitions % 2 != 0:
            n_partitions -= 1

        pbo_score = None
        if n_partitions >= 2 and clean_matrix.shape[1] >= 2:
            try:
                pbo_score = probability_of_backtest_overfitting(
                    clean_matrix, n_partitions=n_partitions
                )
            except Exception:
                pbo_score = None

        # Compute DSR using actual number of trials (total_nfev)
        avg_ic = float(np.mean(window_oos_ics))
        std_ic = float(np.std(window_oos_ics))
        n_obs = len(window_oos_ics)
        ir = avg_ic / std_ic if std_ic > 0 else 0.0

        dsr_val = None
        if total_nfev > 1 and n_obs > 2 and std_ic > 0:
            # We treat the variance of trials as the variance of the ICs generated across configurations
            var_trials = (
                np.var(np.nanmean(perf_matrix, axis=0)) if clean_matrix.shape[1] > 1 else 0.001
            )
            if var_trials > 0:
                dsr_val = deflated_sharpe_ratio(
                    observed_sr=ir,
                    n_obs=n_obs,
                    n_trials=total_nfev,
                    var_trials=var_trials,  # type: ignore
                    mean_trials=0.0,
                )

        return OptimizerResult(
            status="success",
            final_weights=final_weights,
            avg_oos_ic=avg_ic,
            std_oos_ic=std_ic,
            window_weights=window_weights,
            window_oos_ics=window_oos_ics,
            weight_names=self.config.factor_names,
            validation=StatisticalValidation(
                pbo_score=pbo_score, dsr=dsr_val, n_trials_searched=total_nfev
            ),
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
                regularization_penalty=self.config.regularization_penalty,
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
            bootstrap_weights=weights_arr,
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
        regime_to_dates: dict[str, list[pd.Timestamp]] = {}
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
                regularization_penalty=self.config.regularization_penalty,
                max_iter=self.config.max_iter,
                tol=self.config.tol,
            )
            regime_weights[r] = w
            regime_counts[r] = len(r_dates)

        status = "success" if regime_weights else "failed: no regimes had enough data"

        return RegimeResult(
            status=status,
            regime_weights=regime_weights,  # type: ignore
            regime_counts=regime_counts,
            weight_names=self.config.factor_names,
        )


class CPCVOptimizer:
    def __init__(
        self,
        config: WeightOptimizerConfig,
        n_groups: int = 6,
        k_test_groups: int = 2,
        purge_days: int = 15,
        embargo_days: int = 15,
    ):
        self.config = config
        self.n_groups = n_groups
        self.k_test_groups = k_test_groups
        self.purge_days = purge_days
        self.embargo_days = embargo_days

    def run(
        self,
        dates: list[pd.Timestamp],
        factor_scores_by_date: dict[pd.Timestamp, np.ndarray],
        returns_by_date: dict[pd.Timestamp, np.ndarray],
    ) -> OptimizerResult:
        if not dates:
            return OptimizerResult(
                "failed", np.array([]), 0.0, 0.0, [], [], self.config.factor_names
            )

        try:
            splits = get_cpcv_splits(
                dates,
                n_groups=self.n_groups,
                k_test_groups=self.k_test_groups,
                purge_days=self.purge_days,
                embargo_days=self.embargo_days,
            )
        except ValueError:
            return OptimizerResult(
                "failed: too few dates", np.array([]), 0.0, 0.0, [], [], self.config.factor_names
            )

        path_weights = []
        path_oos_ics = []
        total_nfev = 0

        for train_idx, test_idx in splits:
            train_dates = [dates[i] for i in train_idx]
            test_dates = [dates[i] for i in test_idx]

            train_scores = [
                factor_scores_by_date[d] for d in train_dates if d in factor_scores_by_date
            ]
            train_rets = [returns_by_date[d] for d in train_dates if d in returns_by_date]

            w_opt, nfev = optimize_weights(
                train_scores,
                train_rets,
                prior_weights=self.config.prior_weights,
                shrinkage_lambda=self.config.shrinkage_lambda,
                regularization_penalty=self.config.regularization_penalty,
                max_iter=self.config.max_iter,
                tol=self.config.tol,
                return_nfev=True,
            )
            total_nfev += nfev

            test_scores = [
                factor_scores_by_date[d] for d in test_dates if d in factor_scores_by_date
            ]
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
                path_oos_ics.append(float(np.mean(ics)))
                path_weights.append(w_opt)

        if not path_weights:
            return OptimizerResult(
                "failed: no valid paths", np.array([]), 0.0, 0.0, [], [], self.config.factor_names
            )

        final_weights = np.median(path_weights, axis=0)
        final_weights /= np.sum(final_weights)

        # CPCV Stability Score
        avg_ic = float(np.mean(path_oos_ics))
        std_ic = float(np.std(path_oos_ics))
        stability_score = avg_ic / std_ic if std_ic > 0 else 0.0

        return OptimizerResult(
            status="success",
            final_weights=final_weights,
            avg_oos_ic=avg_ic,
            std_oos_ic=std_ic,
            window_weights=path_weights,
            window_oos_ics=path_oos_ics,
            weight_names=self.config.factor_names,
            validation=StatisticalValidation(
                pbo_score=None,  # We could compute PBO here too
                cpcv_stability_score=stability_score,
                n_trials_searched=total_nfev,
            ),
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
