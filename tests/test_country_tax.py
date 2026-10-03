"""Damodaran country tax data and the company MARGINAL tax rate (Part A).

Owner methodology (NYU Stern "On BLK" plus Damodaran's convention): the MARGINAL
rate relevers beta and tax-effects the cost of debt; it is the country statutory
rate weighted by revenue geography exactly like the owner's ERP. All offline.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from iam.data import damodaran as dm
from iam.data.ground_truth import GroundTruthProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.orchestrator import ValuationPipeline
from iam.valuation import country_risk as cr
from iam.valuation import country_tax as ct

ONE_BP = 1e-4
RF = 0.043
BLK_MIX = {
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
# Claude's independent check of the owner's mix.
BLK_COMPONENTS = {
    "United States": 0.2500,
    "Canada": 0.2614,
    "latam": 0.3155,
    "United Kingdom": 0.2500,
    "eurozone": 0.2727,
    "mea": 0.2059,
    "Japan": 0.2974,
    "Australia": 0.3000,
    "asia": 0.2565,
}
TAX_FILE = dm._REFERENCE_DIR / "country_tax_2026-04.json"


def _tnx(_symbol: str) -> SimpleNamespace:
    return SimpleNamespace(last=RF * 100.0)


def _blk(**kw) -> Security:
    return Security(
        ticker="BLKX",
        sector="Investments & Asset Management",
        industry="Asset Management",
        fundamentals=Fundamentals(
            revenue_ttm=100.0,
            operating_margin=0.3,
            interest_expense_ttm=5.0,
            net_income_ttm=50.0,
            fcf_ttm=50.0,
            total_debt=230.0,
            shares_outstanding=10.0,
            **kw,
        ),
        market=MarketData(price=100.0, shares_outstanding=10.0, market_cap=1000.0, beta=1.3),
        revenue_mix=dict(BLK_MIX),
    )


def _offline():
    return (
        patch("iam.data.markets.fetch_live_quote", side_effect=_tnx),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=Exception("No network"),
        ),
    )


# ------------------------------------------------------------------ data + loader
def test_shipped_tax_file_is_the_provided_extract():
    data = json.loads(TAX_FILE.read_text(encoding="utf-8"))
    assert data["as_of"] == "2026-04-01"
    assert data["countries"]["United States"] == 0.25
    assert data["regions"]["Asia"]["marginal_tax_gdp_weighted"] == pytest.approx(0.256545)


def test_loader_picks_newest_dated_file_and_ignores_other_names(tmp_path):
    for name in (
        "country_tax_2025-12.json",
        "country_tax_2026-04.json",
        "country_tax_latest.json",
        "country_tax_2026-4.json",
    ):
        (tmp_path / name).write_text("{}")
    assert dm.latest_country_tax_file(tmp_path).name == "country_tax_2026-04.json"
    assert ct.load_country_tax()["as_of"] == "2026-04-01"


def test_env_override_wins(tmp_path, monkeypatch):
    alt = tmp_path / "alt.json"
    alt.write_text('{"as_of": "2030-01-01", "countries": {"United States": 0.5}, "regions": {}}')
    monkeypatch.setenv("IAM_COUNTRY_TAX_FILE", str(alt))
    assert ct.load_country_tax()["countries"]["United States"] == 0.5
    assert ct.company_marginal_tax(Security(ticker="X"))[0] == 0.5


# ------------------------------------------------------------------ the owner's mix
def test_blk_mix_marginal_tax_within_1bp_and_components():
    out = ct.blended_marginal_tax(BLK_MIX)
    assert out.rate == pytest.approx(0.2557, abs=ONE_BP)
    by_name = {n: r for n, _w, r in out.components}
    assert set(by_name) == set(BLK_COMPONENTS)
    for name, rate in BLK_COMPONENTS.items():
        assert by_name[name] == pytest.approx(rate, abs=ONE_BP), name
    assert sum(w for _n, w, _r in out.components) == pytest.approx(1.0)  # 99% mix renormalised
    assert out.coverage == pytest.approx(1.0)


def test_company_marginal_tax_blk_and_source_names_dataset_and_coverage():
    rate, src = ct.company_marginal_tax(_blk())
    assert rate == pytest.approx(0.2557, abs=ONE_BP)
    assert "Damodaran Apr 2026" in src and "coverage 100%" in src
    assert "revenue-weighted" in src


def test_aliases_approximations_are_stated_in_the_source():
    rate, src = ct.company_marginal_tax(Security(ticker="X", revenue_mix={"emea": 1.0}))
    assert rate == pytest.approx(0.255572, abs=1e-3)
    assert "emea treated as Western Europe" in src


def test_unresolved_keys_are_excluded_reported_and_renormalised():
    out = ct.blended_marginal_tax({"us": 0.5, "atlantis": 0.5})
    assert out.unresolved == ["atlantis"]
    assert out.coverage == pytest.approx(0.5)
    assert out.rate == pytest.approx(0.25)
    assert "atlantis" in out.source


def test_country_missing_from_the_tax_table_is_reported_not_invented():
    tbl = {"as_of": "2026-04-01", "countries": {"United States": 0.25}, "regions": {}}
    out = ct.blended_marginal_tax({"us": 0.5, "uk": 0.5}, table=tbl)
    assert out.unresolved == ["uk"]
    assert out.rate == pytest.approx(0.25)


# ------------------------------------------------------------------ no mix
def test_no_mix_uses_country_iso_rate():
    rate, src = ct.company_marginal_tax(Security(ticker="X", country_iso="DE"))
    assert rate == pytest.approx(0.2993)
    assert "Germany" in src and "country_iso" in src
    rate, src = ct.company_marginal_tax(Security(ticker="X", country_iso="GB"))
    assert rate == pytest.approx(0.25)
    assert "United Kingdom" in src


def test_no_mix_and_no_iso_uses_the_us_rate():
    rate, src = ct.company_marginal_tax(Security(ticker="X", country_iso=""))
    assert rate == pytest.approx(0.25)
    assert "United States" in src and "no revenue mix" in src
    assert ct.company_marginal_tax(Security(ticker="X"))[0] == pytest.approx(0.25)


# ------------------------------------------------------------------ relevering + WACC
def test_relevered_beta_uses_the_marginal_rate_for_the_blk_like_security():
    p1, p2 = _offline()
    with p1, p2:
        profile = GroundTruthProvider().get_equity_risk_profile(_blk())
    assert profile is not None
    t = ct.company_marginal_tax(_blk())[0]
    assert profile.tax_rate == pytest.approx(t)
    assert profile.levered_beta == pytest.approx(0.59 * (1 + (1 - 0.2557) * 0.23), abs=1e-4)
    assert profile.levered_beta == pytest.approx(0.691, abs=1e-3)
    assert profile.cost_of_equity == pytest.approx(0.08057, abs=ONE_BP)
    assert "Damodaran Apr 2026" in profile.tax_source
    assert not any("21%" in d for d in profile.defaults_used)


def test_reference_wacc_uses_the_same_marginal_rate_for_the_after_tax_cost_of_debt():
    sec = _blk()
    p1, p2 = _offline()
    with p1, p2:
        info = ValuationPipeline._calculate_dynamic_wacc(sec)
    assert info is not None
    t = ct.company_marginal_tax(sec)[0]
    assert info["tax_rate"] == pytest.approx(t)
    assert "Damodaran Apr 2026" in info["tax_source"]
    de = 0.23
    expected = info["cost_of_equity"] / (1 + de) + info["cost_of_debt"] * (1 - t) * de / (1 + de)
    assert info["wacc"] == pytest.approx(expected, abs=1e-12)
    assert not any("21%" in d for d in info["defaults_used"])


def test_us_statutory_constants_are_gone():
    import iam.data.ground_truth as gt
    import iam.pipeline.orchestrator as orch

    assert not hasattr(gt, "US_FEDERAL_STATUTORY_TAX")
    assert not hasattr(orch, "US_FEDERAL_STATUTORY_TAX")


def test_tax_loader_does_not_disturb_the_erp_loader():
    assert cr.load_country_erp()["as_of"].startswith("2026-04-01")


def test_unresolvable_revenue_mix_falls_back_to_home_country_before_us():
    """AGY review (gemini-3.8-flash): zero coverage must try country_iso before the US rate."""
    from iam.data.security import Security
    from iam.valuation.country_tax import company_marginal_tax, load_country_tax

    germany = load_country_tax()["countries"]["Germany"]
    rate, source = company_marginal_tax(
        Security(ticker="DEX", revenue_mix={"atlantis": 1.0}, country_iso="DE")
    )
    assert rate == pytest.approx(germany)
    assert "Germany" in source and "atlantis" in source
