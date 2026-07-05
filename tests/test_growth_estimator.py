"""Tests for the questionnaire-based fundamental growth estimator."""

from iam.data.security import Fundamentals, MarketData, Security
from iam.engine.growth_estimator import (
    GrowthQuestionnaire,
    QuestionnaireGrowthEngine,
)
from iam.engine.market_implied import MarketImpliedEngine
from iam.valuation.types import ImpliedExpectations, Method, ValuationResult


def _security(revenue_history: list[float] | None = None) -> Security:
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(revenue_history=revenue_history or []),
        market=MarketData(price=50.0),
    )


# ---------------------------------------------------------------------------
# Component-level behavior
# ---------------------------------------------------------------------------


def test_no_inputs_returns_no_estimate():
    result = QuestionnaireGrowthEngine().compute(_security(), GrowthQuestionnaire())
    assert result.blended_growth is None
    assert result.confidence == 0.0


def test_historical_growth_falls_back_to_revenue_history():
    sec = _security(revenue_history=[150, 130, 115, 105, 100])  # most-recent-first
    result = QuestionnaireGrowthEngine().compute(sec, GrowthQuestionnaire())
    hist = result.components["historical"]
    assert hist.value is not None
    expected = (150 / 100) ** (1 / 4) - 1
    assert abs(hist.value - expected) < 1e-9


def test_historical_questionnaire_override_takes_precedence():
    sec = _security(revenue_history=[150, 130, 115, 105, 100])
    q = GrowthQuestionnaire(historical_revenue_growth=0.05)
    result = QuestionnaireGrowthEngine().compute(sec, q)
    assert result.components["historical"].value == 0.05


def test_analyst_estimate_is_debiased_below_raw_consensus():
    q = GrowthQuestionnaire(analyst_consensus_growth=0.20)
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    analyst = result.components["analyst"]
    assert analyst.value is not None
    assert 0 < analyst.value < 0.20


def test_analyst_confidence_drops_with_high_dispersion():
    low_disp = GrowthQuestionnaire(
        analyst_consensus_growth=0.10, analyst_coverage_count=15, analyst_dispersion=0.05
    )
    high_disp = GrowthQuestionnaire(
        analyst_consensus_growth=0.10, analyst_coverage_count=15, analyst_dispersion=0.80
    )
    r_low = QuestionnaireGrowthEngine().compute(_security(), low_disp)
    r_high = QuestionnaireGrowthEngine().compute(_security(), high_disp)
    assert r_high.components["analyst"].confidence < r_low.components["analyst"].confidence


def test_fundamental_growth_is_retention_times_roe():
    q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    assert result.equity_growth_fundamental is not None
    assert abs(result.equity_growth_fundamental - 0.12) < 1e-9


def test_fundamental_growth_is_reinvestment_times_roic():
    q = GrowthQuestionnaire(reinvestment_rate=0.5, return_on_capital=0.18)
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    assert result.operating_growth_fundamental is not None
    assert abs(result.operating_growth_fundamental - 0.09) < 1e-9


def test_negative_roic_tanks_fundamental_confidence():
    q = GrowthQuestionnaire(reinvestment_rate=0.5, return_on_capital=-0.05)
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    fund = result.components["fundamental"]
    assert fund.value is not None
    assert fund.confidence < 0.5


def test_qualitative_overlay_penalizes_no_moat_and_declining_industry():
    base_q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    weak_q = GrowthQuestionnaire(
        retention_ratio=0.6,
        return_on_equity=0.20,
        competitive_moat_strength="none",
        industry_lifecycle_stage="decline",
        reinvestment_opportunity="scarce",
        management_capital_discipline="poor",
    )
    r_base = QuestionnaireGrowthEngine().compute(_security(), base_q)
    r_weak = QuestionnaireGrowthEngine().compute(_security(), weak_q)
    assert r_weak.components["fundamental"].value < r_base.components["fundamental"].value


def test_qualitative_overlay_boosts_wide_moat_abundant_opportunity():
    base_q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    strong_q = GrowthQuestionnaire(
        retention_ratio=0.6,
        return_on_equity=0.20,
        competitive_moat_strength="wide",
        industry_lifecycle_stage="high_growth",
        reinvestment_opportunity="abundant",
        management_capital_discipline="excellent",
    )
    r_base = QuestionnaireGrowthEngine().compute(_security(), base_q)
    r_strong = QuestionnaireGrowthEngine().compute(_security(), strong_q)
    assert r_strong.components["fundamental"].value > r_base.components["fundamental"].value


