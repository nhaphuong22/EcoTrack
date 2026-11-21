---
title: 'Story 4.13: Forecast with learned prediction intervals'
type: 'feature'
created: '2026-11-21'
status: 'done'
baseline_commit: '34f7204f6aa83ae7184c821069613f0309737d45'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The 95% forecast band is a fixed `predicted ± 1.96 × RMSE`, equally wide at every hour whatever the model's uncertainty.

**Approach:** Train one XGBoost multi-quantile model (2.5%, 50%, 97.5%, pinball loss) beside the point forecaster, register it in the same MLflow `champion` version, serve the bounds from it, and report 95% coverage and width per horizon against the old band.

## Boundaries & Constraints

**Always:** The Story 4.13 acceptance criteria in `_bmad-output/planning-artifacts/epics.md` are the contract. One `xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=[0.025, 0.5, 0.975])` trained on the same features and chronological split as the point model; its output columns are lower, median, upper. It is logged as MLflow artifact `quantile_model` in the same run, before the version is registered, and saved as `xgboost_quantile.joblib` in the models directory. Retrain stages, promotes and restores it together with the point model. `predicted_kwh` stays from the point forecaster; the median is reported in evaluation only. Bounds come from the quantile model applied to the same feature row used for each step and get the same live scaling as `predicted_kwh`; then `lower = max(0, min(q2.5, predicted))` and `upper = max(q97.5, predicted)`. Missing quantile artifacts (disk or champion run) raise `ModelArtifactError` (503 `ERR_MODEL_NOT_FOUND`), with no fixed-band fallback. One shared helper replaces every `1.96 × RMSE` site.

**Never:** Do not run model training, `train_models`, `run_benchmark` or any script that trains; print the command for the user (pytest on fixture data is fine). No MLflow pyfunc wrapper. No change to the promotion gate, to the forecast response shape, or to the `train_xgboost_forecaster` signature and return (retrain tests monkeypatch it). No LSTM quantiles.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal | Point and quantile artifacts present | Bounds satisfy `0 ≤ lower ≤ predicted ≤ upper`; width varies by hour | N/A |
| Crossing quantiles | `q2.5 > predicted` or `q97.5 < predicted` | Clamp rule above | N/A |
| Disk artifact missing | `xgboost_quantile.joblib` absent | 503 `ERR_MODEL_NOT_FOUND` | No fixed band |
| Champion lacks extra | Champion run has no `quantile_model` | 503 `ERR_MODEL_NOT_FOUND`; `/internal/mlops/status` still reports the champion | N/A |
| Retrain promoted | Challenger passes the MAPE gate | Point and quantile files and run artifacts swap together | Failure restores both snapshots and the alias |
| Retrain rejected | Gate fails | Champion and quantile files unchanged | N/A |
| Live-scaled series | `predict_next_24h_from_series` | Bounds scaled like `predicted_kwh` | N/A |
| Coverage report | Held-out 24 h autoregressive forecasts | Coverage and mean width overall and per horizon 1–24 h, beside `±1.96 × RMSE` | Low coverage reported, not hidden |

</frozen-after-approval>

## Code Map

All under `ai-service/`.
- `src/models/train_models.py` -- `XGB_FEATURE_COLUMNS` (:52), `split_time_series_data` (:127), `train_xgboost_forecaster` (:152, keep as is), `save_trained_models` (:256), `run_pipeline` (:286, calls `track_training_run` at :355). Add `train_quantile_forecaster`, save it, add `quantile_metrics` (pinball, coverage) to metadata.
- `src/mlops/tracking.py` -- `track_training_run` (:246) logs `mlflow.xgboost.log_model(model, "model")` then `register_model` (:289-290): log `quantile_model` in the same run before it. `load_champion_forecaster` (:341): add a sibling loader via `get_model_version_by_alias(...).run_id` and `runs:/<run_id>/quantile_model`. Do not use a pyfunc wrapper.
- `src/mlops/retrain.py` -- `_train_challenger` (:212), `track_training_run` call (:446), `_verify_and_promote_challenger` (:280) with `_update_local_artifacts_atomically` (:220), `promote_champion` (:338), `reset_serving_cache` (:340), failure restore (:341-356): extend staging, probe and snapshot-restore to the quantile joblib.
- `src/data_pipeline/serving_frame.py` -- bounds at :141-142, :390-391 (24 h autoregressive, pair with the :389 `predicted` and its feature rows), :483-484 and :505-506 (live scaling via `scale`/`eff`); `_cached_xgb_model` (:47) loaded through `_load_champion_forecaster_or_fallback` (:78) and `_load_model_artifacts` (:174), reset in `reset_serving_cache` (:58). Add the quantile model beside it and one bounds helper. `src/data_pipeline/inference_pipeline.py:306` `predict_forecast_autoregressive` builds the feature rows.
- `src/agent/tools/energy_tools.py:41` -- assumes a symmetric `±ci`; report lower and upper instead.
- `src/api/routers/forecast.py:27`, `energy.py:46` -- consume the bounds, shape unchanged.
- `experiments/benchmark/benchmark.py` (:118, :224 rolling-origin) and `run_benchmark.py` (:62) -- add the coverage and width evaluation; `report.py` (:282 `build_results_json`, :299 `build_report_md`) only renders a new `coverage` key and section (it never fits models).
- `tests/conftest.py` -- session fixture trains the point model into a temp dir: also train and save the quantile model. `tests/test_forecast_service.py:99` hard-codes `1.96 × RMSE` (:106, :112, :115): rewrite. Keep `tests/test_smoke.py:112` (p95 < 300 ms).

