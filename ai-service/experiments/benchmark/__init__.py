"""
EcoTrack Forecasting Benchmark Package.
Provides standardized benchmark harness for energy consumption forecasters.
"""

from experiments.benchmark.models import (
    BaseForecaster,
    SeasonalNaiveForecaster,
    XGBoostForecaster,
    SARIMAXForecaster,
    get_registered_forecasters,
    register_forecaster,
)
from experiments.benchmark.benchmark import run_scoring, score_model

__all__ = [
    "BaseForecaster",
    "SeasonalNaiveForecaster",
    "XGBoostForecaster",
    "SARIMAXForecaster",
    "register_forecaster",
    "get_registered_forecasters",
    "score_model",
    "run_scoring",
]
