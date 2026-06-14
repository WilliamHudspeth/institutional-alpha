"""Superior Predictive Ability (SPA) Test and Stationary Bootstrapping.

Implements Hansen's SPA test (2005) to evaluate if the best strategy in a
universe of strategies genuinely outperforms a benchmark, accounting for the
full data-mining / multiple-testing search process.
"""

from __future__ import annotations

import numpy as np


def stationary_bootstrap(
    t_obs: int,
    block_prob: float = 0.1,
    n_boot: int = 5000,
    seed: int | None = None,
) -> np.ndarray:
    """Generate indices for a stationary block bootstrap (Politis & Romano, 1994).

    Resamples indices from 0 to t_obs-1 while preserving time-series autocorrelation.
    Block lengths are geometrically distributed with expected length 1/block_prob.

    Args:
        t_obs: Length of the time series to resample.
        block_prob: Probability of ending the current block and starting a new one.
        n_boot: Number of bootstrap iterations to generate.
        seed: Random seed for reproducibility.

    Returns:
        A (n_boot, t_obs) integer array containing the resampled indices.
    """
    rng = np.random.default_rng(seed)

    indices = np.zeros((n_boot, t_obs), dtype=int)

    # The first element of each bootstrap path is a uniform random draw
    indices[:, 0] = rng.integers(0, t_obs, size=n_boot)

    # Boolean mask: True means start a new block, False means continue the block
    transitions = rng.random((n_boot, t_obs - 1)) < block_prob
    new_starts = rng.integers(0, t_obs, size=(n_boot, t_obs - 1))

    # Iteratively build the paths. (Vectorized over paths, sequential over time).
    for i in range(1, t_obs):
        indices[:, i] = np.where(
            transitions[:, i - 1],
            new_starts[:, i - 1],
            (indices[:, i - 1] + 1) % t_obs,
        )

    return indices


def superior_predictive_ability(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray | None = None,
    block_prob: float = 0.1,
    n_boot: int = 5000,
    seed: int | None = None,
) -> dict:
    """Hansen's Superior Predictive Ability (SPA) Test.

    Tests the null hypothesis that the best model is no better than the benchmark.

    Args:
        strategy_returns: A (T, K) array of returns for K strategies over T periods.
        benchmark_returns: A (T,) array of benchmark returns. If None, defaults to 0.0,
            which tests if the strategies have a significantly positive absolute return.
        block_prob: Parameter for the stationary bootstrap (1 / expected_block_length).
        n_boot: Number of bootstrap iterations.
        seed: Random seed for the bootstrap.

    Returns:
        A dictionary containing:
            - 'spa_pvalue': The p-value of the test (lower means reject the null).
            - 'reject': Boolean indicating if the null is rejected at alpha=0.05.
            - 'best_model_idx': The index (0 to K-1) of the model that performed best.
            - 'observed_max_stat': The test statistic of the best model.
    """
    strat = np.asarray(strategy_returns, dtype=float)
    if strat.ndim == 1:
        strat = strat.reshape(-1, 1)
    elif strat.ndim != 2:
        raise ValueError("strategy_returns must be a 1D or 2D array.")

    t_obs, k_strats = strat.shape

    if benchmark_returns is None:
        bench = np.zeros(t_obs)
    else:
        bench = np.asarray(benchmark_returns, dtype=float)
        if bench.shape != (t_obs,):
            raise ValueError(
                f"benchmark_returns shape {bench.shape} does not match T={t_obs} periods."
            )

    # 1. Compute relative performance matrix D_{t,k}
    # D_{t,k} = Strategy_{t,k} - Benchmark_t
    D = strat - bench[:, None]

    # 2. Compute the sample means of D for each strategy
    D_bar = np.nanmean(D, axis=0)

    # 3. Calculate sample variance of the sample means to standardize
    # We approximate the variance of the sample mean using the time-series variance scaled by T.
    # Note: Hansen uses the bootstrapped variance, but scaling the test statistic
    # is often optional if we use the unstandardized test statistic consistently.
    # For simplicity and robustness, we will use the unstandardized mean difference
    # as the test statistic, which is standard when D_k are returns.
    observed_stat = D_bar
    observed_max_stat = np.max(observed_stat)
    best_model_idx = int(np.argmax(observed_stat))

    # If the best strategy is worse than the benchmark, we already fail to reject
    if observed_max_stat <= 0:
        return {
            "spa_pvalue": 1.0,
            "reject": False,
            "best_model_idx": best_model_idx,
            "observed_max_stat": float(observed_max_stat),
        }

    # 4. Generate bootstrap indices
    boot_indices = stationary_bootstrap(t_obs, block_prob, n_boot, seed)

    # 5. Recenter the relative performance matrix under the null hypothesis.
    # The null hypothesis is that no strategy is better than the benchmark: E[D_k] <= 0.
    # Hansen (2005) suggests recentering by subtracting max(D_bar_k, 0)
    # or by subtracting D_bar_k.
    # We subtract D_bar to strictly center the bootstrap distributions at 0.
    D_centered = D - D_bar[None, :]

    # 6. Compute test statistics for each bootstrap sample
    boot_max_stats = np.zeros(n_boot)

    # To optimize memory, process bootstraps in chunks or directly
    for b in range(n_boot):
        # Sample the centered performance matrix
        D_boot = D_centered[boot_indices[b], :]

        # Mean of the bootstrapped sample
        D_bar_boot = np.nanmean(D_boot, axis=0)

        # The bootstrap test statistic for this path is the maximum performance
        boot_max_stats[b] = np.max(D_bar_boot)

    # 7. Compute the p-value: what proportion of bootstrap samples exceeded our observed max?
    # Because we centered at 0, we compare the bootstrap max to the observed max.
    p_value = np.mean(boot_max_stats >= observed_max_stat)

    return {
        "spa_pvalue": float(p_value),
        "reject": bool(p_value < 0.05),
        "best_model_idx": best_model_idx,
        "observed_max_stat": float(observed_max_stat),
    }
