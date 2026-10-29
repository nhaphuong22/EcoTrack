"""
MLflow tracking + model-registry wrapper for EcoTrack (Story 4.5 — FR23).

A thin layer over ``mlflow`` that gives ``train_models.py`` three hooks:

* configure a repo-relative store and open a run,
* log params / metrics / feature list / row counts / the model artifact,
* register the version and bootstrap the ``champion`` alias **set-if-absent**
  (first-champion only — promotion over an existing champion is Story 4.8).

It also serves the AI service a champion-first load (:func:`load_champion_forecaster`)
with the locked tri-state behaviour:

* mlflow not installed / no store / no ``champion`` alias  -> ``ChampionUnavailable``
  (caller falls back to ``models_saved/`` with a warning),
* alias resolves but the artifact is missing/corrupt, or the backend is locked
  -> ``ChampionArtifactError`` (caller surfaces ``503 ERR_MODEL_NOT_FOUND``; **no**
  silent fallback).

``mlflow`` is imported lazily inside each function so importing this module never
fails on the no-MLflow dev/CI path.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.mlops.config import (
    CHAMPION_ALIAS,
    REGISTERED_MODEL_NAME,
    _sqlite_path_from_uri,
    get_artifact_location,
    get_experiment_name,
    get_tracking_uri,
    is_mlflow_initialised,
    mlflow_available,
    mlflow_disabled,
    mlruns_dir,
)

logger = logging.getLogger("MLOpsTracking")


class ChampionUnavailable(Exception):
    """MLflow is not initialised (no store / no champion alias). Fall back to models_saved/."""


class ChampionArtifactError(Exception):
    """Champion alias resolves but its artifact is broken, or the backend is locked. Fail loud."""

    def __init__(self, message: str, version: Optional[str] = None):
        super().__init__(message)
        self.version = version


# --------------------------------------------------------------------------- #
# Configuration / run lifecycle
# --------------------------------------------------------------------------- #
def configure(tracking_uri: Optional[str] = None, artifact_location: Optional[str] = None) -> str:
    """
    Point MLflow at the (repo-relative by default) store and ensure the EcoTrack
    experiment exists. Returns the resolved tracking URI. Creates the SQLite
    parent directory when needed so a first run can bootstrap the store.
    """
    import mlflow

    uri = tracking_uri or get_tracking_uri()
    db_path = _sqlite_path_from_uri(uri)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(uri)
    exp_name = get_experiment_name()
    experiment = mlflow.get_experiment_by_name(exp_name)
    if experiment is None:
        mlflow.create_experiment(
            exp_name,
            artifact_location=artifact_location or get_artifact_location(),
        )
    mlflow.set_experiment(exp_name)
    return uri


def _champion_lock_path(tracking_uri: Optional[str]) -> Path:
    """
    Path of the cross-process lock guarding the first-champion critical section.

    Lives next to the store (the SQLite db's directory, or ``ai-service/mlruns``)
    so a host run and a container run sharing the same mount serialise against the
    same file.
    """
    uri = tracking_uri or get_tracking_uri()
    db_path = _sqlite_path_from_uri(uri)
    base = db_path.parent if db_path is not None else mlruns_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base / ".champion.lock"


def register_and_bootstrap_champion(
    version: str,
    name: str = REGISTERED_MODEL_NAME,
    tracking_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set-if-absent ``champion`` alias.

    The whole check-alias -> set-alias section runs under a filesystem lock
    because MLflow + SQLite has no atomic compare-and-set for aliases; two
    concurrent first-champion runs therefore cannot both claim the alias.

    Returns ``{"alias_set": bool, "champion_version": <version>}``. ``alias_set``
    is True only when this call installed the first champion; if a champion
    already exists the alias is left untouched (promotion is Story 4.8).
    """
    from filelock import FileLock
    from mlflow.tracking import MlflowClient

    lock = FileLock(str(_champion_lock_path(tracking_uri)))
    with lock:
        client = MlflowClient()
        version = str(version)
        existing_version: Optional[str] = None
        try:
            existing = client.get_model_version_by_alias(name, CHAMPION_ALIAS)
            existing_version = str(existing.version)
        except Exception:
            existing_version = None

        if existing_version is None:
            client.set_registered_model_alias(name, CHAMPION_ALIAS, version)
            logger.info("Bootstrapped first champion: %s version %s.", name, version)
            return {"alias_set": True, "champion_version": version}

        logger.info(
            "Champion already exists (%s version %s); new version %s registered but alias unchanged "
            "(promotion deferred to Story 4.8).",
            name,
            existing_version,
            version,
        )
        return {"alias_set": False, "champion_version": existing_version}


def track_training_run(
    model: Any,
    params: Dict[str, Any],
    metrics: Dict[str, Any],
    features: List[str],
    row_counts: Dict[str, int],
    run_name: str = "train_models",
    tracking_uri: Optional[str] = None,
    artifact_location: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Log one completed XGBoost training run to MLflow and bootstrap the champion.

    No-op (returns None) when mlflow is not installed, so the no-MLflow training
    path is never broken. Only numeric values in ``metrics`` are logged as MLflow
    metrics; the feature list is stored as a tag + a count param; row counts are
    logged as params. Returns a summary dict on success.
    """
    if not mlflow_available():
        logger.info("mlflow not installed; skipping MLflow tracking (models_saved/ path only).")
        return None

    import mlflow

    configure(tracking_uri=tracking_uri, artifact_location=artifact_location)

    numeric_metrics = {
        k: float(v) for k, v in metrics.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
    }

    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        mlflow.log_params({str(k): v for k, v in params.items()})
        mlflow.log_params({str(k): int(v) for k, v in row_counts.items()})
        mlflow.log_param("n_features", len(features))
        if numeric_metrics:
            mlflow.log_metrics(numeric_metrics)
        mlflow.set_tag("xgb_features", json.dumps(list(features)))

        model_info = mlflow.xgboost.log_model(model, artifact_path="model")
        model_version = mlflow.register_model(model_info.model_uri, REGISTERED_MODEL_NAME)
        version = str(model_version.version)

    champion = register_and_bootstrap_champion(version, tracking_uri=tracking_uri)
    summary = {
        "run_id": run_id,
        "version": version,
        "registered_model": REGISTERED_MODEL_NAME,
        **champion,
    }
    logger.info("MLflow run %s logged; registered %s v%s.", run_id, REGISTERED_MODEL_NAME, version)
    return summary


# --------------------------------------------------------------------------- #
# Champion-aware serving load (tri-state)
# --------------------------------------------------------------------------- #
def _is_not_found(exc: Exception) -> bool:
    """Heuristic: True when an MlflowException means 'no such model/alias' (vs. a locked DB)."""
    code = getattr(exc, "error_code", "") or ""
    if code == "RESOURCE_DOES_NOT_EXIST":
        return True
    text = str(exc).lower()
    return "does not exist" in text or "not found" in text or "no versions" in text


def resolve_champion_version(tracking_uri: Optional[str] = None) -> Optional[str]:
    """
    Best-effort champion version lookup for the health check. Never raises:
    returns the version string when the alias resolves, else None. Honours the
    shared ``ECOTRACK_DISABLE_MLFLOW`` opt-out so health agrees with what serving
    actually loads.
    """
    if mlflow_disabled() or not is_mlflow_initialised(tracking_uri):
        return None
    try:
        from mlflow.tracking import MlflowClient

        configure(tracking_uri=tracking_uri)
        mv = MlflowClient().get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
        return str(mv.version)
    except Exception:
        return None


def load_champion_forecaster(tracking_uri: Optional[str] = None) -> Tuple[Any, str]:
    """
    Resolve the forecast model through the ``champion`` alias.

    Returns ``(model, version)`` when the champion resolves and loads.
    Raises :class:`ChampionUnavailable` when MLflow is not initialised or no
    champion alias is set (caller should fall back to ``models_saved/``).
    Raises :class:`ChampionArtifactError` when the alias resolves but the
    artifact is missing/corrupt, or the backend is locked (caller must fail loud).
    """
    if not mlflow_available():
        raise ChampionUnavailable("mlflow is not installed")
    if not is_mlflow_initialised(tracking_uri):
        raise ChampionUnavailable("MLflow store is not initialised")

    import mlflow
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    configure(tracking_uri=tracking_uri)
    client = MlflowClient()
    try:
        mv = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
    except MlflowException as exc:
        if _is_not_found(exc):
            raise ChampionUnavailable(f"No champion alias resolvable: {exc}") from exc
        # Non not-found MlflowException (e.g. SQLite locked) must not be masked.
        raise ChampionArtifactError(f"Could not resolve champion alias: {exc}") from exc

    version = str(mv.version)
    try:
        model = mlflow.xgboost.load_model(f"models:/{REGISTERED_MODEL_NAME}@{CHAMPION_ALIAS}")
    except Exception as exc:  # broken/missing artifact
        raise ChampionArtifactError(
            f"Champion model version {version} failed to load: {exc}", version=version
        ) from exc

    logger.info("Loaded champion %s version %s.", REGISTERED_MODEL_NAME, version)
    return model, version
