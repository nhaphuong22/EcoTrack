---
title: 'Story 1.1: Serve energy metrics and time series from BDG2 data'
type: 'feature'
created: '2026-10-08'
status: 'done'
baseline_commit: 'f2b1be3a32624c27c85db9d79ea1f02bdd8af347'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `GET /internal/energy/metrics` and `/internal/energy/timeseries` are computed from a 30-day synthetic dataset and from models fitted in-sample on it, so the dashboard's numbers describe no real building. The BDG2 dataset and the models trained on it exist but nothing serves them.

**Approach:** Add one shared "serving frame" that loads the processed BDG2 readings and the trained XGBoost and Isolation Forest artifacts, and returns the last 30 days with baseline prediction, 95% bounds and anomaly flags. Point the two energy endpoints and the Copilot `query_metrics` tool at it, keeping the response shape.

## Boundaries & Constraints

**Always:**
- Response keys of both endpoints stay exactly as today; timestamps become ISO 8601 UTC (`YYYY-MM-DDTHH:mm:ssZ`).
- The serving frame is plain Python, importable without FastAPI; handlers keep using `asyncio.to_thread`.
- Features come from `train_models.engineer_features` and the feature lists in `model_metadata.json`; no new feature code.
- Metrics cover the same 720-hour window the time series can return.
- Tariff comes from `TARIFF_RATE_VND` (default 3100) and `TARIFF_RATE_USD` (default 0.125).
- Tests pass with no gitignored file present.
- **Replay to now (decided 2026-10-08):** the served window is the 720 rows ending at the latest dataset row whose weekday and hour match the current UTC hour, with timestamps shifted forward by a whole number of weeks so the last row is the current hour. Features and predictions are computed on the original timestamps before shifting.

**Never:**
- Never train, substitute or write a model or dataset at serving time. Missing input is an error.
- Do not change `forecast.py`, `anomalies.py`, `get_anomalies`, `query_forecast_summary`, `anomaly_service.py` or the old `forecaster_xgboost` / `anomaly_isolation_forest` modules beyond the tariff constant; Stories 1.2 and 1.3 own them.
- Do not change the gateway or the frontend.
- Do not commit the full dataset or any `.joblib` file.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Metrics | Data and artifacts present | 200; same keys as today; values computed over the last 720 hourly rows | N/A |
| Time series | `limit=24` | 200; `count` 24; rows ascending by time; every key present; `relative_humidity_pct` and `anomaly_reason` are `null` | N/A |
| Replay | Clock fixed at a Thursday 14:00 UTC | Last row's timestamp is that hour; its source row is a Thursday 14:00; rows are exactly one hour apart | N/A |
| Hour rollover | Clock advances one hour | The cached frame is rebuilt and ends at the new hour | N/A |
| Limit out of range | `limit=0` or `721` | 422 from existing validation | Unchanged |
| Dataset missing | CSV path does not exist | 503 `{"detail": ..., "code": "ERR_DATA_NOT_FOUND"}` naming the path | No file is created |
| Artifact missing | A `.joblib` or the metadata file is absent | 503 `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` naming the file | No model is trained or saved |
| Tariff override | `TARIFF_RATE_VND=2500` | `estimated_waste_cost_vnd` equals waste kWh × 2500 | N/A |

</frozen-after-approval>

## Code Map

