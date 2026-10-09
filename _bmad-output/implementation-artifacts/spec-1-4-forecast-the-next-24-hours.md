---
title: 'Story 1.4: Forecast the next 24 hours'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '03da4759f0ba7da76d1339205341d9ffdf2a2392'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 1-4-forecast-the-next-24-hours
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `GET /internal/forecast/predict` builds its "24-hour forecast" by running a batch `energy_forecaster.predict_horizon(df)` over the whole replayed dataset and slicing `.tail(24)` off the end (`forecast.py:11-25`). That is a replay of the *past* 24 hours, produced by the lazy in-sample `XGBoostEnergyForecaster` fitted on the synthetic `bdg2_loader` data with a hardcoded `residual_std = 8.5` for its bounds — it never forecasts forward, never uses the real BDG2-trained artifact in `models_saved/`, and its intervals are in-sample. FR14 requires a true 24-hour-*ahead* recursive forecast. The real recursive helper `EnergyInferencePipeline.predict_forecast_autoregressive` already exists and is tested, but nothing serves it.

**Approach:** Rewire the endpoint to return a genuine 24-step-ahead recursive forecast from the Story 1.1 serving frame and the trained XGBoost artifact. Add one forecast function to `serving_frame.py` (the single real-data source established in Story 1.1) that reuses the already-loaded base frame, caches the XGBoost model so a warm call does no disk I/O, builds the 24 hourly steps after the last observed hour, drives `predict_forecast_autoregressive` (each step's prediction becomes the next step's `lag_1h`), and attaches 95% bounds from the held-out test-split RMSE. The endpoint keeps its response contract and `asyncio.to_thread`.

## Boundaries & Constraints

**Always:**
- The forecast covers exactly the 24 hours *after* the last observed reading in the serving frame; every forecast timestamp is strictly later than the last observed timestamp and strictly increasing, in ISO 8601 UTC with a `Z` suffix.
- Predictions come from `EnergyInferencePipeline.predict_forecast_autoregressive` driven by the trained XGBoost artifact (`models_saved/xgboost_forecaster.joblib`); each hourly prediction feeds the next step's `lag_1h` (recursive).
- 95% bounds are `predicted ± 1.96 × xgboost_metrics.rmse_kwh` read from `model_metadata.json` (the held-out test-split RMSE), with the lower bound floored at 0 — the same convention Story 1.1 uses in the serving frame.
- History and the model come from the Story 1.1 serving cache; the XGBoost artifact is loaded once and reused (no per-request disk read), and the warm endpoint answers under 300 ms at p95 (NFR3).
- CPU-bound forecasting runs through `asyncio.to_thread` in the handler (NFR6).
- The response shape is unchanged: `{ "building_id": "office_tower_01", "horizon_hours": 24, "forecast": [ { "timestamp", "predicted_kwh", "lower_bound_95", "upper_bound_95", "outdoor_temperature_c" } × 24 ] }`.
- Future outdoor temperatures use a documented daily-seasonal proxy (see Design Notes); no values are invented silently.
- Tests pass with the gitignored BDG2 data and `.joblib` artifacts absent, reusing the existing `conftest.py` fixture environment.

**Never:**
- Never train, fit, substitute or persist a model at request time. A missing artifact is a 503 error, not a fallback.
- Never use in-sample residuals or the hardcoded `residual_std = 8.5` from `predictor.py` for the bounds.
- Do not delete `src/models/forecaster_xgboost/predictor.py`, `energy_forecaster`, `src/data_pipeline/bdg2_loader.py`/`data_loader`, or the stray `src/src/models/artifacts/` directory — **Story 1.5** owns removing the dead in-sample path; Story 1.4 only stops the endpoint from using it.
- Do not invent or call an external weather API or network/DB source; the AI service reads its inputs from files only.
- Do not change the gateway `backend/src/routes/forecast.js` or the frontend `ForecastChart`.
- Do not change `energy.py`, `anomalies.py`, `compute_energy_metrics`, or the serving frame's existing metrics/anomaly columns beyond adding the forecast function and the model cache.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | Artifact + ≥ 24 h history present | 200; `forecast` has 24 points; timestamps strictly increasing and each later than the last observed reading; per point `lower_bound_95 ≤ predicted_kwh ≤ upper_bound_95` and `lower_bound_95 ≥ 0` | N/A |
| Bounds source | `rmse_kwh = 74.02` | `upper_bound_95 − lower_bound_95 ≈ 2 × 1.96 × rmse_kwh` where lower is not floored | N/A |
| Autoregressive chaining | Step *t* prediction | It is used as `lag_1h` for step *t+1* (recursive, not a flat repeat) | N/A |
| Warm perf | Endpoint called repeatedly in a test after warm-up | p95 response time < 300 ms | N/A |
| Response shape | Any success | Keys exactly as today (`building_id`, `horizon_hours`, `forecast[]` with the five fields) | N/A |
| Insufficient history | Fewer than 24 hourly observations available | 422 `{"detail": ..., "code": "ERR_INSUFFICIENT_HISTORY"}` naming the shortfall | No model trained or saved |
| Artifact missing | `xgboost_forecaster.joblib` or `model_metadata.json` absent | 503 `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` naming the file | No model trained or saved |
| Dataset missing | Processed CSV absent | 503 `{"detail": ..., "code": "ERR_DATA_NOT_FOUND"}` naming the path | No file is created |

