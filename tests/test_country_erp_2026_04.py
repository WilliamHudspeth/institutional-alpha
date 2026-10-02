"""April 2026 Damodaran country ERP data: rating/CDS averaging and GDP-weighted aggregates.

The owner's method (NYU Stern "On BLK"): the country ERP is the average of the
rating-based and the CDS-based ERP, "averaged at the country level and then
weighted by revenue distribution". Regions and named aggregates are the
GDP-weighted average of their member countries' per-country ERPs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from iam.data import damodaran as dm
from iam.data.damodaran import DamodaranProvider
from iam.data.security import Security
from iam.valuation import country_risk as cr
from tests.erp_helpers import gdp_weighted as _gdp_weighted
from tests.erp_helpers import members_in

REFERENCE = Path(dm.__file__).resolve().parent / "reference"
JAN_FILE = REFERENCE / "country_erp_2026-01.json"
APR_FILE = REFERENCE / "country_erp_2026-04.json"

# The owner's BLK revenue mix (April 2026 report).
OWNER_MIX = {
    "us": 0.64,
    "canada": 0.025,
    "latam": 0.015,
    "uk": 0.09,
    "eurozone": 0.13,
    "mea": 0.025,
    "japan": 0.035,
    "australia": 0.015,
    "asia": 0.015,
}
TWO_BP = 2e-4


# ----------------------------------------------------------- the owner's number
def test_owner_number_company_erp_is_5_40_percent_within_2bp():
    erp, src = cr.company_erp(Security(ticker="BLK", revenue_mix=dict(OWNER_MIX)))
    assert erp == pytest.approx(0.0540, abs=TWO_BP)
    assert "rating/CDS averaged" in src
    assert "2026-04-01" in src
    assert "coverage 100%" in src


def test_owner_mix_rating_only_and_cds_only_blends_are_tested_separately():
    rating = cr.blended_erp(OWNER_MIX, basis="rating").erp
    cds = cr.blended_erp(OWNER_MIX, basis="cds").erp
    both = cr.blended_erp(OWNER_MIX, basis="average").erp
    assert rating == pytest.approx(0.05353, abs=TWO_BP)
    assert cds == pytest.approx(0.05444, abs=TWO_BP)
    assert both == pytest.approx(0.05399, abs=TWO_BP)
    assert both == pytest.approx((rating + cds) / 2, abs=1e-9)  # linear: average of the two


# ----------------------------------------------------------- per-country ERP
def test_us_per_country_rating_cds_and_average():
    assert cr.country_erp("United States", basis="rating") == pytest.approx(0.0503)
    assert cr.country_erp("United States", basis="cds") == pytest.approx(0.053838, abs=1e-6)
    assert cr.country_erp("United States") == pytest.approx(0.052069, abs=1e-6)


def test_country_without_cds_uses_rating_alone():
    luxembourg = cr.load_country_erp()["countries"]["Luxembourg"]
    assert luxembourg["erp_cds"] is None
    assert cr.country_erp("Luxembourg") == pytest.approx(luxembourg["erp_rating"])


def test_no_revenue_mix_fallback_is_us_per_country_average():
    erp, src = cr.company_erp(Security(ticker="X"))
    assert erp == pytest.approx(0.052069, abs=1e-6)
    assert "no revenue mix" in src and "rating/CDS averaged" in src
    assert "2026-04-01" in src


def test_consensus_erp_is_the_rating_based_us_erp():
    erp, _src = cr.us_consensus_erp()
    assert erp == pytest.approx(0.0503)


def test_constants_follow_the_april_dataset():
    assert DamodaranProvider.CURRENT_IMPLIED_ERP == pytest.approx(0.0503)
    assert cr.DEFAULT_MATURE_ERP == pytest.approx(0.0477)


# ----------------------------------------------------------- aggregates
def test_eurozone_is_gdp_weighted_over_the_owners_five_countries():
    names = ["Germany", "France", "Italy", "Ireland", "Luxembourg"]
    out = cr.blended_erp({"eurozone": 1.0})
    assert out.erp == pytest.approx(_gdp_weighted(names), abs=1e-9)
    assert out.skipped == []


def test_latam_mea_and_asia_aggregates_are_gdp_weighted_country_averages():
    assert cr.blended_erp({"latam": 1.0}).erp == pytest.approx(
        _gdp_weighted(members_in("Central and South America")), abs=1e-9
    )
    assert cr.blended_erp({"mea": 1.0}).erp == pytest.approx(
        _gdp_weighted(members_in("Middle East", "Africa")), abs=1e-9
    )
    assert cr.blended_erp({"asia": 1.0}).erp == pytest.approx(
        _gdp_weighted(members_in("Asia")), abs=1e-9
    )


def test_existing_region_aliases_are_computed_the_same_gdp_weighted_way():
    out = cr.blended_erp({"westerneurope": 1.0})
    assert out.erp == pytest.approx(_gdp_weighted(members_in("Western Europe")), abs=1e-9)


def test_aggregate_reports_members_skipped_for_missing_gdp():
    # The shipped file carries no GDP for China, India and Japan.
    out = cr.blended_erp({"asia": 1.0})
    assert {"China", "India", "Japan"} <= set(out.skipped)
    assert any("China" in n and "GDP" in n for n in out.notes)
    assert "China" in out.source


def test_aggregate_skip_is_reported_with_a_fixture_table():
    tbl = {
        "source": "fixture",
        "as_of": "fixture-date",
        "mature_market_erp": 0.05,
        "us_erp": 0.05,
        "countries": {
            "Germany": {
                "region": "Western Europe",
                "erp_rating": 0.05,
                "erp_cds": 0.06,
                "gdp_musd_2024": 100.0,
            },
            "France": {
                "region": "Western Europe",
                "erp_rating": 0.09,
                "erp_cds": None,
                "gdp_musd_2024": None,
            },
            "Italy": {
                "region": "Western Europe",
                "erp_rating": 0.07,
                "erp_cds": None,
                "gdp_musd_2024": 100.0,
            },
        },
        "regions": {},
    }
    out = cr.blended_erp({"eurozone": 1.0}, table=tbl)
    assert out.skipped == ["France", "Ireland", "Luxembourg"]  # France: no GDP; others: absent
    # (Germany avg 0.055 + Italy rating-only 0.07) / 2, equal GDP
    assert out.erp == pytest.approx(0.0625)
    assert any("France" in n for n in out.notes)


def test_malformed_dataset_rows_are_excluded_not_rated():
    # The shipped file has unrated rows with shifted columns (region is a number).
    out = cr.blended_erp({"us": 0.5, "russia": 0.5})
    assert out.unresolved == ["russia"]
    assert out.coverage == pytest.approx(0.5)
    assert any("russia" in n.lower() and "malformed" in n for n in out.notes)
    assert out.erp == pytest.approx(cr.country_erp("United States"))


# ----------------------------------------------------------- loader
def test_loader_picks_the_newest_dated_file_by_default(monkeypatch):
    monkeypatch.delenv("IAM_COUNTRY_ERP_FILE", raising=False)
    data = cr.load_country_erp()
    assert data["as_of"].startswith("2026-04-01")
    assert data["mature_market_erp"] == 0.0477


def test_newest_file_selection_ignores_non_dated_names_and_older_months(tmp_path):
    for name in (
        "country_erp_2025-12.json",
        "country_erp_2026-01.json",
        "country_erp_2026-04.json",
        "country_erp_latest.json",
        "country_erp_2026-4.json",
    ):
        (tmp_path / name).write_text("{}")
    assert dm.latest_country_erp_file(tmp_path).name == "country_erp_2026-04.json"


def test_env_override_still_wins(tmp_path, monkeypatch):
    alt = tmp_path / "alt.json"
    alt.write_text('{"mature_market_erp": 0.01, "us_erp": 0.02}')
    monkeypatch.setenv("IAM_COUNTRY_ERP_FILE", str(alt))
    assert cr.load_country_erp()["us_erp"] == 0.02


def test_january_file_still_loads_and_per_country_is_rating_only(monkeypatch):
    monkeypatch.setenv("IAM_COUNTRY_ERP_FILE", str(JAN_FILE))
    data = cr.load_country_erp()
    assert data["as_of"].startswith("2026-01-01")
    assert data["mature_market_erp"] == 0.0423
    jan_us = data["countries"]["United States"]["erp"]
    assert cr.country_erp("United States") == pytest.approx(jan_us)  # no CDS in January
    assert cr.country_erp("United States", basis="cds") == pytest.approx(jan_us)
    out = cr.blended_erp({"us": 0.5, "uk": 0.5})
    assert out.erp == pytest.approx(0.5 * jan_us + 0.5 * data["countries"]["United Kingdom"]["erp"])
    assert "rating-based only" in out.source


def test_january_regions_fall_back_to_published_regional_figure(monkeypatch):
    # January countries carry no GDP, so a region cannot be re-weighted: its own
    # published GDP-weighted rating figure is used, and the source says so.
    monkeypatch.setenv("IAM_COUNTRY_ERP_FILE", str(JAN_FILE))
    data = cr.load_country_erp()
    out = cr.blended_erp({"asia": 1.0})
    assert out.erp == pytest.approx(data["regions"]["Asia"]["erp"])
    assert any("published" in n for n in out.notes)


def test_shipped_april_file_is_unchanged_from_the_provided_extract():
    data = json.loads(APR_FILE.read_text(encoding="utf-8"))
    assert data["us_erp"] == 0.0503 and data["us_erp_cds"] == 0.053838
    assert data["mature_market_erp"] == 0.0477
    assert data["as_of"] == "2026-04-01 (sovereign ratings updated 2026-02-16)"


# ----------------------------------------------------------- revenue-mix weights
def test_owner_mix_sums_to_99_percent_and_the_rounding_residual_is_reported():
    assert sum(OWNER_MIX.values()) == pytest.approx(0.99)
    out = cr.blended_erp(OWNER_MIX)
    assert out.coverage == pytest.approx(1.0)
    assert any("rounding residual 1.0% left unallocated" in n for n in out.notes)
    # Not scaled up: the blend is the plain sum of share x ERP.
    assert out.erp == pytest.approx(sum(w * e for _, w, e in out.components), abs=1e-12)
    assert sum(w for _, w, _ in out.components) == pytest.approx(0.99)


def test_a_large_shortfall_is_renormalised_not_left_unallocated():
    out = cr.blended_erp({"us": 0.5})
    assert out.erp == pytest.approx(cr.country_erp("United States"))
    assert not any("rounding residual" in n for n in out.notes)


def test_percentage_mix_equals_decimal_mix():
    pct = {k: v * 100 for k, v in OWNER_MIX.items()}
    assert cr.blended_erp(pct).erp == pytest.approx(cr.blended_erp(OWNER_MIX).erp, abs=1e-12)
