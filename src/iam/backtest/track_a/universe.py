"""Point-in-time universe: the largest listed filers at each month-end.

Built from EDGAR ``companyfacts`` documents (one per CIK, from the bulk ``companyfacts.zip`` or
the per-CIK API), so filers that later delisted are included. Rules, each covered by a test:

* **Size measure.** By default the public float (``dei:EntityPublicFloat``): the market value of
  common equity held by non-affiliates, which every listed filer reports on its 10-K cover as of
  the end of its second fiscal quarter. It is the free, survivorship-safe counterpart of the
  float-adjusted market cap that Russell and S&P rank on (Russell also reconstitutes once a
  year), it needs no price feed, and it treats banks, insurers and REITs the same as everyone
  else. Trailing revenue is the alternative measure (``size_measure="revenue"``) and is
  recorded for every member either way; ranking on it over-weights low-margin distributors and
  depends on which revenue tag a filer used (Exxon's 10-Ks before 2012 carry none of the standard
  tags), so it serves as a robustness check. Market cap from prices is not used: free prices are
  missing for exactly the names that later delisted.
* **Availability.** A filing counts from one business day after its ``filed`` date, so the
  month-end ``M`` uses facts filed on or before ``M`` minus one business day.
* **Listed equity only.** A filer needs a positive public float filed within
  ``FLOAT_MAX_AGE_DAYS`` of the as-of date. Reports of zero are ignored rather than trusted:
  AT&T's 10-K filed in March 2011 states a float of 0 between years of $146B and $186B, and debt-
  only subsidiaries never report a positive float, so they are still excluded.
* **Revenue** (when recorded or ranked on): trailing twelve months from
  ``iam.data.edgar.facts`` (latest filed value per period, 10-K/10-Q forms only, never a partial
  sum, stale after 15 months). When no standard tag is available, banks use interest and dividend
  income plus non-interest income (same period end) and the basis is recorded. Filers of
  20-F/40-F are out because their forms are not accepted.
* **Delistings.** A filer whose common stock was delisted (``delisted``: CIK to effective date,
  transfers between exchanges already removed) leaves the universe from the first month-end on
  or after the effective date. The Form 25 is public ten days before it takes effect.
* **No merging of "duplicate" filers.** A registrant subsidiary that files alongside its parent
  reports no positive float, so the float rule already removes it. Merging on matching numbers
  is unsafe: floats are disclosed rounded to $0.1B and revenue to the million, and unrelated
  companies collide (Verizon and Wells Fargo both reported a float of exactly $156.3B as of
  30 June 2023; Amazon and Verizon reported revenue within 0.5% for the same quarter). Two
  listed entities with their own floats (a tracking stock, a listed subsidiary) are separate
  securities and both stay, as in the index providers' practice.
* **Speed.** Only filers that ever reported annual revenue of at least
  ``MIN_EVER_ANNUAL_REVENUE`` or a public float of at least ``MIN_EVER_PUBLIC_FLOAT`` are
  evaluated, both far below any top-500 cut-off. The pre-filter reads all filing dates, so it
  affects only which small filers appear in the exclusion log, never the members.

Every excluded filer-month is logged with a reason; nothing is filled with a default.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from iam.data.edgar.facts import (
    ANNUAL_FORMS,
    ANNUAL_MAX_DAYS,
    ANNUAL_MIN_DAYS,
    MAX_STALE_DAYS,
    REVENUE_TAGS,
    _best_ttm,
    _load,
    _Ttm,
)

UNIVERSE_SIZE = 500
SIZE_MEASURES = ("public_float", "revenue")
MIN_EVER_ANNUAL_REVENUE = 250e6
MIN_EVER_PUBLIC_FLOAT = 500e6
FLOAT_MAX_AGE_DAYS = 456  # one fiscal year plus the 10-K deadline, as for stale TTM values
AVAILABILITY_LAG = pd.offsets.BDay(1)

EXTRA_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenuesNetOfInterestExpense",
    # Asset managers and brokers (BlackRock 2010-2023).
    "RevenuesExcludingInterestAndDividends",
    # Utilities.
    "RegulatedAndUnregulatedOperatingRevenue",
)
UNIVERSE_REVENUE_TAGS = REVENUE_TAGS + EXTRA_REVENUE_TAGS
BANK_REVENUE_TAGS = ("InterestAndDividendIncomeOperating", "NoninterestIncome")
FLOAT_TAG = "EntityPublicFloat"


@dataclass(frozen=True)
class FilerMonth:
    """One filer's eligibility and size at one month-end."""

    cik: int
    month_end: pd.Timestamp
    entity_name: str
    public_float: float | None
    float_as_of: date | None  # the date the float was measured (second fiscal quarter end)
    revenue_ttm: float | None
    revenue_tag: str | None
    revenue_period_end: date | None
    revenue_reason: str | None  # why revenue is missing (recorded even when ranking on float)
    reason: str | None  # None when eligible for the size measure in use


