import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from src.config import get_data_path, get_models_dir, get_tariff_rate_usd, get_tariff_rate_vnd
from src.data_pipeline.inference_pipeline import EnergyInferencePipeline
from src.models.train_models import engineer_features, load_dataset


class ServingDataError(Exception):
    """Raised when the input dataset cannot be found or read."""
    def __init__(self, message: str, path: str = ""):
        super().__init__(message)
        self.path = path


class ModelArtifactError(Exception):
    """Raised when a trained model artifact is missing or invalid."""
    def __init__(self, message: str, file_path: str = ""):
        super().__init__(message)
        self.file_path = file_path


class InsufficientHistoryError(Exception):
    """Raised when there are fewer than 24 hourly observations to forecast from."""
    def __init__(self, message: str, available: int = 0, required: int = 24):
        super().__init__(message)
        self.available = available
        self.required = required


_lock = threading.Lock()
_cached_base_df: Optional[pd.DataFrame] = None
_cached_meta: Optional[Dict[str, Any]] = None
_cached_hour_key: Optional[datetime] = None
_cached_serving_frame: Optional[pd.DataFrame] = None
_cached_xgb_model: Optional[Any] = None
_cached_pipeline: Optional["EnergyInferencePipeline"] = None

FORECAST_HORIZON_HOURS = 24


def reset_serving_cache() -> None:
    """Clears all in-memory cached frames and model artifacts."""
    global _cached_base_df, _cached_meta, _cached_hour_key, _cached_serving_frame, _cached_xgb_model, _cached_pipeline
    with _lock:
        _cached_base_df = None
        _cached_meta = None
        _cached_hour_key = None
        _cached_serving_frame = None
        _cached_xgb_model = None
        _cached_pipeline = None


def _load_artifacts_and_base_frame(data_path: Path, models_dir: Path) -> Tuple[pd.DataFrame, Dict[str, Any], Any]:
    if not data_path.exists():
        raise ServingDataError(f"Processed dataset not found at: {data_path}", path=str(data_path))

    xgb_path = models_dir / "xgboost_forecaster.joblib"
    iso_path = models_dir / "isolation_forest.joblib"
    meta_path = models_dir / "model_metadata.json"

    for required_file in (xgb_path, iso_path, meta_path):
        if not required_file.exists():
            raise ModelArtifactError(f"Model artifact not found: {required_file}", file_path=str(required_file))

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        xgb_model = joblib.load(xgb_path)
        iso_model = joblib.load(iso_path)
    except Exception as e:
        raise ModelArtifactError(f"Failed to load model artifact: {e}", file_path=str(models_dir))

    raw_df = load_dataset(data_path)
    df_feat = engineer_features(raw_df)

    xgb_cols = metadata["xgb_features"]
    iso_cols = metadata["iso_features"]

    predicted = xgb_model.predict(df_feat[xgb_cols])
    actual = df_feat["meter_reading"].values
    residual = actual - predicted

    rmse = float(metadata["xgboost_metrics"]["rmse_kwh"])
    lower_bound = np.maximum(0.0, predicted - 1.96 * rmse)
    upper_bound = predicted + 1.96 * rmse

    raw_decisions = iso_model.decision_function(df_feat[iso_cols])
    preds = iso_model.predict(df_feat[iso_cols])
    is_anom = (preds == -1)

    raw_scores = -raw_decisions
    min_score = float(metadata["isolation_forest_metrics"]["anomaly_score_min"])
    max_score = float(metadata["isolation_forest_metrics"]["anomaly_score_max"])
    if max_score > min_score:
        scaled_scores = (raw_scores - min_score) / (max_score - min_score)
    else:
        scaled_scores = np.zeros_like(raw_scores)
    anom_scores = np.clip(scaled_scores, 0.0, 1.0)

    critical_mask = is_anom & (actual > 1.30 * predicted)
    severity = np.where(~is_anom, "Normal", np.where(critical_mask, "Critical", "Medium"))

    base_df = pd.DataFrame({
        "timestamp": df_feat["timestamp"],
        "meter_reading_kwh": actual.astype(float),
        "outdoor_temperature_c": df_feat["air_temperature"].values.astype(float),
        "predicted_kwh": predicted.astype(float),
        "residual": residual.astype(float),
        "lower_bound_95": lower_bound.astype(float),
        "upper_bound_95": upper_bound.astype(float),
        "anomaly_score": anom_scores.astype(float),
        "is_anomaly": is_anom.astype(bool),
        "severity": severity,
    })

    return base_df, metadata, xgb_model


