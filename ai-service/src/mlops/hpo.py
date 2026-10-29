"""
Optuna hyperparameter search for EcoTrack's XGBoost and LSTM forecasters
(Story 4.5 — FR47).

Design (locked with the product owner):

* **Objective = validation RMSE (kWh), minimized** — same unit/metric as the
  benchmark's headline column.
* **Scoring data is the training split only.** :func:`make_validation_slices`
  cuts time-ordered, expanding-window ``(sub_train, val)`` folds from the
  training partition and asserts no fold ever reaches past the training split's
  last timestamp. The test split is never passed in and never read.
* **Same number of completed trials per model** (``OPTUNA_N_TRIALS``); pruned
  and failed trials are excluded from best-parameter selection and from that
  count.
* **MedianPruner** with ``n_startup_trials`` warmup so a noisy early CPU fold
  cannot prune a good configuration prematurely.
* **Per-trial wall-clock cap** (``OPTUNA_TRIAL_TIMEOUT_S``) enforced inside the
  LSTM training loop (reduced epochs + elapsed-time stop), not a study-level
  timeout which cannot stop a running trial.
* **Resumable SQLite study** (``mlruns/optuna.db``, separate from the MLflow
  backend) + **fixed TPESampler seed** so the chosen best parameters are
  reproducible (Story 4.1 AC3). Timing is exempt from determinism.
* **Every trial is logged to MLflow** as a run **nested** under that model's
  parent search run, carrying its sampled parameters and validation metric.

``optuna`` / ``mlflow`` / ``torch`` are imported lazily so importing this module
never requires the offline-search extras. No CLI logic lives here (see
``run_hpo.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error

from src.mlops.config import (
    OPTUNA_N_STARTUP_TRIALS,
    OPTUNA_N_TRIALS,
    OPTUNA_SEED,
    OPTUNA_TRIAL_TIMEOUT_S,
    mlruns_dir,
)
from src.models.train_models import XGB_FEATURE_COLUMNS

logger = logging.getLogger("MLOpsHPO")

SUPPORTED_MODELS: Tuple[str, ...] = ("xgboost", "lstm")
DEFAULT_N_VALIDATION_SLICES = 3
# During the search the LSTM is capped to far fewer epochs than the benchmark's 50 so a
# single trial stays inside the per-trial wall-clock budget; the elapsed-time stop is the
# hard cap on top of this.
DEFAULT_LSTM_SEARCH_EPOCH_CAP = 15


# --------------------------------------------------------------------------- #
# Training-split-only validation slicer (test-split guard lives here)
# --------------------------------------------------------------------------- #
def make_validation_slices(
    train_df: pd.DataFrame, n_slices: int = DEFAULT_N_VALIDATION_SLICES
) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Expanding-window, time-ordered ``(sub_train, val)`` folds cut from the
    **training split only**. Fold *i* trains on ``train[:i*block]`` and validates
    on the following block; the last fold's validation block runs to the end of
    the training split.

    Guard: asserts every fold (train and validation alike) stays within the
    training split's timestamp range, so the chronological test split is provably
    never touched by the search.
    """
    n = len(train_df)
    if n < 2:
        raise ValueError(f"train_df too small for validation slicing: {n} rows")

    if n < (n_slices + 1) * 2:
        cut = max(1, int(n * 0.8))
        raw_slices = [(train_df.iloc[:cut], train_df.iloc[cut:])]
    else:
        block = n // (n_slices + 1)
        raw_slices = []
        for i in range(1, n_slices + 1):
            sub_train = train_df.iloc[: i * block]
            val = train_df.iloc[i * block : (i + 1) * block] if i < n_slices else train_df.iloc[i * block :]
            raw_slices.append((sub_train, val))

    slices = [
        (tr.reset_index(drop=True), va.reset_index(drop=True))
        for tr, va in raw_slices
        if len(va) > 0 and len(tr) > 0
    ]

    # Test-split guard: nothing in any fold may reach past the training split.
    train_max_ts = pd.to_datetime(train_df["timestamp"]).max()
    for tr, va in slices:
        assert pd.to_datetime(tr["timestamp"]).max() <= train_max_ts, "sub-train leaked past training split"
        assert pd.to_datetime(va["timestamp"]).max() <= train_max_ts, "validation slice leaked past training split"
    if not slices:
        raise ValueError("No usable validation slices could be built from the training split")
    return slices


# --------------------------------------------------------------------------- #
# Documented search spaces
# --------------------------------------------------------------------------- #
def xgboost_search_space(trial: Any) -> Dict[str, Any]:
    """Documented XGBoost search space (regularised gradient boosting)."""
    return {
        "n_estimators": trial.suggest_int("n_estimators", 100, 600, step=50),
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
    }


