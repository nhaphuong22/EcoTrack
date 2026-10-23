"""
Benchmark report generator for EcoTrack (Story 4.4).

Pure read + plot + format: given the artifacts written by the benchmark harness
(``results.csv``, ``results_by_horizon.csv``, ``predictions.parquet``) this module
renders four PNG charts, a human-readable ``REPORT.md`` and a machine-readable
``results.json`` for the MLOps page. It never fits a model, runs inference, or reads
the raw dataset — all numbers come from the artifacts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

# A non-interactive backend so charts render on a headless CI/host. Must be set
# before pyplot is imported.
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

logger = logging.getLogger("BenchmarkReport")


def _json_default(obj: Any) -> Any:
    """Coerce numpy scalars to native numbers (and anything else to str) for json.dumps."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return str(obj)

# Chart filenames (relative to the report output directory so links stay clickable).
CHART_METRIC_COMPARISON = "chart_metric_comparison.png"
CHART_ACTUAL_VS_PREDICTED = "chart_actual_vs_predicted_week.png"
CHART_ERROR_BY_HOUR = "chart_error_by_hour.png"
CHART_ERROR_VS_HORIZON = "chart_error_vs_horizon.png"

REPORT_MD = "REPORT.md"
RESULTS_JSON = "results.json"

SAMPLE_WEEK_HOURS = 168  # one week of hourly readings for the actual-vs-predicted chart
NEAR_HORIZON = 1
FAR_HORIZON = 24

# Models whose mean MAE is within this fraction of the best mean MAE are treated as an
# accuracy tie (a "near-tie") and decided on serving cost (latency, then size). Keeps the
# recommendation from flipping on sub-1% MAE noise between two otherwise-comparable models.
RECOMMENDATION_EPSILON_FRAC = 0.01


