"""Normalised fundamental growth (Damodaran's growth lectures) and the histories it needs."""

import math
import statistics
from datetime import date as D

import pytest

import iam.growth.profile as profile_mod
from iam.data.edgar.facts import fundamentals_from_companyfacts, to_fundamentals
from iam.data.security import Fundamentals, Security
from iam.growth.estimators import MODEL_ERROR, normalised_fundamental
from iam.growth.profile import build_growth_profile
from tests.edgar.helpers import facts_doc, row

PRE = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"


def op_firm(nopat, reinv, ic, sector="Industrials", **kw):
    f = Fundamentals(
        revenue_ttm=10_000.0,
        nopat_history=nopat,
        reinvestment_history=reinv,
        invested_capital_history=ic,
        **kw,
    )
    return Security(ticker="X", sector=sector, fundamentals=f)


def bank(ni, payout, be):
    f = Fundamentals(
        revenue_ttm=10_000.0,
        net_income_history=ni,
        equity_payout_history=payout,
        book_equity_history=be,
    )
    return Security(ticker="B", sector="Financial Services", fundamentals=f)


# ----------------------------------------------------------------------- operating firms
def test_operating_formula_matches_hand_computation():
    nopat = [110.0, 100.0, 95.0, 90.0, 85.0]
    reinv = [55.0, 50.0, 47.0, 45.0, 42.0]
    ic = [1150.0, 1100.0, 1000.0, 950.0, 900.0, 850.0]  # one more entry: beginning capital
    est = normalised_fundamental(op_firm(nopat, reinv, ic))
    assert est.ok
    rr = sum(reinv) / sum(nopat)
    roics = [nopat[i] / ic[i + 1] for i in range(5)]
    roic_bar = statistics.median(roics)
    g_reinv = rr * roic_bar
    g_eff = ((roic_bar / roics[0]) ** (1 / 3) - 1) * 3 / 5
    assert est.value == pytest.approx(g_reinv + g_eff)
    assert est.inputs["reinvestment_rate"] == pytest.approx(rr)
    assert est.inputs["roic_normalised"] == pytest.approx(roic_bar)
    assert est.inputs["roic_now"] == pytest.approx(roics[0])
    assert est.inputs["g_reinvestment"] == pytest.approx(g_reinv)
    assert est.inputs["g_efficiency"] == pytest.approx(g_eff)
    assert est.inputs["n_years"] == 5
    assert est.horizon_years == 5
    assert est.method == "normalised_fundamental"


def test_uses_at_most_five_years():
    nopat = [100.0] * 8
    reinv = [50.0] * 8
    ic = [1000.0] * 9
    est = normalised_fundamental(op_firm(nopat, reinv, ic))
    assert est.inputs["n_years"] == 5
    assert est.value == pytest.approx(0.5 * 0.1)  # steady state: no efficiency term


def test_needs_three_years_with_beginning_capital():
    # three NOPAT years but only three capital points: two usable years
    est = normalised_fundamental(op_firm([100.0] * 3, [50.0] * 3, [1000.0] * 3))
    assert not est.ok
    assert est.reason


def test_cumulative_nopat_not_positive_is_not_usable():
    est = normalised_fundamental(op_firm([-50.0, 20.0, 20.0], [10.0] * 3, [1000.0] * 4))
    assert not est.ok
    assert "NOPAT" in est.reason


def test_reinvestment_rate_is_clamped_to_one():
    est = normalised_fundamental(op_firm([100.0] * 4, [300.0] * 4, [1000.0] * 5))
    assert est.inputs["reinvestment_rate"] == pytest.approx(1.0)
    assert est.value == pytest.approx(0.1)  # can never exceed ROIC without new capital


def test_negative_reinvestment_shrinks_the_firm():
    est = normalised_fundamental(op_firm([100.0] * 4, [-30.0] * 4, [1000.0] * 5))
    assert est.value == pytest.approx(-0.3 * 0.1)


