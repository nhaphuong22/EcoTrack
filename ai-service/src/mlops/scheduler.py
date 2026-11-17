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
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.config import get_data_path, get_models_dir
from src.mlops import drift
from src.mlops.config import (
    DRIFT_STATUS_FILENAME,
    DRIFT_STATUS_LOCK as _drift_status_lock,
    get_drift_recent_path,
    get_scheduler_initial_delay_seconds,
    get_scheduler_interval_seconds,
    optional_path as _optional_path,
    optional_str as _optional_str,
    scheduler_enabled,
    validate_duration_seconds,
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

_scheduler_lock = threading.Lock()
_stop_event: Optional[threading.Event] = None
_scheduler_thread: Optional[threading.Thread] = None


def _drift_status_path(models_dir: Optional[Path | str] = None) -> Path:
    resolved = _optional_path(models_dir)
    base = resolved if resolved is not None else get_models_dir()
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
    data_path: Optional[Path | str],
    recent_path: Optional[Path | str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    base_feat: Optional[pd.DataFrame] = None

    def _load_base_feat() -> pd.DataFrame:
        nonlocal base_feat
        if base_feat is None:
            normalized_data = _optional_path(data_path)
            resolved_data = normalized_data if normalized_data is not None else get_data_path()
            base_feat = engineer_features(load_dataset(resolved_data))
        return base_feat

    if reference_df is None:
        ref_df, _ = split_time_series_data(_load_base_feat(), train_ratio=0.8)
    else:
        ref_df = reference_df

    if recent_df is None:
        normalized_recent = _optional_path(recent_path)
        resolved_recent = (
            normalized_recent if normalized_recent is not None else get_drift_recent_path()
        )
        if resolved_recent is not None:
            rec_df = load_dataset(resolved_recent)
            if len(rec_df) <= 24:
                logger.warning(
                    "Recent drift dataset %s has only %d row(s); lag_24h feature engineering drops up to 24 rows, so rolling_mape may be skipped.",
                    resolved_recent,
                    len(rec_df),
                )
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
    is_scoped: bool,
    resolved_models: Path,
    tracking_uri: Optional[str],
) -> Tuple[Any, bool]:
    if champion_model is not None or not is_scoped:
        return champion_model, champion_model is None
    try:
        model, _ = _resolve_current_champion(resolved_models, tracking_uri=tracking_uri)
        return model, False
    except Exception as exc:
        logger.warning(
            "No champion resolved from scoped models_dir/tracking_uri (%s: %s); skipping rolling MAPE.",
            type(exc).__name__,
            exc,
        )
        return None, False


def run_drift_check_and_retrain(
    reference_df: Optional[pd.DataFrame] = None,
    recent_df: Optional[pd.DataFrame] = None,
    champion_model: Any = None,
    data_path: Optional[Path | str] = None,
    recent_path: Optional[Path | str] = None,
    models_dir: Optional[Path | str] = None,
    tracking_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute one drift check + conditional guarded retrain cycle.

    Callable directly in tests or invoked periodically by the background scheduler.
    Always persists the latest drift check snapshot to ``drift_status.json``.
    """
    normalized_models = _optional_path(models_dir)
    normalized_data = _optional_path(data_path)
    normalized_tracking = _optional_str(tracking_uri)
    is_scoped = normalized_models is not None or normalized_tracking is not None
    resolved_models = normalized_models if normalized_models is not None else get_models_dir()

    ref_df, rec_df = _resolve_windows(reference_df, recent_df, normalized_data, recent_path)
    scoped_champion, resolve_global = _resolve_champion_if_scoped(
        champion_model, is_scoped, resolved_models, normalized_tracking
    )
    drift_result = drift.check(
        ref_df,
        rec_df,
        champion_model=scoped_champion,
        resolve_champion=resolve_global,
    )

    retrain_triggered = False
    retrain_run_id: Optional[str] = None
    retrain_outcome: Optional[str] = None
    retrain_skipped_reason: Optional[str] = None
    trigger_used: Optional[str] = None

    triggered_signals = list(drift_result.get("triggered_signals") or [])
    try:
        if drift_result.get("drift_detected"):
            candidate_trigger = _classify_trigger(triggered_signals)
            try:
                record = run_retrain(
                    trigger=candidate_trigger,
                    data_path=normalized_data,
                    models_dir=resolved_models,
                    tracking_uri=normalized_tracking,
                    signals=triggered_signals,
                )
                retrain_triggered = True
                trigger_used = candidate_trigger
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


def _wait_interruptible(stop_event: threading.Event, seconds: float) -> bool:
    """Wait up to ``seconds`` (chunked under ``threading.TIMEOUT_MAX``); return True if stopped."""
    remaining = seconds
    max_chunk = max(1.0, float(threading.TIMEOUT_MAX) - 1.0)
    while remaining > 0.0:
        chunk = min(remaining, max_chunk)
        if stop_event.wait(chunk):
            return True
        remaining -= chunk
    return stop_event.is_set()


def _scheduler_loop(
    stop_event: threading.Event,
    initial_delay: float,
    interval: float,
    check_fn: Callable[[], Any],
) -> None:
    if initial_delay > 0.0 and _wait_interruptible(stop_event, initial_delay):
        return
    while not stop_event.is_set():
        try:
            check_fn()
        except Exception:
            logger.exception("Scheduled drift check failed.")
        if _wait_interruptible(stop_event, interval):
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

    delay = (
        get_scheduler_initial_delay_seconds()
        if initial_delay is None
        else validate_duration_seconds(initial_delay, "initial_delay", minimum=0.0, allow_zero=True)
    )
    period = (
        get_scheduler_interval_seconds()
        if interval is None
        else validate_duration_seconds(interval, "interval", minimum=0.05, allow_zero=False)
    )

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
        thread.start()
        _stop_event = stop_event
        _scheduler_thread = thread
        logger.info(
            "Started MLOps drift-check scheduler (initial_delay=%.2fs, interval=%.2fs).",
            delay,
            period,
        )
        return True


def stop_scheduler(timeout: float = 5.0) -> None:
    """Signal the background scheduler thread to stop and wait up to ``timeout`` seconds."""
    global _stop_event, _scheduler_thread
    wait_timeout = validate_duration_seconds(timeout, "timeout", minimum=0.0, allow_zero=True)
    with _scheduler_lock:
        stop_event = _stop_event
        thread = _scheduler_thread

    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        if thread is threading.current_thread():
            return
        max_chunk = max(1.0, float(threading.TIMEOUT_MAX) - 1.0)
        thread.join(timeout=min(wait_timeout, max_chunk))
        if thread.is_alive():
            logger.warning(
                "MLOps drift-check scheduler thread did not exit within %.2fs timeout.",
                wait_timeout,
            )
            return

    with _scheduler_lock:
        if _scheduler_thread is thread:
            _scheduler_thread = None
            _stop_event = None
            _stop_event = None
