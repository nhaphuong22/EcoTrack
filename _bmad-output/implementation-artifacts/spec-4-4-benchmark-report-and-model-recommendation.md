---
title: 'Story 4.4: Benchmark report and model recommendation'
type: 'feature'
created: '2026-10-23'
status: 'done'
baseline_commit: 'f885e757aac5b05d1096c5348c0f747a56302b04'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 4-4-benchmark-report-and-model-recommendation
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 4.1–4.3 produced a four-model benchmark harness (`ai-service/experiments/benchmark/`) that writes `results.csv` with one aggregate row per model (MAE, RMSE, MAPE, R², training time, hour-1 inference latency, model size), scoring only the **first forecast hour**. A project reviewer still cannot see (a) how each model degrades as the forecast reaches further ahead, (b) the forecast against reality on a chart, or (c) a written, evidence-backed conclusion about which model to serve. FR21 asks for charts and a results export; FR46 asks for per-horizon scoring (1–24 hours ahead) with a recommendation that names the best model at the near and far horizon.

**Approach:** Two separable pieces on top of the existing harness.

1. **Per-horizon scoring inside the harness (compute).** Extend the benchmark so that, in addition to the existing hour-1 `results.csv`, it evaluates every registered model over a **rolling forecast origin** across the test split: at each origin `t`, each model emits a 24-hour-ahead path using **only readings observed up to and including `t`**. The path is produced by each model in its natural way under one shared protocol — **recursive** one-step-ahead for lag-based models (XGBoost feeds its own prediction back into `lag_1h`; `lag_24h` stays an observed value because every horizon `h ≤ 24` reads `t+h−24 ∈ [t−23, t]`), **native multi-step** for SARIMAX (`forecast(h)` from the origin) and LSTM (its 24-value output head), and **seasonal-naive** as the observed reading 24 h earlier. The harness writes per-horizon MAE/RMSE to `results_by_horizon.csv` and persists a per-timestamp **predictions artifact** so the report never recomputes anything.

2. **Report generation (pure read).** A separate `report` command reads `results.csv`, `results_by_horizon.csv` and the predictions artifact and writes four PNG charts, a human-readable `REPORT.md` (results table + charts + recommendation) and a machine-readable `results.json` for the MLOps page (Story 4.12). The report performs **no training, fitting or model inference** — it only reads, plots and formats.

**Decisions locked with the product owner (2026-10-23):**
- Charts get their per-timestamp predictions from a **harness-written predictions artifact**; the report is strictly read-only (chosen over re-running the benchmark inside the report or embedding full prediction series in `results.json`).
- Per-horizon evaluation uses one **rolling-origin** protocol applied to all four models, recursive for lag-based models, native multi-step where a model supports it — so horizon-1 of the per-horizon table reconciles with the existing hour-1 `results.csv`.
- **SARIMAX per-origin cost** is bounded by fitting once on the training split and, at each origin, **extending/applying** the fitted model to the observed history with **fixed parameters (no per-origin refit)** before `forecast(24)` — chosen over full refit (too slow over ~3.5k origins) and over striding origins (keeps every-hour origins for all models).
- The **predictions artifact is Parquet holding all 24 horizons** for every model (`model`, `origin_timestamp`, `horizon_h`, `target_timestamp`, `actual`, `prediction`); `pyarrow` is an experiment-only dependency. CSV / chart-only subsets were rejected to keep the per-horizon data reusable by later analysis and the MLOps page.
- **Future exogenous `air_temperature`** at horizons `t+1 … t+24` is the **actual observed temperature** supplied as a known covariate (perfect-forecast assumption), applied identically to XGBoost's `air_temperature` feature and SARIMAX's `exog`. Only the forecast **target** (`meter_reading`) is restricted to values observed up to the origin; weather is treated as a known input. Last-observed-hold and 24 h-persistence were rejected as less realistic for a weather-aware load forecast.

## Boundaries & Constraints

