---
title: 'Story 4.1: Benchmark harness with naive and XGBoost baselines'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '1d3807c10d6d4020ba3f9f63e0baecab63f20308'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 4-1-benchmark-harness-with-naive-and-xgboost-baselines
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** EcoTrack serves an XGBoost forecaster (`src/models/train_models.py`) but has never scored it against a baseline on held-out data, so there is no evidence it beats a trivial model, and no reproducible, equal-terms comparison that later forecasters (SARIMAX in 4.2, LSTM in 4.3) can join. FR20/FR21 require one command that evaluates models on the same chronological split `train_models.py` uses and writes a results file with accuracy, speed and size.

**Approach:** Add a plain-Python benchmark package `ai-service/experiments/benchmark/` runnable as `python -m experiments.benchmark.run_benchmark`. It reuses `train_models.py`'s dataset loading, feature engineering and 80/20 chronological split (so the comparison matches the served model exactly), runs every model registered through a tiny `fit`/`predict` interface — Seasonal-naive (the value 24 h earlier) and XGBoost for this story — and writes one `results.csv` row per model with MAE, RMSE, MAPE, R², training time, mean inference latency (ms) and model file size. Adding a model is implement-the-interface-and-register, with no edit to the scoring code.

## Boundaries & Constraints

**Always:**
- `python -m experiments.benchmark.run_benchmark` (run from the `ai-service/` root) loads `data/processed/office_building_clean.csv`, applies `train_models.engineer_features`, splits with `train_models.split_time_series_data` (80/20, chronological, no shuffle), and scores every registered model on that one test partition.
- Seasonal-naive predicts the meter reading from 24 hours earlier (the engineered `lag_24h` column); XGBoost uses `train_models.XGB_FEATURE_COLUMNS` and the same hyperparameters/seed (`random_state=42`) as `train_models.train_xgboost_forecaster`.
- Accuracy metrics (MAE, RMSE, MAPE %, R²) are computed with the same scikit-learn functions as `train_models.py`, against `test_df["meter_reading"]`.
- `results.csv` has exactly one row per registered model and these columns: `model`, `mae_kwh`, `rmse_kwh`, `mape_percent`, `r2`, `training_time_s`, `mean_inference_latency_ms`, `model_file_size_bytes`. No `NaN`/empty cells for the scored models.
- Accuracy metrics are deterministic: two runs on the same data produce bit-identical `mae_kwh`/`rmse_kwh`/`mape_percent`/`r2` per model (seeds fixed; no nondeterministic parallelism that perturbs the fit). Timing columns may differ run to run.
- A new forecaster is added by subclassing the interface and registering it; `run_benchmark` and the scoring loop iterate the registry unchanged and emit the new row.
- Plain Python, importable and runnable without starting FastAPI or any network/DB (AD-1).

