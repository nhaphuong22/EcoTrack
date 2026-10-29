"""
Optuna search tests for Story 4.5 (FR47).

Covers: the training-split-only validation slicer never reaches the test split,
a tiny real study runs and logs nested MLflow trial runs, the completed-trial
count excludes pruned/failed trials, and the search is deterministic under a
fixed seed.
"""

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("optuna")
mlflow = pytest.importorskip("mlflow")

from mlflow.tracking import MlflowClient

from src.mlops.hpo import make_validation_slices, run_study
from src.models.train_models import (
    engineer_features,
    load_dataset,
    split_time_series_data,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


@pytest.fixture(scope="module")
def splits():
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    db = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str((tmp_path / "artifacts").as_posix()))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    yield tmp_path


def _storage(tmp_path, name="study.db"):
    return f"sqlite:///{(tmp_path / name).as_posix()}"


def test_slicer_never_reaches_the_test_split(splits):
    train_df, test_df = splits
    slices = make_validation_slices(train_df, n_slices=3)
    assert len(slices) >= 1

    train_max = pd.to_datetime(train_df["timestamp"]).max()
    test_min = pd.to_datetime(test_df["timestamp"]).min()
    for sub_train, val in slices:
        # Both sides of every fold stay strictly inside the training split.
        assert pd.to_datetime(sub_train["timestamp"]).max() <= train_max
        assert pd.to_datetime(val["timestamp"]).max() <= train_max
        assert pd.to_datetime(val["timestamp"]).min() < test_min


def test_xgboost_study_runs_and_logs_nested_runs(splits, temp_store, tmp_path):
    train_df, _ = splits
    result = run_study(
        "xgboost",
        train_df.iloc[:800],
        n_trials=5,
        storage=_storage(tmp_path),
        study_name="t-xgb",
        n_slices=2,
        n_startup_trials=5,  # == n_trials, so the pruner never prunes within this budget
    )

    assert result["model"] == "xgboost"
    assert result["n_complete"] == 5  # no pruning with startup == n_trials
    assert result["n_pruned"] == 0
    assert set(result["best_params"]).issubset({
        "n_estimators", "max_depth", "learning_rate", "subsample",
        "colsample_bytree", "min_child_weight", "reg_lambda",
    })

    # The parent search run has the completed trials as nested child runs in MLflow.
    client = MlflowClient()
    exp = client.get_experiment_by_name("ecotrack-forecasting")
    runs = client.search_runs([exp.experiment_id])
    parents = [r for r in runs if r.data.tags.get("mlflow.runName") == "hpo-xgboost"]
    assert parents, "expected a parent search run"
    parent_id = parents[0].info.run_id
    children = [r for r in runs if r.data.tags.get("mlflow.parentRunId") == parent_id]
    assert len(children) == 5
    assert all(c.data.tags.get("trial_state") == "COMPLETE" for c in children)


def test_completed_count_excludes_pruned(splits, tmp_path, monkeypatch):
    """With an aggressive pruner, the completed count hits the budget and excludes pruned trials."""
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    train_df, _ = splits
    n = 6
    result = run_study(
        "xgboost",
        train_df.iloc[:800],
        n_trials=n,
        storage=_storage(tmp_path, "pruned.db"),
        study_name="t-prune",
        n_slices=3,
        n_startup_trials=1,
        log_to_mlflow=False,
    )
    assert result["n_complete"] == n  # budget is completed trials, not total
    assert result["n_pruned"] >= 0
    # best value comes from a completed trial (not NaN).
    assert result["best_value"] == result["best_value"]


def test_runs_exactly_n_completed_trials_under_pruning(splits, tmp_path):
    """Guards the HPO fix: the budget is COMPLETED trials, not total, even with pruning active."""
    train_df, _ = splits
    n = 5
    result = run_study(
        "xgboost",
        train_df.iloc[:800],
        n_trials=n,
        storage=_storage(tmp_path, "ncomplete.db"),
        study_name="t-ncomplete",
        n_slices=3,
        n_startup_trials=1,  # pruning active well before n_trials
        log_to_mlflow=False,
    )
    assert result["n_complete"] == n  # exactly N completed despite pruning
    assert result["n_pruned"] >= 1  # pruning really did fire with this budget


def test_search_is_deterministic_under_fixed_seed(splits, tmp_path):
    train_df, _ = splits
    sub = train_df.iloc[:800]
    r1 = run_study("xgboost", sub, n_trials=5, storage=_storage(tmp_path, "d1.db"),
                   study_name="d1", n_slices=2, n_startup_trials=1, log_to_mlflow=False)
    r2 = run_study("xgboost", sub, n_trials=5, storage=_storage(tmp_path, "d2.db"),
                   study_name="d2", n_slices=2, n_startup_trials=1, log_to_mlflow=False)
    assert r1["best_params"] == r2["best_params"]
    assert r1["best_value"] == pytest.approx(r2["best_value"])


@pytest.mark.slow
def test_lstm_study_smoke(splits, tmp_path):
    """A minimal LSTM study exercises the set_params + per-trial time-budget path."""
    pytest.importorskip("torch")
    train_df, _ = splits
    result = run_study(
        "lstm",
        train_df.iloc[:700],
        n_trials=2,
        storage=_storage(tmp_path, "lstm.db"),
        study_name="t-lstm",
        n_slices=2,
        n_startup_trials=1,
        lstm_epoch_cap=1,
        trial_timeout_s=60,
        log_to_mlflow=False,
    )
    assert result["model"] == "lstm"
    assert result["n_complete"] >= 1
    assert set(result["best_params"]).issubset({"hidden_size", "num_layers", "learning_rate", "batch_size"})