def test_weight_override_shifts_blend_toward_fundamental():
    q = GrowthQuestionnaire(
        historical_revenue_growth=0.02,
        analyst_consensus_growth=0.02,
        retention_ratio=0.6,
        return_on_equity=0.20,
        weight_historical=0.0,
        weight_analyst=0.0,
        weight_fundamental=1.0,
    )
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    fund_value = result.components["fundamental"].value
    assert abs(result.blended_growth - fund_value) < 1e-9


def test_partial_inputs_renormalize_over_available_components():
    """Only fundamental inputs supplied -> blended growth equals that component."""
    q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    assert result.components["historical"].value is None
    assert result.components["analyst"].value is None
    assert result.blended_growth == result.components["fundamental"].value


# ---------------------------------------------------------------------------
# Contrast against reverse DCF (market-implied growth)
# ---------------------------------------------------------------------------


def test_contrast_with_reverse_dcf_from_valuation_result():
    q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    result = QuestionnaireGrowthEngine().compute(_security(), q)

    reverse_dcf = ValuationResult(
        method=Method.REVERSE_DCF,
        implied=ImpliedExpectations(implied_revenue_growth=0.30),
    )
    result = QuestionnaireGrowthEngine().contrast_with_reverse_dcf(result, reverse_dcf)

    assert result.market_implied_growth == 0.30
    assert result.growth_gap is not None
    assert result.growth_gap < 0  # market implies more growth than fundamentals support
    assert "market is pricing in more growth" in result.gap_verdict


def test_contrast_with_reverse_dcf_from_raw_float():
    q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    result = QuestionnaireGrowthEngine().compute(_security(), q)
    result = QuestionnaireGrowthEngine().contrast_with_reverse_dcf(result, 0.05)
    assert result.market_implied_growth == 0.05
    assert result.growth_gap is not None
    assert result.growth_gap > 0
    assert "underpriced" in result.gap_verdict


def test_contrast_handles_missing_market_implied_growth():
    q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    result = QuestionnaireGrowthEngine().compute(_security(), q)

    reverse_dcf = ValuationResult(method=Method.REVERSE_DCF, implied=None)
    result = QuestionnaireGrowthEngine().contrast_with_reverse_dcf(result, reverse_dcf)

    assert result.market_implied_growth is None
    assert result.growth_gap is None
    assert "Cannot compare" in result.gap_verdict


def test_contrast_end_to_end_with_market_implied_engine():
    """Reverse DCF output flows directly into the growth contrast, matching
    the shape MarketImpliedEngine().compute() actually produces."""
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            net_income_ttm=900.0, fcf_ttm=1000.0, shares_outstanding=100.0
        ),
        market=MarketData(price=50.0),
    )
    reverse_dcf = MarketImpliedEngine().compute(sec)
    assert reverse_dcf.implied is not None

    q = GrowthQuestionnaire(retention_ratio=0.6, return_on_equity=0.20)
    result = QuestionnaireGrowthEngine().compute(sec, q)
    result = QuestionnaireGrowthEngine().contrast_with_reverse_dcf(result, reverse_dcf)

    assert result.market_implied_growth == reverse_dcf.implied.implied_revenue_growth
    assert result.gap_verdict != ""


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_pipeline_surfaces_growth_estimate_when_questionnaire_supplied():
    from iam import ValuationPipeline

    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            revenue_history=[150, 130, 115, 105, 100],
            net_income_ttm=900.0,
            fcf_ttm=1000.0,
            shares_outstanding=100.0,
        ),
        market=MarketData(price=50.0, market_cap=5000.0),
    )
    q = GrowthQuestionnaire(analyst_consensus_growth=0.12, retention_ratio=0.6, return_on_equity=0.20)

    report = ValuationPipeline().run(sec, growth_questionnaire=q)

    assert report.growth_estimate is not None
    assert report.growth_estimate.blended_growth is not None
    assert report.growth_estimate.market_implied_growth is not None
    assert "GROWTH QUESTIONNAIRE" in report.summary
    assert "GROWTH vs. REVERSE DCF" in report.summary


def test_pipeline_omits_growth_estimate_when_no_questionnaire():
    from iam import ValuationPipeline

    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(net_income_ttm=900.0, shares_outstanding=100.0),
        market=MarketData(price=50.0, market_cap=5000.0),
    )
    report = ValuationPipeline().run(sec)
    assert report.growth_estimate is None
