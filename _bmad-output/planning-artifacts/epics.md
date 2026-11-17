---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
story48Refinement:
  scope: 4-8-retrain-on-demand-with-guarded-promotion
  stepsCompleted:
    - step-01-validate-prerequisites
    - step-02-design-epics
    - step-03-create-stories
    - step-04-final-validation
  status: completed
  elicitation:
    methods: [assumption-audit, failure-mode-analysis, boundary-edge-case-sweep, problem-decomposition, second-order-thinking]
    status: trimmed-via-party-mode
    accepted: 2026-11-16
story49Refinement:
  scope: 4-9-retrain-automatically-when-the-model-degrades
  stepsCompleted:
    - step-01-validate-prerequisites
    - step-02-design-epics
    - step-03-create-stories
    - step-04-final-validation
  status: completed
  partyMode:
    status: accepted-via-party-mode
    accepted: 2026-11-17
  inputDocuments:
    - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md
    - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md
    - _bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md
    - _bmad-output/planning-artifacts/epics.md
story410Refinement:
  scope: 4-10-report-model-and-drift-status
  stepsCompleted:
    - step-01-validate-prerequisites
    - step-02-design-epics
    - step-03-create-stories
    - step-04-final-validation
  status: completed
  partyMode:
    status: accepted-via-party-mode
    accepted: 2026-11-17
  inputDocuments:
    - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md
    - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md
    - _bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md
    - _bmad-output/planning-artifacts/epics.md
inputDocuments:
  - plan.md
  - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md
  - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md
---

# EcoTrack - Epic Breakdown

## Story 4.8 refinement — Requirements extraction (2026-11-16)

Scope and source selection confirmed by the product owner. This scoped pass reuses the existing inventory and epic structure; the original completed workflow above remains historical. Story 4.8 wording and acceptance criteria have been refined and validated.

### Functional requirements in scope

- FR25 (manual portion): accept `POST /internal/mlops/retrain`, train a challenger on the latest data in a background thread, and immediately return HTTP 202 with a run ID.
- FR25 (promotion guard): evaluate challenger and champion on the same holdout; promote only for strictly lower challenger MAPE. Equal or worse MAPE retains the champion.
- FR25 (serving): assign the winning model the `champion` alias and serve it without restarting, as already required by Story 4.8.
- FR25 (history): record timestamp, trigger `manual`, both MAPE values, and outcome `promoted` or `rejected` for completed evaluations.
- FR25 (concurrency): return HTTP 409 when retraining is already running.
- PRD FR-3 constraint: preserve chronological training/evaluation boundaries and prevent temporal leakage.
- FR23 dependency: reuse the MLflow tracking and registered champion introduced in Story 4.5.
- FR17 dependency: retain internal-token protection on the new internal endpoint.

### Applicable non-functional requirements

- NFR3: preserve the existing forecast latency target (p95 below 300 ms); do not interpret it as a training completion deadline.
- NFR5: training and serving run on CPU.
- NFR6 / AD-2: CPU-intensive work must not block the FastAPI event loop.
- NFR7 / AD-5: API timestamps use ISO 8601 UTC.
- NFR8: provide scope-specific pytest coverage and pass CI before merge.
- PRD NFR-3: retain estimator-compatible model interfaces.

### Architecture and scope boundaries

- Extend the brownfield `ai-service/`; keep training/evaluation callable without FastAPI (AD-1). The older spine's ML paths under `backend/` map to `ai-service/` per the existing inventory.
- Reuse serving features and artifacts; do not introduce a second training or inference stack.
- Reconcile the source conflict explicitly: `plan.md` calls hot reload stretch work, while the existing Story 4.8 explicitly requires it. This refinement retains the story requirement pending requirements confirmation.
- Scheduled/drift-triggered execution stays in Story 4.9; the status endpoint in 4.10; gateway proxy in 4.11; UI in 4.12; role gates in Epic 5.
- No standalone UX contract was discovered. This story introduces an internal API and no UI work.
- No starter template or database migration is prescribed by the selected sources for this story.

### Clarifications proposed for acceptance-criteria drafting

These are proposed safeguards, not requirements already specified by the sources:

- Define one reproducible holdout snapshot excluded from challenger training, with identical scoring rules and a documented zero-target policy for MAPE.
- On invalid or insufficient data, training/evaluation failure, or non-finite scores, retain the champion, record an explicit failure reason, and release the retrain lock.
- If registry promotion or model reload fails, preserve a consistent usable champion and make the failed attempt traceable.
- Define the run lifecycle and history fields for failures, including unavailable metrics, without conflating operational failure with a completed evaluation rejection.

Requirements, including the proposed safeguards above, were confirmed by the product owner with `C` on 2026-11-16 and applied to Story 4.8 below.

### Proposed epic placement and coverage

- Retain Story 4.8 in the existing Epic 4 (model lifecycle); introduce no additional epic for this scoped refinement.
- User outcome: an administrator can request a model refresh while the service retains its champion unless a challenger demonstrates lower MAPE on the shared holdout. This is a measured holdout guarantee, not a guarantee about all future forecasts.
- FR25 manual retraining, promotion guard, concurrency, history, and confirmed failure safeguards map to Epic 4 / Story 4.8.
- PRD FR-3 temporal separation constrains Story 4.8 evaluation; existing FR23 model tracking/registry (Story 4.5) and FR17 internal-token enforcement (Story 1.6) are prerequisites.
- Story 4.8 must function through its internal endpoint without requiring later scheduling (4.9), status API (4.10), gateway (4.11), UI (4.12), or Epic 5 role gates. Persist history here for later status consumption.
- Reuse the existing training, tracking, and serving modules within this epic. Their shared ownership supports retaining one model-lifecycle epic rather than splitting training, HTTP, and model loading into separate epics.

Epic placement approved by the product owner on 2026-11-16; the global epic list and FR coverage map remain unchanged.

### Accepted refinements after Party Mode review (2026-11-16)

Following Advanced Elicitation and Party Mode review, the product owner approved trimming the 5 elicitation blocks down to 3 practical guardrails for Story 4.8 acceptance-criteria drafting (dropping multi-replica coordination and process-restart crash-recovery machinery):

1. **Fair Holdout (No Temporal Leakage):** Evaluate both `champion` and `challenger` on a shared chronological holdout window strictly after the training cutoff of both models, using an identical MAPE rule with documented handling for zero targets (`y == 0`) and rejecting non-finite (`NaN`/`Inf`) scores. Promote only when `challenger_mape < champion_mape`.
2. **Safe Hot-Reload:** Verify that the challenger artifact loads cleanly before updating the MLflow `champion` alias under `.champion.lock` and calling `reset_serving_cache()` in `serving_frame.py`. If promotion or reload fails, preserve the existing usable champion.
3. **Three-State History & Lock Safety (`promoted` | `rejected` | `failed`):** Use an atomic in-process lock to return HTTP 409 on concurrent requests, always release the lock in a `finally` block across every terminal path, and persist history records (`run_id`, `timestamp`, `trigger`, `champion_mape`, `challenger_mape`, `outcome`, and optional `reason`) via a reusable retrain coordinator in `ai-service/src/mlops/` that Story 4.9 and Story 4.10 can consume.

## Story 4.9 refinement — Requirements extraction (2026-11-17)

Scope and source selection confirmed by the product owner (explicitly excluding `plan.md`). This scoped pass reuses the existing inventory and epic structure; Story 4.9 wording and acceptance criteria have been refined and validated.

### Functional requirements in scope

- FR25 (automatic / scheduled portion) & PRD FR-5: run a scheduled daily job that calls the Story 4.6 drift check (`drift.check()`) and triggers retraining (`run_retrain()`) only when `drift_detected` is `true`.
- FR25 (trigger & signal attribution): classify automatic retrain `trigger` as `"mape"` when only `"rolling_mape"` triggered, or `"drift"` when `"meter_reading"` or `"air_temperature"` triggered (including when accompanied by `"rolling_mape"`), and persist the full `triggered_signals` list in `signals` on the `retrain_history.json` record.
- FR25 (configuration & testability): allow disabling the background scheduler via configuration (defaulting to disabled in tests) and expose the daily job function as plain Python directly callable in `pytest`.
- FR24 dependency (Story 4.6): reuse `ai-service/src/mlops/drift.py` (`drift.check()`) and its configured thresholds.
- FR25 dependency (Story 4.8): reuse `ai-service/src/mlops/retrain.py` (`run_retrain()`) and its guarded holdout promotion / `_retrain_lock` (`RetrainAlreadyRunningError` handled safely by logging and skipping without crashing the scheduler).
- FR26 downstream readiness (Story 4.10): persist the latest drift check snapshot (`drift_status.json` in `get_models_dir()` with `checked_at` in ISO 8601 UTC) after every job execution (even when `drift_detected` is `false`).

### Applicable non-functional requirements

- NFR5: drift checking and retraining execute on CPU.
- NFR6 / AD-2: scheduled background checks and retraining must not block the FastAPI event loop.
- NFR7 / AD-5: all persisted timestamps (`checked_at`, history entries) use ISO 8601 UTC (`Z`).
- NFR8: provide offline `pytest` coverage without starting FastAPI or running heavy BDG2 training jobs.

### Architecture and scope boundaries

- AD-1 (hexagonal boundary): keep the check/retrain decision logic and scheduler helper as plain Python under `ai-service/src/mlops/`; wire only startup/shutdown lifecycle hooks in `ai-service/src/main.py`.
- Dependency boundary (`plan.md` excluded): no APScheduler dependency is mandated by the remaining sources; implement the daily scheduler using Python stdlib (`threading.Event` + daemon `threading.Thread` with configurable interval) without adding external packages.
- Default window resolution: construct `reference_df` (first 80% chronological split) and `recent_df` (trailing 168 hours) from `get_data_path()`, while allowing callers/tests to inject `reference_df` / `recent_df` directly.
- Out of scope: `GET /internal/mlops/status` (Story 4.10), gateway proxy (Story 4.11), UI (Story 4.12), RBAC (Epic 5).

