---
title: 'Story 4.9: Retrain automatically when the model degrades'
type: 'feature'
created: '2026-11-17'
status: 'done'
baseline_commit: 'ec4a4879656272b1644fc4de9f3a76818180ae1d'
route: 'oneshot'
review_loop_iteration: 0
story_keys:
  - 4-9-retrain-automatically-when-the-model-degrades
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After Story 4.6 added drift/accuracy-decay checks (`drift.check()`) and Story 4.8 added guarded retraining (`run_retrain()`), there is still no daily automated check to monitor model degradation and trigger retraining when needed (FR25, PRD FR-5).

**Approach:** Add a plain-Python scheduler and check orchestrator (`ai-service/src/mlops/scheduler.py`, AD-1) using Python stdlib (`threading.Event` + daemon `threading.Thread`, zero new dependencies since `plan.md` was excluded) and wire it into FastAPI's `lifespan` in `ai-service/src/main.py`:
- **Configurable stdlib scheduler:** Add runtime env helpers in `ai-service/src/mlops/config.py` for `ECOTRACK_SCHEDULER_ENABLED` (default enabled at runtime, disabled in `ai-service/tests/conftest.py`), `ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS` (default `10`), `ECOTRACK_SCHEDULER_INTERVAL_SECONDS` (default `86400`), and `ECOTRACK_DRIFT_RECENT_PATH`. On FastAPI startup (`lifespan`), start the daemon loop only when enabled; wait `initial_delay` then call `run_drift_check_and_retrain()` every `interval` seconds without blocking the event loop (NFR6 / AD-2), catching and logging tick errors so the scheduler loop stays alive, and shutting down cleanly via `stop_event.set()` + bounded `join()`.
- **Plain-Python check & guarded retrain job:** `run_drift_check_and_retrain(...)` resolves `reference_df` (first 80% chronological split of `get_data_path()`) and `recent_df` (`ECOTRACK_DRIFT_RECENT_PATH` if set, else trailing 168 hours of `get_data_path()`), or accepts injected `reference_df` / `recent_df` frames in tests, and runs Story 4.6's `drift.check(...)`. When `drift_detected` is `true`, it classifies `trigger="mape"` if `triggered_signals == ["rolling_mape"]` else `trigger="drift"`, and invokes Story 4.8's `run_retrain(trigger=..., signals=triggered_signals)`. Concurrent `RetrainAlreadyRunningError` is logged and skipped safely without crashing the loop.
- **Drift snapshot persistence (for Story 4.10):** Every completed check (whether drift is detected or not) atomically persists `get_models_dir() / "drift_status.json"` via `retrain._atomic_write_bytes` with `checked_at` (ISO 8601 UTC, NFR7), `drift_detected`, `triggered_signals`, `signals`, `rolling_mape`, `thresholds`, `retrain_triggered`, and `retrain_run_id` (plus `load_drift_status()`).
- **Offline pytest suite (`ai-service/tests/test_mlops_scheduler.py`):** Verify no-drift skips retraining (`retrain_history.json` untouched), `rolling_mape`-only triggers `trigger="mape"`, distribution drift triggers `trigger="drift"` with full `signals`, `ECOTRACK_DRIFT_RECENT_PATH` and default window resolution, safe handling of `RetrainAlreadyRunningError` and tick errors, `conftest.py` disabling the scheduler during tests, and FastAPI `lifespan` startup/shutdown when enabled in test.

</frozen-after-approval>

## Implementation Notes

- Added stdlib configuration helpers (`scheduler_enabled()`, `get_scheduler_interval_seconds()`, `get_scheduler_initial_delay_seconds()`, `get_drift_recent_path()`) in `ai-service/src/mlops/config.py` with whitespace stripping and `math.isfinite()` validation.
- Created `ai-service/src/mlops/scheduler.py` (plain-Python, AD-1, zero new packages) exposing `run_drift_check_and_retrain()`, `load_drift_status()`, `start_scheduler()`, `stop_scheduler()`, and `is_scheduler_running()`:
  - Uses `threading.Event` + daemon `threading.Thread` with configurable `initial_delay` (default `10s`) and `interval` (default `86400s`), logging tracebacks on tick failures without stopping the scheduler loop, and retaining active thread tracking if `stop_scheduler(timeout=...)` times out.
  - Resolves `reference_df` as the chronological first 80% of `get_data_path()`, and `recent_df` from `ECOTRACK_DRIFT_RECENT_PATH` when set or the unmodified baseline dataset (`_load_base_feat()`, whose trailing 168h are scored for rolling MAPE) when unset — preventing spurious seasonal drift (`PSI 7.68 / 8.34`) on static CSV startup. Resolves scoped champion from `(models_dir, tracking_uri)` when provided, triggers `run_retrain(trigger="mape" | "drift", signals=triggered_signals)` only when `drift_detected` is `true`, handles `RetrainAlreadyRunningError` cleanly, and persists `get_models_dir() / "drift_status.json"` in `try/finally`.
