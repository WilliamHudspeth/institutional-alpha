"""Country risk premium (CRP) and revenue-weighted blended ERP.

Implements the owner's methodology (NYU Stern paper "On BLK"): the equity risk
premium of a company is Damodaran's country/regional ERP (mature-market ERP +
country risk premium) weighted by WHERE THE COMPANY EARNS ITS REVENUE
(``Security.revenue_mix``). With no revenue mix, the company's domicile country
is used (the United States by default).

Per-country ERP: the dataset gives a rating-based ERP and, where Damodaran has a
sovereign CDS, a CDS-based ERP. The country ERP is their average ("averaged at the
country level and then weighted by revenue distribution"); the rating-based ERP
alone where there is no CDS. Older datasets (January 2026) carry only the
rating-based ERP per country, which is then used as is.

Regions and named aggregates (``eurozone``, ``mea``, ``latam``, ``asia``) are the
GDP-weighted average of their member countries' per-country ERPs. Members
without a GDP figure are skipped and the skip is reported.

Data: the newest ``iam/data/reference/country_erp_YYYY-MM.json`` (Damodaran
ctryprem.xlsx) by default, loaded by :func:`load_country_erp`; the env var
``IAM_COUNTRY_ERP_FILE`` overrides. Revenue-mix keys that resolve to nothing, and
malformed dataset rows, are EXCLUDED and reported (never given an invented rating).

The legacy rating-table helper :func:`country_risk` (sovereign rating ->
default spread -> CRP = spread x relative volatility) is kept for what-if
analysis with an injected rating/CDS; it raises on unknown countries.

Pure stdlib; fully offline-testable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from iam.data.damodaran import COUNTRY_ERP_ENV as _COUNTRY_ERP_ENV
from iam.data.damodaran import read_country_erp as _read_country_erp

# --------------------------------------------------------------------------- #
# Static rating table for the legacy `country_risk()` helper. Decimals.
# Moody's-style sovereign-rating -> default spread, early-2024 levels; use the
# shipped dataset (load_country_erp) for current numbers.
# --------------------------------------------------------------------------- #
DEFAULT_RATING_SPREADS: dict[str, float] = {
    "Aaa": 0.0000,
    "Aa1": 0.0036,
    "Aa2": 0.0048,
    "Aa3": 0.0060,
    "A1": 0.0072,
    "A2": 0.0084,
    "A3": 0.0107,
    "Baa1": 0.0131,
    "Baa2": 0.0155,
    "Baa3": 0.0191,
    "Ba1": 0.0239,
    "Ba2": 0.0287,
    "Ba3": 0.0358,
    "B1": 0.0454,
    "B2": 0.0537,
    "B3": 0.0717,
    "Caa1": 0.0860,
    "Caa2": 0.1075,
    "Caa3": 0.1344,
}

# ISO (lower) -> sovereign rating. A small starter set for `country_risk()`.
DEFAULT_SOVEREIGN_RATING: dict[str, str] = {
    "us": "Aaa",
    "de": "Aaa",
    "ca": "Aaa",
    "au": "Aaa",
    "ch": "Aaa",
    "nl": "Aaa",
    "sg": "Aaa",
    "tw": "Aa3",
    "hk": "Aa3",
    "ie": "Aa3",
    "es": "A3",
    "it": "Baa3",
    "gb": "Aa3",
    "fr": "Aa2",
    "jp": "A1",
    "cn": "A1",
    "kr": "Aa2",
    "in": "Baa3",
    "br": "Ba2",
    "mx": "Baa2",
    "id": "Baa2",
    "za": "Ba2",
    "tr": "B1",
    "ar": "Caa3",
    "ru": "Caa3",
}

# Fallback sigma_equity/sigma_bond for `country_risk()` when no dataset value is
# passed; the datasets publish their own value (load_country_erp()).
DEFAULT_REL_VOL = 1.50

# --------------------------------------------------------------------------- #
# Shipped Damodaran datasets (ctryprem.xlsx), extracted to dated JSON files.
# --------------------------------------------------------------------------- #
# The loader lives in iam.data.damodaran (a leaf module) because DamodaranProvider
# needs the same file at class-definition time and iam.valuation imports iam.data.
COUNTRY_ERP_ENV = _COUNTRY_ERP_ENV


def dataset_label(table: dict[str, Any]) -> str:
    """Short provenance label of a dataset, e.g. ``Damodaran Apr 2026`` (from its ``as_of``)."""
    as_of = str(table.get("as_of", "unknown"))
    try:
        stamp = datetime.strptime(as_of[:10], "%Y-%m-%d")
    except ValueError:
        return f"Damodaran {as_of}"
    return f"Damodaran {stamp:%b %Y}"


def load_country_erp(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load the Damodaran country/regional ERP dataset (cached per file).

    Resolution order: explicit ``path``, env ``IAM_COUNTRY_ERP_FILE``, then the
    file shipped inside the package (resolved from the package, never the CWD).
    """
    return _read_country_erp(path)


