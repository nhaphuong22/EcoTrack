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
  - Command: `pytest tests/test_mlops_retrain.py -q`

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
