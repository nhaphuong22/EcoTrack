"""
Inference Feature Pipeline for EcoTrack:
Prepares raw incoming energy readings and weather forecasts into standardized
feature sets conforming precisely to the trained XGBoost Forecaster and
Isolation Forest Anomaly Detector.

Metadata and feature specifications are loaded from `backend/models_saved/model_metadata.json`.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

logger = logging.getLogger("InferencePipeline")

# Default fallback feature definitions in case metadata JSON is not present
DEFAULT_XGB_FEATURES = [
    "air_temperature",
    "hour",
    "dayofweek",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "lag_1h",
    "lag_24h",
]

DEFAULT_ISO_FEATURES = [
    "meter_reading",
    "air_temperature",
    "hour",
    "dayofweek",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "lag_1h",
    "lag_24h",
]


class EnergyInferencePipeline:
    """
    Transforms recent historical readings and future weather forecasts
    into model-ready feature DataFrames.
    """

    def __init__(
        self,
        metadata_path: Optional[Union[str, Path]] = None,
        models_dir: Optional[Union[str, Path]] = None,
    ):
        backend_dir = Path(__file__).resolve().parents[2]
        self.models_dir = Path(models_dir) if models_dir else backend_dir / "models_saved"
        self.metadata_path = (
            Path(metadata_path) if metadata_path else self.models_dir / "model_metadata.json"
        )

        self.metadata: Dict[str, Any] = {}
        self.xgb_features: List[str] = DEFAULT_XGB_FEATURES.copy()
        self.iso_features: List[str] = DEFAULT_ISO_FEATURES.copy()

        self._load_metadata()

    def _load_metadata(self) -> None:
        """Reads feature definitions from model_metadata.json if available."""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                if "xgb_features" in self.metadata:
                    self.xgb_features = list(self.metadata["xgb_features"])
                if "iso_features" in self.metadata:
                    self.iso_features = list(self.metadata["iso_features"])
                logger.info(
                    "Loaded feature specifications from %s: %d XGB features, %d ISO features.",
                    self.metadata_path.name,
                    len(self.xgb_features),
                    len(self.iso_features),
                )
            except Exception as e:
                logger.warning(
                    "Failed to parse %s (%s). Using default feature schema.",
                    self.metadata_path,
                    e,
                )
        else:
            logger.info(
                "Metadata file not found at %s. Using default feature schema.",
                self.metadata_path,
            )

    @staticmethod
    def _standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
        """Renames common column aliases to standard names."""
        df = df.copy()
        rename_map = {
            "meter_reading_kwh": "meter_reading",
            "reading": "meter_reading",
            "load_kwh": "meter_reading",
            "airTemperature": "air_temperature",
            "air_temp": "air_temperature",
            "outdoor_temperature_c": "air_temperature",
            "temp": "air_temperature",
        }
        for old_col, new_col in rename_map.items():
            if old_col in df.columns and new_col not in df.columns:
                df = df.rename(columns={old_col: new_col})
        return df

    def prepare_forecast_features(
        self,
        recent_readings_df: pd.DataFrame,
        future_timestamps: Sequence[Any],
        future_temperatures: Sequence[Union[int, float]],
    ) -> pd.DataFrame:
        """
        Transforms recent historical readings and future timestamps/temperatures into
        a model-ready feature DataFrame for XGBoost forecasting (`X_forecast`).

        Parameters:
        -----------
        recent_readings_df: pd.DataFrame
            Historical readings containing at least 24 recent hourly observations.
            Must contain timestamp and meter_reading (or meter_reading_kwh).
        future_timestamps: Sequence[Any]
            Sequence of future timestamps (e.g. 24 hourly steps).
        future_temperatures: Sequence[float]
            Sequence of forecasted outdoor air temperatures matching future_timestamps.

        Returns:
        --------
        pd.DataFrame:
            DataFrame with exact columns matching `xgb_features`, without NaN values.
        """
        if len(recent_readings_df) < 24:
            raise ValueError(
                f"recent_readings_df must contain at least 24 observations to compute "
                f"lag features (got {len(recent_readings_df)})."
            )

        if len(future_timestamps) != len(future_temperatures):
            raise ValueError(
                f"Length mismatch: {len(future_timestamps)} future_timestamps vs "
                f"{len(future_temperatures)} future_temperatures."
            )

        if len(future_timestamps) == 0:
            return pd.DataFrame(columns=self.xgb_features)

        # 1. Standardize recent readings
        hist = self._standardize_column_names(recent_readings_df)
        if "meter_reading" not in hist.columns:
            raise KeyError("recent_readings_df must contain a 'meter_reading' column.")

        hist["timestamp"] = pd.to_datetime(hist["timestamp"])
        hist = hist.sort_values("timestamp").reset_index(drop=True)

        # Timestamp to meter_reading lookup map
        time_to_reading = dict(zip(hist["timestamp"], hist["meter_reading"]))

        # Convert future timestamps to pandas DatetimeIndex
        future_dt = pd.to_datetime(future_timestamps)

        # 2. Build future feature rows
        rows: List[Dict[str, Any]] = []
        n_future = len(future_dt)

        # Last known observation
        last_observed_reading = float(hist["meter_reading"].iloc[-1])

        # Track previous lag for step chaining
        prev_lag = last_observed_reading

        for i in range(n_future):
            ts = future_dt[i]
            temp = float(future_temperatures[i])

            hour = int(ts.hour)
            dayofweek = int(ts.dayofweek)
            is_weekend = int(dayofweek >= 5)

            hour_sin = float(np.sin(2 * np.pi * hour / 24.0))
            hour_cos = float(np.cos(2 * np.pi * hour / 24.0))

            # Calculate lag_24h (reading from 24 hours prior)
            ts_24h_prior = ts - pd.Timedelta(hours=24)
            if ts_24h_prior in time_to_reading:
                lag_24h = float(time_to_reading[ts_24h_prior])
            else:
                # Positional mapping from recent history (24h cyclic fallback)
                pos = -24 + i if (24 - i) <= len(hist) else -1
                lag_24h = float(hist["meter_reading"].iloc[pos])

            # Calculate lag_1h
            if i == 0:
                ts_1h_prior = ts - pd.Timedelta(hours=1)
                lag_1h = float(time_to_reading.get(ts_1h_prior, last_observed_reading))
            else:
                lag_1h = prev_lag

            feature_dict = {
                "air_temperature": round(temp, 2),
                "hour": hour,
                "dayofweek": dayofweek,
                "is_weekend": is_weekend,
                "hour_sin": hour_sin,
                "hour_cos": hour_cos,
                "lag_1h": round(lag_1h, 2),
                "lag_24h": round(lag_24h, 2),
            }
            rows.append(feature_dict)

            # Update prev_lag for next step (defaults to lag_24h if no prediction chained)
            prev_lag = lag_24h

        X_forecast = pd.DataFrame(rows)[self.xgb_features]

        # Ensure no NaNs remain
        if X_forecast.isnull().any().any():
            X_forecast = X_forecast.ffill().bfill()

        return X_forecast

    def prepare_anomaly_features(
        self,
        data_df: pd.DataFrame,
        historical_context_df: Optional[pd.DataFrame] = None,
        drop_initial_lags: bool = True,
    ) -> pd.DataFrame:
        """
        Transforms energy readings and weather into feature DataFrame for Isolation Forest
        anomaly detection (`X_anomaly`).

        Parameters:
        -----------
        data_df: pd.DataFrame
            Target data to be checked for anomalies.
            Must contain timestamp, meter_reading, and air_temperature.
        historical_context_df: Optional[pd.DataFrame]
            Optional prior historical rows (>= 24 rows) used to compute lag_1h and lag_24h
            for data_df without dropping any leading rows.
        drop_initial_lags: bool
            If True and historical_context_df is None, drops initial rows with NaN lags.
            If False and historical_context_df is None, backfills initial lag NaNs.

        Returns:
        --------
        pd.DataFrame:
            DataFrame with exact columns matching `iso_features`, without NaN values.
        """
        df = self._standardize_column_names(data_df)

        required_cols = ["timestamp", "meter_reading", "air_temperature"]
        for col in required_cols:
            if col not in df.columns:
                raise KeyError(f"Input DataFrame missing required column: '{col}'. Available: {list(df.columns)}")

        # Handle historical context for seamless lag computation
        if historical_context_df is not None and len(historical_context_df) >= 24:
            hist_clean = self._standardize_column_names(historical_context_df)
            combined = pd.concat([hist_clean[required_cols], df[required_cols]], ignore_index=True)
            n_target = len(df)
            is_combined = True
        else:
            combined = df[required_cols].copy()
            n_target = len(df)
            is_combined = False

        combined["timestamp"] = pd.to_datetime(combined["timestamp"])
        combined = combined.sort_values("timestamp").reset_index(drop=True)

        # Feature transformations
        combined["hour"] = combined["timestamp"].dt.hour.astype(int)
        combined["dayofweek"] = combined["timestamp"].dt.dayofweek.astype(int)
        combined["is_weekend"] = (combined["dayofweek"] >= 5).astype(int)

        combined["hour_sin"] = np.sin(2 * np.pi * combined["hour"] / 24.0)
        combined["hour_cos"] = np.cos(2 * np.pi * combined["hour"] / 24.0)

        combined["lag_1h"] = combined["meter_reading"].shift(1)
        combined["lag_24h"] = combined["meter_reading"].shift(24)

        if is_combined:
            # Extract target rows from the end of the combined dataset
            target_features = combined.iloc[-n_target:].copy().reset_index(drop=True)
        else:
            if drop_initial_lags:
                target_features = combined.dropna(subset=["lag_1h", "lag_24h"]).reset_index(drop=True)
            else:
                target_features = combined.copy()
                target_features["lag_1h"] = target_features["lag_1h"].bfill()
                target_features["lag_24h"] = target_features["lag_24h"].bfill()

        X_anomaly = target_features[self.iso_features].copy()

        # Ensure no NaNs exist
        if X_anomaly.isnull().any().any():
            X_anomaly = X_anomaly.ffill().bfill()

        return X_anomaly

    def predict_forecast_autoregressive(
        self,
        xgb_model: Any,
        recent_readings_df: pd.DataFrame,
        future_timestamps: Sequence[Any],
        future_temperatures: Sequence[Union[int, float]],
    ) -> pd.DataFrame:
        """
        Executes multi-step recursive autoregressive load forecasting using XGBoost.
        At each hourly step t, the model's prediction becomes lag_1h for step t+1.
        """
        hist = self._standardize_column_names(recent_readings_df)
        if len(hist) < 24:
            raise ValueError(f"Need at least 24 historical points, got {len(hist)}")

        hist["timestamp"] = pd.to_datetime(hist["timestamp"])
        hist = hist.sort_values("timestamp").reset_index(drop=True)

        future_dt = pd.to_datetime(future_timestamps)
        n_steps = len(future_dt)

        # Buffer containing recent timestamps and readings
        simulated_history = list(zip(hist["timestamp"], hist["meter_reading"].astype(float)))

        forecast_records: List[Dict[str, Any]] = []

        for i in range(n_steps):
            current_ts = future_dt[i]
            current_temp = float(future_temperatures[i])

            # Recent readings dataframe slice
            recent_slice = pd.DataFrame(
                simulated_history[-48:], columns=["timestamp", "meter_reading"]
            )

            # Prepare single step feature
            X_step = self.prepare_forecast_features(
                recent_readings_df=recent_slice,
                future_timestamps=[current_ts],
                future_temperatures=[current_temp],
            )

            pred_val = float(xgb_model.predict(X_step)[0])
            pred_val = round(max(0.0, pred_val), 2)

            forecast_records.append({
                "timestamp": current_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "predicted_meter_reading": pred_val,
                "air_temperature": current_temp,
            })

            # Append prediction to simulated history for autoregressive chaining
            simulated_history.append((current_ts, pred_val))

        return pd.DataFrame(forecast_records)
