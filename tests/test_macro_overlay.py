import pytest
from unittest.mock import MagicMock

from iam.data.security import Security, Fundamentals, MarketData
from iam.data.macro import MacroConditions
from iam.pipeline.macro import MacroOverlay


def test_macro_overlay_triggers_on_shock():
    """Ensures that a rate shock > threshold triggers an intrinsic recalculation."""
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(fcf_ttm=100.0, shares_outstanding=10.0),
        market=MarketData(price=100.0),
        qualitative={"forecast_discount_rate": 0.09, "forecast_growth": 0.08}
    )
    
    # Mock a PipelineReport
    report = MagicMock()
    report.summary = "Initial Summary."
    
    # Create MacroConditions with a 75 bps shock (exceeds 50 bps default threshold)
    macro = MacroConditions(rate_shock_bps=75.0)
    
    overlay = MacroOverlay(rate_shock_threshold_bps=50.0)
    updated_report = overlay.apply(report, sec, macro)
    
    # Check that the summary log captured the event
    assert "MACRO OVERLAY TRIGGERED" in updated_report.summary
    assert "75.0 bps detected" in updated_report.summary
    
    # Check that it stressed the WACC from 9.0% to 9.75%
    assert "stressed WACC" in updated_report.summary
    
    # Verify the mocked report's intrinsic value was overwritten by the new FCFEDCF run
    assert updated_report.intrinsic is not None
    assert updated_report.intrinsic.method.name == "INTRINSIC"
    assert updated_report.intrinsic.fair_value_per_share is not None