def get_serving_frame(now: Optional[datetime] = None) -> pd.DataFrame:
    """
    Returns the 720-hour serving window ending at the current UTC hour,
    replayed from the latest matching weekday/hour in the dataset.
    """
    global _cached_base_df, _cached_meta, _cached_hour_key, _cached_serving_frame, _cached_xgb_model

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    now_hour = now.replace(minute=0, second=0, microsecond=0)

    with _lock:
        if _cached_base_df is None:
            data_path = get_data_path()
            models_dir = get_models_dir()
            _cached_base_df, _cached_meta, _cached_xgb_model = _load_artifacts_and_base_frame(data_path, models_dir)

        if _cached_hour_key == now_hour and _cached_serving_frame is not None:
            return _cached_serving_frame

        target_weekday = now_hour.weekday()
        target_hour = now_hour.hour

        ts = _cached_base_df["timestamp"]
        matches = _cached_base_df[(ts.dt.weekday == target_weekday) & (ts.dt.hour == target_hour)]
        if matches.empty:
            raise ServingDataError(
                f"No matching row found for weekday {target_weekday} and hour {target_hour}",
                path=str(get_data_path()),
            )

        valid_matches = matches[matches.index >= 719]
        if not valid_matches.empty:
            end_idx = valid_matches.index[-1]
        else:
            end_idx = matches.index[-1]

        start_idx = max(0, end_idx - 720 + 1)
        slice_df = _cached_base_df.iloc[start_idx : end_idx + 1].copy()

        src_end_ts = slice_df["timestamp"].iloc[-1]
        delta = now_hour.replace(tzinfo=None) - src_end_ts
        shifted_ts = slice_df["timestamp"] + delta

        slice_df["timestamp"] = shifted_ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        slice_df = slice_df.reset_index(drop=True)

        _cached_hour_key = now_hour
        _cached_serving_frame = slice_df
        return slice_df


def compute_energy_metrics(frame: pd.DataFrame) -> Dict[str, Any]:
    """Computes aggregated 720-hour energy metrics using configured tariffs."""
    tariff_vnd = get_tariff_rate_vnd()
    tariff_usd = get_tariff_rate_usd()

    total_kwh = float(frame["meter_reading_kwh"].sum())
    peak_kw = float(frame["meter_reading_kwh"].max())
    baseline_kwh = float(frame["predicted_kwh"].sum())
    anom_count = int(frame["is_anomaly"].sum())

    waste_kwh = float(frame[frame["is_anomaly"]]["residual"].clip(lower=0).sum())
    waste_vnd = waste_kwh * tariff_vnd
    waste_usd = waste_kwh * tariff_usd

    return {
        "building_id": "office_tower_01",
        "total_consumption_kwh": round(total_kwh, 1),
        "peak_demand_kw": round(peak_kw, 1),
        "predicted_baseline_kwh": round(baseline_kwh, 1),
        "total_anomalies_detected": anom_count,
        "estimated_waste_kwh": round(waste_kwh, 1),
        "estimated_waste_cost_vnd": round(waste_vnd, 0),
        "estimated_waste_cost_usd": round(waste_usd, 2),
    }