# Damodaran's MATURE-market ERP (Aaa, no country risk). Differs from the US ERP,
# which carries a default spread now that the US is Aa1. Read from the dataset.
DEFAULT_MATURE_ERP: float = float(load_country_erp()["mature_market_erp"])

# --------------------------------------------------------------------------- #
# Key resolution for revenue_mix keys. Keys are normalised by lower-casing and
# dropping every non-alphanumeric character ("Asia_Pacific" == "asia pacific").
# Targets MUST be names present in the dataset (enforced by a test).
# --------------------------------------------------------------------------- #
COUNTRY_ALIASES: dict[str, str] = {
    "us": "United States",
    "usa": "United States",
    "unitedstatesofamerica": "United States",
    "uk": "United Kingdom",
    "gb": "United Kingdom",
    "gbr": "United Kingdom",
    "greatbritain": "United Kingdom",
    "de": "Germany",
    "cn": "China",
    "jp": "Japan",
    "in": "India",
    "fr": "France",
    "it": "Italy",
    "es": "Spain",
    "ca": "Canada",
    "br": "Brazil",
    "mx": "Mexico",
    "kr": "Korea",
    "southkorea": "Korea",
    "au": "Australia",
    "ch": "Switzerland",
    "nl": "Netherlands",
    "se": "Sweden",
    "tw": "Taiwan",
    "hk": "Hong Kong",
    "sg": "Singapore",
    "ie": "Ireland",
    "be": "Belgium",
    "at": "Austria",
    "no": "Norway",
    "dk": "Denmark",
    "fi": "Finland",
    "pl": "Poland",
    "tr": "Turkey",
    "id": "Indonesia",
    "th": "Thailand",
    "my": "Malaysia",
    "ph": "Philippines",
    "vn": "Vietnam",
    "sa": "Saudi Arabia",
    "ae": "United Arab Emirates",
    "il": "Israel",
    "za": "South Africa",
    "ar": "Argentina",
    "cl": "Chile",
    "co": "Colombia",
    "pe": "Peru",
    "nz": "New Zealand",
}
# Region aliases -> Damodaran region names.
REGION_ALIASES: dict[str, str] = {
    "northamerica": "North America",
    "na": "North America",
    "americas": "North America",
    "westerneurope": "Western Europe",
    "europe": "Western Europe",
    "eu": "Western Europe",
    "emea": "Western Europe",
    "asia": "Asia",
    "apac": "Asia",
    "asiapacific": "Asia",
    "latam": "Central and South America",
    "southamerica": "Central and South America",
    "centralandsouthamerica": "Central and South America",
    "easterneurope": "Eastern Europe",
    "middleeast": "Middle East",
    "africa": "Africa",
    "anz": "Australia & New Zealand",
    "oceania": "Australia & New Zealand",
    "australianewzealand": "Australia & New Zealand",
    "caribbean": "Caribbean",
}
# Coarse region aliases; the approximation is stated in the provenance string.
_APPROXIMATION_NOTES: dict[str, str] = {
    "americas": "americas treated as North America",
    "emea": "emea treated as Western Europe",
    "apac": "apac treated as Asia",
}


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


# Named aggregates from the owner's April 2026 BLK report ("On BLK"). Each resolves
# to the GDP-weighted average of its member countries' per-country ERPs. They take
# precedence over the coarse region aliases above.
NAMED_AGGREGATES: dict[str, dict[str, tuple[str, ...]]] = {
    # The owner's GDP-weighted Eurozone set.
    "eurozone": {"countries": ("Germany", "France", "Italy", "Ireland", "Luxembourg")},
    # "MEA": every country whose region is Middle East or Africa.
    "mea": {"regions": ("Middle East", "Africa")},
    # "LATAM": Damodaran's Central and South America.
    "latam": {"regions": ("Central and South America",)},
    # "Asia": Damodaran's Asia.
    "asia": {"regions": ("Asia",)},
}

