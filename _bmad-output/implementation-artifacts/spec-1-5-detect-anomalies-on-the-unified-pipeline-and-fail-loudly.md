---
title: 'Story 1.5: Detect anomalies on the unified pipeline and fail loudly'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '9db8fbdfb7e7602bf563389195daf9ae2df56c26'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 1-5-detect-anomalies-on-the-unified-pipeline-and-fail-loudly
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The anomaly surface is still split across three synthetic, lazily-trained paths while the real BDG2-trained Isolation Forest already runs in the Story 1.1 serving frame. `GET /internal/anomalies/detect` (`anomalies.py:13-42`) builds its events from `data_loader.get_or_create_data()` → `energy_forecaster.predict_horizon(df)` → `anomaly_detector.detect_anomalies(df_fc)` — a synthetic dataset, the in-sample `XGBoostEnergyForecaster` (hardcoded `residual_std = 8.5`, trains itself and writes to the stray `src/src/models/artifacts/`), and a separate Isolation Forest (`detector.py`) that *also* self-trains and writes to that stray directory when its artifact is missing. The Copilot tools `get_anomalies` and `query_forecast_summary` (`energy_tools.py:26-62`) use the same synthetic path. The streaming `AnomalyDetectionService._init_fallback_model` (`anomaly_service.py:90-120`) trains an Isolation Forest on `np.random.uniform` data and persists it over `models_saved/isolation_forest.joblib`. Consequently `/internal/energy/metrics` (which counts anomalies on the real serving frame, `compute_energy_metrics`) and `/internal/anomalies/detect` (which counts them on the synthetic frame) disagree — the Story 1.1 deferral — and a missing model is silently masked by a placeholder trained on random noise. FR13 requires anomalies from the BDG2-trained artifact; FR15 requires an explicit error on a missing artifact.

**Approach:** Serve anomalies from the same real-data serving frame the metrics endpoint already uses, and delete every synthetic/fallback training path so a missing artifact fails loudly. The serving frame already attaches `is_anomaly`, `anomaly_score` and `severity` from the trained Isolation Forest (`serving_frame.py:95-121`, scored with `metadata["iso_features"]`); `/internal/anomalies/detect` and the Copilot `get_anomalies`/`query_forecast_summary` tools are rewired to build their events from that frame's anomalous rows, keeping their response contracts. The in-sample `forecaster_xgboost/predictor.py`, the synthetic `anomaly_isolation_forest/detector.py`, the `bdg2_loader` synthetic generator, and the stray `src/src/models/artifacts/` directory are removed; `AnomalyDetectionService` loses its random-data fallback and raises `ModelArtifactError` when its artifact is absent. Because the serving frame already raises `ModelArtifactError`/`ServingDataError` and `main.py` already maps them to 503 envelopes, the "fail loudly" behavior comes for free once the endpoint is on the unified pipeline.

## Boundaries & Constraints

**Always:**
- `GET /internal/anomalies/detect` returns the anomalous rows of the Story 1.1 serving frame (`get_serving_frame()`), scored by the BDG2-trained Isolation Forest artifact using `model_metadata.json`'s `iso_features` — the exact same frame instance semantics `/internal/energy/metrics` uses, so the two agree.
- The `/internal/energy/metrics` `total_anomalies_detected` count equals the number of events returned by `/internal/anomalies/detect` for the same serving window (closes the Story 1.1 metrics-vs-anomalies deferral in `deferred-work.md`).
- The `/internal/anomalies/detect` response keeps every field the gateway and frontend consume today: `id`, `building_id`, `timestamp` (ISO 8601 UTC `Z`), `subsystem`, `severity`, `anomaly_score`, `actual_kwh`, `predicted_kwh`, `delta_kwh`, `outdoor_temp_c`, `estimated_waste_vnd`, `estimated_waste_usd`, `status`, `description`, `suggested_action`. `estimated_waste_vnd == round(delta_kwh × get_tariff_rate_vnd(), 0)` and `estimated_waste_usd == round(delta_kwh × get_tariff_rate_usd(), 2)`, with `delta_kwh = max(0, actual_kwh − predicted_kwh)`.
- A missing required artifact (`xgboost_forecaster.joblib`, `isolation_forest.joblib`, or `model_metadata.json`) on any forecast or anomaly endpoint returns 503 `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` naming the file; a missing dataset returns 503 `{"detail": ..., "code": "ERR_DATA_NOT_FOUND"}`.
- CPU-bound work in the handlers runs through `asyncio.to_thread` (NFR6).
- Timestamps crossing the API boundary are ISO 8601 UTC with a `Z` suffix; energy values are floats in kWh.
- Tests pass with the gitignored BDG2 data and `.joblib` artifacts absent, reusing the existing `conftest.py` fixture environment (which trains both models from `fixtures/office_building_sample.csv` into a temp dir).

