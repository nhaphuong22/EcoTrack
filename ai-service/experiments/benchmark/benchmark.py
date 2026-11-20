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

# Per-horizon (Story 4.4) output schemas.
DEFAULT_HORIZON = 24
HORIZON_COLUMNS: List[str] = ["model", "horizon_h", "mae_kwh", "rmse_kwh"]
PREDICTION_COLUMNS: List[str] = [
    "model",
    "origin_timestamp",
    "horizon_h",
    "target_timestamp",
    "actual",
    "prediction",
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


def score_grid(
    model_name: str,
    grid: np.ndarray,
    test_df: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON,
) -> tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    Turns one model's per-origin forecast grid (shape (len(test_df), horizon)) into
    per-horizon MAE/RMSE rows and a long-format predictions frame.

    For horizon h, the scored pairs are every origin p with a target at position p + h
    inside the test span (span-edge origins contribute only their in-range horizons;
    ``np.nan`` grid cells are dropped, never counted). Returns (horizon_rows, predictions_df).
    """
    n = len(test_df)
    timestamps = test_df["timestamp"].to_numpy()
    actual = test_df["meter_reading"].to_numpy(dtype=float)

    horizon_rows: List[Dict[str, Any]] = []
    model_parts: List[np.ndarray] = []
    origin_parts: List[np.ndarray] = []
    horizon_parts: List[np.ndarray] = []
    target_parts: List[np.ndarray] = []
    actual_parts: List[np.ndarray] = []
    pred_parts: List[np.ndarray] = []

    for h in range(1, horizon + 1):
        if h >= n:
            break
        target_pos = np.arange(h, n)  # target positions q
        origin_pos = target_pos - h  # origins p
        preds = grid[origin_pos, h - 1]
        acts = actual[target_pos]

        # Drop any cell with a NaN prediction (span-edge) or a NaN actual so MAE/RMSE stay
        # finite — the "no NaN in results_by_horizon" contract covers both sides of the pair.
        valid = ~np.isnan(preds) & ~np.isnan(acts)
        if not valid.any():
            continue

        p_valid = preds[valid]
        a_valid = acts[valid]
        mae = float(mean_absolute_error(a_valid, p_valid))
        rmse = float(np.sqrt(mean_squared_error(a_valid, p_valid)))
        horizon_rows.append(
            {"model": model_name, "horizon_h": int(h), "mae_kwh": mae, "rmse_kwh": rmse}
        )

        count = int(valid.sum())
        model_parts.append(np.full(count, model_name, dtype=object))
        origin_parts.append(timestamps[origin_pos[valid]])
        horizon_parts.append(np.full(count, h, dtype=int))
        target_parts.append(timestamps[target_pos[valid]])
        actual_parts.append(a_valid)
        pred_parts.append(p_valid)

    if model_parts:
        predictions_df = pd.DataFrame(
            {
                "model": np.concatenate(model_parts),
                "origin_timestamp": np.concatenate(origin_parts),
                "horizon_h": np.concatenate(horizon_parts),
                "target_timestamp": np.concatenate(target_parts),
                "actual": np.concatenate(actual_parts),
                "prediction": np.concatenate(pred_parts),
            }
        )
    else:
        predictions_df = pd.DataFrame(columns=PREDICTION_COLUMNS)

    return horizon_rows, predictions_df[PREDICTION_COLUMNS]


def run_horizon_scoring(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON,
    models: Optional[List[BaseForecaster]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Rolling-origin per-horizon evaluation for the Story 4.4 report (FR46).

    Fits each registered (or provided) forecaster on ``train_df`` and asks it for a
    per-origin forecast grid over ``test_df`` under the shared protocol (recursive for
    lag models, native multi-step for SARIMAX/LSTM, observed lag_24h for seasonal-naive).
    Returns (results_by_horizon, predictions):
      - results_by_horizon: one row per (model, horizon) with MAE/RMSE (HORIZON_COLUMNS).
      - predictions: long-format per-timestamp forecasts (PREDICTION_COLUMNS) for the charts.

    This refits the models independently of :func:`run_scoring` so the hour-1 ``results.csv``
    path is untouched.
    """
    models_to_evaluate = models if models is not None else get_registered_forecasters()

    horizon_rows: List[Dict[str, Any]] = []
    prediction_frames: List[pd.DataFrame] = []
    for model in models_to_evaluate:
        model.fit(train_df)
        grid = model.forecast_grid(test_df, horizon=horizon)
        rows, preds = score_grid(model.name, grid, test_df, horizon=horizon)
        horizon_rows.extend(rows)
        prediction_frames.append(preds)

    results_by_horizon = pd.DataFrame(horizon_rows, columns=HORIZON_COLUMNS)
    if prediction_frames:
        predictions = pd.concat(prediction_frames, ignore_index=True)
    else:
        predictions = pd.DataFrame(columns=PREDICTION_COLUMNS)

    return results_by_horizon[HORIZON_COLUMNS], predictions[PREDICTION_COLUMNS]
