"""
LSTM forecaster tests (Story 4.3), run on the 1,708-row fixture only.

Covers every row of the spec's I/O & Edge-Case Matrix. The shared autouse
fixture in conftest.py caps epochs for the rest of the suite; the tests here
that need real training behaviour set their own constants with monkeypatch.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.preprocessing import StandardScaler

from experiments.benchmark.benchmark import BENCHMARK_COLUMNS, run_scoring
from experiments.benchmark.lstm import (
    LSTM_FEATURES,
    LSTM_INPUT_HOURS,
    LSTM_NUM_LAYERS,
    LSTM_OUTPUT_HOURS,
    LSTM_VALIDATION_FRACTION,
    LSTMForecaster,
)
from src.models.train_models import engineer_features, load_dataset, split_time_series_data

MINIMUM_ROWS = LSTM_INPUT_HOURS + LSTM_OUTPUT_HOURS


def expected_validation_rows(n_train: int) -> int:
    """Rows held out for early stopping, as documented in the spec's Implementation Notes."""
    n_val = max(MINIMUM_ROWS, int(round(n_train * LSTM_VALIDATION_FRACTION)))
    return n_val if n_train - n_val >= MINIMUM_ROWS else 0


def feature_matrix(frame: pd.DataFrame) -> np.ndarray:
    return frame[list(LSTM_FEATURES)].to_numpy(dtype=np.float64)


@pytest.fixture
def sample_partitions():
    """Standard train/test partitions from the fixture, same split as test_benchmark.py."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
    raw_df = load_dataset(fixture_path)
    df_feat = engineer_features(raw_df)
    return split_time_series_data(df_feat, train_ratio=0.8)


def test_lstm_row_is_scored_and_finite(sample_partitions):
    """I/O: the LSTM appears as a fourth scored row with all 9 columns finite."""
    train_df, test_df = sample_partitions
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    lstm_row = results_df[results_df["model"] == "lstm"].iloc[0]
    assert len(results_df) == 4
    for col in BENCHMARK_COLUMNS:
        assert pd.notna(lstm_row[col]), f"lstm column {col} is NaN/empty"
        if col != "model":
            assert np.isfinite(float(lstm_row[col])), f"lstm column {col} is not finite"

    # The fit completes on CPU and is timed (the 900 s budget is checked on the real dataset).
    assert lstm_row["training_time_s"] > 0.0
    assert lstm_row["model_file_size_bytes"] > 0
    # The row reports the rows the scaler and weights were fitted on: the split minus the validation slice.
    fitted_rows = len(train_df) - expected_validation_rows(len(train_df))
    assert fitted_rows < len(train_df)
    assert int(lstm_row["train_window_hours"]) == fitted_rows


def test_lstm_architecture_matches_spec(sample_partitions):
    """I/O: 1-2 LSTM layers, 168-hour input, 24-value output head."""
    train_df, _ = sample_partitions
    model = LSTMForecaster().fit(train_df)

    assert LSTM_INPUT_HOURS == 168
    assert LSTM_OUTPUT_HOURS == 24
    assert LSTM_NUM_LAYERS in (1, 2)

    assert model._net.lstm.input_size == len(LSTM_FEATURES)
    assert model._net.lstm.num_layers == LSTM_NUM_LAYERS
    assert model._net.head.out_features == LSTM_OUTPUT_HOURS
    assert model._history.shape == (LSTM_INPUT_HOURS, len(LSTM_FEATURES))


def test_scaler_is_fitted_on_training_rows_before_validation(sample_partitions):
    """I/O: the scaler statistics come only from the pre-validation training rows."""
    train_df, test_df = sample_partitions
    model = LSTMForecaster().fit(train_df)

    n_val = expected_validation_rows(len(train_df))
    assert n_val > 0
    expected = StandardScaler().fit(feature_matrix(train_df)[: len(train_df) - n_val])

    np.testing.assert_array_equal(model._scaler.mean_, expected.mean_)
    np.testing.assert_array_equal(model._scaler.scale_, expected.scale_)

    # Matrix row: change the validation-slice values, refit on the same training rows,
    # and the scaler statistics must not move.
    shocked_train_df = train_df.copy()
    for column in LSTM_FEATURES:
        shocked_train_df.iloc[-n_val:, shocked_train_df.columns.get_loc(column)] += 1000.0
    refitted = LSTMForecaster().fit(shocked_train_df)
    np.testing.assert_array_equal(refitted._scaler.mean_, expected.mean_)
    np.testing.assert_array_equal(refitted._scaler.scale_, expected.scale_)

    # Changing the test values moves predictions but never the fitted scaler.
    shocked_test_df = test_df.copy()
    shocked_test_df["meter_reading"] = shocked_test_df["meter_reading"] + 100.0
    shocked_preds = model.predict(shocked_test_df)
    np.testing.assert_array_equal(model._scaler.mean_, expected.mean_)
    assert not np.allclose(model.predict(test_df), shocked_preds)


def test_predictions_are_the_hour_one_output_in_kwh(sample_partitions):
    """predict returns output index 0 of the 24-value head, converted back to kWh with the target's statistics."""
    train_df, test_df = sample_partitions
    model = LSTMForecaster().fit(train_df)
    preds = model.predict(test_df)

    scaled_test = model._scaler.transform(feature_matrix(test_df)).astype(np.float32)
    history = np.vstack([model._history, scaled_test])
    target = LSTM_FEATURES.index("meter_reading")

    model._net.eval()
    for row in (0, 1, 200, len(test_df) - 1):
        window = torch.from_numpy(history[row : row + LSTM_INPUT_HOURS][None, :, :])
        with torch.no_grad():
            head = model._net(window)[0].numpy().astype(np.float64)
        assert head.shape == (LSTM_OUTPUT_HOURS,)
        expected_kwh = head[0] * model._scaler.scale_[target] + model._scaler.mean_[target]
        assert preds[row] == pytest.approx(expected_kwh, rel=1e-5)

    # Unit sanity: the predictions must be inverse-scaled to kWh. Skipping the
    # inverse transform would leave them on the standardized scale (mean ~0),
    # far below the readings, so a floor at a tenth of the smallest reading
    # catches that defect without depending on how well the capped-epoch fit converged.
    readings = test_df["meter_reading"].to_numpy(dtype=float)
    assert preds.min() > readings.min() / 10.0


