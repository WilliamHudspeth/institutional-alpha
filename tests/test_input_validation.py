"""Tests for input validation and financial guards."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from iam.validation import (
    parse_growth_rate,
    parse_percentage_input,
    sanity_check_valuation,
    validate_date,
    validate_discount_rate,
    validate_growth_rate,
    validate_ticker,
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
    """Test growth rate validation using parametrized tests."""

    @pytest.mark.parametrize(
        "growth, growth_type, expect_pass",
        [
            (0.08, "forecast", True),
            (0.39, "forecast", True),
            (0.41, "forecast", False),
            (0.03, "terminal", True),
            (0.049, "terminal", True),
            (0.051, "terminal", False),
        ],
    )
    def test_growth_validation_scenarios(self, growth, growth_type, expect_pass):
        if expect_pass:
            validate_growth_rate(growth, growth_type=growth_type)
        else:
            with pytest.raises(ValueError):
                validate_growth_rate(growth, growth_type=growth_type)

    @pytest.mark.parametrize(
        "growth, allow_neg, expect_pass",
        [
            (-0.05, True, True),
            (-0.05, False, False),
            (0.05, False, True),
        ],
    )
    def test_negative_growth_scenarios(self, growth, allow_neg, expect_pass):
        if expect_pass:
            validate_growth_rate(growth, allow_negative=allow_neg)
        else:
            with pytest.raises(ValueError):
                validate_growth_rate(growth, allow_negative=allow_neg)


class TestWACCValidation:
    """Test WACC (discount rate) validation using parametrized tests."""

    @pytest.mark.parametrize(
        "wacc, expect_pass",
        [
            (0.09, True),
            (0.04, True),
            (0.25, True),
            (0.039, False),
            (0.251, False),
        ],
    )
    def test_wacc_validation_scenarios(self, wacc, expect_pass):
        if expect_pass:
            validate_discount_rate(wacc)
        else:
            with pytest.raises(ValueError):
                validate_discount_rate(wacc)


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


class TestTickerAndDateValidation:
    """Test ticker and date validation helper methods."""

    def test_ticker_valid(self):
        validate_ticker("AAPL")
        validate_ticker("MSFT")
        validate_ticker("A")

    def test_ticker_invalid_chars(self):
        with pytest.raises(ValueError, match="Invalid ticker symbol"):
            validate_ticker("AAP1")
        with pytest.raises(ValueError, match="Invalid ticker symbol"):
            validate_ticker("aapl")

    def test_ticker_invalid_length(self):
        with pytest.raises(ValueError, match="Invalid ticker symbol"):
            validate_ticker("GOOGLE")
        with pytest.raises(ValueError, match="Invalid ticker symbol"):
            validate_ticker("")

    def test_ticker_not_string(self):
        with pytest.raises(ValueError, match="Ticker must be a string"):
            validate_ticker(123)

    def test_date_valid(self):
        validate_date("2026-06-13")
        validate_date("1999-12-31")

    def test_date_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date("06/13/2026")
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date("2026-6-13")

    def test_date_invalid_values(self):
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date("2026-02-30")

    def test_date_not_string(self):
        with pytest.raises(ValueError, match="Date must be a string"):
            validate_date(None)


class TestPropertyBasedValidation:
    """Property-based tests using hypothesis."""

    @given(st.floats(min_value=-0.05, max_value=0.40))
    def test_valid_growth_rates(self, growth):
        """Any growth rate between -5% and 40% should be accepted for forecast."""
        validate_growth_rate(growth, growth_type="forecast", allow_negative=True)
        # Should not raise ValueError

    @given(st.floats(min_value=-1.0, max_value=-0.051))
    def test_invalid_negative_growth_rates(self, growth):
        """Growth rates below -5% should fail when allow_negative is False."""
        with pytest.raises(ValueError):
            validate_growth_rate(growth, growth_type="forecast", allow_negative=False)

    @given(st.floats(min_value=0.401, max_value=10.0))
    def test_invalid_high_growth_rates(self, growth):
        """Growth rates above 40% should fail for forecast."""
        with pytest.raises(ValueError):
            validate_growth_rate(growth, growth_type="forecast", allow_negative=True)

    @given(st.floats(min_value=0.04, max_value=0.25))
    def test_valid_discount_rates(self, wacc):
        """Discount rates between 4% and 25% should pass."""
        validate_discount_rate(wacc)
        # Should not raise ValueError

    @given(st.floats(min_value=-1.0, max_value=0.039))
    def test_invalid_low_discount_rates(self, wacc):
        """Discount rates below 4% should fail."""
        with pytest.raises(ValueError):
            validate_discount_rate(wacc)

    @given(st.floats(min_value=0.251, max_value=2.0))
    def test_invalid_high_discount_rates(self, wacc):
        """Discount rates above 25% should fail."""
        with pytest.raises(ValueError):
            validate_discount_rate(wacc)

    @given(st.floats(min_value=1e6, max_value=10e12), st.floats(min_value=1e6, max_value=1e12))
    def test_valuation_sanity_bounds(self, implied_val, mcap):
        """Test random ranges of valuations and market caps."""
        result = sanity_check_valuation(implied_val, mcap, ticker="TEST")
        assert "passed" in result
        assert isinstance(result["ratio"], float)
        assert isinstance(result["warnings"], list)