## Tasks & Acceptance

**Execution:**
- [x] `src/models/train_models.py` -- quantile trainer, save, metadata, pipeline wiring -- artifacts exist for tracking and serving
- [x] `src/mlops/tracking.py` -- log `quantile_model` in the run; add the champion quantile loader -- same version as the champion
- [x] `src/mlops/retrain.py` -- train, stage, promote and restore the quantile model with the challenger -- promotion and rollback move together
- [x] `src/data_pipeline/serving_frame.py` -- load and cache the quantile model, shared bounds helper at all five sites -- learned bounds, no fallback
- [x] `src/agent/tools/energy_tools.py` -- asymmetric bounds -- Copilot text stays correct
- [x] `experiments/benchmark/{benchmark,run_benchmark,report}.py` -- coverage and width per horizon vs the old band -- AC report
- [x] `tests/` -- conftest quantile fixture; rewrite the 1.96 test; add crossing, missing-artifact, champion-without-extra, retrain stage/restore and coverage tests

**Acceptance Criteria:**
- Given the Story 4.13 ACs in `epics.md`, when `pytest ai-service` runs, then it passes, including the warm `/internal/forecast/predict` p95 under 300 ms
- Given quantile artifacts are absent, when the forecast is requested, then it returns `ERR_MODEL_NOT_FOUND` and never the fixed band

## Implementation Notes

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `disk_updated` is set only after the swap returns, so a mid-swap failure restores nothing | medium | patch | Confirmed at `retrain.py:351`; the three snapshots exist before the call and restore is idempotent |
| 2 | No test that the pipeline's per-step quantiles match `quantile_model.predict` on the same row | medium | patch | Band tests only check ordering and non-constant width, so a shifted row would pass |
| 3 | First-promotion rollback with no prior quantile file is untested | medium | patch | Rollback test always seeds the file, so the `None` branch never runs |
| 4 | `score_timeseries_from_series` bounds with `scale != 1` are untested | low | patch | Only `predict_next_24h_from_series` has a scaled-band test |
| 5 | A champion registered before this story has no `quantile_model`, so forecast returns 503 and no step migrates it | medium | patch | Fixed at the user's request: a champion without `quantile_model` is replaced by the first version that has one; three tests added |
| 6 | Anomaly scoring and the time series now fail without the quantile artifact | medium | defer | The AC puts the shared helper at all five sites; a degraded path is a design change |
| 7 | `_get_quantile_model` can deadlock on `_lock` | false | reject | `_lock` is a `threading.RLock` (`serving_frame.py:42`) |
| 8 | The Copilot may parse the old `±` text | false | reject | `orchestrator.py:414` inserts the string unchanged; nothing parses it |
| 9 | The quantile model is trained before the promotion gate | low | reject | Costs time only; the spec does not restrict it |
| 10 | No minimum-coverage guard on promotion | low | reject | The spec keeps the promotion gate unchanged |
| 11 | Quantile metrics are not logged to MLflow | low | reject | The spec asks for metadata only |
| 12 | Point and quantile caches can briefly come from different versions | low | reject | Promotion resets both caches under the lock |
| 13 | Empty or single-row test set, non-finite quantiles, stale `coverage.csv`, report pivot duplicates | low | reject | Real data has thousands of rows; each fix adds a guard for an unreachable case |
| 14 | No `get_booster` fallback for the quantile model | low | reject | Every load path returns an `XGBRegressor` |
| 15 | The coverage benchmark is optimistic and retrains its own models | low | reject | `lag_24h` comes from history exactly as in serving; the baseline matches the old served band |
| 16 | The three `os.replace` calls are not atomic as a group | low | reject | Pre-existing pattern; finding 1 closes the in-process failure window |
| 17 | Dead `global` line, `__import__("os")` in a test, `kW` on a kWh value | low | reject | Cosmetic or carried over |

## Design Notes

One multi-quantile model keeps a single extra artifact instead of three; installed `xgboost` is 3.4.1 (`requirements.txt` says `>=2.1.0`), which supports `quantile_alpha` lists. Until the user retrains, `models_saved/` and the MLflow champion lack the quantile artifact, so the live forecast returns 503 by design (the AC forbids a silent fallback); the user must run the training command first.

## Verification

**Commands:**
- `pytest ai-service -q` -- expected: all pass (trains small models on the fixture only)

**Manual checks (user runs, not the agent):**
- From `ai-service/`: `python -m src.models.train_models`, then check `models_saved/xgboost_quantile.joblib` exists and `GET /internal/forecast/predict` returns bounds that widen and narrow by hour
- From `ai-service/`: `python -m experiments.benchmark.run_benchmark` then `python -m experiments.benchmark.run_report` to refresh `results.json` and the coverage table
