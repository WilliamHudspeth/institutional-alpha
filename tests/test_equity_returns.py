"""Company ROE for the FCFE reinvestment charge (replaces the flat 15%)."""

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.engine.market_implied import MarketImpliedEngine
from iam.valuation.equity_returns import MARKET_ROE, ROE_BOUNDS, company_roe
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions
from iam.valuation.reverse_dcf import _present_value_path, _present_value_two_stage


def sec(qualitative=None, **f):
    return Security(
        ticker="X",
        fundamentals=Fundamentals(**f),
        market=MarketData(price=100.0, beta=1.0),
        qualitative=qualitative or {},
    )


# ------------------------------------------------------------------ company_roe
def test_normalised_roe_sums_over_beginning_equity():
    s = sec(net_income_history=[120.0, 110.0, 100.0], book_equity_history=[1100, 1000, 950, 900])
    er = company_roe(s)
    assert er.roe == pytest.approx(330 / (1000 + 950 + 900))
    assert er.source == "normalised ROE over 3 years"
    assert not er.user


def test_buyback_inflated_roe_is_capped():
    s = sec(net_income_history=[100.0] * 3, book_equity_history=[100.0] * 4)  # ROE 100%
    er = company_roe(s)
    assert er.roe == ROE_BOUNDS[1]
    assert er.raw == pytest.approx(1.0)


def test_negative_equity_falls_back_to_trailing_then_market():
    neg = sec(net_income_history=[100.0] * 3, book_equity_history=[-50.0] * 4)
    assert company_roe(neg).source.startswith("market ROE default")
    trailing = sec(net_income_ttm=30.0, book_equity=200.0)
    assert company_roe(trailing).roe == pytest.approx(0.15)
    assert company_roe(trailing).source == "trailing ROE"


def test_low_roe_is_floored():
    s = sec(net_income_ttm=1.0, book_equity=1000.0)
    assert company_roe(s).roe == ROE_BOUNDS[0]


def test_losses_fall_back_to_market_roe():
    s = sec(net_income_history=[-100.0, 20.0, 20.0], book_equity_history=[1000.0] * 4)
    assert company_roe(s).roe == MARKET_ROE


def test_user_roe_overrides_and_stays_flat():
    s = sec(
        qualitative={"forecast_roe": 0.25},
        net_income_history=[100.0] * 3,
        book_equity_history=[1000.0] * 4,
    )
    er = company_roe(s)
    assert er.user and er.roe == 0.25
    assert er.path(10) == [0.25] * 10
    assert er.terminal() == 0.25


def test_path_holds_then_fades_to_market():
    s = sec(net_income_history=[350.0] * 5, book_equity_history=[1000.0] * 6)  # 35%
    path = company_roe(s).path(years=10, hold=5)
    assert path[:5] == [pytest.approx(0.35)] * 5
    assert path[-1] == pytest.approx(MARKET_ROE)
    assert path[5] == pytest.approx(0.35 + (0.15 - 0.35) / 5)


# ------------------------------------------------------------------ PV functions
def test_terminal_roe_defaults_to_the_same_rate():
    a = _present_value_two_stage(1.0, 0.08, 10, 0.025, 0.09, 0.2)
    b = _present_value_two_stage(1.0, 0.08, 10, 0.025, 0.09, 0.2, 0.2)
    assert a == pytest.approx(b)


def test_higher_roe_means_less_reinvestment_and_more_value():
    low = _present_value_two_stage(1.0, 0.08, 10, 0.025, 0.09, 0.15, 0.15)
    high = _present_value_two_stage(1.0, 0.08, 10, 0.025, 0.09, 0.40, 0.15)
    assert high > low


def test_path_pv_with_flat_roe_list_matches_scalar():
    path = [0.06] * 10
    assert _present_value_path(1.0, path, 0.025, 0.09, [0.2] * 10) == pytest.approx(
        _present_value_path(1.0, path, 0.025, 0.09, 0.2)
    )


def test_path_pv_rejects_mismatched_roe_path():
    with pytest.raises(ValueError):
        _present_value_path(1.0, [0.05] * 10, 0.025, 0.09, [0.2] * 9)


# ------------------------------------------------------------------ stages
def _priced(**f):
    base = dict(
        net_income_ttm=10.0,
        fcf_ttm=10.0,
        shares_outstanding=1.0,
        net_income_history=[100.0] * 5,
        book_equity_history=[250.0] * 6,  # ROE 40%
    )
    base.update(f)
    return sec(qualitative={"forecast_discount_rate": 0.09}, **base)


def test_stage3_uses_company_roe_and_reports_it():
    res = FCFEDCF().compute(_priced())
    assert res.assumptions["roe"] == pytest.approx(0.40)
    assert res.assumptions["roe_terminal"] == pytest.approx(MARKET_ROE)
    assert any("normalised ROE over 5 years" in n for n in res.notes)


def test_stage3_high_roe_firm_is_worth_more_than_with_flat_15pct():
    s = _priced()
    company = FCFEDCF().compute(s).fair_value_per_share
    flat = (
        FCFEDCF()
        .compute(_priced(net_income_history=[], book_equity_history=[]))
        .fair_value_per_share
    )
    assert company > flat


def test_stage3_explicit_assumptions_keep_their_roe():
    a = FCFEAssumptions(high_growth=0.06, discount_rate=0.09, roe=0.12)
    res = FCFEDCF().compute(_priced(), assumptions=a)
    assert res.assumptions["roe"] == pytest.approx(0.12)
    assert res.assumptions["roe_terminal"] == pytest.approx(0.12)


def test_stage1_high_roe_firm_needs_less_implied_growth():
    # P/E 30: the price implies growth (in decline the ROE effect runs the other way)
    company, flat = _priced(), _priced(net_income_history=[], book_equity_history=[])
    company.market.price = flat.market.price = 300.0
    c = MarketImpliedEngine().compute(company)
    f = MarketImpliedEngine().compute(flat)
    assert 0 < c.implied.implied_revenue_growth < f.implied.implied_revenue_growth
    assert any("ROE 40.0%" in n for n in c.notes)
