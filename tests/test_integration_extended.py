"""Extended integration tests for hardened orchestration architecture.

These tests validate edge cases, scenario management, provenance tracking,
and multi-region blending across the complete pipeline.
"""

import pytest

from iam.api import Security, value_security
from iam.data import (
    DamodaranProvider,
    Fundamentals,
    GroundTruthProvider,
    MarketData,
    apply_scenario,
)
from iam.integration import ModelResult, Orchestrator, from_ground_truth


class TestSecurityImmutability:
    """Validate that Security is immutable and scenarios don't mutate base."""

    def test_security_fields_unchanged_after_scenario(self):
        """Scenarios don't mutate original Security fields."""
        base = Security(
            ticker="TEST",
            sector="Technology",
            industry="Software",
            country_iso="US",
            revenue_mix={"US": 0.64, "EU": 0.30, "APAC": 0.06},
            fundamentals=Fundamentals(total_debt=100.0),
            market=MarketData(market_cap=1000.0),
        )

        bull = apply_scenario(base, {"US": 0.10, "EU": -0.05, "APAC": -0.05})

        # Original should be unchanged
        assert base.ticker == "TEST"
        assert base.sector == "Technology"
        assert base.country_iso == "US"
        assert base.fundamentals.total_debt == 100.0
        assert base.market.market_cap == 1000.0

        # Bull should have updated revenue mix
        assert bull.ticker == "TEST"
        assert bull.sector == "Technology"
        bull_mix = bull.normalized_mix()
        assert bull_mix["us"] > base.normalized_mix()["us"]

    def test_apply_scenario_with_negative_delta(self):
        """Negative deltas reduce allocations correctly."""
        base = Security(
            ticker="TEST",
            sector="Tech",
            revenue_mix={"US": 0.50, "EU": 0.30, "APAC": 0.20},
        )

        # Shift 10% from US to APAC
        scenario = apply_scenario(base, {"US": -0.10, "APAC": 0.10})
        mix = scenario.normalized_mix()

        assert mix["us"] < base.normalized_mix()["us"]
        assert mix["apac"] > base.normalized_mix()["apac"]
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-6)

    def test_apply_scenario_clamps_to_zero(self):
        """Deltas that would go negative are clamped to zero."""
        base = Security(
            ticker="TEST",
            sector="Tech",
            revenue_mix={"US": 0.30, "EU": 0.70},
        )

        # Try to reduce US by 50% (would go negative)
        scenario = apply_scenario(base, {"US": -0.50})
        mix = scenario.normalized_mix()

        # US should be 0, EU should be 100%
        assert mix["us"] == pytest.approx(0.0, abs=1e-6)
        assert mix["eu"] == pytest.approx(1.0, abs=1e-6)


