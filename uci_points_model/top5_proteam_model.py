from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .historical_data_import import DEFAULT_IMPORTED_ROOT
from .target_definitions import default_top5_target_path
from .team_depth_features import build_team_depth_panel

TOP5_TRAINING_TABLE_FILENAME = "top5_proteam_training_table.csv"
TOP5_TARGET_COLUMN = "next_top5_proteam"
TOP5_BASELINE_SUMMARY_FILENAME = "top5_proteam_baseline_summary.json"
TOP5_BASELINE_PREDICTIONS_FILENAME = "top5_proteam_training_predictions.csv"
TOP5_TEAM_PANEL_SCORES_FILENAME = "team_season_top5_scores.csv"
TOP5_MODEL_OUTPUT_DIRNAME = "model_outputs"
DEFAULT_TOP5_BASELINE_REGULARIZATION = 0.25
DEFAULT_TOP5_BASELINE_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("baseline_n_riders_150", ("n_riders_150_plus",)),
    (
        "baseline_depth_concentration",
        ("n_riders_150_plus", "top5_share", "effective_contributors"),
    ),
)
MIN_PROBABILITY = 1e-9


@dataclass(frozen=True, slots=True)
class Top5ProTeamBaselineResult:
    model_name: str
    feature_columns: tuple[str, ...]
    intercept: float
    coefficients: dict[str, float]
    standardized_coefficients: dict[str, float]
    odds_ratios: dict[str, float]
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    training_rows: int
    positive_rows: int
    negative_rows: int
    iterations: int
    converged: bool
    regularization_strength: float
    in_sample_metrics: dict[str, float]
    expanding_window_summary: dict[str, object]
    expanding_window_folds: tuple[dict[str, object], ...]

    def predict_probability(self, dataset: pd.DataFrame) -> pd.Series:
        return predict_top5_proteam_probability(dataset, self)

    def to_dict(self) -> dict[str, object]:
        return {
            "model_name": self.model_name,
            "feature_columns": list(self.feature_columns),
            "intercept": round(self.intercept, 8),
            "coefficients": {
                feature: round(self.coefficients[feature], 8) for feature in self.feature_columns
            },
            "standardized_coefficients": {
                feature: round(self.standardized_coefficients[feature], 8)
                for feature in self.feature_columns
            },
            "odds_ratios": {
                feature: round(self.odds_ratios[feature], 8) for feature in self.feature_columns
            },
            "feature_means": {
                feature: round(self.feature_means[feature], 8) for feature in self.feature_columns
            },
            "feature_scales": {
                feature: round(self.feature_scales[feature], 8) for feature in self.feature_columns
            },
            "training_rows": self.training_rows,
            "positive_rows": self.positive_rows,
            "negative_rows": self.negative_rows,
            "iterations": self.iterations,
            "converged": self.converged,
            "regularization_strength": round(self.regularization_strength, 8),
            "in_sample_metrics": {
                key: round(float(value), 8) for key, value in self.in_sample_metrics.items()
            },
            "expanding_window_summary": _normalize_summary_dict(self.expanding_window_summary),
            "expanding_window_folds": [
                _normalize_summary_dict(fold_summary) for fold_summary in self.expanding_window_folds
            ],
        }


