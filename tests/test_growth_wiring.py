"""Wiring of the growth engine into the data layer and every valuation stage."""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from iam import Fundamentals, MarketData, Security, ValuationPipeline
from iam.data.edgar.facts import EdgarFundamentals, FieldValue, to_fundamentals
from iam.data.providers.yfinance_adapter import estimate_roic
from iam.growth.apply import ensure_growth_profile
from iam.ui.menu import rating_interpretation
from iam.valuation.fcfe_dcf import FCFEDCF
from iam.valuation.reverse_dcf import _present_value_path, _present_value_two_stage


def _security(**qual) -> Security:
    return Security(
        ticker="TEST",
        sector="Industrials",
        fundamentals=Fundamentals(
            revenue_ttm=1210.0,
            revenue_history=[1210.0, 1100.0, 1000.0, 909.0, 826.0, 751.0],
            operating_margin=0.20,
            operating_margin_history=[0.20] * 6,
            fcf_ttm=150.0,
            net_income_ttm=160.0,
            shares_outstanding=100.0,
            effective_tax_rate=0.21,
        ),
        market=MarketData(price=30.0, market_cap=3000.0, beta=1.0),
        qualitative=dict(qual),
    )


@pytest.fixture()
def offline():
    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=RuntimeError("offline"),
        ),
    ):
        yield


# --------------------------------------------------------------------------- DCF maths


class TestPresentValuePath:
    def test_flat_path_matches_two_stage(self):
        flat = _present_value_two_stage(5.0, 0.08, 10, 0.025, 0.09, 0.15)
        path = _present_value_path(5.0, [0.08] * 10, 0.025, 0.09, 0.15)
        assert path == pytest.approx(flat, rel=1e-12)

    def test_fade_is_worth_less_than_flat(self):
        flat = _present_value_path(5.0, [0.10] * 10, 0.025, 0.09, 0.15)
        fade = _present_value_path(
            5.0, [0.10] * 5 + [0.085, 0.07, 0.055, 0.04, 0.025], 0.025, 0.09, 0.15
        )
        assert fade < flat

    def test_negative_growth_never_releases_more_than_earnings(self):
        # With ERR floored at 0, each year's FCFE equals NI; it never exceeds it.
        pv = _present_value_path(5.0, [-0.10] * 10, 0.0, 0.09, 0.15)
        ni = [5.0 * 0.9**t for t in range(1, 11)]
        expected = sum(n / 1.09**t for t, n in enumerate(ni, 1)) + ni[-1] * 1.0 / 0.09 / 1.09**10
        assert pv == pytest.approx(expected, rel=1e-9)

    def test_diverges_when_r_not_above_terminal(self):
        assert _present_value_path(5.0, [0.05] * 10, 0.09, 0.09, 0.15) == float("inf")


class TestFcfeUsesPath:
    def test_path_is_used_and_recorded(self, offline):
        sec = _security()
        ensure_growth_profile(sec)
        res = FCFEDCF().compute(sec)
        assert res.components["growth_path"] == sec.qualitative["forecast_growth_path"]
        assert any("growth path from the growth engine" in n for n in res.notes)
        assert math.isfinite(res.fair_value_per_share)

    def test_bear_below_bull_for_negative_growth(self, offline):
        sec = _security(forecast_growth=-0.06)
        res = FCFEDCF().compute(sec)
        sc = res.components["scenarios"]
        assert sc["Bear Case"]["g"] < sc["Base Case"]["g"] < sc["Bull Case"]["g"]
        assert sc["Bear Case"]["target"] < sc["Bull Case"]["target"]

    def test_non_convergent_scenario_is_dropped_and_weights_renormalised(self, offline):
        # A low cost of equity makes the bull case (wacc - 1%) fall to its terminal growth.
        sec = _security(forecast_growth=0.05, risk_free_rate=0.03, equity_risk_premium=0.0)
        res = FCFEDCF().compute(sec)
        assert math.isfinite(res.fair_value_per_share)
        sc = res.components["scenarios"]
        # Ke = 3% + 1.0 x 0% = 3%; the bull case discounts at 2% against terminal growth of 3%.
        assert "Bull Case" not in sc
        ran = list(sc.values())
        total = sum(s["prob"] for s in ran)
        pwev = sum(s["target"] * s["prob"] for s in ran) / total
        assert res.fair_value_per_share == pytest.approx(pwev, rel=1e-9)
        assert any("skipped" in n.lower() for n in res.notes)


