"""Point-in-time ticker hints for a CIK, from the file names of its own filings.

``submissions.tickers`` lists only today's tickers and is empty for delisted filers, and
``companyfacts`` carries no ticker (its ``dei`` facts are numeric). The file names of periodic
filings do: SEC's naming convention for XBRL documents is ``<prefix>-<period end>``, and filers
almost always use their ticker as the prefix (``twtr-20211231.htm`` for an inline XBRL 10-K since
2019, ``twtr-20131231.xml`` for the separate instance document before that). A hint is dated by
the filing it came from, so it is point-in-time.

A prefix is a hint, not proof: some filers use a name abbreviation, and tickers are reused. The
price layer must validate a hint (prices exist for the dated span, and stop near the delisting
date for delisted names) before a price series is attached to the CIK.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

PERIODIC_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-Q", "10-Q/A"})
# prefix: a letter, then up to 5 letters/digits, optionally a class suffix (brk.a / bf-b);
# then a dash, an 8-digit date and an optional "_htm" (pre-2019 instance names) and extension.
_DOC_RE = re.compile(
    r"^(?P<prefix>[a-z][a-z0-9]{0,5}(?:[.][a-z])?)-(?P<date>(?:19|20)\d{6})(?:_htm)?\.(?:htm|xml)$"
)
# Generic prefixes that are not tickers (filing-agent or form names).
_NOT_TICKERS = frozenset({"form", "def", "ex", "exhibit", "doc", "document", "report", "fs"})


def ticker_from_document(name: str) -> str | None:
    """Upper-case ticker hint from an XBRL document file name, or None."""
    base = name.rsplit("/", 1)[-1].lower()
    m = _DOC_RE.match(base)
    if not m or m.group("prefix") in _NOT_TICKERS:
        return None
    return m.group("prefix").upper().replace(".", "-")


def hints_from_filings(filings: pd.DataFrame) -> pd.DataFrame:
    """One row per periodic filing whose primary document name carries a ticker hint.

    ``filings`` is the frame from ``delistings.filings_frame`` (columns ``filed``, ``form``,
    ``accession``, ``primary_document``).
    """
    rows = []
    for r in filings.itertuples(index=False):
        if r.form not in PERIODIC_FORMS:
            continue
        ticker = ticker_from_document(r.primary_document or "")
        if ticker:
            rows.append({"ticker": ticker, "filed": r.filed, "accession": r.accession,
                         "source": "primary_document"})  # fmt: skip
    return pd.DataFrame(rows, columns=["ticker", "filed", "accession", "source"])


def hint_from_index(index_doc: dict[str, Any]) -> str | None:
    """Ticker hint from a filing's ``index.json`` (the XBRL instance file name).

    Used for filings before inline XBRL, whose primary document is an agent-named HTML file.
    Prefers the ``.xml`` instance; schema (``.xsd``) and linkbase files are ignored.
    """
    items = ((index_doc.get("directory") or {}).get("item")) or []
    names = [str(i.get("name", "")) for i in items]
    for name in sorted(names, key=lambda n: (not n.endswith(".xml"), n)):
        ticker = ticker_from_document(name)
        if ticker and not re.search(r"_(cal|def|lab|pre)\.xml$", name):
            return ticker
    return None


def ticker_spans(hints: pd.DataFrame) -> pd.DataFrame:
    """Collapse dated hints into spans: consecutive filings with the same ticker.

    Columns: ticker, first_filed, last_filed, n_filings. A ticker that comes back after a
    different one starts a new span, so a rename and a later reversal stay distinguishable.
    """
    cols = ["ticker", "first_filed", "last_filed", "n_filings"]
    if hints.empty:
        return pd.DataFrame(columns=cols)
    h = hints.sort_values(["filed", "accession"]).reset_index(drop=True)
    run = (h["ticker"] != h["ticker"].shift()).cumsum()
    spans = h.groupby(run).agg(
        ticker=("ticker", "first"),
        first_filed=("filed", "min"),
        last_filed=("filed", "max"),
        n_filings=("filed", "size"),
    )
    return spans.reset_index(drop=True)[cols]


# A hint older than one fiscal year plus the 10-K deadline is not trusted: the filer may have
# changed ticker and switched to agent-named documents that carry no hint.
MAX_HINT_AGE_DAYS = 456
AVAILABILITY_LAG = pd.offsets.BDay(1)


def ticker_at(spans: pd.DataFrame, when: pd.Timestamp) -> str | None:
    """The ticker in use at ``when``, or None.

    The latest span whose first filing was public by ``when`` (one business day after it was
    filed), provided that span's last hint is no older than ``MAX_HINT_AGE_DAYS``.
    """
    if spans.empty:
        return None
    usable = pd.Timestamp(when) - AVAILABILITY_LAG
    started = spans[spans["first_filed"] <= usable]
    if started.empty:
        return None
    span = started.iloc[-1]
    last_seen = min(pd.Timestamp(span["last_filed"]), usable)
    if (usable - last_seen).days > MAX_HINT_AGE_DAYS:
        return None
    return str(span["ticker"])


def reused_tickers(spans_by_cik: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Tickers hinted by more than one CIK, with each CIK's span (for manual review)."""
    rows = []
    for cik, spans in spans_by_cik.items():
        for s in spans.itertuples(index=False):
            rows.append({"ticker": s.ticker, "cik": cik, "first_filed": s.first_filed,
                         "last_filed": s.last_filed})  # fmt: skip
    frame = pd.DataFrame(rows, columns=["ticker", "cik", "first_filed", "last_filed"])
    shared = frame.groupby("ticker")["cik"].transform("nunique") > 1
    return frame[shared].sort_values(["ticker", "first_filed"]).reset_index(drop=True)