def predict_next_24h(now: Optional[datetime] = None) -> pd.DataFrame:
    """
    Produces a genuine 24-hour-ahead recursive forecast anchored on the serving
    frame's last observed hour (the current UTC hour).

    The forecast covers exactly the 24 hours *after* the last observed reading.
    Predictions come from the trained XGBoost artifact driven recursively by
    ``EnergyInferencePipeline.predict_forecast_autoregressive`` (each step's
    prediction becomes the next step's ``lag_1h``). 95% bounds are
    ``predicted ± 1.96 × xgboost_metrics.rmse_kwh`` (held-out test-split RMSE),
    with the lower bound floored at 0.

    Future outdoor temperatures use a documented daily-seasonal proxy: each
    future hour reuses the serving frame's ``outdoor_temperature_c`` from the
    same hour on the previous day (``future_ts - 24h``).

    Returns a DataFrame of 24 rows with columns:
    ``timestamp`` (ISO 8601 UTC with ``Z``), ``predicted_kwh``,
    ``lower_bound_95``, ``upper_bound_95``, ``outdoor_temperature_c``.
    """
    global _cached_pipeline

    # Reuses the Story 1.1 serving cache (base frame + metadata + model loaded once).
    frame = get_serving_frame(now)

    with _lock:
        xgb_model = _cached_xgb_model
        meta = _cached_meta

    if xgb_model is None or meta is None:
        # Defensive: get_serving_frame populates both on success.
        raise ModelArtifactError("XGBoost model artifact is not loaded", file_path=str(get_models_dir()))

    available = len(frame)
    if available < FORECAST_HORIZON_HOURS:
        raise InsufficientHistoryError(
            f"Insufficient history to forecast: need at least {FORECAST_HORIZON_HOURS} "
            f"hourly observations, got {available}.",
            available=available,
            required=FORECAST_HORIZON_HOURS,
        )

    rmse = float(meta["xgboost_metrics"]["rmse_kwh"])

    # Parse the frame's ISO-Z timestamps once (vectorized) to stay off the per-request disk/CPU budget.
    frame_ts = pd.to_datetime(frame["timestamp"])

    # Anchor on the serving frame's last row = current UTC hour.
    last_ts = frame_ts.iloc[-1]

    # 24 future hourly timestamps: current_hour + 1 ... current_hour + 24.
    future_dt = [last_ts + pd.Timedelta(hours=h) for h in range(1, FORECAST_HORIZON_HOURS + 1)]

    # Future temperatures: same hour of the previous day (future_ts - 24h),
    # looked up from the serving frame. Documented daily-seasonal proxy.
    temp_by_ts = dict(zip(frame_ts, frame["outdoor_temperature_c"].astype(float)))
    recent_temps = frame["outdoor_temperature_c"].to_numpy(dtype=float)
    future_temps: list = []
    for i, ts in enumerate(future_dt):
        prior_day_ts = ts - pd.Timedelta(hours=24)
        if prior_day_ts in temp_by_ts:
            future_temps.append(float(temp_by_ts[prior_day_ts]))
        else:
            # Contiguous hourly frame ending at the anchor: the same-hour-prior-day
            # value is the i-th row of the trailing 24-hour window.
            future_temps.append(float(recent_temps[-FORECAST_HORIZON_HOURS + i]))

    # Build the pipeline once and reuse it; its constructor reads model_metadata.json
    # from disk, so a warm call must not re-instantiate it.
    with _lock:
        if _cached_pipeline is None:
            _cached_pipeline = EnergyInferencePipeline(models_dir=get_models_dir())
        pipeline = _cached_pipeline

    # The recursive helper only consults the trailing window (last 48 readings); pass a
    # compact slice with pre-parsed timestamps so the per-request work stays tiny.
    tail_n = min(len(frame), 48)
    recent_readings = pd.DataFrame({
        "timestamp": frame_ts.iloc[-tail_n:].to_numpy(),
        "meter_reading_kwh": frame["meter_reading_kwh"].iloc[-tail_n:].to_numpy(dtype=float),
    })

    forecast_df = pipeline.predict_forecast_autoregressive(
        xgb_model=xgb_model,
        recent_readings_df=recent_readings,
        future_timestamps=future_dt,
        future_temperatures=future_temps,
    )

    predicted = forecast_df["predicted_meter_reading"].to_numpy(dtype=float)
    lower_bound = np.maximum(0.0, predicted - 1.96 * rmse)
    upper_bound = predicted + 1.96 * rmse

    iso_timestamps = [ts.strftime("%Y-%m-%dT%H:%M:%SZ") for ts in future_dt]

    return pd.DataFrame({
        "timestamp": iso_timestamps,
        "predicted_kwh": predicted.astype(float),
        "lower_bound_95": lower_bound.astype(float),
        "upper_bound_95": upper_bound.astype(float),
        "outdoor_temperature_c": np.asarray(future_temps, dtype=float),
    })
