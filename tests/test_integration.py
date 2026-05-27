"""Integration tests for the hardened orchestration architecture.

These tests validate the data flow through the complete pipeline:
Data Layer → Adapter → Orchestrator → Result
"""

import pytest

from iam.api import Security, value_security
from iam.data import apply_scenario, GroundTruthProvider, DamodaranProvider
from iam.integration import from_ground_truth, ModelResult, Orchestrator


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
            "erp_breakdown": {
                "us": {"weight": 1.0, "erp": 0.046, "contrib": 0.046}
            },
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
            revenue_mix={"US": 0.44, "CN": 0.25, "TW": 0.13, "DE": 0.18},
        )

        orchestrator = Orchestrator()
        result = orchestrator.value_security(nvda)
        profile = result["risk_profile"]

        # US: 4.6%, CN: 7.5%, TW: 4.8%, DE: 5.2%
        # Blended: 0.44*0.046 + 0.25*0.075 + 0.13*0.048 + 0.18*0.052
        expected_erp = 0.44 * 0.046 + 0.25 * 0.075 + 0.13 * 0.048 + 0.18 * 0.052
        assert profile["erp"] == pytest.approx(expected_erp, abs=1e-4)

    def test_provenance_attached(self):
        """Risk profile includes _provenance for auditability."""
        blk = Security(
            ticker="BLK",
            sector="Investments & Asset Management",
            industry="Asset Management",
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
            revenue_mix={"NA": 0.64, "EMEA": 0.30, "APAC": 0.06},
        )

        gt = GroundTruthProvider()
        profile = gt.get_risk_profile(blk)

        # Expected ERP blending: 64% NA (4.6%) + 30% EU (5.2%) + 6% APAC (4.8%)
        # = 0.64*0.046 + 0.30*0.052 + 0.06*0.048 = 0.04792
        expected_erp = 0.64 * 0.046 + 0.30 * 0.052 + 0.06 * 0.048

        assert profile["erp"] == pytest.approx(expected_erp, abs=1e-4)
        assert profile["_provenance"]["version"] == "damodaran_jan_2026"
        assert profile["_provenance"]["stale"] is False