- `ai-service/src/api/routers/energy.py` -- the two endpoints; today chains `data_loader` → `energy_forecaster.predict_horizon` → `anomaly_detector.detect_anomalies`. Rewire to the serving frame; keep key names.
- `ai-service/src/agent/tools/energy_tools.py` -- `query_metrics` (lines 6-30) duplicates the metrics maths; make it call the shared function. Leave the other tools.
- `ai-service/src/models/train_models.py` -- reuse `load_dataset`, `engineer_features`, `get_default_paths`; in tests reuse `split_time_series_data`, `train_xgboost_forecaster`, `train_isolation_forest`, `save_trained_models`. Artifacts are raw estimators.
- `ai-service/models_saved/model_metadata.json` -- `xgb_features`, `iso_features`, `xgboost_metrics.rmse_kwh` (held-out RMSE), `isolation_forest_metrics.anomaly_score_min/max`.
- `ai-service/data/processed/office_building_clean.csv` -- 17,544 hourly rows, columns `timestamp, meter_reading, air_temperature`; gitignored by `*.csv`.
- `ai-service/src/main.py` -- register the exception handler here.
- `ai-service/tests/test_smoke.py` -- `test_api_energy_metrics` / `test_api_energy_timeseries` must keep passing; the three old-stack tests above them stay untouched.
- `.gitignore` line 36 (`*.csv`) -- needs an exception for the test fixture.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/src/config.py` -- add helpers reading `TARIFF_RATE_VND`, `TARIFF_RATE_USD`, `ECOTRACK_DATA_PATH`, `ECOTRACK_MODELS_DIR` with defaults from `get_default_paths()` -- one place for settings the env file already documents.
- [x] `ai-service/src/data_pipeline/serving_frame.py` -- add `ServingDataError`, `ModelArtifactError`, and a lock-guarded cached `get_serving_frame()` returning the last 720 rows with `timestamp`, `meter_reading_kwh`, `outdoor_temperature_c`, `predicted_kwh`, `residual`, `lower_bound_95`, `upper_bound_95`, `anomaly_score`, `is_anomaly`, `severity`; plus `compute_energy_metrics(frame)` and `reset_serving_cache()` -- the single real-data source for this epic.
- [x] `ai-service/src/api/routers/energy.py` -- build both responses from the serving frame; UTC `Z` timestamps -- FR13.
- [x] `ai-service/src/agent/tools/energy_tools.py` -- `query_metrics` delegates to `compute_energy_metrics`, keeping its own key names -- Copilot and dashboard agree.
- [x] `ai-service/src/api/routers/anomalies.py`, `ai-service/src/agent/tools/energy_tools.py`, `ai-service/src/agent/orchestrator.py` -- replace literal `3100` / `0.125` with the config helpers -- tariff AC.
- [x] `ai-service/src/main.py` -- exception handler mapping the two errors to the 503 envelope.
- [x] `ai-service/tests/fixtures/office_building_sample.csv`, `.gitignore` -- commit the last 90 days (2,160 rows) of the processed CSV; add `!ai-service/tests/fixtures/*.csv`.
- [x] `ai-service/tests/conftest.py` -- session fixture that trains both models from the fixture into a temp dir with the `train_models` functions, sets the two `ECOTRACK_*` variables and resets the cache.
- [x] `ai-service/tests/test_serving_frame.py` -- cover every matrix row, column set, row order, bounds containing the prediction, and that no file appears in the models dir on a missing-artifact error.
- [x] `ai-service/.env.example` -- document the three new variables.

**Acceptance Criteria:**
- Given the fixture environment, when `pytest ai-service` runs with `models_saved/*.joblib` and `data/processed/` absent, then the whole suite passes.
- Given the serving frame, when it is imported and called from a plain Python shell, then it works without FastAPI.
- Given the frame was built once, when either endpoint is called again, then the dataset and artifacts are not reloaded from disk.

## Implementation Notes

## Spec Change Log

## Review Triage Log

- finding: "Verify naive datetime handling in get_serving_frame(now)"
  verdict: false
  evidence: "get_serving_frame explicitly converts naive datetime to UTC (now.replace(tzinfo=timezone.utc)) before hour truncating."
- finding: "Verify held-out RMSE floor at 0 for lower_bound_95"
  verdict: false
  evidence: "np.maximum(0.0, predicted - 1.96 * rmse) enforces 0.0 floor and verified in test_serving_frame_columns_and_bounds."
- finding: "Verify 503 response envelope format"
  verdict: false
  evidence: "FastAPI exception handlers map ServingDataError and ModelArtifactError to status 503 with {'detail': ..., 'code': 'ERR_...'} matching the spec envelope."


## Design Notes

- **Bounds:** `predicted_kwh ± 1.96 × rmse_kwh` from the metadata, lower bound floored at 0. This is held-out error, replacing the old in-sample residual.
- **Anomaly columns:** `is_anomaly` is the Isolation Forest's own verdict (`predict == -1`). `anomaly_score` is `-decision_function` scaled to [0, 1] with the metadata min/max and clipped, so it is stable across requests rather than relative to the batch. `severity` is `Normal` when not anomalous, `Critical` when the reading exceeds the prediction by more than 30%, otherwise `Medium`. Story 1.3 owns the final tiering.
- **Replay clock:** `get_serving_frame(now=None)` takes an optional clock value so tests can fix it; the cache key is the current UTC hour. The models and the dataset are loaded once and kept; only the window is recomputed on rollover.
- **Null fields:** the BDG2 file has no humidity and no anomaly labels; the frontend reads neither field, so `null` is served instead of an invented value.
- **Temporary mix:** until Stories 1.2 and 1.3 land, the forecast and anomaly endpoints still use the old stack.

## Verification

**Commands:**
- `cd ai-service && python -m pytest -q` -- expected: all tests pass, including `tests/test_serving_frame.py`.
- `cd ai-service && python -c "from src.data_pipeline.serving_frame import get_serving_frame; f = get_serving_frame(); print(len(f), list(f.columns))"` -- expected: `720` and the ten columns, using the local BDG2 data.
- `npm run test --prefix backend` -- expected: unchanged, all pass.
