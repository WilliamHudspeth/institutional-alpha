"""Effective tax rate in the data model (Part B).

Damodaran's convention: the EFFECTIVE rate (Tax Provision / Pretax Income) feeds the
multiples regression's TaxRate; relevering and the after-tax cost of debt keep the
MARGINAL rate even when an effective rate exists. Offline: yfinance is faked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
import yfinance as yf

from iam.data import ground_truth
from iam.data.providers import yfinance_adapter as ya
from iam.data.providers.yfinance_adapter import YFinanceAdapter
from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.country_tax import company_marginal_tax


def _statement(**rows: float) -> pd.DataFrame:
    """Income statement, most recent fiscal year first, one older column behind it."""
    latest, older = pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")
    return pd.DataFrame(
        {latest: list(rows.values()), older: [v * 0.5 for v in rows.values()]},
        index=list(rows),
    )


def _fetch(monkeypatch, financials: pd.DataFrame, ticker: str = "TAXT") -> Security:
    class MockTicker:
        def __init__(self, _ticker):
            self.info = {"currentPrice": 100.0, "marketCap": 1000.0, "totalDebt": 230.0}
            self.financials = financials
            self.cashflow = pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", MockTicker)
    monkeypatch.setattr(ya, "_get_cached_data", lambda _t: None)
    monkeypatch.setattr(ya, "_save_cached_data", lambda _t, _d: None)
    return YFinanceAdapter().fetch(ticker)


# ------------------------------------------------------------------ B1 / B2
def test_fundamentals_has_an_optional_effective_tax_rate():
    assert Fundamentals().effective_tax_rate is None
    assert Fundamentals(effective_tax_rate=0.2).effective_tax_rate == 0.2


def test_tax_provision_over_pretax_income(monkeypatch):
    sec = _fetch(monkeypatch, _statement(**{"Tax Provision": 2.4, "Pretax Income": 10.0}))
    assert sec.fundamentals.effective_tax_rate == pytest.approx(0.24)
    assert not any("effective_tax_rate" in d for d in sec.qualitative.get("defaulted_inputs", []))


def test_income_tax_expense_label_is_accepted(monkeypatch):
    sec = _fetch(monkeypatch, _statement(**{"Income Tax Expense": 1.5, "Pretax Income": 10.0}))
    assert sec.fundamentals.effective_tax_rate == pytest.approx(0.15)


def test_latest_fiscal_year_is_used_even_if_columns_are_oldest_first(monkeypatch):
    df = pd.DataFrame(
        {pd.Timestamp("2023-12-31"): [9.0, 10.0], pd.Timestamp("2025-12-31"): [2.0, 10.0]},
        index=["Tax Provision", "Pretax Income"],
    )
    sec = _fetch(monkeypatch, df)
    assert sec.fundamentals.effective_tax_rate == pytest.approx(0.20)


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ({"Pretax Income": 10.0}, "tax provision"),
        ({"Tax Provision": 2.4}, "pretax income"),
        ({"Tax Provision": 2.4, "Pretax Income": -10.0}, "pretax income"),
        ({"Tax Provision": 2.4, "Pretax Income": 0.0}, "pretax income"),
        ({"Tax Provision": 9.0, "Pretax Income": 10.0}, "outside"),  # 90%
        ({"Tax Provision": -1.0, "Pretax Income": 10.0}, "outside"),  # negative
    ],
)
def test_missing_negative_or_absurd_values_give_none_and_a_reason(monkeypatch, rows, reason):
    sec = _fetch(monkeypatch, _statement(**rows))
    assert sec.fundamentals.effective_tax_rate is None
    notes = [d for d in sec.qualitative["defaulted_inputs"] if d.startswith("effective_tax_rate")]
    assert len(notes) == 1 and reason in notes[0].lower()


def test_empty_statement_gives_none_and_a_reason(monkeypatch):
    sec = _fetch(monkeypatch, pd.DataFrame())
    assert sec.fundamentals.effective_tax_rate is None
    assert any("no income statement" in d for d in sec.qualitative["defaulted_inputs"])


def test_nan_values_are_missing_not_zero(monkeypatch):
    sec = _fetch(monkeypatch, _statement(**{"Tax Provision": float("nan"), "Pretax Income": 10.0}))
    assert sec.fundamentals.effective_tax_rate is None


def test_adapter_no_longer_writes_a_21_percent_default(monkeypatch):
    sec = _fetch(monkeypatch, pd.DataFrame())
    # qualitative tax_rate is the sourced MARGINAL rate (US 25%), not the old 21% constant
    assert sec.qualitative["tax_rate"] == pytest.approx(0.25)
    assert "United States statutory tax" in sec.qualitative["tax_rate_source"]
    assert not hasattr(ya, "US_FEDERAL_TAX_RATE")


# ------------------------------------------------------------------ B3
def test_regression_inputs_use_the_effective_rate_when_present(monkeypatch):
    _fetch(monkeypatch, _statement(**{"Tax Provision": 2.4, "Pretax Income": 10.0}))
    inputs = YFinanceAdapter().build_regression_inputs("TAXT")
    assert inputs.tax_rate == pytest.approx(0.24)
    assert not any(d.startswith("tax_rate") for d in inputs.defaulted_inputs)


def test_regression_inputs_fall_back_to_the_labelled_marginal_rate(monkeypatch):
    _fetch(monkeypatch, pd.DataFrame())
    inputs = YFinanceAdapter().build_regression_inputs("TAXT")
    assert inputs.tax_rate == pytest.approx(0.25)
    labelled = [d for d in inputs.defaulted_inputs if d.startswith("tax_rate")]
    assert len(labelled) == 1
    assert "marginal" in labelled[0] and "Damodaran Apr 2026" in labelled[0]


def test_relevering_and_wacc_ignore_the_effective_rate():
    from iam.pipeline.orchestrator import ValuationPipeline

    def sec(effective: float | None) -> Security:
        return Security(
            ticker="X",
            sector="Investments & Asset Management",
            industry="Asset Management",
            fundamentals=Fundamentals(
                revenue_ttm=100.0,
                operating_margin=0.3,
                interest_expense_ttm=5.0,
                total_debt=230.0,
                effective_tax_rate=effective,
            ),
            market=MarketData(price=100.0, shares_outstanding=10.0, market_cap=1000.0, beta=1.3),
        )

    quote = SimpleNamespace(last=4.30)
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=quote),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=Exception("No network"),
        ),
    ):
        base = ground_truth.GroundTruthProvider().get_equity_risk_profile(sec(None))
        eff = ground_truth.GroundTruthProvider().get_equity_risk_profile(sec(0.10))
        w_base = ValuationPipeline._calculate_dynamic_wacc(sec(None))
        w_eff = ValuationPipeline._calculate_dynamic_wacc(sec(0.10))
    assert base is not None and eff is not None and w_base is not None and w_eff is not None
    marginal = company_marginal_tax(sec(0.10))[0]
    assert eff.tax_rate == pytest.approx(marginal) == pytest.approx(base.tax_rate)
    assert eff.levered_beta == pytest.approx(base.levered_beta)
    assert w_eff["tax_rate"] == pytest.approx(marginal)
    assert w_eff["wacc"] == pytest.approx(w_base["wacc"])


def test_nan_tax_provision_falls_through_to_income_tax_expense():
    """AGY review (gemini-3.8-flash): a NaN first label must not stop the search."""
    latest, older = pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")
    fin = pd.DataFrame(
        {latest: [float("nan"), 2.5, 10.0], older: [1.0, 1.0, 5.0]},
        index=["Tax Provision", "Income Tax Expense", "Pretax Income"],
    )
    rate, reason = ya.effective_tax_rate_from_statement(fin)
    assert reason is None
    assert rate == pytest.approx(0.25)
