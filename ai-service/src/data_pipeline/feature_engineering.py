import numpy as np
import pandas as pd

def add_time_and_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes time-series cyclic encodings, lag features, and rolling statistics
    as specified in PRD FR-2 and Technical Addendum §1.1.
    """
    df = df.copy()
    
    # 1. Cyclic time encodings
    df["sin_hour"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["cos_hour"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    df["sin_day"] = np.sin(2 * np.pi * df["day_of_week"] / 7.0)
    df["cos_day"] = np.cos(2 * np.pi * df["day_of_week"] / 7.0)
    
    # 2. Lag features (t-1 hour, t-24 hours)
    df["lag_1h"] = df["meter_reading_kwh"].shift(1)
    df["lag_24h"] = df["meter_reading_kwh"].shift(24)
    
    # 3. Rolling statistics
    df["rolling_mean_24h"] = df["meter_reading_kwh"].shift(1).rolling(window=24, min_periods=1).mean()
    df["rolling_std_24h"] = df["meter_reading_kwh"].shift(1).rolling(window=24, min_periods=1).std().fillna(0)
    
    # Backfill earliest rows where shift created NaNs
    df["lag_1h"] = df["lag_1h"].bfill()
    df["lag_24h"] = df["lag_24h"].bfill()
    df["rolling_mean_24h"] = df["rolling_mean_24h"].bfill()
    df["rolling_std_24h"] = df["rolling_std_24h"].bfill()
    
    return df
