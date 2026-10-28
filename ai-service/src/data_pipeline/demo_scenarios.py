"""
Demo Scenario Data Generator for EcoTrack (Sprint 4: TV1 & TV2):
Generates realistic edge-case operational scenarios based on clean building telemetry
for demonstrations, load testing, and AI Copilot financial impact evaluations.

Scenarios:
1. HVAC Night Overrun:
   Simulates HVAC and chiller plant left running at high load (~750 kWh) during
   unoccupied weekday night hours (22:00 - 05:00, baseline ~230 kWh).
2. EVN Peak Hour Demand Spike:
   Simulates demand spikes during EVN peak tariff windows (10:00 - 11:00 and 18:00 - 19:00)
   exceeding the contract design demand (~2850 kWh) to test AI Copilot surcharge penalty calculations.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

logger = logging.getLogger("DemoScenarios")


def get_default_paths() -> Tuple[Path, Path]:
    """Resolves default paths for processed data source and output directory."""
    backend_dir = Path(__file__).resolve().parents[2]
    base_data_path = backend_dir / "data" / "processed" / "office_building_clean.csv"
    output_dir = backend_dir / "data" / "processed"
    return base_data_path, output_dir


def load_base_dataset(base_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Loads base clean dataset from argument, file, or fallback generator.
    Ensures timestamp, meter_reading, and air_temperature are present.
    """
    if base_df is not None:
        df = base_df.copy()
    else:
        base_data_path, _ = get_default_paths()
        if base_data_path.exists():
            df = pd.read_csv(base_data_path)
        else:
            # Fallback for CI/CD environments
            from src.data_pipeline.stream_worker import StreamDataWorker
            worker = StreamDataWorker()
            df = worker._df.copy() if worker._df is not None else worker._create_fallback_dataset()

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def generate_scenario_hvac_night_overrun(
    base_df: Optional[pd.DataFrame] = None,
    target_overrun_kwh: float = 750.0,
    noise_std: float = 8.0,
) -> pd.DataFrame:
    """
    Scenario 1: HVAC & Chiller Overnight Runaway
    Injects anomalous high-power HVAC consumption (~750 kWh) across an unoccupied
    weekday overnight shift (22:00 to 05:00 next morning), where normal load is ~230 kWh.

    Parameters:
    -----------
    base_df: Optional[pd.DataFrame]
        Base clean time series DataFrame.
    target_overrun_kwh: float
        Elevated power load (default ~750.0 kWh).
    noise_std: float
        Gaussian jitter to simulate realistic equipment load fluctuation.

    Returns:
    --------
    pd.DataFrame:
        DataFrame containing full time-series with overnight anomaly injected.
    """
    df = load_base_dataset(base_df)
    np.random.seed(42)

    # Locate first weekday overnight window (Monday 22:00 -> Tuesday 05:00)
    # dayofweek 0 is Monday, 1 is Tuesday
    target_start_idx = None
    for i in range(24, len(df) - 10):
        ts = df.loc[i, "timestamp"]
        if ts.dayofweek == 0 and ts.hour == 22:
            target_start_idx = i
            break

    # If no Monday 22:00 found, find any weekday 22:00
    if target_start_idx is None:
        for i in range(24, len(df) - 10):
            ts = df.loc[i, "timestamp"]
            if ts.dayofweek < 4 and ts.hour == 22:
                target_start_idx = i
                break

    # Fallback to index 22 if calendar search yields no match
    if target_start_idx is None:
        target_start_idx = 22

    # Inject 8 consecutive hours of overnight overrun (22:00, 23:00, 00:00, 01:00, 02:00, 03:00, 04:00, 05:00)
    overrun_indices = list(range(target_start_idx, target_start_idx + 8))

    for idx in overrun_indices:
        jitter = float(np.random.normal(0, noise_std))
        df.loc[idx, "meter_reading"] = round(target_overrun_kwh + jitter, 2)

    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        "Generated HVAC night overrun scenario (%d hours modified around %s).",
        len(overrun_indices),
        df.loc[target_start_idx, "timestamp"],
    )
    return df[["timestamp", "meter_reading", "air_temperature"]]


