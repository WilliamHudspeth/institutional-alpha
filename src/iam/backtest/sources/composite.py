"""Composite data source: tries each source in order, returns first success.

Used to chain yfinance (primary) → Stooq (fallback) without coupling the
snapshot logic to either implementation.
"""

from __future__ import annotations

import pandas as pd

from .base import DataSource, DataSourceError


class CompositeDataSource(DataSource):
    """Chain of DataSource instances tried in priority order."""

    name = "composite"

    def __init__(self, sources: list[DataSource]):
        if not sources:
            raise ValueError("CompositeDataSource requires at least one source")
        self.sources = sources
        self.last_used: str | None = None

    def is_available(self) -> bool:
        return any(s.is_available() for s in self.sources)

    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        errors = []
        for source in self.sources:
            if not source.is_available():
                continue
            try:
                price = source.fetch_price(ticker, as_of)
                self.last_used = source.name
                return price
            except DataSourceError as e:
                errors.append(f"{source.name}: {e.reason}")
                continue
            except Exception as e:
                errors.append(f"{source.name}: unexpected error {e}")
                continue

        raise DataSourceError(self.name, ticker, f"all sources failed: {'; '.join(errors)}")

    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        """Try each source in order; first non-zero result wins.

        Returns 0.0 if no source has debt data (conservative).
        """
        for source in self.sources:
            if not source.is_available():
                continue
            try:
                debt = source.fetch_debt(ticker, as_of)
                if debt > 0:
                    return debt
            except Exception:
                continue
        return 0.0

    def download_history(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> pd.DataFrame | None:
        for source in self.sources:
            if not source.is_available():
                continue
            df = source.download_history(ticker, start, end)
            if df is not None and not df.empty:
                self.last_used = source.name
                return df
        return None

    def __repr__(self) -> str:
        names = " → ".join(s.name for s in self.sources)
        return f"<CompositeDataSource: {names}>"
