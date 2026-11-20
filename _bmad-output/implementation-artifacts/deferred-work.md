# Deferred Work

## Deferred from: code review of story-4.5 (2026-10-31)

- **`n_jobs=-1` in the XGBoost search objective vs the determinism guarantee** (`ai-service/src/mlops/hpo.py:154`). `test_search_is_deterministic_under_fixed_seed` asserts exact-equal best params; multithreaded XGBoost *could* perturb fold RMSE and diverge the TPE sampler. Maybe-false — XGBoost `hist` is generally deterministic and the CI test is currently green. Settle by running that test repeatedly (or watching CI) before deciding to pin `n_jobs=1` (small speed cost on the already-fast XGBoost trials).
- **`XGBoostForecaster.DEFAULT_PARAMS` duplicates `train_models.py` hyperparameters** (`ai-service/experiments/benchmark/models.py:152`). The docstring claims the two are kept identical so the untuned benchmark row reproduces the served model, but nothing enforces it. A future tweak to `train_models.py`'s XGBoost config would silently make the "untuned" benchmark row stop matching the served model. Add an equality-guard test or single-source the values.

## Deferred from: bmad-review of story-4.6 (2026-11-03)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-detect-data-drift-and-accuracy-decay.md`
  summary: `drift.check()`'s reference window is reconstructed on every call from whatever currently sits at `office_building_clean.csv`, with nothing checking it still matches the data the deployed champion was actually trained on.
  evidence: Real — if the processed CSV is regenerated/appended between training and a drift check (no lock prevents this), the "reference" window silently stops representing the champion's actual training distribution and drift results become meaningless without any error. Fixing it properly means recording the training data's identity (row count + timestamp range, or a hash) in `model_metadata.json` at train time — i.e. touching Story 4.5's already-shipped, already-reviewed `train_models.py`, which is a larger change than this story's scope. (adversarial lens finding #3)
- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-detect-data-drift-and-accuracy-decay.md`
  summary: `_resolve_champion_for_drift()` re-resolves and reloads the champion model from MLflow/disk on every `check()` call, with no cache analogous to `serving_frame.py`'s module-level `_cached_xgb_model`.
  evidence: Real but harmless today — `drift.check()` is not wired into any endpoint or scheduler yet (explicitly out of scope; that's Stories 4.9/4.10). Once those stories call it on a recurring cadence, each tick will pay full model-load I/O with no caching. Add a version-keyed cache mirroring `serving_frame.py`'s when that wiring lands. (adversarial lens finding #6)
- source_spec: `_bmad-output/implementation-artifacts/spec-4-6-detect-data-drift-and-accuracy-decay.md`
  summary: The rolling-MAPE window (`_ROLLING_WINDOW_HOURS = 7*24`) is a row-count tail (`recent_df.tail(168)`), not a timestamp-based filter, so "rolling 7-day MAPE" silently becomes "MAPE over the last 168 rows" once gappy real sensor data is fed in.
  evidence: Real, but consistent with every other time-based assumption already in this codebase (`engineer_features`'s `lag_1h`/`lag_24h` shifts, `demo_scenarios.py`'s index arithmetic) — all assume a regular hourly grid with no gaps, a convention set at the loading boundary (`train_models.load_dataset` sorts but never fills gaps). Fixing only `drift.py` to filter by `timestamp >= max_timestamp - pd.Timedelta(hours=168)` would be inconsistent with that convention; revisit when Stories 4.9/4.10 feed real, potentially gappy production data. (adversarial lens finding #7)

## Deferred from: bmad-build blind-hunter review of story-4.7 (2026-11-04)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-7-measure-anomaly-detector-quality.md`
  summary: `generate_scenario_hvac_night_overrun`'s final fallback (`target_start_idx = 22` when no weekday-22:00 row is found anywhere in the dataset) injects two of its eight anomalous rows (indices 22-23) inside the first-24-row window `engineer_features()` drops for lag warm-up, silently undercounting `positive_count` by up to 2 when `evaluate()` scores that scenario.
  evidence: Real but pre-existing (the fallback itself predates this story; this story only added the label that now makes the undercount visible/measurable) and very low-probability to trigger — it requires no weekday-22:00 row anywhere in at least the first ~10 days of hourly data, which no real BDG2 building sample or the committed test fixture actually hits (both logged `target_start_idx` around index 166-200+ in this session's testing). Fixing it means nudging the pre-existing fallback constant in `demo_scenarios.py`, touching code outside this story's stated scope for a condition not observed to occur with any real data in this project.

## Deferred from: code review of spec-4-9-retrain-automatically-when-the-model-degrades (2026-11-17)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-9-retrain-automatically-when-the-model-degrades.md`
  summary: `ai-service/src/main.py` lines 10-15 import `src.config` and `src.data_pipeline.serving_frame` before `sys.path.insert` and `load_dotenv()` at lines 17-22.
  evidence: Pre-existing bootstrap ordering from Stories 4.1–4.7 outside Story 4.9 diff scope (`from src.mlops.scheduler import start_scheduler, stop_scheduler` at `main.py:25` is already after `load_dotenv()`, and Story 4.9 config helpers read `os.getenv()` lazily at runtime rather than import time). (blind-hunter finding #6, pre-existing)

## Deferred from: bmad-build blind-hunter review of story-4.10 (2026-11-17)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-10-report-model-and-drift-status.md`
  summary: `register_and_bootstrap_champion` constructs `MlflowClient()` without passing `tracking_uri` (`ai-service/src/mlops/tracking.py:124`) and `champion_health` maps unexpected exceptions to `"unavailable"` instead of `"broken"` (`ai-service/src/mlops/tracking.py:394-395`).
  evidence: Pre-existing Story 4.5 code carried from the dirty worktree prior to Story 4.10; `register_and_bootstrap_champion` callers invoke `configure(tracking_uri)` beforehand, and `champion_health` keeps Story 4.5 `/health` behavior unchanged. (blind-hunter finding #10)

## Deferred from: code review of spec-4-10-report-model-and-drift-status (2026-11-17)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-10-report-model-and-drift-status.md`
  summary: `tests/test_smoke.py::test_api_forecast_predict_warm_p95` exceeded the 300 ms p95 budget (`319.5 ms` in full run, `399.7 ms` standalone on Windows).
  evidence: Pre-existing Story 1.4/1.5 `/internal/forecast/predict` latency test not modified by Story 4.10 (`acceptance-auditor` note).
- source_spec: `_bmad-output/implementation-artifacts/spec-4-10-report-model-and-drift-status.md`
  summary: `register_and_bootstrap_champion` omits `tracking_uri` on `MlflowClient()` (`ai-service/src/mlops/tracking.py:126`) and `champion_health` maps unexpected exceptions to `"unavailable"` instead of `"broken"` (`ai-service/src/mlops/tracking.py:394-395`).
  evidence: Pre-existing Story 4.5 code carried from the dirty worktree prior to Story 4.10 (`blind-hunter` finding #6).
- source_spec: `_bmad-output/implementation-artifacts/spec-4-10-report-model-and-drift-status.md`
  summary: `anomaly_quality.merge_into_metadata()` writes `model_metadata.json` via a fixed `.json.tmp` sibling path without holding a shared metadata lock (`ai-service/src/mlops/anomaly_quality.py:126`).
  evidence: Pre-existing Story 4.7 code outside Story 4.10 diff (`blind-hunter` finding #8).

## Deferred from: bmad-build review of story-4.12 (2026-11-21)

- source_spec: `_bmad-output/implementation-artifacts/spec-4-12-monitor-the-model-as-an-admin.md`
  summary: The dashboard building id `office_tower_01` and the MLOps viewer rule are duplicated in `backend/src/routes/mlops.js` and `frontend/src/hooks/useMLOpsStatus.js`, and no test links the two.
  evidence: Real but small. Changing one side only gives a dead tab (UI shows it, API returns 403) or a hidden feature, while every test still passes. Fix with one shared constant or a `/auth/me` capability flag when the dashboard gets a building picker.
