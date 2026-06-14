"""Tests for Combinatorial Purged Cross-Validation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from iam.backtest.cpcv import get_cpcv_splits


def test_cpcv_generates_correct_number_of_splits():
    dates = pd.date_range("2010-01-01", periods=120, freq="ME")
    n_groups = 6
    k = 2
    splits = get_cpcv_splits(dates, n_groups=n_groups, k_test_groups=k)

    # C(6, 2) = 15 splits
    expected_splits = math.comb(n_groups, k)
    assert len(splits) == expected_splits


def test_cpcv_purges_and_embargoes_correctly():
    # 3 groups of 5 days each
    dates = pd.date_range("2020-01-01", periods=15, freq="D")

    # Let's test with n_groups=3, k=1. Groups: [0-4], [5-9], [10-14]
    # We add 1 day purge and 2 days embargo
    splits = get_cpcv_splits(dates, n_groups=3, k_test_groups=1, purge_days=1, embargo_days=2)
    assert len(splits) == 3

    # Split 0: Test group is 0 (dates 0-4).
    # Purge: date -1 (doesn't exist).
    # Embargo + Purge after: dates 5, 6, 7 should be purged from training.
    # Train should be: dates 8-14
    train_0, test_0 = splits[0]
    assert np.array_equal(test_0, np.arange(0, 5))
    assert np.array_equal(train_0, np.arange(8, 15))

    # Split 1: Test group is 1 (dates 5-9).
    # Purge before: date 4.
    # Embargo + Purge after: dates 10, 11, 12.
    # Train should be: dates 0-3, and 13-14.
    train_1, test_1 = splits[1]
    assert np.array_equal(test_1, np.arange(5, 10))
    expected_train_1 = np.concatenate([np.arange(0, 4), np.arange(13, 15)])
    assert np.array_equal(train_1, expected_train_1)


def test_cpcv_raises_on_invalid_parameters():
    dates = pd.date_range("2020-01-01", periods=10, freq="D")

    with pytest.raises(ValueError, match="Too few dates"):
        get_cpcv_splits(dates, n_groups=12)

    with pytest.raises(ValueError, match="k_test_groups must be between"):
        get_cpcv_splits(dates, n_groups=4, k_test_groups=4)