### Proposed epic placement and coverage

- Retain **Story 4.9** within existing **Epic 4: Self-Monitoring Model Lifecycle**; do not split scheduler wiring and drift-check orchestration into separate epics or stories.
- User outcome: an admin can rely on daily automated drift monitoring that refreshes the model only when degradation is detected and still enforces Story 4.8's guarded promotion rules.
- FR coverage mapping: **FR25 (automatic retraining)** and **PRD FR-5** map to **Epic 4 / Story 4.9**, building on **FR24 (Story 4.6)** and **FR25 manual coordinator (Story 4.8)** while supplying `drift_status.json` and triggered history entries for **FR26 (Story 4.10)**.
- Independence: fully functional via Python module and FastAPI lifecycle without requiring Stories 4.10–4.12 or Epic 5.

Epic placement approved by the product owner on 2026-11-17; the global epic list and FR coverage map remain unchanged.

### Accepted refinements after Party Mode review (2026-11-17)

1. **Stdlib Daily Scheduler (No APScheduler):** With `plan.md` excluded, run the daily drift check using Python stdlib (`threading.Event` + daemon `threading.Thread`) managed via FastAPI `lifespan` (`stop_event.set()` + bounded `join()` on shutdown) in `ai-service/src/main.py`, with a configurable interval (default `86400`s / 24h) and a short configurable initial delay (`ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS`, default `10`s so startup health checks complete before the first check populates `drift_status.json`). `ECOTRACK_SCHEDULER_ENABLED` defaults to enabled at runtime (matching `docker-compose.yml` out of the box) and is disabled via configuration in `ai-service/tests/conftest.py`. Errors during any scheduled tick are logged and do not terminate the scheduler loop or FastAPI process.
2. **Recent-Window Resolution & Test Injection:** Resolve `reference_df` as the chronological first 80% of `get_data_path()` and `recent_df` from optional `ECOTRACK_DRIFT_RECENT_PATH` (falling back to the unmodified baseline dataset at `get_data_path()`, whose trailing 168h are scored for rolling MAPE), while letting the plain-Python job accept `reference_df` / `recent_df` directly in tests without adding a cooldown/dedup layer not requested by FR25. If a drifted demo scenario causes `run_retrain()` to reject an inferior/unchanged challenger, preserving the champion as `rejected` is the intended guarded-promotion behavior.
3. **Observability & Trigger Rules:** Persist `get_models_dir() / "drift_status.json"` on every scheduled check with `checked_at` (ISO 8601 UTC), `drift_detected`, `triggered_signals`, `signals`, `rolling_mape`, `thresholds`, `retrain_triggered`, and optional `retrain_run_id` for Story 4.10/4.12. Classify automatic retrain `trigger` as `"mape"` when only `"rolling_mape"` triggered, else `"drift"`, passing `signals=triggered_signals` into `run_retrain(...)`, and log-and-skip safely on `RetrainAlreadyRunningError`.

## Story 4.10 refinement — Requirements extraction (2026-11-17)

Scope and source selection confirmed by the product owner (excluding missing `plan.md`). This scoped pass reuses the existing inventory and epic structure; Story 4.10 requirements have been extracted and validated for downstream epic/story refinement.

### Functional requirements in scope

- **FR26 (`GET /internal/mlops/status`):** Return a single consolidated health summary for monitoring consumers without exposing MLflow internals:
  - Champion model summary: version, training date (ISO 8601 UTC), and evaluation metrics (`rmse_kwh`, `mae_kwh`, `mape_percent`, `r2_score`) from the active MLflow `champion` run or `models_saved/` fallback when MLflow is disabled/uninitialized.
  - Latest drift status: snapshot from `get_models_dir() / "drift_status.json"` (Story 4.9 / Story 4.6), or `null` when no drift check has run yet while still responding HTTP 200.
  - Anomaly detector quality metrics: `isolation_forest_quality` from `get_models_dir() / "model_metadata.json"` (Story 4.7), or `null` when absent.
  - Retraining history (newest first): entries from `get_models_dir() / "retrain_history.json"` (Stories 4.8–4.9), returning `[]` when empty/absent.
  - Forecast benchmark table: parsed payload from `experiments/benchmark/results.json` (Story 4.4) when present, or `null` when absent.
- **FR17 dependency (Story 1.6):** Enforce `X-Internal-Token` authentication on `GET /internal/mlops/status` via the existing `/internal/*` middleware (`401 ERR_UNAUTHORIZED` when missing/invalid).
- **Downstream consumers (out of scope here):** Story 4.11 (`FR40` gateway proxy `/api/v1/mlops/status`) and Story 4.12 (`FR44` frontend MLOps monitoring page).

### Applicable non-functional requirements

- **NFR5:** Execute on CPU with no new external dependencies or GPU requirements.
- **NFR6 / AD-2:** Handle `GET /internal/mlops/status` via an `async def` FastAPI route running blocking disk/MLflow reads in `asyncio.to_thread` so the event loop is not starved.
- **NFR7 / AD-5:** Emit all API timestamps in ISO 8601 UTC (`Z`) and all numeric metrics as finite JSON floats (no `NaN`/`Inf`).
- **NFR8:** Ship offline `pytest` coverage in `ai-service/tests/` exercising present/missing artifacts, newest-first retrain history, MLflow disabled/uninitialized vs broken champion states, and `X-Internal-Token` enforcement.

### Architecture and scope boundaries

- **AD-1 (hexagonal boundary):** Implement status aggregation as plain Python under `ai-service/src/mlops/` callable directly without FastAPI; keep `ai-service/src/api/routers/mlops.py` as a thin HTTP adapter.
- **Brownfield artifact sources:** Read only from existing configured locations (`ai-service/src/mlops/tracking.py`, `get_models_dir() / "model_metadata.json"`, `get_models_dir() / "drift_status.json"`, `get_models_dir() / "retrain_history.json"`, and `ai-service/experiments/benchmark/results.json` with configurable path override for tests); no new DB drivers or migrations.
- **No UX design contract:** No standalone UX documents exist; UI rendering belongs to Story 4.12 (`FR44`).

### Confirmed clarifications for Story 4.10 drafting

- **HTTP 200 resilience vs broken champion visibility:** Keep `GET /internal/mlops/status` returning HTTP 200 even when MLflow is disabled/uninitialized (local fallback) or when the resolved `champion` artifact/SQLite store is broken/locked (surfaced explicitly in the champion health/status fields rather than crashing the monitoring endpoint).
- **Champion training timestamp fallback:** Read run timestamp from MLflow when available; on local fallback, derive `trained_at` from `train_end_timestamp` in `model_metadata.json` or the artifact `mtime` in ISO 8601 UTC.
- **Optional benchmark path & missing anomaly quality:** Allow overriding the benchmark `results.json` path for clean offline testing, and return `null` cleanly when `results.json` or `isolation_forest_quality` is absent.

Requirements confirmed by the product owner (`C`) on 2026-11-17.

### Proposed epic placement and coverage

- Retain **Story 4.10** within existing **Epic 4: Self-Monitoring Model Lifecycle**; do not create a new epic or split plain-Python status aggregation from the `/internal/mlops/status` FastAPI router.
- User outcome: an admin and downstream monitoring consumers (`4.11` gateway, `4.12` UI) get a single consolidated health summary (`champion`, `drift`, `anomaly_quality`, `retrain_history`, `benchmark`) without coupling to MLflow internals or scattered JSON artifacts.
- FR coverage mapping: **FR26 (`GET /internal/mlops/status`)** maps to **Epic 4 / Story 4.10**, building on **FR17 (Story 1.6)**, **FR21 (Story 4.4)**, **FR23 (Story 4.5)**, **FR24 (Story 4.6)**, **FR27 (Story 4.7)**, and **FR25 (Stories 4.8–4.9)**.
- Independence: fully functional via plain-Python module and FastAPI internal endpoint (responding HTTP 200 with `null`/`[]` when optional upstream artifacts are absent) without requiring Stories 4.11–4.12 or Epic 5.

Epic placement approved by the product owner on 2026-11-17; the global epic list and FR coverage map remain unchanged.

### Accepted refinements after Party Mode review (2026-11-17)

1. **Lightweight Champion Inspection & Explicit Broken-State Visibility:** Read champion `version`, `trained_at`, and `metrics` via `MlflowClient` metadata (`get_model_version_by_alias` + `get_run`) without deserializing the XGBoost model on every status call. When MLflow is disabled, uninitialized, or has no `champion` alias, fall back to `models_saved/` (`source: "local"`, `status: "fallback"`, or `status: "unavailable"` if no local model exists). When an MLflow `champion` alias exists but SQLite is locked or its artifact is missing/corrupt, **never** fall back silently to `models_saved/` — return HTTP 200 with `champion.status = "broken"`, `metrics: null`, and a diagnostic `error` so downstream UI can alert without blanking other sections.
2. **Honest `trained_at` Timestamp (ISO 8601 UTC, NFR7):** Derive `trained_at` from the MLflow run timestamp (`end_time` / `start_time` / `creation_timestamp`) formatted in ISO 8601 UTC (`Z`). On `local` fallback, read `train_end_timestamp` from `model_metadata.json` when present and return `null` when absent rather than fabricating a training date from file `mtime` (which reflects container build/copy time).
3. **Verbatim Benchmark Payload (~16 KB):** Return the parsed `experiments/benchmark/results.json` object verbatim when present (or `null` when absent), avoiding unnecessary projection layers while supporting an optional path/env override (`ECOTRACK_BENCHMARK_RESULTS_PATH` / function parameter) for offline tests.
4. **Per-Section Disk Error Isolation & Safe Serialization:** Missing artifact files return `null` (`drift`, `anomaly_quality`, `benchmark`) or `[]` (`retrain_history`). If a persisted JSON file exists on disk but is corrupt/invalid, preserve fail-loud behavior in `load_drift_status()` / `load_retrain_history()` for scheduler/retrain callers while catching and logging the read error in the status aggregator, returning `null`/`[]` for that section alongside a per-section entry in `errors` while still keeping HTTP 200. Sort `retrain_history` stably by `timestamp` descending (newest first) and sanitize/reject non-finite floats (`NaN`/`Inf`) so JSON serialization never fails.

