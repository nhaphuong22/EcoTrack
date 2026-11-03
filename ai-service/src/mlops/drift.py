"""
Data drift and accuracy-decay detection for EcoTrack (Story 4.6 — FR24).

Plain-Python module (AD-1, no FastAPI dependency): compares a reference window
(the champion's training split) against a recent window of readings on
``meter_reading`` and ``air_temperature`` via a KS test + PSI, plus the
champion's rolling 7-day MAPE scored directly on the recent window.

The champion is a feature-based regressor (not an autoregressive forecaster),
so its actual target and its predictable features coexist in any window of
readings -- no prediction log or new persistence is needed for the MAPE signal.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.metrics import mean_absolute_percentage_error

from src.mlops.config import (
    DRIFT_KS_PVALUE_THRESHOLD,
    DRIFT_MAPE_THRESHOLD_PERCENT,
    DRIFT_PSI_THRESHOLD,
)
from src.models.train_models import XGB_FEATURE_COLUMNS, engineer_features

logger = logging.getLogger("MLOpsDrift")

DRIFT_COLUMNS: tuple = ("meter_reading", "air_temperature")
_PSI_BINS = 10
_PSI_EPSILON = 1e-4
_ROLLING_WINDOW_HOURS = 7 * 24


_ENGINEERED_MARKERS = ("lag_1h", "lag_24h", "hour_sin", "hour_cos")


def _ensure_engineered(df: pd.DataFrame) -> pd.DataFrame:
    """Runs engineer_features() when lag/calendar columns are absent, so a raw
    ``timestamp, meter_reading, air_temperature`` frame (e.g. a demo scenario
    CSV) works directly, same as an already-engineered training frame.

    Checks every marker column engineer_features() adds (not just one), so a
    raw frame that happens to already have a same-named column (e.g. its own
    ``hour`` field) is not mistaken for an already-engineered frame.
    """
    if all(col in df.columns for col in _ENGINEERED_MARKERS):
        return df
    return engineer_features(df)


def _psi(reference: pd.Series, recent: pd.Series, bins: int = _PSI_BINS) -> float:
    """Population Stability Index between two 1-D samples.

    Bin edges are quantiles of the reference sample (outer edges widened to
    +/-inf so out-of-range recent values still fall in a bin). When the
    reference is low-cardinality or heavily tied, quantile edges collapse and
    would silently zero out PSI resolution; this falls back to equal-width
    bins over the reference's value range instead of losing resolution. A
    small epsilon is added to every bin's share before the log ratio so an
    empty bin in either sample never divides by zero or takes log(0).
    """
    ref = reference.dropna().to_numpy()
    rec = recent.dropna().to_numpy()
    if ref.size == 0 or rec.size == 0:
        return 0.0

    lo, hi = float(ref.min()), float(ref.max())
    if lo == hi:
        return 0.0  # Reference is perfectly constant; nothing to compare against.

    edges = np.quantile(ref, np.linspace(0, 1, bins + 1))
    if np.unique(edges).size < bins + 1:
        edges = np.linspace(lo, hi, bins + 1)
    edges[0], edges[-1] = -np.inf, np.inf

    ref_counts, _ = np.histogram(ref, bins=edges)
    rec_counts, _ = np.histogram(rec, bins=edges)
    ref_share = ref_counts / ref_counts.sum() + _PSI_EPSILON
    rec_share = rec_counts / rec_counts.sum() + _PSI_EPSILON
    return float(np.sum((rec_share - ref_share) * np.log(rec_share / ref_share)))


def _ks_and_psi(reference_df: pd.DataFrame, recent_df: pd.DataFrame, column: str) -> Dict[str, Any]:
    ref = reference_df[column].dropna() if column in reference_df.columns else pd.Series(dtype=float)
    rec = recent_df[column].dropna() if column in recent_df.columns else pd.Series(dtype=float)
    if ref.empty or rec.empty:
        # The column is entirely missing or all-NaN in either window (e.g. a
        # sensor outage) -- cannot be judged for drift. Flagged distinctly
        # from a genuine "checked, no drift" result rather than crashing
        # ks_2samp on an empty sample.
        return {"ks_statistic": 0.0, "p_value": 1.0, "psi": 0.0, "ref_n": len(ref), "rec_n": len(rec), "insufficient_data": True}
    ks_result = ks_2samp(ref, rec)
    return {
        "ks_statistic": float(ks_result.statistic),
        "p_value": float(ks_result.pvalue),
        "psi": _psi(ref, rec),
        "ref_n": int(len(ref)),
        "rec_n": int(len(rec)),
        "insufficient_data": False,
    }


def _rolling_mape(
    recent_df: pd.DataFrame, champion_model: Any, window_hours: int = _ROLLING_WINDOW_HOURS
) -> Optional[Dict[str, Any]]:
    """MAPE of champion_model.predict() against actual meter_reading, over the
    last window_hours rows of recent_df (or all of it when shorter)."""
    if champion_model is None or recent_df.empty:
        return None
    window_df = recent_df.tail(window_hours)
    try:
        predictions = champion_model.predict(window_df[XGB_FEATURE_COLUMNS])
    except Exception as exc:
        # An incompatible/unusable model must not take down the whole check --
        # the KS/PSI signals are still valid on their own.
        logger.warning("Champion model could not score the recent window (%s); skipping rolling MAPE.", exc)
        return None
    mape = float(mean_absolute_percentage_error(window_df["meter_reading"], predictions) * 100)
    return {"mape_percent": round(mape, 2), "window_hours": len(window_df)}


def _resolve_champion_for_drift() -> Optional[Any]:
    """
    Best-effort champion resolution for the rolling-MAPE signal only.

    Reuses the same champion-or-fallback path serving uses (MLflow champion,
    else ``models_saved/``, both through :func:`src.config.get_models_dir` so
    an ``ECOTRACK_MODELS_DIR`` override is honoured exactly like serving
    honours it). A drift check is a monitoring tool, not the serving path: it
    must never raise just because no model could be resolved. Any failure (no
    champion, broken champion, no local artifact either) is logged -- with
    the exception type, so "unavailable" and "broken" are distinguishable in
    the logs even though both end up skipping the signal the same way -- and
    treated as "skip the rolling-MAPE signal"; the KS/PSI signals above are
    still reported either way.
    """
    try:
        from src.config import get_models_dir
        from src.data_pipeline.serving_frame import _load_champion_forecaster_or_fallback

        return _load_champion_forecaster_or_fallback(get_models_dir() / "xgboost_forecaster.joblib")
    except Exception as exc:
        logger.warning(
            "No champion model available for the rolling-MAPE signal (%s: %s); skipping it.",
            type(exc).__name__,
            exc,
        )
        return None


def check(
    reference_df: pd.DataFrame,
    recent_df: pd.DataFrame,
    champion_model: Any = None,
) -> Dict[str, Any]:
    """
    Compares ``reference_df`` (the champion's training split) against
    ``recent_df`` (any window of readings shaped like training data) on
    ``meter_reading`` and ``air_temperature``, plus the champion's rolling
    7-day MAPE on ``recent_df``.

    ``drift_detected`` is true when a column's KS p-value drops below
    ``DRIFT_KS_PVALUE_THRESHOLD`` *and* its PSI exceeds ``DRIFT_PSI_THRESHOLD``,
    or when the rolling MAPE exceeds ``DRIFT_MAPE_THRESHOLD_PERCENT``.
    ``triggered_signals`` names exactly which signal(s) tripped it. The
    returned ``thresholds`` echoes the three values actually applied (they
    are env-configurable), and each entry in ``signals`` carries ``ref_n``/
    ``rec_n``/``insufficient_data`` so a result can be judged for statistical
    power or told apart from "checked, genuinely no drift" later.

    When ``champion_model`` is omitted, it is resolved the same way serving
    resolves it (MLflow champion, else ``models_saved/``) via
    :func:`_resolve_champion_for_drift`, which never raises: any resolution
    failure simply skips the rolling-MAPE signal (``None``) rather than
    failing the whole check.
    """
    reference_df = _ensure_engineered(reference_df)
    recent_df = _ensure_engineered(recent_df)

    signals: Dict[str, Dict[str, float]] = {}
    triggered: List[str] = []
    for column in DRIFT_COLUMNS:
        result = _ks_and_psi(reference_df, recent_df, column)
        signals[column] = result
        if result["p_value"] < DRIFT_KS_PVALUE_THRESHOLD and result["psi"] > DRIFT_PSI_THRESHOLD:
            triggered.append(column)

    if champion_model is None:
        champion_model = _resolve_champion_for_drift()

    rolling_mape = _rolling_mape(recent_df, champion_model)
    if rolling_mape is not None and rolling_mape["mape_percent"] > DRIFT_MAPE_THRESHOLD_PERCENT:
        triggered.append("rolling_mape")

    drift_detected = bool(triggered)
    if drift_detected:
        logger.warning("Drift detected: signals=%s", triggered)

    return {
        "drift_detected": drift_detected,
        "triggered_signals": triggered,
        "signals": signals,
        "rolling_mape": rolling_mape,
        "thresholds": {
            "ks_pvalue": DRIFT_KS_PVALUE_THRESHOLD,
            "psi": DRIFT_PSI_THRESHOLD,
            "mape_percent": DRIFT_MAPE_THRESHOLD_PERCENT,
        },
    }
