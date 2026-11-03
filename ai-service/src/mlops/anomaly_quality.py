"""
Anomaly detector quality evaluation for EcoTrack (Story 4.7 — FR27).

Plain-Python module (AD-1, no FastAPI dependency): scores the served
Isolation Forest against `is_injected_anomaly` ground truth on the demo
scenarios, reporting precision, recall, F1 and false-positive rate. The
unmodified dataset carries no positive-class rows by construction, so it is
not evaluated here; FR27's "data with is_injected_anomaly labels" refers to
the scenario datasets themselves, which are the only ones that carry it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from src.models.train_models import ISO_FEATURE_COLUMNS, engineer_features

logger = logging.getLogger("MLOpsAnomalyQuality")

_ENGINEERED_MARKERS = ("lag_1h", "lag_24h", "hour_sin", "hour_cos")


def _ensure_engineered(df: pd.DataFrame) -> pd.DataFrame:
    """Runs engineer_features() when lag/calendar columns are absent, so a raw
    demo-scenario frame (timestamp, meter_reading, air_temperature,
    is_injected_anomaly) can be scored directly. `is_injected_anomaly` has no
    NaNs, so it survives engineer_features()'s dropna()/reset_index() row-wise,
    with no separate re-alignment needed."""
    if all(col in df.columns for col in _ENGINEERED_MARKERS):
        return df
    return engineer_features(df)


def evaluate(labeled_df: pd.DataFrame, iso_model: Any) -> Dict[str, Any]:
    """
    Scores `iso_model` against `labeled_df`'s `is_injected_anomaly` ground
    truth, returning precision, recall, F1 and false-positive rate.

    `labeled_df` must carry `is_injected_anomaly`; everything else needed for
    scoring (`ISO_FEATURE_COLUMNS`) is engineered automatically when absent.
    """
    if "is_injected_anomaly" not in labeled_df.columns:
        raise ValueError(
            "evaluate() requires a 'is_injected_anomaly' ground-truth column; "
            "got columns: " + ", ".join(labeled_df.columns)
        )
    engineered = _ensure_engineered(labeled_df)
    y_true = engineered["is_injected_anomaly"].astype(int).to_numpy()
    predictions = iso_model.predict(engineered[ISO_FEATURE_COLUMNS])
    y_pred = (predictions == -1).astype(int)

    negatives = y_true == 0
    false_positive_rate = float((y_pred[negatives] == 1).mean()) if negatives.any() else 0.0

    return {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "positive_count": int(y_true.sum()),
        "total_count": int(len(y_true)),
    }


def log_to_mlflow(results: Dict[str, Dict[str, Any]], model_path: Optional[str] = None) -> Optional[str]:
    """
    Logs a standalone MLflow run for the detector's quality evaluation.

    Deliberately does **not** go through `tracking.track_training_run` /
    champion registration -- Story 4.5 scoped the champion alias to the
    forecaster only. No-op (returns None) when mlflow is not installed,
    matching the project's no-MLflow dev/CI contract. `model_path`, when
    given, is tagged on the run so repeated evaluations over time can be
    traced back to the exact artifact file they scored.
    """
    from src.mlops.config import mlflow_available, mlflow_disabled

    if mlflow_disabled() or not mlflow_available():
        logger.info("MLflow disabled or not installed; skipping MLflow logging for anomaly quality.")
        return None

    import mlflow

    from src.mlops.tracking import configure

    configure()
    with mlflow.start_run(run_name="evaluate_isolation_forest") as run:
        if model_path:
            mlflow.set_tag("evaluated_model_path", str(model_path))
        for dataset_name, metrics in results.items():
            mlflow.log_metrics(
                {
                    f"{dataset_name}_{key}": value
                    for key, value in metrics.items()
                    if isinstance(value, (int, float))
                }
            )
        return run.info.run_id


def merge_into_metadata(metadata_path: Path, results: Dict[str, Dict[str, Any]]) -> None:
    """
    Read-modify-write `model_metadata.json`: adds/overwrites only the
    `isolation_forest_quality` key, leaving every other key (dataset_rows,
    xgboost_metrics, isolation_forest_metrics, ...) untouched.

    Writes to a sibling temp file and atomically replaces the original
    (`os.replace`), so a crash mid-write can never leave this git-tracked
    production artifact half-written.
    """
    import os

    metadata_path = Path(metadata_path)
    if not metadata_path.exists():
        raise FileNotFoundError(f"model_metadata.json not found at: {metadata_path}")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    metadata["isolation_forest_quality"] = results

    tmp_path = metadata_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    os.replace(tmp_path, metadata_path)
