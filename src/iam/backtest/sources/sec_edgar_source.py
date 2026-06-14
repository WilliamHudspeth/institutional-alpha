"""SEC EDGAR — free, official, point-in-time fundamentals.

OFFICIAL-tier source: authoritative US filing data, no API key, 20+ years of
history. It serves FUNDAMENTALS | DEBT | POINT_IN_TIME — but **not** prices
(EDGAR has none), so the tiered router never asks it for a price.

Why this is the right free debt source (vs. yfinance): EDGAR lets us filter on
the actual *filing date*, so a snapshot as-of date T only ever sees data that
was genuinely public by T. We filter on `filed <= as_of`, eliminating the
look-ahead bias that latest-balance-sheet scrapers silently introduce.

Debt has no single XBRL tag, so we combine current + noncurrent debt across a
small priority list of us-gaap concepts and take the most recent *filed* value
whose period end is on/before the as-of date.

No API key required, but the SEC mandates a descriptive User-Agent; set a real
contact via `user_agent=`. HTTP is injectable for offline tests.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

import pandas as pd

from .base import DataSource, DataSourceError
from .tiers import Capability, DataTier

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"

# Debt is assembled from (current, noncurrent) pairs in priority order. The first
# pair that yields any data on/before the as-of date is used.
_DEBT_TAG_PAIRS: list[tuple[str | None, str]] = [
    ("DebtCurrent", "LongTermDebtNoncurrent"),
    ("LongTermDebtCurrent", "LongTermDebtNoncurrent"),
    (None, "LongTermDebt"),  # single combined tag as a last resort
]

HttpGet = Callable[[str], object]


def _default_http_get(url: str, user_agent: str, timeout: float = 15.0) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed SEC hosts
        return json.loads(resp.read().decode("utf-8"))


class SecEdgarSource(DataSource):
    """SEC EDGAR XBRL adapter. OFFICIAL tier; FUNDAMENTALS | DEBT | POINT_IN_TIME."""

    name = "sec_edgar"
    tier = DataTier.OFFICIAL
    capabilities = Capability.FUNDAMENTALS | Capability.DEBT | Capability.POINT_IN_TIME

    def __init__(
        self,
        user_agent: str = "institutional-alpha research contact@example.com",
        http_get: HttpGet | None = None,
    ):
        from iam.config.credentials import get_key

        # Prefer a user-configured contact UA; fall back to the default.
        self.user_agent = get_key("sec_edgar", explicit=None) or user_agent
        if user_agent != "institutional-alpha research contact@example.com":
            self.user_agent = user_agent  # explicit arg always wins
        # default getter closes over the UA so callers only inject a url->json fn
        self._get: HttpGet = http_get or (lambda url: _default_http_get(url, self.user_agent))
        self._cik_map: dict[str, int] | None = None

    def is_available(self) -> bool:
        # Public, keyless API. Network reachability is handled at call time.
        return True

    # -- CIK resolution ------------------------------------------------------ #
    def _load_cik_map(self) -> dict[str, int]:
        if self._cik_map is not None:
            return self._cik_map
        data = self._get(_TICKERS_URL)
        mapping: dict[str, int] = {}
        # company_tickers.json is {"0": {"cik_str": int, "ticker": "AAPL", ...}, ...}
        rows = data.values() if isinstance(data, dict) else data
        for row in rows:
            tk = str(row.get("ticker", "")).upper()
            if tk:
                mapping[tk] = int(row["cik_str"])
        self._cik_map = mapping
        return mapping

    def _cik(self, ticker: str) -> int:
        cik = self._load_cik_map().get(ticker.upper())
        if cik is None:
            raise DataSourceError(self.name, ticker, "ticker not found in SEC CIK map")
        return cik

    # -- concept fetch with point-in-time discipline ------------------------- #
    def _latest_value_as_of(self, cik: int, tag: str, as_of: pd.Timestamp) -> float | None:
        """Most recent USD value for a us-gaap tag that was *filed* on/before as_of."""
        url = _CONCEPT_URL.format(cik=cik, tag=tag)
        try:
            data = self._get(url)
        except Exception:  # noqa: BLE001 — tag may not exist for this filer
            return None
        units = (data or {}).get("units", {}) if isinstance(data, dict) else {}
        rows = units.get("USD", [])
        # Filter on the FILING date to avoid look-ahead; rank by period end.
        visible = [
            r
            for r in rows
            if r.get("filed") and pd.Timestamp(r["filed"]) <= as_of and r.get("val") is not None
        ]
        if not visible:
            return None
        latest = max(visible, key=lambda r: (pd.Timestamp(r["end"]), pd.Timestamp(r["filed"])))
        return float(latest["val"])

    # -- contract ------------------------------------------------------------ #
    def fetch_price(self, ticker: str, as_of: pd.Timestamp) -> float:
        raise DataSourceError(self.name, ticker, "SEC EDGAR provides no price data")

    def fetch_debt(self, ticker: str, as_of: pd.Timestamp) -> float:
        as_of = pd.Timestamp(as_of)
        cik = self._cik(ticker)
        for current_tag, noncurrent_tag in _DEBT_TAG_PAIRS:
            noncurrent = self._latest_value_as_of(cik, noncurrent_tag, as_of)
            current = (
                self._latest_value_as_of(cik, current_tag, as_of)
                if current_tag is not None
                else 0.0
            )
            if noncurrent is not None or (current_tag is not None and current is not None):
                return float((noncurrent or 0.0) + (current or 0.0))
        raise DataSourceError(self.name, ticker, "no debt concept available on/before date")

    def download_history(self, ticker: str, start: str, end: str) -> pd.DataFrame | None:
        return None  # EDGAR has no price history
