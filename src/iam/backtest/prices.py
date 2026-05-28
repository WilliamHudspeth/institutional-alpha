"""High-performance price data loading with Polars and dynamic forward returns.

Loads price data via RedundantDataFetcher, computing forward returns on the fly.
"""

from typing import TYPE_CHECKING
from datetime import datetime

import pandas as pd
import polars as pl

from iam.backtest.universe import load_universe_tickers
from iam.data.fetcher import RedundantDataFetcher

# This satisfies Mypy without causing runtime circular imports
if TYPE_CHECKING:
    from iam.backtest.config import BacktestConfig


def load_price_block(config: "BacktestConfig") -> pl.DataFrame:
    """Load price data via RedundantDataFetcher and compute forward returns.

    Args:
        config: BacktestConfig

    Returns:
        Polars DataFrame with columns:
            - ticker: str
            - date: Date
            - close: float64 (adjusted close)
            - fwd_ret: float64 (forward return over primary horizon)
    """
    try:
        tickers = load_universe_tickers(config.universe_file)
    except FileNotFoundError:
        # Fallback to empty if universe file doesn't exist, though it shouldn't happen.
        tickers = []

    fetcher = RedundantDataFetcher()
    
    start_dt = pd.to_datetime(config.start)
    horizon = getattr(config, "horizon_days", 21)
    all_horizons = sorted(set(getattr(config, "horizons_days", []) + [horizon]))
    max_horizon = max(all_horizons) if all_horizons else horizon
    
    # We fetch extra days to compute forward returns
    end_dt = pd.to_datetime(config.end)
    end_with_horizon = (end_dt + pd.Timedelta(days=max_horizon + 15)).to_pydatetime()
    
    rows = []
    for ticker in tickers:
        prices = fetcher.fetch_price_history(ticker, start_dt.to_pydatetime(), end_with_horizon)
        if prices.empty:
            continue
            
        df = prices.reset_index()
        # the fetched prices might have "Date" or "index", reset_index usually names it "index" or "Date"
        df.columns = ["date", "close"]
        df["ticker"] = ticker
        
        # Convert date column to string just to be safe during dict conversion
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        rows.extend(df.to_dict("records"))

    if not rows:
        raise ValueError("No price data found for the given universe and date range.")

    df_pl = pl.DataFrame(rows)
    
    # Ensure correct typing
    df_pl = df_pl.with_columns([
        pl.col("date").str.to_date("%Y-%m-%d"),
        pl.col("close").cast(pl.Float64)
    ])
    
    df_pl = df_pl.sort(["ticker", "date"])

    horizon_exprs = [
        pl.col("close")
        .shift(-h)
        .over("ticker")
        .truediv(pl.col("close"))
        .sub(1)
        .alias(f"fwd_ret_{h}d")
        for h in all_horizons
    ]
    df_pl = df_pl.with_columns(horizon_exprs)
    df_pl = df_pl.with_columns(pl.col(f"fwd_ret_{horizon}d").alias("fwd_ret"))

    # Filter back down to the requested end date
    df_pl = df_pl.filter(pl.col("date") <= pl.lit(end_dt.strftime("%Y-%m-%d")).cast(pl.Date))

    return df_pl


def load_price_block_for_date(
    config: "BacktestConfig",
    as_of: str,  # YYYY-MM-DD format
) -> pl.DataFrame:
    """Load price data for a specific evaluation date.

    Args:
        config: BacktestConfig
        as_of: Evaluation date (YYYY-MM-DD)

    Returns:
        Polars DataFrame with prices and forward returns for the given date
    """
    df = load_price_block(config)

    # Filter to specific date and drop date column
    as_of_date = pl.lit(as_of).cast(pl.Date)
    result = df.filter(pl.col("date") == as_of_date).drop("date")

    return result
