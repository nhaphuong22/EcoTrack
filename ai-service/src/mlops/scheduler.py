"""
Automated drift-check and retraining scheduler for EcoTrack (Story 4.9 — FR25, PRD FR-5).

Plain-Python module (AD-1, no FastAPI dependency) using Python stdlib
``threading.Event`` and daemon ``threading.Thread``:
  - Runs the Story 4.6 drift check on a daily interval (or direct call in tests)
  - Persists ``drift_status.json`` in ``get_models_dir()`` for Story 4.10
  - Invokes Story 4.8's ``run_retrain()`` only when ``drift_detected`` is true,
    classifying ``trigger="mape"`` (rolling-MAPE-only) vs ``trigger="drift"``
    (distribution drift) and preserving ``triggered_signals`` in ``signals``.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.config import get_data_path, get_models_dir
from src.mlops import drift
from src.mlops.config import (
    get_drift_recent_path,
    get_scheduler_initial_delay_seconds,
    get_scheduler_interval_seconds,
    scheduler_enabled,
)
from src.mlops.retrain import (
    RetrainAlreadyRunningError,
    _atomic_write_bytes,
    _resolve_current_champion,
    _utc_now_iso,
    run_retrain,
)
from src.models.train_models import engineer_features, load_dataset, split_time_series_data

logger = logging.getLogger("MLOpsScheduler")

DRIFT_STATUS_FILENAME = "drift_status.json"

_drift_status_lock = threading.Lock()
_scheduler_lock = threading.Lock()
_stop_event: Optional[threading.Event] = None
_scheduler_thread: Optional[threading.Thread] = None


def _drift_status_path(models_dir: Optional[Path] = None) -> Path:
    base = Path(models_dir) if models_dir is not None else get_models_dir()
    return base / DRIFT_STATUS_FILENAME


def load_drift_status(models_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read the latest persisted drift check snapshot, or ``None`` if never run."""
    with _drift_status_lock:
        path = _drift_status_path(models_dir)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a JSON object in {path}")
        return data


def _save_drift_status(status: Dict[str, Any], models_dir: Optional[Path] = None) -> None:
    with _drift_status_lock:
        path = _drift_status_path(models_dir)
        payload = json.dumps(status, indent=2, allow_nan=False).encode("utf-8")
        _atomic_write_bytes(path, payload)


def _classify_trigger(triggered_signals: List[str]) -> str:
    """Return ``mape`` when only rolling_mape fired, else ``drift``."""
    return "mape" if triggered_signals == ["rolling_mape"] else "drift"


