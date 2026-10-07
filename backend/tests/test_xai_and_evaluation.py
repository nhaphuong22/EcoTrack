"""
Unit and Integration Tests for Explainable AI (SHAP XAI) & Evaluation Metrics.
Validates:
1. SHAP TreeExplainer feature attributions for energy anomaly root-cause analysis.
2. AnomalyExplainer single and batch explanation formats.
3. Classification metrics and FPR reduction calculation for scientific paper benchmarking.
4. Agent domain grounding and faithfulness evaluation.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from src.models.explainability import AnomalyExplainer, anomaly_explainer
from src.models.evaluation_metrics import (
    calculate_classification_metrics,
    compare_agent_filtering_impact,
    evaluate_agent_faithfulness_and_grounding,
)


# =========================================================================
# 1. SHAP EXPLAINABLE AI (XAI) TESTS
# =========================================================================

def test_anomaly_explainer_initialization():
    """Validates that AnomalyExplainer initializes with TreeExplainer properly."""
    assert anomaly_explainer is not None
    assert anomaly_explainer.model is not None
    assert hasattr(anomaly_explainer, "explainer")
    assert isinstance(anomaly_explainer.feature_names, list)
    assert len(anomaly_explainer.feature_names) == 6


def test_anomaly_explainer_custom_model():
    """Ensures AnomalyExplainer can wrap any custom IsolationForest instance."""
    df_train = pd.DataFrame(
        np.random.RandomState(42).randn(40, 6),
        columns=anomaly_explainer.feature_names,
    )
    custom_model = IsolationForest(n_estimators=20, random_state=42)
    custom_model.fit(df_train)

    custom_explainer = AnomalyExplainer(
        model=custom_model, feature_names=anomaly_explainer.feature_names
    )
    assert custom_explainer.model == custom_model

    sample = df_train.iloc[0].to_dict()
    res = custom_explainer.explain_instance(sample, top_k=2)

    assert "shap_values" in res
    assert len(res["top_contributing_features"]) == 2
    assert "summary_explanation" in res


def test_anomaly_explainer_explain_instance():
    """Validates structure and feature attribution of a single telemetry explanation."""
    test_sample = {
        "meter_reading_kwh": 350.0,
        "residual": 95.0,
        "outdoor_temperature_c": 36.5,
        "hour": 14,
        "is_business_hour": 1,
        "is_weekend": 0,
    }

    explanation = anomaly_explainer.explain_instance(test_sample, top_k=3)

    assert isinstance(explanation, dict)
    assert "shap_values" in explanation
    assert "feature_values" in explanation
    assert "top_contributing_features" in explanation
    assert "summary_explanation" in explanation
    assert "base_value" in explanation

    # Verify top_k elements
    top_features = explanation["top_contributing_features"]
    assert len(top_features) == 3

    for item in top_features:
        assert "feature" in item
        assert "display_name" in item
        assert "actual_value" in item
        assert "shap_value" in item
        assert "impact_direction" in item
        assert isinstance(item["shap_value"], float)

    # Verify summary text
    assert isinstance(explanation["summary_explanation"], str)
    assert len(explanation["summary_explanation"]) > 20


def test_anomaly_explainer_explain_batch():
    """Validates batch processing of multiple telemetry data points."""
    df_batch = pd.DataFrame(
        [
            {
                "meter_reading_kwh": 100.0,
                "residual": 5.0,
                "outdoor_temperature_c": 28.0,
                "hour": 9,
                "is_business_hour": 1,
                "is_weekend": 0,
            },
            {
                "meter_reading_kwh": 300.0,
                "residual": 80.0,
                "outdoor_temperature_c": 38.0,
                "hour": 14,
                "is_business_hour": 1,
                "is_weekend": 0,
            },
        ]
    )

    batch_res = anomaly_explainer.explain_batch(df_batch, top_k=2)
    assert len(batch_res) == 2
    assert batch_res[0]["row_index"] == 0
    assert batch_res[1]["row_index"] == 1
    assert len(batch_res[0]["top_contributing_features"]) == 2


def test_anomaly_explainer_global_importance():
    """Validates global feature ranking across multiple points."""
    df_eval = pd.DataFrame(
        np.random.RandomState(101).randn(25, 6),
        columns=anomaly_explainer.feature_names,
    )
    importance = anomaly_explainer.get_global_feature_importance(df_eval)

    assert isinstance(importance, dict)
    assert len(importance) == 6
    # Importance values should be non-negative
    for val in importance.values():
        assert val >= 0.0


# =========================================================================
# 2. RESEARCH EVALUATION METRICS TESTS
# =========================================================================

def test_calculate_classification_metrics_standard():
    """Validates known confusion matrix calculations."""
    # TP: 2, FP: 1, TN: 2, FN: 1 (Total: 6)
    y_true = [1, 1, 1, 0, 0, 0]
    y_pred = [1, 1, 0, 1, 0, 0]

    metrics = calculate_classification_metrics(y_true, y_pred)

    assert metrics["tp"] == 2
    assert metrics["fp"] == 1
    assert metrics["tn"] == 2
    assert metrics["fn"] == 1
    assert metrics["total"] == 6

    # Precision = 2 / (2 + 1) = 0.6667
    assert pytest.approx(metrics["precision"], 0.001) == 0.6667
    # Recall = 2 / (2 + 1) = 0.6667
    assert pytest.approx(metrics["recall"], 0.001) == 0.6667
    # Specificity = 2 / (2 + 1) = 0.6667
    assert pytest.approx(metrics["specificity"], 0.001) == 0.6667
    # FPR = 1 / (1 + 2) = 0.3333
    assert pytest.approx(metrics["fpr"], 0.001) == 0.3333
    # F1 = 0.6667
    assert pytest.approx(metrics["f1_score"], 0.001) == 0.6667


def test_calculate_classification_metrics_edge_cases():
    """Handles empty inputs and zero division scenarios gracefully."""
    empty_res = calculate_classification_metrics([], [])
    assert empty_res["total"] == 0
    assert empty_res["accuracy"] == 0.0
    assert empty_res["precision"] == 0.0
    assert empty_res["recall"] == 0.0
    assert empty_res["fpr"] == 0.0

    with pytest.raises(ValueError):
        calculate_classification_metrics([1, 0], [1])


def test_compare_agent_filtering_impact():
    """Validates FPR reduction comparison between baseline and proposed agent."""
    y_true = [1] * 20 + [0] * 80
    y_pred_base = [1] * 19 + [0] * 1 + [1] * 20 + [0] * 60  # 19 TP, 1 FN, 20 FP
    y_pred_agent = [1] * 19 + [0] * 1 + [1] * 4 + [0] * 76  # 19 TP, 1 FN, 4 FP

    comp = compare_agent_filtering_impact(
        y_true, y_pred_base, y_pred_agent, benchmark_name="Unit Test Benchmark"
    )

    assert comp["benchmark_name"] == "Unit Test Benchmark"
    assert comp["sample_size"] == 100

    imp = comp["improvements"]
    assert imp["false_alarms_prevented"] == 16
    assert imp["delta_fpr_relative_pct"] > 70.0
    assert imp["precision_gain"] > 0.30
    assert imp["recall_retention_pct"] == 100.0

    # Tables generation
    assert "Markdown Table" not in comp["markdown_table"]  # Real content exists
    assert "False Positive Rate (FPR)" in comp["markdown_table"]
    assert "\\begin{table}" in comp["latex_table"]


def test_evaluate_agent_faithfulness_and_grounding():
    """Validates domain grounding and tool calling accuracy calculation."""
    cases = [
        {
            "expected_tools": ["query_meter_telemetry", "evaluate_weather_impact"],
            "actual_tools": ["query_meter_telemetry"],
            "ground_truth_facts": ["chiller", "cooling", "schedule"],
            "response_text": "Hệ thống chiller tiêu thụ cao do vượt tải hệ thống cooling theo schedule.",
        },
        {
            "expected_tools": ["diagnose_chiller_anomaly"],
            "actual_tools": ["diagnose_chiller_anomaly"],
            "ground_truth_facts": ["leakage", "compressor"],
            "response_text": "Phát hiện hiện tượng rò rỉ (leakage) ở cụm máy nén compressor.",
        },
    ]

    res = evaluate_agent_faithfulness_and_grounding(cases)

    assert res["total_cases"] == 2
    assert res["tool_selection_accuracy"] == 1.0
    assert res["rca_grounding_score"] == 1.0
    assert res["hallucination_rate"] == 0.0
