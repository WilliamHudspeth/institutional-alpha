"""yfinance data source — primary, institutional-grade.

Provides:
- Point-in-time prices via .history()
- Quarterly balance sheet for debt extraction
- Bulk OHLCV download via .download()
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import DataSource, DataSourceError

try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    yf = None  # type: ignore


class YFinanceSource(DataSource):
    """Yahoo Finance data source (via yfinance library)."""

    name = "yfinance"

    def __init__(self, timeout: float = 10.0):
        """Initialize with request timeout."""
        self.timeout = timeout

    def is_available(self) -> bool:
        return HAS_YFINANCE

    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        if not HAS_YFINANCE:
            raise DataSourceError(self.name, ticker, "yfinance not installed")

        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(
                start=as_of - pd.Timedelta(days=30),
                end=as_of + pd.Timedelta(days=5),
            )
        except Exception as e:
            raise DataSourceError(self.name, ticker, f"history() failed: {e}")

        if hist is None or hist.empty:
            raise DataSourceError(self.name, ticker, f"no history near {as_of.date()}")

        # Filter to dates on or before as_of (handle tz-aware indices)
        try:
            hist = hist[hist.index.date <= as_of.date()]
        except AttributeError:
            hist = hist[pd.to_datetime(hist.index).date <= as_of.date()]

        if hist.empty:
            raise DataSourceError(self.name, ticker, f"no close on/before {as_of.date()}")

        return float(hist["Close"].iloc[-1])

    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        """Fetch latest quarterly debt. Returns 0.0 on any failure (conservative)."""
        if not HAS_YFINANCE:
            return 0.0

        try:
            tk = yf.Ticker(ticker)
            bs = tk.quarterly_balance_sheet

            if bs is None or bs.empty:
                return 0.0

            # Find columns dated on or before as_of, sorted ascending so the
            # most recent quarterly report is cols[-1] regardless of yfinance's
            # column ordering (which is descending, latest-first).
            cols = sorted(
                c for c in bs.columns if pd.Timestamp(c).date() <= as_of.date()
            )
            if not cols:
                return 0.0
            latest_col = cols[-1]

            # Look for Total Debt row (try several variants)
            for debt_field in ("Total Debt", "Long Term Debt", "Total Long Term Debt"):
                if debt_field in bs.index:
                    value = bs.loc[debt_field, latest_col]
                    if pd.notna(value):
                        return float(value)

            return 0.0
        except Exception:
            return 0.0

    def download_history(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        if not HAS_YFINANCE:
            return None

        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                progress=False,
                auto_adjust=True,
            )
            if df is None or df.empty:
                return None

            # Standardize columns (handle MultiIndex from multi-ticker case)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()
            df = df.rename(columns={"Date": "Date"})

            # Keep standard columns
            keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            df = df[keep]
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").reset_index(drop=True)
            return df
        except Exception:
            return None