def _resolve_windows(
    reference_df: Optional[pd.DataFrame],
    recent_df: Optional[pd.DataFrame],
    data_path: Optional[Path],
    recent_path: Optional[Path],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    base_feat: Optional[pd.DataFrame] = None

    def _load_base_feat() -> pd.DataFrame:
        nonlocal base_feat
        if base_feat is None:
            resolved_data = Path(data_path) if data_path is not None else get_data_path()
            base_feat = engineer_features(load_dataset(resolved_data))
        return base_feat

    if reference_df is None:
        ref_df, _ = split_time_series_data(_load_base_feat(), train_ratio=0.8)
    else:
        ref_df = reference_df

    if recent_df is None:
        resolved_recent = Path(recent_path) if recent_path is not None else get_drift_recent_path()
        if resolved_recent is not None:
            rec_df = load_dataset(resolved_recent)
        else:
            # Compare against the unmodified baseline dataset when no separate recent capture
            # is configured (preventing false seasonal drift on static CSV startup while
            # drift._rolling_mape still scores the trailing 168h window).
            rec_df = _load_base_feat().copy()
    else:
        rec_df = recent_df

    return ref_df, rec_df


def _resolve_champion_if_scoped(
    champion_model: Any,
    models_dir: Optional[Path],
    resolved_models: Path,
    tracking_uri: Optional[str],
) -> Any:
    if champion_model is not None or (models_dir is None and tracking_uri is None):
        return champion_model
    try:
        model, _ = _resolve_current_champion(resolved_models, tracking_uri=tracking_uri)
        return model
    except Exception as exc:
        logger.warning(
            "No champion resolved from scoped models_dir/tracking_uri (%s: %s); skipping rolling MAPE.",
            type(exc).__name__,
            exc,
        )
        return None


def run_drift_check_and_retrain(
    reference_df: Optional[pd.DataFrame] = None,
    recent_df: Optional[pd.DataFrame] = None,
    champion_model: Any = None,
    data_path: Optional[Path] = None,
    recent_path: Optional[Path] = None,
    models_dir: Optional[Path] = None,
    tracking_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute one drift check + conditional guarded retrain cycle.

    Callable directly in tests or invoked periodically by the background scheduler.
    Always persists the latest drift check snapshot to ``drift_status.json``.
    """
    resolved_models = Path(models_dir) if models_dir is not None else get_models_dir()
    ref_df, rec_df = _resolve_windows(reference_df, recent_df, data_path, recent_path)
    scoped_champion = _resolve_champion_if_scoped(
        champion_model, models_dir, resolved_models, tracking_uri
    )
    drift_result = drift.check(ref_df, rec_df, champion_model=scoped_champion)

    retrain_triggered = False
    retrain_run_id: Optional[str] = None
    retrain_outcome: Optional[str] = None
    retrain_skipped_reason: Optional[str] = None
    trigger_used: Optional[str] = None

    triggered_signals = list(drift_result.get("triggered_signals") or [])
    try:
        if drift_result.get("drift_detected"):
            trigger_used = _classify_trigger(triggered_signals)
            try:
                record = run_retrain(
                    trigger=trigger_used,
                    data_path=data_path,
                    models_dir=resolved_models,
                    tracking_uri=tracking_uri,
                    signals=triggered_signals,
                )
                retrain_triggered = True
                retrain_run_id = record.get("run_id")
                retrain_outcome = record.get("outcome")
            except RetrainAlreadyRunningError as exc:
                logger.warning(
                    "Drift detected (%s) but retrain skipped because another run is already in progress: %s",
                    triggered_signals,
                    exc,
                )
                retrain_skipped_reason = "retrain_already_running"
    finally:
        snapshot: Dict[str, Any] = {
            "checked_at": _utc_now_iso(),
            **drift_result,
            "retrain_triggered": retrain_triggered,
            "retrain_trigger": trigger_used,
            "retrain_run_id": retrain_run_id,
            "retrain_outcome": retrain_outcome,
        }
        if retrain_skipped_reason is not None:
            snapshot["retrain_skipped_reason"] = retrain_skipped_reason
        _save_drift_status(snapshot, models_dir=resolved_models)

    return snapshot


def _scheduler_loop(
    stop_event: threading.Event,
    initial_delay: float,
    interval: float,
    check_fn: Callable[[], Any],
) -> None:
    if initial_delay > 0.0 and stop_event.wait(initial_delay):
        return
    while not stop_event.is_set():
        try:
            check_fn()
        except Exception:
            logger.exception("Scheduled drift check failed.")
        if stop_event.wait(interval):
            return


def is_scheduler_running() -> bool:
    """True when the background drift-check scheduler thread is currently alive."""
    with _scheduler_lock:
        return _scheduler_thread is not None and _scheduler_thread.is_alive()


def start_scheduler(
    check_fn: Optional[Callable[[], Any]] = None,
    initial_delay: Optional[float] = None,
    interval: Optional[float] = None,
    respect_config: bool = True,
) -> bool:
    """
    Start the stdlib background scheduler thread if enabled and not already running.
    Returns True if a new thread was started, False if disabled or already active.
    """
    global _stop_event, _scheduler_thread
    if respect_config and not scheduler_enabled():
        logger.info("MLOps drift-check scheduler disabled via configuration.")
        return False

    if initial_delay is None:
        delay = get_scheduler_initial_delay_seconds()
    else:
        delay_val = float(initial_delay)
        if not math.isfinite(delay_val):
            raise ValueError(f"initial_delay must be finite; got {initial_delay!r}")
        delay = max(0.0, delay_val)

    if interval is None:
        period = get_scheduler_interval_seconds()
    else:
        period_val = float(interval)
        if not math.isfinite(period_val):
            raise ValueError(f"interval must be finite; got {interval!r}")
        period = max(0.05, period_val)

    target_fn = check_fn or run_drift_check_and_retrain

    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return False
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_scheduler_loop,
            args=(stop_event, delay, period, target_fn),
            name="ecotrack-drift-scheduler",
            daemon=True,
        )
        _stop_event = stop_event
        _scheduler_thread = thread
        thread.start()
        logger.info(
            "Started MLOps drift-check scheduler (initial_delay=%.2fs, interval=%.2fs).",
            delay,
            period,
        )
        return True


def stop_scheduler(timeout: float = 5.0) -> None:
    """Signal the background scheduler thread to stop and wait up to ``timeout`` seconds."""
    global _stop_event, _scheduler_thread
    with _scheduler_lock:
        stop_event = _stop_event
        thread = _scheduler_thread

    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning(
                "MLOps drift-check scheduler thread did not exit within %.2fs timeout.",
                timeout,
            )
            return

    with _scheduler_lock:
        if _scheduler_thread is thread:
            _scheduler_thread = None
            _stop_event = None
