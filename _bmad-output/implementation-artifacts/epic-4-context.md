# Epic 4 Context: Self-Monitoring Model Lifecycle

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Prove which forecaster to serve with a reproducible benchmark, then run it under MLflow with drift detection, guarded retraining (manual and scheduled) and an admin monitoring page, so the model keeps itself honest. Quality of the forecaster and anomaly detector becomes measurable, traceable and self-correcting.

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

- Models are compared on one chronological 80/20 split (same as `train_models.py`) with MAE, RMSE, MAPE, R2, training time, inference latency and model size; a fixed seed must give identical accuracy metrics. New models only implement a small fit/predict interface and register themselves.
- Per-horizon (1-24h) scoring uses only data observed before the forecast origin. The benchmark emits results.csv, results_by_horizon.csv, results.json, charts and REPORT.md with a recommendation weighing accuracy, latency and size.
- LSTM: CPU-only PyTorch, 168h input / 24h output, scaler fitted on train split only, trains in under 15 minutes with early stopping.
- Hyperparameter search (Optuna) uses equal trial counts per model, time-ordered validation slices from the training split, and never touches the test split.
- Drift: KS statistic, p-value and PSI for meter_reading and air_temperature plus rolling 7-day MAPE; thresholds are configurable (defaults p<0.05 with PSI>0.2, or MAPE>15%). The unmodified dataset must show no drift and `scenario_hvac_overrun.csv` must show drift.
- Promotion is guarded: a challenger replaces the champion only if its holdout MAPE is strictly lower on a chronological holdout after both training cutoffs; MAPE excludes zero targets and rejects non-finite scores. Any failure keeps the existing champion. Only one retrain may run at a time.
- Anomaly detector quality (precision, recall, F1, FPR) is measured on labelled and scenario data.
- Learned 2.5/50/97.5% quantile intervals replace the fixed +/-1.96*RMSE band; coverage and width are reported against the old band.
- Working agreement: the AI agent must never run Python files that train models (benchmark, train_models, retraining scripts); print the exact command with working directory for the project owner to run.

## Technical Decisions

- New code lives in `ai-service/experiments/benchmark/` and `ai-service/src/mlops/` and must stay callable as plain Python without FastAPI (AD-1). Blocking work in routes runs via `asyncio.to_thread` (AD-2). Timestamps are ISO 8601 UTC (AD-5).
- MLflow uses a local SQLite backend at a repo-relative path (`ai-service/mlruns/`), mounted into the AI container by Docker volume; tracking URI and artifact root come from config as relative paths. The `champion` alias is set only if none exists (idempotent, concurrency-guarded); promotion over an existing champion belongs to retraining. Promotion updates the alias under `.champion.lock` then calls `reset_serving_cache()`.
- Model loading: no MLflow store or no champion falls back to `models_saved/` with a warning; a resolved champion with a missing/corrupt artifact or locked store returns 503 `ERR_MODEL_NOT_FOUND` naming the version, never a silent fallback. Missing quantile artifacts also give `ERR_MODEL_NOT_FOUND`.
- Retrain: `POST /internal/mlops/retrain` takes an in-process lock, runs in a background thread, returns 202 (`run_id`, `status`, `started_at`) or 409 if running; the lock is always released in `finally`. History persists to `retrain_history.json` (run_id, timestamp, trigger, versions, MAPEs, outcome promoted/rejected/failed, reason).
- Scheduler: stdlib `threading.Event` + daemon thread (no external scheduler package), env-configured (`ECOTRACK_SCHEDULER_ENABLED`, `_INITIAL_DELAY_SECONDS` default 10, `_INTERVAL_SECONDS` default 86400), started in FastAPI lifespan with bounded join on shutdown, disabled in tests. Daily check writes `drift_status.json` in the models dir; trigger is `mape` only when rolling_mape is the sole signal, else `drift`. Errors and an already-running retrain are logged without killing the loop.
- Status: `GET /internal/mlops/status` (X-Internal-Token, else 401 `ERR_UNAUTHORIZED`) always returns 200, aggregating champion (resolved/fallback/unavailable/broken; fallback metrics from `model_metadata.json`, `trained_at` null rather than fabricated), drift, anomaly_quality, retrain_history (newest first), benchmark, and a per-section `errors` map. Corrupt JSON or non-finite numbers are isolated per section, never fail the response.
- Gateway: `GET /api/v1/mlops/status` is a pass-through via `callAIService` with a short TTL cache (`MLOPS_STATUS_CACHE_TTL_SECONDS`, default 5) cleared after retrain; non-resolved champion statuses stay HTTP 200. `POST /api/v1/mlops/retrain` forwards with no body and returns 202/409 verbatim, rate limited (`MLOPS_RETRAIN_RATE_LIMIT_PER_MINUTE`, default 3, 429). Upstream unreachable gives 502, timeout 504, other non-2xx gives 502 with `upstream_status` and a fixed message; upstream bodies are never returned. All use the standard error envelope.
- Endpoints in Epics 1-4 ship open (internal token only); Epic 5 applies auth and the role matrix.

## UX & Interaction Patterns

- MLOps is a tab in the operations dashboard (`App.jsx` uses tabs, no router). It shows champion version/date/metrics, drift indicator with signals, anomaly precision/recall/F1, retrain history, and the benchmark table; drift and benchmark are Recharts charts following existing dashboard conventions.
- Null sections show an empty state; `errors[section]` shows a distinct error state; non-resolved champion statuses show a banner, and `broken` shows the error prominently and is never styled as healthy.
- Retrain button: confirm dialog, disabled while running. After 202, poll status every 4s until history contains the run_id or a 15-minute ceiling (then a "still running or unknown" message). 409 shows "already running" and starts polling; 429/502/504 show the gateway message without permanently disabling the button. Idle refresh every 30s. All polling pauses when the browser tab is hidden and stops on unmount.
- Visibility: only a platform ADMIN or a MANAGER of the displayed building (`office_tower_01`) sees the tab (gateway returns 403 otherwise); only ADMIN sees "Retrain". `AccountPortal` must pass `user.role` to the dashboard. Status stays platform-wide.

## Cross-Story Dependencies

- 4.2 and 4.3 plug into the 4.1 harness; 4.4 reports on all four models; 4.5 tunes and registers XGBoost/LSTM and the champion alias used by 4.6, 4.8, 4.10.
- 4.8 builds on 4.5 and 4.6; 4.9 reuses 4.6 drift check and 4.8 `run_retrain` and history; 4.10 aggregates outputs of 4.4 (results.json), 4.6/4.9 (drift_status), 4.7 (isolation_forest_quality), 4.8 (history).
- 4.11 wraps 4.8 and 4.10 in the gateway; 4.12 consumes 4.11. 4.13 is scheduled after 4.5.
- Role gating of these endpoints and the tab arrives with Epic 5 (Stories 5.3, 5.4); until then they are open. Builds on Epic 1 Story 1.5 (`ERR_MODEL_NOT_FOUND`).
