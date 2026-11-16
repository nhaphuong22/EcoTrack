"""
Tracking + champion-registry tests for Story 4.5 (FR23).

Covers: happy-path tracked training (params/metrics/feature-list/row-counts/artifact
logged, metrics reconcile), first-champion bootstrap, idempotent "champion already
exists", and concurrent first-champion (set-if-absent). Everything runs against a
temporary MLflow store — never the real one.
"""

import json
import threading
from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

from mlflow.tracking import MlflowClient

from src.mlops import config as mlops_config
from src.mlops.tracking import (
    CHAMPION_ALIAS,
    REGISTERED_MODEL_NAME,
    ChampionArtifactError,
    clear_champion_alias,
    promote_champion,
    register_and_bootstrap_champion,
    resolve_champion_version,
    track_training_run,
)
from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    """A throwaway MLflow SQLite store + absolute artifact root under tmp_path."""
    db = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str((tmp_path / "artifacts").as_posix()))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    yield tmp_path


def _tiny_trained():
    """Small XGBoost fit on the fixture, plus the metrics/features/row-counts payload."""
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)
    model = xgb.XGBRegressor(n_estimators=25, max_depth=3, random_state=42, n_jobs=1)
    model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"])
    pred = model.predict(test_df[XGB_FEATURE_COLUMNS])
    rmse = float(np.sqrt(mean_squared_error(test_df["meter_reading"], pred)))
    mae = float(mean_absolute_error(test_df["meter_reading"], pred))
    metrics = {"rmse_kwh": round(rmse, 2), "mae_kwh": round(mae, 2), "r2_score": 0.9, "target_mape_met": True}
    params = {"n_estimators": 25, "max_depth": 3, "random_state": 42}
    row_counts = {"dataset_rows": len(df), "train_rows": len(train_df), "test_rows": len(test_df)}
    return model, params, metrics, row_counts


def test_happy_path_tracked_training_logs_and_reconciles(temp_store):
    model, params, metrics, row_counts = _tiny_trained()
    summary = track_training_run(model, params, metrics, XGB_FEATURE_COLUMNS, row_counts)

    assert summary is not None
    assert summary["version"] == "1"
    assert summary["alias_set"] is True
    assert summary["champion_version"] == "1"

    client = MlflowClient()
    run = client.get_run(summary["run_id"])
    # Params + row counts + feature count are logged.
    assert run.data.params["max_depth"] == "3"
    assert run.data.params["train_rows"] == str(row_counts["train_rows"])
    assert run.data.params["n_features"] == str(len(XGB_FEATURE_COLUMNS))
    # Feature list logged as a tag that round-trips.
    assert json.loads(run.data.tags["xgb_features"]) == XGB_FEATURE_COLUMNS
    # Metrics reconcile with the numbers handed in (same split).
    assert run.data.metrics["rmse_kwh"] == pytest.approx(metrics["rmse_kwh"])
    assert run.data.metrics["mae_kwh"] == pytest.approx(metrics["mae_kwh"])
    # Non-numeric metric (bool) is not logged as a metric.
    assert "target_mape_met" not in run.data.metrics


def test_first_champion_bootstrap_sets_alias(temp_store):
    model, params, metrics, row_counts = _tiny_trained()
    track_training_run(model, params, metrics, XGB_FEATURE_COLUMNS, row_counts)

    client = MlflowClient()
    champ = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
    assert str(champ.version) == "1"


def test_champion_already_exists_leaves_alias_unchanged(temp_store):
    model, params, metrics, row_counts = _tiny_trained()
    first = track_training_run(model, params, metrics, XGB_FEATURE_COLUMNS, row_counts)
    second = track_training_run(model, params, metrics, XGB_FEATURE_COLUMNS, row_counts)

    assert first["alias_set"] is True
    assert second["version"] == "2"
    assert second["alias_set"] is False
    # Alias still points at the first champion; promotion is Story 4.8.
    assert second["champion_version"] == "1"
    client = MlflowClient()
    assert str(client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS).version) == "1"


def test_concurrent_first_champion_only_one_wins(temp_store):
    """Two registered versions race for the alias; set-if-absent lets exactly one win."""
    model, params, metrics, row_counts = _tiny_trained()
    # Configure the store and register two versions WITHOUT setting an alias.
    from src.mlops.tracking import configure

    configure()
    with mlflow.start_run():
        model_info = mlflow.xgboost.log_model(model, artifact_path="model")
    v1 = str(mlflow.register_model(model_info.model_uri, REGISTERED_MODEL_NAME).version)
    v2 = str(mlflow.register_model(model_info.model_uri, REGISTERED_MODEL_NAME).version)
    assert {v1, v2} == {"1", "2"}

    results = {}

    def claim(version):
        results[version] = register_and_bootstrap_champion(version)

    threads = [threading.Thread(target=claim, args=(v,)) for v in (v1, v2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [v for v, r in results.items() if r["alias_set"]]
    assert len(winners) == 1  # exactly one set the alias
    client = MlflowClient()
    champ = str(client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS).version)
    assert champ == winners[0]
    # The loser observed that a champion already exists.
    loser_results = [r for v, r in results.items() if not r["alias_set"]]
    assert loser_results and loser_results[0]["champion_version"] == champ


def test_run_pipeline_logs_run_and_bootstraps_champion(temp_store, tmp_path):
    """End-to-end train_models.run_pipeline against a temp store: a run + champion appear."""
    from src.models.train_models import run_pipeline

    models_dir = tmp_path / "models"
    run_pipeline(data_path=str(FIXTURE_CSV), models_dir=str(models_dir))

    client = MlflowClient()
    exp = client.get_experiment_by_name("ecotrack-forecasting")
    assert exp is not None
    runs = client.search_runs([exp.experiment_id])
    assert len(runs) >= 1  # the training run was logged
    # First-champion alias bootstrapped.
    champ = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
    assert champ is not None
    # models_saved/ artifacts still written as the fallback source of truth.
    assert (models_dir / "xgboost_forecaster.joblib").exists()
    assert (models_dir / "model_metadata.json").exists()


def test_promote_champion_translates_mlflow_error_and_clear_alias(temp_store):
    model, params, metrics, row_counts = _tiny_trained()
    first = track_training_run(model, params, metrics, XGB_FEATURE_COLUMNS, row_counts)
    assert first is not None and first["champion_version"] == "1"

    with pytest.raises(ChampionArtifactError) as exc_info:
        promote_champion("999")
    assert exc_info.value.version == "999"

    clear_champion_alias()
    assert resolve_champion_version() is None
