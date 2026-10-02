"""
Script to extract, clean, and merge BDG2 data for a representative office building.

Steps:
1. Reads `metadata.csv` to identify office buildings and selects the representative building
   with the lowest missing/zero rate and highest data completeness.
2. Extracts only `timestamp` and the selected office building's electricity consumption
   from `electricity_cleaned.csv`.
3. Merges with corresponding outdoor air temperature from `weather.csv` by matching `site_id` and `timestamp`.
4. Handles any missing values using linear interpolation (with forward/backward fill for boundaries).
5. Exports clean, lightweight dataset to `backend/data/processed/office_building_clean.csv`.
"""

import argparse
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BDG2OfficeExtractor")


def get_default_paths() -> Tuple[Path, Path]:
    """Resolves default raw directory and output file paths relative to this script."""
    backend_dir = Path(__file__).resolve().parents[2]
    raw_dir = backend_dir / "data" / "raw"
    output_path = backend_dir / "data" / "processed" / "office_building_clean.csv"
    return raw_dir, output_path


def find_best_office_building(
    raw_dir: Path, target_building_id: Optional[str] = None
) -> Tuple[str, str, Dict]:
    """
    Finds the representative office building from metadata.csv and electricity_cleaned.csv.
    If target_building_id is specified, verifies it and retrieves its site_id.
    Otherwise, evaluates all office buildings and picks the one with the lowest missing/zero rate.
    """
    meta_path = raw_dir / "metadata.csv"
    elec_path = raw_dir / "electricity_cleaned.csv"

    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.csv not found at: {meta_path}")
    if not elec_path.exists():
        raise FileNotFoundError(f"electricity_cleaned.csv not found at: {elec_path}")

    logger.info("Reading metadata from %s...", meta_path.name)
    meta_df = pd.read_csv(meta_path)

    # Detect primary use column ('primaryspaceusage' or 'primary_use')
    primary_col = None
    for col in ["primaryspaceusage", "primary_use", "primary_space_usage"]:
        if col in meta_df.columns:
            primary_col = col
            break

    if not primary_col:
        raise KeyError("Could not find primary use column (e.g. primaryspaceusage) in metadata.csv")

    # Filter for office buildings
    office_mask = meta_df[primary_col].astype(str).str.lower() == "office"
    office_df = meta_df[office_mask].copy()
    logger.info("Found %d office buildings in metadata.csv.", len(office_df))

    # Read column header of electricity_cleaned.csv
    with open(elec_path, "r", encoding="utf-8") as f:
        elec_header = set(f.readline().strip().split(","))

    available_offices = office_df[office_df["building_id"].isin(elec_header)]["building_id"].tolist()
    logger.info("Found %d office buildings available in %s.", len(available_offices), elec_path.name)

    if not available_offices:
        raise ValueError("No office buildings from metadata were found in electricity_cleaned.csv header.")

    if target_building_id:
        if target_building_id not in available_offices:
            raise ValueError(f"Specified building_id '{target_building_id}' is not an available office building.")
        selected_building = target_building_id
    else:
        # Evaluate candidate office buildings to select the one with lowest missing & zero values
        logger.info("Scanning candidate office buildings for data completeness...")
        cols_to_read = ["timestamp"] + available_offices
        df_eval = pd.read_csv(elec_path, usecols=cols_to_read)

        null_counts = df_eval[available_offices].isnull().sum()
        zero_counts = (df_eval[available_offices] == 0).sum()
        std_devs = df_eval[available_offices].std()
        means = df_eval[available_offices].mean()

        scores = pd.DataFrame({
            "null_count": null_counts,
            "zero_count": zero_counts,
            "mean": means,
            "std": std_devs,
        })

        # Rank by: fewest nulls -> fewest zeros -> healthy standard deviation
        sorted_candidates = scores.sort_values(
            by=["null_count", "zero_count", "std"],
            ascending=[True, True, False]
        )
        selected_building = sorted_candidates.index[0]
        best_stats = sorted_candidates.iloc[0].to_dict()
        logger.info(
            "Selected best office building: '%s' (Nulls: %d, Zeros: %d, Mean: %.2f kWh, Std: %.2f)",
            selected_building,
            int(best_stats["null_count"]),
            int(best_stats["zero_count"]),
            best_stats["mean"],
            best_stats["std"],
        )

    # Get site_id and metadata info
    building_row = meta_df[meta_df["building_id"] == selected_building].iloc[0]
    site_id = str(building_row["site_id"])
    meta_info = {
        "building_id": selected_building,
        "site_id": site_id,
        "primary_use": building_row[primary_col],
        "sqm": building_row.get("sqm", None),
        "timezone": building_row.get("timezone", None),
    }

    logger.info("Selected building info: Site='%s', SQM=%s, Timezone='%s'", site_id, meta_info.get("sqm"), meta_info.get("timezone"))
    return selected_building, site_id, meta_info


