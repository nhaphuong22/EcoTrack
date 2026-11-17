# Epic 4 Context: Self-Monitoring Model Lifecycle

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic proves which forecasting model should serve production traffic through a reproducible, extensible benchmark (seasonal-naive, SARIMAX, XGBoost, LSTM), then puts the winner under full lifecycle management: MLflow experiment tracking and model registry, scheduled hyperparameter search, data/accuracy drift detection, guarded automatic and manual retraining, anomaly-detector quality measurement, and an admin-facing monitoring page. The outcome is a model that keeps itself honest — its provenance is traceable, its accuracy is continuously measured against live data, and it can only improve itself, never silently regress. New code lives under `ai-service/experiments/benchmark/` and `ai-service/src/mlops/` and must stay callable as plain Python (no FastAPI dependency).

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

- Benchmark: all forecasters run on the same chronological 80/20 split used by `train_models.py`; metrics (MAE, RMSE, MAPE, R², training time, mean inference latency in ms, model file size) are deterministic for a fixed seed and exported to `results.csv`. Adding a model requires only implementing a `fit`/`predict` interface and registering it, with no change to scoring code.
- Per-horizon scoring extends the benchmark across horizons 1–24h ahead (`results_by_horizon.csv`) using only readings available before the forecast origin; the report names the best model at 1h and 24h.
- SARIMAX trains on a documented recent window (recorded in results) due to compute cost. LSTM is CPU-only (PyTorch CPU build), 168h input / 24h output, scaler fit on train split only, early stopping on a training validation slice, and finishes within 15 minutes on a CPU laptop.
- Hyperparameter search (Optuna) for XGBoost and LSTM uses an equal trial budget per model, scores only on time-ordered validation slices from the training split (never the test split), and logs every trial to MLflow nested under that model's search.
- MLflow uses a local SQLite backend at a repo-relative path (`ai-service/mlruns/mlflow.db`, artifacts under `ai-service/mlruns/`), mounted into the AI service container via a Docker volume; tracking URI and artifact root come from config, never hardcoded absolute paths.
- Champion registration and guarded promotion: initial registration of `champion` is idempotent and race-safe when none exists; promoting over an existing champion (Story 4.8+) happens only when the challenger achieves a finite, strictly lower MAPE than the current champion on a shared chronological holdout strictly after both models' training cutoffs (excluding zero-target rows and rejecting `NaN`/`Inf`). Before updating the `champion` alias under `.champion.lock` and calling `reset_serving_cache()`, the challenger artifact is verified to load and predict cleanly.
- Drift detection computes KS statistic, p-value, and PSI on `meter_reading` and `air_temperature` plus rolling 7-day MAPE using configurable thresholds (defaults: p-value < 0.05 with PSI > 0.2, or rolling MAPE > 15%), distinguishing the unmodified dataset (no drift) from `scenario_hvac_overrun.csv` (drift).
- Anomaly detector (Isolation Forest) quality reports precision, recall, F1, and FPR against `is_injected_anomaly` labels and the two demo scenarios (target ≥85% detection rate with FPR ≤12%), logged to MLflow and saved to `model_metadata.json`.
- Manual retrain (`POST /internal/mlops/retrain`): enforces `X-Internal-Token`, atomically acquires an in-process lock, runs the plain-Python coordinator in a background thread, and returns 202 immediately (`run_id`, `status: "running"`, `started_at` UTC); concurrent requests return 409, and the lock is always released in `finally`. Every run persists `run_id`, `timestamp` (UTC), `trigger`, `champion_version`, `challenger_version`, both MAPE values, `outcome` (`promoted`/`rejected`/`failed`), and `reason`.
- Automatic retraining runs as a daily stdlib background job (`threading.Event` + daemon thread in FastAPI `lifespan`, no APScheduler) configured by `ECOTRACK_SCHEDULER_ENABLED` (enabled at runtime, disabled in tests), `ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS` (default 10s), and `ECOTRACK_SCHEDULER_INTERVAL_SECONDS` (default 86400s). The plain-Python daily check resolves `reference_df` (first 80% of `get_data_path()`) and `recent_df` (`ECOTRACK_DRIFT_RECENT_PATH` or unmodified `get_data_path()`), runs `drift.check()`, atomically persists `get_models_dir() / "drift_status.json"` (`checked_at` UTC, `retrain_triggered`, `retrain_run_id`), and calls `run_retrain()` only when `drift_detected` is true (`trigger="mape"` if only `"rolling_mape"` triggered else `"drift"`, passing `signals=triggered_signals`), logging and skipping safely on `RetrainAlreadyRunningError` or tick errors.
- Serving model loading fails loudly: if MLflow is uninitialized, fall back to `models_saved/` with a warning; if the `champion` alias resolves but its artifact is missing/corrupt or SQLite is locked, surface `503 ERR_MODEL_NOT_FOUND` naming the failed version — never fall back silently on a broken champion or missing quantile artifacts.
- Status reporting (`GET /internal/mlops/status` and plain-Python aggregator under `ai-service/src/mlops/`): enforces `X-Internal-Token` (`401 ERR_UNAUTHORIZED`), executes blocking disk/MLflow reads in `asyncio.to_thread`, and responds HTTP 200 with `champion`, `drift`, `anomaly_quality`, `retrain_history`, `benchmark`, and `errors` (`{}` when clean). Champion inspection reads MLflow metadata lightly via `MlflowClient` (`get_model_version_by_alias` + `get_run`) without deserializing the XGBoost binary; when MLflow is disabled/uninitialized or has no `champion` alias, it falls back to `get_models_dir()` (`status: "fallback"`, `source: "local"`, `trained_at` from `train_end_timestamp` in ISO 8601 UTC or `null` when absent — never fabricated from file `mtime`) or `status: "unavailable"` when no local model exists. When a resolved MLflow `champion` is broken/unreadable or SQLite is locked, it never falls back silently to `models_saved/`, reporting `champion.status: "broken"`, `source: "mlflow"`, `metrics: null`, and a diagnostic `error` while still returning other sections.
- Status resilience & serialization: missing optional artifacts return `null` (`drift`, `anomaly_quality`, `benchmark`) or `[]` (`retrain_history`). Fail-loud behavior in `load_drift_status()` and `load_retrain_history()` remains unchanged for scheduler/retrain callers, while the status aggregator catches and logs corrupt JSON or non-finite floats (`NaN`/`Inf`), isolates failures per section (`null`/`[]` plus an entry in `errors`), stably sorts `retrain_history` newest-first by `timestamp`, and sanitizes/rejects non-finite floats for safe JSON serialization.
- Prediction intervals move from fixed `±1.96 × RMSE` to learned 2.5/50/97.5% quantiles (pinball loss), reporting empirical 95% coverage and mean width against the fixed band; served `lower_bound_95` is clamped to `[0, predicted_kwh]` with the response shape unchanged.
- Working agreement: the AI agent must never execute a Python file that trains a model (e.g. `run_benchmark`, `train_models.py`, retraining scripts). Always print the exact command and working directory for the project owner to run and report output back — applies to build, verification, and review for every story in Epic 4.
- Cross-cutting NFRs: CPU-only execution, `asyncio.to_thread` for blocking/CPU work in FastAPI handlers, ISO 8601 UTC (`Z`) timestamps and finite float metrics across API boundaries, offline pytest coverage per story with green CI, and hexagonal plain-Python modules under `experiments/benchmark/` and `src/mlops/`.

