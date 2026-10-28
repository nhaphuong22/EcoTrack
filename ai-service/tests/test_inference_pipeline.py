"""
Unit tests for EcoTrack Inference Feature Pipeline:
- Validates that extracted features match model_metadata.json specifications exactly
- Validates forecast feature matrix structure, column order, data types, and absence of NaNs
- Validates anomaly detection feature matrix and handling of historical context
- Validates seamless prediction execution against saved .joblib models
"""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from src.data_pipeline.inference_pipeline import EnergyInferencePipeline


@pytest.fixture(scope="session")
def model_metadata():
    """Loads feature definitions from model_metadata.json."""
    backend_dir = Path(__file__).resolve().parents[1]
    meta_path = backend_dir / "models_saved" / "model_metadata.json"
    assert meta_path.exists(), f"model_metadata.json not found at: {meta_path}"

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return meta


@pytest.fixture(scope="session")
def inference_pipeline():
    """Initializes singleton instance of EnergyInferencePipeline."""
    return EnergyInferencePipeline()


@pytest.fixture(scope="session")
def saved_models():
    """Loads trained estimators from models_saved directory."""
    backend_dir = Path(__file__).resolve().parents[1]
    models_dir = backend_dir / "models_saved"
    xgb_path = models_dir / "xgboost_forecaster.joblib"
    iso_path = models_dir / "isolation_forest.joblib"

    models = {}
    if xgb_path.exists():
        models["xgboost"] = joblib.load(xgb_path)
    if iso_path.exists():
        models["isolation_forest"] = joblib.load(iso_path)
    return models


@pytest.fixture
def sample_recent_readings():
    """Generates 30 hourly historical readings."""
    timestamps = pd.date_range("2026-05-01 00:00:00", periods=30, freq="1h")
    np.random.seed(101)
    df = pd.DataFrame({
        "timestamp": timestamps,
        "meter_reading": np.random.uniform(250.0, 750.0, size=len(timestamps)),
        "air_temperature": np.random.uniform(18.0, 32.0, size=len(timestamps)),
    })
    return df


@pytest.fixture
def sample_future_inputs():
    """Generates 24 future timestamps and corresponding forecasted temperatures."""
    future_timestamps = pd.date_range("2026-05-02 06:00:00", periods=24, freq="1h")
    np.random.seed(202)
    future_temperatures = np.round(np.random.uniform(20.0, 35.0, size=24), 1)
    return future_timestamps, future_temperatures


def test_pipeline_initialization_matches_metadata(inference_pipeline, model_metadata):
    """Verify that feature lists in pipeline exactly match model_metadata.json."""
    expected_xgb = model_metadata["xgb_features"]
    expected_iso = model_metadata["iso_features"]

    assert inference_pipeline.xgb_features == expected_xgb, "XGB feature list mismatch"
    assert inference_pipeline.iso_features == expected_iso, "ISO feature list mismatch"
    assert len(inference_pipeline.xgb_features) == 8
    assert len(inference_pipeline.iso_features) == 9


def test_prepare_forecast_features_columns_and_types(
    inference_pipeline, model_metadata, sample_recent_readings, sample_future_inputs
):
    """Verify X_forecast column count, column names, ordering, and data types."""
    future_ts, future_temps = sample_future_inputs
    X_forecast = inference_pipeline.prepare_forecast_features(
        recent_readings_df=sample_recent_readings,
        future_timestamps=future_ts,
        future_temperatures=future_temps,
    )

    expected_cols = model_metadata["xgb_features"]

    # 1. Column count and exact name matching
    assert len(X_forecast.columns) == len(expected_cols)
    assert list(X_forecast.columns) == expected_cols

    # 2. Output row count
    assert len(X_forecast) == len(future_ts)

    # 3. Numeric types
    for col in expected_cols:
        assert pd.api.types.is_numeric_dtype(X_forecast[col]), f"Column {col} is not numeric"


def test_prepare_forecast_features_no_nan(
    inference_pipeline, sample_recent_readings, sample_future_inputs
):
    """Verify that X_forecast contains zero NaN or Inf values with sufficient history."""
    future_ts, future_temps = sample_future_inputs
    X_forecast = inference_pipeline.prepare_forecast_features(
        recent_readings_df=sample_recent_readings,
        future_timestamps=future_ts,
        future_temperatures=future_temps,
    )

    assert X_forecast.isna().sum().sum() == 0, "X_forecast contains NaN values"
    assert not np.isinf(X_forecast.values).any(), "X_forecast contains infinite values"


def test_prepare_forecast_features_insufficient_history(
    inference_pipeline, sample_future_inputs
):
    """Verify ValueError is raised when recent_readings_df has fewer than 24 rows."""
    short_readings = pd.DataFrame({
        "timestamp": pd.date_range("2026-05-01 00:00:00", periods=15, freq="1h"),
        "meter_reading": np.random.uniform(100, 200, 15),
    })
    future_ts, future_temps = sample_future_inputs

    with pytest.raises(ValueError, match="at least 24 observations"):
        inference_pipeline.prepare_forecast_features(
            recent_readings_df=short_readings,
            future_timestamps=future_ts,
            future_temperatures=future_temps,
        )


