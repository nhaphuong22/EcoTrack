"""
Drift detection tests for Story 4.6 (FR24).

Covers: KS+PSI on meter_reading/air_temperature between a reference (training
split) and a recent window; no drift when the recent window is the unmodified
reference itself; drift on an injected HVAC-overrun scenario, surfaced via the
rolling 7-day MAPE signal; the champion-unavailable fallback (MAPE skipped,
not fatal); the PSI zero-bin epsilon path; and a short-recent-window MAPE.
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
    """No MLflow store and no local models_saved/ artifact either -> MAPE is skipped, not fatal."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{(tmp_path / 'absent.db').as_posix()}")
    monkeypatch.setattr(
        "src.models.train_models.get_default_paths",
        lambda: (tmp_path / "data.csv", tmp_path / "empty_models"),
    )
    reference_df, _test_df, _champion = _reference_and_champion()

    result = drift.check(reference_df, reference_df.copy())

    assert result["rolling_mape"] is None
    assert result["drift_detected"] is False


def test_shifted_column_triggers_ks_and_psi_signal():
    """A clear distribution shift on meter_reading alone (no champion) must trip the KS+PSI signal."""
    rng = np.random.RandomState(42)
    reference_df = pd.DataFrame(
        {
            "meter_reading": rng.normal(200, 10, size=300),
            "air_temperature": rng.normal(22, 2, size=300),
        }
    )
    recent_df = pd.DataFrame(
        {
            # Shifted well outside the reference range -> low KS p-value and high PSI.
            "meter_reading": rng.normal(500, 10, size=300),
            "air_temperature": rng.normal(22, 2, size=300),
        }
    )

    signal = drift._ks_and_psi(reference_df, recent_df, "meter_reading")

    assert signal["p_value"] < drift.DRIFT_KS_PVALUE_THRESHOLD
    assert signal["psi"] > drift.DRIFT_PSI_THRESHOLD


def test_ks_and_psi_handles_empty_column_without_crashing():
    reference_df = pd.DataFrame({"meter_reading": [100.0, 110.0, 120.0]})
    recent_df = pd.DataFrame({"meter_reading": [np.nan, np.nan, np.nan]})

    result = drift._ks_and_psi(reference_df, recent_df, "meter_reading")

    assert result == {"ks_statistic": 0.0, "p_value": 1.0, "psi": 0.0}


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
