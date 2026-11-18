"""
Unit tests for the Story 4.4 per-horizon (rolling-origin) benchmark scoring.

Covers the I/O & Edge-Case Matrix rows that belong to the harness:
- Recursive no-leakage (XGBoost) + horizon-1 reconciliation with the hour-1 predict().
- Native multi-step (SARIMAX/LSTM) horizon-1 reconciliation.
- Seasonal-naive per-horizon equals the observed lag_24h.
- Span-edge truncation leaves no NaN in results_by_horizon.
- Determinism of per-horizon accuracy across repeated runs.
- run_horizon_scoring schema (HORIZON_COLUMNS / PREDICTION_COLUMNS, all four models).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error, mean_squared_error

from experiments.benchmark.benchmark import (
    DEFAULT_HORIZON,
    HORIZON_COLUMNS,
    PREDICTION_COLUMNS,
    run_horizon_scoring,
)
from experiments.benchmark.lstm import LSTMForecaster
from experiments.benchmark.models import (
    SeasonalNaiveForecaster,
    SARIMAXForecaster,
    XGBoostForecaster,
)
from src.models.train_models import (
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    split_time_series_data,
)


@pytest.fixture
def sample_partitions():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
    raw_df = load_dataset(fixture_path)
    df_feat = engineer_features(raw_df)
    train_df, test_df = split_time_series_data(df_feat, train_ratio=0.8)
    return train_df, test_df


def test_seasonal_naive_grid_equals_lag24(sample_partitions):
    """Seasonal-naive horizon-h forecast for target q equals the observed lag_24h[q]."""
    train_df, test_df = sample_partitions
    model = SeasonalNaiveForecaster().fit(train_df)
    grid = model.forecast_grid(test_df, horizon=DEFAULT_HORIZON)

    lag_24h = test_df["lag_24h"].to_numpy(dtype=float)
    n = len(test_df)
    for h in (1, 2, 12, 24):
        target = np.arange(h, n)
        np.testing.assert_array_equal(grid[target - h, h - 1], lag_24h[target])


def test_xgboost_recursion_uses_own_prediction(sample_partitions):
    """
    No-leakage: for h >= 2 the lag_1h fed to XGBoost is the model's own prior-step
    prediction (never a future actual); for h == 1 it is the observed reading at the origin.
    """
    train_df, test_df = sample_partitions
    model = XGBoostForecaster().fit(train_df)
    grid = model.forecast_grid(test_df, horizon=DEFAULT_HORIZON)

    feats = test_df[XGB_FEATURE_COLUMNS].to_numpy(dtype=float)
    idx_lag1 = XGB_FEATURE_COLUMNS.index("lag_1h")

    p, h = 5, 3  # origin 5, horizon 3 -> target 8
    q = p + h
    feat = feats[q].copy()
    feat[idx_lag1] = grid[p, h - 2]  # the model's own horizon-(h-1) prediction
    expected = float(model.model.predict(feat.reshape(1, -1))[0])
    assert np.isclose(grid[p, h - 1], expected)

    # Horizon 1 keeps the observed reading at the origin (feats[p+1] unchanged).
    feat1 = feats[p + 1].copy()
    expected_h1 = float(model.model.predict(feat1.reshape(1, -1))[0])
    assert np.isclose(grid[p, 0], expected_h1)


def test_horizon_one_reconciles_with_hour_one(sample_partitions):
    """grid[p, 0] (origin p, horizon 1, target p+1) matches predict(test_df)[p+1]."""
    train_df, test_df = sample_partitions
    n = len(test_df)

    for model, rtol, atol in [
        (SeasonalNaiveForecaster(), 0.0, 0.0),
        (XGBoostForecaster(), 1e-6, 1e-6),
        (LSTMForecaster(), 1e-5, 1e-4),
        (SARIMAXForecaster(), 1e-3, 1e-2),
    ]:
        model.fit(train_df)
        preds = model.predict(test_df)
        grid = model.forecast_grid(test_df, horizon=DEFAULT_HORIZON)
        horizon1 = grid[: n - 1, 0]
        hour1_shifted = preds[1:n]
        np.testing.assert_allclose(
            horizon1, hour1_shifted, rtol=rtol, atol=atol,
            err_msg=f"{model.name}: horizon-1 did not reconcile with hour-1",
        )


def test_horizon_one_aggregate_reconciles_with_hour_one(sample_partitions):
    """
    The aggregated horizon-1 MAE/RMSE from run_horizon_scoring reconciles with the hour-1
    predict() path on the same origins (test positions 1..n-1). The hour-1 results.csv figure
    additionally includes origin 0 (position 0 is no origin at horizon 1), so reconciliation is
    checked on the shared row set — exactly where a leakage/alignment regression would surface —
    within the per-model tolerances used by the point-level reconciliation test.
    """
    train_df, test_df = sample_partitions
    n = len(test_df)
    actual = test_df["meter_reading"].to_numpy(dtype=float)

    by_horizon, _ = run_horizon_scoring(train_df, test_df, horizon=DEFAULT_HORIZON)
    h1 = by_horizon[by_horizon["horizon_h"] == 1].set_index("model")

    models = [
        (SeasonalNaiveForecaster(), 0.0, 1e-9),
        (XGBoostForecaster(), 1e-6, 1e-6),
        (LSTMForecaster(), 1e-5, 1e-4),
        (SARIMAXForecaster(), 1e-3, 1e-2),
    ]
    for model, rtol, atol in models:
        model.fit(train_df)
        preds = model.predict(test_df)
        expected_mae = mean_absolute_error(actual[1:n], preds[1:n])
        expected_rmse = float(np.sqrt(mean_squared_error(actual[1:n], preds[1:n])))
        assert np.isclose(h1.loc[model.name, "mae_kwh"], expected_mae, rtol=rtol, atol=atol), (
            f"{model.name}: horizon-1 aggregate MAE did not reconcile with hour-1 predict()"
        )
        assert np.isclose(h1.loc[model.name, "rmse_kwh"], expected_rmse, rtol=rtol, atol=atol), (
            f"{model.name}: horizon-1 aggregate RMSE did not reconcile with hour-1 predict()"
        )


@pytest.mark.parametrize("make_model", [SARIMAXForecaster, LSTMForecaster])
def test_native_multistep_no_leakage(sample_partitions, make_model):
    """
    Native multi-step (SARIMAX/LSTM) forecasts from origin p must condition only on readings
    observed up to p. Altering a future actual (here a target of origin p) must leave the whole
    forecast row grid[p] unchanged — otherwise the model peeked past the origin.
    """
    train_df, test_df = sample_partitions
    model = make_model().fit(train_df)
    grid = model.forecast_grid(test_df, horizon=DEFAULT_HORIZON)

    p, k = 5, 20  # k is a future target of origin p (horizon 15); its actual must not leak
    shocked = test_df.copy()
    shocked.iloc[k, shocked.columns.get_loc("meter_reading")] += 1000.0
    grid_shocked = model.forecast_grid(shocked, horizon=DEFAULT_HORIZON)

    np.testing.assert_allclose(
        grid[p], grid_shocked[p],
        err_msg=f"{model.name}: forecast from origin {p} changed when a future actual was altered",
    )


def test_run_horizon_scoring_schema_and_no_nan(sample_partitions):
    """
    run_horizon_scoring returns the documented schemas, covers all four models and
    horizons 1..24, and leaves no NaN (span-edge origins only drop out-of-range horizons).
    """
    train_df, test_df = sample_partitions
    by_horizon, predictions = run_horizon_scoring(train_df, test_df, horizon=DEFAULT_HORIZON)

    assert list(by_horizon.columns) == HORIZON_COLUMNS
    assert list(predictions.columns) == PREDICTION_COLUMNS

    assert set(by_horizon["model"]) == {"seasonal_naive", "xgboost", "sarimax", "lstm"}
    assert set(predictions["model"]) == {"seasonal_naive", "xgboost", "sarimax", "lstm"}

    # Every model has all 24 horizons (the fixture test span exceeds 24 rows).
    for model_name, group in by_horizon.groupby("model"):
        assert sorted(group["horizon_h"]) == list(range(1, DEFAULT_HORIZON + 1))

    assert by_horizon[["mae_kwh", "rmse_kwh"]].notna().all().all()
    assert np.isfinite(by_horizon[["mae_kwh", "rmse_kwh"]].to_numpy()).all()
    assert predictions[["actual", "prediction"]].notna().all().all()


def test_span_edge_origins_drop_out_of_range_horizons(sample_partitions):
    """
    The last origins cannot reach 24 h ahead; those cells are NaN in the grid and are
    excluded from scoring rather than counted. The count of scored pairs at horizon h is
    exactly (n - h) for seasonal-naive (which scores every reachable origin).
    """
    train_df, test_df = sample_partitions
    n = len(test_df)
    model = SeasonalNaiveForecaster().fit(train_df)
    grid = model.forecast_grid(test_df, horizon=DEFAULT_HORIZON)

    # Last origin (p = n-1) has no reachable target: its whole row is NaN.
    assert np.isnan(grid[n - 1]).all()
    # At horizon 24 only origins 0..n-25 are scorable.
    assert np.count_nonzero(~np.isnan(grid[:, DEFAULT_HORIZON - 1])) == n - DEFAULT_HORIZON


def test_per_horizon_determinism(sample_partitions):
    """Per-(model, horizon) MAE/RMSE are bit-identical across repeated runs."""
    train_df, test_df = sample_partitions

    run1, _ = run_horizon_scoring(train_df, test_df, horizon=DEFAULT_HORIZON)
    run2, _ = run_horizon_scoring(train_df, test_df, horizon=DEFAULT_HORIZON)

    run1 = run1.sort_values(["model", "horizon_h"]).reset_index(drop=True)
    run2 = run2.sort_values(["model", "horizon_h"]).reset_index(drop=True)

    for col in ("mae_kwh", "rmse_kwh"):
        np.testing.assert_array_equal(
            run1[col].to_numpy(), run2[col].to_numpy(),
            err_msg=f"Per-horizon {col} was not deterministic across runs",
        )
