from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ALLOCATION_SUMMARY_SUFFIX = "_rider_race_allocation_summary.json"
ALLOCATION_PAIRINGS_SUFFIX = "_rider_race_allocations.csv"
ALLOCATION_RACE_PLAN_SUFFIX = "_rider_race_plan.csv"
ALLOCATION_RIDER_LOAD_SUFFIX = "_rider_load_summary.csv"

RACE_SIGNAL_COLUMNS = (
    "one_day_signal",
    "stage_hunter_signal",
    "gc_signal",
    "time_trial_signal",
    "all_round_signal",
    "sprint_bonus_signal",
)

SPECIALTY_SIGNAL_WEIGHTS: dict[str, dict[str, float]] = {
    "sprint": {
        "stage_hunter_signal": 0.45,
        "sprint_bonus_signal": 0.35,
        "one_day_signal": 0.20,
    },
    "gc": {
        "gc_signal": 0.60,
        "all_round_signal": 0.25,
        "time_trial_signal": 0.15,
    },
    "climber": {
        "gc_signal": 0.55,
        "all_round_signal": 0.35,
        "stage_hunter_signal": 0.10,
    },
    "hills": {
        "one_day_signal": 0.35,
        "all_round_signal": 0.35,
        "gc_signal": 0.20,
        "sprint_bonus_signal": 0.10,
    },
    "oneday": {
        "one_day_signal": 0.55,
        "all_round_signal": 0.25,
        "sprint_bonus_signal": 0.20,
    },
    "tt": {
        "time_trial_signal": 0.70,
        "gc_signal": 0.20,
        "all_round_signal": 0.10,
    },
    "fallback": {
        "all_round_signal": 0.45,
        "one_day_signal": 0.25,
        "stage_hunter_signal": 0.20,
        "gc_signal": 0.10,
    },
}


@dataclass(frozen=True, slots=True)
class RiderRaceAllocationArtifacts:
    summary: dict[str, object]
    allocation_table: pd.DataFrame
    race_plan: pd.DataFrame
    rider_load_summary: pd.DataFrame


def build_rider_race_allocation_artifacts(
    calendar_ev_df: pd.DataFrame,
    rider_scores_df: pd.DataFrame,
    *,
    roster_size: int = 7,
    top_riders_per_race: int = 3,
) -> RiderRaceAllocationArtifacts:
    if calendar_ev_df.empty:
        raise ValueError("Rider-race allocation requires a non-empty Team Calendar EV table.")
    if rider_scores_df.empty:
        raise ValueError("Rider-race allocation requires a non-empty rider-score table.")
    if roster_size <= 0:
        raise ValueError("roster_size must be positive.")
    if top_riders_per_race <= 0:
        raise ValueError("top_riders_per_race must be positive.")

    race_frame = _prepare_race_frame(calendar_ev_df)
    rider_frame = _prepare_rider_frame(rider_scores_df)
    if race_frame.empty:
        raise ValueError("No allocation-ready races remained after filtering the Team Calendar EV table.")
    if rider_frame.empty:
        raise ValueError("No allocation-ready riders remained after filtering the rider-score table.")

    allocation_table = race_frame.merge(rider_frame, how="cross")
    allocation_table["specialty_match_score"] = allocation_table.apply(_specialty_match_score, axis=1)
    allocation_table["allocation_score"] = (
        allocation_table["race_priority_points"]
        * (0.55 * allocation_table["specialty_match_score"] + 0.45 * allocation_table["rider_selection_score"])
    ).round(6)
    allocation_table["allocation_rank"] = (
        allocation_table.groupby("race_key")["allocation_score"]
        .rank(ascending=False, method="first")
        .astype("Int64")
    )
    allocation_table["recommended_start_flag"] = (allocation_table["allocation_rank"] <= int(roster_size)).astype(int)
    allocation_table["race_leader_flag"] = (allocation_table["allocation_rank"] == 1).astype(int)
    allocation_table = allocation_table.sort_values(
        ["start_date", "race_name", "allocation_rank", "rider_name"],
        na_position="last",
    ).reset_index(drop=True)

    race_plan = _build_race_plan(allocation_table, roster_size=roster_size, top_riders_per_race=top_riders_per_race)
    rider_load_summary = _build_rider_load_summary(allocation_table)
    summary = _build_summary(
        allocation_table,
        race_plan=race_plan,
        rider_load_summary=rider_load_summary,
        roster_size=roster_size,
        top_riders_per_race=top_riders_per_race,
    )
    return RiderRaceAllocationArtifacts(
        summary=summary,
        allocation_table=allocation_table,
        race_plan=race_plan,
        rider_load_summary=rider_load_summary,
    )


