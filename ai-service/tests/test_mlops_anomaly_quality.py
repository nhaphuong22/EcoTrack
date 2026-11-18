"""
Anomaly detector quality evaluation tests for Story 4.7 (FR27).

Covers: evaluate() scoring the HVAC-overrun and peak-spike demo scenarios
against their (newly added) is_injected_anomaly ground truth, the
zero-predicted-positives edge case (no zero-division warning/crash),
merge_into_metadata() preserving unrelated keys, and log_to_mlflow() against
a temporary store.
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

import src.mlops.run_anomaly_eval as anomaly_eval_cli
from src.data_pipeline.demo_scenarios import (
    generate_scenario_hvac_night_overrun,
    generate_scenario_peak_hour_spike,
)
from src.mlops import anomaly_quality
from src.models.train_models import ISO_FEATURE_COLUMNS, engineer_features, load_dataset

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


class _AlwaysNormalPredictor:
    """Stub detector that never flags anything as anomalous."""

    def predict(self, features):
        return np.ones(len(features))


def _tiny_detector():
    df = engineer_features(load_dataset(FIXTURE_CSV))
    model = IsolationForest(n_estimators=100, contamination=0.03, random_state=42, n_jobs=1)
    model.fit(df[ISO_FEATURE_COLUMNS])
    return model


def _labeled_scenario(generator):
    raw_fixture = pd.read_csv(FIXTURE_CSV)
    scenario_df = generator(base_df=raw_fixture).copy()
    scenario_df["timestamp"] = pd.to_datetime(scenario_df["timestamp"])
    return scenario_df


def test_evaluate_scores_hvac_overrun_scenario():
    scenario_df = _labeled_scenario(generate_scenario_hvac_night_overrun)
    expected_positive_count = int(scenario_df["is_injected_anomaly"].sum())
    assert expected_positive_count > 0, "scenario fixture did not inject any overrun rows"

    result = anomaly_quality.evaluate(scenario_df, _tiny_detector())

    assert result["positive_count"] == expected_positive_count
    assert result["total_count"] > 0
    for key in ("precision", "recall", "f1", "false_positive_rate"):
        assert 0.0 <= result[key] <= 1.0


def test_evaluate_scores_peak_spike_scenario():
    scenario_df = _labeled_scenario(generate_scenario_peak_hour_spike)
    expected_positive_count = int(scenario_df["is_injected_anomaly"].sum())
    assert expected_positive_count > 0, "scenario fixture did not inject any spike rows"

    result = anomaly_quality.evaluate(scenario_df, _tiny_detector())

    assert result["positive_count"] == expected_positive_count
    for key in ("precision", "recall", "f1", "false_positive_rate"):
        assert 0.0 <= result[key] <= 1.0


def test_evaluate_handles_zero_predicted_positives_without_crashing():
    """A detector that never flags anything must not raise on sklearn's
    zero-division (undefined precision) path."""
    scenario_df = _labeled_scenario(generate_scenario_hvac_night_overrun)

    result = anomaly_quality.evaluate(scenario_df, _AlwaysNormalPredictor())

    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0
    assert result["false_positive_rate"] == 0.0


def test_ensure_engineered_skips_when_markers_already_present():
    """An already-engineered frame must be returned as-is, not re-processed."""
    df = engineer_features(load_dataset(FIXTURE_CSV))
    df["is_injected_anomaly"] = False

    result = anomaly_quality._ensure_engineered(df)

    assert result is df


def test_evaluate_raises_clear_error_when_label_column_missing():
    unlabeled_df = pd.DataFrame({"meter_reading": [100.0], "air_temperature": [20.0]})

    with pytest.raises(ValueError, match="is_injected_anomaly"):
        anomaly_quality.evaluate(unlabeled_df, _AlwaysNormalPredictor())


def test_merge_into_metadata_raises_clear_error_when_file_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        anomaly_quality.merge_into_metadata(tmp_path / "does_not_exist.json", {})


def test_merge_into_metadata_preserves_other_keys(tmp_path):
    metadata_path = tmp_path / "model_metadata.json"
    metadata_path.write_text(json.dumps({"dataset_rows": 123, "xgboost_metrics": {"mape_percent": 5.0}}))

    anomaly_quality.merge_into_metadata(
        metadata_path, {"scenario_hvac_overrun": {"precision": 1.0, "recall": 0.5, "f1": 0.67, "false_positive_rate": 0.0}}
    )

    merged = json.loads(metadata_path.read_text())
    assert merged["dataset_rows"] == 123
    assert merged["xgboost_metrics"] == {"mape_percent": 5.0}
    assert merged["isolation_forest_quality"]["scenario_hvac_overrun"]["precision"] == 1.0


def test_log_to_mlflow_logs_metrics_and_returns_run_id(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    db = tmp_path / "mlflow.db"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str((tmp_path / "artifacts").as_posix()))
    monkeypatch.delenv("ECOTRACK_DISABLE_MLFLOW", raising=False)

    run_id = anomaly_quality.log_to_mlflow(
        {"scenario_hvac_overrun": {"precision": 1.0, "recall": 0.5, "f1": 0.67, "false_positive_rate": 0.01}},
        model_path="models_saved/isolation_forest.joblib",
    )

    assert run_id is not None
    from mlflow.tracking import MlflowClient

    run = MlflowClient().get_run(run_id)
    assert run.data.metrics["scenario_hvac_overrun_precision"] == pytest.approx(1.0)
    assert run.data.tags["evaluated_model_path"] == "models_saved/isolation_forest.joblib"


def test_log_to_mlflow_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")

    run_id = anomaly_quality.log_to_mlflow({"scenario_hvac_overrun": {"precision": 1.0}})

    assert run_id is None


def test_run_anomaly_eval_cli_end_to_end(tmp_path, monkeypatch):
    """CLI wiring: load artifact + scenarios -> evaluate -> merge metadata, fully offline."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    joblib.dump(_tiny_detector(), models_dir / "isolation_forest.joblib")
    metadata_path = models_dir / "model_metadata.json"
    metadata_path.write_text(json.dumps({"dataset_rows": 1}))

    # Keep the CLI offline: use the small committed fixture instead of the real production CSV.
    fixture_df = pd.read_csv(FIXTURE_CSV)
    monkeypatch.setattr(anomaly_eval_cli, "load_base_dataset", lambda *a, **k: fixture_df)
    monkeypatch.setenv("ECOTRACK_DISABLE_MLFLOW", "1")
    monkeypatch.setattr(sys, "argv", ["run_anomaly_eval.py", "--models-dir", str(models_dir)])

    anomaly_eval_cli.main()

    merged = json.loads(metadata_path.read_text())
    assert merged["dataset_rows"] == 1  # untouched
    quality = merged["isolation_forest_quality"]
    assert "scenario_hvac_overrun" in quality
    assert "scenario_peak_spike" in quality
    assert quality["scenario_hvac_overrun"]["positive_count"] > 0