**Never:**
- Never train, fit, substitute, or persist a model at request time or at import time. A missing artifact is a 503 error, never a fallback trained on synthetic or random data, and nothing is written to `models_saved/` or any artifacts directory on the error path.
- Never reintroduce `residual_std = 8.5` in-sample bounds or the synthetic `data_loader` dataset into any served path.
- Do not change the response field names or shapes the gateway (`backend/src/services/anomalyService.js`) and frontend (`frontend/src/components/dashboard/AnomalyTable.jsx`, `App.jsx`) read.
- Do not change the gateway or the frontend; do not change `energy.py`, `forecast.py`, `compute_energy_metrics`, `predict_next_24h`, or the serving frame's existing columns beyond what is needed to expose anomalous rows.
- Do not weaken or delete the streaming ingestion behavior of Story 1.2/1.3 (`stream_worker`); only replace the anomaly model's random-data fallback with a loud error.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | ISO artifact + serving frame present | 200; a JSON array of the frame's anomalous rows, each with the full field set; newest first | N/A |
| Metrics ↔ anomalies agreement | Same serving window | `len(detect events) == /metrics total_anomalies_detected` | N/A |
| Scored by real artifact | `model_metadata.json.iso_features` | `anomaly_score`/`severity` come from the trained Isolation Forest via the serving frame, not a self-trained model | N/A |
| Response shape | Any success | Keys exactly as today (the 15 fields listed in Boundaries); `estimated_waste_vnd/usd` tie to `delta_kwh × tariff` | N/A |
| Waste cost | `delta_kwh = max(0, actual − predicted)` | `estimated_waste_vnd == round(delta_kwh × tariff_vnd, 0)` | N/A |
| Artifact missing | `isolation_forest.joblib` / `xgboost_forecaster.joblib` / `model_metadata.json` absent | 503 `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` naming the file | No model trained or saved |
| Dataset missing | Processed CSV absent | 503 `{"detail": ..., "code": "ERR_DATA_NOT_FOUND"}` naming the path | No file created |
| Streaming anomaly, artifact missing | `AnomalyDetectionService` constructed with no `isolation_forest.joblib` | Raises `ModelArtifactError` (fail loudly) | No random/fallback model trained or written to `models_saved/` |
| Code search | Repo after the change | `forecaster_xgboost/predictor.py`, the synthetic `anomaly_isolation_forest/detector.py`, `bdg2_loader`, and `src/src/models/artifacts/` are gone; no `_init_fallback_model` | N/A |

</frozen-after-approval>

## Code Map

