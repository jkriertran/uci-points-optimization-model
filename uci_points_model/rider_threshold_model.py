from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .data_sources import load_historical_dataset
from .historical_data_import import DEFAULT_IMPORTED_ROOT
from .team_identity import canonicalize_team_slug
from .top5_proteam_model import (
    _compute_binary_classification_metrics,
    _fit_penalized_logistic_regression,
    _sigmoid,
    _weighted_mean,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RIDER_MODEL_INPUT_ROOT = PROJECT_ROOT / "data" / "model_inputs"
RIDER_MODEL_OUTPUT_ROOT = PROJECT_ROOT / "data" / "model_outputs"

RIDER_SEASON_PANEL_FILENAME = "rider_season_panel.csv"
RIDER_THRESHOLD_TARGET_COLUMN = "rider_reaches_150_next_season"
RIDER_THRESHOLD_SUMMARY_FILENAME = "rider_threshold_baseline_summary.json"
RIDER_THRESHOLD_PREDICTIONS_FILENAME = "rider_threshold_training_predictions.csv"
RIDER_THRESHOLD_PANEL_SCORES_FILENAME = "rider_season_threshold_scores.csv"

DEFAULT_RIDER_THRESHOLD_REGULARIZATION = 1.0
DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("baseline_prior_points", ("uci_points",)),
    (
        "baseline_points_scoring_role",
        ("uci_points", "n_scoring_results", "team_rank_within_roster"),
    ),
)


@dataclass(frozen=True, slots=True)
class RiderThresholdBaselineResult:
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


