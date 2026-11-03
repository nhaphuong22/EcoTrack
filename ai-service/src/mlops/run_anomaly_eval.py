"""
CLI for Story 4.7: evaluate the served Isolation Forest against the demo
scenarios' injected-anomaly ground truth, log a standalone MLflow run, and
merge the results into `model_metadata.json`.

Per the Epic 4 working agreement, the agent prints this command; the owner
runs it. It does not train anything, but it does mutate a git-tracked
production artifact file (`model_metadata.json`), so it gets the same
hands-off treatment as this epic's training commands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.data_pipeline.demo_scenarios import (
    generate_scenario_hvac_night_overrun,
    generate_scenario_peak_hour_spike,
    load_base_dataset,
)
from src.mlops.anomaly_quality import evaluate, log_to_mlflow, merge_into_metadata
from src.models.train_models import get_default_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Isolation Forest quality against demo scenarios")
    parser.add_argument("--models-dir", type=str, default=None, help="Directory holding isolation_forest.joblib")
    args = parser.parse_args()

    _, default_models_dir = get_default_paths()
    models_dir = Path(args.models_dir) if args.models_dir else default_models_dir
    iso_model_path = models_dir / "isolation_forest.joblib"
    iso_model = joblib.load(iso_model_path)

    base_df = load_base_dataset()
    scenarios = {
        "scenario_hvac_overrun": generate_scenario_hvac_night_overrun(base_df=base_df),
        "scenario_peak_spike": generate_scenario_peak_hour_spike(base_df=base_df),
    }

    results = {}
    for name, scenario_df in scenarios.items():
        scenario_df = scenario_df.copy()
        scenario_df["timestamp"] = pd.to_datetime(scenario_df["timestamp"])
        results[name] = evaluate(scenario_df, iso_model)
        print(f"{name}: {results[name]}")

    run_id = log_to_mlflow(results, model_path=str(iso_model_path))
    if run_id:
        print(f"Logged MLflow run: {run_id}")

    metadata_path = models_dir / "model_metadata.json"
    merge_into_metadata(metadata_path, results)
    print(f"Merged into {metadata_path}")


if __name__ == "__main__":
    main()