BASES = ("average", "rating", "cds")  # how a country's ERP is formed from rating and CDS ERPs


def _country_value(row: Any, basis: str = "average") -> tuple[float, bool] | None:
    """A country row's ERP as ``(erp, uses_cds)``; ``None`` if the row is unusable.

    ``average``: mean of the rating and CDS ERPs, the rating ERP alone when there is
    no CDS. ``rating``: rating ERP. ``cds``: CDS ERP, the rating ERP where CDS is
    missing. January-schema rows (``erp`` only) are rating-based. Malformed rows
    (non-text region, missing ERP) are unusable.
    """
    if not isinstance(row, dict) or not isinstance(row.get("region"), str):
        return None
    rating = row.get("erp_rating", row.get("erp"))
    if isinstance(rating, bool) or not isinstance(rating, int | float):
        return None
    cds = row.get("erp_cds")
    if basis == "rating" or isinstance(cds, bool) or not isinstance(cds, int | float):
        return float(rating), False
    if basis == "cds":
        return float(cds), True
    return (float(rating) + float(cds)) / 2.0, True


def _find_country(name: str, table: dict[str, Any]) -> str | None:
    """Dataset country name matching ``name`` (exact, case/punctuation-insensitive)."""
    n = _norm(name)
    for cname in table.get("countries", {}):
        if _norm(cname) == n:
            return str(cname)
    return None


def country_erp(name: str, *, basis: str = "average", table: dict[str, Any] | None = None) -> float:
    """Per-country ERP from the dataset (see :func:`_country_value` for ``basis``).

    Raises:
        KeyError: the country is not in the dataset or its row is malformed.
    """
    tbl = table if table is not None else load_country_erp()
    cname = _find_country(name, tbl)
    value = _country_value(tbl["countries"][cname], basis) if cname else None
    if value is None:
        raise KeyError(f"no usable country ERP row for {name!r}")
    return value[0]


@dataclass(frozen=True)
class _Resolved:
    name: str
    erp: float
    note: str | None = None
    skipped: tuple[str, ...] = ()
    uses_cds: bool = False


def _aggregate(
    names: list[str], table: dict[str, Any], basis: str
) -> tuple[float | None, list[str], bool]:
    """GDP-weighted average of per-country ERPs. Returns (erp|None, skipped members, uses_cds).

    A member is skipped when it is not a usable dataset row or has no positive GDP.
    """
    countries = table.get("countries", {})
    num = den = 0.0
    skipped: list[str] = []
    uses_cds = False
    for name in names:
        row = countries.get(name)
        value = _country_value(row, basis)
        gdp = row.get("gdp_musd_2024") if isinstance(row, dict) else None
        if value is None or isinstance(gdp, bool) or not isinstance(gdp, int | float) or gdp <= 0:
            skipped.append(name)
            continue
        num += gdp * value[0]
        den += gdp
        uses_cds = uses_cds or value[1]
    return (num / den if den > 0 else None), skipped, uses_cds


def _region_members(region: str, table: dict[str, Any]) -> list[str]:
    """Countries of a Damodaran region (country labels may extend the region name,
    e.g. region "Eastern Europe" vs country label "Eastern Europe & Russia")."""
    want = _norm(region)
    return [
        cname
        for cname, row in table.get("countries", {}).items()
        if _country_value(row) is not None and _norm(row["region"]).startswith(want)
    ]


def _skip_note(label: str, skipped: list[str]) -> str:
    return f"{label}: members skipped (no GDP): " + ", ".join(skipped)


def _resolve_region(
    region: str, table: dict[str, Any], basis: str, approx: str | None, label: str | None = None
) -> _Resolved | None:
    name = label or region
    members = _region_members(region, table)
    erp, skipped, uses_cds = _aggregate(members, table, basis)
    notes = [approx] if approx else []
    if erp is not None:
        if skipped:
            notes.append(_skip_note(name, skipped))
        return _Resolved(name, erp, "; ".join(notes) or None, tuple(skipped), uses_cds)
    rrow = table.get("regions", {}).get(region)
    published = None
    if isinstance(rrow, dict):
        published = rrow.get("erp_rating_gdp_weighted", rrow.get("erp"))
    if isinstance(published, int | float) and not isinstance(published, bool):
        notes.append(
            f"{name}: no member GDP in the dataset, used the published GDP-weighted "
            "rating-based regional figure"
        )
        return _Resolved(name, float(published), "; ".join(notes))
    return None


