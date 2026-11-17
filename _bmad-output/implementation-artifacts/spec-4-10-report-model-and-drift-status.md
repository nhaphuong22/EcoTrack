---
title: 'Story 4.10: Report model and drift status'
type: 'feature'
created: '2026-11-17'
status: 'done'
baseline_commit: '8bdbf26c281b7c5e9d27b513560bd4e97cbb0feb'
route: 'oneshot'
review_loop_iteration: 0
story_keys:
  - 4-10-report-model-and-drift-status
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 4.4–4.9 produced benchmark results (`results.json`), MLflow champion tracking, drift snapshots (`drift_status.json`), anomaly detector quality metrics (`isolation_forest_quality` in `model_metadata.json`), and retraining history (`retrain_history.json`), but there is still no consolidated `GET /internal/mlops/status` endpoint (FR26) for the gateway (Story 4.11) and admin monitoring UI (Story 4.12) to read model health without knowing MLflow internals.

**Approach:** Add a plain-Python MLOps status aggregator (`ai-service/src/mlops/status.py`, AD-1) reusing existing `mlops` helpers and expose `GET /internal/mlops/status` in `ai-service/src/api/routers/mlops.py` behind the existing `X-Internal-Token` middleware (FR17):
- **Lightweight champion inspection & honest timestamps:** Add `get_champion_metadata()` to `ai-service/src/mlops/tracking.py` reading `version`, ISO 8601 UTC `trained_at`, and `metrics` via `MlflowClient` (`get_model_version_by_alias` + `get_run`) plus lightweight artifact presence check without deserializing the XGBoost binary. When MLflow is disabled, uninitialized, or lacks a `champion` alias, fall back to `get_models_dir()` (`source: "local"`, `status: "fallback"`, `version: "local"`, `metrics` from `model_metadata.json` `xgboost_metrics`, and `trained_at` from `train_end_timestamp` in ISO 8601 UTC or `None` when absent — never file `mtime`), or `status: "unavailable"` when no local model exists. When a resolved MLflow `champion` is broken/unreadable or SQLite fails, never fall back silently to `models_saved/`: return HTTP 200 with `champion.status = "broken"`, `source = "mlflow"`, `metrics = None`, and a diagnostic `error`.
- **Consolidated non-blocking HTTP 200 contract & per-section error isolation:** `GET /internal/mlops/status` runs `get_mlops_status()` inside `asyncio.to_thread` (NFR6 / AD-2) and returns `{champion, drift, anomaly_quality, retrain_history, benchmark, errors}` with HTTP 200. Missing optional files return `None` (`drift`, `anomaly_quality`, `benchmark`) or `[]` (`retrain_history`); add `get_benchmark_results_path()` in `ai-service/src/mlops/config.py` (`ECOTRACK_BENCHMARK_RESULTS_PATH`, defaulting to `ai-service/experiments/benchmark/results.json`, returned verbatim). Preserve fail-loud behavior in `load_drift_status()` and `load_retrain_history()` for scheduler/retrain callers while `get_mlops_status()` logs and isolates corrupt JSON, invalid section shapes, or non-finite numbers (`NaN`/`Inf`) per section into `errors` (returning `None`/`[]` for the bad section), and stably sorts `retrain_history` newest-first by `timestamp`.
- **Offline pytest coverage (`ai-service/tests/test_mlops_status.py`):** Exercise plain-Python and `TestClient` paths across MLflow resolved champion (verifying no model deserialization), local fallback (`trained_at: None` vs `train_end_timestamp`), unavailable local model, broken MLflow champion non-fallback, absent artifacts (`null`/`[]`), corrupt JSON & non-finite float isolation in `errors`, newest-first `retrain_history` ordering, `asyncio.to_thread` execution, and `X-Internal-Token` `401` enforcement.

</frozen-after-approval>

## Implementation Notes

