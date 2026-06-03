"""Tests for all valuation lenses and the synthesis engine."""

import pytest

from iam.data.security import Fundamentals, MacroContext, MarketData, Security
from iam.lenses.base import LensResult
from iam.engine.damodaran import DamodaranEngine
from iam.lenses.expectations_difficulty import ExpectationsDifficultyLens
from iam.lenses.platform_compounder import PlatformCompounderLens
from iam.lenses.rate_sensitive import RateSensitiveLens
from iam.lenses.synthesis import synthesize_lenses

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_security(
    fcf_ttm: float = 500.0,
    shares: float = 100.0,
    price: float = 100.0,
    macro: MacroContext | None = None,
    operating_margin_history: list[float] | None = None,
) -> Security:
    f = Fundamentals(
        fcf_ttm=fcf_ttm,
        shares_outstanding=shares,
        operating_margin_history=operating_margin_history or [],
    )
    m = MarketData(price=price)
    return Security(ticker="TEST", fundamentals=f, market=m, macro=macro)


# ---------------------------------------------------------------------------
# RateSensitiveLens
# ---------------------------------------------------------------------------


def test_rate_sensitive_fallback_wacc_is_nine_percent():
    sec = _make_security()
    result = RateSensitiveLens().compute(sec)
    assert result.lens_name == "rate_sensitive"
    assert result.assumptions["wacc"] == pytest.approx(0.09)
    assert result.fair_value_low is not None
    assert result.fair_value_high is not None
    assert result.fair_value_low < result.fair_value_high


def test_rate_sensitive_macro_wacc():
    macro = MacroContext(real_rate_10y=0.02)
    sec = _make_security(macro=macro)
    result = RateSensitiveLens().compute(sec)
    assert result.assumptions["wacc"] == pytest.approx(0.075)


def test_rate_sensitive_null_real_rate_falls_back():
    # real_rate_10y is set to None explicitly — should use 9% fallback
    macro = MacroContext(real_rate_10y=None)
    sec = _make_security(macro=macro)
    result = RateSensitiveLens().compute(sec)
    assert result.assumptions["wacc"] == pytest.approx(0.09)


def test_rate_sensitive_higher_wacc_lowers_value():
    macro_low = MacroContext(real_rate_10y=0.00)  # WACC = 5.5%
    macro_high = MacroContext(real_rate_10y=0.03)  # WACC = 8.5%
    r_low = RateSensitiveLens().compute(_make_security(macro=macro_low))
    r_high = RateSensitiveLens().compute(_make_security(macro=macro_high))
    assert r_high.fair_value_high < r_low.fair_value_high


def test_rate_sensitive_missing_data():
    result = RateSensitiveLens().compute(Security(ticker="EMPTY"))
    assert result.confidence == 0.0
    assert result.fair_value_low is None


def test_rate_sensitive_confidence_lower_without_macro():
    with_macro = _make_security(macro=MacroContext(real_rate_10y=0.02))
    without_macro = _make_security()
    r_with = RateSensitiveLens().compute(with_macro)
    r_without = RateSensitiveLens().compute(without_macro)
    assert r_with.confidence > r_without.confidence


# ---------------------------------------------------------------------------
# PlatformCompounderLens
# ---------------------------------------------------------------------------


def test_platform_compounder_no_history_lower_confidence():
    sec = _make_security()
    result = PlatformCompounderLens().compute(sec)
    assert result.lens_name == "platform_compounder"
    assert result.confidence == pytest.approx(0.55)
    assert result.fair_value_low is not None
    assert result.fair_value_high is not None


def test_platform_compounder_with_expansion():
    # 2pp/yr expansion: most-recent-first [0.25, 0.23, 0.21, 0.19, 0.17, 0.15]
    sec = _make_security(operating_margin_history=[0.25, 0.23, 0.21, 0.19, 0.17, 0.15])
    result = PlatformCompounderLens().compute(sec)
    assert result.confidence == pytest.approx(0.80)
    assert result.assumptions["g_terminal"] > 0.025  # adjusted upward


def test_platform_compounder_high_expansion_adj():
    # > 3pp/yr: adj = +0.75%
    sec = _make_security(operating_margin_history=[0.30, 0.24, 0.18, 0.12, 0.06, 0.00])
    result = PlatformCompounderLens().compute(sec)
    assert result.assumptions["g_terminal"] == pytest.approx(0.025 + 0.0075)


def test_platform_compounder_terminal_capped_at_four():
    sec = _make_security(operating_margin_history=[0.30, 0.24, 0.18, 0.12, 0.06, 0.00])
    result = PlatformCompounderLens().compute(sec)
    assert result.assumptions["g_terminal"] <= 0.04