def _resolve_key(key: str, table: dict[str, Any], basis: str = "average") -> _Resolved | None:
    """Resolve a revenue_mix key to a country, named aggregate or region ERP; None if unknown."""
    n = _norm(key)
    countries: dict[str, Any] = table.get("countries", {})
    regions: dict[str, Any] = table.get("regions", {})
    cname = _find_country(key, table)  # (1) exact country name
    if cname is None:
        target = COUNTRY_ALIASES.get(n)  # (2) country alias
        cname = target if target in countries else None
    if cname is not None:
        value = _country_value(countries[cname], basis)
        return None if value is None else _Resolved(cname, value[0], None, (), value[1])
    agg = NAMED_AGGREGATES.get(n)  # (3) named aggregate (owner's report)
    if agg is not None:
        members = list(agg.get("countries", ()))
        for region in agg.get("regions", ()):
            members.extend(_region_members(region, table))
        erp, skipped, uses_cds = _aggregate(members, table, basis)
        if erp is None:
            only = agg.get("regions", ())
            if len(only) == 1 and not agg.get("countries"):
                return _resolve_region(only[0], table, basis, None, label=n)
            return None
        agg_note = _skip_note(n, skipped) if skipped else None
        return _Resolved(n, erp, agg_note, tuple(skipped), uses_cds)
    alias_region = REGION_ALIASES.get(n)  # (4) region alias
    if alias_region and alias_region in regions:
        return _resolve_region(alias_region, table, basis, _APPROXIMATION_NOTES.get(n))
    for rname in regions:  # (5) exact region name
        if _norm(rname) == n:
            return _resolve_region(rname, table, basis, None)
    return None


def resolve_revenue_key(key: str, table: dict[str, Any] | None = None) -> tuple[str, float] | None:
    """Resolve one revenue_mix key to ``(dataset name, ERP)``; ``None`` if it resolves to nothing."""
    hit = _resolve_key(key, table if table is not None else load_country_erp())
    return None if hit is None else (hit.name, hit.erp)


@dataclass(frozen=True)
class CountryRisk:
    iso: str
    rating: str
    default_spread: float
    crp: float  # default_spread * rel_vol
    erp: float  # mature_erp + crp


@dataclass
class BlendedERP:
    erp: float
    mature_erp: float
    rel_vol: float
    components: list[tuple[str, float, float]] = field(
        default_factory=list
    )  # (dataset name, weight, erp)
    notes: list[str] = field(default_factory=list)
    coverage: float = 1.0  # share (0-1) of revenue weight that resolved to a dataset ERP
    unresolved: list[str] = field(default_factory=list)  # revenue_mix keys left out
    skipped: list[str] = field(default_factory=list)  # aggregate members skipped (no GDP)
    basis: str = "average"
    source: str = ""

    def explain(self) -> str:
        lines = [
            f"Blended ERP = {self.erp:.4f}  (mature {self.mature_erp:.4f}, "
            f"coverage {self.coverage:.0%})"
        ]
        for name, w, e in self.components:
            lines.append(f"  {name:>26}  w={w:5.1%}  ERP={e:.4f}")
        if self.unresolved:
            lines.append("  unresolved: " + ", ".join(self.unresolved))
        return "\n".join(lines)


def country_risk(
    iso: str,
    *,
    mature_erp: float = DEFAULT_MATURE_ERP,
    rel_vol: float = DEFAULT_REL_VOL,
    rating_spreads: dict[str, float] | None = None,
    sovereign_rating: dict[str, str] | None = None,
    default_spread_override: float | None = None,
) -> CountryRisk:
    """Compute one country's CRP and total ERP from the static rating table.

    Raises:
        ValueError: ``iso`` has no sovereign rating in the table. An unknown
            country never receives an invented rating.
    """
    spreads = rating_spreads or DEFAULT_RATING_SPREADS
    ratings = sovereign_rating or DEFAULT_SOVEREIGN_RATING
    code = iso.strip().lower()
    if code not in ratings:
        raise ValueError(f"No sovereign rating for {iso!r}; refusing to invent one")
    rating = ratings[code]
    if default_spread_override is not None:
        spread = float(default_spread_override)
    else:
        spread = spreads[rating]

    crp = spread * rel_vol
    return CountryRisk(
        iso=code,
        rating=rating,
        default_spread=spread,
        crp=crp,
        erp=mature_erp + crp,
    )


