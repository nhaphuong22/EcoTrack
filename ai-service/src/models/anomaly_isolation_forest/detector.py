import os
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

class IsolationForestAnomalyDetector:
    def __init__(self, artifact_path: str = "src/models/artifacts/isolation_forest_v1.joblib"):
        self.artifact_path = artifact_path
        self.model = None

    def train_or_load(self, df_with_residual: pd.DataFrame) -> None:
        """Trains or loads the Isolation Forest anomaly detector."""
        if os.path.exists(self.artifact_path):
            try:
                self.model = joblib.load(self.artifact_path)
                return
            except Exception:
                pass
                
        X = df_with_residual[ANOMALY_FEATURE_COLUMNS].fillna(0)
        
        self.model = IsolationForest(
            n_estimators=150,
            contamination=0.04,
            max_samples="auto",
            random_state=42
        )
        self.model.fit(X)
        
        os.makedirs(os.path.dirname(self.artifact_path), exist_ok=True)
        joblib.dump(self.model, self.artifact_path)

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
            norm_scores = np.zeros_like(raw_scores)
            
        df_out = df_with_residual.copy()
        df_out["anomaly_score"] = np.round(norm_scores, 3)
        
        # Anomaly thresholding logic (AD-1 & PRD FR-7)
        # Point is anomalous if normalized score > 0.68 or residual > 35% of predicted load
        is_anom = (df_out["anomaly_score"] >= 0.70) | (df_out["residual"] > 40.0)
        df_out["is_anomaly"] = is_anom.astype(bool)
        
        # Severity assignment
        def assign_severity(row):
            if not row["is_anomaly"]:
                return "Normal"
            score = row["anomaly_score"]
            res = row["residual"]
            if score >= 0.85 or res > 60.0:
                return "Critical"
            elif score >= 0.75 or res > 35.0:
                return "Medium"
            else:
                return "Low"
                
        df_out["severity"] = df_out.apply(assign_severity, axis=1)
        return df_out

# Singleton detector
anomaly_detector = IsolationForestAnomalyDetector()
