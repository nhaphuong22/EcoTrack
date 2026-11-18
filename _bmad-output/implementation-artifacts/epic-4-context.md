# Epic 4 Context: Self-Monitoring Model Lifecycle

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Prove which forecaster to serve with a reproducible benchmark, then run it under MLflow with drift detection, guarded retraining (manual and scheduled), a consolidated status endpoint, a protected gateway proxy and an admin monitoring page. New code lives under `ai-service/experiments/benchmark/` and `ai-service/src/mlops/` and stays callable as plain Python. Note: the PRD/architecture spine in the planning directory predate this epic and say little about it; this context is drawn mainly from the epics file.

## Stories

- Story 4.1: Benchmark harness with naive and XGBoost baselines
- Story 4.2: Add a statistical baseline (SARIMAX)
- Story 4.3: Add an LSTM forecaster
- Story 4.4: Benchmark report and model recommendation
- Story 4.5: Track training runs and register the serving model
- Story 4.6: Detect data drift and accuracy decay
- Story 4.7: Measure anomaly detector quality
- Story 4.8: Retrain on demand with guarded promotion
- Story 4.9: Retrain automatically when the model degrades
- Story 4.10: Report model and drift status
- Story 4.11: Expose model monitoring to admins
- Story 4.12: Monitor the model as an admin
- Story 4.13: Forecast with learned prediction intervals

## Requirements & Constraints

- Working agreement: the AI agent must never run a Python file that trains a model (benchmark, `train_models`, retrain scripts). Print the exact command with working directory; the project owner runs it and reports back. Applies to build, verification and review.
- Models are compared on the same chronological 80/20 split; accuracy metrics must be reproducible with a fixed seed. Scalers/tuning never touch the test split.
- MLflow tracking uses a repo-relative SQLite store (`ai-service/mlruns/`), shared with the container via a Docker volume; never absolute machine paths.
- Serving: no MLflow or no `champion` alias falls back to `models_saved/` with a warning; a resolvable but broken champion must surface explicit `503 ERR_MODEL_NOT_FOUND`, never a silent fallback.
- Retraining promotes only if challenger MAPE is strictly lower than champion MAPE on a holdout after both training cutoffs (MAPE excludes zero targets, rejects non-finite); failures keep the existing champion. One retrain at a time (in-process lock, 409 otherwise), always released in `finally`; every attempt is recorded in persisted history.
- Drift: KS, p-value, PSI for `meter_reading` and `air_temperature` plus rolling 7-day MAPE; configurable thresholds.
- Status endpoint degrades gracefully: missing or corrupt artifacts yield `null`/`[]` per section with entries in `errors`, still HTTP 200.
- Story 4.11 gateway (FR40):
  - `GET /api/v1/mlops/status` proxies `GET /internal/mlops/status` unchanged. A `champion.status` of `fallback`, `unavailable` or `broken` is still HTTP 200.
  - The status response is cached for `MLOPS_STATUS_CACHE_TTL_SECONDS` (default 5). The cache is cleared after any `POST /api/v1/mlops/retrain`.
  - `POST /api/v1/mlops/retrain` forwards `POST /internal/mlops/retrain` with no body. The AI service's 202 and 409 status and body (including `run_id`) pass through verbatim.
  - Retrain is rate limited by `MLOPS_RETRAIN_RATE_LIMIT_PER_MINUTE` (default 3). Over the limit returns 429 in the standard envelope without calling the AI service.
  - Error mapping: AI service unreachable gives 502, timeout gives 504, and any other non-2xx upstream status (e.g. 401 token mismatch, 500) gives 502 with `upstream_status` and a fixed per-status `message`. The upstream body is logged server-side only and never returned.
  - Tests mock the AI service.
- Story 4.13: learned 2.5/50/97.5% quantile intervals replace the fixed band; missing quantile artifacts give an explicit `ERR_MODEL_NOT_FOUND`, never a silent fallback.

## Technical Decisions

- AD-1: all ML, drift, benchmark and status logic is plain Python under `ai-service/src/mlops/` (and `experiments/`); FastAPI routers are thin adapters; only lifespan hooks are wired in `main.py`.
- AD-2: blocking work in async routes runs via `asyncio.to_thread` (status aggregation) or a background thread (retrain, returns 202 immediately).
- AD-5: timestamps are ISO 8601 UTC, energy values floats.
- Internal AI-service endpoints (`/internal/mlops/status`, `/internal/mlops/retrain`) require `X-Internal-Token` (401 `ERR_UNAUTHORIZED` otherwise). The gateway reaches them via the existing `callAIService` client (injects the token, 30 s timeout).
- Persisted artifacts in `get_models_dir()`: `drift_status.json`, `retrain_history.json`, `model_metadata.json` (includes `isolation_forest_quality`); benchmark output `experiments/benchmark/results.json`. Loaders for drift and history stay fail-loud for scheduler and retrain callers; only the status aggregator isolates failures.
- Scheduler is stdlib (`threading.Event` + daemon thread), controlled by `ECOTRACK_SCHEDULER_ENABLED`, `..._INITIAL_DELAY_SECONDS` (10) and `..._INTERVAL_SECONDS` (86400). It is disabled under tests. Retrain trigger is `manual`, `mape` (rolling_mape only) or `drift` (any distribution signal).
- Promotion updates the MLflow `champion` alias under `.champion.lock`, then calls `reset_serving_cache()` so no restart is needed.
- The role gate (ADMIN/MANAGER, ADMIN-only retrain) is added in Epic 5, not in Epic 4.

## UX & Interaction Patterns

- MLOps page (Story 4.12) reads `GET /api/v1/mlops/status` and shows champion version, training date and metrics, a drift indicator with its signals, anomaly precision/recall/F1, retrain history and the benchmark table.
- Retrain needs a confirm step. The button is disabled while a run is in progress, and history refreshes when the run ends. A 409 means a run is already active, so show "running".
- Any `null` section renders an empty state, never an error.

## Cross-Story Dependencies

- 4.1 is the base for 4.2, 4.3 and 4.4 (new models plug into its `fit`/`predict` registry). 4.4 writes `results.json`, which 4.10 and 4.12 display.
- 4.5 (MLflow registry and `champion` alias) underpins 4.6, 4.8, 4.10 and 4.13.
- 4.6 drift check feeds 4.9. 4.8 `run_retrain` and its history are reused by 4.9 and 4.10.
- 4.7 anomaly quality is surfaced through 4.10.
- 4.10 status feeds 4.11, which feeds 4.12. 4.11 retrain also depends on 4.8.
- Epic 5 (Stories 5.3 and 5.4) later adds the role gates on 4.11 and 4.12.
- 4.13 is scheduled after 4.5.