def test_depressed_current_roic_adds_finite_efficiency_growth():
    # ROIC 8% now vs 10% normal: existing capital earns its way back over three years
    est = normalised_fundamental(op_firm([80.0, 100.0, 100.0, 100.0], [0.0] * 4, [1000.0] * 5))
    assert est.inputs["g_efficiency"] > 0
    assert est.inputs["g_efficiency"] == pytest.approx(((0.1 / 0.08) ** (1 / 3) - 1) * 3 / 5)


def test_peak_current_roic_mean_reverts_down():
    est = normalised_fundamental(op_firm([200.0, 100.0, 100.0, 100.0], [0.0] * 4, [1000.0] * 5))
    assert est.inputs["g_efficiency"] < 0


def test_efficiency_term_is_clamped():
    est = normalised_fundamental(op_firm([5.0, 100.0, 100.0, 100.0], [0.0] * 4, [1000.0] * 5))
    assert est.inputs["g_efficiency"] == pytest.approx(0.15 * 3 / 5)


def test_current_roic_not_positive_drops_efficiency_term():
    est = normalised_fundamental(op_firm([-10.0, 100.0, 100.0, 100.0], [0.0] * 4, [1000.0] * 5))
    assert est.ok
    assert est.inputs["g_efficiency"] == 0.0
    assert any("efficiency" in n for n in est.notes)


def test_low_normalised_roic_is_flagged():
    est = normalised_fundamental(op_firm([50.0] * 4, [25.0] * 4, [1000.0] * 5))
    assert any("cost of capital" in n for n in est.notes)


def test_value_is_bounded():
    est = normalised_fundamental(op_firm([600.0] * 4, [600.0] * 4, [1000.0] * 5))
    assert est.value <= 0.40


def test_shipped_mode_and_calibrated_error():
    assert profile_mod.DCF_GROWTH_MODE == "replace_fundamental"
    assert MODEL_ERROR["normalised_fundamental"] == pytest.approx(0.12)


def test_law2_prefers_the_normalised_reinvestment_rate():
    from iam.growth.apply import ensure_growth_profile

    sec = steady_firm()
    ensure_growth_profile(sec)
    assert sec.qualitative["reinvestment_rate"] == pytest.approx(0.5)
    assert sec.qualitative["reinvestment_rate_source"] == "growth engine"


def test_std_error_grows_with_roic_dispersion():
    steady = normalised_fundamental(op_firm([100.0] * 4, [50.0] * 4, [1000.0] * 5))
    noisy = normalised_fundamental(op_firm([100.0, 60.0, 140.0, 100.0], [50.0] * 4, [1000.0] * 5))
    assert steady.std_error == pytest.approx(MODEL_ERROR["normalised_fundamental"])
    assert noisy.std_error > steady.std_error
    assert 0.1 <= noisy.confidence <= 1.0


def test_missing_histories_are_not_usable():
    est = normalised_fundamental(
        Security(ticker="X", sector="Technology", fundamentals=Fundamentals())
    )
    assert not est.ok
    assert est.value is None
    assert est.confidence == 0.0


# ----------------------------------------------------------------------- financials
def test_financial_uses_retention_net_of_buybacks_times_roe():
    ni = [120.0, 110.0, 100.0]
    payout = [60.0, 55.0, 50.0]
    be = [1100.0, 1000.0, 950.0, 900.0]
    est = normalised_fundamental(bank(ni, payout, be))
    roe = sum(ni) / sum(be[1:4])
    retention = 1 - sum(payout) / sum(ni)
    assert est.value == pytest.approx(retention * roe)
    assert est.inputs["retention"] == pytest.approx(retention)
    assert est.inputs["roe_normalised"] == pytest.approx(roe)


def test_financial_growth_never_exceeds_roe():
    est = normalised_fundamental(bank([100.0] * 3, [-50.0] * 3, [1000.0] * 4))
    assert est.inputs["retention"] == pytest.approx(1.0)
    assert est.value == pytest.approx(0.1)


def test_financial_losses_are_not_usable():
    est = normalised_fundamental(bank([-100.0, 20.0, 20.0], [0.0] * 3, [1000.0] * 4))
    assert not est.ok


