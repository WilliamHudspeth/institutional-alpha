"""Tests that define the growth engine (src/iam/growth/).

Each valuation type gets its own growth rate, derived independently from the numbers:
DCF (near-term rate plus a fade path), relative valuation (revenue growth g and earnings
growth gEPS for the multiples regressions) and expectations (the market-implied rate). Company
evidence is precision-weighted and shrunk toward a size-based base rate; the DCF rate never
uses the price.
"""

import math

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.growth import base_rates, estimators
from iam.growth.apply import ensure_growth_profile
from iam.growth.profile import build_growth_profile, fade_path
from iam.growth.types import GrowthEstimate


def _sec(
    revenue=(110.0, 100.0, 90.9, 82.6, 75.1, 68.3),
    margins=(0.20, 0.20, 0.20, 0.20, 0.20, 0.20),
    **kw,
) -> Security:
    f = dict(
        revenue_ttm=revenue[0] * 1e9 if revenue else None,
        revenue_history=[r * 1e9 for r in revenue],
        operating_margin=margins[0] if margins else None,
        operating_margin_history=list(margins),
        net_income_ttm=15e9,
        ebitda_ttm=None,
        capex_ttm=None,
        fcf_ttm=None,
        effective_tax_rate=0.21,
        shares_outstanding=1e9,
    )
    m = dict(price=100.0, market_cap=100e9, pe_ttm=None, pe_forward=None)
    sector = kw.pop("sector", "Industrials")
    for k, v in kw.items():
        (f if k in Fundamentals.model_fields else m)[k] = v
    return Security(
        ticker="TEST", sector=sector, fundamentals=Fundamentals(**f), market=MarketData(**m)
    )


# --------------------------------------------------------------------------- base rates


class TestBaseRates:
    def test_buckets_fall_with_size(self):
        small = base_rates.base_rate(0.5e9)
        mid = base_rates.base_rate(10e9)
        mega = base_rates.base_rate(300e9)
        assert small.value > mid.value > mega.value
        assert small.std_error > mid.std_error > mega.std_error
        assert mega.method == "base_rate" and mega.horizon_years == 5

    def test_bucket_edges_and_values(self):
        assert base_rates.base_rate(300e9).value == pytest.approx(0.040)
        assert base_rates.base_rate(300e9).std_error == pytest.approx(0.050)
        assert base_rates.base_rate(0.5e9).value == pytest.approx(0.080)
        assert base_rates.base_rate(1e9).value == pytest.approx(0.065)  # upper bound is exclusive

    def test_unknown_revenue_uses_middle_bucket_with_low_confidence(self):
        est = base_rates.base_rate(None)
        assert est.value == pytest.approx(0.055)
        assert est.confidence < base_rates.base_rate(10e9).confidence


# --------------------------------------------------------------------------- estimators


class TestHistoricalRevenue:
    def test_steady_ten_percent_grower(self):
        est = estimators.historical_revenue(_sec())
        assert est.method == "historical_revenue"
        assert est.value == pytest.approx(0.10, abs=0.002)
        # Steady history: the error is close to the model-error floor.
        assert est.std_error == pytest.approx(
            estimators.MODEL_ERROR["historical_revenue"], abs=0.005
        )
        assert est.inputs["n_years"] == 5

    def test_uses_at_most_five_years(self):
        long = (200.0, 100.0, 100.0, 100.0, 100.0, 100.0, 10.0, 1.0)
        est = estimators.historical_revenue(_sec(revenue=long, margins=()))
        assert est.inputs["n_years"] == 5

    def test_trend_not_endpoints(self):
        # A spike in the latest year moves a log-linear trend less than an endpoint CAGR.
        rev = (150.0, 100.0, 95.0, 90.0, 86.0, 82.0)
        est = estimators.historical_revenue(_sec(revenue=rev, margins=()))
        cagr = (150 / 82) ** (1 / 5) - 1
        assert est.value < cagr

    def test_volatile_history_has_larger_error(self):
        steady = estimators.historical_revenue(_sec())
        wild = estimators.historical_revenue(
            _sec(revenue=(130.0, 90.0, 120.0, 70.0, 100.0, 60.0), margins=())
        )
        assert wild.std_error > steady.std_error

    def test_needs_three_positive_points(self):
        est = estimators.historical_revenue(_sec(revenue=(110.0, 100.0), margins=()))
        assert est.value is None and "3" in est.reason
        neg = estimators.historical_revenue(_sec(revenue=(110.0, 100.0, -5.0, 80.0), margins=()))
        assert neg.value is None  # only the leading run of positive values is used

    def test_missing_history(self):
        est = estimators.historical_revenue(_sec(revenue=(), margins=()))
        assert est.value is None and est.reason


