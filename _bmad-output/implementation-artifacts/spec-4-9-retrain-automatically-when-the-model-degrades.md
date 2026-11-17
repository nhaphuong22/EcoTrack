---
title: 'Story 4.9: Retrain automatically when the model degrades'
type: 'feature'
created: '2026-11-17'
status: 'done'
baseline_commit: 'ec4a4879656272b1644fc4de9f3a76818180ae1d'
route: 'oneshot'
review_loop_iteration: 1
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

### Review Findings

1. - [x] [Review][Decision->Rejected] Default `recent_df` window (`_load_base_feat().copy()`) [ai-service/src/mlops/scheduler.py:105-109] — Đã chốt phương án 1: giữ nguyên hành vi baseline theo AC `epics.md:1036`, không sửa code sang `.tail(168)` (chi tiết tại R6).

2. - [x] [Review][Patch] Scoped champion resolution fallback leaks global champion into `rolling_mape` and is masked by `MLFLOW_TRACKING_URI=uri` in tests [ai-service/src/mlops/scheduler.py:116-156, ai-service/src/mlops/drift.py:193-194, ai-service/tests/test_mlops_scheduler.py:260] (findings F02, F04, F14, F24, F27).
3. - [x] [Review][Patch] Contradictory `retrain_trigger` persisted alongside `retrain_triggered: False` on `RetrainAlreadyRunningError` / retrain exception, plus missing `retrain_trigger is None` test assertion [ai-service/src/mlops/scheduler.py:167-197, ai-service/tests/test_mlops_scheduler.py:315-320] (findings F05, F20).
4. - [x] [Review][Patch] Non-positive scheduler interval (`<= 0`) silently clamped to `0.05s` (20 Hz spin loop), `bool` accepted by `start_scheduler()`, and missing boundary/env tests (`<= 0`, min clamp, `get_drift_recent_path()`, invalid `start_scheduler()` args) [ai-service/src/mlops/config.py, ai-service/src/mlops/scheduler.py:243-254, ai-service/tests/test_mlops_scheduler.py:323-341] (findings F08, F26).
5. - [x] [Review][Patch] Zero-argument production call path (`run_drift_check_and_retrain()` / `load_drift_status()` with `models_dir=None`) and unmocked FastAPI `lifespan` scheduler execution never tested [ai-service/tests/test_mlops_scheduler.py:366] (findings F25, F12-part).
6. - [x] [Review][Patch] Scheduler test hygiene and `load_drift_status()` edge-case tests (`None` on missing file, `ValueError` on non-dict, `JSONDecodeError` on malformed JSON, dead `perfect_stub`, stale `"Missing data_path"` comment, `other_dir` & failed-history assertions) [ai-service/tests/test_mlops_scheduler.py:176,279-296] (findings F12-part, F10-part).
7. - [x] [Review][Patch] Stdlib `threading` guards for `stop_event.wait` above `threading.TIMEOUT_MAX` (`4294967.0`), `stop_scheduler()` self-join `RuntimeError`, and invalid `timeout` (`NaN`/`Inf`/negative/`bool`/`> TIMEOUT_MAX`) [ai-service/src/mlops/scheduler.py:208,215,279-295] (findings F15, F16, F17).
8. - [x] [Review][Patch] Assign `_stop_event` and `_scheduler_thread` after `thread.start()` succeeds so `thread.start()` `RuntimeError` cannot leave stale globals [ai-service/src/mlops/scheduler.py:268-270] (findings F11-part, F23).
9. - [x] [Review][Patch] Blank/whitespace string path (`""`) passed to `data_path`/`recent_path`/`models_dir` resolves to `Path(".")` instead of `None`/default [ai-service/src/mlops/scheduler.py:52,92,102,151] (findings F07-part, F19).
10. - [x] [Review][Patch] Log explicit warning when `ECOTRACK_DRIFT_RECENT_PATH` / `recent_path` has `< 25` rows so `engineer_features()` `lag_24h` drop yielding `rolling_mape: None` is not silent [ai-service/src/mlops/scheduler.py:103-104] (findings F07-part, F18).
11. - [x] [Review][Patch] Set `ECOTRACK_SCHEDULER_INTERVAL_SECONDS`, `ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS`, and `ECOTRACK_DRIFT_RECENT_PATH` to `""` (instead of `pop`) in `conftest.py` so `load_dotenv(..., override=False)` cannot reload `.env` values during tests [ai-service/tests/conftest.py] (finding F09-part).

12. - [x] [Review][Defer] Pre-existing `src/main.py` import order loads `src.config` and `serving_frame` before `sys.path.insert` and `load_dotenv()` [ai-service/src/main.py:10-22] — deferred: pre-existing Story 4.1–4.7 bootstrap ordering outside Story 4.9 scope; Story 4.9 imports `src.mlops.scheduler` at line 25 after `load_dotenv()` and reads env vars lazily at runtime (finding F09-part).

#### Rejected

- **R1 (`spec-4-9` frontmatter `status: 'done'` vs `sprint-status.yaml` `review` — findings F03, F13):** Rejected under triage rule (do not accept findings whose only fix is editing the spec under review; Step 4 also updates spec/sprint tracking cleanly at review end).
- **R2 (`load_drift_status()` raising `JSONDecodeError`/`UnicodeDecodeError` on corrupt JSON — finding F21):** Rejected (`false`): intentional fail-loud behavior matching `retrain.load_retrain_history()` so disk corruption is surfaced instead of silently masquerading as `None`.
- **R3 (`_save_drift_status()` `allow_nan=False` raising `ValueError` on `NaN`/`Inf` from `DRIFT_*` env vars — finding F22):** Rejected (`false`): `allow_nan=False` intentionally prevents writing invalid RFC-8259 JSON, and module-level `DRIFT_*` env parsing in `config.py` is pre-existing Story 4.6 code.
- **R4 (`_resolve_windows()` and `drift.check()` outside `try...finally` in `run_drift_check_and_retrain()` — finding F10-part):** Rejected (`false`): without `drift_result`, a schema-valid `drift_status.json` (`**drift_result`) cannot be written, and inventing an undocumented error-only schema or swallowing missing-CSV errors violates fail-loud / Story 4.10 expectations (`_scheduler_loop` already logs tick errors).
- **R5 (`stop_scheduler(timeout=5.0)` daemon shutdown cap & unserialized concurrent `run_drift_check_and_retrain()` / `checked_at` placement — finding F11-part):** Rejected (`false` on 5s daemon join cap: intentional bounded graceful-shutdown trade-off tested in `test_mlops_scheduler.py` while `_atomic_write_bytes` protects persisted artifacts from torn writes; `low` rejected on adding a coarse blocking lock across `run_drift_check_and_retrain()` because concurrent manual+scheduler overlap is rare on a 24h schedule and blocking manual callers behind a ~60s retrain conflicts with non-blocking `_retrain_lock`).
- **R6 (D1 — Default `recent_df` window vs frozen Intent — findings F01, F06):** Rejected per owner decision (Option 1): keep `_load_base_feat().copy()` in `scheduler.py:109` per `epics.md` Story 4.9 AC (`lines 146, 1036`) to prevent false seasonal PSI drift (`4.855–8.622` / `7.682–8.337`) at static CSV startup; `<frozen-after-approval>` Intent untouched per review rule.
