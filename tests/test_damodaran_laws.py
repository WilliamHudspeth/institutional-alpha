from datetime import datetime

import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.validation.damodaran_laws import DamodaranAuditReport, DamodaranLaws, LawVerdict
from iam.valuation.fcfe_dcf import FCFEDCF, FCFEAssumptions


@pytest.fixture
def sample_security():
    """Create a mock security for testing."""
    f = Fundamentals(
        revenue_ttm=1e9,
        net_income_ttm=1.5e8,
        fcf_ttm=1.2e8,
        shares_outstanding=1e7,
        operating_margin=0.20,
        roic_history=[0.25],
    )
    m = MarketData(
        price=150.0,
        market_cap=1.5e9,
    )
    return Security(ticker="TEST", fundamentals=f, market=m)


class TestDamodaranLaws:
    """Test suite for Damodaran Consistency Laws."""

    def test_law1_narrative_vs_numbers_pass(self):
        """Test Law 1 passes under high-growth consistent margins."""
        # Margin stable or expanding
        v = DamodaranLaws.audit_narrative_vs_numbers(
            growth=0.20,
            current_margin=0.20,
            target_margin=0.22,
            current_roe=0.20,
            target_roe=0.22,
        )
        assert v.passed
        assert v.score >= 0.9
        assert len(v.warnings) == 0

    def test_law1_narrative_vs_numbers_fail(self):
        """Test Law 1 fails under high growth but collapsing efficiency."""
        # Both margins and ROE contract significantly during high growth
        v = DamodaranLaws.audit_narrative_vs_numbers(
            growth=0.25,
            current_margin=0.20,
            target_margin=0.12,
            current_roe=0.25,
            target_roe=0.10,
        )
        assert not v.passed
        assert v.score < 0.5
        assert len(v.warnings) > 0

    def test_law2_growth_vs_reinvestment_pass(self):
        """Test Law 2 passes when ROE and reinvestment support growth."""
        # g = ROE * Reinvestment_rate -> 0.20 * 0.70 = 14% growth assumed
        v = DamodaranLaws.audit_growth_vs_reinvestment(
            growth=0.14,
            roe=0.20,
            reinvestment_rate=0.70,
        )
        assert v.passed
        assert v.score >= 0.9

    def test_law2_growth_vs_reinvestment_fail(self):
        """Test Law 2 fails when growth exceeds reinvestment bound."""
        # Growth assumed 30% but ROE is 10% and reinvestment is 50% (sustainable growth = 5%)
        v = DamodaranLaws.audit_growth_vs_reinvestment(
            growth=0.30,
            roe=0.10,
            reinvestment_rate=0.50,
        )
        assert not v.passed
        assert v.score < 0.5
        assert len(v.warnings) > 0

    def test_law3_terminal_growth_pass(self):
        """Test Law 3 passes when terminal growth <= risk-free rate."""
        v = DamodaranLaws.audit_terminal_growth(
            terminal_growth=0.02,
            risk_free_rate=0.04,
        )
        assert v.passed
        assert len(v.warnings) == 0

    def test_law3_terminal_growth_fail(self):
        """Test Law 3 fails when terminal growth exceeds risk-free rate."""
        v = DamodaranLaws.audit_terminal_growth(
            terminal_growth=0.05,
            risk_free_rate=0.03,
        )
        assert not v.passed
        assert v.score == 0.0
        assert len(v.warnings) > 0

    def test_law4_excess_returns_fade_pass(self):
        """Test Law 4 passes when terminal ROE mean-reverts to Ke."""
        v = DamodaranLaws.audit_excess_returns_fade(
            terminal_roe=0.10,
            cost_of_equity=0.09,
        )
        assert v.passed

    def test_law4_excess_returns_fade_fail(self):
        """Test Law 4 fails when infinite high excess returns are assumed."""
        v = DamodaranLaws.audit_excess_returns_fade(
            terminal_roe=0.35,
            cost_of_equity=0.10,
        )
        assert not v.passed
        assert v.score < 0.5
        assert len(v.warnings) > 0

    def test_security_valuation_audit_report(self, sample_security):
        """Test auditing security valuation parameters."""
        report = DamodaranLaws.audit_security_valuation(
            security=sample_security,
            growth=0.10,
            terminal_growth=0.02,
            discount_rate=0.09,
            roe=0.15,
            reinvestment_rate=0.50,
        )
        assert isinstance(report, DamodaranAuditReport)
        assert report.ticker == "TEST"
        assert report.overall_score > 0.5

    def test_fcfe_dcf_integrates_audit(self, sample_security):
        """Test that FCFEDCF compute runs the audit and returns results in verdict."""
        engine = FCFEDCF()
        assumptions = FCFEAssumptions(
            high_growth=0.10,
            terminal_growth=0.02,
            high_growth_years=5,
            discount_rate=0.08,
            roe=0.15,
        )

        result = engine.compute(sample_security, assumptions=assumptions)

        assert "damodaran_audit" in result.components
        audit = result.components["damodaran_audit"]
        assert isinstance(audit, DamodaranAuditReport)
        assert "Damodaran Consistency Audit Report:" in result.verdict_text
        assert "Overall Score:" in result.verdict_text
