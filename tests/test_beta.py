"""Tests for beta unlevering / relevering and CAPM pipeline wiring."""

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.valuation.beta import (
    get_custom_beta_for_intrinsic,
    get_yahoo_beta,
    market_value_of_debt,
    relever_beta,
    unlever_beta,
)
from iam.valuation.fcfe_dcf import FCFEDCF
from iam.valuation.reverse_dcf import ReverseDCF


# ---------------------------------------------------------------------------
# Core math — verified against Damodaran's levbeta.xls workbook
# ---------------------------------------------------------------------------


class TestUnleverBeta:
    def test_levbeta_xls_example(self):
        # Damodaran levbeta.xls: Beta=1.40, tax=36%, avg D/E=14%
        # Expected: 1.40 / (1 + 0.64*0.14) = 1.284875
        result = unlever_beta(levered_beta=1.40, debt_to_equity=0.14, tax_rate=0.36)
        assert result == pytest.approx(1.284875, rel=1e-5)

    def test_zero_debt_is_identity(self):
        assert unlever_beta(1.50, debt_to_equity=0.0, tax_rate=0.21) == pytest.approx(1.50)

    def test_higher_leverage_produces_lower_unlevered_beta(self):
        low = unlever_beta(1.40, debt_to_equity=0.10, tax_rate=0.21)
        high = unlever_beta(1.40, debt_to_equity=0.50, tax_rate=0.21)
        assert low > high

    def test_full_tax_shield_uses_pre_tax_de(self):
        # tax_rate = 0 means no tax shield, unlever just divides by (1 + D/E)
        result = unlever_beta(1.40, debt_to_equity=0.40, tax_rate=0.0)
        assert result == pytest.approx(1.40 / 1.40)


class TestReleverBeta:
    def test_levbeta_xls_example(self):
        # Unlevered=1.284875, current D/E=12142.26/50889.04=0.238603, tax=36%
        de_current = 12142.26 / 50889.04
        result = relever_beta(unlevered_beta=1.284875, debt_to_equity=de_current, tax_rate=0.36)
        assert result == pytest.approx(1.481083, rel=1e-5)

    def test_zero_debt_is_identity(self):
        assert relever_beta(1.20, debt_to_equity=0.0, tax_rate=0.21) == pytest.approx(1.20)

    def test_unlever_relever_roundtrip(self):
        original = 1.75
        de = 0.30
        tax = 0.25
        assert relever_beta(unlever_beta(original, de, tax), de, tax) == pytest.approx(original)

    def test_higher_leverage_raises_relevered_beta(self):
        low = relever_beta(1.20, debt_to_equity=0.10, tax_rate=0.21)
        high = relever_beta(1.20, debt_to_equity=0.60, tax_rate=0.21)
        assert high > low


class TestMarketValueOfDebt:
    def test_coupon_equals_market_rate_gives_book_value(self):
        # When coupon rate = market rate, PV of debt = face value
        book = 10_000.0
        interest = book * 0.075          # 7.5% coupon
        result = market_value_of_debt(book, interest, market_rate=0.075, maturity=5.0)
        assert result == pytest.approx(book, rel=1e-5)

    def test_coupon_below_market_gives_discount(self):
        # Market rate > coupon → bonds trade at a discount
        result = market_value_of_debt(10_000, 500, market_rate=0.08, maturity=5.0)
        assert result < 10_000

    def test_coupon_above_market_gives_premium(self):
        # Market rate < coupon → bonds trade at a premium
        result = market_value_of_debt(10_000, 500, market_rate=0.04, maturity=5.0)
        assert result > 10_000

    def test_zero_market_rate_falls_back_to_book(self):
        assert market_value_of_debt(10_000, 500, market_rate=0.0, maturity=5.0) == 10_000

    def test_zero_maturity_falls_back_to_book(self):
        assert market_value_of_debt(10_000, 500, market_rate=0.05, maturity=0.0) == 10_000

    def test_longer_maturity_amplifies_rate_sensitivity(self):
        # High-rate environment: longer maturity → bigger discount
        short = market_value_of_debt(10_000, 400, market_rate=0.08, maturity=3.0)
        long_ = market_value_of_debt(10_000, 400, market_rate=0.08, maturity=15.0)
        assert long_ < short


