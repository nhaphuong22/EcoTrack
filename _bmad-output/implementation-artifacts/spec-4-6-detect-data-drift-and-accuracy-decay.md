---
title: 'Story 4.6: Detect data drift and accuracy decay'
type: 'feature'
created: '2026-11-03'
status: 'done'
baseline_commit: '1d841c8d55f0b51dd4c3888c2628a9ee0ad661e1'
route: 'oneshot'
review_loop_iteration: 0
story_keys:
  - 4-6-detect-data-drift-and-accuracy-decay
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The champion forecaster (Story 4.5) is served with no check on whether the world it was trained on still matches the world it is scoring. FR24 asks for a drift check comparing a reference window against a recent window on `meter_reading` and `air_temperature` (KS test + PSI), plus the champion's rolling 7-day MAPE, with configurable thresholds, correctly distinguishing the unmodified dataset (no drift) from `scenario_hvac_overrun.csv` (drift).

**Approach:** Add `ai-service/src/mlops/drift.py`, a plain-Python module (AD-1, no FastAPI dependency) exposing `check(reference_df, recent_df, champion_model=None) -> dict`. No new persistence is introduced:
- **Reference window** = the training split, reconstructed deterministically by re-running `load_dataset` → `engineer_features` → `split_time_series_data(train_ratio=0.8)` (`train_models.py`) against the same source CSV used to train the champion, taking `train_df`. This is a fixed window — it does not change until a retrain re-splits the data — and needs no new field in `model_metadata.json` since the split is reproducible as-is.
- **Recent window** = any caller-supplied dataframe shaped like training data (`timestamp, meter_reading, air_temperature`, e.g. the full recent dataset or `scenario_hvac_overrun.csv`); `drift.py` runs `engineer_features` on it internally if lag/calendar columns are absent.
- **KS test + PSI**: `scipy.stats.ks_2samp` on `meter_reading` and `air_temperature` between reference and recent (dropping NaNs from both series first); PSI on the same two columns using a shared binning computed from the reference distribution, with a small epsilon (e.g. `1e-4`) added to zero-count bins before the `log` ratio to avoid div-by-zero/`log(0)`.
- **Rolling 7-day MAPE**: loads the champion via `mlops.tracking.load_champion_forecaster()`, runs `champion_model.predict()` on the last 7 days of the recent window's engineered features, and computes MAPE against the actual `meter_reading` already present in that same window — no prediction log or new persistence, because the champion is a feature-based regressor scored in-sample, not an autoregressive forecaster, so actuals and features coexist in `recent_df`. If the recent window has fewer than 7 days, MAPE is computed over whatever is available and the result notes the shorter window rather than erroring.
- **Thresholds**: configurable in `ai-service/src/mlops/config.py` following the existing `OPTUNA_*` env-var pattern — `DRIFT_KS_PVALUE_THRESHOLD` (default `0.05`), `DRIFT_PSI_THRESHOLD` (default `0.2`), `DRIFT_MAPE_THRESHOLD_PERCENT` (default `15.0`). `drift_detected: true` when (KS p-value < threshold **and** PSI > threshold) for either column, **or** rolling MAPE > its threshold; the result lists exactly which signal(s) tripped it.
- Add `scipy` to `ai-service/requirements.txt` (used directly by `drift.py`, currently only a transitive dependency).
- New `ai-service/tests/test_mlops_drift.py`, following the `tmp_path`/`monkeypatch` MLflow-store conventions already used in `test_mlops_tracking.py` / `test_serving_champion_load.py`: reference built from `tests/fixtures/office_building_sample.csv`, recent window first set to the same unmodified data (expect no drift) and then to `ai-service/data/processed/scenario_hvac_overrun.csv` (expect drift), plus one test each for the PSI zero-bin epsilon path and the short-recent-window MAPE path.
- Per the Epic 4 working agreement, no training/benchmark command is run by the agent; this story adds no such command (drift checking is pure computation over already-existing fixtures/artifacts).

## Implementation Notes

