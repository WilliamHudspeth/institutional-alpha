"""Point-in-time fundamentals from SEC companyfacts.

Rule tests use small hand-written companyfacts documents (test inputs, not recorded
data). Fixture tests use real recorded filings and hand-computed expectations.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from iam.data.edgar import facts as ef_mod
from iam.data.edgar.client import EdgarClient, companyfacts_url
from iam.data.edgar.facts import (
    fundamentals_as_of,
    fundamentals_from_companyfacts,
    to_fundamentals,
)
from tests.edgar.helpers import FIXTURES, FixtureTransport, facts_doc, recorded_routes, row

REV = "Revenues"
D = date


def fy(val, year, filed, **kw):
    """A calendar fiscal-year flow fact (10-K)."""
    return row(val, f"{year}-12-31", filed, start=f"{year}-01-01", **kw)


def ytd(val, start, end, filed, fp="Q1"):
    return row(val, end, filed, start=start, form="10-Q", fp=fp, fy=int(end[:4]))


def inst(val, end, filed, form="10-K"):
    return row(val, end, filed, form=form)


# --------------------------------------------------------------------------- PIT
def test_fact_filed_after_the_date_is_invisible():
    doc = facts_doc({REV: [fy(1000, 2023, "2024-02-20")]})
    before = fundamentals_from_companyfacts(doc, D(2024, 2, 19))
    assert before.revenue_ttm.value is None
    assert before.revenue_ttm.reason
    on_day = fundamentals_from_companyfacts(doc, D(2024, 2, 20))
    assert on_day.revenue_ttm.value == 1000


def test_restatement_filed_before_the_date_wins():
    doc = facts_doc(
        {
            "NetIncomeLoss": [
                fy(100, 2023, "2024-02-20"),
                fy(80, 2023, "2024-09-10", form="10-K/A"),
            ]
        }
    )
    assert fundamentals_from_companyfacts(doc, D(2024, 12, 31)).net_income_ttm.value == 80


def test_original_is_used_if_the_restatement_was_filed_later():
    doc = facts_doc(
        {
            "NetIncomeLoss": [
                fy(100, 2023, "2024-02-20"),
                fy(80, 2023, "2024-09-10", form="10-K/A"),
            ]
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 6, 30)).net_income_ttm
    assert res.value == 100
    assert res.sources[0].filed == "2024-02-20"


def test_restatement_on_real_apple_filings():
    doc = json.loads((FIXTURES / "companyfacts_AAPL.json").read_text())
    # FY2009 net income: 5,704m in the original 10-K (2009-10-27), 8,235m restated in the
    # 10-K/A filed 2010-01-25.
    original = fundamentals_from_companyfacts(doc, D(2009, 12, 31)).net_income_ttm
    assert original.value == 5_704_000_000
    assert original.sources[0].form == "10-K"
    # After 2010-01-25 the Q1 FY10 10-Q is also visible, so the TTM adds its pieces; the FY
    # leg of that TTM must be the restated 10-K/A value.
    after = fundamentals_from_companyfacts(doc, D(2010, 2, 1)).net_income_ttm
    fy_leg = next(s for s in after.sources if s.role == "fy")
    assert fy_leg.value == 8_235_000_000
    assert fy_leg.form == "10-K/A"


def test_unaccepted_forms_are_ignored():
    doc = facts_doc({REV: [fy(1000, 2023, "2024-02-20", form="8-K")]})
    assert fundamentals_from_companyfacts(doc, D(2024, 12, 31)).revenue_ttm.value is None


# --------------------------------------------------------------------------- TTM
def ttm_doc(**extra):
    rows = [
        fy(1000, 2023, "2024-02-20"),
        ytd(300, "2024-01-01", "2024-03-31", "2024-05-01"),
        ytd(250, "2023-01-01", "2023-03-31", "2024-05-01"),
    ]
    return facts_doc({REV: rows, **extra})


def test_ttm_is_the_latest_fy_when_it_is_the_most_recent_period():
    res = fundamentals_from_companyfacts(ttm_doc(), D(2024, 4, 15)).revenue_ttm
    assert res.value == 1000
    assert res.method == "FY"


def test_ttm_from_10q_pieces_matches_hand_computation():
    res = fundamentals_from_companyfacts(ttm_doc(), D(2024, 5, 2)).revenue_ttm
    assert res.value == 1000 + 300 - 250  # FY + YTD(current) - YTD(prior year, same span)
    assert res.method == "FY + YTD - prior YTD"
    assert {s.role for s in res.sources} == {"fy", "ytd", "prior_ytd"}
    assert res.period_end == "2024-03-31"


def test_ttm_from_six_month_ytd():
    doc = facts_doc(
        {
            REV: [
                fy(1000, 2023, "2024-02-20"),
                ytd(700, "2024-01-01", "2024-06-30", "2024-08-01", fp="Q2"),
                ytd(600, "2023-01-01", "2023-06-30", "2024-08-01", fp="Q2"),
                ytd(300, "2024-04-01", "2024-06-30", "2024-08-01", fp="Q2"),  # 3-month: ignored
            ]
        }
    )
    assert fundamentals_from_companyfacts(doc, D(2024, 9, 1)).revenue_ttm.value == 1100


def test_missing_prior_year_ytd_gives_none_not_a_partial_sum():
    doc = facts_doc(
        {
            REV: [
                fy(1000, 2023, "2024-02-20"),
                ytd(300, "2024-01-01", "2024-03-31", "2024-05-01"),
            ]
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 5, 2)).revenue_ttm
    assert res.value is None
    assert "prior" in res.reason


def test_ytd_not_adjacent_to_the_latest_fy_gives_none():
    # FY2022 is the latest 10-K, but a 10-Q for 2024 exists: FY2023 is missing.
    doc = facts_doc(
        {
            REV: [
                fy(900, 2022, "2023-02-20"),
                ytd(300, "2024-01-01", "2024-03-31", "2024-05-01"),
                ytd(250, "2023-01-01", "2023-03-31", "2024-05-01"),
            ]
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 5, 2)).revenue_ttm
    assert res.value is None


def test_prior_ytd_must_be_filed_by_the_date():
    doc = facts_doc(
        {
            REV: [
                fy(1000, 2023, "2024-02-20"),
                ytd(300, "2024-01-01", "2024-03-31", "2024-05-01"),
                ytd(250, "2023-01-01", "2023-03-31", "2024-05-01"),
            ]
        }
    )
    # the date precedes the 10-Q: pieces filed later must not leak in
    assert fundamentals_from_companyfacts(doc, D(2024, 4, 30)).revenue_ttm.value == 1000


def test_stale_data_is_none():
    doc = facts_doc({REV: [fy(1000, 2019, "2020-02-20")]})
    res = fundamentals_from_companyfacts(doc, D(2024, 5, 2)).revenue_ttm
    assert res.value is None
    assert "stale" in res.reason


def test_revenue_tag_with_the_latest_period_wins_and_is_recorded():
    doc = facts_doc(
        {
            "SalesRevenueNet": [fy(500, 2017, "2018-02-20")],
            "RevenueFromContractWithCustomerExcludingAssessedTax": [fy(1000, 2023, "2024-02-20")],
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).revenue_ttm
    assert res.value == 1000
    assert res.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert res.sources[0].tag == res.tag


def test_revenue_history_most_recent_first_and_stops_at_a_gap():
    doc = facts_doc(
        {
            REV: [
                fy(700, 2019, "2020-02-20"),
                fy(800, 2021, "2022-02-20"),  # FY2020 missing: history must not skip over it
                fy(900, 2022, "2023-02-20"),
                fy(1000, 2023, "2024-02-20"),
            ]
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).revenue_history
    assert res.value == [1000, 900, 800]


# --------------------------------------------------------------------------- flows
def flows(**tags):
    return facts_doc({t: [fy(v, 2023, "2024-02-20")] for t, v in tags.items()})


def test_fcf_is_operating_cash_flow_minus_capex():
    doc = flows(
        NetCashProvidedByUsedInOperatingActivities=500,
        PaymentsToAcquirePropertyPlantAndEquipment=120,
    )
    r = fundamentals_from_companyfacts(doc, D(2024, 3, 1))
    assert r.fcf_ttm.value == 380
    assert r.capex_ttm.value == 120
    assert {s.tag for s in r.fcf_ttm.sources} == {
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    }


def test_fcf_is_none_when_capex_is_missing():
    doc = flows(NetCashProvidedByUsedInOperatingActivities=500)
    r = fundamentals_from_companyfacts(doc, D(2024, 3, 1))
    assert r.fcf_ttm.value is None
    assert "capex" in r.fcf_ttm.reason.lower()


def test_operating_margin_uses_the_same_period_for_both_legs():
    doc = facts_doc(
        {
            REV: [fy(1000, 2023, "2024-02-20")],
            "OperatingIncomeLoss": [fy(250, 2023, "2024-02-20")],
        }
    )
    assert fundamentals_from_companyfacts(doc, D(2024, 3, 1)).operating_margin.value == 0.25


def test_operating_margin_none_when_periods_differ():
    doc = facts_doc(
        {
            REV: [
                fy(1000, 2023, "2024-02-20"),
                ytd(300, "2024-01-01", "2024-03-31", "2024-05-01"),
                ytd(250, "2023-01-01", "2023-03-31", "2024-05-01"),
            ],
            "OperatingIncomeLoss": [fy(250, 2023, "2024-02-20")],  # no Q1 pieces
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 5, 2)).operating_margin
    assert res.value is None
    assert res.reason


def test_interest_expense_and_net_income_ttm():
    doc = flows(InterestExpense=40, NetIncomeLoss=90)
    r = fundamentals_from_companyfacts(doc, D(2024, 3, 1))
    assert r.interest_expense_ttm.value == 40
    assert r.net_income_ttm.value == 90


# --------------------------------------------------------------------------- balance sheet
def balance(date_end="2023-12-31", filed="2024-02-20", **tags):
    return facts_doc({t: [inst(v, date_end, filed)] for t, v in tags.items()})


def test_total_debt_never_uses_liabilities():
    doc = balance(Liabilities=9_999)
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).total_debt
    assert res.value is None
    assert "debt" in res.reason


def test_total_debt_noncurrent_plus_current_portion():
    doc = balance(LongTermDebtNoncurrent=700, LongTermDebtCurrent=100, Liabilities=9_999)
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).total_debt
    assert res.value == 800
    assert {s.tag for s in res.sources} == {"LongTermDebtNoncurrent", "LongTermDebtCurrent"}


def test_total_debt_noncurrent_plus_short_term_debt():
    doc = balance(LongTermDebtNoncurrent=700, DebtCurrent=60)
    assert fundamentals_from_companyfacts(doc, D(2024, 3, 1)).total_debt.value == 760


def test_total_debt_falls_back_to_long_term_debt_total():
    doc = balance(LongTermDebt=650)
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).total_debt
    assert res.value == 650
    assert res.tag == "LongTermDebt"


def test_total_debt_components_must_share_a_date():
    doc = facts_doc(
        {
            "LongTermDebtNoncurrent": [inst(700, "2023-12-31", "2024-02-20")],
            "LongTermDebtCurrent": [inst(100, "2023-09-30", "2023-11-01", form="10-Q")],
        }
    )
    assert fundamentals_from_companyfacts(doc, D(2024, 3, 1)).total_debt.value is None


def test_cash_and_equity_use_the_latest_balance_sheet_date():
    doc = facts_doc(
        {
            "CashAndCashEquivalentsAtCarryingValue": [
                inst(50, "2023-12-31", "2024-02-20"),
                inst(70, "2024-03-31", "2024-05-01", form="10-Q"),
            ],
            "StockholdersEquity": [inst(900, "2023-12-31", "2024-02-20")],
        }
    )
    r = fundamentals_from_companyfacts(doc, D(2024, 5, 2))
    assert r.cash_and_equivalents.value == 70
    assert r.equity.value == 900
    assert fundamentals_from_companyfacts(doc, D(2024, 4, 1)).cash_and_equivalents.value == 50


# --------------------------------------------------------------------------- shares
def test_shares_come_from_dei_first():
    doc = facts_doc(
        us_gaap_shares={
            "WeightedAverageNumberOfDilutedSharesOutstanding": [fy(111, 2023, "2024-02-20")]
        },
        dei={"EntityCommonStockSharesOutstanding": [inst(100, "2024-02-10", "2024-02-20")]},
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).shares_outstanding
    assert res.value == 100
    assert res.tag == "EntityCommonStockSharesOutstanding"
    assert res.sources[0].taxonomy == "dei"


def test_shares_fall_back_to_weighted_average_diluted_when_dei_is_missing():
    doc = facts_doc(
        us_gaap_shares={
            "WeightedAverageNumberOfDilutedSharesOutstanding": [fy(111, 2023, "2024-02-20")]
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).shares_outstanding
    assert res.value == 111
    assert res.tag == "WeightedAverageNumberOfDilutedSharesOutstanding"


def test_stale_dei_shares_defer_to_the_newer_weighted_average():
    doc = facts_doc(
        us_gaap_shares={
            "WeightedAverageNumberOfDilutedSharesOutstanding": [
                ytd(120, "2024-01-01", "2024-03-31", "2024-05-01"),
            ]
        },
        dei={"EntityCommonStockSharesOutstanding": [inst(100, "2023-02-10", "2023-02-20")]},
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 6, 1)).shares_outstanding
    assert res.value == 120
    assert res.tag == "WeightedAverageNumberOfDilutedSharesOutstanding"


def test_shares_missing_everywhere_is_none_with_reason():
    res = fundamentals_from_companyfacts(facts_doc({REV: []}), D(2024, 3, 1)).shares_outstanding
    assert res.value is None
    assert res.reason


# --------------------------------------------------------------------------- tax and ROIC
def tax_doc(tax, pretax):
    return facts_doc(
        {
            "IncomeTaxExpenseBenefit": [fy(tax, 2023, "2024-02-20")],
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": [
                fy(pretax, 2023, "2024-02-20")
            ],
        }
    )


def test_effective_tax_rate_is_tax_over_pretax():
    res = fundamentals_from_companyfacts(tax_doc(20, 100), D(2024, 3, 1)).effective_tax_rate
    assert res.value == pytest.approx(0.2)
    assert {s.role for s in res.sources} == {"tax", "pretax"}


def test_pretax_fallback_tag_is_used():
    doc = facts_doc(
        {
            "IncomeTaxExpenseBenefit": [fy(30, 2023, "2024-02-20")],
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": [
                fy(100, 2023, "2024-02-20")
            ],
        }
    )
    assert fundamentals_from_companyfacts(doc, D(2024, 3, 1)).effective_tax_rate.value == (
        pytest.approx(0.3)
    )


@pytest.mark.parametrize(
    ("tax", "pretax"),
    [(10, 0), (10, -50), (-5, 100), (70, 100)],
    ids=["zero-pretax", "negative-pretax", "negative-ratio", "ratio-above-0.6"],
)
def test_effective_tax_is_none_when_not_meaningful(tax, pretax):
    res = fundamentals_from_companyfacts(tax_doc(tax, pretax), D(2024, 3, 1)).effective_tax_rate
    assert res.value is None
    assert res.reason


def test_roic_history_formula_and_provenance():
    pre = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
    doc = facts_doc(
        {
            "OperatingIncomeLoss": [fy(1000, 2023, "2024-02-20")],
            "IncomeTaxExpenseBenefit": [fy(200, 2023, "2024-02-20")],
            pre: [fy(1000, 2023, "2024-02-20")],
            "StockholdersEquity": [inst(3000, "2023-12-31", "2024-02-20")],
            "LongTermDebt": [inst(1500, "2023-12-31", "2024-02-20")],
            "CashAndCashEquivalentsAtCarryingValue": [inst(500, "2023-12-31", "2024-02-20")],
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).roic_history
    # NOPAT = 1000 * (1 - 0.2) = 800; invested capital = 3000 + 1500 - 500 = 4000
    assert res.value == [pytest.approx(0.2)]
    assert "invested capital" in res.method
    assert res.sources


def test_roic_history_includes_fiscal_years_older_than_the_staleness_window():
    pre = "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
    years = {2021: 500, 2022: 800, 2023: 1000}
    doc = facts_doc(
        {
            "OperatingIncomeLoss": [fy(v, y, f"{y + 1}-02-20") for y, v in years.items()],
            "IncomeTaxExpenseBenefit": [fy(v * 0.2, y, f"{y + 1}-02-20") for y, v in years.items()],
            pre: [fy(v, y, f"{y + 1}-02-20") for y, v in years.items()],
            "StockholdersEquity": [inst(3000, f"{y}-12-31", f"{y + 1}-02-20") for y in years],
            "LongTermDebt": [inst(1500, f"{y}-12-31", f"{y + 1}-02-20") for y in years],
            "CashAndCashEquivalentsAtCarryingValue": [
                inst(500, f"{y}-12-31", f"{y + 1}-02-20") for y in years
            ],
        }
    )
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).roic_history
    # invested capital 4000 each year; NOPAT = op income x 0.8
    assert res.value == [pytest.approx(0.2), pytest.approx(0.16), pytest.approx(0.1)]


def test_roic_skips_years_with_missing_inputs():
    doc = facts_doc({"OperatingIncomeLoss": [fy(1000, 2023, "2024-02-20")]})
    res = fundamentals_from_companyfacts(doc, D(2024, 3, 1)).roic_history
    assert res.value is None
    assert res.reason


# --------------------------------------------------------------------------- real fixtures
def real(name):
    return json.loads((FIXTURES / f"companyfacts_{name}.json").read_text())


M = 1_000_000


def test_aapl_2026_06_30_values_match_hand_computation():
    r = fundamentals_from_companyfacts(real("AAPL"), D(2026, 6, 30))
    # Q3 FY26 10-Q was filed 2026-07-31, after the date: latest is the Q2 FY26 10-Q (2026-05-01).
    assert r.revenue_ttm.value == (416_161 + 254_940 - 219_659) * M
    assert r.revenue_ttm.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert r.revenue_ttm.period_end == "2026-03-28"
    assert r.net_income_ttm.value == (112_010 + 71_675 - 61_110) * M
    assert r.operating_margin.value == pytest.approx(
        (133_050 + 86_737 - 72_421) / (416_161 + 254_940 - 219_659)
    )
    assert r.capex_ttm.value == (12_715 + 4_344 - 6_011) * M
    assert r.fcf_ttm.value == (111_482 + 82_627 - 53_887 - (12_715 + 4_344 - 6_011)) * M
    assert r.total_debt.value == (74_404 + 8_310) * M  # NoncurrentDebt + current portion
    assert r.total_debt.value != 264_591 * M  # never Liabilities
    assert r.cash_and_equivalents.value == 45_572 * M
    assert r.equity.value == 106_491 * M
    assert r.shares_outstanding.value == 14_687_356_000
    assert r.shares_outstanding.tag == "EntityCommonStockSharesOutstanding"
    assert r.effective_tax_rate.value == pytest.approx(20_719 / 132_729)
    assert r.interest_expense_ttm.value is None  # Apple stopped tagging InterestExpense (FY2023)
    assert "stale" in r.interest_expense_ttm.reason
    assert r.revenue_history.value[:3] == [416_161 * M, 391_035 * M, 383_285 * M]
    assert len(r.revenue_history.value) >= 5
    for field in ef_mod.FIELD_NAMES:
        fv = getattr(r, field)
        assert fv.value is not None or fv.reason, field
        if fv.value is not None and field != "roic_history":
            assert fv.sources, field
            for s in fv.sources:
                assert s.accn and s.form and s.filed and s.end and s.tag
                assert s.filed <= "2026-06-30"


def test_blk_2026_06_30_values_match_hand_computation():
    r = fundamentals_from_companyfacts(real("BLK_new"), D(2026, 6, 30))
    assert r.revenue_ttm.value == (24_216 + 6_698 - 5_276) * M
    assert r.net_income_ttm.value == (5_553 + 2_212 - 1_510) * M
    assert r.fcf_ttm.value == ((3_927 - 980 + 1_128) - (375 + 106 - 78)) * M
    assert r.total_debt.value == 12_749 * M
    assert r.total_debt.tag == "LongTermDebt"
    assert r.cash_and_equivalents.value == 9_841 * M
    assert r.equity.value == 56_688 * M
    # dei shares (filed 2025-05-07) are over a year old: the newer diluted weighted average
    # of the latest quarter is used instead, and says so.
    assert r.shares_outstanding.tag == "WeightedAverageNumberOfDilutedSharesOutstanding"
    assert r.shares_outstanding.value == 165_001_107
    assert r.interest_expense_ttm.value is None
    assert "InterestExpense" in r.interest_expense_ttm.reason


def test_blk_old_entity_stops_at_its_last_filing():
    r = fundamentals_from_companyfacts(real("BLK_old"), D(2024, 11, 5))
    # last 10-Q of the old entity: Q2 2024 (filed 2024-08-06); TTM = FY23 + 6M24 - 6M23
    assert r.revenue_ttm.period_end == "2024-06-30"
    assert r.revenue_ttm.sources[0].filed <= "2024-11-05"


# --------------------------------------------------------------------------- wiring
def test_fundamentals_as_of_goes_through_the_client_without_network(tmp_path):
    transport = FixtureTransport(recorded_routes())
    client = EdgarClient(tmp_path / "c", transport=transport, sleep=lambda s: None)
    r = fundamentals_as_of(320193, D(2026, 6, 30), client=client)
    assert r.cik == 320193
    assert r.entity_name
    assert r.as_of == D(2026, 6, 30)
    assert r.revenue_ttm.value is not None
    assert transport.calls == [companyfacts_url(320193)]


def test_fundamentals_as_of_accepts_iso_strings(tmp_path):
    transport = FixtureTransport(recorded_routes())
    client = EdgarClient(tmp_path / "c", transport=transport, sleep=lambda s: None)
    assert fundamentals_as_of(320193, "2026-06-30", client=client).as_of == D(2026, 6, 30)


def test_to_fundamentals_maps_fields_and_keeps_provenance():
    r = fundamentals_from_companyfacts(real("AAPL"), D(2026, 6, 30))
    f, prov = to_fundamentals(r)
    assert f.revenue_ttm == r.revenue_ttm.value
    assert f.net_income_ttm == r.net_income_ttm.value
    assert f.fcf_ttm == r.fcf_ttm.value
    assert f.total_debt == r.total_debt.value
    assert f.shares_outstanding == r.shares_outstanding.value
    assert f.revenue_history == r.revenue_history.value
    assert f.interest_expense_ttm is None  # missing stays None: no default
    p = prov["revenue_ttm"]
    assert p["tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert p["sources"][0]["accn"]
    assert p["sources"][0]["filed"]
    assert prov["interest_expense_ttm"]["reason"]
    assert prov["interest_expense_ttm"]["value"] is None
    assert prov["_meta"]["as_of"] == "2026-06-30"
    assert prov["_meta"]["cik"] == 320193
    json.dumps(prov)  # provenance is JSON-serialisable


def test_to_fundamentals_leaves_unsourced_fields_unset():
    f, _ = to_fundamentals(fundamentals_from_companyfacts(facts_doc({REV: []}), D(2024, 3, 1)))
    assert f.revenue_ttm is None
    assert f.revenue_history == []
    assert f.gross_margin is None  # not an EDGAR field in the facts parser
    assert f.ebitda_ttm is None
