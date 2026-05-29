import pytest

from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.orchestrator import ValuationPipeline
from iam.valuation.business_reality import BusinessRealityEngine, BusinessRealityReport


@pytest.fixture
def perfect_security():
    """Create a mock security with exceptional fundamental indicators."""
    f = Fundamentals(
        revenue_ttm=1.2e9,
        revenue_history=[1.2e9, 1.1e9, 1.0e9],  # Stable, growing
        operating_margin=0.20,
        net_income_ttm=2e8,
        fcf_ttm=1.8e8,
        fcf_history=[1.8e8, 1.7e8, 1.6e8],  # Consistently positive
        roic_history=[0.25, 0.23, 0.21],  # Expanding ROIC
        shares_outstanding_history=[1e7, 1.02e7, 1.05e7],  # Net share buyback/contraction
        total_debt=1e8,
        cash_and_equivalents=2e8,  # Net cash positive
        ebitda_ttm=2.5e8,
    )
    m = MarketData(
        price=150.0,
        market_cap=1.5e9,
    )
    return Security(ticker="GOOD", fundamentals=f, market=m)


@pytest.fixture
def risky_security():
    """Create a highly volatile security with problematic operating indicators."""
    f = Fundamentals(
        revenue_ttm=8e8,
        revenue_history=[8e8, 1.2e9, 7e8],  # Highly cyclical/volatile
        operating_margin=0.05,
        net_income_ttm=-5e7,
        fcf_ttm=-8e7,
        fcf_history=[-8e7, 5e7, -1e8],  # Volatile/negative FCF
        roic_history=[0.04, 0.08, 0.05],  # Declining ROIC, below cost of capital
        shares_outstanding_history=[1.5e7, 1.2e7, 1.0e7],  # Large shareholder dilution
        total_debt=6e8,
        cash_and_equivalents=5e7,  # Highly levered
        ebitda_ttm=8e7,
    )
    m = MarketData(
        price=30.0,
        market_cap=4.5e8,
    )
    return Security(ticker="RISK", fundamentals=f, market=m)


class TestBusinessRealityEngine:
    """Test suite for the Business Reality operational durability engine."""

    def test_analyze_perfect_security(self, perfect_security):
        """Verify that perfect security rates highly across all 4 operational indices."""
        report = BusinessRealityEngine.analyze_security(
            security=perfect_security,
            forecast_growth=0.10,
            terminal_growth=0.02,
            discount_rate=0.08,
            roe=0.10,
        )
        assert isinstance(report, BusinessRealityReport)
        assert report.ticker == "GOOD"
        assert report.overall_score >= 0.8

        # Revenue quality check
        assert report.revenue_quality_classification == "Highly Recurring"
        assert report.revenue_quality_score == 1.0

        # FCF durability
        assert report.fcf_durability_classification == "High Durability"
        assert report.fcf_durability_score == 1.0

        # Growth Quality (ROIC trend is positive/expanding)
        assert report.growth_quality_classification == "High-Moat Organic"
        assert report.growth_quality_score == 1.0

        # Capital Allocation (shares outstanding is shrinking -> buyback)
        assert report.capital_allocation_classification == "Share Buyback Discipline"
        assert report.capital_allocation_score == 1.0

        assert len(report.warnings) <= 2

    def test_analyze_risky_security(self, risky_security):
        """Verify that risky security triggers operational penalties and warnings."""
        report = BusinessRealityEngine.analyze_security(
            security=risky_security,
            forecast_growth=0.20,
            terminal_growth=0.03,
            discount_rate=0.10,
            roe=0.05,
        )
        assert isinstance(report, BusinessRealityReport)
        assert report.ticker == "RISK"
        assert report.overall_score < 0.6

        # Revenue is highly volatile
        assert report.revenue_quality_classification == "Cyclical / Volatile"

        # FCF has negative years and extremely high leverage
        assert report.fcf_durability_classification == "Capital Markets Dependent"

        # Growth Quality is low (contracting ROIC)
        assert report.growth_quality_classification == "Low-Quality Aggressive Scaling"

        # Capital allocation shows dilution
        assert report.capital_allocation_classification == "Share Dilution"

        # Should flag several warnings
        assert len(report.warnings) > 0
        assert any("dilution" in w.lower() for w in report.warnings)
        assert any("volatility" in w.lower() for w in report.warnings)

    def test_pipeline_integration(self, perfect_security):
        """Validate that Business Reality runs cleanly in the main Orchestrator pipeline."""
        pipeline = ValuationPipeline()
        report = pipeline.run(perfect_security)

        assert report.business_reality is not None
        assert report.business_reality.confidence > 0.7
        assert "STAGE 3b — Business Reality Engine" in report.explain()
        assert "Highly Recurring" in report.explain()
        assert "Share Buyback Discipline" in report.explain()
