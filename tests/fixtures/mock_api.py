from typing import Any


class MockTicker:
    """Simulates a yfinance.Ticker object."""

    def __init__(self, ticker: str, info: dict[str, Any] | None = None):
        self.ticker = ticker
        self._info = info

    @property
    def info(self) -> dict[str, Any]:
        if self._info is not None:
            return self._info

        # Realistic default response schema resembling Yahoo Finance
        return {
            "currentPrice": 150.0,
            "marketCap": 15000000000.0,
            "sharesOutstanding": 100000000.0,
            "netIncomeToCommon": 1000000000.0,
            "ebitda": 2000000000.0,
            "freeCashflow": 1200000000.0,
            "totalDebt": 5000000000.0,
            "totalCash": 2000000000.0,
            "trailingPE": 15.0,
            "forwardPE": 14.0,
            "priceToBook": 3.5,
            "enterpriseToEbitda": 9.0,
            "enterpriseToRevenue": 2.5,
            "totalRevenue": 8000000000.0,
            "operatingMargins": 0.22,
            "profitMargins": 0.12,
            "returnOnEquity": 0.18,
            "returnOnAssets": 0.08,
            "revenueGrowth": 0.10,
            "earningsGrowth": 0.12,
            "targetMeanPrice": 170.0,
            "recommendationKey": "buy",
            "sector": "Technology",
            "industry": "Software",
        }


class MockYFinance:
    """Mock for the yfinance library."""

    def __init__(self):
        self._tickers: dict[str, MockTicker] = {}
        self.fail_all = False
        self._download_data = None

    def Ticker(self, ticker: str) -> MockTicker:
        if self.fail_all:
            raise RuntimeError("Mock network failure")
        if ticker not in self._tickers:
            self._tickers[ticker] = MockTicker(ticker)
        return self._tickers[ticker]

    def set_ticker_info(self, ticker: str, info: dict[str, Any]):
        """Inject specific info for a given ticker."""
        self._tickers[ticker] = MockTicker(ticker, info)

    def download(self, *args, **kwargs):
        """Simulate yfinance.download"""
        if self.fail_all:
            raise RuntimeError("Mock network failure")
        if self._download_data is not None:
            return self._download_data

        # Default realistic-ish download response
        import numpy as np
        import pandas as pd

        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        return pd.DataFrame(
            {
                "Adj Close": np.linspace(100, 150, 100),
                "Close": np.linspace(100, 150, 100),
                "Volume": np.random.randint(1000000, 5000000, 100),
            },
            index=dates,
        )

    def set_download_data(self, data):
        """Inject specific dataframe to be returned by download()"""
        self._download_data = data
