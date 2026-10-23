"""
Unit tests for the Story 4.4 benchmark report generator.

Uses synthetic artifacts (no model training) to keep the report logic isolated and fast:
- Happy path: four PNGs + REPORT.md + valid results.json written.
- Recommendation names a served model and reports best-at-1h / best-at-24h.
- Deterministic tie-break (lower latency, then smaller size).
- Missing artifact: generate_report raises FileNotFoundError; the CLI exits non-zero.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiments.benchmark import run_report as run_report_mod
from experiments.benchmark.benchmark import (
    BENCHMARK_COLUMNS,
    HORIZON_COLUMNS,
    PREDICTION_COLUMNS,
)
from experiments.benchmark.report import (
    CHART_ACTUAL_VS_PREDICTED,
    CHART_ERROR_BY_HOUR,
    CHART_ERROR_VS_HORIZON,
    CHART_METRIC_COMPARISON,
    compute_recommendation,
    generate_report,
    load_artifacts,
    render_actual_vs_predicted,
)

MODELS = ["seasonal_naive", "xgboost", "sarimax", "lstm"]
MODEL_BASE_MAE = {"seasonal_naive": 150.0, "xgboost": 40.0, "sarimax": 78.0, "lstm": 55.0}


def _write_artifacts(tmp_path: Path):
    """Writes synthetic results.csv, results_by_horizon.csv and predictions.parquet."""
    results = pd.DataFrame(
        {
            "model": MODELS,
            "mae_kwh": [MODEL_BASE_MAE[m] for m in MODELS],
            "rmse_kwh": [MODEL_BASE_MAE[m] * 1.3 for m in MODELS],
            "mape_percent": [24.0, 8.0, 15.0, 11.0],
            "r2": [0.71, 0.978, 0.90, 0.95],
            "training_time_s": [0.0, 2.0, 30.0, 100.0],
            "mean_inference_latency_ms": [0.01, 0.05, 0.2, 0.5],
            "model_file_size_bytes": [500, 200000, 80000, 300000],
            "train_window_hours": [1000, 1000, 336, 900],
        }
    )[BENCHMARK_COLUMNS]

    horizon_rows = []
    for m in MODELS:
        for h in range(1, 25):
            mae = MODEL_BASE_MAE[m] + h * 0.5
            horizon_rows.append({"model": m, "horizon_h": h, "mae_kwh": mae, "rmse_kwh": mae * 1.3})
    by_horizon = pd.DataFrame(horizon_rows)[HORIZON_COLUMNS]

    n = 200
    targets = pd.date_range("2026-01-01 00:00", periods=n, freq="h")
    actual = 500.0 + 100.0 * np.sin(np.arange(n) / 3.0)
    pred_frames = []
    for m in MODELS:
        # Deterministic, model-specific offset instead of random noise.
        offset = (MODEL_BASE_MAE[m] / 10.0) * np.cos(np.arange(n) / 5.0)
        pred_frames.append(
            pd.DataFrame(
                {
                    "model": m,
                    "origin_timestamp": targets - pd.Timedelta(hours=1),
                    "horizon_h": 1,
                    "target_timestamp": targets,
                    "actual": actual,
                    "prediction": actual + offset,
                }
            )
        )
    predictions = pd.concat(pred_frames, ignore_index=True)[PREDICTION_COLUMNS]

    results_path = tmp_path / "results.csv"
    by_horizon_path = tmp_path / "results_by_horizon.csv"
    predictions_path = tmp_path / "predictions.parquet"
    results.to_csv(results_path, index=False)
    by_horizon.to_csv(by_horizon_path, index=False)
    predictions.to_parquet(predictions_path, index=False)
    return results_path, by_horizon_path, predictions_path


def test_generate_report_writes_all_outputs(tmp_path):
    results_path, by_horizon_path, predictions_path = _write_artifacts(tmp_path)
    out_dir = tmp_path / "report"

    written = generate_report(results_path, by_horizon_path, predictions_path, out_dir)

    for chart in (
        CHART_METRIC_COMPARISON,
        CHART_ACTUAL_VS_PREDICTED,
        CHART_ERROR_BY_HOUR,
        CHART_ERROR_VS_HORIZON,
    ):
        assert (out_dir / chart).exists(), f"Missing chart {chart}"

    assert (out_dir / "REPORT.md").exists()
    assert (out_dir / "results.json").exists()

    report_text = (out_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "Recommendation" in report_text
    assert "Model to serve" in report_text
    for chart in (CHART_METRIC_COMPARISON, CHART_ERROR_VS_HORIZON):
        assert chart in report_text  # charts embedded by relative path

    assert written["report_md"].exists() and written["results_json"].exists()


def test_results_json_schema_and_recommendation(tmp_path):
    results_path, by_horizon_path, predictions_path = _write_artifacts(tmp_path)
    out_dir = tmp_path / "report"

    generate_report(results_path, by_horizon_path, predictions_path, out_dir)
    payload = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))

    assert payload["generated_horizon"] == 24
    assert len(payload["models"]) == 4
    assert len(payload["by_horizon"]) == 4 * 24

    rec = payload["recommendation"]
    assert rec["recommended_model"] in MODELS
    # xgboost has the lowest mean MAE in the synthetic data -> it must win.
    assert rec["recommended_model"] == "xgboost"
    assert rec["best_at_1h"]["horizon_h"] == 1
    assert rec["best_at_24h"]["horizon_h"] == 24
    assert rec["best_at_1h"]["model"] == "xgboost"

    assert set(payload["charts"].keys()) == {
        "metric_comparison",
        "actual_vs_predicted",
        "error_by_hour",
        "error_vs_horizon",
    }


def test_recommendation_tie_break_prefers_lower_latency_then_size():
    """When mean MAE ties, the pick is the lower-latency, then smaller model."""
    results = pd.DataFrame(
        {
            "model": ["a", "b"],
            "mae_kwh": [50.0, 50.0],
            "rmse_kwh": [60.0, 60.0],
            "mape_percent": [10.0, 10.0],
            "r2": [0.9, 0.9],
            "training_time_s": [1.0, 1.0],
            "mean_inference_latency_ms": [0.5, 0.2],  # b is faster
            "model_file_size_bytes": [1000, 2000],
            "train_window_hours": [100, 100],
        }
    )[BENCHMARK_COLUMNS]
    by_horizon = pd.DataFrame(
        [{"model": m, "horizon_h": h, "mae_kwh": 50.0, "rmse_kwh": 60.0} for m in ("a", "b") for h in range(1, 25)]
    )[HORIZON_COLUMNS]

    rec = compute_recommendation(results, by_horizon)
    assert rec["recommended_model"] == "b", "Lower-latency model must win an accuracy tie"


def test_sample_week_falls_back_to_full_span_when_short(tmp_path):
    """When the test span is shorter than a week, the chart uses the full span (no error)."""
    n = 50  # < SAMPLE_WEEK_HOURS (168)
    targets = pd.date_range("2026-01-01 00:00", periods=n, freq="h")
    short = pd.DataFrame(
        {
            "model": "xgboost",
            "origin_timestamp": targets - pd.Timedelta(hours=1),
            "horizon_h": 1,
            "target_timestamp": targets,
            "actual": np.arange(n, dtype=float),
            "prediction": np.arange(n, dtype=float) + 1.0,
        }
    )[PREDICTION_COLUMNS]

    filename = render_actual_vs_predicted(short, tmp_path)
    assert (tmp_path / filename).exists()


def test_load_artifacts_missing_raises(tmp_path):
    results_path, by_horizon_path, predictions_path = _write_artifacts(tmp_path)
    predictions_path.unlink()  # remove one required artifact

    with pytest.raises(FileNotFoundError) as exc_info:
        load_artifacts(results_path, by_horizon_path, predictions_path)
    assert str(predictions_path) in str(exc_info.value)


def test_run_report_cli_exits_nonzero_on_missing_artifact(tmp_path, monkeypatch):
    results_path, by_horizon_path, predictions_path = _write_artifacts(tmp_path)
    predictions_path.unlink()
    out_dir = tmp_path / "report"

    argv = [
        "run_report",
        "--results", str(results_path),
        "--results-by-horizon", str(by_horizon_path),
        "--predictions", str(predictions_path),
        "--out-dir", str(out_dir),
    ]
    monkeypatch.setattr(run_report_mod.sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        run_report_mod.main()
    assert exc_info.value.code == 1
    assert not (out_dir / "REPORT.md").exists(), "No partial report on missing artifact"
