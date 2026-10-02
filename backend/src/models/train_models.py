"""
Train script for EcoTrack Machine Learning Models:
1. XGBoost Energy Forecaster
2. Isolation Forest Anomaly Detector

Dataset: Building Data Genome 2 (BDG2) - Building 'Hog_office_Betsy'
Outputs:
- backend/models_saved/xgboost_forecaster.joblib
- backend/models_saved/isolation_forest.joblib
- backend/models_saved/model_metadata.json
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.ensemble import IsolationForest
import xgboost as xgb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

XGB_FEATURE_COLUMNS = [
    "air_temperature",
    "hour",
    "dayofweek",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "lag_1h",
    "lag_24h"
]

ISO_FEATURE_COLUMNS = [
    "meter_reading",
    "air_temperature",
    "hour",
    "dayofweek",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "lag_1h",
    "lag_24h"
]

def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    df["dayofweek"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = df["dayofweek"].isin([5, 6]).astype(int)
    
    # Cyclical hour encoding
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    
    # Lag features
    df["lag_1h"] = df["meter_reading"].shift(1)
    df["lag_24h"] = df["meter_reading"].shift(24)
    
    return df.dropna().reset_index(drop=True)

def split_time_series_data(df: pd.DataFrame, train_ratio: float = 0.8):
    """Performs chronological train/test split (without shuffling)."""
    split_index = int(len(df) * train_ratio)
    train_df = df.iloc[:split_index].copy()
    test_df = df.iloc[split_index:].copy()
    logging.info(
        f"Time-series split ({train_ratio*100:.0f}% / {(1-train_ratio)*100:.0f}%): "
        f"Train={len(train_df)} rows ({train_df['timestamp'].min()} to {train_df['timestamp'].max()}) | "
        f"Test={len(test_df)} rows ({test_df['timestamp'].min()} to {test_df['timestamp'].max()})"
    )
    return train_df, test_df

def train_and_evaluate(data_path: str = "backend/data/processed/office_building_clean.csv", output_dir: str = "backend/models_saved"):
    if not os.path.exists(data_path):
        # Fallback relative path check
        if os.path.exists("../data/processed/office_building_clean.csv"):
            data_path = "../data/processed/office_building_clean.csv"
            output_dir = "../models_saved"
            
    logging.info(f"Loading data from {data_path}...")
    df_raw = pd.read_csv(data_path)
    df = prepare_features(df_raw)
    logging.info(f"Clean samples after feature engineering: {len(df)}")
    
    train_df, test_df = split_time_series_data(df, train_ratio=0.8)
    
    # 1. Train XGBoost
    logging.info("Training XGBoost Energy Forecaster...")
    xgb_model = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=350,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        random_state=42,
        n_jobs=-1
    )
    xgb_model.fit(train_df[XGB_FEATURE_COLUMNS], train_df["meter_reading"])
    
    # Evaluate XGBoost
    y_test = test_df["meter_reading"]
    y_pred = xgb_model.predict(test_df[XGB_FEATURE_COLUMNS])
    
    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = float(r2_score(y_test, y_pred))
    mape = float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100)
    
    xgb_metrics = {
        "MAE": round(mae, 2),
        "RMSE": round(rmse, 2),
        "R2": round(r2, 4),
        "MAPE_pct": round(mape, 2)
    }
    logging.info(f"XGBoost Test Metrics: MAE={mae:.2f} kWh, RMSE={rmse:.2f} kWh, R2={r2:.4f}, MAPE={mape:.2f}%")
    
    # 2. Train Isolation Forest
    logging.info("Training Isolation Forest Anomaly Detector...")
    iso_model = IsolationForest(
        n_estimators=150,
        contamination=0.03,
        max_samples="auto",
        random_state=42,
        n_jobs=-1
    )
    iso_model.fit(train_df[ISO_FEATURE_COLUMNS])
    
    # Evaluate Isolation Forest
    iso_preds = iso_model.predict(test_df[ISO_FEATURE_COLUMNS])
    test_anomalies = int((iso_preds == -1).sum())
    test_normal = int((iso_preds == 1).sum())
    scores = iso_model.decision_function(test_df[ISO_FEATURE_COLUMNS])
    
    iso_metrics = {
        "test_total_samples": len(test_df),
        "anomalies_detected": test_anomalies,
        "anomaly_rate_pct": round((test_anomalies / len(test_df)) * 100, 2),
        "normal_samples": test_normal,
        "decision_score_min": round(float(scores.min()), 4),
        "decision_score_max": round(float(scores.max()), 4),
        "decision_score_mean": round(float(scores.mean()), 4)
    }
    logging.info(f"Isolation Forest Test Results: {test_anomalies} anomalies / {len(test_df)} samples ({iso_metrics['anomaly_rate_pct']}%)")
    
    # Save artifacts
    os.makedirs(output_dir, exist_ok=True)
    joblib.dump(xgb_model, os.path.join(output_dir, "xgboost_forecaster.joblib"))
    joblib.dump(iso_model, os.path.join(output_dir, "isolation_forest.joblib"))
    
    metadata = {
        "dataset": {
            "source": "Building Data Genome 2 (BDG2)",
            "building_id": "Hog_office_Betsy",
            "primary_use": "Office",
            "total_clean_samples": len(df),
            "date_range": {
                "start": str(df["timestamp"].min()),
                "end": str(df["timestamp"].max())
            },
            "split": {
                "strategy": "Time-Series Split (Chronological, No Shuffle)",
                "train_ratio": 0.8,
                "test_ratio": 0.2,
                "train_samples": len(train_df),
                "train_range": {"start": str(train_df["timestamp"].min()), "end": str(train_df["timestamp"].max())},
                "test_samples": len(test_df),
                "test_range": {"start": str(test_df["timestamp"].min()), "end": str(test_df["timestamp"].max())}
            },
            "features": {
                "cyclical": ["hour_sin", "hour_cos"],
                "temporal": ["hour", "dayofweek", "is_weekend"],
                "lag": ["lag_1h", "lag_24h"],
                "exogenous": ["air_temperature"]
            }
        },
        "xgboost_forecaster": {
            "model_type": "XGBRegressor",
            "hyperparameters": {
                "n_estimators": 350,
                "max_depth": 4,
                "learning_rate": 0.05,
                "subsample": 0.85,
                "colsample_bytree": 0.85,
                "random_state": 42
            },
            "feature_importance": dict(zip(XGB_FEATURE_COLUMNS, [round(float(x), 4) for x in xgb_model.feature_importances_])),
            "metrics_test": xgb_metrics
        },
        "isolation_forest_anomaly_detector": {
            "model_type": "IsolationForest",
            "hyperparameters": {
                "n_estimators": 150,
                "contamination": 0.03,
                "max_samples": "auto",
                "random_state": 42
            },
            "test_evaluation": iso_metrics,
            "severity_tiers": {
                "CRITICAL_OR_HIGH": "decision_score <= -0.05 hoặc residual > 60 kWh",
                "MEDIUM": "-0.05 < decision_score <= -0.02 hoặc residual > 35 kWh",
                "LOW": "decision_score > -0.02"
            }
        },
        "scenarios": {
            "hvac_overrun": {
                "description": "HVAC chạy quá tải ban đêm (22:00 - 05:00)",
                "time_window": "2016-01-04 22:00:00 to 2016-01-05 05:00:00",
                "duration_hours": 8,
                "baseline_kwh": "220.47 - 268.08 kWh",
                "actual_spike_kwh": "748.13 - 762.18 kWh (~750 kWh)",
                "excess_consumption_kwh": 4056.2
            },
            "peak_spike": {
                "description": "Phụ tải tăng vọt vào khung giờ cao điểm biểu giá EVN",
                "time_windows": ["2016-01-05 10:00:00 to 11:00:00", "2016-01-05 18:00:00 to 19:00:00"],
                "duration_hours": 4,
                "baseline_kwh": "265.20 - 322.12 kWh",
                "actual_spike_kwh": "2857.56 - 2890.60 kWh (~2,850 kWh)",
                "excess_consumption_kwh": 10283.4
            }
        }
    }
    
    meta_path = os.path.join(output_dir, "model_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        
    logging.info(f"Models and metadata successfully saved to: {output_dir}")

if __name__ == "__main__":
    train_and_evaluate()
