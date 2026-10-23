---
title: 'Story 4.4: Benchmark report and model recommendation'
type: 'feature'
created: '2026-10-23'
status: 'draft'
baseline_commit: 'ef78a9b544641e9bbdd22ca1398314208e1d72ff'
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

## Boundaries & Constraints

**Always:**
- Per-horizon scoring reuses the exact Story 4.1 dataset path, `train_models.engineer_features`, and `train_models.split_time_series_data` (80/20 chronological, no shuffle); the test partition is identical to the one `results.csv` is scored on — imported, never re-derived.
- At every forecast origin `t`, each model's 24-hour path is computed from readings observed **up to and including `t`** only; no reading at `t+1 … t+23` (actual future) ever enters a feature, a lag, or a conditioning window. For XGBoost this means `lag_1h` at horizon `h ≥ 2` is the model's **own** prior-step prediction, while `lag_24h` remains the observed reading at `t+h−24`.
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
- `ai-service/experiments/benchmark/models.py` — existing `BaseForecaster`/registry and the four forecasters. **Add** a per-origin multi-step capability under one protocol: a default recursive path (uses existing `predict` step-by-step, feeding prediction into `lag_1h`, observed `lag_24h`) overridable by `SARIMAXForecaster` (native `forecast(h)`) and `LSTMForecaster` (24-value head). No change to the existing `fit`/`predict` hour-1 contract.
- `ai-service/experiments/benchmark/benchmark.py` — existing hour-1 `run_scoring` stays. **Add** a rolling-origin per-horizon scorer that iterates origins across the test split, collects each model's 24-vector, aligns to actuals, and returns per-`(model, horizon)` MAE/RMSE plus the aligned prediction series for the artifact. Pure, unit-testable, no CLI.
- `ai-service/experiments/benchmark/run_benchmark.py` — existing CLI, extended to also write `results_by_horizon.csv` and the Parquet predictions artifact (`predictions.parquet`) next to `results.csv` (new `--output` siblings; defaults under `experiments/benchmark/`).
- `ai-service/requirements-experiments.txt` — add `matplotlib` (report charts) and `pyarrow` (Parquet predictions artifact); the served `requirements.txt`/Dockerfile are untouched.
- `ai-service/experiments/benchmark/report.py` *(new)* — pure read + plot + format: reads the three artifacts, renders the four PNGs (matplotlib), computes the recommendation deterministically from metrics (accuracy vs latency vs size; best-at-1h / best-at-24h), and returns the `REPORT.md` text and `results.json` object. No fitting/inference.
- `ai-service/experiments/benchmark/run_report.py` *(new)* — `__main__` CLI (`--results`, `--results-by-horizon`, `--predictions`, `--out-dir`); reads → renders → writes `REPORT.md`, `results.json`, four PNGs; exits non-zero on any missing input.
- `ai-service/tests/test_benchmark_horizon.py` *(new)* — per-horizon matrix: no-leakage recursion, horizon-1↔hour-1 reconciliation, naive = observed `lag_24h`, span-edge truncation, determinism.
- `ai-service/tests/test_report.py` *(new)* — report matrix: artifacts→4 PNGs + `REPORT.md` + valid `results.json`, recommendation names a served model and best-at-1h/24h, missing-artifact non-zero exit, deterministic tie-break.

## Tasks & Acceptance

**Execution:**
- [ ] Add per-origin multi-step protocol to `models.py` (recursive default; SARIMAX/LSTM native overrides) with the no-leakage guard — FR46.
- [ ] Add rolling-origin per-horizon scorer to `benchmark.py` returning per-`(model, horizon)` MAE/RMSE + aligned prediction series — FR46.
- [ ] Extend `run_benchmark.py` to write `results_by_horizon.csv` and the predictions artifact — FR21, FR46.
- [ ] Add `report.py` + `run_report.py`: four PNG charts, `REPORT.md` (table + charts + recommendation), `results.json` — FR21, FR46.
- [ ] `test_benchmark_horizon.py` + `test_report.py` covering the full I/O matrix.

**Acceptance Criteria (from epics.md Story 4.4 — FR21, FR46):**
- Given the four registered forecasters, when the benchmark runs, then each is scored at every horizon 1–24 h ahead on the same test split using only readings observed before the origin, and per-horizon MAE/RMSE are written to `results_by_horizon.csv`.
- Given the per-horizon results, when the report is generated, then a fourth chart shows error against horizon for all models and the recommendation states which model is best at 1 h and at 24 h ahead.
- Given a completed `results.csv`, when I run the report command, then three PNG charts are written: metric comparison across models, actual vs predicted for a sample week, and absolute error by hour of day.
- Given the results, when the report is generated, then `REPORT.md` contains the results table, the three charts, and a recommendation that names the model to serve and weighs accuracy against latency and size.
- Given the benchmark results, when they are saved, then a `results.json` copy is written for the MLOps page to display.

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

## Review Triage Log