def generate_scenario_peak_hour_spike(
    base_df: Optional[pd.DataFrame] = None,
    target_spike_kwh: float = 2850.0,
    noise_std: float = 15.0,
) -> pd.DataFrame:
    """
    Scenario 2: EVN Peak Hour Demand Spike
    Injects demand surges during official EVN peak tariff windows:
    - Morning Peak: 10:00 - 11:00
    - Evening Peak: 18:00 - 19:00
    Elevates load to ~2850 kWh (exceeding building design capacity ~2500 kWh)
    for testing AI Copilot peak demand penalty calculation and tariff alerts.

    Parameters:
    -----------
    base_df: Optional[pd.DataFrame]
        Base clean time series DataFrame.
    target_spike_kwh: float
        Surge demand load exceeding capacity (default ~2850.0 kWh).
    noise_std: float
        Gaussian jitter.

    Returns:
    --------
    pd.DataFrame:
        DataFrame with EVN peak hour spikes injected.
    """
    df = load_base_dataset(base_df)
    np.random.seed(101)

    # Locate a target weekday (Tuesday or Wednesday)
    target_day_idx = None
    for i in range(24, len(df) - 30):
        ts = df.loc[i, "timestamp"]
        if ts.dayofweek == 1 and ts.hour == 0:  # Tuesday midnight start
            target_day_idx = i
            break

    if target_day_idx is None:
        target_day_idx = 24

    # Inject morning peak (10:00 - 11:00, i.e. hours 10, 11)
    # and evening peak (18:00 - 19:00, i.e. hours 18, 19)
    peak_offsets = [10, 11, 18, 19]
    spike_indices = [target_day_idx + offset for offset in peak_offsets if target_day_idx + offset < len(df)]

    for idx in spike_indices:
        jitter = float(np.random.normal(0, noise_std))
        df.loc[idx, "meter_reading"] = round(target_spike_kwh + jitter, 2)

    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(
        "Generated EVN peak hour spike scenario (%d hours spiked at indices %s).",
        len(spike_indices),
        spike_indices,
    )
    return df[["timestamp", "meter_reading", "air_temperature"]]


def export_demo_scenarios(
    output_dir: Optional[Union[str, Path]] = None,
    base_df: Optional[pd.DataFrame] = None,
) -> Tuple[Path, Path]:
    """
    Generates and exports both demo scenarios to CSV files:
    - `scenario_hvac_overrun.csv`
    - `scenario_peak_spike.csv`

    Returns:
    --------
    Tuple[Path, Path]:
        Paths to the generated scenario CSV files.
    """
    _, default_out = get_default_paths()
    target_dir = Path(output_dir) if output_dir else default_out
    target_dir.mkdir(parents=True, exist_ok=True)

    hvac_path = target_dir / "scenario_hvac_overrun.csv"
    peak_path = target_dir / "scenario_peak_spike.csv"

    logger.info("Exporting demo scenarios to: %s...", target_dir)

    # 1. Generate and save Scenario 1
    df_hvac = generate_scenario_hvac_night_overrun(base_df=base_df)
    df_hvac.to_csv(hvac_path, index=False)
    logger.info("Saved HVAC Overrun Scenario: %s (%d rows)", hvac_path.name, len(df_hvac))

    # 2. Generate and save Scenario 2
    df_peak = generate_scenario_peak_hour_spike(base_df=base_df)
    df_peak.to_csv(peak_path, index=False)
    logger.info("Saved Peak Spike Scenario: %s (%d rows)", peak_path.name, len(df_peak))

    return hvac_path, peak_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and export demo scenarios for EcoTrack")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save scenario CSVs")
    args = parser.parse_args()

    export_demo_scenarios(output_dir=args.output_dir)