## Overview

This document provides the complete epic and story breakdown for the EcoTrack upgrade, decomposing the requirements from the approved upgrade plan (`plan.md`), the PRD, and the Architecture spine into implementable stories.

Scope note: this breakdown covers the **upgrade** described in `plan.md` (2026-10-08). PRD requirements FR-1 to FR-12 are the original MVP; the list below continues that numbering from FR13. Where an upgrade requirement finishes a PRD requirement that the current code does not actually satisfy, the PRD ID is given in brackets. Only the "Bắt buộc" (must-have) scope of `plan.md` is turned into requirements; the "Mở rộng" (stretch) scope is listed separately as backlog.

**Reorganized 2026-10-08** to match `sprint-status.yaml`: the epics are now sequenced to deliver a live, demo-able data path first (real data → sensor simulator → ingest → forecast/anomalies), then the live console, then the knowledge Copilot, then the model lifecycle, with authentication and RBAC pulled into a final hardening epic. The requirement set (FR13–FR45) is unchanged; only the epic grouping and story order changed. Story 1.1 is already `done`.

## Requirements Inventory

### Functional Requirements

**Foundation (Phase 0, whole team)**

FR13: The AI service serves energy metrics, time series, forecasts and anomalies from the BDG2-trained artifacts in `models_saved/` and the `EnergyInferencePipeline` feature pipeline; the in-sample model fitted on the synthetic 721-row dataset is no longer served.
FR14: `GET /internal/forecast/predict` returns a true 24-hour-ahead recursive forecast (`predict_forecast_autoregressive`) as `{ timestamp, predicted_kwh, lower_bound_95, upper_bound_95 }` per hour. [completes PRD FR-4]
FR15: When a required model artifact is missing, the AI service returns an explicit error; it never trains and persists a fallback model on random data.
FR16: LLM provider failures are logged with provider and reason, and LLM model names are read from configuration rather than hardcoded.
FR17: The AI service rejects any `/internal/*` request that lacks a valid `X-Internal-Token`, and neither service ships a default secret.
FR18: `MeterReading` enforces uniqueness on `(building_id, timestamp)` so duplicate ingests are skipped.
FR19: Clicking "Ask Copilot" on an anomaly row opens the Copilot drawer with the prepared diagnostic prompt loaded. [completes PRD FR-12]

**Forecast benchmark and LSTM (Member 1)**

FR20: A benchmark script runs Seasonal-naive, SARIMAX, XGBoost and LSTM forecasters on the same chronological 80/20 split used by `train_models.py`.
FR21: The benchmark reports MAE, RMSE, MAPE, R², training time, inference latency (ms) and model file size per model, and exports `results.csv` plus three charts (metric comparison, actual vs predicted, error by hour of day).
FR22: An LSTM forecaster (PyTorch, CPU, 168-hour input window, 24-hour output) can be trained and evaluated through the same pipeline.

**MLOps (Member 2)**

FR23: Training runs log parameters, metrics and artifacts to a local MLflow store, and the serving model is registered under the `champion` alias.
FR24: A drift module computes a KS test and PSI on `meter_reading` and `air_temperature` between a reference window and the most recent window, plus a rolling 7-day MAPE.
FR25: Retraining can be triggered by `POST /internal/mlops/retrain` and by a daily scheduled check when rolling MAPE exceeds its threshold or drift is detected; the new model is promoted to `champion` only if it beats the current one on the holdout set. [realizes PRD FR-5]
FR26: `GET /internal/mlops/status` returns the current model, its metrics, drift status and retraining history.
FR27: The Isolation Forest detector is evaluated for precision, recall and F1 against the `is_injected_anomaly` labels and the two demo scenarios.

**Technical depth additions (owner decision 2026-10-10)**

FR46: The benchmark scores every forecaster at each forecast horizon from 1 to 24 hours ahead and exports the per-horizon results, so models are compared at the horizon they are used for and not only one step ahead.
FR47: The hyperparameters of the XGBoost and LSTM forecasters are selected by an automated search (Optuna) with the same trial budget per model, scored on time-ordered validation slices of the training split only, with every trial logged to MLflow.
FR48: The served forecast carries prediction intervals learned by quantile (pinball-loss) training, replacing the fixed `±1.96 × RMSE` band, and their empirical coverage on the held-out test split is measured and reported.

**RAG and evaluation (Member 3)**

FR28: A knowledge base of 10–20 short documents exists under `ai-service/knowledge_base/`, covering QCVN 09:2017/BXD excerpts, EVN time-of-use tariffs, Chiller/HVAC operating guidance and energy-saving practices.
FR29: An ingest script chunks the knowledge base (~500 tokens), embeds it with a multilingual model and stores it in an embedded ChromaDB collection.
FR30: The Copilot has a `search_knowledge` tool, and answers that use it list their sources.
FR31: The Copilot uses the conversation `history` it receives when generating an answer.
FR32: An evaluation script runs a 30-question golden set and reports hit-rate@3 and MRR for retrieval, and Ragas faithfulness and answer relevancy for answers, comparing with-RAG against without-RAG.

**Backend: auth, ingest, streaming (Member 4)**

FR33: The database has `User` (role `ADMIN`, `MANAGER` or `TECHNICIAN`), `RefreshToken` and `Zone` (belongs to `Building`, with `floor` and `name`) models, and `MeterReading` has an optional `zone_id`.
FR34: Users can log in, refresh and log out through `POST /api/v1/auth/{login,refresh,logout}`, with bcrypt password hashing, short-lived access tokens and rotating refresh tokens stored as hashes.
FR35: Role-based access control protects mutating endpoints: `POST /buildings`, `PATCH /anomalies/:id/status` and `POST /energy/cache/clear` require authentication and an allowed role.
FR36: `POST /api/v1/ingest/readings` validates and stores meter readings, and a simulator sends readings for about 10 zones every 2–5 seconds. [partially realizes PRD FR-1]
FR37: `GET /api/v1/stream/readings` pushes newly ingested readings to subscribed clients over SSE.
FR38: The Copilot answer is streamed end to end: the AI service emits SSE events `token`, `sources` and `done` from `POST /internal/copilot/chat/stream`, and the gateway relays them at `POST /api/v1/copilot/chat/stream`. [completes PRD FR-10]
FR39: `GET /api/v1/buildings/:id/zones` returns the zones of a building with their latest reading.
FR40: The gateway proxies the MLOps status and retrain endpoints; retrain is restricted to `ADMIN`.

**Frontend (Member 5)**

FR41: The app has routed pages (Login, Dashboard, Floor Plan, MLOps), attaches the access token to API calls, refreshes it automatically, and hides the MLOps page from non-admin roles.
FR42: A 2D SVG floor plan of one floor (8–12 rooms) colours each room by temperature or waste level, updates live from the readings stream, and shows room details on click.
FR43: The Copilot renders Markdown (including lists and tables), shows the answer token by token while streaming, offers a stop button, and displays cited sources.
FR44: The MLOps page shows the current model and metrics, drift status, retraining history, the forecast benchmark table, and a "Retrain" action for admins.
FR45: The "System status" panel reflects real health data instead of hardcoded values.

### NonFunctional Requirements

NFR1: LLM API keys and JWT secrets live only in server-side environment variables; the frontend never receives them. [PRD NFR-2]
NFR2: The gateway applies `helmet`, rate limiting and a CORS origin allowlist.
NFR3: The 24-hour forecast endpoint responds within 300 ms at the 95th percentile. [PRD SM-5]
NFR4: The first Copilot token reaches the client within 2.5 s. [PRD SM-5]
NFR5: Everything trains and runs on CPU; Docker images use CPU-only builds of `torch` and related libraries.
NFR6: CPU-bound inference in FastAPI handlers runs via `asyncio.to_thread`. [AD-2]
NFR7: Timestamps crossing an API boundary are ISO 8601 UTC, and energy values are floats in kWh or kW. [AD-5]
NFR8: Every story ships tests for its own scope (pytest for `ai-service`, Vitest + Supertest for `backend`), and CI is green before merging into `develop`.
NFR9: Agent tool calls and their latencies are logged. [PRD NFR-4]
NFR10: Copilot streaming updates must not re-render the dashboard charts. [AD-4]

### Additional Requirements

- **Brownfield, no starter template.** All work extends the existing `ai-service/`, `backend/` and `frontend/` code; Story 1.1 was a consolidation story, not a scaffold.
- **Architecture spine is partly stale.** It predates the split into an Express gateway (`backend/`, Prisma + PostgreSQL) and a FastAPI AI service (`ai-service/`). Spine paths under `backend/src/{models,agent,data_pipeline}` now live under `ai-service/src/`. `plan.md` is the newer source where the two disagree.
- **AD-1 (hexagonal boundary):** new ML, drift, RAG and benchmark modules must be callable as plain Python without starting FastAPI.
- **AD-3 (no raw telemetry in prompts):** the Copilot reaches data and knowledge only through tools returning compact summaries.
- **AD-6 (dockerized reproducibility):** changes to core APIs must still pass `docker compose up --build`.
- **API contracts first:** the cross-member endpoints in `plan.md` section 7 need agreed request/response examples in week 1 so the frontend can build against mocks.
- **SSE with auth:** browsers' `EventSource` cannot send an `Authorization` header, so clients read streams with `fetch`.
- **Database:** PostgreSQL through Prisma migrations; the AI service has no database driver today.
- **Reuse:** `stream_worker.py` for the simulator, `demo_scenarios.py` for drift and anomaly evaluation, `inference_pipeline.py` for serving features.

