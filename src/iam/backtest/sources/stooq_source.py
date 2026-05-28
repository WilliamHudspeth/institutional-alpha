"""Stooq data source — free, sandbox-compatible fallback.

Stooq provides historical OHLCV data via CSV export (no API key needed).
Limitations:
- No balance sheet data (fetch_debt always returns 0.0)
- US tickers require .us suffix
"""

from __future__ import annotations

import io
import urllib.request

import pandas as pd

from .base import DataSource, DataSourceError


class StooqSource(DataSource):
    """Stooq CSV-export data source."""

    name = "stooq"
    BASE_URL = "https://stooq.com/q/d/l/"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def is_available(self) -> bool:
        # Stooq has no external dependencies beyond pandas.read_csv
        return True

    def _url(self, ticker: str, start: str, end: str) -> str:
        """Build Stooq CSV export URL."""
        return (
            f"{self.BASE_URL}?s={ticker.lower()}.us"
            f"&d1={start.replace('-', '')}"
            f"&d2={end.replace('-', '')}"
            f"&i=d"
        )

    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        start = (as_of - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        end = (as_of + pd.Timedelta(days=5)).strftime("%Y-%m-%d")

        df = self.download_history(ticker, start, end)
        if df is None or df.empty:
            raise DataSourceError(self.name, ticker, f"no history near {as_of.date()}")

        df = df[df["Date"].dt.date <= as_of.date()]
        if df.empty:
            raise DataSourceError(self.name, ticker, f"no close on/before {as_of.date()}")

        return float(df["Close"].iloc[-1])

    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        # Stooq does not provide balance sheet data
        return 0.0

    def download_history(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> pd.DataFrame | None:
        try:
            url = self._url(ticker, start, end)
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                csv_data = response.read().decode("utf-8")
            df = pd.read_csv(io.StringIO(csv_data))

            if df is None or df.empty:
                return None

            # Stooq returns: Date, Open, High, Low, Close, Volume
            expected = ["Date", "Open", "High", "Low", "Close", "Volume"]
            if not all(c in df.columns for c in expected):
                return None

            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").reset_index(drop=True)
            return df[expected]
        except Exception:
            return None