# ----------------------------------------------------------------------- profile wiring
def steady_firm():
    return op_firm(
        [100.0] * 5,
        [50.0] * 5,
        [1000.0] * 6,
        revenue_history=[10_000.0, 9_500.0, 9_000.0, 8_600.0, 8_200.0],
    )


def test_profile_reports_the_estimate():
    p = build_growth_profile(steady_firm())
    assert p.estimates["normalised_fundamental"].ok


def test_blend_mode_adds_it_to_the_dcf(monkeypatch):
    monkeypatch.setattr(profile_mod, "DCF_GROWTH_MODE", "blend")
    p = build_growth_profile(steady_firm())
    assert "normalised_fundamental" in p.dcf.sources
    assert "historical_revenue" in p.dcf.sources


def test_replace_mode_drops_single_year_fundamental(monkeypatch):
    monkeypatch.setattr(profile_mod, "DCF_GROWTH_MODE", "replace_fundamental")
    p = build_growth_profile(steady_firm())
    assert "normalised_fundamental" in p.dcf.sources
    assert "fundamental" not in p.dcf.sources


def test_anchor_mode_uses_only_it(monkeypatch):
    monkeypatch.setattr(profile_mod, "DCF_GROWTH_MODE", "anchor")
    p = build_growth_profile(steady_firm())
    assert p.dcf.sources == ("normalised_fundamental",)
    # still shrunk toward the size base rate
    assert p.dcf.shrinkage_weight is not None and p.dcf.shrinkage_weight < 1.0


def test_anchor_mode_falls_back_when_unusable(monkeypatch):
    monkeypatch.setattr(profile_mod, "DCF_GROWTH_MODE", "anchor")
    sec = Security(
        ticker="X",
        sector="Technology",
        fundamentals=Fundamentals(revenue_ttm=1e9, revenue_history=[1e9, 9e8, 8e8, 7e8]),
    )
    p = build_growth_profile(sec)
    assert "historical_revenue" in p.dcf.sources


def test_relative_and_expectations_rates_are_unchanged_by_mode(monkeypatch):
    sec = steady_firm()
    monkeypatch.setattr(profile_mod, "DCF_GROWTH_MODE", "blend")
    a = build_growth_profile(sec)
    monkeypatch.setattr(profile_mod, "DCF_GROWTH_MODE", "anchor")
    b = build_growth_profile(sec)
    assert a.relative_revenue.value == b.relative_revenue.value
    assert a.relative_eps.value == b.relative_eps.value


# ----------------------------------------------------------------------- EDGAR histories
def fy(val, year, filed):
    return row(val, f"{year}-12-31", filed, start=f"{year}-01-01", fy=year)


def inst(val, end, filed):
    return row(val, end, filed)


def edgar_doc(years):
    g = {
        "OperatingIncomeLoss": [],
        "IncomeTaxExpenseBenefit": [],
        PRE: [],
        "PaymentsToAcquirePropertyPlantAndEquipment": [],
        "DepreciationDepletionAndAmortization": [],
        "PaymentsToAcquireBusinessesNetOfCashAcquired": [],
        "IncreaseDecreaseInOperatingCapital": [],
        "NetIncomeLoss": [],
        "PaymentsOfDividends": [],
        "PaymentsForRepurchaseOfCommonStock": [],
        "StockholdersEquity": [],
        "LongTermDebt": [],
        "CashAndCashEquivalentsAtCarryingValue": [],
    }
    for y in years:
        filed = f"{y + 1}-02-20"
        k = y - years[0]
        g["OperatingIncomeLoss"].append(fy(1000 + 100 * k, y, filed))
        g["IncomeTaxExpenseBenefit"].append(fy((1000 + 100 * k) * 0.2, y, filed))
        g[PRE].append(fy(1000 + 100 * k, y, filed))
        g["PaymentsToAcquirePropertyPlantAndEquipment"].append(fy(300, y, filed))
        g["DepreciationDepletionAndAmortization"].append(fy(200, y, filed))
        g["PaymentsToAcquireBusinessesNetOfCashAcquired"].append(fy(50, y, filed))
        g["IncreaseDecreaseInOperatingCapital"].append(fy(25, y, filed))
        g["NetIncomeLoss"].append(fy(700 + 70 * k, y, filed))
        g["PaymentsOfDividends"].append(fy(100, y, filed))
        g["PaymentsForRepurchaseOfCommonStock"].append(fy(150, y, filed))
        g["StockholdersEquity"].append(inst(3000 + 100 * k, f"{y}-12-31", filed))
        g["LongTermDebt"].append(inst(1500, f"{y}-12-31", filed))
        g["CashAndCashEquivalentsAtCarryingValue"].append(inst(500, f"{y}-12-31", filed))
    return facts_doc(g)


