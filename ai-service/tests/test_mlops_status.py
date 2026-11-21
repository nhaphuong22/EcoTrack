"""
Offline tests for Story 4.10 (FR26): plain-Python MLOps status aggregation and
GET /internal/mlops/status.

Runs completely offline with zero model training (per Epic 4 working agreement),
using lightweight MLflow text artifacts and synthetic JSON/stub files under tmp_path.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.mlops import config as mlops_config
from src.mlops.config import CHAMPION_ALIAS, REGISTERED_MODEL_NAME
from src.mlops.retrain import load_retrain_history
from src.mlops.scheduler import load_drift_status
from src.mlops.status import get_mlops_status
from src.mlops.tracking import _epoch_ms_to_iso_utc


def _seed_mlflow_champion(
    tmp_path: Path,
    metrics: dict,
    *,
    with_alias: bool = True,
    with_flavor_data: bool = True,
    mlmodel_content: str | None = None,
    artifact_relpath: str | None = "model.xgb",
) -> tuple[str, Path]:
    mlflow = pytest.importorskip("mlflow")
    from mlflow.tracking import MlflowClient

    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "mlflow.db"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    uri = f"sqlite:///{db.as_posix()}"
    prev_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    try:
        exp_id = mlflow.create_experiment("ecotrack-test", artifact_location=artifacts.resolve().as_uri())
        with mlflow.start_run(experiment_id=exp_id) as run:
            mlflow.log_metrics(metrics)
            if mlmodel_content is not None:
                mlflow.log_text(mlmodel_content, "model/MLmodel")
                if artifact_relpath is not None:
                    mlflow.log_text("stub-xgb-bytes", f"model/{artifact_relpath}")
            elif with_flavor_data:
                mlflow.log_text(
                    "flavors:\n  xgboost:\n    data: model.xgb\n",
                    "model/MLmodel",
                )
                mlflow.log_text("stub-xgb-bytes", "model/model.xgb")
            else:
                mlflow.log_text("format: stub\n", "model/MLmodel")
            mlflow.log_text("dependencies: []\n", "model/conda.yaml")
            run_id = run.info.run_id
        mv = mlflow.register_model(f"runs:/{run_id}/model", REGISTERED_MODEL_NAME)
        if with_alias:
            client = MlflowClient(tracking_uri=uri)
            client.set_registered_model_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS, mv.version)
    finally:
        mlflow.set_tracking_uri(prev_uri)
    return uri, artifacts


def test_status_happy_path_mlflow_champion_without_binary_deserialization(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    import joblib

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    uri, _ = _seed_mlflow_champion(
        tmp_path,
        {"rmse_kwh": 41.2, "mape_percent": 7.5},
        with_flavor_data=True,
    )
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)

    # Guard against accidental heavy model loading on status probes.
    monkeypatch.setattr(
        mlflow.xgboost,
        "load_model",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("Must not deserialize MLflow model")),
    )
    monkeypatch.setattr(
        joblib,
        "load",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("Must not deserialize local joblib")),
    )

    drift_payload = {"checked_at": "2026-11-17T06:00:00Z", "drift_detected": False, "triggered_signals": []}
    (models_dir / "drift_status.json").write_text(json.dumps(drift_payload), encoding="utf-8")

    quality_payload = {"scenario_hvac_overrun": {"precision": 0.91, "recall": 0.88, "f1": 0.89, "false_positive_rate": 0.04}}
    (models_dir / "model_metadata.json").write_text(
        json.dumps({"isolation_forest_quality": quality_payload}),
        encoding="utf-8",
    )

    # Deliberately mix offsets, out-of-order entries, and equal-timestamp ties.
    oldest = {"run_id": "r1", "timestamp": "2026-11-16T00:00:00Z", "outcome": "rejected"}
    tie_a = {"run_id": "r2", "timestamp": "2026-11-17T08:00:00+07:00", "outcome": "promoted"}
    tie_b = {"run_id": "r3", "timestamp": "2026-11-17T01:00:00Z", "outcome": "rejected"}
    newest = {"run_id": "r4", "timestamp": "2026-11-17T02:00:00Z", "outcome": "promoted"}
    (models_dir / "retrain_history.json").write_text(json.dumps([oldest, tie_a, tie_b, newest]), encoding="utf-8")

    benchmark_file = tmp_path / "results.json"
    benchmark_payload = {"generated_horizon": 24, "models": [{"model": "xgboost", "mape_percent": 8.0}]}
    benchmark_file.write_text(json.dumps(benchmark_payload), encoding="utf-8")

    status = get_mlops_status(models_dir=models_dir, tracking_uri=uri, benchmark_path=benchmark_file)

    assert status["errors"] == {}
    assert status["champion"]["status"] == "resolved"
    assert status["champion"]["source"] == "mlflow"
    assert status["champion"]["version"] == "1"
    assert status["champion"]["trained_at"] and status["champion"]["trained_at"].endswith("Z")
    assert status["champion"]["metrics"] == {"rmse_kwh": 41.2, "mape_percent": 7.5}
    assert status["drift"] == drift_payload
    assert status["anomaly_quality"] == quality_payload
    assert [row["run_id"] for row in status["retrain_history"]] == ["r4", "r2", "r3", "r1"]
    assert status["benchmark"] == benchmark_payload


def test_status_local_fallback_honest_trained_at_and_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    missing_bench = tmp_path / "absent_results.json"

    # Empty dir -> unavailable champion, null/[] optional sections.
    empty_status = get_mlops_status(models_dir=models_dir, benchmark_path=missing_bench)
    assert empty_status["champion"] == {
        "status": "unavailable",
        "source": None,
        "version": None,
        "trained_at": None,
        "metrics": None,
        "error": None,
    }
    assert empty_status["drift"] is None
    assert empty_status["anomaly_quality"] is None
    assert empty_status["retrain_history"] == []
    assert empty_status["benchmark"] is None
    assert empty_status["errors"] == {}

    # Metadata without xgboost_forecaster.joblib on disk -> still unavailable (matches serving/health).
    (models_dir / "model_metadata.json").write_text(
        json.dumps({"xgboost_metrics": {"rmse_kwh": 39.5, "mape_percent": 6.8}}),
        encoding="utf-8",
    )
    meta_only_status = get_mlops_status(models_dir=models_dir, benchmark_path=missing_bench)
    assert meta_only_status["champion"]["status"] == "unavailable"
    assert meta_only_status["champion"]["metrics"] is None

    # Local fallback without train_end_timestamp -> trained_at must be None (never file mtime).
    (models_dir / "xgboost_forecaster.joblib").write_bytes(b"stub")
    fallback_no_ts = get_mlops_status(models_dir=models_dir, benchmark_path=missing_bench)
    assert fallback_no_ts["champion"]["status"] == "fallback"
    assert fallback_no_ts["champion"]["source"] == "local"
    assert fallback_no_ts["champion"]["version"] == "local"
    assert fallback_no_ts["champion"]["trained_at"] is None
    assert fallback_no_ts["champion"]["metrics"] == {"rmse_kwh": 39.5, "mape_percent": 6.8}

    # With train_end_timestamp -> normalized to ISO 8601 UTC ('Z').
    (models_dir / "model_metadata.json").write_text(
        json.dumps(
            {
                "train_end_timestamp": "2026-11-17T08:30:00",
                "xgboost_metrics": {"rmse_kwh": 39.5, "mape_percent": 6.8},
            }
        ),
        encoding="utf-8",
    )
    fallback_with_ts = get_mlops_status(models_dir=models_dir, benchmark_path=missing_bench)
    assert fallback_with_ts["champion"]["trained_at"] == "2026-11-17T08:30:00Z"

    # Initialized MLflow store without a champion alias falls back cleanly to local.
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    no_alias_uri, _ = _seed_mlflow_champion(tmp_path / "no_alias", {"rmse_kwh": 11.0}, with_alias=False)
    no_alias_status = get_mlops_status(models_dir=models_dir, tracking_uri=no_alias_uri, benchmark_path=missing_bench)
    assert no_alias_status["champion"]["status"] == "fallback"
    assert no_alias_status["champion"]["source"] == "local"

    # 0-byte mlflow.db is treated as uninitialized without mutating the empty file on read.
    zero_db = tmp_path / "zero_mlflow.db"
    zero_db.write_bytes(b"")
    zero_status = get_mlops_status(
        models_dir=models_dir,
        tracking_uri=f"sqlite:///{zero_db.as_posix()}",
        benchmark_path=missing_bench,
    )
    assert zero_status["champion"]["status"] == "fallback"
    assert zero_db.stat().st_size == 0


def test_status_broken_mlflow_champion_never_falls_back_to_local(tmp_path, monkeypatch):
    pytest.importorskip("mlflow")
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "xgboost_forecaster.joblib").write_bytes(b"local-fallback")
    (models_dir / "model_metadata.json").write_text(
        json.dumps({"xgboost_metrics": {"rmse_kwh": 999.0}}),
        encoding="utf-8",
    )
    (models_dir / "drift_status.json").write_text(
        json.dumps({"checked_at": "2026-11-17T09:00:00Z", "drift_detected": True}),
        encoding="utf-8",
    )

    # 1. Partial artifact deletion (model.xgb removed while conda.yaml & MLmodel remain) -> broken!
    uri_partial, arts_partial = _seed_mlflow_champion(tmp_path / "partial", {"rmse_kwh": 35.0}, with_flavor_data=True)
    for xgb_file in arts_partial.rglob("model.xgb"):
        xgb_file.unlink()
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)

    partial_status = get_mlops_status(models_dir=models_dir, tracking_uri=uri_partial, benchmark_path=tmp_path / "none.json")
    assert partial_status["champion"]["status"] == "broken"
    assert partial_status["champion"]["source"] == "mlflow"
    assert partial_status["champion"]["version"] == "1"
    assert partial_status["champion"]["metrics"] is None
    assert "model.xgb" in partial_status["champion"]["error"]
    assert "champion" in partial_status["errors"]
    assert partial_status["drift"] == {"checked_at": "2026-11-17T09:00:00Z", "drift_detected": True}

    # 2. Missing MLmodel while conda.yaml remains -> broken!
    uri_no_mlmodel, arts_no_mlmodel = _seed_mlflow_champion(tmp_path / "no_mlmodel", {"rmse_kwh": 35.0})
    for mlmodel_file in arts_no_mlmodel.rglob("MLmodel"):
        mlmodel_file.unlink()
    no_mlmodel_status = get_mlops_status(
        models_dir=models_dir, tracking_uri=uri_no_mlmodel, benchmark_path=tmp_path / "none.json"
    )
    assert no_mlmodel_status["champion"]["status"] == "broken"
    assert "MLmodel" in no_mlmodel_status["champion"]["error"]

    # 3. Full artifacts removed -> broken!
    shutil.rmtree(arts_no_mlmodel)
    status = get_mlops_status(models_dir=models_dir, tracking_uri=uri_no_mlmodel, benchmark_path=tmp_path / "none.json")
    assert status["champion"]["status"] == "broken"

    # 4. Corrupt MLflow SQLite DB also reports broken without falling back to local metrics.
    corrupt_db = tmp_path / "corrupt_mlflow.db"
    corrupt_db.write_bytes(b"not-a-sqlite-db")
    corrupt_status = get_mlops_status(
        models_dir=models_dir,
        tracking_uri=f"sqlite:///{corrupt_db.as_posix()}",
        benchmark_path=tmp_path / "none.json",
    )
    assert corrupt_status["champion"]["status"] == "broken"
    assert corrupt_status["champion"]["metrics"] is None
    assert "champion" in corrupt_status["errors"]

    # Out-of-range epoch timestamps never raise OverflowError.
    assert _epoch_ms_to_iso_utc(1e20) is None


def test_status_isolates_corrupt_json_and_non_finite_while_loaders_fail_loud(tmp_path, monkeypatch):
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    (models_dir / "drift_status.json").write_text("{corrupt", encoding="utf-8")
    (models_dir / "retrain_history.json").write_text("{}", encoding="utf-8")
    (models_dir / "model_metadata.json").write_text('["not-an-object"]', encoding="utf-8")
    bad_bench = tmp_path / "results.json"
    bad_bench.write_text('{"score": Infinity}', encoding="utf-8")

    # Fail-loud contracts for scheduler/retrain callers remain untouched.
    with pytest.raises(json.JSONDecodeError):
        load_drift_status(models_dir)
    with pytest.raises(ValueError):
        load_retrain_history(models_dir)

    status = get_mlops_status(models_dir=models_dir, benchmark_path=bad_bench)
    assert status["drift"] is None
    assert status["retrain_history"] == []
    assert status["anomaly_quality"] is None
    assert status["benchmark"] is None
    assert status["champion"]["error"] == status["errors"]["champion"]
    assert set(status["errors"].keys()) == {"champion", "anomaly_quality", "drift", "retrain_history", "benchmark"}

    # Non-dict section values & malformed train_end_timestamp are isolated consistently.
    (models_dir / "xgboost_forecaster.joblib").write_bytes(b"stub")
    (models_dir / "drift_status.json").write_text('{"mape": NaN}', encoding="utf-8")
    (models_dir / "retrain_history.json").write_text('["not-an-object"]', encoding="utf-8")
    (models_dir / "model_metadata.json").write_text(
        json.dumps(
            {
                "xgboost_metrics": ["bad"],
                "train_end_timestamp": "not-a-timestamp",
                "isolation_forest_quality": ["bad"],
            }
        ),
        encoding="utf-8",
    )
    bad_types_status = get_mlops_status(models_dir=models_dir, benchmark_path=bad_bench)
    assert bad_types_status["champion"]["status"] == "fallback"
    assert bad_types_status["champion"]["metrics"] is None
    assert bad_types_status["champion"]["trained_at"] is None
    assert bad_types_status["champion"]["error"] == bad_types_status["errors"]["champion"]
    assert "xgboost_metrics" in bad_types_status["champion"]["error"]
    assert bad_types_status["anomaly_quality"] is None
    assert "anomaly_quality" in bad_types_status["errors"]
    assert bad_types_status["drift"] is None
    assert "drift" in bad_types_status["errors"]
    assert bad_types_status["retrain_history"] == []
    assert "retrain_history" in bad_types_status["errors"]

    # Output remains strict RFC-8259 JSON serializable.
    json.dumps(status, allow_nan=False)
    json.dumps(bad_types_status, allow_nan=False)


def test_status_mlmodel_flavors_nested_artifacts_and_tracking_uri_whitespace(
    tmp_path, monkeypatch
):
    from src.mlops.status import get_mlops_status

    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    empty_models = tmp_path / "models_empty"
    empty_models.mkdir()
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(empty_models))
    monkeypatch.setenv("ECOTRACK_BENCHMARK_RESULTS_PATH", str(tmp_path / "missing_bench.json"))

    # 1. MLmodel missing flavors -> broken.
    uri_no_flavors, _ = _seed_mlflow_champion(
        tmp_path / "no_flavors", {"rmse_kwh": 21.0}, with_flavor_data=False
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri_no_flavors)
    assert get_mlops_status()["champion"]["status"] == "broken"

    # 2. Non-dict MLmodel YAML -> broken.
    uri_nondict, _ = _seed_mlflow_champion(
        tmp_path / "nondict",
        {"rmse_kwh": 21.0},
        mlmodel_content="- not-a-mapping\n",
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri_nondict)
    assert get_mlops_status()["champion"]["status"] == "broken"

    # 3. Invalid data path "." -> broken.
    uri_dot_data, _ = _seed_mlflow_champion(
        tmp_path / "dot_data",
        {"rmse_kwh": 21.0},
        mlmodel_content="flavors:\n  xgboost:\n    data: .\n",
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri_dot_data)
    assert get_mlops_status()["champion"]["status"] == "broken"

    # 4. Nested artifact subdir/model.xgb present -> resolved; deleting leaf file -> broken.
    uri_nested, arts_nested = _seed_mlflow_champion(
        tmp_path / "nested",
        {"rmse_kwh": 19.5},
        mlmodel_content="flavors:\n  xgboost:\n    data: subdir/model.xgb\n",
        artifact_relpath="subdir/model.xgb",
    )
    # Whitespace-padded MLFLOW_TRACKING_URI is trimmed consistently by config & status.
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"  {uri_nested}  ")
    assert mlops_config.get_tracking_uri() == uri_nested
    assert mlops_config.is_mlflow_initialised(f"  {uri_nested}  ") is True
    assert get_mlops_status()["champion"]["status"] == "resolved"

    for leaf in arts_nested.rglob("model.xgb"):
        leaf.unlink()
    assert get_mlops_status()["champion"]["status"] == "broken"

    # 5. Whitespace-only MLFLOW_TRACKING_URI treated as unset / uninitialized.
    # Point the default store at an empty folder so a real ai-service/mlruns/mlflow.db on the
    # developer's machine cannot make the "uninitialized" assertion fail.
    monkeypatch.setattr(mlops_config, "mlruns_dir", lambda: tmp_path / "no_default_store")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    unset_uri = mlops_config.get_tracking_uri()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "   ")
    assert mlops_config.get_tracking_uri() == unset_uri
    assert mlops_config.is_mlflow_initialised("   ") is False


def test_status_nan_mlflow_metric_warned_and_filtered(tmp_path, monkeypatch, caplog):
    import json
    import logging
    from fastapi.testclient import TestClient
    from src.main import app
    from src.mlops.tracking import get_champion_metadata

    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("ECOTRACK_BENCHMARK_RESULTS_PATH", str(tmp_path / "missing_bench.json"))
    monkeypatch.setenv("INTERNAL_API_KEY", "status-secret")

    uri, _ = _seed_mlflow_champion(
        tmp_path / "nan_run",
        {"rmse_kwh": 22.5, "nan_metric": float("nan")},
    )
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)

    # MLflow SQLite initialization triggers Alembic's logging.config.fileConfig(),
    # which replaces root logger handlers and detaches pytest's caplog handler.
    root_logger = logging.getLogger()
    if caplog.handler not in root_logger.handlers:
        root_logger.addHandler(caplog.handler)

    with caplog.at_level(logging.WARNING):
        meta = get_champion_metadata()
    assert meta is not None
    assert meta["metrics"] == {"rmse_kwh": 22.5}
    assert any("non-finite" in rec.message.lower() for rec in caplog.records)

    with TestClient(app) as client:
        resp = client.get(
            "/internal/mlops/status",
            headers={"X-Internal-Token": "status-secret"},
        )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["champion"]["metrics"] == {"rmse_kwh": 22.5}
    json.dumps(payload, allow_nan=False)


def test_status_json_edge_cases_and_lightweight_import(tmp_path, monkeypatch, caplog):
    import logging
    import subprocess
    import sys
    from src.mlops.status import get_mlops_status

    # 1. validate_duration_seconds rejects None and non-scalar containers.
    with pytest.raises(ValueError):
        mlops_config.validate_duration_seconds(None, "timeout")

    # 2. Default benchmark path resolves exactly to AI_SERVICE_DIR/experiments/benchmark/results.json.
    monkeypatch.delenv("ECOTRACK_BENCHMARK_RESULTS_PATH", raising=False)
    expected_bench = mlops_config.AI_SERVICE_DIR / "experiments" / "benchmark" / "results.json"
    assert mlops_config.get_benchmark_results_path() == expected_bench

    # 3. 1e500 overflow float, directory at artifact path, 0-byte .joblib,
    # and malformed retrain_history timestamps are isolated without crashing.
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    models_dir = tmp_path / "models_edge"
    models_dir.mkdir()
    (models_dir / "xgboost_forecaster.joblib").write_bytes(b"")  # 0 bytes -> unavailable
    (models_dir / "model_metadata.json").write_text('{"rmse_kwh": 1e500}', encoding="utf-8")
    (models_dir / "drift_status.json").mkdir()  # directory at file path
    (models_dir / "retrain_history.json").write_text(
        (
            '[{"timestamp": "not-a-timestamp", "trigger": "manual"},'
            ' {"timestamp": "2026-01-02T00:00:00Z", "trigger": "scheduled"},'
            ' {"trigger": "missing-ts"}]'
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("ECOTRACK_BENCHMARK_RESULTS_PATH", str(tmp_path / "missing_bench.json"))

    with caplog.at_level(logging.WARNING):
        payload = get_mlops_status()

    assert payload["champion"]["status"] == "unavailable"
    assert payload["champion"]["metrics"] is None
    assert "Non-finite" in payload["errors"]["champion"]
    assert "Non-finite" in payload["errors"]["anomaly_quality"]
    assert payload["drift"] is None
    assert "drift" in payload["errors"]
    assert payload["retrain_history"][0]["trigger"] == "scheduled"
    assert len(payload["retrain_history"]) == 3
    assert any("retrain_history" in rec.message for rec in caplog.records)

    # 4. astimezone overflow on train_end_timestamp and invalid inner metadata types.
    models_dir_2 = tmp_path / "models_inner"
    models_dir_2.mkdir()
    (models_dir_2 / "xgboost_forecaster.joblib").write_bytes(b"xgb")
    (models_dir_2 / "model_metadata.json").write_text(
        json.dumps(
            {
                "train_end_timestamp": "9999-12-31T23:59:59-05:00",
                "xgboost_metrics": ["bad"],
                "isolation_forest_quality": "bad",
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        payload2 = get_mlops_status(models_dir=models_dir_2)

    assert payload2["champion"]["status"] == "fallback"
    assert payload2["champion"]["trained_at"] is None
    assert payload2["champion"]["metrics"] is None
    assert payload2["anomaly_quality"] is None
    assert "Invalid train_end_timestamp" in payload2["errors"]["champion"]
    assert "Expected dict for xgboost_metrics" in payload2["errors"]["champion"]
    assert "Expected dict for isolation_forest_quality" in payload2["errors"]["anomaly_quality"]

    # 5. Importing src.mlops.status stays lightweight (no FastAPI, MLflow, retrain, or scheduler imported).
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, src.mlops.status; "
                "assert {'fastapi', 'mlflow', 'src.mlops.retrain', 'src.mlops.scheduler'}.isdisjoint(sys.modules)"
            ),
        ],
        cwd=str(mlops_config.AI_SERVICE_DIR),
        check=True,
    )


def test_http_internal_mlops_status_auth_to_thread_and_states(tmp_path, monkeypatch):
    # Config helper: unset/whitespace defaults to experiments/benchmark/results.json.
    monkeypatch.setenv("ECOTRACK_BENCHMARK_RESULTS_PATH", "   ")
    assert mlops_config.get_benchmark_results_path().name == "results.json"

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    bench_file = tmp_path / "bench.json"
    bench_file.write_text(json.dumps({"models": [{"model": "xgboost"}]}), encoding="utf-8")

    monkeypatch.setenv("INTERNAL_API_KEY", "secret-token")
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    monkeypatch.setenv("ECOTRACK_SCHEDULER_ENABLED", "0")
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("ECOTRACK_BENCHMARK_RESULTS_PATH", str(bench_file))
    assert mlops_config.get_benchmark_results_path() == bench_file

    called_in_thread = []
    orig_to_thread = asyncio.to_thread

    async def spy_to_thread(func, /, *args, **kwargs):
        called_in_thread.append(getattr(func, "__name__", str(func)))
        return await orig_to_thread(func, *args, **kwargs)

    monkeypatch.setattr("src.api.routers.mlops.asyncio.to_thread", spy_to_thread)

    with TestClient(app) as client:
        assert client.get("/internal/mlops/status").status_code == 401
        wrong = client.get("/internal/mlops/status", headers={"X-Internal-Token": "wrong-token"})
        assert wrong.status_code == 401
        assert wrong.json()["code"] == "ERR_UNAUTHORIZED"

        ok = client.get("/internal/mlops/status", headers={"X-Internal-Token": "secret-token"})
        assert ok.status_code == 200
        body = ok.json()
        assert body["champion"]["status"] == "unavailable"
        assert body["drift"] is None
        assert body["retrain_history"] == []
        assert body["benchmark"] == {"models": [{"model": "xgboost"}]}
        assert body["errors"] == {}
        assert "get_mlops_status" in called_in_thread

        # Resolved MLflow champion over HTTP 200.
        uri, arts = _seed_mlflow_champion(tmp_path / "http_mlflow", {"rmse_kwh": 22.5}, with_flavor_data=True)
        monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
        monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
        ok_mlflow = client.get("/internal/mlops/status", headers={"X-Internal-Token": "secret-token"})
        assert ok_mlflow.status_code == 200
        assert ok_mlflow.json()["champion"]["status"] == "resolved"
        assert ok_mlflow.json()["champion"]["metrics"] == {"rmse_kwh": 22.5}

        # Broken MLflow champion over HTTP 200.
        shutil.rmtree(arts)
        broken_mlflow = client.get("/internal/mlops/status", headers={"X-Internal-Token": "secret-token"})
        assert broken_mlflow.status_code == 200
        assert broken_mlflow.json()["champion"]["status"] == "broken"
        assert "champion" in broken_mlflow.json()["errors"]