def write_rider_race_allocation_artifacts(
    artifacts: RiderRaceAllocationArtifacts,
    *,
    output_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_root) if output_root is not None else default_rider_race_allocation_output_root()
    root.mkdir(parents=True, exist_ok=True)

    artifact_stem = rider_race_allocation_artifact_stem(
        str(artifacts.summary.get("team_slug") or "unknown-team"),
        int(artifacts.summary.get("planning_year") or 0),
    )

    summary_path = root / f"{artifact_stem}{ALLOCATION_SUMMARY_SUFFIX}"
    summary_path.write_text(json.dumps(artifacts.summary, indent=2, sort_keys=True) + "\n")

    allocation_path = root / f"{artifact_stem}{ALLOCATION_PAIRINGS_SUFFIX}"
    artifacts.allocation_table.to_csv(allocation_path, index=False)

    race_plan_path = root / f"{artifact_stem}{ALLOCATION_RACE_PLAN_SUFFIX}"
    artifacts.race_plan.to_csv(race_plan_path, index=False)

    rider_load_path = root / f"{artifact_stem}{ALLOCATION_RIDER_LOAD_SUFFIX}"
    artifacts.rider_load_summary.to_csv(rider_load_path, index=False)

    return {
        "summary_path": summary_path,
        "allocation_path": allocation_path,
        "race_plan_path": race_plan_path,
        "rider_load_path": rider_load_path,
    }


def rider_race_allocation_artifact_stem(team_slug: str, planning_year: int) -> str:
    return f"{str(team_slug).replace('-', '_')}_{int(planning_year)}"


def default_rider_race_allocation_output_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "model_outputs" / "rider_race_allocations"


