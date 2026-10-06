from unittest.mock import patch

import numpy as np
import pytest

from iam.data.security import Security
from iam.ml.ml_lens import MLDiagnosticLens
from iam.ml.models.anomaly_forest import AnomalyDetector


def test_anomaly_detector_fallback():
    """Test that AnomalyDetector falls back gracefully when sklearn is absent."""
    with patch("iam.ml.models.anomaly_forest.SKLEARN_AVAILABLE", False):
        detector = AnomalyDetector()

        # Fit should not fail and should log/skip
        detector.fit([[1, 2], [3, 4]])
        assert not detector.is_fitted

        # Predict should return 1 (normal) for all samples
        preds = detector.predict([[10, 20], [30, 40]])
        assert np.array_equal(preds, [1, 1])

        # is_anomaly should return None when not fitted/sklearn absent
        assert detector.is_anomaly([1, 2]) is None


def test_anomaly_detector_with_sklearn():
    """Test AnomalyDetector with sklearn if available, or mock if not."""
    detector = AnomalyDetector(random_state=42)

    if not detector.model:
        pytest.skip("scikit-learn is not available")

    # Fit on some normal data
    X_train = np.random.normal(0, 0.1, (100, 3))
    detector.fit(X_train)

    assert detector.is_fitted

    # Predict on normal data
    X_normal = np.array([[0, 0, 0]])
    assert detector.is_anomaly(X_normal) is False

    # Predict on anomalous data
    X_anomaly = np.array([[10, -10, 20]])
    assert detector.is_anomaly(X_anomaly) is True


def test_ml_lens():
    """Test that MLDiagnosticLens extracts features correctly and handles anomaly output."""
    # Create a security object
    security = Security(ticker="TEST")
    security.market.ev_sales = 5.0
    security.fundamentals.roic_history = [0.15, 0.14]
    security.fundamentals.revenue_history = [110.0, 100.0]

    lens = MLDiagnosticLens()
    lens.detector.is_fitted = True

    with patch("iam.ml.models.anomaly_forest.SKLEARN_AVAILABLE", True):
        # Force the detector to consider this an anomaly
        with patch.object(lens.detector, "is_anomaly", return_value=True):
            res = lens.compute(security)
            assert res.confidence == 0.5
            assert res.assumptions["is_anomaly"] == 1.0
            assert res.assumptions["ev_sales"] == 5.0
            assert res.assumptions["roic"] == pytest.approx(0.15)
            assert res.assumptions["rev_growth"] == pytest.approx(0.10)
            assert "Anomaly detected" in res.notes[0]

        # Force the detector to consider this normal
        with patch.object(lens.detector, "is_anomaly", return_value=False):
            res = lens.compute(security)
            assert res.confidence == 1.0
            assert res.assumptions["is_anomaly"] == 0.0


def test_unfitted_lens_not_evaluated():
    security = Security(ticker="TEST")
    security.market.ev_sales = 5.0
    security.fundamentals.roic_history = [0.15]
    security.fundamentals.revenue_history = [110.0, 100.0]

    lens = MLDiagnosticLens()
    res = lens.compute(security)

    assert "normal" not in res.narrative.lower()
    assert res.confidence == 0.0
    assert res.assumptions.get("evaluated") == 0.0


def test_missing_feature_not_available():
    security = Security(ticker="TEST")
    # missing ev_sales
    security.market.ev_sales = None
    security.fundamentals.roic_history = [0.15]
    security.fundamentals.revenue_history = [110.0, 100.0]

    lens = MLDiagnosticLens()
    res = lens.compute(security)

    assert res.confidence == 0.0
    assert "not available" in res.narrative.lower()
    assert "ev_sales" in res.narrative
    assert res.assumptions.get("evaluated") == 0.0


def test_pipeline_no_lens_penalty():
    from iam.data.security import Security
    from iam.pipeline.orchestrator import ValuationPipeline

    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=ValueError("Offline"),
        ),
    ):
        pipeline = ValuationPipeline()
        sec = Security(ticker="AAPL")

        report = pipeline.run(sec)

        assert "Confidence reduced due to ML fundamental anomaly." not in report.relative.notes


def _priced_security():
    from iam.data.security import Fundamentals, MarketData, Security

    return Security(
        ticker="RELX",
        sector="Technology",
        industry="Software",
        fundamentals=Fundamentals(
            revenue_ttm=1_000.0,
            net_income_ttm=100.0,
            fcf_ttm=120.0,
            shares_outstanding=10.0,
            operating_margin=0.2,
            total_debt=50.0,
            cash_and_equivalents=20.0,
        ),
        market=MarketData(price=150.0, market_cap=1_500.0, pe_ttm=15.0, ev_ebitda=10.0, beta=1.1),
    )


def test_unavailable_ml_lens_leaves_relative_confidence_untouched():
    """Claude review: compare against a run with the ML step removed, not just a missing note.

    Before the orchestrator fix, an unavailable lens (confidence 0.0) multiplied relative
    valuation confidence by 0.
    """
    from iam.ml.ml_lens import MLDiagnosticLens
    from iam.pipeline.orchestrator import ValuationPipeline
    from iam.valuation.relative import RelativeValuation
    from iam.valuation.types import Method, ValuationResult

    def _fixed_relative(*_a, **_k):
        # A known relative result, so the test isolates what the ML step does to it.
        return ValuationResult(method=Method.RELATIVE, confidence=0.8, notes=[])

    with (
        patch("iam.data.markets.fetch_live_quote", return_value=None),
        patch(
            "iam.data.providers.yfinance_adapter.build_regression_inputs",
            side_effect=ValueError("offline"),
        ),
        patch.object(RelativeValuation, "compute", side_effect=_fixed_relative),
    ):
        report = ValuationPipeline().run(_priced_security())

    # The unfitted lens did not evaluate, so it must not touch relative confidence
    # (the old `confidence < 1.0` rule multiplied it by the lens's 0.0).
    assert report.relative.confidence == pytest.approx(0.8)
    assert not any("ML fundamental anomaly" in n for n in report.relative.notes)
    assert any("not available" in n for n in report.intrinsic.notes)
    assert MLDiagnosticLens().compute(_priced_security()).assumptions["evaluated"] == 0.0
