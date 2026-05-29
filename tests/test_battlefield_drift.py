import pytest

from iam.data.security import Assumption, Fundamentals, MarketData, Security, Thesis
from iam.pipeline.orchestrator import ValuationPipeline
from iam.thesis.battlefield import BattlefieldReport, ValuationBattlefield
from iam.thesis.drift import ThesisDriftDetector, ThesisDriftReport


@pytest.fixture
def mock_security_with_thesis():
    """Construct a mock security with active thesis scenarios for drift testing."""
    f = Fundamentals(
        revenue_ttm=1e9,
        revenue_history=[1e9, 9.5e8, 9e8],  # 5% actual revenue growth
        operating_margin=0.15,  # 15% actual margin
        roic_history=[0.14, 0.13, 0.12],  # 14% actual return
        total_debt=2e8,
        cash_and_equivalents=5e7,  # 1.5e8 net debt
        ebitda_ttm=1e8,  # 1.5x actual leverage
    )
    m = MarketData(
        price=100.0,
        market_cap=1e9,
    )

    # Define an optimistic Bull Thesis
    bull_thesis = Thesis(
        label="Bull Case",
        assumptions=[
            Assumption(name="forecast_growth", value=0.20),  # High growth assumption (actual is 5%)
            Assumption(
                name="steady_state_margin", value=0.25
            ),  # High margin assumption (actual is 15%)
        ],
        fair_value_low=150.0,
        fair_value_high=180.0,
    )

    # Define a conservative Bear Thesis
    bear_thesis = Thesis(
        label="Bear Case",
        assumptions=[
            Assumption(name="forecast_growth", value=0.03),  # Realistic growth (actual is 5%)
            Assumption(name="steady_state_margin", value=0.12),  # Realistic margin (actual is 15%)
        ],
        fair_value_low=60.0,
        fair_value_high=80.0,
    )

    sec = Security(ticker="BATTLE", fundamentals=f, market=m)
    sec.theses = [bull_thesis, bear_thesis]
    return sec


class TestBattlefieldAndDrift:
    """Test suite for Thesis Drift Detection and Valuation Battlefield engines."""

    def test_thesis_drift_detection(self, mock_security_with_thesis):
        """Verify that assumption drifts are accurately measured as operational fragility."""
        report = ThesisDriftDetector.detect_drift(mock_security_with_thesis)

        assert isinstance(report, ThesisDriftReport)
        assert report.ticker == "BATTLE"

        # Bull case should have high fragility due to large growth and margin drift
        assert "Bull Case" in report.thesis_fragilities
        assert report.thesis_fragilities["Bull Case"] > 0.4

        # Bear case should have low fragility since actual fundamentals are better
        assert "Bear Case" in report.thesis_fragilities
        assert report.thesis_fragilities["Bear Case"] == 0.0

        # Check warnings
        assert len(report.drift_warnings) > 0
        assert any("Growth Drift" in w for w in report.drift_warnings)
        assert any("Margin Drift" in w for w in report.drift_warnings)

    def test_valuation_battlefield_matrix(self, mock_security_with_thesis):
        """Verify that the side-by-side battlefield view generates correctly."""
        pipeline = ValuationPipeline()
        report = pipeline.run(mock_security_with_thesis)

        assert report.battlefield is not None
        assert isinstance(report.battlefield, BattlefieldReport)

        # Confirm thesis targets are gathered
        assert "Market Expectations" in report.battlefield.thesis_targets
        assert "Intrinsic Baseline" in report.battlefield.thesis_targets

        # Confirm that battlefield text has the matrix and the key disagreement
        assert "Valuation Battlefield View" in report.battlefield.verdict_text
        assert "Thesis Comparison Matrix" in report.battlefield.verdict_text

        # Explain output should render Battlefield stage and Drift stage
        explain_str = report.explain()
        assert "STAGE 8 — VALUATION BATTLEFIELD VIEW" in explain_str
        assert "STAGE 9 — THESIS OPERATIONAL DRIFT AUDIT" in explain_str
