"""The GUI cost-of-equity card equals the intrinsic bottom-up Ke (Part D).

GUI -> integration.Orchestrator.value_security -> GroundTruthProvider.get_risk_profile
-> integration.adapter.from_ground_truth. The arbitration layer applies NO adjustment
to the value (the reliability weight rides along in ModelResult.reliability for a
later blend); the card therefore equals the profile's bottom-up Ke exactly.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from iam.data.damodaran import DamodaranProvider
from iam.data.ground_truth import GroundTruthProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.integration.adapter import from_ground_truth
from iam.integration.orchestrator import Orchestrator
from iam.ui import gui
from iam.valuation.country_risk import company_erp
from iam.valuation.country_tax import company_marginal_tax

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


def _blk() -> Security:
    return Security(
        ticker="BLKX",
        sector="Investments & Asset Management",
        industry="Asset Management",
        fundamentals=Fundamentals(total_debt=230.0, interest_expense_ttm=5.0),
        market=MarketData(price=100.0, shares_outstanding=10.0, market_cap=1000.0, beta=1.3),
        revenue_mix=dict(BLK_MIX),
    )


class _Poison(dict):
    def __getitem__(self, key):
        raise AssertionError(f"legacy 4.6% ERP table read: {key!r}")

    def get(self, key, default=None):
        raise AssertionError(f"legacy 4.6% ERP table read: {key!r}")

    def __contains__(self, key):
        raise AssertionError(f"legacy 4.6% ERP table read: {key!r}")


def _value(sec: Security) -> dict:
    with patch("iam.data.markets.fetch_live_quote", return_value=SimpleNamespace(last=RF * 100)):
        return Orchestrator().value_security(sec)


def test_card_value_is_the_intrinsic_bottom_up_ke():
    sec = _blk()
    out = _value(sec)
    card = gui._extract_cost_of_equity(out)
    erp, _ = company_erp(sec)
    tax, _ = company_marginal_tax(sec)
    beta_l = 0.59 * (1 + (1 - tax) * 0.23)
    assert tax == pytest.approx(0.2557, abs=1e-4)
    assert beta_l == pytest.approx(0.691, abs=1e-3)
    assert card == pytest.approx(RF + beta_l * erp, abs=1e-12)
    assert card == pytest.approx(0.08057, abs=1e-4)
    # and the same number the intrinsic stage and the ground-truth profile carry
    with patch("iam.data.markets.fetch_live_quote", return_value=SimpleNamespace(last=RF * 100)):
        profile = GroundTruthProvider().get_equity_risk_profile(sec)
    assert profile is not None
    assert card == pytest.approx(profile.cost_of_equity, abs=1e-12)


def test_nothing_on_the_card_path_reads_the_legacy_erp_tables(monkeypatch):
    monkeypatch.setattr(DamodaranProvider, "REGIONAL_ERPS", _Poison())
    monkeypatch.setattr(DamodaranProvider, "COUNTRY_ERPS", _Poison())
    monkeypatch.setattr(DamodaranProvider, "COUNTRY_TO_REGION", _Poison())

    def boom(*_a, **_k):
        raise AssertionError("DamodaranProvider.resolve_erp is on the card path")

    monkeypatch.setattr(DamodaranProvider, "resolve_erp", classmethod(boom))
    out = _value(_blk())
    assert out["model_result"].value == pytest.approx(0.08057, abs=1e-4)


def test_arbitration_applies_no_adjustment_to_the_value():
    out = _value(_blk())
    mr = out["model_result"]
    assert mr.value == out["risk_profile"]["cost_of_equity"]  # exact, not approx
    assert mr.distribution["mean"] == mr.value
    assert mr.reliability == pytest.approx(0.90)  # weight only; the blend is elsewhere
    assert mr.provenance["version"] == "damodaran_2026-04"
    assert mr.provenance["tax_version"] == "damodaran_tax_2026-04"


def test_dispersion_uses_the_profiles_erp_not_a_recomputed_blend():
    profile = {
        "erp": 0.052,  # the profile's own blended ERP (breakdown weights are rounded)
        "levered_beta": 0.5,
        "cost_of_equity": 0.07,
        "erp_breakdown": {
            "a": {"weight": 0.5, "erp": 0.04},
            "b": {"weight": 0.5, "erp": 0.06},
        },
    }
    out = from_ground_truth("t", profile)
    expected = math.sqrt(0.5 * (0.04 - 0.052) ** 2 + 0.5 * (0.06 - 0.052) ** 2) * 0.5
    assert out.distribution["std"] == pytest.approx(expected, abs=1e-15)


def test_dispersion_falls_back_to_the_breakdown_blend_when_the_profile_has_no_erp():
    profile = {
        "levered_beta": 1.0,
        "cost_of_equity": 0.07,
        "erp_breakdown": {"a": {"weight": 0.5, "erp": 0.04}, "b": {"weight": 0.5, "erp": 0.06}},
    }
    assert from_ground_truth("t", profile).distribution["std"] == pytest.approx(0.01)


def test_the_card_caption_says_what_the_number_is():
    assert "bottom-up" in gui.COST_OF_EQUITY_CAPTION.lower()
    assert "arbitrated" not in gui.COST_OF_EQUITY_CAPTION.lower()
