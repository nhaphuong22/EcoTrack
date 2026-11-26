---
title: 'Story 4.3: Add an LSTM forecaster'
type: 'feature'
created: '2026-10-10'
status: 'done'
baseline_commit: 'bf614912045a81c17c4cb4b8decd8a45a7247722'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 4-3-add-an-lstm-forecaster
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The benchmark compares a seasonal-naive baseline, XGBoost and SARIMAX, so the choice of serving model is not yet backed by a neural baseline (FR20, FR22). PyTorch is also not declared anywhere in the repo, and the two experiment-only libraries must not inflate the served image (NFR5 asks for CPU-only builds).

**Approach:** Add an `LSTMForecaster` (PyTorch, CPU) that plugs into the existing registry and is scored as a fourth `results.csv` row. It takes a 168-hour input window and emits a 24-hour output, scales inputs with a scaler fitted on the training split only, and stops early on a validation slice cut from the training split. To stay on equal terms with XGBoost and SARIMAX, the benchmark row scores the **first hour** of each 24-hour output, rolled through the test span on observed history. Experiment-only dependencies move to a separate `requirements-experiments.txt` that CI installs and the Docker image does not.

## Boundaries & Constraints

**Always:**
- `LSTMForecaster` (registry name `lstm`) subclasses `BaseForecaster`, lives in its own module, registers via `@register_forecaster`, and appears as a fourth row with no change to `score_model`/`run_scoring` control flow or to `BENCHMARK_COLUMNS`.
- The network is an LSTM with one or two layers, a 168-hour input window and a 24-value output head (hours t … t+23), trained on CPU only.
- Input scaling is fitted on the training rows only; the validation slice and the test split are transformed with that fitted scaler, never used to fit it.
- Training holds out the **last part of the training split** as a validation slice and stops early when validation loss stops improving (documented patience and epoch cap as module constants); the test split is never used for training, scaling, early stopping or hyperparameter choice.
- `predict(test_df)` returns a 1-D float ndarray of length `len(test_df)` holding the **hour-1** output for each test row: the forecast for hour t is produced from the 168 observed readings before t (the tail of the training split kept from `fit`, then earlier test rows) and never from the reading at t or later.
- A full fit on the real dataset finishes within 15 minutes on a laptop CPU.
- Accuracy metrics are identical across two runs in the same environment (fixed seeds, deterministic CPU settings), honoring Story 4.1 AC3.
- The module is importable and usable as plain Python without starting FastAPI (AD-1).
- `torch` (CPU build) and `statsmodels` are declared in `ai-service/requirements-experiments.txt`; CI installs it before running tests.

**Never:**
- Do not add `torch` to `ai-service/requirements.txt` or change the Dockerfile; the served image must not gain experiment-only libraries.
- Do not use a GPU, CUDA wheels, or any device other than CPU.
- Do not change `SeasonalNaiveForecaster`, `XGBoostForecaster`, `SARIMAXForecaster`, the registry mechanics, the scoring loop, `train_models.py`, or anything under `models_saved/`.
- Do not serve the LSTM from the API or register it with any serving path (later stories decide the serving model).
- Do not add charts or a report (Story 4.4).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| LSTM scored | Benchmark run on the dataset | `results.csv` has a fourth row `lstm`, all 9 columns finite | N/A |
| Architecture | Fitted model inspected | 1 or 2 LSTM layers; input sequence length 168; output size 24 | N/A |
| Scaler isolation | Test (or validation) values changed, model refitted on the same training rows | Fitted scaler statistics are unchanged | N/A |
| One step ahead | Reading at test position k changed | Predictions up to k unchanged; prediction at k+1 changes | N/A |
| Start of test span | First test rows have fewer than 168 earlier test rows | History is completed from the training tail; predictions are finite for every test row | N/A |
| Early stopping | Validation loss stops improving | Training stops before the epoch cap and keeps the best-validation weights | N/A |
| Determinism | Benchmark run twice | `lstm` accuracy columns identical across runs | N/A |
| Time budget | Full fit on the real dataset, CPU | `training_time_s` < 900 | N/A |
| Too little history | `train_df` shorter than 168 + 24 rows | Clear `ValueError` naming the minimum rows needed | Raised, not swallowed |

</frozen-after-approval>

## Code Map

