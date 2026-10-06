"""Point-in-time geographic revenue mix from the 10-K XBRL instance.

``companyfacts`` has no dimensional facts, but the 10-K instance reports revenue on
``StatementGeographicalAxis``. This module answers: what geographic revenue split had the
company FILED, on or before ``as_of``, and how complete is it? The result feeds
``Security.revenue_mix`` (and so ``company_erp`` / ``company_marginal_tax``). Missing or
ambiguous data is ``None`` with a reason; nothing is guessed.

Selection rules (each is covered by a test):

* **Filing.** The latest 10-K with ``filingDate <= as_of`` in ``submissions.filings.recent``
  (about the last 1,000 filings). If ``recent`` holds no 10-K that old, the older pages in
  ``filings.files`` are followed newest first (pages whose ``filingFrom`` is after ``as_of``
  are never fetched) until one yields a 10-K. A 10-K/A is used only when it is filed after the
  10-K it amends and carries a full XBRL instance (a dimensionless annual revenue total); a Part
  III amendment has no such instance and is ignored. 10-KT (transition period) is not accepted.
  The CIK comes from :func:`iam.data.edgar.cik.resolve_cik` with ``as_of`` (BLK: old CIK
  before 2024-11-06). A 10-K that cannot be read is reported, never replaced by an older one.
* **Instance.** Found through the filing's ``index.json``, never by a guessed name: the single
  file ending ``_htm.xml`` (the instance extracted from inline XBRL); otherwise the single
  ``.xml`` that is not a linkbase (``_cal``, ``_def``, ``_lab``, ``_pre``, ``_ref``) or
  ``FilingSummary.xml``. Zero or several candidates: None with a reason.
* **Period.** The fiscal year: the dimensionless revenue total whose duration is 350 to 380
  days and ends on the 10-K's period end (``dei:DocumentPeriodEndDate``, which must equal the
  submissions ``reportDate`` when both exist). Prior-year and quarterly contexts are ignored.
* **Concept.** First of Revenues, RevenueFromContractWithCustomerExcludingAssessedTax,
  SalesRevenueNet, RevenuesExcludingInterestAndDividends that has geographic facts AND a
  dimensionless total for that period (the last is how BlackRock tagged FY2019 and FY2020).
  The tag is recorded.
* **Contexts.** Only a context whose segment/scenario holds exactly one explicit member, on
  ``srt:`` or ``us-gaap:StatementGeographicalAxis``. A context with any other dimension (product,
  segment) is ignored. Identical duplicate facts collapse; conflicting ones are None.
* **Eliminations.** A member with a value <= 0 is excluded and reported. Coverage still
  counts it (net sum / total), so a filer's eliminations line does not read as a gap.
* **Overlap.** Members summing to more than 101% of the total are ambiguous (a country listed
  next to its region, or "non-US" next to countries). A partition is recovered only when it is
  proven by the data: countries only (``country:`` members), else areas only (everything else),
  summing to within 1% of the total. Both can hold; countries win (finer). Otherwise None with
  "overlapping geographic members".
* **Keys.** See :func:`map_member`. Unresolved members stay in the mix under their local name,
  so ``company_erp`` reports coverage below 100% instead of hiding the gap. Values are fractions
  of the geographic sum; ``coverage_of_total_revenue`` is that sum over the reported total.

Parsing is stdlib ``xml.etree`` after the document is refused if it declares a DOCTYPE or
ENTITY (see ``_refuse_dtd``); no dependency is added.
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET  # nosec B405 - input is screened by _refuse_dtd before parsing
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from iam.data.edgar.cik import UnresolvedTickerError, resolve_cik
from iam.data.edgar.client import EdgarClient, EdgarError, archive_file_url
from iam.data.edgar.facts import ANNUAL_MAX_DAYS, ANNUAL_MIN_DAYS, REVENUE_TAGS
from iam.data.edgar.iso_countries import ISO2_TO_DATASET_NAME
from iam.valuation.country_risk import load_country_erp, resolve_revenue_key

GEOGRAPHY_REVENUE_CONCEPTS = (*REVENUE_TAGS, "RevenuesExcludingInterestAndDividends")
TENK_FORMS = frozenset({"10-K", "10-K/A"})
# Members may exceed the total by this much (rounding of reported figures, in millions) before
# the split is called overlapping; a recovered partition must land within the same band.
OVERLAP_TOLERANCE = 0.01
AMBIGUOUS_OVERLAP_REASON = "overlapping geographic members"

_XBRLI = "http://www.xbrl.org/2003/instance"
_XBRLDI = "http://xbrl.org/2006/xbrldi"
_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
_GAAP_NS = "http://fasb.org/us-gaap/"
_SRT_NS = "http://fasb.org/srt/"
_DEI_NS = "http://xbrl.sec.gov/dei/"
_COUNTRY_NS = "http://xbrl.sec.gov/country/"
_ISO4217_NS = "http://www.xbrl.org/2003/iso4217"
_GEO_AXIS_LOCAL = "StatementGeographicalAxis"
_LINKBASE_SUFFIXES = ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml", "_ref.xml")

Qn = tuple[str, str]  # (namespace URI, local name)


# --------------------------------------------------------------------------- types
@dataclass(frozen=True)
class FilingRef:
    cik: int
    accn: str
    form: str
    filed: date
    report_date: str  # "" when the submissions row has none
    primary_document: str = ""


@dataclass(frozen=True)
class MemberRow:
    """One geographic member kept in the mix."""

    member: str  # as written in the instance, e.g. "srt:EuropeMember"
    key: str  # the Security.revenue_mix key it feeds
    value: float  # reported revenue
    resolved: bool  # country_risk resolves ``key``


@dataclass(frozen=True)
class UnresolvedMember:
    member: str
    key: str
    share: float  # of the geographic sum


@dataclass(frozen=True)
class ExcludedMember:
    member: str
    value: float
    reason: str


@dataclass(frozen=True)
class GeographicMix:
    mix: dict[str, float]  # revenue_mix key -> fraction of the geographic sum
    coverage_of_total_revenue: float  # geographic sum / dimensionless total
    resolved_share: float  # fraction of the mix whose key country_risk resolves
    unresolved: tuple[UnresolvedMember, ...]
    excluded: tuple[ExcludedMember, ...]
    concept: str
    period_start: str
    period_end: str
    total_revenue: float
    members: tuple[MemberRow, ...]
    cik: int
    accn: str
    form: str
    filed: str
    instance_url: str
    notes: tuple[str, ...] = field(default=())

    def source(self) -> str:
        return (
            f"SEC EDGAR {self.form} {self.accn} filed {self.filed}, FY ending {self.period_end}, "
            f"tag {self.concept}, coverage {self.coverage_of_total_revenue * 100:.1f}%"
        )


@dataclass(frozen=True)
class GeographicMixResult:
    """A mix, or None plus the reason there is none."""

    mix: GeographicMix | None = None
    reason: str | None = None
    cik: int | None = None
    as_of: date | None = None


def _fail(reason: str, **kw: Any) -> GeographicMixResult:
    return GeographicMixResult(reason=reason, **kw)


# --------------------------------------------------------------------------- member mapping
def _strip_member_suffix(local: str) -> str:
    for suffix in ("SegmentMember", "Member"):
        if local.endswith(suffix) and len(local) > len(suffix):
            return local[: -len(suffix)]
    return local


def map_member(namespace: str, local: str, table: dict[str, Any] | None = None) -> tuple[str, bool]:
    """``(revenue_mix key, resolved)`` for one geographic member.

    * ``country:XX``: the dataset name from the ISO table; a code the dataset lacks keeps the
      code as its key and is unresolved.
    * Any other member: the local name without its ``Member`` / ``SegmentMember`` suffix is run
      through ``resolve_revenue_key``. A country result becomes the dataset name; a region or
      aggregate result keeps the derived name (``Americas``), so country_risk still applies and
      states its own approximation note (``americas treated as North America``). No result:
      unresolved, the derived name is kept. Nothing is mapped by guess.
    """
    tbl = table if table is not None else load_country_erp()
    if namespace.startswith(_COUNTRY_NS):
        code = local.upper()
        name = ISO2_TO_DATASET_NAME.get(code)
        if name is not None and resolve_revenue_key(name, tbl) is not None:
            return name, True
        return (name or code), False
    key = _strip_member_suffix(local)
    hit = resolve_revenue_key(key, tbl)
    if hit is None:
        return key, False
    return (hit[0] if hit[0] in tbl.get("countries", {}) else key), True


# --------------------------------------------------------------------------- instance parsing
class InstanceParseError(ValueError):
    """The instance cannot be read safely."""


@dataclass(frozen=True)
class _Context:
    start: str | None
    end: str | None  # None for an instant
    dims: tuple[tuple[Qn, Qn | None], ...]  # (axis, explicit member or None for typed/other)


@dataclass(frozen=True)
class _Fact:
    concept: str
    context: str
    unit: str
    value: float


@dataclass
class _Instance:
    contexts: dict[str, _Context] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)  # unit id -> currency measure
    facts: list[_Fact] = field(default_factory=list)
    member_labels: dict[Qn, str] = field(default_factory=dict)  # member -> as written
    document_type: str | None = None
    period_end: str | None = None


def _refuse_dtd(data: bytes) -> None:
    """Instances never declare a DOCTYPE or entities; one that does is refused unparsed."""
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", data, re.IGNORECASE):
        raise InstanceParseError("instance declares a DOCTYPE/ENTITY; refused")


def _qname(text: str, ns_map: dict[str, str]) -> Qn | None:
    prefix, sep, local = text.strip().partition(":")
    if not sep:
        return None
    uri = ns_map.get(prefix)
    return None if uri is None or not local else (uri, local)


def _local(tag: str) -> tuple[str, str]:
    ns, _, name = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
    return ns, name


def _parse_context(el: ET.Element, ns_map: dict[str, str], inst: _Instance) -> None:
    cid = el.get("id")
    period = el.find(f"{{{_XBRLI}}}period")
    if cid is None or period is None:
        return
    start = period.findtext(f"{{{_XBRLI}}}startDate")
    end = period.findtext(f"{{{_XBRLI}}}endDate")
    if start is None or end is None:  # an instant (balance sheet) is never a revenue period
        inst.contexts[cid] = _Context(None, None, ())
        return
    dims: list[tuple[Qn, Qn | None]] = []
    for holder in (
        el.find(f"{{{_XBRLI}}}entity/{{{_XBRLI}}}segment"),
        el.find(f"{{{_XBRLI}}}scenario"),
    ):
        if holder is None:
            continue
        for child in holder:
            axis = _qname(child.get("dimension", ""), ns_map) or ("", child.get("dimension", "?"))
            member: Qn | None = None
            if child.tag == f"{{{_XBRLDI}}}explicitMember":
                text = (child.text or "").strip()
                member = _qname(text, ns_map)
                if member is not None:
                    inst.member_labels.setdefault(member, text)
            dims.append((axis, member))
    inst.contexts[cid] = _Context(start.strip(), end.strip(), tuple(dims))


def parse_instance(data: bytes) -> _Instance:
    """Read the contexts, currency units and revenue/dei facts of an XBRL instance."""
    _refuse_dtd(data)
    inst = _Instance()
    ns_map: dict[str, str] = {}
    depth = 0
    try:
        events = ET.iterparse(  # nosec B314 - DOCTYPE/ENTITY refused above, no network resolution
            io.BytesIO(data), events=("start-ns", "start", "end")
        )
        for event, el in events:
            if event == "start-ns":
                prefix, uri = el  # type: ignore[misc]  # start-ns yields (prefix, uri) tuples
                ns_map.setdefault(prefix, uri)  # type: ignore[arg-type]
                continue
            if event == "start":
                depth += 1
                continue
            depth -= 1
            if depth != 1:
                continue  # only direct children of the root element are facts/contexts/units
            ns, name = _local(el.tag)
            if ns == _XBRLI and name == "context":
                _parse_context(el, ns_map, inst)
            elif ns == _XBRLI and name == "unit":
                measure = el.findtext(f"{{{_XBRLI}}}measure")
                uid = el.get("id")
                m = _qname(measure or "", ns_map)
                if uid and m and m[0].startswith(_ISO4217_NS):
                    inst.units[uid] = m[1]
            elif ns.startswith(_DEI_NS) and name in ("DocumentType", "DocumentPeriodEndDate"):
                text = (el.text or "").strip()
                if name == "DocumentType" and inst.document_type is None:
                    inst.document_type = text
                elif name == "DocumentPeriodEndDate" and inst.period_end is None:
                    inst.period_end = text
            elif ns.startswith(_GAAP_NS) and name in GEOGRAPHY_REVENUE_CONCEPTS:
                _collect_fact(el, name, inst)
            el.clear()
    except ET.ParseError as exc:
        raise InstanceParseError(f"cannot parse instance XML: {exc}") from exc
    return inst


def _collect_fact(el: ET.Element, concept: str, inst: _Instance) -> None:
    if el.get(_XSI_NIL, "").lower() in ("true", "1"):
        return
    ctx, unit = el.get("contextRef"), el.get("unitRef")
    if ctx is None or unit is None:
        return
    try:
        value = float((el.text or "").strip())
    except ValueError:
        return
    inst.facts.append(_Fact(concept, ctx, unit, value))


# --------------------------------------------------------------------------- extraction
def _days(start: str, end: str) -> int | None:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def _is_geo_axis(axis: Qn) -> bool:
    return axis[1] == _GEO_AXIS_LOCAL and axis[0].startswith((_SRT_NS, _GAAP_NS))


def _annual(ctx: _Context, period_end: str) -> bool:
    if ctx.start is None or ctx.end != period_end:
        return False
    days = _days(ctx.start, ctx.end)
    return days is not None and ANNUAL_MIN_DAYS <= days <= ANNUAL_MAX_DAYS


@dataclass(frozen=True)
class _Extraction:
    result: GeographicMixResult
    has_total: bool  # the instance carries a dimensionless annual revenue total


def _extract(
    inst: _Instance,
    *,
    report_date: str,
    cik: int,
    accn: str,
    form: str,
    filed: str,
    instance_url: str,
) -> _Extraction:
    def fail(reason: str, has_total: bool = False) -> _Extraction:
        return _Extraction(_fail(reason, cik=cik), has_total)

    if inst.document_type is not None and not inst.document_type.startswith("10-K"):
        return fail(f"instance document type is {inst.document_type!r}, not a 10-K")
    if inst.period_end and report_date and inst.period_end != report_date:
        return fail(
            f"period end mismatch: submissions reportDate {report_date} vs instance "
            f"DocumentPeriodEndDate {inst.period_end}"
        )
    period_end = inst.period_end or report_date
    if not period_end:
        return fail("no period end (no DocumentPeriodEndDate and no reportDate)")

    any_geo = False
    geo_without_total: list[str] = []
    has_total = False
    chosen: str | None = None
    for concept in GEOGRAPHY_REVENUE_CONCEPTS:
        totals: list[tuple[str, tuple[str, str], float]] = []  # (currency, period, value)
        geos: list[tuple[str, tuple[str, str], Qn, float]] = []
        for f in inst.facts:
            if f.concept != concept:
                continue
            ctx = inst.contexts.get(f.context)
            currency = inst.units.get(f.unit)
            if ctx is None or currency is None or not _annual(ctx, period_end):
                continue
            span = (ctx.start or "", ctx.end or "")
            if not ctx.dims:
                totals.append((currency, span, f.value))
            elif len(ctx.dims) == 1 and _is_geo_axis(ctx.dims[0][0]) and ctx.dims[0][1] is not None:
                geos.append((currency, span, ctx.dims[0][1], f.value))  # type: ignore[arg-type]
        has_total = has_total or bool(totals)
        if not geos:
            continue
        any_geo = True
        if not totals:
            geo_without_total.append(concept)
            continue
        chosen = concept
        break
    if chosen is None:
        if geo_without_total:
            return fail(
                "geographic revenue facts without a dimensionless total for the fiscal year "
                f"ending {period_end} (concepts: {', '.join(geo_without_total)})",
                has_total,
            )
        why = "no geographic revenue facts" if not any_geo else "no usable geographic facts"
        return fail(
            f"{why} for the fiscal year ending {period_end} "
            f"(tried {', '.join(GEOGRAPHY_REVENUE_CONCEPTS)})",
            has_total,
        )

    spans = {s for _, s, _ in totals}
    currencies = {c for c, _, _ in totals}
    if len(spans) != 1 or len(currencies) != 1:
        return fail(
            f"ambiguous fiscal-year total for {chosen}: {sorted(spans)} {sorted(currencies)}", True
        )
    span, currency = next(iter(spans)), next(iter(currencies))
    total_values = {v for _, _, v in totals}
    if len(total_values) != 1:
        return fail(f"conflicting duplicate total facts for {chosen}: {sorted(total_values)}", True)
    total = next(iter(total_values))
    if total <= 0:
        return fail(f"non-positive total revenue {total:g} for {chosen}", True)

    by_member: dict[Qn, set[float]] = {}
    for c, s, member, value in geos:
        if s == span and c == currency:
            by_member.setdefault(member, set()).add(value)
    if not by_member:
        return fail(
            f"no geographic facts in the same period and currency as the {chosen} total", True
        )
    for member, values in by_member.items():
        if len(values) > 1:
            label = inst.member_labels.get(member, member[1])
            return fail(f"conflicting duplicate facts for member {label}: {sorted(values)}", True)

    rows = {m: next(iter(v)) for m, v in by_member.items()}
    excluded: list[ExcludedMember] = []
    retained: dict[Qn, float] = {}
    negatives = 0.0
    for m, v in rows.items():
        if v <= 0:
            negatives += v
            excluded.append(
                ExcludedMember(
                    inst.member_labels.get(m, m[1]), v, "non-positive value (elimination or nil)"
                )
            )
        else:
            retained[m] = v
    if not retained:
        return fail("no positive geographic revenue members", True)

    net = sum(retained.values()) + negatives
    band = OVERLAP_TOLERANCE * total
    if net > total + band:
        recovered = _recover_partition(retained, total, band)
        if recovered is None:
            return fail(
                f"{AMBIGUOUS_OVERLAP_REASON}: members sum to {net / total:.1%} of total revenue "
                "and neither the country members nor the area members alone reach the total "
                f"within {OVERLAP_TOLERANCE:.0%}",
                True,
            )
        kept, dropped_kind = recovered
        for m in retained:
            if m not in kept:
                excluded.append(
                    ExcludedMember(
                        inst.member_labels.get(m, m[1]),
                        retained[m],
                        f"overlap: dropped {dropped_kind} members so the rest partition the total",
                    )
                )
        retained = {m: retained[m] for m in kept}
        net = sum(retained.values())

    table = load_country_erp()
    geo_sum = sum(retained.values())
    mix: dict[str, float] = {}
    members: list[MemberRow] = []
    unresolved: list[UnresolvedMember] = []
    resolved_share = 0.0
    for m, v in sorted(retained.items(), key=lambda kv: -kv[1]):
        key, resolved = map_member(m[0], m[1], table)
        label = inst.member_labels.get(m, m[1])
        share = v / geo_sum
        mix[key] = mix.get(key, 0.0) + share
        members.append(MemberRow(label, key, v, resolved))
        if resolved:
            resolved_share += share
        else:
            unresolved.append(UnresolvedMember(label, key, share))

    result = GeographicMix(
        mix=mix,
        coverage_of_total_revenue=net / total,
        resolved_share=resolved_share,
        unresolved=tuple(unresolved),
        excluded=tuple(excluded),
        concept=chosen,
        period_start=span[0],
        period_end=span[1],
        total_revenue=total,
        members=tuple(members),
        cik=cik,
        accn=accn,
        form=form,
        filed=filed,
        instance_url=instance_url,
    )
    return _Extraction(GeographicMixResult(mix=result, cik=cik), True)


def _recover_partition(
    values: dict[Qn, float], total: float, band: float
) -> tuple[set[Qn], str] | None:
    """Countries only, else areas only, if that subset sums to the total within ``band``."""
    countries = {m for m in values if m[0].startswith(_COUNTRY_NS)}
    areas = set(values) - countries
    for kept, dropped in ((countries, "area"), (areas, "country")):
        if kept and kept != set(values) and abs(sum(values[m] for m in kept) - total) <= band:
            return kept, dropped
    return None


def mix_from_instance(
    data: bytes,
    *,
    report_date: str,
    instance_url: str,
    cik: int,
    accn: str,
    form: str,
    filed: str,
) -> GeographicMixResult:
    """The geographic mix of one XBRL instance (the unit-testable core of the module)."""
    try:
        inst = parse_instance(data)
    except InstanceParseError as exc:
        return _fail(str(exc), cik=cik)
    return _extract(
        inst,
        report_date=report_date,
        cik=cik,
        accn=accn,
        form=form,
        filed=filed,
        instance_url=instance_url,
    ).result


# --------------------------------------------------------------------------- filing selection
def pick_instance_name(index: Any) -> tuple[str | None, str | None]:
    """The instance file named in a filing's ``index.json``: ``(name, None)`` or ``(None, reason)``."""
    try:
        items = index["directory"]["item"]
        names = [str(i["name"]) for i in items]
    except (KeyError, TypeError):
        return None, "filing index has no file list"
    xml = [
        n
        for n in names
        if n.lower().endswith(".xml")
        and n.lower() != "filingsummary.xml"
        and not n.lower().endswith(_LINKBASE_SUFFIXES)
    ]
    inline = [n for n in xml if n.lower().endswith("_htm.xml")]
    if len(inline) == 1:
        return inline[0], None
    if len(inline) > 1:
        return None, f"several inline-XBRL instance files: {', '.join(inline)}"
    if len(xml) == 1:
        return xml[0], None
    if not xml:
        return None, "filing has no XBRL instance file"
    return None, f"several candidate instance files: {', '.join(xml)}"