def lstm_search_space(trial: Any) -> Dict[str, Any]:
    """Documented LSTM search space (architecture + optimisation; windows stay fixed)."""
    return {
        "hidden_size": trial.suggest_categorical("hidden_size", [32, 64, 96, 128]),
        "num_layers": trial.suggest_int("num_layers", 1, 2),
        "learning_rate": trial.suggest_float("learning_rate", 1e-4, 1e-2, log=True),
        "batch_size": trial.suggest_categorical("batch_size", [64, 128, 256]),
    }


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


# --------------------------------------------------------------------------- #
# Per-model fold scoring (reports intermediate values so the pruner can act)
# --------------------------------------------------------------------------- #
def _score_xgboost(
    params: Dict[str, Any],
    slices: List[Tuple[pd.DataFrame, pd.DataFrame]],
    trial: Any,
) -> float:
    import optuna
    import xgboost as xgb

    fold_rmses: List[float] = []
    for step, (sub_train, val) in enumerate(slices):
        model = xgb.XGBRegressor(
            objective="reg:squarederror",
            random_state=OPTUNA_SEED,
            n_jobs=-1,
            **params,
        )
        model.fit(sub_train[XGB_FEATURE_COLUMNS], sub_train["meter_reading"])
        preds = model.predict(val[XGB_FEATURE_COLUMNS])
        fold_rmses.append(_rmse(val["meter_reading"].to_numpy(dtype=float), preds))

        running = float(np.mean(fold_rmses))
        trial.report(running, step=step)
        if trial.should_prune():
            raise optuna.TrialPruned()

    return float(np.mean(fold_rmses))


def _score_lstm(
    params: Dict[str, Any],
    slices: List[Tuple[pd.DataFrame, pd.DataFrame]],
    trial: Any,
    epoch_cap: int,
    trial_timeout_s: float,
) -> float:
    import optuna

    from experiments.benchmark.lstm import LSTM_INPUT_HOURS, LSTM_OUTPUT_HOURS, LSTMForecaster

    minimum = LSTM_INPUT_HOURS + LSTM_OUTPUT_HOURS
    # Spread the per-trial wall-clock budget across the folds this trial will fit.
    usable = [(tr, va) for tr, va in slices if len(tr) >= minimum and len(va) >= 1]
    if not usable:
        raise optuna.TrialPruned()
    per_fold_budget = max(1.0, trial_timeout_s / len(usable))

    fold_rmses: List[float] = []
    for step, (sub_train, val) in enumerate(usable):
        model = LSTMForecaster(max_epochs=epoch_cap, **params)
        model.set_time_budget(per_fold_budget)
        model.fit(sub_train)
        preds = model.predict(val)
        fold_rmses.append(_rmse(val["meter_reading"].to_numpy(dtype=float), preds))

        running = float(np.mean(fold_rmses))
        trial.report(running, step=step)
        if trial.should_prune():
            raise optuna.TrialPruned()

    return float(np.mean(fold_rmses))


# --------------------------------------------------------------------------- #
# Study runner
# --------------------------------------------------------------------------- #
def default_study_storage() -> str:
    """Repo-relative resumable SQLite study storage (separate from the MLflow backend)."""
    mlruns_dir().mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(mlruns_dir() / 'optuna.db').as_posix()}"


