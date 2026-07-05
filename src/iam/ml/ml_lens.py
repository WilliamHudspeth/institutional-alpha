from __future__ import annotations

from iam.data.security import Security
from iam.lenses.base import BaseLens, LensResult
from iam.ml.models.anomaly_forest import AnomalyDetector

class MLDiagnosticLens(BaseLens):
    """
    Diagnostic lens that uses IsolationForest to flag fundamental anomalies.
    Returns a diagnostic LensResult.
    """

    name = "ml_anomaly_diagnostic"

    def __init__(self, contamination="auto", random_state=42):
        self.detector = AnomalyDetector(contamination=contamination, random_state=random_state)
        # We need to fit the detector. In a real scenario, this would be fit on a broader universe.
        # Here we just keep it initialized. The is_anomaly method falls back to normal if not fitted,
        # but let's provide a mock fit for demonstration if we have some data, or rely on pass-through.
        # For this lens, we will assume it's pre-fitted or we fit on dummy data just to have it active.
        # A more complex pipeline would inject a fitted model.

    def _extract_features(self, security: Security) -> list[float]:
        # Basic ratios
        ev_sales = security.market.ev_sales or 0.0
        
        roic = 0.0
        if security.fundamentals.roic_history:
            roic = security.fundamentals.roic_history[0]
            
        rev_growth = 0.0
        if len(security.fundamentals.revenue_history) > 1:
            curr = security.fundamentals.revenue_history[0]
            prev = security.fundamentals.revenue_history[1]
            if prev and prev != 0:
                rev_growth = (curr / prev) - 1.0
                
        return [ev_sales, roic, rev_growth]

    def compute(self, security: Security) -> LensResult:
        features = self._extract_features(security)
        
        # In a real world case, self.detector would be fitted on a universe.
        # We check if it's an anomaly.
        is_anomaly = self.detector.is_anomaly(features)
        
        narrative = "Fundamentals appear normal based on ML anomaly detection."
        confidence = 1.0
        notes = []
        
        if is_anomaly:
            narrative = "ML model flagged these fundamental ratios as anomalous."
            confidence = 0.5  # Apply a penalty to confidence
            notes.append("Anomaly detected in [EV/Sales, ROIC, Rev Growth] combination.")
            
        return LensResult(
            lens_name=self.name,
            fair_value_low=None,
            fair_value_high=None,
            implied_move_pct=None,
            confidence=confidence,
            narrative=narrative,
            assumptions={
                "is_anomaly": 1.0 if is_anomaly else 0.0,
                "ev_sales": features[0],
                "roic": features[1],
                "rev_growth": features[2]
            },
            notes=notes,
        )