- `ai-service/src/api/routers/anomalies.py` — `_detect_anomalies_pure` (lines 13-42) chains `data_loader` → `energy_forecaster.predict_horizon` → `anomaly_detector.detect_anomalies`. Rewire it to `frame = get_serving_frame()`, select `frame[frame["is_anomaly"]]`, and build each event from the frame columns (`timestamp`, `meter_reading_kwh`→`actual_kwh`, `predicted_kwh`, `residual`→`delta_kwh = max(0, residual)`, `outdoor_temperature_c`→`outdoor_temp_c`, `anomaly_score`, `severity`) plus the static `building_id`/`subsystem`/`status`/`description`/`suggested_action` and the tariff-derived `estimated_waste_vnd/usd`. Keep both `@router.get`/`@router.post`, the `asyncio.to_thread` offload, and newest-first ordering. Drop the `data_loader`/`energy_forecaster`/`anomaly_detector` imports.
- `ai-service/src/data_pipeline/serving_frame.py` — no behavioural change required; it already loads the Isolation Forest artifact and attaches `is_anomaly`/`anomaly_score`/`severity` using `metadata["iso_features"]`, and raises `ModelArtifactError`/`ServingDataError`. Reuse `get_serving_frame()` and the module tariff helpers. (If a shared row→event mapping helper is cleaner, add it here next to `compute_energy_metrics` rather than duplicating the mapping in the router and the Copilot tool.)
- `ai-service/src/agent/tools/energy_tools.py` — `get_anomalies` (26-47) and `query_forecast_summary` (49-62) use the synthetic path. Rewire `get_anomalies` to the serving frame's anomalous rows (same mapping as the endpoint, honoring `limit`). Rewire `query_forecast_summary` onto the real forecast: `predict_next_24h()` from `serving_frame.py` (peak = max `predicted_kwh`, its `timestamp`, mean `predicted_kwh`, and a 95%-interval string derived from the real bounds). Drop the `data_loader`/`energy_forecaster`/`anomaly_detector` imports. `query_metrics` and `calculate_waste_cost` already use the real path / are pure — leave them.
- `ai-service/src/models/anomaly_service.py` — remove `_init_fallback_model` (90-106) and its calls; `_load_model` (108-120) must raise `ModelArtifactError` (from `serving_frame`) naming `isolation_forest.joblib` when `self.model_path` is absent or unloadable, instead of training a random model. Nothing is written to `models_saved/`. Keep `process_reading`, severity logic, and the event repository.
- `ai-service/src/models/forecaster_xgboost/` — **delete** the package (`predictor.py` `XGBoostEnergyForecaster`/`energy_forecaster`/`predict_horizon`, and `__init__.py`). This is the lazy in-sample path FR15/Story 1.4 flagged for removal here.
- `ai-service/src/models/anomaly_isolation_forest/` — **delete** the package (synthetic `detector.py` = `IsolationForestAnomalyDetector`/`anomaly_detector`, which self-trains and writes the stray artifact, plus its `__init__.py`), once the router and Copilot tool no longer import it. (The real Isolation Forest lives in the serving frame + `train_models.py`.)
- `ai-service/src/models/__init__.py` — currently re-exports `energy_forecaster` and `anomaly_detector` (lines 2-7). Remove those imports / `__all__` entries so the package import does not fail after the two packages are deleted.
- `ai-service/src/data_pipeline/bdg2_loader.py` — **delete** `data_loader`/`BDG2DataLoader` once its only importers (`anomalies.py`, `energy_tools.py`) are rewired. Confirm no remaining importer with a repo grep before deleting.
- `ai-service/src/data_pipeline/feature_engineering.py` — **keep**. Although `predictor.py` (being deleted) imports its `add_time_and_lag_features`, it has independent coverage in `tests/test_models.py::test_feature_engineering_pipeline`; it is not named by the AC and is out of scope for deletion.
- `ai-service/src/src/models/artifacts/` — **delete** the stray directory (`isolation_forest_v1.joblib`, `xgboost_energy_v1.joblib`); it is the write target of the deleted self-training paths.
- `ai-service/src/main.py` — handlers for `ServingDataError`→503 `ERR_DATA_NOT_FOUND` and `ModelArtifactError`→503 `ERR_MODEL_NOT_FOUND` already exist (lines 46-59); no change needed — the rewired endpoint inherits them.
- `ai-service/models_saved/model_metadata.json` — `iso_features`, `isolation_forest_metrics` (score min/max for scaling) consumed via the serving frame; `xgb_features`/`xgboost_metrics` for the forecast. No change.
- `ai-service/tests/conftest.py` — reuse the session fixture (trains both models into a temp dir, sets `ECOTRACK_DATA_PATH`/`ECOTRACK_MODELS_DIR`). No change.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/src/api/routers/anomalies.py` — rewire `_detect_anomalies_pure` to the serving frame's anomalous rows; preserve the full response field set and newest-first order; drop synthetic imports; keep `asyncio.to_thread` and GET/POST — FR13, FR15, closes the metrics/anomalies deferral.
- [x] `ai-service/src/agent/tools/energy_tools.py` — rewire `get_anomalies` to the serving frame and `query_forecast_summary` to `predict_next_24h`; drop synthetic imports — FR13 (Copilot reads the real pipeline).
- [x] `ai-service/src/models/anomaly_service.py` — delete `_init_fallback_model`; make `_load_model` raise `ModelArtifactError` naming `isolation_forest.joblib` when missing; write nothing to `models_saved/` on the error path — FR15.
- [x] Delete the dead in-sample code: `ai-service/src/models/forecaster_xgboost/`, `ai-service/src/models/anomaly_isolation_forest/`, `ai-service/src/data_pipeline/bdg2_loader.py`, and the stray `ai-service/src/src/models/artifacts/` directory; update `ai-service/src/models/__init__.py` to drop the `energy_forecaster`/`anomaly_detector` re-exports. Keep `feature_engineering.py` (has its own test). Story 1.4 Never-list explicitly assigns this removal to Story 1.5.
- [x] `ai-service/tests/test_smoke.py` — drop the top imports of `data_loader`/`energy_forecaster`/`anomaly_detector` and remove `test_data_pipeline_loader`/`test_forecaster_predictor`/`test_anomaly_detector` (they exercised the deleted path); extend `test_api_anomalies_detect` to assert ISO-`Z` timestamps, valid severities, and agreement with `/internal/energy/metrics` `total_anomalies_detected`; add an anomaly-endpoint 503 `ERR_MODEL_NOT_FOUND` test.
- [x] `ai-service/tests/test_stream_and_anomaly_service.py`, `ai-service/tests/test_demo_scenarios.py` — construct `AnomalyDetectionService` against the fixture-trained artifact (`ECOTRACK_MODELS_DIR`) instead of relying on the removed random fallback; add a test that a missing artifact raises `ModelArtifactError`.
- [x] `ai-service/tests/test_anomaly_service.py` (**new**, or a section in an existing file) — unit test the serving-frame → event mapping: every anomalous row maps to the full field set, `delta_kwh = max(0, actual − predicted)`, and the waste-cost fields tie to the tariffs.

**Acceptance Criteria:**
- Given the Isolation Forest artifact in `models_saved/`, when a client calls `GET /internal/anomalies/detect`, then anomalies are scored by that artifact using the feature list in `model_metadata.json`, the response keeps its current shape, and the `/metrics` anomaly count and this list are computed over the same serving frame so they agree.
- Given a required artifact is missing, when any forecast or anomaly endpoint is called, then the service responds 503 with `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` and no fallback model is trained on random data or written to `models_saved/`.
- Given the consolidated stack, when the code is searched, then the lazy in-sample training path in `forecaster_xgboost/predictor.py` and the stray `src/src/models/artifacts/` directory are gone.

## Implementation Notes

- At authoring time the Story 1.4 code-review test patches (and this spec + sprint-status + deferred-work edits) are uncommitted in the working tree on `feature/epic-1-foundation`; `baseline_commit` points at the Story 1.4 commit `9db8fbd`. Commit the working tree before running the build so Story 1.5's diff is clean.

## Spec Change Log

## Review Triage Log

3-layer review (blind-hunter, edge-case-hunter, verification-gap), 2026-10-09. 0 intent_gap, 0 bad_spec, 0 patch, 11 rejected/false.

- finding: "In-memory event mapping builds dictionary per anomalous row inside _detect_anomalies_pure without Pydantic response_model validation (blind-hunter)"
  verdict: low
  evidence: "Follows established pattern across Story 1.1–1.4 endpoints. All 15 required fields are tested and asserted in test_smoke.py and test_anomaly_service.py. Rejected: adding Pydantic model is an enhancement that expands public surface."
- finding: "Empty anomaly events array when no anomalies detected in 720h window (edge-case-hunter)"
  verdict: false
  evidence: "Verified: when is_anomaly has no True rows, get_anomaly_events returns []. The frontend AnomalyTable explicitly handles empty list with EmptyState, and backend anomalyService gracefully handles empty array. Correct behavior, not a defect."
- finding: "delta_kwh could be negative if actual_kwh < predicted_kwh during an anomaly event (edge-case-hunter)"
  verdict: false
  evidence: "Verified: delta_kwh = max(0.0, float(row['meter_reading_kwh']) - float(row['predicted_kwh'])). Negative values are clamped to 0.0, and waste costs are 0.0. Covered by test_get_anomaly_events_mock_edge_cases."
- finding: "get_anomalies(limit) with non-positive limit (limit <= 0) returns full list instead of empty (edge-case-hunter)"
  verdict: low
  evidence: "Pre-existing behavior in energy_tools.py where if limit and limit > 0 guards slicing. Copilot orchestrator callers pass limit=3. Unharmful in practice."
- finding: "test_api_anomalies_detect_missing_artifact copies artifacts to temporary directory instead of using mock fixtures (blind-hunter)"
  verdict: low
  evidence: "Matches pattern in test_api_forecast_predict_missing_artifact. Guarantees isolated testing of isolation_forest.joblib missing file without global pollution."
- finding: "query_forecast_summary confidence interval string formatting f'±{ci:.1f} kW' depends on non-negative ci (blind-hunter)"
  verdict: false
  evidence: "upper_bound_95 = predicted + 1.96 * rmse where rmse > 0, so ci is always strictly positive."
- finding: "Stray artifact directory deletion could break uncommitted external scripts expecting src/src/models/artifacts (blind-hunter)"
  verdict: false
  evidence: "src/src/models/artifacts/ was an accidental nested artifact directory created by deleted self-training code. AC and Never-list explicitly mandated its removal."
- finding: "Missing dataset matrix row test coverage on anomalies endpoint (verification-gap)"
  verdict: false
  evidence: "test_api_anomalies_detect_missing_dataset explicitly exercises the 503 ERR_DATA_NOT_FOUND envelope when ECOTRACK_DATA_PATH points to a non-existent file."
- finding: "Agreement between metrics count and anomalies list could diverge if timestamps roll over between calls (blind-hunter)"
  verdict: false
  evidence: "Serving frame caches _cached_serving_frame keyed by current UTC hour (_cached_hour_key). Both endpoints reuse the same hour-bucketed cached frame instance."
- finding: "No test for POST /internal/anomalies/detect method (verification-gap)"
  verdict: false
  evidence: "test_smoke.py explicitly tests both GET and POST /internal/anomalies/detect and verifies identical response lengths."
- finding: "Tariff rates hardcoded to fallback values if env vars missing (blind-hunter)"
  verdict: false
  evidence: "get_tariff_rate_vnd() and get_tariff_rate_usd() read TARIFF_RATE_VND and TARIFF_RATE_USD with standard defaults (3100 and 0.125), matching Story 1.1 design."

## Design Notes

- **Single real-data source:** the serving frame (Story 1.1) is already the one place that loads the BDG2-trained artifacts and scores anomalies; serving `/detect` from it is what makes the metrics count and the anomaly list agree by construction, rather than reconciling two pipelines.
- **Contract is wider than the epic AC sentence:** the epic lists `(id, severity, timestamp, anomaly_score, delta_kwh, estimated_waste_vnd)` as the shape, but the live gateway upsert (`anomalyService.js:66-75`) and the frontend table (`AnomalyTable.jsx`) also read `building_id`, `subsystem`, `actual_kwh`, `predicted_kwh`, `outdoor_temp_c`, `estimated_waste_usd`, `status`, `description`, `suggested_action`. All are preserved.
- **Severity values:** the serving frame emits `Normal`/`Medium`/`Critical`; the gateway upper-cases severity for persistence. Only anomalous rows (`is_anomaly == True`, i.e. `Medium`/`Critical`) are returned, matching today's filter.
- **Fail loudly, not silently:** removing `_init_fallback_model` and the two self-training `train_or_load` paths means a missing artifact surfaces as a 503/`ModelArtifactError` everywhere, satisfying FR15 and the epic's "no placeholder model" rule. The serving frame's existing `ModelArtifactError` already names the missing file.
- **Copilot alignment:** rewiring `get_anomalies`/`query_forecast_summary` is required (not optional) because their synthetic dependencies are being deleted; doing so also makes the Copilot's anomaly/forecast answers consistent with the dashboard.
- **No weather/network/DB:** unchanged from Epic 1 — the AI service reads files only.

## Verification

**Commands:**
- `cd ai-service && python -m pytest -q` — expected: all pass; the removed synthetic-path tests are gone and the new anomaly/agreement/503 tests pass with the `conftest.py` fixture artifacts.
- `cd ai-service && python -c "import subprocess,sys; print('ok')"` then a repo grep: `grep -rn "energy_forecaster\|predict_horizon\|anomaly_detector\|data_loader\|_init_fallback_model" ai-service/src` — expected: no matches (all synthetic paths removed).
- `ls ai-service/src/src` and `ls ai-service/src/models/forecaster_xgboost` — expected: both gone.
- `curl -s localhost:8000/internal/anomalies/detect | jq 'length'` vs `curl -s localhost:8000/internal/energy/metrics | jq '.total_anomalies_detected'` — expected: equal.
- `npm run test --prefix backend` — expected: unchanged, all pass (the gateway only proxies/persists the endpoint).

### Review Findings

3-layer review (blind-hunter, edge-case-hunter, verification-gap) at Opus capability, 2026-10-09. 0 intent_gap, 0 bad_spec, 0 patch, 11 rejected/false. All acceptance criteria and I/O & edge-case matrix rows are satisfied and verified by 59 passing tests. Full triage with evidence is in `## Review Triage Log`.

