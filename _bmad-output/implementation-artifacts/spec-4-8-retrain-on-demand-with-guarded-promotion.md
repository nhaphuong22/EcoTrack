---
title: 'Story 4.8: Retrain on demand with guarded promotion'
type: 'feature'
created: '2026-11-17'
status: 'done'
baseline_commit: '23d46e68d2a81ca1daa1f7ea5ce9eb53546d16bb'
route: 'oneshot'
review_loop_iteration: 0
story_keys:
  - 4-8-retrain-on-demand-with-guarded-promotion
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After Story 4.5 registered the initial `champion` forecaster and Stories 4.6–4.7 added drift and anomaly-quality checks, there is still no way to retrain the forecaster on demand or promote a stronger model over the current champion (FR25). Without a guarded promotion flow, a retrain could either overwrite the serving model with a worse one or require a service restart to take effect.

**Approach:** Add a plain-Python retrain coordinator (`ai-service/src/mlops/retrain.py`, AD-1) and expose `POST /internal/mlops/retrain` (`ai-service/src/api/routers/mlops.py`, mounted in `ai-service/src/main.py` behind the existing `/internal/*` token middleware):
- **Atomic concurrency lock (`409` vs `202`):** An in-process `threading.Lock` guards retrain execution (`RetrainAlreadyRunningError` -> HTTP 409 `ERR_RETRAIN_IN_PROGRESS`). `start_retrain(trigger="manual")` acquires the lock atomically, launches `run_retrain(...)` in a daemon background thread without blocking the FastAPI event loop (NFR6 / AD-2), and immediately returns HTTP 202 with `{run_id, status: "running", started_at, trigger}` (ISO 8601 UTC, NFR7). The lock is always released in a `finally` block across every terminal path.
- **Fair holdout evaluation (no temporal leakage):** `run_retrain()` loads the dataset via `src.config.get_data_path()`, runs `engineer_features`, and splits chronologically (`split_time_series_data(train_ratio=0.8)`), verifying `train_df["timestamp"].max() < test_df["timestamp"].min()`. The challenger is trained on `train_df` only, and both the current `champion` and the `challenger` are scored on the same held-out `test_df` using an identical MAPE helper that filters out zero-target (`y == 0`) rows and rejects non-finite (`NaN`/`Inf`) values.
- **Guarded promotion & safe hot-reload:** Only when both holdout MAPEs are finite and `challenger_mape < champion_mape` (strictly lower), the coordinator verifies that the challenger artifact loads and produces a finite prediction before calling `tracking.promote_champion(challenger_version)` under `.champion.lock`, updating the on-disk fallback `xgboost_forecaster.joblib` and `model_metadata.json` atomically (preserving existing keys such as `isolation_forest_quality`), and calling `serving_frame.reset_serving_cache()` so subsequent requests serve the new champion without restarting. When `challenger_mape >= champion_mape`, the existing champion alias and serving cache remain untouched (`outcome: "rejected"`). Any data, champion-resolution, training, non-finite metric, or promotion/reload error aborts without replacing the champion (`outcome: "failed"` with `reason`).
- **Three-state history persistence:** Every completed run (`promoted`, `rejected`, or `failed`) prepends a record (`run_id`, ISO 8601 UTC `timestamp`, `trigger`, `champion_version`, `challenger_version`, `champion_mape`, `challenger_mape`, `outcome`, `reason`) to `get_models_dir() / "retrain_history.json"` via atomic temp-file swap (`load_retrain_history()` returns newest-first for Stories 4.9 and 4.10).
- **Offline tests (`ai-service/tests/test_mlops_retrain.py`):** Exercise promotion (`challenger_mape < champion_mape` + hot-reload cache reset), rejection (equal or higher MAPE), operational failure (missing data / non-finite score / reload error keeping champion intact and releasing the lock), zero-target MAPE handling, and HTTP `202` / `409` / `401` on `POST /internal/mlops/retrain` using lightweight stubs and temporary stores (`tmp_path`), honouring the Epic 4 working agreement never to execute heavy production training runs from the agent.

</frozen-after-approval>

## Implementation Notes

