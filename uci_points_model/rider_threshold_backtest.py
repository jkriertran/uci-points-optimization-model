from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import pandas as pd

from .rider_threshold_model import (
    DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS,
    DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    RIDER_THRESHOLD_TARGET_COLUMN,
    default_rider_threshold_output_root,
    evaluate_rider_threshold_expanding_window,
    fit_rider_threshold_baseline,
)

RIDER_BACKTEST_SUMMARY_FILENAME = "rider_threshold_backtest_summary.json"
RIDER_BACKTEST_BENCHMARK_FILENAME = "rider_threshold_backtest_benchmark.csv"
RIDER_BACKTEST_FOLDS_FILENAME = "rider_threshold_backtest_folds.csv"
RIDER_BACKTEST_PREDICTIONS_FILENAME = "rider_threshold_backtest_predictions.csv"
RIDER_BACKTEST_REPORT_FILENAME = "rider_threshold_backtest_report.md"


@dataclass(frozen=True, slots=True)
class RiderThresholdBacktestArtifacts:
    summary: dict[str, object]
    benchmark_table: pd.DataFrame
    fold_table: pd.DataFrame
    prediction_table: pd.DataFrame
    report_text: str


def build_rider_threshold_backtest_artifacts(
    rider_panel: pd.DataFrame,
    *,
    model_specs: Sequence[tuple[str, Sequence[str]]] = DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS,
    target_column: str = RIDER_THRESHOLD_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> RiderThresholdBacktestArtifacts:
    if not model_specs:
        raise ValueError("At least one rider-threshold backtest model spec is required.")

    benchmark_rows: list[dict[str, object]] = []
    fold_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    model_summaries: list[dict[str, object]] = []

    prepared = rider_panel.copy()
    prepared[target_column] = pd.to_numeric(prepared[target_column], errors="coerce")
    prepared = prepared.dropna(subset=[target_column]).reset_index(drop=True)
    if prepared.empty:
        raise ValueError("Rider-threshold backtest requires observed target rows.")

    next_seasons = sorted(
        pd.to_numeric(prepared.get("next_season"), errors="coerce").dropna().astype(int).unique().tolist()
    )

    for model_name, feature_columns in model_specs:
        fit_result = fit_rider_threshold_baseline(
            prepared,
            feature_columns=feature_columns,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            include_expanding_window=False,
        )
        backtest_summary, fold_summaries, prediction_table = evaluate_rider_threshold_expanding_window(
            prepared,
            feature_columns=feature_columns,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            min_train_seasons=min_train_seasons,
        )

        coefficients_text = ", ".join(
            f"{feature}={fit_result.coefficients[feature]:.3f}" for feature in fit_result.feature_columns
        )
        benchmark_rows.append(
            {
                "model_name": model_name,
                "feature_columns": ", ".join(feature_columns),
                "feature_count": len(feature_columns),
                "training_rows": fit_result.training_rows,
                "positive_rows": fit_result.positive_rows,
                "negative_rows": fit_result.negative_rows,
                "in_sample_accuracy": fit_result.in_sample_metrics["accuracy"],
                "in_sample_precision": fit_result.in_sample_metrics["precision"],
                "in_sample_recall": fit_result.in_sample_metrics["recall"],
                "in_sample_brier_score": fit_result.in_sample_metrics["brier_score"],
                "in_sample_log_loss": fit_result.in_sample_metrics["log_loss"],
                "backtest_fold_count": int(backtest_summary.get("fold_count", 0)),
                "backtest_rows_scored": int(backtest_summary.get("rows_scored", 0)),
                "backtest_accuracy": float(backtest_summary.get("accuracy", 0.0)),
                "backtest_precision": float(backtest_summary.get("precision", 0.0)),
                "backtest_recall": float(backtest_summary.get("recall", 0.0)),
                "backtest_brier_score": float(backtest_summary.get("brier_score", 0.0)),
                "backtest_log_loss": float(backtest_summary.get("log_loss", 0.0)),
                "backtest_top_k_capture": float(backtest_summary.get("top_k_capture", 0.0)),
                "coefficients": coefficients_text,
            }
        )
        model_summaries.append(
            {
                "model_name": model_name,
                "feature_columns": list(feature_columns),
                "coefficients": {
                    feature: round(fit_result.coefficients[feature], 8)
                    for feature in fit_result.feature_columns
                },
                "odds_ratios": {
                    feature: round(fit_result.odds_ratios[feature], 8)
                    for feature in fit_result.feature_columns
                },
                "in_sample_metrics": {
                    key: round(float(value), 8) for key, value in fit_result.in_sample_metrics.items()
                },
                "backtest_summary": _normalize_summary_dict(backtest_summary),
                "backtest_folds": [_normalize_summary_dict(fold_summary) for fold_summary in fold_summaries],
            }
        )

        if fold_summaries:
            fold_frame = pd.DataFrame(fold_summaries)
            fold_frame.insert(0, "model_name", model_name)
            fold_frame.insert(1, "feature_columns", ", ".join(feature_columns))
            if "train_next_seasons" in fold_frame.columns:
                fold_frame["train_next_seasons"] = fold_frame["train_next_seasons"].apply(
                    lambda values: ", ".join(str(value) for value in values)
                    if isinstance(values, list)
                    else values
                )
            fold_frames.append(fold_frame)

        if not prediction_table.empty:
            prediction_copy = prediction_table.copy()
            prediction_copy.insert(1, "feature_columns", ", ".join(feature_columns))
            prediction_frames.append(prediction_copy)

    benchmark_table = pd.DataFrame(benchmark_rows)
    benchmark_table = benchmark_table.sort_values(
        ["backtest_top_k_capture", "backtest_brier_score", "backtest_accuracy", "model_name"],
        ascending=[False, True, False, True],
    ).reset_index(drop=True)
    benchmark_table.insert(0, "benchmark_rank", range(1, len(benchmark_table) + 1))

    fold_table = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    prediction_table = (
        pd.concat(prediction_frames, ignore_index=True)
        if prediction_frames
        else pd.DataFrame()
    )
    if not prediction_table.empty:
        prediction_table = prediction_table.sort_values(
            ["model_name", "test_next_season", "predicted_probability_rank", "rider_name"],
            na_position="last",
        ).reset_index(drop=True)

    winning_model_name = benchmark_table.iloc[0]["model_name"] if not benchmark_table.empty else None
    summary = {
        "artifact_version": "rider_threshold_backtest_v1",
        "ranking_metric": "backtest_top_k_capture",
        "anchor_model_name": model_specs[0][0],
        "winning_model_name": winning_model_name,
        "training_summary": {
            "rows": int(len(prepared)),
            "positive_rows": int(prepared[target_column].astype(int).sum()),
            "negative_rows": int(len(prepared) - prepared[target_column].astype(int).sum()),
            "next_seasons": next_seasons,
        },
        "model_results": model_summaries,
    }
    report_text = _format_backtest_report(summary, benchmark_table, fold_table)

    return RiderThresholdBacktestArtifacts(
        summary=summary,
        benchmark_table=benchmark_table,
        fold_table=fold_table,
        prediction_table=prediction_table,
        report_text=report_text,
    )


def write_rider_threshold_backtest_artifacts(
    artifacts: RiderThresholdBacktestArtifacts,
    *,
    output_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_root) if output_root is not None else default_rider_threshold_output_root()
    root.mkdir(parents=True, exist_ok=True)

    summary_path = root / RIDER_BACKTEST_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(artifacts.summary, indent=2, sort_keys=True) + "\n")

    benchmark_path = root / RIDER_BACKTEST_BENCHMARK_FILENAME
    artifacts.benchmark_table.to_csv(benchmark_path, index=False)

    fold_path = root / RIDER_BACKTEST_FOLDS_FILENAME
    artifacts.fold_table.to_csv(fold_path, index=False)

    predictions_path = root / RIDER_BACKTEST_PREDICTIONS_FILENAME
    artifacts.prediction_table.to_csv(predictions_path, index=False)

    report_path = root / RIDER_BACKTEST_REPORT_FILENAME
    report_path.write_text(artifacts.report_text)

    return {
        "summary_path": summary_path,
        "benchmark_path": benchmark_path,
        "fold_path": fold_path,
        "predictions_path": predictions_path,
        "report_path": report_path,
    }