### UX Design Requirements

No UX design contract exists for this project. UI requirements are carried by FR41–FR45 and by the frontend items of `plan.md`.

### Stretch Backlog (not turned into stories)

- TFT / PatchTST via `neuralforecast`; multi-fold `TimeSeriesSplit`; forecast intervals for the benchmark-only models (intervals for the served forecast are now Story 4.13).
- Evidently HTML drift report; hot model reload without restart.
- Gemini native function calling replacing the keyword router; Ollama offline fallback; reranking.
- Mosquitto MQTT ingest; `docker-compose.prod.yml` with multi-stage images; Redis cache.
- Mini Recharts charts inside chat messages; KaTeX; Three.js 3D building.
- ONNX export of XGBoost / Isolation Forest / LSTM with parity tests. Owner decision 2026-10-10: `.joblib` stays the serving format for now; if time allows, add ONNX as an extra benchmark row (for example `xgboost_onnx`) that reports prediction parity, latency and file size against the native model. Note that SARIMAX has no ONNX exporter and that retraining still needs the native libraries.
- Multi-building experiment (only under `ai-service/experiments/`, no serving change): train one LSTM on about ten BDG2 office buildings and compare it, as an extra benchmark row, with the LSTM trained on the single served building.

### FR Coverage Map

FR13: Epic 1 - Real-data serving, forecast and anomalies (Stories 1.1, 1.4, 1.5)
FR14: Epic 1 - True 24-hour-ahead forecast (Story 1.4)
FR15: Epic 1 - Explicit error on missing artifact (Story 1.5)
FR16: Epic 3 - Logged LLM failures, configurable model names (Story 3.7)
FR17: Epic 1 - Internal token enforcement (Story 1.6)
FR18: Epic 1 - Unique meter readings, folded into zone ingest (Story 1.3)
FR19: Epic 1 - "Ask Copilot" carries the prompt (Story 1.7)
FR20: Epic 4 - Four-model benchmark on one split (Stories 4.1, 4.2, 4.3)
FR21: Epic 4 - Metrics, results file and charts (Stories 4.1, 4.4)
FR22: Epic 4 - LSTM forecaster (Story 4.3)
FR23: Epic 4 - MLflow tracking and `champion` alias (Story 4.5)
FR24: Epic 4 - Drift and rolling accuracy (Story 4.6)
FR25: Epic 4 - Retraining with guarded promotion (Stories 4.8, 4.9)
FR26: Epic 4 - MLOps status endpoint (Story 4.10)
FR27: Epic 4 - Anomaly detector quality report (Story 4.7)
FR28: Epic 3 - Knowledge base corpus (Story 3.1)
FR29: Epic 3 - Chunk, embed and store (Story 3.1)
FR30: Epic 3 - `search_knowledge` tool with sources (Story 3.2)
FR31: Epic 3 - Conversation history (Story 3.3)
FR32: Epic 3 - RAG evaluation (Story 3.8)
FR33: Epic 1 - Zone model and `zone_id` (Story 1.3); Epic 5 - User and RefreshToken (Stories 5.1, 5.2)
FR34: Epic 5 - Login, refresh, logout (Stories 5.1, 5.2)
FR35: Epic 5 - Role-based protection (Story 5.3)
FR36: Epic 1 - Ingest endpoint and simulator (Stories 1.2, 1.3)
FR37: Epic 2 - Live readings stream (Story 2.1)
FR38: Epic 3 - Copilot streaming: AI service (Story 3.4), gateway relay (Story 3.5)
FR39: Epic 1 - Zones endpoint (Story 1.3)
FR40: Epic 4 - MLOps proxy, admin-only retrain (Story 4.11)
FR41: Epic 5 - Login, routing, role-aware navigation (Story 5.4)
FR42: Epic 2 - Live floor plan (Story 2.2)
FR43: Epic 3 - Streaming Copilot with Markdown and sources (Story 3.6)
FR44: Epic 4 - MLOps page (Story 4.12)
FR45: Epic 2 - Real system status (Story 2.3)
FR46: Epic 4 - Per-horizon benchmark scoring (Story 4.4)
FR47: Epic 4 - Automated hyperparameter search logged to MLflow (Story 4.5)
FR48: Epic 4 - Learned prediction intervals with measured coverage (Story 4.13)

## Epic List

The epics are sequenced for demo value: Epic 1 stands up a live real-data path end to end, Epic 2 shows it on screen, Epic 3 adds the knowledge Copilot, Epic 4 adds the model lifecycle and its admin view, and Epic 5 hardens everything with authentication and RBAC.

**Sequencing & dependency notes.** Authentication and RBAC are deliberately last (Epic 5). To avoid forward dependencies, the `/api/v1/*` endpoints introduced in Epics 1–4 (ingest, zones, readings stream, Copilot stream relay, MLOps proxy) ship **open**, guarded only by the service-to-service `X-Internal-Token` and the ingest `X-Ingest-Key` where noted. Epic 5 Story 5.3 then applies `requireAuth` and the role matrix across all remaining `/api/v1/*` routes in one pass, and Story 5.4 adds the role-aware frontend. The frontend MLOps page (Story 4.12) and role-aware navigation (Story 5.4) therefore reach their final gated form only once Epic 5 lands; built before that, Story 4.12 renders without a role gate.

### Epic 1: Live Real-Data Foundation
A real building's data flows end to end: the service serves BDG2-trained metrics, a simulator feeds per-zone readings into the database through an ingest endpoint, and forecasts and anomalies come from the real models with failures surfaced, not masked.
**FRs covered:** FR13, FR14, FR15, FR17, FR18, FR19, FR33 (Zone/`zone_id`), FR36, FR39

### Epic 2: Live Operations Console
Operators watch the building update in real time: new readings stream to the browser, a 2D floor plan colours each room by its live state, and the system-status panel reflects the real health of each service.
**FRs covered:** FR37, FR42, FR45

### Epic 3: Knowledge-Grounded Streaming Copilot
Facility staff get Copilot answers grounded in standards, tariffs and operating guides, with cited sources and multi-turn context, streamed token by token from the AI service through the gateway to a Markdown chat, with provider failures visible and answer quality measured.
**FRs covered:** FR16, FR28, FR29, FR30, FR31, FR32, FR38, FR43

### Epic 4: Self-Monitoring Model Lifecycle
The team proves which forecaster to serve with a reproducible benchmark, then runs it under MLflow with drift detection, guarded retraining and an admin monitoring page, so the model keeps itself honest.
**FRs covered:** FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27, FR40, FR44

### Epic 5: Secure Access & RBAC
Users sign in with a role, sessions renew and revoke safely, and the open endpoints from earlier epics are locked down behind authentication and a role matrix, with the frontend routing by role.
**FRs covered:** FR33 (User/RefreshToken), FR34, FR35, FR41

## Epic 1: Live Real-Data Foundation

A real building's data flows end to end. This epic removes the split between the synthetic serving stack and the BDG2 training stack in `ai-service`, stands up a per-zone ingest path fed by a simulator, and makes forecasts and anomalies come from the real models with failures surfaced. Story 1.1 is `done`.

### Story 1.1: Serve energy metrics and time series from BDG2 data

As a facility engineer,
I want the dashboard metrics and load curve to come from the real BDG2 building data,
So that the numbers I act on reflect an actual building rather than a synthetic sample.

**Implements:** FR13, NFR6, NFR7

**Acceptance Criteria:**

**Given** `data/processed/office_building_clean.csv` is present
**When** a client calls `GET /internal/energy/metrics` or `GET /internal/energy/timeseries?limit=N`
**Then** the values are computed from that dataset through `EnergyInferencePipeline` feature preparation
**And** the response field names and types are unchanged (`meter_reading_kwh`, `predicted_kwh`, `timestamp` in ISO 8601 UTC), so the existing frontend keeps working

**Given** the gitignored BDG2 files are absent, as in CI
**When** the test suite runs
**Then** it uses a small committed fixture dataset with the same columns
**And** all existing `ai-service` tests still pass

**Given** the electricity tariff is configured through `TARIFF_RATE_VND`
**When** waste cost is calculated
**Then** the configured value is used instead of the hardcoded 3100

### Story 1.2: Simulate building sensors

As a demo presenter,
I want a simulator that feeds realistic readings into the system,
So that the live features can be shown without real hardware.

**Implements:** FR36

**Acceptance Criteria:**

**Given** the gateway is running
**When** I start the simulator with one command
**Then** it posts readings for all 10 zones every 2 to 5 seconds to the ingest endpoint, deriving values from the BDG2 replay in `stream_worker.py` with per-zone variation

**Given** the simulator is running
**When** I pass `--anomaly-zone <id>`
**Then** that zone's consumption and temperature rise clearly above the others

**Given** the gateway is unreachable
**When** the simulator sends a batch
**Then** it logs the failure and retries on the next tick without exiting

### Story 1.3: Ingest readings per zone

As a building operator,
I want sensors to push readings for each zone of a floor, stored once per timestamp,
So that the system holds current, non-duplicated data for every room.

**Implements:** FR33 (Zone/`zone_id`), FR36, FR39, FR18

**Acceptance Criteria:**

**Given** a migration adding `Zone` (`id`, `building_id`, `floor`, `name`) and an optional `zone_id` on `MeterReading`, with the unique constraint extended to `(building_id, zone_id, timestamp)`
**When** the default building is seeded
**Then** it has 10 zones on one floor
**And** building-level readings with no zone remain unique per `(building_id, timestamp)` through a partial unique index, since PostgreSQL treats null `zone_id` values as distinct

