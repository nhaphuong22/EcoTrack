"""
CLI entry point for the EcoTrack Optuna hyperparameter search (Story 4.5 — FR47).

Usage (run from ``ai-service/`` — the owner runs this; the agent only prints the
command, per the Epic 4 working agreement):

    python -m src.mlops.run_hpo --model both --n-trials 30

Loads the processed dataset, takes the **training split only** (the test split is
dropped before the search so it can never be read), runs an Optuna study per
requested model, logs nested trial runs to MLflow, writes the best parameters to
``experiments/benchmark/best_params.json``, and prints the exact benchmark
re-run command to produce the tuned comparison rows.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# UTF-8 console on Windows (reuse the project's guard).
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.models.train_models import (
    engineer_features,
    get_default_paths,
    load_dataset,
    split_time_series_data,
)
from src.mlops.config import OPTUNA_N_TRIALS
from src.mlops.hpo import SUPPORTED_MODELS, run_searches

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MLOpsHPO")


def _best_params_path() -> Path:
    ai_service_dir = Path(__file__).resolve().parents[2]
    return ai_service_dir / "experiments" / "benchmark" / "best_params.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Optuna hyperparameter search for EcoTrack forecasters.")
    parser.add_argument("--model", choices=["xgboost", "lstm", "both"], default="both")
    parser.add_argument("--n-trials", type=int, default=OPTUNA_N_TRIALS)
    parser.add_argument("--data-path", type=str, default=None, help="Processed CSV (defaults to the project path).")
    parser.add_argument("--study-storage", type=str, default=None, help="Optuna SQLite storage URL (default: mlruns/optuna.db).")
    parser.add_argument("--output", type=str, default=None, help="Where to write best_params.json.")
    args = parser.parse_args()

    models = list(SUPPORTED_MODELS) if args.model == "both" else [args.model]

    data_path = Path(args.data_path) if args.data_path else get_default_paths()[0]
    if not data_path.exists():
        logger.error("Processed dataset not found at %s", data_path)
        sys.exit(1)

    raw_df = load_dataset(data_path)
    df_feat = engineer_features(raw_df)
    # Take the training split only; the test split is dropped and never reaches the search.
    train_df, _test_df_unused = split_time_series_data(df_feat, train_ratio=0.8)
    logger.info("Search uses the training split only: %d rows (test split withheld).", len(train_df))

    results = run_searches(models, train_df, n_trials=args.n_trials, storage=args.study_storage)

    out_path = Path(args.output) if args.output else _best_params_path()
    best_params = {model: res["best_params"] for model, res in results.items()}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(best_params, f, indent=2)

    print("\n" + "=" * 70)
    print("           ECOTRACK HYPERPARAMETER SEARCH — BEST PARAMETERS")
    print("=" * 70)
    for model, res in results.items():
        print(f"\n[{model}] best val RMSE = {res['best_value']:.4f} kWh "
              f"({res['n_complete']} complete / {res['n_pruned']} pruned trials)")
        for key, value in res["best_params"].items():
            print(f"    - {key}: {value}")
    print("\n" + "-" * 70)
    print(f"Best parameters written to: {out_path}")
    print("\nRe-run the benchmark with the tuned parameters to compare tuned vs. untuned rows:")
    print(f"    python -m experiments.benchmark.run_benchmark --params-file \"{out_path}\"")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