**Never:**
- Do not modify `src/models/train_models.py`, and never overwrite or read-then-resave the production artifacts in `models_saved/` — the harness trains its own in-memory models for comparison only.
- Do not re-implement the split or feature engineering; import them from `train_models.py` so the test partition is identical (drift here invalidates the comparison).
- Do not add SARIMAX or LSTM here (Stories 4.2/4.3) — only naive + XGBoost — but the interface and registry must accommodate them without scoring-code changes.
- Do not invent metric columns beyond those listed, and do not call any external/network source; inputs are files only.
- Do not generate charts or a report here (Story 4.4 reads `results.csv`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | Processed CSV present | `results.csv` written with 2 rows (`seasonal_naive`, `xgboost`), all 8 columns finite; XGBoost `mae_kwh` < Seasonal-naive `mae_kwh` | N/A |
| Seasonal-naive values | Engineered test partition | Predictions equal `test_df["lag_24h"]`; no `NaN` (feature engineering already drops lag-NaN rows) | N/A |
| Pluggability | A third model registered in a test | It appears as a third `results.csv` row with no edit to the scoring loop | N/A |
| Determinism | Benchmark run twice | Per model, the four accuracy columns are identical across runs | N/A |
| Mean latency | Any model | `mean_inference_latency_ms` = total `predict()` wall time over the test set ÷ test-row count, in ms (documented) | N/A |
| Model file size | Naive (no heavy artifact) | `model_file_size_bytes` = size of the fitted model serialized with `joblib` to a temp file; small but > 0 for naive | N/A |
| Dataset missing | Processed CSV absent | Exits non-zero with a message naming the missing path; no partial `results.csv` is written | `FileNotFoundError` surfaced, not swallowed |

</frozen-after-approval>

## Code Map

- `ai-service/src/models/train_models.py` — reuse (import, do not edit): `load_dataset`, `engineer_features`, `split_time_series_data`, `XGB_FEATURE_COLUMNS`, and mirror the XGBoost hyperparameters from `train_xgboost_forecaster` (lines 166-175).
- `ai-service/data/processed/office_building_clean.csv` — the dataset (17,544 hourly rows; `timestamp, meter_reading, air_temperature`). Default input.
- `ai-service/experiments/benchmark/__init__.py` *(new)* — package marker (the `experiments/` dir exists; only `logs/` is under it today).
- `ai-service/experiments/benchmark/models.py` *(new)* — `BaseForecaster` (`name`, `fit(train_df)`, `predict(test_df) -> np.ndarray`), a module-level registry + `register` decorator, `SeasonalNaiveForecaster` (fit no-op; predict returns `lag_24h`), `XGBoostForecaster` (wraps `xgb.XGBRegressor` with the train_models params).
- `ai-service/experiments/benchmark/benchmark.py` *(new)* — pure scoring: given train/test frames, iterate the registry, time `fit`/`predict`, compute MAE/RMSE/MAPE/R², measure serialized size, return a rows list / DataFrame. No CLI, no FastAPI (AD-1, unit-testable).
- `ai-service/experiments/benchmark/run_benchmark.py` *(new)* — `__main__` CLI: `--data-path`, `--output` (default `experiments/benchmark/results.csv`); loads → engineers → splits → `benchmark.score_all()` → writes `results.csv`; prints a summary table.
- `ai-service/tests/test_benchmark.py` *(new)* — pytest covering the matrix (uses `tests/fixtures/office_building_sample.csv` or a synthetic frame with ≥ 48 h).

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/experiments/benchmark/models.py` — interface + registry + `SeasonalNaiveForecaster` + `XGBoostForecaster` — FR20.
- [x] `ai-service/experiments/benchmark/benchmark.py` — registry-driven scoring (metrics, timing, latency, serialized size) returning rows — FR20, FR21.
- [x] `ai-service/experiments/benchmark/run_benchmark.py` + `__init__.py` — `__main__` entry that reuses `train_models` load/split and writes `results.csv` — FR20, FR21.
- [x] `ai-service/tests/test_benchmark.py` — unit-test the I/O matrix: happy-path schema, naive = `lag_24h`, pluggability, determinism of accuracy metrics, missing-dataset failure.

**Acceptance Criteria:**
- Given the processed BDG2 dataset, when I run `python -m experiments.benchmark.run_benchmark`, then Seasonal-naive and XGBoost are scored on the same chronological 80/20 split `train_models.py` uses and `results.csv` holds one row per model with MAE, RMSE, MAPE, R², training time, mean inference latency (ms) and model file size.
- Given the harness, when a new model is added, then it only implements the `fit`/`predict` interface and registers itself, with no change to the scoring code.
- Given the fixed random seed, when the benchmark runs twice, then the accuracy metrics are identical.

## Implementation Notes

- Added `ai-service/experiments/benchmark/models.py` defining `BaseForecaster`, `register_forecaster`, `get_registered_forecasters`, `SeasonalNaiveForecaster` (predicting `lag_24h`), and `XGBoostForecaster` (wrapping `XGBRegressor` with `n_estimators=350, max_depth=4, learning_rate=0.05, subsample=0.85, colsample_bytree=0.85, objective='reg:squarederror', random_state=42`).
- Added `ai-service/experiments/benchmark/benchmark.py` with `score_model()` and `run_scoring()`, evaluating MAE, RMSE, MAPE %, R2, training duration (s), mean inference latency (ms/sample), and serialized artifact file size (bytes).
- Added `ai-service/experiments/benchmark/run_benchmark.py` with CLI flags `--data-path` and `--output` (defaulting to `experiments/benchmark/results.csv`), reusing `load_dataset`, `engineer_features`, and `split_time_series_data` from `src.models.train_models`.
- Added unit tests in `ai-service/tests/test_benchmark.py` testing happy-path schema, seasonal-naive values, registry pluggability, determinism across repeat runs, latency/size metrics, and missing dataset exceptions.
- Updated root `.gitignore` to track `ai-service/experiments/benchmark/` while ignoring `experiments/logs/`.

## Spec Change Log

## Review Triage Log

- `models.py` / `benchmark.py` / `run_benchmark.py`: All 7 matrix rows verified and tested by `test_benchmark.py`. Zero defects found across blind-hunter, edge-case-hunter, and verification-gap lenses. Verdict: PASS (no deferred items).
- Post-review patch pass (2026-10-10): both review patches applied — added `test_execute_benchmark_writes_results_csv` (guards the AC1 one-command `results.csv` deliverable) and made `score_model` re-raise a `joblib.dump` failure instead of silently emitting `model_file_size_bytes = 0`. Re-verified: `pytest tests/test_benchmark.py` → 7 passed; CLI `python -m experiments.benchmark.run_benchmark` → exit 0, `results.csv` written, XGBoost (MAE 39.63 / MAPE 8.04% / R² 0.9785) beats seasonal_naive (MAE 153.00 / MAPE 24.10% / R² 0.7110).
- One item deferred (pre-existing, environmental, out of Story 4.1 scope): `tests/test_smoke.py::test_api_forecast_predict_warm_p95` intermittently exceeds its 300 ms budget on this local machine (348–416 ms). `test_smoke.py` is not in the Story 4.1 diff and the flake reproduces standalone; recorded in `deferred-work.md` rather than patching unrelated forecast code.

## Design Notes

- **Reuse the split, don't copy it:** importing `engineer_features`/`split_time_series_data`/`XGB_FEATURE_COLUMNS` from `train_models.py` is the only way to guarantee "the same split used by `train_models.py`" (AC1) survives future edits; re-deriving them would silently drift the comparison.
- **Registry is the pluggability contract (AC2):** scoring iterates a registry of `BaseForecaster` instances, so 4.2 (SARIMAX) and 4.3 (LSTM) add a subclass + `register` and nothing in `benchmark.py`/`run_benchmark.py` changes. Keep the interface minimal: `fit(train_df)`, `predict(test_df) -> np.ndarray`, `name`.
- **Determinism (AC3) is on accuracy only:** fix `random_state=42` and keep XGBoost's fit reproducible (default `tree_method`; avoid parallelism that reorders float sums if metrics drift in testing). Training time and latency are wall-clock and intentionally excluded from the determinism guarantee.
- **Uniform size/latency:** `model_file_size_bytes` = bytes of `joblib.dump` to a temp file (uniform across models, including naive); `mean_inference_latency_ms` = test-set `predict` wall time ÷ rows. Both are documented, comparable proxies rather than micro-benchmarks.
- **Naive from `lag_24h`:** feature engineering already shifts `meter_reading` by 24 and `dropna()`s, so the test partition's `lag_24h` is exactly "the value 24 hours earlier" with no NaN — the seasonal-naive prediction is that column, no extra computation.

## Verification

**Commands:**
- `cd ai-service && python -m experiments.benchmark.run_benchmark` — expected: writes `experiments/benchmark/results.csv` with ≥ 2 rows and all 8 columns finite; XGBoost beats Seasonal-naive on MAE/RMSE.
- `pytest ai-service/tests/test_benchmark.py -q` — expected: all pass (schema, naive=`lag_24h`, pluggability, accuracy determinism, missing-dataset failure).
- Determinism spot-check: run the command twice and diff the accuracy columns of `results.csv` — expected: identical.

## Code Review Findings — 2026-10-10 (4-layer adversarial: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor)

Diff reviewed: commit `a6f7baf` (baseline `1d3807c`). Ground-truthed by running `pytest tests/test_benchmark.py` (6 passed) and `python -m experiments.benchmark.run_benchmark` (exit 0; `results.csv` written; XGBoost MAE 39.63 / MAPE 8.04% / R² 0.9785 beats seasonal_naive).

**Patch (2):**
- [x] [Review][Patch] No automated test guards the `execute_benchmark` happy path. Every happy-path test calls `run_scoring` directly; only the missing-dataset branch touches `execute_benchmark`, so a regression to the `to_csv`/default-path/column logic (AC1's one-command `results.csv` deliverable that Story 4.4 consumes) would ship green. Add a pytest: `execute_benchmark(data_path=<fixture>, output_path=tmp_path/"results.csv")` → assert the file exists, `pd.read_csv` it, 2 rows, `list(df.columns) == BENCHMARK_COLUMNS`. [ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] `score_model` swallows a `joblib.dump` failure into `model_file_size_bytes = 0` silently (`except Exception: file_size_bytes = 0`), contradicting the I/O-matrix ">0 / no empty cells" guarantee and the project's fail-loudly ethos — a future unpicklable model would emit an invalid `0` into `results.csv` with no error. Re-raise (naming the model) instead of emitting `0`. [ai-service/experiments/benchmark/benchmark.py:85-86]

**Rejected (12):**
- (false) `R²` summary print raises `UnicodeEncodeError` on a Windows cp1252 console: verified empirically — the CLI ran to exit 0 and printed `R²` fine; U+00B2 is representable in cp1252/cp437.
- (false) broad `except Exception` in `main()` reports post-write success as failure: no reachable post-write exception (the hypothesized Unicode trigger is false); the CLI exits 0.
- (false) MAPE returns `inf` on zero readings, breaking the "finite" contract: scikit-learn clamps the zero denominator to epsilon (finite), `train_models.py` uses the identical MAPE, and real building readings are never 0 — empirically MAPE = 8.04/24.10, finite.
- (low) `run_scoring` raises `KeyError` on an empty model set: unreachable — the registry always holds `seasonal_naive`+`xgboost` and no caller passes `models=[]`.
- (low) `register_forecaster` silently overwrites on a duplicate `name`: requires a developer naming mistake; no collision in this story. Worth a duplicate-key guard when 4.2/4.3 add forecasters.
- (low) `score_model` metrics raise on an empty `test_df`: unreachable — the 80/20 split on the real/fixture data always yields a non-empty test partition.
- (low) determinism tested in-process, not across processes: the in-process twice-run test covers practical determinism; a subprocess harness is disproportionate for a theoretical thread-order risk.
- (reject — impl correct; fix edits spec) `n_jobs=-1` vs the Design-Notes determinism caution: the frozen "Always" clause requires the same hyperparameters as `train_models.py` (which sets `n_jobs=-1`); the impl correctly prioritized the frozen clause and `test_benchmark_determinism` passes.
- (low) undocumented `ECOTRACK_DATA_PATH` env override in `get_default_paths`: harmless (files-only; default unchanged) convenience input beyond the spec; no reachable harm.
- (reject — intentional) `.gitignore` narrowed `experiments/` → `experiments/logs/`: deliberate, to track the new benchmark code; the generated `results.csv` stays ignored via `*.csv` (confirmed by `git check-ignore`).
- (low) `get_registry()` is unused: a harmless public accessor; no defect.
- (low) `print_summary_table` has no test, and the Code Map names `score_all()` vs the impl's `run_scoring()`: display-only / non-frozen descriptive naming, no behavioral impact.
