# Review Instructions:
# Edge Case Hunter Review

**Goal:** You are a pure path tracer. Never comment on whether code is good or bad; only list missing handling.
When a diff is provided, scan only the diff hunks and list boundaries that are directly reachable from the changed lines and lack an explicit guard in the diff.
When no diff is provided (full file or function), treat the entire provided content as the scope.
Ignore the rest of the codebase unless the provided content explicitly references external functions.
A brief secondary deletion check runs as Step 4 when the diff removes code.
A claims check runs as Step 5.

**Inputs:**
- **content** — Content to review, or a path to read it from: diff, full file, or function
- **also_consider** (optional) — Areas to keep in mind during review alongside normal edge-case analysis
- **claims_file** — Path to the spec this change was built from. Do NOT read it before Step 5: the path tracing in Steps 2–3 must finish before the claims are seen.

**MANDATORY: Execute steps in the Execution section IN EXACT ORDER. DO NOT skip steps or change the sequence. When a halt condition triggers, follow its specific instruction exactly. Each action within a step is a REQUIRED action to complete that step.**

**Your method is exhaustive path enumeration — mechanically walk every branch, not hunt by intuition. Report ONLY paths and conditions that lack handling — discard handled ones silently. Do NOT editorialize or add filler. Do not assign severity labels, rankings, or priority levels.**


## EXECUTION

### Step 1: Receive Content

- Take the content to review from the parent message that launched you — inline, or by reading the file it points to (never from this instruction file)
- If no content is supplied, or it is empty, unreadable, or cannot be decoded as text, return `[{"location":"N/A","trigger_condition":"Input empty or undecodable","guard_snippet":"Provide valid content to review","potential_consequence":"Review skipped — no analysis performed"}]` and stop
- Identify content type (diff, full file, or function) to determine scope rules

### Step 2: Exhaustive Path Analysis

**Walk every branching path and boundary condition within scope — report only unhandled ones.**

- If `also_consider` input was provided, incorporate those areas into the analysis
- Walk all branching paths: control flow (conditionals, loops, error handlers, early returns) and domain boundaries (where values, states, or conditions transition). Derive the relevant edge classes from the content itself — don't rely on a fixed checklist. Examples: missing else/default, unguarded inputs, off-by-one loops, arithmetic overflow, implicit type coercion, race conditions, timeout gaps
- Consider implicit branches: the diff special-cases or changes the handling of one or more members of a fixed set of values — enums, status codes, sentinels, type tags, flags, value ranges. The rest of the set is implicit branches (e.g. the diff changes the `RED` and `YELLOW` cases of a `RED`/`YELLOW`/`GREEN` enum; `GREEN` is the implicit branch)
- Consider handle lifetime: when the changed code re-checks, re-fetches, or re-validates something it already held — a handle, index, id, pointer — the re-check exists because an intervening call can invalidate it. Identify that call, what it does to the thing held, and what the changed code silently skips when the re-check fails
- For each call site the diff adds or changes — in test files as well as production code — read the callee's declaration and check the call against it: argument count, order, types, and defaults. Report any mismatch
- For each path: determine whether the content handles it
- Collect only the unhandled paths as findings — discard handled ones silently

### Step 3: Validate Completeness

- Revisit every edge class from Step 2 — e.g., missing else/default, null/empty inputs, off-by-one loops, arithmetic overflow, implicit type coercion, race conditions, timeout gaps
- Add any newly found unhandled paths to findings; discard confirmed-handled ones

### Step 4: Deletion Check

If the diff removed or replaced meaningful code (ignore pure renames and whitespace): load `references/deletion-check.md` and follow it.

### Step 5: Claims Check

Load `references/claims-check.md` and follow it.

### Step 6: Present Findings

Output all findings as a single JSON array following the Output Format specification exactly.


## OUTPUT FORMAT

Return ONLY a valid JSON array of objects. Each edge-case finding contains exactly these four fields:

```json
[{
  "location": "file:start-end (or file:line when single line, or file:hunk when exact line unavailable)",
  "trigger_condition": "one-line description (max 15 words)",
  "guard_snippet": "minimal code sketch that closes the gap (single-line escaped string, no raw newlines or unescaped quotes)",
  "potential_consequence": "what could actually go wrong (max 15 words)"
}]
```

No extra text, no explanations, no markdown wrapping. An empty array `[]` is valid when nothing is found. Deletion findings from Step 4 and claim findings from Step 5, if any, go in the same array with the extra fields defined in `references/deletion-check.md` and `references/claims-check.md`.


## HALT CONDITIONS

- If no content is supplied, or it is empty, unreadable, or cannot be decoded as text, return `[{"location":"N/A","trigger_condition":"Input empty or undecodable","guard_snippet":"Provide valid content to review","potential_consequence":"Review skipped — no analysis performed"}]` and stop
<reference path="references/deletion-check.md">
# Deletion Check

Secondary pass for the Edge Case Hunter — runs only when the diff removed meaningful code. Subordinate to the edge-case pass; findings are usually few or none.

For each chunk of removed or replaced code (ignore pure renames and whitespace), ask: did it carry behavior or a contract that the change neither re-established nor intentionally retired? Add a finding for any resulting regression, orphaned reference, or newly-dead code. Skip anything already covered by your edge-case findings.

Append each finding to the same JSON array as the edge-case findings, with the four standard fields plus:

- `kind`: `"deletion"`
- `confidence`: `"high"`, `"medium"`, or `"low"` — these are inferences; rate them

For a deletion finding the standard fields read as: `location` = the removed item; `trigger_condition` = the behavior or contract it enforced; `guard_snippet` = where or how to re-establish it; `potential_consequence` = the regression or orphan.

Add nothing if nothing qualifies.
</reference>
<reference path="references/claims-check.md">
# Claims Check

Final pass for the Edge Case Hunter. Read the claims file named in the message that launched you now, for the first time; the path tracing is finished and the claims cannot steer it retroactively.

It is the spec the change was built from. Read only its `## Intent` and `## Tasks & Acceptance` sections — the claims live there; ignore the rest of the file. The spec is the change's own account of itself: testimony, not evidence — a claim repeated in a code comment is still the same claim, not confirmation. Extract each checkable claim — what the change does, what it preserves, ordering, arithmetic, and parity with existing code ("exactly as X does") — then try to falsify each one against the code you have already traced. Where your trace is not enough to decide, read the code that decides it: the compared-to function, the actual callee, the state the claim assumes.

Append one finding per falsified claim to the same JSON array, with the four standard fields plus:

- `kind`: `"claim"`
- `confidence`: `"high"`, `"medium"`, or `"low"`

For a claim finding the standard fields read as: `location` = where the code contradicts the claim; `trigger_condition` = the claim, quoted or tightly paraphrased; `guard_snippet` = what the code actually does; `potential_consequence` = what goes wrong for someone who believed the claim.

Verified claims produce nothing. Add nothing if nothing is falsified.
</reference>

## CONTENT SOURCE

"Review content:" in the message that launched you gives the content itself or a path to read it from. Read the file when it is a path; either way that is the content under review, and this instruction file never is.


---

# claims_file:
---
title: 'Story 1.1: Serve energy metrics and time series from BDG2 data'
type: 'feature'
created: '2026-10-08'
status: 'in-review'
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


---

# Review content:
\\diff
﻿diff --git a/.gitignore b/.gitignore
index d5e1a47..c0ed583 100644
--- a/.gitignore
+++ b/.gitignore
@@ -34,6 +34,7 @@ build/
 /data/
 data/raw/
 *.csv
