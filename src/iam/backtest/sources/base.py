"""Abstract base class defining the contract for all price/fundamental data sources.

Any data source plugged into the backtest must implement:
- fetch_price(ticker, as_of): point-in-time close price
- fetch_debt(ticker, as_of): latest quarterly total debt on or before date
- download_history(ticker, start, end): bulk historical OHLCV
- name: source identifier for audit trail
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


class DataSourceError(Exception):
    """Raised when a data source cannot fulfill a request."""

    def __init__(self, source: str, ticker: str, reason: str):
        self.source = source
        self.ticker = ticker
        self.reason = reason
        super().__init__(f"[{source}] {ticker}: {reason}")


class DataSource(ABC):
    """Abstract contract for all backtest data sources."""

    name: str = "base"

    @abstractmethod
    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        """Fetch single close price on or before a date.

        Args:
            ticker: Stock ticker
            as_of: Target date (use latest close on or before this)

        Returns:
            Close price as float

        Raises:
            DataSourceError: If price unavailable
        """
        ...

    @abstractmethod
    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        """Fetch latest quarterly total debt on or before a date.

        Args:
            ticker: Stock ticker
            as_of: Target date

        Returns:
            Total debt in dollars (0.0 if unavailable from this source)
        """
        ...

    @abstractmethod
    def download_history(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """Download bulk historical OHLCV data for a single ticker.

        Args:
            ticker: Stock ticker
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)

        Returns:
            DataFrame indexed by Date with columns Open, High, Low, Close, Volume.
            Returns None if download fails.
        """
        ...

    def is_available(self) -> bool:
        """Check whether the source is configured and reachable.

        Override in subclasses to test for required imports or credentials.
        Default returns True.
        """
        return True

    def __repr__(self) -> str:
        return f"<DataSource: {self.name}>"
