---
title: 'Story 4.2: Add a statistical baseline (SARIMAX)'
type: 'feature'
created: '2026-10-10'
status: 'done'
baseline_commit: '1e55d5b3dcd44e01658a8fb54ac64b253febf276'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 4-2-add-a-statistical-baseline-sarimax
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Story 4.1 benchmark harness compares only a seasonal-naive baseline and the tree-based XGBoost model. FR20 requires the benchmark to cover statistical, tree-based and neural approaches on equal terms, so a classical statistical forecaster is missing. SARIMAX is also slow to fit on the full ~14k-row training split, so it cannot simply reuse the whole partition the way XGBoost does.

**Approach:** Add a `SARIMAXForecaster` that plugs into the existing registry (`@register_forecaster`, `fit`/`predict`/`name` — no change to the scoring loop's contract) and is scored as a third row in `results.csv`. It fits a statsmodels `SARIMAX` with daily seasonality (period 24) and `air_temperature` as the exogenous regressor, trained on a **documented recent window** (the last N hours of the training split) to stay tractable. Because the window differs per model, the harness records the training window length in a new `train_window_hours` results column — full-data models report their full train-row count, SARIMAX reports its truncated window.

## Boundaries & Constraints

**Always:**
- `SARIMAXForecaster` (registry name `sarimax`) subclasses `BaseForecaster` and registers via `@register_forecaster`; `run_scoring`/`score_model` iterate it with no change to their control flow, so it appears as a third `results.csv` row alongside `seasonal_naive` and `xgboost`.
- It fits a statsmodels `SARIMAX` on the endogenous `meter_reading` with `air_temperature` as the exogenous variable and daily seasonality (seasonal period `s = 24`), using a documented model order held as a module constant.
- It trains on the **last N hours of the training split** (a documented module constant, not the full partition), and `predict(test_df)` rolls one step ahead through the test span with the fitted parameters held fixed — the forecast for hour t uses the observed `meter_reading` up to t−1 (the same information `XGBoostForecaster` receives through `lag_1h`) and the test-period `air_temperature` as exog — returning a 1-D float ndarray of length `len(test_df)`. (Renegotiated 2026-10-10 in code review; previously one open-loop forecast of `len(test_df)` steps.)
- The training window length is recorded per model in a new `train_window_hours` column appended to `BENCHMARK_COLUMNS`; `seasonal_naive` and `xgboost` report their full training-row count there (they are unchanged otherwise), `sarimax` reports its window N.
- Accuracy metrics stay deterministic across runs (statsmodels MLE is deterministic for fixed data and start params), honoring Story 4.1 AC3.
- Reuses the Story 4.1 dataset load / feature engineering / 80/20 split and the same metric functions; plain Python, no FastAPI/network (AD-1).

**Never:**
- Do not change `SeasonalNaiveForecaster`, `XGBoostForecaster`, the registry mechanics, `train_models.py`, or the served artifacts in `models_saved/`.
- Do not fit SARIMAX on the full training split (intractably slow) — only on the documented window.
- Do not add the LSTM forecaster (Story 4.3) or any report/charts (Story 4.4).
- Do not drop or reorder the existing 8 `BENCHMARK_COLUMNS`; only append `train_window_hours`.
- Do not invent future exog values — `predict` uses the actual `air_temperature` already present in `test_df`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| SARIMAX scored | Benchmark run on the dataset | `results.csv` has a third row `sarimax`, all 9 columns finite (no NaN/empty) | N/A |
| Window recorded | Any run | `sarimax` `train_window_hours` = N (the documented window) and N < the full-train count reported by `seasonal_naive`/`xgboost` | N/A |
| Prediction length | Any `test_df` | `predict(test_df)` returns a float ndarray of length `len(test_df)` | N/A |
| One step ahead | Reading at test position k changed | Predictions up to k are unchanged; the prediction at k+1 changes (no look-ahead, observed t−1 is used) | N/A |
| Exog alignment | Fit + forecast | `air_temperature` is passed as exog for both fit (window) and forecast (test span); lengths match their frames | N/A |
| Determinism | Benchmark run twice | `sarimax` accuracy columns (`mae_kwh`/`rmse_kwh`/`mape_percent`/`r2`) identical across runs | N/A |
| Convergence noise | statsmodels emits convergence warnings | Warnings are non-fatal; the fit still produces a scored row | Suppressed/ignored, not raised |

</frozen-after-approval>

## Code Map

- `ai-service/requirements.txt` — add `statsmodels>=0.14.2` (scipy is pulled transitively). Not yet installed in the dev env, so `pip install -r ai-service/requirements.txt` is a prerequisite.
- `ai-service/experiments/benchmark/models.py` — `BaseForecaster` (L16), `_FORECASTER_REGISTRY`/`register_forecaster` (L42-70), `SeasonalNaiveForecaster` (L73-89), `XGBoostForecaster` (L92-124). Append `SARIMAXForecaster(BaseForecaster)` (name `sarimax`) with `@register_forecaster`, plus module constants `SARIMAX_ORDER = (1, 1, 1)`, `SARIMAX_SEASONAL_ORDER = (1, 0, 1, 24)`, `SARIMAX_TRAIN_WINDOW_HOURS = 336`. `fit(train_df)`: `fit_df = train_df.iloc[-SARIMAX_TRAIN_WINDOW_HOURS:]`; wrap the fit in a scoped `warnings.catch_warnings()` that ignores only `ConvergenceWarning` and the start-parameter fallback notice, and log when `mle_retvals["converged"]` is false; build `SARIMAX(endog=fit_df["meter_reading"].to_numpy(float), exog=fit_df[["air_temperature"]].to_numpy(float), order=SARIMAX_ORDER, seasonal_order=SARIMAX_SEASONAL_ORDER)`; store `self._results` and `self.train_window_used = len(fit_df)`. `predict(test_df)`: `self._results.extend(endog=test_df["meter_reading"]..., exog=test_df[["air_temperature"]]...).fittedvalues` → `np.asarray(..., dtype=float)` (one-step-ahead, fixed parameters; changed in code review). Do NOT touch `SeasonalNaiveForecaster`/`XGBoostForecaster`.
- `ai-service/experiments/benchmark/benchmark.py` — append `"train_window_hours"` to `BENCHMARK_COLUMNS` (L19-28); in `score_model` add `"train_window_hours": int(getattr(model, "train_window_used", len(train_df)))` to the returned dict (L88-97) and fix its docstring "8 standard" → "9 standard". No control-flow change.
- `ai-service/experiments/benchmark/run_benchmark.py` — widen `print_summary_table` (L89-110) header/separators and add a `train_window_hours` column to the header and each row.
- `ai-service/tests/test_benchmark.py` — a 3rd registered model changes the registry size, so THREE existing tests that hard-code 2 models MUST be updated (not merely extended): `test_benchmark_happy_path_schema_and_comparison` (L44-70: `len==2`→`3`, `model_names` set gains `sarimax`), `test_execute_benchmark_writes_results_csv` (L73-94: same two), `test_benchmark_pluggability` (L130-153: `len==3`→`4` after registering `constant_mean`). Then add SARIMAX assertions (row present; `train_window_hours` == 336 and < full-train count; `predict` length; determinism). Column-equality assertions stay green because they import `BENCHMARK_COLUMNS`.
- `ai-service/src/models/train_models.py` — reuse (import only, do NOT edit) `load_dataset`/`engineer_features`/`split_time_series_data` and `XGB_FEATURE_COLUMNS`.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/requirements.txt` — add `statsmodels>=0.14.2` — FR20.
- [x] `ai-service/experiments/benchmark/models.py` — `SARIMAXForecaster` (order (1,1,1)×(1,0,1,24), `air_temperature` exog, 336-hour recent window, sets `train_window_used`), registered as `sarimax` — FR20.
- [x] `ai-service/experiments/benchmark/benchmark.py` — append `train_window_hours` to `BENCHMARK_COLUMNS` and populate it in `score_model` — FR20.
- [x] `ai-service/experiments/benchmark/run_benchmark.py` — show `train_window_hours` in the summary table.
- [x] `ai-service/tests/test_benchmark.py` — update the three 2-model-count assertions to include `sarimax`; add SARIMAX row/window/length/determinism assertions (use the fixture to stay fast).

**Acceptance Criteria:**
- Given the Story 4.1 harness, when the benchmark runs, then a SARIMAX model with daily seasonality and `air_temperature` as an exogenous variable is fitted and scored, appearing as a row in `results.csv`.
- Given SARIMAX is slow on the full training set, when it is fitted, then it trains on a documented recent window and that window length is recorded in the results (`train_window_hours`).

## Implementation Notes

- Code review (2026-10-10) changed `SARIMAXForecaster.predict` from one open-loop `get_forecast` to a one-step-ahead roll (`results.extend(...).fittedvalues`) after the human renegotiated the frozen clause. On the real dataset the `sarimax` row moved from MAE 555.88 / MAPE 182.33% / R² −0.405 to MAE 38.67 / RMSE 76.48 / MAPE 6.30% / R² 0.9770 (xgboost: 39.63 / 74.02 / 8.04% / 0.9785).
- `BaseForecaster` now declares `train_window_used: Optional[int] = None`; `score_model` reports `len(train_df)` when it is `None`.
- `fit` keeps `min(SARIMAX_TRAIN_WINDOW_HOURS, len(train_df))`; it selects the same rows as the Code Map's `iloc[-N:]`.
- `statsmodels` floor raised to `>=0.14.2`; summary-table rules widened to 118 characters.
- Tests: 13 in `tests/test_benchmark.py` (was 10), about 40–50 s locally because several tests fit SARIMAX.

## Spec Change Log

- 2026-10-10 — Trigger: code-review decision finding (SARIMAX scored open-loop over 3,504 steps while XGBoost and seasonal-naive use observed lags; the row scored worse than a constant mean). Amended: the frozen "Always" clause on `predict` now specifies a one-step-ahead roll with fixed parameters, and the I/O matrix gained a "One step ahead" row. Avoids: a benchmark row that is not comparable on equal terms (FR20) and a window choice tuned on the test split. KEEP: registry plug-in with no scoring-loop change, the 336 h recent window, exog taken from the frame, the appended `train_window_hours` column.

## Review Triage Log

## Design Notes

- **Recent window (336 h), chosen on a validation slice:** the last 336 h of the training split were held out and each candidate was fitted on the rows before them and scored one step ahead. Validation MAE on the real dataset: 168 h → 78.4, 336 h → 77.8, 720 h → 80.6, 1440 h → 77.8 (fit time 2.0 / 3.1 / 4.6 / 10.5 s). The differences are small, so 336 h is kept as the shortest window that ties the best score. The test split was not used for this choice. (The earlier figures of 424 vs 598 came from the open-loop forecast on the test split and did not reproduce.)
- **Order (1,1,1)×(1,0,1,24):** a reasonable, reproducible statistical baseline; kept as a named constant, deliberately not tuned (this is a baseline, not the serving model).
- **statsmodels defaults for stationarity/invertibility:** no extra `enforce_*` flags — the library default is the standard, defensible setting; convergence warnings are suppressed (I/O matrix) so a noisy fit is non-fatal and still yields a scored row.
- **Serialized size is legitimately large:** a fitted SARIMAX results object joblib-dumps to ~45 MB vs XGBoost's sub-MB. This is a real, informative benchmark result (state-space models are heavy to pickle), not a defect; `train_window_hours` records the training footprint the size reflects.
- **Determinism:** statsmodels MLE with the default optimizer is deterministic for fixed data/order, so `sarimax` accuracy columns are bit-identical across runs (Story 4.1 AC3 holds).
- **Plug into the registry, don't fork scoring:** the "appears as a row" AC needs only a subclass + `@register_forecaster`; `run_scoring` already iterates the registry.
- **Exog and observed readings from the test frame:** `air_temperature` for the test span already exists in `test_df` and is passed straight through as exog — no invented or forecast weather. The roll also reads `test_df["meter_reading"]`, but only values before the hour being predicted, which a test pins (changing the reading at position k leaves predictions up to k unchanged).

## Verification

**Commands:**
- `pip install -r ai-service/requirements.txt` — installs `statsmodels`.
- `cd ai-service && python -m experiments.benchmark.run_benchmark` — expected: `results.csv` has 3 rows including `sarimax`; all 9 columns finite; `sarimax.train_window_hours` (=336) < the full-train count shown for `seasonal_naive`/`xgboost`.
- `pytest ai-service/tests/test_benchmark.py -q` — expected: all pass, including the updated 2-model-count assertions (now 3, or 4 in the pluggability test), the new SARIMAX row/window/length/determinism assertions, and the unchanged `seasonal_naive`/`xgboost` behavior.

## Code Review Findings — 2026-10-10 (4-layer adversarial: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor)

Diff reviewed: uncommitted changes against HEAD `1e55d5b` (= `baseline_commit`). Ground-truthed by running `pytest tests/test_benchmark.py` (10 passed, 37 s) and `python -m experiments.benchmark.run_benchmark` (exit 0) on the real dataset: `sarimax` MAE 555.88 / MAPE 182.33% / R² −0.405, versus `xgboost` MAE 39.63 and `seasonal_naive` MAE 153.00. A constant mean-of-train forecast scores MAE 413.1 on the same test split.

**Decision (1):**
- [x] [Review][Decision → Patch] (Resolved 2026-10-10: the human chose option A — roll the forecast one step ahead through the test span with fixed fitted parameters, then re-select the training window on a validation slice cut from the training split. Requires amending the frozen "forecasts exactly `len(test_df)` steps forward" clause.) SARIMAX is not scored on equal terms with the other two models (FR20). `XGBoostForecaster` predicts from `lag_1h`/`lag_24h` built from observed test-period readings (effectively 1 step ahead) and `SeasonalNaiveForecaster` reads `lag_24h` (24 steps ahead), while `SARIMAXForecaster.predict` issues one open-loop `get_forecast(steps=len(test_df))` of 3,504 steps that never sees an observed test value. The forecast flattens (last values constant at 714.1; std of the last 500 predictions 71 vs 504 for the actuals) and the row scores worse than a constant mean. The code follows the frozen "forecasts exactly `len(test_df)` steps forward" clause, so the defect is in the evaluation protocol, and changing it means renegotiating the frozen block. Related: the Design Notes pick the 336 h window by test-split MAE and quote 424 vs 598; a re-run gives 555.9 (336 h) vs 616.9 (720 h), and at a 24-hour horizon the order reverses (405.8 vs 377.1), so "shorter window is more accurate" is an artifact of the open-loop horizon. The same claim sits in the `models.py` comment above `SARIMAX_TRAIN_WINDOW_HOURS`. Options: (A) roll the forecast one step ahead through the test span with fixed parameters, matching XGBoost's information set; (B) roll 24 steps ahead, re-anchoring daily, matching seasonal-naive; (C) keep the open-loop forecast and record the horizon per model so Story 4.4 can caveat the row.

**Patch (7):**
- [x] [Review][Patch] No test pins the SARIMAX specification: removing `exog=` from both calls or zeroing the seasonal order leaves every test green. Assert `k_exog == 1`, `seasonal_periods == 24`, and that perturbing `test_df["air_temperature"]` changes the predictions. [ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] No test pins "last N rows": `train_df.iloc[:window]` passes every assertion because only the slice length is checked. Assert the fitted endog equals `train_df["meter_reading"].iloc[-N:]`. [ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] The `train_window_hours` contract is implicit and half-tested: `score_model` reads `getattr(model, "train_window_used", len(train_df))`, `BaseForecaster` does not declare the attribute, and no test asserts the full-data models report `len(train_df)` (a fallback of `len(test_df)` would pass). Declare/document the attribute on `BaseForecaster` and assert the value for `seasonal_naive`, `xgboost` and `constant_mean`. [ai-service/experiments/benchmark/models.py, ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] `test_sarimax_row_and_window_in_results` promises "all 9 columns finite" but asserts `pd.notna` only. Use `np.isfinite` on the numeric columns. [ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] `warnings.simplefilter("ignore")` silences every warning category during `fit`, and `mle_retvals["converged"]` is discarded, so a non-converged fit would be scored as a normal row with no trace. Filter only statsmodels' `ConvergenceWarning` and log a warning when the fit did not converge. [ai-service/experiments/benchmark/models.py]
- [x] [Review][Patch] `print_summary_table` rules are 108 characters while the header and rows are 118, so the printed table is ragged; the function also has no test, and a failure inside it makes `main()` exit 1 after `results.csv` is written. Widen the rules to 118 and add a `capsys` test that prints a scored frame and checks the `Window (h)` header and the `sarimax` line. [ai-service/experiments/benchmark/run_benchmark.py, ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] `statsmodels>=0.14.2` sits next to `numpy>=1.26.0`, which admits NumPy 2 (2.4.2 is installed here with statsmodels 0.15.0); statsmodels releases before 0.14.2 do not support NumPy 2. Raise the floor to `>=0.14.2`. [ai-service/requirements.txt]

**Rejected (11):**
- (low) Missing guards in `SARIMAXForecaster` (predict before fit, empty `test_df`, missing columns, NaN exog, unsorted or non-contiguous frames, fewer than 48 training rows, uncontextualised `LinAlgError`, non-finite forecast): none is reachable through the harness, the real dataset is verified gap-free hourly, and each fix adds a guard.
- (false) `min(SARIMAX_TRAIN_WINDOW_HOURS, len(train_df))` deviates from the Code Map's `iloc[-N:]`: both select the same rows for every input.
- (false) `test_sarimax_determinism` compares predictions rather than accuracy columns: identical predictions give identical metrics, and Story 4.1's `test_benchmark_determinism` already runs `run_scoring` twice over the whole registry, which now includes `sarimax`.
- (low) `predict` ignores where `test_df` sits in time: the harness always passes the partition that immediately follows the training split.
- (low) The "Convergence noise" matrix row has no test: forcing a `ConvergenceWarning` needs a contrived fixture; the convergence patch above covers the practical risk.
- (reject — fix edits spec) `train_window_hours` holds a row count, and reports the full train count for `seasonal_naive`, which uses no training data: the column name and semantics come from the frozen block, and rows equal hours on this gap-free dataset.
- (low) `statsmodels` is imported at module top and installed into the served image through `requirements.txt`: the spec's Code Map asked for that line, scipy is already present through scikit-learn, and splitting requirements also means changing CI. Worth deciding before Story 4.3 adds PyTorch to the same file.
- (low) SARIMAX's ~45 MB pickle and batched latency are not like-for-like with the other rows: already acknowledged in the Design Notes.
- (low) Test runtime rose from 11 s to 37 s because five tests each fit SARIMAX and dump ~45 MB: a shared module-scoped fixture is more than a direct correction.
- (reject — reconciled at close) Spec `status: in-review` versus sprint `4-2: in-progress`.
- (reject — fix edits spec) Empty Implementation Notes, and no regenerated `results.csv` in the diff (the file is generated and git-ignored).
