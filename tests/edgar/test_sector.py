"""SIC -> engine sector/industry mapping and the submissions-JSON reader."""

from __future__ import annotations

import json

import pytest

from iam.data.damodaran import DamodaranProvider
from iam.data.edgar import client as ec
from iam.data.edgar.client import EdgarClient
from iam.data.edgar.sector import (
    SIC_TABLE,
    company_sector,
    fetch_company_sector,
    sector_for_sic,
)
from tests.edgar.helpers import FIXTURES, FixtureTransport, recorded_routes


@pytest.mark.parametrize(
    ("sic", "industry"),
    [
        ("7372", "software"),
        ("3571", "hardware"),
        ("3674", "semiconductors"),
        ("6021", "banks"),
        ("6211", "brokerage"),
        ("6282", "asset management"),
        ("6311", "insurance"),
        ("2834", "pharmaceuticals"),
        ("1311", "energy"),  # oil and gas map to the energy key (see module docstring)
        ("4911", "utilities"),
        ("6798", "reit"),
    ],
)
def test_known_sic_codes_map_to_damodaran_industries(sic, industry):
    m = sector_for_sic(sic)
    assert m.industry == industry
    assert m.sector is not None
    assert m.reason is None


def test_mapping_resolves_to_the_intended_industry_beta():
    m = sector_for_sic("7372")
    assert (
        DamodaranProvider.find_industry_unlevered_beta(m.sector, m.industry)
        == (DamodaranProvider.UNLEVERED_BETAS["software"])
    )


def test_every_table_entry_resolves_to_its_own_industry_beta():
    """The sector/industry strings must be ones the engine's beta lookup understands."""
    for entry in SIC_TABLE:
        beta = DamodaranProvider.find_industry_unlevered_beta(entry.sector, entry.industry)
        assert beta == DamodaranProvider.UNLEVERED_BETAS[entry.industry], entry


def test_sic_ranges_are_sorted_and_do_not_overlap():
    for entry in SIC_TABLE:
        assert entry.low <= entry.high
    for prev, nxt in zip(SIC_TABLE, SIC_TABLE[1:], strict=False):
        assert prev.high < nxt.low, (prev, nxt)


@pytest.mark.parametrize("sic", ["6770", "9995", "0", "", None, "abc"])
def test_unmapped_sic_gives_none_and_a_reason_never_unknown(sic):
    m = sector_for_sic(sic)
    assert m.sector is None
    assert m.industry is None
    assert m.reason
    assert "unknown" not in (m.sector or "").lower()


def test_company_sector_from_recorded_submissions():
    doc = json.loads((FIXTURES / "submissions_MSFT.json").read_text())
    cs = company_sector(doc)
    assert cs.sic == "7372"
    assert cs.sic_description == "Services-Prepackaged Software"
    assert cs.industry == "software"
    assert cs.cik == 789019


def test_former_names_expose_cik_history():
    doc = json.loads((FIXTURES / "submissions_BLK_old.json").read_text())
    cs = company_sector(doc)
    names = [f.name for f in cs.former_names]
    assert "BlackRock Inc." in names
    assert cs.name == "BlackRock Finance, Inc."
    first = next(f for f in cs.former_names if f.name == "BlackRock Inc.")
    assert first.to.startswith("2024-09-26")


def test_company_sector_unmapped_carries_reason():
    cs = company_sector({"cik": "0000000001", "name": "SHELL", "sic": "6770", "formerNames": []})
    assert cs.sector is None
    assert cs.reason


def test_fetch_company_sector_uses_the_client(tmp_path):
    transport = FixtureTransport(recorded_routes())
    client = EdgarClient(tmp_path / "c", transport=transport, sleep=lambda s: None)
    cs = fetch_company_sector(320193, client=client)
    assert cs.industry == "hardware"
    assert transport.calls == [ec.submissions_url(320193)]
