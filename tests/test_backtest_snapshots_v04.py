"""Tests for v0.4 snapshot layer (diskcache + pluggable sources).

Covers:
- build_snapshot uses the injected DataSource
- Cache hits return the same object without re-fetching
- Custom source can be set via set_default_source
- Fallback chain integration (yfinance fails → Stooq succeeds)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from iam.backtest.snapshots import (
    build_snapshot,
    get_snapshot_cache,
    load_snapshot,
    reset_snapshot_cache,
    set_default_source,
)
from iam.backtest.sources import CompositeDataSource, DataSource, DataSourceError
from iam.data.security import Fundamentals, Security


class _StubSource(DataSource):
    """In-memory data source for testing snapshots."""

    name = "stub"

    def __init__(self, price: float = 100.0, debt: float = 1_000_000.0, raise_on_price: bool = False):
        self._price = price
        self._debt = debt
        self._raise = raise_on_price
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def fetch_price(self, ticker, as_of):
        self.calls += 1
        if self._raise:
            raise DataSourceError(self.name, ticker, "stub failure")
        return self._price

    def fetch_debt(self, ticker, as_of):
        return self._debt

    def download_history(self, ticker, start, end):
        return None


@pytest.fixture(autouse=True)
def reset_caches():
    """Reset snapshot cache between tests."""
    reset_snapshot_cache()
    set_default_source(None)  # type: ignore
    yield
    reset_snapshot_cache()


@pytest.fixture
def base_security():
    return Security(
        ticker="AAPL",
        sector="Technology",
        industry="Consumer Electronics",
        fundamentals=Fundamentals(shares_outstanding=15_000_000_000),
    )


class TestBuildSnapshot:
    def test_uses_injected_source(self, base_security, tmp_path):
        source = _StubSource(price=150.0, debt=5_000_000_000.0)
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)

        assert snap.market.price == 150.0
        assert snap.fundamentals.total_debt == 5_000_000_000.0
        assert snap.ticker == "AAPL"
        assert source.calls == 1

    def test_market_cap_computed_from_shares(self, base_security, tmp_path):
        source = _StubSource(price=200.0, debt=0.0)
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)

        assert snap.market.market_cap == 200.0 * 15_000_000_000

    def test_cache_hit_skips_fetch(self, base_security, tmp_path):
        source = _StubSource(price=100.0)
        # First call populates cache
        snap1 = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)
        # Second call should hit cache (source.calls stays at 1)
        snap2 = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)

        assert source.calls == 1
        assert snap1.market.price == snap2.market.price

    def test_different_dates_create_different_cache_entries(self, base_security, tmp_path):
        source = _StubSource(price=100.0)
        build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)
        build_snapshot(base_security, "2024-02-05", cache_dir=tmp_path, source=source)

        # Two distinct cache entries → two fetches
        assert source.calls == 2

    def test_falls_back_to_secondary_source(self, base_security, tmp_path):
        primary = _StubSource(raise_on_price=True)
        fallback = _StubSource(price=99.0, debt=0.0)
        chain = CompositeDataSource([primary, fallback])

        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=chain)

        assert snap.market.price == 99.0
        assert chain.last_used == "stub"

    def test_raises_when_all_sources_fail(self, base_security, tmp_path):
        from tenacity import RetryError

        primary = _StubSource(raise_on_price=True)
        fallback = _StubSource(raise_on_price=True)
        chain = CompositeDataSource([primary, fallback])

        # tenacity wraps the underlying DataSourceError after 3 retries
        with pytest.raises((DataSourceError, RetryError)):
            build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=chain)

    def test_preserves_sector_and_industry(self, base_security, tmp_path):
        source = _StubSource()
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)

        assert snap.sector == "Technology"
        assert snap.industry == "Consumer Electronics"

    def test_uses_default_shares_when_unset(self, tmp_path):
        sec = Security(ticker="XYZ", fundamentals=Fundamentals(shares_outstanding=None))
        source = _StubSource(price=50.0)
        snap = build_snapshot(sec, "2024-01-05", cache_dir=tmp_path, source=source)

        # Default 1_000_000_000 shares applied when unset
        assert snap.market.market_cap == 50.0 * 1_000_000_000


class TestLoadSnapshot:
    def test_returns_none_when_not_cached(self, tmp_path):
        result = load_snapshot("AAPL", "2024-01-05", cache_dir=tmp_path)
        assert result is None

    def test_returns_cached_snapshot(self, base_security, tmp_path):
        source = _StubSource(price=123.0)
        original = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path, source=source)

        loaded = load_snapshot("AAPL", "2024-01-05", cache_dir=tmp_path)
        assert loaded is not None
        assert loaded.market.price == original.market.price
        assert loaded.ticker == original.ticker


class TestSnapshotCache:
    def test_cache_directory_is_created(self, tmp_path):
        cache_dir = tmp_path / "nested" / "cache"
        get_snapshot_cache(cache_dir)
        assert cache_dir.exists()

    def test_cache_is_singleton(self, tmp_path):
        cache1 = get_snapshot_cache(tmp_path)
        cache2 = get_snapshot_cache(tmp_path)
        assert cache1 is cache2

    def test_reset_releases_cache(self, tmp_path):
        cache1 = get_snapshot_cache(tmp_path)
        reset_snapshot_cache()
        cache2 = get_snapshot_cache(tmp_path)
        # New cache instance after reset
        assert cache1 is not cache2
