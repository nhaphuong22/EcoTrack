"""
Drift detection tests for Story 4.6 (FR24).

Covers: the KS+PSI signal end-to-end through check() (isolated from MAPE);
no drift when the recent window is the unmodified reference itself; drift on
an injected HVAC-overrun scenario, surfaced via the rolling 7-day MAPE signal;
multiple signals firing simultaneously; champion resolution failures (no
champion anywhere, and a broken champion artifact) skipping MAPE without
being fatal; the PSI low-cardinality/zero-bin fallback; an entirely-missing
column; and a short-recent-window MAPE.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from src.data_pipeline.demo_scenarios import generate_scenario_hvac_night_overrun
from src.mlops import drift
from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
)

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
ANOMALY_THRESHOLD_KWH = 500.0  # scenario injects ~750 kWh against a ~230 kWh baseline


class _ExactPredictor:
    """Stub champion that always "predicts" the actual values it was built
    with, i.e. 0% MAPE -- used to isolate the KS/PSI signal from MAPE."""

    def __init__(self, actual):
        self._actual = actual

    def predict(self, _features):
        return self._actual


class _ConstantPredictor:
    """Stub champion whose prediction is always far from the actual value --
    used to force a high rolling MAPE regardless of input features."""

    def predict(self, features):
        return np.full(len(features), 50.0)


def _reference_and_champion():
    """Training split (reference window) + a champion fit on it, plus the held-out test split."""
    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)
    model = xgb.XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.1, random_state=42, n_jobs=1)
    model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"])
    return train_df, test_df, model


def test_unmodified_reference_reports_no_drift():
    """The reference window checked against itself is the deterministic no-drift case."""
    reference_df, _test_df, champion = _reference_and_champion()

    result = drift.check(reference_df, reference_df.copy(), champion_model=champion)

    assert result["drift_detected"] is False
    assert result["triggered_signals"] == []
    assert result["rolling_mape"] is not None
    assert result["rolling_mape"]["mape_percent"] <= 15.0
    assert result["thresholds"] == {
        "ks_pvalue": drift.DRIFT_KS_PVALUE_THRESHOLD,
        "psi": drift.DRIFT_PSI_THRESHOLD,
        "mape_percent": drift.DRIFT_MAPE_THRESHOLD_PERCENT,
    }


def test_check_triggers_ks_and_psi_signal_independent_of_mape():
    """A shifted feature column (air_temperature) trips the KS+PSI gate through
    check() itself, with a champion deliberately scored at ~0% MAPE so the
    rolling-MAPE signal cannot also fire -- isolating the KS+PSI path."""
    rng = np.random.RandomState(11)
    reference_df, _test_df, _champion = _reference_and_champion()

    recent_df = reference_df.copy()
    recent_df["air_temperature"] = rng.normal(80, 2, size=len(recent_df))  # far outside the training range

    tail_df = recent_df.tail(7 * 24)
    perfect_champion = _ExactPredictor(tail_df["meter_reading"].to_numpy())

    result = drift.check(reference_df, recent_df, champion_model=perfect_champion)

    assert result["drift_detected"] is True
    assert result["triggered_signals"] == ["air_temperature"]
    assert result["rolling_mape"]["mape_percent"] == 0.0


def test_check_reports_multiple_simultaneous_signals():
    """A shifted target column plus a badly-wrong champion must report both
    signals together, with no duplicate entries in triggered_signals."""
    rng = np.random.RandomState(7)
    reference_df, _test_df, _champion = _reference_and_champion()

    recent_df = reference_df.copy()
    recent_df["meter_reading"] = rng.normal(900, 10, size=len(recent_df))

    result = drift.check(reference_df, recent_df, champion_model=_ConstantPredictor())

    assert result["drift_detected"] is True
    assert "meter_reading" in result["triggered_signals"]
    assert "rolling_mape" in result["triggered_signals"]
    assert len(result["triggered_signals"]) == len(set(result["triggered_signals"]))


def test_hvac_overrun_scenario_reports_drift_via_rolling_mape():
    reference_df, _test_df, champion = _reference_and_champion()

    raw_fixture = pd.read_csv(FIXTURE_CSV)
    scenario_df = generate_scenario_hvac_night_overrun(base_df=raw_fixture)
    scenario_df = scenario_df.copy()
    scenario_df["timestamp"] = pd.to_datetime(scenario_df["timestamp"])

    anomalous = scenario_df[scenario_df["meter_reading"] > ANOMALY_THRESHOLD_KWH]
    assert not anomalous.empty, "scenario fixture did not inject an overrun above the test threshold"
    anomaly_start = anomalous.index.min()
    anomaly_end = anomalous.index.max()

    # Keep a short lead-in before the anomaly so the 8 injected hours dominate the
    # recent window once engineer_features() drops the first 24 (lag) rows.
    recent_raw = scenario_df.iloc[max(0, anomaly_start - 40): anomaly_end + 1]

    result = drift.check(reference_df, recent_raw, champion_model=champion)

    assert result["drift_detected"] is True
    assert "rolling_mape" in result["triggered_signals"]
    assert result["rolling_mape"]["mape_percent"] > 15.0


def test_no_champion_available_skips_mape_signal(tmp_path, monkeypatch):
    """No MLflow store and no local models_saved/ artifact either -> MAPE is skipped, not fatal.

    ECOTRACK_MODELS_DIR is the real override point (src.config.get_models_dir(),
    the same one serving_frame.py/main.py honour), so this also pins the fix
    that drift resolution must use it instead of the hardcoded default.
    """
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'absent.db').as_posix()}")
    monkeypatch.setenv("ECOTRACK_MODELS_DIR", str((tmp_path / "empty_models").as_posix()))
    reference_df, _test_df, _champion = _reference_and_champion()

    result = drift.check(reference_df, reference_df.copy())

    assert result["rolling_mape"] is None
    assert result["drift_detected"] is False


def test_broken_champion_artifact_skips_mape_signal_not_fatal(monkeypatch):
    """Alias resolves but the artifact is broken (ChampionArtifactError, wrapped
    as ModelArtifactError by the shared fallback helper) -> still not fatal."""
    from src.mlops.tracking import ChampionArtifactError

    def _broken(*_args, **_kwargs):
        raise ChampionArtifactError("artifact corrupt", version="3")

    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)
    monkeypatch.setattr("src.mlops.tracking.load_champion_forecaster", _broken)

    reference_df, _test_df, _champion = _reference_and_champion()
    result = drift.check(reference_df, reference_df.copy())

    assert result["rolling_mape"] is None
    assert result["drift_detected"] is False


def test_ensure_engineered_requires_all_markers_not_just_lag_1h_and_hour():
    """A partially-engineered frame (has lag_1h and hour, but not lag_24h/
    hour_sin/hour_cos) must still be re-engineered -- the old check (lag_1h
    AND hour only) would have returned it as-is and broken the later
    XGB_FEATURE_COLUMNS lookup on the missing columns."""
    raw = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=48, freq="h"),
            "meter_reading": np.linspace(100, 150, 48),
            "air_temperature": np.linspace(18, 22, 48),
            "hour": 0,
            "lag_1h": 0.0,
        }
    )

    engineered = drift._ensure_engineered(raw)

    assert set(XGB_FEATURE_COLUMNS).issubset(engineered.columns)


def test_ks_and_psi_handles_missing_column_without_crashing():
    reference_df = pd.DataFrame({"meter_reading": [100.0, 110.0, 120.0]})
    recent_df = pd.DataFrame({"meter_reading": [np.nan, np.nan, np.nan]})

    result = drift._ks_and_psi(reference_df, recent_df, "meter_reading")

    assert result["insufficient_data"] is True
    assert result == {
        "ks_statistic": 0.0,
        "p_value": 1.0,
        "psi": 0.0,
        "ref_n": 3,
        "rec_n": 0,
        "insufficient_data": True,
    }

    # Entirely absent column (not just all-NaN) must degrade the same way, not KeyError.
    other_df = pd.DataFrame({"something_else": [1.0, 2.0, 3.0]})
    result_missing = drift._ks_and_psi(reference_df, other_df, "meter_reading")
    assert result_missing["insufficient_data"] is True


def test_psi_falls_back_to_equal_width_bins_when_quantiles_collapse():
    """A low-cardinality reference (ties at every quantile) must not silently
    report PSI=0 for a clearly shifted recent sample."""
    reference = pd.Series([100.0] * 180 + [101.0] * 20)  # 9 ties per quantile decile
    recent = pd.Series(np.random.RandomState(2).normal(140, 2, size=200))

    psi = drift._psi(reference, recent)

    assert np.isfinite(psi)
    assert psi > drift.DRIFT_PSI_THRESHOLD


def test_psi_zero_bin_does_not_raise_or_divide_by_zero():
    reference = pd.Series(np.random.RandomState(0).normal(100, 5, size=200))
    # Entirely above the reference range -> the lowest reference bins are empty in `recent`.
    recent = pd.Series(np.random.RandomState(1).normal(140, 5, size=200))

    psi = drift._psi(reference, recent)

    assert np.isfinite(psi)
    assert psi > 0


def test_rolling_mape_uses_whatever_window_is_shorter_than_seven_days():
    _reference_df, test_df, champion = _reference_and_champion()
    short_recent = test_df.tail(10)

    result = drift._rolling_mape(short_recent, champion)

    assert result is not None
    assert result["window_hours"] == 10


def test_rolling_mape_returns_none_when_champion_predict_raises():
    """A model incompatible with the given features must not crash check();
    the KS/PSI signals still need to be usable on their own."""

    class _BrokenPredictor:
        def predict(self, _features):
            raise ValueError("incompatible feature shape")

    _reference_df, test_df, _champion = _reference_and_champion()

    result = drift._rolling_mape(test_df.tail(10), _BrokenPredictor())

    assert result is None