def test_prepare_anomaly_features_columns_and_types(
    inference_pipeline, model_metadata
):
    """Verify X_anomaly column count, column names, ordering, and data types."""
    timestamps = pd.date_range("2026-05-01 00:00:00", periods=48, freq="1h")
    data_df = pd.DataFrame({
        "timestamp": timestamps,
        "meter_reading": np.random.uniform(300.0, 700.0, size=len(timestamps)),
        "air_temperature": np.random.uniform(22.0, 34.0, size=len(timestamps)),
    })

    X_anomaly = inference_pipeline.prepare_anomaly_features(data_df=data_df)
    expected_cols = model_metadata["iso_features"]

    # 1. Column count and exact name matching
    assert len(X_anomaly.columns) == len(expected_cols)
    assert list(X_anomaly.columns) == expected_cols

    # 2. Dropping initial 24 lag NaNs leaves 24 rows
    assert len(X_anomaly) == 48 - 24

    # 3. Numeric types
    for col in expected_cols:
        assert pd.api.types.is_numeric_dtype(X_anomaly[col]), f"Column {col} is not numeric"


def test_prepare_anomaly_features_no_nan(inference_pipeline):
    """Verify that X_anomaly contains zero NaN values."""
    timestamps = pd.date_range("2026-05-01 00:00:00", periods=50, freq="1h")
    data_df = pd.DataFrame({
        "timestamp": timestamps,
        "meter_reading": np.linspace(200, 600, 50),
        "air_temperature": np.linspace(15, 30, 50),
    })

    X_anomaly = inference_pipeline.prepare_anomaly_features(data_df=data_df)
    assert X_anomaly.isna().sum().sum() == 0, "X_anomaly contains NaN values"


def test_prepare_anomaly_features_with_historical_context(
    inference_pipeline, model_metadata
):
    """Verify seamless feature generation for new batch using historical context."""
    hist_df = pd.DataFrame({
        "timestamp": pd.date_range("2026-05-01 00:00:00", periods=24, freq="1h"),
        "meter_reading": np.random.uniform(300, 600, 24),
        "air_temperature": np.random.uniform(20, 30, 24),
    })
    new_data = pd.DataFrame({
        "timestamp": pd.date_range("2026-05-02 00:00:00", periods=6, freq="1h"),
        "meter_reading": [450.0, 480.0, 520.0, 560.0, 590.0, 610.0],
        "air_temperature": [24.0, 24.5, 25.0, 26.0, 27.5, 29.0],
    })

    X_anomaly = inference_pipeline.prepare_anomaly_features(
        data_df=new_data,
        historical_context_df=hist_df,
    )

    # All 6 target points preserved without dropping
    assert len(X_anomaly) == 6
    assert list(X_anomaly.columns) == model_metadata["iso_features"]
    assert X_anomaly.isna().sum().sum() == 0


def test_end_to_end_predictions_with_saved_models(
    inference_pipeline, saved_models, sample_recent_readings, sample_future_inputs
):
    """Verify that pipeline outputs feed successfully into actual saved .joblib models."""
    if "xgboost" not in saved_models or "isolation_forest" not in saved_models:
        pytest.skip("Saved models not available on disk, skipping end-to-end inference test.")

    xgb_model = saved_models["xgboost"]
    iso_model = saved_models["isolation_forest"]

    # 1. XGBoost forecast inference
    future_ts, future_temps = sample_future_inputs
    X_forecast = inference_pipeline.prepare_forecast_features(
        recent_readings_df=sample_recent_readings,
        future_timestamps=future_ts,
        future_temperatures=future_temps,
    )
    xgb_preds = xgb_model.predict(X_forecast)

    assert isinstance(xgb_preds, np.ndarray)
    assert len(xgb_preds) == 24
    assert (xgb_preds > 0).all()

    # 2. Isolation Forest anomaly inference
    X_anomaly = inference_pipeline.prepare_anomaly_features(data_df=sample_recent_readings)
    iso_preds = iso_model.predict(X_anomaly)
    iso_scores = -iso_model.decision_function(X_anomaly)

    assert isinstance(iso_preds, np.ndarray)
    assert len(iso_preds) == len(X_anomaly)
    assert set(np.unique(iso_preds)).issubset({-1, 1})
    assert len(iso_scores) == len(X_anomaly)
    assert not np.isnan(iso_scores).any()


def test_autoregressive_forecast_execution(
    inference_pipeline, saved_models, sample_recent_readings, sample_future_inputs
):
    """Verify recursive multi-step forecasting helper."""
    if "xgboost" not in saved_models:
        pytest.skip("XGBoost model not loaded, skipping autoregressive test.")

    xgb_model = saved_models["xgboost"]
    future_ts, future_temps = sample_future_inputs

    df_fc = inference_pipeline.predict_forecast_autoregressive(
        xgb_model=xgb_model,
        recent_readings_df=sample_recent_readings,
        future_timestamps=future_ts,
        future_temperatures=future_temps,
    )

    assert isinstance(df_fc, pd.DataFrame)
    assert len(df_fc) == len(future_ts)
    assert "timestamp" in df_fc.columns
    assert "predicted_meter_reading" in df_fc.columns
    assert "air_temperature" in df_fc.columns
    assert (df_fc["predicted_meter_reading"] > 0).all()