class TestHistoricalOperatingIncome:
    def test_margin_expansion_adds_to_revenue_growth(self):
        flat = estimators.historical_operating_income(_sec())
        expanding = estimators.historical_operating_income(
            _sec(margins=(0.25, 0.24, 0.23, 0.22, 0.21, 0.20))
        )
        assert flat.value == pytest.approx(0.10, abs=0.003)
        assert expanding.value > flat.value + 0.03

    def test_needs_margin_history_aligned_with_revenue(self):
        est = estimators.historical_operating_income(_sec(margins=(0.2,)))
        assert est.value is None and est.reason

    def test_loss_years_stop_the_series(self):
        est = estimators.historical_operating_income(
            _sec(margins=(0.10, 0.08, -0.02, 0.05, 0.05, 0.05))
        )
        assert est.value is None  # only two positive leading points


class TestFundamental:
    def test_reinvestment_times_roic(self):
        # Revenue 110, margin 20%, tax 21% -> NOPAT 17.38. EBITDA 30 -> D&A 8.
        # Capex 12 -> net capex 4; working capital outflow 1.21 (cash-flow sign: -1.21).
        # Reinvestment 5.21 -> RR 0.30. ROIC from history 0.20 -> g = 0.06.
        sec = _sec(
            ebitda_ttm=30e9, capex_ttm=12e9, change_in_working_capital=-1.214e9, roic_history=[0.20]
        )
        est = estimators.fundamental(sec)
        assert est.method == "fundamental"
        assert est.inputs["reinvestment_rate"] == pytest.approx(0.30, abs=0.002)
        assert est.inputs["roic"] == pytest.approx(0.20)
        assert est.value == pytest.approx(0.06, abs=0.001)

    def test_roic_from_book_equity_when_no_history(self):
        # Invested capital = equity 60 + debt 30 - cash 3.1 = 86.9 -> ROIC = 17.38 / 86.9 = 0.20.
        sec = _sec(
            ebitda_ttm=30e9,
            capex_ttm=12e9,
            change_in_working_capital=-1.214e9,
            book_equity=60e9,
            total_debt=30e9,
            cash_and_equivalents=3.1e9,
        )
        est = estimators.fundamental(sec)
        assert est.inputs["roic"] == pytest.approx(0.20, abs=0.002)
        assert est.value == pytest.approx(0.06, abs=0.002)

    def test_fcf_approximation_has_larger_error(self):
        exact = estimators.fundamental(
            _sec(
                ebitda_ttm=30e9,
                capex_ttm=12e9,
                change_in_working_capital=-1.214e9,
                roic_history=[0.20],
            )
        )
        approx = estimators.fundamental(_sec(fcf_ttm=12.166e9, roic_history=[0.20]))
        assert approx.inputs["reinvestment_rate"] == pytest.approx(0.30, abs=0.002)
        assert approx.std_error > exact.std_error
        assert any("approximat" in n for n in approx.notes)

    def test_banks_use_retention_times_roe(self):
        sec = _sec(
            sector="Financial Services", net_income_ttm=12e9, book_equity=100e9, payout_ratio=0.40
        )
        est = estimators.fundamental(sec)
        assert est.inputs["roe"] == pytest.approx(0.12)
        assert est.value == pytest.approx(0.072)

    def test_no_roic_or_negative_nopat_gives_none(self):
        assert estimators.fundamental(_sec(ebitda_ttm=30e9, capex_ttm=12e9)).value is None
        loss = _sec(margins=(-0.05,), ebitda_ttm=3e9, capex_ttm=1e9, roic_history=[0.1])
        assert estimators.fundamental(loss).value is None

    def test_output_is_bounded(self):
        sec = _sec(ebitda_ttm=30e9, capex_ttm=60e9, roic_history=[0.80])
        assert estimators.fundamental(sec).value <= 0.40


