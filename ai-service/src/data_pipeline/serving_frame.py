import json
import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from src.config import get_data_path, get_models_dir, get_tariff_rate_usd, get_tariff_rate_vnd
from src.data_pipeline.inference_pipeline import EnergyInferencePipeline
from src.models.train_models import engineer_features, load_dataset

logger = logging.getLogger("ServingFrame")


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


_lock = threading.RLock()
_cached_base_df: Optional[pd.DataFrame] = None
_cached_meta: Optional[Dict[str, Any]] = None
_cached_hour_key: Optional[datetime] = None
_cached_serving_frame: Optional[pd.DataFrame] = None
_cached_xgb_model: Optional[Any] = None
_cached_iso_model: Optional[Any] = None
_cached_pipeline: Optional["EnergyInferencePipeline"] = None

FORECAST_HORIZON_HOURS = 24
_ZONE_SHARES: Dict[str, float] = {
    "z1": 0.08, "z2": 0.12, "z3": 0.09, "z4": 0.11, "z5": 0.10,
    "z6": 0.14, "z7": 0.07, "z8": 0.13, "z9": 0.06, "z10": 0.10,
}


def reset_serving_cache() -> None:
    """Clears all in-memory cached frames and model artifacts."""
    global _cached_base_df, _cached_meta, _cached_hour_key, _cached_serving_frame, _cached_xgb_model, _cached_iso_model, _cached_pipeline
    with _lock:
        _cached_base_df = None
        _cached_meta = None
        _cached_hour_key = None
        _cached_serving_frame = None
        _cached_xgb_model = None
        _cached_iso_model = None
        _cached_pipeline = None


def _mlflow_disabled() -> bool:
    """When ``ECOTRACK_DISABLE_MLFLOW`` is truthy, always serve from ``models_saved/``."""
    from src.mlops.config import mlflow_disabled

    return mlflow_disabled()


def _load_champion_forecaster_or_fallback(xgb_path: Path) -> Any:
    """
    Resolve the forecaster through the MLflow ``champion`` alias when MLflow is
    initialised (Story 4.5 FR23); otherwise load it from ``models_saved/``.

    Tri-state:
      * champion resolves + loads -> return the champion model,
      * MLflow not installed / not initialised / no champion alias -> fall back to
        ``xgb_path`` with a logged warning,
      * champion alias resolves but the artifact is broken / backend locked ->
        raise ``ModelArtifactError`` (-> 503 ERR_MODEL_NOT_FOUND), **no** fallback.
    """
    if not _mlflow_disabled():
        try:
            from src.mlops.tracking import (
                ChampionArtifactError,
                ChampionUnavailable,
                load_champion_forecaster,
            )

            model, version = load_champion_forecaster()
            logger.info("Serving forecaster from MLflow champion version %s.", version)
            return model
        except ChampionArtifactError as exc:
            # Alias resolved but the artifact is unusable: fail loud, do not mask.
            raise ModelArtifactError(
                f"Champion model version {exc.version} failed to load: {exc}",
                file_path=f"champion:{exc.version}",
            ) from exc
        except ChampionUnavailable as exc:
            logger.warning(
                "MLflow champion unavailable (%s); falling back to models_saved/ forecaster.", exc
            )
        except ModelArtifactError:
            raise
        except Exception as exc:  # mlops import / unexpected config error -> safe fallback
            logger.warning(
                "Champion resolution skipped (%s); falling back to models_saved/ forecaster.", exc
            )

    if not xgb_path.exists():
        raise ModelArtifactError(f"Model artifact not found: {xgb_path}", file_path=str(xgb_path))
    try:
        return joblib.load(xgb_path)
    except Exception as exc:
        raise ModelArtifactError(f"Failed to load model artifact: {exc}", file_path=str(xgb_path)) from exc


