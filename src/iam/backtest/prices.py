"""Bulk price cache and forward returns calculation.

Downloads price history once per backtest run, then slices forward returns
without refetching. This is the read-only interface to market data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd
import yfinance as yf


def get_price_block(
    tickers: list[str],
    start_date: str,  # YYYY-MM-DD
    end_date: str,    # YYYY-MM-DD
    horizon_days: int = 63,
) -> pd.DataFrame:
    """Download price history and compute forward returns for a block of tickers.

    Downloads closing prices for the date range + horizon, then computes
    forward returns: (price_{t+horizon} / price_t) - 1

    Args:
        tickers: List of ticker symbols
        start_date: Backtest start date (YYYY-MM-DD)
        end_date: Backtest end date (YYYY-MM-DD)
        horizon_days: Forward return horizon in trading days (~63 = 3 months)

    Returns:
        DataFrame with MultiIndex (date, ticker) and columns:
        - close: Price on that date
        - fwd_ret: Forward return over horizon
    """
    # Download with buffer for forward returns
    data = yf.download(
        tickers,
        start=start_date,
        end=pd.Timestamp(end_date) + pd.Timedelta(days=horizon_days),
        progress=False,
    )

    # Handle single ticker (yfinance returns Series instead of DataFrame)
    if isinstance(data, pd.Series):
        data = data.to_frame(name="Close")
    else:
        data = data["Close"]

    # Ensure data is a DataFrame with ticker columns
    if isinstance(data.columns, pd.RangeIndex):
        # Single ticker case
        data = data.reset_index().set_index(["Date"])
        data.columns = tickers if len(tickers) == 1 else [tickers[0]]
    else:
        # Multi-ticker case
        data = data.reset_index().set_index(["Date"])

    # Normalize to MultiIndex (date, ticker) and forward returns
    rows = []
    for date_idx, row in data.iterrows():
        for ticker in tickers:
            if ticker in row.index:
                close_price = row[ticker]
                if pd.notna(close_price):
                    # Find forward return at t + horizon
                    future_date = date_idx + pd.Timedelta(days=horizon_days)
                    future_data = data.loc[data.index >= future_date]
                    if not future_data.empty and ticker in future_data.columns:
                        future_price = future_data[ticker].iloc[0]
                        if pd.notna(future_price):
                            fwd_ret = (future_price / close_price) - 1
                            rows.append(
                                {
                                    "date": date_idx.date(),
                                    "ticker": ticker,
                                    "close": close_price,
                                    "fwd_ret": fwd_ret,
                                }
                            )

    if not rows:
        raise ValueError(f"No price data for {tickers} in range {start_date} to {end_date}")

    result = pd.DataFrame(rows)
    result = result.set_index(["date", "ticker"])
    return result