</frozen-after-approval>

## Code Map

- `ai-service/src/api/routers/forecast.py` -- `_get_forecast` (lines 11-25) chains `data_loader.get_or_create_data()` → `energy_forecaster.predict_horizon(df).tail(24)`. Rewire it to call the new serving-frame forecast function and map each row to the response contract (ISO-`Z` timestamp, `predicted_kwh`, the two bounds, `outdoor_temperature_c`). Keep the `get_forecast` wrapper, `horizon_hours: 24`, and `asyncio.to_thread`.
- `ai-service/src/data_pipeline/serving_frame.py` -- today `_load_artifacts_and_base_frame` loads `xgb_model` into a local variable and drops it (only `base_df` and `meta` are cached). Add: `InsufficientHistoryError`; a cached `_cached_xgb_model`; and `predict_next_24h(now=None) -> pd.DataFrame` returning 24 rows with `timestamp` (ISO-`Z`), `predicted_kwh`, `lower_bound_95`, `upper_bound_95`, `outdoor_temperature_c`, reusing `_cached_base_df`, the cached model, and `EnergyInferencePipeline.predict_forecast_autoregressive`. Reset it in `reset_serving_cache()`.
- `ai-service/src/data_pipeline/inference_pipeline.py` -- reuse `EnergyInferencePipeline.predict_forecast_autoregressive` (already recursive, raises `ValueError` on < 24 history) and `prepare_forecast_features`. Instantiate the pipeline against the serving `models_dir`/`metadata_path` (`get_models_dir()`) so it reads the same `xgb_features`. No behavioural change to the pipeline itself.
- `ai-service/models_saved/model_metadata.json` -- `xgb_features` (8 features) and `xgboost_metrics.rmse_kwh` (held-out test RMSE) for the bounds.
- `ai-service/src/main.py` -- `ServingDataError`→503 and `ModelArtifactError`→503 handlers already exist (lines 42-55). Add a handler mapping `InsufficientHistoryError` → 422 with `{"detail": ..., "code": "ERR_INSUFFICIENT_HISTORY"}`.
- `ai-service/src/config.py` -- reuse `get_data_path`, `get_models_dir` (no change).
- `ai-service/tests/conftest.py` -- reuse the session fixture that trains both models into a temp dir and sets `ECOTRACK_*` (no change).
- `ai-service/tests/test_smoke.py` -- `test_api_forecast_predict` (lines 87-94) must keep passing; extend it to assert the 24 timestamps are strictly increasing, all later than the last timeseries timestamp, and `lower ≤ predicted ≤ upper`. The old `test_forecaster_predictor` (lines 30-45) stays untouched (Story 1.5 owns that path).
- `ai-service/tests/test_forecast_service.py` -- **new**: unit tests for `predict_next_24h` and the 422 short-history path.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/src/data_pipeline/serving_frame.py` -- add `InsufficientHistoryError`; cache the loaded XGBoost model alongside `_cached_base_df`; add `predict_next_24h(now=None)`. It anchors on the serving frame's last row (current UTC hour), builds 24 future hourly timestamps, derives each future temperature from the same hour of the previous day in the frame, calls `predict_forecast_autoregressive`, attaches `predicted ± 1.96 × rmse_kwh` bounds (lower floored at 0), and returns ISO-`Z` timestamps -- FR13, FR14, the single real-data forecast source.
- [x] `ai-service/src/api/routers/forecast.py` -- rewire `_get_forecast` to `predict_next_24h`; build the response rows from it; keep the wrapper and `asyncio.to_thread` -- FR14, NFR6.
- [x] `ai-service/src/main.py` -- exception handler `InsufficientHistoryError` → 422 `ERR_INSUFFICIENT_HISTORY`.
- [x] `ai-service/tests/test_forecast_service.py` -- new tests: 24 rows; timestamps strictly increasing and all after the last observed; `lower ≤ predicted ≤ upper` and `lower ≥ 0`; bounds width ties to the metadata `rmse_kwh` (held-out), not in-sample; prediction at step *t* feeds `lag_1h` at *t+1*; a frame with < 24 rows raises `InsufficientHistoryError`; a missing artifact surfaces `ModelArtifactError` and writes no file.
- [x] `ai-service/tests/test_smoke.py` -- extend `test_api_forecast_predict` with the ordering/bound assertions; add a warm-call p95 < 300 ms smoke check; add endpoint-level 422 (insufficient history) and 503 (missing artifact) tests covering the handler mappings.

**Acceptance Criteria:**
- Given the XGBoost artifact and ≥ 24 h of history, when `GET /internal/forecast/predict` is called, then the response holds 24 hourly points produced by `predict_forecast_autoregressive`, each with `timestamp`, `predicted_kwh`, `lower_bound_95` and `upper_bound_95`, and every timestamp is later than the last observed reading.
- Given the 95% bounds, when they are computed, then they use the residual standard deviation measured on the held-out test split (`xgboost_metrics.rmse_kwh`), not in-sample residuals.
- Given a warm service, when the endpoint is called repeatedly in a test, then the 95th-percentile response time is under 300 ms.
- Given fewer than 24 hours of history, when the endpoint is called, then it returns a 422 error envelope naming the missing history.

## Implementation Notes

## Spec Change Log

## Review Triage Log

3-layer review (blind-hunter, edge-case-hunter, verification-gap), 2026-10-09. 0 intent_gap, 0 bad_spec, 3 patch, 10 rejected/false.

- finding: "Timezone mismatch breaks the recursive path — `frame_ts.iloc[-tail_n:].to_numpy()` strips tz to naive while `future_dt` is tz-aware, so the recursive column mixes tz and `pd.to_datetime` raises / lag lookups silently fall back (blind-hunter)"
  verdict: false
  evidence: "Verified on pandas 3.0.6 (the project's version): `Series(tz-aware).to_numpy()` returns an object array of tz-aware Timestamps, not naive datetime64, so no naive/aware mix occurs; `pd.to_datetime` on the recursive column stays `datetime64[us, UTC]` and does not raise, and the tz-aware lag key matches the dict (`probe in d` → True). The premise that `.to_numpy()` strips tz is incorrect; the timestamp-keyed lag lookups match as designed."
- finding: "Per-request metadata disk read contradicts the 'warm call does no disk I/O' Design Note — `EnergyInferencePipeline(models_dir=get_models_dir())` is constructed every call and its `_load_metadata()` reopens `model_metadata.json` (blind-hunter, edge-case-hunter, verification-gap)"
  verdict: low
  evidence: "Confirmed: `predict_next_24h` builds a fresh pipeline each request; the constructor reads the JSON from disk. p95 is unaffected (tiny file) but it is an every-request disk read that the Design Note says should not happen. → patch: cache the pipeline instance."
- finding: "Temperature-proxy values are unasserted — no test reads any `outdoor_temperature_c` value; a regressed proxy (e.g. off-by-one fallback) ships undetected (verification-gap, blind-hunter)"
  verdict: medium
  evidence: "Confirmed: `test_returns_24_rows_and_columns` checks only the column name; the smoke test never reads the field. The daily-seasonal proxy is the one new forecasting decision and is unpinned. → patch: assert each value equals the frame's reading at `future_ts − 24h` and is finite."
- finding: "Dataset-missing 503 `ERR_DATA_NOT_FOUND` path (I/O matrix row 8) has no covering forecast test (blind-hunter)"
  verdict: low
  evidence: "Confirmed: only `ERR_MODEL_NOT_FOUND` and `ERR_INSUFFICIENT_HISTORY` are exercised for the forecast endpoint. The ServingDataError→503 mapping is tested via Story 1.1's energy endpoints and the same handler, but the matrix row is unbacked on this endpoint. → patch: add the forecast 503 dataset-missing test."
- finding: "Full re-parse of ~720 timestamps and 720-entry dict rebuild on every warm call despite the 'tiny' comment (blind-hunter)"
  verdict: low
  evidence: "Real but CPU-only; p95 < 300 ms still holds with the real artifact. Rejected: the fix adds cache state/complexity for no everyday harm; the stated-design violation (disk I/O) is handled by the pipeline-caching patch, this pure-CPU reparse is negligible."
- finding: "`test_bounds_width_ties_to_heldout_rmse` asserts `len(non_floored) > 0`, which fails if every prediction < ~145 kWh (all lower bounds floor to 0) (blind-hunter)"
  verdict: low
  evidence: "Passes on the real fixture (office-building loads exceed 1.96×74.02≈145 for part of the day). Data-dependent but not met in everyday use; rejected (fix would weaken the assertion or add a guard)."
- finding: "`test_api_forecast_predict_warm_p95` is a flaky in-process timing test that can false-fail on shared CI (blind-hunter)"
  verdict: low
  evidence: "The spec AC explicitly requires verifying p95 < 300 ms, so the test is mandated; loosening it would contradict the acceptance criterion. Rejected (the fix edits a spec-mandated check). CI-timing risk noted in Design Notes already flagged at implementation."
- finding: "Tests reassign `os.environ`, module globals and `get_serving_frame` with manual try/finally instead of `monkeypatch`; not xdist-safe (blind-hunter)"
  verdict: low
  evidence: "try/finally restores state and the suite does not run under pytest-xdist; no everyday harm. Rejected (fix is a multi-test rewrite beyond a direct correction)."
- finding: "Spec `status: in-review` disagrees with `sprint-status.yaml: in-progress` (blind-hunter)"
  verdict: false
  evidence: "Transient by workflow design: step-04 sets the spec to in-review; sprint-status syncs to review/done in a later step. Not a defect."
- finding: "Stale spec sections — 'Review Findings' says _Pending implementation_ and Implementation Notes / Spec Change Log / Review Triage Log are empty (blind-hunter)"
  verdict: false
  evidence: "Rejected: the fix is to edit this build's spec, and these sections are filled during the review/present steps (this triage log is one of them)."
- finding: "Cache race — `predict_next_24h` reads `_cached_xgb_model`/`_cached_meta` in a second locked section after `get_serving_frame` returns; a concurrent `reset_serving_cache()` in the gap raises a spurious `ModelArtifactError` (blind-hunter, edge-case-hunter)"
  verdict: low
  evidence: "Real under a concurrent cache clear mid-request (rare admin action); the effect is one transient 503 that a retry clears. Rejected: unlikely in everyday use and the fix restructures the locking/signature beyond a direct correction."
- finding: "Duplicated constants — `horizon_hours: 24` and `building_id: 'office_tower_01'` hardcoded in `forecast.py` while the horizon also exists as `FORECAST_HORIZON_HOURS` and the id is repeated in `compute_energy_metrics` (blind-hunter)"
  verdict: low
  evidence: "Pre-existing: both literals were already in `forecast.py` and `compute_energy_metrics` before this story; not caused by the change. Rejected (cosmetic, pre-existing)."
- finding: "Redundant `str(row['timestamp'])` cast in `_get_forecast` masks a future type regression (blind-hunter)"
  verdict: low
  evidence: "Pre-existing no-op cast; `predict_next_24h` returns ISO-Z strings. Cosmetic, not caused by this change. Rejected."

## Design Notes

- **Bounds:** `predicted_kwh ± 1.96 × xgboost_metrics.rmse_kwh` from `model_metadata.json` (held-out test RMSE = 74.02 kWh on the real artifact), lower floored at 0. This is the same held-out-error convention Story 1.1 established for the serving frame, and it replaces `predictor.py`'s in-sample `residual_std = 8.5`.
- **Future temperatures:** no weather-forecast feed exists and the AI service reads files only (AD: no network/DB), so each future hour reuses the serving frame's `outdoor_temperature_c` from the same hour on the previous day (daily seasonality). This is a documented proxy, recorded here so the choice is visible; a real temperature forecast is out of scope for Epic 1 and can replace this later without changing the endpoint contract.
- **History & model reuse:** `predict_next_24h` reuses the cached `_cached_base_df` and a newly cached `_cached_xgb_model`, so a warm call does no disk I/O; the 24-step recursive loop is ~24 single-row `xgb.predict` calls, well within the 300 ms p95 budget. Cold start (first call) pays the one-time load already owned by the serving frame.
- **Last-observed anchor:** the serving frame's last row is the current UTC hour (Story 1.1 replays the window to "now"), so the 24 future steps are `current_hour + 1 … current_hour + 24`.
- **Timestamp format:** `predict_forecast_autoregressive` emits `"%Y-%m-%d %H:%M:%S"`; `predict_next_24h` must convert to ISO 8601 UTC with `Z` (`"%Y-%m-%dT%H:%M:%SZ"`) to match NFR7 and the serving frame's timeseries format.
- **Temporary coexistence:** the old `energy_forecaster` / `data_loader` / `predictor.py` in-sample path stays in the tree until Story 1.5 removes it; this story only stops the forecast endpoint from reaching it.
- **No live UI consumer yet:** the dashboard `ForecastChart` is fed by the energy *timeseries* endpoint, not `/forecast/predict`; `getForecast()` in `frontend/src/services/api.js` and the smoke test are the only consumers. The contract is kept stable so a future forecast view can use it.

## Verification

**Commands:**
- `cd ai-service && python -m pytest -q` -- expected: all tests pass, including `tests/test_forecast_service.py` and the extended `test_api_forecast_predict`.
- `cd ai-service && python -c "from src.data_pipeline.serving_frame import predict_next_24h; d = predict_next_24h(); print(len(d), list(d.columns)); print(d['timestamp'].iloc[0], d['timestamp'].iloc[-1])"` -- expected: `24`, the five columns, and 24 ISO-`Z` timestamps after the current hour, using the local BDG2 data.
- `npm run test --prefix backend` -- expected: unchanged, all pass (the gateway only proxies the endpoint).

### Review Findings

3-layer review (blind-hunter, edge-case-hunter, verification-gap) at Opus capability, 2026-10-09. 0 intent_gap, 0 bad_spec, 3 patch (applied), 10 rejected/false. Full triage with evidence is in `## Review Triage Log`.

