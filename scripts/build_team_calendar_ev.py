from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.calendar_ev import (
    DEFAULT_EV_WEIGHTS,
    build_actual_points_table,
    build_historical_target_summary,
    build_team_calendar_ev,
    canonicalize_team_slug,
    load_team_profile,
    summarize_team_calendar_ev,
)
from uci_points_model.team_calendar import build_live_team_calendar, derive_calendar_status

OPPORTUNITY_WEIGHT_RATIONALE = {
    "avg_points_efficiency": "Highest weight because the model should favor races that have historically turned field quality into points efficiently.",
    "avg_top10_points": "Rewards broad scoring opportunity instead of only winner upside.",
    "avg_winner_points": "Keeps a smaller reward for races with real ceiling if the team lands a big result.",
    "avg_stage_top10_points": "Adds stage-race scoring depth without letting stage volume dominate the entire ranking.",
    "field_softness_score": "Rewards races whose historical top end has looked softer for the points on offer.",
}

TEAM_STRENGTH_RATIONALE = {
    "one_day": "How much the team profile should care about classic-style one-day signals.",
    "stage_hunter": "How much the profile should value stage-hunting or sprinter-friendly stage-race signals.",
    "gc": "How much the profile should care about GC-heavy stage-race opportunity.",
    "time_trial": "How much time-trial signals should influence team fit.",
    "all_round": "How much the profile should reward balanced, all-round stage-race opportunity.",
    "sprint_bonus": "Extra boost for sprint-sensitive opportunities when the roster is built to exploit them.",
}

PARTICIPATION_RULE_RATIONALE = {
    "completed": "Completed races get full participation confidence because the team actually started.",
    "program_confirmed": "A live team program listing is strong evidence, but still below a completed race.",
    "observed_startlist": "Observed startlists are nearly as strong as a program-confirmed entry.",
    "calendar_seed": "The planning calendar alone is a weaker signal, so future starts get a haircut.",
    "overlap_penalty": "When races overlap, confidence is capped because a team cannot fully commit to both.",
}

EXECUTION_RULE_RATIONALE = "Execution multipliers are conservative realization haircuts by race category. Bigger races keep a lower multiplier because historical opportunity does not fully translate into team-level realized points."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic team calendar expected value outputs.")
    parser.add_argument("--team-slug", required=True, help="Stable team slug used inside the saved artifacts.")
    parser.add_argument(
        "--pcs-team-slug",
        default=None,
        help="Optional season-qualified PCS team slug used for live fetches. Defaults to the profile value or team slug.",
    )
    parser.add_argument("--planning-year", type=int, required=True, help="Planning year for the EV build.")
    parser.add_argument("--team-profile-path", required=True, help="JSON path for the team EV profile.")
    parser.add_argument("--calendar-path", required=True, help="Latest team calendar snapshot CSV.")
    parser.add_argument("--actual-points-path", required=True, help="Output CSV for race-level actual points.")
    parser.add_argument("--ev-output-path", required=True, help="Output CSV for the race-level calendar EV table.")
    parser.add_argument("--summary-output-path", required=True, help="Output CSV for calendar EV summaries.")
    parser.add_argument("--readme-path", required=True, help="Markdown readme path for the EV dataset.")
    parser.add_argument("--dictionary-path", required=True, help="Markdown data dictionary path for the EV dataset.")
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Optional YYYY-MM-DD override for status calculation.",
    )
    return parser.parse_args()


def _load_calendar_or_build(
    team_slug: str,
    planning_year: int,
    calendar_path: Path,
    as_of_date: str | None,
    pcs_team_slug: str,
) -> pd.DataFrame:
    if calendar_path.exists():
        calendar_df = pd.read_csv(calendar_path, low_memory=False)
        if "race_id" in calendar_df.columns:
            calendar_df["race_id"] = pd.to_numeric(calendar_df["race_id"], errors="coerce").astype("Int64")
        if "end_date" in calendar_df.columns:
            calendar_df["status"] = calendar_df["end_date"].map(lambda value: derive_calendar_status(value, as_of_date))
        calendar_df["team_slug"] = team_slug
        calendar_df["planning_year"] = int(planning_year)
        return calendar_df

    calendar_df = build_live_team_calendar(
        team_slug=team_slug,
        pcs_team_slug=pcs_team_slug,
        planning_year=planning_year,
        as_of_date=as_of_date,
    )
    calendar_path.parent.mkdir(parents=True, exist_ok=True)
    calendar_df.to_csv(calendar_path, index=False)
    return calendar_df