def run_study(
    model_name: str,
    train_df: pd.DataFrame,
    n_trials: int = OPTUNA_N_TRIALS,
    *,
    storage: Optional[str] = None,
    study_name: Optional[str] = None,
    tracking_uri: Optional[str] = None,
    artifact_location: Optional[str] = None,
    n_slices: int = DEFAULT_N_VALIDATION_SLICES,
    seed: int = OPTUNA_SEED,
    n_startup_trials: int = OPTUNA_N_STARTUP_TRIALS,
    trial_timeout_s: float = OPTUNA_TRIAL_TIMEOUT_S,
    lstm_epoch_cap: int = DEFAULT_LSTM_SEARCH_EPOCH_CAP,
    log_to_mlflow: bool = True,
) -> Dict[str, Any]:
    """
    Run one Optuna study for ``model_name`` and return
    ``{"model", "best_params", "best_value", "n_complete", "n_pruned", "study_name"}``.

    Each trial is logged to MLflow as a run nested under the study's parent run
    when ``log_to_mlflow`` (and mlflow is installed). The study is persisted to
    ``storage`` with a fixed sampler seed so it is resumable and deterministic.
    """
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model '{model_name}'; supported: {SUPPORTED_MODELS}")

    import optuna
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler
    from optuna.trial import TrialState

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    slices = make_validation_slices(train_df, n_slices=n_slices)
    storage = storage or default_study_storage()
    study_name = study_name or f"ecotrack-hpo-{model_name}"

    sampler = TPESampler(seed=seed)
    pruner = MedianPruner(n_startup_trials=n_startup_trials)
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="minimize",
        sampler=sampler,
        pruner=pruner,
        load_if_exists=True,
    )

    # Optional MLflow parent run.
    mlflow = None
    if log_to_mlflow:
        try:
            import mlflow as _mlflow

            from src.mlops.tracking import configure

            configure(tracking_uri=tracking_uri, artifact_location=artifact_location)
            mlflow = _mlflow
        except Exception as exc:
            logger.warning("MLflow unavailable for HPO logging (%s); running without nested runs.", exc)
            mlflow = None

    if model_name == "xgboost":
        space = xgboost_search_space
        scorer: Callable[[Dict[str, Any], Any], float] = lambda p, t: _score_xgboost(p, slices, t)
    else:
        space = lstm_search_space
        scorer = lambda p, t: _score_lstm(p, slices, t, lstm_epoch_cap, trial_timeout_s)

    def objective(trial: Any) -> float:
        params = space(trial)
        if mlflow is not None:
            with mlflow.start_run(run_name=f"{model_name}-trial-{trial.number}", nested=True):
                mlflow.log_params(params)
                mlflow.set_tag("optuna_trial", str(trial.number))
                mlflow.set_tag("model", model_name)
                try:
                    value = scorer(params, trial)
                except optuna.TrialPruned:
                    mlflow.set_tag("trial_state", "PRUNED")
                    mlflow.log_metric("val_rmse", float("nan"))
                    raise
                mlflow.set_tag("trial_state", "COMPLETE")
                mlflow.log_metric("val_rmse", value)
                return value
        return scorer(params, trial)

    def _n_complete() -> int:
        return len([t for t in study.trials if t.state == TrialState.COMPLETE])

    # Run until exactly ``n_trials`` COMPLETED trials, counting completions (not total
    # trials) so pruned/failed trials never reduce the budget and every model gets the
    # same number of completed trials (spec guarantee). A generous hard cap on total
    # trials keeps a pathological all-pruned/all-failed study from looping forever.
    max_total_trials = max(n_trials * 50, n_trials + 50)

    def _stop_when_enough(study_: Any, trial_: Any) -> None:
        if _n_complete() >= n_trials or len(study_.trials) >= max_total_trials:
            study_.stop()

    def _run_parent() -> None:
        # ``catch`` records a trial that raises (non-prune) as FAILED and continues, instead
        # of aborting the whole study. optuna handles TrialPruned before ``catch``, so pruned
        # trials stay PRUNED.
        study.optimize(
            objective,
            n_trials=None,
            callbacks=[_stop_when_enough],
            catch=(Exception,),
        )

    if mlflow is not None:
        with mlflow.start_run(run_name=f"hpo-{model_name}"):
            mlflow.set_tag("model", model_name)
            mlflow.set_tag("search", "optuna")
            _run_parent()
            if _n_complete() > 0:
                mlflow.log_params({f"best_{k}": v for k, v in study.best_params.items()})
                mlflow.log_metric("best_val_rmse", float(study.best_value))
    else:
        _run_parent()

    complete = [t for t in study.trials if t.state == TrialState.COMPLETE]
    pruned = [t for t in study.trials if t.state == TrialState.PRUNED]
    failed = [t for t in study.trials if t.state == TrialState.FAIL]
    if not complete:
        raise RuntimeError(
            f"HPO '{model_name}' produced no completed trials "
            f"({len(pruned)} pruned, {len(failed)} failed); cannot select best parameters."
        )

    result = {
        "model": model_name,
        "best_params": dict(study.best_params),
        "best_value": float(study.best_value),
        "n_complete": len(complete),
        "n_pruned": len(pruned),
        "n_failed": len(failed),
        "study_name": study_name,
    }
    logger.info(
        "HPO %s finished: %d complete, %d pruned, %d failed, best val RMSE %.4f.",
        model_name,
        len(complete),
        len(pruned),
        len(failed),
        result["best_value"],
    )
    return result


def run_searches(
    models: List[str],
    train_df: pd.DataFrame,
    n_trials: int = OPTUNA_N_TRIALS,
    **kwargs: Any,
) -> Dict[str, Dict[str, Any]]:
    """Run a study per requested model and return ``{model_name: run_study(...) result}``."""
    results: Dict[str, Dict[str, Any]] = {}
    for model_name in models:
        results[model_name] = run_study(model_name, train_df, n_trials=n_trials, **kwargs)
    return results
