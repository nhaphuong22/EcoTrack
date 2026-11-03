"""
Repo-relative MLflow / Optuna configuration for EcoTrack (Story 4.5).

All paths default to a store under ``ai-service/mlruns/`` so the owner's
host runs and the Docker container (which mounts ``ai-service/mlruns`` as a
volume) resolve the *same* store. No absolute, machine-specific path is ever
written into the registry: the relative ``artifact_location`` keeps the store
portable; see :func:`get_artifact_location`.

This module imports nothing heavy (no mlflow/optuna at import time) so it is
safe to import from the serving process and from plain-Python tools (AD-1).
"""

from __future__ import annotations

import os
from pathlib import Path


# ai-service/src/mlops/config.py -> parents[2] == ai-service/
AI_SERVICE_DIR: Path = Path(__file__).resolve().parents[2]

# Registry identity. One registered model holds every tracked forecaster
# version; the serving model is the one carrying the `champion` alias.
REGISTERED_MODEL_NAME: str = os.getenv("ECOTRACK_REGISTERED_MODEL", "ecotrack-forecaster")
CHAMPION_ALIAS: str = "champion"

# Optuna budget (locked with the product owner 2026-10-29). Every value is
# env-overridable so the owner can run the search in smaller stages.
OPTUNA_N_TRIALS: int = int(os.getenv("OPTUNA_N_TRIALS", "30"))
OPTUNA_TRIAL_TIMEOUT_S: float = float(os.getenv("OPTUNA_TRIAL_TIMEOUT_S", "300"))
OPTUNA_N_STARTUP_TRIALS: int = int(os.getenv("OPTUNA_N_STARTUP_TRIALS", "5"))
OPTUNA_SEED: int = int(os.getenv("OPTUNA_SEED", "42"))

# Drift thresholds (Story 4.6 — FR24). A column is flagged when its KS test
# p-value drops below DRIFT_KS_PVALUE_THRESHOLD *and* its PSI exceeds
# DRIFT_PSI_THRESHOLD; the rolling-MAPE signal fires independently above
# DRIFT_MAPE_THRESHOLD_PERCENT. Defaults match the epics.md acceptance criteria.
DRIFT_KS_PVALUE_THRESHOLD: float = float(os.getenv("DRIFT_KS_PVALUE_THRESHOLD", "0.05"))
DRIFT_PSI_THRESHOLD: float = float(os.getenv("DRIFT_PSI_THRESHOLD", "0.2"))
DRIFT_MAPE_THRESHOLD_PERCENT: float = float(os.getenv("DRIFT_MAPE_THRESHOLD_PERCENT", "15.0"))


def mlruns_dir() -> Path:
    """Absolute path to the repo-relative ``ai-service/mlruns/`` store directory."""
    return AI_SERVICE_DIR / "mlruns"


def get_tracking_uri() -> str:
    """
    MLflow tracking URI.

    Honours ``MLFLOW_TRACKING_URI`` verbatim when set (tests pass a temp store
    here). Otherwise defaults to the repo-relative SQLite backend
    ``mlruns/mlflow.db`` resolved against ``ai-service/`` so the live
    connection works regardless of the process CWD. The URI is a runtime
    connection string, not data persisted inside the registry.
    """
    env = os.getenv("MLFLOW_TRACKING_URI")
    if env:
        return env
    db_path = mlruns_dir() / "mlflow.db"
    return f"sqlite:///{db_path.as_posix()}"


def get_artifact_location() -> str:
    """
    Artifact root for the MLflow experiment.

    Honours ``MLFLOW_ARTIFACT_ROOT`` when set, else a **relative** location
    (``./mlruns/artifacts``). Keeping this relative is what keeps the store
    portable between the owner's host and the container (both run MLflow
    commands with CWD = ``ai-service/``); no absolute path is written to the
    registry.
    """
    return os.getenv("MLFLOW_ARTIFACT_ROOT", "./mlruns/artifacts")


def get_experiment_name() -> str:
    """Name of the MLflow experiment that groups EcoTrack training/search runs."""
    return os.getenv("ECOTRACK_MLFLOW_EXPERIMENT", "ecotrack-forecasting")


def _sqlite_path_from_uri(uri: str) -> Path | None:
    """Returns the filesystem path for a ``sqlite:///...`` URI, else None."""
    prefix = "sqlite:///"
    if uri.startswith(prefix):
        return Path(uri[len(prefix):])
    return None


def mlflow_disabled() -> bool:
    """
    Shared opt-out: when ``ECOTRACK_DISABLE_MLFLOW`` is truthy every MLflow path
    (training hook, serving champion load, health champion report) must behave as
    if MLflow were absent and use ``models_saved/``. One helper keeps all three in
    agreement so health never reports a champion the service is not actually serving.
    """
    return os.getenv("ECOTRACK_DISABLE_MLFLOW", "").strip() in ("1", "true", "True")


def mlflow_available() -> bool:
    """True when the ``mlflow`` package is importable (served dependency)."""
    try:
        import mlflow  # noqa: F401
    except Exception:
        return False
    return True


def is_mlflow_initialised(tracking_uri: str | None = None) -> bool:
    """
    Whether an MLflow store is present and usable.

    For the default/explicit SQLite backend this means the ``.db`` file
    already exists on disk (a training run creates it). For any non-SQLite
    backend we assume an operator who set the URI also provisioned the store.
    Returns False when mlflow itself is not installed, so the serving path
    falls back to ``models_saved/`` (no-MLflow dev/CI contract).
    """
    if not mlflow_available():
        return False
    uri = tracking_uri or get_tracking_uri()
    db_path = _sqlite_path_from_uri(uri)
    if db_path is not None:
        return db_path.exists()
    return True
