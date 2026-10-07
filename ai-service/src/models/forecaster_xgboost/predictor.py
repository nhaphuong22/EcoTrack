import os
import threading
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    from sklearn.ensemble import GradientBoostingRegressor

from src.data_pipeline.feature_engineering import add_time_and_lag_features

FEATURE_COLUMNS = [
    "outdoor_temperature_c",
    "relative_humidity_pct",
    "sin_hour",
    "cos_hour",
    "sin_day",
    "cos_day",
    "is_business_hour",
    "is_weekend",
    "lag_1h",
    "lag_24h",
    "rolling_mean_24h"
]

DEFAULT_ARTIFACT_PATH = str(Path(__file__).resolve().parent.parent / "artifacts" / "xgboost_energy_v1.joblib")


class XGBoostEnergyForecaster:
    def __init__(self, artifact_path: str = DEFAULT_ARTIFACT_PATH):
        self.artifact_path = artifact_path
        self.model = None
        self.residual_std = 8.5  # Default residual standard deviation for 95% bounds
        self._lock = threading.Lock()

    def train_or_load(self, df: pd.DataFrame) -> None:
        """Thread-safe trains or loads the XGBoost regressor model."""
        with self._lock:
            # Double-checked locking
            if self.model is not None:
                return

            if os.path.exists(self.artifact_path):
                try:
                    bundle = joblib.load(self.artifact_path)
                    self.model = bundle["model"]
                    self.residual_std = bundle.get("residual_std", 8.5)
                    return
                except Exception:
                    pass

            df_feat = add_time_and_lag_features(df)
            X = df_feat[FEATURE_COLUMNS]
            y = df_feat["meter_reading_kwh"]

            if XGB_AVAILABLE:
                new_model = xgb.XGBRegressor(
                    n_estimators=120,
                    max_depth=5,
                    learning_rate=0.06,
                    subsample=0.85,
                    random_state=42
                )
            else:
                new_model = GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=4,
                    learning_rate=0.06,
                    random_state=42
                )

            # Fit on local reference to prevent exposing unfitted estimator to other threads
            new_model.fit(X, y)
            preds = new_model.predict(X)
            residual_std = float(np.std(y - preds))

            # Persist artifact
            os.makedirs(os.path.dirname(self.artifact_path), exist_ok=True)
            joblib.dump({"model": new_model, "residual_std": residual_std}, self.artifact_path)

            # Atomic publication: assign to instance only when completely fitted
            self.residual_std = residual_std
            self.model = new_model

    def predict_horizon(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Runs batch prediction over the dataframe to produce baseline and 95% confidence intervals.
        """
        if self.model is None:
            self.train_or_load(df)

        df_feat = add_time_and_lag_features(df)
        X = df_feat[FEATURE_COLUMNS]
        preds = self.model.predict(X)

        df_out = df.copy()
        df_out["predicted_kwh"] = np.round(preds, 2)
        df_out["residual"] = np.round(df_out["meter_reading_kwh"] - df_out["predicted_kwh"], 2)

        # 95% empirical confidence intervals (~ 1.96 * residual_std)
        margin = 1.96 * self.residual_std
        df_out["lower_bound_95"] = np.round(np.maximum(0, preds - margin), 2)
        df_out["upper_bound_95"] = np.round(preds + margin, 2)

        return df_out


# Global singleton instance
energy_forecaster = XGBoostEnergyForecaster()
