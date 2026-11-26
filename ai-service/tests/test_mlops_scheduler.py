"""
Automated drift-check and scheduled-retrain tests for Story 4.9 (FR25, PRD FR-5).

Covers:
  - No-drift check skips retraining and persists drift_status.json
  - Rolling-MAPE-only degradation sets trigger="mape" with signals=["rolling_mape"]
  - Distribution drift (HVAC overrun scenario, air_temperature-only, and combined)
    sets trigger="drift" and preserves all triggered_signals in retrain_history.json
  - Guarded promotion outcomes via automatic trigger ("rejected" & "failed") and
    MLflow-enabled scoped champion resolution (models_dir + tracking_uri)
  - Default unmodified baseline vs ECOTRACK_DRIFT_RECENT_PATH override
  - Concurrent RetrainAlreadyRunningError is logged and skipped without touching history
  - Config env validation (falsy booleans, empty fallback, invalid/NaN/Inf floats)
  - Scheduler disabled by conftest.py, initial_delay cancel, tick-error survival,
    restart after stop, and join-timeout duplicate prevention
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import xgboost as xgb
from fastapi.testclient import TestClient

from src.data_pipeline.demo_scenarios import generate_scenario_hvac_night_overrun
from src.main import app
from src.mlops import config as mlops_config
from src.mlops import retrain as retrain_mod
from src.mlops import scheduler as scheduler_mod
from src.mlops.retrain import load_retrain_history
from src.mlops.scheduler import (
    is_scheduler_running,
    load_drift_status,
    run_drift_check_and_retrain,
    start_scheduler,
    stop_scheduler,
)
from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


class _WrongPredictor:
    """Stub champion predicting an unrealistic constant to force rolling_mape > 15%."""

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), 10.0)


def _fit_tiny_xgb(train_df: pd.DataFrame, max_depth: int = 3, scale_target: float = 1.0):
    model = xgb.XGBRegressor(n_estimators=25, max_depth=max_depth, learning_rate=0.1, random_state=42, n_jobs=1)
    model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"] * scale_target)
    return model


@pytest.fixture
def isolated_models_env(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("ECOTRACK_DATA_PATH", str(FIXTURE_CSV))
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    monkeypatch.delenv("ECOTRACK_DRIFT_RECENT_PATH", raising=False)
    yield {"tmp": tmp_path, "models_dir": models_dir}
    stop_scheduler(timeout=2.0)


def test_run_drift_check_no_drift_skips_retrain_and_persists_status(isolated_models_env):
    models_dir = isolated_models_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    champion = _fit_tiny_xgb(train_df)

    status = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=train_df.copy(),
        champion_model=champion,
        models_dir=models_dir,
    )

    assert status["drift_detected"] is False
    assert status["triggered_signals"] == []
    assert status["retrain_triggered"] is False
    assert status["retrain_trigger"] is None
    assert status["retrain_run_id"] is None
    assert status["checked_at"].endswith("Z")
    assert load_drift_status(models_dir) == status
    assert load_retrain_history(models_dir) == []


def test_run_drift_check_rolling_mape_only_triggers_mape(isolated_models_env, monkeypatch):
    models_dir = isolated_models_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)

    seed_champ = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    joblib.dump(seed_champ, models_dir / "xgboost_forecaster.joblib")

    better_chall = _fit_tiny_xgb(train_df, max_depth=3, scale_target=1.0)
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (better_chall, {"rmse_kwh": 10.0, "mae_kwh": 8.0, "r2_score": 0.9, "target_mape_met": True}),
    )

    status = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=train_df.copy(),
        champion_model=_WrongPredictor(),
        data_path=FIXTURE_CSV,
        models_dir=models_dir,
    )

    assert status["drift_detected"] is True
    assert status["triggered_signals"] == ["rolling_mape"]
    assert status["retrain_triggered"] is True
    assert status["retrain_trigger"] == "mape"
    assert status["retrain_outcome"] == "promoted"

    history = load_retrain_history(models_dir)
    assert len(history) == 1
    assert history[0]["run_id"] == status["retrain_run_id"]
    assert history[0]["trigger"] == "mape"
    assert history[0]["signals"] == ["rolling_mape"]
    assert history[0]["outcome"] == "promoted"


def test_run_drift_check_distribution_drift_triggers_drift_with_signals(isolated_models_env, monkeypatch):
    models_dir = isolated_models_env["models_dir"]
    raw_fixture = load_dataset(FIXTURE_CSV)
    df = engineer_features(raw_fixture)
    train_df, _ = split_time_series_data(df, train_ratio=0.8)

    champion = _fit_tiny_xgb(train_df)
    joblib.dump(champion, models_dir / "xgboost_forecaster.joblib")
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (champion, {"rmse_kwh": 10.0, "mae_kwh": 8.0, "r2_score": 0.9, "target_mape_met": True}),
    )

    # 1. Realistic HVAC overrun scenario window (rejected equal champion keeps incumbent)
    scenario_df = generate_scenario_hvac_night_overrun(base_df=raw_fixture)
    scenario_df["timestamp"] = pd.to_datetime(scenario_df["timestamp"])
    injected = (scenario_df["meter_reading"] - raw_fixture["meter_reading"]).abs() > 50.0
    anom_idx = scenario_df.index[injected]
    recent_hvac = scenario_df.iloc[max(0, anom_idx.min() - 40) : anom_idx.max() + 1]

    status_hvac = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=recent_hvac,
        champion_model=champion,
        data_path=FIXTURE_CSV,
        models_dir=models_dir,
    )
    assert status_hvac["drift_detected"] is True
    assert "meter_reading" in status_hvac["triggered_signals"]
    assert status_hvac["retrain_triggered"] is True
    assert status_hvac["retrain_trigger"] == "drift"
    assert status_hvac["retrain_outcome"] == "rejected"

    # 2. Air-temperature-only drift -> classified as "drift" with signals=["air_temperature"]
    temp_shifted = train_df.copy()
    temp_shifted["air_temperature"] = np.random.RandomState(3).normal(80.0, 2.0, size=len(temp_shifted))

    class _ExactTail:
        def predict(self, X):
            return temp_shifted.tail(len(X))["meter_reading"].to_numpy()

    status_temp = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=temp_shifted,
        champion_model=_ExactTail(),
        data_path=FIXTURE_CSV,
        models_dir=models_dir,
    )
    assert status_temp["triggered_signals"] == ["air_temperature"]
    assert status_temp["retrain_trigger"] == "drift"

    # 3. Combined air_temperature shift + rolling_mape -> classified as "drift" preserving both signals
    status_combo = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=temp_shifted,
        champion_model=_WrongPredictor(),
        data_path=FIXTURE_CSV,
        models_dir=models_dir,
    )
    assert status_combo["retrain_trigger"] == "drift"
    assert set(status_combo["triggered_signals"]) == {"air_temperature", "rolling_mape"}

    history = load_retrain_history(models_dir)
    assert len(history) == 3
    assert history[0]["trigger"] == "drift"
    assert set(history[0]["signals"]) == {"air_temperature", "rolling_mape"}
    assert history[1]["signals"] == ["air_temperature"]
    assert history[2]["outcome"] == "rejected"


def test_run_drift_check_resolves_default_and_env_recent_paths(isolated_models_env, monkeypatch):
    models_dir = isolated_models_env["models_dir"]
    tmp_path = isolated_models_env["tmp"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    champion = _fit_tiny_xgb(train_df)
    joblib.dump(champion, models_dir / "xgboost_forecaster.joblib")

    # Default paths (unmodified baseline -> no drift, no retrain triggered)
    status_default = run_drift_check_and_retrain(models_dir=models_dir)
    assert status_default["checked_at"].endswith("Z")
    assert status_default["drift_detected"] is False
    assert status_default["retrain_triggered"] is False
    assert load_drift_status(models_dir) == status_default
    assert load_retrain_history(models_dir) == []

    # Override recent window via ECOTRACK_DRIFT_RECENT_PATH -> triggers drift retrain
    recent_csv = tmp_path / "recent_drifted.csv"
    raw_tail = pd.read_csv(FIXTURE_CSV).tail(200).copy()
    raw_tail["air_temperature"] = 75.0
    raw_tail.to_csv(recent_csv, index=False)
    monkeypatch.setenv("ECOTRACK_DRIFT_RECENT_PATH", str(recent_csv))
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (champion, {"rmse_kwh": 10.0, "mae_kwh": 8.0, "r2_score": 0.9, "target_mape_met": True}),
    )

    status_env = run_drift_check_and_retrain(models_dir=models_dir)
    assert status_env["drift_detected"] is True
    assert "air_temperature" in status_env["triggered_signals"]
    assert status_env["retrain_triggered"] is True
    assert status_env["retrain_trigger"] == "drift"
    assert status_env["retrain_outcome"] == "rejected"
    assert len(load_retrain_history(models_dir)) == 1


def test_run_drift_check_scoped_mlflow_and_retrain_failure_still_persist_status(
    tmp_path, monkeypatch
):
    mlflow = pytest.importorskip("mlflow")
    from src.mlops.tracking import track_training_run

    db = tmp_path / "mlflow.db"
    artifacts = tmp_path / "artifacts"
    models_dir = tmp_path / "scoped_models"
    models_dir.mkdir(parents=True, exist_ok=True)
    uri = f"sqlite:///{db.as_posix()}"

    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'other_mlflow.db').as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(artifacts.as_posix()))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(tmp_path / "other_dir"))
    monkeypatch.setenv("ECOTRACK_DATA_PATH", str(FIXTURE_CSV))

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)
    weak_champ = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    track_training_run(
        model=weak_champ,
        params={"n_estimators": 25},
        metrics={"mape_percent": 50.0},
        features=list(XGB_FEATURE_COLUMNS),
        row_counts={"dataset_rows": len(df), "train_rows": len(train_df), "test_rows": len(test_df)},
        tracking_uri=uri,
    )

    # Scoped models_dir/tracking_uri resolves the weak MLflow champion (rolling_mape > 15%),
    # even though MLFLOW_TRACKING_URI and ECOTRACK_MODELS_DIR point elsewhere. Simulated
    # _train_challenger error triggers failed retrain while drift_status.json is saved cleanly.
    monkeypatch.setattr(
        retrain_mod,
        "_train_challenger",
        lambda tr, te: (_ for _ in ()).throw(RuntimeError("Simulated retrain failure")),
    )
    status = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=train_df.copy(),
        data_path=FIXTURE_CSV,
        models_dir=models_dir,
        tracking_uri=uri,
    )
    assert status["rolling_mape"] is not None
    assert status["rolling_mape"]["mape_percent"] > 15.0
    assert status["retrain_triggered"] is True
    assert status["retrain_trigger"] == "mape"
    assert status["retrain_outcome"] == "failed"
    assert load_drift_status(models_dir) == status
    assert not (tmp_path / "other_dir").exists()
    history = load_retrain_history(models_dir)
    assert len(history) == 1
    assert history[0]["outcome"] == "failed"


def test_run_drift_check_scoped_empty_dir_does_not_leak_global_champion(isolated_models_env):
    global_models_dir = isolated_models_env["models_dir"]
    scoped_empty_dir = isolated_models_env["tmp"] / "scoped_empty"
    scoped_empty_dir.mkdir(parents=True, exist_ok=True)

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    bad_global_champ = _fit_tiny_xgb(train_df, max_depth=2, scale_target=0.5)
    joblib.dump(bad_global_champ, global_models_dir / "xgboost_forecaster.joblib")

    status = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=train_df.copy(),
        models_dir=scoped_empty_dir,
    )

    assert status["rolling_mape"] is None
    assert status["drift_detected"] is False
    assert status["retrain_triggered"] is False
    assert status["retrain_trigger"] is None
    assert load_drift_status(scoped_empty_dir) == status
    assert load_drift_status(global_models_dir) is None


def test_run_drift_check_handles_retrain_lock_conflict_safely(isolated_models_env):
    models_dir = isolated_models_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)

    assert retrain_mod._retrain_lock.acquire(blocking=False)
    try:
        status = run_drift_check_and_retrain(
            reference_df=train_df,
            recent_df=train_df.copy(),
            champion_model=_WrongPredictor(),
            models_dir=models_dir,
        )
    finally:
        retrain_mod._retrain_lock.release()

    assert status["drift_detected"] is True
    assert status["retrain_triggered"] is False
    assert status["retrain_trigger"] is None
    assert status["retrain_run_id"] is None
    assert status["retrain_skipped_reason"] == "retrain_already_running"
    assert load_drift_status(models_dir) == status
    assert load_retrain_history(models_dir) == []


def test_scheduler_config_env_parsing_and_validation(monkeypatch):
    for falsy in ("0", "false", "False", "NO", " off "):
        monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", falsy)
        assert mlops_config.scheduler_enabled() is False

    for truthy in ("", "1", "true", "yes"):
        monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", truthy)
        assert mlops_config.scheduler_enabled() is True

    monkeypatch.setenv("ECOTRACK_SCHEDULER_INTERVAL_SECONDS", "   ")
    monkeypatch.setenv("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS", "")
    assert mlops_config.get_scheduler_interval_seconds() == 86400.0
    assert mlops_config.get_scheduler_initial_delay_seconds() == 10.0

    monkeypatch.setenv("ECOTRACK_SCHEDULER_INTERVAL_SECONDS", "0.01")
    assert mlops_config.get_scheduler_interval_seconds() == 0.05
    monkeypatch.setenv("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS", "0")
    assert mlops_config.get_scheduler_initial_delay_seconds() == 0.0

    for bad in ("nan", "inf", "-inf", "abc", "0", "-5"):
        monkeypatch.setenv("ECOTRACK_SCHEDULER_INTERVAL_SECONDS", bad)
        with pytest.raises(ValueError):
            mlops_config.get_scheduler_interval_seconds()

    monkeypatch.setenv("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS", "-1")
    with pytest.raises(ValueError):
        mlops_config.get_scheduler_initial_delay_seconds()

    monkeypatch.setenv("ECOTRACK_DRIFT_RECENT_PATH", "   ")
    assert mlops_config.get_drift_recent_path() is None
    monkeypatch.setenv("ECOTRACK_DRIFT_RECENT_PATH", f"  {FIXTURE_CSV}  ")
    assert mlops_config.get_drift_recent_path() == FIXTURE_CSV

    monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", "1")
    for bad_kw in (
        {"interval": 0},
        {"interval": -1.0},
        {"interval": True},
        {"interval": float("nan")},
        {"initial_delay": -0.1},
        {"initial_delay": False},
    ):
        with pytest.raises(ValueError):
            start_scheduler(check_fn=lambda: None, **bad_kw)


def test_scheduler_lifecycle_disabled_in_test_cancel_restart_and_timeout(
    isolated_models_env, monkeypatch
):
    # 1. conftest.py disables scheduler across the test suite
    assert mlops_config.scheduler_enabled() is False
    with TestClient(app):
        assert not is_scheduler_running()

    # 2. When enabled, FastAPI lifespan starts scheduler, survives a failing tick, and stops cleanly
    monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", "1")
    monkeypatch.setenv("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS", "0.01")
    monkeypatch.setenv("ECOTRACK_SCHEDULER_INTERVAL_SECONDS", "0.05")

    calls = 0
    second_tick_done = threading.Event()

    def _flaky_check():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Simulated transient tick failure")
        second_tick_done.set()

    monkeypatch.setattr(scheduler_mod, "run_drift_check_and_retrain", _flaky_check)

    with TestClient(app):
        assert is_scheduler_running()
        assert start_scheduler() is False  # idempotent while running
        assert second_tick_done.wait(timeout=2.0), "scheduler loop stopped after tick 1 error"

    assert not is_scheduler_running()
    assert calls >= 2

    # 3. Stopping during initial_delay cancels without executing check_fn, and restart works cleanly
    early_calls = []
    assert start_scheduler(check_fn=lambda: early_calls.append(1), initial_delay=5.0, interval=5.0)
    assert is_scheduler_running()
    stop_scheduler(timeout=2.0)
    assert not is_scheduler_running()
    assert early_calls == []

    ran = threading.Event()
    assert start_scheduler(check_fn=ran.set, initial_delay=0.0, interval=1.0)
    assert ran.wait(timeout=1.0)
    stop_scheduler(timeout=2.0)
    assert not is_scheduler_running()

    # 4. stop_scheduler timeout leaves is_scheduler_running() True until blocked thread exits
    release_blocked = threading.Event()
    entered_blocked = threading.Event()

    def _blocking_tick():
        entered_blocked.set()
        release_blocked.wait(timeout=3.0)

    assert start_scheduler(check_fn=_blocking_tick, initial_delay=0.0, interval=1.0)
    assert entered_blocked.wait(timeout=1.0)
    stop_scheduler(timeout=0.05)
    assert is_scheduler_running() is True
    assert start_scheduler() is False
    release_blocked.set()
    for _ in range(40):
        if not is_scheduler_running():
            break
        time.sleep(0.02)
    stop_scheduler(timeout=2.0)
    assert not is_scheduler_running()


def test_run_drift_check_zero_args_and_unmocked_lifespan(isolated_models_env, monkeypatch):
    models_dir = isolated_models_env["models_dir"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    joblib.dump(_fit_tiny_xgb(train_df), models_dir / "xgboost_forecaster.joblib")

    assert load_drift_status() is None
    status = run_drift_check_and_retrain()
    assert status["drift_detected"] is False
    assert status["rolling_mape"] is not None
    assert load_drift_status() == status

    (models_dir / "drift_status.json").unlink()
    monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", "1")
    monkeypatch.setenv("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS", "0.01")
    monkeypatch.setenv("ECOTRACK_SCHEDULER_INTERVAL_SECONDS", "60.0")

    with TestClient(app):
        assert is_scheduler_running()
        for _ in range(100):
            if load_drift_status() is not None:
                break
            time.sleep(0.05)

    assert not is_scheduler_running()
    persisted = load_drift_status()
    assert persisted is not None
    assert persisted["drift_detected"] is False
    assert persisted["retrain_triggered"] is False


def test_scheduler_edge_cases_paths_timeouts_and_corrupt_status(
    isolated_models_env, monkeypatch, caplog
):
    models_dir = isolated_models_env["models_dir"]
    tmp_path = isolated_models_env["tmp"]
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)
    champion = _fit_tiny_xgb(train_df)

    # Blank string path arguments fall back cleanly instead of resolving to Path(".")
    cwd_guard = tmp_path / "cwd_guard"
    cwd_guard.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd_guard)
    status_blank = run_drift_check_and_retrain(
        reference_df=train_df,
        recent_df=train_df.copy(),
        champion_model=champion,
        data_path="",
        recent_path="  ",
        models_dir="",
    )
    assert load_drift_status(models_dir) == status_blank
    assert not (cwd_guard / "drift_status.json").exists()

    # Short recent_path (<= 24 rows) warns cleanly before lag_24h drops all rows
    short_csv = tmp_path / "short_recent.csv"
    pd.read_csv(FIXTURE_CSV).head(10).to_csv(short_csv, index=False)
    with caplog.at_level(logging.WARNING, logger="MLOpsScheduler"):
        status_short = run_drift_check_and_retrain(
            reference_df=train_df,
            recent_path=short_csv,
            champion_model=champion,
            models_dir=models_dir,
        )
    assert status_short["rolling_mape"] is None
    assert "lag_24h" in caplog.text

    # Corrupt / non-dict drift_status.json fails loudly
    status_path = models_dir / "drift_status.json"
    status_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected a JSON object"):
        load_drift_status(models_dir)
    status_path.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_drift_status(models_dir)

    # Values exceeding threading.TIMEOUT_MAX, self-stop, invalid stop_scheduler timeout, start failure
    monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", "1")
    assert start_scheduler(
        check_fn=lambda: None,
        initial_delay=float(threading.TIMEOUT_MAX) + 500.0,
        interval=1.0,
    )
    assert is_scheduler_running()
    stop_scheduler(timeout=float(threading.TIMEOUT_MAX) + 10.0)
    assert not is_scheduler_running()

    self_stopped = threading.Event()

    def _self_stop_check():
        stop_scheduler(timeout=1.0)
        self_stopped.set()

    assert start_scheduler(check_fn=_self_stop_check, initial_delay=0.0, interval=5.0)
    assert self_stopped.wait(timeout=2.0)
    for _ in range(40):
        if not is_scheduler_running():
            break
        time.sleep(0.02)
    stop_scheduler(timeout=1.0)
    assert not is_scheduler_running()

    for bad_timeout in (float("nan"), -1.0, True):
        with pytest.raises(ValueError):
            stop_scheduler(timeout=bad_timeout)

    monkeypatch.setattr(
        threading.Thread,
        "start",
        lambda self: (_ for _ in ()).throw(RuntimeError("Thread creation failed")),
    )
    with pytest.raises(RuntimeError, match="Thread creation failed"):
        start_scheduler(check_fn=lambda: None, initial_delay=1.0, interval=1.0)
    assert scheduler_mod._stop_event is None
    assert scheduler_mod._scheduler_thread is None
    assert not is_scheduler_running()