def extract_electricity_series(raw_dir: Path, building_id: str) -> pd.DataFrame:
    """Extracts timestamp and meter reading for the target building."""
    elec_path = raw_dir / "electricity_cleaned.csv"
    logger.info("Extracting '%s' from %s...", building_id, elec_path.name)
    df_elec = pd.read_csv(elec_path, usecols=["timestamp", building_id])
    df_elec = df_elec.rename(columns={building_id: "meter_reading"})
    df_elec["timestamp"] = pd.to_datetime(df_elec["timestamp"])
    return df_elec


def extract_weather_series(raw_dir: Path, site_id: str) -> pd.DataFrame:
    """Extracts outdoor air temperature for the site corresponding to the building."""
    weather_path = raw_dir / "weather.csv"
    if not weather_path.exists():
        raise FileNotFoundError(f"weather.csv not found at: {weather_path}")

    logger.info("Extracting weather for site '%s' from %s...", site_id, weather_path.name)
    df_weather = pd.read_csv(weather_path)

    temp_col = None
    for col in ["airTemperature", "air_temperature", "air_temp"]:
        if col in df_weather.columns:
            temp_col = col
            break

    if not temp_col:
        raise KeyError("Could not find air temperature column in weather.csv")

    site_weather = df_weather[df_weather["site_id"].astype(str) == str(site_id)].copy()
    if site_weather.empty:
        raise ValueError(f"No weather records found for site_id: '{site_id}'")

    site_weather = site_weather[["timestamp", temp_col]].rename(columns={temp_col: "air_temperature"})
    site_weather["timestamp"] = pd.to_datetime(site_weather["timestamp"])
    site_weather = site_weather.drop_duplicates(subset=["timestamp"])
    return site_weather


def merge_and_clean_data(
    df_elec: pd.DataFrame, df_weather: pd.DataFrame
) -> pd.DataFrame:
    """
    Merges electricity and weather time series by timestamp,
    sorts chronologically, and imputes any missing values via linear interpolation.
    """
    logger.info("Merging electricity and weather time series...")
    merged = pd.merge(df_elec, df_weather, on="timestamp", how="left")
    merged = merged.sort_values("timestamp").reset_index(drop=True)

    null_summary_before = merged.isnull().sum().to_dict()
    logger.info("Missing values before interpolation: %s", null_summary_before)

    # Linear interpolation across time, followed by ffill and bfill for edge values
    merged["meter_reading"] = (
        merged["meter_reading"]
        .interpolate(method="linear")
        .ffill()
        .bfill()
        .round(2)
    )
    merged["air_temperature"] = (
        merged["air_temperature"]
        .interpolate(method="linear")
        .ffill()
        .bfill()
        .round(2)
    )

    null_summary_after = merged.isnull().sum().to_dict()
    logger.info("Missing values after interpolation: %s", null_summary_after)

    # Format timestamp as clean string for CSV storage
    merged["timestamp"] = merged["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Reorder columns explicitly
    merged = merged[["timestamp", "meter_reading", "air_temperature"]]
    return merged


def export_clean_dataset(
    df: pd.DataFrame, output_path: Path
) -> Path:
    """Saves the processed DataFrame to CSV and displays file metadata."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Successfully exported clean dataset to: %s (%.2f MB, %d rows)",
        output_path,
        file_size_mb,
        len(df),
    )
    return output_path


def run_pipeline(
    raw_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    building_id: Optional[str] = None,
) -> Path:
    """Executes the complete extraction, merge, interpolation, and export pipeline."""
    default_raw, default_out = get_default_paths()
    raw_path = Path(raw_dir) if raw_dir else default_raw
    out_path = Path(output_path) if output_path else default_out

    logger.info("Starting Office Building Extraction Pipeline...")
    logger.info("Raw data directory: %s", raw_path)
    logger.info("Output target path: %s", out_path)

    selected_building, site_id, meta_info = find_best_office_building(
        raw_dir=raw_path, target_building_id=building_id
    )

    df_elec = extract_electricity_series(raw_dir=raw_path, building_id=selected_building)
    df_weather = extract_weather_series(raw_dir=raw_path, site_id=site_id)
    df_clean = merge_and_clean_data(df_elec=df_elec, df_weather=df_weather)

    exported_file = export_clean_dataset(df_clean, output_path=out_path)
    logger.info("Pipeline completed successfully!")
    return exported_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract and clean BDG2 electricity and weather data for a representative office building."
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default=None,
        help="Path to directory containing raw BDG2 CSV files (metadata.csv, electricity_cleaned.csv, weather.csv).",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Path where the processed office_building_clean.csv should be saved.",
    )
    parser.add_argument(
        "--building-id",
        type=str,
        default=None,
        help="Optional explicit office building ID (e.g. 'Hog_office_Betsy'). If omitted, optimal building is chosen automatically.",
    )

    args = parser.parse_args()
    run_pipeline(
        raw_dir=args.raw_dir,
        output_path=args.output_path,
        building_id=args.building_id,
    )
