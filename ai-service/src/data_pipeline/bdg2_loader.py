import os
import json
import math
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

def generate_synthetic_bdg2_dataset(days: int = 30) -> pd.DataFrame:
    """
    Generates realistic hourly building energy consumption modeled after
    the Building Data Genome 2 / ASHRAE Great Energy Predictor III benchmark.
    Includes normal business/weekend cycles, outdoor temperature coupling,
    and 3 realistic anomalous equipment fault events.
    """
    np.random.seed(42)
    end_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=days)
    
    timestamps = pd.date_range(start=start_time, end=end_time, freq="1h")
    records = []
    
    for ts in timestamps:
        hour = ts.hour
        day_of_week = ts.weekday() # 0 = Monday, 6 = Sunday
        is_weekend = day_of_week >= 5
        is_business_hour = (8 <= hour <= 18) and not is_weekend
        
        # Diurnal temperature cycle: peaks at 14:00, coolest at 05:00 (Hanoi / SEA typical 24-34C)
        temp_cycle = math.sin((hour - 9) * math.pi / 12)
        outdoor_temp = round(28.0 + 5.0 * temp_cycle + np.random.normal(0, 0.8), 1)
        humidity = round(70.0 - 15.0 * temp_cycle + np.random.normal(0, 2.0), 1)
        
        # Base cooling and electrical load
        if is_business_hour:
            base_load = 140.0 + 35.0 * math.sin((hour - 8) * math.pi / 10)
            cooling_load = max(0, (outdoor_temp - 24.0) * 8.5)
            occupancy_noise = np.random.normal(0, 4.0)
        elif not is_weekend:
            # Weekday night
            base_load = 42.0
            cooling_load = max(0, (outdoor_temp - 26.0) * 2.5)
            occupancy_noise = np.random.normal(0, 1.5)
        else:
            # Weekend
            base_load = 35.0
            cooling_load = max(0, (outdoor_temp - 26.0) * 2.0)
            occupancy_noise = np.random.normal(0, 1.0)
            
        load_kwh = max(15.0, base_load + cooling_load + occupancy_noise)
        
        records.append({
            "timestamp": ts.isoformat(),
            "meter_reading_kwh": round(load_kwh, 2),
            "outdoor_temperature_c": outdoor_temp,
            "relative_humidity_pct": humidity,
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": int(is_weekend),
            "is_business_hour": int(is_business_hour),
            "is_injected_anomaly": 0,
            "anomaly_reason": ""
        })
        
    df = pd.DataFrame(records)
    
    # Inject 3 realistic historical anomalies into the time series
    # 1. Anomaly 1: Saturday overnight chiller bypass damper stuck open (Days ago: ~14)
    target_idx_1 = max(0, len(df) - 24 * 14 + 23)
    if target_idx_1 + 6 < len(df):
        for i in range(target_idx_1, target_idx_1 + 6):
            df.loc[i, "meter_reading_kwh"] += 65.0 # Elevated power during unoccupied night
            df.loc[i, "is_injected_anomaly"] = 1
            df.loc[i, "anomaly_reason"] = "Chiller damper stuck open overnight; building unoccupied"
            
    # 2. Anomaly 2: Tuesday afternoon cooling load spike (Days ago: ~7)
    target_idx_2 = max(0, len(df) - 24 * 7 + 14)
    if target_idx_2 + 3 < len(df):
        for i in range(target_idx_2, target_idx_2 + 3):
            df.loc[i, "meter_reading_kwh"] += 85.0 # Sharp power surge
            df.loc[i, "is_injected_anomaly"] = 1
            df.loc[i, "anomaly_reason"] = "HVAC compressor short cycling & simultaneous chiller surge"
            
    # 3. Anomaly 3: Recent baseload leakage (Days ago: ~2, Sunday morning)
    target_idx_3 = max(0, len(df) - 24 * 2 + 3)
    if target_idx_3 + 4 < len(df):
        for i in range(target_idx_3, target_idx_3 + 4):
            df.loc[i, "meter_reading_kwh"] += 45.0
            df.loc[i, "is_injected_anomaly"] = 1
            df.loc[i, "anomaly_reason"] = "Zone lighting and fan coil units left running after overtime shift"
            
    return df

AI_SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = AI_SERVICE_ROOT / "data" / "sample_bdg2_energy.json"

class BDG2DataLoader:
    def __init__(self, data_path: Optional[str] = None):
        self.data_path = Path(data_path) if data_path else DEFAULT_DATA_PATH
        self._df = None

    def get_or_create_data(self) -> pd.DataFrame:
        if self._df is not None:
            return self._df
            
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._df = pd.DataFrame(data)
                return self._df
            except Exception:
                pass
                
        # Generate and cache if missing
        self._df = generate_synthetic_bdg2_dataset(days=30)
        os.makedirs(os.path.dirname(self.data_path) or ".", exist_ok=True)
        self._df.to_json(self.data_path, orient="records", indent=2)
        return self._df

# Global singleton loader
data_loader = BDG2DataLoader()
