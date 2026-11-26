---
title: 'Story 4.5: Track training runs and register the serving model'
type: 'feature'
created: '2026-10-29'
status: 'done'
baseline_commit: 'ddd37ae'
route: 'dispatch'
review_loop_iteration: 0
story_keys:
  - 4-5-track-training-runs-and-register-the-serving-model
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 4.1–4.4 built a four-model benchmark that proves *which* forecaster to serve, but the serving path is still untracked and unversioned. `train_models.py` fits XGBoost + Isolation Forest and `joblib.dump`s them to `models_saved/` with a hand-written `model_metadata.json`; there is no record of which parameters produced the served model, no experiment lineage, and no automated hyperparameter search — the XGBoost/LSTM hyperparameters are hand-picked. FR23 asks that training runs log parameters, metrics and artifacts to a local MLflow store and that the serving model be registered under a `champion` alias. FR47 asks that the XGBoost and LSTM hyperparameters be selected by an automated Optuna search, with every trial logged to MLflow and scored only on the training split.

**Approach:** Three separable pieces, all plain Python runnable without FastAPI (AD-1), none of which the agent executes (Epic 4 working agreement — commands are printed, the owner runs them).

1. **MLflow tracking + registry (`ai-service/src/mlops/tracking.py`).** A thin wrapper that configures a **local, repo-relative** MLflow store and gives `train_models.py` three hooks: start a run, log params/metrics/feature-list/row-counts, and log + register the model artifact. On a completed training run the model version receives the `champion` alias **only if no champion exists yet** (first-champion bootstrap; promoting a *better* model over an existing champion is Story 4.8's job, out of scope here).

2. **Optuna hyperparameter search (`ai-service/src/mlops/hpo.py` + `experiments/benchmark` hook).** One command runs an Optuna study per model (XGBoost, LSTM) over a **documented search space**, with the **same completed-trial count** per model, each trial scored on **time-ordered validation slices cut from the training split only** (never the test split). Every trial is logged to MLflow as a run **nested** under that model's parent search run. The best parameters feed back into the benchmark so tuned-vs-untuned rows can be compared.

3. **Champion-aware serving load (`serving_frame.py`).** At startup the AI service resolves the forecast model through the `champion` alias; when MLflow is not initialised it falls back to `models_saved/` with a logged warning, but when the alias resolves to a **broken** artifact it fails loud rather than masking it.

**Decisions locked with the product owner (2026-10-28 / 2026-10-29):**
- **MLflow store is repo-relative + Docker-mounted.** SQLite backend at `ai-service/mlruns/mlflow.db`, artifact root under `ai-service/mlruns/`, both read from configuration as **relative paths** (never an absolute machine-specific path), and the directory is mounted into the AI service container through a Docker volume so the owner's training runs and the running container see the same store. (Chosen over an absolute local path, and over "MLflow for tracking only, serving always from `models_saved/`".)
- **Champion-load failure is tri-state, not binary.** MLflow not initialised (no store / no `champion` alias) → fall back to `models_saved/` with a logged warning and serve normally. Alias resolves but its artifact is missing/corrupt, or the SQLite backend is locked → **do not** silently fall back; surface the same explicit `503 ERR_MODEL_NOT_FOUND` used in Epic 1 Story 1.5, naming the champion version that failed to load. (Chosen over "always fall back" and "always fail loud".)
- **Registration scope — forecaster only (decided 2026-10-29).** Although `train_models.py` trains both the XGBoost forecaster and the Isolation Forest, this story tracks + `champion`-registers **only the XGBoost forecaster**. The Isolation Forest keeps loading from `models_saved/` as today; Story 4.7 opens its own detector MLflow run separately. (Chosen over "track both" and "alias both".)
- **Champion model — XGBoost is the served forecaster (decided 2026-10-29).** `train_models.py` produces XGBoost and it becomes the `champion`. Story 4.4's benchmark recommendation is **advisory text only**; swapping the served forecaster architecture is out of scope for Epic 4, consistent with Stories 1.4 and 4.13 which assume XGBoost. (Chosen over "champion follows the 4.4 recommendation".)
- **Optuna budget (approved 2026-10-29).** Same **completed**-trial count per model, `OPTUNA_N_TRIALS=30`. The search **objective is validation RMSE (kWh), minimized** — same unit and metric as the benchmark's headline column. Each trial has a **per-trial wall-clock cap of ~5 minutes** (default `OPTUNA_TRIAL_TIMEOUT_S=300`), enforced inside the LSTM training loop via reduced epochs + an early-stopping/elapsed-time callback (not a study-level `timeout`, which cannot stop a running trial); the XGBoost trials are far faster. The expected wall-clock is **~2.5 h/model** on CPU; the owner may run it in stages. The Optuna study is persisted in **SQLite storage separate from the MLflow backend** (`ai-service/mlruns/optuna.db`), resumable across interruptions, and the **TPESampler seed is fixed** so the chosen best-parameters are reproducible, consistent with Story 4.1 AC3. Pruned/failed trials are logged to MLflow but **excluded** from best-parameter selection and from the "same number of trials" count. MedianPruner uses startup/warmup trials (default `n_startup_trials=5`) before pruning begins so a noisy early CPU validation slice cannot prune a good configuration prematurely.

## Boundaries & Constraints

**Always:**
- MLflow tracking URI and artifact root come from configuration (`MLFLOW_TRACKING_URI`, default `sqlite:///mlruns/mlflow.db` resolved **relative to `ai-service/`**; artifact root relative under `ai-service/mlruns/`). No absolute, machine-specific path is ever written to the store or committed.
- A finished `train_models.py` run logs, to one MLflow run: the hyperparameters, RMSE, MAE, MAPE, R², the XGBoost feature list, the train/test row counts, and the model artifact(s). Logged metrics reconcile with what is written to `model_metadata.json` (same numbers, same split).
- The model version is registered and receives the `champion` alias **only when no champion alias currently exists**. First-champion registration is **idempotent** and guarded so a concurrent run cannot both claim the alias (set-if-absent semantics).
- The Optuna search explores a documented space for **both** XGBoost and LSTM with the **same number of completed trials**, scores every trial on **time-ordered validation slices taken from the training split only**, and **never reads the test split** at any point in the search.
- Each Optuna trial is logged to MLflow as a run **nested** under that model's parent search run, carrying its sampled parameters and its validation metric(s).
- After a search finishes, applying the best parameters and re-running the benchmark (Story 4.1 harness) produces **tuned** rows that can be compared against the existing **untuned** rows for both models.
- Optuna study persistence uses SQLite storage and a **fixed sampler seed**; re-running a completed search with the same seed and data yields the same best parameters (determinism, honoring Story 4.1 AC3). Timing is exempt from determinism.
- At AI-service startup, the forecast model is loaded **behind the `champion` alias** when MLflow is initialised; otherwise it falls back to `models_saved/` with a logged warning and serves normally.
- When the `champion` alias resolves but its artifact is missing/corrupt or the SQLite backend is locked, the service raises the Epic 1 Story 1.5 error envelope `{"detail": ..., "code": "ERR_MODEL_NOT_FOUND"}` at `503`, naming the champion version it failed to load — it does **not** fall back to `models_saved/`.
- New code lives under `ai-service/src/mlops/` (tracking, hpo, config) and stays importable/callable as plain Python without starting FastAPI (AD-1). UTF-8 console output on Windows (reuse the existing `reconfigure` guard).
- `mlflow` is added to the **served** `ai-service/requirements.txt` (the running service resolves the champion at startup); `optuna` is added to `ai-service/requirements-experiments.txt` only (the search is an offline experiment).
- The MLflow store directory (`ai-service/mlruns/`) and any generated artifacts are git-ignored; the store is a runtime/dev artifact, not source.
- Every new module ships pytest coverage for its own scope; tests run without the real BDG2 files (committed fixtures), and the champion-load tests use a temporary MLflow store, never the real one.

**Never:**
- Do not let any Optuna trial, validation slice, or search metric read the chronological **test split**; the test partition is reserved for the benchmark's final scoring.
- Do not promote a model over an **existing** champion here — guarded promotion/challenger comparison is Story 4.8. This story only bootstraps the first champion.
- Do not change the existing response shape of `GET /internal/forecast/predict` or the serving metrics/anomaly contracts; this story changes *where the model is loaded from*, not the API.
- Do not break the no-MLflow path: with no store present, `train_models.py` and the service must still work (train → `models_saved/`, serve from `models_saved/`), so the team can run without MLflow in dev/CI.
- Do not write an absolute path into the MLflow store or commit the `mlruns/` contents; the store must stay portable between the owner's host and the Docker container.
- Do not run any training, search, or benchmark command from the agent — print the exact command and working directory for the owner to run (Epic 4 working agreement).
- Do not add `optuna` to the served `requirements.txt`, and do not pull heavy search dependencies into the Docker serving image.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path — tracked training | MLflow store present, `train_models.py` run | One MLflow run with params + RMSE/MAE/MAPE/R² + feature list + row counts + artifact; metrics match `model_metadata.json` | N/A |
| First champion bootstrap | No `champion` alias exists | Registered version gets the `champion` alias | N/A |
| Champion already exists | A `champion` alias is set | New version registered but alias **unchanged**; promotion deferred to 4.8 | No error; logged note |
| Concurrent first-champion | Two runs register with no champion | Exactly one wins the alias (set-if-absent); the other sees champion exists | Race guarded, no crash |
| Optuna search | XGBoost + LSTM, `OPTUNA_N_TRIALS=30` | Two studies, 30 completed trials each, each trial a nested MLflow run; best params returned | N/A |
| Trial pruned/timed out | A trial crosses the per-trial cap or MedianPruner cut | Trial logged to MLflow as PRUNED/FAIL, excluded from best-param selection and the completed-trial count | Caught, not fatal |
| Search determinism | Same seed + data, run twice | Identical best parameters per model | N/A |
| Test-split guard | Search validation slicing | All slices come from the training split; test split untouched | Assertion/guard in slicer |
| Serve — champion present | MLflow init, alias resolves, artifact OK | Service loads the champion version | N/A |
| Serve — MLflow not initialised | No store / no `champion` alias | Falls back to `models_saved/` with a logged warning; serves normally | Warning, not error |
| Serve — champion broken | Alias resolves but artifact missing/corrupt or DB locked | `503 ERR_MODEL_NOT_FOUND` naming the champion version; **no** fallback | Error surfaced, not masked |
| No-MLflow dev/CI | No store, no `mlflow` config | `train_models.py` → `models_saved/`; service serves from `models_saved/`; tests green | N/A |
| Store portability | Store created on host, read in container | Same relative paths resolve inside the Docker volume mount | N/A |

</frozen-after-approval>

## Code Map

- `ai-service/src/models/train_models.py` — reuse + extend (do not break the no-MLflow path): `run_pipeline` / `save_trained_models` (lines 256–283) currently `joblib.dump` to `models_saved/` and write `model_metadata.json`. **Add** an MLflow logging hook around the fit so the same run records params + RMSE/MAE/MAPE/R² + `XGB_FEATURE_COLUMNS` + train/test row counts + artifact, then registers the version and bootstraps the `champion` alias. Keep `models_saved/` writing intact as the fallback source of truth. Reuse `engineer_features` / `split_time_series_data`.
- `ai-service/src/mlops/__init__.py` *(new)* — package marker; importable without FastAPI.
- `ai-service/src/mlops/config.py` *(new)* — reads `MLFLOW_TRACKING_URI`/artifact root from env with the repo-relative defaults; exposes an `is_mlflow_initialised()` check and the registered model name + `champion` alias constant.
- `ai-service/src/mlops/tracking.py` *(new)* — thin MLflow wrapper: `start_run`, `log_training(params, metrics, features, row_counts, artifact)`, `register_and_bootstrap_champion(run, version)` with **set-if-absent** alias semantics (no promotion), and `load_champion_forecaster()` returning the champion model or raising the tri-state result (fallback-signal vs. `ModelArtifactError`).
- `ai-service/src/mlops/hpo.py` *(new)* — Optuna study per model: documented search spaces for XGBoost and LSTM, a **training-split-only** time-ordered validation slicer, MedianPruner + per-trial wall-clock cap, SQLite study storage, fixed TPESampler seed, and per-trial MLflow nested-run logging. Returns best params per model; no CLI logic.
- `ai-service/src/mlops/run_hpo.py` *(new)* — `__main__` CLI (`--model {xgboost,lstm,both}`, `--n-trials`, `--study-storage`); runs the search(es), logs to MLflow, prints the best params and the exact benchmark command to re-run with them.
- `ai-service/src/data_pipeline/serving_frame.py` — `_load_artifacts_and_base_frame` (lines 61–93) loads `xgboost_forecaster.joblib` from `models_dir`. **Add** a champion-first load path via `mlops.tracking.load_champion_forecaster()`: use the champion when MLflow is initialised; fall back to the existing `models_dir` load with a logged warning when it is not; raise `ModelArtifactError` (→ `503 ERR_MODEL_NOT_FOUND`) when the alias resolves but the artifact is broken. Keep the existing `ModelArtifactError`/`ServingDataError` behavior for the plain `models_saved/` path.
- `ai-service/src/main.py` — health check at line 101 (`xgboost_forecaster.joblib` existence) extended to also report whether a `champion` is resolvable, feeding Story 2.3 / Story 4.10 status.
- `ai-service/experiments/benchmark/models.py` / `lstm.py` — `XGBoostForecaster.__init__(random_state=42)` and `LSTMForecaster.__init__()` currently take no hyperparameters; both self-register via `@register_forecaster`. To produce tuned-vs-untuned rows, the benchmark must be able to construct these with the best params the search found. Minimal reuse: have `hpo.py` accept/emit a params dict and a thin way to apply it (constructor kwargs or a `set_params`), without changing the existing `fit`/`predict`/registry contracts used by Stories 4.1–4.4. The benchmark harness itself is otherwise read-only here.
- `ai-service/requirements.txt` — add `mlflow` (served; champion resolution at startup).
- `ai-service/requirements-experiments.txt` — add `optuna` (offline search only).
- `ai-service/.gitignore` (or repo root) — ignore `ai-service/mlruns/`.
- `ai-service/tests/test_mlops_tracking.py` *(new)* — tracking + champion bootstrap/idempotency/concurrency against a temp MLflow store.
- `ai-service/tests/test_mlops_hpo.py` *(new)* — search runs a tiny trial budget on a fixture, asserts test-split is never read, pruned trials excluded, determinism under a fixed seed.
- `ai-service/tests/test_serving_champion_load.py` *(new)* — the three serving states: champion OK, MLflow-not-init fallback+warning, broken-champion `ERR_MODEL_NOT_FOUND`.

## Tasks & Acceptance

**Execution:**
- [x] `mlops/config.py` + `mlops/__init__.py`: repo-relative MLflow config, `is_mlflow_initialised()`, champion alias constant — FR23.
- [x] `mlops/tracking.py`: run logging, set-if-absent champion bootstrap, tri-state champion load — FR23.
- [x] Wire MLflow logging + champion bootstrap into `train_models.py` without breaking the `models_saved/` path — FR23.
- [x] `mlops/hpo.py` + `run_hpo.py`: Optuna per model, training-split-only slicer, pruner + per-trial cap, SQLite study, fixed seed, nested MLflow runs — FR47.
- [x] Champion-first load in `serving_frame.py` with the tri-state fallback/fail-loud behavior — FR23.
- [x] `requirements.txt` (`mlflow`) + `requirements-experiments.txt` (`optuna`) + gitignore `mlruns/`.
- [x] Tests: `test_mlops_tracking.py`, `test_mlops_hpo.py`, `test_serving_champion_load.py` covering the I/O matrix.

**Acceptance Criteria (from epics.md Story 4.5 — FR23, FR47):**
- Given the XGBoost and LSTM forecasters, when the hyperparameter search runs, then Optuna explores a documented search space for each with the same number of trials, scores every trial on time-ordered validation slices cut from the training split, and never reads the test split.
- Given a search in progress, when a trial finishes, then its parameters and validation metrics are logged to MLflow as a run nested under that model's search.
- Given a finished search, when the best parameters are applied, then the benchmark is re-run with them and the tuned and untuned rows can be compared for both models.
- Given MLflow configured with a repo-relative SQLite backend (mounted into the container via Docker volume), when `train_models.py` runs, then the run logs hyperparameters, RMSE, MAE, MAPE, R², the feature list, the data row counts and the model artifacts, read from relative paths.
- Given a completed training run, when it is registered, then the model version receives the `champion` alias only if no champion exists yet; first-champion registration is idempotent and race-guarded.
- Given the AI service starts and MLflow is not initialised, when it loads the forecast model, then it falls back to `models_saved/` with a logged warning and serves normally.
- Given the AI service starts and the `champion` alias resolves but its artifact is missing/corrupt or the backend is locked, when it loads the forecast model, then it surfaces `503 ERR_MODEL_NOT_FOUND` naming the champion version and does not silently fall back.

## Verification

**Commands (run from `ai-service/` — owner runs these; the agent only prints them, per the Epic 4 working agreement):**
- `python -m src.models.train_models` — writes `models_saved/` artifacts **and** logs one MLflow run; registers + bootstraps the `champion` alias on first run.
- `python -m src.mlops.run_hpo --model both --n-trials 30` — runs both Optuna studies, logs nested trial runs to MLflow, prints best params + the benchmark re-run command.
- `python -m experiments.benchmark.run_benchmark` (with best params applied) — produces tuned rows to compare against the untuned `results.csv`.
- `pytest tests/test_mlops_tracking.py tests/test_mlops_hpo.py tests/test_serving_champion_load.py -q` — champion bootstrap/idempotency/concurrency; search test-split guard, pruned-trial exclusion, seed determinism; three serving-load states.
- Determinism spot-check: run `run_hpo` twice with the same seed and diff the best params — expected identical.

> Theo quy ước Epic 4, mọi lệnh train/search/benchmark ở trên do người dùng tự chạy; spec chỉ in lệnh, agent không tự thực thi.

## Spec Change Log

- 2026-10-29 — Story file created from `epics.md` Story 4.5 (FR23, FR47). Folded in two product-owner decisions captured during story creation: (1) MLflow store is repo-relative (`ai-service/mlruns/mlflow.db`) + Docker-volume-mounted; (2) champion-load failure is tri-state (not-init → fallback+warning; broken alias → `ERR_MODEL_NOT_FOUND`). Optuna budget defaults (30 completed trials/model, per-trial cap, MedianPruner, SQLite resumable study, fixed seed) set provisionally and flagged in Open Questions. Status `backlog` → `draft`.
- 2026-10-29 — Optuna budget APPROVED by product owner: 30 completed trials/model + per-trial wall-clock cap + MedianPruner (with warmup) + resumable SQLite study at `ai-service/mlruns/optuna.db` (separate from `mlflow.db`) + fixed TPESampler seed.
- 2026-10-29 — Final Optuna details locked: objective = validation RMSE (kWh, minimized); per-trial cap ~5 min (`OPTUNA_TRIAL_TIMEOUT_S=300`, enforced inside the LSTM loop, not a study-level timeout); `n_startup_trials=5` for the pruner; expected ~2.5 h/model on CPU.
- 2026-10-29 (bmad-build step-01, architect pass) — Two implementation-mechanism decisions locked with the owner before coding: (1) **First-champion race** is guarded by a **filesystem lock** (`filelock`) wrapping the check-alias → register → set-alias critical section, lock file at `ai-service/mlruns/.champion.lock` (shared across host↔container via the same mount), since MLflow+SQLite offers no atomic compare-and-set for aliases. (2) **Store portability** uses a **relative `artifact_location`** (`./mlruns/...`) plus the discipline of running every MLflow command with CWD = `ai-service/`; no absolute artifact URI is written to the store. `filelock` to be added alongside `mlflow` in the served `requirements.txt`.
- 2026-10-29 (bmad-build step-04, review) — Three review layers (blind-hunter, edge-case-hunter, verification-gap) ran against the baseline diff. Triage recorded in `## Review Triage Log`. No intent_gap / bad_spec (no loopback); 5 entries routed to `patch`, the rest rejected as `false`/`low`. Key patch: `run_study` must guarantee N **completed** trials per model (I/O-matrix "30 completed trials each") and tolerate failed trials.
- 2026-10-29 (bmad-build step-02) — Investigation surfaced two intent gaps; product owner resolved both: (1) registration scope = **forecaster only** (Isolation Forest stays on `models_saved/`, Story 4.7 opens its own detector run); (2) champion = the **XGBoost** from `train_models.py`, with Story 4.4's recommendation advisory only. Both folded into the frozen block. Token gate: spec ≈5k tokens (>1600); owner chose to **keep the full single story** (consistent with the epic grouping and the Story 4.4 precedent). Open Questions section emptied and removed — spec ready for the step-02 checkpoint.

## Review Triage Log

Iteration 0 (2026-10-29). Verdicts rendered against the actual tree; grouped by root cause; routed per cascade (no intent_gap/bad_spec ⇒ no loopback).

| # | Finding (layer) | Verdict | Route | Evidence |
|---|-----------------|---------|-------|----------|
| G1 | `run_study` `n_trials` counts TOTAL trials, so with MedianPruner active completed count <N and differs per model (edge-case) | medium | patch | Contradicts the I/O-matrix row "Two studies, 30 **completed** trials each"; the covering test masks it by setting `n_startup_trials==n_trials`. Must guarantee N completed. |
| G2 | `study.optimize(..., catch=())` aborts the whole study on any non-`TrialPruned` exception; docstring/spec claim "failed trials excluded from the count" (blind-hunter) | medium | patch | `catch=()` ⇒ one failing trial raises out of `run_study`; no `n_failed`. Spec Intent says pruned/failed excluded, not fatal. Same root area as G1. |
| G3 | Zero completed trials ⇒ `study.best_params`/`best_value` raise "No trials are completed" uncaught (edge-case) | medium | patch | Reachable when all trials pruned/failed (e.g. LSTM small-data). Same root area as G1/G2 — guard needed. |
| G4 | `resolve_champion_version()` (health) ignores `ECOTRACK_DISABLE_MLFLOW`, unlike serving/training (verification-gap "other"; blind #3; edge #7) | medium | patch | On a host with a real store, `/health?details=true` reports a resolved champion while serving uses `models_saved/`; and `forecast:"loaded"` can show while serving 503s. Fix: honor the disable flag in the health resolver. |
| G5 | No test for `/health?details=true` champion fields + `forecast` logic (verification-gap, pre-verified) | medium | patch | AI tests only hit `details=False`; backend test mocks the old payload. Regression in detailed-health contract ships undetected. |
| G6 | `run_pipeline` MLflow/registration block never executed by any test (verification-gap, pre-verified) | medium | patch | `grep run_pipeline tests/` empty; block wrapped in `except Exception`→warn. FR23 deliverable can break invisibly. |
| G7 | Tuned-benchmark path (`build_tuned_models`, `XGBoostForecaster.set_params`) untested (verification-gap, pre-verified) | medium | patch | Breaking the per-model lookup/merge silently yields untuned numbers labeled "tuned". `set_params` for XGB covered nowhere. |
| R1 | Docker volume mount for `mlruns` missing from diff (blind-hunter) | false | reject | `docker-compose.yml` already bind-mounts `./ai-service:/app`, so `ai-service/mlruns` is visible in the container; relative `artifact_location` + CWD=/app satisfies portability. No separate mount needed. |
| R2 | Per-trial wall-clock cap only for LSTM, not XGBoost (blind-hunter) | false | reject | Spec Decisions: cap enforced "inside the LSTM training loop … the XGBoost trials are far faster." LSTM-only cap is per-spec. |
| R3 | mlflow + filelock added to served `requirements.txt` (blind-hunter) | false | reject | Spec "Always": `mlflow` added to the served requirements (champion resolved at startup). filelock is tiny; its placement is a change-log decision. |
| R4 | `_mlflow_disabled` duplicated / rejects spellings like `TRUE`,`yes` (blind-hunter) | low | reject | Owner sets `1`; negligible harm; G4 already consolidates the resolver onto one shared check. |
| R5 | `_is_not_found` uses English substring matching (blind-hunter) | low | reject | `error_code == RESOURCE_DOES_NOT_EXIST` is the primary path; substring is a fallback. Works on the pinned MLflow; fix is speculative. |
| R6 | `configure()` creates the experiment as a side-effect of read paths (blind-hunter) | low | reject | Only on the first call before any training; `create_experiment` is idempotent thereafter; benign. |
| R7 | `XGBoostForecaster.__init__(params=…)` with `random_state` double-passes the kwarg (edge-case) | low | reject | Unreachable in practice: Optuna space has no `random_state`; `build_tuned_models` uses `set_params` (which pops it), not constructor `params=`. |
| R8 | LSTM `batch_size=0`/negative ⇒ `range(...,0)` ValueError (edge-case) | low | reject | Search space is categorical `[64,128,256]`; never 0. Unreachable within the search. |
| R9 | `set_time_budget(0)` ⇒ net left untrained (edge-case) | low | reject | `per_fold_budget = max(1.0, timeout/folds)` ≥ 1.0; never 0 within the search. |
| R10 | `build_tuned_models` crashes on malformed/non-dict `best_params.json` (edge-case) | low | reject | File is produced by `run_hpo`; a hand-corrupted file failing loudly with a traceback is tolerable, and the fix adds guards. |
| R11 | `torch` ImportError aborts an LSTM study under `catch=()` (edge-case, low-conf) | low | reject | `torch` ships in `requirements-experiments.txt` alongside `optuna`; if you run the search it is installed. Resilience subsumed by G2. |

## Review Findings (code-review 2026-10-31)

Second review pass (bmad-code-review) over `git diff ddd37ae...HEAD` with four parallel layers (blind-hunter, edge-case-hunter, verification-gap, acceptance-auditor). Owner-prioritised focus: test-split leakage guard. Verdicts rendered against the live tree.

### decision-needed (resolved 2026-10-31 → applied as patch)

- [x] [Review][Decision→Patch] Health reports `forecast="loaded"` / `champion="resolved"` while serving 503s on a broken champion. **Owner decision: health loads the champion artifact on every probe (no cache).** Applied: new `champion_health()` loads via `load_champion_forecaster()` and reports `resolved`/`broken`/`unavailable`; `/health?details=true` now maps `broken`→`forecast="unavailable"`. [ai-service/src/main.py] [ai-service/src/mlops/tracking.py]

### patch

- [x] [Review][Patch] Test-split guard uses `assert` (stripped under `python -O`/`PYTHONOPTIMIZE`) — the strongest FR47 "test split never touched" guarantee silently disappears in optimized runs; use explicit `raise` [ai-service/src/mlops/hpo.py:101]
- [x] [Review][Patch] `register_and_bootstrap_champion` catches all exceptions on the alias read and treats them as "no champion", so a transient/locked-DB read error while a champion exists overwrites it (violates set-if-absent) — distinguish not-found (→ None) from other errors (→ raise), as `load_champion_forecaster` already does [ai-service/src/mlops/tracking.py:129]
- [x] [Review][Patch] `mlflow>=2.9.0` has no upper bound; code uses `log_model(artifact_path=...)`, `register_model`, `models:/name@alias` APIs that shifted across MLflow majors — pin `<3` [ai-service/requirements.txt:10]
- [x] [Review][Patch] `best_params.json` (generated search output written to experiments/benchmark/) is not git-ignored; `.gitignore` only covers `mlruns/` [.gitignore]
- [x] [Review][Patch] `execute_benchmark` docstring omits the new `models` parameter [ai-service/experiments/benchmark/run_benchmark.py:78]
- [x] [Review][Patch] No test asserts LSTM tuned hyperparameters reach the built network (`_net.lstm.hidden_size`/`num_layers`, optimiser lr/batch) — silent no-op LSTM tuning would make tuned rows equal untuned while labeled "tuned"; mirror the XGBoost `set_params` test [ai-service/tests/test_benchmark_tuning.py]
- [x] [Review][Patch] LSTM per-trial wall-clock cap (`break` on elapsed budget) is never exercised — add a deterministic test (`set_time_budget(0)` stops at ~0 epochs) [ai-service/tests/test_mlops_hpo.py]
- [x] [Review][Patch] No serving test for an initialised store with no `champion` alias; the `_is_not_found` → `ChampionUnavailable` fallback branch is never run, so a misclassified alias-not-found would 503 the service at startup instead of falling back [ai-service/tests/test_serving_champion_load.py]

### defer

- [x] [Review][Defer] `n_jobs=-1` in the XGBoost search objective may undermine the determinism guarantee (4.1 AC3) that `test_search_is_deterministic_under_fixed_seed` asserts — maybe-false: XGBoost `hist` is generally deterministic, and the CI test is green; settle by running that test repeatedly / watching CI for flakes before pinning `n_jobs=1` [ai-service/src/mlops/hpo.py:154]
- [x] [Review][Defer] `XGBoostForecaster.DEFAULT_PARAMS` duplicates `train_models.py` hyperparameters with no equality guard — a future tweak to `train_models.py` silently makes the untuned benchmark row stop reproducing the served model; add a guard test or single-source the values [ai-service/experiments/benchmark/models.py:152]

### Rejected

- `false` — XGBoostForecaster(params={"random_state":...}) double-passes random_state → TypeError: unreachable; the Optuna space has no `random_state` and `build_tuned_models` uses `set_params` (which pops it), not constructor `params=` [models.py:162].
- `false` — LSTM `batch_size=0` → `range(...,0)` ValueError: unreachable; search space is categorical `[64,128,256]` and `best_params.json` is machine-generated [lstm.py:231].
- `low` — malformed/non-dict `best_params.json` crashes `build_tuned_models`: file is produced by `run_hpo`; a hand-corrupted file failing loudly is tolerable.
- `low` — served image uses full `mlflow` not `mlflow-skinny`: `mlflow` in served requirements is a locked spec decision; skinny omits flavor deps and the swap is risky, not a direct fix.
- `low` — tracking URI absolute while artifact root relative (and AC4 literal "relative URI"): intent (portability, no absolute path in the store) is met and the asymmetry is a locked architect decision; the only real failure needs running MLflow from a non-`ai-service/` CWD, against the documented contract.
- `low` — `configure()` side-effect (set_tracking_uri/mkdir/create_experiment) on each detailed health probe: idempotent and benign (R6 recurrence).
- `low` — no distinct test for the genuine `mlflow`-not-installed path (vs the disable-flag path): both reach the same fallback; adding a package-absent test is extra complexity for negligible risk.
- `low` — concurrency test uses threads not processes while `filelock` is cross-process: the lock library handles cross-process serialisation; a multi-process test is new complexity, not a direct fix.
- `low` — happy-path tracking test does not assert `mape_percent` is logged: production logs MAPE (train_models.py:189); coverage-only nit.
- `low` — LSTM best-params determinism not covered by the determinism test: XGBoost-only determinism test is adequate; a slow LSTM determinism test is disproportionate.
- `low` — `ECOTRACK_DISABLE_MLFLOW` only accepts `1`/`true`/`True`, not `yes`/`on`/`TRUE`: owner sets `1`; negligible (R4 recurrence).
- `low` — `run_searches` aborts and skips the `best_params.json` write if a later model has zero completed trials: the Optuna study is persisted in `optuna.db` (resumable), so completed work is not lost; the guard fix adds branches.
- `low` — spec front-matter `status: done` vs `sprint-status.yaml: review`: reconciled by this review's status sync (Step 6), not a code defect.