# --------------------------------------------------------------------------- data layer


class TestDataLayer:
    def test_edgar_equity_becomes_book_equity(self):
        ef = EdgarFundamentals(
            cik=1,
            entity_name="X",
            as_of=__import__("datetime").date(2020, 1, 1),
            equity=FieldValue(value=123.0),
        )
        f, prov = to_fundamentals(ef)
        assert f.book_equity == 123.0
        assert "equity" in prov

    def test_estimate_roic(self):
        f = Fundamentals(
            revenue_ttm=110.0,
            operating_margin=0.20,
            effective_tax_rate=0.21,
            book_equity=60.0,
            total_debt=30.0,
            cash_and_equivalents=3.1,
        )
        assert estimate_roic(f) == pytest.approx(17.38 / 86.9)
        assert estimate_roic(Fundamentals(revenue_ttm=110.0, operating_margin=0.2)) is None
        loss = Fundamentals(revenue_ttm=110.0, operating_margin=-0.1, book_equity=60.0)
        assert estimate_roic(loss) is None


# --------------------------------------------------------------------------- pipeline


class TestPipeline:
    def test_profile_on_report_and_growth_from_engine(self, offline):
        sec = _security()
        report = ValuationPipeline().run(sec)
        assert report.growth_profile is not None
        assert sec.qualitative["forecast_growth"] == pytest.approx(report.growth_profile.dcf.value)
        assert sec.qualitative["forecast_growth_source"].startswith("growth engine")
        # Stage 1 ran, so the expectations rate is filled in.
        assert report.growth_profile.expectations.value is not None
        assert "Growth" in report.explain()

    def test_relative_stage_receives_its_own_growth_rates(self):
        captured = {}

        def fake(ticker, region="US", g_eps=None, g=None, roic=None):
            captured.update(g_eps=g_eps, g=g, roic=roic)
            raise RuntimeError("offline")

        with (
            patch("iam.data.markets.fetch_live_quote", return_value=None),
            patch("iam.data.providers.yfinance_adapter.build_regression_inputs", side_effect=fake),
        ):
            sec = _security()
            report = ValuationPipeline().run(sec)
        p = report.growth_profile
        assert captured["g"] == pytest.approx(p.relative_revenue.value)
        assert captured["g_eps"] == pytest.approx(p.relative_eps.value)

    def test_user_growth_is_respected(self, offline):
        sec = _security(forecast_growth=0.03)
        report = ValuationPipeline().run(sec)
        assert sec.qualitative["forecast_growth"] == 0.03
        assert sec.qualitative["forecast_growth_source"] == "user"
        assert report.growth_profile is not None


# --------------------------------------------------------------------------- menu


@pytest.mark.parametrize(
    ("rating", "word"),
    [
        ("STRONG BUY", "undervalued"),
        ("BUY", "undervalued"),
        ("MODEST BUY", "undervalued"),
        ("HOLD / NEUTRAL", "fairly valued"),
        ("HOLD", "fairly valued"),
        ("MIXED (REDUCED EXPECTED RETURN)", "overvalued"),
        ("SELL", "overvalued"),
        ("HIGH RISK SELL", "overvalued"),
        ("SPECULATIVE_BUY", "speculative"),
        ("INCONCLUSIVE", "inconclusive"),
    ],
)
def test_rating_interpretation_matches_rating(rating, word):
    assert word in rating_interpretation(rating).lower()