def blended_erp(
    revenue_mix: dict[str, float],
    *,
    table: dict[str, Any] | None = None,
    lambdas: dict[str, float] | None = None,
    basis: str = "average",
) -> BlendedERP:
    """Revenue-weighted ERP from Damodaran country/regional ERPs.

    Args:
        revenue_mix: {country_or_region: weight}. Need not be normalised. Keys
            that resolve to nothing are excluded and reported in ``unresolved``;
            weights are renormalised over the resolved part and ``coverage``
            reports the resolved share.
        table: dataset in the load_country_erp() shape (default: newest shipped file).
        lambdas: optional exposure overrides (Damodaran lambda), keyed like
            revenue_mix. When given they replace revenue share as blend weights.
        basis: per-country ERP: ``average`` (default; rating and CDS averaged, rating
            alone where there is no CDS), ``rating`` or ``cds`` (rating where no CDS).
    """
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, got {basis!r}")
    tbl = table if table is not None else load_country_erp()
    mature = float(tbl["mature_market_erp"])
    rel_vol = float(tbl.get("relative_equity_volatility", DEFAULT_REL_VOL))
    label = f"{tbl.get('source', 'Damodaran country ERP')} as_of {tbl.get('as_of', 'unknown')}"
    notes: list[str] = []

    positive = {k: float(v) for k, v in (revenue_mix or {}).items() if v is not None and v > 0}
    if not positive:
        notes.append("Empty revenue_mix; no geographic blend, mature-market ERP shown.")
        return BlendedERP(
            erp=mature,
            mature_erp=mature,
            rel_vol=rel_vol,
            notes=notes,
            coverage=0.0,
            basis=basis,
            source=f"no revenue mix ({label})",
        )

    # Shares of revenue: percentages (sum > 1.5, as in Security.normalized_mix) become decimals.
    total_raw = sum(positive.values())
    scale = 100.0 if total_raw > 1.5 else 1.0
    positive = {k: v / scale for k, v in positive.items()}
    total_raw = sum(positive.values())
    agg: dict[str, float] = {}
    erps: dict[str, float] = {}
    unresolved: list[str] = []
    skipped: list[str] = []
    any_cds = False
    for k, w in positive.items():
        hit = _resolve_key(k, tbl, basis)
        if hit is None:
            unresolved.append(k)
            continue
        agg[hit.name] = agg.get(hit.name, 0.0) + w
        erps[hit.name] = hit.erp
        any_cds = any_cds or hit.uses_cds
        if hit.note and hit.note not in notes:
            notes.append(hit.note)
        skipped.extend(s for s in hit.skipped if s not in skipped)
    coverage = sum(agg.values()) / total_raw
    if unresolved:
        malformed = [
            k
            for k in unresolved
            if (c := _find_country(k, tbl)) is not None
            and _country_value(tbl["countries"][c]) is None
        ]
        for k in malformed:
            notes.append(f"{k}: dataset row malformed (unrated), excluded")
        notes.append("unresolved keys excluded: " + ", ".join(unresolved))

    weights = agg
    if lambdas:
        lam: dict[str, float] = {}
        for k, v in lambdas.items():
            hit = _resolve_key(k, tbl, basis)
            if hit is not None and v and v > 0:
                lam[hit.name] = lam.get(hit.name, 0.0) + float(v)
        weights = {n: lam.get(n, 0.0) for n in agg}
        notes.append("Using explicit lambda exposures as blend weights, not raw revenue share.")
    total_w = sum(weights.values())
    if total_w <= 0:
        notes.append("No resolvable revenue weight; no geographic blend.")
        return BlendedERP(
            erp=mature,
            mature_erp=mature,
            rel_vol=rel_vol,
            notes=notes,
            coverage=0.0,
            unresolved=unresolved,
            skipped=skipped,
            basis=basis,
            source=f"no resolvable revenue mix ({label})",
        )

    components = sorted(
        ((n, w / total_w, erps[n]) for n, w in weights.items() if w > 0),
        key=lambda c: c[1],
        reverse=True,
    )
    erp = sum(w * e for _, w, e in components)
    if basis == "average":
        basis_text = (
            "rating/CDS averaged" if any_cds else "rating-based only (no CDS in the used rows)"
        )
    elif basis == "rating":
        basis_text = "rating-based only"
    else:
        basis_text = "CDS-based (rating where no CDS)"
    source = f"revenue-weighted {label}; {basis_text}; coverage {coverage:.0%}"
    if notes:
        source += "; " + "; ".join(notes)
    return BlendedERP(
        erp=erp,
        mature_erp=mature,
        rel_vol=rel_vol,
        components=components,
        notes=notes,
        coverage=coverage,
        unresolved=unresolved,
        skipped=skipped,
        basis=basis,
        source=source,
    )


