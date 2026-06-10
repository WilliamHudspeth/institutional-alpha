"""Tests for the Business Reality Engine (Seven-Engine architecture, Engine #3).

These assert *theory-driven directional invariants* (monotonicity, bounds,
classification, graceful degradation) rather than exact magic numbers — the
same style as the lens/factor tests. The point is that the reasoning behaves
the way an analyst would expect, not that a particular float is produced.
"""

from __future__ import annotations

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.lenses.business_reality_lens import BusinessRealityLens
from iam.reasoning.business_reality import (
    BusinessReality,
    BusinessRealityEngine,
    RevenueQuality,
    _cagr,
    _coefficient_of_variation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _security(
    *,
    ticker: str = "TEST",
    sector: str | None = None,
    fundamentals: Fundamentals | None = None,
    qualitative: dict | None = None,
) -> Security:
    return Security(
        ticker=ticker,
        sector=sector,
        fundamentals=fundamentals or Fundamentals(),
        market=MarketData(price=100.0),
        qualitative=qualitative or {},
    )


def _assess(**kwargs) -> BusinessReality:
    return BusinessRealityEngine().assess(_security(**kwargs))


# A high-quality, durable software-like business.
_DURABLE = Fundamentals(
    revenue_ttm=1000.0,
    revenue_history=[1000.0, 900.0, 810.0, 730.0, 660.0],  # smooth ~11% CAGR
    gross_margin=0.80,
    operating_margin=0.35,
    fcf_ttm=300.0,
    fcf_history=[300.0, 270.0, 250.0, 230.0, 210.0],  # smooth
    net_income_ttm=250.0,
    ebitda_ttm=400.0,
    roic_history=[0.30, 0.31, 0.29, 0.30, 0.32],  # high + stable
    incremental_roic=0.30,
    total_debt=50.0,
    cash_and_equivalents=400.0,  # net cash
    sbc_ttm=20.0,  # 2% of revenue
    shares_outstanding=100.0,
    shares_outstanding_history=[98.0, 99.0, 100.0, 101.0, 102.0],  # buying back
)

# A fragile, cyclical, capital-hungry business.
_FRAGILE = Fundamentals(
    revenue_ttm=1000.0,
    revenue_history=[1000.0, 600.0, 1400.0, 500.0, 1200.0],  # very lumpy
    gross_margin=0.25,
    operating_margin=0.03,  # high fixed-cost intensity
    fcf_ttm=-100.0,  # burning cash
    fcf_history=[-100.0, 50.0, -200.0, 30.0, -150.0],
    net_income_ttm=10.0,
    ebitda_ttm=80.0,
    roic_history=[0.05, 0.12, 0.02, 0.15, 0.01],  # low + volatile
    incremental_roic=0.02,
    total_debt=900.0,
    cash_and_equivalents=50.0,  # heavily levered
    sbc_ttm=150.0,  # 15% of revenue
    shares_outstanding=140.0,
    shares_outstanding_history=[140.0, 125.0, 112.0, 100.0, 90.0],  # heavy dilution
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_cagr_basic():
    # most-recent-first: 121 -> 100 over 2 periods == 10% CAGR
    assert _cagr([121.0, 110.0, 100.0]) == pytest.approx(0.10)


def test_cagr_guards():
    assert _cagr([]) is None
    assert _cagr([100.0]) is None
    assert _cagr([100.0, 0.0]) is None  # oldest non-positive
    assert _cagr([100.0, -50.0]) is None


def test_coefficient_of_variation_guards():
    assert _coefficient_of_variation([]) is None
    assert _coefficient_of_variation([5.0]) is None
    assert _coefficient_of_variation([0.0, 0.0]) is None  # zero mean
    assert _coefficient_of_variation([10.0, 10.0]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Revenue-quality classification
# ---------------------------------------------------------------------------


def test_revenue_quality_recurring_from_mix():
    br = _assess(qualitative={"recurring_revenue_mix": 0.85})
    assert br.revenue_quality is RevenueQuality.RECURRING


def test_revenue_quality_regulated_sector():
    br = _assess(sector="Utilities")
    assert br.revenue_quality is RevenueQuality.REGULATED


def test_revenue_quality_cyclical_from_volatility():
    f = Fundamentals(revenue_history=[1000.0, 500.0, 1400.0, 400.0])
    br = _assess(fundamentals=f)
    assert br.revenue_quality is RevenueQuality.CYCLICAL


def test_revenue_quality_cyclical_from_sector():
    br = _assess(sector="Energy")
    assert br.revenue_quality is RevenueQuality.CYCLICAL


def test_revenue_quality_recurring_from_stable_high_margin():
    f = Fundamentals(
        gross_margin=0.80,
        revenue_history=[1000.0, 960.0, 925.0, 900.0],  # very smooth, low CV
    )
    br = _assess(fundamentals=f)
    assert br.revenue_quality is RevenueQuality.RECURRING


def test_revenue_quality_unknown_when_no_signals():
    br = _assess()
    assert br.revenue_quality is RevenueQuality.UNKNOWN
    assert br.revenue_quality_confidence <= 0.3


def test_revenue_mix_beats_cyclical_sector():
    # An explicit recurring mix should override a cyclical sector label.
    br = _assess(sector="Energy", qualitative={"recurring_revenue_mix": 0.9})
    assert br.revenue_quality is RevenueQuality.RECURRING


# ---------------------------------------------------------------------------
# Cash-flow durability
# ---------------------------------------------------------------------------


def test_negative_fcf_is_capital_markets_dependent():
    f = Fundamentals(fcf_ttm=-50.0, gross_margin=0.6, operating_margin=0.2)
    br = _assess(fundamentals=f)
    assert br.cashflow_durability_label == "capital_markets_dependent"
    assert br.cashflow_durability < 0.35


def test_durable_business_has_stable_cashflows():
    br = BusinessRealityEngine().assess(_security(fundamentals=_DURABLE))
    assert br.cashflow_durability_label == "stable"
    assert br.cashflow_durability >= 0.6


def test_durable_beats_fragile_on_durability():
    durable = BusinessRealityEngine().assess(_security(fundamentals=_DURABLE))
    fragile = BusinessRealityEngine().assess(_security(fundamentals=_FRAGILE))
    assert durable.cashflow_durability > fragile.cashflow_durability


def test_high_fixed_cost_intensity_lowers_durability():
    # Same gross margin, different operating margin => different fixed-cost load.
    low_fixed = Fundamentals(
        gross_margin=0.60,
        operating_margin=0.50,  # little opex => low fixed-cost intensity
        fcf_history=[100.0, 98.0, 96.0],
    )
    high_fixed = Fundamentals(
        gross_margin=0.60,
        operating_margin=0.05,  # huge opex => high fixed-cost intensity
        fcf_history=[100.0, 98.0, 96.0],
    )
    br_low = _assess(fundamentals=low_fixed)
    br_high = _assess(fundamentals=high_fixed)
    assert br_low.cashflow_durability > br_high.cashflow_durability


# ---------------------------------------------------------------------------
# Growth quality
# ---------------------------------------------------------------------------


def test_organic_growth_beats_dilutive_growth():
    organic = Fundamentals(
        revenue_history=[1500.0, 1300.0, 1100.0, 1000.0],  # ~14% CAGR
        shares_outstanding_history=[98.0, 99.0, 100.0, 100.0],  # flat/shrinking
        incremental_roic=0.25,
    )
    dilutive = Fundamentals(
        revenue_history=[1500.0, 1300.0, 1100.0, 1000.0],  # same top-line growth
        shares_outstanding_history=[150.0, 130.0, 110.0, 100.0],  # funded by issuance
        incremental_roic=0.03,
    )
    br_organic = _assess(fundamentals=organic)
    br_dilutive = _assess(fundamentals=dilutive)
    assert br_organic.growth_quality > br_dilutive.growth_quality


def test_growth_decomposition_populated():
    f = Fundamentals(
        revenue_history=[1210.0, 1100.0, 1000.0],
        shares_outstanding_history=[100.0, 100.0, 100.0],
        incremental_roic=0.20,
    )
    br = _assess(fundamentals=f)
    assert "revenue_cagr" in br.growth_decomposition
    assert "organic_spread" in br.growth_decomposition
    assert br.growth_decomposition["revenue_cagr"] == pytest.approx(0.10)


def test_tam_realism_lifts_growth_quality():
    base = Fundamentals(
        revenue_history=[1100.0, 1050.0, 1000.0],
        shares_outstanding_history=[100.0, 100.0, 100.0],
        incremental_roic=0.12,
    )
    low_tam = _assess(fundamentals=base, qualitative={"tam_remaining": 0.0})
    high_tam = _assess(fundamentals=base, qualitative={"tam_remaining": 1.0})
    assert high_tam.growth_quality > low_tam.growth_quality


# ---------------------------------------------------------------------------
# Capital allocation
# ---------------------------------------------------------------------------


def test_buybacks_score_disciplined():
    f = Fundamentals(
        shares_outstanding_history=[90.0, 95.0, 100.0],  # shrinking share count
        incremental_roic=0.25,
        ebitda_ttm=400.0,
        total_debt=50.0,
        cash_and_equivalents=300.0,
        revenue_ttm=1000.0,
        sbc_ttm=10.0,
    )
    br = _assess(fundamentals=f)
    assert br.capital_allocation > 0
    assert br.capital_allocation_label == "disciplined"


def test_heavy_dilution_scores_destructive():
    f = Fundamentals(
        shares_outstanding_history=[150.0, 120.0, 100.0],  # heavy issuance
        incremental_roic=0.01,
        ebitda_ttm=50.0,
        total_debt=900.0,
        cash_and_equivalents=20.0,
        revenue_ttm=1000.0,
        sbc_ttm=200.0,
    )
    br = _assess(fundamentals=f)
    assert br.capital_allocation < 0
    assert br.capital_allocation_label == "destructive"


# ---------------------------------------------------------------------------
# ROIC durability (excess-return fade)
# ---------------------------------------------------------------------------


def test_stable_high_roic_is_durable():
    f = Fundamentals(roic_history=[0.30, 0.31, 0.29, 0.30], incremental_roic=0.30)
    br = _assess(fundamentals=f)
    assert br.roic_durability >= 0.6


def test_volatile_low_roic_is_not_durable():
    stable = Fundamentals(roic_history=[0.30, 0.31, 0.29, 0.30], incremental_roic=0.30)
    volatile = Fundamentals(roic_history=[0.05, 0.20, 0.02, 0.18], incremental_roic=0.03)
    br_stable = _assess(fundamentals=stable)
    br_volatile = _assess(fundamentals=volatile)
    assert br_stable.roic_durability > br_volatile.roic_durability


def test_roic_fade_signal_lowers_durability():
    # Same high, stable history; only incremental ROIC differs (fade signal).
    no_fade = Fundamentals(roic_history=[0.30, 0.30, 0.30], incremental_roic=0.30)
    fading = Fundamentals(roic_history=[0.30, 0.30, 0.30], incremental_roic=0.05)
    assert (
        _assess(fundamentals=no_fade).roic_durability > _assess(fundamentals=fading).roic_durability
    )


def test_short_roic_history_is_neutral_prior():
    f = Fundamentals(roic_history=[0.30])
    br = _assess(fundamentals=f)
    assert br.roic_durability == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Fragility / robustness synthesis
# ---------------------------------------------------------------------------


def test_fragile_business_is_more_fragile_than_durable():
    durable = BusinessRealityEngine().assess(_security(fundamentals=_DURABLE))
    fragile = BusinessRealityEngine().assess(_security(fundamentals=_FRAGILE))
    assert fragile.fragility > durable.fragility
    assert durable.robustness > fragile.robustness


def test_robustness_and_fragility_sum_to_one():
    for f in (_DURABLE, _FRAGILE):
        br = BusinessRealityEngine().assess(_security(fundamentals=f))
        assert br.robustness + br.fragility == pytest.approx(1.0)


def test_all_scores_within_bounds():
    for f in (_DURABLE, _FRAGILE, Fundamentals()):
        br = BusinessRealityEngine().assess(_security(fundamentals=f))
        assert 0.0 <= br.cashflow_durability <= 1.0
        assert 0.0 <= br.roic_durability <= 1.0
        assert 0.0 <= br.fragility <= 1.0
        assert 0.0 <= br.robustness <= 1.0
        assert -1.0 <= br.growth_quality <= 1.0
        assert -1.0 <= br.capital_allocation <= 1.0
        assert 0.0 <= br.confidence <= 1.0


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_empty_security_does_not_crash():
    br = BusinessRealityEngine().assess(Security(ticker="EMPTY"))
    assert br.ticker == "EMPTY"
    assert br.revenue_quality is RevenueQuality.UNKNOWN
    assert br.confidence < 0.7  # low data => low confidence


def test_more_data_raises_confidence():
    sparse = BusinessRealityEngine().assess(Security(ticker="A"))
    rich = BusinessRealityEngine().assess(_security(fundamentals=_DURABLE))
    assert rich.confidence > sparse.confidence


def test_narrative_is_descriptive():
    br = BusinessRealityEngine().assess(_security(ticker="NVDA", fundamentals=_DURABLE))
    assert "NVDA" in br.narrative
    assert br.revenue_quality.value in br.narrative


# ---------------------------------------------------------------------------
# Diagnostic lens adapter
# ---------------------------------------------------------------------------


def test_lens_is_diagnostic():
    result = BusinessRealityLens().compute(_security(fundamentals=_DURABLE))
    assert result.lens_name == "business_reality"
    # Diagnostic => no fair value, skipped by synthesize_lenses.
    assert result.fair_value_low is None
    assert result.fair_value_high is None
    assert result.implied_move_pct is None
    assert 0.0 <= result.confidence <= 1.0
    assert "fragility" in result.assumptions


def test_lens_skipped_by_synthesis():
    from iam.lenses.synthesis import synthesize_lenses

    # A diagnostic lens must not perturb the synthesis weighted move.
    br_lens = BusinessRealityLens().compute(_security(fundamentals=_DURABLE))
    synth = synthesize_lenses([br_lens])
    assert synth.weighted_implied_move_pct is None


def test_lens_does_not_mutate_security():
    sec = _security(fundamentals=_DURABLE, qualitative={"recurring_revenue_mix": 0.9})
    before = dict(sec.qualitative)
    BusinessRealityLens().compute(sec)
    assert sec.qualitative == before
