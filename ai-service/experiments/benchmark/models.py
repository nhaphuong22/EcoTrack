"""
Forecaster interfaces and implementations for the EcoTrack benchmark harness.
Defines BaseForecaster, SeasonalNaiveForecaster, XGBoostForecaster, SARIMAXForecaster,
and a pluggable registry allowing new models to be registered dynamically.
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Type, Union
import warnings
import numpy as np
import pandas as pd
import xgboost as xgb
from statsmodels.tsa.statespace.sarimax import SARIMAX

from src.models.train_models import XGB_FEATURE_COLUMNS


class BaseForecaster(ABC):
    """
    Abstract base class for all forecasters evaluated by the benchmark harness.
    Subclasses must implement fit() and predict().
    """

    name: str = "base_forecaster"

    @abstractmethod
    def fit(self, train_df: pd.DataFrame) -> "BaseForecaster":
        """
        Fits the forecaster on the training partition.
        Must return self for chaining.
        """
        pass

    @abstractmethod
    def predict(self, test_df: pd.DataFrame) -> np.ndarray:
        """
        Generates predictions for each row in the test partition.
        Must return a 1D numpy array of float predictions matching len(test_df).
        """
        pass


# Global model registry mapping model identifier to model class
_FORECASTER_REGISTRY: Dict[str, Type[BaseForecaster]] = {}


def register_forecaster(name_or_cls: Optional[Union[str, Type[BaseForecaster]]] = None):
    """
    Decorator to register a forecaster class in the global benchmark registry.
    Can be used as @register_forecaster or @register_forecaster("custom_name").
    """
    def decorator(cls: Type[BaseForecaster]) -> Type[BaseForecaster]:
        key = getattr(cls, "name", cls.__name__)
        if isinstance(name_or_cls, str):
            key = name_or_cls
            cls.name = key
        _FORECASTER_REGISTRY[key] = cls
        return cls

    if isinstance(name_or_cls, type) and issubclass(name_or_cls, BaseForecaster):
        return decorator(name_or_cls)
    return decorator


def get_registry() -> Dict[str, Type[BaseForecaster]]:
    """Returns a shallow copy of the forecaster registry."""
    return dict(_FORECASTER_REGISTRY)


def get_registered_forecasters() -> List[BaseForecaster]:
    """Instantiates and returns a list of all registered forecasters."""
    return [cls() for cls in _FORECASTER_REGISTRY.values()]


@register_forecaster
class SeasonalNaiveForecaster(BaseForecaster):
    """
    Seasonal-naive baseline: predicts the meter reading from 24 hours earlier.
    Directly extracts the engineered 'lag_24h' feature column.
    """

    name: str = "seasonal_naive"

    def fit(self, train_df: pd.DataFrame) -> "SeasonalNaiveForecaster":
        # Seasonal naive is a non-parametric heuristic; no training required.
        return self

    def predict(self, test_df: pd.DataFrame) -> np.ndarray:
        if "lag_24h" not in test_df.columns:
            raise KeyError("test_df must contain engineered 'lag_24h' column for SeasonalNaiveForecaster")
        return test_df["lag_24h"].to_numpy(dtype=float)


@register_forecaster
class XGBoostForecaster(BaseForecaster):
    """
    Production XGBoost gradient boosted regression model baseline.
    Configured with hyperparameters matching src/models/train_models.py.
    """

    name: str = "xgboost"

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.model = xgb.XGBRegressor(
            n_estimators=350,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            objective="reg:squarederror",
            random_state=self.random_state,
            n_jobs=-1,
        )

    def fit(self, train_df: pd.DataFrame) -> "XGBoostForecaster":
        X_train = train_df[XGB_FEATURE_COLUMNS]
        y_train = train_df["meter_reading"]
        self.model.fit(X_train, y_train)
        return self

    def predict(self, test_df: pd.DataFrame) -> np.ndarray:
        X_test = test_df[XGB_FEATURE_COLUMNS]
        predictions = self.model.predict(X_test)
        return np.asarray(predictions, dtype=float)


# --- SARIMAX statistical baseline configuration (documented, reproducible constants) ---
# Non-seasonal and daily-seasonal (period 24) order; a reasonable untuned statistical baseline.
SARIMAX_ORDER = (1, 1, 1)
SARIMAX_SEASONAL_ORDER = (1, 0, 1, 24)
# SARIMAX is intractable on the full ~14k-row split, so it fits only the most recent window.
# 336 hours (two weeks hourly) fits in ~1.5s and scores lower MAE than a 720-hour window.
SARIMAX_TRAIN_WINDOW_HOURS = 336


@register_forecaster
class SARIMAXForecaster(BaseForecaster):
    """
    Classical statistical baseline: statsmodels SARIMAX with daily seasonality (s=24)
    and air_temperature as an exogenous regressor. Trained on a documented recent window
    of the training split (SARIMAX_TRAIN_WINDOW_HOURS) because a full-data fit is slow.
    """

    name: str = "sarimax"

    def __init__(self):
        self._results = None
        self.train_window_used: int = 0

    def fit(self, train_df: pd.DataFrame) -> "SARIMAXForecaster":
        window = min(SARIMAX_TRAIN_WINDOW_HOURS, len(train_df))
        fit_df = train_df.iloc[-window:]

        model = SARIMAX(
            endog=fit_df["meter_reading"].to_numpy(dtype=float),
            exog=fit_df[["air_temperature"]].to_numpy(dtype=float),
            order=SARIMAX_ORDER,
            seasonal_order=SARIMAX_SEASONAL_ORDER,
        )
        # Convergence warnings are non-fatal (I/O matrix): suppress them, still produce a fit.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._results = model.fit(disp=False)

        self.train_window_used = len(fit_df)
        return self

    def predict(self, test_df: pd.DataFrame) -> np.ndarray:
        forecast = self._results.get_forecast(
            steps=len(test_df),
            exog=test_df[["air_temperature"]].to_numpy(dtype=float),
        )
        return np.asarray(forecast.predicted_mean, dtype=float)
