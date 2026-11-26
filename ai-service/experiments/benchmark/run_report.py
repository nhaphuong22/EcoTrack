"""
CLI entry point for the EcoTrack benchmark report (Story 4.4).

Reads the benchmark artifacts and writes four PNG charts, REPORT.md and results.json.
Pure read + render: it never fits a model or runs inference. Exits non-zero, naming the
missing path, if any required artifact is absent.

Usage:
    python -m experiments.benchmark.run_report \
        [--results PATH] [--results-by-horizon PATH] [--predictions PATH] [--out-dir DIR]
"""

import argparse
import logging
import sys
from pathlib import Path

from experiments.benchmark.report import FAR_HORIZON, generate_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BenchmarkReport")


def get_default_dir() -> Path:
    """The benchmark package directory, where run_benchmark writes its artifacts."""
    return Path(__file__).resolve().parent


def main() -> None:
    default_dir = get_default_dir()
    parser = argparse.ArgumentParser(
        description="Generate the EcoTrack benchmark report (charts, REPORT.md, results.json)."
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=default_dir / "results.csv",
        help="Path to results.csv.",
    )
    parser.add_argument(
        "--results-by-horizon",
        type=Path,
        default=default_dir / "results_by_horizon.csv",
        help="Path to results_by_horizon.csv.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=default_dir / "predictions.parquet",
        help="Path to predictions.parquet.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=default_dir,
        help="Directory to write the charts, REPORT.md and results.json into.",
    )

    args = parser.parse_args()

    try:
        written = generate_report(
            results_path=args.results,
            by_horizon_path=args.results_by_horizon,
            predictions_path=args.predictions,
            out_dir=args.out_dir,
            horizon=FAR_HORIZON,
        )
    except FileNotFoundError as exc:
        logger.error(str(exc))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - surface any render/format failure as non-zero
        logger.error("Report generation failed: %s", exc)
        sys.exit(1)

    for name, path in written.items():
        logger.info("  %-20s -> %s", name, path)


if __name__ == "__main__":
    main()
