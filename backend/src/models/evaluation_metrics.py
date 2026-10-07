"""
Scientific Research Evaluation Metrics Module for EcoTrack (NCKH Benchmark).
Provides formal quantitative metrics comparing unsupervised Machine Learning (Isolation Forest)
against the proposed hybrid LLM Context-Aware Agent architecture.
Calculates:
- False Positive Rate (FPR), Precision, Recall, F1-Score, Specificity.
- Delta FPR reduction and false alarms mitigation metrics.
- Formats comparison tables for scientific papers (Markdown & LaTeX).
"""

from typing import Any, Dict, List, Sequence, Union
import numpy as np


def calculate_classification_metrics(
    y_true: Union[Sequence[Union[int, bool]], np.ndarray],
    y_pred: Union[Sequence[Union[int, bool]], np.ndarray],
) -> Dict[str, float]:
    """
    Computes standard classification metrics with special focus on False Positive Rate (FPR)
    for energy anomaly detection evaluation.

    Args:
        y_true: Ground truth binary labels (1 = True Anomaly, 0 = Normal / False Alarm).
        y_pred: Predicted binary labels (1 = Flagged Anomaly, 0 = Normal).

    Returns:
        Dictionary of quantitative performance metrics.
    """
    yt = np.asarray(y_true, dtype=int)
    yp = np.asarray(y_pred, dtype=int)

    if len(yt) != len(yp):
        raise ValueError(f"Length mismatch: len(y_true)={len(yt)} != len(y_pred)={len(yp)}")

    if len(yt) == 0:
        return {
            "tp": 0, "fp": 0, "tn": 0, "fn": 0, "total": 0,
            "accuracy": 0.0, "precision": 0.0, "recall": 0.0,
            "specificity": 0.0, "f1_score": 0.0, "fpr": 0.0,
        }

    tp = int(np.sum((yt == 1) & (yp == 1)))
    fp = int(np.sum((yt == 0) & (yp == 1)))
    tn = int(np.sum((yt == 0) & (yp == 0)))
    fn = int(np.sum((yt == 1) & (yp == 0)))
    total = len(yt)

    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    f1_score = (
        (2 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "total": total,
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "specificity": round(float(specificity), 4),
        "f1_score": round(float(f1_score), 4),
        "fpr": round(float(fpr), 4),
    }


def compare_agent_filtering_impact(
    y_true: Union[Sequence[Union[int, bool]], np.ndarray],
    y_pred_baseline: Union[Sequence[Union[int, bool]], np.ndarray],
    y_pred_agent: Union[Sequence[Union[int, bool]], np.ndarray],
    benchmark_name: str = "EcoTrack BDG2 Benchmark",
) -> Dict[str, Any]:
    """
    Compares the baseline unsupervised Isolation Forest against the proposed
    Isolation Forest + LLM Context-Aware Agent filtering layer.

    Evaluates the primary research hypothesis:
    "Does integrating an LLM Agent with operational context (weather, schedules, EVN tariffs)
    significantly reduce the False Positive Rate (FPR) without degrading Recall?"

    Args:
        y_true: Ground truth binary incident labels.
        y_pred_baseline: Raw Isolation Forest anomaly predictions.
        y_pred_agent: Refined predictions after agent contextual reasoning.
        benchmark_name: Label for the benchmark dataset.

    Returns:
        Structured evaluation comparison dict with delta metrics and Markdown/LaTeX summaries.
    """
    base_metrics = calculate_classification_metrics(y_true, y_pred_baseline)
    agent_metrics = calculate_classification_metrics(y_true, y_pred_agent)

    # Calculate delta improvements
    fpr_base = base_metrics["fpr"]
    fpr_agent = agent_metrics["fpr"]
    delta_fpr_abs = fpr_base - fpr_agent
    delta_fpr_pct = (delta_fpr_abs / fpr_base * 100.0) if fpr_base > 0 else 0.0

    false_alarms_prevented = base_metrics["fp"] - agent_metrics["fp"]
    precision_gain = agent_metrics["precision"] - base_metrics["precision"]
    f1_gain = agent_metrics["f1_score"] - base_metrics["f1_score"]
    recall_retention = (
        (agent_metrics["recall"] / base_metrics["recall"] * 100.0)
        if base_metrics["recall"] > 0
        else 100.0
    )

    # Markdown comparison table
    markdown_table = (
        f"### 📊 Bảng Đánh Giá Thực Nghiệm: {benchmark_name}\n\n"
        f"| Chỉ số Đánh Giá | Baseline (Isolation Forest) | Proposed (IF + LLM Agent) | Cải Thiện (Delta) |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"| **False Positive Rate (FPR)** | {base_metrics['fpr'] * 100:.2f}% | {agent_metrics['fpr'] * 100:.2f}% | **-{delta_fpr_pct:.1f}% (Giảm báo giả)** |\n"
        f"| **Số cảnh báo giả (FP count)** | {base_metrics['fp']} | {agent_metrics['fp']} | **-{false_alarms_prevented} cảnh báo** |\n"
        f"| **Precision (Độ chuẩn xác)** | {base_metrics['precision'] * 100:.2f}% | {agent_metrics['precision'] * 100:.2f}% | **+{precision_gain * 100:.2f}%** |\n"
        f"| **Recall (Độ nhạy bắt lỗi)** | {base_metrics['recall'] * 100:.2f}% | {agent_metrics['recall'] * 100:.2f}% | {recall_retention:.1f}% giữ nguyên |\n"
        f"| **F1-Score tổng hợp** | {base_metrics['f1_score']:.4f} | {agent_metrics['f1_score']:.4f} | **+{f1_gain:.4f}** |\n"
        f"| **Accuracy tổng thể** | {base_metrics['accuracy'] * 100:.2f}% | {agent_metrics['accuracy'] * 100:.2f}% | +{(agent_metrics['accuracy'] - base_metrics['accuracy']) * 100:.2f}% |\n"
    )

    # LaTeX snippet for scientific publication
    latex_table = (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        f"\\caption{{Comparative Performance Evaluation on {benchmark_name}}}\n"
        "\\begin{tabular}{lccc}\n"
        "\\hline\n"
        "\\textbf{Metric} & \\textbf{Baseline (IF)} & \\textbf{Proposed (IF + Agent)} & \\textbf{Improvement} \\\\\n"
        "\\hline\n"
        f"FPR (\\%) & {base_metrics['fpr'] * 100:.2f}\\% & {agent_metrics['fpr'] * 100:.2f}\\% & -{delta_fpr_pct:.1f}\\% \\\\\n"
        f"Precision (\\%) & {base_metrics['precision'] * 100:.2f}\\% & {agent_metrics['precision'] * 100:.2f}\\% & +{precision_gain * 100:.2f}\\% \\\\\n"
        f"Recall (\\%) & {base_metrics['recall'] * 100:.2f}\\% & {agent_metrics['recall'] * 100:.2f}\\% & {agent_metrics['recall'] - base_metrics['recall']:+.2f}\\% \\\\\n"
        f"F1-Score & {base_metrics['f1_score']:.4f} & {agent_metrics['f1_score']:.4f} & +{f1_gain:.4f} \\\\\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )

    return {
        "benchmark_name": benchmark_name,
        "sample_size": len(y_true),
        "baseline": base_metrics,
        "agent": agent_metrics,
        "improvements": {
            "delta_fpr_absolute": round(float(delta_fpr_abs), 4),
            "delta_fpr_relative_pct": round(float(delta_fpr_pct), 2),
            "false_alarms_prevented": int(false_alarms_prevented),
            "precision_gain": round(float(precision_gain), 4),
            "f1_gain": round(float(f1_gain), 4),
            "recall_retention_pct": round(float(recall_retention), 2),
        },
        "markdown_table": markdown_table,
        "latex_table": latex_table,
    }


def evaluate_agent_faithfulness_and_grounding(
    benchmark_records: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Evaluates LLM Agent responses for domain grounding and hallucination resistance.

    Args:
        benchmark_records: List of test evaluation cases with:
            - response_text: LLM response
            - ground_truth_facts: List of required factual keywords/assertions
            - expected_tools: List of expected tool names called
            - actual_tools: List of tools actually invoked

    Returns:
        Quantitative evaluation dictionary (Tool Accuracy, Faithfulness, RCA Grounding).
    """
    if not benchmark_records:
        return {
            "total_cases": 0,
            "tool_selection_accuracy": 0.0,
            "rca_grounding_score": 0.0,
            "hallucination_rate": 0.0,
        }

    tool_matches = 0
    grounding_scores = []

    for item in benchmark_records:
        exp_tools = set(item.get("expected_tools", []))
        act_tools = set(item.get("actual_tools", []))
        if not exp_tools or exp_tools.intersection(act_tools):
            tool_matches += 1

        gt_facts = [fact.lower() for fact in item.get("ground_truth_facts", [])]
        resp_text = item.get("response_text", "").lower()
        if gt_facts:
            hits = sum(1 for f in gt_facts if f in resp_text)
            grounding_scores.append(hits / len(gt_facts))
        else:
            grounding_scores.append(1.0)

    avg_grounding = float(np.mean(grounding_scores)) if grounding_scores else 0.0
    tool_acc = tool_matches / len(benchmark_records)
    hallucination_rate = max(0.0, 1.0 - avg_grounding)

    return {
        "total_cases": len(benchmark_records),
        "tool_selection_accuracy": round(float(tool_acc), 4),
        "rca_grounding_score": round(float(avg_grounding), 4),
        "hallucination_rate": round(float(hallucination_rate), 4),
    }
