"""Tests for centralized assumption registry."""

import pytest

from iam.assumptions import (
    AssumptionRegistry,
    AssumptionSet,
    RiskProfile,
    AGGRESSIVE_PROFILE,
    BASE_PROFILE,
    CONSERVATIVE_PROFILE,
)


class TestRiskProfile:
    """Tests for RiskProfile enum."""

    def test_enum_values(self):
        """RiskProfile should have three values."""
        assert len(RiskProfile) == 3
        assert RiskProfile.CONSERVATIVE.value == "conservative"
        assert RiskProfile.BASE.value == "base"
        assert RiskProfile.AGGRESSIVE.value == "aggressive"


class TestAssumptionSet:
    """Tests for AssumptionSet dataclass."""

    def test_instantiation(self):
        """Should create AssumptionSet with all fields."""
        assumptions = AssumptionSet(
            risk_free_rate=0.04,
            market_risk_premium=0.06,
            wacc=0.09,
            terminal_growth_rate=0.025,
            forecast_years=5,
            near_term_growth=0.08,
            mid_term_growth=0.06,
            quality_of_earnings_discount=0.95,
            leverage_penalty_factor=0.10,
            min_pe_acceptable=8.0,
            max_pe_acceptable=50.0,
            min_pb_acceptable=0.6,
            max_pb_acceptable=10.0,
            sentiment_reversion_likelihood=0.60,
            crowding_severity_multiplier=1.5,
        )

        assert assumptions.risk_free_rate == 0.04
        assert assumptions.wacc == 0.09
        assert assumptions.forecast_years == 5

    def test_to_dict(self):
        """Should convert to dictionary."""
        assumptions = BASE_PROFILE
        result = assumptions.to_dict()

        assert isinstance(result, dict)
        assert "risk_free_rate" in result
        assert "wacc" in result
        assert "metadata" in result


class TestPredefinedProfiles:
    """Tests for predefined profiles."""

    def test_conservative_profile(self):
        """Conservative profile should be more pessimistic."""
        assert CONSERVATIVE_PROFILE.wacc > BASE_PROFILE.wacc
        assert CONSERVATIVE_PROFILE.near_term_growth < BASE_PROFILE.near_term_growth
        assert CONSERVATIVE_PROFILE.quality_of_earnings_discount < BASE_PROFILE.quality_of_earnings_discount
        assert CONSERVATIVE_PROFILE.max_pe_acceptable < BASE_PROFILE.max_pe_acceptable

    def test_base_profile(self):
        """Base profile should be balanced."""
        assert BASE_PROFILE.wacc > AGGRESSIVE_PROFILE.wacc
        assert BASE_PROFILE.near_term_growth < AGGRESSIVE_PROFILE.near_term_growth
        assert BASE_PROFILE.quality_of_earnings_discount < AGGRESSIVE_PROFILE.quality_of_earnings_discount

    def test_aggressive_profile(self):
        """Aggressive profile should be most optimistic."""
        assert AGGRESSIVE_PROFILE.near_term_growth > BASE_PROFILE.near_term_growth
        assert AGGRESSIVE_PROFILE.terminal_growth_rate > BASE_PROFILE.terminal_growth_rate
        assert AGGRESSIVE_PROFILE.quality_of_earnings_discount > BASE_PROFILE.quality_of_earnings_discount

    def test_profiles_have_metadata(self):
        """All profiles should have descriptive metadata."""
        for profile in [CONSERVATIVE_PROFILE, BASE_PROFILE, AGGRESSIVE_PROFILE]:
            assert "description" in profile.metadata
            assert "use_case" in profile.metadata
            assert "bias" in profile.metadata


