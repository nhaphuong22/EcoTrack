---
title: 'Story 4.7: Measure anomaly detector quality'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: 'f5fc57bfc7017612f09822a4564e4f8d42406f5e'
route: 'oneshot'
review_loop_iteration: 0
story_keys:
  - 4-7-measure-anomaly-detector-quality
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Isolation Forest anomaly detector has never been scored against known ground truth — `train_models.py` reports score ranges and a raw anomaly percentage, but no precision, recall, F1 or false-positive rate exists anywhere, so nobody can state how reliable its alerts actually are (FR27).

**Approach:** No `is_injected_anomaly` label exists anywhere today (confirmed absent from the dataset, the test fixture, and the demo scenario CSVs — an old loader that referenced it was deleted). Product owner decision: extend `demo_scenarios.py`'s two generators to also emit a boolean `is_injected_anomaly` column marking exactly the rows each one modifies (`generate_scenario_hvac_night_overrun`'s 8-hour `overrun_indices`, `generate_scenario_peak_hour_spike`'s up-to-4 `spike_indices`), as a trailing 4th column after the existing `timestamp, meter_reading, air_temperature` — nothing else in the repo reads these two CSVs, so this is additive and safe.
- New `ai-service/src/mlops/anomaly_quality.py` (plain-Python, AD-1): `evaluate(labeled_df, iso_model) -> {precision, recall, f1, false_positive_rate}`. Runs `engineer_features` on `labeled_df` when needed (reusing the exact pattern `drift.py` already established for scoring a raw demo-scenario frame), scores it with `ISO_FEATURE_COLUMNS` through the given Isolation Forest, and compares `is_anomaly` (`predict() == -1`) against the `is_injected_anomaly` ground truth via `sklearn.metrics.precision_score`/`recall_score`/`f1_score` (already a dependency) plus a hand-computed false-positive rate.
- Evaluation targets are the two demo scenarios only (`scenario_hvac_overrun.csv`, `scenario_peak_spike.csv`) — the unmodified dataset has zero positive-class rows by construction, so precision/recall are undefined there; "data with `is_injected_anomaly` labels" in the AC refers to the scenario datasets themselves, which are the only ones that carry the label.
- Uses the existing served `models_saved/isolation_forest.joblib` artifact as-is — no retraining, matching how the detector is served today and the Epic 4 convention against training inside this kind of story.
- Logs its own standalone MLflow run (`mlflow.start_run(run_name="evaluate_isolation_forest")` after reusing `tracking.configure()`, same experiment via `config.get_experiment_name()`) — **not** `tracking.track_training_run`/champion registration, which Story 4.5 scoped to the forecaster only.
- Merges results into `model_metadata.json` under a new `isolation_forest_quality` key (one entry per evaluated dataset), read-modify-write so every existing key survives untouched — never a wholesale overwrite.
- A thin CLI, `ai-service/src/mlops/run_anomaly_eval.py` (mirrors `run_hpo.py`'s module/CLI split), runs the real end-to-end evaluation against the full production CSVs and the real served artifact, then performs the MLflow log and the `model_metadata.json` merge. Printed as a command for the owner to run, not executed by the agent — it isn't a training command, but it does mutate a git-tracked production artifact file, so it gets the same hands-off treatment as this epic's training commands rather than risk corrupting that file from an environment that may not even have the full BDG2 CSVs locally.
- Tests build their labeled frame in-memory from the small committed fixture (`tests/fixtures/office_building_sample.csv`) plus `demo_scenarios.generate_scenario_*(base_df=...)`, exactly like `test_mlops_drift.py` already does, fitting a tiny Isolation Forest on the fixture rather than touching the real joblib artifact or the real `model_metadata.json` — fully offline and CI-safe.
- Precision/recall/F1 on only 4–8 positive rows per scenario will be statistically noisy; that is inherent to the demo-scenario ground truth this story is scoped to use, not a defect to fix here.

## Review Triage Log

Blind-hunter (only layer configured in this render) against the diff. Arithmetic: ~18.9 KB changed → N = min(floor(sqrt(18.9)+1), 10) = 5; 9 findings reported.

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `test_demo_scenarios.py:50` asserts exactly 3 scenario columns — broken by the new `is_injected_anomaly` column | high | patch | Confirmed real regression this diff caused. Fixed the assertion to expect 4 columns; confirmed no other consumer reads these CSVs positionally. |
| 2 | `generate_scenario_hvac_night_overrun`'s degenerate fallback (`target_start_idx=22`) can inject 2 of 8 anomalous rows inside the dropped first-24-row warm-up window, undercounting `positive_count` | medium | defer | Real but pre-existing (fallback predates this story) and not observed to trigger with any real data here (both the fixture and the full dataset resolve `target_start_idx` well past 24). Logged in `deferred-work.md`. |
| 3 | No test for the new CLI (`run_anomaly_eval.py`) — argument parsing, missing-artifact path, end-to-end flow | medium | patch | Correct gap. Added `test_run_anomaly_eval_cli_end_to_end`, fully offline via a monkeypatched `load_base_dataset`. |
| 4 | No test for the fallback branches: the index-22 fallback (see #2) or `_ensure_engineered`'s already-engineered short-circuit | medium (split) | patch (short-circuit only) / defer (index-22, see #2) | Added `test_ensure_engineered_skips_when_markers_already_present`. The index-22 fallback test would only exercise an already-deferred, unreachable-in-practice path — not worth a dedicated test now. |
| 5 | `evaluate()` raises an opaque `KeyError` if `is_injected_anomaly` is missing, instead of a clear message | medium | patch | Correct and cheap. Added an explicit check raising `ValueError` naming the missing column; covered by `test_evaluate_raises_clear_error_when_label_column_missing`. |
| 6 | `merge_into_metadata()` does a non-atomic read-modify-write with no handling for a missing/malformed file, risky for a git-tracked production artifact | medium | patch | Correct and proportionate to fix given what the file is. Added an explicit `FileNotFoundError` and a tmp-file + `os.replace()` atomic swap; covered by `test_merge_into_metadata_raises_clear_error_when_file_missing`. |
| 7 | `run_anomaly_eval.py` hardcodes the two scenario generators instead of discovering them dynamically | low | reject | The epics.md AC itself names exactly "the two demo scenarios" — they are not meant to grow. A discovery/registry mechanism for 2 fixed, explicitly-scoped functions is premature abstraction, not a fix. |
| 8 | `log_to_mlflow`'s run carries no tag identifying which model artifact/version was evaluated, breaking traceability across repeated runs | medium | patch | Correct and valuable given the story's own stated purpose (know how reliable the detector's alerts are, over time). Added an optional `model_path` parameter tagged on the run; also found and fixed that `log_to_mlflow` didn't honour `ECOTRACK_DISABLE_MLFLOW` unlike the rest of `tracking.py`/`config.py` while verifying this fix. |
| 9 | `precision`/`recall`/`f1` left as raw floats while `false_positive_rate` alone was rounded to 4 decimals | low | patch | Trivial, cheap consistency fix applied directly. |

## Implementation Notes

- `demo_scenarios.py`'s two generators now set `is_injected_anomaly=False` on the whole frame and flip it `True` only for the rows each one actually overwrites, returning it as a trailing 4th column. Confirmed both injection loops start scanning at index 24 or later, so none of the label=True rows ever fall inside the first 24 rows `engineer_features()` drops for lag warm-up — the label survives engineering with its count unchanged.
- `anomaly_quality._ensure_engineered` mirrors `drift.py`'s identical helper (same 4 marker columns) rather than importing it cross-module, to keep `drift.py` and `anomaly_quality.py` independently readable/changeable — a deliberate small duplication, not an oversight.
- `evaluate()` relies on `sklearn.metrics.*_score(..., zero_division=0)` so a detector that predicts no anomalies at all (or a scenario with too few positives) reports `0.0` instead of raising/warning.
- `log_to_mlflow()` deliberately does not reuse `tracking.track_training_run`: that function hardcodes `mlflow.xgboost.log_model` + champion-alias registration, both forecaster-specific per Story 4.5's note that detector tracking was left open for this story. It only reuses the generic `tracking.configure()` and logs to the same `ecotrack-forecasting` experiment.
- Files touched: `ai-service/src/data_pipeline/demo_scenarios.py` (label column in both generators), `ai-service/src/mlops/anomaly_quality.py` (new), `ai-service/src/mlops/run_anomaly_eval.py` (new CLI), `ai-service/tests/test_mlops_anomaly_quality.py` (new). No change to `train_models.py`, `anomaly_service.py` (serving-side, confirmed unrelated), or `requirements.txt` (`sklearn.metrics` is already available). `run_anomaly_eval.py` is not run by the agent — printed as a command for the owner, per the Epic 4 convention, since it mutates the git-tracked `model_metadata.json` with results computed against the full production CSVs this environment may not even have locally.
- Blind-hunter review (2026-11-04) also caught a real regression: `ai-service/tests/test_demo_scenarios.py:50` asserted the scenario CSVs have exactly 3 columns, which the new `is_injected_anomaly` column broke. Fixed the assertion to expect the 4th column; confirmed (via the same review's own repo-wide search, reused from Story 4.6's investigation pattern) that nothing else reads these two CSVs positionally.
- Post-review revisions: `evaluate()` now raises a clear `ValueError` naming the missing column instead of an opaque `KeyError` when `is_injected_anomaly` is absent; `merge_into_metadata()` raises `FileNotFoundError` with the path when the target doesn't exist, and writes via a sibling `.tmp` file + `os.replace()` for an atomic swap (never leaves the tracked `model_metadata.json` half-written on a crash); `log_to_mlflow()` now also honours `ECOTRACK_DISABLE_MLFLOW` (it only checked `mlflow_available()` before, unlike `tracking.py`'s other functions) and accepts an optional `model_path` tagged on the run so repeated evaluations can be traced back to the exact artifact scored; `precision`/`recall`/`f1` are now rounded to 4 decimals, matching `false_positive_rate` (previously only that one was rounded).
- Added `test_run_anomaly_eval_cli_end_to_end` (CLI wiring: load artifact + scenarios → evaluate → merge metadata, fully offline via a monkeypatched `load_base_dataset` returning the small fixture) and a direct test for `_ensure_engineered`'s already-engineered short-circuit, closing two coverage gaps the review found.
- Owner ran `pytest tests/test_mlops_anomaly_quality.py tests/test_demo_scenarios.py -q`: 14/14 passed on the first try. One `SADeprecationWarning` from MLflow's own SQLAlchemy store internals (`noload` loader strategy), unrelated to this story's code.

</frozen-after-approval>
