"""Revenue-weighted ERP from Damodaran country/regional data (newest shipped file)."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from iam.data.damodaran import DamodaranProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.orchestrator import ValuationPipeline
from iam.valuation import country_risk as cr
from tests.erp_helpers import region_erp

# Fixture table for the owner's "On BLK" arithmetic: 66% Americas / 30% EMEA / 4% APAC.
_E_WEST = (0.0540 - 0.66 * 0.0503 - 0.04 * 0.0645) / 0.30


def _fixture_table() -> dict:
    return {
        "source": "fixture",
        "as_of": "fixture-date",
        "mature_market_erp": 0.0423,
        "us_erp": 0.0503,
        "relative_equity_volatility": 1.5,
        "regions": {
            "North America": {"erp": 0.0503, "crp": 0.0, "gdp_musd_2024": 1},
            "Western Europe": {"erp": _E_WEST, "crp": 0.0, "gdp_musd_2024": 1},
            "Asia": {"erp": 0.0645, "crp": 0.0, "gdp_musd_2024": 1},
        },
        "countries": {
            "United States": {"region": "North America", "moodys": "Aa1", "erp": 0.0503, "crp": 0},
            "United Kingdom": {
                "region": "Western Europe",
                "moodys": "Aa3",
                "erp": 0.0600,
                "crp": 0,
            },
        },
    }


def test_owner_arithmetic_blk_mix_with_fixture():
    out = cr.blended_erp({"americas": 0.66, "emea": 0.30, "apac": 0.04}, table=_fixture_table())
    assert out.erp == pytest.approx(0.0540, abs=1e-4)
    assert out.coverage == pytest.approx(1.0)
    assert out.unresolved == []


def test_unknown_key_is_excluded_not_rated():
    out = cr.blended_erp({"us": 0.5, "atlantis": 0.5}, table=_fixture_table())
    assert out.unresolved == ["atlantis"]
    assert out.coverage == pytest.approx(0.5)
    assert out.erp == pytest.approx(0.0503)  # renormalised over the resolved weight
    assert all(name != "atlantis" for name, _, _ in out.components)
    with pytest.raises(ValueError):
        cr.country_risk("atlantis")  # no silent Baa3


def test_only_unknown_keys_fall_back_to_us_erp_with_reason():
    sec = Security(ticker="X", revenue_mix={"atlantis": 1.0})
    erp, src = cr.company_erp(sec)
    # Fallback is the US per-country ERP (rating/CDS averaged), was the rating-only us_erp.
    assert erp == pytest.approx(cr.country_erp("United States"))
    assert "atlantis" in src and "unresolved" in src.lower()


def test_eurozone_uk_row_mix_not_inflated():
    mix = {"us": 0.64, "eurozone": 0.13, "uk": 0.09, "row": 0.14}
    out = cr.blended_erp(mix)
    assert out.unresolved == ["row"]
    assert out.coverage == pytest.approx(0.86)
    assert out.erp != pytest.approx(0.0626, abs=5e-5)
    assert out.erp < 0.055


def test_no_revenue_mix_uses_us_erp():
    erp, src = cr.company_erp(Security(ticker="X"))
    # April 2026 US per-country ERP: mean of rating 5.03% and CDS 5.3838% (was 4.46% in January)
    assert erp == pytest.approx((0.0503 + 0.053838) / 2, abs=1e-9)
    assert "Damodaran Apr 2026" in src and "no revenue mix" in src


def test_shipped_data_blk_mix_matches_regional_values():
    data = cr.load_country_erp()
    # Regions are the GDP-weighted mean of their countries' rating/CDS-averaged ERPs
    # (was the published rating-only regional figure).
    expected = (
        0.66 * region_erp("North America")
        + 0.30 * region_erp("Western Europe")
        + 0.04 * region_erp("Asia")
    )
    sec = Security(ticker="BLK", revenue_mix={"americas": 0.66, "emea": 0.30, "apac": 0.04})
    erp, src = cr.company_erp(sec)
    assert erp == pytest.approx(expected)
    assert "americas treated as North America" in src
    assert "emea treated as Western Europe" in src
    assert "apac treated as Asia" in src
    assert data["as_of"] in src


def test_single_source_of_truth_constants():
    data = cr.load_country_erp()
    assert DamodaranProvider.CURRENT_IMPLIED_ERP == data["us_erp"]
    assert cr.DEFAULT_MATURE_ERP == data["mature_market_erp"]
    assert data["us_erp"] != data["mature_market_erp"]


def test_every_alias_target_exists():
    data = cr.load_country_erp()
    for target in cr.COUNTRY_ALIASES.values():
        assert target in data["countries"], target
    for target in cr.REGION_ALIASES.values():
        assert target in data["regions"], target


def test_loader_env_override_and_cwd_independence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cr.load_country_erp()["mature_market_erp"] == 0.0477
    alt = tmp_path / "alt.json"
    alt.write_text('{"mature_market_erp": 0.01, "us_erp": 0.02}')
    monkeypatch.setenv("IAM_COUNTRY_ERP_FILE", str(alt))
    assert cr.load_country_erp()["us_erp"] == 0.02


# ---------------------------------------------------------------- pipeline
def _offline_security(**qual) -> Security:
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            revenue_ttm=100.0,
            operating_margin=0.1,
            interest_expense_ttm=5.0,
            net_income_ttm=10.0,
            shares_outstanding=1.0,
        ),
        market=MarketData(price=10.0, shares_outstanding=1.0, market_cap=10.0, beta=1.5),
        sector="Investments & Asset Management",
        industry="Asset Management",
        revenue_mix={"americas": 0.66, "emea": 0.30, "apac": 0.04},
        qualitative=dict(qual),
    )


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_pipeline_uses_company_erp(mock_yf, mock_fetch):
    sec = _offline_security()
    expected, src = cr.company_erp(sec)
    ValuationPipeline().run(sec)
    # run() never writes the caller-override keys; the reference WACC records the ERP source.
    assert "equity_risk_premium" not in sec.qualitative
    assert "risk_free_rate" not in sec.qualitative
    wacc = sec.qualitative["wacc_info"]
    rf = DamodaranProvider.get_risk_free_rate()
    # Bottom-up Ke: asset-management unlevered beta 0.59, no debt, revenue-weighted ERP.
    assert wacc["cost_of_equity"] == pytest.approx(rf + 0.59 * expected)
    assert wacc["erp_source"] == src


@patch("iam.data.markets.fetch_live_quote", return_value=None)
@patch(
    "iam.data.providers.yfinance_adapter.build_regression_inputs",
    side_effect=Exception("No network"),
)
def test_pipeline_does_not_overwrite_caller_erp(mock_yf, mock_fetch):
    sec = _offline_security(equity_risk_premium=0.055)
    ValuationPipeline().run(sec)
    assert sec.qualitative["equity_risk_premium"] == 0.055
    assert sec.qualitative["erp_source"] == "caller-supplied"
    assert "risk_free_rate" not in sec.qualitative  # caller set only the ERP
    assert math.isclose(
        sec.qualitative["wacc_info"]["cost_of_equity"],
        DamodaranProvider.get_risk_free_rate() + 1.5 * 0.055,
    )
