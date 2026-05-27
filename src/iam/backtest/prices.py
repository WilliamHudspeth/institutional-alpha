"""High-performance price data loading with Polars and pre-computed forward returns.

Loads price data from parquet file (built via build_price_parquet.py),
which includes pre-computed forward returns for a given horizon.
"""

import polars as pl
from pathlib import Path
from typing import Optional


def load_price_block(config: "BacktestConfig") -> pl.DataFrame:
    """Load price data from parquet file with forward returns already computed.

    Args:
        config: BacktestConfig with price_file path

    Returns:
        Polars DataFrame with columns:
            - ticker: str
            - date: Date
            - close: float64 (adjusted close)
            - fwd_ret: float64 (forward return over horizon)
            - data_source: str ('yfinance' or 'stooq')

    Raises:
        FileNotFoundError: If price file doesn't exist
    """
    if not config.price_file.exists():
        raise FileNotFoundError(
            f"Price file not found: {config.price_file}. "
            f"Run: python scripts/build_price_parquet.py first."
        )

    df = pl.read_parquet(config.price_file)

    # Ensure correct schema
    if "ticker" not in df.columns or "date" not in df.columns or "close" not in df.columns:
        raise ValueError(
            f"Price parquet missing required columns. Expected: ticker, date, close, fwd_ret"
        )

    return df.sort(["ticker", "date"])


def load_price_block_for_date(
    config: "BacktestConfig",
    as_of: str,  # YYYY-MM-DD format
) -> pl.DataFrame:
    """Load price data for a specific evaluation date.

    Args:
        config: BacktestConfig with price_file path
        as_of: Evaluation date (YYYY-MM-DD)

    Returns:
        Polars DataFrame with prices and forward returns for the given date
    """
    df = load_price_block(config)

    # Filter to specific date and drop date column
    result = df.filter(pl.col("date") == as_of).drop("date")

    return result
