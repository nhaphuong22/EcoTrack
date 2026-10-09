"""
Unit tests for the Story 1.4 forecast service: `predict_next_24h`.

Covers the genuine 24-hour-ahead recursive forecast, its 95% bounds sourced from
the held-out test-split RMSE, autoregressive chaining, and the error paths
(insufficient history -> 422 class, missing artifact -> ModelArtifactError).
"""
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import src.data_pipeline.serving_frame as sf
from src.config import get_models_dir
from src.data_pipeline.serving_frame import (
    InsufficientHistoryError,
    ModelArtifactError,
    get_serving_frame,
    predict_next_24h,
    reset_serving_cache,
)

FORECAST_COLUMNS = [
    "timestamp",
    "predicted_kwh",
    "lower_bound_95",
    "upper_bound_95",
    "outdoor_temperature_c",
]


def _load_rmse() -> float:
    meta_path = get_models_dir() / "model_metadata.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return float(meta["xgboost_metrics"]["rmse_kwh"])


def test_returns_24_rows_and_columns():
    """24 forward points with exactly the five contract columns."""
    df = predict_next_24h()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 24
    assert list(df.columns) == FORECAST_COLUMNS


def test_timestamps_increasing_and_after_last_observed():
    """Every forecast timestamp is strictly increasing, ISO-Z, and later than the last observed reading."""
    frame = get_serving_frame()
    last_observed = frame["timestamp"].iloc[-1]

    df = predict_next_24h()
    timestamps = list(df["timestamp"])

    assert all(ts.endswith("Z") for ts in timestamps)
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 24
    assert all(ts > last_observed for ts in timestamps)

    # Exactly one hour apart and starting one hour after the last observed hour.
    ts_series = pd.to_datetime(df["timestamp"])
    diffs = ts_series.diff().dropna()
    assert (diffs == pd.Timedelta(hours=1)).all()
    assert ts_series.iloc[0] == pd.to_datetime(last_observed) + pd.Timedelta(hours=1)


def test_future_temperatures_match_prior_day_proxy():
    """Daily-seasonal proxy: each point's temperature = serving frame's value at future_ts - 24h."""
    frame = get_serving_frame()
    temp_by_ts = dict(zip(pd.to_datetime(frame["timestamp"]), frame["outdoor_temperature_c"].astype(float)))

    df = predict_next_24h()
    assert np.isfinite(df["outdoor_temperature_c"].to_numpy(dtype=float)).all()

    for _, row in df.iterrows():
        prior_day_ts = pd.to_datetime(row["timestamp"]) - pd.Timedelta(hours=24)
        assert prior_day_ts in temp_by_ts, f"expected {prior_day_ts} present in serving frame"
        assert row["outdoor_temperature_c"] == pytest.approx(temp_by_ts[prior_day_ts], abs=1e-6)


def test_bounds_contain_prediction_and_floored():
    """lower <= predicted <= upper and lower bound floored at 0."""
    df = predict_next_24h()
    assert (df["lower_bound_95"] <= df["predicted_kwh"] + 1e-6).all()
    assert (df["predicted_kwh"] <= df["upper_bound_95"] + 1e-6).all()
    assert (df["lower_bound_95"] >= 0.0).all()


def test_bounds_width_ties_to_heldout_rmse():
    """Bounds use held-out test-split RMSE (metadata), not the in-sample residual_std=8.5."""
    rmse = _load_rmse()
    df = predict_next_24h()

    # Upper bound is never floored: upper - predicted == 1.96 * rmse for every point.
    upper_half = df["upper_bound_95"] - df["predicted_kwh"]
    assert np.allclose(upper_half, 1.96 * rmse, atol=1e-6)

    # For non-floored points, the full width is 2 * 1.96 * rmse.
    non_floored = df[df["lower_bound_95"] > 0.0]
    assert len(non_floored) > 0, "expected at least one non-floored lower bound"
    width = non_floored["upper_bound_95"] - non_floored["lower_bound_95"]
    assert np.allclose(width, 2 * 1.96 * rmse, atol=1e-6)

    # Guard against the deprecated in-sample convention.
    assert not np.allclose(upper_half, 1.96 * 8.5, atol=1e-6)


def test_autoregressive_chaining_feeds_lag_1h():
    """Step t's prediction feeds step t+1's lag_1h (recursive, not a flat repeat)."""
    # Warm the cache so the base frame, metadata and model are loaded.
    frame = get_serving_frame()
    last_reading = float(frame["meter_reading_kwh"].iloc[-1])

    class _IncrementModel:
        """Stub model: prediction = incoming lag_1h + 1.0, exposing the recursion."""
        def predict(self, X):
            return (X["lag_1h"].to_numpy(dtype=float) + 1.0)

    original_model = sf._cached_xgb_model
    try:
        sf._cached_xgb_model = _IncrementModel()
        df = predict_next_24h()
    finally:
        sf._cached_xgb_model = original_model
        reset_serving_cache()

    preds = df["predicted_kwh"].to_numpy(dtype=float)
    # Recursive chaining: each step's prediction = previous prediction + 1.0.
    # A flat repeat would give the same value every step (all diffs 0).
    diffs = np.diff(preds)
    assert np.allclose(diffs, 1.0, atol=1e-6), f"expected +1.0 per recursive step, got {diffs}"
    assert len(set(preds.tolist())) == 24  # not a flat repeat
    # Step 0 anchors on the last observed reading (pipeline rounds lag_1h to 2 decimals).
    assert preds[0] == pytest.approx(round(last_reading, 2) + 1.0, abs=1e-6)


def test_insufficient_history_raises():
    """A frame with fewer than 24 rows raises InsufficientHistoryError and trains/saves nothing."""
    # Warm the cache (model + metadata) so the short-history check is the only failure.
    get_serving_frame()

    short_frame = pd.DataFrame({
        "timestamp": [f"2026-01-01T{h:02d}:00:00Z" for h in range(10)],
        "meter_reading_kwh": [100.0 + h for h in range(10)],
        "outdoor_temperature_c": [20.0 + h for h in range(10)],
    })

    def _fake_frame(now=None):
        return short_frame

    original = sf.get_serving_frame
    try:
        sf.get_serving_frame = _fake_frame
        with pytest.raises(InsufficientHistoryError) as exc_info:
            predict_next_24h()
    finally:
        sf.get_serving_frame = original
        reset_serving_cache()

    assert exc_info.value.available == 10
    assert exc_info.value.required == 24
    assert "24" in str(exc_info.value)


def test_missing_artifact_raises_and_writes_no_file():
    """A missing XGBoost artifact surfaces ModelArtifactError and creates no file."""
    reset_serving_cache()
    with tempfile.TemporaryDirectory() as empty_dir:
        old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
        os.environ["ECOTRACK_MODELS_DIR"] = empty_dir
        try:
            with pytest.raises(ModelArtifactError) as exc_info:
                predict_next_24h()
            assert "xgboost_forecaster.joblib" in str(exc_info.value)
            assert len(os.listdir(empty_dir)) == 0, "no model should be trained or saved on error"
        finally:
            if old_models_dir is not None:
                os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
            else:
                os.environ.pop("ECOTRACK_MODELS_DIR", None)
            reset_serving_cache()
