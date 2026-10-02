"""Country risk premium (CRP) and revenue-weighted blended ERP.

Implements the owner's methodology (NYU Stern paper "On BLK"): the equity risk
premium of a company is Damodaran's country/regional ERP (mature-market ERP +
country risk premium) weighted by WHERE THE COMPANY EARNS ITS REVENUE
(``Security.revenue_mix``). The US ERP is the fallback when no revenue mix is
known or none of its keys resolve.

Data: ``iam/data/reference/country_erp_2026-01.json`` (Damodaran ctryprem.xlsx,
Jan 2026), loaded by :func:`load_country_erp`. Regional ERPs are Damodaran's
GDP-weighted figures. Revenue-mix keys that resolve to nothing are EXCLUDED and
reported (never given an invented rating).

The legacy rating-table helper :func:`country_risk` (sovereign rating ->
default spread -> CRP = spread x relative volatility) is kept for what-if
analysis with an injected rating/CDS; it raises on unknown countries.

Pure stdlib; fully offline-testable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
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
# passed; the Jan 2026 dataset publishes 1.523378 (load_country_erp()).
DEFAULT_REL_VOL = 1.50

# --------------------------------------------------------------------------- #
# Shipped Damodaran dataset (ctryprem.xlsx, Jan 2026), extracted to JSON.
# --------------------------------------------------------------------------- #
# The loader lives in iam.data.damodaran (a leaf module) because DamodaranProvider
# needs the same file at class-definition time and iam.valuation imports iam.data.
COUNTRY_ERP_ENV = _COUNTRY_ERP_ENV
# Label of the shipped dataset for provenance strings; matches the file name.
DATASET_LABEL = "Damodaran Jan 2026"


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
    "eurozone": "Western Europe",
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
    "eurozone": "eurozone treated as Western Europe",
}


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _resolve_key(key: str, table: dict[str, Any]) -> tuple[str, float, str | None] | None:
    """Resolve a revenue_mix key to (dataset name, erp, approximation note) or None."""
    n = _norm(key)
    countries: dict[str, Any] = table.get("countries", {})
    regions: dict[str, Any] = table.get("regions", {})
    for name, row in countries.items():  # (1) exact country name
        if _norm(name) == n:
            return name, float(row["erp"]), None
    target = COUNTRY_ALIASES.get(n)  # (2) country alias
    if target and target in countries:
        return target, float(countries[target]["erp"]), None
    region = REGION_ALIASES.get(n)  # (3) region alias
    if region and region in regions:
        return region, float(regions[region]["erp"]), _APPROXIMATION_NOTES.get(n)
    for name, rrow in regions.items():  # exact region name
        if _norm(name) == n:
            return name, float(rrow["erp"]), None
    return None


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
) -> BlendedERP:
    """Revenue-weighted ERP from Damodaran country/regional ERPs.

    Args:
        revenue_mix: {country_or_region: weight}. Need not be normalised. Keys
            that resolve to nothing are excluded and reported in ``unresolved``;
            weights are renormalised over the resolved part and ``coverage``
            reports the resolved share.
        table: dataset in the load_country_erp() shape (default: shipped file).
        lambdas: optional exposure overrides (Damodaran lambda), keyed like
            revenue_mix. When given they replace revenue share as blend weights.
    """
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
            source=f"no revenue mix ({label})",
        )

    total_raw = sum(positive.values())
    agg: dict[str, float] = {}
    erps: dict[str, float] = {}
    unresolved: list[str] = []
    for k, w in positive.items():
        hit = _resolve_key(k, tbl)
        if hit is None:
            unresolved.append(k)
            continue
        name, erp_val, note = hit
        agg[name] = agg.get(name, 0.0) + w
        erps[name] = erp_val
        if note and note not in notes:
            notes.append(note)
    coverage = sum(agg.values()) / total_raw
    if unresolved:
        notes.append("unresolved keys excluded: " + ", ".join(unresolved))

    weights = agg
    if lambdas:
        lam: dict[str, float] = {}
        for k, v in lambdas.items():
            hit = _resolve_key(k, tbl)
            if hit is not None and v and v > 0:
                lam[hit[0]] = lam.get(hit[0], 0.0) + float(v)
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
            source=f"no resolvable revenue mix ({label})",
        )

    components = sorted(
        ((n, w / total_w, erps[n]) for n, w in weights.items() if w > 0),
        key=lambda c: c[1],
        reverse=True,
    )
    erp = sum(w * e for _, w, e in components)
    source = f"revenue-weighted {label}; coverage {coverage:.0%}"
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
        source=source,
    )


def resolve_revenue_key(key: str, table: dict[str, Any] | None = None) -> tuple[str, float] | None:
    """Resolve one revenue_mix key to ``(dataset name, ERP)``; ``None`` if it resolves to nothing."""
    hit = _resolve_key(key, table if table is not None else load_country_erp())
    return None if hit is None else (hit[0], hit[1])


def company_erp(security: Any) -> tuple[float, str]:
    """Single entry point: a company's ERP and its provenance string.

    Uses the revenue-weighted blend when ``security.revenue_mix`` is non-empty
    and at least part of it resolves. With no usable mix it falls back to the
    country of domicile (``security.country_iso``) when that is a non-US country
    the dataset knows, else the dataset's US ERP.
    """
    tbl = load_country_erp()
    us = float(tbl["us_erp"])
    mix = getattr(security, "revenue_mix", None)
    if not mix:
        iso = str(getattr(security, "country_iso", "") or "")
        home = _resolve_key(iso, tbl) if iso and _norm(iso) not in ("us", "usa") else None
        if home is not None:
            name, erp_val, _ = home
            return (
                erp_val,
                f"{name} ERP {erp_val:.2%} ({DATASET_LABEL}; no revenue mix, country_iso {iso})",
            )
        return us, f"US ERP {us:.2%} ({DATASET_LABEL}; no revenue mix)"
    out = blended_erp(dict(mix), table=tbl)
    if out.coverage > 0:
        return out.erp, out.source
    bad = ", ".join(out.unresolved) if out.unresolved else "none"
    return us, f"US ERP {us:.2%} ({DATASET_LABEL}; revenue mix unresolved, keys: {bad})"


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
    return us, f"US ERP {us:.2%} ({DATASET_LABEL}, rating-based)"