**Patch (applied):**

- [x] [Review][Patch] Per-request metadata disk read [`ai-service/src/data_pipeline/serving_frame.py`] — `predict_next_24h` built a new `EnergyInferencePipeline` each call, whose `_load_metadata()` reopened `model_metadata.json`, contradicting the "warm call does no disk I/O" note. Fixed with a lock-guarded module-global `_cached_pipeline`, cleared in `reset_serving_cache()`.
- [x] [Review][Patch] Temperature-proxy values unasserted [`ai-service/tests/test_forecast_service.py`] — added `test_future_temperatures_match_prior_day_proxy`: each `outdoor_temperature_c` equals the frame's value at `future_ts − 24h` and all 24 are finite.
- [x] [Review][Patch] Dataset-missing 503 matrix row uncovered [`ai-service/tests/test_smoke.py`] — added `test_api_forecast_dataset_missing_503`: a missing `ECOTRACK_DATA_PATH` yields 503 `ERR_DATA_NOT_FOUND` from the endpoint.

**Rejected / false (key ones):**

- `false` — Timezone mismatch breaks the recursive path (blind-hunter): verified on pandas 3.0.6 that `Series(tz-aware).to_numpy()` keeps tz-aware Timestamps (object array), so no naive/aware mix, no raise, and lag keys match.
- `low` — Flaky warm-p95 timing test (blind-hunter): the test is mandated by the NFR3 acceptance criterion; loosening it would contradict the spec.
- `low` — Cache race on the model read under a concurrent `reset_serving_cache()` (blind-hunter, edge-case-hunter): rare admin cache-clear mid-request, transient 503 cleared by retry; fix restructures locking beyond a direct correction.
- `low` — Reparse of 720 timestamps per call, brittle data-dependent bounds assertion, non-`monkeypatch` test globals, duplicated `horizon_hours`/`building_id`, redundant `str()` cast: cosmetic or pre-existing, p95 budget still met.
- `false` — Spec/sprint-status state disagreement and stale spec sections: transient workflow state; filled by the review/present steps.