def _rows(columns: Any, cik: int, as_of: date) -> list[FilingRef]:
    out: list[FilingRef] = []
    forms = columns.get("form") or []
    for i, form in enumerate(forms):
        if form not in TENK_FORMS:
            continue
        try:
            filed = date.fromisoformat(columns["filingDate"][i])
            accn = columns["accessionNumber"][i]
        except (KeyError, IndexError, ValueError):
            continue
        if filed > as_of:
            continue
        report = (columns.get("reportDate") or [""] * len(forms))[i] or ""
        doc = (columns.get("primaryDocument") or [""] * len(forms))[i] or ""
        out.append(FilingRef(cik, accn, form, filed, report, doc))
    return out


def candidate_filings(submissions: Any, as_of: date, client: EdgarClient) -> list[FilingRef]:
    """10-K and 10-K/A filings with ``filed <= as_of``, newest first.

    Starts from ``filings.recent`` and follows ``filings.files`` pages (newest first, skipping
    pages that begin after ``as_of``) until a plain 10-K is found, because a 10-K/A cannot stand
    alone.
    """
    cik = int(submissions.get("cik", 0)) if str(submissions.get("cik", "")).isdigit() else 0
    filings = submissions.get("filings", {})
    found = _rows(filings.get("recent", {}), cik, as_of)
    pages = sorted(filings.get("files", []), key=lambda p: str(p.get("filingTo", "")), reverse=True)
    for page in pages:
        if any(f.form == "10-K" for f in found):
            break
        start = page.get("filingFrom")
        if start and date.fromisoformat(start) > as_of:
            continue
        found.extend(_rows(client.submissions_page(page["name"]), cik, as_of))
    return sorted(found, key=lambda f: (f.filed, f.accn), reverse=True)