- Added `get_benchmark_results_path()` (`ECOTRACK_BENCHMARK_RESULTS_PATH`, defaulting to `ai-service/experiments/benchmark/results.json`) in `ai-service/src/mlops/config.py`, documented it in `ai-service/.env.example`, and isolated `ECOTRACK_BENCHMARK_RESULTS_PATH=""` in `ai-service/tests/conftest.py`.
- Added lightweight `get_champion_metadata()` in `ai-service/src/mlops/tracking.py` reading `MlflowClient(tracking_uri=uri)` inside a `try/except` guard (catching DB initialization/lock errors cleanly), verifying artifacts via `mlflow.artifacts.list_artifacts(...)` without deserializing the XGBoost model binary, and emitting ISO 8601 UTC `trained_at` plus finite float metrics.
- Created plain-Python `ai-service/src/mlops/status.py` (`get_mlops_status()`, AD-1) aggregating `champion`, `drift`, `anomaly_quality`, `retrain_history`, `benchmark`, and per-section `errors` at HTTP 200:
  - Reuses `_drift_status_lock` / `_history_lock`, `_optional_path` / `_optional_str`, and strict `json.loads(..., parse_constant=_reject_non_finite)` so `NaN`/`Inf` or corrupt JSON files are isolated per section in `errors` while `load_drift_status()` and `load_retrain_history()` stay fail-loud for scheduler/retrain callers.
  - Derives local fallback `trained_at` strictly from `train_end_timestamp` (ISO 8601 UTC, or `None` when absent — never file `mtime`), never falls back silently when MLflow `champion` is `"broken"`, and sorts `retrain_history` stably newest-first by `timestamp`.
- Added `GET /internal/mlops/status` in `ai-service/src/api/routers/mlops.py` dispatching `get_mlops_status` via `asyncio.to_thread` behind the existing `X-Internal-Token` middleware.
- Added offline tests in `ai-service/tests/test_mlops_status.py` (no model training). Verified `python -m py_compile` on all 6 Python files and `pytest --noconftest tests/test_mlops_status.py -q` (`5 passed, 1 warning in 25.00s`). Full suite command for the project owner (runs `conftest.py` session fixture):
  - Working directory: `c:\Users\ADMIN\Desktop\EcoTrack\ai-service`
  - Command: `pytest tests/test_mlops_status.py tests/test_mlops_tracking.py tests/test_serving_champion_load.py tests/test_health_champion.py tests/test_mlops_scheduler.py tests/test_mlops_retrain.py tests/test_smoke.py -q`
- Post-review hardening (`blind-hunter`):
  - Verified `MLmodel` (`file_size > 0`) and flavor-declared `data`/`model_path` artifact presence via `client.get_model_version_download_uri()` + `mlflow.artifacts.download_artifacts(..., tracking_uri=uri, registry_uri=uri)` in `ai-service/src/mlops/tracking.py` (without deserializing the XGBoost binary or depending on process-global `mlflow.get_tracking_uri()`).
  - Guarded `_epoch_ms_to_iso_utc()` against `(ValueError, OverflowError, OSError)` and wrapped `get_champion_metadata()` and `_resolve_champion_summary()` so unexpected MLflow/timestamp failures degrade to `champion.status = "broken"` at HTTP 200.
  - Stripped whitespace on `MLFLOW_TRACKING_URI` in `get_tracking_uri()` and required `db_path.is_file() and db_path.stat().st_size > 0` in `is_mlflow_initialised()` so 0-byte `mlflow.db` files are not initialized on read-only status probes.
  - Tightened `status.py` local fallback to require `xgboost_forecaster.joblib` on disk (`if xgb_exists:`), validated `xgboost_metrics` & `train_end_timestamp` types/formats, populated `champion["error"]` consistently across local/unavailable paths, and caught `(ValueError, OverflowError, OSError)` in `_history_sort_key`.
  - Pointed `ECOTRACK_BENCHMARK_RESULTS_PATH` in `ai-service/tests/conftest.py` at a non-existent path inside `temp_dir` instead of `""` so local `experiments/benchmark/results.json` never leaks into tests, and expanded `ai-service/tests/test_mlops_status.py`.

## Review Triage Log