def test_history_is_the_scaled_tail_of_the_training_split(sample_partitions):
    """The first test windows are completed from the last 168 training rows, validation slice included."""
    train_df, test_df = sample_partitions
    model = LSTMForecaster().fit(train_df)

    expected_history = model._scaler.transform(feature_matrix(train_df)[-LSTM_INPUT_HOURS:]).astype(np.float32)
    np.testing.assert_array_equal(model._history, expected_history)

    # The very last training reading is the t-1 input of the first test forecast.
    baseline_first = model.predict(test_df.iloc[:1])[0]
    model._history = model._history.copy()
    model._history[-1, LSTM_FEATURES.index("meter_reading")] += 5.0
    assert model.predict(test_df.iloc[:1])[0] != baseline_first


def test_lstm_predictions_are_one_step_ahead(sample_partitions):
    """I/O: the forecast for hour t uses readings up to t-1 only."""
    train_df, test_df = sample_partitions
    model = LSTMForecaster().fit(train_df)
    preds = model.predict(test_df)

    k = 50
    shocked_test_df = test_df.copy()
    shocked_test_df.iloc[k, shocked_test_df.columns.get_loc("meter_reading")] += 500.0
    shocked_preds = model.predict(shocked_test_df)

    np.testing.assert_array_equal(preds[: k + 1], shocked_preds[: k + 1])
    assert shocked_preds[k + 1] != preds[k + 1], "Reading at t-1 did not inform the forecast at t"


def test_start_of_test_span_is_completed_from_training_tail(sample_partitions):
    """I/O: a test span shorter than 168 rows still yields finite predictions for every row."""
    train_df, test_df = sample_partitions
    model = LSTMForecaster().fit(train_df)

    short_test_df = test_df.iloc[:5]
    preds = model.predict(short_test_df)

    assert preds.shape == (5,)
    assert np.isfinite(preds).all()


def test_early_stopping_stops_before_the_epoch_cap(sample_partitions, monkeypatch):
    """I/O: a plateau in validation loss stops training before the cap and keeps best weights."""
    train_df, _ = sample_partitions

    # lr=0 freezes the weights, so validation loss is constant and patience runs out deterministically.
    monkeypatch.setattr("experiments.benchmark.lstm.LSTM_LEARNING_RATE", 0.0)
    monkeypatch.setattr("experiments.benchmark.lstm.LSTM_MAX_EPOCHS", 10)
    monkeypatch.setattr("experiments.benchmark.lstm.LSTM_PATIENCE", 3)

    model = LSTMForecaster().fit(train_df)

    assert model._epochs_run == 4, "should stop after 1 improving epoch + 3 patience epochs"
    assert model._epochs_run < 10
    assert np.isfinite(model._best_val_loss)