### Code Review Findings — 2026-10-09 (human review gate)

4-layer code review (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor) at Opus capability, 2026-10-09, over `03da475..HEAD`. 0 decision-needed, 2 patch, 1 defer, 8 rejected. The Acceptance Auditor found no acceptance-criteria violations. This is the human-gate review (`bmad-code-review`), separate from the build-loop triage in `## Review Triage Log`.

**Patch:**

- [x] [Review][Patch] Endpoint response field `outdoor_temperature_c` unpinned at the API boundary [`ai-service/tests/test_smoke.py`:111] — `test_api_forecast_predict`'s per-point loop asserts `timestamp`/`lower_bound_95`/`predicted_kwh`/`upper_bound_95` but never `outdoor_temperature_c`; the unit test checks only the DataFrame column, so dropping or renaming the field in `_get_forecast` ships green. Fixed: the smoke loop now asserts each forecast point carries a finite `outdoor_temperature_c`.
- [x] [Review][Patch] Hour-rollover flakiness — tests read the anchor separately from the forecast call [`ai-service/tests/test_forecast_service.py`:68, `ai-service/tests/test_smoke.py`:108] — `last_observed` was read via a `get_serving_frame()` call distinct from `predict_next_24h()` / the HTTP request; a UTC hour tick between the two diverged the anchors and false-failed the strict assertions. Fixed: `test_timestamps_increasing_and_after_last_observed` and `test_future_temperatures_match_prior_day_proxy` now pin a single `fixed_now` across both calls, and `test_api_forecast_predict` captures `last_observed` before issuing the request.

