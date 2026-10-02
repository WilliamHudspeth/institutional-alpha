"""Behavioural tests for validation.financial_guards and valuation.damodaran_defaults."""

import pytest

from iam.validation import financial_guards as fg
from iam.valuation import damodaran_defaults as dd


class TestGrowthGuard:
    def test_forecast_limit(self):
        fg.validate_growth_rate(0.40)
        with pytest.raises(ValueError, match="Forecast growth"):
            fg.validate_growth_rate(0.41)

    def test_terminal_limit(self):
        fg.validate_growth_rate(0.05, growth_type="terminal")
        with pytest.raises(ValueError, match="Terminal growth"):
            fg.validate_growth_rate(0.06, growth_type="terminal")

    def test_negative_allowed_by_default(self):
        fg.validate_growth_rate(-0.2)
        with pytest.raises(ValueError, match="Negative growth"):
            fg.validate_growth_rate(-0.01, allow_negative=False)


class TestDiscountAndMargin:
    @pytest.mark.parametrize("fn", [fg.validate_discount_rate, fg.validate_wacc])
    def test_wacc_bounds(self, fn):
        fn(0.04)
        fn(0.25)
        with pytest.raises(ValueError, match="below minimum"):
            fn(0.039)
        with pytest.raises(ValueError, match="exceeds maximum"):
            fn(0.26)

    def test_margin_bounds(self):
        fg.validate_margin(0.6)
        fg.validate_margin(-0.5, "net")
        with pytest.raises(ValueError, match="unrealistically low"):
            fg.validate_margin(-0.51)
        with pytest.raises(ValueError, match="exceeds"):
            fg.validate_margin(0.61)


class TestSanityCheck:
    def test_invalid_market_cap(self):
        r = fg.sanity_check_valuation(100, 0)
        assert r["passed"] is False and r["ratio"] == float("inf")

    def test_normal(self):
        r = fg.sanity_check_valuation(150, 100)
        assert r == {"passed": True, "ratio": 1.5, "warnings": []}

    def test_suspicious_but_passes(self):
        r = fg.sanity_check_valuation(20, 1, "ZZZ")
        assert r["passed"] is True and "SUSPICIOUS: ZZZ" in r["warnings"][0]

    def test_extreme_fails(self):
        r = fg.sanity_check_valuation(60, 1)
        assert r["passed"] is False and len(r["warnings"]) == 2

    def test_trillion_with_small_cap_critical(self):
        r = fg.sanity_check_valuation(2e12, 5e11)
        assert r["passed"] is False
        assert any("CRITICAL" in w for w in r["warnings"])

    def test_trillion_with_trillion_cap_ok(self):
        r = fg.sanity_check_valuation(2e12, 1.5e12)
        assert r["passed"] is True


class TestValidateAll:
    def test_clean(self):
        assert fg.validate_all_assumptions(0.1, 0.03, 0.09, 0.2) == []

    def test_collects_every_warning(self):
        w = fg.validate_all_assumptions(0.9, 0.2, 0.01, 0.9)
        assert [x.split(":")[0] for x in w] == [
            "Forecast Growth",
            "Terminal Growth",
            "WACC",
            "Forecast Margin",
        ]

    def test_margin_optional(self):
        assert fg.validate_all_assumptions(0.1, 0.03, 0.09) == []


UNI = dd.DamodaranUniverse(
    us_erp=0.05,
    region_erps={"Americas": 0.05, "EMEA": 0.06},
    sector_beta_u={"Software": 1.0},
)


class TestDamodaran:
    def test_normalized_mix(self):
        p = dd.CompanyProfile("X", "Software", {"a": 2.0, "b": 2.0})
        assert p.normalized_mix() == {"a": 0.5, "b": 0.5}
        with pytest.raises(ValueError, match="sums to zero"):
            dd.CompanyProfile("X", "Software", {"a": 0.0}).normalized_mix()

    def test_geographic_erp_weighted_with_fallback(self):
        p = dd.CompanyProfile("X", "Software", {"Americas": 0.5, "EMEA": 0.25, "Mars": 0.25})
        # Mars falls back to US ERP 0.05
        assert dd.build_geographic_erp(p, UNI) == pytest.approx(0.0525)

    def test_unlevered_beta_lookup(self):
        p = dd.CompanyProfile("X", "Software", {"Americas": 1})
        assert dd.get_unlevered_beta(p, UNI) == 1.0
        bad = dd.CompanyProfile("X", "Nope", {"Americas": 1})
        with pytest.raises(KeyError, match="Nope"):
            dd.get_unlevered_beta(bad, UNI)

    def test_hamada_and_capm_and_cap(self):
        assert dd.lever_beta(1.0, 0.0, 0.21) == 1.0
        assert dd.lever_beta(1.0, 1.0, 0.25) == pytest.approx(1.75)
        assert dd.cost_of_equity(0.04, 1.5, 0.05) == pytest.approx(0.115)
        assert dd.cap_terminal_growth(0.03, 0.04) == 0.03
        assert dd.cap_terminal_growth(0.05, 0.04) == 0.04

    def test_synthetic_spread_edges(self):
        assert dd.get_synthetic_spread(100, 0) == (0.0069, "AAA/Aaa")
        assert dd.get_synthetic_spread(100, -5)[1] == "AAA/Aaa"
        assert dd.get_synthetic_spread(900, 100)[1] == "AAA/Aaa"  # ICR 9
        assert dd.get_synthetic_spread(301, 100)[1] == "A-/A3"
        # thresholds are strict (>): an ICR exactly on 3.00 lands in the next band down
        assert dd.get_synthetic_spread(300, 100)[1] == "BBB/Baa2"
        assert dd.get_synthetic_spread(-100, 10)[1] == "D/D"

    def test_synthetic_spread_monotone_in_coverage(self):
        spreads = [dd.get_synthetic_spread(icr * 10, 10)[0] for icr in (0.1, 1, 2, 3, 5, 9)]
        assert spreads == sorted(spreads, reverse=True)

    def test_build_wacc_weights(self):
        out = dd.build_wacc(
            ke=0.10, ebit=900, interest_expense=100, rf=0.04, d_to_e=1.0, tax_rate=0.25
        )
        assert out["rating"] == "AAA/Aaa"
        assert out["cost_of_debt"] == pytest.approx(0.0469)
        assert out["wacc"] == pytest.approx(0.5 * 0.10 + 0.5 * 0.0469 * 0.75)

    def test_build_wacc_no_debt_equals_ke(self):
        out = dd.build_wacc(0.1, 10, 0, 0.04, 0.0, 0.21)
        assert out["wacc"] == pytest.approx(0.1)

    def test_build_ke_for_company(self):
        p = dd.CompanyProfile("X", "Software", {"Americas": 1.0}, d_to_e=0.5, tax_rate=0.2, rf=0.04)
        out = dd.build_ke_for_company(p, UNI)
        assert out["beta_l"] == pytest.approx(1.4)
        assert out["ke"] == pytest.approx(0.04 + 1.4 * 0.05)
        assert out["ticker"] == "X" and out["geo_erp"] == 0.05