def _prepare_race_frame(calendar_ev_df: pd.DataFrame) -> pd.DataFrame:
    working = calendar_ev_df.copy()
    for column in RACE_SIGNAL_COLUMNS:
        working[column] = pd.to_numeric(
            working.get(column, pd.Series(0.0, index=working.index, dtype=float)),
            errors="coerce",
        ).fillna(0.0)

    working["expected_points"] = pd.to_numeric(
        working.get("expected_points", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    )
    working["base_opportunity_points"] = pd.to_numeric(
        working.get("base_opportunity_points", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    )
    working["race_priority_points"] = (
        working["expected_points"].fillna(working["base_opportunity_points"]).fillna(0.0).clip(lower=0.0)
    )
    working["status"] = working.get("status", pd.Series("", index=working.index)).astype(str)
    working = working.loc[working["status"].str.casefold() != "cancelled"].copy()
    working = working.loc[working["race_priority_points"] > 0].copy()
    if working.empty:
        return working

    working["team_slug"] = working.get("team_slug", pd.Series("", index=working.index)).astype(str)
    working["team_name"] = working.get("team_name", pd.Series("", index=working.index)).astype(str)
    working["planning_year"] = pd.to_numeric(
        working.get("planning_year", pd.Series(pd.NA, index=working.index, dtype="Int64")),
        errors="coerce",
    ).astype("Int64")
    working["race_name"] = working.get("race_name", pd.Series("", index=working.index)).astype(str)
    working["category"] = working.get("category", pd.Series("", index=working.index)).astype(str)
    working["start_date"] = working.get("start_date", pd.Series("", index=working.index)).astype(str)
    working["route_profile"] = working.get("route_profile", pd.Series("", index=working.index)).astype(str)
    race_identifier = working.get("race_id", pd.Series(pd.NA, index=working.index, dtype="Int64"))
    race_identifier = pd.to_numeric(race_identifier, errors="coerce").astype("Int64").astype(str)
    working["race_key"] = race_identifier.where(
        race_identifier != "<NA>",
        working["race_name"] + "|" + working["start_date"],
    )
    return working.reset_index(drop=True)


def _prepare_rider_frame(rider_scores_df: pd.DataFrame) -> pd.DataFrame:
    working = rider_scores_df.copy()
    working["rider_name"] = working.get("rider_name", pd.Series("", index=working.index)).astype(str)
    working = working.loc[working["rider_name"].str.strip() != ""].copy()
    if working.empty:
        return working

    working["predicted_rider_reaches_150_probability"] = pd.to_numeric(
        working.get(
            "predicted_rider_reaches_150_probability",
            pd.Series(0.0, index=working.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    working["uci_points"] = pd.to_numeric(
        working.get("uci_points", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    working["points_per_raceday"] = pd.to_numeric(
        working.get("points_per_raceday", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    working["team_rank_within_roster"] = pd.to_numeric(
        working.get("team_rank_within_roster", pd.Series(pd.NA, index=working.index, dtype="Float64")),
        errors="coerce",
    )
    if working["team_rank_within_roster"].notna().any():
        fallback_rank = float(working["team_rank_within_roster"].dropna().max()) + 1.0
    else:
        fallback_rank = float(len(working) + 1)
    working["team_rank_within_roster"] = working["team_rank_within_roster"].fillna(fallback_rank)
    working["current_scored_150_flag"] = pd.to_numeric(
        working.get("current_scored_150_flag", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    working["stage_points_share"] = pd.to_numeric(
        working.get("stage_points_share", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    working["gc_points_share"] = pd.to_numeric(
        working.get("gc_points_share", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    working["one_day_points_share"] = pd.to_numeric(
        working.get("one_day_points_share", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    working["secondary_points_share"] = pd.to_numeric(
        working.get("secondary_points_share", pd.Series(0.0, index=working.index, dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    raw_specialty = (
        working.get("specialty_primary", pd.Series("", index=working.index))
        .fillna("")
        .astype(str)
        .str.casefold()
    )
    working["specialty_primary"] = raw_specialty.where(
        raw_specialty.str.strip() != "",
        working.apply(_derive_specialty_from_points_mix, axis=1),
    )
    working["specialty_primary"] = working["specialty_primary"].replace("", "fallback")
    working["archetype"] = working.get("archetype", pd.Series("", index=working.index)).astype(str)
    working["model_name"] = working.get("model_name", pd.Series("", index=working.index)).astype(str)

    working["uci_points_score"] = _minmax_scale(working["uci_points"])
    working["points_per_raceday_score"] = _minmax_scale(working["points_per_raceday"])
    working["roster_priority_score"] = _minmax_scale(working["team_rank_within_roster"], invert=True)
    working["rider_selection_score"] = (
        0.60 * working["predicted_rider_reaches_150_probability"]
        + 0.15 * working["points_per_raceday_score"]
        + 0.10 * working["uci_points_score"]
        + 0.10 * working["roster_priority_score"]
        + 0.05 * working["current_scored_150_flag"]
    ).clip(lower=0.0, upper=1.0)
    keep_columns = [
        "rider_name",
        "specialty_primary",
        "archetype",
        "predicted_rider_reaches_150_probability",
        "uci_points",
        "points_per_raceday",
        "team_rank_within_roster",
        "current_scored_150_flag",
        "model_name",
        "uci_points_score",
        "points_per_raceday_score",
        "roster_priority_score",
        "rider_selection_score",
    ]
    return working.loc[:, keep_columns].reset_index(drop=True)


def _specialty_match_score(row: pd.Series) -> float:
    specialty = str(row.get("specialty_primary") or "").casefold()
    weights = SPECIALTY_SIGNAL_WEIGHTS.get(specialty, SPECIALTY_SIGNAL_WEIGHTS["fallback"])
    total = 0.0
    for signal_column, weight in weights.items():
        signal_value = pd.to_numeric(row.get(signal_column), errors="coerce")
        if pd.isna(signal_value):
            signal_value = 0.0
        total += float(signal_value) * float(weight)
    return round(max(min(total, 1.0), 0.0), 6)


def _build_race_plan(
    allocation_table: pd.DataFrame,
    *,
    roster_size: int,
    top_riders_per_race: int,
) -> pd.DataFrame:
    selected = allocation_table.loc[allocation_table["recommended_start_flag"] == 1].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for _, group in selected.groupby("race_key", sort=False):
        ordered = group.sort_values(["allocation_rank", "rider_name"]).reset_index(drop=True)
        top_rows = ordered.head(top_riders_per_race)
        race_leader_row = ordered.iloc[0]
        rows.append(
            {
                "team_slug": str(race_leader_row["team_slug"]),
                "team_name": str(race_leader_row["team_name"]),
                "planning_year": int(race_leader_row["planning_year"]),
                "race_id": race_leader_row.get("race_id", pd.NA),
                "race_name": str(race_leader_row["race_name"]),
                "category": str(race_leader_row["category"]),
                "start_date": str(race_leader_row["start_date"]),
                "status": str(race_leader_row["status"]),
                "route_profile": str(race_leader_row["route_profile"]),
                "expected_points": round(float(race_leader_row["expected_points"]), 6),
                "race_priority_points": round(float(race_leader_row["race_priority_points"]), 6),
                "recommended_rider_count": min(int(roster_size), len(ordered)),
                "race_leader_rider": str(race_leader_row["rider_name"]),
                "race_leader_specialty": str(race_leader_row["specialty_primary"]),
                "race_leader_probability": round(
                    float(race_leader_row["predicted_rider_reaches_150_probability"]),
                    6,
                ),
                "race_leader_allocation_score": round(float(race_leader_row["allocation_score"]), 6),
                "selected_breakout_probability_sum": round(
                    float(ordered["predicted_rider_reaches_150_probability"].sum()),
                    6,
                ),
                "selected_breakout_probability_mean": round(
                    float(ordered["predicted_rider_reaches_150_probability"].mean()),
                    6,
                ),
                "selected_allocation_score_total": round(float(ordered["allocation_score"].sum()), 6),
                "selected_specialty_match_mean": round(float(ordered["specialty_match_score"].mean()), 6),
                "top_recommended_riders": " | ".join(top_rows["rider_name"].astype(str).tolist()),
                "top_recommended_specialties": " | ".join(top_rows["specialty_primary"].astype(str).tolist()),
            }
        )

    race_plan = pd.DataFrame(rows)
    return race_plan.sort_values(
        ["start_date", "selected_allocation_score_total", "race_name"],
        ascending=[True, False, True],
        na_position="last",
    ).reset_index(drop=True)


def _build_rider_load_summary(allocation_table: pd.DataFrame) -> pd.DataFrame:
    selected = allocation_table.loc[allocation_table["recommended_start_flag"] == 1].copy()
    if selected.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for _, group in selected.groupby("rider_name", sort=False):
        ordered = group.sort_values(["allocation_score", "start_date"], ascending=[False, True]).reset_index(drop=True)
        best_row = ordered.iloc[0]
        rows.append(
            {
                "team_slug": str(best_row["team_slug"]),
                "team_name": str(best_row["team_name"]),
                "planning_year": int(best_row["planning_year"]),
                "rider_name": str(best_row["rider_name"]),
                "specialty_primary": str(best_row["specialty_primary"]),
                "archetype": str(best_row["archetype"]),
                "recommended_race_count": int(len(ordered)),
                "race_leader_assignments": int(ordered["race_leader_flag"].sum()),
                "allocation_score_total": round(float(ordered["allocation_score"].sum()), 6),
                "mean_breakout_probability": round(
                    float(ordered["predicted_rider_reaches_150_probability"].mean()),
                    6,
                ),
                "mean_specialty_match_score": round(float(ordered["specialty_match_score"].mean()), 6),
                "best_race_name": str(best_row["race_name"]),
                "best_race_start_date": str(best_row["start_date"]),
                "best_race_category": str(best_row["category"]),
                "best_race_allocation_score": round(float(best_row["allocation_score"]), 6),
            }
        )

    rider_load_summary = pd.DataFrame(rows)
    return rider_load_summary.sort_values(
        ["race_leader_assignments", "allocation_score_total", "rider_name"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _build_summary(
    allocation_table: pd.DataFrame,
    *,
    race_plan: pd.DataFrame,
    rider_load_summary: pd.DataFrame,
    roster_size: int,
    top_riders_per_race: int,
) -> dict[str, object]:
    selected = allocation_table.loc[allocation_table["recommended_start_flag"] == 1].copy()
    team_slug = str(allocation_table["team_slug"].dropna().astype(str).iloc[0])
    team_name = str(allocation_table["team_name"].dropna().astype(str).iloc[0])
    planning_year = int(pd.to_numeric(allocation_table["planning_year"], errors="coerce").dropna().iloc[0])
    model_name = str(allocation_table["model_name"].dropna().astype(str).iloc[0])
    return {
        "artifact_version": "rider_race_allocation_v1",
        "team_slug": team_slug,
        "team_name": team_name,
        "planning_year": planning_year,
        "rider_model_name": model_name,
        "roster_size": int(roster_size),
        "top_riders_per_race": int(top_riders_per_race),
        "race_count": int(allocation_table["race_key"].nunique()),
        "rider_count": int(allocation_table["rider_name"].nunique()),
        "pairings_scored": int(len(allocation_table)),
        "selected_pairings": int(len(selected)),
        "race_leader_assignments": int(selected["race_leader_flag"].sum()),
        "mean_selected_breakout_probability": round(
            float(selected["predicted_rider_reaches_150_probability"].mean()),
            6,
        ),
        "mean_selected_specialty_match_score": round(float(selected["specialty_match_score"].mean()), 6),
        "mean_selected_allocation_score": round(float(selected["allocation_score"].mean()), 6),
        "top_race_leader_rider": str(rider_load_summary.iloc[0]["rider_name"]) if not rider_load_summary.empty else "",
        "top_race_name": str(race_plan.iloc[0]["race_name"]) if not race_plan.empty else "",
    }


def _minmax_scale(series: pd.Series, *, invert: bool = False) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        scaled = pd.Series(0.0, index=series.index, dtype=float)
    else:
        lower = float(numeric.min())
        upper = float(numeric.max())
        if lower == upper:
            scaled = pd.Series(1.0, index=series.index, dtype=float)
        else:
            scaled = ((numeric - lower) / (upper - lower)).astype(float)
    if invert:
        scaled = 1.0 - scaled
    return scaled.fillna(0.0).clip(lower=0.0, upper=1.0)


def _derive_specialty_from_points_mix(row: pd.Series) -> str:
    gc_share = _coerce_scalar(row.get("gc_points_share"))
    one_day_share = _coerce_scalar(row.get("one_day_points_share"))
    stage_share = _coerce_scalar(row.get("stage_points_share"))
    secondary_share = _coerce_scalar(row.get("secondary_points_share"))

    if secondary_share >= 0.25:
        return "tt"
    if gc_share >= 0.60:
        return "gc"
    if stage_share >= 0.45:
        return "sprint"
    if one_day_share >= 0.80:
        return "oneday"
    if gc_share >= 0.30 and one_day_share >= 0.25:
        return "hills"
    return "fallback"


def _coerce_scalar(value: object) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return 0.0
    return float(numeric)
