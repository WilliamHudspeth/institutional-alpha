import pytest

from iam.data.security import Security
from iam.pipeline.orchestrator import ValuationPipeline


@pytest.mark.functional
def test_full_valuation_workflow():
    # Simulate a real ticker valuation workflow
    ticker = "AAPL"
    sec = Security(ticker=ticker)
    # Inject some mock data since we aren't testing data fetchers here
    sec.name = "Apple Inc."
    sec.sector = "Technology"
    sec.market.price = 150.0
    sec.fundamentals.fcf_ttm = 100000.0
    sec.fundamentals.shares_outstanding = 15000.0
    sec.fundamentals.net_debt = 50000.0
    # Add enough history to avoid "Insufficient history" flags
    sec.fundamentals.revenue_history = [1000, 900, 800, 700]
    sec.fundamentals.operating_margin_history = [0.25, 0.24, 0.23, 0.22]
    sec.fundamentals.pe_ratio_history = [25.0] * 24  # Avoid "Insufficient P/E history"
    sec.fundamentals.ev_ebitda_history = [15.0] * 24
    sec.market.ev_ebitda = 14.5  # Required for Stage 2 fallback
    sec.market.sector_ev_ebitda_median = 12.0

    pipeline = ValuationPipeline()
    report = pipeline.run(sec)

    assert report is not None
    assert report.final_verdict is not None
    assert report.final_verdict.rating in [
        "BUY",
        "HOLD",
        "SELL",
        "ACCUMULATE",
        "REDUCE",
        "STRONG_BUY",
        "STRONG_SELL",
        "NEUTRAL",
    ]
    assert isinstance(report.final_verdict.blended_upside, float)

    # Ensure all lenses ran
    assert report.intrinsic.fair_value_to_price is not None
    assert report.relative.fair_value_to_price is not None
    assert report.market_implied_engine is not None


@pytest.mark.functional
def test_error_flow_invalid_ticker():
    # Functional test for handling missing data gracefully
    sec = Security(ticker="INVALID")
    pipeline = ValuationPipeline()
    report = pipeline.run(sec)

    # Should not crash, but verdict might be weak or N/A
    assert report is not None
    assert report.final_verdict.confidence_band == "LOW" or report.final_verdict.rating == "NEUTRAL"
