"""
Consolidated MLOps status aggregation for EcoTrack (Story 4.10 — FR26).

Plain-Python module (AD-1, no FastAPI dependency) aggregating champion metadata,
latest drift check snapshot, anomaly detector quality metrics, retraining
history (newest first), and benchmark results into a JSON-safe HTTP 200 payload.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import get_models_dir
from src.mlops.config import get_benchmark_results_path
from src.mlops.retrain import RETRAIN_HISTORY_FILENAME, _history_lock
from src.mlops.scheduler import DRIFT_STATUS_FILENAME, _drift_status_lock, _optional_path, _optional_str
from src.mlops.tracking import get_champion_metadata

logger = logging.getLogger("MLOpsStatus")


def _reject_non_finite(token: str) -> Any:
    raise ValueError(f"Non-finite JSON constant {token!r}")


def _read_json_strict(path: Path, expected_type: type) -> Tuple[Optional[Any], Optional[str]]:
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_non_finite)
        if not isinstance(data, expected_type):
            raise ValueError(f"Expected {expected_type.__name__} in {path.name}")
        return data, None
    except Exception as exc:
        logger.warning("Failed to read %s (%s: %s)", path, type(exc).__name__, exc)
        return None, f"{type(exc).__name__}: {exc}"


def _normalize_utc_iso(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _history_sort_key(entry: Dict[str, Any]) -> Tuple[int, float]:
    raw = entry.get("timestamp")
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (1, dt.timestamp())
        except (ValueError, OverflowError, OSError):
            pass
    return (0, float("-inf"))


def _resolve_champion_summary(
    resolved_models: Path,
    resolved_tracking: Optional[str],
    metadata: Optional[Dict[str, Any]],
    meta_err: Optional[str],
    errors: Dict[str, str],
) -> Dict[str, Any]:
    try:
        mlflow_champ = get_champion_metadata(tracking_uri=resolved_tracking)
    except Exception as exc:
        logger.warning("Unexpected MLflow champion inspection error (%s: %s)", type(exc).__name__, exc)
        mlflow_champ = {
            "status": "broken",
            "version": None,
            "trained_at": None,
            "metrics": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    status = mlflow_champ["status"]

    if status == "resolved":
        return {
            "status": "resolved",
            "source": "mlflow",
            "version": mlflow_champ["version"],
            "trained_at": mlflow_champ["trained_at"],
            "metrics": mlflow_champ["metrics"],
            "error": None,
        }

    if status == "broken":
        errors["champion"] = mlflow_champ["error"] or "Champion model unavailable."
        return {
            "status": "broken",
            "source": "mlflow",
            "version": mlflow_champ["version"],
            "trained_at": None,
            "metrics": None,
            "error": errors["champion"],
        }

    xgb_exists = (resolved_models / "xgboost_forecaster.joblib").is_file()
    champ_errors: List[str] = []
    if meta_err:
        champ_errors.append(meta_err)

    xgb_metrics: Optional[Dict[str, Any]] = None
    trained_at: Optional[str] = None
    if isinstance(metadata, dict):
        if "xgboost_metrics" in metadata:
            raw_xgb_metrics = metadata["xgboost_metrics"]
            if raw_xgb_metrics is None or isinstance(raw_xgb_metrics, dict):
                xgb_metrics = raw_xgb_metrics
            else:
                champ_errors.append("ValueError: Expected dict for xgboost_metrics")
        raw_ts = metadata.get("train_end_timestamp")
        if raw_ts is not None and (not isinstance(raw_ts, str) or raw_ts.strip()):
            trained_at = _normalize_utc_iso(raw_ts)
            if trained_at is None:
                logger.warning("Ignoring malformed train_end_timestamp in model_metadata.json: %r", raw_ts)
                champ_errors.append("ValueError: Invalid train_end_timestamp in model_metadata.json")

    champ_err = "; ".join(champ_errors) if champ_errors else None
    if champ_err:
        errors["champion"] = champ_err

    if xgb_exists:
        return {
            "status": "fallback",
            "source": "local",
            "version": "local",
            "trained_at": trained_at,
            "metrics": xgb_metrics,
            "error": champ_err,
        }

    return {
        "status": "unavailable",
        "source": None,
        "version": None,
        "trained_at": None,
        "metrics": None,
        "error": champ_err,
    }


def get_mlops_status(
    models_dir: Optional[Path | str] = None,
    tracking_uri: Optional[str] = None,
    benchmark_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Aggregate current MLOps model health into one JSON-serializable summary dict.

    Missing artifacts resolve to ``None`` (or ``[]`` for ``retrain_history``);
    corrupt persisted JSON files are logged and isolated per section in ``errors``.
    """
    resolved_models = _optional_path(models_dir) or get_models_dir()
    resolved_benchmark = _optional_path(benchmark_path) or get_benchmark_results_path()
    resolved_tracking = _optional_str(tracking_uri)
    errors: Dict[str, str] = {}

    metadata, meta_err = _read_json_strict(resolved_models / "model_metadata.json", dict)
    champion = _resolve_champion_summary(
        resolved_models=resolved_models,
        resolved_tracking=resolved_tracking,
        metadata=metadata,
        meta_err=meta_err,
        errors=errors,
    )

    if meta_err:
        anomaly_quality = None
        errors["anomaly_quality"] = meta_err
    elif isinstance(metadata, dict) and "isolation_forest_quality" in metadata:
        raw_aq = metadata["isolation_forest_quality"]
        if raw_aq is None or isinstance(raw_aq, dict):
            anomaly_quality = raw_aq
        else:
            anomaly_quality = None
            errors["anomaly_quality"] = "ValueError: Expected dict for isolation_forest_quality"
    else:
        anomaly_quality = None

    with _drift_status_lock:
        drift_data, drift_err = _read_json_strict(resolved_models / DRIFT_STATUS_FILENAME, dict)
    if drift_err:
        errors["drift"] = drift_err

    with _history_lock:
        hist_data, hist_err = _read_json_strict(resolved_models / RETRAIN_HISTORY_FILENAME, list)
    if hist_err:
        retrain_history: List[Dict[str, Any]] = []
        errors["retrain_history"] = hist_err
    elif hist_data is None:
        retrain_history = []
    elif not all(isinstance(item, dict) for item in hist_data):
        retrain_history = []
        errors["retrain_history"] = "ValueError: Expected list of objects in retrain_history.json"
    else:
        retrain_history = sorted(hist_data, key=_history_sort_key, reverse=True)

    benchmark_data, bench_err = _read_json_strict(resolved_benchmark, dict)
    if bench_err:
        errors["benchmark"] = bench_err

    return {
        "champion": champion,
        "drift": drift_data,
        "anomaly_quality": anomaly_quality,
        "retrain_history": retrain_history,
        "benchmark": benchmark_data,
        "errors": errors,
    }
