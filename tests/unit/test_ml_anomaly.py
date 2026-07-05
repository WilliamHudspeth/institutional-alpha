import pytest
import numpy as np
from unittest.mock import patch

from iam.ml.models.anomaly_forest import AnomalyDetector
from iam.data.security import Security
from iam.ml.ml_lens import MLDiagnosticLens

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
        
        # is_anomaly should return False
        assert detector.is_anomaly([1, 2]) is False

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
    assert not detector.is_anomaly(X_normal)
    
    # Predict on anomalous data
    X_anomaly = np.array([[10, -10, 20]])
    assert detector.is_anomaly(X_anomaly)

def test_ml_lens():
    """Test that MLDiagnosticLens extracts features correctly and handles anomaly output."""
    # Create a security object
    security = Security(ticker="TEST")
    security.market.ev_sales = 5.0
    security.fundamentals.roic_history = [0.15, 0.14]
    security.fundamentals.revenue_history = [110.0, 100.0]
    
    lens = MLDiagnosticLens()
    
    # Force the detector to consider this an anomaly
    with patch.object(lens.detector, 'is_anomaly', return_value=True):
        res = lens.compute(security)
        assert res.confidence == 0.5
        assert res.assumptions["is_anomaly"] == 1.0
        assert res.assumptions["ev_sales"] == 5.0
        assert res.assumptions["roic"] == pytest.approx(0.15)
        assert res.assumptions["rev_growth"] == pytest.approx(0.10)
        assert "Anomaly detected" in res.notes[0]

    # Force the detector to consider this normal
    with patch.object(lens.detector, 'is_anomaly', return_value=False):
        res = lens.compute(security)
        assert res.confidence == 1.0
        assert res.assumptions["is_anomaly"] == 0.0
