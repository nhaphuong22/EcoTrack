"""
On-demand retraining with guarded champion promotion for EcoTrack (Story 4.8 — FR25).

Plain-Python coordinator (AD-1, no FastAPI dependency) reusable by both the
manual internal endpoint (``POST /internal/mlops/retrain``) and the scheduled
drift-triggered retrain job (Story 4.9), persisting history for ``GET /internal/mlops/status``
(Story 4.10).
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from src.config import get_data_path, get_models_dir
from src.data_pipeline import serving_frame
from src.mlops.config import (
    REGISTERED_MODEL_NAME,
    is_mlflow_initialised,
    mlflow_available,
    mlflow_disabled,
)
from src.mlops.tracking import (
    ChampionArtifactError,
    ChampionUnavailable,
    clear_champion_alias,
    configure,
    get_champion_tag,
    load_champion_forecaster,
    promote_champion,
    track_training_run,
)
from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
    train_xgboost_forecaster,
)

logger = logging.getLogger("MLOpsRetrain")

RETRAIN_HISTORY_FILENAME = "retrain_history.json"

# ponytail: single-process threading.Lock for HTTP 409 concurrency guard; upgrade to a FileLock/DB lease only if multi-worker deployment is introduced.
_retrain_lock = threading.Lock()
_history_lock = threading.Lock()


class RetrainAlreadyRunningError(Exception):
    """Raised when a retrain request arrives while another run holds the lock."""


def is_retrain_running() -> bool:
    """True when a retrain run currently holds the in-process lock."""
    return _retrain_lock.locked()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_train_ratio(train_ratio: float) -> float:
    if isinstance(train_ratio, bool) or not isinstance(train_ratio, (int, float)):
        raise ValueError(f"train_ratio must be a float in (0, 1); got {train_ratio!r}")
    ratio = float(train_ratio)
    if not math.isfinite(ratio) or not (0.0 < ratio < 1.0):
        raise ValueError(f"train_ratio must be strictly between 0 and 1; got {train_ratio!r}")
    return ratio


def _history_path(models_dir: Optional[Path] = None) -> Path:
    base = Path(models_dir) if models_dir is not None else get_models_dir()
    return base / RETRAIN_HISTORY_FILENAME


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(f"{target.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def load_retrain_history(models_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Read persisted retraining history (newest first). Returns ``[]`` when no
    history file exists yet.
    """
    with _history_lock:
        path = _history_path(models_dir)
        if not path.is_file():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON list in {path}")
        return data