def month_ends(start: str, end: str) -> list[pd.Timestamp]:
    return list(pd.date_range(start, end, freq="ME"))


def as_of_for(month_end: pd.Timestamp) -> date:
    """Latest filing date usable at ``month_end`` (one business day of lag)."""
    usable: date = (pd.Timestamp(month_end) - AVAILABILITY_LAG).date()
    return usable


def ever_large(
    doc: dict[str, Any],
    revenue_threshold: float = MIN_EVER_ANNUAL_REVENUE,
    float_threshold: float = MIN_EVER_PUBLIC_FLOAT,
) -> bool:
    """Cheap pre-filter: any annual revenue or public float fact at or above its threshold."""
    facts = doc.get("facts") or {}
    gaap = facts.get("us-gaap") or {}
    for tag in UNIVERSE_REVENUE_TAGS + BANK_REVENUE_TAGS:
        for row in ((gaap.get(tag) or {}).get("units") or {}).get("USD") or []:
            if row.get("form") not in ANNUAL_FORMS or not row.get("start"):
                continue
            days = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
            val = row.get("val")
            if ANNUAL_MIN_DAYS <= days <= ANNUAL_MAX_DAYS and isinstance(val, int | float):
                if not isinstance(val, bool) and val >= revenue_threshold:
                    return True
    floats = (((facts.get("dei") or {}).get(FLOAT_TAG) or {}).get("units") or {}).get("USD") or []
    return any(
        isinstance(r.get("val"), int | float) and not isinstance(r.get("val"), bool)
        and r["val"] >= float_threshold
        for r in floats
    )  # fmt: skip


def _bank_revenue(doc: dict[str, Any], as_of: date) -> _Ttm | None:
    legs = [_best_ttm(doc, (tag,), as_of) for tag in BANK_REVENUE_TAGS]
    if any(leg.value is None for leg in legs):
        return None
    if len({leg.period_end for leg in legs}) != 1:
        return None
    return _Ttm(
        value=sum(leg.value for leg in legs),  # type: ignore[misc]
        reason=None,
        period_end=legs[0].period_end,
        method="bank: interest and dividend income + noninterest income",
        sources=tuple(s for leg in legs for s in leg.sources),
        tag="+".join(BANK_REVENUE_TAGS),
    )


def revenue_as_of(doc: dict[str, Any], as_of: date) -> _Ttm:
    """PIT TTM revenue: standard tags first, the bank composite only when they all fail."""
    ttm = _best_ttm(doc, UNIVERSE_REVENUE_TAGS, as_of)
    if ttm.value is not None:
        return ttm
    bank = _bank_revenue(doc, as_of)
    return bank if bank is not None else ttm


def public_float_as_of(
    doc: dict[str, Any], as_of: date
) -> tuple[float | None, date | None, str | None]:
    """Latest positive ``dei:EntityPublicFloat`` filed on or before ``as_of`` and not too old."""
    return _float_from(_load(doc, "dei", FLOAT_TAG, "USD", as_of), as_of)


def _float_from(facts: list[Any], as_of: date) -> tuple[float | None, date | None, str | None]:
    positive = [f for f in facts if f.val > 0]
    if not positive:
        if facts:
            return None, None, "no positive public float reported (no listed common equity)"
        return None, None, "no public float reported (not listed equity)"
    latest = max(positive, key=lambda f: (f.filed, f.end))
    if (as_of - latest.filed).days > FLOAT_MAX_AGE_DAYS:
        return (
            None,
            None,
            (f"public float last filed {latest.filed}, older than {FLOAT_MAX_AGE_DAYS} days"),
        )
    return latest.val, latest.end, None


def _filed_dates(doc: dict[str, Any]) -> list[date]:
    """Every filing date of a fact the revenue or float rules read, sorted."""
    facts = doc.get("facts") or {}
    dates: set[date] = set()
    sources = [("us-gaap", t) for t in UNIVERSE_REVENUE_TAGS + BANK_REVENUE_TAGS]
    sources.append(("dei", FLOAT_TAG))
    for taxonomy, tag in sources:
        for rows in (((facts.get(taxonomy) or {}).get(tag) or {}).get("units") or {}).values():
            dates.update(date.fromisoformat(r["filed"]) for r in rows if r.get("filed"))
    return sorted(dates)