**Always:**
- Per-horizon scoring reuses the exact Story 4.1 dataset path, `train_models.engineer_features`, and `train_models.split_time_series_data` (80/20 chronological, no shuffle); the test partition is identical to the one `results.csv` is scored on — imported, never re-derived.
- At every forecast origin `t`, each model's 24-hour path uses **meter readings** observed **up to and including `t`** only; no actual `meter_reading` at `t+1 … t+23` ever enters a feature, a lag, or a conditioning window. For XGBoost this means `lag_1h` at horizon `h ≥ 2` is the model's **own** prior-step prediction, while `lag_24h` remains the observed reading at `t+h−24`. Exogenous `air_temperature` is exempt from this rule — it is supplied as the actual future value (perfect-forecast covariate, see the locked decision).
- `results_by_horizon.csv` has one row per `(model, horizon)` for horizons `1..24`, with columns exactly `model`, `horizon_h`, `mae_kwh`, `rmse_kwh`, and no `NaN`/empty cells for scored models.
- Horizon-1 MAE/RMSE in `results_by_horizon.csv` reconcile with each model's hour-1 figures in `results.csv` to within documented floating tolerance (same test rows, same metric functions) — a divergence beyond tolerance is a leakage/alignment bug, not acceptable noise.
- The predictions artifact is written by the **harness** (not the report) as a **Parquet file** holding, per model, every `(origin_timestamp, horizon_h)` with its `target_timestamp`, `actual`, and `prediction` for all 24 horizons; it is read-only input to the report.
- SARIMAX is fitted once on the training split; at each origin its state is advanced over observed history with the **already-fitted parameters** (statsmodels `append`/`extend`/`apply`, `refit=False`) and never refit per origin.
- Chart rendering uses matplotlib with a **non-interactive `Agg` backend** (set before importing pyplot) so PNGs render on a headless CI/host; `matplotlib` and `pyarrow` are declared in `ai-service/requirements-experiments.txt`, never in the served `requirements.txt`.
- The `report` command is pure read + plot + format: it imports no training code paths, fits nothing, and calls no model `predict`; given stale-but-present artifacts it still produces a report.
- The report writes exactly four PNG charts: (1) metric comparison across models, (2) actual vs predicted for a sample week, (3) absolute error by hour of day, (4) error against horizon `1..24` for all four models.
- `REPORT.md` contains the full results table, embeds the four charts, and a recommendation that (a) names the single model to **serve**, explicitly weighing accuracy against inference latency and model file size, and (b) states which model is best at **1 hour ahead** and which at **24 hours ahead**, each with its metric.
- `results.json` is written for the MLOps page (Story 4.12) with a stable, documented schema: the per-model aggregate metrics, the per-horizon series, the chosen-to-serve model name, and relative paths to the four PNGs.
- Per-horizon accuracy columns are deterministic across two runs in the same environment (seeds fixed, honoring Story 4.1 AC3); timing columns are exempt.
- Plain Python, runnable without starting FastAPI or any network/DB (AD-1). UTF-8 console output on Windows (reuse the existing `reconfigure` guard) so `R²` prints cleanly.

