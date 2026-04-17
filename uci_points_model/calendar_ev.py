from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .proteam_risk import load_proteam_risk_snapshot
from .team_calendar import TEAM_CALENDAR_COLUMNS
from .team_calendar import derive_calendar_status
from .team_calendar_client import (
    ProCyclingStatsTeamCalendarClient,
    build_team_in_race_points_url,
)

RACE_EDITIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "race_editions_snapshot.csv"

ACTUAL_POINTS_COLUMNS = [
    "team_slug",
    "team_name",
    "planning_year",
    "race_id",
    "race_name",
    "category",
    "date_label",
    "status",
    "actual_points",
    "rider_count",
    "source_url",
    "pcs_race_slug",
    "checked_at_utc",
    "notes",
]

DEFAULT_EV_WEIGHTS = {
    "avg_points_efficiency": 0.50,
    "avg_top10_points": 0.15,
    "avg_winner_points": 0.10,
    "avg_stage_top10_points": 0.10,
    "field_softness_score": 0.15,
}

DEFAULT_EXECUTION_RULES = {
    "1.1": 0.40,
    "1.Pro": 0.30,
    "1.UWT": 0.18,
    "2.1": 0.30,
    "2.Pro": 0.25,
    "2.UWT": 0.18,
}

CATEGORY_HISTORY_FALLBACKS = {
    "1.UWT": "1.Pro",
    "2.UWT": "2.Pro",
}


def _minmax_scale(series: pd.Series, invert: bool = False) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        return pd.Series([0.0] * len(series), index=series.index, dtype="Float64")
    lower = float(numeric.min())
    upper = float(numeric.max())
    if lower == upper:
        scaled = pd.Series([1.0 if pd.notna(value) else 0.0 for value in numeric], index=series.index, dtype="Float64")
    else:
        scaled = ((numeric - lower) / (upper - lower)).astype("Float64")
    if invert:
        scaled = 1 - scaled
    return scaled.fillna(0.0).astype("Float64")