- Added `promote_champion(version, name, tracking_uri)` and an optional `bootstrap_champion: bool = True` flag to `track_training_run(...)` in `ai-service/src/mlops/tracking.py`. When `retrain.py` logs a challenger run, it passes `bootstrap_champion=False` so registering a challenger version never prematurely claims the `champion` alias before holdout evaluation.
- Created `ai-service/src/mlops/retrain.py` (plain-Python, AD-1) providing `run_retrain()`, `start_retrain()`, `load_retrain_history()`, `is_retrain_running()`, and `compute_holdout_mape()`:
  - Uses an in-process `threading.Lock` (`_retrain_lock`) for atomic `409 Conflict` admission and releases it inside the outermost `finally:` block across every terminal path (`promoted`, `rejected`, `failed`).
  - Evaluates both current `champion` and `challenger` on the chronological 80/20 holdout slice (`train_df["timestamp"].max() < test_df["timestamp"].min()`) with `compute_holdout_mape()`, which excludes `y == 0` rows and raises on `NaN`/`Inf`.
  - Promotes only when `challenger_mape < champion_mape` (strict inequality): verifies challenger loadability and finite probe prediction, atomically swaps `xgboost_forecaster.joblib` and `model_metadata.json` (preserving `isolation_forest_quality` from Story 4.7), switches the MLflow `champion` alias under `.champion.lock` (with rollback on failure), and calls `serving_frame.reset_serving_cache()` for hot reload without restart.
  - Prepends every completed attempt (`promoted`, `rejected`, `failed`) to `get_models_dir() / "retrain_history.json"` via atomic temp-file swap, including optional `signals` so Story 4.9 and Story 4.10 can reuse the same coordinator and history format directly.
