from unittest.mock import MagicMock

from iam.data.security import Security
from iam.pipeline.orchestrator import ValuationPipeline


def test_sotp_integration():
    """Verify the orchestrator properly routes SOTP and wraps it in a ValuationResult."""
    # Build a mock security with segments
    mock_sec = MagicMock(spec=Security)
    mock_sec.ticker = "BLK"

    mock_sec.fundamentals = MagicMock()
    mock_sec.fundamentals.segments = [
        {
            "name": "iShares",
            "revenue": 1000,
            "ebit": 500,
            "unlevered_beta": 1.1,
            "tax_rate": 0.21,
            "growth_rate": 0.05,
            "fcfe": 200,
        },
        {
            "name": "Aladdin",
            "revenue": 500,
            "ebit": 300,
            "unlevered_beta": 1.5,
            "tax_rate": 0.21,
            "growth_rate": 0.10,
            "fcfe": 150,
        },
    ]
    mock_sec.fundamentals.shares_outstanding = 150.0
    mock_sec.fundamentals.revenue_ttm = 1500.0
    mock_sec.fundamentals.revenue_history = [1500.0, 1400.0, 1300.0]
    mock_sec.fundamentals.operating_margin = 0.35
    mock_sec.fundamentals.total_debt = 200.0
    mock_sec.fundamentals.interest_expense_ttm = 20.0
    mock_sec.fundamentals.ebitda_ttm = 800.0
    mock_sec.fundamentals.roic_history = [0.15, 0.14, 0.16]
    mock_sec.fundamentals.fcf_ttm = 200.0
    mock_sec.fundamentals.net_income_ttm = 300.0

    mock_sec.balance_sheet = MagicMock()
    mock_sec.balance_sheet.debt_to_equity = 0.2
    mock_sec.balance_sheet.tax_rate = 0.21

    mock_sec.market = MagicMock()
    mock_sec.market.market_cap = 1000.0
    mock_sec.market.price = 10.0

    mock_sec.qualitative = {}

    pipeline = ValuationPipeline()
    pipeline.use_sotp = True

    # Mocking out the other engines so they don't blow up without real data
    pipeline.market_implied_engine.compute = MagicMock(return_value=MagicMock(implied=None))
    from iam.valuation.types import Method, TriangulationResult, ValuationResult

    pipeline.relative.compute = MagicMock(
        return_value=ValuationResult(
            method=Method.RELATIVE,
            fair_value_per_share=12.0,
            fair_value_to_price=0.2,
        )
    )

    pipeline.triangulator.triangulate = MagicMock(
        return_value=TriangulationResult(cluster_center=0.15, confidence=0.8, verdict="agree")
    )

    report = pipeline.run(mock_sec)

    # Verify that the intrinsic result (which went through SOTP) is a ValuationResult
    assert report.intrinsic.method == "intrinsic"
    assert report.intrinsic.fair_value_per_share > 0
    assert len(report.intrinsic.notes) >= 2
    assert "Cost of equity" in report.intrinsic.notes[1]
    assert "iShares:" in report.intrinsic.notes[2]
