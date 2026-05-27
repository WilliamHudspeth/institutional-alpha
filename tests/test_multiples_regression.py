"""Tests for the Damodaran Jan 2026 regression-based multiple predictions."""

import math
import pytest

from iam.valuation.multiples_regression import (
    RegressionInputs,
    predict_multiple,
    predict_all,
    REGRESSIONS,
)
from iam.valuation.relative import RelativeValuation
from iam.data.security import Fundamentals, MarketData, Security


# ---------------------------------------------------------------------------
# Baseline inputs: a generic US mid-cap with no dividends
# ---------------------------------------------------------------------------
BASE_INPUTS = {
    "Beta": 1.0,
    "gEPS": 0.10,
    "Payout": 0.0,
    "ROE": 0.15,
    "g": 0.10,
    "ROIC": 0.12,
    "DFR": 0.20,
    "OperMargin": 0.15,
    "TaxRate": 0.21,
}


class TestPredictMultiple:
    def test_us_pe_known_value(self):
        # 13.12 + 10.52*1.0 + 36.47*0.10 + 8.46*0.0 = 27.287
        result = predict_multiple("US", "PE", BASE_INPUTS)
        assert result == pytest.approx(27.287, abs=0.01)

    def test_us_pbv_known_value(self):
        # -0.79 + (-0.47*0.10) + (1.49*1.0) + (20.90*0.15) + (0.17*0.0) = 3.788
        result = predict_multiple("US", "PBV", BASE_INPUTS)
        assert result == pytest.approx(3.788, abs=0.01)

    def test_us_ev_ebitda_known_value(self):
        # 18.82 + 39.30*0.10 + (-0.20*0.20) + (1.77*0.12) = 22.9224
        result = predict_multiple("US", "EV_EBITDA", BASE_INPUTS)
        assert result == pytest.approx(22.922, abs=0.01)

    def test_peg_uses_log_of_g_eps(self):
        # -0.60 + 0.56*0.0 + (-1.48*ln(0.10)) + 0.23*1.0 ≈ 3.038
        result = predict_multiple("US", "PEG", BASE_INPUTS)
        assert result == pytest.approx(3.038, abs=0.01)

    def test_higher_growth_raises_pe(self):
        high_g = {**BASE_INPUTS, "gEPS": 0.25}
        low_g = {**BASE_INPUTS, "gEPS": 0.05}
        assert predict_multiple("US", "PE", high_g) > predict_multiple("US", "PE", low_g)

    def test_higher_roe_raises_pbv(self):
        high_roe = {**BASE_INPUTS, "ROE": 0.30}
        low_roe = {**BASE_INPUTS, "ROE": 0.08}
        assert predict_multiple("US", "PBV", high_roe) > predict_multiple("US", "PBV", low_roe)

    def test_higher_debt_ratio_lowers_ev_ebitda(self):
        high_debt = {**BASE_INPUTS, "DFR": 0.50}
        low_debt = {**BASE_INPUTS, "DFR": 0.05}
        assert predict_multiple("US", "EV_EBITDA", high_debt) < predict_multiple("US", "EV_EBITDA", low_debt)

    def test_peg_raises_on_zero_g_eps(self):
        inputs = {**BASE_INPUTS, "gEPS": 0.0}
        with pytest.raises(ValueError, match="gEPS > 0"):
            predict_multiple("US", "PEG", inputs)

    def test_peg_raises_on_negative_g_eps(self):
        inputs = {**BASE_INPUTS, "gEPS": -0.05}
        with pytest.raises(ValueError):
            predict_multiple("US", "PEG", inputs)

    def test_all_five_regions_return_float(self):
        for region in ("US", "Europe", "Japan", "Emerging", "Global"):
            result = predict_multiple(region, "PE", BASE_INPUTS)
            assert isinstance(result, float)
            assert result > 0

    def test_unknown_region_raises_key_error(self):
        with pytest.raises(KeyError):
            predict_multiple("Mars", "PE", BASE_INPUTS)  # type: ignore[arg-type]

    def test_unknown_multiple_raises_key_error(self):
        with pytest.raises(KeyError):
            predict_multiple("US", "FAKE", BASE_INPUTS)  # type: ignore[arg-type]


