import os
from pathlib import Path
from src.models.train_models import get_default_paths


def get_tariff_rate_vnd() -> float:
    return float(os.getenv("TARIFF_RATE_VND", "3100"))

def get_tariff_rate_usd() -> float:
    return float(os.getenv("TARIFF_RATE_USD", "0.125"))

def get_data_path() -> Path:
    val = os.getenv("ECOTRACK_DATA_PATH")
    return Path(val) if val else get_default_paths()[0]

def get_models_dir() -> Path:
    val = os.getenv("ECOTRACK_MODELS_DIR")
    return Path(val) if val else get_default_paths()[1]


def get_internal_api_key() -> str | None:
    return os.getenv("INTERNAL_API_KEY")