class TestAnalystAndImplied:
    def test_forward_pe_gives_next_year_eps_growth(self):
        est = estimators.analyst_forward(_sec(pe_ttm=30.0, pe_forward=25.0))
        assert est.value == pytest.approx(0.20)
        assert est.horizon_years == 1

    def test_analyst_missing_or_negative_pe(self):
        assert estimators.analyst_forward(_sec()).value is None
        assert estimators.analyst_forward(_sec(pe_ttm=-5.0, pe_forward=20.0)).value is None

    def test_market_implied_reads_engine_result(self):
        class Result:
            components = {"implied_growth": 0.123}
            confidence = 0.9

        est = estimators.market_implied(_sec(), engine_result=Result())
        assert est.value == pytest.approx(0.123)
        assert est.horizon_years == 10

    def test_market_implied_missing(self):
        class Result:
            components = {}
            confidence = 0.2

        assert estimators.market_implied(_sec(), engine_result=Result()).value is None


# --------------------------------------------------------------------------- profile


class TestProfile:
    def test_independent_rates_per_valuation(self):
        sec = _sec(
            pe_ttm=30.0,
            pe_forward=25.0,
            ebitda_ttm=30e9,
            capex_ttm=12e9,
            change_in_working_capital=-1.214e9,
            roic_history=[0.20],
        )
        p = build_growth_profile(sec, market_implied_value=0.15)
        # The single-year fundamental rate is out of the DCF (the multi-year normalised one
        # replaces it; this fixture has no multi-year histories) but still feeds relative g.
        assert set(p.dcf.sources) == {
            "historical_revenue",
            "historical_operating_income",
            "analyst_forward",
        }
        assert set(p.relative_revenue.sources) == {"historical_revenue", "fundamental"}
        assert set(p.relative_eps.sources) == {"historical_operating_income", "analyst_forward"}
        assert p.expectations.sources == ("market_implied",)
        assert p.expectations.value == pytest.approx(0.15)
        # The DCF rate never uses the price.
        assert "market_implied" not in p.dcf.sources
        p2 = build_growth_profile(sec, market_implied_value=0.40)
        assert p2.dcf.value == pytest.approx(p.dcf.value)

    def test_precision_weighting_and_shrinkage(self):
        sec = _sec()  # only revenue and operating-income history available, both ~10%
        p = build_growth_profile(sec)
        base = base_rates.base_rate(110e9)
        assert 0 < p.dcf.shrinkage_weight < 1
        # Shrunk between the evidence (~10%) and the base rate (4%).
        assert base.value < p.dcf.value < 0.10
        # Recompute by hand from the reported pieces.
        m = sum(p.dcf.weights[k] * p.estimates[k].value for k in p.dcf.sources)
        k = p.dcf.shrinkage_weight
        assert p.dcf.value == pytest.approx(k * m + (1 - k) * base.value, abs=1e-9)
        assert sum(p.dcf.weights.values()) == pytest.approx(1.0)

    def test_noisy_history_is_shrunk_harder(self):
        steady = build_growth_profile(_sec())
        noisy = build_growth_profile(
            _sec(revenue=(135.0, 90.0, 120.0, 70.0, 95.0, 60.0), margins=(0.2,) * 6)
        )
        assert noisy.dcf.shrinkage_weight < steady.dcf.shrinkage_weight

    def test_no_evidence_falls_back_to_base_rate(self):
        p = build_growth_profile(_sec(revenue=(110.0,), margins=()))
        assert p.dcf.value == pytest.approx(base_rates.base_rate(110e9).value)
        assert p.dcf.shrinkage_weight == 0.0
        assert p.dcf.sources == ()
        assert any("base rate" in n for n in p.dcf.notes)

    def test_analyst_one_year_figure_counts_less(self):
        sec = _sec(pe_ttm=30.0, pe_forward=15.0)  # +100% next-year EPS
        p = build_growth_profile(sec)
        assert p.dcf.weights["analyst_forward"] < p.dcf.weights["historical_revenue"]
        assert p.dcf.value < 0.20

    def test_dcf_value_is_clamped(self):
        rev = (500.0, 250.0, 125.0, 62.5, 31.25, 15.6)
        p = build_growth_profile(_sec(revenue=rev, margins=(0.3,) * 6, market_cap=10e9))
        assert p.dcf.value <= 0.35

    def test_fade_path(self):
        path = fade_path(0.12, 0.025)
        assert len(path) == 10
        assert path[:5] == (0.12,) * 5
        assert path[9] == pytest.approx(0.025)
        assert path[5] == pytest.approx(0.12 + (0.025 - 0.12) * 1 / 5)
        assert all(a >= b for a, b in zip(path, path[1:]))

    def test_terminal_growth_capped_at_risk_free(self):
        p = build_growth_profile(_sec(), risk_free_rate=0.02)
        assert p.terminal_growth == pytest.approx(0.02)
        assert p.dcf_path[9] == pytest.approx(0.02)

    def test_expectations_gap_and_percentile(self):
        p = build_growth_profile(_sec(), market_implied_value=0.25)
        assert p.expectations_gap == pytest.approx(0.25 - p.dcf.value)
        base = base_rates.base_rate(110e9)
        z = (0.25 - base.value) / base.std_error
        assert p.expectations_percentile == pytest.approx(0.5 * (1 + math.erf(z / math.sqrt(2))))
        none = build_growth_profile(_sec())
        assert none.expectations.value is None and none.expectations_gap is None

    def test_summary_mentions_each_valuation(self):
        text = build_growth_profile(_sec(), market_implied_value=0.1).summary()
        for word in ("DCF", "Relative", "Expectations"):
            assert word in text