class TestMultiRegionBlendingEdgeCases:
    """Test multi-region ERP blending across regions and aliases."""

    def test_country_code_resolution(self):
        """Country codes (US, CN, etc.) resolve to correct ERPs."""
        dt = DamodaranProvider()

        assert dt.resolve_erp("US") == pytest.approx(0.046)
        assert dt.resolve_erp("CN") == pytest.approx(0.075)
        assert dt.resolve_erp("DE") == pytest.approx(0.052)
        assert dt.resolve_erp("JP") == pytest.approx(0.048)

    def test_region_name_resolution(self):
        """Region names (north_america, europe) resolve correctly."""
        dt = DamodaranProvider()

        assert dt.resolve_erp("north_america") == pytest.approx(0.046)
        assert dt.resolve_erp("europe") == pytest.approx(0.052)
        assert dt.resolve_erp("apac_developed") == pytest.approx(0.048)
        assert dt.resolve_erp("emerging_markets") == pytest.approx(0.075)

    def test_alias_resolution(self):
        """Aliases (NA, EU, APAC) resolve to correct regions."""
        dt = DamodaranProvider()

        assert dt.resolve_erp("na") == dt.resolve_erp("north_america")
        assert dt.resolve_erp("eu") == dt.resolve_erp("europe")
        assert dt.resolve_erp("apac") == dt.resolve_erp("apac_developed")
        assert dt.resolve_erp("em") == dt.resolve_erp("emerging_markets")

    def test_unknown_country_defaults_to_north_america(self):
        """Unknown countries default to North America ERP."""
        dt = DamodaranProvider()

        # Hypothetical country that doesn't exist
        erp = dt.resolve_erp("XX")
        assert erp == pytest.approx(0.046)  # North America default

    def test_blended_erp_three_regions(self):
        """Blended ERP with three regions weights correctly."""
        gt = GroundTruthProvider()
        sec = Security(
            ticker="TEST",
            sector="Tech",
            industry="Software",
            revenue_mix={"US": 0.50, "CN": 0.30, "EU": 0.20},
        )

        blended_erp, breakdown = gt.get_blended_erp(sec)

        # US: 4.6%, CN: 7.5%, EU: 5.2%
        # Blended: 0.50*0.046 + 0.30*0.075 + 0.20*0.052
        expected = 0.50 * 0.046 + 0.30 * 0.075 + 0.20 * 0.052
        assert blended_erp == pytest.approx(expected, abs=1e-5)

        # Check breakdown structure
        assert "us" in breakdown
        assert "cn" in breakdown
        assert "eu" in breakdown
        assert breakdown["us"]["weight"] == pytest.approx(0.50, abs=1e-6)
        assert breakdown["cn"]["weight"] == pytest.approx(0.30, abs=1e-6)
        assert breakdown["eu"]["weight"] == pytest.approx(0.20, abs=1e-6)

    def test_normalized_mix_handles_percentages(self):
        """normalized_mix() correctly handles percentage inputs (> 1.5)."""
        sec = Security(
            ticker="TEST",
            sector="Tech",
            revenue_mix={"US": 50, "CN": 30, "EU": 20},  # Percentages
        )

        mix = sec.normalized_mix()
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-6)
        assert mix["us"] == pytest.approx(0.50, abs=1e-6)
        assert mix["cn"] == pytest.approx(0.30, abs=1e-6)
        assert mix["eu"] == pytest.approx(0.20, abs=1e-6)

    def test_normalized_mix_handles_decimals(self):
        """normalized_mix() correctly handles decimal inputs (< 1.5)."""
        sec = Security(
            ticker="TEST",
            sector="Tech",
            revenue_mix={"US": 0.50, "CN": 0.30, "EU": 0.20},  # Decimals
        )

        mix = sec.normalized_mix()
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-6)
        assert mix["us"] == pytest.approx(0.50, abs=1e-6)


class TestModelResultAndAdapter:
    """Test ModelResult construction and from_ground_truth adapter."""

    def test_model_result_reliability_bounds(self):
        """ModelResult validates reliability is in [0, 1]."""
        with pytest.raises(ValueError):
            ModelResult(name="test", value=0.08, reliability=1.5)

        with pytest.raises(ValueError):
            ModelResult(name="test", value=0.08, reliability=-0.1)

    def test_from_ground_truth_with_regional_variance(self):
        """from_ground_truth computes std from regional ERP variance."""
        profile = {
            "erp": 0.050,  # Blended
            "risk_free_rate": 0.0425,
            "industry_unlevered_beta": 1.0,
            "levered_beta": 1.2,
            "cost_of_equity": 0.0825,
            "erp_breakdown": {
                "us": {"weight": 0.50, "erp": 0.046},
                "eu": {"weight": 0.50, "erp": 0.052},
            },
            "_provenance": {"version": "test", "stale": False},
        }

        result = from_ground_truth("test_model", profile, reliability=0.85)

        # Variance = 0.5*(0.046-0.050)^2 + 0.5*(0.052-0.050)^2
        # = 0.5*0.000016 + 0.5*0.000004 = 0.00001
        # std = sqrt(0.00001) = 0.00316
        # ke_std = 0.00316 * 1.2 = 0.00379
        assert result.distribution["std"] > 0
        assert result.distribution["mean"] == pytest.approx(0.0825)

    def test_from_ground_truth_dampens_stale_10_percent(self):
        """Stale profiles have reliability dampened by 30% (0.7 multiplier)."""
        profile = {
            "cost_of_equity": 0.08,
            "levered_beta": 1.0,
            "erp_breakdown": {},
            "_provenance": {"stale": True},
        }

        result = from_ground_truth("old", profile, reliability=1.0)
        assert result.reliability == pytest.approx(0.70)

    def test_from_ground_truth_current_vintage_full_reliability(self):
        """Current profiles retain full reliability."""
        profile = {
            "cost_of_equity": 0.08,
            "levered_beta": 1.0,
            "erp_breakdown": {},
            "_provenance": {"stale": False},
        }

        result = from_ground_truth("current", profile, reliability=0.90)
        assert result.reliability == pytest.approx(0.90)