# ---------------------------------------------------------------------------
# get_yahoo_beta — reads from market.beta, then qualitative, then defaults
# ---------------------------------------------------------------------------


class TestGetYahooBeta:
    def test_reads_market_beta(self):
        sec = Security(ticker="T", market=MarketData(beta=1.35))
        assert get_yahoo_beta(sec) == pytest.approx(1.35)

    def test_falls_back_to_qualitative(self):
        sec = Security(ticker="T")
        sec.qualitative["beta"] = 0.85
        assert get_yahoo_beta(sec) == pytest.approx(0.85)

    def test_defaults_to_one_when_absent(self):
        sec = Security(ticker="T")
        assert get_yahoo_beta(sec) == pytest.approx(1.0)

    def test_market_beta_takes_precedence_over_qualitative(self):
        sec = Security(ticker="T", market=MarketData(beta=1.40))
        sec.qualitative["beta"] = 0.50
        assert get_yahoo_beta(sec) == pytest.approx(1.40)


# ---------------------------------------------------------------------------
# get_custom_beta_for_intrinsic — unlever / relever with audit trail
# ---------------------------------------------------------------------------


class TestGetCustomBetaForIntrinsic:
    def _make_security(self, beta=1.40, market_cap=50_889.04) -> Security:
        sec = Security(
            ticker="TEST",
            fundamentals=Fundamentals(
                total_debt=10_000.0,
                interest_expense_ttm=750.0,   # 7.5% coupon on 10k book debt
            ),
            market=MarketData(beta=beta, market_cap=market_cap),
        )
        # levbeta.xls example parameters
        sec.qualitative["tax_rate"] = 0.36
        sec.qualitative["avg_de_ratio"] = 0.14
        sec.qualitative["pre_tax_cost_debt"] = 0.075   # coupon = market rate → MVD = book
        sec.qualitative["debt_maturity"] = 5.0
        return sec

    def test_unlever_writes_audit_key(self):
        sec = self._make_security()
        get_custom_beta_for_intrinsic(sec)
        assert "beta_unlevered" in sec.qualitative
        assert sec.qualitative["beta_unlevered"] == pytest.approx(1.284875, rel=1e-4)

    def test_relevered_beta_stored(self):
        sec = self._make_security()
        get_custom_beta_for_intrinsic(sec)
        # MVD = 10_000 (coupon = market rate), equity = 50_889.04
        # D/E = 10000 / 50889.04 = 0.19650
        # relevered = 1.284875 * (1 + 0.64 * 0.19650)
        expected_de = 10_000 / 50_889.04
        expected_beta = 1.284875 * (1 + 0.64 * expected_de)
        assert sec.qualitative["beta_stage3"] == pytest.approx(expected_beta, rel=1e-4)

    def test_debt_market_value_stored(self):
        sec = self._make_security()
        get_custom_beta_for_intrinsic(sec)
        # coupon = market rate → MVD = book_debt
        assert sec.qualitative["debt_market_value"] == pytest.approx(10_000, rel=1e-4)

    def test_lease_debt_adds_to_total_debt(self):
        sec = self._make_security()
        sec.qualitative["lease_debt"] = 5_000.0
        beta_with_lease = get_custom_beta_for_intrinsic(sec)
        sec2 = self._make_security()
        beta_without_lease = get_custom_beta_for_intrinsic(sec2)
        assert beta_with_lease > beta_without_lease

    def test_no_debt_equals_unlevered_beta(self):
        sec = Security(
            ticker="TEST",
            fundamentals=Fundamentals(total_debt=0.0, interest_expense_ttm=0.0),
            market=MarketData(beta=1.40, market_cap=50_000.0),
        )
        sec.qualitative["tax_rate"] = 0.36
        sec.qualitative["avg_de_ratio"] = 0.14
        result = get_custom_beta_for_intrinsic(sec)
        # Current D/E = 0, so relevered = unlevered
        assert result == pytest.approx(1.284875, rel=1e-4)


# ---------------------------------------------------------------------------
# Pipeline integration — Stage 1 uses Yahoo beta, Stage 3 uses custom beta
# ---------------------------------------------------------------------------


