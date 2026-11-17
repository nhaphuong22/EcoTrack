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
from src.models.train_models import engineer_features, load_dataset, split_time_series_data

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "office_building_sample.csv"


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


def test_lstm_set_params_overrides_reach_network():
    """The tuned LSTM architecture must actually reach the built network, not just _overrides.

    Without this, a silent no-op in _hp/fit would train an identical-architecture net for
    every trial and make the tuned benchmark row equal the untuned one while labeled 'tuned'.
    """
    from experiments.benchmark.lstm import LSTMForecaster

    df = engineer_features(load_dataset(FIXTURE_CSV))
    train_df, _ = split_time_series_data(df, train_ratio=0.8)

    model = LSTMForecaster()
    # Non-default architecture + optimiser params, and 1 epoch to keep the fit fast.
    model.set_params(hidden_size=8, num_layers=2, batch_size=32, learning_rate=5e-3, max_epochs=1)
    model.fit(train_df)

    assert model._net is not None
    # Architecture overrides reached the actual nn.LSTM.
    assert model._net.lstm.hidden_size == 8
    assert model._net.lstm.num_layers == 2
    # Optimiser-side overrides are resolved from the same _overrides dict.
    assert int(model._hp("batch_size", -1)) == 32
    assert float(model._hp("learning_rate", -1.0)) == pytest.approx(5e-3)