def _append_history(entry: Dict[str, Any], models_dir: Optional[Path] = None) -> None:
    """Prepend ``entry`` (newest first) to ``retrain_history.json`` via atomic temp-file swap."""
    with _history_lock:
        path = _history_path(models_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: List[Dict[str, Any]] = []
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(loaded, list):
                    raise ValueError(f"Expected a JSON list in {path}")
                existing = loaded
            except Exception as exc:
                backup_path = path.with_name(f"{path.stem}.corrupt.{uuid.uuid4().hex[:8]}.bak")
                logger.warning(
                    "Could not parse existing %s (%s); backing up to %s before starting fresh.",
                    path,
                    exc,
                    backup_path.name,
                )
                os.replace(path, backup_path)
        updated = [entry, *existing]
        payload = json.dumps(updated, indent=2, allow_nan=False).encode("utf-8")
        _atomic_write_bytes(path, payload)


def compute_holdout_mape(y_true: pd.Series | np.ndarray, y_pred: np.ndarray) -> float:
    """
    Shared holdout MAPE (%) policy for champion and challenger:
    - Rejects non-finite inputs or predictions immediately.
    - Excludes zero-target (``y == 0``) rows to avoid division by zero.
    - Raises ``ValueError`` if no non-zero target rows remain or the resulting MAPE is non-finite.
    """
    y_t = np.asarray(y_true, dtype=float)
    y_p = np.asarray(y_pred, dtype=float)
    if y_t.shape != y_p.shape or y_t.size == 0:
        raise ValueError("Holdout target and prediction arrays must be non-empty and match in shape.")
    if not (np.all(np.isfinite(y_t)) and np.all(np.isfinite(y_p))):
        raise ValueError("Holdout targets or predictions contain non-finite (NaN/Inf) values.")
    non_zero = y_t != 0.0
    if not np.any(non_zero):
        raise ValueError("Holdout window contains no non-zero target rows for MAPE calculation.")
    mape = float(np.mean(np.abs((y_t[non_zero] - y_p[non_zero]) / y_t[non_zero])) * 100.0)
    if not np.isfinite(mape):
        raise ValueError(f"Computed holdout MAPE is non-finite: {mape}")
    return mape


def _resolve_current_champion(models_dir: Path, tracking_uri: Optional[str] = None) -> Tuple[Any, str]:
    """
    Load the currently active champion forecaster and its version identifier.
    Raises ``ChampionArtifactError`` or ``FileNotFoundError`` if no usable
    champion can be loaded for comparison.
    """
    if not mlflow_disabled():
        try:
            return load_champion_forecaster(tracking_uri=tracking_uri)
        except ChampionUnavailable as exc:
            logger.warning(
                "MLflow champion unavailable (%s); resolving on-disk forecaster for retrain comparison.",
                exc,
            )
        except ChampionArtifactError:
            raise

    xgb_path = models_dir / "xgboost_forecaster.joblib"
    if not xgb_path.is_file():
        raise FileNotFoundError(f"Champion model artifact not found at {xgb_path}")
    return joblib.load(xgb_path), "local"


def _resolve_champion_train_end(
    champion_version: str,
    models_dir: Path,
    tracking_uri: Optional[str] = None,
) -> Optional[pd.Timestamp]:
    """Return the recorded training cutoff timestamp for the active champion, if available."""
    raw_cutoff: Optional[str] = None
    if champion_version != "local" and not mlflow_disabled():
        raw_cutoff = get_champion_tag("train_end_timestamp", tracking_uri=tracking_uri)
    if raw_cutoff is None:
        meta_path = models_dir / "model_metadata.json"
        if meta_path.is_file():
            try:
                loaded_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(loaded_meta, dict):
                    raw_cutoff = loaded_meta.get("train_end_timestamp")
            except Exception:
                raw_cutoff = None
    if not raw_cutoff:
        return None
    ts = pd.Timestamp(raw_cutoff)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts


def _train_challenger(
    train_df: pd.DataFrame, test_df: pd.DataFrame
) -> Tuple[Any, Dict[str, Any]]:
    """Train the challenger XGBoost forecaster on ``train_df``."""
    model, metrics, _ = train_xgboost_forecaster(train_df, test_df)
    return model, metrics


def _update_local_artifacts_atomically(
    challenger_model: Any,
    models_dir: Path,
    df_feat: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    xgb_metrics: Dict[str, Any],
    probe_X: pd.DataFrame,
    train_end_iso: str,
) -> None:
    """
    Stage the challenger ``.joblib`` to a temp file, verify it loads and produces
    finite predictions, then atomically swap both ``xgboost_forecaster.joblib``
    and ``model_metadata.json`` (preserving existing keys such as ``isolation_forest_quality``).
    """
    models_dir.mkdir(parents=True, exist_ok=True)
    xgb_path = models_dir / "xgboost_forecaster.joblib"
    tmp_xgb = models_dir / f"xgboost_forecaster.joblib.{uuid.uuid4().hex}.tmp"
    meta_path = models_dir / "model_metadata.json"

    try:
        joblib.dump(challenger_model, tmp_xgb)
        reloaded = joblib.load(tmp_xgb)
        probe_pred = np.asarray(reloaded.predict(probe_X), dtype=float)
        if probe_pred.size == 0 or not np.all(np.isfinite(probe_pred)):
            raise ValueError("Reloaded challenger artifact produced non-finite probe predictions.")

        existing_meta: Dict[str, Any] = {}
        if meta_path.is_file():
            loaded_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(loaded_meta, dict):
                raise ValueError(f"Expected JSON object in {meta_path}")
            existing_meta = loaded_meta

        existing_meta.update(
            {
                "dataset_rows": len(df_feat),
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "train_end_timestamp": train_end_iso,
                "xgb_features": list(XGB_FEATURE_COLUMNS),
                "xgboost_metrics": xgb_metrics,
            }
        )
        meta_bytes = json.dumps(existing_meta, indent=2, allow_nan=False).encode("utf-8")

        os.replace(tmp_xgb, xgb_path)
        _atomic_write_bytes(meta_path, meta_bytes)
    finally:
        if tmp_xgb.exists():
            tmp_xgb.unlink(missing_ok=True)


def _restore_file_snapshot(target: Path, snapshot: Optional[bytes]) -> None:
    if snapshot is not None:
        _atomic_write_bytes(target, snapshot)
    elif target.exists():
        target.unlink(missing_ok=True)


def _verify_and_promote_challenger(
    challenger_model: Any,
    challenger_version: str,
    champion_version: str,
    models_dir: Path,
    df_feat: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    xgb_metrics: Dict[str, Any],
    train_end_iso: str,
    tracking_uri: Optional[str] = None,
) -> None:
    """
    Verify challenger loadability before updating disk artifacts, switching the
    MLflow ``champion`` alias, and refreshing the serving cache under
    ``serving_frame._lock``. Restores prior disk artifacts and MLflow alias
    on any failure.
    """
    probe_X = test_df[XGB_FEATURE_COLUMNS].iloc[:1]
    use_mlflow = (
        not mlflow_disabled()
        and mlflow_available()
        and is_mlflow_initialised(tracking_uri)
        and challenger_version != "local"
    )

    if use_mlflow:
        import mlflow

        configure(tracking_uri=tracking_uri)
        loaded_mlflow = mlflow.xgboost.load_model(
            f"models:/{REGISTERED_MODEL_NAME}/{challenger_version}"
        )
        probe_pred = np.asarray(loaded_mlflow.predict(probe_X), dtype=float)
        if probe_pred.size == 0 or not np.all(np.isfinite(probe_pred)):
            raise ValueError("Challenger MLflow artifact produced non-finite probe predictions.")

    xgb_path = models_dir / "xgboost_forecaster.joblib"
    meta_path = models_dir / "model_metadata.json"
    prev_xgb = xgb_path.read_bytes() if xgb_path.is_file() else None
    prev_meta = meta_path.read_bytes() if meta_path.is_file() else None

    alias_switched = False
    disk_updated = False
    with serving_frame._lock:
        try:
            _update_local_artifacts_atomically(
                challenger_model=challenger_model,
                models_dir=models_dir,
                df_feat=df_feat,
                train_df=train_df,
                test_df=test_df,
                xgb_metrics=xgb_metrics,
                probe_X=probe_X,
                train_end_iso=train_end_iso,
            )
            disk_updated = True
            if use_mlflow:
                promote_champion(challenger_version, tracking_uri=tracking_uri)
                alias_switched = True
            serving_frame.reset_serving_cache()
        except Exception:
            if disk_updated:
                try:
                    _restore_file_snapshot(xgb_path, prev_xgb)
                    _restore_file_snapshot(meta_path, prev_meta)
                except Exception as restore_exc:
                    logger.error("Failed to restore local model artifacts: %s", restore_exc)
            if alias_switched and use_mlflow:
                try:
                    if champion_version and champion_version != "local":
                        promote_champion(champion_version, tracking_uri=tracking_uri)
                    else:
                        clear_champion_alias(tracking_uri=tracking_uri)
                except Exception as rollback_exc:
                    logger.error("Failed to roll back champion alias to %s: %s", champion_version, rollback_exc)
            raise


def _execute_retrain_locked(
    trigger: str = "manual",
    run_id: Optional[str] = None,
    data_path: Optional[Path] = None,
    models_dir: Optional[Path] = None,
    train_ratio: float = 0.8,
    tracking_uri: Optional[str] = None,
    signals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Core retrain execution body; caller must already hold ``_retrain_lock``."""
    resolved_run_id = run_id or uuid.uuid4().hex[:12]
    resolved_models: Optional[Path] = None
    champion_version: Optional[str] = None
    challenger_version: Optional[str] = None
    champion_mape: Optional[float] = None
    challenger_mape: Optional[float] = None
    outcome = "failed"
    reason: Optional[str] = None

    try:
        validated_ratio = _validate_train_ratio(train_ratio)
        resolved_data = Path(data_path) if data_path is not None else get_data_path()
        resolved_models = Path(models_dir) if models_dir is not None else get_models_dir()

        champion_model, champion_version = _resolve_current_champion(
            resolved_models, tracking_uri=tracking_uri
        )
        champion_train_end = _resolve_champion_train_end(
            champion_version, resolved_models, tracking_uri=tracking_uri
        )

        raw_df = load_dataset(resolved_data)
        df_feat = engineer_features(raw_df)
        if len(df_feat) < 10:
            raise ValueError(f"Insufficient engineered rows for retraining: {len(df_feat)}")

        train_df, test_df = split_time_series_data(df_feat, train_ratio=validated_ratio)
        if train_df.empty or test_df.empty:
            raise ValueError("Chronological train/holdout split produced an empty partition.")

        holdout_start = pd.Timestamp(test_df["timestamp"].min())
        if holdout_start.tzinfo is not None:
            holdout_start = holdout_start.tz_convert(None)
        train_end = pd.Timestamp(train_df["timestamp"].max())
        if train_end.tzinfo is not None:
            train_end = train_end.tz_convert(None)

        if train_end >= holdout_start:
            raise ValueError("Temporal leakage detected: holdout window must start strictly after training cutoff.")
        if champion_train_end is not None and champion_train_end >= holdout_start:
            raise ValueError(
                "Temporal leakage detected: holdout window must start strictly after active champion training cutoff."
            )

        train_end_iso = train_end.isoformat()
        challenger_model, xgb_metrics = _train_challenger(train_df, test_df)

        X_holdout = test_df[XGB_FEATURE_COLUMNS]
        y_holdout = test_df["meter_reading"]

        champ_preds = np.asarray(champion_model.predict(X_holdout), dtype=float)
        chall_preds = np.asarray(challenger_model.predict(X_holdout), dtype=float)

        champion_mape = compute_holdout_mape(y_holdout, champ_preds)
        challenger_mape = compute_holdout_mape(y_holdout, chall_preds)
        xgb_metrics = {
            **xgb_metrics,
            "mape_percent": round(challenger_mape, 4),
            "target_mape_met": challenger_mape <= 10.0,
        }

        challenger_version = "local"
        if not mlflow_disabled() and mlflow_available():
            tracked_params = {}
            if hasattr(challenger_model, "get_params"):
                raw_params = challenger_model.get_params()
                for key in (
                    "n_estimators",
                    "max_depth",
                    "learning_rate",
                    "subsample",
                    "colsample_bytree",
                    "objective",
                    "random_state",
                ):
                    if key in raw_params:
                        tracked_params[key] = raw_params[key]
            tracked = track_training_run(
                model=challenger_model,
                params=tracked_params,
                metrics=xgb_metrics,
                features=list(XGB_FEATURE_COLUMNS),
                row_counts={
                    "dataset_rows": len(df_feat),
                    "train_rows": len(train_df),
                    "test_rows": len(test_df),
                },
                run_name=f"retrain_{trigger}",
                tracking_uri=tracking_uri,
                bootstrap_champion=False,
                tags={"train_end_timestamp": train_end_iso},
            )
            if tracked:
                challenger_version = str(tracked["version"])

        if challenger_mape < champion_mape:
            _verify_and_promote_challenger(
                challenger_model=challenger_model,
                challenger_version=challenger_version,
                champion_version=champion_version,
                models_dir=resolved_models,
                df_feat=df_feat,
                train_df=train_df,
                test_df=test_df,
                xgb_metrics=xgb_metrics,
                train_end_iso=train_end_iso,
                tracking_uri=tracking_uri,
            )
            outcome = "promoted"
            reason = None
            logger.info(
                "Retrain %s promoted challenger v%s over champion v%s (MAPE %.6f%% < %.6f%%).",
                resolved_run_id,
                challenger_version,
                champion_version,
                challenger_mape,
                champion_mape,
            )
        else:
            outcome = "rejected"
            reason = (
                f"Challenger MAPE ({challenger_mape:.6f}%) is not strictly lower than "
                f"champion MAPE ({champion_mape:.6f}%)."
            )
            logger.info(
                "Retrain %s rejected challenger v%s vs champion v%s (MAPE %.6f%% >= %.6f%%).",
                resolved_run_id,
                challenger_version,
                champion_version,
                challenger_mape,
                champion_mape,
            )
    except Exception as exc:
        outcome = "failed"
        reason = str(exc)
        logger.error("Retrain %s failed: %s", resolved_run_id, exc)
    finally:
        record: Dict[str, Any] = {
            "run_id": resolved_run_id,
            "timestamp": _utc_now_iso(),
            "trigger": trigger,
            "champion_version": champion_version,
            "challenger_version": challenger_version,
            "champion_mape": round(champion_mape, 6) if champion_mape is not None and np.isfinite(champion_mape) else None,
            "challenger_mape": round(challenger_mape, 6) if challenger_mape is not None and np.isfinite(challenger_mape) else None,
            "outcome": outcome,
            "reason": reason,
        }
        if signals is not None:
            record["signals"] = list(signals)
        try:
            _append_history(record, models_dir=resolved_models)
        except Exception as hist_exc:
            logger.error("Failed to persist retrain history for %s: %s", resolved_run_id, hist_exc)
            record["history_persisted"] = False
        finally:
            _retrain_lock.release()

    return record


def run_retrain(
    trigger: str = "manual",
    run_id: Optional[str] = None,
    data_path: Optional[Path] = None,
    models_dir: Optional[Path] = None,
    train_ratio: float = 0.8,
    tracking_uri: Optional[str] = None,
    signals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute one synchronous retrain + holdout evaluation + guarded promotion cycle.

    Callable directly as plain Python (AD-1, Story 4.9 scheduler, or tests).
    Always releases ``_retrain_lock`` in ``finally`` and persists a history record
    with outcome ``promoted``, ``rejected``, or ``failed``.
    """
    if not _retrain_lock.acquire(blocking=False):
        raise RetrainAlreadyRunningError("A retrain run is already in progress.")
    return _execute_retrain_locked(
        trigger=trigger,
        run_id=run_id,
        data_path=data_path,
        models_dir=models_dir,
        train_ratio=train_ratio,
        tracking_uri=tracking_uri,
        signals=signals,
    )


def start_retrain(
    trigger: str = "manual",
    data_path: Optional[Path] = None,
    models_dir: Optional[Path] = None,
    train_ratio: float = 0.8,
    tracking_uri: Optional[str] = None,
    signals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Atomically acquire the retrain lock, launch :func:`_execute_retrain_locked`
    in a daemon background thread, and return immediately with ``run_id`` and
    ``started_at``. Raises :class:`RetrainAlreadyRunningError` (HTTP 409) when
    a job is already active.
    """
    _validate_train_ratio(train_ratio)
    if not _retrain_lock.acquire(blocking=False):
        raise RetrainAlreadyRunningError("A retrain run is already in progress.")

    run_id = uuid.uuid4().hex[:12]
    started_at = _utc_now_iso()
    try:
        worker = threading.Thread(
            target=_execute_retrain_locked,
            kwargs={
                "trigger": trigger,
                "run_id": run_id,
                "data_path": data_path,
                "models_dir": models_dir,
                "train_ratio": train_ratio,
                "tracking_uri": tracking_uri,
                "signals": signals,
            },
            name=f"ecotrack-retrain-{run_id}",
            daemon=True,
        )
        worker.start()
    except Exception:
        _retrain_lock.release()
        raise

    return {
        "run_id": run_id,
        "status": "running",
        "trigger": trigger,
        "started_at": started_at,
    }