**Given** the migration
**When** it is applied to a database that already holds duplicate readings
**Then** it removes existing duplicates before adding the constraint

**Given** a valid batch of readings (`building_id`, `zone_id`, `timestamp`, `meter_reading_kwh`, optional temperature and humidity)
**When** it is posted to `POST /api/v1/ingest/readings` with a valid `X-Ingest-Key`
**Then** the response is 201 with the number of rows stored, and duplicate `(building_id, zone_id, timestamp)` rows are skipped with `skipDuplicates` rather than raising

**Given** a malformed payload, an unknown building or an unknown zone
**When** it is posted
**Then** the response is 422 and nothing is stored

**Given** a missing or wrong `X-Ingest-Key`
**When** a batch is posted
**Then** the response is 401

**Given** a client (auth added in Epic 5)
**When** it calls `GET /api/v1/buildings/:id/zones`
**Then** each zone is returned with its latest reading, or `null` when it has none

### Story 1.4: Forecast the next 24 hours

As an operations planner,
I want a forecast of the next 24 hours of load,
So that I can plan around the coming peak instead of looking at a replay of the past.

**Implements:** FR13, FR14, NFR3, NFR6

**Acceptance Criteria:**

**Given** the XGBoost artifact in `models_saved/` and at least 24 hours of history
**When** a client calls `GET /internal/forecast/predict`
**Then** the response holds 24 hourly points produced by `predict_forecast_autoregressive`, each with `timestamp`, `predicted_kwh`, `lower_bound_95` and `upper_bound_95`
**And** every timestamp is later than the last observed reading

**Given** the 95% bounds
**When** they are computed
**Then** they use the residual standard deviation measured on the held-out test split, not in-sample residuals

**Given** a warm service
**When** the endpoint is called repeatedly in a test
**Then** the 95th percentile response time is under 300 ms

**Given** fewer than 24 hours of history
**When** the endpoint is called
**Then** it returns a 422 error envelope naming the missing history

### Story 1.5: Detect anomalies on the unified pipeline and fail loudly

As a facility engineer,
I want anomalies detected by the BDG2-trained Isolation Forest, with a clear error when the model is unavailable,
So that I never act on alerts produced by a placeholder model.

**Implements:** FR13, FR15

**Acceptance Criteria:**

**Given** the Isolation Forest artifact in `models_saved/`
**When** a client calls `GET /internal/anomalies/detect`
**Then** anomalies are scored by that artifact using the feature list in `model_metadata.json`
**And** the response keeps its current shape (`id`, `severity`, `timestamp`, `anomaly_score`, `delta_kwh`, `estimated_waste_vnd`)
**And** the `/metrics` anomaly count and this list are computed over the same serving frame so they agree (closing the Story 1.1 deferral)

**Given** a required artifact is missing
**When** any forecast or anomaly endpoint is called
**Then** the service responds 503 with `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}`
**And** no fallback model is trained on random data or written to `models_saved/`

**Given** the consolidated stack
**When** the code is searched
**Then** the lazy in-sample training path in `forecaster_xgboost/predictor.py` and the stray `src/src/models/artifacts/` directory are gone

### Story 1.6: Enforce the internal service token

As a system owner,
I want the AI service to reject calls that do not carry the internal token,
So that nobody can bypass the gateway and reach the models or the LLM directly.

**Implements:** FR17, NFR1

**Acceptance Criteria:**

**Given** `INTERNAL_API_KEY` is configured
**When** a request reaches any `/internal/*` route without `X-Internal-Token` or with a wrong value
**Then** the AI service responds 401

**Given** a request carries the correct token
**When** it reaches an `/internal/*` route
**Then** it is served normally, and `/health` stays reachable without a token

**Given** `INTERNAL_API_KEY` is not set
**When** either service starts outside the test environment
**Then** it fails at startup with a clear message
**And** the fallback secret `ecotrack_internal_secret_2026` no longer exists in `backend/src/utils/aiClient.js`

### Story 1.7: Open the Copilot with the anomaly's context

As a facility engineer,
I want "Ask Copilot" on an anomaly to open the chat with that anomaly's question ready,
So that I get a diagnosis in one click instead of retyping the details.

**Implements:** FR19

**Acceptance Criteria:**

**Given** the anomaly list is shown
**When** I click "Copilot" on a row
**Then** the drawer opens and the prepared diagnostic prompt for that anomaly is sent as the first message

**Given** the drawer is already open with a conversation
**When** I click "Copilot" on a different anomaly
**Then** the new prompt is added to the same conversation without losing earlier messages

**Given** the gateway is unreachable
**When** the dashboard shows its error banner
**Then** the banner names the configured `VITE_API_URL`, not a hardcoded port 8000

## Epic 2: Live Operations Console

Operators watch the building update in real time. Per AD-4, live readings and chat state are held separately so streaming never redraws the charts. These endpoints ship open; Epic 5 adds the auth gate.

### Story 2.1: Push live readings to clients

As a dashboard user,
I want new readings to arrive without refreshing,
So that what I see is the current state of the building.

**Implements:** FR37

**Acceptance Criteria:**

**Given** a client (auth added in Epic 5)
**When** it opens `GET /api/v1/stream/readings?building_id=...`
**Then** the response is `text/event-stream`, and each stored reading is delivered as a `reading` event within one second of ingest

**Given** an open stream
**When** no reading arrives for 15 seconds
**Then** a comment heartbeat is sent to keep the connection alive

**Given** a client disconnects
**When** the connection closes
**Then** its listener is removed and no further writes are attempted

### Story 2.2: See the building live on a floor plan

As a facility engineer,
I want a floor plan that shows each room's current state,
So that I can spot a room wasting energy at a glance.

**Implements:** FR42, NFR10

**Acceptance Criteria:**

**Given** the Floor Plan page
**When** it loads
**Then** an SVG plan of one floor shows the zones returned by `GET /api/v1/buildings/:id/zones`, each labelled with its name and latest temperature

**Given** the readings stream is connected through `fetch`
**When** a reading for a zone arrives
**Then** that zone's colour and values update without reloading, and other components do not re-render

**Given** a toggle between "Nhiệt độ" and "Lãng phí"
**When** I switch it
**Then** zones are coloured on a green-to-red scale for the selected measure, with a legend, and the state is also conveyed by text so it does not rely on colour alone

**Given** I click or press Enter on a zone
**When** the detail panel opens
**Then** it shows the zone's latest readings and an "Hỏi Copilot" action that opens the Copilot with that zone's context

**Given** the stream drops
**When** the connection is lost
**Then** a "Mất kết nối" indicator appears and the client reconnects with backoff

### Story 2.3: Show real system status

As an operator,
I want the status panel to reflect the actual state of each service,
So that I know when something is down.

**Implements:** FR45

**Acceptance Criteria:**

**Given** the gateway `GET /health`
**When** it is called
**Then** it reports the state of the database and of the AI service, including whether the forecast and anomaly models are loaded and which Copilot engine is active

**Given** the Dashboard status panel
**When** it loads and every 30 seconds after
**Then** it shows each component as healthy or unavailable from that response, with no hardcoded values

**Given** the health endpoint cannot be reached
**When** the panel refreshes
**Then** every component is shown as unknown

## Epic 3: Knowledge-Grounded Streaming Copilot

Facility staff get Copilot answers grounded in standards, tariffs and operating guides, streamed end to end. Retrieval follows AD-3: the model reaches knowledge only through a tool that returns compact passages.

### Story 3.1: Build a searchable energy knowledge base

As a facility engineer,
I want the Copilot to have reference material on standards, tariffs and equipment operation,
So that its advice rests on documents rather than on the model's memory.

**Implements:** FR28, FR29, NFR5

**Acceptance Criteria:**

**Given** `ai-service/knowledge_base/`
**When** I list it
**Then** it holds 10 to 20 Markdown documents covering QCVN 09:2017/BXD excerpts, EVN time-of-use tariffs, Chiller/HVAC operating guidance and energy-saving practices, each with a title and source line in its front matter

**Given** the knowledge base
**When** I run `python -m src.rag.ingest`
**Then** documents are split into chunks of about 500 tokens with overlap, embedded with `intfloat/multilingual-e5-small` on CPU, and stored in a persistent ChromaDB collection with document title, source and chunk index as metadata

**Given** the ingest has already run
**When** it runs again
**Then** the collection is rebuilt without duplicate chunks

**Given** a Vietnamese query such as "giá điện giờ cao điểm"
**When** the retriever is called with `k=3`
**Then** at least one returned chunk comes from the tariff document

### Story 3.2: Answer knowledge questions with cited sources

As a facility engineer,
I want the Copilot to cite the documents behind its advice,
So that I can check a recommendation before acting on it.

**Implements:** FR30, NFR9

**Acceptance Criteria:**

**Given** a question about standards, tariffs or equipment operation
**When** the orchestrator handles it
**Then** it calls the `search_knowledge` tool and passes the top passages to the model as context
**And** `tools_used` includes `domain_knowledge`

**Given** an answer that used retrieved passages
**When** it is returned
**Then** the response includes `sources`, a list of `{title, source, snippet}` for the passages used

**Given** a question that is only about live metrics
**When** it is handled
**Then** `search_knowledge` is not called and `sources` is empty

**Given** the vector store has not been built
**When** a knowledge question arrives
**Then** the Copilot still answers from its other tools and logs a warning

### Story 3.3: Keep context across turns

As a facility engineer,
I want to ask follow-up questions without repeating myself,
So that a diagnosis feels like a conversation.

**Implements:** FR31

**Acceptance Criteria:**

**Given** a request with a `history` of earlier turns
**When** the orchestrator builds the model input
**Then** the last 10 turns are included in order, for both the Gemini and the OpenAI path