class TestAssumptionRegistry:
    """Tests for AssumptionRegistry."""

    def test_instantiation(self):
        """Should create registry with default profiles."""
        registry = AssumptionRegistry()

        assert len(registry.profiles) == 3
        assert RiskProfile.CONSERVATIVE in registry.profiles
        assert RiskProfile.BASE in registry.profiles
        assert RiskProfile.AGGRESSIVE in registry.profiles

    def test_get_profile(self):
        """Should retrieve profiles by risk level."""
        registry = AssumptionRegistry()

        conservative = registry.get_profile(RiskProfile.CONSERVATIVE)
        base = registry.get_profile(RiskProfile.BASE)
        aggressive = registry.get_profile(RiskProfile.AGGRESSIVE)

        assert conservative is not base
        assert base is not aggressive
        assert conservative.wacc > aggressive.wacc

    def test_get_sector_adjusted_no_override(self):
        """Should return base profile if no sector override exists."""
        registry = AssumptionRegistry()

        result = registry.get_sector_adjusted(RiskProfile.BASE, "NonExistent")

        assert result.risk_free_rate == BASE_PROFILE.risk_free_rate
        assert result.wacc == BASE_PROFILE.wacc

    def test_get_sector_adjusted_with_override(self):
        """Should apply sector-specific overrides."""
        registry = AssumptionRegistry()

        # Tech should have higher growth assumptions
        tech_assumptions = registry.get_sector_adjusted(RiskProfile.BASE, "Technology")

        assert tech_assumptions.near_term_growth > BASE_PROFILE.near_term_growth
        assert tech_assumptions.mid_term_growth > BASE_PROFILE.mid_term_growth
        assert tech_assumptions.max_pe_acceptable > BASE_PROFILE.max_pe_acceptable

    def test_register_sector_override(self):
        """Should allow registering new sector overrides."""
        registry = AssumptionRegistry()

        overrides = {
            "near_term_growth": 0.20,
            "wacc": 0.10,
        }
        registry.register_sector_override("CustomSector", RiskProfile.BASE, overrides)

        result = registry.get_sector_adjusted(RiskProfile.BASE, "CustomSector")
        assert result.near_term_growth == 0.20
        assert result.wacc == 0.10

    def test_sector_override_audit_trail(self):
        """Should record all assumption changes."""
        registry = AssumptionRegistry()

        overrides = {"near_term_growth": 0.20}
        registry.register_sector_override("TestSector", RiskProfile.BASE, overrides)

        log = registry.get_change_log()
        assert len(log) == 1
        assert log[0]["action"] == "register_override"
        assert log[0]["sector"] == "TestSector"
        assert log[0]["profile"] == "base"

    def test_compare_profiles(self):
        """Should compare two profiles side-by-side."""
        registry = AssumptionRegistry()

        comparison = registry.compare_profiles(RiskProfile.CONSERVATIVE, RiskProfile.AGGRESSIVE)

        assert "risk_free_rate" in comparison
        assert "wacc" in comparison
        assert len(comparison) == 15  # All non-metadata fields

        # Conservative should have higher wacc
        conservative_wacc, aggressive_wacc = comparison["wacc"]
        assert conservative_wacc > aggressive_wacc

    def test_generate_report(self):
        """Should generate formatted report."""
        registry = AssumptionRegistry()

        report = registry.generate_report(RiskProfile.BASE)

        assert "BASE ASSUMPTIONS" in report
        assert "COST OF CAPITAL" in report
        assert "GROWTH & TERMINAL VALUE" in report
        assert "VALUATION BOUNDS" in report
        assert "9.00%" in report  # BASE_PROFILE.wacc formatted

    def test_generate_report_with_sector(self):
        """Should generate sector-adjusted report."""
        registry = AssumptionRegistry()

        report = registry.generate_report(RiskProfile.BASE, sector="Technology")

        assert "TECHNOLOGY" in report
        assert "BASE ASSUMPTIONS" in report


class TestSectorOverrides:
    """Tests for sector-specific overrides."""

    def test_technology_overrides(self):
        """Tech sector should have higher growth assumptions."""
        registry = AssumptionRegistry()

        # Conservative tech
        conservative_tech = registry.get_sector_adjusted(RiskProfile.CONSERVATIVE, "Technology")
        assert conservative_tech.near_term_growth == 0.10
        assert conservative_tech.wacc == 0.105

        # Base tech
        base_tech = registry.get_sector_adjusted(RiskProfile.BASE, "Technology")
        assert base_tech.near_term_growth == 0.15
        assert base_tech.terminal_growth_rate == 0.035

        # Aggressive tech
        aggressive_tech = registry.get_sector_adjusted(RiskProfile.AGGRESSIVE, "Technology")
        assert aggressive_tech.near_term_growth == 0.20
        assert aggressive_tech.max_pe_acceptable == 100.0

    def test_financials_overrides(self):
        """Financials sector should have lower growth, higher leverage penalty."""
        registry = AssumptionRegistry()

        base_financials = registry.get_sector_adjusted(RiskProfile.BASE, "Financials")
        assert base_financials.near_term_growth == 0.05
        assert base_financials.leverage_penalty_factor == 0.08

    def test_utilities_overrides(self):
        """Utilities should have low growth, low WACC."""
        registry = AssumptionRegistry()

        base_utilities = registry.get_sector_adjusted(RiskProfile.BASE, "Utilities")
        assert base_utilities.near_term_growth == 0.03
        assert base_utilities.wacc == 0.075

    def test_all_sectors_defined(self):
        """All major sectors should have overrides."""
        expected_sectors = ["Technology", "Financials", "Healthcare", "Utilities", "Consumer", "Energy"]
        registry = AssumptionRegistry()

        for sector in expected_sectors:
            base = registry.get_sector_adjusted(RiskProfile.BASE, sector)
            assert base is not None


