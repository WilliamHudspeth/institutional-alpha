"""Point-in-time fundamentals from SEC ``companyfacts``.

Everything here answers one question: what had the company FILED, on or before ``as_of``?
A fact filed after the date is invisible, however old its period.

Selection rules (each is covered by a test):

* **Forms.** Only 10-K / 10-K/A / 10-KT / 10-Q / 10-Q/A facts (``ACCEPTED_FORMS``); proxy
  statements, 8-Ks and the like are ignored. Only USD facts (and ``shares`` for share counts).
* **Restatements.** The same period (``start``, ``end``) appears once per filing that reported
  it. The version with the latest ``filed`` on or before ``as_of`` wins: the restated value if
  the restatement was already filed, the original otherwise. Ties on ``filed`` go to the
  higher accession number.
* **TTM flows** (revenue, net income, operating income, cash flow, capex, interest expense).
  Periods are matched by their dates, never by ``fy``/``fp`` (those describe the filing, not
  the fact). Let ``FY`` be the latest annual (10-K, 350 to 380 days) fact.
    - No 10-Q fact for the tag ends after ``FY``: TTM = FY.
    - Otherwise ``YTD`` is the latest 10-Q year-to-date fact that starts within
      ``YTD_START_GAP_DAYS`` after FY ends, and ``PRIOR`` is the 10-Q fact for the same span one
      year earlier (start and end within ``PRIOR_YEAR_TOLERANCE_DAYS`` of 365 days earlier):
      TTM = FY + YTD - PRIOR.
    - If YTD or PRIOR is missing (or 10-Q data exists that no YTD fact connects to FY), the
      value is None with a reason. It is never a partial sum.
    - A TTM whose period ended more than ``MAX_STALE_DAYS`` before ``as_of`` is None ("stale"):
      the filer stopped reporting that concept.
* **Tag fallbacks** (revenue, pretax income): each tag is evaluated; the tag whose latest period
  is most recent wins, ties by list order. The tag used is recorded.
* **Total debt** (balance-sheet instant; never ``Liabilities``, never defaulted to zero).
  Candidates, each evaluated at a date where ALL its legs were reported; the candidate with the
  latest date wins, ties by this order:
    1. ``LongTermDebtNoncurrent`` + ``LongTermDebtCurrent``
    2. ``LongTermDebtNoncurrent`` + ``DebtCurrent``
    3. ``LongTermDebt`` (us-gaap: includes current maturities)
  Commercial paper or other short-term borrowings not tagged ``DebtCurrent`` are not included
  (a known understatement, visible in the provenance tags used).
* **Shares.** ``dei:EntityCommonStockSharesOutstanding`` (latest filed) when it was filed within
  ``DEI_MAX_AGE_DAYS`` of ``as_of``; otherwise ``WeightedAverageNumberOfDilutedSharesOutstanding``
  of the most recent period (a period average, not a point-in-time count: the tag says so).
* **Effective tax** = ``IncomeTaxExpenseBenefit`` / pretax income for the latest fiscal year;
  None when pretax <= 0 or the ratio is outside [0, ``MAX_EFFECTIVE_TAX_RATE``], the same rule
  as the yfinance adapter.
* **ROIC history** (per fiscal year, most recent first) = NOPAT / invested capital, where
  NOPAT = OperatingIncomeLoss x (1 - that year's effective tax rate) and invested capital =
  StockholdersEquity + total debt - cash, all at the fiscal year end. Years missing any input
  are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any

from iam.data.edgar.client import EdgarClient
from iam.data.security import Fundamentals

ACCEPTED_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-Q", "10-Q/A"})
ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "10-KT"})
QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A"})

# A fiscal year is 52 or 53 weeks (364/371 days) or a calendar year; allow for both.
ANNUAL_MIN_DAYS = 350
ANNUAL_MAX_DAYS = 380
# A 10-Q year-to-date period starts the day after the fiscal year ends; allow for 52/53-week
# calendars that drift a few days.
YTD_START_GAP_DAYS = 8
# The prior-year comparison period sits 365 days earlier, give or take a 52/53-week shift.
PRIOR_YEAR_TOLERANCE_DAYS = 10
# One fiscal year plus the 90-day 10-K deadline, rounded to 15 months: a period older than this
# at as_of means the filer stopped reporting the concept.
MAX_STALE_DAYS = 456
# A quarterly cycle: 3 months + the 45-day 10-Q deadline, rounded up. Older cover-page share
# counts are replaced by the newer weighted average.
DEI_MAX_AGE_DAYS = 140
# Same cap the yfinance adapter applies: a ratio above this is a one-off, not a tax rate.
MAX_EFFECTIVE_TAX_RATE = 0.60
# Fiscal years of history to return, and the largest gap between consecutive fiscal year ends
# (one year plus five weeks of 52/53-week drift) before the history is considered broken.
HISTORY_YEARS = 10
HISTORY_MAX_GAP_DAYS = 400

REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
)
PRETAX_TAGS = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
)
DEBT_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("LongTermDebtNoncurrent", "LongTermDebtCurrent"),
    ("LongTermDebtNoncurrent", "DebtCurrent"),
    ("LongTermDebt",),
)
SHARES_DEI_TAG = "EntityCommonStockSharesOutstanding"
SHARES_FALLBACK_TAG = "WeightedAverageNumberOfDilutedSharesOutstanding"

FIELD_NAMES = (
    "revenue_ttm",
    "revenue_history",
    "net_income_ttm",
    "operating_margin",
    "fcf_ttm",
    "capex_ttm",
    "total_debt",
    "cash_and_equivalents",
    "interest_expense_ttm",
    "effective_tax_rate",
    "shares_outstanding",
    "equity",
    "roic_history",
)


# --------------------------------------------------------------------------- types
@dataclass(frozen=True)
class Provenance:
    """The filed fact a value came from."""

    tag: str
    taxonomy: str
    unit: str
    value: float
    accn: str
    form: str
    filed: str
    end: str
    start: str | None = None
    fy: int | None = None
    fp: str | None = None
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class FieldValue:
    """A value (or None plus a reason) with the filings that produced it."""

    value: Any = None
    reason: str | None = None
    tag: str | None = None
    method: str | None = None
    period_end: str | None = None
    sources: tuple[Provenance, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "reason": self.reason,
            "tag": self.tag,
            "method": self.method,
            "period_end": self.period_end,
            "sources": [s.to_dict() for s in self.sources],
        }


def _missing(reason: str) -> FieldValue:
    return FieldValue(reason=reason)


@dataclass(frozen=True)
class EdgarFundamentals:
    cik: int
    entity_name: str
    as_of: date
    revenue_ttm: FieldValue = field(default_factory=FieldValue)
    revenue_history: FieldValue = field(default_factory=FieldValue)
    net_income_ttm: FieldValue = field(default_factory=FieldValue)
    operating_margin: FieldValue = field(default_factory=FieldValue)
    fcf_ttm: FieldValue = field(default_factory=FieldValue)
    capex_ttm: FieldValue = field(default_factory=FieldValue)
    total_debt: FieldValue = field(default_factory=FieldValue)
    cash_and_equivalents: FieldValue = field(default_factory=FieldValue)
    interest_expense_ttm: FieldValue = field(default_factory=FieldValue)
    effective_tax_rate: FieldValue = field(default_factory=FieldValue)
    shares_outstanding: FieldValue = field(default_factory=FieldValue)
    equity: FieldValue = field(default_factory=FieldValue)
    roic_history: FieldValue = field(default_factory=FieldValue)


@dataclass(frozen=True)
class _Fact:
    tag: str
    taxonomy: str
    unit: str
    val: float
    accn: str
    form: str
    filed: date
    end: date
    start: date | None
    fy: int | None
    fp: str | None

    @property
    def days(self) -> int | None:
        return None if self.start is None else (self.end - self.start).days

    def prov(self, role: str = "") -> Provenance:
        return Provenance(
            tag=self.tag,
            taxonomy=self.taxonomy,
            unit=self.unit,
            value=self.val,
            accn=self.accn,
            form=self.form,
            filed=self.filed.isoformat(),
            end=self.end.isoformat(),
            start=None if self.start is None else self.start.isoformat(),
            fy=self.fy,
            fp=self.fp,
            role=role,
        )


# --------------------------------------------------------------------------- loading
def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _load(doc: dict[str, Any], taxonomy: str, tag: str, unit: str, as_of: date) -> list[_Fact]:
    """Facts for one tag that were FILED on or before ``as_of``, one per period (latest filed)."""
    rows = ((((doc.get("facts") or {}).get(taxonomy) or {}).get(tag) or {}).get("units") or {}).get(
        unit
    ) or []
    best: dict[tuple[date | None, date], _Fact] = {}
    for r in rows:
        val = r.get("val")
        if r.get("form") not in ACCEPTED_FORMS or isinstance(val, bool):
            continue
        if not isinstance(val, int | float):
            continue
        filed = date.fromisoformat(r["filed"])
        if filed > as_of:
            continue
        start = date.fromisoformat(r["start"]) if r.get("start") else None
        end = date.fromisoformat(r["end"])
        fact = _Fact(
            tag, taxonomy, unit, float(val), str(r.get("accn", "")), r["form"], filed, end, start,
            r.get("fy"), r.get("fp"),
        )  # fmt: skip
        key = (start, end)
        old = best.get(key)
        if old is None or (fact.filed, fact.accn) > (old.filed, old.accn):
            best[key] = fact
    return list(best.values())


def _usd(doc: dict[str, Any], tag: str, as_of: date) -> list[_Fact]:
    return _load(doc, "us-gaap", tag, "USD", as_of)


def _stale(period_end: date, as_of: date) -> bool:
    return (as_of - period_end).days > MAX_STALE_DAYS


# --------------------------------------------------------------------------- TTM
@dataclass(frozen=True)
class _Ttm:
    value: float | None
    reason: str | None
    period_end: date | None
    method: str | None
    sources: tuple[Provenance, ...]
    tag: str


def _ttm_none(tag: str, reason: str) -> _Ttm:
    return _Ttm(None, reason, None, None, (), tag)


def _ttm(doc: dict[str, Any], tag: str, as_of: date) -> _Ttm:
    facts = _usd(doc, tag, as_of)
    flows = [f for f in facts if f.start is not None]
    annual = [
        f
        for f in flows
        if f.form in ANNUAL_FORMS and ANNUAL_MIN_DAYS <= (f.days or 0) <= ANNUAL_MAX_DAYS
    ]
    if not annual:
        return _ttm_none(tag, f"no {tag} fiscal-year fact filed on or before {as_of}")
    fy = max(annual, key=lambda f: (f.end, f.filed))
    newer = [f for f in flows if f.form in QUARTERLY_FORMS and f.end > fy.end]

    if not newer:
        value, end, method = fy.val, fy.end, "FY"
        sources: tuple[Provenance, ...] = (fy.prov("fy"),)
    else:
        ytds = [f for f in newer if 0 < (f.start - fy.end).days <= YTD_START_GAP_DAYS]  # type: ignore[operator]
        if not ytds:
            return _ttm_none(
                tag,
                f"{tag}: 10-Q data exists after the latest 10-K (period end {fy.end}) but no "
                "year-to-date fact connects to it",
            )
        ytd = max(ytds, key=lambda f: (f.end, f.filed))
        priors = [
            f
            for f in flows
            if f.form in QUARTERLY_FORMS
            and abs((ytd.end - f.end).days - 365) <= PRIOR_YEAR_TOLERANCE_DAYS
            and abs((ytd.start - f.start).days - 365) <= PRIOR_YEAR_TOLERANCE_DAYS  # type: ignore[operator]
        ]
        if not priors:
            return _ttm_none(
                tag,
                f"{tag}: prior-year year-to-date fact for {ytd.start} to {ytd.end} not filed; "
                "TTM not computed (no partial sum)",
            )
        prior = min(priors, key=lambda f: (abs((ytd.end - f.end).days - 365), -f.filed.toordinal()))
        value = fy.val + ytd.val - prior.val
        end, method = ytd.end, "FY + YTD - prior YTD"
        sources = (fy.prov("fy"), ytd.prov("ytd"), prior.prov("prior_ytd"))

    if _stale(end, as_of):
        return _ttm_none(
            tag,
            f"{tag}: stale, latest period ended {end}, more than {MAX_STALE_DAYS} days before {as_of}",
        )
    return _Ttm(value, None, end, method, sources, tag)


def _best_ttm(doc: dict[str, Any], tags: tuple[str, ...], as_of: date) -> _Ttm:
    """Evaluate each tag; the one with the most recent period wins (ties: list order)."""
    results = [_ttm(doc, t, as_of) for t in tags]
    ok = [r for r in results if r.value is not None and r.period_end is not None]
    if ok:
        # max() keeps the first of equal keys, so ties resolve to list order
        return max(ok, key=lambda r: r.period_end or date.min)
    reasons = "; ".join(r.reason or "" for r in results)
    return _ttm_none(tags[0], reasons)


def _as_field(t: _Ttm) -> FieldValue:
    if t.value is None:
        return _missing(t.reason or f"{t.tag} unavailable")
    return FieldValue(t.value, None, t.tag, t.method, t.period_end.isoformat(), t.sources)  # type: ignore[union-attr]


# --------------------------------------------------------------------------- instants
def _latest_instant(facts: list[_Fact], as_of: date, at_end: date | None = None) -> _Fact | None:
    pool = [f for f in facts if f.start is None and (at_end is None or f.end == at_end)]
    if not pool:
        return None
    return max(pool, key=lambda f: (f.end, f.filed))


def _instant_field(doc: dict[str, Any], tag: str, as_of: date) -> FieldValue:
    fact = _latest_instant(_usd(doc, tag, as_of), as_of)
    if fact is None:
        return _missing(f"no {tag} balance-sheet fact filed on or before {as_of}")
    if _stale(fact.end, as_of):
        return _missing(f"{tag}: stale, latest balance sheet is {fact.end}")
    return FieldValue(
        fact.val, None, tag, "latest balance sheet", fact.end.isoformat(), (fact.prov(),)
    )


def _debt(doc: dict[str, Any], as_of: date, at_end: date | None = None) -> FieldValue:
    best: tuple[date, int, tuple[_Fact, ...]] | None = None
    for rank, legs in enumerate(DEBT_CANDIDATES):
        by_tag = []
        for tag in legs:
            by_end = {f.end: f for f in _usd(doc, tag, as_of) if f.start is None}
            by_tag.append(by_end)
        common = set.intersection(*(set(d) for d in by_tag))
        if at_end is not None:
            common &= {at_end}
        if not common:
            continue
        end = max(common)
        picked = tuple(d[end] for d in by_tag)
        if best is None or end > best[0]:  # strict: ties keep the earlier (higher-priority) rank
            best = (end, rank, picked)
    if best is None:
        tags = " | ".join("+".join(c) for c in DEBT_CANDIDATES)
        return _missing(
            f"no debt reported at a common date ({tags}); not taken from Liabilities, not zero"
        )
    end, _, picked = best
    if at_end is None and _stale(end, as_of):  # a pinned historical date is not 'latest'
        return _missing(f"total debt: stale, latest balance sheet is {end}")
    tag = "+".join(f.tag for f in picked)
    return FieldValue(
        sum(f.val for f in picked),
        None,
        tag if len(picked) > 1 else picked[0].tag,
        "sum of debt legs at one balance-sheet date" if len(picked) > 1 else "total long-term debt",
        end.isoformat(),
        tuple(f.prov(f.tag) for f in picked),
    )


# --------------------------------------------------------------------------- derived
def _combine(
    a: _Ttm, b: _Ttm, as_field: str, label_a: str, label_b: str
) -> tuple[_Ttm, _Ttm] | FieldValue:
    """Both legs must exist and cover the same period; else None with the reason."""
    if a.value is None:
        return _missing(f"{as_field}: {label_a} unavailable ({a.reason})")
    if b.value is None:
        return _missing(f"{as_field}: {label_b} unavailable ({b.reason})")
    if a.period_end != b.period_end:
        return _missing(
            f"{as_field}: {label_a} ends {a.period_end} but {label_b} ends {b.period_end}"
        )
    return a, b


def _operating_margin(doc: dict[str, Any], as_of: date, revenue: _Ttm) -> FieldValue:
    op = _ttm(doc, "OperatingIncomeLoss", as_of)
    legs = _combine(op, revenue, "operating_margin", "operating income", "revenue")
    if isinstance(legs, FieldValue):
        return legs
    op, rev = legs
    if not rev.value or rev.value <= 0:
        return _missing("operating_margin: revenue not positive")
    return FieldValue(
        op.value / rev.value,  # type: ignore[operator]
        None,
        op.tag,
        "OperatingIncomeLoss TTM / revenue TTM (same period)",
        op.period_end.isoformat(),  # type: ignore[union-attr]
        tuple(Provenance(**{**s.to_dict(), "role": f"op:{s.role}"}) for s in op.sources)
        + tuple(Provenance(**{**s.to_dict(), "role": f"rev:{s.role}"}) for s in rev.sources),
    )


def _fcf(doc: dict[str, Any], as_of: date) -> tuple[FieldValue, FieldValue]:
    capex = _ttm(doc, "PaymentsToAcquirePropertyPlantAndEquipment", as_of)
    cfo = _ttm(doc, "NetCashProvidedByUsedInOperatingActivities", as_of)
    capex_field = _as_field(capex)
    legs = _combine(cfo, capex, "fcf_ttm", "operating cash flow", "capex")
    if isinstance(legs, FieldValue):
        return legs, capex_field
    cfo, capex = legs
    return (
        FieldValue(
            cfo.value - capex.value,  # type: ignore[operator]
            None,
            "NetCashProvidedByUsedInOperatingActivities - PaymentsToAcquirePropertyPlantAndEquipment",
            "FCF = CFO - capex (same TTM period)",
            cfo.period_end.isoformat(),  # type: ignore[union-attr]
            tuple(Provenance(**{**s.to_dict(), "role": f"cfo:{s.role}"}) for s in cfo.sources)
            + tuple(
                Provenance(**{**s.to_dict(), "role": f"capex:{s.role}"}) for s in capex.sources
            ),
        ),
        capex_field,
    )


def _annual_facts(doc: dict[str, Any], tag: str, as_of: date) -> dict[tuple[date, date], _Fact]:
    return {
        (f.start, f.end): f  # type: ignore[misc]
        for f in _usd(doc, tag, as_of)
        if f.start is not None
        and f.form in ANNUAL_FORMS
        and ANNUAL_MIN_DAYS <= (f.days or 0) <= ANNUAL_MAX_DAYS
    }


def _tax_pairs(doc: dict[str, Any], as_of: date) -> list[tuple[_Fact, _Fact]]:
    """(tax, pretax) fiscal-year pairs for the same period, latest first (tag order breaks ties)."""
    tax = _annual_facts(doc, "IncomeTaxExpenseBenefit", as_of)
    pairs: list[tuple[_Fact, _Fact, int]] = []
    for rank, ptag in enumerate(PRETAX_TAGS):
        for key, pre in _annual_facts(doc, ptag, as_of).items():
            if key in tax:
                pairs.append((tax[key], pre, rank))
    pairs.sort(key=lambda p: (-p[0].end.toordinal(), p[2]))
    seen: set[date] = set()
    out = []
    for t, p, _ in pairs:
        if t.end not in seen:  # one pair per fiscal year: the highest-priority pretax tag
            seen.add(t.end)
            out.append((t, p))
    return out


def _rate(tax: _Fact, pretax: _Fact) -> tuple[float | None, str | None]:
    if pretax.val <= 0:
        return None, f"pretax income {pretax.val:g} <= 0"
    rate = tax.val / pretax.val
    if not 0.0 <= rate <= MAX_EFFECTIVE_TAX_RATE:
        return None, f"tax/pretax ratio {rate:.3f} outside [0, {MAX_EFFECTIVE_TAX_RATE}]"
    return rate, None


def _effective_tax(doc: dict[str, Any], as_of: date) -> FieldValue:
    pairs = _tax_pairs(doc, as_of)
    if not pairs:
        return _missing(
            "effective_tax_rate: no fiscal year with both tax expense and pretax income"
        )
    tax, pretax = pairs[0]
    if _stale(tax.end, as_of):
        return _missing(f"effective_tax_rate: stale, latest fiscal year ended {tax.end}")
    rate, why = _rate(tax, pretax)
    if rate is None:
        return _missing(f"effective_tax_rate: {why}")
    return FieldValue(
        rate,
        None,
        f"{tax.tag} / {pretax.tag}",
        "latest fiscal year tax expense / pretax income",
        tax.end.isoformat(),
        (tax.prov("tax"), pretax.prov("pretax")),
    )


def _shares(doc: dict[str, Any], as_of: date) -> FieldValue:
    dei = _load(doc, "dei", SHARES_DEI_TAG, "shares", as_of)
    dei_note = ""
    if dei:
        latest = max(dei, key=lambda f: (f.filed, f.end))
        if (as_of - latest.filed).days <= DEI_MAX_AGE_DAYS:
            return FieldValue(
                latest.val, None, SHARES_DEI_TAG, "cover-page shares outstanding",
                latest.end.isoformat(), (latest.prov(),),
            )  # fmt: skip
        dei_note = f"dei shares last filed {latest.filed} are stale; "
    waso = [
        f
        for f in _load(doc, "us-gaap", SHARES_FALLBACK_TAG, "shares", as_of)
        if f.start is not None and f.form in ACCEPTED_FORMS
    ]
    if not waso:
        return _missing(f"shares_outstanding: {dei_note}no {SHARES_FALLBACK_TAG} facts either")
    pick = max(waso, key=lambda f: (f.end, -(f.days or 0), f.filed))
    if _stale(pick.end, as_of):
        return _missing(f"shares_outstanding: {dei_note}diluted share facts are stale ({pick.end})")
    return FieldValue(
        pick.val, None, SHARES_FALLBACK_TAG,
        "weighted-average diluted shares of the latest period (not a point-in-time count)",
        pick.end.isoformat(), (pick.prov(),),
    )  # fmt: skip


def _revenue_history(doc: dict[str, Any], as_of: date, tag: str) -> FieldValue:
    facts = sorted(_annual_facts(doc, tag, as_of).values(), key=lambda f: f.end, reverse=True)
    if not facts:
        return _missing(f"revenue_history: no {tag} fiscal-year facts")
    if _stale(facts[0].end, as_of):
        return _missing(f"revenue_history: stale, latest fiscal year ended {facts[0].end}")
    chosen = [facts[0]]
    for f in facts[1:]:
        if len(chosen) >= HISTORY_YEARS or (chosen[-1].end - f.end).days > HISTORY_MAX_GAP_DAYS:
            break
        chosen.append(f)
    return FieldValue(
        [f.val for f in chosen],
        None,
        tag,
        "fiscal-year values, most recent first, stopping at the first missing year",
        chosen[0].end.isoformat(),
        tuple(f.prov("fy") for f in chosen),
    )


def _roic_history(doc: dict[str, Any], as_of: date) -> FieldValue:
    op = _annual_facts(doc, "OperatingIncomeLoss", as_of)
    tax_by_end = {t.end: (t, p) for t, p in _tax_pairs(doc, as_of)}
    values: list[float] = []
    sources: list[Provenance] = []
    for (_, end), opinc in sorted(op.items(), key=lambda kv: kv[0][1], reverse=True):
        if len(values) >= HISTORY_YEARS:
            break
        pair = tax_by_end.get(end)
        if pair is None:
            continue
        rate, _why = _rate(*pair)
        if rate is None:
            continue
        equity = _latest_instant(_usd(doc, "StockholdersEquity", as_of), as_of, end)
        cash = _latest_instant(
            _usd(doc, "CashAndCashEquivalentsAtCarryingValue", as_of), as_of, end
        )
        debt = _debt(doc, as_of, at_end=end)
        if equity is None or cash is None or debt.value is None:
            continue
        invested = equity.val + debt.value - cash.val
        if invested <= 0:
            continue
        values.append(opinc.val * (1.0 - rate) / invested)
        tag_ = f"roic:{end.isoformat()}"
        sources += [
            opinc.prov(f"{tag_}:opinc"),
            pair[0].prov(f"{tag_}:tax"),
            pair[1].prov(f"{tag_}:pretax"),
        ]
        sources += [equity.prov(f"{tag_}:equity"), cash.prov(f"{tag_}:cash")]
        sources += [Provenance(**{**s.to_dict(), "role": f"{tag_}:debt"}) for s in debt.sources]
    if not values:
        return _missing(
            "roic_history: no fiscal year has operating income, tax, equity, debt and cash together"
        )
    latest_end = date.fromisoformat(sources[0].end)
    if _stale(latest_end, as_of):
        return _missing(f"roic_history: stale, latest fiscal year ended {latest_end}")
    return FieldValue(
        values,
        None,
        "OperatingIncomeLoss",
        "ROIC = OperatingIncomeLoss x (1 - effective tax rate) / invested capital; "
        "invested capital = StockholdersEquity + total debt - cash, all at the fiscal year end",
        latest_end.isoformat(),
        tuple(sources),
    )


# --------------------------------------------------------------------------- public API
def fundamentals_from_companyfacts(doc: dict[str, Any], as_of: date | str) -> EdgarFundamentals:
    """Fundamentals using only facts filed on or before ``as_of`` (pure, no I/O)."""
    when = _as_date(as_of)
    revenue = _best_ttm(doc, REVENUE_TAGS, when)
    fcf, capex = _fcf(doc, when)
    return EdgarFundamentals(
        cik=int(doc.get("cik", 0) or 0),
        entity_name=str(doc.get("entityName", "")),
        as_of=when,
        revenue_ttm=_as_field(revenue),
        revenue_history=_revenue_history(doc, when, revenue.tag)
        if revenue.value is not None
        else _missing(f"revenue_history: {revenue.reason}"),
        net_income_ttm=_as_field(_ttm(doc, "NetIncomeLoss", when)),
        operating_margin=_operating_margin(doc, when, revenue),
        fcf_ttm=fcf,
        capex_ttm=capex,
        total_debt=_debt(doc, when),
        cash_and_equivalents=_instant_field(doc, "CashAndCashEquivalentsAtCarryingValue", when),
        interest_expense_ttm=_as_field(_ttm(doc, "InterestExpense", when)),
        effective_tax_rate=_effective_tax(doc, when),
        shares_outstanding=_shares(doc, when),
        equity=_instant_field(doc, "StockholdersEquity", when),
        roic_history=_roic_history(doc, when),
    )


def fundamentals_as_of(
    cik: int, as_of: date | str, *, client: EdgarClient | None = None
) -> EdgarFundamentals:
    """Fetch (cached) companyfacts for ``cik`` and return what was filed by ``as_of``."""
    doc = (client or EdgarClient()).companyfacts(cik)
    result = fundamentals_from_companyfacts(doc, as_of)
    return EdgarFundamentals(
        **{**{f.name: getattr(result, f.name) for f in fields(result)}, "cik": cik}
    )


def to_fundamentals(ef: EdgarFundamentals) -> tuple[Fundamentals, dict[str, Any]]:
    """Map to the engine's ``Fundamentals`` plus a JSON-serialisable provenance dict.

    Missing values stay ``None`` (or ``[]`` for history lists); the reason is in the
    provenance. ``Fundamentals`` has no equity field, so equity appears in provenance only.
    """
    values: dict[str, Any] = {}
    for name in FIELD_NAMES:
        fv: FieldValue = getattr(ef, name)
        if name == "equity":
            continue
        if name in ("revenue_history", "roic_history"):
            values[name] = list(fv.value) if fv.value is not None else []
        else:
            values[name] = fv.value
    prov: dict[str, Any] = {name: getattr(ef, name).to_dict() for name in FIELD_NAMES}
    prov["_meta"] = {
        "source": "SEC EDGAR companyfacts",
        "cik": ef.cik,
        "entity_name": ef.entity_name,
        "as_of": ef.as_of.isoformat(),
    }
    return Fundamentals(**values), prov