# --------------------------------------------------------------------------- entry point
def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _mix_for_filing(client: EdgarClient, filing: FilingRef) -> _Extraction:
    def fail(reason: str) -> _Extraction:
        return _Extraction(_fail(reason, cik=filing.cik), False)

    index = client.archive_index(filing.cik, filing.accn)
    name, why = pick_instance_name(index)
    if name is None:
        return fail(f"{filing.form} {filing.accn}: {why}")
    url = archive_file_url(filing.cik, filing.accn, name)
    data = client.archive_file(filing.cik, filing.accn, name)
    try:
        inst = parse_instance(data)
    except InstanceParseError as exc:
        return fail(f"{filing.form} {filing.accn}: {exc}")
    return _extract(
        inst,
        report_date=filing.report_date,
        cik=filing.cik,
        accn=filing.accn,
        form=filing.form,
        filed=filing.filed.isoformat(),
        instance_url=url,
    )


def geographic_mix_as_of(
    ticker_or_cik: str | int,
    as_of: date | str,
    client: EdgarClient | None = None,
) -> GeographicMixResult:
    """The geographic revenue mix the latest 10-K filed on or before ``as_of`` reports.

    ``ticker_or_cik`` is a ticker (resolved with the date-aware CIK table) or a CIK number.
    Never raises for a missing or unreadable filing: the reason is in the result.
    """
    when = _as_date(as_of)
    edgar = client or EdgarClient()
    cik: int | None = None
    try:
        if isinstance(ticker_or_cik, int) or str(ticker_or_cik).isdigit():
            cik = int(ticker_or_cik)
        else:
            cik = resolve_cik(str(ticker_or_cik), when, client=edgar).cik
        subs = edgar.submissions(cik)
        if "cik" not in subs:
            subs = {**subs, "cik": cik}
        candidates = candidate_filings(subs, when, edgar)
        if not candidates:
            return _fail(
                f"no 10-K filed on or before {when.isoformat()} for CIK {cik}", cik=cik, as_of=when
            )
        base = next((f for f in candidates if f.form == "10-K"), None)
        for filing in candidates:
            if filing.form == "10-K/A":
                if base is not None and filing.report_date and base.report_date:
                    if filing.report_date < base.report_date:
                        continue  # amends an older fiscal year than the latest 10-K
                try:
                    out = _mix_for_filing(edgar, filing)
                except EdgarError:
                    continue  # an amendment with no readable archive cannot supersede
                if not out.has_total:
                    continue  # a Part III or exhibit-only amendment: no full XBRL instance
            else:
                out = _mix_for_filing(edgar, filing)
            return GeographicMixResult(out.result.mix, out.result.reason, cik, when)
        return _fail(
            f"no 10-K with a full XBRL instance filed on or before {when.isoformat()} for CIK {cik}",
            cik=cik,
            as_of=when,
        )
    except UnresolvedTickerError as exc:
        return _fail(f"cannot resolve CIK: {exc}", as_of=when)
    except EdgarError as exc:
        return _fail(str(exc), cik=cik, as_of=when)
    except (ValueError, json.JSONDecodeError) as exc:
        return _fail(f"unreadable EDGAR response: {exc}", cik=cik, as_of=when)