def test_edgar_histories_are_aligned_and_most_recent_first():
    ef = fundamentals_from_companyfacts(edgar_doc([2020, 2021, 2022, 2023]), D(2024, 3, 1))
    fnd, prov = to_fundamentals(ef)
    assert fnd.nopat_history == [pytest.approx(v * 0.8) for v in (1300, 1200, 1100, 1000)]
    assert fnd.reinvestment_history == [pytest.approx(300 - 200 + 50 + 25)] * 4
    assert fnd.invested_capital_history == [
        pytest.approx(3000 + 100 * k + 1000) for k in (3, 2, 1, 0)
    ]
    assert fnd.net_income_history == [pytest.approx(700 + 70 * k) for k in (3, 2, 1, 0)]
    assert fnd.equity_payout_history == [pytest.approx(250)] * 4
    assert fnd.book_equity_history == [pytest.approx(3000 + 100 * k) for k in (3, 2, 1, 0)]
    assert "reinvestment_history" in prov


def test_edgar_histories_are_point_in_time():
    doc = edgar_doc([2020, 2021, 2022, 2023])
    ef = fundamentals_from_companyfacts(doc, D(2023, 3, 1))  # FY2023 10-K not filed yet
    fnd, _ = to_fundamentals(ef)
    assert len(fnd.nopat_history) == 3
    assert fnd.nopat_history[0] == pytest.approx(1200 * 0.8)


def test_edgar_optional_flows_default_to_zero():
    doc = edgar_doc([2021, 2022, 2023])
    for tag in (
        "PaymentsToAcquireBusinessesNetOfCashAcquired",
        "IncreaseDecreaseInOperatingCapital",
        "PaymentsOfDividends",
        "PaymentsForRepurchaseOfCommonStock",
    ):
        del doc["facts"]["us-gaap"][tag]
    fnd, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    assert fnd.reinvestment_history == [pytest.approx(100.0)] * 3
    assert fnd.equity_payout_history == [0.0] * 3