# --------------------------------------------------------------------------- apply


class TestApply:
    def test_sets_qualitative_keys_when_user_gave_none(self):
        sec = _sec()
        p = ensure_growth_profile(sec, market_implied_value=0.12)
        q = sec.qualitative
        assert q["forecast_growth"] == pytest.approx(p.dcf.value)
        assert q["forecast_growth_path"] == list(p.dcf_path)
        assert q["forecast_growth_source"].startswith("growth engine")
        assert q["relative_growth_revenue"] == pytest.approx(p.relative_revenue.value)
        assert q["relative_growth_eps"] == pytest.approx(p.relative_eps.value)
        assert q["growth_profile"] is p

    def test_user_growth_is_never_overwritten(self):
        sec = _sec()
        sec.qualitative["forecast_growth"] = 0.03
        ensure_growth_profile(sec)
        assert sec.qualitative["forecast_growth"] == 0.03
        assert sec.qualitative["forecast_growth_source"] == "user"
        assert "forecast_growth_path" not in sec.qualitative

    def test_idempotent_unless_forced(self):
        sec = _sec()
        p1 = ensure_growth_profile(sec)
        assert ensure_growth_profile(sec) is p1
        assert ensure_growth_profile(sec, force=True) is not p1

    def test_reconciled_reinvestment_rate_feeds_law_2(self):
        sec = _sec(
            ebitda_ttm=30e9, capex_ttm=12e9, change_in_working_capital=-1.214e9, roic_history=[0.20]
        )
        ensure_growth_profile(sec)
        assert sec.qualitative["reinvestment_rate"] == pytest.approx(0.30, abs=0.002)
        assert sec.qualitative["reinvestment_rate_source"] == "growth engine"

    def test_approximate_or_user_reinvestment_rate_is_not_written(self):
        approx = _sec(fcf_ttm=12.166e9, roic_history=[0.20])
        ensure_growth_profile(approx)
        assert "reinvestment_rate" not in approx.qualitative
        user = _sec(ebitda_ttm=30e9, capex_ttm=12e9, roic_history=[0.20])
        user.qualitative["reinvestment_rate"] = 0.55
        ensure_growth_profile(user)
        assert user.qualitative["reinvestment_rate"] == 0.55

    def test_estimate_types(self):
        p = build_growth_profile(_sec())
        assert all(isinstance(e, GrowthEstimate) for e in p.estimates.values())