**Never:**
- Do not modify `src/models/train_models.py`, and never read-then-resave or overwrite the production artifacts in `models_saved/`; the harness fits its own in-memory models for comparison only.
- Do not change the existing `results.csv` schema (`BENCHMARK_COLUMNS`), the registry mechanics, or the `fit`/`predict` contract of the four forecasters; per-horizon support is **added** alongside them, not a breaking edit to `score_model`/`run_scoring`'s existing hour-1 output.
- Do not re-implement the split or feature engineering, and do not let any future actual reading leak into a horizon-`h` feature (recursive feedback only).
- Do not serve any model from the API or write a serving/promotion decision here — the recommendation is advisory text for the reviewer; Story 4.5 owns registration/promotion.
- Do not make the report train, fit, or run inference; if the required artifacts are missing it exits non-zero naming the missing file rather than regenerating them.
- Do not call any external/network source or an LLM to write the recommendation; it is computed deterministically from the metrics.
- Do not invent metric columns beyond those listed for `results_by_horizon.csv`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path — benchmark | Processed CSV present, 4 models registered | `results.csv` (4 rows, unchanged schema) + `results_by_horizon.csv` (4 × 24 rows) + predictions artifact, all finite | N/A |
| Happy path — report | Benchmark artifacts present | 4 PNGs + `REPORT.md` (table + charts + recommendation) + `results.json` written | N/A |
| Recursive no-leakage (XGBoost) | Origin `t`, horizon `h ≥ 2` | `lag_1h` = model's own step-`h−1` prediction; `lag_24h` = observed reading at `t+h−24`; no actual at `≥ t+1` touched | Assertion/guard in the roll loop |
| Native multi-step (SARIMAX/LSTM) | Origin `t` | SARIMAX `forecast(h)` / LSTM output head give the horizon-`h` value from history ≤ `t`; horizon-1 == hour-1 within tolerance | N/A |
| Seasonal-naive per-horizon | Engineered test partition | Horizon-`h` prediction = observed reading at `t+h−24` (h ≤ 24); error-vs-horizon ~flat | N/A |
| Span-edge origins | Origins where `t+24` exceeds the test end | Incomplete origins drop the horizons past the end (or are excluded); `results_by_horizon.csv` has no `NaN`; rule documented | Deterministic truncation, not silent NaN |
| Short test span for chart 2 | Test partition < 1 week | "Sample week" falls back to the full test span; window choice is deterministic (fixed rule, not random) | N/A |
| Report missing artifacts | `results.csv` / `results_by_horizon.csv` / predictions absent | Exits non-zero naming the missing path; no partial `REPORT.md`/PNG/`results.json` written | `FileNotFoundError` surfaced, not swallowed |
| Determinism | Benchmark run twice | Per `(model, horizon)`, `mae_kwh`/`rmse_kwh` identical across runs | N/A |
| Recommendation tie/near-tie | Two models within a documented metric epsilon | Tie-break rule is deterministic and documented (e.g. prefer lower latency, then smaller size); recommendation text states the trade-off | N/A |
| MLOps schema | `results.json` consumed by Story 4.12 | Keys stable and documented; PNG paths relative; valid JSON | N/A |

</frozen-after-approval>

## Code Map

