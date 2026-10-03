"""Company MARGINAL corporate tax rate from Damodaran's country tax table.

Damodaran's convention (and the owner's BlackRock paper): the MARGINAL (statutory)
rate relevers beta and tax-effects the cost of debt; the EFFECTIVE rate belongs to
operating cash flows and to the effective-tax variable of the multiples regression.

The marginal rate follows the same geographic logic as the owner's ERP
(:func:`iam.valuation.country_risk.company_erp`): country statutory rates weighted by
``Security.revenue_mix`` with the same key resolution and aliases (countries, named
aggregates ``eurozone``/``mea``/``latam``/``asia``, regions), aggregates and regions
GDP-weighted with ``gdp_musd_2024`` from the ERP dataset, unresolved keys excluded
and reported, weights always renormalised. With no revenue mix the company's
``country_iso`` rate is used, otherwise the United States'.

Data: the newest ``iam/data/reference/country_tax_YYYY-MM.json``;
``IAM_COUNTRY_TAX_FILE`` overrides. Pure stdlib; offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iam.data.damodaran import COUNTRY_TAX_ENV as _COUNTRY_TAX_ENV
from iam.data.damodaran import read_country_tax as _read_country_tax
from iam.valuation import country_risk as _cr

COUNTRY_TAX_ENV = _COUNTRY_TAX_ENV
_US = "United States"


def load_country_tax(path: Any = None) -> dict[str, Any]:
    """Load the Damodaran country tax dataset (explicit path, env override, newest file)."""
    return _read_country_tax(path)


def _tax_label(table: dict[str, Any]) -> str:
    return f"{_cr.dataset_label(table)} country tax table"


def _rate(table: dict[str, Any], name: str) -> float | None:
    v = table.get("countries", {}).get(name)
    return None if isinstance(v, bool) or not isinstance(v, int | float) else float(v)


@dataclass(frozen=True)
class _Hit:
    name: str
    rate: float
    note: str | None = None
    skipped: tuple[str, ...] = ()


def _gdp(erp_table: dict[str, Any], name: str) -> float | None:
    row = erp_table.get("countries", {}).get(name)
    gdp = row.get("gdp_musd_2024") if isinstance(row, dict) else None
    return None if isinstance(gdp, bool) or not isinstance(gdp, int | float) or gdp <= 0 else gdp


def _aggregate(
    members: list[str], tax: dict[str, Any], erp_table: dict[str, Any]
) -> tuple[float | None, list[str]]:
    """GDP-weighted mean of member tax rates; members without a rate or GDP are skipped."""
    num = den = 0.0
    skipped: list[str] = []
    for name in members:
        rate, gdp = _rate(tax, name), _gdp(erp_table, name)
        if rate is None or gdp is None:
            skipped.append(name)
            continue
        num += gdp * rate
        den += gdp
    return (num / den if den > 0 else None), skipped


def _region_hit(
    region: str,
    tax: dict[str, Any],
    erp_table: dict[str, Any],
    approx: str | None,
    label: str | None = None,
) -> _Hit | None:
    name = label or region
    rate, skipped = _aggregate(_cr._region_members(region, erp_table), tax, erp_table)
    notes = [approx] if approx else []
    if rate is not None:
        if skipped:
            notes.append(_cr._skip_note(name, skipped))
        return _Hit(name, rate, "; ".join(notes) or None, tuple(skipped))
    rrow = tax.get("regions", {}).get(region)
    published = rrow.get("marginal_tax_gdp_weighted") if isinstance(rrow, dict) else None
    if isinstance(published, int | float) and not isinstance(published, bool):
        notes.append(f"{name}: no member GDP, used the published GDP-weighted regional figure")
        return _Hit(name, float(published), "; ".join(notes))
    return None


def _resolve(key: str, tax: dict[str, Any], erp_table: dict[str, Any]) -> _Hit | None:
    n = _cr._norm(key)
    cname = _cr._find_country(key, tax)  # (1) exact country name
    if cname is None:
        target = _cr.COUNTRY_ALIASES.get(n)  # (2) country alias
        cname = target if target is not None and _rate(tax, target) is not None else None
    if cname is not None:
        rate = _rate(tax, cname)
        return None if rate is None else _Hit(cname, rate)
    agg = _cr.NAMED_AGGREGATES.get(n)  # (3) named aggregate
    if agg is not None:
        members = list(agg.get("countries", ()))
        for region in agg.get("regions", ()):
            members.extend(_cr._region_members(region, erp_table))
        rate, skipped = _aggregate(members, tax, erp_table)
        if rate is None:
            only = agg.get("regions", ())
            if len(only) == 1 and not agg.get("countries"):
                return _region_hit(only[0], tax, erp_table, None, label=n)
            return None
        return _Hit(n, rate, _cr._skip_note(n, skipped) if skipped else None, tuple(skipped))
    regions: dict[str, Any] = erp_table.get("regions", {})
    alias_region = _cr.REGION_ALIASES.get(n)  # (4) region alias
    if alias_region and alias_region in regions:
        return _region_hit(alias_region, tax, erp_table, _cr._APPROXIMATION_NOTES.get(n))
    for rname in regions:  # (5) exact region name
        if _cr._norm(rname) == n:
            return _region_hit(rname, tax, erp_table, None)
    return None


@dataclass
class BlendedTax:
    rate: float
    components: list[tuple[str, float, float]] = field(
        default_factory=list
    )  # (dataset name, renormalised weight, rate)
    notes: list[str] = field(default_factory=list)
    coverage: float = 1.0  # share (0-1) of revenue weight that resolved to a tax rate
    unresolved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    source: str = ""


def blended_marginal_tax(
    revenue_mix: dict[str, float],
    *,
    table: dict[str, Any] | None = None,
    erp_table: dict[str, Any] | None = None,
) -> BlendedTax:
    """Revenue-weighted statutory tax rate.

    Keys that resolve to nothing are excluded and reported in ``unresolved``; weights
    are renormalised over the resolved part and ``coverage`` reports the resolved
    share. ``rate`` is 0.0 with ``coverage`` 0.0 when nothing resolves (check coverage).
    """
    tax = table if table is not None else load_country_tax()
    erp = erp_table if erp_table is not None else _cr.load_country_erp()
    label = f"{_tax_label(tax)} as_of {tax.get('as_of', 'unknown')}"
    positive = {k: float(v) for k, v in (revenue_mix or {}).items() if v is not None and v > 0}
    if not positive:
        return BlendedTax(0.0, coverage=0.0, source=f"no revenue mix ({label})")

    total_raw = sum(positive.values())
    scale = 100.0 if total_raw > 1.5 else 1.0  # percentages become decimals
    positive = {k: v / scale for k, v in positive.items()}
    total_raw = sum(positive.values())
    agg: dict[str, float] = {}
    rates: dict[str, float] = {}
    unresolved: list[str] = []
    skipped: list[str] = []
    notes: list[str] = []
    for k, w in positive.items():
        hit = _resolve(k, tax, erp)
        if hit is None:
            unresolved.append(k)
            continue
        agg[hit.name] = agg.get(hit.name, 0.0) + w
        rates[hit.name] = hit.rate
        if hit.note and hit.note not in notes:
            notes.append(hit.note)
        skipped.extend(s for s in hit.skipped if s not in skipped)
    if unresolved:
        notes.append("unresolved keys excluded: " + ", ".join(unresolved))
    total_w = sum(agg.values())
    if total_w <= 0:
        return BlendedTax(
            0.0,
            notes=notes,
            coverage=0.0,
            unresolved=unresolved,
            skipped=skipped,
            source=f"no resolvable revenue mix ({label})",
        )
    coverage = total_w / total_raw
    components = sorted(
        ((n, w / total_w, rates[n]) for n, w in agg.items()), key=lambda c: c[1], reverse=True
    )
    rate = sum(w * r for _, w, r in components)
    source = f"revenue-weighted {label}; coverage {coverage:.0%}"
    if notes:
        source += "; " + "; ".join(notes)
    return BlendedTax(rate, components, notes, coverage, unresolved, skipped, source)


def company_marginal_tax(security: Any) -> tuple[float, str]:
    """A company's MARGINAL tax rate and its provenance string.

    Revenue-weighted over ``security.revenue_mix`` when at least part of it resolves.
    Otherwise the ``country_iso`` statutory rate if the table has it, else the United
    States' rate (Damodaran combined federal plus state).

    Raises:
        KeyError: the tax dataset has no United States rate (never invented).
    """
    tbl = load_country_tax()
    erp = _cr.load_country_erp()
    label = _tax_label(tbl)
    as_of = tbl.get("as_of", "unknown")
    mix = getattr(security, "revenue_mix", None)
    if mix:
        out = blended_marginal_tax(dict(mix), table=tbl, erp_table=erp)
        if out.coverage > 0:
            return out.rate, out.source
        bad = ", ".join(out.unresolved) if out.unresolved else "none"
        reason = f"revenue mix unresolved, keys: {bad}"
    else:
        reason = "no revenue mix"
        iso = str(getattr(security, "country_iso", "") or "")
        home = _resolve(iso, tbl, erp) if iso else None
        if home is not None and _cr._norm(iso) not in ("us", "usa", "unitedstates"):
            return (
                home.rate,
                f"{home.name} statutory tax {home.rate:.2%} ({label}, as_of {as_of}; "
                f"{reason}, country_iso {iso})",
            )
    us = _rate(tbl, _US)
    if us is None:
        raise KeyError("no United States tax rate in the country tax dataset")
    return us, f"United States statutory tax {us:.2%} ({label}, as_of {as_of}; {reason})"