**Defer:**

- [x] [Review][Defer] Malformed / partial `model_metadata.json` raises an unhandled `KeyError` (bare 500, no error envelope) [`ai-service/src/data_pipeline/serving_frame.py`:91] — deferred: pre-existing Story 1.1 behavior in `_load_artifacts_and_base_frame` (`metadata["xgboost_metrics"]["rmse_kwh"]`), which runs inside `get_serving_frame` *before* `predict_next_24h`'s own read; not introduced by this change. The I/O matrix covers a wholly-absent artifact but not a present-but-incomplete metadata file.

**Rejected:**

- `low` — Temperature-proxy `else` fallback substitutes a positional (wrong-hour) value on a non-contiguous frame (blind-hunter + edge-case-hunter + acceptance-auditor): unreachable on the contiguous hourly serving frame (the proxy test asserts the `if` branch for all 24 points); the proposed fix adds a new `raise`/branch guarding a state never shown reachable.
- `false` — Spec `status: done` contradicts `sprint-status.yaml: review` (blind-hunter + acceptance-auditor): the two track different axes — `status: done` is the build's route/terminal state (implementation + build-loop review complete), `review` is the human lifecycle gate (this code review). `done`/`review` is the expected pairing entering the gate, and the only fix would edit the spec under review.
- `low` — Cache race: a concurrent `reset_serving_cache()` between `get_serving_frame()` returning and the locked model read yields a spurious 503 (blind-hunter + edge-case-hunter): `reset_serving_cache` has no production caller (tests only), so the window is unreachable in production; the fix changes `get_serving_frame`'s return contract (public surface).
- `low` — Tests mutate module globals / `os.environ` instead of `monkeypatch`; "not xdist-safe" (blind-hunter): each test restores state in `try/finally` and pytest-xdist isolates workers in separate processes, so globals/env are not shared; the fix is a multi-test refactor.
- `low` — No Pydantic `response_model` enforces the five-field shape (blind-hunter): pre-existing hand-rolled-dict pattern from Stories 1.1–1.2, not introduced here; adding response models is an enhancement that adds public surface.
- `low` — Reported `outdoor_temperature_c` differs from the model-consumed value (blind-hunter): `prepare_forecast_features` rounds `air_temperature` to 2 dp while the response reports the unrounded proxy; divergence ≤ 0.005 °C beyond two decimals, and the reported value is the genuine proxy input — cosmetic.
- `low` — Forecast path also hard-requires `isolation_forest.joblib` (acceptance-auditor): pre-existing shared-loader behavior; a missing ISO artifact still yields a correct 503 (naming the ISO file); the fix would split the shared loader.
- `low` — Redundant `str(row['timestamp'])` cast in `_get_forecast` (acceptance-auditor): pre-existing no-op; `predict_next_24h` already returns ISO-Z strings — cosmetic.
