"""Integration tests for the hardened orchestration architecture.

These tests validate the data flow through the complete pipeline:
Data Layer → Adapter → Orchestrator → Result
"""

import pytest

from iam.api import Security, value_security
from iam.data import GroundTruthProvider, MarketData, apply_scenario
from iam.integration import ModelResult, Orchestrator, from_ground_truth
from tests.erp_helpers import country_avg as _country_erp
from tests.erp_helpers import region_erp as _region_erp


class TestApplyScenario:
    """Test immutable scenario construction."""

    def test_apply_positive_delta(self):
        """Positive delta increases revenue_mix allocation."""
        base = Security(
            ticker="TEST",
            sector="Technology",
            industry="Software",
            revenue_mix={"US": 0.64, "EU": 0.30, "APAC": 0.06},
        )

        bull = apply_scenario(base, {"US": 0.10, "EU": -0.05, "APAC": -0.05})
        mix = bull.normalized_mix()

        assert mix["us"] > base.normalized_mix()["us"]
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-6)

    def test_apply_scenario_does_not_mutate_base(self):
        """apply_scenario returns new Security without mutating base."""
        base = Security(
            ticker="TEST",
            sector="Technology",
            revenue_mix={"US": 0.5, "EU": 0.5},
        )
        base_mix = base.normalized_mix().copy()

        apply_scenario(base, {"US": 0.3, "EU": -0.3})

        assert base.normalized_mix() == base_mix


class TestFromGroundTruth:
    """Test adaptation of GroundTruth profiles to ModelResult."""

    def test_from_ground_truth_basic(self):
        """Converts profile dict to ModelResult with reliability dampening."""
        profile = {
            "erp": 0.046,
            "risk_free_rate": 0.0425,
            "industry_unlevered_beta": 0.59,
            "levered_beta": 0.62,
            "cost_of_equity": 0.0711,
            "erp_breakdown": {"us": {"weight": 1.0, "erp": 0.046, "contrib": 0.046}},
            "_provenance": {
                "version": "damodaran_jan_2026",
                "source": "Damodaran (NYU Stern)",
                "stale": False,
            },
        }

        result = from_ground_truth("test_model", profile, reliability=0.90)

        assert isinstance(result, ModelResult)
        assert result.name == "test_model"
        assert result.value == pytest.approx(0.0711)
        assert result.reliability == pytest.approx(0.90)
        assert result.distribution["mean"] == pytest.approx(0.0711)

    def test_dampens_stale_vintage(self):
        """Reliability is dampened if profile is marked stale."""
        profile = {
            "cost_of_equity": 0.08,
            "levered_beta": 1.0,
            "erp_breakdown": {},
            "_provenance": {"stale": True, "version": "old"},
        }

        result = from_ground_truth("old_model", profile, reliability=0.90)

        assert result.reliability == pytest.approx(0.90 * 0.7)


class TestOrchestrator:
    """Test the orchestrator integration."""

    def test_value_security_basic(self):
        """Orchestrator produces complete valuation."""
        nvda = Security(
            ticker="NVDA",
            sector="Semiconductors",
            industry="Semiconductors",
            market=MarketData(market_cap=1000.0),
            revenue_mix={"US": 0.44, "CN": 0.25, "TW": 0.13, "DE": 0.18},
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(nvda)

        assert "model_result" in result
        assert "risk_profile" in result
        assert "recommendation" in result

        model = result["model_result"]
        assert isinstance(model, ModelResult)
        assert model.value > 0
        assert model.reliability > 0

    def test_blended_erp_from_revenue_mix(self):
        """Multi-region revenue mix produces blended ERP."""
        nvda = Security(
            ticker="NVDA",
            sector="Semiconductors",
            market=MarketData(market_cap=1000.0),
            revenue_mix={"US": 0.44, "CN": 0.25, "TW": 0.13, "DE": 0.18},
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(nvda)
        profile = result["risk_profile"]

        # Country ERPs (rating/CDS averaged) from the April 2026 Damodaran dataset
        # (was the stale 4.6/7.5/4.8/5.2% table).
        expected_erp = (
            0.44 * _country_erp("United States")
            + 0.25 * _country_erp("China")
            + 0.13 * _country_erp("Taiwan")
            + 0.18 * _country_erp("Germany")
        )
        assert profile["erp"] == pytest.approx(expected_erp, abs=1e-4)

    def test_provenance_attached(self):
        """Risk profile includes _provenance for auditability."""
        blk = Security(
            ticker="BLK",
            sector="Investments & Asset Management",
            industry="Asset Management",
            market=MarketData(market_cap=1000.0),
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(blk)
        profile = result["risk_profile"]

        assert "_provenance" in profile
        assert "version" in profile["_provenance"]
        assert profile["_provenance"]["version"] == "damodaran_jan_2026"


class TestPublicAPI:
    """Test the public API facade."""

    def test_value_security_function(self):
        """Module-level value_security() function works."""
        sec = Security(
            ticker="TEST",
            sector="Technology",
            industry="Software",
            market=MarketData(market_cap=1000.0),
        )

        result = value_security(sec)

        assert "model_result" in result
        assert result["ticker"] == "TEST"
        assert isinstance(result["model_result"], ModelResult)


class TestMultiRegionBlending:
    """Integration test: BLK case study from user spec."""

    def test_blk_baseline(self):
        """BLK with 64/30/6 regional mix produces expected Ke."""
        blk = Security(
            ticker="BLK",
            sector="Investments & Asset Management",
            industry="Asset Management",
            market=MarketData(market_cap=1000.0),
            revenue_mix={"NA": 0.64, "EMEA": 0.30, "APAC": 0.06},
        )

        gt = GroundTruthProvider()
        profile = gt.get_risk_profile(blk)

        # Expected ERP blending from the GDP-weighted regional ERPs (April 2026 dataset):
        # 64% North America + 30% Western Europe (EMEA) + 6% Asia (APAC)
        expected_erp = (
            0.64 * _region_erp("North America")
            + 0.30 * _region_erp("Western Europe")
            + 0.06 * _region_erp("Asia")
        )

        assert profile["erp"] == pytest.approx(expected_erp, abs=1e-4)
        assert profile["_provenance"]["version"] == "damodaran_jan_2026"
        assert profile["_provenance"]["stale"] is False