- `ai-service/src/models/train_models.py` — reuse (import, do not edit): `load_dataset`/`engineer_features`/`split_time_series_data`, `XGB_FEATURE_COLUMNS` (note it includes `lag_1h` **and** `lag_24h` — the recursion driver). Default dataset `data/processed/office_building_clean.csv`.
- `ai-service/experiments/benchmark/models.py` — existing `BaseForecaster` (`fit`/`predict`, `name`, `train_window_used`), the `_FORECASTER_REGISTRY` + `register_forecaster`/`get_registered_forecasters`, and `SeasonalNaiveForecaster` (`predict` = `test_df["lag_24h"]`), `XGBoostForecaster` (`model.predict(test_df[XGB_FEATURE_COLUMNS])`), `SARIMAXForecaster` (fits last `SARIMAX_TRAIN_WINDOW_HOURS=336` rows; `predict` = `self._results.extend(endog, exog).fittedvalues`, one-step). **Add** a per-origin 24-step capability under one protocol: a default recursive path for lag models (feed prediction into `lag_1h`, keep observed `lag_24h`) overridden by SARIMAX (`self._results.extend(history≤t, exog≤t).forecast(steps=24, exog=future_exog)`, fixed params) and LSTM. Do not change the existing hour-1 `predict` contract or `train_window_used` semantics.
- `ai-service/experiments/benchmark/lstm.py` — `LSTMForecaster` already computes the full 24-value head (`self._net(windows)` shape `(n, 24)`) and currently returns only column 0 denormalized (`outputs[:, 0] * scale + mean`, lines 236-237). Per-horizon reuses the same windows and takes `outputs[:, h-1]` denormalized — no future exog needed. Reuse `LSTM_OUTPUT_HOURS=24`, `_TARGET_INDEX`; keep seeds/determinism intact.
- `ai-service/experiments/benchmark/__init__.py` — imports `models` + `lstm` + `benchmark`, so `python -m experiments.benchmark.*` registers all four forecasters via package import. The per-horizon scorer must be reachable the same way (keep LSTM registration working).
- `ai-service/experiments/benchmark/benchmark.py` — `BENCHMARK_COLUMNS` (9 cols incl. `train_window_hours`) and hour-1 `score_model`/`run_scoring` stay **unchanged**. **Add** a rolling-origin per-horizon scorer that iterates origins across the test split, collects each model's 24-vector (via the new model capability), aligns to actuals, and returns per-`(model, horizon)` MAE/RMSE plus the aligned prediction rows for the Parquet artifact. Pure, unit-testable, no CLI.
- `ai-service/experiments/benchmark/run_benchmark.py` — existing CLI, extended to also write `results_by_horizon.csv` and the Parquet predictions artifact (`predictions.parquet`) next to `results.csv` (new `--output` siblings; defaults under `experiments/benchmark/`).
- `ai-service/requirements-experiments.txt` — add `matplotlib` (report charts) and `pyarrow` (Parquet predictions artifact); the served `requirements.txt`/Dockerfile are untouched.
- `ai-service/experiments/benchmark/report.py` *(new)* — pure read + plot + format: reads the three artifacts, renders the four PNGs (matplotlib), computes the recommendation deterministically from metrics (accuracy vs latency vs size; best-at-1h / best-at-24h), and returns the `REPORT.md` text and `results.json` object. No fitting/inference.
- `ai-service/experiments/benchmark/run_report.py` *(new)* — `__main__` CLI (`--results`, `--results-by-horizon`, `--predictions`, `--out-dir`); reads → renders → writes `REPORT.md`, `results.json`, four PNGs; exits non-zero on any missing input.
- `ai-service/tests/test_benchmark_horizon.py` *(new)* — per-horizon matrix: no-leakage recursion, horizon-1↔hour-1 reconciliation, naive = observed `lag_24h`, span-edge truncation, determinism.
- `ai-service/tests/test_report.py` *(new)* — report matrix: artifacts→4 PNGs + `REPORT.md` + valid `results.json`, recommendation names a served model and best-at-1h/24h, missing-artifact non-zero exit, deterministic tie-break.

## Tasks & Acceptance

**Execution:**
- [x] Add per-origin multi-step protocol to `models.py` (recursive default; SARIMAX/LSTM native overrides) with the no-leakage guard — FR46.
- [x] Add rolling-origin per-horizon scorer to `benchmark.py` returning per-`(model, horizon)` MAE/RMSE + aligned prediction series — FR46.
- [x] Extend `run_benchmark.py` to write `results_by_horizon.csv` and the predictions artifact — FR21, FR46.
- [x] Add `report.py` + `run_report.py`: four PNG charts, `REPORT.md` (table + charts + recommendation), `results.json` — FR21, FR46.
- [x] `test_benchmark_horizon.py` + `test_report.py` covering the full I/O matrix.

**Acceptance Criteria (from epics.md Story 4.4 — FR21, FR46):**
- Given the four registered forecasters, when the benchmark runs, then each is scored at every horizon 1–24 h ahead on the same test split using only readings observed before the origin, and per-horizon MAE/RMSE are written to `results_by_horizon.csv`.
- Given the per-horizon results, when the report is generated, then a fourth chart shows error against horizon for all models and the recommendation states which model is best at 1 h and at 24 h ahead.
- Given a completed `results.csv`, when I run the report command, then three PNG charts are written: metric comparison across models, actual vs predicted for a sample week, and absolute error by hour of day.
- Given the results, when the report is generated, then `REPORT.md` contains the results table, the three charts, and a recommendation that names the model to serve and weighs accuracy against latency and size.
- Given the benchmark results, when they are saved, then a `results.json` copy is written for the MLOps page to display.