def test_edgar_missing_capex_gives_no_reinvestment_history():
    doc = edgar_doc([2021, 2022, 2023])
    del doc["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
    fnd, prov = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    assert fnd.reinvestment_history == []
    assert fnd.nopat_history == []
    assert prov["reinvestment_history"]["reason"]


def test_edgar_to_estimator_end_to_end():
    doc = edgar_doc([2018, 2019, 2020, 2021, 2022, 2023])
    fnd, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    est = normalised_fundamental(Security(ticker="E", sector="Industrials", fundamentals=fnd))
    assert est.ok
    assert math.isfinite(est.value)


# ----------------------------------------------------------------------- yfinance histories
def test_yfinance_annual_histories_signs_and_alignment():
    import pandas as pd

    from iam.data.providers.yfinance_adapter import annual_histories

    cols = [pd.Timestamp(f"{y}-12-31") for y in (2024, 2023, 2022, 2021)]
    fin = pd.DataFrame(
        {
            c: {"Operating Income": oi, "Tax Rate For Calcs": 0.2, "Net Income": ni}
            for c, oi, ni in zip(cols, (1300, 1200, 1100, 1000), (900, 800, 700, 600), strict=True)
        }
    )
    cf = pd.DataFrame(
        {
            c: {
                "Capital Expenditure": -300.0,
                "Depreciation And Amortization": 200.0,
                "Purchase Of Business": -50.0,
                "Change In Working Capital": -25.0,  # cash used
                "Cash Dividends Paid": -100.0,
                "Repurchase Of Capital Stock": -150.0,
            }
            for c in cols
        }
    )
    bs = pd.DataFrame(
        {
            c: {"Stockholders Equity": eq, "Total Debt": 1500.0, "Cash And Cash Equivalents": 500.0}
            for c, eq in zip(cols, (3300, 3200, 3100, 3000), strict=True)
        }
    )
    h = annual_histories(fin, bs, cf, tax_fallback=0.21)
    assert h["nopat_history"] == [pytest.approx(v * 0.8) for v in (1300, 1200, 1100, 1000)]
    assert h["reinvestment_history"] == [pytest.approx(300 - 200 + 50 + 25)] * 4
    assert h["invested_capital_history"] == [
        pytest.approx(e + 1000) for e in (3300, 3200, 3100, 3000)
    ]
    assert h["net_income_history"] == [900.0, 800.0, 700.0, 600.0]
    assert h["equity_payout_history"] == [pytest.approx(250.0)] * 4
    assert h["book_equity_history"] == [3300.0, 3200.0, 3100.0, 3000.0]


def test_yfinance_annual_histories_tolerate_missing_frames():
    import pandas as pd

    from iam.data.providers.yfinance_adapter import annual_histories

    h = annual_histories(pd.DataFrame(), None, pd.DataFrame(), tax_fallback=None)
    assert all(v == [] for v in h.values())
    assert set(h) == {
        "nopat_history",
        "reinvestment_history",
        "invested_capital_history",
        "net_income_history",
        "equity_payout_history",
        "book_equity_history",
    }


def test_edgar_falls_back_to_pretax_plus_interest_and_other_cash_tag():
    doc = edgar_doc([2021, 2022, 2023])
    gaap = doc["facts"]["us-gaap"]
    del gaap["OperatingIncomeLoss"]
    gaap["InterestExpense"] = {
        "units": {"USD": [fy(100, y, f"{y + 1}-02-20") for y in (2021, 2022, 2023)]}
    }
    gaap["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"] = gaap.pop(
        "CashAndCashEquivalentsAtCarryingValue"
    )
    fnd, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    # EBIT = pretax (1200 in 2023) + interest 100; tax 240 / pretax 1200 = 20%
    assert fnd.nopat_history[0] == pytest.approx(1300 * 0.8)
    assert fnd.invested_capital_history[0] == pytest.approx(3200 + 1500 - 500)


def test_edgar_loss_year_is_taxed_at_zero_and_no_debt_line_means_debt_free():
    doc = edgar_doc([2021, 2022, 2023])
    gaap = doc["facts"]["us-gaap"]
    gaap["OperatingIncomeLoss"]["units"]["USD"][-1]["val"] = -400
    gaap[PRE]["units"]["USD"][-1]["val"] = -400
    gaap["IncomeTaxExpenseBenefit"]["units"]["USD"][-1]["val"] = -50
    del gaap["LongTermDebt"]
    fnd, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    assert len(fnd.nopat_history) == 3
    assert fnd.nopat_history[0] == pytest.approx(-400.0)
    assert fnd.invested_capital_history[0] == pytest.approx(3200 - 500)


# ----------------------------------------------------------------------- R&D capitalisation
def test_capitalise_rd_straight_line_three_years():
    from iam.data.rd import capitalise_rd

    out = capitalise_rd([300.0, 200.0, 100.0, 0.0])
    # year 0: amortisation (200 + 100 + 0) / 3 = 100; asset 300 + 200 x 2/3 + 100 x 1/3
    assert out[0] == (pytest.approx(200.0), pytest.approx(300 + 200 * 2 / 3 + 100 / 3))
    # earliest year: nothing before the series, so no amortisation
    assert out[3] == (pytest.approx(0.0), pytest.approx(0.0))
    assert out[2] == (pytest.approx(100.0), pytest.approx(100.0))


def test_capitalise_rd_steady_spend_has_no_income_effect():
    from iam.data.rd import capitalise_rd

    delta, asset = capitalise_rd([90.0] * 6)[0]
    assert delta == pytest.approx(0.0)
    assert asset == pytest.approx(90 * (1 + 2 / 3 + 1 / 3))


def rd_doc(years, rd_by_year):
    doc = edgar_doc(years)
    doc["facts"]["us-gaap"]["ResearchAndDevelopmentExpense"] = {
        "units": {"USD": [fy(v, y, f"{y + 1}-02-20") for y, v in rd_by_year.items()]}
    }
    return doc


def test_edgar_steady_rd_adds_the_research_asset_only():
    doc = rd_doc([2020, 2021, 2022, 2023], {y: 90.0 for y in range(2017, 2024)})
    fnd, prov = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    assert fnd.nopat_history == [pytest.approx(v * 0.8) for v in (1300, 1200, 1100, 1000)]
    assert fnd.reinvestment_history == [pytest.approx(175.0)] * 4
    assert fnd.invested_capital_history == [
        pytest.approx(4000 + 100 * k + 180) for k in (3, 2, 1, 0)
    ]
    assert "R&D capitalised" in prov["nopat_history"]["method"]
    assert any("rd_minus" in s["role"] for s in prov["nopat_history"]["sources"])


def test_edgar_growing_rd_raises_nopat_and_reinvestment():
    rd = {2020: 60.0, 2021: 90.0, 2022: 120.0, 2023: 150.0}
    doc = rd_doc([2021, 2022, 2023], rd)
    fnd, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    # 2023: amortisation (120 + 90 + 60) / 3 = 90, so R&D - amortisation = 60
    assert fnd.nopat_history[0] == pytest.approx(1200 * 0.8 + 60)
    assert fnd.reinvestment_history[0] == pytest.approx(175 + 60)
    assert fnd.invested_capital_history[0] == pytest.approx(4200 + 150 + 120 * 2 / 3 + 90 / 3)


def test_edgar_rd_gap_year_counts_as_zero_and_is_point_in_time():
    doc = rd_doc([2021, 2022, 2023], {2020: 90.0, 2022: 90.0, 2023: 90.0})
    fnd, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2024, 3, 1)))
    # 2023: amortisation (90 + 0 + 90) / 3 = 60; asset 90 + 90 x 2/3 + 0
    assert fnd.nopat_history[0] == pytest.approx(1200 * 0.8 + 30)
    assert fnd.invested_capital_history[0] == pytest.approx(4200 + 90 + 60)
    before, _ = to_fundamentals(fundamentals_from_companyfacts(doc, D(2023, 3, 1)))
    assert len(before.nopat_history) == 2  # FY2023 R&D not yet filed either


