import os
import threading
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from typing import Dict, Any, List

ANOMALY_FEATURE_COLUMNS = [
    "meter_reading_kwh",
    "residual",
    "outdoor_temperature_c",
    "hour",
    "is_business_hour",
    "is_weekend"
]

DEFAULT_ARTIFACT_PATH = str(Path(__file__).resolve().parent.parent / "artifacts" / "isolation_forest_v1.joblib")


class IsolationForestAnomalyDetector:
    def __init__(self, artifact_path: str = DEFAULT_ARTIFACT_PATH):
        self.artifact_path = artifact_path
        self.model = None
        self._lock = threading.Lock()

    def train_or_load(self, df_with_residual: pd.DataFrame) -> None:
        """Thread-safe trains or loads the Isolation Forest anomaly detector."""
        with self._lock:
            # Double-checked locking
            if self.model is not None:
                return

            if os.path.exists(self.artifact_path):
                try:
                    self.model = joblib.load(self.artifact_path)
                    return
                except Exception:
                    pass

            X = df_with_residual[ANOMALY_FEATURE_COLUMNS].fillna(0)

            new_model = IsolationForest(
                n_estimators=150,
                contamination=0.04,
                max_samples="auto",
                random_state=42
            )
            # Fit on local reference before exposing to other threads
            new_model.fit(X)

            os.makedirs(os.path.dirname(self.artifact_path), exist_ok=True)
            joblib.dump(new_model, self.artifact_path)

            # Atomic publication
            self.model = new_model

    def detect_anomalies(self, df_with_residual: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates anomaly scores and assigns severity tiers.
        """
        if self.model is None:
            self.train_or_load(df_with_residual)

        X = df_with_residual[ANOMALY_FEATURE_COLUMNS].fillna(0)

        # decision_function yields negative values for outliers, positive for inliers
        raw_scores = self.model.decision_function(X)

        # Normalize into [0, 1] where higher = more anomalous
        min_s = np.min(raw_scores)
        max_s = np.max(raw_scores)
        if max_s > min_s:
            norm_scores = 1.0 - (raw_scores - min_s) / (max_s - min_s)
        else:
            norm_scores = np.zeros(len(raw_scores))

        df_out = df_with_residual.copy()
        df_out["anomaly_score"] = np.round(norm_scores, 4)

        # Rule-based thresholding & severity categorization
        high_threshold = 0.75
        med_threshold = 0.60

        is_high = df_out["anomaly_score"] >= high_threshold
        is_med = (df_out["anomaly_score"] >= med_threshold) & (~is_high)

        # Flag anomalies (High or Med severity)
        df_out["is_anomaly"] = is_high | is_med

        df_out["severity"] = "Normal"
        df_out.loc[is_med, "severity"] = "Medium"
        df_out.loc[is_high, "severity"] = "Critical"

        return df_out


# Global singleton instance
anomaly_detector = IsolationForestAnomalyDetector()
