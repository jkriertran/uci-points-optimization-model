from pathlib import Path

import pandas as pd

from uci_points_model.rider_race_allocation import (
    build_rider_race_allocation_artifacts,
    rider_race_allocation_artifact_stem,
    write_rider_race_allocation_artifacts,
)


def test_build_rider_race_allocation_artifacts_assigns_specialists_to_best_races() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 11,
                "race_name": "Classic Day",
                "category": "1.1",
                "start_date": "2026-03-01",
                "status": "scheduled",
                "route_profile": "one-day classic",
                "expected_points": 100.0,
                "base_opportunity_points": 95.0,
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.4,
                "gc_signal": 0.1,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.5,
                "sprint_bonus_signal": 0.6,
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 22,
                "race_name": "Mountain Tour",
                "category": "2.1",
                "start_date": "2026-04-10",
                "status": "scheduled",
                "route_profile": "gc-heavy stage race",
                "expected_points": 90.0,
                "base_opportunity_points": 85.0,
                "one_day_signal": 0.1,
                "stage_hunter_signal": 0.3,
                "gc_signal": 1.0,
                "time_trial_signal": 0.2,
                "all_round_signal": 0.8,
                "sprint_bonus_signal": 0.1,
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 33,
                "race_name": "Cancelled Example",
                "category": "1.2",
                "start_date": "2026-05-20",
                "status": "cancelled",
                "expected_points": 70.0,
                "base_opportunity_points": 60.0,
                "one_day_signal": 0.8,
                "stage_hunter_signal": 0.1,
                "gc_signal": 0.1,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.2,
                "sprint_bonus_signal": 0.5,
            },
        ]
    )
    rider_scores_df = pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider Classic",
                "specialty_primary": "oneday",
                "archetype": "anchor",
                "predicted_rider_reaches_150_probability": 0.72,
                "uci_points": 250.0,
                "points_per_raceday": 8.0,
                "team_rank_within_roster": 1,
                "current_scored_150_flag": 1,
                "model_name": "baseline_prior_points",
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider Climb",
                "specialty_primary": "gc",
                "archetype": "anchor",
                "predicted_rider_reaches_150_probability": 0.65,
                "uci_points": 220.0,
                "points_per_raceday": 7.2,
                "team_rank_within_roster": 2,
                "current_scored_150_flag": 1,
                "model_name": "baseline_prior_points",
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider TT",
                "specialty_primary": "tt",
                "archetype": "engine",
                "predicted_rider_reaches_150_probability": 0.48,
                "uci_points": 120.0,
                "points_per_raceday": 5.0,
                "team_rank_within_roster": 3,
                "current_scored_150_flag": 0,
                "model_name": "baseline_prior_points",
            },
        ]
    )

    artifacts = build_rider_race_allocation_artifacts(
        calendar_ev_df,
        rider_scores_df,
        roster_size=2,
        top_riders_per_race=2,
    )

    assert artifacts.summary["race_count"] == 2
    assert artifacts.summary["rider_count"] == 3
    assert artifacts.summary["selected_pairings"] == 4
    assert artifacts.race_plan["race_name"].tolist() == ["Classic Day", "Mountain Tour"]
    assert artifacts.race_plan["race_leader_rider"].tolist() == ["Rider Classic", "Rider Climb"]
    assert artifacts.race_plan["top_recommended_riders"].tolist() == [
        "Rider Classic | Rider Climb",
        "Rider Climb | Rider Classic",
    ]
    assert artifacts.rider_load_summary.loc[0, "rider_name"] == "Rider Classic"
    assert artifacts.allocation_table["race_name"].nunique() == 2
    assert "Cancelled Example" not in artifacts.allocation_table["race_name"].tolist()


def test_write_rider_race_allocation_artifacts_persists_expected_files(tmp_path: Path) -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 11,
                "race_name": "Classic Day",
                "category": "1.1",
                "start_date": "2026-03-01",
                "status": "scheduled",
                "expected_points": 100.0,
                "base_opportunity_points": 95.0,
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.4,
                "gc_signal": 0.1,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.5,
                "sprint_bonus_signal": 0.6,
            }
        ]
    )
    rider_scores_df = pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider Classic",
                "specialty_primary": "oneday",
                "archetype": "anchor",
                "predicted_rider_reaches_150_probability": 0.72,
                "uci_points": 250.0,
                "points_per_raceday": 8.0,
                "team_rank_within_roster": 1,
                "current_scored_150_flag": 1,
                "model_name": "baseline_prior_points",
            }
        ]
    )

    artifacts = build_rider_race_allocation_artifacts(calendar_ev_df, rider_scores_df, roster_size=1)
    written_paths = write_rider_race_allocation_artifacts(artifacts, output_root=tmp_path)
    stem = rider_race_allocation_artifact_stem("alpha-team", 2026)

    assert written_paths["summary_path"] == tmp_path / f"{stem}_rider_race_allocation_summary.json"
    assert written_paths["allocation_path"] == tmp_path / f"{stem}_rider_race_allocations.csv"
    assert written_paths["race_plan_path"] == tmp_path / f"{stem}_rider_race_plan.csv"
    assert written_paths["rider_load_path"] == tmp_path / f"{stem}_rider_load_summary.csv"
    for path in written_paths.values():
        assert path.exists()


def test_build_rider_race_allocation_artifacts_derives_specialty_when_missing() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 44,
                "race_name": "Mountain Tour",
                "category": "2.1",
                "start_date": "2026-04-10",
                "status": "scheduled",
                "expected_points": 90.0,
                "base_opportunity_points": 85.0,
                "one_day_signal": 0.1,
                "stage_hunter_signal": 0.2,
                "gc_signal": 1.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.8,
                "sprint_bonus_signal": 0.1,
            }
        ]
    )
    rider_scores_df = pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider GC",
                "specialty_primary": "",
                "archetype": "anchor",
                "predicted_rider_reaches_150_probability": 0.60,
                "uci_points": 180.0,
                "points_per_raceday": 6.0,
                "team_rank_within_roster": 1,
                "current_scored_150_flag": 1,
                "gc_points_share": 0.75,
                "one_day_points_share": 0.25,
                "stage_points_share": 0.0,
                "secondary_points_share": 0.0,
                "model_name": "baseline_prior_points",
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider OneDay",
                "specialty_primary": "",
                "archetype": "engine",
                "predicted_rider_reaches_150_probability": 0.62,
                "uci_points": 185.0,
                "points_per_raceday": 6.1,
                "team_rank_within_roster": 2,
                "current_scored_150_flag": 1,
                "gc_points_share": 0.0,
                "one_day_points_share": 0.95,
                "stage_points_share": 0.05,
                "secondary_points_share": 0.0,
                "model_name": "baseline_prior_points",
            },
        ]
    )

    artifacts = build_rider_race_allocation_artifacts(calendar_ev_df, rider_scores_df, roster_size=1)

    race_leader_row = artifacts.race_plan.iloc[0]
    assert race_leader_row["race_leader_rider"] == "Rider GC"
    assert race_leader_row["race_leader_specialty"] == "gc"
