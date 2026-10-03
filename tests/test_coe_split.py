"""Stage-specific costs of equity (consensus vs bottom-up) and the Rf terminal cap.

Owner methodology (NYU Stern "On BLK"):
  * Stage 1, "what does the price imply?": consensus Ke = Rf + regression beta x US ERP.
  * Stage 3, "what is it worth?":          bottom-up Ke = Rf + relevered industry beta
                                           x revenue-weighted ERP.
  * Terminal growth never exceeds the risk-free rate.

All tests run offline: ``fetch_live_quote`` returns a fixed ^TNX quote and the
regression-input builder raises.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from iam.data.damodaran import DamodaranProvider
from iam.data.ground_truth import GroundTruthProvider
from iam.data.security import Fundamentals, MarketData, Security
from iam.engine.market_implied import MarketImpliedEngine
from iam.pipeline.orchestrator import ValuationPipeline
from iam.valuation import country_risk as cr
from iam.valuation.beta import get_custom_beta_for_intrinsic
from iam.valuation.country_tax import company_marginal_tax
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.reverse_dcf import ReverseDCF

RF = 0.043  # ^TNX 4.30
BETA = 1.30
UNLEVERED_ASSET_MGMT = 0.59  # Damodaran sector unlevered beta for asset management
DE = 0.23
MIX = {"us": 0.64, "uk": 0.09, "eurozone": 0.13, "japan": 0.035, "asia": 0.105}


def _tnx(_symbol: str) -> SimpleNamespace:
    return SimpleNamespace(last=RF * 100.0)


def _blk_like(market_cap: float | None = 1000.0, **qual) -> Security:
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
            total_debt=DE * 1000.0,
            shares_outstanding=10.0,
        ),
        market=MarketData(price=100.0, shares_outstanding=10.0, market_cap=market_cap, beta=BETA),
        revenue_mix=dict(MIX),
        qualitative=dict(qual),
    )


def _offline():
    return (
        patch("iam.data.markets.fetch_live_quote", side_effect=_tnx),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=Exception("No network"),
        ),
    )


def _run(sec: Security):
    p1, p2 = _offline()
    with p1, p2:
        return ValuationPipeline().run(sec)


def _bottom_up_ke(sec: Security) -> tuple[float, float]:
    erp, _ = cr.company_erp(sec)
    tax, _ = company_marginal_tax(sec)  # revenue-weighted statutory rate (was 21%)
    beta_l = UNLEVERED_ASSET_MGMT * (1 + (1 - tax) * DE)
    return RF + beta_l * erp, beta_l


# ---------------------------------------------------------------- Stage 1
def test_stage1_uses_consensus_ke_with_us_erp_not_blended():
    sec = _blk_like()
    report = _run(sec)
    us_erp = cr.load_country_erp()["us_erp"]
    blended, _ = cr.company_erp(sec)
    assert blended != pytest.approx(us_erp, abs=1e-4)  # the mix really differs from US
    r = report.market_implied_engine.implied.discount_rate_assumed
    assert r == pytest.approx(RF + BETA * us_erp, abs=1e-9)
    assert r != pytest.approx(RF + BETA * blended, abs=1e-4)
    notes = " | ".join(report.market_implied_engine.notes)
    assert "consensus Ke (US ERP, regression beta)" in notes


# ---------------------------------------------------------------- Stage 3
def test_intrinsic_uses_bottom_up_ke_with_company_erp():
    sec = _blk_like()
    report = _run(sec)
    ke, _ = _bottom_up_ke(sec)
    assert report.intrinsic.assumptions["discount_rate"] == pytest.approx(ke, abs=1e-9)
    notes = " | ".join(report.intrinsic.notes)
    assert "bottom-up Ke (industry beta relevered, revenue-weighted ERP)" in notes
    assert "custom CAPM" not in notes


def test_reference_wacc_uses_bottom_up_ke():
    sec = _blk_like()
    _run(sec)
    ke, _ = _bottom_up_ke(sec)
    assert sec.qualitative["wacc_info"]["cost_of_equity"] == pytest.approx(ke, abs=1e-9)


def test_run_does_not_write_caller_capm_keys():
    sec = _blk_like()
    _run(sec)
    assert "risk_free_rate" not in sec.qualitative
    assert "equity_risk_premium" not in sec.qualitative


def test_caller_supplied_capm_is_honoured_by_both_stages_and_not_overwritten():
    sec = _blk_like(risk_free_rate=0.045, equity_risk_premium=0.055)
    probe = copy.deepcopy(sec)
    custom_beta = get_custom_beta_for_intrinsic(probe)
    report = _run(sec)
    assert sec.qualitative["risk_free_rate"] == 0.045
    assert sec.qualitative["equity_risk_premium"] == 0.055
    assert report.market_implied_engine.implied.discount_rate_assumed == pytest.approx(
        0.045 + BETA * 0.055, abs=1e-9
    )
    assert report.intrinsic.assumptions["discount_rate"] == pytest.approx(
        0.045 + custom_beta * 0.055, abs=1e-9
    )
    assert "custom CAPM" in " | ".join(report.intrinsic.notes)


# ---------------------------------------------------------------- missing inputs
def test_no_market_cap_means_no_bottom_up_profile():
    sec = _blk_like(market_cap=None)
    p1, p2 = _offline()
    with p1, p2:
        assert GroundTruthProvider().get_equity_risk_profile(sec) is None
        assert ValuationPipeline._calculate_dynamic_wacc(sec) is None


def test_no_market_cap_intrinsic_does_not_claim_a_computed_ke():
    sec = _blk_like(market_cap=None)
    report = _run(sec)
    notes = " | ".join(report.intrinsic.notes)
    assert "bottom-up Ke" not in notes
    assert "market cap" in notes.lower()
    assert "wacc_info" not in sec.qualitative


def test_unknown_industry_means_no_bottom_up_profile():
    sec = _blk_like()
    sec.sector = "Zzz Unclassified"
    sec.industry = "Qqq Unclassified"
    p1, p2 = _offline()
    with p1, p2:
        assert GroundTruthProvider().get_equity_risk_profile(sec) is None


def test_profile_records_sources_and_statutory_tax_default():
    sec = _blk_like()
    p1, p2 = _offline()
    with p1, p2:
        profile = GroundTruthProvider().get_equity_risk_profile(sec)
    assert profile is not None
    ke, beta_l = _bottom_up_ke(sec)
    assert profile.levered_beta == pytest.approx(beta_l, abs=1e-9)
    assert profile.cost_of_equity == pytest.approx(ke, abs=1e-9)
    assert profile.industry_unlevered_beta == UNLEVERED_ASSET_MGMT
    assert "live ^TNX" in profile.rf_source
    assert cr.load_country_erp()["as_of"] in profile.erp_source
    assert profile.tax_rate == pytest.approx(company_marginal_tax(sec)[0])
    assert profile.tax_rate != 0.21
    assert "Damodaran Apr 2026" in profile.tax_source
    assert profile.defaults_used == []
    assert DamodaranProvider.CURRENT_RISK_FREE_RATE != RF  # rf really came from the quote


# ---------------------------------------------------------------- terminal cap
def _plain(rf_cap_security: Security | None = None) -> Security:
    return rf_cap_security or _blk_like(risk_free_rate=RF, equity_risk_premium=0.05)


@pytest.mark.parametrize("engine_cls", [MarketImpliedEngine, ReverseDCF])
def test_reverse_dcf_engines_cap_terminal_growth_at_rf(engine_cls):
    res = engine_cls(terminal_growth=0.06).compute(_plain())
    assert res.implied.implied_terminal_growth == pytest.approx(RF)
    assert res.assumptions["terminal_growth"] == pytest.approx(RF)
    assert "terminal growth capped at Rf 4.30%" in " | ".join(res.notes)


@pytest.mark.parametrize("engine_cls", [MarketImpliedEngine, ReverseDCF])
def test_reverse_dcf_engines_leave_lower_terminal_growth_unchanged(engine_cls):
    res = engine_cls(terminal_growth=0.02).compute(_plain())
    assert res.implied.implied_terminal_growth == pytest.approx(0.02)
    assert "capped" not in " | ".join(res.notes)


def test_fcfe_caps_base_and_every_scenario_tv_g_at_rf():
    res = FCFEDCF().compute(_plain(), FCFEAssumptions(high_growth=0.08, terminal_growth=0.06))
    assert res.assumptions["terminal_growth"] == pytest.approx(RF)
    sc = res.components["scenarios"]
    assert sc["Base Case"]["tv_g"] == pytest.approx(RF)
    assert sc["Bear Case"]["tv_g"] == pytest.approx(RF * 0.8)
    assert sc["Bull Case"]["tv_g"] == pytest.approx(RF)  # 1.2 x cap, re-capped at Rf
    assert all(s["tv_g"] <= RF + 1e-12 for s in sc.values())
    assert "terminal growth capped at Rf 4.30%" in " | ".join(res.notes)


def test_fcfe_leaves_lower_terminal_growth_unchanged_but_caps_bull_scenario():
    res = FCFEDCF().compute(_plain(), FCFEAssumptions(high_growth=0.08, terminal_growth=0.02))
    sc = res.components["scenarios"]
    assert res.assumptions["terminal_growth"] == pytest.approx(0.02)
    assert sc["Base Case"]["tv_g"] == pytest.approx(0.02)
    assert sc["Bull Case"]["tv_g"] == pytest.approx(0.024)  # 1.2 x 2%, below Rf: untouched
    assert "capped" not in " | ".join(res.notes)


def test_fcfe_bottom_up_path_caps_at_profile_rf():
    sec = _blk_like()
    p1, p2 = _offline()
    with p1, p2:
        res = FCFEDCF().compute(sec, FCFEAssumptions(high_growth=0.08, terminal_growth=0.06))
    assert res.assumptions["terminal_growth"] == pytest.approx(RF)


# ------------------------------------------------- AGY review follow-ups (gemini)
def test_pipeline_caps_stage1_terminal_growth_at_the_consensus_rf():
    """No caller override: Stage 1's cap must use the consensus Rf passed by the orchestrator."""
    sec = _blk_like()
    p1, p2 = _offline()
    with p1, p2:
        pipeline = ValuationPipeline()
        pipeline.market_implied_engine = MarketImpliedEngine(terminal_growth=0.06)
        report = pipeline.run(sec)
    stage1 = report.market_implied_engine
    assert stage1.assumptions["terminal_growth"] == pytest.approx(RF)
    assert any("terminal growth capped at Rf" in n for n in stage1.notes)
    assert any("consensus Ke" in n for n in stage1.notes)


@pytest.mark.parametrize("engine_cls", [MarketImpliedEngine, ReverseDCF])
def test_string_caller_overrides_are_used_not_crashing(engine_cls):
    """Overrides parsed from JSON arrive as strings; they must be honoured, not crash the note."""
    sec = _blk_like(risk_free_rate=str(RF), equity_risk_premium="0.05")
    res = engine_cls().compute(sec)
    assert res.assumptions["discount_rate"] == pytest.approx(RF + BETA * 0.05)


def test_string_caller_overrides_are_not_silently_dropped_by_fcfe():
    sec = _blk_like(risk_free_rate=str(RF), equity_risk_premium="0.05")
    res = FCFEDCF().compute(sec, FCFEAssumptions(high_growth=0.08, terminal_growth=0.02))
    assert any("custom CAPM" in n for n in res.notes)
    beta = get_custom_beta_for_intrinsic(_blk_like(risk_free_rate=RF, equity_risk_premium=0.05))
    assert res.assumptions["discount_rate"] == pytest.approx(RF + beta * 0.05)
