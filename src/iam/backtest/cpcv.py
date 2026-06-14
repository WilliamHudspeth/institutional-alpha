"""Combinatorial Purged Cross-Validation (CPCV) layer.

Implements chronological dataset splitting with purging and embargoing
to prevent temporal leakage and lookahead bias in cross-validation.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd


def get_cpcv_splits(
    dates: list[pd.Timestamp] | pd.DatetimeIndex,
    n_groups: int = 6,
    k_test_groups: int = 2,
    purge_days: int = 0,
    embargo_days: int = 0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate Combinatorial Purged Cross-Validation train/test splits.

    Divides chronological dates into `n_groups`. Forms all combinations of
    `k_test_groups` for testing, using the remainder for training.
    Purges any training dates that fall within `purge_days` of any test date.
    Applies an `embargo_days` window exclusively after the test dates to
    prevent forward temporal leakage.

    Args:
        dates: A sorted chronological list of evaluation dates.
        n_groups: Total number of chronological groups to split dates into.
        k_test_groups: Number of groups to use for testing in each split.
        purge_days: Number of days to purge from the training set before and
            after any test observations.
        embargo_days: Number of extra days to purge from the training set
            immediately following any test group.

    Returns:
        A list of (train_indices, test_indices) tuples.
    """
    if not isinstance(dates, (pd.DatetimeIndex, list)):
        dates = pd.DatetimeIndex(dates)
    elif isinstance(dates, list):
        dates = pd.to_datetime(dates)

    if not dates.is_monotonic_increasing:
        dates = dates.sort_values()

    n = len(dates)
    if n < n_groups:
        raise ValueError(f"Too few dates ({n}) for {n_groups} groups")
    if k_test_groups >= n_groups or k_test_groups < 1:
        raise ValueError(f"k_test_groups must be between 1 and {n_groups - 1}")

    # Divide indices into n_groups
    indices = np.arange(n)
    groups = np.array_split(indices, n_groups)

    splits = []
    group_indices = set(range(n_groups))
    combinations = list(itertools.combinations(group_indices, k_test_groups))

    purge_td = pd.Timedelta(days=purge_days)
    embargo_td = pd.Timedelta(days=embargo_days)

    for test_idx_tuple in combinations:
        # Collect test indices
        test_mask = np.zeros(n, dtype=bool)
        for g in test_idx_tuple:
            test_mask[groups[g]] = True
        test_indices = indices[test_mask]

        if len(test_indices) == 0:
            continue

        # Start with all remaining dates as training candidates
        train_mask = ~test_mask
        train_indices_initial = indices[train_mask]

        # Iterate over continuous blocks of test dates
        # Since groups are contiguous, a test group is a contiguous block
        for g in test_idx_tuple:
            test_block = groups[g]
            if len(test_block) == 0:
                continue

            first_test_date = dates[test_block[0]]
            last_test_date = dates[test_block[-1]]

            # Define invalid boundaries for this test block
            purge_start = first_test_date - purge_td
            # embargo is added to the purge window after the test set
            purge_end = last_test_date + purge_td + embargo_td

            # Apply purging/embargoing to the training mask
            for t_idx in train_indices_initial:
                # If the training date falls inside the purge/embargo window, mark it invalid
                if purge_start <= dates[t_idx] <= purge_end:
                    train_mask[t_idx] = False

        final_train_indices = indices[train_mask]
        splits.append((final_train_indices, test_indices))

    return splits