- `ai-service/experiments/benchmark/lstm.py` *(new)* — `LSTMForecaster(BaseForecaster)` registered as `lstm`; the `torch.nn` module (LSTM → linear head of 24) and module constants: `LSTM_INPUT_HOURS = 168`, `LSTM_OUTPUT_HOURS = 24`, `LSTM_NUM_LAYERS`, `LSTM_HIDDEN_SIZE`, `LSTM_BATCH_SIZE`, `LSTM_LEARNING_RATE`, `LSTM_MAX_EPOCHS`, `LSTM_PATIENCE`, `LSTM_VALIDATION_FRACTION`, `LSTM_SEED`, `LSTM_NUM_THREADS`, `LSTM_FEATURES = ("meter_reading", "air_temperature")`. `fit`: raise `ValueError` naming the minimum when `len(train_df) < LSTM_INPUT_HOURS + LSTM_OUTPUT_HOURS`; seed torch + NumPy, `torch.use_deterministic_algorithms(True)`, `torch.set_num_threads(LSTM_NUM_THREADS)`; fit a `StandardScaler` on the rows **before** the validation slice; build (168 → 24) windows; train with early stopping and restore the best-validation `state_dict`; keep the last 168 scaled training rows in `self._history`. `predict`: build one 168-row window per test row from `self._history` plus earlier test rows, run batched inference, inverse-scale, return output index 0. Test-visible internals: `self._net`, `self._scaler`, `self._history`, `self._val_X`, `self._val_y`, `self._epochs_run`, `self._best_val_loss`. Set `train_window_used` to the rows the scaler and weights are fitted on (the split minus the validation slice), and read the epoch/patience constants inside `fit` so a test fixture can lower them. `__getstate__` drops `_val_X`/`_val_y` from the pickled artifact so `model_file_size_bytes` measures the model, not the training scaffolding.
- `ai-service/experiments/benchmark/models.py` — `BaseForecaster` (L22-48), `_FORECASTER_REGISTRY`/`register_forecaster` (L52-80), the three existing forecasters (L83-200). Import `BaseForecaster`/`register_forecaster` only; do not edit.
- `ai-service/experiments/benchmark/__init__.py` — import `experiments.benchmark.lstm` so the model registers, and add `LSTMForecaster` to the imports and `__all__` (L6-25).
- `ai-service/experiments/benchmark/benchmark.py`, `run_benchmark.py` — unchanged; `BENCHMARK_COLUMNS` (L19-29) already carries `train_window_hours` and `score_model` (L32-103) already reports `len(train_df)` when `train_window_used` is `None`, so the registry drives the new row and the summary table.
- `ai-service/requirements-experiments.txt` *(new)* — `--extra-index-url https://download.pytorch.org/whl/cpu`, `torch==2.10.0+cpu`, `statsmodels>=0.14.2`.
- `ai-service/requirements.txt` — delete the `statsmodels>=0.14.2` line (L9); nothing under `ai-service/src/` imports `experiments` or `statsmodels`.
- `.github/workflows/ci.yml` — add `pip install -r requirements-experiments.txt` to the AI-service install step (L41-45) and add `ai-service/requirements-experiments.txt` to `cache-dependency-path` (L39).
- `ai-service/tests/conftest.py` — add one function-scoped autouse fixture that monkeypatches `experiments.benchmark.lstm.LSTM_MAX_EPOCHS`/`LSTM_PATIENCE` down so every benchmark test fits a cheap LSTM.
- `ai-service/tests/test_benchmark.py` — the three hard-coded registry counts grow by one: `len == 3` → `4` (L57) and the `model_names` set (L60), `len == 3` → `4` (L90) and its set (L91), pluggability `len == 4` → `5` (L147).
- `ai-service/tests/test_benchmark_lstm.py` *(new)* — LSTM-specific tests on the fixture (`tests/fixtures/office_building_sample.csv`, 1,708 training / 428 test rows).
- `ai-service/src/models/train_models.py` — reused by the new test module only (`load_dataset`/`engineer_features`/`split_time_series_data`, exactly as `test_benchmark.py` does at L29-33); `lstm.py` itself needs nothing from it.

## Tasks & Acceptance

**Execution:**
- [x] `ai-service/requirements-experiments.txt`, `ai-service/requirements.txt`, `.github/workflows/ci.yml` — declare CPU `torch` and move `statsmodels`; CI installs the new file — NFR5.
- [x] `ai-service/experiments/benchmark/lstm.py` — `LSTMForecaster` with train-only scaling, validation-slice early stopping, hour-1 rolling `predict`, fixed seeds — FR20, FR22.
- [x] `ai-service/experiments/benchmark/__init__.py` — register and export the LSTM.
- [x] `ai-service/tests/conftest.py` — cap LSTM epochs in a shared fixture so the suite stays fast.
- [x] `ai-service/tests/test_benchmark.py` — update the model-count and model-name assertions.
- [x] `ai-service/tests/test_benchmark_lstm.py` — cover every row of the I/O matrix.