- Wired FastAPI `lifespan` in `ai-service/src/main.py` (importing `scheduler` after `sys.path` insertion and `load_dotenv(...)`) to call `start_scheduler()` on startup and `await asyncio.to_thread(stop_scheduler)` on shutdown.
- Isolated `ECOTRACK_SCHEDULER_ENABLED=0` and Story 4.9 env overrides in `ai-service/tests/conftest.py` (with `stop_scheduler()` in teardown), documented optional env vars in `ai-service/.env.example`, and added offline tests in `ai-service/tests/test_mlops_scheduler.py`.
- Per the Epic 4 working agreement, the agent verified bytecode compilation (`python -m py_compile`) without executing `pytest`; command for the project owner to run:
  - Working directory: `c:\Users\ADMIN\Desktop\EcoTrack\ai-service`
  - Command: `pytest tests/test_mlops_scheduler.py tests/test_mlops_drift.py tests/test_mlops_retrain.py -q`

## Review Triage Log

Blind-hunter (only layer configured in this render) against Story 4.9 changes (~20.62 KB -> N = min(floor(sqrt(20.62)+1), 10) = 5; 11 findings reported).

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `main.py` imported `scheduler` before `sys.path.insert` and `load_dotenv()` | high | patch | `mlops.config` froze `DRIFT_*` / `REGISTERED_MODEL_NAME` constants before `.env` loaded. Moved import below `load_dotenv()`. |
| 2 | Env float getters lacked empty-string fallback and `math.isfinite()` checks | medium | patch | Added `_parse_env_float()` checking empty strings and `math.isfinite()`, plus finite checks on `start_scheduler()` args. |
| 3 | Default `_load_base_feat().tail(168)` vs `train_df` caused seasonal drift (`PSI 7.68 / 8.34`) on static CSV at every startup | high | patch | Confirmed directly against `office_building_clean.csv` and `office_building_sample.csv`; defaulted `recent_df` to unmodified `_load_base_feat()` (`PSI 0.016 / 0.0026`, rolling MAPE still scores `.tail(168)`) and updated `epics.md` / `epic-4-context.md`. |
| 4 | `ECOTRACK_DRIFT_RECENT_PATH` drops 24 lag rows and `run_retrain()` trains on `data_path` instead of `recent_path` | false | reject | `drift._ensure_engineered` intentionally drops lag warm-up and degrades via `insufficient_data`; `run_retrain()` intentionally avoids training on anomalous scenario CSVs per Party Mode decision. |
| 5 | `run_drift_check_and_retrain(..., models_dir=..., tracking_uri=...)` ignored scoped args during `drift.check()` champion resolution | high | patch | Added `_resolve_champion_if_scoped()` using `_resolve_current_champion(resolved_models, tracking_uri=tracking_uri)` before calling `drift.check()`. |
| 6 | `stop_scheduler()` cleared `_scheduler_thread` / `_stop_event` even when `thread.join(timeout)` timed out | medium | patch | Added `thread.is_alive()` guard and warning log so duplicate threads cannot spawn while an old tick is still running. |
| 7 | `run_retrain()` exception skipped `_save_drift_status()` and `_scheduler_loop` dropped tracebacks (plus `inf` / corrupt JSON / private helper imports / multi-worker notes) | medium | patch | Moved `_save_drift_status()` into `finally:` around `run_retrain()`, switched `_scheduler_loop` to `logger.exception()`, and kept `allow_nan=False` fail-loud and `load_drift_status` parity with `load_retrain_history`; rejected private-import rename and single-process lock note as low/consistent with Story 4.8. |
| 8 | `conftest.py` did not isolate `ECOTRACK_DRIFT_RECENT_PATH` / interval / delay env vars or call `stop_scheduler()` in teardown | medium | patch | Added save/clear/restore for all 3 env vars and `stop_scheduler(timeout=2.0)` in teardown. |
| 9 | `test_run_drift_check_resolves_default_and_env_recent_paths` silently triggered 350-tree training due to tail drift and lacked outcome assertions | high | patch | Resolved via #3 (`drift_detected is False` on baseline) plus explicit assertions on default status, env override outcome, and history count. |
| 10 | Missing test coverage for `rejected`/`failed` outcomes, scoped MLflow path, `air_temperature`-only drift, empty history on lock conflict, config parsing, cancel/restart/timeout | medium | patch | Added dedicated tests for all listed branches in `test_mlops_scheduler.py`. |
| 11 | New Story 4.9 env vars undocumented in `ai-service/.env.example` | low | patch | Added commented defaults under `# Automated MLOps drift-check scheduler (Story 4.9)` in `ai-service/.env.example`. |
