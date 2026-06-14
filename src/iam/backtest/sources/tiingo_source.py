"""Tiingo — premium price/history data source.

PREMIUM-tier adapter for Tiingo's daily EOD endpoint. Tiingo's free key covers
prices and history richly; fundamentals are a separate paid product, so this
adapter deliberately declares only PRICE | HISTORY capability — which means the
tiered router will never route a `fetch_debt` request here (it routes debt only
to DEBT-capable tiers), and `fetch_debt` raises if called directly.

Gated on `TIINGO_API_KEY`; HTTP layer injectable for offline tests.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable

import pandas as pd

from .base import DataSource, DataSourceError
from .tiers import Capability, DataTier

_BASE = "https://api.tiingo.com/tiingo/daily"

HttpGet = Callable[[str], object]


def _default_http_get(url: str, timeout: float = 15.0) -> object:
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class TiingoSource(DataSource):
    """Tiingo daily EOD adapter. PREMIUM tier; PRICE | HISTORY only."""

    name = "tiingo"
    tier = DataTier.PREMIUM
    capabilities = Capability.PRICE | Capability.HISTORY

    def __init__(self, api_key: str | None = None, http_get: HttpGet | None = None):
        from iam.config.credentials import get_key
        self.api_key = get_key("tiingo", explicit=api_key)
        self._get = http_get or _default_http_get

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _url(self, ticker: str, start: str, end: str) -> str:
        return (
            f"{_BASE}/{ticker}/prices?startDate={start}&endDate={end}"
            f"&token={self.api_key}"
        )

    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        if not self.is_available():
            raise DataSourceError(self.name, ticker, "TIINGO_API_KEY not set")
        as_of = pd.Timestamp(as_of)
        start = (as_of - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        url = self._url(ticker, start, as_of.strftime("%Y-%m-%d"))
        try:
            data = self._get(url)
        except Exception as e:  # noqa: BLE001
            raise DataSourceError(self.name, ticker, f"http error {e}") from e
        if not isinstance(data, list) or not data:
            raise DataSourceError(self.name, ticker, "no prices on/before date")
        # Tiingo returns oldest-first; take the last row on/before as_of.
        chosen = None
        for row in data:
            d = pd.Timestamp(row["date"]).tz_localize(None)
            if d <= as_of:
                chosen = row
        if chosen is None:
            raise DataSourceError(self.name, ticker, "no close on/before date")
        # prefer adjusted close
        return float(chosen.get("adjClose", chosen.get("close")))

    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        raise DataSourceError(
            self.name, ticker,
            "Tiingo daily endpoint has no balance-sheet data (DEBT capability not declared)",
        )

    def download_history(self, ticker: str, start: str, end: str) -> pd.DataFrame | None:
        if not self.is_available():
            return None
        try:
            data = self._get(self._url(ticker, start, end))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(data, list) or not data:
            return None
        df = pd.DataFrame(data)
        if "date" not in df:
            return None
        df["Date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df = df.set_index("Date").sort_index()
        rename = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }
        df = df.rename(columns=rename)
        cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df]
        return df[cols] if cols else None
