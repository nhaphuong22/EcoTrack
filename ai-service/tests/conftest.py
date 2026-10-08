import os
import shutil
import tempfile
from pathlib import Path
import pytest

from src.data_pipeline.serving_frame import reset_serving_cache
from src.models.train_models import (
    ISO_FEATURE_COLUMNS,
    XGB_FEATURE_COLUMNS,
    engineer_features,
    load_dataset,
    save_trained_models,
    split_time_series_data,
    train_isolation_forest,
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
    iso_model, iso_metrics, _, _ = train_isolation_forest(train_df, test_df, contamination=0.03)

    metadata = {
        "dataset_rows": len(df_feat),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "xgb_features": XGB_FEATURE_COLUMNS,
        "iso_features": ISO_FEATURE_COLUMNS,
        "xgboost_metrics": xgb_metrics,
        "isolation_forest_metrics": iso_metrics,
    }

    save_trained_models(
        xgb_model=xgb_model,
        iso_model=iso_model,
        output_dir=temp_models_dir,
        metadata=metadata,
    )

    old_data_path = os.environ.get("ECOTRACK_DATA_PATH")
    old_models_dir = os.environ.get("ECOTRACK_MODELS_DIR")

    os.environ["ECOTRACK_DATA_PATH"] = str(fixture_csv)
    os.environ["ECOTRACK_MODELS_DIR"] = str(temp_models_dir)
    reset_serving_cache()

    yield {
        "data_path": fixture_csv,
        "models_dir": temp_models_dir,
        "metadata": metadata,
    }

    reset_serving_cache()
    if old_data_path is not None:
        os.environ["ECOTRACK_DATA_PATH"] = old_data_path
    else:
        os.environ.pop("ECOTRACK_DATA_PATH", None)

    if old_models_dir is not None:
        os.environ["ECOTRACK_MODELS_DIR"] = old_models_dir
    else:
        os.environ.pop("ECOTRACK_MODELS_DIR", None)

    shutil.rmtree(temp_dir, ignore_errors=True)