## Implementation Notes

- **`models.py`** — added `BaseForecaster.forecast_grid(test_df, horizon=24)` (default raises `NotImplementedError`), plus concrete overrides: `SeasonalNaiveForecaster` (grid = observed `lag_24h[q]`), `XGBoostForecaster` (vectorised-per-step recursion; `lag_1h` ← own prior prediction for `h ≥ 2`, observed for `h = 1`; predicts through a `DataFrame` so feature names match the fit), `SARIMAXForecaster` (fit-once; per origin `self._results.extend(obs ≤ t).forecast(h_max, exog=actual future temp)` — no refit, `ConvergenceWarning` silenced). The existing hour-1 `predict` contracts and `train_window_used` are untouched.
- **`lstm.py`** — added `LSTMForecaster.forecast_grid`; reuses the existing windows and the full 24-value head (`outputs[p+1, :]` is the path from the origin ending at test position `p`), denormalised with the fitted scaler. No future exog needed; guards `horizon <= LSTM_OUTPUT_HOURS`.
- **`benchmark.py`** — added `DEFAULT_HORIZON=24`, `HORIZON_COLUMNS`, `PREDICTION_COLUMNS`, `score_grid` (grid → per-horizon MAE/RMSE rows + long predictions frame, dropping span-edge `NaN`) and `run_horizon_scoring` (fits each registered model, builds its grid, aggregates). `BENCHMARK_COLUMNS` and the hour-1 `score_model`/`run_scoring` are unchanged.
- **`run_benchmark.py`** — `execute_benchmark` now also writes `results_by_horizon.csv` and `predictions.parquet` (siblings of `results.csv`, overridable via new `--results-by-horizon`/`--predictions`/`--horizon` flags). NOTE: this means the existing `execute_benchmark` happy path now also runs per-horizon scoring and requires `pyarrow`; CI installs `requirements-experiments.txt`.
- **`report.py` / `run_report.py`** — pure read + render: `matplotlib` forced to the `Agg` backend before `pyplot` import; four charts, deterministic recommendation (lowest mean MAE across horizons, tie-break latency→size), `REPORT.md` (hand-built Markdown table, no `tabulate` dependency) and `results.json` (numpy scalars coerced to native JSON numbers). Missing artifacts raise `FileNotFoundError`/exit non-zero before anything is written.
- **Deps** — `matplotlib>=3.8.0` and `pyarrow>=16.0.0` added to `ai-service/requirements-experiments.txt` only.
- **Cost note** — SARIMAX `forecast_grid` is O(n²) in the test length (one `extend` per origin). This is the accepted consequence of the fit-once/no-refit decision; acceptable for an offline experiment, and the report never pays it (it reads artifacts).
- **Verification status** — all files pass `python -m py_compile`. Per the project rule (see memory: never run training files; print the command), the benchmark run and `pytest` were **not executed here**; the user must run the commands in the Verification section to complete the Matrix Test Audit.

## Design Notes