def build_rider_season_panel(
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    current_snapshot_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rider_df, rider_decision = load_historical_dataset(
        dataset_key="historical_proteam_rider_panel",
        import_root=import_root,
    )
    team_df, team_decision = load_historical_dataset(
        dataset_key="historical_proteam_team_panel",
        import_root=import_root,
    )
    if rider_df.empty or team_df.empty:
        raise ValueError("Imported historical rider and team panels are required to build the rider-season panel.")

    panel = _normalize_rider_panel(rider_df)
    team_context = _normalize_team_context(team_df)
    team_context = _apply_current_snapshot_team_context_overrides(
        team_context,
        current_snapshot_df=current_snapshot_df,
    )
    panel = panel.merge(
        team_context,
        on=["season", "team_slug"],
        how="left",
        validate="many_to_one",
    )

    summary_df, summary_decision = load_historical_dataset(
        dataset_key="rider_season_result_summary",
        import_root=import_root,
    )
    panel = panel.merge(
        _normalize_rider_result_summary(summary_df),
        on=["season", "rider_slug", "team_slug"],
        how="left",
        validate="one_to_one",
    )

    transfer_df, transfer_decision = load_historical_dataset(
        dataset_key="rider_transfer_context_enriched",
        import_root=import_root,
    )
    panel = panel.merge(
        _normalize_transfer_context(transfer_df),
        on=["season", "rider_slug", "team_slug"],
        how="left",
        validate="one_to_one",
    )

    next_season_map = _build_next_season_map(panel)
    panel = panel.merge(
        next_season_map,
        on=["next_season", "rider_slug"],
        how="left",
        validate="one_to_one",
    )

    panel["has_observed_next_season"] = panel["next_uci_points"].notna()
    panel["same_team_base_next_season"] = (
        panel["has_observed_next_season"]
        & (panel["team_base_slug"].fillna("") == panel["next_team_base_slug"].fillna(""))
    )
    panel["same_team_base_next_season"] = panel["same_team_base_next_season"].astype("boolean")
    panel[RIDER_THRESHOLD_TARGET_COLUMN] = pd.Series(pd.NA, index=panel.index, dtype="Int64")
    observed_next = panel["has_observed_next_season"]
    panel.loc[observed_next, RIDER_THRESHOLD_TARGET_COLUMN] = (
        pd.to_numeric(panel.loc[observed_next, "next_uci_points"], errors="coerce").fillna(0.0) >= 150.0
    ).astype(int)
    panel["rider_reaches_250_next_season"] = pd.Series(pd.NA, index=panel.index, dtype="Int64")
    panel.loc[observed_next, "rider_reaches_250_next_season"] = (
        pd.to_numeric(panel.loc[observed_next, "next_uci_points"], errors="coerce").fillna(0.0) >= 250.0
    ).astype(int)
    panel["next_points_delta"] = (
        pd.to_numeric(panel["next_uci_points"], errors="coerce")
        - pd.to_numeric(panel["uci_points"], errors="coerce")
    )
    panel["next_racedays_delta"] = (
        pd.to_numeric(panel["next_racedays"], errors="coerce")
        - pd.to_numeric(panel["racedays"], errors="coerce")
    )

    panel["rider_history_source"] = rider_decision.selected_source
    panel["team_context_source"] = team_decision.selected_source
    panel["result_summary_source"] = summary_decision.selected_source
    panel["transfer_context_source"] = transfer_decision.selected_source

    ordered_columns = [
        "season",
        "next_season",
        "rider_name",
        "rider_slug",
        "team_name",
        "team_slug",
        "team_base_slug",
        "team_class",
        "archetype",
        "uci_points",
        "pcs_points",
        "racedays",
        "wins_panel",
        "points_per_raceday",
        "team_rank_within_roster",
        "team_points_share",
        "current_scored_150_flag",
        "current_scored_250_flag",
        "team_proteam_rank",
        "team_points_total",
        "team_top1_share",
        "team_top3_share",
        "team_top5_share",
        "team_n_riders_100_plus",
        "team_n_riders_150_plus",
        "team_n_riders_250_plus",
        "team_n_riders_400_plus",
        "result_summary_available",
        "total_uci_points_detailed",
        "total_pcs_points_detailed",
        "uci_point_diff_vs_panel",
        "points_match_within_1",
        "gap_classification",
        "n_starts",
        "n_started",
        "n_finished",
        "n_dnf",
        "n_dns",
        "n_wins",
        "n_podiums",
        "n_top10s",
        "n_scoring_results",
        "finish_rate",
        "scoring_rate",
        "uci_points_from_stages",
        "uci_points_from_gc",
        "uci_points_from_one_day",
        "uci_points_from_secondary_classifications",
        "stage_points_share",
        "gc_points_share",
        "one_day_points_share",
        "secondary_points_share",
        "transfer_context_available",
        "age_on_jan_1",
        "specialty_primary",
        "transfer_step_label",
        "had_prior_year_trainee_with_team_to",
        "prior_year_uci_points",
        "prior_year_n_starts",
        "prior_year_scored_150_flag",
        "next_team_name",
        "next_team_slug",
        "next_team_base_slug",
        "next_team_class",
        "next_uci_points",
        "next_racedays",
        "next_points_per_raceday",
        "next_team_rank_within_roster",
        "next_team_points_share",
        "has_observed_next_season",
        "same_team_base_next_season",
        RIDER_THRESHOLD_TARGET_COLUMN,
        "rider_reaches_250_next_season",
        "next_points_delta",
        "next_racedays_delta",
        "rider_history_source",
        "team_context_source",
        "result_summary_source",
        "transfer_context_source",
    ]
    available_columns = [column for column in ordered_columns if column in panel.columns]
    panel = panel[available_columns]
    panel = panel.sort_values(
        ["season", "team_name", "team_rank_within_roster", "rider_name"],
        na_position="last",
    ).reset_index(drop=True)
    return panel


def fit_rider_threshold_baseline(
    rider_panel: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    model_name: str = "baseline_prior_points",
    target_column: str = RIDER_THRESHOLD_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    include_expanding_window: bool = True,
    min_train_seasons: int = 1,
) -> RiderThresholdBaselineResult:
    prepared = _prepare_rider_training_frame(rider_panel, feature_columns, target_column)
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
        expanding_window_summary, expanding_window_folds, _ = evaluate_rider_threshold_expanding_window(
            rider_panel,
            feature_columns=feature_names,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            min_train_seasons=min_train_seasons,
        )

    return RiderThresholdBaselineResult(
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


def fit_rider_threshold_baseline_suite(
    rider_panel: pd.DataFrame,
    model_specs: Sequence[tuple[str, Sequence[str]]] = DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS,
    *,
    target_column: str = RIDER_THRESHOLD_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> tuple[RiderThresholdBaselineResult, ...]:
    return tuple(
        fit_rider_threshold_baseline(
            rider_panel,
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


def predict_rider_threshold_probability(
    dataset: pd.DataFrame,
    fit_result: RiderThresholdBaselineResult,
) -> pd.Series:
    if dataset.empty:
        return pd.Series(index=dataset.index, dtype=float, name="predicted_rider_reaches_150_probability")

    feature_frame = dataset.loc[:, fit_result.feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    linear_score = pd.Series(fit_result.intercept, index=dataset.index, dtype=float)
    for feature in fit_result.feature_columns:
        linear_score = linear_score + (feature_frame[feature] * fit_result.coefficients[feature])
    probabilities = pd.Series(
        _sigmoid(linear_score.to_numpy(dtype=float)),
        index=dataset.index,
        dtype=float,
        name="predicted_rider_reaches_150_probability",
    )
    return probabilities


def score_rider_threshold_dataset(
    dataset: pd.DataFrame,
    fit_result: RiderThresholdBaselineResult,
    *,
    evaluation_split: str,
    ranking_group_column: str | None = None,
    train_next_seasons: str = "",
    test_next_season: int | None = None,
) -> pd.DataFrame:
    scored = dataset.copy()
    scored["predicted_rider_reaches_150_probability"] = predict_rider_threshold_probability(scored, fit_result)
    scored["predicted_rider_reaches_150_label"] = (
        pd.to_numeric(scored["predicted_rider_reaches_150_probability"], errors="coerce").fillna(0.0) >= 0.5
    ).astype(int)
    scored["model_name"] = fit_result.model_name
    scored["evaluation_split"] = evaluation_split
    scored["train_next_seasons"] = train_next_seasons
    scored["test_next_season"] = pd.Series(test_next_season, index=scored.index, dtype="Int64")
    scored["predicted_probability_rank"] = pd.Series(pd.NA, index=scored.index, dtype="Int64")

    active_group_column = ranking_group_column
    if active_group_column is None:
        if "season" in scored.columns and scored["season"].notna().any():
            active_group_column = "season"
        elif "next_season" in scored.columns and scored["next_season"].notna().any():
            active_group_column = "next_season"

    if active_group_column is not None and active_group_column in scored.columns:
        mask = scored[active_group_column].notna()
        if mask.any():
            ranked = (
                scored.loc[mask]
                .groupby(active_group_column)["predicted_rider_reaches_150_probability"]
                .rank(ascending=False, method="first")
                .astype("Int64")
            )
            scored.loc[ranked.index, "predicted_probability_rank"] = ranked
    return scored


def evaluate_rider_threshold_expanding_window(
    rider_panel: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    model_name: str,
    target_column: str = RIDER_THRESHOLD_TARGET_COLUMN,
    regularization_strength: float = DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> tuple[dict[str, object], tuple[dict[str, object], ...], pd.DataFrame]:
    prepared = _prepare_rider_training_frame(rider_panel, feature_columns, target_column)
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

        fold_result = fit_rider_threshold_baseline(
            train,
            feature_columns=feature_columns,
            model_name=model_name,
            target_column=target_column,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            include_expanding_window=False,
        )
        scored_fold = score_rider_threshold_dataset(
            test,
            fold_result,
            evaluation_split="expanding_window_test",
            ranking_group_column="next_season",
            train_next_seasons=", ".join(str(value) for value in train_next_seasons),
            test_next_season=int(test_next_season),
        )
        actual = scored_fold[target_column].astype(int).to_numpy()
        probabilities = scored_fold["predicted_rider_reaches_150_probability"].to_numpy(dtype=float)
        fold_metrics = _compute_binary_classification_metrics(actual, probabilities)
        top_k = max(int(actual.sum()), 1)
        captured_mask = (
            scored_fold["predicted_probability_rank"].fillna(999999).astype(int) <= top_k
        )
        scored_fold["captured_in_top_k"] = captured_mask.astype(int)

        fold_summaries.append(
            {
                "test_next_season": int(test_next_season),
                "train_next_seasons": train_next_seasons,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "actual_positive_rows": int(actual.sum()),
                "predicted_positive_rows": int(scored_fold["predicted_rider_reaches_150_label"].sum()),
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


def build_rider_threshold_baseline_artifacts(
    rider_panel: pd.DataFrame,
    *,
    model_specs: Sequence[tuple[str, Sequence[str]]] = DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS,
    regularization_strength: float = DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    max_iterations: int = 200,
    tolerance: float = 1e-8,
    min_train_seasons: int = 1,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    results = fit_rider_threshold_baseline_suite(
        rider_panel,
        model_specs=model_specs,
        regularization_strength=regularization_strength,
        max_iterations=max_iterations,
        tolerance=tolerance,
        min_train_seasons=min_train_seasons,
    )

    prediction_frames: list[pd.DataFrame] = []
    panel_score_frames: list[pd.DataFrame] = []
    for result in results:
        training_rows = rider_panel.loc[rider_panel[RIDER_THRESHOLD_TARGET_COLUMN].notna()].copy()
        prediction_frames.append(
            score_rider_threshold_dataset(
                training_rows,
                result,
                evaluation_split="full_fit",
                ranking_group_column="next_season" if "next_season" in training_rows.columns else None,
            )
        )
        _, _, expanding_predictions = evaluate_rider_threshold_expanding_window(
            rider_panel,
            feature_columns=result.feature_columns,
            model_name=result.model_name,
            regularization_strength=regularization_strength,
            max_iterations=max_iterations,
            tolerance=tolerance,
            min_train_seasons=min_train_seasons,
        )
        if not expanding_predictions.empty:
            prediction_frames.append(expanding_predictions)
        panel_score_frames.append(
            score_rider_threshold_dataset(
                rider_panel,
                result,
                evaluation_split="full_fit_panel",
                ranking_group_column="season" if "season" in rider_panel.columns else None,
            )
        )

    training_frame = _prepare_rider_training_frame(
        rider_panel,
        DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS[0][1],
        RIDER_THRESHOLD_TARGET_COLUMN,
    )
    summary = {
        "artifact_version": "rider_threshold_baseline_v1",
        "anchor_model_name": DEFAULT_RIDER_THRESHOLD_BASELINE_SPECS[0][0],
        "training_summary": {
            "rows": int(len(training_frame)),
            "positive_rows": int(training_frame[RIDER_THRESHOLD_TARGET_COLUMN].sum()),
            "negative_rows": int(len(training_frame) - training_frame[RIDER_THRESHOLD_TARGET_COLUMN].sum()),
            "next_seasons": [
                int(value)
                for value in sorted(
                    pd.to_numeric(training_frame["next_season"], errors="coerce")
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
    panel_scores = pd.concat(panel_score_frames, ignore_index=True) if panel_score_frames else pd.DataFrame()
    return summary, predictions, panel_scores


def write_rider_season_panel(
    dataset: pd.DataFrame,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(output_path) if output_path is not None else default_rider_season_panel_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)
    return path


def write_rider_threshold_baseline_artifacts(
    summary: dict[str, object],
    predictions: pd.DataFrame,
    *,
    panel_scores: pd.DataFrame | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_root) if output_root is not None else default_rider_threshold_output_root()
    root.mkdir(parents=True, exist_ok=True)

    summary_path = root / RIDER_THRESHOLD_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    predictions_path = root / RIDER_THRESHOLD_PREDICTIONS_FILENAME
    predictions.to_csv(predictions_path, index=False)

    written_paths: dict[str, Path] = {
        "summary_path": summary_path,
        "predictions_path": predictions_path,
    }
    if panel_scores is not None and not panel_scores.empty:
        panel_scores_path = root / RIDER_THRESHOLD_PANEL_SCORES_FILENAME
        panel_scores.to_csv(panel_scores_path, index=False)
        written_paths["panel_scores_path"] = panel_scores_path
    return written_paths


def default_rider_season_panel_path() -> Path:
    return RIDER_MODEL_INPUT_ROOT / RIDER_SEASON_PANEL_FILENAME


def default_rider_threshold_output_root() -> Path:
    return RIDER_MODEL_OUTPUT_ROOT


def _normalize_rider_panel(rider_df: pd.DataFrame) -> pd.DataFrame:
    panel = rider_df.rename(
        columns={
            "season_year": "season",
            "wins": "wins_panel",
        }
    ).copy()
    panel["season"] = pd.to_numeric(panel["season"], errors="coerce").astype("Int64")
    panel["next_season"] = panel["season"] + 1
    panel["team_base_slug"] = panel.apply(
        lambda row: canonicalize_team_slug(row["team_slug"], int(row["season"])),
        axis=1,
    )
    panel["current_scored_150_flag"] = (
        pd.to_numeric(panel["uci_points"], errors="coerce").fillna(0.0) >= 150.0
    ).astype(int)
    panel["current_scored_250_flag"] = (
        pd.to_numeric(panel["uci_points"], errors="coerce").fillna(0.0) >= 250.0
    ).astype(int)
    return panel


def _normalize_team_context(team_df: pd.DataFrame) -> pd.DataFrame:
    context = team_df.rename(
        columns={
            "season_year": "season",
            "team_rank": "team_proteam_rank",
            "team_total_uci_points": "team_points_total",
            "top1_share": "team_top1_share",
            "top3_share": "team_top3_share",
            "top5_share": "team_top5_share",
            "n_riders_100": "team_n_riders_100_plus",
            "n_riders_150": "team_n_riders_150_plus",
            "n_riders_250": "team_n_riders_250_plus",
            "n_riders_400": "team_n_riders_400_plus",
        }
    ).copy()
    keep_columns = [
        "season",
        "team_slug",
        "team_proteam_rank",
        "team_points_total",
        "team_top1_share",
        "team_top3_share",
        "team_top5_share",
        "team_n_riders_100_plus",
        "team_n_riders_150_plus",
        "team_n_riders_250_plus",
        "team_n_riders_400_plus",
    ]
    context = context[keep_columns]
    context["season"] = pd.to_numeric(context["season"], errors="coerce").astype("Int64")
    return context


def _apply_current_snapshot_team_context_overrides(
    team_context: pd.DataFrame,
    *,
    current_snapshot_df: pd.DataFrame | None,
) -> pd.DataFrame:
    # Rider context stays in season space. The rolling counted-ranking snapshot is
    # useful for separate monitoring, but it should not overwrite season-only team context.
    _ = current_snapshot_df
    return team_context.copy()


def _normalize_rider_result_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "rider_slug",
                "team_slug",
                "result_summary_available",
                "total_uci_points_detailed",
                "total_pcs_points_detailed",
                "uci_point_diff_vs_panel",
                "points_match_within_1",
                "gap_classification",
                "n_starts",
                "n_started",
                "n_finished",
                "n_dnf",
                "n_dns",
                "n_wins",
                "n_podiums",
                "n_top10s",
                "n_scoring_results",
                "finish_rate",
                "scoring_rate",
                "uci_points_from_stages",
                "uci_points_from_gc",
                "uci_points_from_one_day",
                "uci_points_from_secondary_classifications",
                "stage_points_share",
                "gc_points_share",
                "one_day_points_share",
                "secondary_points_share",
            ]
        )

    summary = summary_df.rename(columns={"season_year": "season"}).copy()
    summary["season"] = pd.to_numeric(summary["season"], errors="coerce").astype("Int64")
    summary["result_summary_available"] = True
    summary["finish_rate"] = (
        pd.to_numeric(summary["n_finished"], errors="coerce")
        / pd.to_numeric(summary["n_started"], errors="coerce").replace(0, pd.NA)
    )
    summary["scoring_rate"] = (
        pd.to_numeric(summary["n_scoring_results"], errors="coerce")
        / pd.to_numeric(summary["n_starts"], errors="coerce").replace(0, pd.NA)
    )
    total_detailed = pd.to_numeric(summary["total_uci_points_detailed"], errors="coerce")
    summary["stage_points_share"] = (
        pd.to_numeric(summary["uci_points_from_stages"], errors="coerce") / total_detailed.replace(0, pd.NA)
    )
    summary["gc_points_share"] = (
        pd.to_numeric(summary["uci_points_from_gc"], errors="coerce") / total_detailed.replace(0, pd.NA)
    )
    summary["one_day_points_share"] = (
        pd.to_numeric(summary["uci_points_from_one_day"], errors="coerce") / total_detailed.replace(0, pd.NA)
    )
    summary["secondary_points_share"] = (
        pd.to_numeric(summary["uci_points_from_secondary_classifications"], errors="coerce")
        / total_detailed.replace(0, pd.NA)
    )
    keep_columns = [
        "season",
        "rider_slug",
        "team_slug",
        "result_summary_available",
        "total_uci_points_detailed",
        "total_pcs_points_detailed",
        "uci_point_diff_vs_panel",
        "points_match_within_1",
        "gap_classification",
        "n_starts",
        "n_started",
        "n_finished",
        "n_dnf",
        "n_dns",
        "n_wins",
        "n_podiums",
        "n_top10s",
        "n_scoring_results",
        "finish_rate",
        "scoring_rate",
        "uci_points_from_stages",
        "uci_points_from_gc",
        "uci_points_from_one_day",
        "uci_points_from_secondary_classifications",
        "stage_points_share",
        "gc_points_share",
        "one_day_points_share",
        "secondary_points_share",
    ]
    return summary[keep_columns]


def _normalize_transfer_context(transfer_df: pd.DataFrame) -> pd.DataFrame:
    if transfer_df.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "rider_slug",
                "team_slug",
                "transfer_context_available",
                "age_on_jan_1",
                "specialty_primary",
                "transfer_step_label",
                "had_prior_year_trainee_with_team_to",
                "prior_year_uci_points",
                "prior_year_n_starts",
                "prior_year_scored_150_flag",
            ]
        )

    transfer = transfer_df.rename(
        columns={
            "year_to": "season",
            "team_to_slug": "team_slug",
        }
    ).copy()
    transfer["season"] = pd.to_numeric(transfer["season"], errors="coerce").astype("Int64")
    transfer["transfer_context_available"] = True
    keep_columns = [
        "season",
        "rider_slug",
        "team_slug",
        "transfer_context_available",
        "age_on_jan_1",
        "specialty_primary",
        "transfer_step_label",
        "had_prior_year_trainee_with_team_to",
        "prior_year_uci_points",
        "prior_year_n_starts",
        "prior_year_scored_150_flag",
    ]
    return transfer[keep_columns]


def _build_next_season_map(panel: pd.DataFrame) -> pd.DataFrame:
    next_map = panel[
        [
            "season",
            "rider_slug",
            "team_name",
            "team_slug",
            "team_base_slug",
            "team_class",
            "uci_points",
            "racedays",
            "points_per_raceday",
            "team_rank_within_roster",
            "team_points_share",
        ]
    ].rename(
        columns={
            "season": "next_season",
            "team_name": "next_team_name",
            "team_slug": "next_team_slug",
            "team_base_slug": "next_team_base_slug",
            "team_class": "next_team_class",
            "uci_points": "next_uci_points",
            "racedays": "next_racedays",
            "points_per_raceday": "next_points_per_raceday",
            "team_rank_within_roster": "next_team_rank_within_roster",
            "team_points_share": "next_team_points_share",
        }
    ).copy()
    return next_map


def _prepare_rider_training_frame(
    rider_panel: pd.DataFrame,
    feature_columns: Sequence[str],
    target_column: str,
) -> pd.DataFrame:
    required_columns = list(feature_columns) + [target_column, "next_season"]
    missing_columns = [column for column in required_columns if column not in rider_panel.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns for rider-threshold model: {missing_columns}")

    prepared = rider_panel.copy()
    prepared.loc[:, feature_columns] = (
        prepared.loc[:, feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    )
    prepared[target_column] = pd.to_numeric(prepared[target_column], errors="coerce")
    prepared["next_season"] = pd.to_numeric(prepared["next_season"], errors="coerce")
    prepared = prepared.dropna(subset=[target_column, "next_season"]).reset_index(drop=True)
    if prepared.empty:
        raise ValueError("No observed rider-threshold rows remained after preparing the training frame.")

    target_values = prepared[target_column].astype(int)
    if target_values.nunique() < 2:
        raise ValueError("Rider-threshold baseline requires both positive and negative target rows.")
    prepared[target_column] = target_values
    prepared["next_season"] = prepared["next_season"].astype("Int64")
    return prepared


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
