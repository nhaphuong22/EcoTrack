"""
Champion-aware serving-load tests for Story 4.5 (FR23).

Covers the three serving states:
  1. champion present      -> the service loads the champion version,
  2. MLflow not initialised -> falls back to models_saved/ with a logged warning,
  3. champion broken        -> ModelArtifactError (-> 503 ERR_MODEL_NOT_FOUND), no fallback.
"""

import logging
import shutil
from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

from src.data_pipeline import serving_frame
from src.data_pipeline.serving_frame import (
    ModelArtifactError,
    _load_champion_forecaster_or_fallback,
    get_serving_frame,
    reset_serving_cache,
)
from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


def _tiny_model():
    import xgboost as xgb

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    model = xgb.XGBRegressor(n_estimators=20, max_depth=3, random_state=42, n_jobs=1)
    model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"])
    return model


@pytest.fixture
def champion_store(tmp_path, monkeypatch):
    """Temp MLflow store with a bootstrapped champion; champion serving path enabled."""
    db = tmp_path / "mlflow.db"
    artifacts = tmp_path / "artifacts"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(artifacts.as_posix()))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)

    from src.mlops.tracking import track_training_run

    summary = track_training_run(
        _tiny_model(),
        {"n_estimators": 20, "max_depth": 3},
        {"rmse_kwh": 10.0, "mae_kwh": 8.0},
        XGB_FEATURE_COLUMNS,
        {"dataset_rows": 1, "train_rows": 1, "test_rows": 1},
    )
    reset_serving_cache()
    yield {"tmp": tmp_path, "artifacts": artifacts, "version": summary["version"]}
    reset_serving_cache()


def test_champion_present_loads_champion(champion_store):
    # Direct loader returns the champion model.
    from src.mlops.tracking import load_champion_forecaster

    loaded, resolved_version = load_champion_forecaster()
    assert resolved_version == champion_store["version"]
    assert hasattr(loaded, "predict")

    # End-to-end: the serving frame builds using the champion forecaster.
    frame = get_serving_frame()
    assert len(frame) == 720


def test_mlflow_not_initialised_falls_back_with_warning(tmp_path, monkeypatch, caplog):
    # Point at a store that does not exist -> not initialised -> fallback.
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'missing.db').as_posix()}")
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    reset_serving_cache()

    models_dir = Path(__import__("os").environ["ECOTRACK_MODELS_DIR"])
    xgb_path = models_dir / "xgboost_forecaster.joblib"

    with caplog.at_level(logging.WARNING, logger="ServingFrame"):
        model = _load_champion_forecaster_or_fallback(xgb_path)
    assert hasattr(model, "predict")  # loaded from models_saved/
    assert any("falling back to models_saved" in rec.message for rec in caplog.records)
    reset_serving_cache()


def test_broken_champion_raises_model_artifact_error(champion_store):
    # Alias resolves but the artifact files are gone -> fail loud, no fallback.
    shutil.rmtree(champion_store["artifacts"], ignore_errors=True)
    reset_serving_cache()

    models_dir = Path(__import__("os").environ["ECOTRACK_MODELS_DIR"])
    xgb_path = models_dir / "xgboost_forecaster.joblib"

    with pytest.raises(ModelArtifactError) as exc_info:
        _load_champion_forecaster_or_fallback(xgb_path)
    # The error names the champion version it failed to load.
    assert champion_store["version"] in str(exc_info.value)
    reset_serving_cache()