- Created `ai-service/src/api/routers/mlops.py` (`POST /internal/mlops/retrain` returning `202` or `409 ERR_RETRAIN_IN_PROGRESS`) and mounted it in `ai-service/src/main.py` behind the existing `/internal/*` `X-Internal-Token` middleware.
- Created `ai-service/tests/test_mlops_retrain.py` covering zero/non-finite holdout MAPE handling, guarded promotion + hot-reload cache invalidation + metadata preservation, equal/worse rejection, missing data / missing champion / non-finite challenger / probe failure / alias rollback + lock release, and `202`/`409`/`401` on `POST /internal/mlops/retrain`.
- Per the Epic 4 working agreement, the agent verified bytecode compilation (`python -m py_compile`) without executing `pytest` (since `conftest.py`'s session fixture trains models); command for the project owner to run:
  - Working directory: `c:\Users\ADMIN\Desktop\EcoTrack\ai-service`
  - Command: `pytest tests/test_mlops_retrain.py tests/test_mlops_tracking.py -q`
- Post-`bmad-review` hardening (2026-11-17):
  - Switched `serving_frame._lock` to `threading.RLock()` and wrapped `_verify_and_promote_challenger`'s disk swap + MLflow alias promotion + `reset_serving_cache()` inside `with serving_frame._lock:`, snapshotting and restoring `xgboost_forecaster.joblib` and `model_metadata.json` on any promotion/cache failure.
  - Added `clear_champion_alias()` (under `.champion.lock`), `get_champion_tag()`, and optional `tags` on `track_training_run()` in `ai-service/src/mlops/tracking.py`; recorded and enforced `train_end_timestamp` against holdout start to prevent champion-vs-challenger temporal leakage.
  - Added `_history_lock`, corrupt history backup (`.corrupt.*.bak`), strict `allow_nan=False` JSON writes, corrupt `model_metadata.json` failure guard, `train_ratio` range check `(0, 1)`, `_execute_retrain_locked` separation (removing `_lock_already_held` from `run_retrain`), and `history_persisted: False` surfacing on history write errors.
  - Closed verification gaps in `test_mlops_retrain.py` and `test_mlops_tracking.py`: real end-to-end XGBoost retraining + `GET /internal/forecast/predict` hot-reload test, real `promote_champion` + `reset_serving_cache` rollback tests (both MLflow v1 and `local` fallback), newest-first `run_id` history ordering assertion, temporal-leakage boundary & champion-cutoff tests, corrupt file guards, and `promote_champion` `ChampionArtifactError` test.
- Owner ran `pytest tests/test_mlops_retrain.py tests/test_mlops_tracking.py -q` (2026-11-17): `13 passed, 1 warning in 156.31s` (pre-existing MLflow `SADeprecationWarning` on SQLAlchemy `noload`).

## Review Triage Log — `bmad-review` pass (2026-11-17)

Sequential 3-lens review (`adversarial` [13], `edge-case-hunter` [9], `verification-gap` [7]) against commit `1d50862`.

| # | Lens | Finding | Route | Resolution |
|---|------|---------|-------|------------|
| 1 | adversarial / edge-case / verification | Disk artifacts overwritten before `promote_champion` were not rolled back on failure, and `test_mlops_retrain.py` only mocked `_update_local_artifacts_atomically` so the rollback block never ran | patch | Snapshotted `xgboost_forecaster.joblib` + `model_metadata.json` before swap and restored both on error; added `promote_champion` failure and `reset_serving_cache` failure rollback tests (both v1 and `local`). |
| 2 | adversarial / edge-case / verification | `_verify_and_promote_challenger` lacked `serving_frame._lock` around swap + alias switch + cache clear; hot-reload test checked only `_cached_xgb_model is None` | patch | Changed `serving_frame._lock` to `RLock()`, locked the transition block, and added an end-to-end `GET /internal/forecast/predict` before/after hot-reload test. |
| 3 | adversarial / edge-case / verification | No champion `train_end_timestamp` cutoff check or boundary-duplicate test | patch | Persisted `train_end_timestamp` in `model_metadata.json` and MLflow run tags (`get_champion_tag`); rejected overlapping champion cutoff or duplicate split timestamps, with dedicated tests. |
| 4 | adversarial / edge-case | Corrupt `retrain_history.json` and `model_metadata.json` were silently clobbered; concurrent history read/write lacked lock; JSON lacked `allow_nan=False` | patch | Added `_history_lock`, backed up corrupt history to `.corrupt.*.bak`, raised on corrupt `model_metadata.json`, and enabled `allow_nan=False`. |
| 5 | adversarial / edge-case | `run_retrain` exposed `_lock_already_held`, accepted negative `train_ratio`, swallowed `_append_history` errors silently, and rounded MAPE to 4 decimals | patch | Extracted `_execute_retrain_locked`, enforced `0 < train_ratio < 1`, surfaced `history_persisted: False` on error, and rounded history MAPE to 6 decimals. |
| 6 | adversarial / edge-case | `champion_version == "local"` rollback deleted alias outside `.champion.lock` | patch | Added `clear_champion_alias()` under `.champion.lock` in `tracking.py`. |
| 7 | verification-gap | All tests mocked `_train_challenger`; history newest-first ordering and `promote_champion` error translation were untested | patch | Added unmocked `train_xgboost_forecaster` integration test, distinct-`run_id` ordering assertion, and `test_promote_champion_translates_mlflow_error_and_clear_alias`. |
| 8 | adversarial | `run_retrain` initializes `mlruns/mlflow.db` when `ECOTRACK_DISABLE_MLFLOW` is unset even on local-only runs; `_train_challenger` uses `train_xgboost_forecaster` (`n_jobs=-1`) | reject | Matches Story 4.5's `train_models.py` convention (`ECOTRACK_DISABLE_MLFLOW=1` is the explicit opt-out); avoided altering `train_models.py` without measured CPU contention (`/ponytail ultra`). |

## Review Triage Log

Blind-hunter (only layer configured in this render) against the Story 4.8 changes (~31.24 KB -> N = min(floor(sqrt(31.24)+1), 10) = 6; 7 findings reported).

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `run_retrain` called `track_training_run()` before the `challenger_mape < champion_mape` check, which unconditionally called `register_and_bootstrap_champion()` and would prematurely assign the `champion` alias to a rejected challenger when `champion_version == "local"` | high | patch | Real bug in the local-fallback-to-MLflow transition path. Added `bootstrap_champion: bool = True` to `track_training_run()` and passed `bootstrap_champion=False` from `run_retrain()`, plus a regression assertion in `test_mlops_retrain.py`. |
| 2 | `run_retrain` called `get_data_path()` and `get_models_dir()` after acquiring `_retrain_lock` but before entering `try:`, risking a leaked lock if path resolution raised | medium | patch | Real lock-safety gap. Moved path resolution inside the `try:` block and guarded `_append_history` in `finally:` so `_retrain_lock.release()` is unconditionally reached. |
| 3 | `run_retrain` updated `xgb_metrics["mape_percent"]` from the zero-filtered `compute_holdout_mape()` but left `xgb_metrics["target_mape_met"]` derived from `train_xgboost_forecaster`'s unfiltered MAPE | low | patch | Real consistency issue; updated `target_mape_met` alongside `mape_percent` from `challenger_mape <= 10.0`. |
| 4 | `_verify_and_promote_challenger` switched the MLflow `champion` alias before staging/verifying local artifacts and skipped alias rollback when `champion_version == "local"` | medium | patch | Reordered `_update_local_artifacts_atomically` before `promote_champion` and added alias deletion rollback when `champion_version == "local"`. |
| 5 | `promote_champion` did not pass `tracking_uri` to `MlflowClient(tracking_uri=uri)` or translate `MlflowException` into `ChampionArtifactError` | low | patch | Patched `promote_champion` to pass `tracking_uri=uri` and wrap `MlflowException` in `ChampionArtifactError`. (Left `register_and_bootstrap_champion` untouched as Story 4.5 code.) |
| 6 | `run_retrain` and `start_retrain` lacked an optional `signals` parameter (and `train_ratio` on `start_retrain`) for Story 4.9 reuse | low | patch | Added optional `signals` (persisted on the history record when provided) and `train_ratio` on `start_retrain`. |
| 7 | `test_mlops_retrain.py` lacked direct tests for missing champion, non-finite challenger predictions (`NaN`), and challenger probe failure aborting before `promote_champion` | medium | patch | Added `test_run_retrain_handles_missing_champion_non_finite_challenger_and_probe_failure` covering all three cases plus the `champion_version == "local"` rejection guard. |
