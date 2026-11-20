import os
import shutil
import tempfile
from pathlib import Path
import pytest

from src.data_pipeline.serving_frame import reset_serving_cache
from src.mlops.scheduler import stop_scheduler
from src.models.train_models import (
    ISO_FEATURE_COLUMNS,
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    save_trained_models,
    split_time_series_data,
    train_isolation_forest,
    train_quantile_forecaster,
    train_xgboost_forecaster,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Session fixture that trains both models from the fixture sample into a temp dir,
    sets ECOTRACK_DATA_PATH and ECOTRACK_MODELS_DIR, and resets serving cache.
    """
    fixture_csv = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"
    temp_dir = tempfile.mkdtemp(prefix="ecotrack_test_models_")
    temp_models_dir = Path(temp_dir)

    raw_df = load_dataset(fixture_csv)
    df_feat = engineer_features(raw_df)
    train_df, test_df = split_time_series_data(df_feat, train_ratio=0.8)

    xgb_model, xgb_metrics, _ = train_xgboost_forecaster(train_df, test_df)
    quantile_model, quantile_metrics, _ = train_quantile_forecaster(train_df, test_df)
    iso_model, iso_metrics, _, _ = train_isolation_forest(train_df, test_df, contamination=0.03)

    metadata = {
        "dataset_rows": len(df_feat),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "xgb_features": XGB_FEATURE_COLUMNS,
        "iso_features": ISO_FEATURE_COLUMNS,
        "xgboost_metrics": xgb_metrics,
        "quantile_metrics": quantile_metrics,
        "isolation_forest_metrics": iso_metrics,
    }

    save_trained_models(
        xgb_model=xgb_model,
        iso_model=iso_model,
        output_dir=temp_models_dir,
        metadata=metadata,
        quantile_model=quantile_model,
    )

    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
    old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")
    old_internal_key = os.environ.get("INTERNAL_API_KEY")
    old_disable_mlflow = os.environ.get("ECOTRACK_DISABLE_MLFLOW")
    old_scheduler_enabled = os.environ.get("ECOTRACK_SCHEDULER_ENABLED")
    old_scheduler_interval = os.environ.get("ECOTRACK_SCHEDULER_INTERVAL_SECONDS")
    old_scheduler_delay = os.environ.get("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS")
    old_drift_recent = os.environ.get("ECOTRACK_DRIFT_RECENT_PATH")
    old_benchmark_results = os.environ.get("ECOTRACK_BENCHMARK_RESULTS_PATH")

    os.environ["ECOTRACK_DATA_PATH"] = str(fixture_csv)
    os.environ["ECOTRACK_MODELS_DIR"] = str(temp_models_dir)
    os.environ["INTERNAL_API_KEY"] = "test-internal-token"
    # Default the suite to the models_saved/ serving path so a stray MLflow store on the
    # owner's machine cannot leak a real champion into fixture-based tests. The dedicated
    # champion-load tests opt back in with their own temp store (Story 4.5).
    os.environ["ECOTRACK_DISABLE_MLFLOW"] = "1"
    # Keep background drift-check scheduler disabled across the test suite (Story 4.9).
    # Set optional Story 4.9 overrides to empty string rather than popping so load_dotenv(override=False)
    # cannot re-inject developer .env values later in test execution.
    os.environ["ECOTRACK_SCHEDULER_ENABLED"] = "0"
    os.environ["ECOTRACK_SCHEDULER_INTERVAL_SECONDS"] = ""
    os.environ["ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS"] = ""
    os.environ["ECOTRACK_DRIFT_RECENT_PATH"] = ""
    os.environ["ECOTRACK_BENCHMARK_RESULTS_PATH"] = str(temp_models_dir / "benchmark_results.json")
    reset_serving_cache()

    yield {
        "data_path": fixture_csv,
        "models_dir": temp_models_dir,
        "metadata": metadata,
    }

    stop_scheduler(timeout=2.0)
    reset_serving_cache()
    if old_data_path is not None:
        os.environ["ECOTRACK_DATA_PATH"] = old_data_path
    else:
        os.environ.pop("ECOTRACK_DATA_PATH", None)

    if old_models_dir is not None:
        os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
    else:
        os.environ.pop("ECOTRACK_MODELS_DIR", None)

    if old_internal_key is not None:
        os.environ["INTERNAL_API_KEY"] = old_internal_key
    else:
        os.environ.pop("INTERNAL_API_KEY", None)

    if old_disable_mlflow is not None:
        os.environ["ECOTRACK_DISABLE_MLFLOW"] = old_disable_mlflow
    else:
        os.environ.pop("ECOTRACK_DISABLE_MLFLOW", None)

    if old_scheduler_enabled is not None:
        os.environ["ECOTRACK_SCHEDULER_ENABLED"] = old_scheduler_enabled
    else:
        os.environ.pop("ECOTRACK_SCHEDULER_ENABLED", None)

    if old_scheduler_interval is not None:
        os.environ["ECOTRACK_SCHEDULER_INTERVAL_SECONDS"] = old_scheduler_interval
    else:
        os.environ.pop("ECOTRACK_SCHEDULER_INTERVAL_SECONDS", None)

    if old_scheduler_delay is not None:
        os.environ["ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS"] = old_scheduler_delay
    else:
        os.environ.pop("ECOTRACK_SCHEDULER_INITIAL_DELAY_SECONDS", None)

    if old_drift_recent is not None:
        os.environ["ECOTRACK_DRIFT_RECENT_PATH"] = old_drift_recent
    else:
        os.environ.pop("ECOTRACK_DRIFT_RECENT_PATH", None)

    if old_benchmark_results is not None:
        os.environ["ECOTRACK_BENCHMARK_RESULTS_PATH"] = old_benchmark_results
    else:
        os.environ.pop("ECOTRACK_BENCHMARK_RESULTS_PATH", None)

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def fast_lstm_epochs(monkeypatch):
    """Caps LSTM training for every test; real early stopping is exercised in test_benchmark_lstm.py."""
    try:
        import experiments.benchmark.lstm as lstm_module
    except ImportError:
        # Benchmark extras (requirements-experiments.txt) are not installed; the API tests
        # do not need them, so there is nothing to cap.
        return
    monkeypatch.setattr(lstm_module, "LSTM_MAX_EPOCHS", 2)
    monkeypatch.setattr(lstm_module, "LSTM_PATIENCE", 1)
