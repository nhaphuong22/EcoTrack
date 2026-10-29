"""
Tuned-parameter plumbing tests for Story 4.5 (FR47 benchmark re-run path).

Covers ``build_tuned_models`` feeding a best_params.json through the forecasters'
``set_params`` so a keyed model reflects the overrides while an un-keyed model
keeps its defaults.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("statsmodels")

from experiments.benchmark.models import XGBoostForecaster
from experiments.benchmark.run_benchmark import build_tuned_models


def test_xgboost_set_params_overrides_and_rebuilds():
    model = XGBoostForecaster()
    assert model.params["n_estimators"] == 350  # default
    model.set_params(n_estimators=123, max_depth=7)
    assert model.params["n_estimators"] == 123
    assert model.params["max_depth"] == 7
    # The underlying estimator is rebuilt with the overrides.
    assert model.model.get_params()["n_estimators"] == 123
    assert model.model.get_params()["max_depth"] == 7


def test_build_tuned_models_applies_only_keyed_models(tmp_path):
    params_file = tmp_path / "best_params.json"
    params_file.write_text(json.dumps({"xgboost": {"n_estimators": 77, "max_depth": 6}}), encoding="utf-8")

    models = build_tuned_models(params_file)
    by_name = {m.name: m for m in models}

    # The keyed model reflects the overrides...
    xgb = by_name["xgboost"]
    assert xgb.params["n_estimators"] == 77
    assert xgb.params["max_depth"] == 6

    # ...while an un-keyed model keeps its defaults (no overrides applied).
    lstm = by_name["lstm"]
    assert lstm._overrides == {}