- `ai-service/data/processed/scenario_hvac_overrun.csv` mentioned in the Intent is **not tracked in git** (confirmed via `git ls-files`) — only `ai-service/tests/fixtures/office_building_sample.csv` is. `test_mlops_drift.py` therefore calls `demo_scenarios.generate_scenario_hvac_night_overrun(base_df=...)` directly against the small fixture to produce the drifted scenario in-memory, instead of reading that file from disk. This keeps the test CI-safe (no gitignored BDG2-derived file dependency) and is behaviourally the same scenario the real file is exported from. Pure implementation detail; does not change `drift.py`'s public contract.
- The injected HVAC-overrun anomaly (8 hours at ~750 kWh vs a ~230 kWh baseline) is only ~0.4% of the full dataset, which standard KS/PSI on the whole column would not reliably flag — this is why the AC's third signal (rolling 7-day MAPE) is what actually detects it in the test: the recent window is trimmed to end right at the anomaly so it dominates the (shorter-than-7-day) tail the model is scored against. This matches real usage too: a drift check is normally run against a short recent window (days), not the whole history.
- Chose the reference window checked against **itself** as the deterministic "no drift" test case (rather than the training split vs. its own held-out test split) to avoid flakiness from any natural seasonal/temporal difference between those two slices of the fixture, which cannot be verified without running the test (Epic 4 working agreement: the agent prints commands, the owner runs them).
- Files touched: `ai-service/src/mlops/config.py` (3 new `DRIFT_*` env-var thresholds), `ai-service/src/mlops/drift.py` (new), `ai-service/requirements.txt` (added `scipy`), `ai-service/tests/test_mlops_drift.py` (new). No change to `train_models.py`, `serving_frame.py`, or any API route — `drift.check()` is not wired into any endpoint or scheduler yet (that is Stories 4.9/4.10).
- Post-review revision: champion resolution for the rolling-MAPE signal now reuses `serving_frame._load_champion_forecaster_or_fallback()` (MLflow champion, else `models_saved/`) instead of calling `tracking.load_champion_forecaster()` directly, so the common dev/CI case where only a local `models_saved/` artifact exists still gets the MAPE signal. Unlike the serving path, `drift.check()` never raises on a broken/missing/unavailable champion — a drift check is a monitoring tool, not the user-facing serving path, so any resolution failure just skips the MAPE signal (logged) rather than failing the whole check.

## Review Triage Log

One review layer ran (blind-hunter; the only layer configured in this render). Arithmetic: ~10.6 KB changed → N = min(floor(sqrt(10.6)+1), 10) = 4; 9 findings reported.

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `requirements.txt`'s `mlflow>=2.9.0` → `mlflow>=2.9.0,<3` is undocumented scope creep | false | reject | `git diff` shows the line changed, but this edit predates this story — it's part of Story 4.5's own review fix (already in the working tree before this story started); this story's only edit to that file is the inserted `scipy` line. |
| 2 | The KS+PSI per-column trigger path (half of FR24's detection mechanism) has no test that actually fires `True` | medium | patch | Correct: the HVAC-overrun test only trips `rolling_mape`. Added `test_shifted_column_triggers_ks_and_psi_signal` (synthetic shifted distribution) to exercise the branch directly. |
| 3 | No test for `ChampionArtifactError` propagating out of `check()` | medium | patch (superseded) | The underlying design was wrong, not just untested: a monitoring check should not fail-loud like the serving path. Changed `check()` to resolve the champion via `_resolve_champion_for_drift()`, which never raises — this also resolves #8, so the propagation this finding asked to test no longer exists. |
| 4 | `_ks_and_psi`/`ks_2samp` crashes on an empty/all-NaN column instead of degrading gracefully like `_psi` does | medium | patch | Real gap (sensor-outage columns are explicitly anticipated elsewhere in this project, e.g. PRD FR-2). Added an empty-check returning a neutral result, plus `test_ks_and_psi_handles_empty_column_without_crashing`. |
| 5 | `logger` is defined but never called | low | patch | Cheap, matches the logging-heavy style of `tracking.py`/`serving_frame.py` this module otherwise mirrors. Added a warning log on `drift_detected` and inside `_resolve_champion_for_drift`'s fallback. |
| 6 | `DRIFT_COLUMNS` is hardcoded while the thresholds are env-configurable — "inconsistent configurability" | false | reject | FR24 names `meter_reading`/`air_temperature` explicitly as the columns to check; only the *thresholds* are specified as "set in configuration" in the acceptance criteria. Making the column set env-configurable would be scope beyond FR24, not a fix. |
| 7 | `_rolling_mape`'s MAPE has no guard against near-zero `meter_reading` denominators | low | reject | Matches the exact same unguarded `mean_absolute_percentage_error` call already shipped in `train_models.py` (Story 4.5, reviewed and done) for the same column; FR24 specifies MAPE as the metric. Deviating here would be inconsistent with the rest of the codebase for a case not shown to be reachable with real building data (never literally 0 kWh). |
| 8 | Champion-unavailable path gives up on the MAPE signal instead of falling back to `models_saved/` like `serving_frame.py` does | medium | patch | Correct and the most important finding: in CI/dev without an MLflow store, this silently lost 1 of 3 drift signals. Fixed by reusing `serving_frame._load_champion_forecaster_or_fallback()`; see Implementation Notes. |
| 9 | `_rolling_mape` trusts `recent_df` to already be time-sorted/contiguous (`.tail()` by row count) | low | reject | Consistent with the rest of the pipeline: `engineer_features`/`split_time_series_data` make the same assumption, and sorting is established as the loading boundary's job (`train_models.load_dataset`, `demo_scenarios.load_base_dataset`) everywhere else in this codebase. Adding a sort-guard here only would be inconsistent, not a fix. |

</frozen-after-approval>
