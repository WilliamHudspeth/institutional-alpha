"""Country risk premium (CRP) and revenue-weighted blended ERP.

Implements Damodaran's country-risk methodology, which the existing
`build_geographic_erp` only approximates with three fixed regional ERPs:

  1. **Country default spread** from sovereign rating (or an injected market
     CDS). A static rating->spread table ships as a default and is overridable.
  2. **Country risk premium**:  CRP = default_spread x (sigma_equity / sigma_bond).
     The relative-volatility scalar lifts the bond-market default spread to an
     equity-market risk premium (Damodaran's standard ~1.5 default, configurable).
  3. **Country total ERP**:  ERP_country = mature_market_ERP + CRP.
  4. **Company blended ERP** weighted by where revenue is actually earned, using
     the Security's country-level `revenue_mix`. A per-country lambda override is
     supported for the (common) case where revenue exposure != operating risk
     exposure; lambda defaults to the revenue weight.

The output feeds directly into the repo's existing
`iam.valuation.damodaran_defaults.cost_of_equity(rf, beta_l, erp)`.

All tables are explicit, dated, and injectable — no magic constants (design
principle #4). The bundled numbers are reasonable static anchors meant to be
refreshed from Damodaran's January dataset; override via the function args.

Pure stdlib; fully offline-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Static anchors — REFRESH from Damodaran's annual dataset. Decimals.
# Moody's-style sovereign-rating -> default spread. Anchored to early-2024
# levels; treat as defaults, not ground truth, and override per run.
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

# ISO (lower) -> sovereign rating. A small starter set; extend as needed.
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

# Common region aliases -> a representative ISO, so a region-keyed revenue_mix
# still resolves. Coarse by construction; prefer country codes when available.
REGION_TO_ISO: dict[str, str] = {
    "north_america": "us",
    "na": "us",
    "americas": "us",
    "us": "us",
    "europe": "de",
    "emea": "de",
    "eu": "de",
    "apac": "cn",
    "asia": "cn",
    "asia_pacific": "cn",
    "latam": "br",
    "row": "br",
}

# Damodaran's relative equity-market volatility multiplier (sigma_equity/sigma_bond).
DEFAULT_REL_VOL = 1.50
# Mature-market (US) ERP anchor — matches damodaran_defaults.us_erp.
DEFAULT_MATURE_ERP = 0.0503


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
    )  # (iso, weight, erp_country)
    notes: list[str] = field(default_factory=list)

    def explain(self) -> str:
        lines = [
            f"Blended ERP = {self.erp:.4f}  (mature {self.mature_erp:.4f}, rel_vol {self.rel_vol:.2f})"
        ]
        for iso, w, e in self.components:
            lines.append(
                f"  {iso.upper():>4}  w={w:5.1%}  ERP={e:.4f}  (CRP {e - self.mature_erp:+.4f})"
            )
        return "\n".join(lines)


def _resolve_iso(key: str) -> str:
    k = key.strip().lower()
    if k in DEFAULT_SOVEREIGN_RATING:
        return k
    return REGION_TO_ISO.get(k, k)


def country_risk(
    iso: str,
    *,
    mature_erp: float = DEFAULT_MATURE_ERP,
    rel_vol: float = DEFAULT_REL_VOL,
    rating_spreads: dict[str, float] | None = None,
    sovereign_rating: dict[str, str] | None = None,
    default_spread_override: float | None = None,
) -> CountryRisk:
    """Compute a single country's CRP and total ERP.

    Args:
        iso: ISO country code or region alias (case-insensitive).
        default_spread_override: market CDS spread to use instead of the
            rating-derived spread (decimal).
    """
    spreads = rating_spreads or DEFAULT_RATING_SPREADS
    ratings = sovereign_rating or DEFAULT_SOVEREIGN_RATING
    code = _resolve_iso(iso)

    rating = ratings.get(code, "Baa3")  # conservative default for unknowns
    if default_spread_override is not None:
        spread = float(default_spread_override)
    else:
        spread = spreads.get(rating, spreads["Baa3"])

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
    mature_erp: float = DEFAULT_MATURE_ERP,
    rel_vol: float = DEFAULT_REL_VOL,
    lambdas: dict[str, float] | None = None,
    rating_spreads: dict[str, float] | None = None,
    sovereign_rating: dict[str, str] | None = None,
) -> BlendedERP:
    """Revenue-weighted blended ERP across the countries a firm earns in.

    Args:
        revenue_mix: {iso_or_region: weight}. Need not be normalised; weights
            are rescaled to sum to 1. Accepts the output of
            `Security.normalized_revenue_mix()`.
        lambdas: optional per-country exposure overrides (Damodaran lambda). When
            omitted, lambda == the revenue weight. When supplied, lambdas are
            used as the blend weights (and renormalised), letting operating-risk
            exposure differ from raw revenue share.

    Returns a BlendedERP whose `.erp` plugs straight into cost_of_equity().
    """
    notes: list[str] = []
    if not revenue_mix:
        notes.append("Empty revenue_mix; defaulting to 100% mature market.")
        return BlendedERP(
            erp=mature_erp,
            mature_erp=mature_erp,
            rel_vol=rel_vol,
            components=[("us", 1.0, mature_erp)],
            notes=notes,
        )

    # Aggregate by resolved ISO (multiple aliases may map to the same country).
    agg: dict[str, float] = {}
    for k, v in revenue_mix.items():
        if v is None or v <= 0:
            continue
        agg[_resolve_iso(k)] = agg.get(_resolve_iso(k), 0.0) + float(v)

    weight_source = lambdas if lambdas else agg
    if lambdas:
        notes.append("Using explicit lambda exposures as blend weights, not raw revenue share.")
    total_w = sum(weight_source.get(iso, 0.0) for iso in agg) if lambdas else sum(agg.values())
    if total_w <= 0:
        notes.append("All weights zero after resolution; defaulting to mature market.")
        return BlendedERP(
            erp=mature_erp,
            mature_erp=mature_erp,
            rel_vol=rel_vol,
            components=[("us", 1.0, mature_erp)],
            notes=notes,
        )

    erp = 0.0
    components: list[tuple[str, float, float]] = []
    for iso in agg:
        raw_w = lambdas.get(iso, 0.0) if lambdas else agg[iso]
        w = raw_w / total_w
        if w <= 0:
            continue
        cr = country_risk(
            iso,
            mature_erp=mature_erp,
            rel_vol=rel_vol,
            rating_spreads=rating_spreads,
            sovereign_rating=sovereign_rating,
        )
        erp += w * cr.erp
        components.append((iso, w, cr.erp))

    components.sort(key=lambda c: c[1], reverse=True)
    return BlendedERP(
        erp=erp,
        mature_erp=mature_erp,
        rel_vol=rel_vol,
        components=components,
        notes=notes,
    )
