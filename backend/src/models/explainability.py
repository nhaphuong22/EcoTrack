"""
Explainable AI (XAI) Module for EcoTrack Energy Anomaly Detection.
Provides AnomalyExplainer using SHAP TreeExplainer on Isolation Forest models
to attribute root-cause feature importance for every flagged abnormal energy consumption.
"""

import logging
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import IsolationForest

from src.models.anomaly_isolation_forest.detector import (
    ANOMALY_FEATURE_COLUMNS,
    anomaly_detector,
)

logger = logging.getLogger("AnomalyExplainer")

FEATURE_DISPLAY_NAMES = {
    "meter_reading_kwh": "Điện năng tiêu thụ thực tế (kWh)",
    "residual": "Độ lệch so với dự báo baseline (kWh)",
    "outdoor_temperature_c": "Nhiệt độ môi trường bên ngoài (°C)",
    "hour": "Khung giờ trong ngày (0-23h)",
    "is_business_hour": "Giờ hành chính / Giờ làm việc",
    "is_weekend": "Ngày cuối tuần / Ngày nghỉ",
}


class AnomalyExplainer:
    """
    Explainable AI (XAI) engine for energy anomaly detection.
    Computes local feature attributions via SHAP TreeExplainer to explain
    why an energy consumption reading was flagged as anomalous.
    """

    def __init__(
        self,
        model: Optional[IsolationForest] = None,
        feature_names: Optional[List[str]] = None,
    ):
        self.feature_names = feature_names or ANOMALY_FEATURE_COLUMNS

        # Resolve model
        if model is not None:
            self.model = model
        elif anomaly_detector.model is not None:
            self.model = anomaly_detector.model
        else:
            # Fallback or initialize detector
            try:
                from src.data_pipeline.bdg2_loader import data_loader
                from src.models.forecaster_xgboost import energy_forecaster

                df = data_loader.get_or_create_data()
                df_fc = energy_forecaster.predict_horizon(df)
                anomaly_detector.train_or_load(df_fc)
                self.model = anomaly_detector.model
            except Exception as e:
                logger.warning("Could not auto-train detector for explainer: %s. Using default mock.", e)
                # Quick mock model for isolation
                mock_model = IsolationForest(n_estimators=50, random_state=42)
                mock_data = pd.DataFrame(np.zeros((10, len(self.feature_names))), columns=self.feature_names)
                mock_model.fit(mock_data)
                self.model = mock_model

        # Initialize TreeExplainer
        self.explainer = shap.TreeExplainer(self.model)
        self.expected_value = self.explainer.expected_value
        if isinstance(self.expected_value, np.ndarray):
            self.expected_value = float(self.expected_value[0])
        else:
            self.expected_value = float(self.expected_value)

    def _prepare_input_df(
        self, data: Union[pd.Series, pd.DataFrame, Dict[str, Any]]
    ) -> pd.DataFrame:
        """Standardizes input row into a pandas DataFrame matching feature columns."""
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, pd.Series):
            df = pd.DataFrame([data])
        elif isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            raise ValueError(f"Unsupported data type for explanation: {type(data)}")

        # Ensure all required features are present
        for col in self.feature_names:
            if col not in df.columns:
                df[col] = 0.0

        return df[self.feature_names].fillna(0.0)

    def explain_instance(
        self,
        instance: Union[pd.Series, pd.DataFrame, Dict[str, Any]],
        top_k: int = 3,
    ) -> Dict[str, Any]:
        """
        Computes SHAP feature attributions for a single telemetry point.

        Args:
            instance: Telemetry point with features (or dictionary/Series).
            top_k: Number of most impactful features to highlight.

        Returns:
            Dictionary containing:
            - shap_values: Mapping of feature -> shap value
            - feature_values: Mapping of feature -> observed value
            - top_contributing_features: Ordered list of top features with metadata
            - summary_explanation: Natural language explanation string
            - base_value: Baseline expected model output
        """
        X = self._prepare_input_df(instance)
        raw_shap = self.explainer.shap_values(X)

        if isinstance(raw_shap, list):
            sample_shap = raw_shap[0][0]
        elif isinstance(raw_shap, np.ndarray):
            sample_shap = raw_shap[0]
        else:
            sample_shap = np.array(raw_shap)[0]

        row_vals = X.iloc[0].to_dict()
        shap_dict = {
            feat: float(sample_shap[i]) for i, feat in enumerate(self.feature_names)
        }

        # Rank by absolute impact on anomaly decision
        sorted_features = sorted(
            shap_dict.items(), key=lambda item: abs(item[1]), reverse=True
        )

        top_contributing = []
        explanation_bullets = []

        for feat_name, shap_val in sorted_features[:top_k]:
            actual_val = float(row_vals.get(feat_name, 0.0))
            display_name = FEATURE_DISPLAY_NAMES.get(feat_name, feat_name)

            # Impact direction: negative shap values in TreeExplainer for Isolation Forest
            # indicate shorter path lengths / higher anomaly contribution
            direction = "Tăng độ bất thường (Anomaly Driver)" if shap_val < 0 else "Giảm độ bất thường (Normalizing)"

            top_contributing.append(
                {
                    "feature": feat_name,
                    "display_name": display_name,
                    "actual_value": round(actual_val, 2),
                    "shap_value": round(shap_val, 4),
                    "impact_direction": direction,
                }
            )

            explanation_bullets.append(
                f"{display_name} = {round(actual_val, 1)} (SHAP: {round(shap_val, 4)})"
            )

        summary_explanation = (
            f"Điểm đo có sự đóng góp lớn nhất từ {top_k} đặc trưng: "
            + "; ".join(explanation_bullets)
            + "."
        )

        return {
            "shap_values": shap_dict,
            "feature_values": {k: round(float(v), 2) for k, v in row_vals.items()},
            "top_contributing_features": top_contributing,
            "summary_explanation": summary_explanation,
            "base_value": round(self.expected_value, 4),
        }

    def explain_batch(
        self,
        df: pd.DataFrame,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """Computes explanations for a batch of telemetry records."""
        X = self._prepare_input_df(df)
        raw_shap = self.explainer.shap_values(X)

        if isinstance(raw_shap, list):
            matrix = raw_shap[0]
        else:
            matrix = raw_shap

        results = []
        for row_idx in range(len(X)):
            sample_shap = matrix[row_idx]
            row_vals = X.iloc[row_idx].to_dict()
            shap_dict = {
                feat: float(sample_shap[i]) for i, feat in enumerate(self.feature_names)
            }
            sorted_features = sorted(
                shap_dict.items(), key=lambda item: abs(item[1]), reverse=True
            )

            top_contributing = [
                {
                    "feature": feat_name,
                    "display_name": FEATURE_DISPLAY_NAMES.get(feat_name, feat_name),
                    "actual_value": round(float(row_vals.get(feat_name, 0.0)), 2),
                    "shap_value": round(float(shap_val), 4),
                }
                for feat_name, shap_val in sorted_features[:top_k]
            ]

            results.append(
                {
                    "row_index": row_idx,
                    "shap_values": shap_dict,
                    "top_contributing_features": top_contributing,
                }
            )
        return results

    def get_global_feature_importance(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Computes mean absolute SHAP values across the dataset
        representing global feature importance.
        """
        X = self._prepare_input_df(df)
        raw_shap = self.explainer.shap_values(X)
        if isinstance(raw_shap, list):
            matrix = raw_shap[0]
        else:
            matrix = raw_shap

        mean_abs_shap = np.mean(np.abs(matrix), axis=0)
        importance_dict = {
            feat: round(float(mean_abs_shap[i]), 4)
            for i, feat in enumerate(self.feature_names)
        }
        return dict(
            sorted(importance_dict.items(), key=lambda item: item[1], reverse=True)
        )


# Singleton instance
anomaly_explainer = AnomalyExplainer()