**Given** a first question about an anomaly and a follow-up "còn nguyên nhân nào khác không?"
**When** the follow-up is handled
**Then** the tool selection takes the earlier turn into account, so the anomaly tool is still used

**Given** an empty or missing `history`
**When** a request arrives
**Then** it is handled as a single-turn question

### Story 3.4: Stream Copilot answers from the AI service

As a Copilot user,
I want to see the answer appear as it is generated,
So that I am not left waiting on a blank screen.

**Implements:** FR38, NFR4

**Acceptance Criteria:**

**Given** a chat request
**When** a client calls `POST /internal/copilot/chat/stream`
**Then** the response is `text/event-stream` with `token` events carrying text fragments, then one `sources` event with the sources and tools used, then one `done` event

**Given** a configured provider
**When** streaming starts
**Then** the provider's streaming API is used, and the first `token` event is sent within 2.5 s

**Given** only the heuristic engine is available
**When** streaming is requested
**Then** the heuristic answer is emitted in chunks using the same event sequence

**Given** a provider fails mid-stream
**When** the failure occurs
**Then** an `error` event with a message is emitted and the stream closes

**Given** the existing `POST /internal/copilot/chat`
**When** it is called
**Then** it still works as before

### Story 3.5: Relay the streamed Copilot answer

As a Copilot user,
I want streamed answers to reach my browser through the gateway,
So that I get the typing effect without the browser talking to the AI service.

**Implements:** FR38, NFR4

**Acceptance Criteria:**

**Given** a client (auth added in Epic 5)
**When** it calls `POST /api/v1/copilot/chat/stream`
**Then** the gateway forwards the request to `/internal/copilot/chat/stream` with the internal token and relays `token`, `sources`, `done` and `error` events unbuffered and in order

**Given** the stream completes
**When** the `done` event has been relayed
**Then** the user message and the full assistant answer are saved as `Conversation` rows

**Given** the client disconnects mid-stream
**When** the gateway notices
**Then** it aborts the upstream request

**Given** the AI service is unreachable
**When** a stream is requested
**Then** the gateway responds 502 before any event is sent

### Story 3.6: Read streamed, formatted Copilot answers with sources

As a facility engineer,
I want Copilot answers to appear as they are written, properly formatted and with their sources,
So that I can start reading immediately and verify what I am told.

**Implements:** FR43, NFR10

**Acceptance Criteria:**

**Given** I send a message
**When** the answer streams from `POST /api/v1/copilot/chat/stream`
**Then** text appears incrementally in the assistant bubble as `token` events arrive

**Given** an answer containing headings, lists, tables or code
**When** it is rendered
**Then** `react-markdown` with `remark-gfm` displays them correctly, replacing the hand-written `MarkdownText`

**Given** a `sources` event
**When** it arrives
**Then** the sources are listed under the answer with title and snippet, and tool badges are shown

**Given** an answer is streaming
**When** I click "Dừng"
**Then** the request is aborted and the partial answer stays visible

**Given** an `error` event or a network failure
**When** it occurs
**Then** the bubble shows an error with a retry action

**Given** the Dashboard charts are visible while an answer streams
**When** tokens arrive
**Then** the chart components do not re-render

### Story 3.7: Make Copilot provider failures visible

As a developer,
I want LLM provider errors logged and model names set in configuration,
So that I can tell whether the Copilot is using a real model or the heuristic fallback, and switch models without a code change.

**Implements:** FR16, NFR9

**Acceptance Criteria:**

**Given** a Gemini or OpenAI call raises an exception
**When** the orchestrator falls through to the next provider
**Then** a warning is logged with the provider name and the error reason
**And** the response still succeeds through the next provider or the heuristic engine

**Given** `GEMINI_MODEL` and `OPENAI_MODEL` are set in the environment
**When** the orchestrator calls a provider
**Then** it uses those names, and no model name is hardcoded in `orchestrator.py`

**Given** any Copilot answer
**When** it is returned
**Then** the response states which engine produced it (`gemini`, `openai` or `heuristic`)

### Story 3.8: Measure RAG quality

As a project reviewer,
I want scores showing how much retrieval improves the Copilot,
So that the value of RAG is demonstrated with numbers.

**Implements:** FR32

**Acceptance Criteria:**

**Given** a golden set of 30 questions, each with a reference answer and the expected source document
**When** I run `python -m experiments.rag_eval.run_eval`
**Then** it reports hit-rate@3 and MRR for retrieval

**Given** an LLM key is configured
**When** the evaluation runs
**Then** it also reports Ragas faithfulness and answer relevancy for answers generated with RAG and without RAG, in one comparison table

**Given** no LLM key is configured
**When** the evaluation runs
**Then** it reports the retrieval metrics and states that the answer metrics were skipped

**Given** a finished evaluation
**When** results are saved
**Then** `results.csv` and a short `REPORT.md` are written under `experiments/rag_eval/`

## Epic 4: Self-Monitoring Model Lifecycle

The team proves which forecaster to serve with a reproducible benchmark, then runs it under MLflow with drift detection, guarded retraining and an admin monitoring page. New code lives under `ai-service/experiments/benchmark/` and `ai-service/src/mlops/` and stays callable as plain Python.

**Working agreement — model training runs (added 2026-10-10 by the project owner):** whenever a story reaches a step that runs a Python file which trains a model (for example `python -m experiments.benchmark.run_benchmark`, `python -m src.models.train_models`, or a retraining script), the AI agent must not run it. It prints the exact command, including the working directory, and the project owner runs it and reports the output back. This applies to every story in this epic, in build, verification and review.

### Story 4.1: Benchmark harness with naive and XGBoost baselines

As an ML engineer,
I want one command that scores forecasting models on the same held-out data,
So that every later model is compared on equal terms.

**Implements:** FR20, FR21

**Acceptance Criteria:**

**Given** the processed BDG2 dataset
**When** I run `python -m experiments.benchmark.run_benchmark`
**Then** Seasonal-naive (value 24 hours earlier) and XGBoost are evaluated on the chronological 80/20 split used by `train_models.py`
**And** `results.csv` holds one row per model with MAE, RMSE, MAPE, R², training time, mean inference latency in ms and model file size

**Given** the harness
**When** a new model is added
**Then** it only needs to implement a small `fit` / `predict` interface and register itself, with no change to the scoring code

**Given** a fixed random seed
**When** the benchmark is run twice
**Then** the accuracy metrics are identical

### Story 4.2: Add a statistical baseline (SARIMAX)

As an ML engineer,
I want a classical statistical model in the comparison,
So that the benchmark covers statistical, tree-based and neural approaches.

**Implements:** FR20

**Acceptance Criteria:**

**Given** the harness from Story 4.1
**When** the benchmark runs
**Then** a SARIMAX model with daily seasonality and air temperature as an exogenous variable is fitted and scored, and appears as a row in `results.csv`

**Given** SARIMAX is slow on the full training set
**When** it is fitted
**Then** it trains on a documented recent window, and the window length is recorded in the results

### Story 4.3: Add an LSTM forecaster

As an ML engineer,
I want a deep learning forecaster in the comparison,
So that the choice of model is backed by a neural baseline and not assumed.

**Implements:** FR20, FR22, NFR5

**Acceptance Criteria:**

**Given** PyTorch installed as a CPU-only build
**When** the benchmark runs
**Then** an LSTM with one or two layers, a 168-hour input window and a 24-hour output is trained and scored, and appears as a row in `results.csv`

**Given** the LSTM training code
**When** it scales its inputs
**Then** the scaler is fitted on the training split only

**Given** a laptop without a GPU
**When** the LSTM trains
**Then** it finishes within 15 minutes, with early stopping on a validation slice taken from the training split

**Given** the LSTM module
**When** it is imported
**Then** it can be used without starting FastAPI (AD-1)

### Story 4.4: Benchmark report and model recommendation

As a project reviewer,
I want charts and a written conclusion from the benchmark,
So that I can see at a glance which model was chosen and the evidence for it.

**Implements:** FR21, FR46

**Acceptance Criteria:**

**Given** the four registered forecasters
**When** the benchmark runs
**Then** each one is also scored at every horizon from 1 to 24 hours ahead on the same test split, using only readings observed before the forecast origin, and the per-horizon MAE and RMSE are written to `results_by_horizon.csv`

**Given** the per-horizon results
**When** the report is generated
**Then** a fourth chart shows error against horizon for all models, and the recommendation states which model is best at 1 hour and at 24 hours ahead

**Given** a completed `results.csv`
**When** I run the report command
**Then** three PNG charts are written: metric comparison across models, actual versus predicted for a sample week, and absolute error by hour of day

**Given** the results
**When** the report is generated
**Then** `REPORT.md` contains the results table, the three charts, and a recommendation that names the model to serve and weighs accuracy against latency and size

**Given** the benchmark results
**When** they are saved
**Then** a `results.json` copy is written for the MLOps page to display

### Story 4.5: Track training runs and register the serving model

As an ML engineer,
I want each training run recorded with its parameters, metrics and artifacts,
So that I can trace which run produced the model in production.

**Implements:** FR23, FR47

**Acceptance Criteria:**

**Given** the XGBoost and LSTM forecasters
**When** the hyperparameter search command runs
**Then** Optuna explores a documented search space for each model with the same number of trials, scores every trial on time-ordered validation slices cut from the training split, and never reads the test split

**Given** a search in progress
**When** a trial finishes
**Then** its parameters and validation metrics are logged to MLflow as a run nested under that model's search

**Given** a finished search
**When** the best parameters are applied
**Then** the benchmark is re-run with them and the tuned and untuned rows can be compared for both models