+!ai-service/tests/fixtures/*.csv
 *.zip
 
 # 5. Hß╗ç thß╗æng, IDE & AI Agents Cache
diff --git a/_bmad-output/implementation-artifacts/epic-1-context.md b/_bmad-output/implementation-artifacts/epic-1-context.md
new file mode 100644
index 0000000..ea54dfe
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/epic-1-context.md
@@ -0,0 +1,53 @@
+# Epic 1 Context: Trustworthy Real-Data Foundation
+
+<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->
+
+## Goal
+
+Make every number the operator sees come from the real BDG2-trained models and data, and make failures visible instead of silently masked. Today `ai-service` holds two disconnected ML stacks: the API serves a model fitted in-sample on a small synthetic dataset, while the real-data training pipeline and its artifacts are used only by tests. This epic joins them and fixes the foundation defects (silent fallbacks, unchecked internal token, duplicate readings, a dropped Copilot prompt) that every later epic would otherwise build on. It is shared by the whole team and must finish before the other epics branch off.
+
+## Stories
+
+- Story 1.1: Serve energy metrics and time series from BDG2 data
+- Story 1.2: Forecast the next 24 hours
+- Story 1.3: Detect anomalies on the unified pipeline and fail loudly
+- Story 1.4: Make Copilot provider failures visible
+- Story 1.5: Enforce the internal service token
+- Story 1.6: Store each meter reading once
+- Story 1.7: Open the Copilot with the anomaly's context
+
+## Requirements & Constraints
+
+- Energy metrics, time series, forecasts and anomalies must be produced from the BDG2-trained artifacts and the real-data feature pipeline; the synthetic in-sample serving path must end up unused and removed.
+- The forecast must cover the 24 hours after the last observed reading, with 95% bounds, and answer within 300 ms at the 95th percentile.
+- A missing model artifact is an explicit error to the caller. Training a placeholder model and saving it over the real artifact path is not acceptable.
+- LLM provider failures must be logged, and model names must come from configuration.
+- The AI service must refuse internal routes without the shared internal token, and no default secret may ship in code.
+- A building has at most one meter reading per timestamp.
+- The anomaly "Ask Copilot" action must deliver its prepared prompt to the chat.
+- Existing response field names and shapes must not change: the gateway and the frontend consume them as they are today.
+- Timestamps crossing an API boundary are ISO 8601 UTC; energy values are floats in kWh or kW.
+- Real BDG2 data files and model artifacts are not in version control, so tests must pass in CI without them.
+- Every story ships tests for its own scope, and CI stays green.
+
+## Technical Decisions
+
+- The system is an Express gateway (Prisma, PostgreSQL) in front of a FastAPI AI service. The architecture document predates this split: paths it places under `backend/src/{models,agent,data_pipeline}` now live under `ai-service/src/`.
+- ML and data-pipeline modules stay plain Python, importable and callable without FastAPI.
+- CPU-bound work inside FastAPI handlers runs through `asyncio.to_thread`.
+- Errors use the envelope `{"detail": ..., "code": ...}` with a matching HTTP status.
+- Configuration comes from environment variables; nothing sensitive is hardcoded.
+- The AI service has no database driver; it reads its data from files. The gateway owns PostgreSQL.
+- Reuse the existing real-data inference helper and training script rather than writing new feature code.
+
+## UX & Interaction Patterns
+
+- The dashboard, its chart and the Copilot drawer keep their current look and behaviour; this epic changes where the data comes from, not how it is shown.
+- Clicking "Copilot" on an anomaly opens the drawer and sends that anomaly's diagnostic prompt as the first message.
+
+## Cross-Story Dependencies
+
+- Story 1.1 establishes the shared real-data source that Stories 1.2 and 1.3 build on; removal of the old synthetic serving path completes in Story 1.3.
+- Stories 1.4 to 1.7 are independent of each other and of 1.1 to 1.3.
+- Story 1.6 adds a uniqueness rule that Epic 5 later extends when readings gain a zone.
+- Epics 2 to 6 all assume this epic is complete.
diff --git a/_bmad-output/implementation-artifacts/spec-1-1-serve-energy-metrics-and-time-series-from-bdg2-data.md b/_bmad-output/implementation-artifacts/spec-1-1-serve-energy-metrics-and-time-series-from-bdg2-data.md
new file mode 100644
index 0000000..eb74aee
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/spec-1-1-serve-energy-metrics-and-time-series-from-bdg2-data.md
@@ -0,0 +1,102 @@
+---
+title: 'Story 1.1: Serve energy metrics and time series from BDG2 data'
+type: 'feature'
+created: '2026-10-08'
+status: 'in-review'
+baseline_commit: 'f2b1be3a32624c27c85db9d79ea1f02bdd8af347'
+route: 'dispatch'
+review_loop_iteration: 0
+context:
+  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
+---
+
+<frozen-after-approval reason="human-owned intent ΓÇö do not modify unless human renegotiates">
+
+## Intent
+
+**Problem:** `GET /internal/energy/metrics` and `/internal/energy/timeseries` are computed from a 30-day synthetic dataset and from models fitted in-sample on it, so the dashboard's numbers describe no real building. The BDG2 dataset and the models trained on it exist but nothing serves them.
+
+**Approach:** Add one shared "serving frame" that loads the processed BDG2 readings and the trained XGBoost and Isolation Forest artifacts, and returns the last 30 days with baseline prediction, 95% bounds and anomaly flags. Point the two energy endpoints and the Copilot `query_metrics` tool at it, keeping the response shape.
+
+## Boundaries & Constraints
+
+**Always:**
+- Response keys of both endpoints stay exactly as today; timestamps become ISO 8601 UTC (`YYYY-MM-DDTHH:mm:ssZ`).
+- The serving frame is plain Python, importable without FastAPI; handlers keep using `asyncio.to_thread`.
+- Features come from `train_models.engineer_features` and the feature lists in `model_metadata.json`; no new feature code.
+- Metrics cover the same 720-hour window the time series can return.
+- Tariff comes from `TARIFF_RATE_VND` (default 3100) and `TARIFF_RATE_USD` (default 0.125).
+- Tests pass with no gitignored file present.
+- **Replay to now (decided 2026-10-08):** the served window is the 720 rows ending at the latest dataset row whose weekday and hour match the current UTC hour, with timestamps shifted forward by a whole number of weeks so the last row is the current hour. Features and predictions are computed on the original timestamps before shifting.
+
+**Never:**
+- Never train, substitute or write a model or dataset at serving time. Missing input is an error.
+- Do not change `forecast.py`, `anomalies.py`, `get_anomalies`, `query_forecast_summary`, `anomaly_service.py` or the old `forecaster_xgboost` / `anomaly_isolation_forest` modules beyond the tariff constant; Stories 1.2 and 1.3 own them.
+- Do not change the gateway or the frontend.
+- Do not commit the full dataset or any `.joblib` file.
+
+## I/O & Edge-Case Matrix
+
+| Scenario | Input / State | Expected Output / Behavior | Error Handling |
+|----------|--------------|---------------------------|----------------|
+| Metrics | Data and artifacts present | 200; same keys as today; values computed over the last 720 hourly rows | N/A |
+| Time series | `limit=24` | 200; `count` 24; rows ascending by time; every key present; `relative_humidity_pct` and `anomaly_reason` are `null` | N/A |
+| Replay | Clock fixed at a Thursday 14:00 UTC | Last row's timestamp is that hour; its source row is a Thursday 14:00; rows are exactly one hour apart | N/A |
+| Hour rollover | Clock advances one hour | The cached frame is rebuilt and ends at the new hour | N/A |
+| Limit out of range | `limit=0` or `721` | 422 from existing validation | Unchanged |
+| Dataset missing | CSV path does not exist | 503 `{"detail": ..., "code": "ERR_DATA_NOT_FOUND"}` naming the path | No file is created |
+| Artifact missing | A `.joblib` or the metadata file is absent | 503 `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` naming the file | No model is trained or saved |
+| Tariff override | `TARIFF_RATE_VND=2500` | `estimated_waste_cost_vnd` equals waste kWh ├ù 2500 | N/A |
+
+</frozen-after-approval>
+
+## Code Map
+
+- `ai-service/src/api/routers/energy.py` -- the two endpoints; today chains `data_loader` ΓåÆ `energy_forecaster.predict_horizon` ΓåÆ `anomaly_detector.detect_anomalies`. Rewire to the serving frame; keep key names.
+- `ai-service/src/agent/tools/energy_tools.py` -- `query_metrics` (lines 6-30) duplicates the metrics maths; make it call the shared function. Leave the other tools.
+- `ai-service/src/models/train_models.py` -- reuse `load_dataset`, `engineer_features`, `get_default_paths`; in tests reuse `split_time_series_data`, `train_xgboost_forecaster`, `train_isolation_forest`, `save_trained_models`. Artifacts are raw estimators.
+- `ai-service/models_saved/model_metadata.json` -- `xgb_features`, `iso_features`, `xgboost_metrics.rmse_kwh` (held-out RMSE), `isolation_forest_metrics.anomaly_score_min/max`.
+- `ai-service/data/processed/office_building_clean.csv` -- 17,544 hourly rows, columns `timestamp, meter_reading, air_temperature`; gitignored by `*.csv`.
+- `ai-service/src/main.py` -- register the exception handler here.
+- `ai-service/tests/test_smoke.py` -- `test_api_energy_metrics` / `test_api_energy_timeseries` must keep passing; the three old-stack tests above them stay untouched.
+- `.gitignore` line 36 (`*.csv`) -- needs an exception for the test fixture.
+
+## Tasks & Acceptance
+
+**Execution:**
+- [x] `ai-service/src/config.py` -- add helpers reading `TARIFF_RATE_VND`, `TARIFF_RATE_USD`, `ECOTRACK_DATA_PATH`, `ECOTRACK_MODELS_DIR` with defaults from `get_default_paths()` -- one place for settings the env file already documents.
+- [x] `ai-service/src/data_pipeline/serving_frame.py` -- add `ServingDataError`, `ModelArtifactError`, and a lock-guarded cached `get_serving_frame()` returning the last 720 rows with `timestamp`, `meter_reading_kwh`, `outdoor_temperature_c`, `predicted_kwh`, `residual`, `lower_bound_95`, `upper_bound_95`, `anomaly_score`, `is_anomaly`, `severity`; plus `compute_energy_metrics(frame)` and `reset_serving_cache()` -- the single real-data source for this epic.
+- [x] `ai-service/src/api/routers/energy.py` -- build both responses from the serving frame; UTC `Z` timestamps -- FR13.
+- [x] `ai-service/src/agent/tools/energy_tools.py` -- `query_metrics` delegates to `compute_energy_metrics`, keeping its own key names -- Copilot and dashboard agree.
+- [x] `ai-service/src/api/routers/anomalies.py`, `ai-service/src/agent/tools/energy_tools.py`, `ai-service/src/agent/orchestrator.py` -- replace literal `3100` / `0.125` with the config helpers -- tariff AC.
+- [x] `ai-service/src/main.py` -- exception handler mapping the two errors to the 503 envelope.
+- [x] `ai-service/tests/fixtures/office_building_sample.csv`, `.gitignore` -- commit the last 90 days (2,160 rows) of the processed CSV; add `!ai-service/tests/fixtures/*.csv`.
+- [x] `ai-service/tests/conftest.py` -- session fixture that trains both models from the fixture into a temp dir with the `train_models` functions, sets the two `ECOTRACK_*` variables and resets the cache.
+- [x] `ai-service/tests/test_serving_frame.py` -- cover every matrix row, column set, row order, bounds containing the prediction, and that no file appears in the models dir on a missing-artifact error.
+- [x] `ai-service/.env.example` -- document the three new variables.
+
+**Acceptance Criteria:**
+- Given the fixture environment, when `pytest ai-service` runs with `models_saved/*.joblib` and `data/processed/` absent, then the whole suite passes.
+- Given the serving frame, when it is imported and called from a plain Python shell, then it works without FastAPI.
+- Given the frame was built once, when either endpoint is called again, then the dataset and artifacts are not reloaded from disk.
+
+## Implementation Notes
+
+## Spec Change Log
+
+## Review Triage Log
+
+## Design Notes
+
+- **Bounds:** `predicted_kwh ┬▒ 1.96 ├ù rmse_kwh` from the metadata, lower bound floored at 0. This is held-out error, replacing the old in-sample residual.
+- **Anomaly columns:** `is_anomaly` is the Isolation Forest's own verdict (`predict == -1`). `anomaly_score` is `-decision_function` scaled to [0, 1] with the metadata min/max and clipped, so it is stable across requests rather than relative to the batch. `severity` is `Normal` when not anomalous, `Critical` when the reading exceeds the prediction by more than 30%, otherwise `Medium`. Story 1.3 owns the final tiering.
+- **Replay clock:** `get_serving_frame(now=None)` takes an optional clock value so tests can fix it; the cache key is the current UTC hour. The models and the dataset are loaded once and kept; only the window is recomputed on rollover.
+- **Null fields:** the BDG2 file has no humidity and no anomaly labels; the frontend reads neither field, so `null` is served instead of an invented value.
+- **Temporary mix:** until Stories 1.2 and 1.3 land, the forecast and anomaly endpoints still use the old stack.
+
+## Verification
+
+**Commands:**
+- `cd ai-service && python -m pytest -q` -- expected: all tests pass, including `tests/test_serving_frame.py`.
+- `cd ai-service && python -c "from src.data_pipeline.serving_frame import get_serving_frame; f = get_serving_frame(); print(len(f), list(f.columns))"` -- expected: `720` and the ten columns, using the local BDG2 data.
+- `npm run test --prefix backend` -- expected: unchanged, all pass.
diff --git a/_bmad-output/implementation-artifacts/sprint-status.yaml b/_bmad-output/implementation-artifacts/sprint-status.yaml
index 54a4210..fd90102 100644
--- a/_bmad-output/implementation-artifacts/sprint-status.yaml
+++ b/_bmad-output/implementation-artifacts/sprint-status.yaml
@@ -29,14 +29,14 @@
 # - Dev moves story to 'review', then runs code-review (fresh context, different LLM recommended)
 # - Retrospective appends its action items to action_items; the status view surfaces open ones
 generated: 10-08-2026 21:56
-last_updated: 10-08-2026 21:56
+last_updated: 10-08-2026 22:06
 project: EcoTrack
 project_key: NOKEY
 tracking_system: file-system
 story_location: _bmad-output/implementation-artifacts
 development_status:
-  epic-1: backlog
-  1-1-serve-energy-metrics-and-time-series-from-bdg2-data: backlog
+  epic-1: in-progress
+  1-1-serve-energy-metrics-and-time-series-from-bdg2-data: in-progress
   1-2-forecast-the-next-24-hours: backlog
   1-3-detect-anomalies-on-the-unified-pipeline-and-fail-loudly: backlog
   1-4-make-copilot-provider-failures-visible: backlog
diff --git a/ai-service/.env.example b/ai-service/.env.example
index 5c8ab2a..d3c1013 100644
--- a/ai-service/.env.example
+++ b/ai-service/.env.example
@@ -9,5 +9,11 @@ DATABASE_URL=postgresql://ecotrack:ecotrack_secret@localhost:5432/ecotrack
 GEMINI_API_KEY=
 OPENAI_API_KEY=
 
-# Electricity Tariff for waste estimation (VND per kWh)
+# Electricity Tariff for waste estimation
 TARIFF_RATE_VND=3100
+TARIFF_RATE_USD=0.125
+
+# Dataset & Model artifact path overrides (defaults to local data/processed and models_saved)
+# ECOTRACK_DATA_PATH=data/processed/office_building_clean.csv
+# ECOTRACK_MODELS_DIR=models_saved
+
diff --git a/ai-service/src/agent/orchestrator.py b/ai-service/src/agent/orchestrator.py
index a67be1d..2678cda 100644
--- a/ai-service/src/agent/orchestrator.py
+++ b/ai-service/src/agent/orchestrator.py
@@ -2,6 +2,7 @@ import os
 import json
 import time
 from typing import Dict, Any, List, Tuple
+from src.config import get_tariff_rate_usd, get_tariff_rate_vnd
 from src.agent.prompts import SYSTEM_PROMPT
 from src.agent.tools.energy_tools import (
     query_metrics,
@@ -138,7 +139,7 @@ class CopilotOrchestrator:
 #### ≡ƒöÄ Ph├ón t├¡ch nguy├¬n nh├ón gß╗æc rß╗à (RCA)
 1. **Lß╗çch pha chu kß╗│**: Sß╗▒ cß╗æ xß║úy ra ngo├ái giß╗¥ vß║¡n h├ánh ch├¡nh (Building unoccupied), nh╞░ng phß╗Ñ tß║úi chiller v├á quß║ít th├┤ng gi├│ vß║½n duy tr├¼ ß╗ƒ c├┤ng suß║Ñt t╞░╞íng ─æ╞░╞íng giß╗¥ cao ─æiß╗âm.
 2. **Nguy├¬n nh├ón tiß╗üm ß║⌐n**: {top_anom['reason']}.
-3. **Tß╗òn thß║Ñt chi ph├¡**: ╞»ß╗¢c t├¡nh g├óy l├úng ph├¡ khoß║úng **{top_anom['delta_kwh'] * 3100:,.0f} VN─É** (~${top_anom['delta_kwh'] * 0.125:.2f} USD) cho mß╗ùi giß╗¥ duy tr├¼ sß╗▒ cß╗æ.
+3. **Tß╗òn thß║Ñt chi ph├¡**: ╞»ß╗¢c t├¡nh g├óy l├úng ph├¡ khoß║úng **{top_anom['delta_kwh'] * get_tariff_rate_vnd():,.0f} VN─É** (~${top_anom['delta_kwh'] * get_tariff_rate_usd():.2f} USD) cho mß╗ùi giß╗¥ duy tr├¼ sß╗▒ cß╗æ.
 
 #### ≡ƒÆí Khuyß║┐n nghß╗ï cho Kß╗╣ s╞░ vß║¡n h├ánh
 - [ ] Kiß╗âm tra actuator v├á van damper gi├│ t╞░╞íi tß║íi buß╗ông AHU tß║ºng kß╗╣ thuß║¡t.
diff --git a/ai-service/src/agent/tools/energy_tools.py b/ai-service/src/agent/tools/energy_tools.py
index 2652358..b2d1da4 100644
--- a/ai-service/src/agent/tools/energy_tools.py
+++ b/ai-service/src/agent/tools/energy_tools.py
@@ -1,43 +1,37 @@
-from typing import Dict, Any, List
+from typing import Any, Dict, List
+
+from src.config import get_tariff_rate_usd, get_tariff_rate_vnd
 from src.data_pipeline.bdg2_loader import data_loader
-from src.models.forecaster_xgboost import energy_forecaster
+from src.data_pipeline.serving_frame import compute_energy_metrics, get_serving_frame
 from src.models.anomaly_isolation_forest import anomaly_detector
+from src.models.forecaster_xgboost import energy_forecaster
+
 
 def query_metrics() -> Dict[str, Any]:
     """Truy vß║Ñn c├íc chß╗ë sß╗æ ─æiß╗çn n─âng tß╗òng quan cß╗ºa t├▓a nh├á."""
-    df = data_loader.get_or_create_data()
-    df_fc = energy_forecaster.predict_horizon(df)
-    df_anom = anomaly_detector.detect_anomalies(df_fc)
-    
-    total_kwh = float(df_anom["meter_reading_kwh"].sum())
-    peak_kw = float(df_anom["meter_reading_kwh"].max())
-    baseline_kwh = float(df_anom["predicted_kwh"].sum())
-    anom_count = int(df_anom["is_anomaly"].sum())
-    
-    waste_kwh = float(df_anom[df_anom["is_anomaly"]]["residual"].clip(lower=0).sum())
-    waste_vnd = waste_kwh * 3100
-    waste_usd = waste_kwh * 0.125
-    
+    frame = get_serving_frame()
+    metrics = compute_energy_metrics(frame)
     return {
-        "building_id": "office_tower_01",
-        "total_consumption_kwh": round(total_kwh, 1),
-        "peak_demand_kw": round(peak_kw, 1),
-        "baseline_kwh": round(baseline_kwh, 1),
-        "anomalies_detected": anom_count,
-        "estimated_waste_kwh": round(waste_kwh, 1),
-        "estimated_waste_vnd": round(waste_vnd, 0),
-        "estimated_waste_usd": round(waste_usd, 2)
+        "building_id": metrics["building_id"],
+        "total_consumption_kwh": metrics["total_consumption_kwh"],
+        "peak_demand_kw": metrics["peak_demand_kw"],
+        "baseline_kwh": metrics["predicted_baseline_kwh"],
+        "anomalies_detected": metrics["total_anomalies_detected"],
+        "estimated_waste_kwh": metrics["estimated_waste_kwh"],
+        "estimated_waste_vnd": metrics["estimated_waste_cost_vnd"],
+        "estimated_waste_usd": metrics["estimated_waste_cost_usd"],
     }
 
+
 def get_anomalies(limit: int = 5) -> List[Dict[str, Any]]:
     """Truy vß║Ñn danh s├ích c├íc ─æiß╗âm v├á sß╗▒ kiß╗çn bß║Ñt th╞░ß╗¥ng gß║ºn nhß║Ñt."""
     df = data_loader.get_or_create_data()
     df_fc = energy_forecaster.predict_horizon(df)
     df_anom = anomaly_detector.detect_anomalies(df_fc)
-    
+
     anom_rows = df_anom[df_anom["is_anomaly"]].tail(limit)
     events = []
-    
+
     for idx, row in anom_rows.iterrows():
         events.append({
             "id": f"ANOM-{idx}",
@@ -48,32 +42,34 @@ def get_anomalies(limit: int = 5) -> List[Dict[str, Any]]:
             "predicted_kwh": float(row["predicted_kwh"]),
             "delta_kwh": round(float(row["residual"]), 1),
             "outdoor_temp_c": float(row["outdoor_temperature_c"]),
-            "reason": row["anomaly_reason"] or "─Éß╗Ö lß╗çch phß╗Ñ tß║úi bß║Ñt th╞░ß╗¥ng kh├┤ng giß║úi th├¡ch bß║▒ng nhiß╗çt ─æß╗Ö"
+            "reason": row["anomaly_reason"] or "─Éß╗Ö lß╗çch phß╗Ñ tß║úi bß║Ñt th╞░ß╗¥ng kh├┤ng giß║úi th├¡ch bß║▒ng nhiß╗çt ─æß╗Ö",
         })
     return events
 
+
 def query_forecast_summary() -> Dict[str, Any]:
     """Truy vß║Ñn th├┤ng tin t├│m tß║»t dß╗▒ b├ío phß╗Ñ tß║úi ─æiß╗çn 24 giß╗¥ tß╗¢i."""
     df = data_loader.get_or_create_data()
     df_fc = energy_forecaster.predict_horizon(df)
     last_24h = df_fc.tail(24)
-    
+
     max_row = last_24h.loc[last_24h["predicted_kwh"].idxmax()]
     return {
         "forecast_horizon": "24 hours",
         "expected_peak_kw": float(max_row["predicted_kwh"]),
         "peak_timestamp": max_row["timestamp"],
         "average_forecast_kwh": round(float(last_24h["predicted_kwh"].mean()), 1),
-        "confidence_interval_95": "┬▒16.7 kW"
+        "confidence_interval_95": "┬▒16.7 kW",
     }
 
+
 def calculate_waste_cost(delta_kwh: float, duration_hours: float = 1.0) -> Dict[str, Any]:
     """T├¡nh to├ín chi ph├¡ l├úng ph├¡ ─æiß╗çn n─âng dß╗▒a tr├¬n kWh ch├¬nh lß╗çch."""
     total_waste_kwh = delta_kwh * duration_hours
-    vnd = total_waste_kwh * 3100
-    usd = total_waste_kwh * 0.125
+    vnd = total_waste_kwh * get_tariff_rate_vnd()
+    usd = total_waste_kwh * get_tariff_rate_usd()
     return {
         "excess_kwh": round(total_waste_kwh, 1),
         "cost_vnd": round(vnd, 0),
-        "cost_usd": round(usd, 2)
+        "cost_usd": round(usd, 2),
     }
diff --git a/ai-service/src/api/routers/anomalies.py b/ai-service/src/api/routers/anomalies.py
index b069e07..44b49b4 100644
--- a/ai-service/src/api/routers/anomalies.py
+++ b/ai-service/src/api/routers/anomalies.py
@@ -2,6 +2,7 @@ import asyncio
 from typing import Any, Dict, List
 from fastapi import APIRouter
 
+from src.config import get_tariff_rate_usd, get_tariff_rate_vnd
 from src.data_pipeline.bdg2_loader import data_loader
 from src.models.forecaster_xgboost import energy_forecaster
 from src.models.anomaly_isolation_forest import anomaly_detector
@@ -19,8 +20,8 @@ def _detect_anomalies_pure() -> List[Dict[str, Any]]:
 
     for idx, row in anom_rows.iterrows():
         delta = max(0.0, float(row["meter_reading_kwh"]) - float(row["predicted_kwh"]))
-        cost_vnd = delta * 3100
-        cost_usd = delta * 0.125
+        cost_vnd = delta * get_tariff_rate_vnd()
+        cost_usd = delta * get_tariff_rate_usd()
         events.append({
             "id": f"ANOM-{idx}",
             "building_id": "office_tower_01",
diff --git a/ai-service/src/api/routers/energy.py b/ai-service/src/api/routers/energy.py
index 2753361..8d5ec8d 100644
--- a/ai-service/src/api/routers/energy.py
+++ b/ai-service/src/api/routers/energy.py
@@ -1,60 +1,45 @@
 import asyncio
-from typing import Any, Dict, List
+from typing import Any, Dict
 from fastapi import APIRouter, Query
 
-from src.data_pipeline.bdg2_loader import data_loader
-from src.models.forecaster_xgboost import energy_forecaster
-from src.models.anomaly_isolation_forest import anomaly_detector
+from src.data_pipeline.serving_frame import compute_energy_metrics, get_serving_frame
 
 router = APIRouter(prefix="/internal/energy", tags=["Energy Telemetry"])
 
 
 def _compute_energy_metrics() -> Dict[str, Any]:
-    df = data_loader.get_or_create_data()
-    df_fc = energy_forecaster.predict_horizon(df)
-    df_anom = anomaly_detector.detect_anomalies(df_fc)
-
-    total_kwh = float(df_anom["meter_reading_kwh"].sum())
-    peak_kw = float(df_anom["meter_reading_kwh"].max())
-    baseline_kwh = float(df_anom["predicted_kwh"].sum())
-    anom_count = int(df_anom["is_anomaly"].sum())
-
-    waste_kwh = float(df_anom[df_anom["is_anomaly"]]["residual"].clip(lower=0).sum())
-    waste_vnd = waste_kwh * 3100
-    waste_usd = waste_kwh * 0.125
-
+    frame = get_serving_frame()
+    metrics = compute_energy_metrics(frame)
     return {
-        "building_id": "office_tower_01",
-        "total_consumption_kwh": round(total_kwh, 1),
-        "peak_demand_kw": round(peak_kw, 1),
-        "predicted_baseline_kwh": round(baseline_kwh, 1),
-        "total_anomalies_detected": anom_count,
-        "estimated_waste_cost_vnd": round(waste_vnd, 0),
-        "estimated_waste_cost_usd": round(waste_usd, 2),
+        "building_id": metrics["building_id"],
+        "total_consumption_kwh": metrics["total_consumption_kwh"],
+        "peak_demand_kw": metrics["peak_demand_kw"],
+        "predicted_baseline_kwh": metrics["predicted_baseline_kwh"],
+        "total_anomalies_detected": metrics["total_anomalies_detected"],
+        "estimated_waste_cost_vnd": metrics["estimated_waste_cost_vnd"],
+        "estimated_waste_cost_usd": metrics["estimated_waste_cost_usd"],
     }
 
 
 def _get_timeseries(limit: int) -> Dict[str, Any]:
-    df = data_loader.get_or_create_data()
-    df_fc = energy_forecaster.predict_horizon(df)
-    df_anom = anomaly_detector.detect_anomalies(df_fc)
-
-    df_slice = df_anom.tail(limit)
-    points = []
-    for _, row in df_slice.iterrows():
-        points.append({
+    frame = get_serving_frame()
+    df_slice = frame.tail(limit)
+    points = [
+        {
             "timestamp": str(row["timestamp"]),
             "meter_reading_kwh": float(row["meter_reading_kwh"]),
             "predicted_kwh": float(row["predicted_kwh"]),
             "lower_bound_95": float(row["lower_bound_95"]),
             "upper_bound_95": float(row["upper_bound_95"]),
             "outdoor_temperature_c": float(row["outdoor_temperature_c"]),
-            "relative_humidity_pct": float(row.get("relative_humidity_pct", 65.0)),
+            "relative_humidity_pct": None,
             "is_anomaly": bool(row["is_anomaly"]),
             "anomaly_score": float(row["anomaly_score"]),
             "severity": str(row["severity"]),
-            "anomaly_reason": row.get("anomaly_reason") if bool(row["is_anomaly"]) else None,
-        })
+            "anomaly_reason": None,
+        }
+        for _, row in df_slice.iterrows()
+    ]
     return {
         "building_id": "office_tower_01",
         "count": len(points),
diff --git a/ai-service/src/config.py b/ai-service/src/config.py
new file mode 100644
index 0000000..cca143c
--- /dev/null
+++ b/ai-service/src/config.py
@@ -0,0 +1,19 @@
+import os
+from pathlib import Path
+from src.models.train_models import get_default_paths
+
+# ponytail: simple env readers, no pydantic BaseSettings class
+
+def get_tariff_rate_vnd() -> float:
+    return float(os.getenv("TARIFF_RATE_VND", "3100"))
+
+def get_tariff_rate_usd() -> float:
+    return float(os.getenv("TARIFF_RATE_USD", "0.125"))
+
+def get_data_path() -> Path:
+    val = os.getenv("ECOTRACK_DATA_PATH")
+    return Path(val) if val else get_default_paths()[0]
+
+def get_models_dir() -> Path:
+    val = os.getenv("ECOTRACK_MODELS_DIR")
+    return Path(val) if val else get_default_paths()[1]
diff --git a/ai-service/src/data_pipeline/serving_frame.py b/ai-service/src/data_pipeline/serving_frame.py
new file mode 100644
index 0000000..b3a6878
--- /dev/null
+++ b/ai-service/src/data_pipeline/serving_frame.py
@@ -0,0 +1,194 @@
+import json
+import threading
+from datetime import datetime, timezone
+from pathlib import Path
+from typing import Any, Dict, Optional, Tuple
+
+import joblib
+import numpy as np
+import pandas as pd
+
+from src.config import get_data_path, get_models_dir, get_tariff_rate_usd, get_tariff_rate_vnd
+from src.models.train_models import engineer_features, load_dataset
+
+
+class ServingDataError(Exception):
+    """Raised when the input dataset cannot be found or read."""
+    def __init__(self, message: str, path: str = ""):
+        super().__init__(message)
+        self.path = path
+
+
+class ModelArtifactError(Exception):
+    """Raised when a trained model artifact is missing or invalid."""
+    def __init__(self, message: str, file_path: str = ""):
+        super().__init__(message)
+        self.file_path = file_path
+
+
+_lock = threading.Lock()
+_cached_base_df: Optional[pd.DataFrame] = None
+_cached_meta: Optional[Dict[str, Any]] = None
+_cached_hour_key: Optional[datetime] = None
+_cached_serving_frame: Optional[pd.DataFrame] = None
+
+
+def reset_serving_cache() -> None:
+    """Clears all in-memory cached frames and model artifacts."""
+    global _cached_base_df, _cached_meta, _cached_hour_key, _cached_serving_frame
+    with _lock:
+        _cached_base_df = None
+        _cached_meta = None
+        _cached_hour_key = None
+        _cached_serving_frame = None
+
+
+def _load_artifacts_and_base_frame(data_path: Path, models_dir: Path) -> Tuple[pd.DataFrame, Dict[str, Any]]:
+    if not data_path.exists():
+        raise ServingDataError(f"Processed dataset not found at: {data_path}", path=str(data_path))
+
+    xgb_path = models_dir / "xgboost_forecaster.joblib"
+    iso_path = models_dir / "isolation_forest.joblib"
+    meta_path = models_dir / "model_metadata.json"
+
+    for required_file in (xgb_path, iso_path, meta_path):
+        if not required_file.exists():
+            raise ModelArtifactError(f"Model artifact not found: {required_file}", file_path=str(required_file))
+
+    try:
+        with open(meta_path, "r", encoding="utf-8") as f:
+            metadata = json.load(f)
+        xgb_model = joblib.load(xgb_path)
+        iso_model = joblib.load(iso_path)
+    except Exception as e:
+        if isinstance(e, (ServingDataError, ModelArtifactError)):
+            raise
+        raise ModelArtifactError(f"Failed to load model artifact: {e}", file_path=str(models_dir))
+
+    raw_df = load_dataset(data_path)
+    df_feat = engineer_features(raw_df)
+
+    xgb_cols = metadata["xgb_features"]
+    iso_cols = metadata["iso_features"]
+
+    predicted = xgb_model.predict(df_feat[xgb_cols])
+    actual = df_feat["meter_reading"].values
+    residual = actual - predicted
+
+    rmse = float(metadata["xgboost_metrics"]["rmse_kwh"])
+    lower_bound = np.maximum(0.0, predicted - 1.96 * rmse)
+    upper_bound = predicted + 1.96 * rmse
+
+    raw_decisions = iso_model.decision_function(df_feat[iso_cols])
+    preds = iso_model.predict(df_feat[iso_cols])
+    is_anom = (preds == -1)
+
+    raw_scores = -raw_decisions
+    min_score = float(metadata["isolation_forest_metrics"]["anomaly_score_min"])
+    max_score = float(metadata["isolation_forest_metrics"]["anomaly_score_max"])
+    if max_score > min_score:
+        scaled_scores = (raw_scores - min_score) / (max_score - min_score)
+    else:
+        scaled_scores = np.zeros_like(raw_scores)
+    anom_scores = np.clip(scaled_scores, 0.0, 1.0)
+
+    critical_mask = is_anom & (actual > 1.30 * predicted)
+    severity = np.where(~is_anom, "Normal", np.where(critical_mask, "Critical", "Medium"))
+
+    base_df = pd.DataFrame({
+        "timestamp": df_feat["timestamp"],
+        "meter_reading_kwh": actual.astype(float),
+        "outdoor_temperature_c": df_feat["air_temperature"].values.astype(float),
+        "predicted_kwh": predicted.astype(float),
+        "residual": residual.astype(float),
+        "lower_bound_95": lower_bound.astype(float),
+        "upper_bound_95": upper_bound.astype(float),
+        "anomaly_score": anom_scores.astype(float),
+        "is_anomaly": is_anom.astype(bool),
+        "severity": severity,
+    })
+
+    return base_df, metadata
+
+
+def get_serving_frame(now: Optional[datetime] = None) -> pd.DataFrame:
+    """
+    Returns the 720-hour serving window ending at the current UTC hour,
+    replayed from the latest matching weekday/hour in the dataset.
+    """
+    global _cached_base_df, _cached_meta, _cached_hour_key, _cached_serving_frame
+
+    if now is None:
+        now = datetime.now(timezone.utc)
+    elif now.tzinfo is None:
+        now = now.replace(tzinfo=timezone.utc)
+    else:
+        now = now.astimezone(timezone.utc)
+
+    now_hour = now.replace(minute=0, second=0, microsecond=0)
+
+    with _lock:
+        if _cached_base_df is None:
+            data_path = get_data_path()
+            models_dir = get_models_dir()
+            _cached_base_df, _cached_meta = _load_artifacts_and_base_frame(data_path, models_dir)
+
+        if _cached_hour_key == now_hour and _cached_serving_frame is not None:
+            return _cached_serving_frame
+
+        target_weekday = now_hour.weekday()
+        target_hour = now_hour.hour
+
+        ts = _cached_base_df["timestamp"]
+        matches = _cached_base_df[(ts.dt.weekday == target_weekday) & (ts.dt.hour == target_hour)]
+        if matches.empty:
+            raise ServingDataError(
+                f"No matching row found for weekday {target_weekday} and hour {target_hour}",
+                path=str(get_data_path()),
+            )
+
+        valid_matches = matches[matches.index >= 719]
+        if not valid_matches.empty:
+            end_idx = valid_matches.index[-1]
+        else:
+            end_idx = matches.index[-1]
+
+        start_idx = max(0, end_idx - 720 + 1)
+        slice_df = _cached_base_df.iloc[start_idx : end_idx + 1].copy()
+
+        src_end_ts = slice_df["timestamp"].iloc[-1]
+        delta = now_hour.replace(tzinfo=None) - src_end_ts
+        shifted_ts = slice_df["timestamp"] + delta
+
+        slice_df["timestamp"] = shifted_ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
+        slice_df = slice_df.reset_index(drop=True)
+
+        _cached_hour_key = now_hour
+        _cached_serving_frame = slice_df
+        return slice_df
+
+
+def compute_energy_metrics(frame: pd.DataFrame) -> Dict[str, Any]:
+    """Computes aggregated 720-hour energy metrics using configured tariffs."""
+    tariff_vnd = get_tariff_rate_vnd()
+    tariff_usd = get_tariff_rate_usd()
+
+    total_kwh = float(frame["meter_reading_kwh"].sum())
+    peak_kw = float(frame["meter_reading_kwh"].max())
+    baseline_kwh = float(frame["predicted_kwh"].sum())
+    anom_count = int(frame["is_anomaly"].sum())
+
+    waste_kwh = float(frame[frame["is_anomaly"]]["residual"].clip(lower=0).sum())
+    waste_vnd = waste_kwh * tariff_vnd
+    waste_usd = waste_kwh * tariff_usd
+
+    return {
+        "building_id": "office_tower_01",
+        "total_consumption_kwh": round(total_kwh, 1),
+        "peak_demand_kw": round(peak_kw, 1),
+        "predicted_baseline_kwh": round(baseline_kwh, 1),
+        "total_anomalies_detected": anom_count,
+        "estimated_waste_kwh": round(waste_kwh, 1),
+        "estimated_waste_cost_vnd": round(waste_vnd, 0),
+        "estimated_waste_cost_usd": round(waste_usd, 2),
+    }
diff --git a/ai-service/src/main.py b/ai-service/src/main.py
index 7d57c6a..10171f5 100644
--- a/ai-service/src/main.py
+++ b/ai-service/src/main.py
@@ -3,8 +3,11 @@ import sys
 from pathlib import Path
 from fastapi import FastAPI
 from fastapi.middleware.cors import CORSMiddleware
+from fastapi.responses import JSONResponse
 from dotenv import load_dotenv
 
+from src.data_pipeline.serving_frame import ModelArtifactError, ServingDataError
+
 # Ensure ai-service root is in sys.path so `src...` imports work from any working directory
 AI_SERVICE_DIR = Path(__file__).resolve().parent.parent
 if str(AI_SERVICE_DIR) not in sys.path:
@@ -35,6 +38,22 @@ app.include_router(forecast.router)
 app.include_router(anomalies.router)
 app.include_router(copilot.router)
 
+
+@app.exception_handler(ServingDataError)
+async def serving_data_error_handler(request, exc: ServingDataError):
+    return JSONResponse(
+        status_code=503,
+        content={"detail": str(exc), "code": "ERR_DATA_NOT_FOUND"},
+    )
+
+
+@app.exception_handler(ModelArtifactError)
+async def model_artifact_error_handler(request, exc: ModelArtifactError):
+    return JSONResponse(
+        status_code=503,
+        content={"detail": str(exc), "code": "ERR_MODEL_NOT_FOUND"},
+    )
+
 @app.get("/")
 def root():
     return {
diff --git a/ai-service/tests/conftest.py b/ai-service/tests/conftest.py
new file mode 100644
index 0000000..0848bc3
--- /dev/null
+++ b/ai-service/tests/conftest.py
@@ -0,0 +1,78 @@
+import os
+import shutil
+import tempfile
+from pathlib import Path
+import pytest
+
+from src.data_pipeline.serving_frame import reset_serving_cache
+from src.models.train_models import (
+    ISO_FEATURE_COLUMNS,
+    XGB_FEATURE_COLUMNS,
+    engineer_features,
+    load_dataset,
+    save_trained_models,
+    split_time_series_data,
+    train_isolation_forest,
+    train_xgboost_forecaster,
+)
+
+
+@pytest.fixture(scope="session", autouse=True)
+def setup_test_environment():
+    """
+    Session fixture that trains both models from the fixture sample into a temp dir,
+    sets ECOTRACK_DATA_PATH and ECOTRACK_MODELS_DIR, and resets serving cache.
+    """
+    fixture_csv = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
+    temp_dir = tempfile.mkdtemp(prefix="ecotrack_test_models_")
+    temp_models_dir = Path(temp_dir)
+
+    raw_df = load_dataset(fixture_csv)
+    df_feat = engineer_features(raw_df)
+    train_df, test_df = split_time_series_data(df_feat, train_ratio=0.8)
+
+    xgb_model, xgb_metrics, _ = train_xgboost_forecaster(train_df, test_df)
+    iso_model, iso_metrics, _, _ = train_isolation_forest(train_df, test_df, contamination=0.03)
+
+    metadata = {
+        "dataset_rows": len(df_feat),
+        "train_rows": len(train_df),
+        "test_rows": len(test_df),
+        "xgb_features": XGB_FEATURE_COLUMNS,
+        "iso_features": ISO_FEATURE_COLUMNS,
+        "xgboost_metrics": xgb_metrics,
+        "isolation_forest_metrics": iso_metrics,
+    }
+
+    save_trained_models(
+        xgb_model=xgb_model,
+        iso_model=iso_model,
+        output_dir=temp_models_dir,
+        metadata=metadata,
+    )
+
+    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
+    old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
+
+    os.environ["ECOTRACK_DATA_PATH"] = str(fixture_csv)
+    os.environ["ECOTRACK_MODELS_DIR"] = str(temp_models_dir)
+    reset_serving_cache()
+
+    yield {
+        "data_path": fixture_csv,
+        "models_dir": temp_models_dir,
+        "metadata": metadata,
+    }
+
+    reset_serving_cache()
+    if old_data_path is not None:
+        os.environ["ECOTRACK_DATA_PATH"] = old_data_path
+    else:
+        os.environ.pop("ECOTRACK_DATA_PATH", None)
+
+    if old_models_dir is not None:
+        os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
+    else:
+        os.environ.pop("ECOTRACK_MODELS_DIR", None)
+
+    shutil.rmtree(temp_dir, ignore_errors=True)
diff --git a/ai-service/tests/fixtures/office_building_sample.csv b/ai-service/tests/fixtures/office_building_sample.csv
new file mode 100644
index 0000000..32deabf
--- /dev/null
+++ b/ai-service/tests/fixtures/office_building_sample.csv
@@ -0,0 +1,2161 @@
+timestamp,meter_reading,air_temperature
+2017-10-03 00:00:00,110.97,18.3
+2017-10-03 01:00:00,98.97,18.3
+2017-10-03 02:00:00,99.97,18.3
+2017-10-03 03:00:00,99.97,19.4
+2017-10-03 04:00:00,98.97,21.7
+2017-10-03 05:00:00,106.97,17.8
+2017-10-03 06:00:00,145.97,17.2
+2017-10-03 07:00:00,150.97,17.2
+2017-10-03 08:00:00,180.97,17.2
+2017-10-03 09:00:00,192.97,18.3
+2017-10-03 10:00:00,214.97,20.0
+2017-10-03 11:00:00,216.97,20.6
+2017-10-03 12:00:00,211.97,20.6
+2017-10-03 13:00:00,208.97,18.9
+2017-10-03 14:00:00,225.97,16.7
+2017-10-03 15:00:00,233.97,16.7
+2017-10-03 16:00:00,235.97,17.8
+2017-10-03 17:00:00,230.97,17.2
+2017-10-03 18:00:00,202.97,15.6
+2017-10-03 19:00:00,177.97,15.0
+2017-10-03 20:00:00,177.97,13.3
+2017-10-03 21:00:00,169.97,12.8
+2017-10-03 22:00:00,158.97,11.7
+2017-10-03 23:00:00,129.97,11.1
+2017-10-04 00:00:00,109.97,11.1
+2017-10-04 01:00:00,99.97,10.6
+2017-10-04 02:00:00,99.97,10.0
+2017-10-04 03:00:00,98.97,9.4
+2017-10-04 04:00:00,99.97,9.4
+2017-10-04 05:00:00,107.97,8.9
+2017-10-04 06:00:00,143.97,8.3
+2017-10-04 07:00:00,150.97,8.3
+2017-10-04 08:00:00,170.97,9.4
+2017-10-04 09:00:00,185.97,10.6
+2017-10-04 10:00:00,190.97,11.7
+2017-10-04 11:00:00,228.97,13.3
+2017-10-04 12:00:00,235.97,13.9
+2017-10-04 13:00:00,237.97,14.4
+2017-10-04 14:00:00,238.97,14.4
+2017-10-04 15:00:00,239.97,15.0
+2017-10-04 16:00:00,217.97,15.6
+2017-10-04 17:00:00,208.97,14.4
+2017-10-04 18:00:00,186.97,13.3
+2017-10-04 19:00:00,186.97,12.2
+2017-10-04 20:00:00,181.97,11.7
+2017-10-04 21:00:00,174.97,11.7
+2017-10-04 22:00:00,149.97,10.6
+2017-10-04 23:00:00,115.97,10.6
+2017-10-05 00:00:00,106.97,10.0
+2017-10-05 01:00:00,98.97,9.4
+2017-10-05 02:00:00,98.97,9.4
+2017-10-05 03:00:00,97.97,9.4
+2017-10-05 04:00:00,100.97,10.0
+2017-10-05 05:00:00,105.97,11.1
+2017-10-05 06:00:00,142.97,11.1
+2017-10-05 07:00:00,150.97,11.7
+2017-10-05 08:00:00,176.97,12.8
+2017-10-05 09:00:00,188.97,12.8
+2017-10-05 10:00:00,217.97,14.4
+2017-10-05 11:00:00,224.97,16.1
+2017-10-05 12:00:00,215.97,16.7
+2017-10-05 13:00:00,219.97,17.8
+2017-10-05 14:00:00,224.97,17.2
+2017-10-05 15:00:00,224.97,17.2
+2017-10-05 16:00:00,216.97,16.7
+2017-10-05 17:00:00,213.97,16.7
+2017-10-05 18:00:00,196.97,15.6
+2017-10-05 19:00:00,188.97,15.6
+2017-10-05 20:00:00,188.97,14.4
+2017-10-05 21:00:00,186.97,13.3
+2017-10-05 22:00:00,167.97,13.3
+2017-10-05 23:00:00,140.97,12.8
+2017-10-06 00:00:00,108.97,12.8
+2017-10-06 01:00:00,99.97,11.7
+2017-10-06 02:00:00,99.97,10.0
+2017-10-06 03:00:00,99.97,10.0
+2017-10-06 04:00:00,99.97,10.0
+2017-10-06 05:00:00,107.97,9.4
+2017-10-06 06:00:00,141.97,9.4
+2017-10-06 07:00:00,150.97,10.6
+2017-10-06 08:00:00,175.97,11.7
+2017-10-06 09:00:00,188.97,13.9
+2017-10-06 10:00:00,228.97,15.0
+2017-10-06 11:00:00,237.97,15.0
+2017-10-06 12:00:00,241.97,15.6
+2017-10-06 13:00:00,247.97,15.6
+2017-10-06 14:00:00,237.97,14.4
+2017-10-06 15:00:00,235.97,13.9
+2017-10-06 16:00:00,264.97,13.3
+2017-10-06 17:00:00,289.97,13.9
+2017-10-06 18:00:00,287.97,13.3
+2017-10-06 19:00:00,284.97,13.3
+2017-10-06 20:00:00,282.97,13.3
+2017-10-06 21:00:00,248.97,13.3
+2017-10-06 22:00:00,236.97,13.3
+2017-10-06 23:00:00,238.97,13.3
+2017-10-07 00:00:00,198.97,13.3
+2017-10-07 01:00:00,135.97,13.3
+2017-10-07 02:00:00,134.97,13.3
+2017-10-07 03:00:00,133.97,13.3
+2017-10-07 04:00:00,133.97,12.8
+2017-10-07 05:00:00,175.97,12.2
+2017-10-07 06:00:00,197.97,12.2
+2017-10-07 07:00:00,229.97,12.2
+2017-10-07 08:00:00,249.97,12.2
+2017-10-07 09:00:00,256.97,12.8
+2017-10-07 10:00:00,243.97,13.3
+2017-10-07 11:00:00,225.97,13.3
+2017-10-07 12:00:00,204.97,15.0
+2017-10-07 13:00:00,184.97,15.0
+2017-10-07 14:00:00,172.97,16.1
+2017-10-07 15:00:00,173.97,17.8
+2017-10-07 16:00:00,170.97,19.4
+2017-10-07 17:00:00,169.97,18.9
+2017-10-07 18:00:00,170.97,17.2
+2017-10-07 19:00:00,155.97,17.2
+2017-10-07 20:00:00,134.97,15.6
+2017-10-07 21:00:00,132.97,15.6
+2017-10-07 22:00:00,115.97,15.0
+2017-10-07 23:00:00,100.97,13.9
+2017-10-08 00:00:00,97.97,12.8
+2017-10-08 01:00:00,96.97,12.2
+2017-10-08 02:00:00,97.97,12.2
+2017-10-08 03:00:00,96.97,11.7
+2017-10-08 04:00:00,98.97,10.6
+2017-10-08 05:00:00,105.97,10.0
+2017-10-08 06:00:00,106.97,10.0
+2017-10-08 07:00:00,109.97,11.1
+2017-10-08 08:00:00,105.97,12.8
+2017-10-08 09:00:00,196.97,15.6
+2017-10-08 10:00:00,225.97,17.8
+2017-10-08 11:00:00,239.97,20.0
+2017-10-08 12:00:00,246.97,21.7
+2017-10-08 13:00:00,244.97,22.2
+2017-10-08 14:00:00,245.97,21.1
+2017-10-08 15:00:00,246.97,21.1
+2017-10-08 16:00:00,246.97,20.6
+2017-10-08 17:00:00,243.97,19.4
+2017-10-08 18:00:00,238.97,17.2
+2017-10-08 19:00:00,217.97,15.6
+2017-10-08 20:00:00,195.97,14.4
+2017-10-08 21:00:00,137.97,13.3
+2017-10-08 22:00:00,117.97,13.3
+2017-10-08 23:00:00,115.97,12.8
+2017-10-09 00:00:00,117.97,11.7
+2017-10-09 01:00:00,116.97,11.1
+2017-10-09 02:00:00,115.97,10.0
+2017-10-09 03:00:00,116.97,8.9
+2017-10-09 04:00:00,115.97,9.4
+2017-10-09 05:00:00,124.97,8.3
+2017-10-09 06:00:00,161.97,7.8
+2017-10-09 07:00:00,206.97,9.4
+2017-10-09 08:00:00,246.97,10.6
+2017-10-09 09:00:00,266.97,12.2
+2017-10-09 10:00:00,280.97,13.9
+2017-10-09 11:00:00,273.97,12.8
+2017-10-09 12:00:00,274.97,12.2
+2017-10-09 13:00:00,227.97,12.8
+2017-10-09 14:00:00,240.97,11.1
+2017-10-09 15:00:00,232.97,10.0
+2017-10-09 16:00:00,214.97,9.4
+2017-10-09 17:00:00,213.97,8.9
+2017-10-09 18:00:00,203.97,8.9
+2017-10-09 19:00:00,208.97,8.9
+2017-10-09 20:00:00,198.97,8.3
+2017-10-09 21:00:00,198.97,6.7
+2017-10-09 22:00:00,182.97,6.1
+2017-10-09 23:00:00,162.97,5.6
+2017-10-10 00:00:00,106.97,4.4
+2017-10-10 01:00:00,105.97,3.9
+2017-10-10 02:00:00,106.97,3.9
+2017-10-10 03:00:00,110.97,2.8
+2017-10-10 04:00:00,114.97,2.8
+2017-10-10 05:00:00,122.97,1.7
+2017-10-10 06:00:00,160.97,1.7
+2017-10-10 07:00:00,198.97,2.2
+2017-10-10 08:00:00,224.97,4.4
+2017-10-10 09:00:00,229.97,6.1
+2017-10-10 10:00:00,231.97,8.9
+2017-10-10 11:00:00,221.97,8.9
+2017-10-10 12:00:00,235.97,10.0
+2017-10-10 13:00:00,233.97,10.0
+2017-10-10 14:00:00,245.97,10.6
+2017-10-10 15:00:00,267.03,10.6
+2017-10-10 16:00:00,235.85,10.0
+2017-10-10 17:00:00,279.6,10.0
+2017-10-10 18:00:00,291.8,9.4
+2017-10-10 19:00:00,292.35,9.4
+2017-10-10 20:00:00,291.54,8.9
+2017-10-10 21:00:00,274.38,7.8
+2017-10-10 22:00:00,234.39,7.2
+2017-10-10 23:00:00,148.03,6.7
+2017-10-11 00:00:00,141.55,5.6
+2017-10-11 01:00:00,138.63,5.0
+2017-10-11 02:00:00,137.47,3.9
+2017-10-11 03:00:00,139.94,3.9
+2017-10-11 04:00:00,151.47,4.4
+2017-10-11 05:00:00,168.1,4.4
+2017-10-11 06:00:00,170.51,3.9
+2017-10-11 07:00:00,188.18,5.6
+2017-10-11 08:00:00,253.57,7.2
+2017-10-11 09:00:00,279.55,8.3
+2017-10-11 10:00:00,289.07,9.4
+2017-10-11 11:00:00,293.58,10.0
+2017-10-11 12:00:00,274.06,11.1
+2017-10-11 13:00:00,237.53,11.7
+2017-10-11 14:00:00,230.92,12.2
+2017-10-11 15:00:00,226.91,12.2
+2017-10-11 16:00:00,222.57,12.8
+2017-10-11 17:00:00,226.42,12.2
+2017-10-11 18:00:00,219.1,11.1
+2017-10-11 19:00:00,181.37,10.6
+2017-10-11 20:00:00,177.88,10.6
+2017-10-11 21:00:00,171.47,11.1
+2017-10-11 22:00:00,153.39,11.7
+2017-10-11 23:00:00,118.68,11.7
+2017-10-12 00:00:00,111.39,11.7
+2017-10-12 01:00:00,101.54,12.2
+2017-10-12 02:00:00,100.42,12.2
+2017-10-12 03:00:00,100.48,12.8
+2017-10-12 04:00:00,101.47,12.8
+2017-10-12 05:00:00,108.42,13.3
+2017-10-12 06:00:00,145.52,12.8
+2017-10-12 07:00:00,153.4,12.8
+2017-10-12 08:00:00,197.39,13.3
+2017-10-12 09:00:00,194.27,13.9
+2017-10-12 10:00:00,222.98,14.4
+2017-10-12 11:00:00,230.54,15.0
+2017-10-12 12:00:00,231.04,15.6
+2017-10-12 13:00:00,235.03,16.7
+2017-10-12 14:00:00,239.22,17.2
+2017-10-12 15:00:00,263.38,17.8
+2017-10-12 16:00:00,231.38,17.8
+2017-10-12 17:00:00,221.5,17.2
+2017-10-12 18:00:00,192.39,15.0
+2017-10-12 19:00:00,190.47,15.0
+2017-10-12 20:00:00,191.41,14.4
+2017-10-12 21:00:00,186.45,13.9
+2017-10-12 22:00:00,165.68,13.3
+2017-10-12 23:00:00,139.48,12.8
+2017-10-13 00:00:00,108.46,12.8
+2017-10-13 01:00:00,86.46,12.8
+2017-10-13 02:00:00,99.47,12.2
+2017-10-13 03:00:00,98.44,11.1
+2017-10-13 04:00:00,98.48,10.0
+2017-10-13 05:00:00,108.4,9.4
+2017-10-13 06:00:00,144.48,8.9
+2017-10-13 07:00:00,153.4,8.3
+2017-10-13 08:00:00,176.77,10.0
+2017-10-13 09:00:00,313.71,10.6
+2017-10-13 10:00:00,369.72,11.1
+2017-10-13 11:00:00,430.33,11.1
+2017-10-13 12:00:00,481.68,12.8
+2017-10-13 13:00:00,518.25,14.4
+2017-10-13 14:00:00,568.5,15.0
+2017-10-13 15:00:00,683.0,15.6
+2017-10-13 16:00:00,776.91,15.0
+2017-10-13 17:00:00,810.08,13.9
+2017-10-13 18:00:00,731.36,13.9
+2017-10-13 19:00:00,641.19,12.8
+2017-10-13 20:00:00,555.64,11.7
+2017-10-13 21:00:00,505.97,11.1
+2017-10-13 22:00:00,447.58,10.0
+2017-10-13 23:00:00,420.72,8.9
+2017-10-14 00:00:00,368.05,7.2
+2017-10-14 01:00:00,348.11,7.2
+2017-10-14 02:00:00,341.06,8.3
+2017-10-14 03:00:00,335.41,8.3
+2017-10-14 04:00:00,330.56,8.3
+2017-10-14 05:00:00,329.44,8.3
+2017-10-14 06:00:00,331.2,8.9
+2017-10-14 07:00:00,333.98,8.9
+2017-10-14 08:00:00,344.35,8.9
+2017-10-14 09:00:00,382.9,10.0
+2017-10-14 10:00:00,388.07,13.9
+2017-10-14 11:00:00,415.16,13.9
+2017-10-14 12:00:00,487.43,13.9
+2017-10-14 13:00:00,584.56,13.9
+2017-10-14 14:00:00,587.77,12.2
+2017-10-14 15:00:00,604.85,11.1
+2017-10-14 16:00:00,560.16,10.6
+2017-10-14 17:00:00,509.95,10.0
+2017-10-14 18:00:00,483.07,10.0
+2017-10-14 19:00:00,459.97,10.0
+2017-10-14 20:00:00,424.71,8.9
+2017-10-14 21:00:00,373.33,8.9
+2017-10-14 22:00:00,357.34,8.9
+2017-10-14 23:00:00,339.32,8.3
+2017-10-15 00:00:00,329.76,7.8
+2017-10-15 01:00:00,322.66,7.2
+2017-10-15 02:00:00,314.58,6.1
+2017-10-15 03:00:00,300.59,5.6
+2017-10-15 04:00:00,297.77,5.6
+2017-10-15 05:00:00,297.66,5.6
+2017-10-15 06:00:00,299.59,5.0
+2017-10-15 07:00:00,303.75,5.6
+2017-10-15 08:00:00,297.89,7.2
+2017-10-15 09:00:00,329.29,7.2
+2017-10-15 10:00:00,448.56,8.9
+2017-10-15 11:00:00,627.79,8.9
+2017-10-15 12:00:00,636.67,10.6
+2017-10-15 13:00:00,661.07,10.6
+2017-10-15 14:00:00,709.51,11.7
+2017-10-15 15:00:00,634.23,11.7
+2017-10-15 16:00:00,642.57,11.1
+2017-10-15 17:00:00,648.7,10.0
+2017-10-15 18:00:00,628.42,10.0
+2017-10-15 19:00:00,605.96,9.4
+2017-10-15 20:00:00,576.09,10.0
+2017-10-15 21:00:00,569.16,8.3
+2017-10-15 22:00:00,553.62,8.3
+2017-10-15 23:00:00,553.74,7.8
+2017-10-16 00:00:00,557.32,7.2
+2017-10-16 01:00:00,514.17,6.1
+2017-10-16 02:00:00,508.38,6.1
+2017-10-16 03:00:00,512.86,5.6
+2017-10-16 04:00:00,508.83,5.0
+2017-10-16 05:00:00,503.21,4.4
+2017-10-16 06:00:00,559.95,4.4
+2017-10-16 07:00:00,561.95,3.9
+2017-10-16 08:00:00,603.8,5.6
+2017-10-16 09:00:00,639.97,7.8
+2017-10-16 10:00:00,663.2,10.0
+2017-10-16 11:00:00,690.42,12.2
+2017-10-16 12:00:00,789.33,14.4
+2017-10-16 13:00:00,789.05,16.7
+2017-10-16 14:00:00,849.12,17.8
+2017-10-16 15:00:00,969.61,18.9
+2017-10-16 16:00:00,1126.68,18.9
+2017-10-16 17:00:00,1174.49,18.3
+2017-10-16 18:00:00,1150.61,16.7
+2017-10-16 19:00:00,1104.97,16.1
+2017-10-16 20:00:00,1039.24,16.1
+2017-10-16 21:00:00,941.24,15.6
+2017-10-16 22:00:00,870.21,14.4
+2017-10-16 23:00:00,783.25,13.9
+2017-10-17 00:00:00,725.39,13.3
+2017-10-17 01:00:00,679.33,12.2
+2017-10-17 02:00:00,628.8,11.1
+2017-10-17 03:00:00,586.15,10.6
+2017-10-17 04:00:00,572.54,10.0
+2017-10-17 05:00:00,535.67,9.4
+2017-10-17 06:00:00,560.94,9.4
+2017-10-17 07:00:00,601.49,8.9
+2017-10-17 08:00:00,641.61,9.4
+2017-10-17 09:00:00,645.33,11.7
+2017-10-17 10:00:00,695.48,13.3
+2017-10-17 11:00:00,769.67,16.1
+2017-10-17 12:00:00,842.62,18.3
+2017-10-17 13:00:00,1047.43,20.0
+2017-10-17 14:00:00,1176.85,21.7
+2017-10-17 15:00:00,1181.35,22.8
+2017-10-17 16:00:00,1110.71,22.8
+2017-10-17 17:00:00,857.79,22.2
+2017-10-17 18:00:00,625.59,18.9
+2017-10-17 19:00:00,505.54,18.3
+2017-10-17 20:00:00,507.55,18.3
+2017-10-17 21:00:00,468.34,17.2
+2017-10-17 22:00:00,447.7,17.2
+2017-10-17 23:00:00,457.45,16.7
+2017-10-18 00:00:00,432.08,16.1
+2017-10-18 01:00:00,415.87,15.0
+2017-10-18 02:00:00,400.49,14.4
+2017-10-18 03:00:00,391.39,13.3
+2017-10-18 04:00:00,408.74,10.6
+2017-10-18 05:00:00,432.92,10.0
+2017-10-18 06:00:00,443.88,9.4
+2017-10-18 07:00:00,453.62,10.0
+2017-10-18 08:00:00,473.71,11.7
+2017-10-18 09:00:00,478.58,13.9
+2017-10-18 10:00:00,499.81,16.1
+2017-10-18 11:00:00,559.97,17.8
+2017-10-18 12:00:00,717.02,18.3
+2017-10-18 13:00:00,719.44,19.4
+2017-10-18 14:00:00,756.04,21.1
+2017-10-18 15:00:00,875.35,22.2
+2017-10-18 16:00:00,986.32,21.7
+2017-10-18 17:00:00,920.42,19.4
+2017-10-18 18:00:00,748.2,16.7
+2017-10-18 19:00:00,646.14,15.0
+2017-10-18 20:00:00,499.87,13.3
+2017-10-18 21:00:00,510.08,12.8
+2017-10-18 22:00:00,597.21,12.8
+2017-10-18 23:00:00,485.72,12.2
+2017-10-19 00:00:00,429.76,11.1
+2017-10-19 01:00:00,409.13,11.1
+2017-10-19 02:00:00,402.61,10.0
+2017-10-19 03:00:00,395.45,8.3
+2017-10-19 04:00:00,404.41,8.3
+2017-10-19 05:00:00,402.7,7.8
+2017-10-19 06:00:00,380.64,7.8
+2017-10-19 07:00:00,381.43,7.2
+2017-10-19 08:00:00,412.87,7.8
+2017-10-19 09:00:00,425.06,10.6
+2017-10-19 10:00:00,436.27,13.3
+2017-10-19 11:00:00,492.33,17.2
+2017-10-19 12:00:00,529.07,19.4
+2017-10-19 13:00:00,710.22,21.7
+2017-10-19 14:00:00,806.8,22.8
+2017-10-19 15:00:00,913.01,22.8
+2017-10-19 16:00:00,974.26,22.2
+2017-10-19 17:00:00,973.91,21.7
+2017-10-19 18:00:00,896.73,20.0
+2017-10-19 19:00:00,749.85,17.8
+2017-10-19 20:00:00,632.92,16.7
+2017-10-19 21:00:00,555.71,14.4
+2017-10-19 22:00:00,529.64,13.3
+2017-10-19 23:00:00,455.69,12.8
+2017-10-20 00:00:00,377.62,12.8
+2017-10-20 01:00:00,368.85,12.8
+2017-10-20 02:00:00,365.53,12.8
+2017-10-20 03:00:00,367.47,12.8
+2017-10-20 04:00:00,385.88,11.7
+2017-10-20 05:00:00,401.63,12.2
+2017-10-20 06:00:00,404.4,12.2
+2017-10-20 07:00:00,446.82,12.2
+2017-10-20 08:00:00,506.22,13.9
+2017-10-20 09:00:00,498.83,16.7
+2017-10-20 10:00:00,605.36,20.0
+2017-10-20 11:00:00,661.93,22.2
+2017-10-20 12:00:00,809.64,23.9
+2017-10-20 13:00:00,968.47,24.4
+2017-10-20 14:00:00,1071.57,25.0
+2017-10-20 15:00:00,1025.79,25.0
+2017-10-20 16:00:00,916.57,25.0
+2017-10-20 17:00:00,749.91,23.9
+2017-10-20 18:00:00,685.49,21.7
+2017-10-20 19:00:00,547.92,20.6
+2017-10-20 20:00:00,480.08,20.0
+2017-10-20 21:00:00,493.84,20.0
+2017-10-20 22:00:00,527.36,20.0
+2017-10-20 23:00:00,472.02,19.4
+2017-10-21 00:00:00,418.18,18.9
+2017-10-21 01:00:00,401.1,17.8
+2017-10-21 02:00:00,400.46,17.8
+2017-10-21 03:00:00,388.3,17.2
+2017-10-21 04:00:00,380.94,17.2
+2017-10-21 05:00:00,386.19,17.2
+2017-10-21 06:00:00,384.0,17.2
+2017-10-21 07:00:00,389.86,15.6
+2017-10-21 08:00:00,432.58,16.1
+2017-10-21 09:00:00,583.07,16.1
+2017-10-21 10:00:00,603.56,16.1
+2017-10-21 11:00:00,647.79,17.2
+2017-10-21 12:00:00,569.11,18.3
+2017-10-21 13:00:00,753.18,18.9
+2017-10-21 14:00:00,786.5,19.4
+2017-10-21 15:00:00,846.01,20.0
+2017-10-21 16:00:00,869.82,20.6
+2017-10-21 17:00:00,874.01,20.6
+2017-10-21 18:00:00,898.19,20.0
+2017-10-21 19:00:00,857.29,13.9
+2017-10-21 20:00:00,687.71,13.9
+2017-10-21 21:00:00,406.89,13.3
+2017-10-21 22:00:00,417.0,12.2
+2017-10-21 23:00:00,369.64,11.7
+2017-10-22 00:00:00,347.9,11.1
+2017-10-22 01:00:00,326.21,10.6
+2017-10-22 02:00:00,311.48,10.0
+2017-10-22 03:00:00,281.98,10.0
+2017-10-22 04:00:00,297.32,10.0
+2017-10-22 05:00:00,321.34,9.4
+2017-10-22 06:00:00,321.86,9.4
+2017-10-22 07:00:00,317.78,8.9
+2017-10-22 08:00:00,319.8,9.4
+2017-10-22 09:00:00,319.72,10.0
+2017-10-22 10:00:00,316.88,10.0
+2017-10-22 11:00:00,331.28,12.8
+2017-10-22 12:00:00,341.31,15.6
+2017-10-22 13:00:00,363.17,16.7
+2017-10-22 14:00:00,465.4,17.2
+2017-10-22 15:00:00,509.03,17.8
+2017-10-22 16:00:00,473.57,17.2
+2017-10-22 17:00:00,559.69,16.7
+2017-10-22 18:00:00,525.65,13.9
+2017-10-22 19:00:00,445.07,14.4
+2017-10-22 20:00:00,374.37,13.3
+2017-10-22 21:00:00,354.82,13.9
+2017-10-22 22:00:00,331.29,13.3
+2017-10-22 23:00:00,326.47,13.3
+2017-10-23 00:00:00,324.68,13.3
+2017-10-23 01:00:00,314.59,13.3
+2017-10-23 02:00:00,311.17,13.3
+2017-10-23 03:00:00,311.46,12.2
+2017-10-23 04:00:00,306.68,10.6
+2017-10-23 05:00:00,303.24,8.9
+2017-10-23 06:00:00,340.09,11.1
+2017-10-23 07:00:00,344.87,10.6
+2017-10-23 08:00:00,362.65,11.1
+2017-10-23 09:00:00,379.21,13.9
+2017-10-23 10:00:00,401.32,13.9
+2017-10-23 11:00:00,530.03,15.6
+2017-10-23 12:00:00,835.03,15.0
+2017-10-23 13:00:00,886.92,15.0
+2017-10-23 14:00:00,893.37,13.3
+2017-10-23 15:00:00,876.11,11.1
+2017-10-23 16:00:00,780.43,10.6
+2017-10-23 17:00:00,718.97,10.0
+2017-10-23 18:00:00,702.03,9.4
+2017-10-23 19:00:00,686.51,9.4
+2017-10-23 20:00:00,620.93,9.4
+2017-10-23 21:00:00,623.24,8.9
+2017-10-23 22:00:00,631.9,8.3
+2017-10-23 23:00:00,851.73,7.2
+2017-10-24 00:00:00,838.17,6.1
+2017-10-24 01:00:00,627.84,5.6
+2017-10-24 02:00:00,536.74,5.6
+2017-10-24 03:00:00,546.05,6.1
+2017-10-24 04:00:00,552.62,6.1
+2017-10-24 05:00:00,564.05,6.1
+2017-10-24 06:00:00,600.02,5.6
+2017-10-24 07:00:00,621.26,4.4
+2017-10-24 08:00:00,684.74,5.0
+2017-10-24 09:00:00,670.11,5.0
+2017-10-24 10:00:00,693.67,5.6
+2017-10-24 11:00:00,718.25,7.2
+2017-10-24 12:00:00,696.42,8.3
+2017-10-24 13:00:00,763.2,10.0
+2017-10-24 14:00:00,824.0,10.0
+2017-10-24 15:00:00,789.8,10.6
+2017-10-24 16:00:00,771.5,10.0
+2017-10-24 17:00:00,808.43,8.9
+2017-10-24 18:00:00,742.51,7.8
+2017-10-24 19:00:00,700.45,7.2
+2017-10-24 20:00:00,702.53,6.1
+2017-10-24 21:00:00,636.78,6.1
+2017-10-24 22:00:00,602.19,6.7
+2017-10-24 23:00:00,594.91,6.1
+2017-10-25 00:00:00,555.79,6.1
+2017-10-25 01:00:00,564.65,6.7
+2017-10-25 02:00:00,541.6,5.6
+2017-10-25 03:00:00,535.84,5.0
+2017-10-25 04:00:00,533.96,5.0
+2017-10-25 05:00:00,550.86,4.4
+2017-10-25 06:00:00,602.88,4.4
+2017-10-25 07:00:00,598.86,3.9
+2017-10-25 08:00:00,660.3,5.6
+2017-10-25 09:00:00,651.86,7.8
+2017-10-25 10:00:00,634.88,9.4
+2017-10-25 11:00:00,718.65,10.6
+2017-10-25 12:00:00,701.82,11.7
+2017-10-25 13:00:00,705.68,12.2
+2017-10-25 14:00:00,794.65,12.8
+2017-10-25 15:00:00,769.09,13.3
+2017-10-25 16:00:00,979.82,13.3
+2017-10-25 17:00:00,1005.86,12.8
+2017-10-25 18:00:00,1043.16,10.0
+2017-10-25 19:00:00,777.02,10.6
+2017-10-25 20:00:00,690.55,9.4
+2017-10-25 21:00:00,615.44,8.3
+2017-10-25 22:00:00,509.91,8.3
+2017-10-25 23:00:00,430.96,7.8
+2017-10-26 00:00:00,416.12,7.2
+2017-10-26 01:00:00,395.42,7.8
+2017-10-26 02:00:00,404.25,7.2
+2017-10-26 03:00:00,401.05,7.2
+2017-10-26 04:00:00,401.52,7.2
+2017-10-26 05:00:00,403.87,7.8
+2017-10-26 06:00:00,415.24,8.9
+2017-10-26 07:00:00,490.03,8.9
+2017-10-26 08:00:00,533.21,9.4
+2017-10-26 09:00:00,536.81,10.0
+2017-10-26 10:00:00,564.0,11.1
+2017-10-26 11:00:00,619.36,13.9
+2017-10-26 12:00:00,689.32,13.9
+2017-10-26 13:00:00,763.41,10.6
+2017-10-26 14:00:00,772.42,10.0
+2017-10-26 15:00:00,635.13,7.2
+2017-10-26 16:00:00,590.62,5.6
+2017-10-26 17:00:00,543.09,4.4
+2017-10-26 18:00:00,516.3,3.9
+2017-10-26 19:00:00,489.08,3.3
+2017-10-26 20:00:00,506.46,2.2
+2017-10-26 21:00:00,508.66,2.2
+2017-10-26 22:00:00,490.68,2.2
+2017-10-26 23:00:00,478.28,1.7
+2017-10-27 00:00:00,447.3,1.7
+2017-10-27 01:00:00,432.53,1.7
+2017-10-27 02:00:00,423.78,1.7
+2017-10-27 03:00:00,411.38,1.7
+2017-10-27 04:00:00,415.62,1.1
+2017-10-27 05:00:00,430.2,1.7
+2017-10-27 06:00:00,473.02,1.1
+2017-10-27 07:00:00,511.4,1.1
+2017-10-27 08:00:00,611.72,1.1
+2017-10-27 09:00:00,684.6,0.85
+2017-10-27 10:00:00,566.55,0.6
+2017-10-27 11:00:00,567.28,1.1
+2017-10-27 12:00:00,574.16,0.6
+2017-10-27 13:00:00,573.67,0.6
+2017-10-27 14:00:00,594.35,1.1
+2017-10-27 15:00:00,574.77,0.6
+2017-10-27 16:00:00,634.53,1.1
+2017-10-27 17:00:00,603.32,1.1
+2017-10-27 18:00:00,584.74,0.6
+2017-10-27 19:00:00,588.96,1.1
+2017-10-27 20:00:00,555.58,1.1
+2017-10-27 21:00:00,543.42,0.6
+2017-10-27 22:00:00,543.29,0.6
+2017-10-27 23:00:00,529.93,0.6
+2017-10-28 00:00:00,444.31,0.0
+2017-10-28 01:00:00,407.78,-0.6
+2017-10-28 02:00:00,399.31,-0.6
+2017-10-28 03:00:00,391.87,-1.1
+2017-10-28 04:00:00,393.9,0.0
+2017-10-28 05:00:00,389.85,0.0
+2017-10-28 06:00:00,398.23,0.0
+2017-10-28 07:00:00,448.9,0.0
+2017-10-28 08:00:00,526.13,0.0
+2017-10-28 09:00:00,541.14,0.0
+2017-10-28 10:00:00,526.29,0.6
+2017-10-28 11:00:00,556.91,0.6
+2017-10-28 12:00:00,547.28,0.6
+2017-10-28 13:00:00,551.89,1.1
+2017-10-28 14:00:00,556.75,1.1
+2017-10-28 15:00:00,570.38,1.1
+2017-10-28 16:00:00,592.26,1.1
+2017-10-28 17:00:00,608.75,1.1
+2017-10-28 18:00:00,621.06,0.6
+2017-10-28 19:00:00,613.27,-0.6
+2017-10-28 20:00:00,605.22,-1.1
+2017-10-28 21:00:00,594.79,-1.1
+2017-10-28 22:00:00,602.98,-1.1
+2017-10-28 23:00:00,563.83,-1.1
+2017-10-29 00:00:00,530.3,-1.1
+2017-10-29 01:00:00,432.36,-1.1
+2017-10-29 02:00:00,406.31,-1.7
+2017-10-29 03:00:00,402.79,-1.1
+2017-10-29 04:00:00,407.55,-1.1
+2017-10-29 05:00:00,413.44,-0.6
+2017-10-29 06:00:00,413.82,0.0
+2017-10-29 07:00:00,416.09,0.0
+2017-10-29 08:00:00,431.14,0.6
+2017-10-29 09:00:00,439.51,1.1
+2017-10-29 10:00:00,448.28,2.8
+2017-10-29 11:00:00,486.32,3.9
+2017-10-29 12:00:00,511.93,4.4
+2017-10-29 13:00:00,537.35,6.1
+2017-10-29 14:00:00,522.67,6.1
+2017-10-29 15:00:00,473.9,6.1
+2017-10-29 16:00:00,538.95,6.1
+2017-10-29 17:00:00,559.98,6.1
+2017-10-29 18:00:00,573.18,6.1
+2017-10-29 19:00:00,580.63,5.6
+2017-10-29 20:00:00,587.21,6.1
+2017-10-29 21:00:00,610.84,6.1
+2017-10-29 22:00:00,512.04,5.6
+2017-10-29 23:00:00,467.42,5.6
+2017-10-30 00:00:00,461.37,4.4
+2017-10-30 01:00:00,442.82,3.3
+2017-10-30 02:00:00,449.68,3.9
+2017-10-30 03:00:00,467.17,3.9
+2017-10-30 04:00:00,436.6,3.3
+2017-10-30 05:00:00,444.97,3.3
+2017-10-30 06:00:00,456.81,2.2
+2017-10-30 07:00:00,459.62,2.2
+2017-10-30 08:00:00,496.64,2.2
+2017-10-30 09:00:00,571.21,2.8
+2017-10-30 10:00:00,583.77,2.8
+2017-10-30 11:00:00,561.8,3.3
+2017-10-30 12:00:00,434.51,3.3
+2017-10-30 13:00:00,579.76,2.8
+2017-10-30 14:00:00,768.03,2.2
+2017-10-30 15:00:00,720.74,1.1
+2017-10-30 16:00:00,727.87,1.1
+2017-10-30 17:00:00,743.68,0.6
+2017-10-30 18:00:00,716.08,0.6
+2017-10-30 19:00:00,735.16,0.0
+2017-10-30 20:00:00,740.21,0.0
+2017-10-30 21:00:00,726.45,0.0
+2017-10-30 22:00:00,692.95,0.0
+2017-10-30 23:00:00,694.13,-0.6
+2017-10-31 00:00:00,629.9,-0.6
+2017-10-31 01:00:00,579.66,-0.6
+2017-10-31 02:00:00,565.97,-0.6
+2017-10-31 03:00:00,560.82,-0.6
+2017-10-31 04:00:00,555.98,-1.1
+2017-10-31 05:00:00,569.44,-1.7
+2017-10-31 06:00:00,565.05,-1.7
+2017-10-31 07:00:00,535.31,-1.7
+2017-10-31 08:00:00,578.85,-1.7
+2017-10-31 09:00:00,641.27,-1.1
+2017-10-31 10:00:00,651.23,-1.1
+2017-10-31 11:00:00,531.31,-1.1
+2017-10-31 12:00:00,467.62,-0.6
+2017-10-31 13:00:00,474.87,0.0
+2017-10-31 14:00:00,484.28,0.6
+2017-10-31 15:00:00,508.43,1.1
+2017-10-31 16:00:00,510.2,1.1
+2017-10-31 17:00:00,479.74,1.1
+2017-10-31 18:00:00,458.0,0.0
+2017-10-31 19:00:00,459.42,0.0
+2017-10-31 20:00:00,430.27,-2.2
+2017-10-31 21:00:00,410.39,-2.2
+2017-10-31 22:00:00,397.71,-2.8
+2017-10-31 23:00:00,359.93,-2.2
+2017-11-01 00:00:00,348.14,-2.2
+2017-11-01 01:00:00,345.63,-2.8
+2017-11-01 02:00:00,346.09,-2.8
+2017-11-01 03:00:00,343.8,-1.7
+2017-11-01 04:00:00,342.32,-1.7
+2017-11-01 05:00:00,349.26,-1.1
+2017-11-01 06:00:00,399.99,-0.6
+2017-11-01 07:00:00,412.49,0.0
+2017-11-01 08:00:00,447.61,0.0
+2017-11-01 09:00:00,462.02,0.0
+2017-11-01 10:00:00,468.46,0.6
+2017-11-01 11:00:00,474.86,1.1
+2017-11-01 12:00:00,469.7,2.8
+2017-11-01 13:00:00,465.71,1.1
+2017-11-01 14:00:00,479.54,1.1
+2017-11-01 15:00:00,472.71,1.1
+2017-11-01 16:00:00,479.74,1.1
+2017-11-01 17:00:00,472.61,1.1
+2017-11-01 18:00:00,466.38,1.7
+2017-11-01 19:00:00,468.04,1.7
+2017-11-01 20:00:00,468.6,2.2
+2017-11-01 21:00:00,465.07,2.2
+2017-11-01 22:00:00,449.92,1.7
+2017-11-01 23:00:00,386.97,1.7
+2017-11-02 00:00:00,358.48,1.7
+2017-11-02 01:00:00,350.29,1.1
+2017-11-02 02:00:00,349.32,1.1
+2017-11-02 03:00:00,346.01,1.7
+2017-11-02 04:00:00,349.35,2.2
+2017-11-02 05:00:00,353.68,2.8
+2017-11-02 06:00:00,392.54,2.8
+2017-11-02 07:00:00,403.68,2.8
+2017-11-02 08:00:00,421.85,3.3
+2017-11-02 09:00:00,422.62,3.9
+2017-11-02 10:00:00,430.31,3.9
+2017-11-02 11:00:00,445.46,3.9
+2017-11-02 12:00:00,469.16,3.3
+2017-11-02 13:00:00,475.3,4.4
+2017-11-02 14:00:00,477.12,4.4
+2017-11-02 15:00:00,483.82,3.9
+2017-11-02 16:00:00,496.83,3.3
+2017-11-02 17:00:00,549.78,2.8
+2017-11-02 18:00:00,541.1,2.8
+2017-11-02 19:00:00,537.99,2.8
+2017-11-02 20:00:00,529.83,2.8
+2017-11-02 21:00:00,513.83,2.8
+2017-11-02 22:00:00,471.57,2.8
+2017-11-02 23:00:00,394.76,2.2
+2017-11-03 00:00:00,391.35,1.7
+2017-11-03 01:00:00,375.4,0.6
+2017-11-03 02:00:00,378.23,0.0
+2017-11-03 03:00:00,373.47,-0.6
+2017-11-03 04:00:00,375.87,-1.7
+2017-11-03 05:00:00,397.86,-2.2
+2017-11-03 06:00:00,409.12,-2.2
+2017-11-03 07:00:00,414.22,-2.8
+2017-11-03 08:00:00,454.29,-1.1
+2017-11-03 09:00:00,471.7,-0.6
+2017-11-03 10:00:00,487.58,0.0
+2017-11-03 11:00:00,494.24,0.6
+2017-11-03 12:00:00,498.38,0.6
+2017-11-03 13:00:00,489.07,1.1
+2017-11-03 14:00:00,495.84,1.1
+2017-11-03 15:00:00,487.15,-0.6
+2017-11-03 16:00:00,473.29,-0.6
+2017-11-03 17:00:00,471.12,-0.6
+2017-11-03 18:00:00,465.67,0.0
+2017-11-03 19:00:00,471.85,0.6
+2017-11-03 20:00:00,491.62,0.6
+2017-11-03 21:00:00,474.53,0.6
+2017-11-03 22:00:00,461.74,0.6
+2017-11-03 23:00:00,417.52,1.1
+2017-11-04 00:00:00,363.58,1.1
+2017-11-04 01:00:00,347.82,1.1
+2017-11-04 02:00:00,343.54,1.1
+2017-11-04 03:00:00,345.08,1.7
+2017-11-04 04:00:00,344.2,1.7
+2017-11-04 05:00:00,349.12,2.2
+2017-11-04 06:00:00,358.91,2.2
+2017-11-04 07:00:00,369.83,2.2
+2017-11-04 08:00:00,415.85,2.8
+2017-11-04 09:00:00,445.13,2.8
+2017-11-04 10:00:00,464.63,3.3
+2017-11-04 11:00:00,531.15,3.9
+2017-11-04 12:00:00,517.41,4.4
+2017-11-04 13:00:00,502.29,4.4
+2017-11-04 14:00:00,513.39,5.0
+2017-11-04 15:00:00,511.92,5.0
+2017-11-04 16:00:00,491.23,5.0
+2017-11-04 17:00:00,421.1,5.0
+2017-11-04 18:00:00,408.1,5.0
+2017-11-04 19:00:00,400.38,5.0
+2017-11-04 20:00:00,396.43,5.6
+2017-11-04 21:00:00,394.08,5.6
+2017-11-04 22:00:00,375.98,5.6
+2017-11-04 23:00:00,364.0,5.6
+2017-11-05 00:00:00,361.5,6.1
+2017-11-05 01:00:00,349.68,6.1
+2017-11-05 02:00:00,704.2,6.1
+2017-11-05 03:00:00,349.04,6.1
+2017-11-05 04:00:00,351.56,5.6
+2017-11-05 05:00:00,363.3,3.9
+2017-11-05 06:00:00,369.67,2.8
+2017-11-05 07:00:00,372.25,2.2
+2017-11-05 08:00:00,373.95,2.2
+2017-11-05 09:00:00,378.49,1.1
+2017-11-05 10:00:00,377.35,0.6
+2017-11-05 11:00:00,392.68,1.1
+2017-11-05 12:00:00,406.01,0.0
+2017-11-05 13:00:00,404.7,1.1
+2017-11-05 14:00:00,401.46,0.6
+2017-11-05 15:00:00,402.04,-0.6
+2017-11-05 16:00:00,399.58,-0.6
+2017-11-05 17:00:00,408.8,-0.6
+2017-11-05 18:00:00,409.56,-1.1
+2017-11-05 19:00:00,395.62,-1.7
+2017-11-05 20:00:00,371.52,-1.7
+2017-11-05 21:00:00,371.61,-2.8
+2017-11-05 22:00:00,358.31,-2.8
+2017-11-05 23:00:00,349.49,-3.3
+2017-11-06 00:00:00,346.23,-3.3
+2017-11-06 01:00:00,336.9,-4.4
+2017-11-06 02:00:00,338.34,-4.4
+2017-11-06 03:00:00,335.15,-5.0
+2017-11-06 04:00:00,335.15,-5.0
+2017-11-06 05:00:00,342.64,-5.0
+2017-11-06 06:00:00,388.56,-5.6
+2017-11-06 07:00:00,457.68,-5.0
+2017-11-06 08:00:00,505.39,-4.4
+2017-11-06 09:00:00,515.11,-3.3
+2017-11-06 10:00:00,549.73,-2.8
+2017-11-06 11:00:00,555.37,-1.7
+2017-11-06 12:00:00,548.26,-1.1
+2017-11-06 13:00:00,472.04,-0.6
+2017-11-06 14:00:00,354.33,0.0
+2017-11-06 15:00:00,336.81,0.6
+2017-11-06 16:00:00,320.54,0.0
+2017-11-06 17:00:00,305.07,0.0
+2017-11-06 18:00:00,274.19,-0.6
+2017-11-06 19:00:00,263.26,-0.6
+2017-11-06 20:00:00,257.1,-1.7
+2017-11-06 21:00:00,253.08,-1.1
+2017-11-06 22:00:00,238.03,-1.7
+2017-11-06 23:00:00,199.78,-1.7
+2017-11-07 00:00:00,189.15,-1.7
+2017-11-07 01:00:00,179.22,-1.7
+2017-11-07 02:00:00,181.46,-1.7
+2017-11-07 03:00:00,181.4,-1.1
+2017-11-07 04:00:00,178.93,-1.7
+2017-11-07 05:00:00,188.24,-1.7
+2017-11-07 06:00:00,236.6,-1.7
+2017-11-07 07:00:00,250.15,-1.7
+2017-11-07 08:00:00,277.87,-2.2
+2017-11-07 09:00:00,291.12,-1.7
+2017-11-07 10:00:00,297.61,-2.2
+2017-11-07 11:00:00,294.37,-0.6
+2017-11-07 12:00:00,303.02,0.6
+2017-11-07 13:00:00,306.75,1.7
+2017-11-07 14:00:00,313.04,2.2
+2017-11-07 15:00:00,312.33,2.2
+2017-11-07 16:00:00,303.74,1.7
+2017-11-07 17:00:00,286.86,0.6
+2017-11-07 18:00:00,278.42,-0.6
+2017-11-07 19:00:00,266.26,-0.6
+2017-11-07 20:00:00,267.31,-1.1
+2017-11-07 21:00:00,258.1,-1.7
+2017-11-07 22:00:00,242.89,-2.2
+2017-11-07 23:00:00,226.25,-1.7
+2017-11-08 00:00:00,200.98,-1.1
+2017-11-08 01:00:00,196.8,-1.1
+2017-11-08 02:00:00,196.26,-1.7
+2017-11-08 03:00:00,198.41,-2.2
+2017-11-08 04:00:00,194.67,-2.2
+2017-11-08 05:00:00,199.92,-2.2
+2017-11-08 06:00:00,236.07,-2.8
+2017-11-08 07:00:00,243.52,-2.8
+2017-11-08 08:00:00,265.13,-2.8
+2017-11-08 09:00:00,281.65,-1.1
+2017-11-08 10:00:00,311.83,-0.6
+2017-11-08 11:00:00,314.91,1.1
+2017-11-08 12:00:00,323.22,2.2
+2017-11-08 13:00:00,345.63,3.9
+2017-11-08 14:00:00,346.91,4.4
+2017-11-08 15:00:00,325.58,5.0
+2017-11-08 16:00:00,363.71,5.6
+2017-11-08 17:00:00,379.55,4.4
+2017-11-08 18:00:00,369.38,3.3
+2017-11-08 19:00:00,382.1,3.9
+2017-11-08 20:00:00,370.54,2.8
+2017-11-08 21:00:00,370.36,2.2
+2017-11-08 22:00:00,291.17,1.1
+2017-11-08 23:00:00,248.1,0.6
+2017-11-09 00:00:00,242.79,-1.1
+2017-11-09 01:00:00,230.2,-1.1
+2017-11-09 02:00:00,224.68,-2.2
+2017-11-09 03:00:00,223.29,-2.8
+2017-11-09 04:00:00,213.62,-4.4
+2017-11-09 05:00:00,219.11,-6.1
+2017-11-09 06:00:00,224.62,-6.1
+2017-11-09 07:00:00,230.19,-7.2
+2017-11-09 08:00:00,272.93,-7.2
+2017-11-09 09:00:00,296.04,-7.2
+2017-11-09 10:00:00,323.92,-6.1
+2017-11-09 11:00:00,299.92,-6.1
+2017-11-09 12:00:00,302.29,-5.6
+2017-11-09 13:00:00,306.93,-5.6
+2017-11-09 14:00:00,299.6,-6.1
+2017-11-09 15:00:00,299.11,-6.1
+2017-11-09 16:00:00,316.95,-6.7
+2017-11-09 17:00:00,295.84,-8.3
+2017-11-09 18:00:00,259.68,-8.9
+2017-11-09 19:00:00,255.83,-8.9
+2017-11-09 20:00:00,257.67,-9.4
+2017-11-09 21:00:00,246.83,-10.0
+2017-11-09 22:00:00,232.55,-10.0
+2017-11-09 23:00:00,203.11,-10.6
+2017-11-10 00:00:00,185.77,-11.1
+2017-11-10 01:00:00,179.96,-11.1
+2017-11-10 02:00:00,174.67,-11.7
+2017-11-10 03:00:00,171.21,-11.7
+2017-11-10 04:00:00,177.78,-11.7
+2017-11-10 05:00:00,180.64,-11.1
+2017-11-10 06:00:00,216.46,-11.1
+2017-11-10 07:00:00,223.79,-11.1
+2017-11-10 08:00:00,255.22,-10.6
+2017-11-10 09:00:00,272.08,-9.4
+2017-11-10 10:00:00,275.56,-8.3
+2017-11-10 11:00:00,280.67,-7.8
+2017-11-10 12:00:00,314.27,-6.7
+2017-11-10 13:00:00,316.0,-6.7
+2017-11-10 14:00:00,324.08,-5.6
+2017-11-10 15:00:00,323.56,-5.0
+2017-11-10 16:00:00,304.36,-5.0
+2017-11-10 17:00:00,313.55,-5.0
+2017-11-10 18:00:00,319.95,-4.4
+2017-11-10 19:00:00,332.16,-4.4
+2017-11-10 20:00:00,320.34,-3.9
+2017-11-10 21:00:00,313.65,-3.9
+2017-11-10 22:00:00,280.78,-3.9
+2017-11-10 23:00:00,260.53,-4.4
+2017-11-11 00:00:00,259.75,-4.4
+2017-11-11 01:00:00,253.21,-2.8
+2017-11-11 02:00:00,259.02,-2.8
+2017-11-11 03:00:00,256.58,-2.2
+2017-11-11 04:00:00,254.54,-1.1
+2017-11-11 05:00:00,251.51,-0.6
+2017-11-11 06:00:00,261.2,-0.6
+2017-11-11 07:00:00,263.01,-1.1
+2017-11-11 08:00:00,270.58,-0.6
+2017-11-11 09:00:00,275.45,0.0
+2017-11-11 10:00:00,276.36,1.1
+2017-11-11 11:00:00,301.42,2.8
+2017-11-11 12:00:00,301.69,4.4
+2017-11-11 13:00:00,310.11,5.6
+2017-11-11 14:00:00,294.89,6.1
+2017-11-11 15:00:00,299.55,6.1
+2017-11-11 16:00:00,297.05,6.1
+2017-11-11 17:00:00,303.67,5.6
+2017-11-11 18:00:00,299.84,4.4
+2017-11-11 19:00:00,281.68,2.8
+2017-11-11 20:00:00,257.44,1.7
+2017-11-11 21:00:00,255.22,0.0
+2017-11-11 22:00:00,249.77,-0.6
+2017-11-11 23:00:00,237.46,0.0
+2017-11-12 00:00:00,231.36,-1.7
+2017-11-12 01:00:00,228.2,-2.8
+2017-11-12 02:00:00,222.84,-2.2
+2017-11-12 03:00:00,214.91,-2.2
+2017-11-12 04:00:00,211.66,-2.8
+2017-11-12 05:00:00,216.66,-3.3
+2017-11-12 06:00:00,225.54,-3.3
+2017-11-12 07:00:00,240.18,-3.9
+2017-11-12 08:00:00,272.4,-2.8
+2017-11-12 09:00:00,281.08,-0.6
+2017-11-12 10:00:00,297.03,0.6
+2017-11-12 11:00:00,351.43,0.0
+2017-11-12 12:00:00,361.43,0.6
+2017-11-12 13:00:00,376.88,0.6
+2017-11-12 14:00:00,395.72,1.7
+2017-11-12 15:00:00,391.33,2.2
+2017-11-12 16:00:00,383.16,1.7
+2017-11-12 17:00:00,377.07,1.1
+2017-11-12 18:00:00,293.5,0.0
+2017-11-12 19:00:00,265.68,0.0
+2017-11-12 20:00:00,262.58,-0.6
+2017-11-12 21:00:00,257.0,-0.6
+2017-11-12 22:00:00,242.98,-1.1
+2017-11-12 23:00:00,236.27,-1.7
+2017-11-13 00:00:00,237.11,-2.2
+2017-11-13 01:00:00,234.29,-2.8
+2017-11-13 02:00:00,234.97,-2.8
+2017-11-13 03:00:00,231.38,-3.3
+2017-11-13 04:00:00,231.37,-3.3
+2017-11-13 05:00:00,237.46,-3.3
+2017-11-13 06:00:00,244.47,-2.8
+2017-11-13 07:00:00,255.25,-2.8
+2017-11-13 08:00:00,284.74,-2.2
+2017-11-13 09:00:00,305.71,-0.6
+2017-11-13 10:00:00,325.42,2.2
+2017-11-13 11:00:00,347.62,3.9
+2017-11-13 12:00:00,342.7,5.0
+2017-11-13 13:00:00,352.16,7.2
+2017-11-13 14:00:00,349.6,6.1
+2017-11-13 15:00:00,345.4,7.8
+2017-11-13 16:00:00,346.59,7.8
+2017-11-13 17:00:00,355.25,6.7
+2017-11-13 18:00:00,323.45,5.6
+2017-11-13 19:00:00,308.59,5.0
+2017-11-13 20:00:00,304.89,4.4
+2017-11-13 21:00:00,298.97,4.4
+2017-11-13 22:00:00,286.79,3.9
+2017-11-13 23:00:00,272.86,3.9
+2017-11-14 00:00:00,242.76,3.9
+2017-11-14 01:00:00,236.66,3.9
+2017-11-14 02:00:00,235.71,4.4
+2017-11-14 03:00:00,234.27,4.4
+2017-11-14 04:00:00,234.34,4.4
+2017-11-14 05:00:00,240.03,3.9
+2017-11-14 06:00:00,279.0,4.4
+2017-11-14 07:00:00,289.82,4.4
+2017-11-14 08:00:00,346.09,4.4
+2017-11-14 09:00:00,372.0,5.0
+2017-11-14 10:00:00,407.0,5.6
+2017-11-14 11:00:00,716.96,6.1
+2017-11-14 12:00:00,453.92,6.7
+2017-11-14 13:00:00,452.76,6.7
+2017-11-14 14:00:00,440.6,6.7
+2017-11-14 15:00:00,432.17,6.7
+2017-11-14 16:00:00,428.84,6.7
+2017-11-14 17:00:00,435.62,6.7
+2017-11-14 18:00:00,418.32,6.1
+2017-11-14 19:00:00,408.03,6.1
+2017-11-14 20:00:00,396.98,6.1
+2017-11-14 21:00:00,392.74,6.7
+2017-11-14 22:00:00,376.28,6.7
+2017-11-14 23:00:00,301.75,6.7
+2017-11-15 00:00:00,288.25,7.2
+2017-11-15 01:00:00,291.09,7.2
+2017-11-15 02:00:00,286.7,7.8
+2017-11-15 03:00:00,286.52,7.2
+2017-11-15 04:00:00,278.57,7.2
+2017-11-15 05:00:00,284.21,6.7
+2017-11-15 06:00:00,320.2,6.1
+2017-11-15 07:00:00,318.67,3.9
+2017-11-15 08:00:00,399.93,3.3
+2017-11-15 09:00:00,440.39,2.8
+2017-11-15 10:00:00,447.08,1.7
+2017-11-15 11:00:00,461.66,0.6
+2017-11-15 12:00:00,407.97,0.0
+2017-11-15 13:00:00,381.18,0.6
+2017-11-15 14:00:00,366.67,0.6
+2017-11-15 15:00:00,354.11,0.6
+2017-11-15 16:00:00,355.54,0.0
+2017-11-15 17:00:00,374.45,-0.6
+2017-11-15 18:00:00,385.26,-1.1
+2017-11-15 19:00:00,370.56,-1.1
+2017-11-15 20:00:00,392.33,-1.7
+2017-11-15 21:00:00,369.53,-2.2
+2017-11-15 22:00:00,339.97,-2.2
+2017-11-15 23:00:00,248.75,-2.2
+2017-11-16 00:00:00,199.77,-2.2
+2017-11-16 01:00:00,192.07,-2.8
+2017-11-16 02:00:00,189.8,-2.2
+2017-11-16 03:00:00,187.44,-2.2
+2017-11-16 04:00:00,189.7,-1.7
+2017-11-16 05:00:00,197.27,-1.7
+2017-11-16 06:00:00,232.76,-1.7
+2017-11-16 07:00:00,242.84,-1.7
+2017-11-16 08:00:00,304.79,-1.7
+2017-11-16 09:00:00,334.85,-1.7
+2017-11-16 10:00:00,344.28,-1.7
+2017-11-16 11:00:00,355.6,-1.1
+2017-11-16 12:00:00,349.68,-1.1
+2017-11-16 13:00:00,365.27,-0.6
+2017-11-16 14:00:00,389.38,0.0
+2017-11-16 15:00:00,393.22,0.0
+2017-11-16 16:00:00,366.92,0.0
+2017-11-16 17:00:00,395.09,0.0
+2017-11-16 18:00:00,402.35,0.0
+2017-11-16 19:00:00,368.43,0.6
+2017-11-16 20:00:00,348.74,0.6
+2017-11-16 21:00:00,334.19,1.1
+2017-11-16 22:00:00,319.53,0.6
+2017-11-16 23:00:00,245.71,1.1
+2017-11-17 00:00:00,228.15,1.1
+2017-11-17 01:00:00,222.55,1.7
+2017-11-17 02:00:00,222.68,1.7
+2017-11-17 03:00:00,224.66,1.7
+2017-11-17 04:00:00,224.54,2.2
+2017-11-17 05:00:00,232.53,2.2
+2017-11-17 06:00:00,270.55,2.8
+2017-11-17 07:00:00,281.4,2.8
+2017-11-17 08:00:00,354.23,2.2
+2017-11-17 09:00:00,375.2,2.2
+2017-11-17 10:00:00,392.14,2.2
+2017-11-17 11:00:00,413.58,2.8
+2017-11-17 12:00:00,412.53,2.8
+2017-11-17 13:00:00,414.09,2.8
+2017-11-17 14:00:00,409.89,3.3
+2017-11-17 15:00:00,416.94,3.3
+2017-11-17 16:00:00,423.82,3.3
+2017-11-17 17:00:00,419.81,3.3
+2017-11-17 18:00:00,400.09,3.3
+2017-11-17 19:00:00,414.64,3.9
+2017-11-17 20:00:00,432.52,3.3
+2017-11-17 21:00:00,421.47,3.3
+2017-11-17 22:00:00,369.34,2.8
+2017-11-17 23:00:00,285.82,2.8
+2017-11-18 00:00:00,249.13,2.2
+2017-11-18 01:00:00,249.2,2.2
+2017-11-18 02:00:00,224.36,2.2
+2017-11-18 03:00:00,229.16,1.7
+2017-11-18 04:00:00,225.04,1.7
+2017-11-18 05:00:00,231.39,1.1
+2017-11-18 06:00:00,266.69,1.1
+2017-11-18 07:00:00,291.75,0.6
+2017-11-18 08:00:00,310.29,0.0
+2017-11-18 09:00:00,333.07,0.0
+2017-11-18 10:00:00,373.44,1.1
+2017-11-18 11:00:00,380.39,1.7
+2017-11-18 12:00:00,397.84,2.2
+2017-11-18 13:00:00,379.82,2.8
+2017-11-18 14:00:00,376.9,1.7
+2017-11-18 15:00:00,372.16,0.6
+2017-11-18 16:00:00,371.05,0.0
+2017-11-18 17:00:00,368.94,-1.7
+2017-11-18 18:00:00,372.0,-2.2
+2017-11-18 19:00:00,385.28,-3.3
+2017-11-18 20:00:00,393.3,-5.0
+2017-11-18 21:00:00,373.05,-5.6
+2017-11-18 22:00:00,357.91,-5.6
+2017-11-18 23:00:00,271.6,-6.1
+2017-11-19 00:00:00,231.33,-6.1
+2017-11-19 01:00:00,223.02,-6.7
+2017-11-19 02:00:00,219.84,-6.7
+2017-11-19 03:00:00,220.17,-7.2
+2017-11-19 04:00:00,218.36,-7.2
+2017-11-19 05:00:00,226.96,-7.8
+2017-11-19 06:00:00,222.54,-7.2
+2017-11-19 07:00:00,234.97,-7.8
+2017-11-19 08:00:00,249.0,-7.8
+2017-11-19 09:00:00,248.01,-6.1
+2017-11-19 10:00:00,250.29,-5.0
+2017-11-19 11:00:00,311.94,-2.2
+2017-11-19 12:00:00,335.24,-0.6
+2017-11-19 13:00:00,358.82,1.7
+2017-11-19 14:00:00,389.24,3.3
+2017-11-19 15:00:00,407.13,4.4
+2017-11-19 16:00:00,393.96,5.0
+2017-11-19 17:00:00,388.5,3.9
+2017-11-19 18:00:00,317.09,2.2
+2017-11-19 19:00:00,279.43,3.3
+2017-11-19 20:00:00,232.67,3.3
+2017-11-19 21:00:00,231.38,3.3
+2017-11-19 22:00:00,234.63,3.3
+2017-11-19 23:00:00,229.04,2.8
+2017-11-20 00:00:00,226.69,2.8
+2017-11-20 01:00:00,221.48,1.7
+2017-11-20 02:00:00,215.03,1.7
+2017-11-20 03:00:00,211.33,0.0
+2017-11-20 04:00:00,212.12,-1.1
+2017-11-20 05:00:00,211.38,-1.1
+2017-11-20 06:00:00,252.68,-1.7
+2017-11-20 07:00:00,260.95,-1.1
+2017-11-20 08:00:00,308.21,-1.1
+2017-11-20 09:00:00,319.33,1.1
+2017-11-20 10:00:00,333.4,2.8
+2017-11-20 11:00:00,338.4,5.6
+2017-11-20 12:00:00,341.1,6.1
+2017-11-20 13:00:00,351.27,7.2
+2017-11-20 14:00:00,357.71,7.2
+2017-11-20 15:00:00,368.02,7.8
+2017-11-20 16:00:00,366.14,8.3
+2017-11-20 17:00:00,331.85,8.3
+2017-11-20 18:00:00,313.55,8.3
+2017-11-20 19:00:00,300.91,7.2
+2017-11-20 20:00:00,299.84,6.7
+2017-11-20 21:00:00,297.82,6.1
+2017-11-20 22:00:00,284.71,6.1
+2017-11-20 23:00:00,269.13,6.1
+2017-11-21 00:00:00,242.12,5.6
+2017-11-21 01:00:00,236.22,3.9
+2017-11-21 02:00:00,244.53,2.2
+2017-11-21 03:00:00,208.66,0.6
+2017-11-21 04:00:00,207.58,-1.1
+2017-11-21 05:00:00,214.09,-2.2
+2017-11-21 06:00:00,242.9,-2.2
+2017-11-21 07:00:00,257.12,-2.8
+2017-11-21 08:00:00,303.17,-4.4
+2017-11-21 09:00:00,292.46,-5.0
+2017-11-21 10:00:00,298.76,-5.0
+2017-11-21 11:00:00,299.63,-3.9
+2017-11-21 12:00:00,313.05,-3.3
+2017-11-21 13:00:00,308.73,-2.8
+2017-11-21 14:00:00,306.95,-2.2
+2017-11-21 15:00:00,306.83,-1.7
+2017-11-21 16:00:00,312.51,-2.2
+2017-11-21 17:00:00,311.57,-3.3
+2017-11-21 18:00:00,288.89,-3.9
+2017-11-21 19:00:00,265.65,-4.4
+2017-11-21 20:00:00,259.29,-5.6
+2017-11-21 21:00:00,255.23,-6.7
+2017-11-21 22:00:00,236.82,-6.7
+2017-11-21 23:00:00,208.13,-7.2
+2017-11-22 00:00:00,192.58,-7.2
+2017-11-22 01:00:00,181.41,-7.8
+2017-11-22 02:00:00,183.35,-8.9
+2017-11-22 03:00:00,181.02,-8.9
+2017-11-22 04:00:00,181.4,-9.4
+2017-11-22 05:00:00,191.28,-8.9
+2017-11-22 06:00:00,228.64,-8.9
+2017-11-22 07:00:00,238.44,-8.9
+2017-11-22 08:00:00,265.62,-8.9
+2017-11-22 09:00:00,306.64,-7.2
+2017-11-22 10:00:00,318.43,-6.1
+2017-11-22 11:00:00,336.87,-5.0
+2017-11-22 12:00:00,343.19,-5.0
+2017-11-22 13:00:00,342.16,-4.4
+2017-11-22 14:00:00,341.47,-3.3
+2017-11-22 15:00:00,331.71,-2.8
+2017-11-22 16:00:00,317.99,-1.7
+2017-11-22 17:00:00,293.5,-1.7
+2017-11-22 18:00:00,286.8,-1.1
+2017-11-22 19:00:00,284.3,-1.1
+2017-11-22 20:00:00,285.26,-0.6
+2017-11-22 21:00:00,285.2,0.0
+2017-11-22 22:00:00,271.83,0.0
+2017-11-22 23:00:00,257.31,0.0
+2017-11-23 00:00:00,223.88,-1.1
+2017-11-23 01:00:00,215.13,-2.2
+2017-11-23 02:00:00,213.42,-2.8
+2017-11-23 03:00:00,210.68,-3.3
+2017-11-23 04:00:00,210.71,-3.3
+2017-11-23 05:00:00,211.88,-5.0
+2017-11-23 06:00:00,246.58,-5.0
+2017-11-23 07:00:00,246.87,-5.0
+2017-11-23 08:00:00,267.48,-3.3
+2017-11-23 09:00:00,262.53,-1.1
+2017-11-23 10:00:00,271.97,0.6
+2017-11-23 11:00:00,278.02,1.7
+2017-11-23 12:00:00,282.63,3.3
+2017-11-23 13:00:00,280.54,5.0
+2017-11-23 14:00:00,283.82,6.1
+2017-11-23 15:00:00,281.07,6.7
+2017-11-23 16:00:00,295.32,7.2
+2017-11-23 17:00:00,307.63,5.6
+2017-11-23 18:00:00,304.12,6.1
+2017-11-23 19:00:00,298.71,5.6
+2017-11-23 20:00:00,301.42,3.3
+2017-11-23 21:00:00,295.69,3.3
+2017-11-23 22:00:00,291.43,7.8
+2017-11-23 23:00:00,281.48,8.9
+2017-11-24 00:00:00,250.78,8.9
+2017-11-24 01:00:00,243.68,8.9
+2017-11-24 02:00:00,241.7,9.4
+2017-11-24 03:00:00,240.92,8.9
+2017-11-24 04:00:00,242.56,8.3
+2017-11-24 05:00:00,249.47,8.3
+2017-11-24 06:00:00,285.44,8.9
+2017-11-24 07:00:00,283.3,8.9
+2017-11-24 08:00:00,304.42,9.4
+2017-11-24 09:00:00,303.0,10.0
+2017-11-24 10:00:00,302.06,11.7
+2017-11-24 11:00:00,303.96,12.2
+2017-11-24 12:00:00,496.1,14.4
+2017-11-24 13:00:00,512.12,15.6
+2017-11-24 14:00:00,422.82,14.4
+2017-11-24 15:00:00,394.02,13.9
+2017-11-24 16:00:00,409.21,11.7
+2017-11-24 17:00:00,370.19,10.0
+2017-11-24 18:00:00,359.4,7.8
+2017-11-24 19:00:00,361.43,7.8
+2017-11-24 20:00:00,345.15,7.2
+2017-11-24 21:00:00,348.5,7.2
+2017-11-24 22:00:00,332.84,6.1
+2017-11-24 23:00:00,320.87,5.0
+2017-11-25 00:00:00,269.42,5.0
+2017-11-25 01:00:00,277.42,3.9
+2017-11-25 02:00:00,280.54,3.9
+2017-11-25 03:00:00,278.61,3.3
+2017-11-25 04:00:00,285.52,2.8
+2017-11-25 05:00:00,285.65,2.2
+2017-11-25 06:00:00,285.79,1.1
+2017-11-25 07:00:00,298.24,0.6
+2017-11-25 08:00:00,311.75,0.6
+2017-11-25 09:00:00,348.63,1.1
+2017-11-25 10:00:00,334.35,1.7
+2017-11-25 11:00:00,351.75,2.8
+2017-11-25 12:00:00,346.38,2.8
+2017-11-25 13:00:00,347.5,3.9
+2017-11-25 14:00:00,344.47,4.4
+2017-11-25 15:00:00,336.39,3.9
+2017-11-25 16:00:00,344.91,3.9
+2017-11-25 17:00:00,348.56,2.2
+2017-11-25 18:00:00,367.81,1.7
+2017-11-25 19:00:00,334.65,0.6
+2017-11-25 20:00:00,325.91,-0.6
+2017-11-25 21:00:00,320.49,-1.1
+2017-11-25 22:00:00,307.39,-0.6
+2017-11-25 23:00:00,284.18,-1.7
+2017-11-26 00:00:00,311.59,-1.7
+2017-11-26 01:00:00,281.22,-2.2
+2017-11-26 02:00:00,267.51,-2.2
+2017-11-26 03:00:00,266.73,-2.8
+2017-11-26 04:00:00,273.94,-2.8
+2017-11-26 05:00:00,287.94,-2.2
+2017-11-26 06:00:00,280.26,-1.1
+2017-11-26 07:00:00,277.64,-1.1
+2017-11-26 08:00:00,281.09,0.6
+2017-11-26 09:00:00,312.28,2.2
+2017-11-26 10:00:00,313.55,3.9
+2017-11-26 11:00:00,319.09,5.6
+2017-11-26 12:00:00,311.18,7.8
+2017-11-26 13:00:00,316.07,10.0
+2017-11-26 14:00:00,331.2,9.4
+2017-11-26 15:00:00,421.68,9.4
+2017-11-26 16:00:00,407.9,8.9
+2017-11-26 17:00:00,397.41,8.3
+2017-11-26 18:00:00,372.58,7.8
+2017-11-26 19:00:00,355.25,7.2
+2017-11-26 20:00:00,312.54,6.1
+2017-11-26 21:00:00,309.79,6.7
+2017-11-26 22:00:00,308.25,5.0
+2017-11-26 23:00:00,306.15,3.3
+2017-11-27 00:00:00,318.17,2.2
+2017-11-27 01:00:00,287.14,2.8
+2017-11-27 02:00:00,304.46,1.1
+2017-11-27 03:00:00,299.61,0.6
+2017-11-27 04:00:00,297.44,0.0
+2017-11-27 05:00:00,301.91,1.1
+2017-11-27 06:00:00,341.88,2.2
+2017-11-27 07:00:00,349.3,2.2
+2017-11-27 08:00:00,375.47,2.8
+2017-11-27 09:00:00,372.05,4.4
+2017-11-27 10:00:00,392.71,6.7
+2017-11-27 11:00:00,401.98,10.0
+2017-11-27 12:00:00,445.34,12.8
+2017-11-27 13:00:00,465.69,14.4
+2017-11-27 14:00:00,500.27,15.6
+2017-11-27 15:00:00,547.32,15.6
+2017-11-27 16:00:00,525.05,15.0
+2017-11-27 17:00:00,520.54,13.9
+2017-11-27 18:00:00,482.39,12.8
+2017-11-27 19:00:00,460.42,12.8
+2017-11-27 20:00:00,423.89,12.8
+2017-11-27 21:00:00,417.69,13.9
+2017-11-27 22:00:00,414.04,13.9
+2017-11-27 23:00:00,402.45,12.8
+2017-11-28 00:00:00,370.52,11.7
+2017-11-28 01:00:00,338.88,10.6
+2017-11-28 02:00:00,325.76,9.4
+2017-11-28 03:00:00,305.88,8.9
+2017-11-28 04:00:00,310.14,7.8
+2017-11-28 05:00:00,309.82,7.8
+2017-11-28 06:00:00,345.05,7.2
+2017-11-28 07:00:00,354.85,7.2
+2017-11-28 08:00:00,369.69,7.2
+2017-11-28 09:00:00,383.1,7.2
+2017-11-28 10:00:00,406.82,7.8
+2017-11-28 11:00:00,405.69,7.2
+2017-11-28 12:00:00,410.43,10.6
+2017-11-28 13:00:00,406.24,11.7
+2017-11-28 14:00:00,429.54,11.1
+2017-11-28 15:00:00,429.91,10.0
+2017-11-28 16:00:00,408.4,8.9
+2017-11-28 17:00:00,406.69,7.8
+2017-11-28 18:00:00,394.76,6.7
+2017-11-28 19:00:00,385.49,5.6
+2017-11-28 20:00:00,360.66,5.0
+2017-11-28 21:00:00,346.78,3.3
+2017-11-28 22:00:00,345.72,3.3
+2017-11-28 23:00:00,314.45,1.7
+2017-11-29 00:00:00,299.81,1.1
+2017-11-29 01:00:00,296.58,0.0
+2017-11-29 02:00:00,294.45,0.0
+2017-11-29 03:00:00,293.72,-1.7
+2017-11-29 04:00:00,260.31,-1.7
+2017-11-29 05:00:00,327.31,-2.8
+2017-11-29 06:00:00,345.83,-1.7
+2017-11-29 07:00:00,345.75,-2.2
+2017-11-29 08:00:00,384.44,-3.3
+2017-11-29 09:00:00,408.4,-1.1
+2017-11-29 10:00:00,418.78,0.6
+2017-11-29 11:00:00,414.5,2.8
+2017-11-29 12:00:00,409.64,3.9
+2017-11-29 13:00:00,391.91,6.1
+2017-11-29 14:00:00,381.0,7.2
+2017-11-29 15:00:00,395.35,7.8
+2017-11-29 16:00:00,418.1,6.7
+2017-11-29 17:00:00,400.3,6.1
+2017-11-29 18:00:00,386.5,5.0
+2017-11-29 19:00:00,343.54,5.0
+2017-11-29 20:00:00,346.19,5.6
+2017-11-29 21:00:00,343.28,6.1
+2017-11-29 22:00:00,317.1,6.7
+2017-11-29 23:00:00,286.43,6.1
+2017-11-30 00:00:00,289.8,6.1
+2017-11-30 01:00:00,284.17,6.7
+2017-11-30 02:00:00,278.87,6.1
+2017-11-30 03:00:00,281.66,5.6
+2017-11-30 04:00:00,278.83,4.4
+2017-11-30 05:00:00,291.01,3.9
+2017-11-30 06:00:00,337.66,3.3
+2017-11-30 07:00:00,335.02,3.3
+2017-11-30 08:00:00,367.95,2.8
+2017-11-30 09:00:00,404.26,3.3
+2017-11-30 10:00:00,429.09,5.0
+2017-11-30 11:00:00,434.67,6.1
+2017-11-30 12:00:00,428.68,7.2
+2017-11-30 13:00:00,414.97,7.8
+2017-11-30 14:00:00,416.93,8.3
+2017-11-30 15:00:00,421.94,8.3
+2017-11-30 16:00:00,420.38,7.8
+2017-11-30 17:00:00,419.91,6.1
+2017-11-30 18:00:00,384.57,5.0
+2017-11-30 19:00:00,378.96,5.0
+2017-11-30 20:00:00,379.14,4.4
+2017-11-30 21:00:00,371.58,3.3
+2017-11-30 22:00:00,360.08,3.3
+2017-11-30 23:00:00,326.6,2.2
+2017-12-01 00:00:00,312.87,0.0
+2017-12-01 01:00:00,308.62,-0.6
+2017-12-01 02:00:00,307.94,-1.7
+2017-12-01 03:00:00,306.31,-1.7
+2017-12-01 04:00:00,304.73,-1.7
+2017-12-01 05:00:00,309.8,-1.7
+2017-12-01 06:00:00,348.11,-1.1
+2017-12-01 07:00:00,357.2,-0.6
+2017-12-01 08:00:00,379.4,0.0
+2017-12-01 09:00:00,382.53,1.1
+2017-12-01 10:00:00,396.35,3.3
+2017-12-01 11:00:00,396.9,7.2
+2017-12-01 12:00:00,396.15,9.4
+2017-12-01 13:00:00,390.74,10.0
+2017-12-01 14:00:00,398.11,10.0
+2017-12-01 15:00:00,418.73,10.6
+2017-12-01 16:00:00,411.64,10.0
+2017-12-01 17:00:00,402.48,8.9
+2017-12-01 18:00:00,384.86,8.9
+2017-12-01 19:00:00,358.45,7.8
+2017-12-01 20:00:00,367.67,6.7
+2017-12-01 21:00:00,340.68,6.1
+2017-12-01 22:00:00,339.78,6.1
+2017-12-01 23:00:00,302.33,4.4
+2017-12-02 00:00:00,279.61,3.3
+2017-12-02 01:00:00,273.53,1.7
+2017-12-02 02:00:00,283.65,1.1
+2017-12-02 03:00:00,280.88,0.6
+2017-12-02 04:00:00,295.05,0.0
+2017-12-02 05:00:00,288.85,0.0
+2017-12-02 06:00:00,296.29,-0.6
+2017-12-02 07:00:00,294.36,-0.6
+2017-12-02 08:00:00,301.71,-1.1
+2017-12-02 09:00:00,330.31,0.0
+2017-12-02 10:00:00,340.58,1.7
+2017-12-02 11:00:00,357.22,3.3
+2017-12-02 12:00:00,341.21,5.6
+2017-12-02 13:00:00,349.71,7.2
+2017-12-02 14:00:00,345.53,7.2
+2017-12-02 15:00:00,359.76,8.3
+2017-12-02 16:00:00,350.78,7.8
+2017-12-02 17:00:00,342.1,6.1
+2017-12-02 18:00:00,345.33,5.6
+2017-12-02 19:00:00,326.48,5.0
+2017-12-02 20:00:00,313.53,3.9
+2017-12-02 21:00:00,314.75,2.2
+2017-12-02 22:00:00,297.76,1.1
+2017-12-02 23:00:00,292.75,0.6
+2017-12-03 00:00:00,289.12,-0.6
+2017-12-03 01:00:00,278.89,0.0
+2017-12-03 02:00:00,290.29,-1.7
+2017-12-03 03:00:00,289.73,-1.1
+2017-12-03 04:00:00,284.49,0.0
+2017-12-03 05:00:00,293.34,0.0
+2017-12-03 06:00:00,292.76,-0.6
+2017-12-03 07:00:00,293.69,-0.6
+2017-12-03 08:00:00,291.92,1.7
+2017-12-03 09:00:00,336.5,2.8
+2017-12-03 10:00:00,320.42,3.3
+2017-12-03 11:00:00,324.44,5.0
+2017-12-03 12:00:00,341.05,7.2
+2017-12-03 13:00:00,358.35,7.8
+2017-12-03 14:00:00,349.04,8.3
+2017-12-03 15:00:00,341.88,8.9
+2017-12-03 16:00:00,405.49,8.9
+2017-12-03 17:00:00,388.06,8.3
+2017-12-03 18:00:00,360.47,8.3
+2017-12-03 19:00:00,340.24,8.3
+2017-12-03 20:00:00,336.67,8.3
+2017-12-03 21:00:00,369.26,8.9
+2017-12-03 22:00:00,342.05,8.9
+2017-12-03 23:00:00,320.38,10.0
+2017-12-04 00:00:00,317.48,10.0
+2017-12-04 01:00:00,348.09,10.6
+2017-12-04 02:00:00,287.22,10.6
+2017-12-04 03:00:00,350.05,10.6
+2017-12-04 04:00:00,332.96,11.7
+2017-12-04 05:00:00,325.35,11.7
+2017-12-04 06:00:00,365.0,11.7
+2017-12-04 07:00:00,370.13,11.7
+2017-12-04 08:00:00,510.83,11.7
+2017-12-04 09:00:00,543.2,11.7
+2017-12-04 10:00:00,532.49,12.2
+2017-12-04 11:00:00,569.73,12.8
+2017-12-04 12:00:00,563.76,13.9
+2017-12-04 13:00:00,556.67,13.3
+2017-12-04 14:00:00,595.24,13.9
+2017-12-04 15:00:00,635.95,13.3
+2017-12-04 16:00:00,553.83,12.2
+2017-12-04 17:00:00,592.3,9.4
+2017-12-04 18:00:00,503.31,6.1
+2017-12-04 19:00:00,379.14,4.4
+2017-12-04 20:00:00,349.53,2.8
+2017-12-04 21:00:00,373.79,1.1
+2017-12-04 22:00:00,377.37,-0.6
+2017-12-04 23:00:00,356.55,-2.2
+2017-12-05 00:00:00,318.41,-2.8
+2017-12-05 01:00:00,294.43,-3.9
+2017-12-05 02:00:00,287.64,-5.0
+2017-12-05 03:00:00,284.28,-5.6
+2017-12-05 04:00:00,287.18,-5.6
+2017-12-05 05:00:00,281.51,-6.1
+2017-12-05 06:00:00,347.7,-7.8
+2017-12-05 07:00:00,329.42,-8.3
+2017-12-05 08:00:00,381.46,-8.9
+2017-12-05 09:00:00,407.95,-8.3
+2017-12-05 10:00:00,340.04,-8.3
+2017-12-05 11:00:00,330.48,-7.8
+2017-12-05 12:00:00,326.13,-7.2
+2017-12-05 13:00:00,315.42,-6.7
+2017-12-05 14:00:00,314.57,-6.7
+2017-12-05 15:00:00,315.14,-6.7
+2017-12-05 16:00:00,311.92,-6.1
+2017-12-05 17:00:00,315.28,-6.1
+2017-12-05 18:00:00,310.94,-6.7
+2017-12-05 19:00:00,294.65,-6.7
+2017-12-05 20:00:00,260.64,-6.7
+2017-12-05 21:00:00,258.27,-6.7
+2017-12-05 22:00:00,240.19,-7.2
+2017-12-05 23:00:00,206.74,-7.2
+2017-12-06 00:00:00,194.71,-7.8
+2017-12-06 01:00:00,189.09,-7.8
+2017-12-06 02:00:00,187.25,-7.8
+2017-12-06 03:00:00,184.16,-8.3
+2017-12-06 04:00:00,189.16,-8.3
+2017-12-06 05:00:00,196.6,-8.3
+2017-12-06 06:00:00,233.85,-8.9
+2017-12-06 07:00:00,248.69,-8.9
+2017-12-06 08:00:00,283.69,-8.9
+2017-12-06 09:00:00,316.39,-8.3
+2017-12-06 10:00:00,308.58,-7.8
+2017-12-06 11:00:00,311.51,-7.2
+2017-12-06 12:00:00,310.84,-7.2
+2017-12-06 13:00:00,308.92,-7.2
+2017-12-06 14:00:00,309.99,-6.7
+2017-12-06 15:00:00,313.24,-8.3
+2017-12-06 16:00:00,315.7,-8.9
+2017-12-06 17:00:00,318.9,-8.9
+2017-12-06 18:00:00,311.83,-8.3
+2017-12-06 19:00:00,276.69,-7.8
+2017-12-06 20:00:00,270.58,-7.8
+2017-12-06 21:00:00,263.89,-7.8
+2017-12-06 22:00:00,248.46,-7.8
+2017-12-06 23:00:00,205.07,-7.8
+2017-12-07 00:00:00,201.87,-8.9
+2017-12-07 01:00:00,196.61,-9.4
+2017-12-07 02:00:00,195.31,-10.0
+2017-12-07 03:00:00,195.68,-10.6
+2017-12-07 04:00:00,194.52,-11.1
+2017-12-07 05:00:00,200.5,-12.2
+2017-12-07 06:00:00,226.6,-12.8
+2017-12-07 07:00:00,227.66,-13.3
+2017-12-07 08:00:00,275.27,-13.3
+2017-12-07 09:00:00,298.69,-12.2
+2017-12-07 10:00:00,311.95,-11.1
+2017-12-07 11:00:00,328.51,-10.0
+2017-12-07 12:00:00,337.23,-9.4
+2017-12-07 13:00:00,325.5,-8.9
+2017-12-07 14:00:00,325.88,-8.3
+2017-12-07 15:00:00,327.76,-8.3
+2017-12-07 16:00:00,322.77,-8.3
+2017-12-07 17:00:00,323.56,-8.3
+2017-12-07 18:00:00,323.46,-7.8
+2017-12-07 19:00:00,322.24,-6.7
+2017-12-07 20:00:00,283.41,-6.7
+2017-12-07 21:00:00,279.26,-6.7
+2017-12-07 22:00:00,260.81,-6.1
+2017-12-07 23:00:00,216.04,-6.1
+2017-12-08 00:00:00,200.18,-6.1
+2017-12-08 01:00:00,186.99,-5.6
+2017-12-08 02:00:00,182.53,-6.1
+2017-12-08 03:00:00,190.9,-6.1
+2017-12-08 04:00:00,188.54,-6.1
+2017-12-08 05:00:00,195.92,-6.1
+2017-12-08 06:00:00,236.56,-6.7
+2017-12-08 07:00:00,249.01,-6.1
+2017-12-08 08:00:00,294.79,-5.0
+2017-12-08 09:00:00,320.29,-4.4
+2017-12-08 10:00:00,325.39,-4.4
+2017-12-08 11:00:00,332.32,-2.8
+2017-12-08 12:00:00,335.02,-2.8
+2017-12-08 13:00:00,323.51,-2.2
+2017-12-08 14:00:00,294.5,-2.2
+2017-12-08 15:00:00,359.13,-2.2
+2017-12-08 16:00:00,370.81,-1.7
+2017-12-08 17:00:00,328.91,-2.2
+2017-12-08 18:00:00,324.63,-1.7
+2017-12-08 19:00:00,297.94,-1.7
+2017-12-08 20:00:00,282.36,-0.6
+2017-12-08 21:00:00,279.5,-0.6
+2017-12-08 22:00:00,256.0,-0.6
+2017-12-08 23:00:00,233.65,-0.6
+2017-12-09 00:00:00,199.96,-1.1
+2017-12-09 01:00:00,188.55,-2.8
+2017-12-09 02:00:00,184.83,-3.9
+2017-12-09 03:00:00,187.22,-4.4
+2017-12-09 04:00:00,185.2,-5.0
+2017-12-09 05:00:00,190.69,-5.0
+2017-12-09 06:00:00,189.12,-6.1
+2017-12-09 07:00:00,187.94,-6.7
+2017-12-09 08:00:00,194.55,-6.7
+2017-12-09 09:00:00,234.69,-7.2
+2017-12-09 10:00:00,270.24,-7.2
+2017-12-09 11:00:00,285.18,-6.7
+2017-12-09 12:00:00,288.34,-6.7
+2017-12-09 13:00:00,285.3,-6.1
+2017-12-09 14:00:00,291.73,-5.6
+2017-12-09 15:00:00,265.42,-6.1
+2017-12-09 16:00:00,249.14,-5.6
+2017-12-09 17:00:00,257.86,-6.1
+2017-12-09 18:00:00,269.66,-5.6
+2017-12-09 19:00:00,269.89,-5.6
+2017-12-09 20:00:00,263.01,-5.6
+2017-12-09 21:00:00,261.68,-5.6
+2017-12-09 22:00:00,238.61,-5.0
+2017-12-09 23:00:00,228.49,-4.4
+2017-12-10 00:00:00,226.37,-5.0
+2017-12-10 01:00:00,219.34,-5.0
+2017-12-10 02:00:00,221.53,-6.1
+2017-12-10 03:00:00,217.38,-6.1
+2017-12-10 04:00:00,220.64,-6.7
+2017-12-10 05:00:00,229.43,-5.0
+2017-12-10 06:00:00,235.53,-4.4
+2017-12-10 07:00:00,236.83,-3.3
+2017-12-10 08:00:00,242.54,-3.3
+2017-12-10 09:00:00,243.08,-2.8
+2017-12-10 10:00:00,238.96,-2.2
+2017-12-10 11:00:00,252.08,-2.2
+2017-12-10 12:00:00,252.95,-2.2
+2017-12-10 13:00:00,250.86,-1.7
+2017-12-10 14:00:00,254.6,-1.7
+2017-12-10 15:00:00,252.68,-1.7
+2017-12-10 16:00:00,253.03,-1.7
+2017-12-10 17:00:00,256.1,-2.8
+2017-12-10 18:00:00,251.86,-2.8
+2017-12-10 19:00:00,232.54,-3.9
+2017-12-10 20:00:00,215.15,-2.8
+2017-12-10 21:00:00,209.11,-3.9
+2017-12-10 22:00:00,196.15,-4.4
+2017-12-10 23:00:00,195.44,-3.9
+2017-12-11 00:00:00,195.94,-3.9
+2017-12-11 01:00:00,185.89,-3.3
+2017-12-11 02:00:00,184.99,-3.9
+2017-12-11 03:00:00,187.39,-3.3
+2017-12-11 04:00:00,187.52,-2.8
+2017-12-11 05:00:00,197.15,-2.2
+2017-12-11 06:00:00,234.66,-1.7
+2017-12-11 07:00:00,242.01,-1.7
+2017-12-11 08:00:00,295.77,-0.6
+2017-12-11 09:00:00,326.33,-0.6
+2017-12-11 10:00:00,328.08,0.6
+2017-12-11 11:00:00,335.04,1.1
+2017-12-11 12:00:00,332.4,1.7
+2017-12-11 13:00:00,326.24,1.7
+2017-12-11 14:00:00,326.7,1.1
+2017-12-11 15:00:00,324.43,1.1
+2017-12-11 16:00:00,319.91,-0.6
+2017-12-11 17:00:00,307.31,-1.7
+2017-12-11 18:00:00,302.48,-2.8
+2017-12-11 19:00:00,271.39,-3.9
+2017-12-11 20:00:00,250.74,-5.6
+2017-12-11 21:00:00,245.92,-6.1
+2017-12-11 22:00:00,237.97,-6.7
+2017-12-11 23:00:00,195.36,-7.8
+2017-12-12 00:00:00,191.91,-8.9
+2017-12-12 01:00:00,181.34,-10.6
+2017-12-12 02:00:00,177.19,-11.1
+2017-12-12 03:00:00,177.56,-12.2
+2017-12-12 04:00:00,177.69,-12.8
+2017-12-12 05:00:00,183.11,-13.3
+2017-12-12 06:00:00,219.89,-13.9
+2017-12-12 07:00:00,250.92,-14.4
+2017-12-12 08:00:00,308.48,-13.9
+2017-12-12 09:00:00,366.17,-12.8
+2017-12-12 10:00:00,368.82,-11.1
+2017-12-12 11:00:00,373.62,-10.6
+2017-12-12 12:00:00,358.89,-9.4
+2017-12-12 13:00:00,349.75,-8.9
+2017-12-12 14:00:00,355.15,-7.8
+2017-12-12 15:00:00,353.3,-7.2
+2017-12-12 16:00:00,349.41,-6.7
+2017-12-12 17:00:00,328.34,-6.1
+2017-12-12 18:00:00,330.54,-6.7
+2017-12-12 19:00:00,345.07,-6.1
+2017-12-12 20:00:00,304.76,-5.0
+2017-12-12 21:00:00,296.02,-4.4
+2017-12-12 22:00:00,279.73,-3.9
+2017-12-12 23:00:00,219.27,-3.3
+2017-12-13 00:00:00,210.84,-3.3
+2017-12-13 01:00:00,204.35,-3.3
+2017-12-13 02:00:00,205.2,-2.2
+2017-12-13 03:00:00,203.58,-1.7
+2017-12-13 04:00:00,201.09,-2.2
+2017-12-13 05:00:00,207.9,-2.2
+2017-12-13 06:00:00,247.69,-1.1
+2017-12-13 07:00:00,244.17,-2.8
+2017-12-13 08:00:00,278.84,-2.2
+2017-12-13 09:00:00,328.2,-3.3
+2017-12-13 10:00:00,343.98,-3.3
+2017-12-13 11:00:00,339.02,-2.8
+2017-12-13 12:00:00,336.31,-3.9
+2017-12-13 13:00:00,333.58,-4.4
+2017-12-13 14:00:00,330.8,-3.9
+2017-12-13 15:00:00,338.32,-4.4
+2017-12-13 16:00:00,345.11,-4.4
+2017-12-13 17:00:00,349.17,-4.4
+2017-12-13 18:00:00,342.71,-4.4
+2017-12-13 19:00:00,330.34,-5.0
+2017-12-13 20:00:00,277.14,-6.1
+2017-12-13 21:00:00,270.46,-6.7
+2017-12-13 22:00:00,251.54,-7.2
+2017-12-13 23:00:00,200.43,-7.8
+2017-12-14 00:00:00,198.15,-8.3
+2017-12-14 01:00:00,194.68,-7.8
+2017-12-14 02:00:00,193.66,-6.7
+2017-12-14 03:00:00,194.94,-6.7
+2017-12-14 04:00:00,194.19,-7.2
+2017-12-14 05:00:00,200.85,-7.2
+2017-12-14 06:00:00,237.1,-8.3
+2017-12-14 07:00:00,241.06,-8.3
+2017-12-14 08:00:00,264.23,-8.9
+2017-12-14 09:00:00,308.38,-7.8
+2017-12-14 10:00:00,321.92,-7.2
+2017-12-14 11:00:00,347.22,-6.7
+2017-12-14 12:00:00,321.53,-6.1
+2017-12-14 13:00:00,314.81,-6.1
+2017-12-14 14:00:00,306.73,-5.6
+2017-12-14 15:00:00,326.22,-5.6
+2017-12-14 16:00:00,327.33,-5.0
+2017-12-14 17:00:00,325.36,-5.6
+2017-12-14 18:00:00,322.59,-5.6
+2017-12-14 19:00:00,282.78,-5.0
+2017-12-14 20:00:00,274.71,-5.0
+2017-12-14 21:00:00,274.8,-5.0
+2017-12-14 22:00:00,262.01,-5.0
+2017-12-14 23:00:00,220.64,-5.0
+2017-12-15 00:00:00,212.75,-5.0
+2017-12-15 01:00:00,203.73,-5.0
+2017-12-15 02:00:00,197.35,-5.0
+2017-12-15 03:00:00,199.68,-5.0
+2017-12-15 04:00:00,203.01,-4.4
+2017-12-15 05:00:00,206.34,-4.4
+2017-12-15 06:00:00,244.78,-4.4
+2017-12-15 07:00:00,246.89,-5.6
+2017-12-15 08:00:00,283.79,-5.0
+2017-12-15 09:00:00,301.89,-4.4
+2017-12-15 10:00:00,320.18,-3.9
+2017-12-15 11:00:00,332.34,-3.9
+2017-12-15 12:00:00,322.74,-3.9
+2017-12-15 13:00:00,331.16,-3.3
+2017-12-15 14:00:00,338.32,-2.8
+2017-12-15 15:00:00,336.55,-2.8
+2017-12-15 16:00:00,326.98,-2.2
+2017-12-15 17:00:00,300.74,-2.8
+2017-12-15 18:00:00,275.7,-2.8
+2017-12-15 19:00:00,267.23,-2.8
+2017-12-15 20:00:00,263.4,-2.8
+2017-12-15 21:00:00,259.41,-2.8
+2017-12-15 22:00:00,248.7,-2.2
+2017-12-15 23:00:00,219.5,-1.7
+2017-12-16 00:00:00,204.63,-1.1
+2017-12-16 01:00:00,203.42,-1.1
+2017-12-16 02:00:00,200.54,-0.6
+2017-12-16 03:00:00,198.45,-1.1
+2017-12-16 04:00:00,193.73,-2.2
+2017-12-16 05:00:00,201.0,-2.8
+2017-12-16 06:00:00,217.48,-2.8
+2017-12-16 07:00:00,234.7,-3.3
+2017-12-16 08:00:00,251.78,-3.9
+2017-12-16 09:00:00,264.81,-3.9
+2017-12-16 10:00:00,257.23,-3.3
+2017-12-16 11:00:00,277.92,-2.2
+2017-12-16 12:00:00,299.56,-2.2
+2017-12-16 13:00:00,301.26,-2.2
+2017-12-16 14:00:00,310.94,-1.7
+2017-12-16 15:00:00,306.78,-1.7
+2017-12-16 16:00:00,310.76,-1.7
+2017-12-16 17:00:00,298.75,-2.2
+2017-12-16 18:00:00,272.09,-2.8
+2017-12-16 19:00:00,257.51,-3.3
+2017-12-16 20:00:00,255.46,-3.3
+2017-12-16 21:00:00,248.28,-3.3
+2017-12-16 22:00:00,230.71,-3.9
+2017-12-16 23:00:00,221.51,-5.0
+2017-12-17 00:00:00,220.49,-5.0
+2017-12-17 01:00:00,211.63,-6.1
+2017-12-17 02:00:00,210.78,-6.7
+2017-12-17 03:00:00,208.23,-7.2
+2017-12-17 04:00:00,210.99,-6.7
+2017-12-17 05:00:00,223.68,-5.6
+2017-12-17 06:00:00,226.28,-6.1
+2017-12-17 07:00:00,226.27,-5.6
+2017-12-17 08:00:00,227.72,-5.0
+2017-12-17 09:00:00,233.23,-4.4
+2017-12-17 10:00:00,232.69,-4.4
+2017-12-17 11:00:00,244.54,-3.9
+2017-12-17 12:00:00,246.84,-2.8
+2017-12-17 13:00:00,251.43,-2.8
+2017-12-17 14:00:00,252.03,-2.2
+2017-12-17 15:00:00,251.07,-2.8
+2017-12-17 16:00:00,251.48,-2.2
+2017-12-17 17:00:00,258.37,-2.2
+2017-12-17 18:00:00,258.41,-2.2
+2017-12-17 19:00:00,255.48,-2.8
+2017-12-17 20:00:00,256.58,-2.8
+2017-12-17 21:00:00,255.29,-2.8
+2017-12-17 22:00:00,240.53,-2.8
+2017-12-17 23:00:00,240.58,-2.8
+2017-12-18 00:00:00,237.88,-3.3
+2017-12-18 01:00:00,230.04,-3.3
+2017-12-18 02:00:00,227.6,-3.3
+2017-12-18 03:00:00,229.23,-3.3
+2017-12-18 04:00:00,224.35,-3.9
+2017-12-18 05:00:00,235.72,-3.3
+2017-12-18 06:00:00,239.64,-3.3
+2017-12-18 07:00:00,247.1,-2.2
+2017-12-18 08:00:00,275.13,-3.9
+2017-12-18 09:00:00,302.82,-1.7
+2017-12-18 10:00:00,310.23,-0.6
+2017-12-18 11:00:00,322.23,1.1
+2017-12-18 12:00:00,340.97,1.7
+2017-12-18 13:00:00,342.5,2.2
+2017-12-18 14:00:00,330.44,2.2
+2017-12-18 15:00:00,322.42,2.8
+2017-12-18 16:00:00,303.28,3.9
+2017-12-18 17:00:00,328.14,3.9
+2017-12-18 18:00:00,315.88,5.0
+2017-12-18 19:00:00,312.96,5.6
+2017-12-18 20:00:00,311.24,5.6
+2017-12-18 21:00:00,305.4,5.0
+2017-12-18 22:00:00,290.67,3.9
+2017-12-18 23:00:00,249.84,2.8
+2017-12-19 00:00:00,247.58,2.2
+2017-12-19 01:00:00,241.69,2.2
+2017-12-19 02:00:00,235.45,2.2
+2017-12-19 03:00:00,245.36,2.8
+2017-12-19 04:00:00,248.64,2.8
+2017-12-19 05:00:00,249.16,2.2
+2017-12-19 06:00:00,279.8,1.1
+2017-12-19 07:00:00,281.12,0.6
+2017-12-19 08:00:00,305.49,0.0
+2017-12-19 09:00:00,308.49,0.6
+2017-12-19 10:00:00,310.0,1.1
+2017-12-19 11:00:00,329.59,1.7
+2017-12-19 12:00:00,315.46,1.7
+2017-12-19 13:00:00,305.68,1.7
+2017-12-19 14:00:00,306.1,1.1
+2017-12-19 15:00:00,324.99,1.1
+2017-12-19 16:00:00,312.73,0.0
+2017-12-19 17:00:00,290.27,-1.1
+2017-12-19 18:00:00,280.38,-1.1
+2017-12-19 19:00:00,273.64,-2.2
+2017-12-19 20:00:00,270.71,-2.8
+2017-12-19 21:00:00,267.1,-3.3
+2017-12-19 22:00:00,251.87,-3.9
+2017-12-19 23:00:00,213.18,-4.4
+2017-12-20 00:00:00,199.66,-4.4
+2017-12-20 01:00:00,189.16,-5.0
+2017-12-20 02:00:00,182.39,-5.0
+2017-12-20 03:00:00,178.03,-5.6
+2017-12-20 04:00:00,187.3,-6.1
+2017-12-20 05:00:00,215.6,-7.2
+2017-12-20 06:00:00,250.24,-7.2
+2017-12-20 07:00:00,258.83,-7.8
+2017-12-20 08:00:00,285.72,-7.8
+2017-12-20 09:00:00,316.69,-7.8
+2017-12-20 10:00:00,329.2,-7.2
+2017-12-20 11:00:00,327.62,-7.2
+2017-12-20 12:00:00,331.81,-7.2
+2017-12-20 13:00:00,309.61,-7.2
+2017-12-20 14:00:00,331.53,-7.8
+2017-12-20 15:00:00,331.18,-7.8
+2017-12-20 16:00:00,328.42,-7.2
+2017-12-20 17:00:00,321.69,-7.2
+2017-12-20 18:00:00,300.34,-7.2
+2017-12-20 19:00:00,292.54,-7.2
+2017-12-20 20:00:00,291.27,-6.7
+2017-12-20 21:00:00,287.24,-7.2
+2017-12-20 22:00:00,270.1,-7.2
+2017-12-20 23:00:00,224.11,-7.2
+2017-12-21 00:00:00,220.86,-7.2
+2017-12-21 01:00:00,215.5,-6.7
+2017-12-21 02:00:00,217.17,-6.7
+2017-12-21 03:00:00,215.5,-6.7
+2017-12-21 04:00:00,215.89,-6.7
+2017-12-21 05:00:00,220.17,-6.7
+2017-12-21 06:00:00,256.9,-6.7
+2017-12-21 07:00:00,261.2,-6.1
+2017-12-21 08:00:00,294.45,-6.1
+2017-12-21 09:00:00,303.44,-6.1
+2017-12-21 10:00:00,319.36,-6.1
+2017-12-21 11:00:00,330.61,-6.1
+2017-12-21 12:00:00,334.71,-5.6
+2017-12-21 13:00:00,337.2,-5.0
+2017-12-21 14:00:00,316.87,-5.0
+2017-12-21 15:00:00,310.47,-5.0
+2017-12-21 16:00:00,310.47,-5.0
+2017-12-21 17:00:00,308.8,-5.0
+2017-12-21 18:00:00,296.82,-5.0
+2017-12-21 19:00:00,294.49,-5.0
+2017-12-21 20:00:00,290.35,-5.6
+2017-12-21 21:00:00,294.75,-5.0
+2017-12-21 22:00:00,279.12,-5.6
+2017-12-21 23:00:00,246.02,-5.6
+2017-12-22 00:00:00,229.76,-6.1
+2017-12-22 01:00:00,222.75,-6.1
+2017-12-22 02:00:00,219.52,-7.2
+2017-12-22 03:00:00,220.14,-7.8
+2017-12-22 04:00:00,219.96,-7.8
+2017-12-22 05:00:00,229.02,-7.2
+2017-12-22 06:00:00,261.11,-7.2
+2017-12-22 07:00:00,270.66,-7.2
+2017-12-22 08:00:00,314.18,-7.2
+2017-12-22 09:00:00,316.95,-7.2
+2017-12-22 10:00:00,323.09,-6.7
+2017-12-22 11:00:00,323.51,-6.1
+2017-12-22 12:00:00,319.99,-5.0
+2017-12-22 13:00:00,323.42,-5.0
+2017-12-22 14:00:00,322.32,-3.9
+2017-12-22 15:00:00,298.66,-3.3
+2017-12-22 16:00:00,293.73,-3.9
+2017-12-22 17:00:00,296.62,-3.9
+2017-12-22 18:00:00,293.37,-4.4
+2017-12-22 19:00:00,289.68,-5.0
+2017-12-22 20:00:00,290.41,-6.1
+2017-12-22 21:00:00,294.75,-5.0
+2017-12-22 22:00:00,277.23,-4.4
+2017-12-22 23:00:00,261.06,-5.6
+2017-12-23 00:00:00,232.09,-6.7
+2017-12-23 01:00:00,225.61,-8.9
+2017-12-23 02:00:00,224.56,-10.0
+2017-12-23 03:00:00,223.46,-9.4
+2017-12-23 04:00:00,226.21,-9.4
+2017-12-23 05:00:00,231.39,-11.1
+2017-12-23 06:00:00,229.32,-11.1
+2017-12-23 07:00:00,227.19,-11.1
+2017-12-23 08:00:00,236.11,-11.1
+2017-12-23 09:00:00,265.11,-10.6
+2017-12-23 10:00:00,265.62,-10.0
+2017-12-23 11:00:00,280.74,-8.3
+2017-12-23 12:00:00,284.64,-7.2
+2017-12-23 13:00:00,289.81,-6.1
+2017-12-23 14:00:00,292.52,-5.6
+2017-12-23 15:00:00,277.27,-5.0
+2017-12-23 16:00:00,259.75,-5.6
+2017-12-23 17:00:00,265.35,-5.6
+2017-12-23 18:00:00,264.6,-6.7
+2017-12-23 19:00:00,252.76,-6.7
+2017-12-23 20:00:00,228.3,-7.8
+2017-12-23 21:00:00,225.43,-8.3
+2017-12-23 22:00:00,211.21,-8.3
+2017-12-23 23:00:00,201.43,-8.3
+2017-12-24 00:00:00,197.82,-8.9
+2017-12-24 01:00:00,186.3,-8.9
+2017-12-24 02:00:00,187.49,-8.3
+2017-12-24 03:00:00,189.26,-8.3
+2017-12-24 04:00:00,184.73,-8.9
+2017-12-24 05:00:00,193.1,-8.9
+2017-12-24 06:00:00,194.59,-8.9
+2017-12-24 07:00:00,195.03,-8.9
+2017-12-24 08:00:00,199.17,-8.9
+2017-12-24 09:00:00,225.98,-8.9
+2017-12-24 10:00:00,224.21,-8.3
+2017-12-24 11:00:00,235.98,-7.8
+2017-12-24 12:00:00,240.49,-7.2
+2017-12-24 13:00:00,246.91,-6.1
+2017-12-24 14:00:00,249.95,-5.6
+2017-12-24 15:00:00,249.13,-5.6
+2017-12-24 16:00:00,246.72,-6.7
+2017-12-24 17:00:00,252.15,-7.2
+2017-12-24 18:00:00,252.4,-7.8
+2017-12-24 19:00:00,241.62,-8.3
+2017-12-24 20:00:00,220.13,-10.0
+2017-12-24 21:00:00,211.59,-11.1
+2017-12-24 22:00:00,195.53,-12.8
+2017-12-24 23:00:00,192.38,-13.9
+2017-12-25 00:00:00,192.18,-15.0
+2017-12-25 01:00:00,185.94,-16.7
+2017-12-25 02:00:00,181.75,-16.1
+2017-12-25 03:00:00,182.57,-16.7
+2017-12-25 04:00:00,181.56,-16.7
+2017-12-25 05:00:00,188.76,-16.7
+2017-12-25 06:00:00,225.28,-16.7
+2017-12-25 07:00:00,223.83,-17.2
+2017-12-25 08:00:00,244.84,-17.8
+2017-12-25 09:00:00,238.3,-18.9
+2017-12-25 10:00:00,240.66,-19.4
+2017-12-25 11:00:00,264.46,-18.9
+2017-12-25 12:00:00,257.89,-18.9
+2017-12-25 13:00:00,245.57,-18.3
+2017-12-25 14:00:00,246.53,-18.3
+2017-12-25 15:00:00,248.63,-18.9
+2017-12-25 16:00:00,247.03,-18.9
+2017-12-25 17:00:00,248.73,-19.4
+2017-12-25 18:00:00,263.65,-19.4
+2017-12-25 19:00:00,279.4,-19.4
+2017-12-25 20:00:00,268.19,-19.4
+2017-12-25 21:00:00,254.66,-20.0
+2017-12-25 22:00:00,257.97,-20.0
+2017-12-25 23:00:00,216.5,-20.6
+2017-12-26 00:00:00,215.92,-21.1
+2017-12-26 01:00:00,214.34,-21.1
+2017-12-26 02:00:00,200.45,-21.1
+2017-12-26 03:00:00,206.72,-21.1
+2017-12-26 04:00:00,201.53,-21.7
+2017-12-26 05:00:00,209.65,-21.7
+2017-12-26 06:00:00,223.66,-22.2
+2017-12-26 07:00:00,240.64,-22.2
+2017-12-26 08:00:00,244.28,-22.2
+2017-12-26 09:00:00,276.81,-21.7
+2017-12-26 10:00:00,272.38,-21.1
+2017-12-26 11:00:00,276.58,-20.0
+2017-12-26 12:00:00,276.76,-18.9
+2017-12-26 13:00:00,275.9,-18.9
+2017-12-26 14:00:00,277.23,-17.8
+2017-12-26 15:00:00,270.7,-17.2
+2017-12-26 16:00:00,242.84,-17.8
+2017-12-26 17:00:00,246.76,-17.8
+2017-12-26 18:00:00,249.08,-18.3
+2017-12-26 19:00:00,249.47,-17.8
+2017-12-26 20:00:00,249.1,-18.3
+2017-12-26 21:00:00,248.37,-19.4
+2017-12-26 22:00:00,229.57,-20.0
+2017-12-26 23:00:00,216.44,-20.6
+2017-12-27 00:00:00,186.6,-20.6
+2017-12-27 01:00:00,179.16,-21.1
+2017-12-27 02:00:00,177.69,-21.1
+2017-12-27 03:00:00,178.98,-21.7
+2017-12-27 04:00:00,178.86,-21.7
+2017-12-27 05:00:00,184.15,-21.7
+2017-12-27 06:00:00,241.96,-22.2
+2017-12-27 07:00:00,259.48,-22.2
+2017-12-27 08:00:00,265.18,-22.2
+2017-12-27 09:00:00,271.48,-21.1
+2017-12-27 10:00:00,269.62,-18.9
+2017-12-27 11:00:00,271.74,-17.8
+2017-12-27 12:00:00,276.15,-17.2
+2017-12-27 13:00:00,278.76,-16.7
+2017-12-27 14:00:00,278.14,-15.0
+2017-12-27 15:00:00,275.2,-15.6
+2017-12-27 16:00:00,271.94,-15.6
+2017-12-27 17:00:00,275.43,-15.6
+2017-12-27 18:00:00,278.13,-15.6
+2017-12-27 19:00:00,273.66,-16.7
+2017-12-27 20:00:00,270.69,-16.7
+2017-12-27 21:00:00,249.34,-16.7
+2017-12-27 22:00:00,231.28,-16.7
+2017-12-27 23:00:00,222.14,-16.7
+2017-12-28 00:00:00,190.23,-16.1
+2017-12-28 01:00:00,187.08,-16.1
+2017-12-28 02:00:00,185.17,-16.1
+2017-12-28 03:00:00,185.8,-15.6
+2017-12-28 04:00:00,184.06,-16.1
+2017-12-28 05:00:00,192.13,-16.1
+2017-12-28 06:00:00,227.13,-16.1
+2017-12-28 07:00:00,231.65,-15.6
+2017-12-28 08:00:00,261.17,-15.6
+2017-12-28 09:00:00,246.39,-15.0
+2017-12-28 10:00:00,257.29,-15.0
+2017-12-28 11:00:00,256.48,-14.4
+2017-12-28 12:00:00,266.01,-13.9
+2017-12-28 13:00:00,269.0,-13.3
+2017-12-28 14:00:00,283.74,-12.8
+2017-12-28 15:00:00,280.86,-12.8
+2017-12-28 16:00:00,283.68,-12.8
+2017-12-28 17:00:00,281.01,-12.8
+2017-12-28 18:00:00,250.49,-12.2
+2017-12-28 19:00:00,248.78,-12.2
+2017-12-28 20:00:00,245.16,-12.2
+2017-12-28 21:00:00,246.49,-11.7
+2017-12-28 22:00:00,239.55,-11.7
+2017-12-28 23:00:00,223.55,-13.3
+2017-12-29 00:00:00,194.0,-15.0
+2017-12-29 01:00:00,186.19,-16.1
+2017-12-29 02:00:00,186.59,-17.2
+2017-12-29 03:00:00,185.26,-17.8
+2017-12-29 04:00:00,185.39,-18.3
+2017-12-29 05:00:00,192.25,-18.3
+2017-12-29 06:00:00,225.48,-18.9
+2017-12-29 07:00:00,229.46,-18.3
+2017-12-29 08:00:00,252.91,-18.9
+2017-12-29 09:00:00,254.49,-18.3
+2017-12-29 10:00:00,252.31,-17.8
+2017-12-29 11:00:00,263.58,-17.8
+2017-12-29 12:00:00,276.63,-17.2
+2017-12-29 13:00:00,290.12,-17.2
+2017-12-29 14:00:00,281.42,-16.7
+2017-12-29 15:00:00,253.39,-16.7
+2017-12-29 16:00:00,250.81,-16.7
+2017-12-29 17:00:00,280.7,-16.7
+2017-12-29 18:00:00,279.07,-16.7
+2017-12-29 19:00:00,276.95,-16.7
+2017-12-29 20:00:00,278.38,-17.2
+2017-12-29 21:00:00,275.1,-17.8
+2017-12-29 22:00:00,266.67,-18.3
+2017-12-29 23:00:00,257.81,-19.4
+2017-12-30 00:00:00,248.64,-20.6
+2017-12-30 01:00:00,238.92,-21.7
+2017-12-30 02:00:00,242.93,-22.8
+2017-12-30 03:00:00,241.73,-23.3
+2017-12-30 04:00:00,241.83,-23.9
+2017-12-30 05:00:00,246.9,-24.4
+2017-12-30 06:00:00,249.2,-24.4
+2017-12-30 07:00:00,250.98,-25.6
+2017-12-30 08:00:00,256.28,-25.6
+2017-12-30 09:00:00,235.67,-25.6
+2017-12-30 10:00:00,233.95,-24.4
+2017-12-30 11:00:00,238.72,-23.9
+2017-12-30 12:00:00,246.63,-23.3
+2017-12-30 13:00:00,249.18,-22.2
+2017-12-30 14:00:00,260.28,-21.7
+2017-12-30 15:00:00,274.09,-21.7
+2017-12-30 16:00:00,275.48,-21.7
+2017-12-30 17:00:00,282.07,-22.8
+2017-12-30 18:00:00,266.11,-22.8
+2017-12-30 19:00:00,240.0,-22.8
+2017-12-30 20:00:00,222.13,-22.2
+2017-12-30 21:00:00,214.12,-21.7
+2017-12-30 22:00:00,211.89,-21.7
+2017-12-30 23:00:00,202.43,-21.7
+2017-12-31 00:00:00,202.94,-21.7
+2017-12-31 01:00:00,197.27,-21.7
+2017-12-31 02:00:00,191.38,-22.2
+2017-12-31 03:00:00,202.44,-22.8
+2017-12-31 04:00:00,194.69,-23.3
+2017-12-31 05:00:00,200.75,-23.3
+2017-12-31 06:00:00,205.29,-24.4
+2017-12-31 07:00:00,201.12,-25.6
+2017-12-31 08:00:00,202.04,-26.1
+2017-12-31 09:00:00,250.13,-26.1
+2017-12-31 10:00:00,254.2,-25.6
+2017-12-31 11:00:00,257.08,-24.4
+2017-12-31 12:00:00,258.83,-23.3
+2017-12-31 13:00:00,259.07,-22.2
+2017-12-31 14:00:00,259.22,-21.1
+2017-12-31 15:00:00,259.26,-20.6
+2017-12-31 16:00:00,262.52,-21.1
+2017-12-31 17:00:00,267.01,-21.7
+2017-12-31 18:00:00,270.89,-22.8
+2017-12-31 19:00:00,260.14,-23.3
+2017-12-31 20:00:00,236.78,-23.3
+2017-12-31 21:00:00,232.25,-23.9
+2017-12-31 22:00:00,229.84,-23.9
+2017-12-31 23:00:00,231.14,-23.9
diff --git a/ai-service/tests/test_serving_frame.py b/ai-service/tests/test_serving_frame.py
new file mode 100644
index 0000000..0acb92a
--- /dev/null
+++ b/ai-service/tests/test_serving_frame.py
@@ -0,0 +1,235 @@
+import os
+import tempfile
+from datetime import datetime, timezone
+from pathlib import Path
+from unittest.mock import patch
+
+import pandas as pd
+import pytest
+from starlette.testclient import TestClient
+
+from src.agent.tools.energy_tools import query_metrics
+from src.data_pipeline.serving_frame import (
+    ModelArtifactError,
+    ServingDataError,
+    compute_energy_metrics,
+    get_serving_frame,
+    reset_serving_cache,
+)
+from src.main import app
+
+REQUIRED_COLUMNS = [
+    "timestamp",
+    "meter_reading_kwh",
+    "outdoor_temperature_c",
+    "predicted_kwh",
+    "residual",
+    "lower_bound_95",
+    "upper_bound_95",
+    "anomaly_score",
+    "is_anomaly",
+    "severity",
+]
+
+
+@pytest.fixture
+def client():
+    with TestClient(app) as c:
+        yield c
+
+
+def test_plain_python_import_and_execution():
+    """AC: Given the serving frame, when it is imported and called from a plain Python shell, it works without FastAPI."""
+    frame = get_serving_frame()
+    assert isinstance(frame, pd.DataFrame)
+    assert len(frame) == 720
+    assert list(frame.columns) == REQUIRED_COLUMNS
+
+
+def test_serving_frame_columns_and_bounds():
+    """Verify column names, row order ascending, bounds containing prediction, and floor at 0."""
+    frame = get_serving_frame()
+    assert len(frame) == 720
+    assert list(frame.columns) == REQUIRED_COLUMNS
+
+    # Rows ascending by time
+    ts_list = pd.to_datetime(frame["timestamp"])
+    assert ts_list.is_monotonic_increasing
+
+    # Bounds contain prediction and lower bound floored at 0
+    assert (frame["lower_bound_95"] <= frame["predicted_kwh"] + 1e-5).all()
+    assert (frame["predicted_kwh"] <= frame["upper_bound_95"] + 1e-5).all()
+    assert (frame["lower_bound_95"] >= 0.0).all()
+
+    # Anomaly scores between 0 and 1
+    assert (frame["anomaly_score"] >= 0.0).all()
+    assert (frame["anomaly_score"] <= 1.0).all()
+
+
+def test_api_metrics_endpoint(client):
+    """Matrix: Metrics | Data and artifacts present | 200; same keys as today; values computed over last 720 hourly rows."""
+    res = client.get("/internal/energy/metrics")
+    assert res.status_code == 200
+    data = res.json()
+    expected_keys = {
+        "building_id",
+        "total_consumption_kwh",
+        "peak_demand_kw",
+        "predicted_baseline_kwh",
+        "total_anomalies_detected",
+        "estimated_waste_cost_vnd",
+        "estimated_waste_cost_usd",
+    }
+    assert set(data.keys()) == expected_keys
+    assert data["building_id"] == "office_tower_01"
+
+    frame = get_serving_frame()
+    assert data["total_consumption_kwh"] == round(float(frame["meter_reading_kwh"].sum()), 1)
+    assert data["peak_demand_kw"] == round(float(frame["meter_reading_kwh"].max()), 1)
+    assert data["predicted_baseline_kwh"] == round(float(frame["predicted_kwh"].sum()), 1)
+    assert data["total_anomalies_detected"] == int(frame["is_anomaly"].sum())
+
+
+def test_api_timeseries_endpoint(client):
+    """Matrix: Time series | limit=24 | 200; count 24; rows ascending by time; relative_humidity_pct & anomaly_reason null."""
+    res = client.get("/internal/energy/timeseries?limit=24")
+    assert res.status_code == 200
+    body = res.json()
+    assert body["building_id"] == "office_tower_01"
+    assert body["count"] == 24
+    points = body["data"]
+    assert len(points) == 24
+
+    for pt in points:
+        assert pt["timestamp"].endswith("Z")
+        assert pt["relative_humidity_pct"] is None
+        assert pt["anomaly_reason"] is None
+        assert isinstance(pt["is_anomaly"], bool)
+        assert pt["severity"] in ("Normal", "Medium", "Critical")
+        assert 0.0 <= pt["anomaly_score"] <= 1.0
+
+    # Verify timestamps are ascending
+    ts_strings = [p["timestamp"] for p in points]
+    assert ts_strings == sorted(ts_strings)
+
+
+def test_replay_fixed_clock():
+    """Matrix: Replay | Clock fixed at a Thursday 14:00 UTC | Last row's timestamp is that hour; source row is Thursday 14:00."""
+    fixed_now = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)  # 2026-10-08 is a Thursday
+    frame = get_serving_frame(now=fixed_now)
+    assert len(frame) == 720
+
+    last_ts = frame["timestamp"].iloc[-1]
+    assert last_ts == "2026-10-08T14:00:00Z"
+
+    # All timestamps exactly 1 hour apart
+    ts_series = pd.to_datetime(frame["timestamp"])
+    diffs = ts_series.diff().dropna()
+    assert (diffs == pd.Timedelta(hours=1)).all()
+
+
+def test_hour_rollover_rebuilds_cache():
+    """Matrix: Hour rollover | Clock advances one hour | The cached frame is rebuilt and ends at the new hour."""
+    t1 = datetime(2026, 10, 8, 14, 0, 0, tzinfo=timezone.utc)
+    frame1 = get_serving_frame(now=t1)
+    assert frame1["timestamp"].iloc[-1] == "2026-10-08T14:00:00Z"
+
+    t2 = datetime(2026, 10, 8, 15, 0, 0, tzinfo=timezone.utc)
+    frame2 = get_serving_frame(now=t2)
+    assert frame2["timestamp"].iloc[-1] == "2026-10-08T15:00:00Z"
+
+
+def test_cached_artifacts_not_reloaded_from_disk():
+    """AC: Given the frame was built once, when either endpoint is called again, dataset and artifacts are not reloaded."""
+    reset_serving_cache()
+    from src.models.train_models import load_dataset
+    with patch("src.data_pipeline.serving_frame.load_dataset", wraps=load_dataset) as mock_load:
+        get_serving_frame()
+        get_serving_frame()
+        assert mock_load.call_count == 1
+
+
+def test_timeseries_limit_validation(client):
+    """Matrix: Limit out of range | limit=0 or 721 | 422 from existing validation."""
+    res_zero = client.get("/internal/energy/timeseries?limit=0")
+    assert res_zero.status_code == 422
+
+    res_large = client.get("/internal/energy/timeseries?limit=721")
+    assert res_large.status_code == 422
+
+
+def test_dataset_missing_503(client):
+    """Matrix: Dataset missing | CSV path does not exist | 503 {"detail": ..., "code": "ERR_DATA_NOT_FOUND"} naming path."""
+    reset_serving_cache()
+    non_existent = Path("non_existent_data_path.csv").resolve()
+    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
+    os.environ["ECOTRACK_DATA_PATH"] = str(non_existent)
+    try:
+        res = client.get("/internal/energy/metrics")
+        assert res.status_code == 503
+        data = res.json()
+        assert data["code"] == "ERR_DATA_NOT_FOUND"
+        assert str(non_existent) in data["detail"]
+        assert not non_existent.exists(), "No file should be created on error"
+    finally:
+        if old_data_path is not None:
+            os.environ["ECOTRACK_DATA_PATH"] = old_data_path
+        else:
+            os.environ.pop("ECOTRACK_DATA_PATH", None)
+        reset_serving_cache()
+
+
+def test_artifact_missing_503(client):
+    """Matrix: Artifact missing | A .joblib or metadata file is absent | 503 {"detail": ..., "code": "ERR_MODEL_NOT_FOUND"} naming file."""
+    reset_serving_cache()
+    with tempfile.TemporaryDirectory() as empty_dir:
+        old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
+        os.environ["ECOTRACK_MODELS_DIR"] = empty_dir
+        try:
+            res = client.get("/internal/energy/metrics")
+            assert res.status_code == 503
+            data = res.json()
+            assert data["code"] == "ERR_MODEL_NOT_FOUND"
+            assert "xgboost_forecaster.joblib" in data["detail"]
+            # No model trained or saved
+            assert len(os.listdir(empty_dir)) == 0, "No model should be saved on missing artifact error"
+        finally:
+            if old_models_dir is not None:
+                os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
+            else:
+                os.environ.pop("ECOTRACK_MODELS_DIR", None)
+            reset_serving_cache()
+
+
+def test_tariff_override():
+    """Matrix: Tariff override | TARIFF_RATE_VND=2500 | estimated_waste_cost_vnd equals waste kWh * 2500."""
+    frame = get_serving_frame()
+    old_tariff = os.environ.get("TARIFF_RATE_VND")
+    os.environ["TARIFF_RATE_VND"] = "2500"
+    try:
+        metrics = compute_energy_metrics(frame)
+        waste_kwh = float(frame[frame["is_anomaly"]]["residual"].clip(lower=0).sum())
+        expected_vnd = round(waste_kwh * 2500, 0)
+        assert metrics["estimated_waste_cost_vnd"] == expected_vnd
+    finally:
+        if old_tariff is not None:
+            os.environ["TARIFF_RATE_VND"] = old_tariff
+        else:
+            os.environ.pop("TARIFF_RATE_VND", None)
+
+
+def test_copilot_tool_query_metrics():
+    """Verify query_metrics tool returns matching metrics with copilot keys."""
+    metrics = query_metrics()
+    expected_tool_keys = {
+        "building_id",
+        "total_consumption_kwh",
+        "peak_demand_kw",
+        "baseline_kwh",
+        "anomalies_detected",
+        "estimated_waste_kwh",
+        "estimated_waste_vnd",
+        "estimated_waste_usd",
+    }
+    assert set(metrics.keys()) == expected_tool_keys
+    assert metrics["building_id"] == "office_tower_01"

\
Do not invoke any skill, and do not spawn subagents of your own — you are the reviewer. Return your findings as text in your final message; do not route them through any findings-reporting tool the host may offer.
