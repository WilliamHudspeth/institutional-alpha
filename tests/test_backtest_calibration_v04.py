"""Tests for v0.4 Bayesian shrinkage calibration."""

from __future__ import annotations

import numpy as np
import pytest

from iam.backtest.calibration import (
    ic_to_reliability,
    ic_to_reliability_bayesian,
)


class TestICToReliabilityBayesian:
    def test_returns_expected_keys(self):
        result = ic_to_reliability_bayesian(ic_mean=0.03, ic_std=0.05, n_obs=84)
        assert "prior_ic" in result
        assert "empirical_ic" in result
        assert "posterior_ic" in result
        assert "posterior_std" in result
        assert "reliability" in result
        assert "shrinkage_factor" in result

    def test_zero_observations_returns_prior(self):
        result = ic_to_reliability_bayesian(
            ic_mean=0.10, ic_std=0.05, n_obs=0, prior_ic=0.02, prior_strength=36
        )
        # No data → posterior == prior
        assert result["posterior_ic"] == pytest.approx(0.02)
        assert result["shrinkage_factor"] == 0.0

    def test_infinite_observations_converges_to_empirical(self):
        result = ic_to_reliability_bayesian(
            ic_mean=0.10, ic_std=0.05, n_obs=10_000, prior_ic=0.02, prior_strength=36
        )
        # Lots of data → posterior ≈ empirical
        assert result["posterior_ic"] == pytest.approx(0.10, abs=0.01)
        assert result["shrinkage_factor"] > 0.99

    def test_equal_weighting_at_prior_strength(self):
        # n_obs == prior_strength → posterior is midpoint
        result = ic_to_reliability_bayesian(
            ic_mean=0.10, ic_std=0.05, n_obs=36, prior_ic=0.02, prior_strength=36
        )
        # Midpoint of 0.02 and 0.10 = 0.06
        assert result["posterior_ic"] == pytest.approx(0.06)
        assert result["shrinkage_factor"] == pytest.approx(0.5)

    def test_reliability_bounded_by_clamp(self):
        # Extreme empirical IC should still produce clamped reliability
        result = ic_to_reliability_bayesian(
            ic_mean=10.0, ic_std=0.01, n_obs=84, prior_ic=0.02, prior_strength=36
        )
        assert result["reliability"] <= 0.95
        assert result["reliability"] >= 0.50

    def test_negative_ic_pushes_toward_floor(self):
        result = ic_to_reliability_bayesian(
            ic_mean=-0.10, ic_std=0.05, n_obs=10_000, prior_ic=0.02, prior_strength=36
        )
        # With huge n_obs, posterior should approach -0.10, reliability clamped to 0.50
        assert result["reliability"] == pytest.approx(0.50)

    def test_shrinkage_factor_in_unit_interval(self):
        result = ic_to_reliability_bayesian(
            ic_mean=0.05, ic_std=0.05, n_obs=84, prior_ic=0.02, prior_strength=36
        )
        assert 0 <= result["shrinkage_factor"] <= 1

    def test_short_history_yields_more_shrinkage(self):
        short = ic_to_reliability_bayesian(
            ic_mean=0.10, ic_std=0.05, n_obs=12, prior_ic=0.02, prior_strength=36
        )
        long = ic_to_reliability_bayesian(
            ic_mean=0.10, ic_std=0.05, n_obs=120, prior_ic=0.02, prior_strength=36
        )
        # Short history → more shrinkage → posterior closer to prior
        assert short["posterior_ic"] < long["posterior_ic"]

    def test_custom_prior(self):
        # Use a more bullish prior (0.05 instead of 0.02)
        result = ic_to_reliability_bayesian(
            ic_mean=0.05, ic_std=0.05, n_obs=36, prior_ic=0.05, prior_strength=36
        )
        # If prior = empirical, posterior = both
        assert result["posterior_ic"] == pytest.approx(0.05)


class TestICToReliabilityLinear:
    """Verify backward compatibility of the linear (non-Bayesian) calibration."""

    def test_zero_ic_yields_half(self):
        assert ic_to_reliability(0.0) == pytest.approx(0.50)

    def test_moderate_ic(self):
        # IC=0.05 → 0.5 + 0.25 = 0.75
        assert ic_to_reliability(0.05) == pytest.approx(0.75)

    def test_clamped_upper(self):
        assert ic_to_reliability(1.0) == pytest.approx(0.95)

    def test_clamped_lower(self):
        assert ic_to_reliability(-1.0) == pytest.approx(0.50)


class TestCalibrationConsistency:
    """Bayesian and linear should agree at large n_obs."""

    def test_large_n_bayesian_matches_linear(self):
        ic = 0.05
        linear = ic_to_reliability(ic)
        bayesian = ic_to_reliability_bayesian(ic, 0.05, n_obs=10_000)["reliability"]
        assert bayesian == pytest.approx(linear, abs=0.01)