def _write_readme(path: Path, team_slug: str, planning_year: int) -> None:
    text = f"""# Team Calendar EV Dataset

This dataset stores the deterministic Version 2 calendar expected-value build for `{team_slug}` in `{planning_year}`.

## What It Contains

- One row per tracked race in the live PCS team program matched onto the bundled planning calendar
- Historical opportunity anchors derived from `data/race_editions_snapshot.csv`
- Transparent EV components: `base_opportunity_points`, `team_fit_score`, `participation_confidence`, and `execution_multiplier`
- Live PCS `team-in-race` actual points where a rider table is available, with confirmed zero-point completed races retained as zeroes and unknown actuals left blank

## Important Coverage Note

The team calendar comes from the live PCS team program page and is matched back to the bundled planning calendar with a small alias table. Future races stay in the snapshot as `scheduled`, while completed races are identified from their planning dates.

## Rebuild

1. Refresh the team calendar snapshot with `python scripts/build_team_calendar_snapshots.py`.
2. Rebuild the EV outputs with `python scripts/build_team_calendar_ev.py`.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _write_dictionary(path: Path) -> None:
    race_level_rows = [
        ("team_slug", "Stable team identifier shared across seasons."),
        ("team_name", "Human-readable team name."),
        ("planning_year", "Planning calendar year."),
        ("race_id", "Planning calendar race identifier."),
        ("race_name", "Planning calendar race name."),
        ("category", "Current race category from the planning calendar."),
        ("date_label", "Planning calendar date label."),
        ("month", "Planning calendar month number."),
        ("start_date", "Normalized planning start date."),
        ("end_date", "Normalized planning end date."),
        ("pcs_race_slug", "PCS race slug used to fetch the team-in-race points page."),
        ("historical_years_analyzed", "Count of prior editions used in the historical summary."),
        ("race_type", "Historical race type label from the race-edition snapshot."),
        ("route_profile", "Lightweight race-profile label derived from historical structure."),
        ("avg_top10_points", "Average historical top-10 points haul."),
        ("avg_winner_points", "Average historical winner points."),
        ("avg_points_efficiency", "Average historical points-per-top10-form efficiency."),
        ("avg_stage_top10_points", "Average historical stage-race top-10 points component."),
        ("avg_stage_count", "Average historical stage count."),
        ("avg_top10_field_form", "Average historical top-10 field-form proxy."),
        ("base_opportunity_index", "Normalized historical opportunity score."),
        ("base_opportunity_points", "Points-space base opportunity anchor."),
        ("specialty_fit_score", "Team-fit score from non-sprint dimensions."),
        ("sprint_fit_bonus", "Explicit sprint-sensitive team-fit add-on."),
        ("team_fit_score", "Combined normalized team-fit score."),
        ("team_fit_multiplier", "Bounded multiplier applied to base opportunity."),
        ("participation_confidence", "Deterministic participation confidence factor."),
        ("execution_multiplier", "Category-based conservative realization haircut."),
        ("expected_points", "Final deterministic Version 2 expected-value estimate."),
        ("actual_points", "Live PCS actual UCI points for the team in that race when known."),
        ("ev_gap", "Actual minus expected points when actuals are known."),
        ("status", "Calendar state such as completed or scheduled."),
        ("team_calendar_status", "Current team calendar membership flag."),
        ("source", "Snapshot source label."),
        ("overlap_group", "Overlap flag for simultaneous race windows."),
        ("notes", "Join or data quality notes."),
        ("as_of_date", "Persisted freshness marker used for status derivation and UI messaging."),
    ]
    summary_rows = [
        ("team_slug", "Stable team identifier shared across seasons."),
        ("planning_year", "Planning calendar year."),
        ("as_of_date", "Freshness marker shown in the UI."),
        ("total_expected_points", "Full-season expected-value total."),
        ("completed_expected_points", "Expected points from races whose status is completed."),
        ("remaining_expected_points", "Expected points from races whose status is scheduled."),
        ("actual_points_known", "Observed points summed only from races with known actuals, including confirmed zeroes."),
        ("ev_gap_known", "Observed minus expected points summed only where actuals are known."),
        ("race_count", "Total number of tracked races in the saved season artifact."),
        ("completed_race_count", "Number of completed races in the saved season artifact."),
        ("remaining_race_count", "Number of scheduled races in the saved season artifact."),
    ]
    lines = ["# Team Calendar EV Data Dictionary", "", "## Race-Level EV File", "", "| Field | Description |", "| --- | --- |"]
    lines.extend(f"| `{field}` | {description} |" for field, description in race_level_rows)
    lines.extend(["", "## Summary File", "", "| Field | Description |", "| --- | --- |"])
    lines.extend(f"| `{field}` | {description} |" for field, description in summary_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _metadata_path_for_summary(summary_output_path: Path) -> Path:
    if summary_output_path.name.endswith("_calendar_ev_summary.csv"):
        return summary_output_path.with_name(
            summary_output_path.name.replace("_calendar_ev_summary.csv", "_calendar_ev_metadata.json")
        )
    return summary_output_path.with_suffix(".json")


def _build_metadata(
    *,
    team_slug: str,
    pcs_team_slug: str,
    planning_year: int,
    team_profile: dict,
    summary_df: pd.DataFrame,
    calendar_rows: int,
) -> dict[str, object]:
    summary_row = summary_df.iloc[0].to_dict() if not summary_df.empty else {}
    strength_weights = {
        key: float(value)
        for key, value in dict(team_profile.get("strength_weights", {})).items()
    }
    execution_rules = {
        key: float(value)
        for key, value in dict(team_profile.get("execution_rules", {})).items()
    }
    participation_rules = {
        key: float(value)
        for key, value in dict(team_profile.get("participation_rules", {})).items()
    }
    return {
        "team_slug": team_slug,
        "pcs_team_slug": pcs_team_slug,
        "planning_year": int(planning_year),
        "team_name": str(team_profile.get("team_name") or ""),
        "as_of_date": str(summary_row.get("as_of_date") or ""),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_row_count": int(calendar_rows),
        "expected_points_formula": "base_opportunity_points * team_fit_multiplier * participation_confidence * execution_multiplier",
        "opportunity_model": {
            "weights": {key: float(value) for key, value in DEFAULT_EV_WEIGHTS.items()},
            "rationale": OPPORTUNITY_WEIGHT_RATIONALE,
        },
        "team_profile": {
            "strength_weights": strength_weights,
            "strength_weight_rationale": TEAM_STRENGTH_RATIONALE,
            "team_fit_floor": float(team_profile.get("team_fit_floor", 0.70)),
            "team_fit_range": float(team_profile.get("team_fit_range", 0.30)),
            "team_fit_rationale": "The multiplier is bounded as floor + range * team_fit_score, which keeps team fit as an adjustment rather than letting it overwhelm the historical opportunity anchor.",
            "execution_rules": execution_rules,
            "execution_rule_rationale": EXECUTION_RULE_RATIONALE,
            "participation_rules": participation_rules,
            "participation_rule_rationale": PARTICIPATION_RULE_RATIONALE,
        },
    }


def main() -> None:
    args = parse_args()
    team_profile = load_team_profile(args.team_profile_path)
    team_slug = canonicalize_team_slug(args.team_slug, args.planning_year)
    pcs_team_slug = str(args.pcs_team_slug or team_profile.get("pcs_team_slug") or args.team_slug)
    calendar_path = Path(args.calendar_path)
    actual_points_path = Path(args.actual_points_path)
    ev_output_path = Path(args.ev_output_path)
    summary_output_path = Path(args.summary_output_path)
    metadata_output_path = _metadata_path_for_summary(summary_output_path)
    readme_path = Path(args.readme_path)
    dictionary_path = Path(args.dictionary_path)

    team_calendar_df = _load_calendar_or_build(
        team_slug,
        args.planning_year,
        calendar_path,
        args.as_of_date,
        pcs_team_slug,
    )
    actual_points_df = build_actual_points_table(
        team_slug,
        args.planning_year,
        team_calendar_df,
        pcs_team_slug=pcs_team_slug,
        as_of_date=args.as_of_date,
    )
    historical_summary_df = build_historical_target_summary(planning_year=args.planning_year)
    calendar_ev_df = build_team_calendar_ev(
        team_slug=team_slug,
        planning_year=args.planning_year,
        historical_summary=historical_summary_df,
        team_calendar=team_calendar_df,
        team_profile=team_profile,
        actual_points_df=actual_points_df,
        as_of_date=args.as_of_date,
    )
    summary_df = summarize_team_calendar_ev(calendar_ev_df)

    for output_path in [
        calendar_path,
        actual_points_path,
        ev_output_path,
        summary_output_path,
        metadata_output_path,
        readme_path,
        dictionary_path,
    ]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    actual_points_df.to_csv(actual_points_path, index=False)
    calendar_ev_df.to_csv(ev_output_path, index=False)
    summary_df.to_csv(summary_output_path, index=False)
    metadata_output_path.write_text(
        json.dumps(
            _build_metadata(
                team_slug=team_slug,
                pcs_team_slug=pcs_team_slug,
                planning_year=args.planning_year,
                team_profile=team_profile,
                summary_df=summary_df,
                calendar_rows=len(calendar_ev_df),
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    _write_readme(readme_path, team_slug, args.planning_year)
    _write_dictionary(dictionary_path)

    print(f"Wrote {len(actual_points_df)} actual-points rows to {actual_points_path}")
    print(f"Wrote {len(calendar_ev_df)} race-level EV rows to {ev_output_path}")
    print(f"Wrote {len(summary_df)} summary rows to {summary_output_path}")
    print(f"Wrote metadata to {metadata_output_path}")


if __name__ == "__main__":
    main()
