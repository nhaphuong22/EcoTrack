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
import math
import tempfile
from datetime import datetime, timezone
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

QUANTILE_ARTIFACT_PATH = "quantile_model"


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
def _normalize_artifact_location(location: str) -> str:
    """Convert Windows drive paths (e.g. ``C:/...``) into ``file:///`` URIs for MLflow."""
    if len(location) >= 2 and location[0].isalpha() and location[1] == ":":
        return Path(location).resolve().as_uri()
    return location


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
        resolved_artifact_loc = _normalize_artifact_location(
            artifact_location or get_artifact_location()
        )
        mlflow.create_experiment(
            exp_name,
            artifact_location=resolved_artifact_loc,
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


def _version_has_quantile(client: Any, name: str, version: str) -> bool:
    """Whether the run behind a registered version carries the ``quantile_model`` artifact."""
    run_id = client.get_model_version(name, str(version)).run_id
    return any(a.path == QUANTILE_ARTIFACT_PATH for a in client.list_artifacts(run_id))


def register_and_bootstrap_champion(
    version: str,
    name: str = REGISTERED_MODEL_NAME,
    tracking_uri: Optional[str] = None,
    new_has_quantile: bool = False,
) -> Dict[str, Any]:
    """
    Set-if-absent ``champion`` alias.

    One exception (Story 4.13): a champion whose run has no ``quantile_model`` cannot serve the
    forecast band, so when ``new_has_quantile`` is true that legacy champion is replaced by the
    new version. A champion that already has the artifact is never replaced here.

    The whole check-alias -> set-alias section runs under a filesystem lock
    because MLflow + SQLite has no atomic compare-and-set for aliases; two
    concurrent first-champion runs therefore cannot both claim the alias.

    Returns ``{"alias_set": bool, "champion_version": <version>}``. ``alias_set``
    is True only when this call installed the first champion; if a champion
    already exists the alias is left untouched (promotion is Story 4.8).
    """
    from filelock import FileLock
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    lock = FileLock(str(_champion_lock_path(tracking_uri)))
    with lock:
        client = MlflowClient()
        version = str(version)
        existing_version: Optional[str] = None
        try:
            existing = client.get_model_version_by_alias(name, CHAMPION_ALIAS)
            existing_version = str(existing.version)
        except MlflowException as exc:
            if _is_not_found(exc):
                # Genuinely no champion yet -> safe to bootstrap below.
                existing_version = None
            else:
                # A non not-found error (e.g. a locked SQLite backend) must NOT be
                # mistaken for "no champion": treating it as absent would overwrite an
                # existing champion and break set-if-absent. Fail loud instead.
                raise ChampionArtifactError(
                    f"Could not read champion alias during bootstrap: {exc}"
                ) from exc

        if existing_version is None:
            client.set_registered_model_alias(name, CHAMPION_ALIAS, version)
            logger.info("Bootstrapped first champion: %s version %s.", name, version)
            return {"alias_set": True, "champion_version": version}

        if new_has_quantile and not _version_has_quantile(client, name, existing_version):
            client.set_registered_model_alias(name, CHAMPION_ALIAS, version)
            logger.info(
                "Champion version %s has no %s; replaced by version %s, which has one.",
                existing_version,
                QUANTILE_ARTIFACT_PATH,
                version,
            )
            return {"alias_set": True, "champion_version": version}

        logger.info(
            "Champion already exists (%s version %s); new version %s registered but alias unchanged "
            "(promotion deferred to Story 4.8).",
            name,
            existing_version,
            version,
        )
        return {"alias_set": False, "champion_version": existing_version}


def promote_champion(
    version: str,
    name: str = REGISTERED_MODEL_NAME,
    tracking_uri: Optional[str] = None,
) -> str:
    """
    Assign the ``champion`` alias to ``version`` under the cross-process
    ``.champion.lock`` (Story 4.8 — FR25 guarded promotion).
    """
    from filelock import FileLock
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    uri = configure(tracking_uri=tracking_uri)
    lock = FileLock(str(_champion_lock_path(tracking_uri)))
    with lock:
        client = MlflowClient(tracking_uri=uri)
        version = str(version)
        try:
            client.set_registered_model_alias(name, CHAMPION_ALIAS, version)
        except MlflowException as exc:
            raise ChampionArtifactError(
                f"Could not promote version {version} to champion alias: {exc}",
                version=version,
            ) from exc
        logger.info("Promoted %s version %s to %s alias.", name, version, CHAMPION_ALIAS)
        return version


def clear_champion_alias(
    name: str = REGISTERED_MODEL_NAME,
    tracking_uri: Optional[str] = None,
) -> None:
    """
    Remove the ``champion`` alias under ``.champion.lock`` (used when rolling back
    a promotion that had no prior MLflow champion alias).
    """
    from filelock import FileLock
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    uri = configure(tracking_uri=tracking_uri)
    lock = FileLock(str(_champion_lock_path(tracking_uri)))
    with lock:
        client = MlflowClient(tracking_uri=uri)
        try:
            client.delete_registered_model_alias(name, CHAMPION_ALIAS)
        except MlflowException as exc:
            if not _is_not_found(exc):
                raise ChampionArtifactError(
                    f"Could not clear champion alias: {exc}"
                ) from exc


def get_champion_tag(
    tag_key: str,
    name: str = REGISTERED_MODEL_NAME,
    tracking_uri: Optional[str] = None,
) -> Optional[str]:
    """Read a tag from the MLflow run backing the current ``champion`` alias, or None."""
    if mlflow_disabled() or not is_mlflow_initialised(tracking_uri):
        return None
    try:
        from mlflow.tracking import MlflowClient

        uri = configure(tracking_uri=tracking_uri)
        client = MlflowClient(tracking_uri=uri)
        mv = client.get_model_version_by_alias(name, CHAMPION_ALIAS)
        if not mv.run_id:
            return None
        run = client.get_run(mv.run_id)
        return run.data.tags.get(tag_key)
    except Exception:
        return None


def track_training_run(
    model: Any,
    params: Dict[str, Any],
    metrics: Dict[str, Any],
    features: List[str],
    row_counts: Dict[str, int],
    run_name: str = "train_models",
    tracking_uri: Optional[str] = None,
    artifact_location: Optional[str] = None,
    bootstrap_champion: bool = True,
    tags: Optional[Dict[str, str]] = None,
    quantile_model: Any = None,
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
        if tags:
            mlflow.set_tags({str(k): str(v) for k, v in tags.items()})

        if quantile_model is not None:
            # Same run, before the version is registered: the champion version carries both.
            mlflow.xgboost.log_model(quantile_model, artifact_path=QUANTILE_ARTIFACT_PATH)
        model_info = mlflow.xgboost.log_model(model, artifact_path="model")
        model_version = mlflow.register_model(model_info.model_uri, REGISTERED_MODEL_NAME)
        version = str(model_version.version)

    if bootstrap_champion:
        champion = register_and_bootstrap_champion(
            version, tracking_uri=tracking_uri, new_has_quantile=quantile_model is not None
        )
    else:
        champion = {
            "alias_set": False,
            "champion_version": resolve_champion_version(tracking_uri=tracking_uri),
        }
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


def load_champion_quantile_model(tracking_uri: Optional[str] = None) -> Any:
    """
    Load the ``quantile_model`` artifact logged in the champion version's run.

    Raises :class:`ChampionUnavailable` when there is no champion (caller falls back to disk) and
    :class:`ChampionArtifactError` when the champion exists but its run has no loadable quantile model.
    """
    if not mlflow_available():
        raise ChampionUnavailable("mlflow is not installed")
    if not is_mlflow_initialised(tracking_uri):
        raise ChampionUnavailable("MLflow store is not initialised")

    import mlflow
    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    configure(tracking_uri=tracking_uri)
    try:
        mv = MlflowClient().get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
    except MlflowException as exc:
        if _is_not_found(exc):
            raise ChampionUnavailable(f"No champion alias resolvable: {exc}") from exc
        raise ChampionArtifactError(f"Could not resolve champion alias: {exc}") from exc
    version = str(mv.version)
    try:
        return mlflow.xgboost.load_model(f"runs:/{mv.run_id}/{QUANTILE_ARTIFACT_PATH}")
    except Exception as exc:
        raise ChampionArtifactError(
            f"Champion model version {version} has no loadable {QUANTILE_ARTIFACT_PATH}: {exc}", version=version
        ) from exc


def champion_health(tracking_uri: Optional[str] = None) -> Dict[str, Any]:
    """
    Champion status for the health check. Never raises.

    Actually loads the champion artifact (no caching — one load per probe) so that
    ``/health`` agrees with what serving does, instead of reporting a champion that
    serving cannot load. Returns one of:

    * ``{"status": "resolved",    "version": <v>}``  — champion resolves and loads,
    * ``{"status": "broken",      "version": <v>}``  — alias resolves but the artifact
      fails to load / the backend is locked (serving would surface 503),
    * ``{"status": "unavailable", "version": None}`` — MLflow disabled / not installed /
      not initialised / no champion alias (serving falls back to ``models_saved/``).
    """
    if mlflow_disabled():
        return {"status": "unavailable", "version": None}
    try:
        _model, version = load_champion_forecaster(tracking_uri)
        return {"status": "resolved", "version": version}
    except ChampionUnavailable:
        return {"status": "unavailable", "version": None}
    except ChampionArtifactError as exc:
        return {"status": "broken", "version": getattr(exc, "version", None)}
    except Exception:  # defensive: health must never raise
        return {"status": "unavailable", "version": None}


def _epoch_ms_to_iso_utc(ts_ms: Any) -> Optional[str]:
    if ts_ms is None or isinstance(ts_ms, bool):
        return None
    try:
        val = float(ts_ms)
        if not math.isfinite(val):
            return None
        return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _artifact_exists_at(root_entries: List[Any], dl_uri: str, rel: str, uri: str) -> bool:
    import mlflow

    parts = Path(rel.strip()).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        return False
    entries = root_entries
    for idx, part in enumerate(parts):
        entry = next((item for item in entries if Path(item.path).name == part), None)
        if entry is None:
            return False
        if idx < len(parts) - 1:
            if not entry.is_dir:
                return False
            sub_uri = f"{dl_uri.rstrip('/')}/{'/'.join(parts[: idx + 1])}"
            entries = mlflow.artifacts.list_artifacts(artifact_uri=sub_uri, tracking_uri=uri)
        elif entry.is_dir:
            sub_uri = f"{dl_uri.rstrip('/')}/{'/'.join(parts)}"
            return bool(mlflow.artifacts.list_artifacts(artifact_uri=sub_uri, tracking_uri=uri))
        else:
            return entry.file_size is None or entry.file_size > 0
    return False


def _verify_champion_artifacts(client: Any, version: str, uri: str) -> Optional[str]:
    """Verify ``MLmodel`` and declared flavor artifacts exist without deserializing the binary."""
    import mlflow
    import yaml

    dl_uri = client.get_model_version_download_uri(REGISTERED_MODEL_NAME, version)
    artifacts = mlflow.artifacts.list_artifacts(artifact_uri=dl_uri, tracking_uri=uri)
    mlmodel_entry = next((item for item in artifacts if Path(item.path).name == "MLmodel"), None)
    if (
        mlmodel_entry is None
        or mlmodel_entry.is_dir
        or (mlmodel_entry.file_size is not None and mlmodel_entry.file_size <= 0)
    ):
        return f"Champion model version {version} is missing MLmodel metadata."

    with tempfile.TemporaryDirectory() as tmp_dir:
        mlmodel_path = mlflow.artifacts.download_artifacts(
            artifact_uri=f"{dl_uri.rstrip('/')}/MLmodel",
            dst_path=tmp_dir,
            tracking_uri=uri,
        )
        doc = yaml.safe_load(Path(mlmodel_path).read_text(encoding="utf-8"))

    if not isinstance(doc, dict):
        return f"Champion model version {version} has invalid MLmodel metadata."
    flavors = doc.get("flavors")
    if not isinstance(flavors, dict) or not flavors:
        return f"Champion model version {version} is missing MLmodel flavors metadata."

    for cfg in flavors.values():
        if not isinstance(cfg, dict):
            continue
        rel = cfg.get("data") or cfg.get("model_path")
        if rel is not None and (not isinstance(rel, str) or not _artifact_exists_at(artifacts, dl_uri, rel, uri)):
            return f"Champion model version {version} is missing model artifact '{rel}'."
    return None


def get_champion_metadata(tracking_uri: Optional[str] = None) -> Dict[str, Any]:
    """
    Lightweight champion inspection for MLOps status reporting (Story 4.10 — FR26).

    Reads alias, run timestamp, and finite metrics via ``MlflowClient`` and checks
    ``MLmodel`` + declared artifact presence without deserializing the XGBoost model.
    Returns ``{"status": "resolved" | "unavailable" | "broken", ...}``.
    """
    clean_uri = tracking_uri.strip() if isinstance(tracking_uri, str) else None
    effective_uri = clean_uri or None
    if mlflow_disabled() or not mlflow_available():
        return {"status": "unavailable", "version": None, "trained_at": None, "metrics": None, "error": None}

    from mlflow.exceptions import MlflowException
    from mlflow.tracking import MlflowClient

    try:
        if not is_mlflow_initialised(effective_uri):
            return {"status": "unavailable", "version": None, "trained_at": None, "metrics": None, "error": None}
        uri = effective_uri or get_tracking_uri()
        client = MlflowClient(tracking_uri=uri, registry_uri=uri)
        mv = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
    except MlflowException as exc:
        if _is_not_found(exc):
            return {"status": "unavailable", "version": None, "trained_at": None, "metrics": None, "error": None}
        return {
            "status": "broken",
            "version": None,
            "trained_at": None,
            "metrics": None,
            "error": f"Could not resolve champion alias: {exc}",
        }
    except Exception as exc:
        return {
            "status": "broken",
            "version": None,
            "trained_at": None,
            "metrics": None,
            "error": f"Could not resolve champion alias: {exc}",
        }

    version = str(mv.version)
    try:
        artifact_err = _verify_champion_artifacts(client, version, uri)
        if artifact_err:
            return {
                "status": "broken",
                "version": version,
                "trained_at": None,
                "metrics": None,
                "error": artifact_err,
            }
        run = client.get_run(mv.run_id) if getattr(mv, "run_id", None) else None
        ts_ms = (
            (run.info.end_time or run.info.start_time) if run is not None else None
        ) or getattr(mv, "creation_timestamp", None)
        trained_at = _epoch_ms_to_iso_utc(ts_ms)
        raw_metrics = run.data.metrics if run is not None else {}
        metrics: Dict[str, float] = {}
        for k, v in raw_metrics.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                fval = float(v)
                if math.isfinite(fval):
                    metrics[str(k)] = fval
                else:
                    logger.warning("Ignoring non-finite MLflow metric %r=%r for champion version %s.", k, v, version)
    except Exception as exc:
        return {
            "status": "broken",
            "version": version,
            "trained_at": None,
            "metrics": None,
            "error": f"Champion model version {version} metadata or artifacts unreadable: {exc}",
        }

    return {
        "status": "resolved",
        "version": version,
        "trained_at": trained_at,
        "metrics": metrics,
        "error": None,
    }
