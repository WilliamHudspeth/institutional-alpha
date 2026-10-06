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

    def _extract_features(self, security: Security) -> list[float | None]:
        # Basic ratios
        ev_sales = security.market.ev_sales

        roic = None
        if security.fundamentals.roic_history:
            roic = security.fundamentals.roic_history[0]

        rev_growth = None
        if len(security.fundamentals.revenue_history) > 1:
            curr = security.fundamentals.revenue_history[0]
            prev = security.fundamentals.revenue_history[1]
            if curr is not None and prev is not None and prev != 0:
                rev_growth = (curr / prev) - 1.0

        return [ev_sales, roic, rev_growth]

    def compute(self, security: Security) -> LensResult:
        from iam.ml.models.anomaly_forest import SKLEARN_AVAILABLE

        features = self._extract_features(security)
        feature_names = ["ev_sales", "roic", "rev_growth"]
        missing_names = [name for name, val in zip(feature_names, features) if val is None]

        def make_assumptions(evaluated_val, is_anomaly_val=None):
            a = {"evaluated": evaluated_val}
            if is_anomaly_val is not None:
                a["is_anomaly"] = is_anomaly_val
            for k, v in zip(feature_names, features):
                if v is not None:
                    a[k] = v
            return a

        if missing_names:
            return LensResult(
                lens_name=self.name,
                fair_value_low=None,
                fair_value_high=None,
                implied_move_pct=None,
                confidence=0.0,
                narrative=f"ML anomaly check not available: missing inputs ({', '.join(missing_names)})",
                assumptions=make_assumptions(0.0),
                notes=[f"Missing inputs: {', '.join(missing_names)}"],
            )

        if not SKLEARN_AVAILABLE:
            return LensResult(
                lens_name=self.name,
                fair_value_low=None,
                fair_value_high=None,
                implied_move_pct=None,
                confidence=0.0,
                narrative="ML anomaly check not available: scikit-learn not installed",
                assumptions=make_assumptions(0.0),
                notes=["scikit-learn not installed"],
            )

        if not self.detector.is_fitted:
            return LensResult(
                lens_name=self.name,
                fair_value_low=None,
                fair_value_high=None,
                implied_move_pct=None,
                confidence=0.0,
                narrative="ML anomaly check not available: model not fitted (no training universe)",
                assumptions=make_assumptions(0.0),
                notes=["model not fitted (no training universe)"],
            )

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
            assumptions=make_assumptions(1.0, 1.0 if is_anomaly else 0.0),
            notes=notes,
        )
