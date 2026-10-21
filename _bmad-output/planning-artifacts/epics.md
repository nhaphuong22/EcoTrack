---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - plan.md
  - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/prd.md
  - _bmad-output/planning-artifacts/prds/prd-EcoTrack-2026-09-23/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-EcoTrack-2026-09-23/ARCHITECTURE-SPINE.md
---

# EcoTrack - Epic Breakdown

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

**Given** MLflow configured with a local SQLite backend
**When** `train_models.py` runs
**Then** the run logs hyperparameters, RMSE, MAE, MAPE, R², the feature list, the data row counts and the model artifacts

**Given** a completed training run
**When** it is registered
**Then** the model version receives the `champion` alias only if no champion exists yet

**Given** the AI service starts
**When** it loads the forecast model
**Then** it loads the version behind the `champion` alias, and falls back to `models_saved/` with a logged warning if MLflow is not initialised

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
I want to trigger retraining and have the new model replace the old one only if it is better,
So that a retrain can never make forecasts worse.

**Implements:** FR25

**Acceptance Criteria:**

**Given** a champion model
**When** `POST /internal/mlops/retrain` is called
**Then** a challenger is trained on the latest data in a background thread, and the endpoint returns 202 with a run id immediately

**Given** the challenger and the champion are scored on the same holdout set
**When** the challenger's MAPE is lower
**Then** it receives the `champion` alias and the service serves it without a restart
**And** when it is not lower, the champion is kept

**Given** any retrain attempt
**When** it finishes
**Then** a history record stores the timestamp, the trigger (`manual`), both MAPE values and the outcome (`promoted` or `rejected`)

**Given** a retrain is already running
**When** the endpoint is called again
**Then** it responds 409

### Story 4.9: Retrain automatically when the model degrades

As an admin,
I want the system to check for drift every day and retrain when needed,
So that the model stays accurate without someone watching it.

**Implements:** FR25

**Acceptance Criteria:**

**Given** the AI service is running with the scheduler enabled
**When** the daily job fires
**Then** it runs the drift check from Story 4.6 and starts a retrain only if `drift_detected` is true

**Given** an automatic retrain
**When** it is recorded
**Then** the history entry has the trigger `drift` or `mape` and the signals that caused it

**Given** the test environment
**When** the service starts
**Then** the scheduler is disabled through configuration, and the job function can be called directly in tests

### Story 4.10: Report model and drift status

As an admin,
I want one endpoint that summarises the model's health,
So that the monitoring page can show it without knowing MLflow internals.

**Implements:** FR26

**Acceptance Criteria:**

**Given** a champion model and at least one drift check
**When** a client calls `GET /internal/mlops/status`
**Then** the response contains the champion's version, training date and metrics; the latest drift result; the anomaly detector's quality metrics; and the retraining history, newest first

**Given** the benchmark `results.json` exists
**When** status is requested
**Then** the benchmark table is included, and the field is `null` when the file is absent

**Given** no drift check has run yet
**When** status is requested
**Then** the drift field is `null` and the endpoint still responds 200

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
