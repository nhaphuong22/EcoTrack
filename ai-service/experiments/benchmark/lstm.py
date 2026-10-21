"""
PyTorch LSTM forecaster for the EcoTrack benchmark harness (Story 4.3).

CPU-only, deterministic, trained with train-only scaling and validation-slice
early stopping. Registered as `lstm`, so the existing registry and scoring loop
pick it up as a fourth `results.csv` row without any change to that control flow.

Scoring contract: `predict` emits the hour-1 output (index 0 of the 24-hour head)
rolled through the test span, which gives the LSTM the same information as
XGBoost's lag_1h and SARIMAX's one-step roll.
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

from experiments.benchmark.models import BaseForecaster, register_forecaster

logger = logging.getLogger("BenchmarkHarness")

# --- Documented, reproducible configuration (module constants so a test or a
# --- future story can retune without touching the code path) ---
LSTM_FEATURES = ("meter_reading", "air_temperature")
LSTM_INPUT_HOURS = 168
LSTM_OUTPUT_HOURS = 24
LSTM_NUM_LAYERS = 1
LSTM_HIDDEN_SIZE = 64
LSTM_BATCH_SIZE = 128
LSTM_LEARNING_RATE = 1e-3
LSTM_MAX_EPOCHS = 50
LSTM_PATIENCE = 8
LSTM_VALIDATION_FRACTION = 0.15
LSTM_SEED = 42
# A fixed thread count keeps runs reproducible on one machine. With 4 threads the full
# real-data fit measured 98-110 s on the project owner's laptop CPU (2026-10-10), well
# inside the 15-minute budget.
LSTM_NUM_THREADS = 4

# Column of the scaled feature matrix that holds the forecast target.
_TARGET_INDEX = LSTM_FEATURES.index("meter_reading")


class _LSTMNet(torch.nn.Module):
    """168-hour multivariate window in, 24-hour meter_reading window out."""

    def __init__(self) -> None:
        super().__init__()
        self.lstm = torch.nn.LSTM(
            input_size=len(LSTM_FEATURES),
            hidden_size=LSTM_HIDDEN_SIZE,
            num_layers=LSTM_NUM_LAYERS,
            batch_first=True,
        )
        self.head = torch.nn.Linear(LSTM_HIDDEN_SIZE, LSTM_OUTPUT_HOURS)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        output, _ = self.lstm(x)
        return self.head(output[:, -1, :])


def _build_windows(values: np.ndarray, targets: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Slice one scaled series into (n, 168, 2) inputs and (n, 24) targets."""
    n = len(values) - LSTM_INPUT_HOURS - LSTM_OUTPUT_HOURS + 1
    inputs = np.stack([values[i : i + LSTM_INPUT_HOURS] for i in range(n)])
    outputs = np.stack(
        [targets[i + LSTM_INPUT_HOURS : i + LSTM_INPUT_HOURS + LSTM_OUTPUT_HOURS] for i in range(n)]
    )
    return inputs, outputs