**Acceptance Criteria:**
- Given PyTorch installed as a CPU-only build, when the benchmark runs, then an LSTM with one or two layers, a 168-hour input window and a 24-hour output is trained and scored, and appears as a row in `results.csv`.
- Given the LSTM training code, when it scales its inputs, then the scaler is fitted on the training split only.
- Given a laptop without a GPU, when the LSTM trains, then it finishes within 15 minutes, with early stopping on a validation slice taken from the training split.
- Given the LSTM module, when it is imported, then it can be used without starting FastAPI.

## Implementation Notes

- Validation slice sizing: `n_val = max(192, round(0.15 * len(train_df)))`; when `len(train_df) - n_val < 192` a full validation window cannot be held out, so `n_val` is set to 0 and every row is used (early stopping is skipped with a logged warning). With the real 14,016-row split that is 2,102 rows; the scaler is fitted on the remaining 11,914 rows that precede it, and `train_window_used` reports those 11,914.
- `_train_network` reads `LSTM_MAX_EPOCHS`/`LSTM_PATIENCE`/`LSTM_LEARNING_RATE` through the module globals (not default arguments), which is what lets `conftest.py` and the early-stopping test retune them.
- When `train_df` is between 192 and 383 rows the 15% slice is too short to build a validation window, so `n_val` becomes 0, `_val_X` stays `None`, and the loop trains on every row to the epoch cap without early stopping. The matrix's "too little history" case (fewer than 192 rows) raises before this point.
- `predict` never reads `test_df["meter_reading"]` at index `i` for the window of row `i` (window ends at `i-1`), so the one-step-ahead property holds for every row including the first.
- Hour-1 inverse-scaling uses `scale_[_TARGET_INDEX]`/`mean_[_TARGET_INDEX]` (the meter_reading channel, derived from `LSTM_FEATURES`) rather than `inverse_transform`, which would need a 2-column array.
- No `run_benchmark` execution was performed by the agent; the two owner-run commands are listed under Verification.

## Spec Change Log

## Review Triage Log

- **2026-10-10, iteration 0 (4-layer adversarial: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor):** 0 decision-needed, 10 patch, 0 defer, 11 rejected. The human chose *Apply every patch*; all 10 were applied and `pytest tests/test_benchmark_lstm.py tests/test_benchmark.py` was re-run green. Three of the patches change behaviour a later story consumes: `model_file_size_bytes` for `lstm` now measures the model (~73 KB) instead of the 2.75 MB of cached validation tensors (P1); `train_window_hours` for `lstm` now reports the fitted 11,914 rows instead of the full 14,016 (P7); the LSTM fit now logs each epoch's validation loss (P9). `results.csv` on disk still holds the pre-patch size and window columns and must be regenerated by the project owner before Story 4.4 reads it.

## Design Notes

