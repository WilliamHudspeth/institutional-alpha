"""Probability of Backtest Overfitting (PBO) layer.

Implements Combinatorial Symmetric Cross-Validation (CSCV) to compute the
probability that the optimal in-sample strategy performs worse than the median
strategy out-of-sample, indicating overfitting (Bailey et al. 2015).
"""

from __future__ import annotations

import itertools

import numpy as np


def probability_of_backtest_overfitting(
    performance_matrix: np.ndarray,
    n_partitions: int = 16,
) -> float:
    """Calculate the Probability of Backtest Overfitting (PBO).

    Args:
        performance_matrix: A (T, N) array where T is the number of time periods
            (e.g., months) and N is the number of strategies/trials. The values
            can be returns or Information Coefficients.
        n_partitions: The number of equal-sized blocks to partition the T periods
            into. Must be an even number.

    Returns:
        The probability (0.0 to 1.0) that the best in-sample strategy underperforms
        the median out-of-sample strategy. A value > 0.5 suggests severe overfitting.

    Raises:
        ValueError: If n_partitions is not even or if there are fewer periods
            than partitions.
    """
    m = np.asarray(performance_matrix, dtype=float)
    if m.ndim != 2:
        raise ValueError("performance_matrix must be 2-dimensional (T periods, N strategies)")

    t_obs, n_strats = m.shape
    if n_strats < 2:
        return 0.0  # Cannot overfit a single strategy against itself

    if n_partitions % 2 != 0:
        raise ValueError("n_partitions must be an even number")
    if t_obs < n_partitions:
        raise ValueError(f"Not enough observations ({t_obs}) for {n_partitions} partitions")

    # 1. Partition the matrix into S blocks
    # To handle remainders, we use array_split
    blocks = np.array_split(m, n_partitions, axis=0)

    # 2. Form all combinations of S/2 blocks for the in-sample (train) set
    train_size = n_partitions // 2
    block_indices = set(range(n_partitions))
    combinations = list(itertools.combinations(block_indices, train_size))

    # We will accumulate the relative rank of the optimal IS strategy in the OOS set
    # rank <= 0.5 means it performed worse than the median strategy.
    overfit_count = 0

    for train_idx in combinations:
        test_idx = tuple(block_indices - set(train_idx))

        # Concatenate train and test matrices
        train_matrix = np.concatenate([blocks[i] for i in train_idx], axis=0)
        test_matrix = np.concatenate([blocks[i] for i in test_idx], axis=0)

        # Objective is to maximize the mean performance (e.g. average IC or return)
        train_means = np.nanmean(train_matrix, axis=0)
        test_means = np.nanmean(test_matrix, axis=0)

        if np.all(np.isnan(train_means)) or np.all(np.isnan(test_means)):
            continue

        # Find the strategy that performed best in-sample
        best_is_strat = np.nanargmax(train_means)

        # Find the out-of-sample performance of that same strategy
        best_is_strat_oos_perf = test_means[best_is_strat]

        # Calculate the median performance of all strategies out-of-sample
        median_oos_perf = np.nanmedian(test_means)

        # Overfit condition: the optimal IS strategy performs worse than the median OOS
        if best_is_strat_oos_perf < median_oos_perf:
            overfit_count += 1

    return float(overfit_count / len(combinations))
