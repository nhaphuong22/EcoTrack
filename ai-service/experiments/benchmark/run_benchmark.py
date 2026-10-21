"""
CLI entry point for the EcoTrack Forecasting Benchmark Harness.
Usage:
    python -m experiments.benchmark.run_benchmark [--data-path PATH] [--output PATH]
"""

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Optional
import pandas as pd

from src.models.train_models import (
    engineer_features,
    load_dataset,
    split_time_series_data,
)
from experiments.benchmark.benchmark import run_scoring

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BenchmarkHarness")


def get_default_paths() -> tuple[Path, Path]:
    """Resolves default paths for dataset input and results output."""
    backend_dir = Path(__file__).resolve().parents[2]
    env_data_path = os.environ.get("ECOTRACK_DATA_PATH")
    if env_data_path:
        default_data_path = Path(env_data_path)
    else:
        default_data_path = backend_dir / "data" / "processed" / "office_building_clean.csv"

    default_output_path = backend_dir / "experiments" / "benchmark" / "results.csv"
    return default_data_path, default_output_path


def execute_benchmark(
    data_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Executes the end-to-end benchmark evaluation and writes results to CSV.

    Parameters:
    -----------
    data_path: Optional[Path]
        Path to processed energy consumption CSV.
    output_path: Optional[Path]
        Destination path for benchmark results.csv.

    Returns:
    --------
    pd.DataFrame:
        DataFrame containing scored model results.
    """
    default_data, default_output = get_default_paths()
    data_file = Path(data_path) if data_path else default_data
    out_file = Path(output_path) if output_path else default_output

    if not data_file.exists():
        raise FileNotFoundError(f"Benchmark dataset not found: {data_file}")

    logger.info("Loading dataset from %s...", data_file)
    raw_df = load_dataset(data_file)

    logger.info("Applying feature engineering (temporal, cyclical, and lags)...")
    df_feat = engineer_features(raw_df)

    logger.info("Splitting time-series partition (80%% train / 20%% test)...")
    train_df, test_df = split_time_series_data(df_feat, train_ratio=0.8)
    logger.info("Partitions prepared: Train=%d rows, Test=%d rows.", len(train_df), len(test_df))

    logger.info("Evaluating registered models...")
    results_df = run_scoring(train_df=train_df, test_df=test_df)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(out_file, index=False)
    logger.info("Benchmark results saved to %s", out_file)

    return results_df


def print_summary_table(results_df: pd.DataFrame) -> None:
    """Prints a clean ASCII summary table of the benchmark results."""
    print("\n" + "=" * 118)
    print(" " * 40 + "ECOTRACK FORECASTING BENCHMARK RESULTS")
    print("=" * 118)
    header = f"{'Model':<18} | {'MAE (kWh)':<10} | {'RMSE (kWh)':<10} | {'MAPE (%)':<9} | {'R²':<7} | {'Train (s)':<9} | {'Latency (ms)':<12} | {'Size (KB)':<9} | {'Window (h)':<10}"
    print(header)
    print("-" * 118)
    for _, row in results_df.iterrows():
        size_kb = row["model_file_size_bytes"] / 1024.0
        line = (
            f"{row['model']:<18} | "
            f"{row['mae_kwh']:<10.2f} | "
            f"{row['rmse_kwh']:<10.2f} | "
            f"{row['mape_percent']:<9.2f} | "
            f"{row['r2']:<7.4f} | "
            f"{row['training_time_s']:<9.2f} | "
            f"{row['mean_inference_latency_ms']:<12.4f} | "
            f"{size_kb:<9.1f} | "
            f"{int(row['train_window_hours']):<10}"
        )
        print(line)
    print("=" * 118 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run benchmark comparison across EcoTrack energy consumption forecasters."
    )
    default_data, default_output = get_default_paths()
    parser.add_argument(
        "--data-path",
        type=Path,
        default=default_data,
        help="Path to the processed office building dataset CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help="Path to write the benchmark results.csv.",
    )

    args = parser.parse_args()

    try:
        results_df = execute_benchmark(data_path=args.data_path, output_path=args.output)
        print_summary_table(results_df)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error("Benchmark execution failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
