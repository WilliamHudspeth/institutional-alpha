"""Point-in-time (PIT) security snapshots with diskcache and pluggable data sources.

Builds immutable Security objects as they existed on a specific date, freezing
price and debt data. Uses diskcache for persistence and delegates data fetching
to the pluggable `sources` package (default: yfinance → Stooq fallback).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

import pandas as pd
from diskcache import Cache
from tenacity import retry, stop_after_attempt, wait_exponential

from iam.data.security import Security, MarketData
from iam.backtest.sources import DataSource, default_chain


# Global cache singleton
_snapshot_cache: Optional[Cache] = None
_default_source: Optional[DataSource] = None


def get_snapshot_cache(cache_dir: Path) -> Cache:
    """Get or create the global diskcache for snapshots."""
    global _snapshot_cache
    if _snapshot_cache is None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _snapshot_cache = Cache(str(cache_dir))
    return _snapshot_cache


def reset_snapshot_cache() -> None:
    """Reset the global snapshot cache (used in tests)."""
    global _snapshot_cache
    if _snapshot_cache is not None:
        _snapshot_cache.close()
    _snapshot_cache = None


def get_default_source() -> DataSource:
    """Get or build the default yfinance → Stooq fallback chain."""
    global _default_source
    if _default_source is None:
        _default_source = default_chain()
    return _default_source


def set_default_source(source: DataSource) -> None:
    """Override the default data source (used in tests and for custom chains)."""
    global _default_source
    _default_source = source


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _fetch_snapshot_data(
    ticker: str,
    as_of: pd.Timestamp,
    source: DataSource,
) -> tuple[float, float]:
    """Fetch price and debt via the provided data source.

    Args:
        ticker: Stock ticker
        as_of: Target date
        source: DataSource (typically a CompositeDataSource fallback chain)

    Returns:
        Tuple of (price, debt). Debt is 0.0 if unavailable.

    Raises:
        DataSourceError: If price cannot be obtained from any source.
    """
    price = source.fetch_price(ticker, as_of)
    debt = source.fetch_debt(ticker, as_of)
    return price, debt


def build_snapshot(
    base: Security,
    as_of: str,  # YYYY-MM-DD
    cache_dir: Path = Path(".cache/snapshots"),
    source: Optional[DataSource] = None,
) -> Security:
    """Build a point-in-time Security snapshot for a specific date.

    Args:
        base: Base Security with sector, industry, revenue_mix, shares_outstanding
        as_of: Date string (YYYY-MM-DD)
        cache_dir: Directory for diskcache persistence
        source: Optional DataSource override (default: yfinance → Stooq chain)

    Returns:
        New Security object with market_cap and total_debt frozen for as_of
    """
    ticker = base.ticker
    as_of_dt = pd.Timestamp(as_of)
    cache_key = f"{ticker}_{as_of}"

    cache = get_snapshot_cache(cache_dir)
    if cache_key in cache:
        return cache[cache_key]

    src = source if source is not None else get_default_source()
    price, debt = _fetch_snapshot_data(ticker, as_of_dt, src)

    shares = base.fundamentals.shares_outstanding if base.fundamentals.shares_outstanding else 1_000_000_000
    market_cap = price * shares

    snapshot = replace(
        base,
        market=MarketData(price=price, market_cap=market_cap),
        fundamentals=replace(base.fundamentals, total_debt=debt),
    )

    cache[cache_key] = snapshot
    return snapshot


def load_snapshot(
    ticker: str,
    as_of: str,
    cache_dir: Path = Path(".cache/snapshots"),
) -> Optional[Security]:
    """Load a cached snapshot if available, else None."""
    cache_key = f"{ticker}_{as_of}"
    cache = get_snapshot_cache(cache_dir)
    if cache_key in cache:
        return cache[cache_key]
    return None
