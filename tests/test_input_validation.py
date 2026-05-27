"""Tests for input validation and financial guards."""

import pytest

from iam.validation import (
    parse_percentage_input,
    parse_growth_rate,
    sanity_check_valuation,
    validate_growth_rate,
    validate_discount_rate,
)


class TestPercentageParser:
    """Test percentage input normalization."""

    def test_percentage_whole_number(self):
        """User input '13' should become 0.13."""
        assert parse_percentage_input("13") == 0.13

    def test_percentage_decimal(self):
        """User input '0.13' should stay 0.13."""
        assert parse_percentage_input("0.13") == 0.13

    def test_percentage_with_space(self):
        """Input with spaces should be trimmed."""
        assert parse_percentage_input("  13  ") == 0.13

    def test_percentage_default(self):
        """Empty input should use default."""
        assert parse_percentage_input("", default=0.08) == 0.08

    def test_percentage_invalid_input(self):
        """Invalid input should raise ValueError."""
        with pytest.raises(ValueError):
            parse_percentage_input("not_a_number")

    def test_percentage_no_default(self):
        """Empty input without default should raise ValueError."""
        with pytest.raises(ValueError):
            parse_percentage_input("")


class TestGrowthRateParser:
    """Test growth rate parsing."""

    def test_growth_whole_percent(self):
        """'13' → 0.13 (13%)."""
        assert parse_growth_rate("13") == 0.13

    def test_growth_decimal(self):
        """'0.13' → 0.13."""
        assert parse_growth_rate("0.13") == 0.13

    def test_growth_default(self):
        """Empty input uses 8% default."""
        assert parse_growth_rate("") == 0.08

    def test_growth_custom_default(self):
        """Custom default works."""
        assert parse_growth_rate("", default=0.12) == 0.12


class TestGrowthValidation:
    """Test growth rate validation."""

    def test_forecast_growth_valid(self):
        """Valid forecast growth (8%) should pass."""
        validate_growth_rate(0.08, growth_type="forecast")

    def test_forecast_growth_too_high(self):
        """Forecast growth > 40% should raise ValueError."""
        with pytest.raises(ValueError):
            validate_growth_rate(0.50, growth_type="forecast")

    def test_terminal_growth_valid(self):
        """Valid terminal growth (3%) should pass."""
        validate_growth_rate(0.03, growth_type="terminal")

    def test_terminal_growth_too_high(self):
        """Terminal growth > 5% should raise ValueError."""
        with pytest.raises(ValueError):
            validate_growth_rate(0.08, growth_type="terminal")

    def test_negative_growth_allowed(self):
        """Negative growth should be allowed by default."""
        validate_growth_rate(-0.05, allow_negative=True)

    def test_negative_growth_not_allowed(self):
        """Negative growth should raise error if not allowed."""
        with pytest.raises(ValueError):
            validate_growth_rate(-0.05, allow_negative=False)


class TestWACCValidation:
    """Test WACC (discount rate) validation."""

    def test_wacc_valid(self):
        """Valid WACC (9%) should pass."""
        validate_discount_rate(0.09)

    def test_wacc_too_low(self):
        """WACC < 4% should raise ValueError."""
        with pytest.raises(ValueError):
            validate_discount_rate(0.02)

    def test_wacc_too_high(self):
        """WACC > 25% should raise ValueError."""
        with pytest.raises(ValueError):
            validate_discount_rate(0.30)


class TestValuationSanityCheck:
    """Test valuation sanity checking."""

    def test_reasonable_valuation(self):
        """Reasonable valuation (3x market cap) should pass."""
        result = sanity_check_valuation(300e9, 100e9, ticker="AAPL")
        assert result["passed"] is True
        assert result["ratio"] == 3.0
        assert len(result["warnings"]) == 0

    def test_extreme_valuation(self):
        """Extreme valuation (100x market cap) should fail."""
        result = sanity_check_valuation(10e12, 100e9, ticker="TEST")
        assert result["passed"] is False
        assert result["ratio"] == 100.0
        assert any("EXTREME" in w for w in result["warnings"])

    def test_trillion_dollar_valuation(self):
        """Trillion+ valuations should fail when market cap is small."""
        result = sanity_check_valuation(1e12, 10e9, ticker="BIG")
        assert result["passed"] is False
        # Should have either EXTREME or CRITICAL warning
        assert any("EXTREME" in w or "CRITICAL" in w for w in result["warnings"])

    def test_invalid_market_cap(self):
        """Zero or negative market cap should fail."""
        result = sanity_check_valuation(100e9, 0, ticker="BAD")
        assert result["passed"] is False


class TestRealWorldScenarios:
    """Test real-world input scenarios."""

    def test_user_enters_13_instead_of_0_13(self):
        """Bug scenario: user enters 13 thinking it's 13%."""
        growth = parse_growth_rate("13")
        assert growth == 0.13
        # This should NOT become 1300%
        assert growth != 13.0

    def test_user_enters_8_for_default(self):
        """User enters 8 for 8% (common usage)."""
        growth = parse_growth_rate("8")
        assert growth == 0.08

    def test_validated_growth_with_user_input(self):
        """Full flow: user input → parse → validate."""
        user_input = "12"
        growth = parse_growth_rate(user_input)
        validate_growth_rate(growth)
        assert growth == 0.12

    def test_extreme_input_caught(self):
        """Extreme input should be caught during validation."""
        user_input = "130"  # User meant 130%?
        growth = parse_growth_rate(user_input)
        with pytest.raises(ValueError):
            validate_growth_rate(growth, growth_type="forecast")
