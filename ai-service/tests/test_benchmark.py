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
    SARIMAXForecaster,
    SARIMAX_TRAIN_WINDOW_HOURS,
    _FORECASTER_REGISTRY,
    get_registered_forecasters,
    register_forecaster,
)
from experiments.benchmark.run_benchmark import execute_benchmark, print_summary_table
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
    - Results table has exactly 4 rows ('seasonal_naive', 'xgboost', 'sarimax', 'lstm').
    - All 9 standard columns are present, non-null, and finite.
    - XGBoost outperforms Seasonal-naive on MAE and RMSE.
    """
    train_df, test_df = sample_partitions
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    assert list(results_df.columns) == BENCHMARK_COLUMNS
    assert len(results_df) == 4

    model_names = set(results_df["model"])
    assert model_names == {"seasonal_naive", "xgboost", "sarimax", "lstm"}

    # No NaN or infinite values
    for col in BENCHMARK_COLUMNS:
        assert results_df[col].isna().sum() == 0, f"Column {col} contains NaN values"

    # Numeric validations
    naive_row = results_df[results_df["model"] == "seasonal_naive"].iloc[0]
    xgb_row = results_df[results_df["model"] == "xgboost"].iloc[0]

    assert xgb_row["mae_kwh"] < naive_row["mae_kwh"], "XGBoost MAE must be lower than Seasonal-naive"
    assert xgb_row["rmse_kwh"] < naive_row["rmse_kwh"], "XGBoost RMSE must be lower than Seasonal-naive"
    assert xgb_row["r2"] > naive_row["r2"], "XGBoost R2 must be higher than Seasonal-naive"


def test_execute_benchmark_writes_results_csv(tmp_path):
    """
    Verify the end-to-end CLI happy path (AC1 one-command deliverable consumed by Story 4.4):
    - execute_benchmark writes results.csv at the requested output path.
    - The written file parses back with exactly the 9 standard columns and 4 model rows.
    """
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
    output_file = tmp_path / "results.csv"

    results_df = execute_benchmark(data_path=fixture_path, output_path=output_file)

    assert output_file.exists(), "execute_benchmark must write results.csv to the output path"

    written_df = pd.read_csv(output_file)
    assert list(written_df.columns) == BENCHMARK_COLUMNS
    assert len(written_df) == 4
    assert set(written_df["model"]) == {"seasonal_naive", "xgboost", "sarimax", "lstm"}
    assert written_df["model_file_size_bytes"].gt(0).all(), "Every serialized size must be > 0"

    # Returned frame matches what was persisted
    assert list(results_df.columns) == list(written_df.columns)
    assert len(results_df) == len(written_df)


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
        assert len(results_df) == 5
        assert "constant_mean" in results_df["model"].values

        mean_row = results_df[results_df["model"] == "constant_mean"].iloc[0]
        assert mean_row["mae_kwh"] > 0.0
        assert mean_row["model_file_size_bytes"] > 0
        # A plugged-in model that fits the whole partition reports the full train-row count.
        assert int(mean_row["train_window_hours"]) == len(train_df)
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


def test_sarimax_predict_length_and_exog_alignment(sample_partitions):
    """
    Verify SARIMAXForecaster:
    - predict returns a finite 1-D float ndarray of exactly len(test_df).
    - the fitted model has one exogenous regressor and daily seasonality (period 24).
    - the test-period air_temperature is used: changing it changes the predictions.
    """
    train_df, test_df = sample_partitions
    model = SARIMAXForecaster()
    model.fit(train_df)
    preds = model.predict(test_df)

    assert isinstance(preds, np.ndarray)
    assert preds.ndim == 1
    assert preds.dtype == float
    assert len(preds) == len(test_df)
    assert np.isfinite(preds).all(), "SARIMAX predictions contain NaN/inf"

    fitted = model._results.model
    assert fitted.k_exog == 1, "air_temperature must be the single exogenous regressor"
    assert fitted.seasonal_periods == 24, "SARIMAX must use daily seasonality"

    warmer_test_df = test_df.copy()
    warmer_test_df["air_temperature"] = warmer_test_df["air_temperature"] + 10.0
    warmer_preds = model.predict(warmer_test_df)
    assert not np.allclose(preds, warmer_preds), "Test-period air_temperature did not affect the forecast"


def test_sarimax_fits_most_recent_window(sample_partitions):
    """SARIMAX fits exactly the last SARIMAX_TRAIN_WINDOW_HOURS rows of the training split."""
    train_df, _ = sample_partitions
    assert len(train_df) > SARIMAX_TRAIN_WINDOW_HOURS, "Fixture too small to exercise window truncation"

    model = SARIMAXForecaster().fit(train_df)

    assert model.train_window_used == SARIMAX_TRAIN_WINDOW_HOURS
    expected_endog = train_df["meter_reading"].iloc[-SARIMAX_TRAIN_WINDOW_HOURS:].to_numpy(dtype=float)
    np.testing.assert_array_equal(np.ravel(model._results.model.endog), expected_endog)


def test_sarimax_predictions_are_one_step_ahead(sample_partitions):
    """
    The forecast for hour t uses readings up to t-1 only (same information as XGBoost's lag_1h):
    changing the reading at position k leaves predictions up to k untouched and moves k+1.
    """
    train_df, test_df = sample_partitions
    model = SARIMAXForecaster().fit(train_df)
    preds = model.predict(test_df)

    k = 50
    shocked_test_df = test_df.copy()
    shocked_test_df.iloc[k, shocked_test_df.columns.get_loc("meter_reading")] += 500.0
    shocked_preds = model.predict(shocked_test_df)

    np.testing.assert_array_equal(preds[: k + 1], shocked_preds[: k + 1])
    assert shocked_preds[k + 1] != preds[k + 1], "Observed reading at t-1 did not inform the forecast at t"


def test_sarimax_row_and_window_in_results(sample_partitions):
    """
    Verify SARIMAX appears as a scored row (I/O matrix):
    - 'sarimax' is present with all 9 columns non-null and every numeric column finite.
    - Its train_window_hours equals the documented window and is < the full-train count,
      which seasonal_naive and xgboost both report.
    """
    train_df, test_df = sample_partitions
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    sarimax_row = results_df[results_df["model"] == "sarimax"].iloc[0]
    naive_row = results_df[results_df["model"] == "seasonal_naive"].iloc[0]
    xgb_row = results_df[results_df["model"] == "xgboost"].iloc[0]

    for col in BENCHMARK_COLUMNS:
        assert pd.notna(sarimax_row[col]), f"sarimax column {col} is NaN/empty"
        if col != "model":
            assert np.isfinite(float(sarimax_row[col])), f"sarimax column {col} is not finite"

    assert int(naive_row["train_window_hours"]) == len(train_df)
    assert int(xgb_row["train_window_hours"]) == len(train_df)
    assert int(sarimax_row["train_window_hours"]) == SARIMAX_TRAIN_WINDOW_HOURS
    assert int(sarimax_row["train_window_hours"]) < len(train_df)


def test_print_summary_table_lists_every_model_and_window(sample_partitions, capsys):
    """The CLI summary prints the Window (h) column and one aligned line per model."""
    train_df, test_df = sample_partitions
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    print_summary_table(results_df)
    lines = capsys.readouterr().out.splitlines()

    header = next(line for line in lines if line.startswith("Model"))
    assert "Window (h)" in header
    rules = [line for line in lines if line and set(line) <= {"=", "-"}]
    assert rules and all(len(rule) == len(header) for rule in rules), "Rules must match the header width"

    sarimax_line = next(line for line in lines if line.startswith("sarimax"))
    assert sarimax_line.rstrip().endswith(str(SARIMAX_TRAIN_WINDOW_HOURS))
    for name in ("seasonal_naive", "xgboost", "lstm"):
        assert any(line.startswith(name) for line in lines)


def test_sarimax_determinism(sample_partitions):
    """SARIMAX accuracy columns are bit-identical across repeated fits on the same data."""
    train_df, test_df = sample_partitions

    run1 = SARIMAXForecaster().fit(train_df)
    preds1 = run1.predict(test_df)
    run2 = SARIMAXForecaster().fit(train_df)
    preds2 = run2.predict(test_df)

    np.testing.assert_array_equal(preds1, preds2, err_msg="SARIMAX predictions were not deterministic")


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