- **Why a shared rolling-origin protocol, not per-model ad hoc:** scoring every model from the same set of origins with the same "observed up to `t`" rule is the only way the error-vs-horizon chart compares like with like. Each model fills its 24-vector in its natural way, but the origins, the alignment to actuals, and the metric functions are common code — so the chart is apples-to-apples and horizon-1 reconciles with the existing hour-1 `results.csv`.
- **Recursion is forced by `lag_1h`:** `XGB_FEATURE_COLUMNS` contains `lag_1h`, so a one-shot `predict` cannot score horizon `h ≥ 2` without the actual at `t+h−1`. Feeding the model's own prediction back into `lag_1h` (while keeping `lag_24h` observed) is what makes multi-horizon honest; this is the crux the PO's "rolling-origin recursive" choice targets.
- **Report stays read-only by construction:** persisting a predictions artifact from the harness (the PO's data-flow choice) keeps the report deterministic and cheap, decouples plotting from compute, and gives Story 4.12's MLOps page the same numbers the charts use. Re-running inference inside the report would risk the charts and `results.json` drifting from `results.csv`.
- **Recommendation is computed, not written by an LLM:** a deterministic rule (lowest serving-horizon error, with a documented latency/size tie-break) keeps the "evidence for the choice" reproducible and testable; the prose only narrates the computed decision.
- **Span edges are truncated, never NaN:** origins whose 24 h window runs past the test end contribute only the horizons that have an actual; this keeps `results_by_horizon.csv` finite and the determinism guarantee intact.

## Verification

**Commands (run from `ai-service/`):**
- `python -m experiments.benchmark.run_benchmark` — writes `results.csv` (4 rows, unchanged schema), `results_by_horizon.csv` (4 × 24 rows, finite), and the predictions artifact.
- `python -m experiments.benchmark.run_report` — writes four PNGs, `REPORT.md` and `results.json`; exits non-zero if any input artifact is missing.
- `pytest tests/test_benchmark_horizon.py tests/test_report.py -q` — per-horizon no-leakage, horizon-1↔hour-1 reconciliation, span-edge truncation, determinism; report artifacts, recommendation content, missing-artifact failure.
- Determinism spot-check: run the benchmark twice and diff the `mae_kwh`/`rmse_kwh` columns of `results_by_horizon.csv` — expected identical.

> Theo quy ước dự án, các lệnh train/benchmark ở trên do người dùng tự chạy; spec chỉ in lệnh, không tự thực thi.

## Spec Change Log

- 2026-10-23 — Folded three build decisions into the frozen Intent/Boundaries during `bmad-build` step-01: SARIMAX uses fit-once + per-origin `append`/`extend` with fixed params (no refit); predictions artifact is Parquet with all 24 horizons (`pyarrow` dependency); report charts use a headless matplotlib `Agg` backend (`matplotlib` + `pyarrow` added to `requirements-experiments.txt`). Status `backlog` → `draft`.
- 2026-10-23 (step-02 plan) — Resolved one Open Question discovered during investigation: future `air_temperature` for XGBoost/SARIMAX multi-horizon uses the **actual observed future value** (perfect-forecast covariate); only `meter_reading` is origin-restricted. Scope gate: spec is ~3.8k tokens (over the 1600 guideline); product owner chose to **keep the full spec** as one cohesive story rather than split the harness/report seam.

## Review Triage Log

### Review Findings (code review 2026-10-23)

Adversarial review (4 layers: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor) against baseline `f885e757`. 9 survivors (3 decision-needed, 4 patch, 2 defer), 11 rejected.

- [x] [Review][Decision → resolved: keep always-on] `execute_benchmark` has no hour-1-only path — it always runs the heavy per-horizon scorer (double-fit) and hard-requires `pyarrow`. **Resolved 2026-10-23:** PO chose to keep always-on (offline experiment; cost accepted); no code change. [run_benchmark.py:96-112]
- [x] [Review][Decision → resolved: patch] Near-tie recommendation epsilon not implemented — matrix "Recommendation tie/near-tie" calls for a documented epsilon band. **Resolved 2026-10-23:** implemented a 1%-of-best-mean-MAE near-tie band (`RECOMMENDATION_EPSILON_FRAC`), decided on latency→size, rationale updated. [report.py:compute_recommendation]
- [x] [Review][Decision → resolved: patch] Generated artifacts not git-ignored. **Resolved 2026-10-23:** added `ai-service/experiments/benchmark/.gitignore` for all generated artifacts (results.csv, results_by_horizon.csv, predictions.parquet, results.json, REPORT.md, chart_*.png). [ai-service/experiments/benchmark/.gitignore]
- [x] [Review][Patch] No test asserts `execute_benchmark` writes `results_by_horizon.csv` + `predictions.parquet` at the default sibling paths with the right schema — **fixed:** added `test_execute_benchmark_writes_horizon_and_prediction_artifacts` [ai-service/tests/test_benchmark.py]
- [x] [Review][Patch] No test reconciles the horizon-1 **aggregate** MAE/RMSE with the hour-1 path — **fixed:** added `test_horizon_one_aggregate_reconciles_with_hour_one` (aligned row set 1..n-1, per-model tolerances) [ai-service/tests/test_benchmark_horizon.py]
- [x] [Review][Patch] `--horizon` unvalidated — **fixed:** up-front `1 <= horizon <= 24` guard in `execute_benchmark` (raises before writing `results.csv`); regression test `test_execute_benchmark_rejects_out_of_range_horizon` [ai-service/experiments/benchmark/run_benchmark.py]
- [x] [Review][Patch] `score_grid` NaN mask ignored actuals — **fixed:** mask now `~np.isnan(preds) & ~np.isnan(acts)` [ai-service/experiments/benchmark/benchmark.py:185]
- [x] [Review][Patch] Native multi-step no-leakage tested only at horizon 1 — **fixed:** added parametrized `test_native_multistep_no_leakage` (SARIMAX+LSTM; a shocked future actual leaves `grid[p]` unchanged) [ai-service/tests/test_benchmark_horizon.py]
- [x] [Review][Defer] Runtime acceptance criteria marked `[x]` but not executed — benchmark run + `pytest` were not run (project rule: user runs training/benchmark). Data-dependent ACs (4×24 finite rows, reconciliation on real data, 4 PNGs rendering) unverified [spec Verification] — deferred: settled by the user running the three Verification commands.
- [x] [Review][Defer] `compute_recommendation` not robust to empty/mismatched present artifacts (empty `by_horizon` → `iloc[0]` IndexError; a model in `by_horizon` absent from `results.csv` → left-join NaN → `int(NaN)` ValueError), and charts are rendered before the crash (orphan PNGs) [report.py:225-230, 335-349] — deferred: low likelihood (both artifacts come from one harness run; `run_report` already exits non-zero), optional hardening.

**Rejected:**
- `false` — XGBoost `forecast_grid` pre-fit "AttributeError": `self.model` is instantiated in `__init__` (never None); an unfitted call raises sklearn `NotFittedError` (clear), not AttributeError, and `run_horizon_scoring` always fits first (unreachable).
- `low` — actual-vs-predicted chart "silently empty" with no horizon-1 rows: `score_grid` always emits `h=1` first; empty only if the test span ≤1 row, impossible for a 20% split of ~14k rows.
- `low` — `results_by_horizon.csv` "not guaranteed 24 rows": all 24 emitted on any span ≥25 rows; the fixture test already asserts 1..24, and the span-edge matrix row explicitly tolerates truncation on short spans.
- `low` — `load_artifacts` no schema validation: artifacts come from the same harness with a fixed schema; a foreign CSV raises a KeyError that `run_report` already converts to a non-zero exit. Guard adds complexity for an unreachable case.
- `reject` — recommendation "weighing accuracy vs latency/size" wording oversells: fix edits the frozen spec; the code matches the Design Note ("lowest error + documented latency/size tie-break").
- `reject` — reconciliation tolerance "only in the test, not the spec": fix edits the spec.
- `reject` — frozen-after-approval section edited: sanctioned by a Spec Change Log entry (PO renegotiation 2026-10-23); not a defect.
- `reject` — stale "three charts" acceptance criterion: fix edits the spec; and not stale — AC lines 103-104 are the original FR21 three-chart criterion, line 102 adds the fourth chart.
- `reject` — `results.json` schema undocumented: fix edits the spec; top-level keys are already pinned by `test_results_json_schema_and_recommendation`.
- `low` — `generate_report` writes PNGs before REPORT.md/json (orphan charts on render failure): folded into the `compute_recommendation` robustness defer; only reachable via malformed present artifacts.
- `low` — `test_xgboost_recursion_uses_own_prediction` predicts via bare numpy not the DataFrame path: numerically identical, the assertion still proves the recursion; cosmetic test-fidelity nit.
