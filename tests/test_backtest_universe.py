"""Tests for universe.py (static JSON universe loader with hash verification)."""

from __future__ import annotations

import json

import pytest

from iam.backtest.universe import load_universe_from_json, load_universe_tickers


class TestLoadUniverseFromJson:
    def test_loads_securities_format(self, tmp_path):
        universe_path = tmp_path / "universe.json"
        data = {
            "universe": "test",
            "date": "2024-12-31",
            "tickers": ["AAPL", "MSFT"],
            "securities": [
                {
                    "ticker": "AAPL",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "revenue_mix": {"US": 0.6, "INTL": 0.4},
                },
                {
                    "ticker": "MSFT",
                    "sector": "Technology",
                    "industry": "Software",
                    "revenue_mix": {"US": 0.5, "INTL": 0.5},
                },
            ],
        }
        universe_path.write_text(json.dumps(data))

        securities, file_hash = load_universe_from_json(universe_path)

        assert len(securities) == 2
        assert securities[0].ticker == "AAPL"
        assert securities[0].sector == "Technology"
        assert securities[1].ticker == "MSFT"
        # Hash is 12-character hex prefix
        assert len(file_hash) == 12

    def test_loads_tickers_only_format(self, tmp_path):
        universe_path = tmp_path / "universe.json"
        data = {"tickers": ["AAPL", "MSFT", "GOOGL"]}
        universe_path.write_text(json.dumps(data))

        securities, file_hash = load_universe_from_json(universe_path)

        assert len(securities) == 3
        assert [s.ticker for s in securities] == ["AAPL", "MSFT", "GOOGL"]
        # Minimal Security objects should have placeholders
        for s in securities:
            assert s.sector == "Unknown"

    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_universe_from_json(tmp_path / "missing.json")

    def test_raises_for_invalid_format(self, tmp_path):
        universe_path = tmp_path / "universe.json"
        universe_path.write_text(json.dumps({"foo": "bar"}))

        with pytest.raises(ValueError):
            load_universe_from_json(universe_path)

    def test_hash_changes_with_content(self, tmp_path):
        p1 = tmp_path / "u1.json"
        p2 = tmp_path / "u2.json"
        p1.write_text(json.dumps({"tickers": ["AAPL"]}))
        p2.write_text(json.dumps({"tickers": ["MSFT"]}))

        _, h1 = load_universe_from_json(p1)
        _, h2 = load_universe_from_json(p2)

        assert h1 != h2

    def test_hash_stable_for_same_content(self, tmp_path):
        p1 = tmp_path / "u1.json"
        p2 = tmp_path / "u2.json"
        same_content = json.dumps({"tickers": ["AAPL"]})
        p1.write_text(same_content)
        p2.write_text(same_content)

        _, h1 = load_universe_from_json(p1)
        _, h2 = load_universe_from_json(p2)

        assert h1 == h2


class TestLoadUniverseTickers:
    def test_from_tickers_key(self, tmp_path):
        universe_path = tmp_path / "u.json"
        universe_path.write_text(json.dumps({"tickers": ["AAPL", "MSFT"]}))

        tickers = load_universe_tickers(universe_path)
        assert tickers == ["AAPL", "MSFT"]

    def test_from_securities_key(self, tmp_path):
        universe_path = tmp_path / "u.json"
        data = {"securities": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]}
        universe_path.write_text(json.dumps(data))

        tickers = load_universe_tickers(universe_path)
        assert tickers == ["AAPL", "MSFT"]

    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_universe_tickers(tmp_path / "missing.json")

    def test_raises_for_invalid_format(self, tmp_path):
        p = tmp_path / "u.json"
        p.write_text(json.dumps({"foo": "bar"}))

        with pytest.raises(ValueError):
            load_universe_tickers(p)