Blind-hunter (only layer configured in this render) against Story 4.10 changes (`35.94 kB -> N = min(floor(sqrt(35.94) + 1), 10) = 6`; 10 findings reported).

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `get_champion_metadata` only checked `if not artifacts:`, marking partial artifact loss (`MLmodel` or `model.xgb` missing while `conda.yaml` remains) as `"resolved"` | medium | patch | Verified against MLflow 3.17.2. Added `_verify_champion_artifacts()` checking `MLmodel` (`file_size > 0`) and declared `flavors.*.data`/`model_path` entries via `get_model_version_download_uri()`. |
| 2 | `status.py` set `errors["champion"]` on local/unavailable `meta_err` while leaving `champion["error"]` as `None` | medium | patch | Updated `fallback` and `unavailable` return dicts in `_resolve_champion_summary()` to populate `champion["error"] = champ_err`. |
| 3 | `status.py` silently ignored non-dict `xgboost_metrics` & malformed `train_end_timestamp`; `_history_sort_key` only caught `ValueError` | medium | patch | Validated `xgboost_metrics` type identically to `isolation_forest_quality`, logged & recorded malformed `train_end_timestamp` into `errors["champion"]`, and caught `(ValueError, OverflowError, OSError)`. |
| 4 | `_epoch_ms_to_iso_utc()` left `datetime.fromtimestamp` unguarded (`OverflowError`) and `get_champion_metadata()` ran outside `try/except` in `status.py` | medium | patch | Guarded `_epoch_ms_to_iso_utc()` with `(TypeError, ValueError, OverflowError, OSError)` inside `get_champion_metadata()`'s `try/except`, and added defensive `try/except` in `_resolve_champion_summary()`. |
| 5 | `get_tracking_uri()` did not strip whitespace and 0-byte `mlflow.db` triggered SQLite DDL initialization during read-only `/status` | medium | patch | Stripped `MLFLOW_TRACKING_URI` in `get_tracking_uri()`, normalized `tracking_uri` in `get_champion_metadata()`, and required `st_size > 0` in `is_mlflow_initialised()`. |
| 6 | (a) Local fallback triggered on `xgboost_metrics` even when `.joblib` was missing (`if xgb_exists or xgb_metrics is not None:`); (b) missing `response_model`; (c) in-memory HTTP float guard | medium / low / false | patch / reject | Changed fallback guard to `if xgb_exists:` matching `serving_frame`/`/health`. Rejected `response_model` boilerplate (`/ponytail ultra`, consistent with `POST /retrain`); `false` on float guard since `_read_json_strict` rejects non-finite constants and `get_champion_metadata` filters `math.isfinite`. |
| 7 | `conftest.py` set `ECOTRACK_BENCHMARK_RESULTS_PATH=""` which resolved to gitignored local `experiments/benchmark/results.json` | high | patch | Updated `conftest.py` to point `ECOTRACK_BENCHMARK_RESULTS_PATH` at `temp_models_dir / "benchmark_results.json"` so tests start isolated from local artifacts. |
| 8 | Relative `ECOTRACK_BENCHMARK_RESULTS_PATH` in `.env.example` assumes CWD = `ai-service/` | low | reject | Consistent with `ECOTRACK_DATA_PATH`, `ECOTRACK_MODELS_DIR`, and `ECOTRACK_DRIFT_RECENT_PATH` in `src/config.py` and `src/mlops/config.py` (all documented for CWD=`ai-service/`). |
| 9 | `test_mlops_status.py` leaked global `mlflow.set_tracking_uri` and lacked coverage for wrong token, MLflow HTTP 200, no-alias fallback, partial artifacts, bad section types, and TZ/tie sorting | medium | patch | Restored previous tracking URI in `_seed_mlflow_champion` `finally:` block and expanded `test_mlops_status.py` across all cited branches. |
| 10 | (a) Pre-existing Story 4.5 `register_and_bootstrap_champion` missing `tracking_uri` & `champion_health` catching `Exception` as `"unavailable"`; (b) owner test command omitted tracking/serving/smoke tests | low | defer / patch | Deferred pre-existing Story 4.5 `tracking.py` items to `deferred-work.md`; added `test_mlops_tracking.py`, `test_serving_champion_load.py`, `test_health_champion.py`, and `test_smoke.py` to owner verification command. |
