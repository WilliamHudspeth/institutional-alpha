import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import IsolationForest
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn is not installed. AnomalyDetector will run in pass-through mode.")

class AnomalyDetector:
    def __init__(self, contamination="auto", random_state=42):
        self.contamination = contamination
        self.random_state = random_state
        self.model = None
        self.is_fitted = False
        
        if SKLEARN_AVAILABLE:
            self.model = IsolationForest(
                contamination=self.contamination, 
                random_state=self.random_state
            )

    def fit(self, X):
        """
        Fits the anomaly detector on the provided feature matrix X.
        X should be a numpy array or similar of shape (n_samples, n_features).
        """
        if not SKLEARN_AVAILABLE:
            logger.info("scikit-learn not available. Skipping fit.")
            return self

        try:
            self.model.fit(X)
            self.is_fitted = True
        except Exception as e:
            logger.error(f"Failed to fit IsolationForest: {e}")
            self.is_fitted = False
            
        return self

    def predict(self, X):
        """
        Predicts whether samples in X are anomalies.
        Returns 1 for normal, -1 for anomaly.
        If sklearn is not available or model is not fitted, returns 1 (normal) for all.
        """
        n_samples = np.array(X).shape[0] if hasattr(X, '__len__') else 1
        
        if not SKLEARN_AVAILABLE or not self.is_fitted:
            return np.ones(n_samples, dtype=int)

        try:
            return self.model.predict(X)
        except Exception as e:
            logger.error(f"Failed to predict with IsolationForest: {e}")
            return np.ones(n_samples, dtype=int)

    def is_anomaly(self, features):
        """
        Convenience method to check a single sample.
        Returns True if anomaly, False otherwise.
        """
        X = np.array(features).reshape(1, -1)
        pred = self.predict(X)
        return bool(pred[0] == -1)