@register_forecaster
class LSTMForecaster(BaseForecaster):
    """
    Recurrent neural baseline: a CPU LSTM trained on 168-hour input windows to
    predict the next 24 hourly readings, scored one hour ahead.

    The scaler is fitted on the training rows that precede the validation slice;
    the validation slice and the test split are only ever transformed with it.
    Early stopping keeps the best-validation weights, and every source of
    randomness is seeded so two runs produce identical metrics (Story 4.1 AC3).
    """

    name: str = "lstm"

    def __init__(self) -> None:
        self._net: Optional[_LSTMNet] = None
        self._scaler: Optional[StandardScaler] = None
        self._history: Optional[np.ndarray] = None
        self._val_X: Optional[np.ndarray] = None
        self._val_y: Optional[np.ndarray] = None
        self._epochs_run: int = 0
        self._best_val_loss: float = float("inf")

    def __getstate__(self) -> dict:
        # The validation windows are training scaffolding, not part of the model: leave them
        # out of the pickled artifact so model_file_size_bytes measures the model itself.
        state = self.__dict__.copy()
        state["_val_X"] = None
        state["_val_y"] = None
        return state

    def fit(self, train_df: pd.DataFrame) -> "LSTMForecaster":
        minimum = LSTM_INPUT_HOURS + LSTM_OUTPUT_HOURS
        if len(train_df) < minimum:
            raise ValueError(
                f"LSTMForecaster needs at least {minimum} training rows "
                f"({LSTM_INPUT_HOURS} input + {LSTM_OUTPUT_HOURS} output); got {len(train_df)}."
            )

        # Determinism: fixed seeds plus CPU-deterministic kernels. Read the caps
        # from module globals here so a test fixture can lower them.
        torch.manual_seed(LSTM_SEED)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(LSTM_NUM_THREADS)

        # Start every fit from a clean slate so a refit never inherits the previous run.
        self._val_X = None
        self._val_y = None
        self._best_val_loss = float("inf")
        self._epochs_run = 0

        raw = train_df[list(LSTM_FEATURES)].to_numpy(dtype=np.float64)

        # Validation slice = the tail of the training split; the scaler never sees it.
        n_val = max(minimum, int(round(len(train_df) * LSTM_VALIDATION_FRACTION)))
        if len(train_df) - n_val < minimum:
            # Too short to hold out a full validation window and still build a training
            # window: use every row and train to the epoch cap without early stopping.
            n_val = 0
            logger.warning(
                "LSTM: %d training rows are too few to hold out a validation slice; "
                "training to the epoch cap without early stopping.",
                len(train_df),
            )
        split = len(train_df) - n_val

        self._scaler = StandardScaler().fit(raw[:split])
        scaled = self._scaler.transform(raw).astype(np.float32)
        scaled_readings = scaled[:, _TARGET_INDEX]

        train_X, train_y = _build_windows(scaled[:split], scaled_readings[:split])
        if n_val:
            self._val_X, self._val_y = _build_windows(scaled[split:], scaled_readings[split:])

        # Rows the scaler and the weights are fitted on (the validation slice only steers stopping).
        self.train_window_used = split
        self._history = scaled[-LSTM_INPUT_HOURS:]
        self._net = _LSTMNet()
        self._train_network(train_X, train_y)
        return self

    def _train_network(self, train_X: np.ndarray, train_y: np.ndarray) -> None:
        net = self._net
        assert net is not None

        optimizer = torch.optim.Adam(net.parameters(), lr=LSTM_LEARNING_RATE)
        loss_fn = torch.nn.MSELoss()
        inputs = torch.from_numpy(train_X)
        targets = torch.from_numpy(train_y)
        val_inputs = None if self._val_X is None else torch.from_numpy(self._val_X)
        val_targets = None if self._val_y is None else torch.from_numpy(self._val_y)

        generator = torch.Generator().manual_seed(LSTM_SEED)
        best_state = None
        patience_left = LSTM_PATIENCE
        self._epochs_run = 0

        for _ in range(LSTM_MAX_EPOCHS):
            net.train()
            order = torch.randperm(len(inputs), generator=generator)
            for start in range(0, len(inputs), LSTM_BATCH_SIZE):
                batch = order[start : start + LSTM_BATCH_SIZE]
                optimizer.zero_grad()
                loss = loss_fn(net(inputs[batch]), targets[batch])
                loss.backward()
                optimizer.step()

            self._epochs_run += 1

            if val_inputs is None:
                # Minimum-data case: nothing to hold out, so train to the cap.
                logger.info("LSTM epoch %d/%d done (no validation slice).", self._epochs_run, LSTM_MAX_EPOCHS)
                continue

            net.eval()
            with torch.no_grad():
                val_loss = float(loss_fn(net(val_inputs), val_targets))

            improved = val_loss < self._best_val_loss
            logger.info(
                "LSTM epoch %d/%d: validation loss %.5f%s",
                self._epochs_run,
                LSTM_MAX_EPOCHS,
                val_loss,
                " (best so far)" if improved else "",
            )

            if improved:
                self._best_val_loss = val_loss
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
                patience_left = LSTM_PATIENCE
            else:
                patience_left -= 1
                if patience_left <= 0:
                    break

        if best_state is not None:
            net.load_state_dict(best_state)
            logger.info(
                "LSTM training finished after %d epoch(s) (%s); restored the weights with validation loss %.5f.",
                self._epochs_run,
                "stopped early" if self._epochs_run < LSTM_MAX_EPOCHS else "reached the epoch cap",
                self._best_val_loss,
            )

    def predict(self, test_df: pd.DataFrame) -> np.ndarray:
        if self._net is None or self._scaler is None or self._history is None:
            raise RuntimeError("LSTMForecaster must be fitted before predict()")

        raw = test_df[list(LSTM_FEATURES)].to_numpy(dtype=np.float64)
        scaled = self._scaler.transform(raw).astype(np.float32)

        # One window per test row: the 168 readings before it, completed from the
        # training tail when the test span has not yet produced 168 rows of its own.
        history = np.vstack([self._history, scaled])
        windows = np.stack([history[i : i + LSTM_INPUT_HOURS] for i in range(len(test_df))])

        self._net.eval()
        with torch.no_grad():
            outputs = self._net(torch.from_numpy(windows))

        hour_one = outputs[:, 0].numpy().astype(np.float64)
        return hour_one * self._scaler.scale_[_TARGET_INDEX] + self._scaler.mean_[_TARGET_INDEX]