def test_early_stopping_restores_the_best_validation_weights(sample_partitions, monkeypatch):
    """I/O: after validation loss worsens, the kept network is the best-validation one, not the last one."""
    train_df, _ = sample_partitions

    # A large learning rate makes validation loss bounce, so patience runs out after a worse epoch.
    monkeypatch.setattr("experiments.benchmark.lstm.LSTM_LEARNING_RATE", 0.05)
    monkeypatch.setattr("experiments.benchmark.lstm.LSTM_MAX_EPOCHS", 30)
    monkeypatch.setattr("experiments.benchmark.lstm.LSTM_PATIENCE", 2)

    model = LSTMForecaster().fit(train_df)

    # Stopping before the cap means the last two epochs were no better than the best one.
    assert model._epochs_run < 30

    model._net.eval()
    with torch.no_grad():
        restored_loss = float(
            torch.nn.MSELoss()(model._net(torch.from_numpy(model._val_X)), torch.from_numpy(model._val_y))
        )
    assert restored_loss == pytest.approx(model._best_val_loss, rel=1e-6)


def test_short_training_split_uses_every_row_without_early_stopping(sample_partitions):
    """Boundary: 192 rows, and any split too short for a validation slice, train on all rows to the cap."""
    train_df, test_df = sample_partitions

    for n_rows in (MINIMUM_ROWS, 300, 2 * MINIMUM_ROWS - 1):
        short_train_df = train_df.iloc[:n_rows]
        model = LSTMForecaster().fit(short_train_df)

        assert model._val_X is None and model._val_y is None
        assert model._epochs_run == 2, "conftest caps training at 2 epochs"
        assert model.train_window_used == n_rows
        full_scaler = StandardScaler().fit(feature_matrix(short_train_df))
        np.testing.assert_array_equal(model._scaler.mean_, full_scaler.mean_)
        assert np.isfinite(model.predict(test_df.iloc[:10])).all()

    # One row more and a full validation slice fits again.
    with_validation = LSTMForecaster().fit(train_df.iloc[: 2 * MINIMUM_ROWS])
    assert with_validation._val_X is not None
    assert with_validation.train_window_used == MINIMUM_ROWS


def test_refit_on_the_same_instance_matches_a_fresh_fit(sample_partitions):
    """fit starts from a clean slate, so reusing an instance gives the same model as a new one."""
    train_df, test_df = sample_partitions

    reused = LSTMForecaster().fit(train_df.iloc[:MINIMUM_ROWS])
    reused.fit(train_df)
    fresh = LSTMForecaster().fit(train_df)

    assert reused._best_val_loss == fresh._best_val_loss
    np.testing.assert_array_equal(reused.predict(test_df), fresh.predict(test_df))


def test_lstm_determinism(sample_partitions):
    """I/O: two fits on the same data give bit-identical predictions."""
    train_df, test_df = sample_partitions

    preds1 = LSTMForecaster().fit(train_df).predict(test_df)
    preds2 = LSTMForecaster().fit(train_df).predict(test_df)

    np.testing.assert_array_equal(preds1, preds2, err_msg="LSTM predictions were not deterministic")


def test_too_little_history_raises_value_error(sample_partitions):
    """I/O: a training split shorter than 168 + 24 rows raises a ValueError naming the minimum."""
    train_df, _ = sample_partitions
    for n_rows in (100, MINIMUM_ROWS - 1):
        with pytest.raises(ValueError) as exc_info:
            LSTMForecaster().fit(train_df.iloc[:n_rows])
        assert str(MINIMUM_ROWS) in str(exc_info.value)


def test_lstm_forecaster_is_picklable_and_cpu_only(sample_partitions, tmp_path):
    """score_model serializes every model; the artifact holds the model, not its validation windows."""
    import joblib

    train_df, test_df = sample_partitions
    model = LSTMForecaster().fit(train_df)
    assert model._val_X is not None, "validation windows stay on the live instance"

    artifact = tmp_path / "lstm.joblib"
    joblib.dump(model, artifact)
    assert artifact.stat().st_size > 0

    loaded = joblib.load(artifact)
    assert loaded._val_X is None and loaded._val_y is None
    np.testing.assert_array_equal(loaded.predict(test_df), model.predict(test_df))
    # The artifact must be far smaller than the validation windows it used to carry.
    assert artifact.stat().st_size < model._val_X.nbytes + model._val_y.nbytes + 200_000

    assert all(param.device.type == "cpu" for param in model._net.parameters())
