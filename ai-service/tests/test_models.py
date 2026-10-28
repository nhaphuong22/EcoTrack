"""
Unit tests for EcoTrack ML Models:
- Validates model persistence and loading from .joblib files
- Validates XGBoost Regressor predictions and output shapes
- Validates Isolation Forest predictions and anomaly scoring
- Validates feature engineering pipeline
"""

import os
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    ISO_FEATURE_COLUMNS,
    engineer_features,
    get_default_paths,
    run_pipeline,
)


@pytest.fixture(scope="session")
def models_directory():
    """Returns the models_saved directory, training models if they do not already exist."""
    _, models_dir = get_default_paths()
    xgb_path = models_dir / "xgboost_forecaster.joblib"
    iso_path = models_dir / "isolation_forest.joblib"

    # Auto-train if models are missing (ensures robust CI/CD execution)
    if not xgb_path.exists() or not iso_path.exists():
        data_path, _ = get_default_paths()
        if data_path.exists():
            run_pipeline(data_path=str(data_path), models_dir=str(models_dir))
        else:
            pytest.skip(f"Processed dataset not found at {data_path}, skipping model unit tests.")

    return models_dir


@pytest.fixture(scope="session")
def loaded_models(models_directory):
    """Loads trained estimators from disk."""
    xgb_path = models_directory / "xgboost_forecaster.joblib"
    iso_path = models_directory / "isolation_forest.joblib"

    assert xgb_path.exists(), f"XGBoost model file not found at: {xgb_path}"
    assert iso_path.exists(), f"Isolation Forest model file not found at: {iso_path}"

    xgb_model = joblib.load(xgb_path)
    iso_model = joblib.load(iso_path)

    return {"xgboost": xgb_model, "isolation_forest": iso_model}


@pytest.fixture
def sample_feature_data():
    """Generates synthetic test features conforming to required model inputs."""
    np.random.seed(42)
    n_samples = 48  # 48 hours (2 days)

    hours = np.tile(np.arange(24), 2)
    days = np.array([1] * 24 + [5] * 24)  # 1 weekday, 1 weekend

    data = {
        "meter_reading": np.random.uniform(200.0, 800.0, size=n_samples),
        "air_temperature": np.random.uniform(5.0, 30.0, size=n_samples),
        "hour": hours,
        "dayofweek": days,
        "is_weekend": (days >= 5).astype(int),
        "hour_sin": np.sin(2 * np.pi * hours / 24.0),
        "hour_cos": np.cos(2 * np.pi * hours / 24.0),
        "lag_1h": np.random.uniform(190.0, 780.0, size=n_samples),
        "lag_24h": np.random.uniform(180.0, 750.0, size=n_samples),
    }
    return pd.DataFrame(data)


def test_models_exist_and_load(loaded_models):
    """Verify that both saved joblib models can be loaded into memory."""
    xgb_model = loaded_models["xgboost"]
    iso_model = loaded_models["isolation_forest"]

    assert xgb_model is not None, "Failed to load XGBoost model."
    assert iso_model is not None, "Failed to load Isolation Forest model."
    assert hasattr(xgb_model, "predict"), "XGBoost model missing predict method."
    assert hasattr(iso_model, "predict"), "Isolation Forest model missing predict method."


def test_xgboost_forecaster_predict(loaded_models, sample_feature_data):
    """Verify XGBoost forecaster predicts valid energy consumption (meter_reading)."""
    xgb_model = loaded_models["xgboost"]
    X = sample_feature_data[XGB_FEATURE_COLUMNS]

    preds = xgb_model.predict(X)

    # 1. Output shape & type assertions
    assert isinstance(preds, np.ndarray), "Predictions should be a numpy ndarray."
    assert len(preds) == len(X), f"Expected {len(X)} predictions, got {len(preds)}."

    # 2. Value validity assertions
    assert not np.isnan(preds).any(), "Predictions contain NaN values."
    assert not np.isinf(preds).any(), "Predictions contain infinite values."
    assert (preds > 0).all(), "Predicted electricity demand should be strictly positive."


def test_isolation_forest_predict(loaded_models, sample_feature_data):
    """Verify Isolation Forest detects anomalies and outputs valid scores & labels."""
    iso_model = loaded_models["isolation_forest"]
    X = sample_feature_data[ISO_FEATURE_COLUMNS]

    preds = iso_model.predict(X)
    decisions = iso_model.decision_function(X)

    # 1. Prediction labels (-1: anomaly, 1: normal)
    assert isinstance(preds, np.ndarray)
    assert len(preds) == len(X)
    assert set(np.unique(preds)).issubset({-1, 1}), "Predictions must only contain 1 and -1."

    # 2. Decision function scores
    assert isinstance(decisions, np.ndarray)
    assert len(decisions) == len(X)
    assert not np.isnan(decisions).any(), "Decision scores contain NaN values."

    # 3. Anomaly flags mapping
    is_anomaly = (preds == -1).astype(int)
    assert set(np.unique(is_anomaly)).issubset({0, 1}), "Binary anomaly flags must be in {0, 1}."


def test_feature_engineering_pipeline():
    """Verify feature engineering logic handles raw clean time-series properly."""
    timestamps = pd.date_range("2020-01-01 00:00:00", periods=50, freq="1h")
    mock_df = pd.DataFrame({
        "timestamp": timestamps,
        "meter_reading": np.linspace(100, 300, 50),
        "air_temperature": np.linspace(15, 25, 50),
    })

    df_feat = engineer_features(mock_df)

    # Check required columns exist
    for col in XGB_FEATURE_COLUMNS:
        assert col in df_feat.columns, f"Missing feature column: {col}"

    # Verify cyclical bounds
    assert df_feat["hour_sin"].between(-1.0, 1.0).all()
    assert df_feat["hour_cos"].between(-1.0, 1.0).all()

    # Verify no nulls remaining after lag creation
    assert df_feat[XGB_FEATURE_COLUMNS].isnull().sum().sum() == 0
    assert len(df_feat) == 50 - 24  # 24 rows dropped due to lag_24h