def load_artifacts(
    results_path: Path,
    by_horizon_path: Path,
    predictions_path: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Loads the three benchmark artifacts. Raises FileNotFoundError naming the first
    missing path so the caller can exit without writing a partial report.
    """
    for path in (results_path, by_horizon_path, predictions_path):
        if not Path(path).exists():
            raise FileNotFoundError(f"Required benchmark artifact not found: {path}")

    results_df = pd.read_csv(results_path)
    by_horizon_df = pd.read_csv(by_horizon_path)
    predictions_df = pd.read_parquet(predictions_path)
    predictions_df["target_timestamp"] = pd.to_datetime(predictions_df["target_timestamp"])
    predictions_df["origin_timestamp"] = pd.to_datetime(predictions_df["origin_timestamp"])
    return results_df, by_horizon_df, predictions_df


# --- Charts ---------------------------------------------------------------------


def _hour_one(predictions_df: pd.DataFrame) -> pd.DataFrame:
    """The horizon-1 slice used by the sample-week and error-by-hour charts."""
    return predictions_df[predictions_df["horizon_h"] == NEAR_HORIZON].copy()


def render_metric_comparison(results_df: pd.DataFrame, out_dir: Path) -> str:
    """Grouped bars of MAE and RMSE (kWh) per model, with MAPE % / R² annotated."""
    models = list(results_df["model"])
    x = np.arange(len(models))
    width = 0.38

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width / 2, results_df["mae_kwh"], width, label="MAE (kWh)", color="#2b6cb0")
    ax.bar(x + width / 2, results_df["rmse_kwh"], width, label="RMSE (kWh)", color="#ed8936")
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=0)
    ax.set_ylabel("Error (kWh)")
    ax.set_title("Benchmark metric comparison across models")
    ax.legend()

    for xi, (_, row) in zip(x, results_df.iterrows()):
        ax.annotate(
            f"MAPE {row['mape_percent']:.1f}%\nR² {row['r2']:.3f}",
            (xi, max(row["mae_kwh"], row["rmse_kwh"])),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=8,
        )

    fig.tight_layout()
    path = out_dir / CHART_METRIC_COMPARISON
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return CHART_METRIC_COMPARISON


def render_actual_vs_predicted(predictions_df: pd.DataFrame, out_dir: Path) -> str:
    """Actual vs each model's horizon-1 forecast over a deterministic sample week."""
    hour_one = _hour_one(predictions_df)
    targets = np.sort(hour_one["target_timestamp"].unique())
    window = targets[:SAMPLE_WEEK_HOURS]  # falls back to the full span if shorter
    window_rows = hour_one[hour_one["target_timestamp"].isin(window)]

    fig, ax = plt.subplots(figsize=(11, 5))
    actual = (
        window_rows.drop_duplicates("target_timestamp")
        .sort_values("target_timestamp")
    )
    ax.plot(actual["target_timestamp"], actual["actual"], label="actual", color="black", linewidth=2)

    for model_name, group in window_rows.groupby("model"):
        group = group.sort_values("target_timestamp")
        ax.plot(group["target_timestamp"], group["prediction"], label=model_name, linewidth=1)

    ax.set_ylabel("meter_reading (kWh)")
    ax.set_xlabel("timestamp")
    ax.set_title(f"Actual vs predicted (horizon 1 h, first {len(window)} h sample)")
    ax.legend(ncol=3, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    path = out_dir / CHART_ACTUAL_VS_PREDICTED
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return CHART_ACTUAL_VS_PREDICTED


def render_error_by_hour(predictions_df: pd.DataFrame, out_dir: Path) -> str:
    """Mean absolute horizon-1 error grouped by hour of day, one line per model."""
    hour_one = _hour_one(predictions_df)
    hour_one = hour_one.assign(
        abs_error=(hour_one["actual"] - hour_one["prediction"]).abs(),
        hour=hour_one["target_timestamp"].dt.hour,
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    for model_name, group in hour_one.groupby("model"):
        by_hour = group.groupby("hour")["abs_error"].mean().reindex(range(24))
        ax.plot(by_hour.index, by_hour.values, marker="o", markersize=3, label=model_name)

    ax.set_xlabel("hour of day")
    ax.set_ylabel("mean absolute error (kWh)")
    ax.set_xticks(range(0, 24, 2))
    ax.set_title("Horizon-1 absolute error by hour of day")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = out_dir / CHART_ERROR_BY_HOUR
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return CHART_ERROR_BY_HOUR


def render_error_vs_horizon(by_horizon_df: pd.DataFrame, out_dir: Path) -> str:
    """MAE against forecast horizon (1..24) for all models."""
    fig, ax = plt.subplots(figsize=(10, 5))
    for model_name, group in by_horizon_df.groupby("model"):
        group = group.sort_values("horizon_h")
        ax.plot(group["horizon_h"], group["mae_kwh"], marker="o", markersize=3, label=model_name)

    ax.set_xlabel("forecast horizon (hours ahead)")
    ax.set_ylabel("MAE (kWh)")
    ax.set_title("Forecast error against horizon")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = out_dir / CHART_ERROR_VS_HORIZON
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return CHART_ERROR_VS_HORIZON


# --- Recommendation -------------------------------------------------------------


def _best_at_horizon(by_horizon_df: pd.DataFrame, horizon: int) -> Dict[str, Any]:
    """Model with the lowest MAE at a horizon; falls back to the largest available."""
    available = sorted(by_horizon_df["horizon_h"].unique())
    if not available:
        return {}
    chosen_h = horizon if horizon in available else available[-1]
    rows = by_horizon_df[by_horizon_df["horizon_h"] == chosen_h]
    best = rows.loc[rows["mae_kwh"].idxmin()]
    return {"horizon_h": int(chosen_h), "model": str(best["model"]), "mae_kwh": float(best["mae_kwh"])}


def compute_recommendation(
    results_df: pd.DataFrame,
    by_horizon_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Deterministic serving recommendation: among the models whose mean MAE across all scored
    horizons is within RECOMMENDATION_EPSILON_FRAC of the best (a near-tie on accuracy), pick
    the one with the lowest inference latency, then the smallest model size. Also reports the
    best model at the near (1 h) and far (24 h) horizon.
    """
    mean_mae = (
        by_horizon_df.groupby("model")["mae_kwh"].mean().rename("mean_mae_kwh").reset_index()
    )
    merged = mean_mae.merge(
        results_df[["model", "mean_inference_latency_ms", "model_file_size_bytes"]],
        on="model",
        how="left",
    )
    # Full ranking stays accuracy-first (then latency, size, name) for the report table.
    merged = merged.sort_values(
        ["mean_mae_kwh", "mean_inference_latency_ms", "model_file_size_bytes", "model"],
        kind="mergesort",
    ).reset_index(drop=True)

    # Near-tie band: every model within epsilon of the best mean MAE competes on serving cost.
    best_mae = float(merged["mean_mae_kwh"].min())
    epsilon = abs(best_mae) * RECOMMENDATION_EPSILON_FRAC
    contenders = merged[merged["mean_mae_kwh"] <= best_mae + epsilon].sort_values(
        ["mean_inference_latency_ms", "model_file_size_bytes", "model"],
        kind="mergesort",
    )

    top = contenders.iloc[0]
    recommended = str(top["model"])
    tie_note = (
        "It was selected on serving cost from a near-tie band "
        f"(mean MAE within {RECOMMENDATION_EPSILON_FRAC:.0%} of the best, {best_mae:.2f} kWh): "
        "lower latency first, then smaller model size."
        if len(contenders) > 1
        else "No other model was within the near-tie band, so it wins on accuracy outright."
    )
    rationale = (
        f"{recommended} serves at {top['mean_mae_kwh']:.2f} kWh mean MAE across horizons, "
        f"{top['mean_inference_latency_ms']:.3f} ms/sample inference latency and "
        f"{int(top['model_file_size_bytes'])} bytes on disk. {tie_note}"
    )

    return {
        "recommended_model": recommended,
        "serve_rationale": rationale,
        "ranking": merged.to_dict(orient="records"),
        "best_at_1h": _best_at_horizon(by_horizon_df, NEAR_HORIZON),
        "best_at_24h": _best_at_horizon(by_horizon_df, FAR_HORIZON),
    }


# --- Document assembly ----------------------------------------------------------


def _markdown_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavored Markdown table (no tabulate dependency)."""
    headers = list(df.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in df.iterrows():
        cells = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_results_json(
    results_df: pd.DataFrame,
    by_horizon_df: pd.DataFrame,
    recommendation: Dict[str, Any],
    charts: Dict[str, str],
    horizon: int,
) -> Dict[str, Any]:
    """Machine-readable summary for the MLOps page (Story 4.12)."""
    return {
        "generated_horizon": int(horizon),
        "models": results_df.to_dict(orient="records"),
        "by_horizon": by_horizon_df.to_dict(orient="records"),
        "recommendation": recommendation,
        "charts": charts,
    }


def build_report_md(
    results_df: pd.DataFrame,
    recommendation: Dict[str, Any],
    charts: Dict[str, str],
) -> str:
    """Human-readable REPORT.md with the results table, the four charts, and the pick."""
    best_1h = recommendation.get("best_at_1h", {})
    best_24h = recommendation.get("best_at_24h", {})

    parts: List[str] = []
    parts.append("# EcoTrack Forecasting Benchmark Report\n")
    parts.append("## Results\n")
    parts.append(_markdown_table(results_df) + "\n")

    parts.append("## Charts\n")
    parts.append(f"![Metric comparison]({charts['metric_comparison']})\n")
    parts.append(f"![Actual vs predicted (sample week)]({charts['actual_vs_predicted']})\n")
    parts.append(f"![Absolute error by hour of day]({charts['error_by_hour']})\n")
    parts.append(f"![Error against horizon]({charts['error_vs_horizon']})\n")

    parts.append("## Recommendation\n")
    parts.append(
        f"**Model to serve: `{recommendation['recommended_model']}`.** "
        f"{recommendation['serve_rationale']}\n"
    )
    if best_1h:
        parts.append(
            f"- Best at **{best_1h['horizon_h']} hour ahead**: `{best_1h['model']}` "
            f"(MAE {best_1h['mae_kwh']:.2f} kWh)."
        )
    if best_24h:
        parts.append(
            f"- Best at **{best_24h['horizon_h']} hours ahead**: `{best_24h['model']}` "
            f"(MAE {best_24h['mae_kwh']:.2f} kWh)."
        )
    return "\n".join(parts) + "\n"


def generate_report(
    results_path: Path,
    by_horizon_path: Path,
    predictions_path: Path,
    out_dir: Path,
    horizon: int = FAR_HORIZON,
) -> Dict[str, Path]:
    """
    End-to-end report generation. Reads the artifacts, renders the four charts, and writes
    REPORT.md and results.json into ``out_dir``. Returns the paths of everything written.
    """
    results_df, by_horizon_df, predictions_df = load_artifacts(
        results_path, by_horizon_path, predictions_path
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    charts = {
        "metric_comparison": render_metric_comparison(results_df, out_dir),
        "actual_vs_predicted": render_actual_vs_predicted(predictions_df, out_dir),
        "error_by_hour": render_error_by_hour(predictions_df, out_dir),
        "error_vs_horizon": render_error_vs_horizon(by_horizon_df, out_dir),
    }

    recommendation = compute_recommendation(results_df, by_horizon_df)
    results_json = build_results_json(results_df, by_horizon_df, recommendation, charts, horizon)
    report_md = build_report_md(results_df, recommendation, charts)

    report_path = out_dir / REPORT_MD
    json_path = out_dir / RESULTS_JSON
    report_path.write_text(report_md, encoding="utf-8")
    json_path.write_text(json.dumps(results_json, indent=2, default=_json_default), encoding="utf-8")

    written = {name: out_dir / filename for name, filename in charts.items()}
    written["report_md"] = report_path
    written["results_json"] = json_path
    logger.info("Report written to %s", out_dir)
    return written
