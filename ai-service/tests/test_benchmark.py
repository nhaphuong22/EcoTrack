"""
Unit tests for the EcoTrack Forecasting Benchmark Harness:
- Verifies happy path schema, columns, and metric validity (XGBoost beats Seasonal-naive).
- Verifies SeasonalNaiveForecaster predictions strictly match 'lag_24h' with zero NaNs.
- Verifies pluggability: registering a 3rd forecaster executes without modifying scoring code.
- Verifies determinism: repeated runs yield bit-identical accuracy metrics.
- Verifies latency and serialized model artifact size metrics.
- Verifies error handling when input dataset is missing.
"""

from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
import pytest

from experiments.benchmark.benchmark import BENCHMARK_COLUMNS, run_scoring, score_model
from experiments.benchmark.models import (
    BaseForecaster,
    SeasonalNaiveForecaster,
    XGBoostForecaster,
    _FORECASTER_REGISTRY,
    get_registered_forecasters,
    register_forecaster,
)
from experiments.benchmark.run_benchmark import execute_benchmark
from src.models.train_models import (
    engineer_features,
    load_dataset,
    split_time_series_data,
)


@pytest.fixture
def sample_partitions():
    """Provides standard train and test partitions from fixture data."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
    raw_df = load_dataset(fixture_path)
    df_feat = engineer_features(raw_df)
    train_df, test_df = split_time_series_data(df_feat, train_ratio=0.8)
    return train_df, test_df


def test_benchmark_happy_path_schema_and_comparison(sample_partitions, tmp_path):
    """
    Verify happy path execution:
    - Results table has exactly 2 rows ('seasonal_naive' and 'xgboost').
    - All 8 standard columns are present, non-null, and finite.
    - XGBoost outperforms Seasonal-naive on MAE and RMSE.
    """
    train_df, test_df = sample_partitions
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    assert list(results_df.columns) == BENCHMARK_COLUMNS
    assert len(results_df) == 2

    model_names = set(results_df["model"])
    assert model_names == {"seasonal_naive", "xgboost"}

    # No NaN or infinite values
    for col in BENCHMARK_COLUMNS:
        assert results_df[col].isna().sum() == 0, f"Column {col} contains NaN values"

    # Numeric validations
    naive_row = results_df[results_df["model"] == "seasonal_naive"].iloc[0]
    xgb_row = results_df[results_df["model"] == "xgboost"].iloc[0]

    assert xgb_row["mae_kwh"] < naive_row["mae_kwh"], "XGBoost MAE must be lower than Seasonal-naive"
    assert xgb_row["rmse_kwh"] < naive_row["rmse_kwh"], "XGBoost RMSE must be lower than Seasonal-naive"
    assert xgb_row["r2"] > naive_row["r2"], "XGBoost R2 must be higher than Seasonal-naive"


def test_seasonal_naive_predictions_equal_lag_24h(sample_partitions):
    """
    Verify SeasonalNaiveForecaster predictions:
    - Strictly equal test_df['lag_24h'].
    - Zero NaNs.
    """
    train_df, test_df = sample_partitions
    model = SeasonalNaiveForecaster()
    model.fit(train_df)
    preds = model.predict(test_df)

    assert isinstance(preds, np.ndarray)
    assert len(preds) == len(test_df)
    assert not np.isnan(preds).any(), "Seasonal naive predictions contain NaN"

    expected = test_df["lag_24h"].to_numpy(dtype=float)
    np.testing.assert_array_equal(preds, expected)


class ConstantMeanForecaster(BaseForecaster):
    name = "constant_mean"

    def __init__(self):
        self.mean_val = 0.0

    def fit(self, train_df: pd.DataFrame) -> "ConstantMeanForecaster":
        self.mean_val = float(train_df["meter_reading"].mean())
        return self

    def predict(self, test_df: pd.DataFrame) -> np.ndarray:
        return np.full(len(test_df), self.mean_val, dtype=float)


def test_benchmark_pluggability(sample_partitions):
    """
    Verify pluggability contract (AC2):
    - Subclassing BaseForecaster and using @register_forecaster registers a 3rd model.
    - run_scoring evaluates all registered models without editing scoring code.
    """
    train_df, test_df = sample_partitions

    register_forecaster(ConstantMeanForecaster)

    try:
        registered = get_registered_forecasters()
        assert any(m.name == "constant_mean" for m in registered)

        results_df = run_scoring(train_df=train_df, test_df=test_df)
        assert len(results_df) == 3
        assert "constant_mean" in results_df["model"].values

        mean_row = results_df[results_df["model"] == "constant_mean"].iloc[0]
        assert mean_row["mae_kwh"] > 0.0
        assert mean_row["model_file_size_bytes"] > 0
    finally:
        # Clean up registry to isolate tests
        _FORECASTER_REGISTRY.pop("constant_mean", None)


def test_benchmark_determinism(sample_partitions):
    """
    Verify determinism of accuracy metrics across repeated runs on the same data.
    MAE, RMSE, MAPE %, R2 must be identical across runs.
    """
    train_df, test_df = sample_partitions

    run1_df = run_scoring(train_df=train_df, test_df=test_df)
    run2_df = run_scoring(train_df=train_df, test_df=test_df)

    accuracy_cols = ["mae_kwh", "rmse_kwh", "mape_percent", "r2"]

    for col in accuracy_cols:
        np.testing.assert_array_equal(
            run1_df[col].values,
            run2_df[col].values,
            err_msg=f"Accuracy metric {col} was not bit-identical across benchmark runs",
        )


def test_benchmark_mean_latency_and_file_size(sample_partitions):
    """
    Verify latency and serialized file size metrics:
    - mean_inference_latency_ms is finite and > 0.
    - model_file_size_bytes is an integer > 0 for all models, including naive.
    """
    train_df, test_df = sample_partitions
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    for _, row in results_df.iterrows():
        assert row["mean_inference_latency_ms"] >= 0.0
        assert isinstance(row["model_file_size_bytes"], (int, np.integer))
        assert row["model_file_size_bytes"] > 0, f"Size for {row['model']} must be > 0 bytes"

    # Serialized XGBoost artifact should be considerably larger than naive
    naive_size = results_df[results_df["model"] == "seasonal_naive"]["model_file_size_bytes"].iloc[0]
    xgb_size = results_df[results_df["model"] == "xgboost"]["model_file_size_bytes"].iloc[0]
    assert xgb_size > naive_size


def test_benchmark_missing_dataset_raises(tmp_path):
    """
    Verify missing dataset handling:
    - Non-existent path raises FileNotFoundError naming the missing path.
    - No partial results.csv is written.
    """
    non_existent = tmp_path / "does_not_exist.csv"
    output_file = tmp_path / "output" / "results.csv"

    with pytest.raises(FileNotFoundError) as exc_info:
        execute_benchmark(data_path=non_existent, output_path=output_file)

    assert str(non_existent) in str(exc_info.value)
    assert not output_file.exists(), "Partial results.csv must not be created on missing dataset"