class TestOrchestratorScenarios:
    """Test Orchestrator with various security configurations."""

    def test_orchestrator_single_region_defaults_to_country(self):
        """Security with no revenue_mix uses country_iso."""
        sec = Security(
            ticker="TEST",
            sector="Tech",
            country_iso="CN",
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(sec)
        profile = result["risk_profile"]

        # Should use CN ERP (7.5%)
        assert profile["erp"] == pytest.approx(0.075, abs=1e-4)

    def test_orchestrator_us_default(self):
        """Default country_iso is US."""
        sec = Security(
            ticker="TEST",
            sector="Tech",
            # country_iso defaults to "US"
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(sec)
        profile = result["risk_profile"]

        # Should use US ERP (4.6%)
        assert profile["erp"] == pytest.approx(0.046, abs=1e-4)

    def test_orchestrator_asset_manager_blk(self):
        """BLK (asset manager) gets correct unlevered beta."""
        blk = Security(
            ticker="BLK",
            sector="Investments & Asset Management",
            industry="Asset Management",
            market=MarketData(market_cap=150e9),
            fundamentals=Fundamentals(total_debt=10e9),
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(blk)
        profile = result["risk_profile"]

        # Asset management unlevered beta = 0.59
        # BLK D/E = 10B / 150B = 0.0667
        # Levered = 0.59 * (1 + 0.79*0.0667) = 0.59 * 1.053 = 0.621
        expected_levered = 0.59 * (1 + 0.79 * (10e9 / 150e9))
        assert profile["levered_beta"] == pytest.approx(expected_levered, abs=0.01)

    def test_orchestrator_semiconductor_nvda(self):
        """NVDA (semiconductor) gets correct unlevered beta."""
        nvda = Security(
            ticker="NVDA",
            sector="Semiconductors",
            industry="Semiconductors",
            market=MarketData(market_cap=2200e9),
            fundamentals=Fundamentals(total_debt=11e9),
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(nvda)
        profile = result["risk_profile"]

        # Semiconductors unlevered beta = 1.18
        # NVDA D/E = 11B / 2200B = 0.005
        # Levered = 1.18 * (1 + 0.79*0.005) = 1.18 * 1.00395 = 1.1847
        expected_levered = 1.18 * (1 + 0.79 * (11e9 / 2200e9))
        assert profile["levered_beta"] == pytest.approx(expected_levered, abs=0.01)


class TestProvenanceTracking:
    """Test provenance metadata creation and propagation."""

    def test_provenance_includes_version(self):
        """_provenance always includes version."""
        gt = GroundTruthProvider()
        sec = Security(ticker="TEST", sector="Tech")

        profile = gt.get_risk_profile(sec)

        assert "_provenance" in profile
        assert "version" in profile["_provenance"]
        assert profile["_provenance"]["version"] == "damodaran_jan_2026"

    def test_provenance_includes_source(self):
        """_provenance includes source attribution."""
        gt = GroundTruthProvider()
        sec = Security(ticker="TEST", sector="Tech")

        profile = gt.get_risk_profile(sec)

        assert "source" in profile["_provenance"]
        assert "Damodaran" in profile["_provenance"]["source"]

    def test_provenance_includes_reference_url(self):
        """_provenance includes reference to original data."""
        gt = GroundTruthProvider()
        sec = Security(ticker="TEST", sector="Tech")

        profile = gt.get_risk_profile(sec)

        assert "reference" in profile["_provenance"]
        assert "stern" in profile["_provenance"]["reference"].lower()

    def test_provenance_stale_flag(self):
        """_provenance includes stale flag."""
        gt = GroundTruthProvider()
        sec = Security(ticker="TEST", sector="Tech")

        profile = gt.get_risk_profile(sec)

        assert "stale" in profile["_provenance"]
        assert profile["_provenance"]["stale"] is False

    def test_model_result_preserves_provenance(self):
        """ModelResult preserves provenance metadata."""
        profile = {
            "cost_of_equity": 0.08,
            "levered_beta": 1.0,
            "erp_breakdown": {},
            "_provenance": {
                "version": "test_v1",
                "source": "Test Source",
                "reference": "http://test.com",
                "stale": False,
            },
        }

        result = from_ground_truth("test", profile)

        assert result.provenance["version"] == "test_v1"
        assert result.provenance["source"] == "Test Source"
        assert result.provenance["stale"] is False


class TestPublicAPIIntegration:
    """Test the public API facade."""

    def test_value_security_returns_expected_shape(self):
        """value_security() returns dict with required fields."""
        sec = Security(
            ticker="TEST",
            sector="Technology",
            industry="Software",
        )

        result = value_security(sec)

        assert isinstance(result, dict)
        assert "ticker" in result
        assert "model_result" in result
        assert "risk_profile" in result
        assert "recommendation" in result

    def test_value_security_model_result_is_typed(self):
        """value_security() returns ModelResult, not plain dict."""
        sec = Security(
            ticker="TEST",
            sector="Technology",
        )

        result = value_security(sec)

        assert isinstance(result["model_result"], ModelResult)
        assert hasattr(result["model_result"], "name")
        assert hasattr(result["model_result"], "value")
        assert hasattr(result["model_result"], "reliability")

    def test_value_security_moderate_cost_of_equity_recommendation(self):
        """Moderate CoE gets balanced risk/return recommendation."""
        # Utilities has very low unlevered beta (0.40) + no debt
        # CoE = 4.25% + 0.40*4.6% = 4.25% + 1.84% = 6.09% (in 6-8% range)
        sec = Security(
            ticker="TEST",
            sector="Utilities",
            industry="Utilities",
        )

        result = value_security(sec)

        recommendation = result["recommendation"]
        assert "Moderate" in recommendation or "balanced" in recommendation

    def test_value_security_high_cost_of_equity_recommendation(self):
        """High CoE gets elevated risk recommendation."""
        # High leverage increases CoE
        sec = Security(
            ticker="DEBT_HEAVY",
            sector="Utilities",  # Low unlevered beta but high leverage
            industry="Utilities",
            market=MarketData(market_cap=1000.0),
            fundamentals=Fundamentals(total_debt=5000.0),  # 5x debt/equity
        )

        result = value_security(sec)

        recommendation = result["recommendation"]
        assert "elevated" in recommendation.lower() or "high" in recommendation.lower()


class TestDependencyInjection:
    """Test dependency injection for testing and mocking."""

    def test_ground_truth_accepts_custom_damodaran(self):
        """GroundTruthProvider accepts custom Damodaran for testing."""

        # Create a mock Damodaran provider
        class MockDamodaran:
            def resolve_erp(self, key):
                return 0.05  # Fixed 5% ERP for testing

            def get_industry_unlevered_beta(self, sector, industry=None):
                return 1.0

            def get_macro_state(self):
                class Macro:
                    risk_free_rate = 0.04
                    implied_erp = 0.05

                return Macro()

            def relever_beta(self, u_beta, de, tax_rate):
                return u_beta * (1 + (1 - tax_rate) * de)

        mock = MockDamodaran()
        gt = GroundTruthProvider(damodaran=mock)

        sec = Security(ticker="TEST", sector="Tech")
        profile = gt.get_equity_risk_profile(sec)

        # Should use mock's 5% ERP
        assert profile.erp == pytest.approx(0.05)

    def test_orchestrator_accepts_custom_damodaran(self):
        """Orchestrator passes Damodaran to GroundTruthProvider."""

        class MockDamodaran:
            def resolve_erp(self, key):
                return 0.06

            def get_industry_unlevered_beta(self, sector, industry=None):
                return 0.8

            def get_macro_state(self):
                class Macro:
                    risk_free_rate = 0.035
                    implied_erp = 0.06

                return Macro()

            def relever_beta(self, u_beta, de, tax_rate):
                return u_beta * (1 + (1 - tax_rate) * de)

        mock = MockDamodaran()
        orchestrator = Orchestrator(damodaran_provider=mock)

        sec = Security(ticker="TEST", sector="Tech")
        result = orchestrator.value_security(sec)

        assert result["risk_profile"]["erp"] == pytest.approx(0.06)


class TestErrorHandling:
    """Test error handling in new features."""

    def test_apply_scenario_raises_on_zero_sum(self):
        """apply_scenario raises if result would sum to zero."""
        base = Security(
            ticker="TEST",
            sector="Tech",
            revenue_mix={"US": 1.0},
        )

        # Try to reduce US by 100% (would be zero)
        with pytest.raises(ValueError):
            apply_scenario(base, {"US": -1.0})

    def test_normalized_mix_raises_on_zero_sum(self):
        """normalized_mix raises if initial mix sums to zero."""
        sec = Security(
            ticker="TEST",
            sector="Tech",
            revenue_mix={"US": 0.0, "EU": 0.0},
        )

        with pytest.raises(ValueError):
            sec.normalized_mix()

    def test_model_result_invalid_reliability(self):
        """ModelResult rejects reliability outside [0, 1]."""
        with pytest.raises(ValueError):
            ModelResult(name="test", value=0.08, reliability=1.1)

        with pytest.raises(ValueError):
            ModelResult(name="test", value=0.08, reliability=-0.05)
