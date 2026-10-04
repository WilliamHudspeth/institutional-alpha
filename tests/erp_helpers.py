"""Independent expected values for country-ERP tests, read straight from the shipped data.

These helpers re-derive the owner's method from the raw April 2026 JSON (per-country
ERP = mean of the rating and CDS ERPs, the rating ERP alone where CDS is null; a
region is the GDP-weighted mean of its countries, members without GDP skipped) so
that tests do not depend on the production code they check.
"""

from __future__ import annotations

from typing import Any

from iam.data.damodaran import latest_country_erp_file, read_country_erp


def dataset() -> dict[str, Any]:
    return read_country_erp(latest_country_erp_file())


def country_avg(name: str, basis: str = "average") -> float:
    row = dataset()["countries"][name]
    rating, cds = row["erp_rating"], row["erp_cds"]
    if basis == "rating" or cds is None:
        return float(rating)
    if basis == "cds":
        return float(cds)
    return (rating + cds) / 2.0


def members_in(*regions: str) -> list[str]:
    return [n for n, r in dataset()["countries"].items() if r["region"] in regions]


def gdp_weighted(names: list[str], basis: str = "average") -> float:
    countries = dataset()["countries"]
    num = den = 0.0
    for n in names:
        gdp = countries[n]["gdp_musd_2024"]
        if not gdp:
            continue
        num += gdp * country_avg(n, basis)
        den += gdp
    return num / den


def region_erp(region: str) -> float:
    return gdp_weighted(members_in(region))
