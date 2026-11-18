"""
Retrain-on-demand and guarded-promotion tests for Story 4.8 (FR25).

Covers:
  - Holdout MAPE helper (zero-target filtering, NaN/Inf rejection)
  - End-to-end real XGBoost retraining + MLflow tracking + guarded promotion +
    hot-reload on GET /internal/forecast/predict without restart
  - Rejection when challenger_mape >= champion_mape (equal or worse keeps champion)
  - Operational failure handling + MLflow alias and disk artifact rollback +
    guaranteed lock release in finally
  - Temporal-leakage guards (boundary duplicate & champion cutoff overlap),
    corrupt metadata/history handling, newest-first history ordering, and train_ratio bounds
  - HTTP endpoint POST /internal/mlops/retrain (202 Accepted, 409 Conflict when
    concurrent, 401 Unauthorized without valid X-Internal-Token)
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

mlflow = pytest.importorskip("mlflow")

from src.data_pipeline import serving_frame
from src.main import app
from src.mlops import retrain as retrain_mod
from src.mlops.retrain import (
    RetrainAlreadyRunningError,
    compute_holdout_mape,
    is_retrain_running,
    load_retrain_history,
    run_retrain,
    start_retrain,
)
from src.mlops.tracking import (
    load_champion_forecaster,
    resolve_champion_version,
    track_training_run,
)
from src.models.train_models import (
    ISO_FEATURE_COLUMNS,
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


class ConstantOffsetForecaster:
    """Lightweight pickle-safe forecaster stub with controllable bias for deterministic MAPE."""

    def __init__(self, scale: float = 1.0, offset: float = 0.0):
        self.scale = scale
        self.offset = offset

    def get_params(self, deep: bool = True):
        return {
            "n_estimators": 10,
            "max_depth": 2,
            "learning_rate": 0.1,
            "random_state": 42,
        }

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.asarray(X["lag_1h"], dtype=float) * self.scale + self.offset


@pytest.fixture(autouse=True)
def clean_serving_cache():
    serving_frame.reset_serving_cache()
    yield
    serving_frame.reset_serving_cache()


@pytest.fixture
def temp_mlflow_env(tmp_path, monkeypatch, setup_test_environment):
    """Isolated MLflow SQLite store + temp models_dir seeded with serving artifacts."""
    db = tmp_path / "mlflow.db"
    artifacts = tmp_path / "artifacts"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Copy baseline isolation_forest.joblib and model_metadata.json from session fixture
    # so end-to-end serving calls (/internal/forecast/predict) work inside temp_mlflow_env.
    base_models = setup_test_environment["models_dir"]
    shutil.copy2(base_models / "isolation_forest.joblib", models_dir / "isolation_forest.joblib")
    shutil.copy2(base_models / "model_metadata.json", models_dir / "model_metadata.json")

    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(artifacts.as_posix()))
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("ECOTRACK_DATA_PATH", str(FIXTURE_CSV))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)

    yield {"tmp": tmp_path, "models_dir": models_dir, "artifacts": artifacts}


def _fit_tiny_xgb(train_df: pd.DataFrame, max_depth: int = 3, scale_target: float = 1.0):
    import xgboost as xgb

    model = xgb.XGBRegressor(n_estimators=15, max_depth=max_depth, learning_rate=0.1, random_state=42, n_jobs=1)
    model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"] * scale_target)
    return model


def test_compute_holdout_mape_filters_zeros_and_rejects_non_finite():
    y_true = np.array([0.0, 100.0, 200.0])
    y_pred = np.array([50.0, 110.0, 180.0])
    # Zero row is ignored; remaining two rows have 10% error each -> 10.0%
    assert compute_holdout_mape(y_true, y_pred) == pytest.approx(10.0)

    with pytest.raises(ValueError, match="no non-zero"):
        compute_holdout_mape(np.array([0.0, 0.0]), np.array([1.0, 2.0]))

    with pytest.raises(ValueError, match="non-finite"):
        compute_holdout_mape(np.array([100.0, 200.0]), np.array([100.0, np.nan]))

    with pytest.raises(ValueError, match="non-finite"):
        compute_holdout_mape(np.array([100.0, 200.0]), np.array([100.0, np.inf]))


def test_run_retrain_real_training_promotes_and_hot_reloads_forecast_endpoint(temp_mlflow_env):
    """End-to-end without monkeypatching _train_challenger: real XGBoost training beats
    a weak seed champion and GET /internal/forecast/predict serves the new champion immediately."""
    models_dir = temp_mlflow_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)

    # Seed a degraded champion (v1) trained on scaled-down targets.
    bad_champion = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    boot = track_training_run(
        model=bad_champion,
        params={"n_estimators": 15, "max_depth": 2},
        metrics={"mape_percent": 50.0, "rmse_kwh": 90.0},
        features=list(XGB_FEATURE_COLUMNS),
        row_counts={"dataset_rows": len(df), "train_rows": len(train_df), "test_rows": len(test_df)},
        run_name="seed_weak_champion",
    )
    assert boot is not None and boot["champion_version"] == "1"
    joblib.dump(bad_champion, models_dir / "xgboost_forecaster.joblib")

    # Preserve Story 4.7 key inside model_metadata.json alongside existing isolation_forest keys.
    meta_path = models_dir / "model_metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["isolation_forest_quality"] = {"scenario_hvac_overrun": {"f1": 0.88}}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Warm serving cache through the real FastAPI forecast endpoint before retrain.
    client = TestClient(app, headers={"X-Internal-Token": "test-internal-token"})
    before_res = client.get("/internal/forecast/predict")
    assert before_res.status_code == 200
    before_preds = [pt["predicted_kwh"] for pt in before_res.json()["forecast"]]

    # Run real retrain (no _train_challenger mock).
    record = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)

    assert record["outcome"] == "promoted"
    assert record["trigger"] == "manual"
    assert record["champion_version"] == "1"
    assert record["challenger_version"] == "2"
    assert record["challenger_mape"] < record["champion_mape"]
    assert record["timestamp"].endswith("Z")
    assert not is_retrain_running()

    _, active_version = load_champion_forecaster()
    assert active_version == "2"

    # Metadata keeps isolation_forest_quality + iso_features and records train_end_timestamp.
    updated_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated_meta["isolation_forest_quality"]["scenario_hvac_overrun"]["f1"] == 0.88
    assert updated_meta["iso_features"] == ISO_FEATURE_COLUMNS
    assert updated_meta["train_end_timestamp"]
    assert updated_meta["xgboost_metrics"]["mape_percent"] == pytest.approx(record["challenger_mape"], abs=0.01)

    # Forecast endpoint serves the promoted champion without restarting the app.
    after_res = client.get("/internal/forecast/predict")
    assert after_res.status_code == 200
    after_preds = [pt["predicted_kwh"] for pt in after_res.json()["forecast"]]
    assert after_preds != before_preds

    history = load_retrain_history(models_dir)
    assert len(history) == 1
    assert history[0]["run_id"] == record["run_id"]
    assert history[0]["outcome"] == "promoted"


def test_run_retrain_rejects_equal_or_worse_challenger_and_preserves_newest_first_history(
    temp_mlflow_env, monkeypatch
):
    models_dir = temp_mlflow_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)

    strong_champion = _fit_tiny_xgb(train_df, max_depth=3, scale_target=1.0)
    boot = track_training_run(
        model=strong_champion,
        params={"n_estimators": 15, "max_depth": 3},
        metrics={"mape_percent": 5.0},
        features=list(XGB_FEATURE_COLUMNS),
        row_counts={"dataset_rows": len(df), "train_rows": len(train_df), "test_rows": len(test_df)},
        run_name="seed_strong_champion",
    )
    assert boot is not None and boot["champion_version"] == "1"

    # Case 1: Equal MAPE (identical model) -> must be rejected (strict inequality).
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (strong_champion, {"rmse_kwh": 10.0, "mae_kwh": 8.0, "r2_score": 0.9, "target_mape_met": True}),
    )
    serving_frame._cached_xgb_model = strong_champion

    rec_equal = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_equal["outcome"] == "rejected"
    assert rec_equal["challenger_mape"] == pytest.approx(rec_equal["champion_mape"], abs=1e-5)
    assert serving_frame._cached_xgb_model is strong_champion
    _, active_version = load_champion_forecaster()
    assert active_version == "1"

    # Case 2: Worse MAPE -> rejected; verify newest-first ordering via distinct run_ids.
    worse_challenger = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (worse_challenger, {"rmse_kwh": 90.0, "mae_kwh": 70.0, "r2_score": 0.1, "target_mape_met": False}),
    )
    rec_worse = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_worse["outcome"] == "rejected"
    assert rec_worse["challenger_mape"] > rec_worse["champion_mape"]
    _, active_version = load_champion_forecaster()
    assert active_version == "1"

    history = load_retrain_history(models_dir)
    assert [h["run_id"] for h in history] == [rec_worse["run_id"], rec_equal["run_id"]]


def test_run_retrain_rollback_restores_disk_and_mlflow_alias_and_releases_lock(
    temp_mlflow_env, monkeypatch
):
    models_dir = temp_mlflow_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)

    bad_champion = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    track_training_run(
        model=bad_champion,
        params={"n_estimators": 15, "max_depth": 2},
        metrics={"mape_percent": 50.0},
        features=list(XGB_FEATURE_COLUMNS),
        row_counts={"dataset_rows": len(df), "train_rows": len(train_df), "test_rows": len(test_df)},
    )
    xgb_path = models_dir / "xgboost_forecaster.joblib"
    meta_path = models_dir / "model_metadata.json"
    joblib.dump(bad_champion, xgb_path)
    orig_xgb_bytes = xgb_path.read_bytes()
    orig_meta_bytes = meta_path.read_bytes()

    # Failure 1: Missing dataset -> outcome == "failed", lock released.
    rec_missing = run_retrain(
        trigger="manual",
        data_path=models_dir / "non_existent.csv",
        models_dir=models_dir,
    )
    assert rec_missing["outcome"] == "failed"
    assert "not found" in (rec_missing["reason"] or "").lower()
    assert not is_retrain_running()

    good_challenger = _fit_tiny_xgb(train_df, max_depth=3, scale_target=1.0)
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (good_challenger, {"rmse_kwh": 12.0, "mae_kwh": 9.0, "r2_score": 0.9, "target_mape_met": True}),
    )

    # Failure 2: promote_champion fails AFTER disk swap -> restores disk artifacts, keeps MLflow v1.
    with monkeypatch.context() as m:
        m.setattr(retrain_mod, "promote_champion", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("MLflow alias locked")))
        rec_promote_err = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_promote_err["outcome"] == "failed"
    assert "MLflow alias locked" in (rec_promote_err["reason"] or "")
    assert xgb_path.read_bytes() == orig_xgb_bytes
    assert meta_path.read_bytes() == orig_meta_bytes
    assert not is_retrain_running()

    # Failure 3: reset_serving_cache fails AFTER promote_champion switched alias -> rolls back BOTH MLflow alias to v1 AND disk files.
    with monkeypatch.context() as m:
        m.setattr(serving_frame, "reset_serving_cache", lambda: (_ for _ in ()).throw(RuntimeError("Cache reset boom")))
        rec_cache_err = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_cache_err["outcome"] == "failed"
    assert "Cache reset boom" in (rec_cache_err["reason"] or "")
    assert xgb_path.read_bytes() == orig_xgb_bytes
    assert meta_path.read_bytes() == orig_meta_bytes
    _, active_version = load_champion_forecaster()
    assert active_version == "1"
    assert not is_retrain_running()


def test_run_retrain_handles_missing_champion_non_finite_challenger_and_probe_failure(
    temp_mlflow_env, monkeypatch
):
    models_dir = temp_mlflow_env["models_dir"]

    # 1. No champion anywhere (neither MLflow nor models_dir) -> outcome == "failed", lock released.
    rec_no_champ = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_no_champ["outcome"] == "failed"
    assert rec_no_champ["champion_version"] is None
    assert not is_retrain_running()

    # Seed a valid on-disk champion (with no MLflow champion alias yet -> champion_version == "local").
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)
    seed_champ = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    xgb_path = models_dir / "xgboost_forecaster.joblib"
    joblib.dump(seed_champ, xgb_path)
    orig_xgb_bytes = xgb_path.read_bytes()

    # 2. Challenger produces NaN predictions -> outcome == "failed", MLflow does NOT bootstrap alias.
    class _NaNForecaster:
        def predict(self, X):
            return np.full(len(X), np.nan)

    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (_NaNForecaster(), {"rmse_kwh": 0.0, "mae_kwh": 0.0, "r2_score": 0.0, "target_mape_met": False}),
    )
    rec_nan = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_nan["outcome"] == "failed"
    assert "non-finite" in (rec_nan["reason"] or "").lower()
    assert not is_retrain_running()

    # 3. Rejected challenger when champion_version == "local" must NOT claim MLflow champion alias.
    worse_challenger = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.2)
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (worse_challenger, {"rmse_kwh": 99.0, "mae_kwh": 90.0, "r2_score": 0.0, "target_mape_met": False}),
    )
    rec_local_reject = run_retrain(trigger="drift", signals=["meter_reading"], data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_local_reject["outcome"] == "rejected"
    assert rec_local_reject["signals"] == ["meter_reading"]
    assert resolve_champion_version() is None

    # 4. Probe failure inside _verify_and_promote_challenger aborts before promote_champion is called.
    good_challenger = _fit_tiny_xgb(train_df, max_depth=3, scale_target=1.0)
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (good_challenger, {"rmse_kwh": 10.0, "mae_kwh": 8.0, "r2_score": 0.9, "target_mape_met": True}),
    )
    promote_called = []
    with monkeypatch.context() as m:
        m.setattr(retrain_mod, "promote_champion", lambda *a, **kw: promote_called.append(True))

        class _NaNProbeModel:
            def predict(self, X):
                return np.array([np.nan])

        m.setattr(mlflow.xgboost, "load_model", lambda uri: _NaNProbeModel())
        rec_probe_fail = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_probe_fail["outcome"] == "failed"
    assert "non-finite probe" in (rec_probe_fail["reason"] or "").lower()
    assert promote_called == []
    assert not is_retrain_running()

    # 5. Failure after promote_champion when champion_version == "local" clears the newly set MLflow alias & restores disk.
    with monkeypatch.context() as m:
        m.setattr(serving_frame, "reset_serving_cache", lambda: (_ for _ in ()).throw(RuntimeError("Cache reset boom local")))
        rec_local_rollback = run_retrain(trigger="manual", data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_local_rollback["outcome"] == "failed"
    assert resolve_champion_version() is None
    assert xgb_path.read_bytes() == orig_xgb_bytes
    assert not is_retrain_running()


def test_run_retrain_temporal_leakage_and_corrupt_file_guards(temp_mlflow_env, monkeypatch):
    models_dir = temp_mlflow_env["models_dir"]
    tmp_path = temp_mlflow_env["tmp"]
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    champ = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    joblib.dump(champ, models_dir / "xgboost_forecaster.joblib")

    # 1. Invalid train_ratio rejected cleanly (including negative values that Python slices would accept).
    with pytest.raises(ValueError, match="train_ratio"):
        start_retrain(train_ratio=-0.2)
    rec_bad_ratio = run_retrain(train_ratio=-0.2, data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_bad_ratio["outcome"] == "failed"
    assert "train_ratio" in (rec_bad_ratio["reason"] or "")

    # 2. Duplicate timestamp across the 80/20 split boundary -> Temporal leakage detected.
    raw_df = pd.read_csv(FIXTURE_CSV)
    # Build 40 rows where split point shares the exact same timestamp.
    dup_rows = raw_df.iloc[:40].copy()
    engineered_count = len(dup_rows) - 24
    split_pos = 24 + int(engineered_count * 0.8)
    dup_rows.loc[dup_rows.index[split_pos], "timestamp"] = dup_rows.loc[dup_rows.index[split_pos - 1], "timestamp"]
    dup_csv = tmp_path / "dup_boundary.csv"
    dup_rows.to_csv(dup_csv, index=False)

    rec_dup = run_retrain(data_path=dup_csv, models_dir=models_dir)
    assert rec_dup["outcome"] == "failed"
    assert "temporal leakage" in (rec_dup["reason"] or "").lower()

    # 3. Active champion's recorded train_end_timestamp overlaps holdout -> Temporal leakage detected.
    meta_path = models_dir / "model_metadata.json"
    orig_meta = meta_path.read_text(encoding="utf-8")
    meta = json.loads(orig_meta)
    # Set champion training cutoff to the last timestamp of the entire fixture (inside test_df).
    meta["train_end_timestamp"] = str(df["timestamp"].max().isoformat())
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    rec_cutoff = run_retrain(data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_cutoff["outcome"] == "failed"
    assert "champion training cutoff" in (rec_cutoff["reason"] or "").lower()

    # 4. Corrupt model_metadata.json aborts promotion instead of overwriting isolation_forest_metrics.
    meta_path.write_text("{broken json", encoding="utf-8")
    good_chall = _fit_tiny_xgb(train_df, max_depth=3, scale_target=1.0)
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (good_chall, {"rmse_kwh": 10.0, "mae_kwh": 8.0, "r2_score": 0.9, "target_mape_met": True}),
    )
    rec_corrupt_meta = run_retrain(data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_corrupt_meta["outcome"] == "failed"
    assert meta_path.read_text(encoding="utf-8") == "{broken json"

    # 5. Corrupt retrain_history.json is backed up before starting fresh, not silently erased.
    hist_path = models_dir / retrain_mod.RETRAIN_HISTORY_FILENAME
    hist_path.write_text("{corrupt history", encoding="utf-8")
    meta_path.write_text(orig_meta, encoding="utf-8")
    rec_after_corrupt_hist = run_retrain(data_path=FIXTURE_CSV, models_dir=models_dir)
    assert rec_after_corrupt_hist["outcome"] == "promoted"
    backups = list(models_dir.glob("retrain_history.corrupt.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{corrupt history"


def test_retrain_endpoint_returns_202_409_and_enforces_internal_token(temp_mlflow_env, monkeypatch):
    models_dir = temp_mlflow_env["models_dir"]
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")

    stub_champ = ConstantOffsetForecaster(scale=1.0, offset=25.0)
    stub_chall = ConstantOffsetForecaster(scale=1.0, offset=5.0)
    joblib.dump(stub_champ, models_dir / "xgboost_forecaster.joblib")

    gate = threading.Event()
    entered = threading.Event()

    def _controlled_train(train_df, test_df):
        entered.set()
        gate.wait(timeout=5.0)
        return stub_chall, {"rmse_kwh": 5.0, "mae_kwh": 5.0, "r2_score": 0.95, "target_mape_met": True}

    monkeypatch.setattr(retrain_mod, "_train_challenger", _controlled_train)

    client = TestClient(app)

    # 1. Missing/invalid internal token -> 401
    unauth = client.post("/internal/mlops/retrain")
    assert unauth.status_code == 401

    headers = {"X-Internal-Token": "test-internal-token"}

    # 2. First valid request -> 202 Accepted immediately while background thread blocks on `gate`
    resp_202 = client.post("/internal/mlops/retrain", headers=headers)
    assert resp_202.status_code == 202
    body = resp_202.json()
    assert body["status"] == "running"
    assert body["trigger"] == "manual"
    assert body["run_id"]
    assert body["started_at"].endswith("Z")

    assert entered.wait(timeout=3.0)

    # 3. Second concurrent request while first is still running -> 409 Conflict
    resp_409 = client.post("/internal/mlops/retrain", headers=headers)
    assert resp_409.status_code == 409
    assert resp_409.json()["code"] == "ERR_RETRAIN_IN_PROGRESS"

    # Release the background thread and wait briefly for completion.
    gate.set()
    for _ in range(50):
        if not is_retrain_running():
            break
        time.sleep(0.02)

    assert not is_retrain_running()
    history = load_retrain_history(models_dir)
    assert len(history) == 1
    assert history[0]["run_id"] == body["run_id"]
    assert history[0]["outcome"] == "promoted"
