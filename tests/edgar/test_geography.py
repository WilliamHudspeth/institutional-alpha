"""Point-in-time geographic revenue mix from the 10-K XBRL instance (Phase B).

Real recorded filings are replayed through an injected transport (no network). Rules the
recordings do not exercise (second dimension, overlap, eliminations, conflicting duplicates,
10-K/A) use the clearly synthetic instance builder in ``geo_helpers``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import iam.data
from iam.data.edgar import client as edgar_client
from iam.data.edgar.client import EdgarClient
from iam.data.edgar.geography import (
    AMBIGUOUS_OVERLAP_REASON,
    candidate_filings,
    geographic_mix_as_of,
    map_member,
    mix_from_instance,
    pick_instance_name,
)
from iam.data.edgar.iso_countries import ISO2_TO_DATASET_NAME
from iam.valuation.country_risk import company_erp, resolve_revenue_key
from iam.valuation.country_tax import company_marginal_tax
from tests.edgar.geo_helpers import (
    GEO_AXIS,
    PRODUCT_AXIS,
    archive_dir,
    fact,
    geo,
    geo_routes,
    instance_url,
    synthetic_instance,
)
from tests.edgar.helpers import FIXTURES, FixtureTransport

AAPL_ACCN = "0000320193-25-000079"
BLK_NEW_2025 = "0001193125-26-071966"
BLK_NEW_2024 = "0000950170-25-026584"
BLK_OLD_2019 = "0001564590-20-007807"
BLK_OLD_2020 = "0001564590-21-008796"
REFERENCE = Path(iam.data.__file__).parent / "reference"


@pytest.fixture()
def transport():
    return FixtureTransport(geo_routes())


@pytest.fixture()
def client(tmp_path, transport):
    return EdgarClient(tmp_path / "cache", transport=transport, sleep=lambda s: None)


def _mix_of(result):
    assert result.reason is None, result.reason
    assert result.mix is not None
    return result.mix


# ---------------------------------------------------------------- recorded filings
def test_aapl_mix_equals_hand_computed_fractions(client):
    # FY2025 (2024-09-29 .. 2025-09-27) net sales, raw values from the 10-K instance:
    us, cn, other = 151_790_000_000, 64_377_000_000, 199_994_000_000
    total = 416_161_000_000
    assert us + cn + other == total
    mix = _mix_of(geographic_mix_as_of("AAPL", date(2026, 6, 30), client=client))
    assert mix.mix == pytest.approx(
        {"United States": us / total, "China": cn / total, "OtherCountries": other / total},
        rel=1e-12,
    )
    assert sum(mix.mix.values()) == pytest.approx(1.0, abs=1e-12)
    assert mix.coverage_of_total_revenue == pytest.approx(1.0, abs=0.01)
    assert mix.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert (mix.period_start, mix.period_end) == ("2024-09-29", "2025-09-27")
    assert mix.total_revenue == total
    assert (mix.cik, mix.accn, mix.form, mix.filed) == (320193, AAPL_ACCN, "10-K", "2025-10-31")
    assert mix.instance_url == instance_url("AAPL_2025")


def test_prior_year_comparative_contexts_in_a_real_filing_are_ignored(client):
    # The same AAPL instance also carries FY2024 (US 142,196M of 391,035M) and FY2023 values.
    mix = _mix_of(geographic_mix_as_of("AAPL", date(2026, 6, 30), client=client))
    assert mix.mix["United States"] == pytest.approx(151_790 / 416_161, rel=1e-12)
    assert mix.mix["United States"] != pytest.approx(142_196 / 391_035, rel=1e-6)


def test_msft_us_and_non_us(client):
    us, non_us, total = 144_546e6, 137_178e6, 281_724e6
    mix = _mix_of(geographic_mix_as_of("MSFT", date(2026, 6, 30), client=client))
    assert mix.mix == pytest.approx({"United States": us / total, "NonUs": non_us / total})
    assert mix.coverage_of_total_revenue == pytest.approx(1.0, abs=0.01)
    assert resolve_revenue_key("NonUs") is None
    assert mix.resolved_share == pytest.approx(us / total)
    assert [u.key for u in mix.unresolved] == ["NonUs"]


def test_blk_2026_uses_new_cik_and_regions(client):
    am, eu, ap, total = 15_956e6, 7_166e6, 1_094e6, 24_216e6
    assert am + eu + ap == total
    mix = _mix_of(geographic_mix_as_of("BLK", date(2026, 6, 30), client=client))
    assert mix.cik == 2012383
    assert mix.accn == BLK_NEW_2025
    assert mix.mix == pytest.approx(
        {"Americas": am / total, "Europe": eu / total, "AsiaPacific": ap / total}
    )
    assert mix.coverage_of_total_revenue == pytest.approx(1.0, abs=0.01)
    assert mix.resolved_share == pytest.approx(1.0)
    assert mix.unresolved == ()


def test_blk_2025_mid_year_uses_the_fy2024_10k_from_an_older_submissions_page(client):
    # The FY2024 10-K (filed 2025-02-25) is not in filings.recent: it is on a filings.files page.
    mix = _mix_of(geographic_mix_as_of("BLK", date(2025, 6, 30), client=client))
    assert mix.accn == BLK_NEW_2024
    # Revenues (12,794M, no geographic facts) comes first in the fallback order; the concept
    # with geographic facts AND a total is the one used.
    assert mix.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert mix.total_revenue == 20_407e6
    assert mix.mix["Americas"] == pytest.approx(13_411 / 20_407)


def test_blk_2020_resolves_old_cik_and_the_fy2019_10k(client):
    am, eu, ap, total = 9_703e6, 4_158e6, 678e6, 14_539e6
    assert am + eu + ap == total
    mix = _mix_of(geographic_mix_as_of("BLK", date(2020, 6, 30), client=client))
    assert mix.cik == 1364742
    assert mix.accn == BLK_OLD_2019
    assert mix.concept == "RevenuesExcludingInterestAndDividends"
    assert mix.mix == pytest.approx(
        {"Americas": am / total, "Europe": eu / total, "AsiaPacific": ap / total}
    )
    assert (mix.period_start, mix.period_end) == ("2019-01-01", "2019-12-31")


def test_before_a_10k_filing_date_the_previous_10k_is_used(client):
    # FY2020 10-K filed 2021-02-25; FY2019 10-K filed 2020-02-28 (old CIK pages 006 / 007).
    day_before = _mix_of(geographic_mix_as_of("BLK", date(2021, 2, 24), client=client))
    on_day = _mix_of(geographic_mix_as_of("BLK", date(2021, 2, 25), client=client))
    assert day_before.accn == BLK_OLD_2019
    assert on_day.accn == BLK_OLD_2020
    assert on_day.mix["Americas"] == pytest.approx(10_593 / 16_205)


def test_candidate_filings_orders_newest_first_and_respects_as_of(client):
    subs = client.submissions(320193)
    before = candidate_filings(subs, date(2025, 10, 30), client)
    assert [f.accn for f in before][:2] == ["0000320193-24-000123", "0000320193-23-000106"]
    on_day = candidate_filings(subs, date(2025, 10, 31), client)
    assert on_day[0].accn == AAPL_ACCN
    assert all(f.filed <= date(2025, 10, 31) for f in on_day)


def test_no_10k_filed_by_as_of_gives_none_with_reason(client):
    # New BLK CIK (valid from 2024-11-06): its first 10-K is filed 2025-02-25.
    res = geographic_mix_as_of("BLK", date(2025, 2, 24), client=client)
    assert res.mix is None
    assert res.reason is not None
    assert "no 10-K filed on or before 2025-02-24" in res.reason
    assert "2012383" in res.reason


def test_unknown_ticker_gives_none_with_reason(client):
    res = geographic_mix_as_of("ZZZZ", date(2026, 6, 30), client=client)
    assert res.mix is None
    assert "ZZZZ" in (res.reason or "")


def test_archive_files_are_cached_and_the_transport_only_sees_recorded_urls(client, transport):
    geographic_mix_as_of("AAPL", date(2026, 6, 30), client=client)
    calls = client.network_calls
    assert calls == len(transport.calls)
    assert all(
        u.startswith(("https://data.sec.gov/", "https://www.sec.gov/")) for u in transport.calls
    )
    geographic_mix_as_of("AAPL", date(2026, 6, 30), client=client)
    assert client.network_calls == calls  # submissions (TTL) and archive files all cached
    # The instance is requested by the name the filing index lists, never guessed.
    assert f"{archive_dir(320193, AAPL_ACCN)}/index.json" in transport.calls
    assert instance_url("AAPL_2025") in transport.calls


# ---------------------------------------------------------------- instance selection rule
def _index(*names: str) -> dict:
    return {"directory": {"item": [{"name": n} for n in names]}}


def test_instance_inline_xbrl_extract_is_preferred():
    name, why = pick_instance_name(
        _index("a-20250101.xsd", "a-20250101_cal.xml", "a-20250101_htm.xml", "FilingSummary.xml")
    )
    assert (name, why) == ("a-20250101_htm.xml", None)


def test_instance_older_plain_xml_is_used_when_there_is_no_htm_extract():
    name, _ = pick_instance_name(
        _index(
            "a.xsd",
            "a-20100101.xml",
            "a-20100101_cal.xml",
            "a-20100101_lab.xml",
            "FilingSummary.xml",
        )
    )
    assert name == "a-20100101.xml"


@pytest.mark.parametrize(
    "names",
    [
        ("a.xsd", "a_cal.xml", "FilingSummary.xml"),  # no instance at all
        ("a-1.xml", "a-2.xml"),  # two candidates, no rule picks one
        ("a_htm.xml", "b_htm.xml"),
    ],
)
def test_instance_ambiguous_or_missing_is_none_with_reason(names):
    name, why = pick_instance_name(_index(*names))
    assert name is None
    assert why


# ---------------------------------------------------------------- member mapping
def test_iso_country_member_maps_to_dataset_name():
    assert map_member("http://xbrl.sec.gov/country/2025", "CN") == ("China", True)


def test_iso_country_not_in_dataset_stays_unresolved_with_its_code():
    assert map_member("http://xbrl.sec.gov/country/2025", "DZ") == ("DZ", False)
    assert resolve_revenue_key("DZ") is None


def test_company_member_key_strips_member_suffix():
    ns = "http://example.test/2025"
    assert map_member(ns, "OtherCountriesMember") == ("OtherCountries", False)
    assert map_member(ns, "GreaterChinaSegmentMember") == ("GreaterChina", False)
    assert resolve_revenue_key("OtherCountries") is None
    assert resolve_revenue_key("GreaterChina") is None


def test_company_member_naming_a_country_resolves_to_the_dataset_name():
    assert map_member("http://example.test/2025", "UnitedKingdomMember") == (
        "United Kingdom",
        True,
    )


@pytest.mark.parametrize(
    ("member", "region"),
    [
        ("AmericasMember", "North America"),
        ("EuropeMember", "Western Europe"),
        ("AsiaPacificMember", "Asia"),
        ("NorthAmericaMember", "North America"),
    ],
)
def test_srt_area_members_resolve_through_country_risk_to_its_region_names(member, region):
    key, resolved = map_member("http://fasb.org/srt/2025", member)
    assert resolved is True
    hit = resolve_revenue_key(key)
    assert hit is not None and hit[0] == region


def test_blk_region_keys_resolve_in_country_risk(client):
    mix = _mix_of(geographic_mix_as_of("BLK", date(2026, 6, 30), client=client))
    names = {}
    for k in mix.mix:
        hit = resolve_revenue_key(k)
        assert hit is not None
        names[k] = hit[0]
    assert names == {"Americas": "North America", "Europe": "Western Europe", "AsiaPacific": "Asia"}


def test_unresolved_member_stays_in_the_mix_and_lowers_coverage(client):
    mix = _mix_of(geographic_mix_as_of("AAPL", date(2026, 6, 30), client=client))
    assert "OtherCountries" in mix.mix
    assert resolve_revenue_key("OtherCountries") is None
    assert [(u.member, u.key) for u in mix.unresolved] == [
        ("aapl:OtherCountriesMember", "OtherCountries")
    ]
    assert mix.unresolved[0].share == pytest.approx(199_994 / 416_161)
    assert mix.resolved_share == pytest.approx((151_790 + 64_377) / 416_161)


# ---------------------------------------------------------------- synthetic rules
FILING_KW = {"cik": 1, "accn": "0000000001-26-000001", "form": "10-K", "filed": "2026-02-01"}


def _mix(facts, **kw):
    xml = synthetic_instance(facts, **kw)
    return mix_from_instance(xml, report_date="2025-12-31", instance_url="u", **FILING_KW)


def test_contexts_with_a_second_dimension_are_ignored():
    res = _mix(
        [
            fact(1000),
            geo("country:US", 700),
            geo("country:DE", 300),
            # same geography, but split by product: must not be read as a geographic member
            fact(9_999, dims=[(GEO_AXIS, "country:US"), (PRODUCT_AXIS, "co:WidgetMember")]),
            fact(8_888, dims=[(PRODUCT_AXIS, "co:WidgetMember")]),
        ]
    )
    mix = _mix_of(res)
    assert mix.mix == pytest.approx({"United States": 0.7, "Germany": 0.3})
    assert mix.coverage_of_total_revenue == pytest.approx(1.0)


def test_prior_year_comparatives_in_the_same_instance_are_ignored():
    prior = ("2024-01-01", "2024-12-31")
    res = _mix(
        [
            fact(1000),
            geo("country:US", 600),
            geo("country:DE", 400),
            fact(500, period=prior),
            geo("country:US", 100, period=prior),
            geo("country:DE", 400, period=prior),
        ]
    )
    mix = _mix_of(res)
    assert mix.mix == pytest.approx({"United States": 0.6, "Germany": 0.4})
    assert mix.period_start == "2025-01-01"


def test_quarterly_contexts_are_not_the_fiscal_year():
    q4 = ("2025-10-01", "2025-12-31")
    res = _mix(
        [
            fact(1000),
            geo("country:US", 1000),
            fact(250, period=q4),
            geo("country:DE", 250, period=q4),
        ]
    )
    assert _mix_of(res).mix == {"United States": 1.0}


def test_geographic_axis_in_us_gaap_namespace_is_accepted():
    res = _mix([fact(1000), fact(1000, dims=[("us-gaap:StatementGeographicalAxis", "country:US")])])
    assert _mix_of(res).mix == {"United States": 1.0}


def test_overlap_without_a_provable_partition_is_none():
    res = _mix(
        [
            fact(1000),
            geo("country:US", 500),
            geo("country:DE", 200),
            geo("srt:EuropeMember", 300),
            geo("srt:AsiaPacificMember", 200),
        ]
    )
    assert res.mix is None
    assert res.reason is not None and AMBIGUOUS_OVERLAP_REASON in res.reason


def test_non_us_line_next_to_countries_is_ambiguous():
    res = _mix(
        [
            fact(1000),
            geo("country:US", 600),
            geo("country:CN", 150),
            geo("us-gaap:NonUsMember", 400),
        ]
    )
    assert res.mix is None
    assert AMBIGUOUS_OVERLAP_REASON in (res.reason or "")


def test_overlap_is_recovered_only_when_dropping_aggregates_proves_a_partition():
    res = _mix(
        [
            fact(1000),
            geo("country:US", 600),
            geo("country:DE", 250),
            geo("country:FR", 150),
            geo("srt:EuropeMember", 400),  # contains DE and FR
        ]
    )
    mix = _mix_of(res)
    assert mix.mix == pytest.approx({"United States": 0.6, "Germany": 0.25, "France": 0.15})
    assert mix.coverage_of_total_revenue == pytest.approx(1.0)
    assert [(e.member, e.value) for e in mix.excluded] == [("srt:EuropeMember", 400.0)]
    assert "overlap" in mix.excluded[0].reason


def test_both_countries_and_regions_partitioning_the_total_prefers_countries():
    res = _mix(
        [
            fact(1000),
            geo("country:US", 600),
            geo("country:DE", 400),
            geo("srt:NorthAmericaMember", 600),
            geo("srt:EuropeMember", 400),
        ]
    )
    mix = _mix_of(res)
    assert set(mix.mix) == {"United States", "Germany"}
    assert {e.member for e in mix.excluded} == {"srt:NorthAmericaMember", "srt:EuropeMember"}


def test_non_positive_members_are_excluded_and_reported():
    res = _mix(
        [
            fact(1000),
            geo("country:US", 700),
            geo("srt:EuropeMember", 400),
            geo("co:EliminationsMember", -100),
            geo("co:NothingMember", 0),
        ]
    )
    mix = _mix_of(res)
    assert mix.mix == pytest.approx({"United States": 700 / 1100, "Europe": 400 / 1100})
    assert {(e.member, e.value) for e in mix.excluded} == {
        ("co:EliminationsMember", -100.0),
        ("co:NothingMember", 0.0),
    }
    assert all("non-positive" in e.reason for e in mix.excluded)
    # coverage counts the eliminations: 700 + 400 - 100 = 1000 of 1000
    assert mix.coverage_of_total_revenue == pytest.approx(1.0)


def test_partial_geography_reports_coverage_below_one():
    mix = _mix_of(_mix([fact(1000), geo("country:US", 500), geo("country:DE", 300)]))
    assert mix.coverage_of_total_revenue == pytest.approx(0.8)
    assert sum(mix.mix.values()) == pytest.approx(1.0)  # fractions of the geographic sum


def test_concept_fallback_skips_a_concept_with_no_geographic_facts():
    rc = "RevenueFromContractWithCustomerExcludingAssessedTax"
    res = _mix(
        [fact(700, concept="Revenues"), fact(1000, concept=rc), geo("country:US", 1000, concept=rc)]
    )
    mix = _mix_of(res)
    assert mix.concept == rc
    assert mix.total_revenue == 1000


def test_concept_with_geographic_facts_but_no_total_is_skipped():
    res = _mix(
        [
            geo("country:US", 5, concept="Revenues"),
            fact(1000, concept="SalesRevenueNet"),
            geo("country:US", 1000, concept="SalesRevenueNet"),
        ]
    )
    assert _mix_of(res).concept == "SalesRevenueNet"


def test_no_geographic_facts_is_none_with_reason():
    res = _mix([fact(1000), fact(1000, dims=[(PRODUCT_AXIS, "co:WidgetMember")])])
    assert res.mix is None
    assert "no geographic revenue facts" in (res.reason or "")


def test_conflicting_duplicate_facts_are_ambiguous():
    res = _mix([fact(1000), geo("country:US", 600), geo("country:US", 650), geo("country:DE", 400)])
    assert res.mix is None
    assert "conflicting" in (res.reason or "")


def test_identical_duplicate_facts_are_collapsed():
    res = _mix(
        [
            fact(1000),
            fact(1000),
            geo("country:US", 600),
            geo("country:US", 600),
            geo("country:DE", 400),
        ]
    )
    assert _mix_of(res).mix == pytest.approx({"United States": 0.6, "Germany": 0.4})


def test_nil_facts_are_ignored():
    res = _mix([fact(1000), geo("country:US", 1000), geo("country:DE", None)])
    assert _mix_of(res).mix == {"United States": 1.0}


def test_total_in_a_different_unit_is_not_used():
    res = _mix([fact(1000, unit="EUR"), geo("country:US", 1000)])
    assert res.mix is None


def test_dei_period_end_must_match_the_report_date():
    xml = synthetic_instance([fact(1000), geo("country:US", 1000)], dei_period_end="2025-09-30")
    res = mix_from_instance(xml, report_date="2025-12-31", instance_url="u", **FILING_KW)
    assert res.mix is None
    assert "period" in (res.reason or "")


def test_instance_with_a_doctype_is_refused_without_parsing():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><xbrl>&a;</xbrl>'
    res = mix_from_instance(evil, report_date="2025-12-31", instance_url="u", **FILING_KW)
    assert res.mix is None
    assert "DOCTYPE" in (res.reason or "")


def test_malformed_xml_is_none_with_reason():
    res = mix_from_instance(
        b"<xbrl><context", report_date="2025-12-31", instance_url="u", **FILING_KW
    )
    assert res.mix is None
    assert "parse" in (res.reason or "")


# ---------------------------------------------------------------- 10-K vs 10-K/A
def _synthetic_world(amend_instance: bytes | None) -> dict[str, bytes]:
    sub = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000000001-26-000002", "0000000001-26-000001"],
                "filingDate": ["2026-03-15", "2026-02-01"],
                "reportDate": ["2025-12-31", "2025-12-31"],
                "form": ["10-K/A", "10-K"],
                "primaryDocument": ["a.htm", "b.htm"],
            },
            "files": [],
        }
    }
    routes: dict[str, bytes] = {edgar_client.submissions_url(1): json.dumps(sub).encode()}
    original = synthetic_instance([fact(1000), geo("country:US", 1000)])
    for accn, name, body in (
        ("0000000001-26-000001", "x_htm.xml", original),
        ("0000000001-26-000002", "y_htm.xml", amend_instance),
    ):
        d = archive_dir(1, accn)
        if body is None:  # a Part III amendment: no XBRL instance in the archive
            routes[f"{d}/index.json"] = json.dumps(_index("y.htm", "y.xsd")).encode()
        else:
            routes[f"{d}/index.json"] = json.dumps(_index(name)).encode()
            routes[f"{d}/{name}"] = body
    return routes


def _client(tmp_path, routes) -> EdgarClient:
    return EdgarClient(tmp_path, transport=FixtureTransport(routes), sleep=lambda s: None)


def test_10ka_without_a_full_instance_is_ignored_and_the_10k_is_used(tmp_path):
    cl = _client(tmp_path, _synthetic_world(None))
    mix = _mix_of(geographic_mix_as_of(1, date(2026, 6, 30), client=cl))
    assert (mix.accn, mix.form) == ("0000000001-26-000001", "10-K")


def test_10ka_with_a_full_instance_supersedes_the_10k(tmp_path):
    amended = synthetic_instance(
        [fact(1000), geo("country:US", 800), geo("country:DE", 200)], doc_type="10-K/A"
    )
    cl = _client(tmp_path, _synthetic_world(amended))
    mix = _mix_of(geographic_mix_as_of(1, date(2026, 6, 30), client=cl))
    assert (mix.accn, mix.form) == ("0000000001-26-000002", "10-K/A")
    assert mix.mix == pytest.approx({"United States": 0.8, "Germany": 0.2})


def test_10ka_filed_after_as_of_is_not_visible(tmp_path):
    amended = synthetic_instance([fact(1000), geo("country:US", 800), geo("country:DE", 200)])
    cl = _client(tmp_path, _synthetic_world(amended))
    mix = _mix_of(geographic_mix_as_of(1, date(2026, 3, 1), client=cl))
    assert mix.accn == "0000000001-26-000001"


def test_missing_archive_document_is_none_with_reason(tmp_path):
    world = _synthetic_world(None)
    del world[f"{archive_dir(1, '0000000001-26-000001')}/x_htm.xml"]

    class Missing(FixtureTransport):
        def __call__(self, url, headers):
            self.calls.append(url)
            return (200, self.routes[url]) if url in self.routes else (404, b"")

    cl = EdgarClient(tmp_path, transport=Missing(world), sleep=lambda s: None)
    res = geographic_mix_as_of(1, date(2026, 6, 30), client=cl)
    assert res.mix is None
    assert "404" in (res.reason or "")


# ---------------------------------------------------------------- ISO table
def _erp_countries() -> dict:
    return json.loads((REFERENCE / "country_erp_2026-04.json").read_text(encoding="utf-8"))[
        "countries"
    ]


def test_iso_table_targets_exist_in_the_erp_and_tax_datasets():
    tax = json.loads((REFERENCE / "country_tax_2026-04.json").read_text(encoding="utf-8"))[
        "countries"
    ]
    targets = {v for v in ISO2_TO_DATASET_NAME.values() if v is not None}
    assert targets
    assert targets <= set(_erp_countries())
    assert targets <= set(tax)  # every country the ERP file rates also has a statutory rate


def test_iso_table_is_complete_alpha2_and_covers_every_iso_country_in_the_dataset():
    assert len(ISO2_TO_DATASET_NAME) == 249  # ISO 3166-1 officially assigned alpha-2 codes
    assert all(len(c) == 2 and c.isupper() for c in ISO2_TO_DATASET_NAME)
    emirates = {"Abu Dhabi", "Sharjah", "Ras Al Khaimah (Emirate of)"}  # sub-national, no ISO code
    mapped = {v for v in ISO2_TO_DATASET_NAME.values() if v}
    assert set(_erp_countries()) - emirates - mapped == set()


def test_iso_codes_without_a_dataset_row_do_not_resolve_by_accident():
    for code, target in ISO2_TO_DATASET_NAME.items():
        if target is None:
            assert resolve_revenue_key(code) is None, code
        else:
            hit = resolve_revenue_key(target)
            assert hit is not None and hit[0] == target


def test_iso_spot_checks():
    t = ISO2_TO_DATASET_NAME
    assert t["US"] == "United States"
    assert t["GB"] == "United Kingdom"
    assert t["KR"] == "Korea"
    assert t["CZ"] == "Czech Republic"
    assert t["RU"] is None  # Russia is in the tax file but has no ERP row
    assert t["CI"] == "Côte d'Ivoire"


# ---------------------------------------------------------------- end to end (offline)
class _Sec:
    """The two attributes company_erp / company_marginal_tax read."""

    def __init__(self, mix):
        self.revenue_mix = mix
        self.country_iso = "US"


def test_blk_mix_drives_company_erp_and_marginal_tax(client):
    mix = _mix_of(geographic_mix_as_of("BLK", date(2026, 6, 30), client=client))
    sec = _Sec(mix.mix)
    erp, erp_source = company_erp(sec)
    tax, tax_source = company_marginal_tax(sec)
    us_erp, us_tax = company_erp(_Sec({}))[0], company_marginal_tax(_Sec({}))[0]
    assert "revenue-weighted" in erp_source and "coverage 100%" in erp_source
    assert "revenue-weighted" in tax_source and "coverage 100%" in tax_source
    assert erp != us_erp
    assert tax != us_tax
    # Computed from the 10-K mix, not the owner's 5.44% (his mix came from his own report).
    print(f"BLK 2026-06-30: ERP {erp:.6f} tax {tax:.6f}")


def test_aapl_mix_reports_partial_resolution_in_the_sources(client):
    mix = _mix_of(geographic_mix_as_of("AAPL", date(2026, 6, 30), client=client))
    sec = _Sec(mix.mix)
    _, erp_source = company_erp(sec)
    _, tax_source = company_marginal_tax(sec)
    assert "coverage 52%" in erp_source
    assert "unresolved keys excluded: OtherCountries" in erp_source
    assert "coverage 52%" in tax_source


def test_recorded_fixtures_are_small():
    for p in FIXTURES.glob("instance_*.xml"):
        assert p.stat().st_size < 100_000, p


def test_10ka_for_an_older_fiscal_year_does_not_supersede_the_latest_10k(tmp_path):
    world = _synthetic_world(
        synthetic_instance([fact(1000), geo("country:DE", 1000)], doc_type="10-K/A")
    )
    sub = json.loads(world[edgar_client.submissions_url(1)])
    sub["filings"]["recent"]["reportDate"] = ["2024-12-31", "2025-12-31"]  # amendment: FY2024
    world[edgar_client.submissions_url(1)] = json.dumps(sub).encode()
    cl = _client(tmp_path, world)
    mix = _mix_of(geographic_mix_as_of(1, date(2026, 6, 30), client=cl))
    assert (mix.accn, mix.form) == ("0000000001-26-000001", "10-K")


def test_10ka_whose_archive_is_unreadable_is_skipped(tmp_path):
    world = _synthetic_world(
        synthetic_instance([fact(1000), geo("country:DE", 1000)], doc_type="10-K/A")
    )
    del world[f"{archive_dir(1, '0000000001-26-000002')}/index.json"]

    class Missing(FixtureTransport):
        def __call__(self, url, headers):
            self.calls.append(url)
            return (200, self.routes[url]) if url in self.routes else (404, b"")

    cl = EdgarClient(tmp_path, transport=Missing(world), sleep=lambda s: None)
    mix = _mix_of(geographic_mix_as_of(1, date(2026, 6, 30), client=cl))
    assert mix.accn == "0000000001-26-000001"
