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


# ===========================================================================
# Elasticity-aware overlay (v0.5 theory-first stress testing)
# ===========================================================================


def _security_with_margins(gross_margin: float, operating_margin: float) -> Security:
    """A security whose elasticity profile is fully measurable."""
    return Security(
        ticker="TEST",
        fundamentals=Fundamentals(
            fcf_ttm=100.0,
            shares_outstanding=10.0,
            gross_margin=gross_margin,
            operating_margin=operating_margin,
        ),
        market=MarketData(price=100.0),
        qualitative={"forecast_discount_rate": 0.09, "forecast_growth": 0.08},
    )


def test_overlay_scales_gate_by_rate_elasticity():
    """A duration-bound business must trigger the overlay on a raw rate move
    below the nominal threshold, because the effective shock is scaled by its
    measured rate elasticity (> 1 for a growing FCFE stream)."""
    sec = _security_with_margins(gross_margin=0.70, operating_margin=0.10)

    from iam.elasticity import ElasticityScorer

    profile = ElasticityScorer().profile(sec)
    assert profile.rate_elasticity is not None and profile.rate_elasticity > 1.0

    # Choose a raw shock just below the threshold but above it after scaling.
    threshold = 50.0
    raw_bps = threshold / profile.rate_elasticity + 1.0
    assert raw_bps < threshold

    report = MagicMock()
    report.summary = ""
    stressed_intrinsic = MagicMock()
    stressed_intrinsic.notes = []
    mock_stress_engine = MagicMock()
    mock_stress_engine.run_stress_test.return_value = stressed_intrinsic

    overlay = MacroOverlay(intrinsic_dcf=MagicMock(), rate_shock_threshold_bps=threshold)
    overlay.stress_engine = mock_stress_engine
    updated = overlay.apply(report, sec, MacroConditions(rate_change=raw_bps / 10000.0))

    assert "MACRO OVERLAY TRIGGERED" in updated.summary
    assert "rate elasticity" in updated.summary


def test_overlay_applies_elasticity_scaled_shock():
    """The shock handed to the stress engine carries elasticity-scaled legs."""
    sec = _security_with_margins(gross_margin=0.70, operating_margin=0.10)

    from iam.data.macro import RATE_HIKE_SHOCK
    from iam.elasticity import ElasticityScorer

    profile = ElasticityScorer().profile(sec)

    report = MagicMock()
    report.summary = ""
    stressed_intrinsic = MagicMock()
    stressed_intrinsic.notes = []
    mock_stress_engine = MagicMock()
    mock_stress_engine.run_stress_test.return_value = stressed_intrinsic

    overlay = MacroOverlay(intrinsic_dcf=MagicMock(), rate_shock_threshold_bps=50.0)
    overlay.stress_engine = mock_stress_engine
    # +75bps with PMI >= 50 maps to the Rate Hike shock.
    overlay.apply(report, sec, MacroConditions(rate_change=0.0075, pmi=55.0))

    (_, shock), _ = mock_stress_engine.run_stress_test.call_args
    assert "elasticity-scaled" in shock.name
    assert shock.rate_shock_bps == RATE_HIKE_SHOCK.rate_shock_bps * profile.rate_elasticity
    assert shock.growth_shock_pct == RATE_HIKE_SHOCK.growth_shock_pct * profile.growth_elasticity


def test_overlay_attaches_stress_response_with_conviction_drift():
    """A triggered overlay must surface the theory-first StressResponse."""
    sec = _security_with_margins(gross_margin=0.70, operating_margin=0.10)
    # Volatile cash flows -> low durability -> high fragility -> real drift.
    sec.fundamentals.fcf_history = [100.0, 30.0, 160.0, 20.0]
    sec.fundamentals.operating_margin_history = [0.10, 0.30, 0.05, 0.25]

    report = MagicMock()
    report.summary = ""
    stressed_intrinsic = MagicMock()
    stressed_intrinsic.notes = []
    mock_stress_engine = MagicMock()
    mock_stress_engine.run_stress_test.return_value = stressed_intrinsic

    overlay = MacroOverlay(intrinsic_dcf=MagicMock(), rate_shock_threshold_bps=50.0)
    overlay.stress_engine = mock_stress_engine
    updated = overlay.apply(report, sec, MacroConditions(rate_change=0.0075, pmi=55.0))

    response = updated.stress_response
    assert response is not None
    assert response.value_change_pct is not None and response.value_change_pct < 0
    assert response.conviction_drift is not None and response.conviction_drift > 0
    assert response.durability.score is not None
    assert response.narrative in updated.summary


def test_overlay_falls_back_to_flat_shock_without_elasticity_inputs():
    """When the elasticity profile is unmeasurable the original flat-shock
    behavior is preserved: raw 75bps gates against the threshold unscaled."""
    sec = Security(
        ticker="TEST",
        fundamentals=Fundamentals(fcf_ttm=100.0, shares_outstanding=10.0),
        market=MarketData(price=100.0),
        # r <= g_terminal makes two_stage_pv return None -> no rate elasticity;
        # missing margins -> no growth elasticity -> confidence 0.
        qualitative={"forecast_discount_rate": 0.02, "forecast_growth": 0.08},
    )

    report = MagicMock()
    report.summary = ""
    stressed_intrinsic = MagicMock()
    stressed_intrinsic.notes = []
    mock_stress_engine = MagicMock()
    mock_stress_engine.run_stress_test.return_value = stressed_intrinsic

    overlay = MacroOverlay(intrinsic_dcf=MagicMock(), rate_shock_threshold_bps=50.0)
    overlay.stress_engine = mock_stress_engine
    updated = overlay.apply(report, sec, MacroConditions(rate_change=0.0075, pmi=55.0))

    assert "MACRO OVERLAY TRIGGERED" in updated.summary
    assert "Rate shock of 75.0 bps" in updated.summary

    (_, shock), _ = mock_stress_engine.run_stress_test.call_args
    assert "elasticity-scaled" not in shock.name
