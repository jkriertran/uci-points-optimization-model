from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from .model import (
    COMPONENT_COLUMNS,
    DEFAULT_WEIGHTS,
    add_score_component_percentiles,
    annotate_target_history,
    normalize_weights,
    TARGET_HISTORY_KEY,
)

OBJECTIVE_WEIGHTS = {
    "spearman": 0.60,
    "precision": 0.20,
    "value_capture": 0.20,
}


@dataclass(frozen=True, slots=True)
class FoldDefinition:
    test_year: int
    train_years: tuple[int, ...]
    prediction_frame: pd.DataFrame
    outcome_frame: pd.DataFrame


def calibrate_weights(
    dataset: pd.DataFrame,
    race_type: str = "One-day",
    search_iterations: int = 600,
    random_seed: int = 7,
    min_train_years: int = 2,
    min_fold_size: int = 8,
    candidate_weights: Sequence[Mapping[str, float]] | None = None,
) -> dict[str, object]:
    filtered = _prepare_calibration_dataset(dataset, race_type)
    folds = _build_walk_forward_folds(
        filtered, min_train_years=min_train_years, min_fold_size=min_fold_size
    )

    if not folds:
        return {
            "eligible": False,
            "message": (
                "Not enough repeated race history for walk-forward calibration. "
                "Use at least three years with repeated race editions."
            ),
            "filtered_rows": len(filtered),
            "race_type": race_type,
        }

    candidates = list(candidate_weights) if candidate_weights is not None else _generate_weight_candidates(
        search_iterations=search_iterations, random_seed=random_seed
    )

    evaluations = []
    seen_signatures: set[tuple[float, ...]] = set()
    for candidate in candidates:
        normalized = normalize_weights(candidate)
        signature = tuple(round(normalized[name], 6) for name in DEFAULT_WEIGHTS)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        evaluations.append(_evaluate_candidate(normalized, folds))

    leaderboard = _evaluations_to_frame(evaluations)
    best = max(evaluations, key=lambda item: item["objective"])
    default_eval = _evaluate_candidate(normalize_weights(DEFAULT_WEIGHTS), folds)

    return {
        "eligible": True,
        "race_type": race_type,
        "filtered_rows": len(filtered),
        "fold_count": len(folds),
        "fold_years": [fold.test_year for fold in folds],
        "default": default_eval,
        "best": best,
        "leaderboard": leaderboard.head(20).reset_index(drop=True),
        "best_fold_details": best["fold_details"],
        "default_fold_details": default_eval["fold_details"],
        "improvement": best["objective"] - default_eval["objective"],
    }


def _prepare_calibration_dataset(dataset: pd.DataFrame, race_type: str) -> pd.DataFrame:
    filtered = annotate_target_history(dataset)
    if race_type != "All":
        filtered = filtered[filtered["race_type"] == race_type]
    repeated_ids = (
        filtered.groupby(TARGET_HISTORY_KEY)["year"].nunique().loc[lambda counts: counts >= 2].index
    )
    filtered = filtered[filtered[TARGET_HISTORY_KEY].isin(repeated_ids)].copy()
    filtered = filtered.sort_values(["year", "month", "race_name"]).reset_index(drop=True)
    return filtered


def _build_walk_forward_folds(
    dataset: pd.DataFrame, min_train_years: int, min_fold_size: int
) -> list[FoldDefinition]:
    if dataset.empty:
        return []

    years = sorted(dataset["year"].unique().tolist())
    folds: list[FoldDefinition] = []

    for test_year in years:
        train = dataset[dataset["year"] < test_year].copy()
        test = dataset[dataset["year"] == test_year].copy()
        if train["year"].nunique() < min_train_years or test.empty:
            continue

        train_components = add_score_component_percentiles(train)
        prediction_frame = (
            train_components.groupby(TARGET_HISTORY_KEY, as_index=False)
            .agg(
                race_id=("race_id", "last"),
                race_name=("race_name", "last"),
                category=("category", "last"),
                category_history=("category_history", "last"),
                category_change_count=("category_change_count", "max"),
                latest_known_category=("latest_known_category", "last"),
                race_type=("race_type", "last"),
                race_country=("race_country", "last"),
                train_editions=("year", "count"),
                train_years=("year", lambda values: ", ".join(str(v) for v in sorted(set(values)))),
                top10_points_pct=("top10_points_pct", "mean"),
                winner_points_pct=("winner_points_pct", "mean"),
                field_softness_pct=("field_softness_pct", "mean"),
                depth_softness_pct=("depth_softness_pct", "mean"),
                finish_rate_pct=("finish_rate_pct", "mean"),
            )
        )

        outcome_frame = (
            test.groupby(TARGET_HISTORY_KEY, as_index=False)
            .agg(
                actual_points_efficiency=("points_per_top10_form", "mean"),
                actual_total_efficiency=("points_per_total_form", "mean"),
                actual_top10_points=("top10_points", "mean"),
                actual_winner_points=("winner_points", "mean"),
                actual_top10_field_form=("avg_top10_field_form", "mean"),
                actual_total_field_form=("total_field_form", "mean"),
                actual_finish_rate=("finish_rate", "mean"),
            )
        )

        merged = prediction_frame.merge(outcome_frame, on=TARGET_HISTORY_KEY, how="inner")
        if len(merged) < min_fold_size:
            continue

        folds.append(
            FoldDefinition(
                test_year=int(test_year),
                train_years=tuple(sorted(train["year"].unique().tolist())),
                prediction_frame=prediction_frame,
                outcome_frame=merged,
            )
        )

    return folds


