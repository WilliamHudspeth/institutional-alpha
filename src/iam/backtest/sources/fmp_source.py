"""Financial Modeling Prep (FMP) — premium, point-in-time data source.

Implements the `DataSource` contract as a PREMIUM-tier source: prices, quarterly
total debt, and bulk history. Gated on an API key, so without `FMP_API_KEY` the
source reports `is_available() is False` and the tiered router simply skips it —
zero-config still works, premium is used only when configured.

The HTTP layer is injectable (`http_get`) so the adapter is fully unit-testable
offline with canned JSON; the default getter uses stdlib urllib (no new
dependency). FMP's domain is intentionally not assumed reachable in CI.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

import pandas as pd

from .base import DataSource, DataSourceError
from .tiers import Capability, DataTier

_BASE = "https://financialmodelingprep.com/api/v3"

HttpGet = Callable[[str], object]  # url -> parsed JSON (list/dict)


def _default_http_get(url: str, timeout: float = 15.0) -> object:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — fixed host
        return json.loads(resp.read().decode("utf-8"))


class FMPSource(DataSource):
    """FMP API adapter. PREMIUM tier; serves price/debt/fundamentals/history."""

    name = "fmp"
    tier = DataTier.PREMIUM
    capabilities = (
        Capability.PRICE
        | Capability.DEBT
        | Capability.FUNDAMENTALS
        | Capability.HISTORY
        | Capability.POINT_IN_TIME
    )

    def __init__(
        self,
        api_key: str | None = None,
        http_get: HttpGet | None = None,
    ):
        from iam.config.credentials import get_key

        self.api_key = get_key("fmp", explicit=api_key)
        self._get = http_get or _default_http_get

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _url(self, path: str, **params: str) -> str:
        params["apikey"] = self.api_key or ""
        return f"{_BASE}/{path}?{urllib.parse.urlencode(params)}"

    # -- prices -------------------------------------------------------------- #
    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        if not self.is_available():
            raise DataSourceError(self.name, ticker, "FMP_API_KEY not set")
        as_of = pd.Timestamp(as_of)
        url = self._url(
            f"historical-price-full/{ticker}",
            **{
                "from": (as_of - pd.Timedelta(days=10)).strftime("%Y-%m-%d"),
                "to": as_of.strftime("%Y-%m-%d"),
            },
        )
        try:
            data = self._get(url)
        except Exception as e:  # noqa: BLE001
            raise DataSourceError(self.name, ticker, f"http error {e}") from e

        hist = data.get("historical") if isinstance(data, dict) else None
        if not hist:
            raise DataSourceError(self.name, ticker, "no historical prices on/before date")
        # FMP returns newest-first; take the latest close on or before as_of.
        for row in hist:
            d = pd.Timestamp(row["date"])
            if d <= as_of and row.get("close") is not None:
                return float(row["close"])
        raise DataSourceError(self.name, ticker, "no close on/before date")

    # -- debt ---------------------------------------------------------------- #
    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        if not self.is_available():
            raise DataSourceError(self.name, ticker, "FMP_API_KEY not set")
        as_of = pd.Timestamp(as_of)
        url = self._url(f"balance-sheet-statement/{ticker}", period="quarter", limit="20")
        try:
            data = self._get(url)
        except Exception as e:  # noqa: BLE001
            raise DataSourceError(self.name, ticker, f"http error {e}") from e
        if not isinstance(data, list) or not data:
            raise DataSourceError(self.name, ticker, "no balance-sheet filings")
        # Point-in-time: latest filing whose date is on/before as_of.
        candidates = [r for r in data if pd.Timestamp(r.get("date", "1900-01-01")) <= as_of]
        if not candidates:
            raise DataSourceError(self.name, ticker, "no filing on/before date")
        latest = max(candidates, key=lambda r: pd.Timestamp(r["date"]))
        total_debt = latest.get("totalDebt")
        if total_debt is None:
            # derive from short + long term if the convenience field is absent
            short = latest.get("shortTermDebt") or 0.0
            long_ = latest.get("longTermDebt") or 0.0
            total_debt = short + long_
        return float(total_debt or 0.0)

    # -- history ------------------------------------------------------------- #
    def download_history(self, ticker: str, start: str, end: str) -> pd.DataFrame | None:
        if not self.is_available():
            return None
        url = self._url(f"historical-price-full/{ticker}", **{"from": start, "to": end})
        try:
            data = self._get(url)
        except Exception:  # noqa: BLE001
            return None
        hist = data.get("historical") if isinstance(data, dict) else None
        if not hist:
            return None
        df = pd.DataFrame(hist)
        if df.empty or "date" not in df:
            return None
        df["Date"] = pd.to_datetime(df["date"])
        df = df.set_index("Date").sort_index()
        rename = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=rename)
        cols = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df]
        return df[cols]