## Technical Decisions

- Benchmark and MLOps core logic live under `ai-service/experiments/benchmark/` and `ai-service/src/mlops/` as plain, FastAPI-independent Python modules; `ai-service/src/api/routers/mlops.py` stays a thin HTTP adapter.
- Reuse existing modules rather than duplicating logic: `demo_scenarios.py` for drift/anomaly fixtures, `inference_pipeline.py` for serving features, `tracking.py` for MLflow config, and `serving_frame.py` (`reset_serving_cache()`) for reload.
- The AI service has no database driver and reads data via the feature pipeline; MLflow's local SQLite store is the only new persistence, mounted as a Docker volume so `docker compose up --build` remains reproducible.
- Benchmark outputs are saved in parallel formats: `results.csv` and `results_by_horizon.csv` for metrics, PNG charts and `REPORT.md` for review, and `results.json` (~16 KB) returned verbatim by `GET /internal/mlops/status` (supporting `ECOTRACK_BENCHMARK_RESULTS_PATH` / parameter override for offline tests).
- `GET /internal/mlops/status` is the single source of truth for gateway and frontend consumers; `backend/` proxies `/api/v1/mlops/status` and `/api/v1/mlops/retrain` to `/internal/mlops/*`, translating AI-service unreachability into 502 with the standard error envelope.

## Cross-Story Dependencies

- Story 4.4's per-horizon scoring and report depend on all four forecasters from Stories 4.1–4.3 being registered.
- Story 4.5 (MLflow tracking + `champion` registration) is a prerequisite for Stories 4.6–4.10 and Story 4.13 (which is scheduled after 4.5 and reuses `ERR_MODEL_NOT_FOUND` from Story 1.5).
- Story 4.8 (manual guarded retrain) must land before Story 4.9 (daily scheduler reusing `drift.check()` from 4.6 and `run_retrain()` from 4.8).
- Story 4.10 builds on `X-Internal-Token` (Story 1.6) and aggregates outputs from 4.4 (`results.json`), 4.5 (champion metadata), 4.6/4.9 (`drift_status.json`), 4.7 (`isolation_forest_quality`), and 4.8/4.9 (`retrain_history.json`), degrading cleanly (`null`/`[]`) when optional artifacts are absent.
- Story 4.11 (gateway proxy) depends on 4.8 and 4.10; Story 4.12 (frontend MLOps page) depends on 4.11.
- Role gating (`ADMIN`/`MANAGER` on status, `ADMIN`-only on retrain, role-aware MLOps navigation) is deferred to Epic 5 (Stories 5.3 and 5.4); Story 4.12 renders without a role gate until Epic 5 lands.