def test_platform_compounder_missing_data():
    result = PlatformCompounderLens().compute(Security(ticker="EMPTY"))
    assert result.confidence == 0.0
    assert result.fair_value_low is None


# ---------------------------------------------------------------------------
# ExpectationsDifficultyLens
# ---------------------------------------------------------------------------


def test_expectations_difficulty_never_has_price_target():
    sec = _make_security()
    result = ExpectationsDifficultyLens().compute(sec)
    assert result.lens_name == "expectations_difficulty"
    assert result.fair_value_low is None
    assert result.fair_value_high is None
    assert result.implied_move_pct is None


def test_expectations_difficulty_has_narrative():
    sec = _make_security()
    result = ExpectationsDifficultyLens().compute(sec)
    assert len(result.narrative) > 0


def test_expectations_difficulty_missing_data():
    result = ExpectationsDifficultyLens().compute(Security(ticker="EMPTY"))
    assert result.confidence == 0.0
    assert result.fair_value_low is None


# ---------------------------------------------------------------------------
# DamodaranEngine
# ---------------------------------------------------------------------------


def test_damodaran_base_produces_range():
    sec = _make_security()
    result = DamodaranEngine().compute(sec)
    assert result.lens_name == "damodaran_engine"
    assert result.fair_value_low is not None
    assert result.fair_value_high is not None
    assert result.fair_value_low <= result.fair_value_high


def test_damodaran_base_higher_growth_higher_value():
    sec_low = _make_security()
    sec_low.qualitative["forecast_growth"] = 0.05

    sec_high = _make_security()
    sec_high.qualitative["forecast_growth"] = 0.20

    r_low = DamodaranEngine().compute(sec_low)
    r_high = DamodaranEngine().compute(sec_high)
    assert r_high.fair_value_high > r_low.fair_value_high


def test_damodaran_base_uses_nine_percent_wacc():
    sec = _make_security()
    result = DamodaranEngine().compute(sec)
    assert result.assumptions["wacc"] == pytest.approx(0.09)


def test_damodaran_base_missing_data():
    result = DamodaranEngine().compute(Security(ticker="EMPTY"))
    assert result.confidence == 0.0
    assert result.fair_value_low is None


# ---------------------------------------------------------------------------
# synthesize_lenses
# ---------------------------------------------------------------------------


def test_synthesize_excludes_diagnostic_lens():
    pricing = LensResult(
        lens_name="damodaran_base",
        fair_value_low=90.0,
        fair_value_high=110.0,
        implied_move_pct=0.05,
        confidence=1.0,
        narrative="test",
    )
    diagnostic = LensResult(
        lens_name="expectations_difficulty",
        fair_value_low=None,
        fair_value_high=None,
        implied_move_pct=None,
        confidence=0.9,
        narrative="diagnostic",
    )
    result = synthesize_lenses([pricing, diagnostic])
    assert result.weighted_fair_value_low == pytest.approx(90.0)
    assert result.weighted_fair_value_high == pytest.approx(110.0)
    assert result.weighted_implied_move_pct == pytest.approx(0.05)


def test_synthesize_no_pricing_lenses():
    diagnostic = LensResult(
        lens_name="expectations_difficulty",
        fair_value_low=None,
        fair_value_high=None,
        implied_move_pct=None,
        confidence=0.5,
        narrative="diagnostic",
    )
    result = synthesize_lenses([diagnostic])
    assert result.weighted_fair_value_low is None
    assert result.weighted_fair_value_high is None
    assert result.weighted_implied_move_pct is None


def test_synthesize_confidence_weighted():
    low_conf = LensResult(
        lens_name="damodaran_base",
        fair_value_low=80.0,
        fair_value_high=100.0,
        implied_move_pct=-0.10,
        confidence=0.2,
        narrative="",
    )
    high_conf = LensResult(
        lens_name="rate_sensitive",
        fair_value_low=120.0,
        fair_value_high=140.0,
        implied_move_pct=0.30,
        confidence=0.8,
        narrative="",
    )
    result = synthesize_lenses([low_conf, high_conf])
    # Weighted low: (80*0.2 + 120*0.8) / 1.0 = 112.0
    assert result.weighted_fair_value_low == pytest.approx(112.0)
    # Weighted implied: (-0.10*0.2 + 0.30*0.8) / 1.0 = 0.22
    assert result.weighted_implied_move_pct == pytest.approx(0.22)


def test_synthesize_returns_all_narratives():
    lenses = [
        LensResult("a", 90.0, 110.0, 0.05, 0.8, "narrative-a"),
        LensResult("b", None, None, None, 0.5, "narrative-b"),
    ]
    result = synthesize_lenses(lenses)
    assert any("narrative-a" in n for n in result.narratives)
    assert any("narrative-b" in n for n in result.narratives)