def _full_security(beta=1.40, market_cap=50_000.0) -> Security:
    """A security with enough data to run both DCF stages."""
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            net_income_ttm=5_000.0,
            fcf_ttm=4_000.0,
            shares_outstanding=1_000.0,
            total_debt=10_000.0,
            interest_expense_ttm=750.0,
            revenue_history=[110.0, 100.0, 90.0, 80.0, 70.0],
        ),
        market=MarketData(price=100.0, beta=beta, market_cap=market_cap),
    )
    sec.qualitative["risk_free_rate"] = 0.045
    sec.qualitative["equity_risk_premium"] = 0.055
    sec.qualitative["tax_rate"] = 0.36
    sec.qualitative["avg_de_ratio"] = 0.14
    return sec


class TestStage1CAPMWiring:
    def test_capm_rate_in_assumptions(self):
        sec = _full_security(beta=1.40)
        result = ReverseDCF().compute(sec)
        # r = 0.045 + 1.40 * 0.055 = 0.122
        assert result.assumptions["discount_rate"] == pytest.approx(0.045 + 1.40 * 0.055, rel=1e-4)

    def test_capm_note_appears(self):
        sec = _full_security()
        result = ReverseDCF().compute(sec)
        assert any("CAPM" in n for n in result.notes)

    def test_without_capm_keys_uses_default_rate(self):
        sec = Security(
            ticker="TEST",
            fundamentals=Fundamentals(
                net_income_ttm=5_000.0, shares_outstanding=1_000.0,
                revenue_history=[110.0, 100.0, 90.0, 80.0, 70.0],
            ),
            market=MarketData(price=100.0, beta=1.40),
        )
        result = ReverseDCF(discount_rate=0.09).compute(sec)
        assert result.assumptions["discount_rate"] == pytest.approx(0.09)

    def test_higher_beta_implies_higher_growth_needed(self):
        # Higher beta → higher discount rate → future cash flows are worth less
        # → to justify the same price, the market must be expecting higher growth.
        sec_high = _full_security(beta=1.80)
        sec_low = _full_security(beta=0.80)
        g_high_beta = ReverseDCF().compute(sec_high).components.get("implied_growth", 0)
        g_low_beta = ReverseDCF().compute(sec_low).components.get("implied_growth", 0)
        assert g_high_beta > g_low_beta


class TestStage3CAPMWiring:
    def test_capm_rate_overrides_resolved_assumptions(self):
        sec = _full_security(beta=1.40, market_cap=50_889.04)
        sec.qualitative["pre_tax_cost_debt"] = 0.075
        sec.qualitative["debt_maturity"] = 5.0
        result = FCFEDCF().compute(sec)
        # Custom beta ≈ 1.284875 * (1 + 0.64 * 10000/50889.04)
        beta_unlev = 1.40 / (1 + 0.64 * 0.14)
        de = 10_000 / 50_889.04
        beta_custom = beta_unlev * (1 + 0.64 * de)
        expected_r = 0.045 + beta_custom * 0.055
        assert result.assumptions["discount_rate"] == pytest.approx(expected_r, rel=1e-4)

    def test_capm_note_appears_in_stage3(self):
        sec = _full_security()
        result = FCFEDCF().compute(sec)
        assert any("CAPM" in n for n in result.notes)

    def test_without_capm_keys_uses_default_rate(self):
        sec = Security(
            ticker="TEST",
            fundamentals=Fundamentals(
                net_income_ttm=5_000.0, fcf_ttm=4_000.0, shares_outstanding=1_000.0,
            ),
            market=MarketData(price=100.0),
        )
        result = FCFEDCF().compute(sec)
        # Now uses Damodaran institutional baseline (not generic 9%)
        # For unknown sector/industry with no debt: 4.25% + 0.85 * 4.6% = 8.16%
        assert result.assumptions["discount_rate"] == pytest.approx(0.0816, abs=0.001)
        assert any("Damodaran" in n for n in result.notes)

    def test_audit_trail_written_after_capm_run(self):
        sec = _full_security()
        FCFEDCF().compute(sec)
        assert "beta_unlevered" in sec.qualitative
        assert "beta_stage3" in sec.qualitative