class TestAssumptionComparisons:
    """Tests for comparing assumptions across profiles and sectors."""

    def test_growth_assumptions_increase_with_risk(self):
        """Growth assumptions should increase from conservative to aggressive."""
        registry = AssumptionRegistry()

        conservative = registry.get_profile(RiskProfile.CONSERVATIVE)
        base = registry.get_profile(RiskProfile.BASE)
        aggressive = registry.get_profile(RiskProfile.AGGRESSIVE)

        assert conservative.near_term_growth < base.near_term_growth
        assert base.near_term_growth < aggressive.near_term_growth

    def test_wacc_decreases_with_risk(self):
        """WACC should decrease from conservative to aggressive."""
        registry = AssumptionRegistry()

        conservative = registry.get_profile(RiskProfile.CONSERVATIVE)
        base = registry.get_profile(RiskProfile.BASE)
        aggressive = registry.get_profile(RiskProfile.AGGRESSIVE)

        assert conservative.wacc > base.wacc
        assert base.wacc > aggressive.wacc

    def test_pe_bounds_increase_with_risk(self):
        """P/E bounds should expand from conservative to aggressive."""
        registry = AssumptionRegistry()

        conservative = registry.get_profile(RiskProfile.CONSERVATIVE)
        base = registry.get_profile(RiskProfile.BASE)
        aggressive = registry.get_profile(RiskProfile.AGGRESSIVE)

        assert conservative.max_pe_acceptable < base.max_pe_acceptable
        assert base.max_pe_acceptable < aggressive.max_pe_acceptable

    def test_quality_discount_decreases_with_risk(self):
        """Quality of earnings discount should decrease with risk appetite."""
        registry = AssumptionRegistry()

        conservative = registry.get_profile(RiskProfile.CONSERVATIVE)
        base = registry.get_profile(RiskProfile.BASE)
        aggressive = registry.get_profile(RiskProfile.AGGRESSIVE)

        # Lower discount = more willing to accept low quality earnings
        assert conservative.quality_of_earnings_discount < base.quality_of_earnings_discount
        assert base.quality_of_earnings_discount < aggressive.quality_of_earnings_discount


class TestAssumptionBounds:
    """Tests for assumption bounds and sanity checks."""

    def test_growth_rate_bounds(self):
        """Terminal growth should be lower than forecasted growth."""
        for profile in [CONSERVATIVE_PROFILE, BASE_PROFILE, AGGRESSIVE_PROFILE]:
            assert profile.terminal_growth_rate < profile.near_term_growth
            assert profile.mid_term_growth > profile.terminal_growth_rate

    def test_wacc_reasonable_range(self):
        """WACC should be in reasonable range."""
        for profile in [CONSERVATIVE_PROFILE, BASE_PROFILE, AGGRESSIVE_PROFILE]:
            assert 0.05 <= profile.wacc <= 0.15

    def test_risk_free_rate_bounds(self):
        """Risk-free rate should be lower than WACC."""
        for profile in [CONSERVATIVE_PROFILE, BASE_PROFILE, AGGRESSIVE_PROFILE]:
            assert profile.risk_free_rate < profile.wacc

    def test_pe_bounds_logical(self):
        """Min P/E should be less than max P/E."""
        for profile in [CONSERVATIVE_PROFILE, BASE_PROFILE, AGGRESSIVE_PROFILE]:
            assert profile.min_pe_acceptable < profile.max_pe_acceptable

    def test_pb_bounds_logical(self):
        """Min P/B should be less than max P/B."""
        for profile in [CONSERVATIVE_PROFILE, BASE_PROFILE, AGGRESSIVE_PROFILE]:
            assert profile.min_pb_acceptable < profile.max_pb_acceptable