def _score_feature_df(
    df_feat: pd.DataFrame,
    metadata: Dict[str, Any],
    xgb_model: Any,
    iso_model: Any,
) -> pd.DataFrame:
    """Apply XGBoost predictions, 95% bounds, and Isolation Forest scores to an engineered DataFrame."""
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

    return pd.DataFrame({
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


def _load_model_artifacts(models_dir: Path) -> Tuple[Dict[str, Any], Any, Any]:
    xgb_path = models_dir / "xgboost_forecaster.joblib"
    iso_path = models_dir / "isolation_forest.joblib"
    meta_path = models_dir / "model_metadata.json"

    xgb_model = _load_champion_forecaster_or_fallback(xgb_path)

    for required_file in (iso_path, meta_path):
        if not required_file.exists():
            raise ModelArtifactError(f"Model artifact not found: {required_file}", file_path=str(required_file))

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        iso_model = joblib.load(iso_path)
    except Exception as e:
        raise ModelArtifactError(f"Failed to load model artifact: {e}", file_path=str(models_dir))

    return metadata, xgb_model, iso_model


def _ensure_artifacts_only() -> Tuple[Dict[str, Any], Any, Any, EnergyInferencePipeline]:
    global _cached_meta, _cached_xgb_model, _cached_iso_model, _cached_pipeline
    with _lock:
        if _cached_xgb_model is None or _cached_iso_model is None or _cached_meta is None:
            models_dir = get_models_dir()
            _cached_meta, _cached_xgb_model, _cached_iso_model = _load_model_artifacts(models_dir)
        if _cached_pipeline is None:
            _cached_pipeline = EnergyInferencePipeline(models_dir=get_models_dir())
        return _cached_meta, _cached_xgb_model, _cached_iso_model, _cached_pipeline


def _load_artifacts_and_base_frame(data_path: Path, models_dir: Path) -> Tuple[pd.DataFrame, Dict[str, Any], Any]:
    global _cached_iso_model
    if not data_path.exists():
        raise ServingDataError(f"Processed dataset not found at: {data_path}", path=str(data_path))

    metadata, xgb_model, iso_model = _load_model_artifacts(models_dir)
    _cached_iso_model = iso_model

    raw_df = load_dataset(data_path)
    df_feat = engineer_features(raw_df)
    base_df = _score_feature_df(df_feat, metadata, xgb_model, iso_model)

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
        matches = _cached_base_df[(ts.dt.day_of_week == target_weekday) & (ts.dt.hour == target_hour)]
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


def get_anomaly_events(frame: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """
    Extracts anomalous rows from the serving frame and maps each to an anomaly event dict.
    Returns events in reverse-chronological order (newest first).
    """
    if frame is None:
        frame = get_serving_frame()

    anom_rows = frame[frame["is_anomaly"]]
    tariff_vnd = get_tariff_rate_vnd()
    tariff_usd = get_tariff_rate_usd()

    events: List[Dict[str, Any]] = []
    for idx, row in anom_rows.iterrows():
        delta = max(0.0, float(row["meter_reading_kwh"]) - float(row["predicted_kwh"]))
        cost_vnd = delta * tariff_vnd
        cost_usd = delta * tariff_usd
        events.append({
            # A replay observation keeps its identity when its position changes.
            "id": "ANOM-" + hashlib.sha256(
                f"replay-v1|office_tower_01|{row['timestamp']}|{float(row['meter_reading_kwh'])}|{float(row['predicted_kwh'])}".encode()
            ).hexdigest()[:40],
            "building_id": "office_tower_01",
            "timestamp": str(row["timestamp"]),
            "subsystem": "Chiller & HVAC Plant",
            "severity": str(row["severity"]),
            "anomaly_score": float(row["anomaly_score"]),
            "actual_kwh": float(row["meter_reading_kwh"]),
            "predicted_kwh": float(row["predicted_kwh"]),
            "delta_kwh": delta,
            "outdoor_temp_c": float(row["outdoor_temperature_c"]),
            "estimated_waste_vnd": round(cost_vnd, 0),
            "estimated_waste_usd": round(cost_usd, 2),
            "status": "OPEN",
            "description": "Abnormal load deviation exceeding baseline prediction",
            "suggested_action": "Inspect chiller plant schedule and sub-meter power draw.",
            "reason": "Abnormal load deviation exceeding baseline prediction",
        })
    return events[::-1]


def _forecast_from_frame(
    frame: pd.DataFrame,
    xgb_model: Any,
    meta: Dict[str, Any],
    pipeline: EnergyInferencePipeline,
) -> pd.DataFrame:
    available = len(frame)
    if available < FORECAST_HORIZON_HOURS:
        raise InsufficientHistoryError(
            f"Insufficient history to forecast: need at least {FORECAST_HORIZON_HOURS} "
            f"hourly observations, got {available}.",
            available=available,
            required=FORECAST_HORIZON_HOURS,
        )

    rmse = float(meta["xgboost_metrics"]["rmse_kwh"])
    tail_n = min(len(frame), 48)
    tail_frame = frame.iloc[-tail_n:]
    tail_ts = pd.to_datetime(tail_frame["timestamp"], utc=True).dt.tz_convert(None)
    last_ts = tail_ts.iloc[-1]
    future_dt = [last_ts + pd.Timedelta(hours=h) for h in range(1, FORECAST_HORIZON_HOURS + 1)]

    recent_temps = tail_frame["outdoor_temperature_c"].to_numpy(dtype=float)
    temp_by_ts = dict(zip(tail_ts, recent_temps))
    future_temps: list = []
    for i, ts in enumerate(future_dt):
        prior_day_ts = ts - pd.Timedelta(hours=24)
        if prior_day_ts in temp_by_ts:
            future_temps.append(float(temp_by_ts[prior_day_ts]))
        else:
            future_temps.append(float(recent_temps[-FORECAST_HORIZON_HOURS + i]))

    recent_readings = pd.DataFrame({
        "timestamp": tail_ts.to_numpy(),
        "meter_reading_kwh": tail_frame["meter_reading_kwh"].to_numpy(dtype=float),
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


def predict_next_24h(now: Optional[datetime] = None) -> pd.DataFrame:
    """Produces a genuine 24-hour-ahead recursive forecast anchored on the serving frame."""
    frame = get_serving_frame(now)
    meta, xgb_model, _, pipeline = _ensure_artifacts_only()
    return _forecast_from_frame(frame, xgb_model, meta, pipeline)


def _prepare_hourly_live_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "meter_reading", "air_temperature"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
    df["meter_reading"] = pd.to_numeric(df["meter_reading_kwh"], errors="coerce")
    if "outdoor_temperature_c" in df.columns:
        df["air_temperature"] = pd.to_numeric(df["outdoor_temperature_c"], errors="coerce").fillna(26.0)
    else:
        df["air_temperature"] = 26.0
    df = df.dropna(subset=["timestamp", "meter_reading"]).sort_values("timestamp").reset_index(drop=True)
    return df[["timestamp", "meter_reading", "air_temperature"]]


def _calibrate_live_scale(
    raw_df: pd.DataFrame,
    meta: Dict[str, Any],
    xgb_model: Any,
    iso_model: Any,
) -> float:
    """Estimate live-vs-training scale ratio when a building's kWh differs materially from BDG2."""
    df_feat = engineer_features(raw_df)
    if df_feat.empty or len(raw_df) < 2:
        return 1.0
    obs_med = float(np.median(raw_df["meter_reading"]))
    if obs_med <= 0:
        return 1.0

    # Two fixed-point steps align lag inputs into XGBoost's trained manifold.
    scale = 1.0
    for step in range(2):
        scaled_df = raw_df.copy()
        scaled_df["meter_reading"] = scaled_df["meter_reading"] / scale
        feat = engineer_features(scaled_df)
        if feat.empty:
            return 1.0
        scored = _score_feature_df(feat, meta, xgb_model, iso_model)
        pred_med = float(np.median(scored["predicted_kwh"])) * scale
        if pred_med <= 0:
            return 1.0
        ratio = obs_med / pred_med
        if step == 0 and 0.85 <= ratio <= 1.18:
            return 1.0
        scale = float(np.clip(scale * ratio, 0.05, 5.0))
    return scale


def predict_next_24h_from_series(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Produces a 24-hour-ahead XGBoost forecast anchored on live DB hourly readings."""
    meta, xgb_model, iso_model, pipeline = _ensure_artifacts_only()
    clean = _prepare_hourly_live_df(rows)
    if clean.empty:
        return predict_next_24h()

    scale = _calibrate_live_scale(clean, meta, xgb_model, iso_model)
    norm_df = clean.copy()
    if scale != 1.0:
        norm_df["meter_reading"] = norm_df["meter_reading"] / scale
    frame = norm_df.rename(columns={"meter_reading": "meter_reading_kwh", "air_temperature": "outdoor_temperature_c"})
    fc = _forecast_from_frame(frame, xgb_model, meta, pipeline)

    # Also anchor against autoregressive drift if recursive horizon diverges from recent 24h median.
    obs_tail_med = float(np.median(clean["meter_reading"].tail(24)))
    raw_fc_med = float(np.median(fc["predicted_kwh"] * scale))
    drift_adj = 1.0
    if raw_fc_med > 0 and obs_tail_med > 0:
        r = obs_tail_med / raw_fc_med
        if r < 0.75 or r > 1.35:
            drift_adj = float(np.clip(r, 0.25, 4.0))
    eff = scale * drift_adj
    if eff != 1.0:
        rmse_scaled = float(meta["xgboost_metrics"]["rmse_kwh"]) * eff
        fc["predicted_kwh"] = (fc["predicted_kwh"] * eff).round(2)
        fc["lower_bound_95"] = np.maximum(0.0, fc["predicted_kwh"] - 1.96 * rmse_scaled).round(2)
        fc["upper_bound_95"] = (fc["predicted_kwh"] + 1.96 * rmse_scaled).round(2)
    return fc


def score_timeseries_from_series(rows: List[Dict[str, Any]], limit: int = 168) -> pd.DataFrame:
    """Score live hourly DB rows through XGBoost and Isolation Forest for chart overlay."""
    meta, xgb_model, iso_model, _ = _ensure_artifacts_only()
    raw_df = _prepare_hourly_live_df(rows)
    scale = _calibrate_live_scale(raw_df, meta, xgb_model, iso_model)
    norm_df = raw_df.copy()
    if scale != 1.0:
        norm_df["meter_reading"] = norm_df["meter_reading"] / scale
    df_feat = engineer_features(norm_df)
    if df_feat.empty:
        return get_serving_frame().tail(limit).reset_index(drop=True)
    scored = _score_feature_df(df_feat, meta, xgb_model, iso_model)
    if scale != 1.0:
        rmse_scaled = float(meta["xgboost_metrics"]["rmse_kwh"]) * scale
        scored["meter_reading_kwh"] = (scored["meter_reading_kwh"].to_numpy(dtype=float) * scale).round(2)
        scored["predicted_kwh"] = (scored["predicted_kwh"].to_numpy(dtype=float) * scale).round(2)
        scored["residual"] = (scored["meter_reading_kwh"] - scored["predicted_kwh"]).round(2)
        scored["lower_bound_95"] = np.maximum(0.0, scored["predicted_kwh"] - 1.96 * rmse_scaled).round(2)
        scored["upper_bound_95"] = (scored["predicted_kwh"] + 1.96 * rmse_scaled).round(2)
    scored["timestamp"] = pd.to_datetime(scored["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return scored.tail(limit).reset_index(drop=True)


def score_live_readings(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Score newly ingested meter readings using XGBoost expected load, Isolation Forest,
    and each meter's rolling baseline rate to detect real-time anomalies.
    """
    if not items:
        return []
    meta, xgb_model, iso_model, _ = _ensure_artifacts_only()

    # Optional hourly reference lookup from base dataset when building series is unavailable.
    with _lock:
        base_df = _cached_base_df
    tariff_vnd = get_tariff_rate_vnd()
    tariff_usd = get_tariff_rate_usd()

    min_score = float(meta["isolation_forest_metrics"]["anomaly_score_min"])
    max_score = float(meta["isolation_forest_metrics"]["anomaly_score_max"])
    xgb_cols = meta["xgb_features"]
    iso_cols = meta["iso_features"]

    events: List[Dict[str, Any]] = []
    for item in items:
        ts = pd.to_datetime(item["timestamp"], utc=True).tz_convert(None)
        hour = int(ts.hour)
        dayofweek = int(ts.day_of_week)
        is_weekend = int(dayofweek >= 5)
        hour_sin = float(np.sin(2.0 * np.pi * hour / 24.0))
        hour_cos = float(np.cos(2.0 * np.pi * hour / 24.0))
        temp_c = float(item.get("outdoor_temperature_c") if item.get("outdoor_temperature_c") is not None else 26.0)

        interval_s = float(item.get("interval_seconds") or 3600.0)
        interval_s = max(1.0, interval_s)
        raw_kwh = float(item["meter_reading_kwh"])
        hourly_kwh = max(0.0, raw_kwh * (3600.0 / interval_s))

        # Expected building-level hourly load from XGBoost when trailing lags are supplied,
        # else matching (dayofweek, hour) median from base frame, else 200.0 kWh/h.
        bldg_series = item.get("recent_building_hourly_kwhs") or []
        if len(bldg_series) >= 24:
            lag_1h = float(bldg_series[-1])
            lag_24h = float(bldg_series[-24])
            x_xgb = pd.DataFrame([{
                "air_temperature": temp_c, "hour": hour, "dayofweek": dayofweek,
                "is_weekend": is_weekend, "hour_sin": hour_sin, "hour_cos": hour_cos,
                "lag_1h": lag_1h, "lag_24h": lag_24h,
            }])[xgb_cols]
            predicted_bldg_kwh = max(10.0, float(xgb_model.predict(x_xgb)[0]))
        elif base_df is not None and not base_df.empty:
            ts_series = pd.to_datetime(base_df["timestamp"])
            matched = base_df[(ts_series.dt.day_of_week == dayofweek) & (ts_series.dt.hour == hour)]
            predicted_bldg_kwh = float(matched["meter_reading_kwh"].median()) if not matched.empty else float(base_df["meter_reading_kwh"].median())
        else:
            predicted_bldg_kwh = 200.0

        zone_id = item.get("zone_id")
        zone_share = _ZONE_SHARES.get(zone_id, 0.10 if zone_id else 1.0)
        meter_hist = [float(v) for v in (item.get("recent_meter_hourly_kwhs") or []) if isinstance(v, (int, float)) and np.isfinite(v) and v > 0]
        expected_meter_kwh = float(np.median(meter_hist)) if len(meter_hist) >= 3 else (predicted_bldg_kwh * zone_share)
        expected_meter_kwh = max(0.05, expected_meter_kwh)

        ratio = hourly_kwh / expected_meter_kwh
        scaled_bldg_kwh = ratio * predicted_bldg_kwh

        x_iso = pd.DataFrame([{
            "meter_reading": scaled_bldg_kwh,
            "air_temperature": temp_c,
            "hour": hour,
            "dayofweek": dayofweek,
            "is_weekend": is_weekend,
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "lag_1h": predicted_bldg_kwh,
            "lag_24h": predicted_bldg_kwh,
        }])[iso_cols]
        raw_decision = float(iso_model.decision_function(x_iso)[0])
        pred_label = int(iso_model.predict(x_iso)[0])
        norm_score = (
            float(np.clip((-raw_decision - min_score) / (max_score - min_score), 0.0, 1.0))
            if max_score > min_score else 0.5
        )
        iso_flagged = (pred_label == -1) and (ratio >= 1.25)
        if not (iso_flagged or ratio >= 1.6):
            continue

        delta_kwh = max(0.0, hourly_kwh - expected_meter_kwh)
        severity = "CRITICAL" if (ratio >= 2.0 or (iso_flagged and ratio >= 1.5)) else "MEDIUM"
        score = round(max(norm_score, 0.72 if severity == "CRITICAL" else 0.55), 4)
        iso_ts = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        bldg_id = item.get("building_id", "office_tower_01")
        zone_label = f"Khu vực {zone_id}" if zone_id else "Tổng tòa nhà"

        events.append({
            "building_id": bldg_id,
            "zone_id": zone_id,
            "meter_id": item.get("meter_id"),
            "timestamp": iso_ts,
            "subsystem": f"{zone_label} (Live)",
            "severity": severity,
            "anomaly_score": score,
            "actual_kwh": round(hourly_kwh, 3),
            "predicted_kwh": round(expected_meter_kwh, 3),
            "delta_kwh": round(delta_kwh, 3),
            "outdoor_temp_c": round(temp_c, 1),
            "estimated_waste_vnd": round(delta_kwh * tariff_vnd, 0),
            "estimated_waste_usd": round(delta_kwh * tariff_usd, 2),
            "description": f"Live load spike ({ratio:.2f}x expected rate) at {zone_label}",
            "suggested_action": f"Inspect HVAC and equipment draw in {zone_label}.",
        })
    return events