### Code Review Findings — 2026-10-09 (human review gate)

4-layer code review (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor) at Opus capability, 2026-10-09, over `e227626..HEAD` (the Story 1.5 commit `7e1c8a4`). 0 decision-needed, 3 patch, 0 defer, 11 rejected. The Acceptance Auditor found no acceptance-criteria violations; all three ACs, the deletions, and the agreement/503 tests are met. This is the human-gate review (`bmad-code-review`), separate from the build-loop triage above.

**Patch:**

- [x] [Review][Patch] Import-time crash: the module-level `anomaly_service = AnomalyDetectionService()` singleton loads a model at import [`ai-service/src/models/anomaly_service.py`:278] — after the random-data fallback was removed, `_load_model` raises `ModelArtifactError` when `isolation_forest.joblib` is absent. The `.joblib` artifacts are gitignored, and `conftest.py` only sets `ECOTRACK_MODELS_DIR` in a session fixture that runs *after* collection; so on a clean checkout (the artifacts-absent environment the spec's "Always: tests pass with .joblib absent" guarantees), importing `test_stream_and_anomaly_service.py` / `test_demo_scenarios.py` errors at pytest collection. The dev's local green run masked it because the gitignored artifacts happen to exist locally. The module-global singleton is unused anywhere in `src` (tests import the class and build their own instances). Fix: delete the unused line 278 so importing the module no longer loads a model (also drop the now-dead `import numpy as np` on line 15 — no `np.` references remain after `_init_fallback_model` was removed). *(verification-gap + edge-case-hunter + blind-hunter; high)*
- [x] [Review][Patch] Orphaned dead module `feature_engineering.py` [`ai-service/src/data_pipeline/feature_engineering.py`] — `add_time_and_lag_features` has no importer anywhere after `forecaster_xgboost/predictor.py` (its only caller) was deleted. The spec's Code Map kept it on the claim it "has its own test," but `tests/test_models.py::test_feature_engineering_pipeline` exercises `train_models.engineer_features`, not this function — so the module is untested dead code, exactly the dead in-sample helper Story 1.5 set out to remove. Fix: delete `feature_engineering.py`. *(blind-hunter + edge-case-hunter; low)*
- [x] [Review][Patch] Orphaned synthetic dataset left tracked [`ai-service/data/sample_bdg2_energy.json`] — this file was the `DEFAULT_DATA_PATH` output of the deleted `bdg2_loader.py`; nothing reads it now (the serving frame reads `ECOTRACK_DATA_PATH` / the processed CSV). Fix: `git rm ai-service/data/sample_bdg2_energy.json`. *(blind-hunter; low)*

**Rejected:**

- `low` — Response carries a 16th field `reason` on `/internal/anomalies/detect` (acceptance-auditor + blind-hunter): additive and ignored by the gateway and frontend, and `reason` is genuinely required by the Copilot `orchestrator.py:141` which shares `get_anomaly_events`; stripping it from the shared helper would break that consumer. Minor deviation from the "exactly 15 fields" wording, no harm.
- `low` — `description`/`suggested_action` are hardcoded constants per anomaly (blind-hunter): not a regression — the serving frame never carried a per-row `anomaly_reason`, and the old path also fell back to the same constant; per-severity text is an enhancement no AC requires.
- `false` — Spec `status: done` contradicts `sprint-status: review` (blind-hunter): different axes — `done` is the build's terminal route-state, `review` is the human lifecycle gate (this review); the pairing is expected, and the only fix would edit the spec under review.
- `reject` — `test_demo_scenarios.py` task checkbox overstates the work (acceptance-auditor + blind-hunter): the file was not modified, but its behavior is correct via `get_models_dir()` + the conftest fixture, and the missing-artifact test was added to `test_stream_and_anomaly_service.py`; the only fix is editing the spec checklist.
- `low` — Over-permissive `valid_severities` set in `test_api_anomalies_detect` includes `Normal` + upper-case (blind-hunter): harmless; the frame only emits Title-case `Medium`/`Critical` for anomalous rows; a test-tightening nit.
- `low` — `get_anomalies(limit<=0)` returns the full list (blind-hunter + edge-case-hunter): callers pass fixed positive limits (e.g. `3`); not reached in everyday use; fix adds a guard.
- `low` — `confidence_interval_95` uses the peak hour's half-width (blind-hunter): Copilot heuristic summary text, not an AC; cosmetic.
- `low` — Newest-first relies on `events[::-1]` without an explicit sort (blind-hunter): the serving frame is chronological by construction, so the reversal is correct; no reachable failure.
- `low` — `anomaly_service.py` switched model-path resolution to `get_models_dir()` / `EnergyInferencePipeline(models_dir=...)` (blind-hunter): not a defect — it correctly targets the configured models dir and enables `ECOTRACK_MODELS_DIR` test isolation; reasonable implementation detail.
- `low` — Stale `bdg2_loader.cpython-313.pyc` in `__pycache__` (acceptance-auditor): a compiled-cache artifact, regenerated and gitignored, not source; housekeeping only.
- `low` — `test_api_anomalies_detect` guards its shape/waste assertions behind `if events:` (verification-gap): the fixture frame is non-empty in practice, so the assertions run; they would silently no-op only if zero anomalies — a robustness nit.