def load_team_profile(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def build_historical_target_summary(
    snapshot_path: str | Path | None = None,
    planning_year: int = 2026,
    ev_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    weights = ev_weights or DEFAULT_EV_WEIGHTS
    path = Path(snapshot_path) if snapshot_path else RACE_EDITIONS_PATH
    snapshot_df = pd.read_csv(path, low_memory=False)
    historical_df = snapshot_df.loc[snapshot_df["year"].astype("Int64") < int(planning_year)].copy()
    historical_df["race_id"] = pd.to_numeric(historical_df["race_id"], errors="coerce").astype("Int64")

    summary_df = (
        historical_df.groupby(["race_id", "race_name"], dropna=False, as_index=False)
        .agg(
            historical_years_analyzed=("year", "nunique"),
            latest_category=("category", "last"),
            race_type=("race_type", "last"),
            avg_top10_points=("top10_points", "mean"),
            avg_winner_points=("winner_points", "mean"),
            avg_points_efficiency=("points_per_top10_form", "mean"),
            avg_stage_top10_points=("stage_top10_points", "mean"),
            avg_stage_count=("stage_count", "mean"),
            avg_top10_field_form=("avg_top10_field_form", "mean"),
        )
        .reset_index(drop=True)
    )

    for column in [
        "avg_top10_points",
        "avg_winner_points",
        "avg_points_efficiency",
        "avg_stage_top10_points",
        "avg_stage_count",
        "avg_top10_field_form",
    ]:
        summary_df[column] = pd.to_numeric(summary_df[column], errors="coerce")

    summary_df["field_softness_score"] = _minmax_scale(summary_df["avg_top10_field_form"], invert=True)
    summary_df["stage_points_score"] = _minmax_scale(summary_df["avg_stage_top10_points"])
    summary_df["stage_count_score"] = _minmax_scale(summary_df["avg_stage_count"])
    summary_df["one_day_signal"] = summary_df["race_type"].fillna("").map(
        lambda value: 0.15 if value != "One-day" else pd.NA
    ).astype("Float64")
    summary_df.loc[summary_df["race_type"].fillna("") == "One-day", "one_day_signal"] = (
        0.35 + 0.65 * summary_df.loc[summary_df["race_type"].fillna("") == "One-day", "field_softness_score"]
    ).astype("Float64")
    summary_df["one_day_signal"] = summary_df["one_day_signal"].fillna(0.15).astype("Float64")
    summary_df["stage_race_signal"] = (1 - (summary_df["race_type"].fillna("") == "One-day").astype("Float64")).astype(
        "Float64"
    )
    summary_df["gc_signal"] = (
        summary_df["stage_race_signal"]
        * (
            0.50 * _minmax_scale(summary_df["avg_winner_points"])
            + 0.30 * summary_df["stage_count_score"]
            + 0.20 * (1 - summary_df["field_softness_score"])
        )
    ).clip(0, 1)
    summary_df["stage_hunter_signal"] = (
        summary_df["stage_race_signal"] * (0.65 * summary_df["stage_points_score"] + 0.35 * summary_df["stage_count_score"])
    ).clip(0, 1)
    summary_df["all_round_signal"] = (
        0.50 * summary_df["stage_race_signal"]
        + 0.50 * (1 - (summary_df["field_softness_score"] - 0.50).abs() * 2).clip(lower=0, upper=1)
    ).clip(0, 1)
    summary_df["time_trial_signal"] = summary_df["race_name"].map(
        lambda value: float(any(token in str(value).casefold() for token in ["itt", " tt", "chrono", "prologue"]))
    )
    summary_df["sprint_bonus_signal"] = (
        0.75 * summary_df["field_softness_score"] + 0.25 * summary_df["stage_points_score"]
    ).clip(0, 1)

    component_scales = {
        "avg_points_efficiency": _minmax_scale(summary_df["avg_points_efficiency"]),
        "avg_top10_points": _minmax_scale(summary_df["avg_top10_points"]),
        "avg_winner_points": _minmax_scale(summary_df["avg_winner_points"]),
        "avg_stage_top10_points": _minmax_scale(summary_df["avg_stage_top10_points"]),
        "field_softness_score": summary_df["field_softness_score"],
    }
    summary_df["base_opportunity_index"] = sum(
        weight * component_scales[column_name] for column_name, weight in weights.items()
    ).clip(0, 1)
    summary_df["base_opportunity_points"] = (
        summary_df["base_opportunity_index"] * summary_df["avg_top10_points"].fillna(0.0)
    ).astype("Float64")
    summary_df["route_profile"] = summary_df.apply(_route_profile_label, axis=1)
    return summary_df


def build_actual_points_table(
    team_slug: str,
    planning_year: int,
    team_calendar: pd.DataFrame,
    client: ProCyclingStatsTeamCalendarClient | None = None,
    checked_at_utc: str | None = None,
    max_workers: int = 8,
    as_of_date: str | date | None = None,
) -> pd.DataFrame:
    if team_calendar.empty:
        return pd.DataFrame(columns=ACTUAL_POINTS_COLUMNS)

    calendar_df = team_calendar.copy()
    if "status" not in calendar_df.columns:
        calendar_df["status"] = calendar_df["end_date"].map(lambda value: derive_calendar_status(value, as_of_date))
    checked_at = checked_at_utc or datetime.now(timezone.utc).isoformat()
    comparison_date = _resolve_as_of_date(as_of_date)

    rows: list[dict[str, object]] = []
    if client is not None or len(calendar_df) <= 1 or max_workers <= 1:
        pcs_client = client or ProCyclingStatsTeamCalendarClient()
        rows = [
            _build_actual_points_row(
                row._asdict(),
                team_slug=team_slug,
                planning_year=planning_year,
                checked_at_utc=checked_at,
                comparison_date=comparison_date,
                client=pcs_client,
            )
            for row in calendar_df.itertuples(index=False)
        ]
    else:
        worker_count = min(max_workers, len(calendar_df))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            future_map = {
                pool.submit(
                    _build_actual_points_row,
                    row._asdict(),
                    team_slug=team_slug,
                    planning_year=planning_year,
                    checked_at_utc=checked_at,
                    comparison_date=comparison_date,
                    client=None,
                ): row
                for row in calendar_df.itertuples(index=False)
            }
            for future in as_completed(future_map):
                rows.append(future.result())

    actual_points_df = pd.DataFrame(rows, columns=ACTUAL_POINTS_COLUMNS)
    actual_points_df["race_id"] = pd.to_numeric(actual_points_df["race_id"], errors="coerce").astype("Int64")
    actual_points_df["actual_points"] = pd.to_numeric(actual_points_df["actual_points"], errors="coerce").astype("Float64")
    actual_points_df["rider_count"] = pd.to_numeric(actual_points_df["rider_count"], errors="coerce").astype("Int64")
    return actual_points_df.sort_values(["race_id"]).reset_index(drop=True)


def attach_actual_points(calendar_ev_df: pd.DataFrame, actual_points_df: pd.DataFrame) -> pd.DataFrame:
    if actual_points_df.empty:
        result_df = calendar_ev_df.copy()
        result_df["actual_points"] = pd.Series([pd.NA] * len(result_df), dtype="Float64")
        result_df["ev_gap"] = pd.Series([pd.NA] * len(result_df), dtype="Float64")
        return result_df

    merged_df = calendar_ev_df.merge(
        actual_points_df[["race_id", "actual_points"]],
        on="race_id",
        how="left",
    )
    merged_df["actual_points"] = pd.to_numeric(merged_df["actual_points"], errors="coerce").astype("Float64")
    merged_df["ev_gap"] = (merged_df["actual_points"] - merged_df["expected_points"]).astype("Float64")
    return merged_df


def build_team_calendar_ev(
    team_slug: str,
    planning_year: int,
    historical_summary: pd.DataFrame,
    team_calendar: pd.DataFrame,
    team_profile: dict,
    actual_points_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if team_calendar.empty:
        return pd.DataFrame()

    merged_df = team_calendar.merge(
        historical_summary,
        on="race_id",
        how="left",
        suffixes=("", "_history"),
    )
    merged_df["planning_year"] = int(planning_year)
    merged_df["team_slug"] = team_slug
    if "race_name_history" in merged_df.columns:
        merged_df["race_name"] = merged_df["race_name"].combine_first(merged_df["race_name_history"])
        merged_df = merged_df.drop(columns=["race_name_history"])
    if "category_history" in merged_df.columns:
        merged_df = merged_df.drop(columns=["category_history"])

    for column in [
        "historical_years_analyzed",
        "avg_top10_points",
        "avg_winner_points",
        "avg_points_efficiency",
        "avg_stage_top10_points",
        "avg_stage_count",
        "avg_top10_field_form",
        "base_opportunity_index",
        "base_opportunity_points",
        "one_day_signal",
        "stage_hunter_signal",
        "gc_signal",
        "time_trial_signal",
        "all_round_signal",
        "sprint_bonus_signal",
        "field_softness_score",
    ]:
        merged_df[column] = pd.to_numeric(merged_df[column], errors="coerce")

    merged_df["notes"] = merged_df["notes"].fillna("")
    missing_history_mask = merged_df["historical_years_analyzed"].isna()
    merged_df = _apply_category_history_fallbacks(merged_df, historical_summary, missing_history_mask)
    merged_df.loc[missing_history_mask, "notes"] = (
        merged_df.loc[missing_history_mask, "notes"].str.strip(" |") + " | history_missing"
    ).str.strip(" |")
    merged_df = _build_team_fit_components(merged_df, team_profile)
    merged_df["participation_confidence"] = _derive_participation_confidence(merged_df, team_profile)
    merged_df["execution_multiplier"] = merged_df["category"].map(
        lambda value: _execution_multiplier_for_category(str(value), team_profile)
    )
    merged_df["expected_points"] = (
        merged_df["base_opportunity_points"].fillna(0.0)
        * merged_df["team_fit_multiplier"].fillna(1.0)
        * merged_df["participation_confidence"].fillna(0.0)
        * merged_df["execution_multiplier"].fillna(0.0)
    ).astype("Float64")

    result_df = attach_actual_points(merged_df, actual_points_df if actual_points_df is not None else pd.DataFrame())
    ordered_columns = [
        "team_slug",
        "team_name",
        "planning_year",
        "race_id",
        "race_name",
        "category",
        "date_label",
        "month",
        "start_date",
        "end_date",
        "pcs_race_slug",
        "historical_years_analyzed",
        "race_type",
        "route_profile",
        "avg_top10_points",
        "avg_winner_points",
        "avg_points_efficiency",
        "avg_stage_top10_points",
        "avg_stage_count",
        "avg_top10_field_form",
        "base_opportunity_index",
        "base_opportunity_points",
        "specialty_fit_score",
        "sprint_fit_bonus",
        "team_fit_score",
        "team_fit_multiplier",
        "participation_confidence",
        "execution_multiplier",
        "expected_points",
        "actual_points",
        "ev_gap",
        "status",
        "team_calendar_status",
        "source",
        "overlap_group",
        "notes",
    ]
    missing_columns = [column for column in ordered_columns if column not in result_df.columns]
    for column in missing_columns:
        result_df[column] = pd.NA
    return result_df[ordered_columns].sort_values(["start_date", "race_name"]).reset_index(drop=True)


def summarize_team_calendar_ev(calendar_ev_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if calendar_ev_df.empty:
        empty_df = pd.DataFrame()
        return {"overview": empty_df, "by_month": empty_df, "by_category": empty_df}

    overview_df = pd.DataFrame(
        [
            {
                "team_slug": calendar_ev_df["team_slug"].iloc[0],
                "planning_year": int(calendar_ev_df["planning_year"].iloc[0]),
                "race_count": len(calendar_ev_df),
                "completed_race_count": int((calendar_ev_df["status"] == "completed").sum()),
                "scheduled_race_count": int((calendar_ev_df["status"] == "scheduled").sum()),
                "total_expected_points": float(calendar_ev_df["expected_points"].fillna(0.0).sum()),
                "completed_expected_points": float(
                    calendar_ev_df.loc[calendar_ev_df["status"] == "completed", "expected_points"].fillna(0.0).sum()
                ),
                "remaining_expected_points": float(
                    calendar_ev_df.loc[calendar_ev_df["status"] != "completed", "expected_points"].fillna(0.0).sum()
                ),
                "actual_points_known": float(calendar_ev_df["actual_points"].fillna(0.0).sum()),
                "ev_gap_known": float(calendar_ev_df["ev_gap"].fillna(0.0).sum()),
            }
        ]
    )

    by_month_df = (
        calendar_ev_df.groupby("month", dropna=False, as_index=False)
        .agg(
            race_count=("race_id", "count"),
            expected_points=("expected_points", "sum"),
            actual_points=("actual_points", "sum"),
            ev_gap=("ev_gap", "sum"),
        )
        .sort_values(["month"])
        .reset_index(drop=True)
    )

    by_category_df = (
        calendar_ev_df.groupby("category", dropna=False, as_index=False)
        .agg(
            race_count=("race_id", "count"),
            expected_points=("expected_points", "sum"),
            actual_points=("actual_points", "sum"),
            ev_gap=("ev_gap", "sum"),
        )
        .sort_values(["category"])
        .reset_index(drop=True)
    )

    return {"overview": overview_df, "by_month": by_month_df, "by_category": by_category_df}


def load_team_reference_total(team_slug: str) -> float | None:
    snapshot_df = load_proteam_risk_snapshot(scope="current")
    if snapshot_df.empty:
        return None
    matches = snapshot_df.loc[snapshot_df["team_slug"] == team_slug]
    if matches.empty:
        return None
    total_points = pd.to_numeric(matches["team_total_points"], errors="coerce").iloc[0]
    return None if pd.isna(total_points) else float(total_points)


def _build_actual_points_row(
    row: dict[str, object],
    team_slug: str,
    planning_year: int,
    checked_at_utc: str,
    comparison_date: date,
    client: ProCyclingStatsTeamCalendarClient | None,
) -> dict[str, object]:
    pcs_client = client or ProCyclingStatsTeamCalendarClient()
    race_slug = str(row.get("pcs_race_slug") or "").strip()
    status = str(row.get("status") or derive_calendar_status(row.get("end_date"), comparison_date))
    team_name = str(row.get("team_name") or "")
    source_url = build_team_in_race_points_url(team_slug, race_slug) if race_slug else ""
    actual_points: float | None
    rider_count = pd.NA
    notes = ""

    if race_slug:
        try:
            race_points = pcs_client.get_team_race_points(team_slug, race_slug)
            source_url = race_points.source_url
            if race_points.has_rows:
                actual_points = float(race_points.actual_points)
                rider_count = race_points.rider_count
            elif status == "completed":
                actual_points = 0.0
                rider_count = 0
                notes = "points_page_empty_after_race"
            else:
                actual_points = None
                rider_count = 0
        except Exception as exc:  # noqa: BLE001
            if status == "completed":
                actual_points = 0.0
                rider_count = 0
            else:
                actual_points = None
                rider_count = 0
            notes = f"points_page_error={type(exc).__name__}"
    else:
        actual_points = 0.0 if status == "completed" else None
        notes = "missing_race_slug" if status == "completed" else ""

    return {
        "team_slug": team_slug,
        "team_name": team_name,
        "planning_year": int(planning_year),
        "race_id": row.get("race_id"),
        "race_name": row.get("race_name"),
        "category": row.get("category"),
        "date_label": row.get("date_label"),
        "status": status,
        "actual_points": actual_points,
        "rider_count": rider_count,
        "source_url": source_url,
        "pcs_race_slug": race_slug,
        "checked_at_utc": checked_at_utc,
        "notes": notes,
    }


def _build_team_fit_components(merged_df: pd.DataFrame, team_profile: dict) -> pd.DataFrame:
    weights = team_profile.get("strength_weights", {})
    non_sprint_keys = ["one_day", "stage_hunter", "gc", "time_trial", "all_round"]
    non_sprint_weight_total = sum(float(weights.get(key, 0.0)) for key in non_sprint_keys) or 1.0
    specialty_fit_score = sum(
        float(weights.get(key, 0.0)) * pd.to_numeric(merged_df[f"{key}_signal"], errors="coerce").fillna(0.0)
        for key in non_sprint_keys
    ) / non_sprint_weight_total

    total_weight = sum(float(value) for value in weights.values()) or 1.0
    sprint_weight_share = float(weights.get("sprint_bonus", 0.0)) / total_weight
    sprint_fit_bonus = sprint_weight_share * pd.to_numeric(merged_df["sprint_bonus_signal"], errors="coerce").fillna(0.0)
    merged_df["specialty_fit_score"] = specialty_fit_score.clip(0, 1).astype("Float64")
    merged_df["sprint_fit_bonus"] = sprint_fit_bonus.clip(0, 1).astype("Float64")
    merged_df["team_fit_score"] = (
        (1 - sprint_weight_share) * merged_df["specialty_fit_score"] + merged_df["sprint_fit_bonus"]
    ).clip(0, 1)
    merged_df["team_fit_multiplier"] = (
        float(team_profile.get("team_fit_floor", 0.70))
        + float(team_profile.get("team_fit_range", 0.30)) * merged_df["team_fit_score"]
    ).clip(lower=0, upper=1)
    return merged_df


def _derive_participation_confidence(calendar_ev_df: pd.DataFrame, team_profile: dict) -> pd.Series:
    rules = team_profile.get("participation_rules", {})
    overlap_penalty = float(rules.get("overlap_penalty", 0.80))
    completed_confidence = float(rules.get("completed", 1.00))
    observed_startlist_confidence = float(rules.get("observed_startlist", 0.95))
    program_confidence = float(rules.get("program_confirmed", 0.95))
    seed_confidence = float(rules.get("calendar_seed", 0.70))

    confidence_values: list[float] = []
    for row in calendar_ev_df.itertuples(index=False):
        if getattr(row, "status", "") == "completed":
            confidence = completed_confidence
        elif "startlist" in str(getattr(row, "source", "")):
            confidence = observed_startlist_confidence
        elif "program" in str(getattr(row, "source", "")):
            confidence = program_confidence
        else:
            confidence = seed_confidence
        if getattr(row, "overlap_group", ""):
            confidence = min(confidence, overlap_penalty)
        confidence_values.append(confidence)
    return pd.Series(confidence_values, index=calendar_ev_df.index, dtype="Float64")


def _execution_multiplier_for_category(category: str, team_profile: dict) -> float:
    rules = team_profile.get("execution_rules", DEFAULT_EXECUTION_RULES)
    return float(rules.get(category, 0.25))


def _route_profile_label(row: pd.Series) -> str:
    if str(row.get("race_type", "")) == "One-day":
        return "sprint-friendly one-day" if float(row.get("field_softness_score", 0.0)) >= 0.5 else "hard one-day"
    if float(row.get("avg_stage_count", 0.0) or 0.0) >= 5:
        return "multi-stage race"
    return "short stage race"


def _resolve_as_of_date(as_of_date: str | date | None) -> date:
    if isinstance(as_of_date, date):
        return as_of_date
    if isinstance(as_of_date, str) and as_of_date.strip():
        return pd.Timestamp(as_of_date).date()
    return datetime.now(timezone.utc).date()


def _apply_category_history_fallbacks(
    merged_df: pd.DataFrame,
    historical_summary: pd.DataFrame,
    missing_history_mask: pd.Series,
) -> pd.DataFrame:
    if not missing_history_mask.any():
        return merged_df

    baseline_df = _build_category_history_baselines(historical_summary)
    if baseline_df.empty:
        return merged_df

    fill_columns = [
        "race_type",
        "route_profile",
        "avg_top10_points",
        "avg_winner_points",
        "avg_points_efficiency",
        "avg_stage_top10_points",
        "avg_stage_count",
        "avg_top10_field_form",
        "base_opportunity_index",
        "base_opportunity_points",
        "one_day_signal",
        "stage_hunter_signal",
        "gc_signal",
        "time_trial_signal",
        "all_round_signal",
        "sprint_bonus_signal",
        "field_softness_score",
    ]

    for index in merged_df.index[missing_history_mask]:
        category = str(merged_df.at[index, "category"] or "")
        fallback_category = CATEGORY_HISTORY_FALLBACKS.get(category, category)
        fallback_race_type = "One-day" if category.startswith("1.") else "Stage race"
        baseline_match = baseline_df.loc[
            (baseline_df["latest_category"] == fallback_category) & (baseline_df["race_type"] == fallback_race_type)
        ]
        if baseline_match.empty:
            continue
        baseline_row = baseline_match.iloc[0]
        for column in fill_columns:
            if pd.isna(merged_df.at[index, column]):
                merged_df.at[index, column] = baseline_row[column]
        merged_df.at[index, "notes"] = (
            str(merged_df.at[index, "notes"]).strip(" |")
            + f" | history_fallback_from={fallback_category}"
        ).strip(" |")

    return merged_df


def _build_category_history_baselines(historical_summary: pd.DataFrame) -> pd.DataFrame:
    if historical_summary.empty:
        return pd.DataFrame()

    numeric_columns = [
        "avg_top10_points",
        "avg_winner_points",
        "avg_points_efficiency",
        "avg_stage_top10_points",
        "avg_stage_count",
        "avg_top10_field_form",
        "base_opportunity_index",
        "base_opportunity_points",
        "one_day_signal",
        "stage_hunter_signal",
        "gc_signal",
        "time_trial_signal",
        "all_round_signal",
        "sprint_bonus_signal",
        "field_softness_score",
    ]
    aggregation = {column: "mean" for column in numeric_columns}
    aggregation["route_profile"] = lambda values: _first_non_empty(values.tolist())

    baseline_df = (
        historical_summary.groupby(["latest_category", "race_type"], dropna=False, as_index=False)
        .agg(aggregation)
        .reset_index(drop=True)
    )
    return baseline_df


def _first_non_empty(values: list[object]) -> str:
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
