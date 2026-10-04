"""Point-in-time snapshot layer: injected fetchers, caching, fallback, honest gaps.

Ported (intent only) from the May-2026 ``test_backtest_snapshots_v04.py``, which was
written against a DataSource API that no longer exists. Fakes are injected through
``set_default_fetcher`` or ``build_snapshot(fetcher=...)``; nothing touches the network.
"""

from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
import pytest

from iam.backtest import snapshots
from iam.backtest.snapshots import (
    build_snapshot,
    get_default_fetcher,
    get_snapshot_cache,
    load_snapshot,
    reset_snapshot_cache,
    set_default_fetcher,
)
from iam.data.fetcher import DataConfig, RedundantDataFetcher
from iam.data.security import Fundamentals, Security


class _FakeSource:
    """Stands in for one entry of ``RedundantDataFetcher.sources``."""

    def __init__(
        self,
        price: float = 100.0,
        fundamentals: dict | None = None,
        fail_prices: bool = False,
    ):
        self._price = price
        self._fundamentals = {"totalDebt": 1_000_000.0} if fundamentals is None else fundamentals
        self._fail = fail_prices
        self.price_calls = 0

    def get_price_history(self, ticker: str, start: datetime, end: datetime) -> pd.Series:
        self.price_calls += 1
        if self._fail:
            raise RuntimeError("fake price failure")
        return pd.Series(
            [self._price - 1.0, self._price],
            index=pd.to_datetime([end - pd.Timedelta(days=1), end]),
        )

    def get_fundamentals(self, ticker: str, as_of: datetime) -> dict:
        return self._fundamentals


def _fetcher(**sources: _FakeSource) -> RedundantDataFetcher:
    """A real RedundantDataFetcher (real fallback logic) wired to fake sources only."""
    f = RedundantDataFetcher.__new__(RedundantDataFetcher)
    cfg = DataConfig()
    cfg.price_sources = list(sources)
    cfg.fundamental_sources = list(sources)
    f.config = cfg
    f.sources = dict(sources)
    return f


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Reset the module-level cache and fetcher around every test; skip retry sleeps."""
    reset_snapshot_cache()
    monkeypatch.setattr(snapshots, "_default_fetcher", None)
    monkeypatch.setattr("iam.data.retry.time.sleep", lambda _s: None)
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
    def test_uses_injected_fetcher(self, base_security, tmp_path):
        src = _FakeSource(price=150.0, fundamentals={"totalDebt": 5_000_000_000.0})
        set_default_fetcher(_fetcher(fake=src))
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

        assert snap.market.price == 150.0
        assert snap.fundamentals.total_debt == 5_000_000_000.0
        assert snap.ticker == "AAPL"
        assert src.price_calls == 1

    def test_fetcher_parameter_overrides_default(self, base_security, tmp_path):
        default_src = _FakeSource(price=1.0)
        param_src = _FakeSource(price=2.0)
        set_default_fetcher(_fetcher(fake=default_src))
        snap = build_snapshot(
            base_security, "2024-01-05", cache_dir=tmp_path, fetcher=_fetcher(fake=param_src)
        )

        assert snap.market.price == 2.0
        assert default_src.price_calls == 0

    def test_set_default_fetcher_is_returned_by_getter(self):
        f = _fetcher(fake=_FakeSource())
        set_default_fetcher(f)
        assert get_default_fetcher() is f

    def test_market_cap_computed_from_shares(self, base_security, tmp_path):
        set_default_fetcher(
            _fetcher(fake=_FakeSource(price=200.0, fundamentals={"totalDebt": 0.0}))
        )
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

        assert snap.market.market_cap == 200.0 * 15_000_000_000

    def test_cache_hit_skips_fetch(self, base_security, tmp_path):
        src = _FakeSource(price=100.0)
        set_default_fetcher(_fetcher(fake=src))
        snap1 = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)
        snap2 = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

        assert src.price_calls == 1
        assert snap1.market.price == snap2.market.price

    def test_different_dates_create_different_cache_entries(self, base_security, tmp_path):
        src = _FakeSource(price=100.0)
        set_default_fetcher(_fetcher(fake=src))
        build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)
        build_snapshot(base_security, "2024-02-05", cache_dir=tmp_path)

        assert src.price_calls == 2

    def test_falls_back_to_secondary_source(self, base_security, tmp_path):
        primary = _FakeSource(fail_prices=True)
        secondary = _FakeSource(price=99.0, fundamentals={"totalDebt": 0.0})
        set_default_fetcher(_fetcher(primary=primary, secondary=secondary))

        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

        assert snap.market.price == 99.0
        assert primary.price_calls == 1
        assert secondary.price_calls == 1

    def test_all_sources_failing_gives_missing_price_not_a_number(self, base_security, tmp_path):
        # May raised (DataSourceError/RetryError). Current code swallows the failure and
        # records a NaN price; price and market cap must never look like computed values.
        set_default_fetcher(
            _fetcher(a=_FakeSource(fail_prices=True), b=_FakeSource(fail_prices=True))
        )
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

        assert snap.market.price is not None and math.isnan(snap.market.price)
        assert snap.market.market_cap is not None and math.isnan(snap.market.market_cap)

    def test_preserves_sector_and_industry(self, base_security, tmp_path):
        set_default_fetcher(_fetcher(fake=_FakeSource()))
        snap = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

        assert snap.sector == "Technology"
        assert snap.industry == "Consumer Electronics"


class TestLoadSnapshot:
    def test_returns_none_when_not_cached(self, tmp_path):
        assert load_snapshot("AAPL", "2024-01-05", cache_dir=tmp_path) is None

    def test_returns_cached_snapshot(self, base_security, tmp_path):
        set_default_fetcher(_fetcher(fake=_FakeSource(price=123.0)))
        original = build_snapshot(base_security, "2024-01-05", cache_dir=tmp_path)

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
        assert get_snapshot_cache(tmp_path) is get_snapshot_cache(tmp_path)

    def test_reset_releases_cache(self, tmp_path):
        cache1 = get_snapshot_cache(tmp_path)
        reset_snapshot_cache()
        cache2 = get_snapshot_cache(tmp_path)
        assert cache1 is not cache2
