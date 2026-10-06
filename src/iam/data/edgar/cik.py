"""Ticker -> CIK resolution with a date-aware override table.

``company_tickers.json`` is a snapshot of TODAY's ticker-to-CIK mapping. It is wrong for
history whenever a company reorganised (a new holding company gets a new CIK) and a
ticker is unsafe to guess across time in general. Known reorganisations are therefore
listed in :data:`CIK_OVERRIDES` as ``ticker -> [(cik, valid_from, valid_to, source)]``
so the backtest can pick the entity that actually filed on a historical date.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from iam.data.edgar.client import EdgarClient


class UnresolvedTickerError(LookupError):
    """The ticker (or the ticker on that date) has no known CIK. Never guessed."""


@dataclass(frozen=True)
class CikOverride:
    """One CIK a ticker maps to over ``[valid_from, valid_to]`` (inclusive, None = open)."""

    cik: int
    valid_from: date | None
    valid_to: date | None
    source: str  # where this entry was verified; required, so every entry is auditable


@dataclass(frozen=True)
class CikResolution:
    ticker: str
    cik: int
    source: str  # "override" or "company_tickers"
    note: str = ""


# BlackRock. EDGAR submissions (data.sec.gov/submissions), verified 2026-10-06:
#   CIK 1364742 is now named "BLACKROCK FINANCE, INC." (formerly "BlackRock Inc.", renamed
#   2024-09-26). It filed the holding company's 10-K/10-Qs up to the Q2 2024 10-Q (filed
#   2024-08-06).
#   CIK 2012383 is "BlackRock, Inc." (ticker BLK, formerly "BlackRock Funding, Inc. /DE";
#   renamed 2024-10-01 at the GIP closing). Its first 10-Q was filed 2024-11-06.
# The window boundary is the new entity's first periodic filing (2024-11-06), not the rename
# date: between 2024-10-01 and 2024-11-05 the latest FILED fundamentals are the old entity's.
# company_tickers.json maps BLK to 2012383 today; the override supplies the pre-cutover entity.
CIK_OVERRIDES: dict[str, tuple[CikOverride, ...]] = {
    "BLK": (
        CikOverride(
            1364742,
            None,
            date(2024, 11, 5),
            "EDGAR submissions CIK0001364742 (name BlackRock Finance, Inc.; last 10-Q filed "
            "2024-08-06), verified 2026-10-06",
        ),
        CikOverride(
            2012383,
            date(2024, 11, 6),
            None,
            "EDGAR submissions CIK0002012383 (BlackRock, Inc., ticker BLK; first 10-Q filed "
            "2024-11-06), verified 2026-10-06",
        ),
    ),
}


def _as_date(value: date | str | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _from_override(
    ticker: str, entries: tuple[CikOverride, ...], as_of: date | None
) -> CikResolution:
    for entry in entries:
        if as_of is None:
            if entry.valid_to is None:  # no date: the currently valid (open-ended) entity
                return CikResolution(ticker, entry.cik, "override", entry.source)
            continue
        if (entry.valid_from is None or entry.valid_from <= as_of) and (
            entry.valid_to is None or as_of <= entry.valid_to
        ):
            return CikResolution(ticker, entry.cik, "override", entry.source)
    when = f"on {as_of.isoformat()}" if as_of else "as the current entity"
    raise UnresolvedTickerError(f"{ticker}: no CIK override covers {when}")


def resolve_cik(
    ticker: str,
    as_of: date | str | None = None,
    *,
    client: EdgarClient | None = None,
    overrides: Mapping[str, tuple[CikOverride, ...]] = CIK_OVERRIDES,
) -> CikResolution:
    """Resolve ``ticker`` to a CIK, using the override table first.

    Without an override the answer is today's ``company_tickers.json`` mapping, which is
    only reliable for the present; tickers that were reused or reorganised need an override
    entry. Raises :class:`UnresolvedTickerError` rather than guessing.
    """
    symbol = ticker.strip().upper()
    when = _as_date(as_of)
    if symbol in overrides:
        return _from_override(symbol, overrides[symbol], when)
    edgar = client or EdgarClient()
    for entry in edgar.company_tickers().values():
        if str(entry.get("ticker", "")).upper() == symbol:
            return CikResolution(symbol, int(entry["cik_str"]), "company_tickers")
    raise UnresolvedTickerError(f"{symbol}: not in SEC company_tickers.json and no override")
