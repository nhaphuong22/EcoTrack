"""
EcoTrack MLOps package (Story 4.5 — FR23, FR47).

Thin, FastAPI-free building blocks for experiment tracking, model-registry
champion management, and Optuna hyperparameter search. Everything here is
importable and callable as plain Python (AD-1); the heavy dependencies
(``mlflow``, ``optuna``) are imported lazily inside functions so that the
no-MLflow code path keeps working when they are not installed.
"""