def evaluate_filer(
    doc: dict[str, Any],
    months: Iterable[pd.Timestamp],
    size_measure: str = "public_float",
) -> list[FilerMonth]:
    """Eligibility, public float and TTM revenue of one filer at each month-end.

    Inputs change only on filing dates, so revenue and float facts are computed once per latest
    filing date ``key`` and reused. A TTM that is stale at ``key`` is also stale at any later
    as-of date, and the newest-period tag at ``key`` is the newest at as-of too, so applying
    the age rules again at each month's own as-of date gives the same result as evaluating every
    month from scratch (only the date quoted in a "missing" message can differ).
    """
    if size_measure not in SIZE_MEASURES:
        raise ValueError(f"size_measure must be one of {SIZE_MEASURES}")
    cik = int(doc.get("cik", 0))
    name = str(doc.get("entityName", ""))
    filed = _filed_dates(doc)
    memo: dict[date | None, tuple[_Ttm, Any]] = {}
    out = []
    for m in months:
        as_of = as_of_for(m)
        pos = pd.Series(filed).searchsorted(as_of, side="right") if filed else 0
        key = filed[pos - 1] if pos else None
        if key not in memo:
            memo[key] = (
                revenue_as_of(doc, key)
                if key
                else _Ttm(None, "no revenue filed", None, None, (), ""),
                _load(doc, "dei", FLOAT_TAG, "USD", key) if key else [],
            )
        ttm, float_facts = memo[key]
        revenue_reason = ttm.reason
        if ttm.value is not None and ttm.period_end is not None:
            if (as_of - ttm.period_end).days > MAX_STALE_DAYS:
                revenue_reason = (
                    f"{ttm.tag}: stale, latest period ended {ttm.period_end}, more than "
                    f"{MAX_STALE_DAYS} days before {as_of}"
                )
            elif ttm.value <= 0:
                revenue_reason = "non-positive TTM revenue"
        flt, float_end, float_reason = _float_from(float_facts, as_of)
        if size_measure == "public_float":
            reason = float_reason
        else:
            reason = revenue_reason or float_reason
        has_revenue = revenue_reason is None
        out.append(
            FilerMonth(
                cik=cik,
                month_end=pd.Timestamp(m),
                entity_name=name,
                public_float=flt,
                float_as_of=float_end,
                revenue_ttm=ttm.value if has_revenue else None,
                revenue_tag=ttm.tag if has_revenue else None,
                revenue_period_end=ttm.period_end if has_revenue else None,
                revenue_reason=revenue_reason,
                reason=reason,
            )
        )
    return out


def rank_month(
    rows: list[FilerMonth], size: int = UNIVERSE_SIZE, size_measure: str = "public_float"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Members (top ``size`` by the size measure) and the exclusion log for one month-end."""
    cols = list(FilerMonth.__dataclass_fields__)
    frame = pd.DataFrame([r.__dict__ for r in rows], columns=cols)
    if frame.empty:
        return (
            pd.DataFrame(columns=cols + ["size_measure", "rank"]),
            pd.DataFrame(columns=["cik", "month_end", "reason"]),
        )
    excluded = frame[frame["reason"].notna()][["cik", "month_end", "reason"]]
    eligible = frame[frame["reason"].isna()]
    sort_col = "public_float" if size_measure == "public_float" else "revenue_ttm"
    kept = eligible.sort_values([sort_col, "cik"], ascending=[False, True]).head(size).copy()
    kept["size_measure"] = size_measure
    kept["rank"] = range(1, len(kept) + 1)
    return kept.reset_index(drop=True), excluded.reset_index(drop=True)


def build_universe(
    docs: Iterable[dict[str, Any]],
    start: str = "2010-01-31",
    end: str | None = None,
    size: int = UNIVERSE_SIZE,
    size_measure: str = "public_float",
    delisted: Mapping[int, pd.Timestamp] | None = None,
    min_ever_revenue: float = MIN_EVER_ANNUAL_REVENUE,
    min_ever_float: float = MIN_EVER_PUBLIC_FLOAT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly universe from an iterable of companyfacts documents.

    Returns ``(members, exclusions)``: members has one row per (month_end, member) with rank,
    float, revenue and provenance; exclusions has one row per (cik, month_end) left out, with the
    reason. Filers below the pre-filter thresholds are not logged.
    """
    if size_measure not in SIZE_MEASURES:
        raise ValueError(f"size_measure must be one of {SIZE_MEASURES}")
    months = month_ends(start, end or pd.Timestamp.today().strftime("%Y-%m-%d"))
    gone = {int(k): pd.Timestamp(v) for k, v in (delisted or {}).items()}
    by_month: dict[pd.Timestamp, list[FilerMonth]] = {m: [] for m in months}
    for doc in docs:
        if not ever_large(doc, min_ever_revenue, min_ever_float):
            continue
        for row in evaluate_filer(doc, months, size_measure):
            effective = gone.get(row.cik)
            if effective is not None and row.month_end >= effective:
                row = FilerMonth(
                    **{**row.__dict__, "reason": f"delisted, effective {effective.date()}"}
                )
            by_month[row.month_end].append(row)
    members, exclusions = [], []
    for m in months:
        kept, excluded = rank_month(by_month[m], size, size_measure)
        members.append(kept)
        exclusions.append(excluded)
    return (
        pd.concat(members, ignore_index=True),
        pd.concat(exclusions, ignore_index=True),
    )
