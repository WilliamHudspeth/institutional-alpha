"""Point-in-time (PIT) security snapshots with diskcache and yfinance→Stooq fallback.

Builds immutable Security objects as they existed on a specific date,
freezing price and debt data. Uses diskcache for persistence and implements
automatic fallback from yfinance to Stooq if primary source fails.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

import pandas as pd
from diskcache import Cache
from tenacity import retry, stop_after_attempt, wait_exponential

from iam.data.security import Security, MarketData

# Import data sources
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


def _fetch_price_yfinance(ticker: str, as_of: pd.Timestamp, timeout: float = 10.0) -> float:
    """Fetch price from yfinance for a specific date.

    Args:
        ticker: Stock ticker
        as_of: Target date (will use close on or before this date)
        timeout: Request timeout in seconds

    Returns:
        Close price on the date

    Raises:
        ValueError: If price data not available
    """
    if not HAS_YFINANCE:
        raise ImportError("yfinance required for primary data source")

    tk = yf.Ticker(ticker, session_kwargs={"timeout": timeout})
    hist = tk.history(start=as_of - pd.Timedelta(days=30), end=as_of + pd.Timedelta(days=5))
    hist = hist[hist.index.date <= as_of.date()]

    if hist.empty:
        raise ValueError(f"No price data for {ticker} on or before {as_of}")

    price = float(hist["Close"].iloc[-1])
    return price


def _fetch_price_stooq(ticker: str, as_of: pd.Timestamp, timeout: float = 15.0) -> float:
    """Fetch price from Stooq as fallback.

    Args:
        ticker: Stock ticker
        as_of: Target date
        timeout: Request timeout in seconds

    Returns:
        Close price on the date

    Raises:
        ValueError: If price data not available
    """
    try:
        from iam.backtest.data_loader import StooqDataLoader
    except ImportError:
        raise ImportError("StooqDataLoader not available; fallback to yfinance")

    loader = StooqDataLoader(timeout=timeout)
    try:
        df = loader.download_ticker_data(
            ticker,
            start=(as_of - pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
            end=(as_of + pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        )
        df = df[df.index.date <= as_of.date()]
        if df.empty:
            raise ValueError(f"No Stooq data for {ticker} on or before {as_of}")
        price = float(df["Close"].iloc[-1])
        return price
    except Exception as e:
        raise ValueError(f"Stooq fallback failed for {ticker}: {e}")


def _fetch_debt_yfinance(ticker: str, as_of: pd.Timestamp, timeout: float = 10.0) -> float:
    """Fetch latest quarterly debt on or before a date from yfinance.

    Args:
        ticker: Stock ticker
        as_of: Target date (will use latest quarterly on or before this date)
        timeout: Request timeout in seconds

    Returns:
        Total debt value (0.0 if not available)
    """
    if not HAS_YFINANCE:
        return 0.0

    try:
        tk = yf.Ticker(ticker, session_kwargs={"timeout": timeout})
        bs = tk.quarterly_balance_sheet

        if bs.empty:
            return 0.0

        # Find latest quarterly report on or before as_of
        cols = [c for c in bs.columns if pd.Timestamp(c).date() <= as_of.date()]
        if not cols:
            return 0.0

        # Look for Total Debt column
        if "Total Debt" in bs.index:
            debt_value = bs.loc["Total Debt", cols[-1]]
            if pd.notna(debt_value):
                return float(debt_value)
    except Exception:
        pass

    return 0.0


# Global cache for snapshots
_snapshot_cache = None


def get_snapshot_cache(cache_dir: Path) -> Cache:
    """Get or create the global snapshot cache."""
    global _snapshot_cache
    if _snapshot_cache is None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _snapshot_cache = Cache(str(cache_dir))
    return _snapshot_cache


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _fetch_snapshot_data(
    ticker: str,
    as_of: pd.Timestamp,
    yfinance_timeout: float = 10.0,
    stooq_timeout: float = 15.0,
) -> tuple[float, float]:
    """Fetch price and debt, trying yfinance first then Stooq.

    Args:
        ticker: Stock ticker
        as_of: Target date
        yfinance_timeout: yfinance timeout in seconds
        stooq_timeout: Stooq timeout in seconds

    Returns:
        Tuple of (price, debt)

    Raises:
        ValueError: If both sources fail
    """
    price = None
    debt = 0.0

    # Try yfinance first for both price and debt
    try:
        price = _fetch_price_yfinance(ticker, as_of, timeout=yfinance_timeout)
        debt = _fetch_debt_yfinance(ticker, as_of, timeout=yfinance_timeout)
        return price, debt
    except Exception as e_yf:
        pass

    # Fallback to Stooq for price only
    try:
        price = _fetch_price_stooq(ticker, as_of, timeout=stooq_timeout)
        debt = 0.0  # Stooq doesn't have balance sheet data
        return price, debt
    except Exception as e_stooq:
        pass

    raise ValueError(f"Both yfinance and Stooq failed for {ticker} on {as_of}")


def build_snapshot(
    base: Security,
    as_of: str,  # YYYY-MM-DD format
    cache_dir: Path = Path(".cache/snapshots"),
    yfinance_timeout: float = 10.0,
    stooq_timeout: float = 15.0,
) -> Security:
    """Build a point-in-time Security snapshot for a specific date.

    Freezes the price as of the date and fetches the latest quarterly debt
    that was reported on or before that date. Uses yfinance primarily,
    falls back to Stooq for price if yfinance fails.

    Args:
        base: Base Security with sector, industry, revenue_mix, shares_outstanding
        as_of: Date string (YYYY-MM-DD)
        cache_dir: Directory for diskcache persistence
        yfinance_timeout: yfinance timeout in seconds
        stooq_timeout: Stooq timeout in seconds

    Returns:
        New Security object with market_cap and total_debt set for as_of date

    Raises:
        ValueError: If neither yfinance nor Stooq can provide price data
    """
    ticker = base.ticker
    as_of_dt = pd.Timestamp(as_of)
    cache_key = f"{ticker}_{as_of}"

    # Check cache first
    cache = get_snapshot_cache(cache_dir)
    if cache_key in cache:
        return cache[cache_key]

    # Fetch price and debt with fallback logic
    price, debt = _fetch_snapshot_data(
        ticker,
        as_of_dt,
        yfinance_timeout=yfinance_timeout,
        stooq_timeout=stooq_timeout,
    )

    # Calculate market cap
    shares = base.fundamentals.shares_outstanding if base.fundamentals.shares_outstanding else 1_000_000_000
    market_cap = price * shares

    # Create snapshot with frozen market data
    snapshot = replace(
        base,
        market=MarketData(
            price=price,
            market_cap=market_cap,
        ),
        fundamentals=replace(
            base.fundamentals,
            total_debt=debt,
        ),
    )

    # Cache the snapshot
    cache[cache_key] = snapshot

    return snapshot


def load_snapshot(
    ticker: str,
    as_of: str,
    cache_dir: Path = Path(".cache/snapshots"),
) -> Optional[Security]:
    """Load a cached snapshot if available.

    Args:
        ticker: Stock ticker
        as_of: Date string (YYYY-MM-DD)
        cache_dir: Cache directory

    Returns:
        Cached Security snapshot or None if not in cache
    """
    cache_key = f"{ticker}_{as_of}"
    cache = get_snapshot_cache(cache_dir)

    if cache_key in cache:
        return cache[cache_key]

    return None
