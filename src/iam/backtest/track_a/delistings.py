"""EDGAR Form 25 delisting parser, classification, and Shumway delisting return adjustments.

One Form 25 is filed per listed security class removed from an exchange. Because
redeeming a preferred stock or maturing a senior note also produces a Form 25,
this module identifies whether common equity was delisted, classifies the event
using contemporary 8-K and proxy/tender filings without look-ahead bias, and maps
distress or unknown delistings to Shumway (1997) / Shumway and Warther (1999)
delisting returns.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # nosec B405 - input is screened for DOCTYPE/ENTITY first
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any
from xml.etree.ElementTree import Element

import pandas as pd

from iam.backtest.track_a.errors import TrackADataError
from iam.data.edgar.client import EdgarClient, EdgarError

# Shumway (1997) "The Delisting Bias in CRSP Data" (-0.30 for NYSE/AMEX performance
# delistings) and Shumway and Warther (1999) "The Delisting Bias in CRSP's Nasdaq
# Data and Its Implications for the Size Effect" (-0.55 for Nasdaq).
SHUMWAY_RETURNS: dict[str, float] = {
    "nyse": -0.30,
    "amex": -0.30,
    "arca": -0.30,
    # No published estimate for Cboe listings; they follow NYSE-style listing standards.
    "cboe": -0.30,
    "nasdaq": -0.55,
    # Exchange not known (no XML, or an unrecognised name): the larger penalty, because the
    # penalised case is meant to bound the bias from the pessimistic side.
    "other": -0.55,
}
PENALISED_CATEGORIES: frozenset[str] = frozenset({"performance", "voluntary", "unknown"})

FORM25_FORMS: frozenset[str] = frozenset({"25", "25-NSE", "25/A", "25-NSE/A"})
MERGER_FORMS: frozenset[str] = frozenset(
    {
        "DEFM14A",
        "DEFM14A/A",
        "PREM14A",
        "PREM14A/A",
        "DEFM14C",
        "DEFM14C/A",
        "SC 14D9",
        "SC 14D9/A",
        "SC TO-T",
        "SC TO-T/A",
        "SC 13E3",
        "SC 13E3/A",
        "425",
    }
)
PERIODIC_FORMS: frozenset[str] = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
NEW_LISTING_FORMS: frozenset[str] = frozenset({"8-A12B", "8-A12B/A"})

_FILINGS_COLUMNS = ("accession", "filed", "form", "items", "primary_document")

_RULE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a1", re.compile(r"12d2-2\s*\(\s*a\s*\)\s*\(\s*1\s*\)", re.IGNORECASE)),
    ("a2", re.compile(r"12d2-2\s*\(\s*a\s*\)\s*\(\s*2\s*\)", re.IGNORECASE)),
    ("a3", re.compile(r"12d2-2\s*\(\s*a\s*\)\s*\(\s*3\s*\)", re.IGNORECASE)),
    ("a4", re.compile(r"12d2-2\s*\(\s*a\s*\)\s*\(\s*4\s*\)", re.IGNORECASE)),
    ("b", re.compile(r"12d2-2\s*\(\s*b\s*\)", re.IGNORECASE)),
    ("c", re.compile(r"12d2-2\s*\(\s*c\s*\)", re.IGNORECASE)),
)
_RULE_LABELS: dict[str, str] = {
    "a1": "rule 12d2-2(a)(1)",
    "a2": "rule 12d2-2(a)(2)",
    "a3": "rule 12d2-2(a)(3)",
    "a4": "rule 12d2-2(a)(4)",
    "b": "rule 12d2-2(b)",
    "c": "rule 12d2-2(c)",
}

_EXCLUSION_RE = re.compile(
    r"\b(?:"
    r"preferred|preference|notes?|debentures?|bonds?|warrants?|rights?|units?|"
    r"trust\s+preferred|due\s+20\d{2}|"
    # Structured products named after the common stock they convert into (Citigroup's
    # "Tangible Dividend Enhanced Common Stock (T-DECS)", 2012) and exchange-traded notes.
    r"dividend\s+enhanced|t-?decs|decs|peps|prides|equity\s+units?|purchase\s+contracts?|"
    r"mandatory|etns?|exchange[-\s]traded\s+notes?|guarantor"
    r")\b|%",
    re.IGNORECASE,
)
_INCLUSION_RE = re.compile(
    r"\b(?:"
    r"common\s+(?:stock|shares?)|"
    r"ordinary\s+shares?|"
    r"class\s+[a-z]\b|"
    r"shares?\s+of\s+beneficial\s+interest|"
    r"american\s+depositary\s+(?:shares?|receipts?)|"
    r"ads|adr"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Form25:
    accession: str
    filed: pd.Timestamp
    exchange_cik: str
    exchange_name: str
    exchange: str
    class_description: str
    rule: str
    is_common: bool | None


@dataclass(frozen=True)
class Delisting:
    cik: int
    form25_filed: pd.Timestamp
    effective: pd.Timestamp
    exchange: str
    rule: str
    category: str
    evidence: tuple[str, ...]
    accession: str


def _parse_items(raw: object) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        return tuple(p for p in parts if p)
    if isinstance(raw, Iterable):
        return tuple(str(p).strip() for p in raw if str(p).strip())
    return ()


def _extract_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    accns = block.get("accessionNumber") or []
    n = len(accns)
    if n == 0:
        return []
    filed = block.get("filingDate") or [""] * n
    forms = block.get("form") or [""] * n
    items = block.get("items") or [""] * n
    docs = block.get("primaryDocument") or [""] * n
    rows: list[dict[str, Any]] = []
    for i in range(n):
        rows.append(
            {
                "accession": str(accns[i]).strip(),
                "filed": pd.Timestamp(filed[i]),
                "form": str(forms[i]).strip() if i < len(forms) else "",
                "items": _parse_items(items[i] if i < len(items) else ""),
                "primary_document": str(docs[i]).strip() if i < len(docs) else "",
            }
        )
    return rows


def filings_frame(
    submissions: dict[str, Any], pages: Sequence[dict[str, Any]] = ()
) -> pd.DataFrame:
    """Build a de-duplicated, chronologically sorted DataFrame of filings."""
    recent = (submissions.get("filings") or {}).get("recent") or submissions
    rows = _extract_block(recent)
    for page in pages:
        page_block = (page.get("filings") or {}).get("recent") or page
        rows.extend(_extract_block(page_block))
    if not rows:
        return pd.DataFrame(columns=list(_FILINGS_COLUMNS))
    df = pd.DataFrame(rows, columns=list(_FILINGS_COLUMNS))
    df = df.drop_duplicates(subset=["accession"], keep="first")
    df = df.sort_values(["filed", "accession"], kind="mergesort").reset_index(drop=True)
    return df


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _child_text(parent: Element | None, name: str) -> str:
    if parent is None:
        return ""
    for child in parent:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _find_child(parent: Element, name: str) -> Element | None:
    for child in parent:
        if _local_name(child.tag) == name:
            return child
    return None


def _map_exchange(entity_name: str) -> str:
    upper = entity_name.upper()
    if "NASDAQ" in upper:
        return "nasdaq"
    if "AMERICAN" in upper or "MKT" in upper or "AMEX" in upper:
        return "amex"
    if "ARCA" in upper:
        return "arca"
    if "CBOE" in upper or "BATS" in upper:
        return "cboe"
    if "NEW YORK STOCK EXCHANGE" in upper or "NYSE" in upper:
        return "nyse"
    return "other"


def _parse_rule(rule_text: str) -> str:
    for code, pattern in _RULE_PATTERNS:
        if pattern.search(rule_text):
            return code
    return "unknown"


# Shareholder-rights plans attach to the common stock and are named in its description:
# "Common Stock, par value $.01 per share, and associated Preferred Stock Purchase Rights".
# That phrase describes the common class, so it is removed before the exclusion check.
_ATTACHED_RIGHTS_RE = re.compile(
    r"[(,]?\s*(?:and|together\s+with|including)?\s*(?:the\s+)?associated\b[^)]*?\brights?\b\)?",
    re.IGNORECASE,
)
# Instruments that ARE the class when named first ("Rights to purchase Common Stock",
# "Warrants, each exercisable for one share of Common Stock").
_LEADING_DERIVATIVE_RE = re.compile(r"^\W*(?:rights?|warrants?|units?)\b", re.IGNORECASE)
_COMMON_RE = re.compile(r"\bcommon\s+(?:stock|shares?)\b|\bordinary\s+shares?\b", re.IGNORECASE)
# A trailing clause that attaches rights to the class: "with attached preferred share purchase
# rights", "(including shareholder rights)", "and the related stockholder rights".
_RIGHTS_CLAUSE_RE = re.compile(
    r"[(,]?\s*\b(?:with|and|including|together\s+with|plus)\b[^;]*?\brights?\b\)?",
    re.IGNORECASE,
)


def is_common_class(description: str | None) -> bool | None:
    """Classify security description as common equity (True), non-common (False), or unknown (None).

    A rights plan attached to the common stock is named in its description in many ways
    ("and associated Preferred Stock Purchase Rights", "with attached preferred share purchase
    rights", "(including shareholder rights)"). When the description names common or ordinary
    shares and does not start with rights, warrants or units, such a clause is removed before
    the exclusion check. "Rights to purchase ..." and "Units, each consisting of ..." are not
    the common class.
    """
    if description is None:
        return None
    text = _ATTACHED_RIGHTS_RE.sub(" ", description).strip()
    if not text:
        return None
    if _LEADING_DERIVATIVE_RE.search(text):
        return False
    if _COMMON_RE.search(text):
        text = _RIGHTS_CLAUSE_RE.sub(" ", text)
    if _EXCLUSION_RE.search(text):
        return False
    if _INCLUSION_RE.search(text):
        return True
    return None


def parse_form25_xml(data: bytes, accession: str, filed: pd.Timestamp | str) -> Form25:
    """Parse an EDGAR Form 25 XML primary document."""
    # Same screen as the 10-K instance parser in iam.data.edgar.geography: a Form 25 never
    # declares a DOCTYPE or entities, so one that does is refused before it is parsed.
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", data, re.IGNORECASE):
        raise TrackADataError(f"Form 25 XML {accession} declares a DOCTYPE/ENTITY; refused")
    try:
        root = ET.fromstring(data)  # nosec B314 - DOCTYPE/ENTITY refused above
    except ET.ParseError as exc:
        raise TrackADataError(f"Malformed Form 25 XML for {accession}: {exc}") from exc

    if _local_name(root.tag) != "notificationOfRemoval":
        raise TrackADataError(f"Unexpected root element {root.tag!r} in Form 25 {accession}")

    exchange_el = _find_child(root, "exchange")
    exchange_cik = _child_text(exchange_el, "cik")
    exchange_name = _child_text(exchange_el, "entityName")
    class_desc = _child_text(root, "descriptionClassSecurity")
    rule_text = _child_text(root, "ruleProvision")

    return Form25(
        accession=str(accession),
        filed=pd.Timestamp(filed),
        exchange_cik=exchange_cik,
        exchange_name=exchange_name,
        exchange=_map_exchange(exchange_name),
        class_description=class_desc,
        rule=_parse_rule(rule_text),
        is_common=is_common_class(class_desc),
    )


def _date_str(ts: pd.Timestamp) -> str:
    text: str = pd.Timestamp(ts).strftime("%Y-%m-%d")
    return text


def classify_delisting(form25: Form25, filings: pd.DataFrame, cik: int) -> Delisting:
    """Classify a Form 25 using filings in [filed - 365d, filed + 30d] (90d for 8-A12B on rule c)."""
    filed = pd.Timestamp(form25.filed)
    effective = filed + pd.Timedelta(days=10)
    evidence: list[str] = []
    if form25.rule in _RULE_LABELS:
        evidence.append(_RULE_LABELS[form25.rule])

    if filings.empty:
        window = filings
    else:
        start = filed - pd.Timedelta(days=365)
        end = filed + pd.Timedelta(days=30)
        window = filings.loc[(filings["filed"] >= start) & (filings["filed"] <= end)]

    items_103: list[str] = []
    items_301: list[str] = []
    merger_ev: list[str] = []

    for row in window.itertuples(index=False):
        form = str(row.form)
        rdate = _date_str(row.filed)
        row_items = row.items if isinstance(row.items, tuple) else _parse_items(row.items)
        if form in {"8-K", "8-K/A"}:
            if "1.03" in row_items:
                items_103.append(f"8-K 1.03 on {rdate}")
            if "3.01" in row_items:
                items_301.append(f"8-K 3.01 on {rdate}")
        if form in MERGER_FORMS:
            merger_ev.append(f"{form} on {rdate}")

    if items_103:
        evidence.extend(items_103)
        category = "performance"
    elif form25.rule == "b":
        category = "performance"
    elif form25.rule == "a3":
        evidence.extend(merger_ev)
        category = "merger"
    elif form25.rule in {"a1", "a2"}:
        category = "redemption"
    elif form25.rule == "a4":
        evidence.append("rights extinguished")
        category = "unknown"
    elif form25.rule == "c":
        transfer_ev: list[str] = []
        if not filings.empty:
            end_90 = filed + pd.Timedelta(days=90)
            after_90 = filings.loc[(filings["filed"] >= filed) & (filings["filed"] <= end_90)]
            for row in after_90.itertuples(index=False):
                if str(row.form) in NEW_LISTING_FORMS:
                    transfer_ev.append(f"{row.form} on {_date_str(row.filed)}")
        if transfer_ev:
            evidence.extend(transfer_ev)
            category = "transfer"
        else:
            category = "voluntary"
    else:
        if merger_ev:
            evidence.extend(merger_ev)
            category = "merger"
        elif items_301:
            evidence.extend(items_301)
            category = "unknown"
        else:
            category = "unknown"

    return Delisting(
        cik=int(cik),
        form25_filed=filed,
        effective=effective,
        exchange=form25.exchange,
        rule=form25.rule,
        category=category,
        evidence=tuple(evidence),
        accession=form25.accession,
    )


REPORTS_STOP_DAYS = 120
REORG_LISTING_DAYS = 30
_REORG_CANDIDATES = frozenset({"merger", "redemption", "unknown"})


def _is_reorganisation(event: Delisting, filings: pd.DataFrame) -> bool:
    if event.category not in _REORG_CANDIDATES or filings.empty:
        return False
    filed = pd.Timestamp(event.form25_filed)
    cutoff = filed + pd.Timedelta(days=REPORTS_STOP_DAYS)
    reports_continue = ((filings["filed"] > cutoff) & filings["form"].isin(PERIODIC_FORMS)).any()
    near = (filings["filed"] - filed).abs() <= pd.Timedelta(days=REORG_LISTING_DAYS)
    relisted = (near & filings["form"].isin(NEW_LISTING_FORMS)).any()
    return bool(reports_continue or relisted)


def common_delisting(
    form25s: Sequence[Form25],
    filings: pd.DataFrame,
    cik: int,
    observed: pd.Timestamp | str | None = None,
) -> Delisting | None:
    """Select and classify the terminal common-stock delisting for a company.

    The earliest common-stock Form 25 that is not a transfer to another exchange (a company that
    moved from NYSE to Nasdaq in 2014 and was delisted in bankruptcy in 2019 must return the 2019
    event) and not a reorganisation. A merger, redemption or unknown event after which the same
    CIK keeps filing 10-K/10-Q reports, or registers a class on an exchange (8-A12B) within
    ``REORG_LISTING_DAYS`` of it, is a reorganisation: a holding-company merger or a change of
    state of incorporation hands shareholders identical shares of the successor (ExxonMobil's
    Form 25 of July 2026 under rule 12d2-2(a)(3), after which it kept filing). Performance and
    voluntary delistings stay terminal even when filings continue: a bankrupt company keeps
    reporting after its common stock is cancelled.

    Whether reports continued is known only after the event. It decides whether the security
    kept trading, which the market knew at once, never a signal; CRSP links successor securities
    the same way.
    """
    if not form25s:
        return None
    ordered = sorted(form25s, key=lambda f: (pd.Timestamp(f.filed), f.accession))
    commons = [f for f in ordered if f.is_common is True]
    if commons:
        events = [classify_delisting(f, filings, cik) for f in commons]
        terminal = [
            e for e in events if e.category != "transfer" and not _is_reorganisation(e, filings)
        ]
        if not terminal:
            return None
        event = terminal[0]
        # Too recent to tell a reorganisation from a merger: flag it rather than decide silently.
        # Measured against the observation date, not the filer's last filing (a merged-away
        # company stops filing, so its last filing is always close to its Form 25).
        when = pd.Timestamp(observed) if observed is not None else pd.Timestamp.today()
        recent = (when - event.form25_filed) <= pd.Timedelta(days=REPORTS_STOP_DAYS)
        if event.category in _REORG_CANDIDATES and recent:
            return replace(
                event,
                evidence=(
                    *event.evidence,
                    f"provisional: fewer than {REPORTS_STOP_DAYS} days of later filings",
                ),
            )
        return event

    unknowns = [f for f in ordered if f.is_common is None]
    if not unknowns:
        return None

    candidate = unknowns[0]
    cutoff = pd.Timestamp(candidate.filed) + pd.Timedelta(days=120)
    if not filings.empty:
        later_periodic = filings.loc[
            (filings["filed"] > cutoff) & (filings["form"].isin(PERIODIC_FORMS))
        ]
        if not later_periodic.empty:
            return None

    base = classify_delisting(candidate, filings, cik)
    return Delisting(
        cik=base.cik,
        form25_filed=base.form25_filed,
        effective=base.effective,
        exchange=base.exchange,
        rule=base.rule,
        category=base.category,
        evidence=(*base.evidence, "class not stated; periodic reports stopped"),
        accession=base.accession,
    )


def delisting_return(d: Delisting, case: str) -> float | None:
    """Return the delisting return adjustment under ``case`` ('drop', 'last_price', 'penalised')."""
    if case == "drop":
        return None
    if case == "last_price":
        return 0.0
    if case == "penalised":
        if d.category not in PENALISED_CATEGORIES:
            return 0.0
        return SHUMWAY_RETURNS.get(d.exchange)
    raise ValueError(f"Unknown delisting return case: {case!r}")


def fetch_delisting(client: EdgarClient, cik: int) -> Delisting | None:
    """Fetch submissions and Form 25 XML archives for ``cik`` and return its common delisting."""
    sub = client.submissions(int(cik))
    files = ((sub.get("filings") or {}).get("files")) or []
    pages = [client.submissions_page(f["name"]) for f in files if f.get("name")]
    filings = filings_frame(sub, pages)
    if filings.empty:
        return None

    f25_rows = filings.loc[filings["form"].isin(FORM25_FORMS)]
    if f25_rows.empty:
        return None

    parsed: list[Form25] = []
    for row in f25_rows.itertuples(index=False):
        accn = str(row.accession)
        filed = pd.Timestamp(row.filed)
        try:
            xml_bytes = client.archive_file(int(cik), accn, "primary_doc.xml")
            f25 = parse_form25_xml(xml_bytes, accn, filed)
        except (EdgarError, TrackADataError):
            f25 = Form25(
                accession=accn,
                filed=filed,
                exchange_cik="",
                exchange_name="",
                exchange="other",
                class_description="",
                rule="unknown",
                is_common=None,
            )
        parsed.append(f25)

    return common_delisting(parsed, filings, int(cik))
