"""
Health-endpoint champion-status tests for Story 4.5 (FR23).

Covers GET /health?details=true `models.champion` / `models.champion_version`
and the `forecast` status across: forecaster-on-disk only, champion present
(even with no on-disk forecaster), and neither.
"""

from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

from src.main import health
from src.models.train_models import XGB_FEATURE_COLUMNS, engineer_features, load_dataset, split_time_series_data

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


def _tiny_model():
    import xgboost as xgb

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    model = xgb.XGBRegressor(n_estimators=15, max_depth=3, random_state=42, n_jobs=1)
    model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"])
    return model


def test_health_forecaster_on_disk_only(monkeypatch):
    """Default suite state: forecaster present on disk, MLflow disabled -> no champion."""
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    models = health(details=True)["models"]
    assert models["forecast"] == "loaded"
    assert models["champion"] == "unavailable"
    assert models["champion_version"] is None


def test_health_champion_present_even_without_disk_forecaster(tmp_path, monkeypatch):
    """A resolvable champion makes forecast 'loaded' even when models_saved/ has no forecaster."""
    db = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str((tmp_path / "artifacts").as_posix()))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    # Empty models dir -> no xgboost_forecaster.joblib on disk.
    empty_models = tmp_path / "models"
    empty_models.mkdir()
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(empty_models))

    from src.mlops.tracking import track_training_run

    summary = track_training_run(
        _tiny_model(),
        {"n_estimators": 15},
        {"rmse_kwh": 10.0},
        XGB_FEATURE_COLUMNS,
        {"dataset_rows": 1, "train_rows": 1, "test_rows": 1},
    )

    models = health(details=True)["models"]
    assert models["champion_version"] == summary["version"]
    assert models["champion"] == "resolved"
    assert models["forecast"] == "loaded"  # champion alone satisfies the forecaster


def test_health_neither_forecaster_nor_champion(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    empty_models = tmp_path / "empty"
    empty_models.mkdir()
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(empty_models))

    models = health(details=True)["models"]
    assert models["forecast"] == "unavailable"
    assert models["champion"] == "unavailable"
    assert models["champion_version"] is None
