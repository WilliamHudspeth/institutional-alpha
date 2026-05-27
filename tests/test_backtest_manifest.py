"""Tests for BacktestManifest (git SHA + file hashes for reproducibility)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from iam.backtest.config import BacktestConfig
from iam.backtest.manifest import BacktestManifest


class TestBacktestManifest:
    def test_creates_manifest_with_git_sha(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)
        assert manifest.git_sha is not None
        assert len(manifest.git_sha) >= 6 or manifest.git_sha == "unknown"

    def test_unknown_sha_when_git_unavailable(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)

        with patch("subprocess.check_output", side_effect=FileNotFoundError):
            manifest = BacktestManifest(cfg)
            assert manifest.git_sha == "unknown"

    def test_timestamp_is_iso_format(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)
        # Should parse as ISO datetime
        from datetime import datetime
        parsed = datetime.fromisoformat(manifest.timestamp)
        assert parsed.year >= 2024

    def test_file_hashes_for_existing_files(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)

        # At least one backtest module file should be hashed
        backtest_files = [
            k for k in manifest.file_hashes.keys() if "backtest" in k
        ]
        assert len(backtest_files) > 0

        # Each hash should be a hex string of fixed length (12 chars truncated)
        for path, hash_val in manifest.file_hashes.items():
            assert len(hash_val) == 12
            assert all(c in "0123456789abcdef" for c in hash_val)

    def test_to_dict_structure(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)
        d = manifest.to_dict()

        assert "_meta" in d
        assert "config" in d
        assert "file_hashes" in d
        assert d["_meta"]["version"] == "v0.4.0"
        assert "git_sha" in d["_meta"]
        assert "timestamp" in d["_meta"]

    def test_write_creates_json_file(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)
        out = tmp_path / "manifest.json"
        manifest.write(out)

        assert out.exists()
        with open(out) as f:
            loaded = json.load(f)
        assert loaded["_meta"]["version"] == "v0.4.0"

    def test_write_creates_parent_directory(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)
        out = tmp_path / "nested" / "deep" / "manifest.json"
        manifest.write(out)
        assert out.exists()

    def test_load_roundtrip(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        manifest = BacktestManifest(cfg)
        out = tmp_path / "manifest.json"
        manifest.write(out)

        loaded = BacktestManifest.load(out)
        assert loaded["_meta"]["version"] == "v0.4.0"
        assert loaded["_meta"]["git_sha"] == manifest.git_sha

    def test_load_missing_file_returns_empty(self, tmp_path):
        result = BacktestManifest.load(tmp_path / "nonexistent.json")
        assert result == {}

    def test_universe_file_hashed_when_present(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        cfg.validate_paths()

        # Create the universe file
        cfg.universe_file.write_text('{"tickers": ["AAPL", "MSFT"]}')

        manifest = BacktestManifest(cfg)
        assert str(cfg.universe_file) in manifest.file_hashes

    def test_price_file_hashed_when_present(self, tmp_path):
        cfg = BacktestConfig(data_root=tmp_path)
        cfg.validate_paths()
        # Create a placeholder file
        cfg.price_file.write_bytes(b"fake parquet data")

        manifest = BacktestManifest(cfg)
        assert str(cfg.price_file) in manifest.file_hashes
