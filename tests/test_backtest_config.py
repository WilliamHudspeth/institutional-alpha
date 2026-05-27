"""Tests for BacktestConfig (Pydantic frozen, typed configuration)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from iam.backtest.config import BacktestConfig


class TestBacktestConfigDefaults:
    def test_defaults_are_sensible(self):
        cfg = BacktestConfig()
        assert cfg.universe_name == "sp100"
        assert cfg.horizon_days == 63
        assert cfg.cost_bps == 5.0
        assert cfg.n_jobs_cpu >= 1
        assert cfg.data_root == Path("data")

    def test_is_frozen_immutable(self):
        cfg = BacktestConfig()
        with pytest.raises(ValidationError):
            cfg.universe_name = "russell3000"  # type: ignore

    def test_path_properties_are_relative_to_data_root(self):
        cfg = BacktestConfig(universe_name="custom")
        assert cfg.price_file == Path("data/prices/custom.parquet")
        assert cfg.universe_file == Path("data/universe/custom.json")
        assert cfg.results_dir == Path("data/results")


class TestBacktestConfigValidation:
    def test_horizon_days_must_be_positive(self):
        with pytest.raises(ValidationError):
            BacktestConfig(horizon_days=0)
        with pytest.raises(ValidationError):
            BacktestConfig(horizon_days=-1)

    def test_cost_bps_must_be_nonnegative(self):
        # Zero is allowed (no transaction costs)
        cfg = BacktestConfig(cost_bps=0.0)
        assert cfg.cost_bps == 0.0

        with pytest.raises(ValidationError):
            BacktestConfig(cost_bps=-5.0)

    def test_n_jobs_must_be_positive(self):
        with pytest.raises(ValidationError):
            BacktestConfig(n_jobs_cpu=0)
        with pytest.raises(ValidationError):
            BacktestConfig(n_jobs_io=-1)

    def test_timeouts_must_be_positive(self):
        with pytest.raises(ValidationError):
            BacktestConfig(yfinance_timeout=0.0)
        with pytest.raises(ValidationError):
            BacktestConfig(stooq_timeout=0.5)  # less than minimum 1.0


class TestBacktestConfigPaths:
    def test_validate_paths_creates_directories(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path / "data", cache_dir=tmp_path / "cache")
        cfg.validate_paths()

        assert (tmp_path / "data").exists()
        assert (tmp_path / "cache").exists()
        assert (tmp_path / "cache" / "snapshots").exists()
        assert (tmp_path / "data" / "results").exists()
        assert (tmp_path / "data" / "prices").exists()
        assert (tmp_path / "data" / "universe").exists()

    def test_validate_paths_idempotent(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path / "data", cache_dir=tmp_path / "cache")
        cfg.validate_paths()
        # Second call should not fail (mkdir exist_ok=True)
        cfg.validate_paths()

    def test_snapshot_cache_path(self, tmp_path):
        cfg = BacktestConfig(cache_dir=tmp_path / "my_cache")
        assert cfg.snapshot_cache == tmp_path / "my_cache" / "snapshots"


class TestBacktestConfigCustom:
    def test_override_specific_fields(self):
        cfg = BacktestConfig(
            universe_name="russell1000",
            horizon_days=252,
            cost_bps=10.0,
            n_jobs_cpu=8,
        )
        assert cfg.universe_name == "russell1000"
        assert cfg.horizon_days == 252
        assert cfg.cost_bps == 10.0
        assert cfg.n_jobs_cpu == 8
        # Defaults preserved for other fields
        assert cfg.freq == "ME"

    def test_model_dump_serializable(self):
        cfg = BacktestConfig()
        dumped = cfg.model_dump()
        assert "universe_name" in dumped
        assert "horizon_days" in dumped
        assert "data_root" in dumped
