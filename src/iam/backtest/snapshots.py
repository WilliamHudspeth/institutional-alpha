"""Point-in-time (PIT) Security snapshots for backtesting.

Builds immutable Security objects as they existed on a specific date,
freezing price and debt data. This prevents lookahead bias in the backtest.

Known limitations:
- Uses latest available quarterly debt (not exact PIT)
- Price is market close on the date
- Does not adjust for splits or dividends
"""

from __future__ import annotations

import pickle
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from iam.data.security import Security, MarketData, Fundamentals


def build_snapshot(
    base: Security,
    as_of: str,  # YYYY-MM-DD format
    cache_dir: Path = Path("data/snapshots"),
) -> Security:
    """Build a point-in-time Security snapshot for a specific date.

    Freezes the price as of the date and fetches the latest quarterly debt
    that was reported on or before that date. This prevents lookahead bias.

    Args:
        base: Base Security with sector, industry, revenue_mix, shares_outstanding
        as_of: Date string (YYYY-MM-DD)
        cache_dir: Directory to cache snapshots

    Returns:
        New Security object with market_cap and total_debt set for as_of date

    Raises:
        ValueError: If price data not available for the date
    """
    ticker = base.ticker
    as_of_dt = pd.Timestamp(as_of)

    # Check cache first
    cache_path = cache_dir / ticker / f"{as_of_dt.year}-{as_of_dt.month:02d}.pkl"
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    # Fetch price data (close on or before as_of)
    tk = yf.Ticker(ticker)
    hist = tk.history(start=as_of_dt - pd.Timedelta(days=30), end=as_of_dt + pd.Timedelta(days=5))
    hist = hist[hist.index.date <= as_of_dt.date()]

    if hist.empty:
        raise ValueError(f"No price data for {ticker} on or before {as_of}")

    price = float(hist["Close"].iloc[-1])

    # Fetch latest quarterly debt on or before as_of
    debt = 0.0
    try:
        bs = tk.quarterly_balance_sheet
        if not bs.empty:
            # Find columns with dates on or before as_of
            cols = [c for c in bs.columns if c.date() <= as_of_dt.date()]
            if cols and "Total Debt" in bs.index:
                debt_value = bs.loc["Total Debt", cols[-1]]
                if pd.notna(debt_value):
                    debt = float(debt_value)
    except Exception:
        # If debt fetch fails, use 0 (conservative)
        debt = 0.0

    # Calculate market cap
    market_cap = price * base.fundamentals.shares_outstanding if base.fundamentals.shares_outstanding else price

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
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(snapshot, f)

    return snapshot


def load_snapshot(ticker: str, as_of: str, cache_dir: Path = Path("data/snapshots")) -> Optional[Security]:
    """Load a cached snapshot if available."""
    as_of_dt = pd.Timestamp(as_of)
    cache_path = cache_dir / ticker / f"{as_of_dt.year}-{as_of_dt.month:02d}.pkl"

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    return None


def load_sp100_tickers() -> list[str]:
    """Load S&P 100 ticker list from universe file.

    Returns:
        List of tickers (e.g., ['AAPL', 'MSFT', ...])
    """
    import json

    universe_path = Path(__file__).parent.parent.parent.parent / "data" / "universe" / "sp100.json"

    if not universe_path.exists():
        raise FileNotFoundError(f"S&P 100 universe file not found: {universe_path}")

    with open(universe_path) as f:
        config = json.load(f)

    return config["tickers"]
