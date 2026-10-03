"""Provenance versions come from the loaded datasets, not a stale literal (Part C2)."""

from __future__ import annotations

from iam.data.ground_truth import GroundTruthProvider
from iam.data.provenance import attach_provenance
from iam.data.security import Fundamentals, MarketData, Security


def test_default_version_is_derived_from_the_loaded_erp_dataset():
    prov = attach_provenance({})["_provenance"]
    assert prov["version"] == "damodaran_2026-04"


def test_version_follows_the_env_override_dataset(tmp_path, monkeypatch):
    alt = tmp_path / "alt.json"
    alt.write_text('{"as_of": "2027-01-01", "mature_market_erp": 0.04, "us_erp": 0.05}')
    monkeypatch.setenv("IAM_COUNTRY_ERP_FILE", str(alt))
    assert attach_provenance({})["_provenance"]["version"] == "damodaran_2027-01"


def test_an_explicit_version_still_wins():
    assert attach_provenance({}, version="custom")["_provenance"]["version"] == "custom"


def test_tax_dataset_version_is_stamped_only_when_the_data_uses_the_tax_table():
    assert "tax_version" not in attach_provenance({"erp": 0.05})["_provenance"]
    with_tax = attach_provenance({"tax_source": "x"})["_provenance"]
    assert with_tax["tax_version"] == "damodaran_tax_2026-04"


def test_risk_profile_carries_both_versions():
    sec = Security(
        ticker="P",
        sector="Investments & Asset Management",
        industry="Asset Management",
        fundamentals=Fundamentals(total_debt=100.0),
        market=MarketData(price=10.0, market_cap=1000.0),
    )
    prov = GroundTruthProvider().get_risk_profile(sec)["_provenance"]
    assert prov["version"] == "damodaran_2026-04"
    assert prov["tax_version"] == "damodaran_tax_2026-04"