def _format_backtest_report(
    summary: dict[str, object],
    benchmark_table: pd.DataFrame,
    fold_table: pd.DataFrame,
) -> str:
    lines: list[str] = [
        "# Rider Threshold Backtest Report",
        "",
        "This report evaluates the current `rider_reaches_150_next_season` baselines with expanding-window validation.",
        "",
        "## Setup",
        "",
        f"- Training rows: {summary['training_summary']['rows']}",
        f"- Positive rows: {summary['training_summary']['positive_rows']}",
        f"- Next seasons: {', '.join(str(value) for value in summary['training_summary']['next_seasons'])}",
        f"- Anchor model: `{summary['anchor_model_name']}`",
        f"- Winning model by `backtest_top_k_capture`: `{summary['winning_model_name']}`",
        "",
        "Top-k capture uses the held-out season's actual number of 150-point riders as the cutoff.",
        "",
        "## Leaderboard",
        "",
    ]
    leaderboard_columns = [
        "benchmark_rank",
        "model_name",
        "feature_columns",
        "backtest_fold_count",
        "backtest_top_k_capture",
        "backtest_brier_score",
        "backtest_accuracy",
        "in_sample_accuracy",
        "coefficients",
    ]
    lines.extend(_format_markdown_table(benchmark_table, leaderboard_columns))

    if not fold_table.empty:
        lines.extend(
            [
                "",
                "## Fold Detail",
                "",
            ]
        )
        fold_columns = [
            "model_name",
            "test_next_season",
            "train_next_seasons",
            "test_rows",
            "actual_positive_rows",
            "predicted_positive_rows",
            "top_k_capture",
            "brier_score",
            "accuracy",
        ]
        lines.extend(_format_markdown_table(fold_table, fold_columns))

    lines.append("")
    return "\n".join(lines)


def _format_markdown_table(frame: pd.DataFrame, columns: Sequence[str]) -> list[str]:
    available_columns = [column for column in columns if column in frame.columns]
    if not available_columns or frame.empty:
        return ["No rows available."]

    display = frame.loc[:, available_columns].copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: f"{value:.3f}")
        else:
            display[column] = display[column].fillna("").astype(str)

    header = "| " + " | ".join(available_columns) + " |"
    divider = "| " + " | ".join(["---"] * len(available_columns)) + " |"
    rows = [
        "| " + " | ".join(row[column] for column in available_columns) + " |"
        for _, row in display.iterrows()
    ]
    return [header, divider, *rows]


def _normalize_summary_dict(summary: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in summary.items():
        if isinstance(value, float):
            normalized[key] = round(value, 8)
        elif isinstance(value, list):
            normalized[key] = [
                int(item) if isinstance(item, (int,)) else item
                for item in value
            ]
        else:
            normalized[key] = value
    return normalized
