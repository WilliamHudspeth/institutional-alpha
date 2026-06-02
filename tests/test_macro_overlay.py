from unittest.mock import MagicMock

from iam.data.macro import MacroConditions
from iam.data.security import Fundamentals, MarketData, Security
from iam.pipeline.macro import MacroOverlay


def test_macro_overlay_triggers_on_shock():
    """Ensures that a rate shock > threshold triggers an intrinsic recalculation."""
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(fcf_ttm=100.0, shares_outstanding=10.0),
        market=MarketData(price=100.0),
        qualitative={"forecast_discount_rate": 0.09, "forecast_growth": 0.08},
    )

    report = MagicMock()
    report.summary = "Initial Summary."

    # Mock the stressed intrinsic valuation result with a notes list
    stressed_intrinsic = MagicMock()
    stressed_intrinsic.notes = []

    # Mock the stress engine to return the stressed intrinsic
    mock_dcf = MagicMock()
    mock_stress_engine = MagicMock()
    mock_stress_engine.run_stress_test.return_value = stressed_intrinsic

    # 75 bps expressed as a decimal (0.0075); threshold is 50 bps
    macro = MacroConditions(rate_change=0.0075)

    overlay = MacroOverlay(intrinsic_dcf=mock_dcf, rate_shock_threshold_bps=50.0)
    overlay.stress_engine = mock_stress_engine
    updated_report = overlay.apply(report, sec, macro)

    assert "Macro Overlay triggered" in str(updated_report.intrinsic.notes)
    assert updated_report.intrinsic is stressed_intrinsic


def test_macro_overlay_no_trigger_below_threshold():
    """Ensures that a rate change below the threshold leaves the report untouched."""
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(fcf_ttm=100.0, shares_outstanding=10.0),
        market=MarketData(price=100.0),
        qualitative={"forecast_discount_rate": 0.09, "forecast_growth": 0.08},
    )

    report = MagicMock()
    report.summary = "Initial Summary."
    original_intrinsic = report.intrinsic

    # 25 bps -- below the 50 bps threshold
    macro = MacroConditions(rate_change=0.0025)

    overlay = MacroOverlay(intrinsic_dcf=MagicMock(), rate_shock_threshold_bps=50.0)
    updated_report = overlay.apply(report, sec, macro)

    assert "within tolerance" in updated_report.summary
    assert updated_report.intrinsic is original_intrinsic
