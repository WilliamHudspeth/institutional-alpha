"""Tests for Probability of Backtest Overfitting (PBO)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from iam.backtest.overfitting import probability_of_backtest_overfitting


def test_pbo_with_noise_is_around_half():
    """A matrix of pure noise should have a PBO around 0.5.
    
    If all strategies are just random noise, the "best" in-sample strategy
    has no predictive power out-of-sample, so it should underperform the median
    out-of-sample strategy about 50% of the time.
    """
    np.random.seed(42)
    # 60 periods, 100 strategies
    noise_matrix = np.random.randn(60, 100)
    pbo = probability_of_backtest_overfitting(noise_matrix, n_partitions=16)
    
    # It won't be exactly 0.5 due to finite sample size, but close.
    assert 0.3 <= pbo <= 0.7


def test_pbo_with_true_signal_is_low():
    """If one strategy is genuinely superior, PBO should be near 0."""
    np.random.seed(42)
    m = np.random.randn(60, 10)
    
    # Inject a true signal into strategy 0
    m[:, 0] += 2.0  # consistently better
    
    pbo = probability_of_backtest_overfitting(m, n_partitions=16)
    assert pbo < 0.1


def test_pbo_raises_on_odd_partitions():
    with pytest.raises(ValueError, match="must be an even number"):
        probability_of_backtest_overfitting(np.zeros((20, 5)), n_partitions=3)


def test_pbo_raises_on_insufficient_periods():
    with pytest.raises(ValueError, match="Not enough observations"):
        probability_of_backtest_overfitting(np.zeros((10, 5)), n_partitions=16)


def test_pbo_returns_zero_for_single_strategy():
    """Cannot overfit if there's no choice of strategy."""
    m = np.random.randn(20, 1)
    assert probability_of_backtest_overfitting(m, n_partitions=4) == 0.0
