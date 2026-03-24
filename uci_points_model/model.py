from __future__ import annotations

from typing import Mapping

import pandas as pd

from .data import OPTIONAL_STAGE_COLUMNS

TARGET_HISTORY_KEY = "target_history_id"

DEFAULT_WEIGHTS: dict[str, float] = {
    "top10_points": 0.270428382182834,
    "winner_points": 0.11386531630100413,
    "field_softness": 0.10517435889360816,
    "depth_softness": 0.3073988715769149,
    "finish_rate": 0.20313307104563885,
}

COMPONENT_COLUMNS: dict[str, str] = {
    "top10_points": "top10_points_pct",
    "winner_points": "winner_points_pct",
    "field_softness": "field_softness_pct",
    "depth_softness": "depth_softness_pct",
    "finish_rate": "finish_rate_pct",
}


def annotate_target_history(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        annotated = dataset.copy()
        annotated[TARGET_HISTORY_KEY] = pd.Series(dtype=str)
        annotated["category_history"] = pd.Series(dtype=str)
        annotated["category_change_count"] = pd.Series(dtype=int)
        annotated["latest_known_category"] = pd.Series(dtype=str)
        return annotated

    annotated = dataset.copy()
    if "month" not in annotated.columns:
        annotated["month"] = 0
    if "category" not in annotated.columns:
        annotated["category"] = "Unknown"
    annotated = annotated.sort_values(["race_id", "year", "month", "category"]).reset_index(drop=True)
    annotated[TARGET_HISTORY_KEY] = (
        annotated["race_id"].astype(str) + "::" + annotated["category"].astype(str)
    )

    category_groups = annotated.groupby("race_id", sort=False)["category"]
    annotated["category_history"] = category_groups.transform(_category_history_string)
    annotated["category_change_count"] = (
        category_groups.transform(_category_change_count).fillna(0).astype(int)
    )
    annotated["latest_known_category"] = category_groups.transform("last")
    return annotated


def add_score_component_percentiles(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return dataset.copy()

    component_frame = dataset.copy()
    component_frame["top10_points_pct"] = _percentile_score(component_frame["top10_points"])
    component_frame["winner_points_pct"] = _percentile_score(component_frame["winner_points"])
    component_frame["field_softness_pct"] = _percentile_score(
        component_frame["avg_top10_field_form"], reverse=True
    )
    component_frame["depth_softness_pct"] = _percentile_score(
        component_frame["total_field_form"], reverse=True
    )
    component_frame["finish_rate_pct"] = _percentile_score(component_frame["finish_rate"])
    return component_frame


def normalize_weights(weights: Mapping[str, float] | None = None) -> dict[str, float]:
    active_weights = dict(DEFAULT_WEIGHTS)
    if weights is not None:
        active_weights.update(weights)

    normalized = {name: max(float(value), 0.0) for name, value in active_weights.items()}
    denominator = sum(normalized.values())
    if denominator <= 0:
        return {name: 1.0 / len(normalized) for name in normalized}
    return {name: value / denominator for name, value in normalized.items()}


def calculate_arbitrage_score(
    dataset: pd.DataFrame, weights: Mapping[str, float] | None = None
) -> pd.Series:
    active_weights = normalize_weights(weights)
    scored = pd.Series(0.0, index=dataset.index, dtype=float)
    for weight_name, component_column in COMPONENT_COLUMNS.items():
        scored = scored + dataset[component_column] * active_weights[weight_name]
    return scored


def score_race_editions(
    dataset: pd.DataFrame, weights: Mapping[str, float] | None = None
) -> pd.DataFrame:
    if dataset.empty:
        return dataset.copy()

    edition_scores = annotate_target_history(dataset)
    edition_scores = add_score_component_percentiles(edition_scores)
    edition_scores["arbitrage_score"] = calculate_arbitrage_score(edition_scores, weights)

    field_form_for_efficiency = (
        edition_scores["top10_field_form"]
        if "top10_field_form" in edition_scores
        else edition_scores["avg_top10_field_form"]
    )
    edition_scores["points_efficiency_index"] = (
        edition_scores["top10_points"] / field_form_for_efficiency.replace(0, pd.NA)
    ).fillna(0)

    return edition_scores.sort_values(
        ["arbitrage_score", "top10_points", "winner_points"], ascending=False
    ).reset_index(drop=True)


def summarize_historical_targets(
    scored_editions: pd.DataFrame, latest_only: bool = True
) -> pd.DataFrame:
    if scored_editions.empty:
        return scored_editions.copy()

    edition_summary = annotate_target_history(scored_editions)
    for column_name, default_value in OPTIONAL_STAGE_COLUMNS.items():
        if column_name not in edition_summary.columns:
            edition_summary[column_name] = default_value

    grouped = (
        edition_summary.sort_values(["year", "month"])
        .groupby(TARGET_HISTORY_KEY, as_index=False)
        .agg(
            race_id=("race_id", "last"),
            race_name=("race_name", "last"),
            race_country=("race_country", "last"),
            category=("category", "last"),
            latest_known_category=("latest_known_category", "last"),
            category_history=("category_history", "last"),
            category_change_count=("category_change_count", "max"),
            race_type=("race_type", "last"),
            years_analyzed=("year", "nunique"),
            years=("year", lambda values: ", ".join(str(value) for value in sorted(set(values)))),
            avg_arbitrage_score=("arbitrage_score", "mean"),
            best_edition_score=("arbitrage_score", "max"),
            avg_top10_points=("top10_points", "mean"),
            avg_winner_points=("winner_points", "mean"),
            avg_total_points=("total_points", "mean"),
            avg_gc_top10_points=("gc_top10_points", "mean"),
            avg_stage_top10_points=("stage_top10_points", "mean"),
            avg_stage_total_points=("stage_total_points", "mean"),
            avg_stage_count=("stage_count", "mean"),
            avg_stage_points_share=("stage_points_share", "mean"),
            avg_top10_field_form=("avg_top10_field_form", "mean"),
            avg_total_field_form=("total_field_form", "mean"),
            avg_finish_rate=("finish_rate", "mean"),
            avg_points_efficiency=("points_efficiency_index", "mean"),
            avg_startlist_size=("startlist_size", "mean"),
        )
    )

    if latest_only:
        grouped = grouped[grouped["category"] == grouped["latest_known_category"]].copy()

    return grouped.sort_values(
        ["avg_arbitrage_score", "avg_top10_points"], ascending=False
    ).reset_index(drop=True)


def _percentile_score(series: pd.Series, reverse: bool = False) -> pd.Series:
    if series.empty:
        return series.copy()
    if series.nunique(dropna=False) <= 1:
        return pd.Series([50.0] * len(series), index=series.index, dtype=float)

    ranked = series.rank(method="average", pct=True) * 100
    return 100 - ranked if reverse else ranked


def _category_history_string(values: pd.Series) -> str:
    ordered_categories = _ordered_unique_strings(values)
    return " -> ".join(ordered_categories)


def _category_change_count(values: pd.Series) -> int:
    ordered_categories = _ordered_unique_strings(values)
    return max(len(ordered_categories) - 1, 0)


def _ordered_unique_strings(values: pd.Series) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen or text == "nan":
            continue
        ordered.append(text)
        seen.add(text)
    return ordered
