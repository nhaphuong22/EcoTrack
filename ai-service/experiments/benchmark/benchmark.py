"""
Benchmark scoring engine for EcoTrack forecasting models.
Evaluates registered models against a held-out test partition,
measuring accuracy metrics (MAE, RMSE, MAPE, R2), training duration,
mean per-sample inference latency, and serialized model artifact size.
"""

from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score

from experiments.benchmark.models import BaseForecaster, get_registered_forecasters

BENCHMARK_COLUMNS: List[str] = [
    "model",
    "mae_kwh",
    "rmse_kwh",
    "mape_percent",
    "r2",
    "training_time_s",
    "mean_inference_latency_ms",
    "model_file_size_bytes",
    "train_window_hours",
]


def score_model(
    model: BaseForecaster,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Fits, evaluates, times, and serializes a single forecaster.

    Parameters:
    -----------
    model: BaseForecaster
        Forecaster instance to score.
    train_df: pd.DataFrame
        Chronological training partition (e.g. 80% split).
    test_df: pd.DataFrame
        Chronological test partition (e.g. 20% split).

    Returns:
    --------
    Dict[str, Any]:
        Dictionary containing all 9 standard benchmark columns.
    """
    # 1. Measure Training Time
    start_fit = time.perf_counter()
    model.fit(train_df)
    fit_duration_s = time.perf_counter() - start_fit

    # 2. Measure Inference Time & Latency
    test_count = len(test_df)
    start_pred = time.perf_counter()
    y_pred = model.predict(test_df)
    pred_duration_s = time.perf_counter() - start_pred

    mean_latency_ms = (pred_duration_s / test_count * 1000.0) if test_count > 0 else 0.0

    # 3. Compute Evaluation Metrics
    y_test = test_df["meter_reading"].to_numpy(dtype=float)
    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mape = float(mean_absolute_percentage_error(y_test, y_pred) * 100)
    r2 = float(r2_score(y_test, y_pred))

    # 4. Measure Serialized Model Artifact Size
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        joblib.dump(model, tmp_path)
        file_size_bytes = tmp_path.stat().st_size
    except Exception as e:
        raise RuntimeError(
            f"Failed to serialize model '{model.name}' for size measurement: {e}"
        ) from e
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    # Full-data models leave train_window_used as None and report the full train-row count;
    # windowed models (SARIMAX) report the rows they actually fitted on.
    train_window = model.train_window_used if model.train_window_used is not None else len(train_df)

    return {
        "model": str(model.name),
        "mae_kwh": float(mae),
        "rmse_kwh": float(rmse),
        "mape_percent": float(mape),
        "r2": float(r2),
        "training_time_s": float(fit_duration_s),
        "mean_inference_latency_ms": float(mean_latency_ms),
        "model_file_size_bytes": int(file_size_bytes),
        "train_window_hours": int(train_window),
    }


def run_scoring(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    models: Optional[List[BaseForecaster]] = None,
) -> pd.DataFrame:
    """
    Runs benchmark evaluation across all registered or provided forecasters.

    Parameters:
    -----------
    train_df: pd.DataFrame
        Training data partition.
    test_df: pd.DataFrame
        Test data partition.
    models: Optional[List[BaseForecaster]]
        Explicit list of models to evaluate. Defaults to all registered models.

    Returns:
    --------
    pd.DataFrame:
        Benchmark results table with columns matching BENCHMARK_COLUMNS.
    """
    models_to_evaluate = models if models is not None else get_registered_forecasters()

    rows: List[Dict[str, Any]] = []
    for model in models_to_evaluate:
        result = score_model(model=model, train_df=train_df, test_df=test_df)
        rows.append(result)

    results_df = pd.DataFrame(rows)
    return results_df[BENCHMARK_COLUMNS]