def _us_erp(tbl: dict[str, Any]) -> tuple[float, str]:
    """The US per-country ERP (rating/CDS averaged) and its basis text."""
    cname = _find_country("United States", tbl)
    value = _country_value(tbl["countries"][cname]) if cname else None
    if value is None:
        return float(tbl["us_erp"]), "rating-based only"
    return value[0], "rating/CDS averaged" if value[1] else "rating-based only"


def company_erp(security: Any) -> tuple[float, str]:
    """Single entry point: a company's ERP and its provenance string.

    Uses the revenue-weighted blend (per-country rating/CDS average, GDP-weighted
    aggregates) when ``security.revenue_mix`` is non-empty and at least part of it
    resolves. With no usable mix it falls back to the country of domicile
    (``security.country_iso``, default US) when the dataset knows it, else to the
    United States' per-country ERP.
    """
    tbl = load_country_erp()
    label = dataset_label(tbl)
    as_of = tbl.get("as_of", "unknown")
    mix = getattr(security, "revenue_mix", None)
    if mix:
        out = blended_erp(dict(mix), table=tbl)
        if out.coverage > 0:
            return out.erp, out.source
        bad = ", ".join(out.unresolved) if out.unresolved else "none"
        reason = f"revenue mix unresolved, keys: {bad}"
    else:
        reason = "no revenue mix"
        iso = str(getattr(security, "country_iso", "") or "")
        home = _resolve_key(iso, tbl) if iso else None
        if home is not None and _norm(iso) not in ("us", "usa", "unitedstates"):
            basis_text = "rating/CDS averaged" if home.uses_cds else "rating-based only"
            return (
                home.erp,
                f"{home.name} ERP {home.erp:.2%} ({label}, as_of {as_of}; {basis_text}; "
                f"{reason}, country_iso {iso})",
            )
    us, basis_text = _us_erp(tbl)
    return us, f"US ERP {us:.2%} ({label}, as_of {as_of}; {basis_text}; {reason})"


def revenue_erp_breakdown(security: Any) -> dict[str, dict[str, Any]]:
    """Per-revenue-key ERP rows behind :func:`company_erp`, keyed by the mix key.

    Each row has ``weight`` (renormalised over the keys that resolved), ``erp``
    and ``contrib``. Without a resolvable mix a single ``fallback`` row holds the
    ERP :func:`company_erp` returned.
    """
    tbl = load_country_erp()
    mix = security.normalized_mix() if getattr(security, "revenue_mix", None) else {}
    resolved = {}
    for token, weight in mix.items():
        hit = resolve_revenue_key(token, tbl)
        if hit is not None and weight > 0:
            resolved[token] = (weight, hit[1])
    total = sum(w for w, _ in resolved.values())
    if total <= 0:
        erp, _ = company_erp(security)
        key = str(getattr(security, "country_iso", "") or "US")
        return {key: {"weight": 1.0, "erp": erp, "contrib": erp, "fallback": True}}
    return {
        token: {
            "weight": round(w / total, 4),
            "erp": e,
            "contrib": round(w / total * e, 5),
        }
        for token, (w, e) in resolved.items()
    }


def us_consensus_erp() -> tuple[float, str]:
    """The US-only (rating-based) ERP used for the Stage 1 consensus cost of equity."""
    tbl = load_country_erp()
    us = float(tbl["us_erp"])
    return (
        us,
        f"US ERP {us:.2%} ({dataset_label(tbl)}, as_of {tbl.get('as_of', 'unknown')}, rating-based)",
    )
