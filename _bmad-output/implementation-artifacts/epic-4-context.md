# Epic 4 Context: Self-Monitoring Model Lifecycle

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

The team proves which forecaster to serve with a reproducible benchmark, then runs the serving model under MLflow with drift detection, guarded retraining (manual and scheduled) and an admin monitoring page, so the model keeps itself honest and the system visibly manages its own quality.

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

- Forecasters (seasonal-naive, XGBoost, SARIMAX, LSTM) are scored on one chronological 80/20 split with MAE, RMSE, MAPE, R2, training time, inference latency and model size; results are reproducible under a fixed seed, and new models plug in via a small fit/predict interface. Per-horizon (1-24 h) results use only data observed before the forecast origin.
- LSTM: CPU-only PyTorch, 168 h input / 24 h output, scaler fitted on train split only, trains in under 15 minutes with early stopping.
- Hyperparameter search (Optuna) uses time-ordered validation slices from the training split and never touches the test split.
- Promotion is guarded: a challenger replaces the champion only if its holdout MAPE is strictly lower on a window after both models' training cutoffs; MAPE excludes zero targets and rejects non-finite scores. Failures never replace a usable champion. Retrain lock is always released; every attempt is persisted to history (promoted/rejected/failed).
- Drift: KS, p-value and PSI on `meter_reading` and `air_temperature` plus rolling 7-day MAPE; thresholds configurable (defaults p<0.05 with PSI>0.2, or MAPE>15%).
- Anomaly detector quality (precision, recall, F1, FPR) is reported and saved with the model metadata.
- Forecast intervals (4.13) are learned quantiles (2.5/50/97.5), bounds always enclose `predicted_kwh` and lower bound is at least 0; forecast endpoint keeps the 300 ms p95 budget.
- Only the platform ADMIN (or a MANAGER of the displayed building) sees the MLOps tab; only ADMIN sees "Retrain"; the gateway is the authority. Endpoints ship open before Epic 5 adds role gating.

## Technical Decisions

- Working agreement: the AI agent must never run Python files that train models (benchmark, train_models, retrain scripts); print the exact command with working directory and let the project owner run it.
- New code lives under `ai-service/experiments/benchmark/` and `ai-service/src/mlops/` and must be callable as plain Python without FastAPI (AD-1); blocking work in routes runs via `asyncio.to_thread` (AD-2); timestamps are ISO 8601 UTC (AD-5).
- MLflow uses a local SQLite backend at a repo-relative path (`ai-service/mlruns/`), mounted into the container by Docker volume; tracking URI/artifact root come from config as relative paths. The `champion` alias is set on first registration only (idempotent, concurrency-guarded); later promotion is only via retrain, under `.champion.lock`, followed by `reset_serving_cache()`.
- Model loading: no MLflow store or no champion falls back to `models_saved/` with a warning; a champion that resolves but fails to load must not fall back and surfaces 503 `ERR_MODEL_NOT_FOUND`. Quantile artifacts are registered in the same champion version as the point model; missing ones also yield `ERR_MODEL_NOT_FOUND`.
- AI-service internal endpoints (`X-Internal-Token`, 401 `ERR_UNAUTHORIZED`): `POST /internal/mlops/retrain` (202 with run_id, 409 if running; in-process lock, background thread) and `GET /internal/mlops/status` (champion with status resolved/fallback/unavailable/broken, drift, anomaly_quality, retrain_history newest-first, benchmark, per-section `errors`; always 200, sections degrade to null/[] and non-finite floats are sanitized).
- Persisted artifacts in the models dir: `drift_status.json`, `retrain_history.json`, `model_metadata.json`; benchmark outputs `results.csv`, `results_by_horizon.csv`, `results.json`, `REPORT.md`. Loaders for drift/history stay fail-loud for scheduler/retrain callers; only the status aggregator isolates failures.
- Scheduler: stdlib thread + stop event started in FastAPI lifespan (`ECOTRACK_SCHEDULER_ENABLED`, initial delay and interval env vars), bounded join on shutdown, disabled in tests; tick errors and lock conflicts are logged without killing the loop. Trigger is `"mape"` only when rolling_mape is the sole signal, otherwise `"drift"`.
- Gateway (`/api/v1/mlops/status` and `/retrain`): proxies via `callAIService`, status cached (`MLOPS_STATUS_CACHE_TTL_SECONDS`, 5) and cleared after retrain, retrain rate limited (`MLOPS_RETRAIN_RATE_LIMIT_PER_MINUTE`, 3, returns 429), retrain forwarded with no body and 202/409 returned verbatim; unreachable maps to 502, timeout to 504, other upstream non-2xx to 502 with `upstream_status` and no upstream body leaked. Standard error envelope throughout.
- Conventions: snake_case Python, PascalCase React components, kebab-case plural `/api/v1/` resources.

## UX & Interaction Patterns

- MLOps is a tab in the operations dashboard (`App.jsx` uses tabs, no router); `AccountPortal` passes `user.role` to the dashboard.
- Page shows champion version/date/metrics, drift indicator with signals, anomaly precision/recall/F1, retrain history table, and benchmark table; drift and benchmark use Recharts following existing dashboard chart conventions.
- A null section shows an empty state; an `errors[section]` shows a distinct error state while other sections still render. Non-resolved champion status shows a banner; "broken" shows the error text prominently, never styled as healthy.
- Retrain: confirm dialog, button disabled while running; after 202 poll status every 4 s until history holds that `run_id` or a 15-minute ceiling ("still running or unknown"); poll pauses when tab hidden and stops on unmount. When idle, quiet refresh every 30 s (same pause/stop rules). 409 shows "already running" and starts polling; 429/502/504 show the gateway message without permanently disabling the button.

## Cross-Story Dependencies

- 4.1 harness underpins 4.2, 4.3, 4.4 and the tuned re-run in 4.5; 4.4 produces `results.json` consumed by 4.10 and 4.12.
- 4.5 (MLflow registry, champion alias) is required by 4.6 (rolling MAPE of champion), 4.8, 4.10 and 4.13; 4.7 writes `isolation_forest_quality` for 4.10.
- 4.8 retrain coordinator and history are reused by 4.9 (scheduler) and 4.10; 4.6 drift check is reused by 4.9.
- 4.10 feeds 4.11 (gateway), which feeds 4.12 (UI). 4.13 depends on 4.5 and keeps 4.8's promotion gate unchanged.
- Epic 1 Story 1.5 defines the `ERR_MODEL_NOT_FOUND` behavior reused here; Epic 5 (Stories 5.3, 5.4) later adds `requireAuth`/role gating and the role-aware frontend over these open endpoints.