def _evaluate_candidate(weights: Mapping[str, float], folds: Sequence[FoldDefinition]) -> dict[str, object]:
    fold_records: list[dict[str, float | int]] = []
    fold_detail_frames: list[pd.DataFrame] = []

    for fold in folds:
        merged = fold.outcome_frame.copy()
        merged["predicted_score"] = _apply_weights(merged, weights)
        merged = merged.sort_values("predicted_score", ascending=False).reset_index(drop=True)
        merged["predicted_rank"] = merged["predicted_score"].rank(ascending=False, method="min")
        merged["actual_rank"] = merged["actual_points_efficiency"].rank(ascending=False, method="min")

        fold_size = len(merged)
        top_k = max(3, math.ceil(fold_size * 0.20))
        spearman = merged["predicted_score"].corr(merged["actual_points_efficiency"], method="spearman")
        spearman = float(0.0 if pd.isna(spearman) else spearman)

        predicted_top = merged.nlargest(top_k, "predicted_score")
        actual_top = merged.nlargest(top_k, "actual_points_efficiency")
        precision = float(
            len(set(predicted_top[TARGET_HISTORY_KEY]) & set(actual_top[TARGET_HISTORY_KEY])) / top_k
        )

        actual_top_efficiency = actual_top["actual_points_efficiency"].sum()
        value_capture = float(
            predicted_top["actual_points_efficiency"].sum() / actual_top_efficiency
        ) if actual_top_efficiency else 0.0

        objective = (
            OBJECTIVE_WEIGHTS["spearman"] * ((spearman + 1.0) / 2.0)
            + OBJECTIVE_WEIGHTS["precision"] * precision
            + OBJECTIVE_WEIGHTS["value_capture"] * value_capture
        )

        fold_records.append(
            {
                "test_year": fold.test_year,
                "races_compared": fold_size,
                "top_k": top_k,
                "spearman": spearman,
                "top_k_precision": precision,
                "top_k_value_capture": value_capture,
                "objective": objective,
            }
        )

        fold_detail = merged[
            [
                TARGET_HISTORY_KEY,
                "race_id",
                "race_name",
                "category",
                "category_history",
                "latest_known_category",
                "category_change_count",
                "race_country",
                "train_editions",
                "train_years",
                "predicted_score",
                "actual_points_efficiency",
                "actual_top10_points",
                "actual_top10_field_form",
                "predicted_rank",
                "actual_rank",
            ]
        ].copy()
        fold_detail.insert(0, "test_year", fold.test_year)
        fold_detail_frames.append(fold_detail)

    fold_table = pd.DataFrame(fold_records)
    weight_by = fold_table["races_compared"] if not fold_table.empty else pd.Series(dtype=float)

    return {
        "weights": dict(weights),
        "objective": _weighted_mean(fold_table.get("objective", pd.Series(dtype=float)), weight_by),
        "spearman": _weighted_mean(fold_table.get("spearman", pd.Series(dtype=float)), weight_by),
        "top_k_precision": _weighted_mean(
            fold_table.get("top_k_precision", pd.Series(dtype=float)), weight_by
        ),
        "top_k_value_capture": _weighted_mean(
            fold_table.get("top_k_value_capture", pd.Series(dtype=float)), weight_by
        ),
        "folds": fold_table,
        "fold_details": pd.concat(fold_detail_frames, ignore_index=True)
        if fold_detail_frames
        else pd.DataFrame(),
    }


def _apply_weights(frame: pd.DataFrame, weights: Mapping[str, float]) -> pd.Series:
    score = pd.Series(0.0, index=frame.index, dtype=float)
    for weight_name, column_name in COMPONENT_COLUMNS.items():
        score = score + frame[column_name] * weights[weight_name]
    return score


def _weighted_mean(series: pd.Series, weights: pd.Series) -> float:
    if series.empty or weights.empty or weights.sum() == 0:
        return 0.0
    return float((series * weights).sum() / weights.sum())


def _evaluations_to_frame(evaluations: Sequence[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for evaluation in evaluations:
        row = {
            "objective": evaluation["objective"],
            "spearman": evaluation["spearman"],
            "top_k_precision": evaluation["top_k_precision"],
            "top_k_value_capture": evaluation["top_k_value_capture"],
        }
        for name in DEFAULT_WEIGHTS:
            row[name] = evaluation["weights"][name]
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["objective", "spearman", "top_k_value_capture"], ascending=False
    )


def _generate_weight_candidates(search_iterations: int, random_seed: int) -> list[dict[str, float]]:
    rng = np.random.default_rng(random_seed)
    candidates: list[dict[str, float]] = [
        normalize_weights(DEFAULT_WEIGHTS),
        normalize_weights({name: 1.0 for name in DEFAULT_WEIGHTS}),
    ]

    for focus_name in DEFAULT_WEIGHTS:
        focused = {name: 0.05 for name in DEFAULT_WEIGHTS}
        focused[focus_name] = 0.80
        candidates.append(normalize_weights(focused))

    for _ in range(search_iterations):
        draws = rng.dirichlet(np.ones(len(DEFAULT_WEIGHTS)))
        candidates.append({name: float(value) for name, value in zip(DEFAULT_WEIGHTS, draws)})

    return candidates