**Given** MLflow configured with a local SQLite backend stored at a repo-relative path (`ai-service/mlruns/mlflow.db` with its artifact store under `ai-service/mlruns/`), mounted into the AI service container through a Docker volume so the same store is visible to the owner's training runs and to the container at runtime
**When** `train_models.py` runs
**Then** the run logs hyperparameters, RMSE, MAE, MAPE, R², the feature list, the data row counts and the model artifacts
**And** the tracking URI and artifact root are read from configuration as relative paths, never as an absolute machine-specific path

**Given** a completed training run
**When** it is registered
**Then** the model version receives the `champion` alias only if no champion exists yet
**And** registering the first champion is idempotent and guarded against a concurrent run claiming the alias at the same time; promoting a better model over an existing champion is out of scope here and belongs to Story 4.8

**Given** the AI service starts and MLflow is not initialised (no tracking store or no `champion` alias)
**When** it loads the forecast model
**Then** it falls back to `models_saved/` with a logged warning and serves normally

**Given** the AI service starts and the `champion` alias resolves, but its artifact is missing or corrupt or the SQLite backend is locked
**When** it loads the forecast model
**Then** it does not silently fall back; it surfaces the same explicit `503` `ERR_MODEL_NOT_FOUND` error used in Epic 1 Story 1.5, naming the champion version it failed to load

### Story 4.6: Detect data drift and accuracy decay

As an ML engineer,
I want a drift check that compares recent data with the training reference,
So that I know when the model's assumptions no longer hold.

**Implements:** FR24

**Acceptance Criteria:**

**Given** a reference window and a recent window of readings
**When** `drift.check()` runs
**Then** it returns, for `meter_reading` and `air_temperature`, the KS statistic, the p-value and the PSI, plus the rolling 7-day MAPE of the champion model

**Given** thresholds set in configuration (defaults: p-value below 0.05 with PSI above 0.2, or rolling MAPE above 15%)
**When** a threshold is crossed
**Then** the result carries `drift_detected: true` and lists which signals triggered it

**Given** the unmodified dataset and `scenario_hvac_overrun.csv`
**When** drift is checked on each in tests
**Then** the first reports no drift and the second reports drift

### Story 4.7: Measure anomaly detector quality

As an ML engineer,
I want precision, recall and F1 for the anomaly detector,
So that I can state how reliable its alerts are.

**Implements:** FR27

**Acceptance Criteria:**

**Given** data with `is_injected_anomaly` labels and the two demo scenarios
**When** the evaluation script runs
**Then** it reports precision, recall, F1 and false positive rate for the Isolation Forest on each dataset

**Given** the evaluation results
**When** they are saved
**Then** they are logged to the MLflow run of the detector and written to `model_metadata.json`

### Story 4.8: Retrain on demand with guarded promotion

As an admin,
I want to trigger retraining and have the new model replace the old one only if it beats the current champion on an unbiased holdout set,
So that a manual retrain refreshes the model safely and never degrades production forecasts.

**Implements:** FR25, NFR3, NFR5, NFR6, NFR7, NFR8 (builds on FR17, FR23, PRD FR-3, AD-1)

**Acceptance Criteria:**

**Given** a registered `champion` forecaster and valid `X-Internal-Token` authentication
**When** `POST /internal/mlops/retrain` is called while no retrain job is active
**Then** the service atomically acquires an in-process retrain lock, starts the plain-Python retrain coordinator (`ai-service/src/mlops/`) in a background thread without blocking the FastAPI event loop, and immediately returns HTTP 202 with `run_id`, `status: "running"`, and `started_at` in ISO 8601 UTC

**Given** a retrain job is already running
**When** `POST /internal/mlops/retrain` is called again
**Then** the endpoint immediately responds with HTTP 409 Conflict and does not start a second run

**Given** a retrain run executing on the latest dataset
**When** the challenger is trained and compared against the current champion
**Then** both models are evaluated on the same chronological holdout window positioned strictly after the training cutoff of both models (preventing temporal leakage)
**And** both models are scored with an identical MAPE calculation that excludes zero-target (`y == 0`) rows and rejects non-finite (`NaN` or `Inf`) scores

**Given** both holdout MAPE scores are finite
**When** `challenger_mape < champion_mape` (strictly lower)
**Then** the coordinator verifies that the challenger artifact loads and produces a valid prediction before updating the MLflow `champion` alias under `.champion.lock` and calling `reset_serving_cache()` so the service serves the new champion without a restart
**And** when `challenger_mape >= champion_mape`, the existing `champion` alias and in-memory serving model are kept unchanged with outcome `rejected`

**Given** invalid or insufficient data, a missing/uncomparable champion, a non-finite MAPE score, or an error during training, alias promotion, or model reload
**When** the retrain attempt aborts
**Then** the existing usable `champion` remains active in serving, the run is recorded with outcome `failed` and a clear `reason`, and no broken model replaces the champion

**Given** any retrain attempt (`promoted`, `rejected`, or `failed`)
**When** the run reaches a terminal state
**Then** the in-process retrain lock is always released in a `finally` block so future retrain requests are not blocked
**And** a persisted history record stores `run_id`, `timestamp` (ISO 8601 UTC), `trigger` (`"manual"`), `champion_version`, `challenger_version`, `champion_mape`, `challenger_mape`, `outcome` (`"promoted"` | `"rejected"` | `"failed"`), and `reason` for Story 4.9 and Story 4.10 to reuse

### Story 4.9: Retrain automatically when the model degrades

As an admin,
I want the system to check for drift every day and automatically trigger guarded retraining when the model degrades,
So that forecast quality stays reliable without manual monitoring.

**Implements:** FR25, PRD FR-5, NFR5, NFR6, NFR7, NFR8 (builds on FR24, Story 4.6, Story 4.8, AD-1)

**Acceptance Criteria:**

**Given** the AI service runs with `ECOTRACK_SCHEDULER_ENABLED` enabled (default at runtime)
**When** the FastAPI application starts and enters its lifespan
**Then** a stdlib background scheduler (`threading.Event` + daemon `threading.Thread`, without external scheduler packages) waits `ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS` (default `10`s) before executing the first check and repeats every `ECOTRACK_SCHEDULER_INTERVAL_SECONDS` (default `86400`s) without blocking the FastAPI event loop
**And** on application shutdown, the scheduler sets its stop event and performs a bounded thread join so no background thread leaks

**Given** the plain-Python daily check function in `ai-service/src/mlops/`
**When** it runs (using `reference_df` from the first 80% of `get_data_path()` and `recent_df` from `ECOTRACK_DRIFT_RECENT_PATH` or the unmodified baseline dataset at `get_data_path()`, or caller-supplied `reference_df`/`recent_df` frames in tests)
**Then** it executes Story 4.6's `drift.check(...)` and persists the latest snapshot (`checked_at` in ISO 8601 UTC, `drift_detected`, `triggered_signals`, `signals`, `rolling_mape`, `thresholds`, `retrain_triggered`, and `retrain_run_id`) atomically to `get_models_dir() / "drift_status.json"`
**And** when `drift_detected` is `false`, it does not call `run_retrain(...)` and writes nothing to `retrain_history.json`

**Given** `drift.check(...)` returns `drift_detected: true`
**When** the daily check triggers Story 4.8's `run_retrain(...)`
**Then** `trigger` is set to `"mape"` when `triggered_signals == ["rolling_mape"]`, and `"drift"` when any distribution signal (`"meter_reading"` or `"air_temperature"`) triggered (even if accompanied by `"rolling_mape"`)
**And** the full `triggered_signals` list is passed as `signals` and persisted in `retrain_history.json`, while Story 4.8's guarded promotion (`challenger_mape < champion_mape`) determines whether the challenger becomes `champion`

**Given** a manual or prior retrain already holds `_retrain_lock` (`RetrainAlreadyRunningError`), or an unexpected error occurs during a scheduled check tick
**When** the scheduled job runs
**Then** it logs the condition/error cleanly without crashing the scheduler loop or FastAPI process, preserving subsequent scheduled ticks

**Given** the test environment (`ai-service/tests/conftest.py`) or `ECOTRACK_SCHEDULER_ENABLED` set to a falsy value
**When** the FastAPI app starts
**Then** the background scheduler does not start, and the plain-Python daily check job remains directly importable and runnable in `pytest` without FastAPI

### Story 4.10: Report model and drift status

As an admin,
I want one endpoint that summarises the model's health,
So that the monitoring page can show it without knowing MLflow internals.

**Implements:** FR26, NFR5, NFR6, NFR7, NFR8 (builds on FR17, FR21, FR23, FR24, FR25, FR27, AD-1, AD-2, AD-5)

**Acceptance Criteria:**

**Given** a valid `X-Internal-Token` header, an active MLflow `champion` model, and persisted `drift_status.json`, `model_metadata.json` (with `isolation_forest_quality`), `retrain_history.json`, and `experiments/benchmark/results.json`
**When** a client calls `GET /internal/mlops/status` (or calls the plain-Python status aggregator under `ai-service/src/mlops/` directly without FastAPI per AD-1)
**Then** the FastAPI route runs the blocking status collection via `asyncio.to_thread` without blocking the event loop and returns HTTP 200 with: `champion` (`status: "resolved"`, `source: "mlflow"`, `version`, `trained_at` in ISO 8601 UTC from the MLflow run, and `metrics`), `drift` (latest snapshot from `drift_status.json`), `anomaly_quality` (`isolation_forest_quality` from `model_metadata.json`), `retrain_history` (entries ordered newest first by `timestamp`), `benchmark` (the parsed `results.json` payload), and `errors` (`{}` when all present sources load cleanly)
**And** requests without a valid `X-Internal-Token` are rejected with HTTP 401 `ERR_UNAUTHORIZED`

