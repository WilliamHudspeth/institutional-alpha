"""Tests for the multiple-testing / selection-bias correction layer."""

from __future__ import annotations

import math

import numpy as np

from iam.backtest.multiple_testing import (
    correct_factor_tests,
    deflated_sharpe_ratio,
    effective_num_tests,
    expected_max_sharpe,
    min_track_record_length,
    probabilistic_sharpe_ratio,
    sharpe_standard_error,
)


# --------------------------------------------------------------------------- #
# PSR
# --------------------------------------------------------------------------- #
def test_psr_is_half_at_zero_sharpe():
    assert math.isclose(probabilistic_sharpe_ratio(0.0, 100), 0.5, abs_tol=1e-9)


def test_psr_monotonic_in_sharpe_and_n():
    base = probabilistic_sharpe_ratio(0.3, 60)
    assert probabilistic_sharpe_ratio(0.5, 60) > base  # higher SR -> higher PSR
    assert probabilistic_sharpe_ratio(0.3, 240) > base  # more data -> higher PSR


def test_psr_penalises_fat_tails():
    normal = probabilistic_sharpe_ratio(0.3, 60, skew=0.0, kurt=3.0)
    fat = probabilistic_sharpe_ratio(0.3, 60, skew=-1.0, kurt=8.0)
    assert fat < normal  # negative skew + fat kurtosis reduce confidence


def test_sharpe_se_matches_lo_formula_for_normal():
    # For a normal series, SE = sqrt((1 + 0.5*SR^2)/(n-1)).
    sr, n = 0.4, 50
    expected = math.sqrt((1 + 0.5 * sr**2) / (n - 1))
    assert math.isclose(sharpe_standard_error(sr, n), expected, rel_tol=1e-12)


def test_min_track_record_length_infinite_below_benchmark():
    assert min_track_record_length(0.0, sr_benchmark=0.1) == float("inf")
    assert min_track_record_length(0.5) > 0


# --------------------------------------------------------------------------- #
# Expected max + DSR
# --------------------------------------------------------------------------- #
def test_expected_max_sharpe_grows_with_trials():
    e10 = expected_max_sharpe(10, var_trials=0.04)
    e100 = expected_max_sharpe(100, var_trials=0.04)
    assert e100 > e10 > 0


def test_single_trial_has_no_deflation_bar():
    assert expected_max_sharpe(1, var_trials=0.04) == 0.0


def test_dsr_below_psr_under_selection():
    """Deflating for many trials lowers confidence vs the naive PSR."""
    psr = probabilistic_sharpe_ratio(0.4, 120)
    dsr = deflated_sharpe_ratio(0.4, n_obs=120, n_trials=50, var_trials=0.02)
    assert dsr < psr


def test_dsr_collapses_when_many_trials_and_modest_edge():
    # A modest IR that looks fine alone should lose significance after 200 trials.
    dsr = deflated_sharpe_ratio(0.30, n_obs=84, n_trials=200, var_trials=0.03)
    assert dsr < 0.95


def test_dsr_higher_with_effective_trials():
    """Using an effective_trials count smaller than n_trials mitigates over-deflation."""
    raw_dsr = deflated_sharpe_ratio(0.30, n_obs=84, n_trials=200, var_trials=0.03)
    eff_dsr = deflated_sharpe_ratio(
        0.30, n_obs=84, n_trials=200, var_trials=0.03, effective_trials=10.0
    )
    assert eff_dsr > raw_dsr


# --------------------------------------------------------------------------- #
# Effective number of tests
# --------------------------------------------------------------------------- #
def test_effective_tests_equals_k_when_independent():
    eye = np.eye(5)
    assert math.isclose(effective_num_tests(eye), 5.0, rel_tol=1e-9)


def test_effective_tests_collapses_to_one_when_fully_correlated():
    ones = np.ones((6, 6))  # rank-1 correlation -> one real dimension
    assert effective_num_tests(ones) < 1.5


def test_effective_tests_between_for_partial_correlation():
    rho = 0.5
    c = np.full((4, 4), rho)
    np.fill_diagonal(c, 1.0)
    eff = effective_num_tests(c)
    assert 1.0 < eff < 4.0


# --------------------------------------------------------------------------- #
# FWER / FDR corrections
# --------------------------------------------------------------------------- #
def test_holm_drops_a_factor_that_passes_naively():
    # t=2.1 passes |t|>2 alone (p~0.036) but should fail Holm among 12 factors
    # where everything else is noise.
    t_stats = {f"noise_{i}": 0.3 for i in range(11)}
    t_stats["lucky_factor"] = 2.1
    report = correct_factor_tests(t_stats, fwer_alpha=0.05)
    lucky = next(v for v in report.verdicts if v.name == "lucky_factor")
    assert lucky.raw_p < 0.05  # passes naive single-test gate
    assert not lucky.survives_holm  # fails family-wise correction
    assert report.notes  # report explains the drop


def test_genuinely_strong_factor_survives():
    t_stats = {f"noise_{i}": 0.2 for i in range(11)}
    t_stats["real_factor"] = 5.0  # p ~ 6e-7, survives correction
    report = correct_factor_tests(t_stats)
    real = next(v for v in report.verdicts if v.name == "real_factor")
    assert real.survives_holm
    assert real.survives_bh


def test_effective_tests_makes_holm_less_conservative():
    t_stats = {"a": 2.3, "b": 2.3, "c": 2.3, "d": 2.3}
    strict = correct_factor_tests(t_stats)  # treats all 4 as independent
    lenient = correct_factor_tests(t_stats, effective_tests=2.0)  # correlated
    # Fewer effective tests -> smaller Holm multiplier -> smaller adjusted p.
    a_strict = next(v for v in strict.verdicts if v.name == "a").holm_p
    a_lenient = next(v for v in lenient.verdicts if v.name == "a").holm_p
    assert a_lenient <= a_strict


def test_empty_input_is_safe():
    report = correct_factor_tests({})
    assert report.n_factors == 0
    assert report.survivors_holm == []


def test_compute_validation_metrics():
    import pandas as pd

    from iam.backtest.multiple_testing import compute_validation_metrics

    # Create mock DataFrame of ICs across dates
    dates = pd.date_range("2020-01-31", periods=15, freq="ME")
    # Simulate a strong factor "quality" and a noisy "momentum"
    # and a positive composite IC
    data = {
        "ic": np.random.normal(0.04, 0.01, 15),
        "ic_quality": np.random.normal(0.05, 0.02, 15),
        "ic_relative_value": np.random.normal(0.02, 0.03, 15),
        "ic_intrinsic_value": np.random.normal(0.01, 0.04, 15),
        "ic_momentum": np.random.normal(-0.01, 0.05, 15),
    }
    df = pd.DataFrame(data, index=dates)

    factor_names = ["quality", "relative_value", "intrinsic_value", "momentum"]
    metrics = compute_validation_metrics(df, factor_names)

    # Assert validation dataclass has valid numeric/bool fields
    assert not np.isnan(metrics.psr)
    assert not np.isnan(metrics.dsr)
    assert not np.isnan(metrics.pbo)
    assert not np.isnan(metrics.effective_tests)
    assert metrics.effective_tests > 0
    assert isinstance(metrics.fwer_significant_factors, int)
    assert isinstance(metrics.fdr_significant_factors, int)