- **Hour-1 scoring (decided with the human, 2026-10-10):** the network still learns the full 24-hour output the epic asks for, but the benchmark row reports output index 0 rolled through the test span. That gives the LSTM the same information as XGBoost (`lag_1h`) and SARIMAX (one-step roll), which Story 4.2's review showed is required for a comparable row. The other 23 outputs are trained but not scored here.
- **Separate requirements file (decided with the human):** the benchmark package already needs `statsmodels` at import and now `torch`; neither is used by the served API, so both live in `requirements-experiments.txt`. NFR5's "CPU-only builds in Docker images" applies if a later story serves the LSTM.
- **Own module:** keeping `torch` out of `models.py` keeps the heavy import in one place and makes AD-1's "importable without FastAPI" directly testable.
- **Architecture (agent's call):** one layer, hidden size 64, batch 128, Adam at `1e-3`, 15% validation slice, epoch cap 50 with patience 8. One layer is the smallest network that still learns a weekly input window and a daily output head; everything is a module constant so it can be raised without touching the code path.
- **Features (agent's call):** `meter_reading` and `air_temperature` only. Hour-of-day encodings would have to be justified on a validation slice of the *real* dataset, which the Epic 4 working agreement puts out of the agent's hands, so the two minimum channels stand.
- **Determinism on CPU:** seed `torch` at the top of `fit`, turn on `torch.use_deterministic_algorithms(True)` and pin the thread count with `torch.set_num_threads`, so two runs give identical metrics. Threads stay above 1 because a single thread would blow the 15-minute budget. (The global NumPy seed was dropped in review: nothing in the fit draws from NumPy's RNG.)
- **`torch==2.10.0+cpu` pin:** `--extra-index-url` alone does not guarantee a CPU wheel (PyPI serves the CUDA build on Linux), so the pin keeps the frozen "no CUDA wheels" rule true.
- **Test cost:** existing tests score the whole registry several times; an uncapped LSTM fit in each would dominate the suite. One shared fixture that lowers `LSTM_MAX_EPOCHS` keeps them fast while `test_benchmark_lstm.py` exercises real early stopping on its own.
- **`train_window_hours` for the LSTM (revised in review):** set to the rows the scaler and weights are actually fitted on (the split minus the validation slice), matching `BaseForecaster.train_window_used`'s documented meaning and the SARIMAX row. The full split is 14,016 rows; the fitted window is 11,914.
- **Picklability (agent's call):** `score_model` measures artifact size with `joblib.dump(model)`, so the fitted network stays a plain `nn.Module` attribute on the forecaster — no closures, lambdas or open handles stored on the instance.
- **Constants read at call time (agent's call):** `fit` reads `LSTM_MAX_EPOCHS`/`LSTM_PATIENCE` through the module globals so the shared conftest fixture can lower the caps for the rest of the suite.

## Verification

Per the Epic 4 working agreement in `epics.md`, the agent does not run commands that train a model on the real dataset: it prints the two `run_benchmark` commands below for the project owner to run, and uses the reported output. The `pytest` runs train only on the 1,708-row fixture.

**Commands:**
- `pip install -r ai-service/requirements.txt -r ai-service/requirements-experiments.txt` — expected: CPU `torch` (`torch.cuda.is_available()` is `False`) and `statsmodels` installed.
- `cd ai-service && python -m experiments.benchmark.run_benchmark` — expected: 4 rows including `lstm`, all columns finite, `lstm` `training_time_s` < 900. *(project owner runs this)*
- `pytest ai-service/tests/test_benchmark.py ai-service/tests/test_benchmark_lstm.py -q` — expected: all pass.
- Run the benchmark twice and compare the accuracy columns of `results.csv` — expected: identical. *(project owner runs this)*
- `python -c "import experiments.benchmark.lstm"` from `ai-service/` — expected: imports without starting FastAPI.

## Code Review Findings — 2026-10-10 (4-layer adversarial: blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor)

Diff reviewed: uncommitted changes against HEAD `bf61491` (= `baseline_commit`), excluding `epics.md`. Evidence: `pytest tests/test_benchmark_lstm.py tests/test_benchmark.py` → 22 passed in 177 s. The project owner ran `python -m experiments.benchmark.run_benchmark` twice on the real dataset (02:48 and 02:52): `lstm` MAE 79.46 / RMSE 115.06 / MAPE 19.53% / R² 0.9479, `training_time_s` 110.1 and 97.9, and all four accuracy columns of all four models identical across the two runs. The time-budget, determinism and "LSTM scored" matrix rows are therefore met.

**Patch (10) — all applied 2026-10-10:**
- [x] [Review][Patch] `model_file_size_bytes` for `lstm` mostly measures cached validation tensors: `score_model` pickles the whole forecaster, `_val_X`/`_val_y` are about 2.75 MB on the real split, and the network is about 18.7k parameters (~73 KB), so the reported 2.83 MB overstates the model roughly 30-fold in the column Story 4.4 compares. Exclude the validation arrays from the pickled state. [ai-service/experiments/benchmark/lstm.py]
- [x] [Review][Patch] The documented local install no longer supports the test suite: `statsmodels` left `requirements.txt`, but `package.json` (`install:all`, `install:ai`) and `README.md` still install only that file, and the autouse `fast_lstm_epochs` fixture imports `experiments.benchmark.lstm` (torch, statsmodels) for every test in `ai-service/tests`, including the API tests. Install both requirement files in the scripts and README, and make the fixture a no-op when the benchmark extras are absent. [package.json, README.md, ai-service/tests/conftest.py]
- [x] [Review][Patch] No test pins the hour-1 selection or the inverse scaling in `predict`: returning output index 23, skipping the inverse transform or using the temperature channel's statistics leaves every test green. Assert predictions equal the hand-computed `net(window)[:, 0] * scale_[0] + mean_[0]`. [ai-service/tests/test_benchmark_lstm.py]
- [x] [Review][Patch] `_history` is checked by shape only: taking the head of the training split, or the rows before the validation slice, passes every test. Assert it equals the scaled last 168 training rows. [ai-service/tests/test_benchmark_lstm.py]
- [x] [Review][Patch] "Keeps the best-validation weights" is unobservable: the early-stopping test uses a learning rate of 0, so best and last weights are identical and deleting `load_state_dict(best_state)` still passes. Add a case where validation loss worsens and assert the restored network's validation loss equals `_best_val_loss`. [ai-service/tests/test_benchmark_lstm.py]
- [x] [Review][Patch] For 193–383 training rows `n_val` is 1–191: too short to build a validation window, so early stopping is silently skipped, yet those tail rows are also excluded from the scaler and the training windows. Use all rows when a full slice cannot be held out, and test the 191/192-row boundary. [ai-service/experiments/benchmark/lstm.py, ai-service/tests/test_benchmark_lstm.py]
- [x] [Review][Patch] `train_window_hours` for `lstm` reports the full training count (14,016) although the scaler and weights are fitted on the rows before the validation slice (11,914); `BaseForecaster.train_window_used` is documented as the rows actually fitted on. Set it in `fit`. [ai-service/experiments/benchmark/lstm.py]
- [x] [Review][Patch] `fit` hygiene: `_best_val_loss`, `_val_X` and `_val_y` are not reset, so a second `fit` on the same instance can keep last-epoch weights; `np.random.seed` resets the global NumPy RNG although nothing here draws from it; `scaled[:, 0]` and `scale_[0]` hard-code the position of `meter_reading`. Reset per-fit state, drop the NumPy seed, derive the target index from `LSTM_FEATURES`. [ai-service/experiments/benchmark/lstm.py]
- [x] [Review][Patch] The fit is silent and its one comment is unfounded: `logger` is never used, so a two-minute real-data fit prints nothing, and the `LSTM_NUM_THREADS` comment (with a stray `ponytail:` token) claims a thread-count measurement that was not made. Log each epoch's validation loss and the stopping outcome; replace the comment with the measured 98–110 s. [ai-service/experiments/benchmark/lstm.py]
- [x] [Review][Patch] Three weak assertions: the scaler-isolation test never perturbs the validation rows and hard-codes `0.15`; `assert not torch.cuda.is_available()` tests the machine instead of the model's device; the summary-table test does not look for the `lstm` line. [ai-service/tests/test_benchmark_lstm.py, ai-service/tests/test_benchmark.py]

**Rejected (11):**
- (false) Time budget, determinism and real-dataset scoring are unverified: the owner's two runs above supply the evidence.
- (reject — by design in the frozen block) The newest 15% of the training split never updates the weights (no refit after early stopping), validation windows spend their first 168 rows as context, and the checkpoint is selected on the 24-output mean while hour 1 is scored: all follow from "hold out the last part of the training split … 24-value output". Revisit in Story 4.5, which tunes the LSTM.
- (low) No guards for NaN inputs, an empty `test_df`, a non-contiguous test frame or a very large single inference batch: none is reachable through the harness on the gap-free dataset; each fix adds a guard.
- (low) `torch.use_deterministic_algorithms(True)` and `set_num_threads` are process-wide and not restored: no other torch code runs in the process; restoring them adds a try/finally for no observed harm.
- (low) `LSTM_NUM_THREADS = 4` may oversubscribe a 2-core runner: changing it per machine would trade away the fixed setting the determinism claim rests on.
- (low) `torch==2.10.0+cpu` has no macOS wheel: the owner's machine is Windows and CI is Linux; adding platform markers is more than a direct correction. Revisit if a teammate develops on macOS.
- (low) CI lints `src` only, and `COPY . .` ships `experiments/` into the image without its libraries: pre-existing since Story 4.1, and the frozen rule (no experiment-only libraries in the image) holds.
- (low) Suite runtime (177 s for the two benchmark test files) because most tests score the whole registry: a shared module-scoped results fixture is more than a direct correction, but is worth doing before Story 4.5 adds tuning tests.
- (false) `test_lstm_determinism` compares two fits in one process rather than two benchmark runs: the owner's two runs cover the cross-process case.
- (reject — reconciled at close) Spec `in-review` versus sprint `4-3: in-progress`.
- (reject — out of scope) `sprint-status.yaml` also carries the `4-13` line and `epics.md` carries FR46–FR48 from the 2026-10-10 planning session; they are committed separately from Story 4.3.