**Given** MLflow is disabled (`ECOTRACK_DISABLE_MLFLOW`), uninitialized, or has no `champion` alias set
**When** status is requested
**Then** the aggregator inspects metadata lightly without deserializing the XGBoost binary and falls back to `get_models_dir()`: when `xgboost_forecaster.joblib` or `model_metadata.json` (`xgboost_metrics`) is available, `champion` reports `source: "local"`, `status: "fallback"`, `version: "local"`, `metrics` from `xgboost_metrics`, and `trained_at` from `train_end_timestamp` in ISO 8601 UTC (`null` when absent, never fabricated from file `mtime`); when no local model exists either, `champion` reports `status: "unavailable"`, `version: null`, `trained_at: null`, `metrics: null`, and the endpoint still responds HTTP 200

**Given** an MLflow `champion` alias resolves but the SQLite registry fails (e.g., locked) or the champion artifact is missing/unreadable
**When** status is requested
**Then** the service never falls back silently to `models_saved/` metrics; it returns HTTP 200 with `champion` reporting `status: "broken"`, `source: "mlflow"`, `metrics: null`, and a diagnostic `error` message while still returning `drift`, `anomaly_quality`, `retrain_history`, and `benchmark`

**Given** no drift check has run yet (`drift_status.json` absent), `isolation_forest_quality` or `model_metadata.json` is absent, no retrain history exists (`retrain_history.json` absent), or `results.json` is absent
**When** status is requested (with configurable benchmark path override for tests)
**Then** the endpoint still responds HTTP 200 with `drift: null`, `anomaly_quality: null`, `retrain_history: []`, and `benchmark: null` respectively

**Given** a persisted JSON artifact (`drift_status.json`, `retrain_history.json`, `model_metadata.json`, or `results.json`) exists on disk with corrupt/invalid JSON or non-finite numbers (`NaN`/`Inf`), or `retrain_history.json` entries are out of timestamp order
**When** the status aggregator runs
**Then** existing fail-loud behavior in `load_drift_status()` and `load_retrain_history()` remains unchanged for scheduler and retrain callers, while the status aggregator logs the error, isolates the failure by returning `null` (or `[]` for `retrain_history`) for the affected section with a per-section diagnostic entry in `errors`, still responds HTTP 200, keeps `retrain_history` stably sorted newest-first by `timestamp`, and rejects/sanitizes non-finite floats so JSON serialization never fails

**Given** the `ai-service` pytest suite
**When** the Story 4.10 offline tests run (without executing model training or starting a live server)
**Then** tests cover the plain-Python aggregator and `GET /internal/mlops/status` across present/absent artifacts, lightweight MLflow metadata lookup, local fallback (`trained_at: null` when `train_end_timestamp` is missing), broken MLflow champion non-fallback visibility, corrupt-JSON isolation in `errors`, newest-first `retrain_history` sorting, `asyncio.to_thread` execution, and `X-Internal-Token` 401 enforcement

### Story 4.11: Expose model monitoring to admins

As an admin,
I want model status and retraining available through the gateway,
So that the monitoring page uses the same protected API as everything else.

**Implements:** FR40

**Acceptance Criteria:**

**Given** a client (the `ADMIN`/`MANAGER` role gate is added in Epic 5, Story 5.3)
**When** it calls `GET /api/v1/mlops/status`
**Then** the gateway returns the AI service's status payload

**Given** a client
**When** it calls `POST /api/v1/mlops/retrain`
**Then** the gateway forwards it and returns the AI service's 202 or 409 response

**Given** the AI service is unreachable
**When** either endpoint is called
**Then** the gateway responds 502 with the standard error envelope

### Story 4.12: Monitor the model as an admin

As an admin,
I want a page showing the model's health and history,
So that I can decide when to retrain and show how the system manages itself.

**Implements:** FR44

**Acceptance Criteria:**

**Given** the MLOps page (role gating arrives with Epic 5, Story 5.4)
**When** it loads `GET /api/v1/mlops/status`
**Then** it shows the champion model's version, training date and metrics; a drift indicator with the signals behind it; the anomaly detector's precision, recall and F1; the retraining history table; and the benchmark table when present

**Given** the page
**When** I click "Retrain" and confirm
**Then** `POST /api/v1/mlops/retrain` is called, the button is disabled while the run is in progress, and the history refreshes when it ends

**Given** a status field is `null`
**When** the page renders
**Then** that section shows an empty state instead of failing

### Story 4.13: Forecast with learned prediction intervals

Scheduled after Story 4.5 (it is numbered 4.13 so that existing story keys keep their numbers).

As a building operator,
I want the forecast band to be wider when the model is less certain and narrower when it is more certain,
So that I can judge how much to trust the forecast at a given hour.

**Implements:** FR48

**Acceptance Criteria:**

**Given** the forecaster chosen for serving
**When** it is trained
**Then** it also learns the 2.5%, 50% and 97.5% quantiles with a pinball (quantile) loss, using XGBoost's quantile objective or a hand-written loss for the LSTM

**Given** the held-out test split
**When** the intervals are evaluated
**Then** the report states the empirical coverage of the 95% interval and its mean width, next to the same two numbers for the current `±1.96 × RMSE` band

**Given** `GET /internal/forecast/predict`
**When** it responds
**Then** `lower_bound_95` and `upper_bound_95` come from the learned quantiles, the lower bound is never below 0 or above `predicted_kwh`, and the response shape is unchanged

**Given** the quantile artifacts are missing
**When** the endpoint is called
**Then** it returns the same explicit `ERR_MODEL_NOT_FOUND` error as for a missing forecaster; it does not fall back to the fixed band silently

## Epic 5: Secure Access & RBAC

Users sign in with a role, sessions renew and revoke safely, and the open endpoints from earlier epics are locked down behind authentication and a role matrix. Each story adds only the tables it needs.

### Story 5.1: Sign in with a role

As a building staff member,
I want to sign in with my email and password,
So that the system knows who I am and what I am allowed to do.

**Implements:** FR33 (User), FR34, NFR1

**Acceptance Criteria:**

**Given** a migration adding `User` with `email` (unique), `password_hash`, `name` and `role` (`ADMIN`, `MANAGER` or `TECHNICIAN`)
**When** the backend starts with `ADMIN_EMAIL` and `ADMIN_PASSWORD` set and no users in the database
**Then** one admin user is created with a bcrypt-hashed password

**Given** valid credentials
**When** I call `POST /api/v1/auth/login`
**Then** I receive a JWT access token valid for 15 minutes containing my user id and role, plus my profile

**Given** a wrong email or password
**When** I call login
**Then** the response is 401 with the same message in both cases

**Given** a `requireAuth` middleware
**When** a request carries a valid access token
**Then** `req.user` is populated
**And** a missing, malformed or expired token gives 401

**Given** `JWT_SECRET` is not set
**When** the backend starts outside the test environment
**Then** it fails at startup with a clear message

### Story 5.2: Stay signed in and sign out

As a signed-in user,
I want my session to renew quietly and end when I log out,
So that I am not interrupted during a shift and my session cannot be reused afterwards.

**Implements:** FR33 (RefreshToken), FR34

**Acceptance Criteria:**

**Given** a migration adding `RefreshToken` with `user_id`, `token_hash`, `expires_at` and `revoked_at`
**When** I log in
**Then** I also receive a refresh token valid for 7 days, and only its hash is stored

**Given** a valid refresh token
**When** I call `POST /api/v1/auth/refresh`
**Then** I receive a new access token and a new refresh token, and the old refresh token is revoked

**Given** a refresh token that was already rotated
**When** it is presented again
**Then** the response is 401 and all refresh tokens of that user are revoked

**Given** a signed-in user
**When** I call `POST /api/v1/auth/logout` with my refresh token
**Then** that token is revoked and can no longer be used

### Story 5.3: Protect operations by role and harden the gateway

As a system owner,
I want sensitive operations limited to the right roles,
So that a technician cannot change what only a manager or admin should.

**Implements:** FR35, FR40 (role gate), NFR2

**Acceptance Criteria:**

**Given** a `requireRole(...roles)` middleware
**When** an authenticated user without an allowed role calls a protected endpoint
**Then** the response is 403

**Given** the role matrix
**When** it is applied
**Then** `POST /buildings`, `POST /energy/cache/clear` and `POST /api/v1/mlops/retrain` require `ADMIN`; `GET /api/v1/mlops/status` requires `ADMIN` or `MANAGER`; `PATCH /anomalies/:id/status` allows all three roles; the ingest and readings-stream routes plus all other `/api/v1/*` routes require authentication; `/health`, `/api/v1/auth/login` and the `X-Ingest-Key`-guarded ingest endpoint stay reachable as defined

**Given** the gateway
**When** it starts
**Then** `helmet` is enabled, CORS allows only origins listed in `CORS_ORIGINS`, and `/api/v1/auth/*` is rate-limited to a configurable number of requests per minute, returning 429 beyond it

**Given** the existing test suite
**When** it runs
**Then** tests authenticate through a shared helper and all pass

### Story 5.4: Sign in and navigate by role

As a building staff member,
I want to sign in and see the pages my role allows,
So that I reach my tools quickly and do not see ones I cannot use.

**Implements:** FR41

**Acceptance Criteria:**

**Given** I am not signed in
**When** I open any page
**Then** I am redirected to the Login page

**Given** valid credentials
**When** I submit the login form
**Then** I land on the Dashboard, and a navigation bar shows Dashboard and Floor Plan, plus MLOps for `ADMIN` and `MANAGER`

**Given** a non-admin user
**When** they open the MLOps URL directly
**Then** they are redirected to the Dashboard

**Given** an API call returns 401 because the access token expired
**When** the Axios interceptor handles it
**Then** it refreshes the token once, retries the call, and redirects to Login only if the refresh fails

**Given** I click "Đăng xuất"
**When** logout completes
**Then** stored tokens are cleared and I am back on the Login page

**Given** wrong credentials
**When** I submit the form
**Then** an inline error is shown and the form stays usable by keyboard
