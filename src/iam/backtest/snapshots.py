"""Point-in-time (PIT) security snapshots with diskcache and pluggable data sources.

Builds immutable Security objects as they existed on a specific date, freezing
price and debt data. Uses diskcache for persistence and delegates data fetching
to the pluggable `fetcher` package (RedundantDataFetcher).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
from diskcache import Cache
from tenacity import retry, stop_after_attempt, wait_exponential

from iam.data.fetcher import RedundantDataFetcher
from iam.data.security import MarketData, Security

# Global cache singleton
_snapshot_cache: Cache | None = None
_default_fetcher: RedundantDataFetcher | None = None


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


def get_default_fetcher() -> RedundantDataFetcher:
    """Get or build the default RedundantDataFetcher."""
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = RedundantDataFetcher()
    return _default_fetcher


def set_default_fetcher(fetcher: RedundantDataFetcher) -> None:
    """Override the default data fetcher (used in tests)."""
    global _default_fetcher
    _default_fetcher = fetcher


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _fetch_snapshot_data(
    ticker: str,
    as_of: pd.Timestamp,
    fetcher: RedundantDataFetcher,
) -> tuple[float, float]:
    """Fetch price and debt via the provided RedundantDataFetcher.

    Args:
        ticker: Stock ticker
        as_of: Target date
        fetcher: RedundantDataFetcher

    Returns:
        Tuple of (price, debt). Debt is 0.0 if unavailable.
    """
    as_of_dt = as_of.to_pydatetime()
    # Fetch a small window of prices to handle weekends/holidays
    start_dt = as_of_dt - pd.Timedelta(days=7)
    prices = fetcher.fetch_price_history(ticker, start_dt, as_of_dt)

    if prices.empty:
        raise ValueError(f"No price data available for {ticker} around {as_of}")

    valid_prices = prices[prices.index <= as_of_dt]
    if valid_prices.empty:
        raise ValueError(f"No valid price data on or before {as_of} for {ticker}")

    price = float(valid_prices.iloc[-1])

    fundamentals = fetcher.fetch_fundamentals(ticker, as_of_dt)
    # Map Liabilities or totalDebt depending on what's available
    debt = float(fundamentals.get('Liabilities', fundamentals.get('totalDebt', 0.0)))

    return price, debt


def build_snapshot(
    base: Security,
    as_of: str,  # YYYY-MM-DD
    cache_dir: Path = Path(".cache/snapshots"),
    fetcher: RedundantDataFetcher | None = None,
) -> Security:
    """Build a point-in-time Security snapshot for a specific date.

    Args:
        base: Base Security with sector, industry, revenue_mix, shares_outstanding
        as_of: Date string (YYYY-MM-DD)
        cache_dir: Directory for diskcache persistence
        fetcher: Optional fetcher override

    Returns:
        New Security object with market_cap and total_debt frozen for as_of
    """
    ticker = base.ticker
    as_of_dt = pd.Timestamp(as_of)
    cache_key = f"{ticker}_{as_of}"

    cache = get_snapshot_cache(cache_dir)
    if cache_key in cache:
        return cache[cache_key]

    src = fetcher if fetcher is not None else get_default_fetcher()
    try:
        price, debt = _fetch_snapshot_data(ticker, as_of_dt, src)
    except Exception:
        # Fallback to base or nan
        price = float('nan')
        debt = 0.0

    shares = (
        base.fundamentals.shares_outstanding
        if base.fundamentals.shares_outstanding
        else 1_000_000_000
    )
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
) -> Security | None:
    """Load a cached snapshot if available, else None."""
    cache_key = f"{ticker}_{as_of}"
    cache = get_snapshot_cache(cache_dir)
    if cache_key in cache:
        return cache[cache_key]
    return None