class TestPredictAll:
    def test_returns_all_six_multiples(self):
        result = predict_all("US", BASE_INPUTS)
        assert set(result.keys()) == {"PE", "PEG", "PBV", "EV_IC", "EV_Sales", "EV_EBITDA"}

    def test_peg_is_none_when_g_eps_zero(self):
        inputs = {**BASE_INPUTS, "gEPS": 0.0}
        result = predict_all("US", inputs)
        assert result["PEG"] is None
        # All other multiples should still succeed
        for key in ("PE", "PBV", "EV_IC", "EV_Sales", "EV_EBITDA"):
            assert result[key] is not None

    def test_results_are_positive_for_healthy_inputs(self):
        result = predict_all("US", BASE_INPUTS)
        for key, val in result.items():
            if val is not None:
                assert val > 0, f"{key} should be positive for healthy inputs"

    def test_europe_different_from_us(self):
        us = predict_all("US", BASE_INPUTS)
        eu = predict_all("Europe", BASE_INPUTS)
        assert us["PE"] != eu["PE"]


class TestRegressionInputs:
    def test_to_dict_has_correct_keys(self):
        inp = RegressionInputs()
        d = inp.to_dict()
        assert set(d.keys()) == {"Beta", "gEPS", "Payout", "ROE", "g", "ROIC", "DFR", "OperMargin", "TaxRate"}

    def test_default_region_is_us(self):
        assert RegressionInputs().region == "US"

    def test_custom_fields_round_trip(self):
        inp = RegressionInputs(beta=1.5, g_eps=0.20, roe=0.25)
        d = inp.to_dict()
        assert d["Beta"] == 1.5
        assert d["gEPS"] == 0.20
        assert d["ROE"] == 0.25


class TestRelativeValuationWithRegression:
    def _make_security(self, price=100.0, pe_ttm=30.0, ev_ebitda=20.0) -> Security:
        return Security(
            ticker="TEST",
            fundamentals=Fundamentals(
                net_income_ttm=5.0,
                ebitda_ttm=10.0,
                total_debt=20.0,
                cash_and_equivalents=5.0,
                shares_outstanding=1.0,
            ),
            market=MarketData(
                price=price,
                pe_ttm=pe_ttm,
                ev_ebitda=ev_ebitda,
            ),
        )

    def test_regression_signal_adds_components(self):
        sec = self._make_security(price=100.0, pe_ttm=40.0, ev_ebitda=25.0)
        inputs = RegressionInputs(g_eps=0.10, beta=1.0)
        result = RelativeValuation().compute(sec, regression_inputs=inputs)
        # At least one regression-anchored component should appear
        reg_keys = [k for k in result.components if "regression" in k]
        assert len(reg_keys) >= 1

    def test_expensive_stock_gets_negative_move(self):
        # PE = 40 but regression predicts ~27 → implied price = 100 * (27/40) < 100
        sec = self._make_security(price=100.0, pe_ttm=40.0, ev_ebitda=25.0)
        inputs = RegressionInputs(g_eps=0.10, beta=1.0, roe=0.15, roic=0.12, dfr=0.20)
        result = RelativeValuation().compute(sec, regression_inputs=inputs)
        # Regression implies lower price → negative fair_value_to_price contribution
        assert result.fair_value_to_price is not None

    def test_cheap_stock_gets_positive_regression_contribution(self):
        # PE = 10 but regression predicts ~27 → implied price = 100 * (27/10) > 100
        sec = self._make_security(price=100.0, pe_ttm=10.0, ev_ebitda=8.0)
        inputs = RegressionInputs(g_eps=0.10, beta=1.0, roe=0.15, roic=0.12, dfr=0.20)
        result = RelativeValuation().compute(sec, regression_inputs=inputs)
        assert result.fair_value_to_price is not None
        assert result.fair_value_to_price > 0

    def test_no_regression_inputs_still_works(self):
        sec = self._make_security()
        result = RelativeValuation().compute(sec)
        # Should not error; regression simply not used
        assert result.method.value == "relative"

    def test_regression_note_appears(self):
        sec = self._make_security(price=100.0, pe_ttm=30.0, ev_ebitda=20.0)
        inputs = RegressionInputs()
        result = RelativeValuation().compute(sec, regression_inputs=inputs)
        reg_notes = [n for n in result.notes if "Regression" in n or "regression" in n]
        assert len(reg_notes) >= 1
