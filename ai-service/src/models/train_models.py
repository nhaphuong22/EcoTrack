"""
Model training pipeline for EcoTrack:
1. Feature Engineering:
   - Temporal features: hour, dayofweek, is_weekend
   - Cyclical features: hour_sin, hour_cos
   - Lag features: lag_1h (1 hour prior), lag_24h (24 hours prior)
2. Time Series Split:
   - Chronological split: 80% train, 20% test (no data shuffling)
3. Model 1 - XGBoost Regressor:
   - Forecasts load demand (meter_reading)
   - Evaluates RMSE and MAPE (target MAPE <= 10.0%)
4. Model 2 - Isolation Forest:
   - Detects operational and energy anomalies (contamination=0.03)
   - Extracts anomaly_score and is_anomaly labels
5. Model Persistence:
   - Saves trained estimators to `backend/models_saved/` as:
     - `xgboost_forecaster.joblib`
     - `isolation_forest.joblib`
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score
import xgboost as xgb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TrainModels")

# Defined feature sets
XGB_FEATURE_COLUMNS: List[str] = [
    "air_temperature",
    "hour",
    "dayofweek",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "lag_1h",
    "lag_24h",
]

ISO_FEATURE_COLUMNS: List[str] = [
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


def get_default_paths() -> Tuple[Path, Path]:
    """Returns default input CSV path and models output directory."""
    backend_dir = Path(__file__).resolve().parents[2]
    data_path = backend_dir / "data" / "processed" / "office_building_clean.csv"
    models_dir = backend_dir / "models_saved"
    return data_path, models_dir


def load_dataset(data_path: Path) -> pd.DataFrame:
    """Loads clean processed building time series data."""
    if not data_path.exists():
        raise FileNotFoundError(f"Processed dataset not found at: {data_path}")
    logger.info("Loading processed data from %s...", data_path)
    df = pd.read_csv(data_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    logger.info("Loaded %d rows with columns: %s", len(df), list(df.columns))
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies time-series feature engineering:
    - hour, dayofweek, is_weekend
    - hour_sin, hour_cos (cyclical angular transformation)
    - lag_1h, lag_24h (prior hourly and diurnal consumption)
    - Drops initial rows with NaN from lag shifts
    """
    logger.info("Applying feature engineering (temporal, cyclical, and lag features)...")
    df = df.copy()

    # Temporal features
    df["hour"] = df["timestamp"].dt.hour
    df["dayofweek"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)

    # Cyclical angle transformations
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)

    # Lag features
    df["lag_1h"] = df["meter_reading"].shift(1)
    df["lag_24h"] = df["meter_reading"].shift(24)

    # Clean initial NaN values created by lagging
    initial_rows = len(df)
    df = df.dropna().reset_index(drop=True)
    logger.info("Feature engineering complete: %d rows retained (dropped %d initial rows with lag NaNs).", len(df), initial_rows - len(df))
    return df


