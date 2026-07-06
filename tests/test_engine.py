"""End-to-end smoke and behavior tests for the scoring engine."""

from iam import Fundamentals, MarketData, Security, score
from iam.data.security import MacroContext
from iam.factors.base import FactorContribution


def test_empty_security_returns_neutral_score():
    """A security with no data should score near zero with low confidence."""
    result = score(Security(ticker="EMPTY"))
    assert -0.3 < result.composite < 0.3
    # Every factor should have run
    assert len(result.factor_breakdown) == 10
    assert len(result.penalties) == 3
    # Confidence should be reduced for data-less factors
    avg_conf = sum(c.confidence for c in result.factor_breakdown.values()) / 10
    assert avg_conf < 0.8


def test_high_quality_inputs_produce_positive_quality():
    sec = Security(
        ticker="HQ",
        fundamentals=Fundamentals(
            roic_history=[0.30, 0.29, 0.31, 0.30, 0.28],  # high + stable
            gross_margin_history=[0.75, 0.74, 0.76, 0.75, 0.74],
            operating_margin_history=[0.30, 0.29, 0.30, 0.28, 0.29],
            fcf_ttm=1000.0,
            net_income_ttm=900.0,
            shares_outstanding_history=[100, 102, 104, 106, 108],
            ebitda_ttm=1500.0,
            total_debt=200.0,
            cash_and_equivalents=800.0,
            incremental_roic=0.25,
        ),
    )
    result = score(sec)
    q = result.factor_breakdown["quality"]
    assert q.value > 0.3, f"Expected positive quality, got {q.value}"


def test_fragility_penalizes_high_pe_low_growth():
    sec = Security(
        ticker="FRAG",
        fundamentals=Fundamentals(revenue_history=[105, 104, 103, 102, 100]),  # ~1% CAGR
        market=MarketData(pe_ttm=80.0),
    )
    result = score(sec)
    frag = result.penalties["fragility_penalty"]
    assert frag.value > 0.5, f"Expected high fragility penalty, got {frag.value}"


def test_low_pe_with_growth_has_low_fragility():
    sec = Security(
        ticker="CHEAP",
        fundamentals=Fundamentals(revenue_history=[150, 130, 115, 105, 100]),  # ~10% CAGR
        market=MarketData(pe_ttm=12.0),
    )
    result = score(sec)
    frag = result.penalties["fragility_penalty"]
    assert frag.value < 0.2, f"Expected low fragility, got {frag.value}"


def test_leverage_penalty_fires_on_high_net_debt():
    sec = Security(
        ticker="LEV",
        fundamentals=Fundamentals(
            total_debt=5000.0,
            cash_and_equivalents=200.0,
            ebitda_ttm=800.0,  # net debt/EBITDA = 6
            interest_expense_ttm=400.0,  # 2x coverage
        ),
    )
    result = score(sec)
    lev = result.penalties["leverage_penalty"]
    assert lev.value > 0.5


def test_components_are_populated():
    sec = Security(
        ticker="DECOMP",
        fundamentals=Fundamentals(
            roic_history=[0.20, 0.19, 0.21, 0.20, 0.18],
            operating_margin_history=[0.20, 0.19, 0.20, 0.19, 0.18],
        ),
    )
    result = score(sec)
    quality = result.factor_breakdown["quality"]
    assert "roic_persistence" in quality.components


def test_custom_weights_change_composite():
    sec = Security(
        ticker="WTS",
        fundamentals=Fundamentals(
            roic_history=[0.30, 0.30, 0.30, 0.30, 0.30],
            operating_margin_history=[0.30, 0.30, 0.30, 0.30, 0.30],
            fcf_ttm=1000.0,
            net_income_ttm=1000.0,
        ),
    )
    default_result = score(sec)
    # Crank quality weight all the way up
    custom = score(
        sec,
        weights={
            "quality": 1.0,
            "expectations_difficulty": 0,
            "intrinsic_value": 0,
            "relative_value": 0,
            "sentiment": 0,
            "reflexivity": 0,
            "reinvestment_runway": 0,
            "macro_regime": 0,
            "crowding": 0,
            "earnings_quality": 0,
        },
    )
    assert custom.composite != default_result.composite


def test_regime_aware_weighting_does_not_crash_with_macro_context():
    """Regression test: security.macro used to construct MacroConditions with
    kwargs (rate_10y/rate_2y/vix) that don't exist on the dataclass, raising
    TypeError on every call. It was silently swallowed by a bare `except
    Exception: pass`, so regime-aware factor weighting never actually ran.
    Fixed by MacroConditions.from_context(); this pins the fix.
    """
    sec = Security(
        ticker="REGIME",
        fundamentals=Fundamentals(roic_history=[0.20] * 5),
        macro=MacroContext(
            real_rate_trend="rising",
            pmi_direction="contracting",
            credit_spread_hy=0.04,
        ),
    )
    result = score(sec)
    # Should compute cleanly, not just avoid raising.
    assert result.composite is not None
    assert len(result.factor_breakdown) == 10


def test_macro_context_from_context_classifies_stagflation():
    """Direct test of the fixed mapping (MacroConditions.from_context) feeding
    MacroRegimeClassifier — this is the exact chain that used to raise
    TypeError. Rising rate + contracting PMI must classify as stagflation.
    """
    from iam.data.macro import MacroConditions
    from iam.pipeline.macro_regimes import MacroRegime, MacroRegimeClassifier

    ctx = MacroContext(real_rate_trend="rising", pmi_direction="contracting")
    cond = MacroConditions.from_context(ctx)
    assessment = MacroRegimeClassifier().classify(cond)
    assert assessment.regime == MacroRegime.STAGFLATION


def test_macro_context_from_context_handles_none_and_missing_fields():
    """No MacroContext, or one with unset trend fields, must degrade to the
    neutral defaults rather than raise."""
    from iam.data.macro import MacroConditions
    from iam.pipeline.macro_regimes import MacroRegime, MacroRegimeClassifier

    assert MacroConditions.from_context(None) == MacroConditions()

    ctx = MacroContext()  # all fields unset
    assessment = MacroRegimeClassifier().classify(MacroConditions.from_context(ctx))
    assert assessment.regime == MacroRegime.NEUTRAL


def test_explain_runs_and_returns_string():
    result = score(Security(ticker="X"))
    text = result.explain()
    assert "Composite score" in text
    assert "X" in text


def test_all_factors_return_factor_contribution():
    result = score(Security(ticker="X"))
    for name, c in result.factor_breakdown.items():
        assert isinstance(c, FactorContribution)
        assert -1.0 <= c.value <= 1.0
        assert 0.0 <= c.confidence <= 1.0
    for name, p in result.penalties.items():
        assert 0.0 <= p.value <= 1.0
