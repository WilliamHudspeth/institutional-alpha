"""Loss-making inputs must not score as cheap, strong or safe (audit T3 findings)."""

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.factors.expectations import ExpectationsDifficultyFactor
from iam.factors.penalties import FragilityPenalty
from iam.factors.quality import QualityFactor
from iam.factors.relative_value import RelativeValueFactor


def sec(fundamentals=None, market=None):
    return Security(
        ticker="X",
        fundamentals=fundamentals or Fundamentals(),
        market=market or MarketData(price=10.0),
    )


# ------------------------------------------------------------------ quality: balance sheet
def test_negative_ebitda_with_net_debt_is_the_weakest_balance_sheet():
    s = sec(Fundamentals(ebitda_ttm=-20.0, total_debt=100.0, cash_and_equivalents=0.0))
    c = QualityFactor().compute(s)
    assert c.components["balance_sheet_strength"] == -1.0
    assert any("Negative EBITDA" in n for n in c.notes)


def test_negative_ebitda_with_net_cash_is_skipped():
    s = sec(Fundamentals(ebitda_ttm=-20.0, total_debt=0.0, cash_and_equivalents=100.0))
    c = QualityFactor().compute(s)
    assert "balance_sheet_strength" not in c.components


def test_positive_ebitda_scoring_is_unchanged():
    s = sec(Fundamentals(ebitda_ttm=50.0, total_debt=100.0, cash_and_equivalents=0.0))
    c = QualityFactor().compute(s)
    # net debt / EBITDA = 2 -> -(2 - 1) / 2
    assert c.components["balance_sheet_strength"] == pytest.approx(-0.5)


# ------------------------------------------------------------------ relative value
def test_negative_ev_ebitda_is_not_cheaper_than_peers():
    s = sec(market=MarketData(price=10.0, ev_ebitda=-6.0, sector_ev_ebitda_median=12.0))
    c = RelativeValueFactor().compute(s)
    assert "ev_ebitda_vs_sector" not in c.components
    assert any("EV/EBITDA not positive" in n for n in c.notes)


def test_positive_ev_ebitda_still_compared():
    s = sec(market=MarketData(price=10.0, ev_ebitda=6.0, sector_ev_ebitda_median=12.0))
    c = RelativeValueFactor().compute(s)
    assert c.components["ev_ebitda_vs_sector"] == pytest.approx(0.5)


def test_negative_pe_is_not_the_cheapest_percentile():
    s = sec(market=MarketData(price=10.0, pe_ttm=-10.0, pe_history=[15.0 + i for i in range(30)]))
    c = RelativeValueFactor().compute(s)
    assert "pe_own_percentile" not in c.components
    assert any("P/E not positive" in n for n in c.notes)


def test_loss_years_in_pe_history_are_ignored():
    history = [10.0 + i for i in range(24)] + [-5.0] * 10  # 24 positive, 10 loss years
    s = sec(market=MarketData(price=10.0, pe_ttm=21.5, pe_history=history))
    c = RelativeValueFactor().compute(s)
    # 12 of the 24 positive P/Es (10..21) sit below 21.5 -> 50th percentile -> 0
    assert c.components["pe_own_percentile"] == pytest.approx(0.0)


# ------------------------------------------------------------------ expectations: margin
def test_negative_margin_gets_no_margin_difficulty_score():
    s = sec(Fundamentals(operating_margin=-0.10, operating_margin_history=[0.20, 0.15]))
    c = ExpectationsDifficultyFactor().compute(s)
    assert "margin_difficulty" not in c.components


def test_positive_margin_difficulty_unchanged():
    s = sec(Fundamentals(operating_margin=0.10, operating_margin_history=[0.20, 0.15]))
    c = ExpectationsDifficultyFactor().compute(s)
    # ratio 0.5 -> -(0.5 - 0.9) x 2 = 0.8
    assert c.components["margin_difficulty"] == pytest.approx(0.8)


# ------------------------------------------------------------------ fragility penalty
def test_negative_pe_is_maximum_fragility():
    s = sec(
        Fundamentals(revenue_history=[120.0, 110.0, 100.0]),
        MarketData(price=10.0, pe_ttm=-25.0),
    )
    c = FragilityPenalty().compute(s)
    assert c.value == 1.0
    assert c.confidence == pytest.approx(0.6)


def test_negative_latest_revenue_does_not_crash():
    s = sec(Fundamentals(revenue_history=[-5.0, 10.0, 20.0]), MarketData(price=10.0, pe_ttm=20.0))
    c = FragilityPenalty().compute(s)
    assert 0.0 <= c.value <= 1.0
    assert any("assuming 10% growth" in n for n in c.notes)


def test_positive_pe_fragility_unchanged():
    s = sec(
        Fundamentals(revenue_history=[121.0, 110.0, 100.0]),  # 10% CAGR
        MarketData(price=10.0, pe_ttm=40.0),
    )
    c = FragilityPenalty().compute(s)
    # PEG 40 / 10 = 4 -> (4 - 1) / 3 = 1.0
    assert c.value == pytest.approx(1.0)
    assert c.components["peg_like"] == pytest.approx(4.0)