def test_firms_without_rd_are_unchanged():
    fnd, _ = to_fundamentals(
        fundamentals_from_companyfacts(edgar_doc([2021, 2022, 2023]), D(2024, 3, 1))
    )
    assert fnd.invested_capital_history[0] == pytest.approx(4200.0)


def test_yfinance_capitalises_rd():
    import pandas as pd

    from iam.data.providers.yfinance_adapter import annual_histories

    cols = [pd.Timestamp(f"{y}-12-31") for y in (2024, 2023, 2022, 2021)]
    fin = pd.DataFrame(
        {
            c: {
                "Operating Income": 1000.0,
                "Tax Rate For Calcs": 0.2,
                "Research And Development": rd,
            }
            for c, rd in zip(cols, (300.0, 200.0, 100.0, 0.0), strict=True)
        }
    )
    cf = pd.DataFrame(
        {c: {"Capital Expenditure": -300.0, "Depreciation And Amortization": 200.0} for c in cols}
    )
    bs = pd.DataFrame(
        {
            c: {
                "Stockholders Equity": 3000.0,
                "Total Debt": 1500.0,
                "Cash And Cash Equivalents": 500.0,
            }
            for c in cols
        }
    )
    h = annual_histories(fin, bs, cf, tax_fallback=0.21)
    assert h["nopat_history"][0] == pytest.approx(800 + 200)
    assert h["reinvestment_history"][0] == pytest.approx(100 + 200)
    assert h["invested_capital_history"][0] == pytest.approx(4000 + 300 + 200 * 2 / 3 + 100 / 3)