def split_time_series_data(
    df: pd.DataFrame, train_ratio: float = 0.8
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Performs chronological train/test split (without shuffling)
    to respect temporal ordering.
    """
    split_index = int(len(df) * train_ratio)
    train_df = df.iloc[:split_index].copy().reset_index(drop=True)
    test_df = df.iloc[split_index:].copy().reset_index(drop=True)

    logger.info(
        "Time-series split (%.0f%% / %.0f%%): Train=%d rows (%s to %s) | Test=%d rows (%s to %s)",
        train_ratio * 100,
        (1 - train_ratio) * 100,
        len(train_df),
        train_df["timestamp"].min(),
        train_df["timestamp"].max(),
        len(test_df),
        test_df["timestamp"].min(),
        test_df["timestamp"].max(),
    )
    return train_df, test_df


def train_xgboost_forecaster(
    train_df: pd.DataFrame, test_df: pd.DataFrame
) -> Tuple[xgb.XGBRegressor, Dict[str, float], np.ndarray]:
    """
    Trains XGBoost Regressor to forecast building electricity demand (`meter_reading`).
    Evaluates RMSE, MAE, MAPE, and R2 on the out-of-time test partition.
    """
    logger.info("Training Model 1: XGBoost Regressor on %d training samples...", len(train_df))
    X_train = train_df[XGB_FEATURE_COLUMNS]
    y_train = train_df["meter_reading"]

    X_test = test_df[XGB_FEATURE_COLUMNS]
    y_test = test_df["meter_reading"]

    forecaster = xgb.XGBRegressor(
        n_estimators=350,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
    )
    forecaster.fit(X_train, y_train)

    y_pred = forecaster.predict(X_test)

    # Calculate evaluation metrics
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    mape = float(mean_absolute_percentage_error(y_test, y_pred) * 100)
    r2 = float(r2_score(y_test, y_pred))

    metrics = {
        "rmse_kwh": round(rmse, 2),
        "mae_kwh": round(mae, 2),
        "mape_percent": round(mape, 2),
        "r2_score": round(r2, 4),
        "target_mape_met": mape <= 10.0,
    }

    logger.info("XGBoost Evaluation Results:")
    logger.info("  - RMSE: %.2f kWh", metrics["rmse_kwh"])
    logger.info("  - MAE:  %.2f kWh", metrics["mae_kwh"])
    logger.info("  - MAPE: %.2f%% (Target <= 10.0%%: %s)", metrics["mape_percent"], "PASSED" if metrics["target_mape_met"] else "FAILED")
    logger.info("  - R^2:  %.4f", metrics["r2_score"])

    return forecaster, metrics, y_pred


def train_isolation_forest(
    train_df: pd.DataFrame, test_df: pd.DataFrame, contamination: float = 0.03
) -> Tuple[IsolationForest, Dict[str, Any], np.ndarray, np.ndarray]:
    """
    Trains Isolation Forest anomaly detector with specified contamination rate.
    Extracts anomaly_score and is_anomaly binary flags.
    """
    logger.info(
        "Training Model 2: Isolation Forest (contamination=%.2f) on %d samples...",
        contamination,
        len(train_df),
    )
    X_train = train_df[ISO_FEATURE_COLUMNS]
    X_test = test_df[ISO_FEATURE_COLUMNS]

    iso_detector = IsolationForest(
        n_estimators=150,
        contamination=contamination,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    iso_detector.fit(X_train)

    # Inference on test set
    raw_decisions = iso_detector.decision_function(X_test)
    test_preds = iso_detector.predict(X_test)  # -1 for anomaly, 1 for normal

    # Invert decision function: higher score means higher likelihood of anomaly
    anomaly_scores = -raw_decisions
    is_anomaly = (test_preds == -1).astype(int)

    anom_count = int(is_anomaly.sum())
    anom_pct = round(float(is_anomaly.mean() * 100), 2)

    metrics = {
        "contamination": contamination,
        "total_test_samples": len(test_df),
        "anomalies_detected": anom_count,
        "anomaly_percentage": anom_pct,
        "anomaly_score_min": round(float(anomaly_scores.min()), 4),
        "anomaly_score_max": round(float(anomaly_scores.max()), 4),
        "anomaly_score_mean": round(float(anomaly_scores.mean()), 4),
    }

    logger.info("Isolation Forest Evaluation Results:")
    logger.info("  - Contamination: %.2f", contamination)
    logger.info("  - Test Anomalies: %d / %d (%.2f%%)", anom_count, len(test_df), anom_pct)
    logger.info("  - Anomaly Score Range: [%.4f, %.4f]", metrics["anomaly_score_min"], metrics["anomaly_score_max"])

    return iso_detector, metrics, anomaly_scores, is_anomaly


def save_trained_models(
    xgb_model: xgb.XGBRegressor,
    iso_model: IsolationForest,
    output_dir: Path,
    metadata: Dict[str, Any],
) -> Tuple[Path, Path]:
    """
    Saves trained models to .joblib files in the target directory.
    Also saves metadata summary JSON.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    xgb_path = output_dir / "xgboost_forecaster.joblib"
    iso_path = output_dir / "isolation_forest.joblib"
    meta_path = output_dir / "model_metadata.json"

    logger.info("Saving models to directory: %s...", output_dir)
    joblib.dump(xgb_model, xgb_path)
    joblib.dump(iso_model, iso_path)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Saved: %s (%.2f MB)", xgb_path.name, xgb_path.stat().st_size / (1024 * 1024))
    logger.info("Saved: %s (%.2f MB)", iso_path.name, iso_path.stat().st_size / (1024 * 1024))
    logger.info("Saved: %s", meta_path.name)

    return xgb_path, iso_path


def run_pipeline(
    data_path: Optional[str] = None,
    models_dir: Optional[str] = None,
    train_ratio: float = 0.8,
    contamination: float = 0.03,
) -> Dict[str, Any]:
    """Executes the full model training, evaluation, and serialization workflow."""
    default_data, default_models = get_default_paths()
    input_file = Path(data_path) if data_path else default_data
    out_dir = Path(models_dir) if models_dir else default_models

    logger.info("==================================================")
    logger.info("   EcoTrack ML Training Pipeline (Member 2)       ")
    logger.info("==================================================")

    # 1. Load and engineer features
    raw_df = load_dataset(input_file)
    df_feat = engineer_features(raw_df)

    # 2. Time-series split (80% train, 20% test)
    train_df, test_df = split_time_series_data(df_feat, train_ratio=train_ratio)

    # 3. Train Model 1 (XGBoost)
    xgb_model, xgb_metrics, _ = train_xgboost_forecaster(train_df, test_df)

    # 4. Train Model 2 (Isolation Forest)
    iso_model, iso_metrics, _, _ = train_isolation_forest(
        train_df, test_df, contamination=contamination
    )

    # 5. Model persistence
    metadata = {
        "dataset_rows": len(df_feat),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "xgb_features": XGB_FEATURE_COLUMNS,
        "iso_features": ISO_FEATURE_COLUMNS,
        "xgboost_metrics": xgb_metrics,
        "isolation_forest_metrics": iso_metrics,
    }
    xgb_path, iso_path = save_trained_models(
        xgb_model=xgb_model,
        iso_model=iso_model,
        output_dir=out_dir,
        metadata=metadata,
    )

    # 6. Display final summary
    print("\n" + "=" * 55)
    print("           METRICS SUMMARY & MODEL STATUS         ")
    print("=" * 55)
    print(f"Dataset:              {input_file.name} ({len(df_feat):,} samples)")
    print(f"Train / Test Split:   {train_ratio*100:.0f}% / {(1-train_ratio)*100:.0f}% (No Shuffling)")
    print("-" * 55)
    print("MÔ HÌNH 1: XGBOOST REGRESSOR (DỰ BÁO PHỤ TẢI)")
    print(f"  - RMSE:             {xgb_metrics['rmse_kwh']:.2f} kWh")
    print(f"  - MAE:              {xgb_metrics['mae_kwh']:.2f} kWh")
    print(f"  - MAPE:             {xgb_metrics['mape_percent']:.2f}% (Mục tiêu <= 10.0%: {'ĐẠT CHUẨN' if xgb_metrics['target_mape_met'] else 'KHÔNG ĐẠT'})")
    print(f"  - R-squared (R2):   {xgb_metrics['r2_score']:.4f}")
    print(f"  - Saved file:       {xgb_path}")
    print("-" * 55)
    print("MÔ HÌNH 2: ISOLATION FOREST (PHÁT HIỆN BẤT THƯỜNG)")
    print(f"  - Contamination:    {iso_metrics['contamination']:.2f}")
    print(f"  - Anomalies Found:  {iso_metrics['anomalies_detected']} / {iso_metrics['total_test_samples']} ({iso_metrics['anomaly_percentage']:.2f}%)")
    print(f"  - Anomaly Scores:   Range [{iso_metrics['anomaly_score_min']}, {iso_metrics['anomaly_score_max']}]")
    print(f"  - Saved file:       {iso_path}")
    print("=" * 55 + "\n")

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XGBoost Forecaster & Isolation Forest Anomaly Detector")
    parser.add_argument("--data-path", type=str, default=None, help="Path to clean processed CSV")
    parser.add_argument("--models-dir", type=str, default=None, help="Directory to save .joblib models")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train ratio (default: 0.8)")
    parser.add_argument("--contamination", type=float, default=0.03, help="Contamination rate (default: 0.03)")

    args = parser.parse_args()
    run_pipeline(
        data_path=args.data_path,
        models_dir=args.models_dir,
        train_ratio=args.train_ratio,
        contamination=args.contamination,
    )