def build_top5_proteam_training_table(
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    team_depth_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    panel = team_depth_panel.copy() if team_depth_panel is not None else build_team_depth_panel(import_root=import_root)
    if panel.empty:
        return panel

    training_df = panel.loc[panel[TOP5_TARGET_COLUMN].notna()].copy()
    training_df["prior_season"] = training_df["season"]
    training_df["prior_team_slug"] = training_df["team_slug"]
    training_df["prior_team_name"] = training_df["team_name"]
    training_df["current_top5_proteam"] = (
        pd.to_numeric(training_df["proteam_rank"], errors="coerce").fillna(999).astype(int) <= 5
    ).astype(int)
    training_df["prior_total_pts"] = training_df["team_points_total"]
    training_df["prior_n_riders_150"] = training_df["n_riders_150_plus"]
    training_df["prior_n_riders_300"] = training_df["n_riders_300_plus"]
    training_df["prior_top1_share"] = training_df["top1_share"]
    training_df["prior_top3_share"] = training_df["top3_share"]
    training_df["prior_top5_share"] = training_df["top5_share"]
    training_df["prior_score_depth_index"] = training_df["score_depth_index"]
    training_df["target_source"] = "ranking_predictor_study_data"

    ordered_columns = [
        "prior_season",
        "next_season",
        "prior_team_name",
        "prior_team_slug",
        "team_base_slug",
        "next_team_slug",
        "next_team_name",
        "continuity_source",
        "proteam_rank",
        "current_top5_proteam",
        "prior_total_pts",
        "n_riders_scoring",
        "n_riders_50_plus",
        "n_riders_100_plus",
        "n_riders_150_plus",
        "n_riders_250_plus",
        "n_riders_300_plus",
        "n_riders_400_plus",
        "prior_n_riders_150",
        "prior_n_riders_300",
        "top1_share",
        "top3_share",
        "top5_share",
        "prior_top1_share",
        "prior_top3_share",
        "prior_top5_share",
        "effective_contributors",
        "points_outside_top5",
        "score_depth_index",
        "prior_score_depth_index",
        "avg_points_per_raceday",
        "median_points_per_raceday",
        "team_points_per_rider_raceday",
        "archetype_anchor_count",
        "archetype_engine_count",
        "archetype_banker_count",
        "next_proteam_rank",
        "next_team_points_total",
        "next_top3_proteam",
        "next_top5_proteam",
        "next_top8_proteam",
        "team_history_source",
        "rider_history_source",
        "target_source",
    ]
    available_columns = [column for column in ordered_columns if column in training_df.columns]
    training_df = training_df[available_columns]
    for column in (
        "prior_season",
        "next_season",
        "proteam_rank",
        "next_proteam_rank",
        "next_top3_proteam",
        "next_top5_proteam",
        "next_top8_proteam",
    ):
        if column in training_df.columns:
            training_df[column] = pd.to_numeric(training_df[column], errors="coerce").astype("Int64")
    return training_df.sort_values(["prior_season", "proteam_rank", "prior_team_name"]).reset_index(drop=True)


def fit_top5_proteam_baseline(
    training_df: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    model_name: str = "baseline_n_riders_150",
    target_column: str = TOP5_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_TOP5_BASELINE_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    include_expanding_window: bool = True,
    min_train_seasons: int = 1,
) -> Top5ProTeamBaselineResult:
    prepared = _prepare_top5_training_frame(training_df, feature_columns, target_column)
    feature_names = tuple(feature_columns)
    feature_matrix = prepared.loc[:, feature_names].to_numpy(dtype=float)
    target = prepared[target_column].astype(int).to_numpy()
    feature_means = feature_matrix.mean(axis=0)
    feature_scales = feature_matrix.std(axis=0)
    feature_scales = np.where(feature_scales > 0, feature_scales, 1.0)
    standardized_matrix = (feature_matrix - feature_means) / feature_scales
    coefficients_standardized, iterations, converged = _fit_penalized_logistic_regression(
        standardized_matrix,
        target,
        regularization_strength=regularization_strength,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )

    standardized_slopes = coefficients_standardized[1:]
    original_slopes = standardized_slopes / feature_scales
    intercept = float(
        coefficients_standardized[0] - np.sum(standardized_slopes * feature_means / feature_scales)
    )
    probabilities = _sigmoid(intercept + (feature_matrix @ original_slopes))
    in_sample_metrics = _compute_binary_classification_metrics(target, probabilities)

    expanding_window_summary: dict[str, object] = {
        "eligible": False,
        "fold_count": 0,
        "rows_scored": 0,
        "test_seasons": [],
    }
    expanding_window_folds: tuple[dict[str, object], ...] = ()
    if include_expanding_window:
        expanding_window_summary, expanding_window_folds, _ = evaluate_top5_proteam_expanding_window(
            training_df,
            feature_columns=feature_names,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            min_train_seasons=min_train_seasons,
        )

    return Top5ProTeamBaselineResult(
        model_name=model_name,
        feature_columns=feature_names,
        intercept=intercept,
        coefficients={
            feature: float(value) for feature, value in zip(feature_names, original_slopes, strict=True)
        },
        standardized_coefficients={
            feature: float(value)
            for feature, value in zip(feature_names, standardized_slopes, strict=True)
        },
        odds_ratios={
            feature: float(np.exp(value)) for feature, value in zip(feature_names, original_slopes, strict=True)
        },
        feature_means={
            feature: float(value) for feature, value in zip(feature_names, feature_means, strict=True)
        },
        feature_scales={
            feature: float(value) for feature, value in zip(feature_names, feature_scales, strict=True)
        },
        training_rows=int(len(prepared)),
        positive_rows=int(target.sum()),
        negative_rows=int(len(prepared) - target.sum()),
        iterations=iterations,
        converged=converged,
        regularization_strength=float(regularization_strength),
        in_sample_metrics=in_sample_metrics,
        expanding_window_summary=expanding_window_summary,
        expanding_window_folds=expanding_window_folds,
    )


def fit_top5_proteam_baseline_suite(
    training_df: pd.DataFrame,
    model_specs: Sequence[tuple[str, Sequence[str]]] = DEFAULT_TOP5_BASELINE_SPECS,
    *,
    target_column: str = TOP5_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_TOP5_BASELINE_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> tuple[Top5ProTeamBaselineResult, ...]:
    return tuple(
        fit_top5_proteam_baseline(
            training_df,
            feature_columns=feature_columns,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            min_train_seasons=min_train_seasons,
        )
        for model_name, feature_columns in model_specs
    )


def predict_top5_proteam_probability(
    dataset: pd.DataFrame,
    fit_result: Top5ProTeamBaselineResult,
) -> pd.Series:
    if dataset.empty:
        return pd.Series(index=dataset.index, dtype=float, name="predicted_next_top5_probability")

    feature_frame = _coerce_numeric_frame(dataset, fit_result.feature_columns)
    linear_score = pd.Series(fit_result.intercept, index=dataset.index, dtype=float)
    for feature in fit_result.feature_columns:
        linear_score = linear_score + (feature_frame[feature] * fit_result.coefficients[feature])
    probabilities = pd.Series(
        _sigmoid(linear_score.to_numpy(dtype=float)),
        index=dataset.index,
        dtype=float,
        name="predicted_next_top5_probability",
    )
    return probabilities


def score_top5_proteam_dataset(
    dataset: pd.DataFrame,
    fit_result: Top5ProTeamBaselineResult,
    *,
    evaluation_split: str,
    ranking_group_column: str | None = None,
    train_next_seasons: str = "",
    test_next_season: int | None = None,
) -> pd.DataFrame:
    scored = dataset.copy()
    scored["predicted_next_top5_probability"] = predict_top5_proteam_probability(scored, fit_result)
    scored["predicted_next_top5_label"] = (
        pd.to_numeric(scored["predicted_next_top5_probability"], errors="coerce").fillna(0.0) >= 0.5
    ).astype(int)
    scored["model_name"] = fit_result.model_name
    scored["evaluation_split"] = evaluation_split
    scored["train_next_seasons"] = train_next_seasons
    scored["test_next_season"] = pd.Series(test_next_season, index=scored.index, dtype="Int64")
    scored["predicted_probability_rank"] = pd.Series(pd.NA, index=scored.index, dtype="Int64")

    active_group_column = ranking_group_column
    if active_group_column is None:
        if "next_season" in scored.columns and scored["next_season"].notna().any():
            active_group_column = "next_season"
        elif "season" in scored.columns and scored["season"].notna().any():
            active_group_column = "season"

    if active_group_column is not None and active_group_column in scored.columns:
        mask = scored[active_group_column].notna()
        if mask.any():
            ranked = (
                scored.loc[mask]
                .groupby(active_group_column)["predicted_next_top5_probability"]
                .rank(ascending=False, method="first")
                .astype("Int64")
            )
            scored.loc[ranked.index, "predicted_probability_rank"] = ranked
    return scored


def evaluate_top5_proteam_expanding_window(
    training_df: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    model_name: str,
    target_column: str = TOP5_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_TOP5_BASELINE_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> tuple[dict[str, object], tuple[dict[str, object], ...], pd.DataFrame]:
    prepared = _prepare_top5_training_frame(training_df, feature_columns, target_column)
    next_seasons = sorted(
        pd.to_numeric(prepared["next_season"], errors="coerce").dropna().astype(int).unique().tolist()
    )
    fold_summaries: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []

    for test_next_season in next_seasons:
        train = prepared.loc[pd.to_numeric(prepared["next_season"], errors="coerce") < test_next_season].copy()
        if train.empty:
            continue
        train_next_seasons = sorted(train["next_season"].astype(int).unique().tolist())
        if len(train_next_seasons) < min_train_seasons:
            continue

        test = prepared.loc[pd.to_numeric(prepared["next_season"], errors="coerce") == test_next_season].copy()
        if test.empty:
            continue

        fold_result = fit_top5_proteam_baseline(
            train,
            feature_columns=feature_columns,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            include_expanding_window=False,
        )
        scored_fold = score_top5_proteam_dataset(
            test,
            fold_result,
            evaluation_split="expanding_window_test",
            ranking_group_column="next_season",
            train_next_seasons=", ".join(str(value) for value in train_next_seasons),
            test_next_season=int(test_next_season),
        )
        actual = scored_fold[target_column].astype(int).to_numpy()
        probabilities = scored_fold["predicted_next_top5_probability"].to_numpy(dtype=float)
        fold_metrics = _compute_binary_classification_metrics(actual, probabilities)
        top_k = max(int(actual.sum()), 1)
        captured_mask = (
            scored_fold["predicted_probability_rank"].fillna(999).astype(int) <= top_k
        )
        scored_fold["captured_in_top_k"] = captured_mask.astype(int)

        fold_summaries.append(
            {
                "test_next_season": int(test_next_season),
                "train_next_seasons": train_next_seasons,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "actual_positive_rows": int(actual.sum()),
                "predicted_positive_rows": int(scored_fold["predicted_next_top5_label"].sum()),
                "top_k": int(top_k),
                "top_k_capture": round(
                    float(scored_fold.loc[captured_mask, target_column].sum() / max(int(actual.sum()), 1)),
                    8,
                ),
                "accuracy": round(fold_metrics["accuracy"], 8),
                "precision": round(fold_metrics["precision"], 8),
                "recall": round(fold_metrics["recall"], 8),
                "brier_score": round(fold_metrics["brier_score"], 8),
                "log_loss": round(fold_metrics["log_loss"], 8),
            }
        )
        prediction_frames.append(scored_fold)

    if not fold_summaries:
        return (
            {"eligible": False, "fold_count": 0, "rows_scored": 0, "test_seasons": []},
            (),
            pd.DataFrame(),
        )

    fold_frame = pd.DataFrame(fold_summaries)
    weighted_rows = pd.to_numeric(fold_frame["test_rows"], errors="coerce")
    weighted_positives = pd.to_numeric(fold_frame["actual_positive_rows"], errors="coerce")
    summary: dict[str, object] = {
        "eligible": True,
        "fold_count": int(len(fold_frame)),
        "rows_scored": int(weighted_rows.sum()),
        "test_seasons": [int(value) for value in fold_frame["test_next_season"].tolist()],
        "accuracy": round(_weighted_mean(fold_frame["accuracy"], weighted_rows), 8),
        "precision": round(_weighted_mean(fold_frame["precision"], weighted_rows), 8),
        "recall": round(_weighted_mean(fold_frame["recall"], weighted_rows), 8),
        "brier_score": round(_weighted_mean(fold_frame["brier_score"], weighted_rows), 8),
        "log_loss": round(_weighted_mean(fold_frame["log_loss"], weighted_rows), 8),
        "top_k_capture": round(_weighted_mean(fold_frame["top_k_capture"], weighted_positives), 8),
    }
    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    return summary, tuple(fold_summaries), predictions


def build_top5_proteam_baseline_artifacts(
    training_df: pd.DataFrame,
    *,
    team_panel_df: pd.DataFrame | None = None,
    model_specs: Sequence[tuple[str, Sequence[str]]] = DEFAULT_TOP5_BASELINE_SPECS,
    regularization_strength: float = DEFAULT_TOP5_BASELINE_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    results = fit_top5_proteam_baseline_suite(
        training_df,
        model_specs=model_specs,
        regularization_strength=regularization_strength,
        max_iterations=max_iterations,
        tolerance=tolerance,
        min_train_seasons=min_train_seasons,
    )

    prediction_frames: list[pd.DataFrame] = []
    team_panel_frames: list[pd.DataFrame] = []
    for result in results:
        prediction_frames.append(
            score_top5_proteam_dataset(
                training_df,
                result,
                evaluation_split="full_fit",
                ranking_group_column="next_season" if "next_season" in training_df.columns else None,
            )
        )
        _, _, expanding_predictions = evaluate_top5_proteam_expanding_window(
            training_df,
            feature_columns=result.feature_columns,
            model_name=result.model_name,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            min_train_seasons=min_train_seasons,
        )
        if not expanding_predictions.empty:
            prediction_frames.append(expanding_predictions)
        if team_panel_df is not None and not team_panel_df.empty:
            team_panel_frames.append(
                score_top5_proteam_dataset(
                    team_panel_df,
                    result,
                    evaluation_split="full_fit_team_panel",
                    ranking_group_column="season" if "season" in team_panel_df.columns else None,
                )
            )

    training_summary = _prepare_top5_training_frame(
        training_df,
        DEFAULT_TOP5_BASELINE_SPECS[0][1],
        TOP5_TARGET_COLUMN,
    )
    summary = {
        "artifact_version": "top5_proteam_baseline_v1",
        "anchor_model_name": DEFAULT_TOP5_BASELINE_SPECS[0][0],
        "training_summary": {
            "rows": int(len(training_summary)),
            "positive_rows": int(training_summary[TOP5_TARGET_COLUMN].sum()),
            "negative_rows": int(len(training_summary) - training_summary[TOP5_TARGET_COLUMN].sum()),
            "next_seasons": [
                int(value)
                for value in sorted(
                    pd.to_numeric(training_summary["next_season"], errors="coerce")
                    .dropna()
                    .astype(int)
                    .unique()
                    .tolist()
                )
            ],
        },
        "model_results": [result.to_dict() for result in results],
    }
    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    team_panel_scores = pd.concat(team_panel_frames, ignore_index=True) if team_panel_frames else pd.DataFrame()
    return summary, predictions, team_panel_scores


def default_top5_proteam_training_table_path() -> Path:
    return default_top5_target_path(TOP5_TRAINING_TABLE_FILENAME)


def default_top5_proteam_model_output_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / TOP5_MODEL_OUTPUT_DIRNAME


def write_top5_proteam_training_table(
    dataset: pd.DataFrame,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(output_path) if output_path is not None else default_top5_proteam_training_table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)
    return path


def write_top5_proteam_baseline_artifacts(
    summary: dict[str, object],
    predictions: pd.DataFrame,
    *,
    team_panel_scores: pd.DataFrame | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_root) if output_root is not None else default_top5_proteam_model_output_root()
    root.mkdir(parents=True, exist_ok=True)

    summary_path = root / TOP5_BASELINE_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    predictions_path = root / TOP5_BASELINE_PREDICTIONS_FILENAME
    predictions.to_csv(predictions_path, index=False)

    written_paths: dict[str, Path] = {
        "summary_path": summary_path,
        "predictions_path": predictions_path,
    }
    if team_panel_scores is not None and not team_panel_scores.empty:
        team_panel_scores_path = root / TOP5_TEAM_PANEL_SCORES_FILENAME
        team_panel_scores.to_csv(team_panel_scores_path, index=False)
        written_paths["team_panel_scores_path"] = team_panel_scores_path
    return written_paths


def _prepare_top5_training_frame(
    dataset: pd.DataFrame,
    feature_columns: Sequence[str],
    target_column: str,
) -> pd.DataFrame:
    required_columns = list(feature_columns) + [target_column]
    missing_columns = [column for column in required_columns if column not in dataset.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns for top-five ProTeam model: {missing_columns}")

    prepared = dataset.copy()
    prepared.loc[:, feature_columns] = _coerce_numeric_frame(prepared, feature_columns)
    prepared[target_column] = pd.to_numeric(prepared[target_column], errors="coerce")
    prepared = prepared.dropna(subset=required_columns).reset_index(drop=True)
    if prepared.empty:
        raise ValueError("No observed rows remained after preparing the top-five ProTeam training frame.")

    target_values = prepared[target_column].astype(int)
    if target_values.nunique() < 2:
        raise ValueError("Top-five ProTeam baseline requires both positive and negative target rows.")
    prepared[target_column] = target_values
    return prepared


def _coerce_numeric_frame(dataset: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    return dataset.loc[:, columns].apply(pd.to_numeric, errors="coerce")


def _fit_penalized_logistic_regression(
    standardized_matrix: np.ndarray,
    target: np.ndarray,
    *,
    regularization_strength: float,
    max_iterations: int,
    tolerance: float,
) -> tuple[np.ndarray, int, bool]:
    design_matrix = np.column_stack([np.ones(len(standardized_matrix)), standardized_matrix])
    coefficients = np.zeros(design_matrix.shape[1], dtype=float)
    penalty = np.eye(design_matrix.shape[1], dtype=float) * float(max(regularization_strength, 0.0))
    penalty[0, 0] = 0.0
    converged = False
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        probabilities = _sigmoid(design_matrix @ coefficients)
        weights = np.clip(probabilities * (1.0 - probabilities), 1e-9, None)
        gradient = (design_matrix.T @ (probabilities - target)) + (penalty @ coefficients)
        hessian = ((design_matrix.T * weights) @ design_matrix) + penalty
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(hessian) @ gradient
        coefficients = coefficients - step
        if float(np.max(np.abs(step))) <= tolerance:
            converged = True
            break

    return coefficients, iterations, converged


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _compute_binary_classification_metrics(
    actual: Sequence[int] | np.ndarray,
    probabilities: Sequence[float] | np.ndarray,
) -> dict[str, float]:
    actual_array = np.asarray(actual, dtype=int)
    probability_array = np.asarray(probabilities, dtype=float)
    clipped_probabilities = np.clip(probability_array, MIN_PROBABILITY, 1.0 - MIN_PROBABILITY)
    predicted = (clipped_probabilities >= 0.5).astype(int)

    true_positive = int(((predicted == 1) & (actual_array == 1)).sum())
    false_positive = int(((predicted == 1) & (actual_array == 0)).sum())
    false_negative = int(((predicted == 0) & (actual_array == 1)).sum())

    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    accuracy = float((predicted == actual_array).mean())
    brier_score = float(np.mean((clipped_probabilities - actual_array) ** 2))
    log_loss = float(
        -np.mean(
            (actual_array * np.log(clipped_probabilities))
            + ((1 - actual_array) * np.log(1.0 - clipped_probabilities))
        )
    )

    return {
        "accuracy": accuracy,
        "precision": float(precision),
        "recall": float(recall),
        "brier_score": brier_score,
        "log_loss": log_loss,
    }


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    value_array = pd.to_numeric(values, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    weight_array = pd.to_numeric(weights, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    denominator = float(weight_array.sum())
    if denominator <= 0:
        if len(value_array) == 0:
            return 0.0
        return float(value_array.mean())
    return float(np.average(value_array, weights=weight_array))


def _normalize_summary_dict(summary: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in summary.items():
        if isinstance(value, float):
            normalized[key] = round(value, 8)
        elif isinstance(value, list):
            normalized[key] = [int(item) if isinstance(item, (int, np.integer)) else item for item in value]
        else:
            normalized[key] = int(value) if isinstance(value, np.integer) else value
    return normalized
