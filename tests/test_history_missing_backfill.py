from pathlib import Path

import pandas as pd

from uci_points_model.history_missing_backfill import (
    build_history_missing_backfill_priority_list,
    write_history_missing_backfill_artifacts,
)


def test_build_history_missing_backfill_priority_list_ranks_repeated_high_impact_races(tmp_path: Path) -> None:
    team_ev_root = tmp_path / "team_ev"
    team_ev_root.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race Repeated",
                "category": "1.2",
                "start_date": "2026-03-01",
                "status": "completed",
                "historical_years_analyzed": pd.NA,
                "avg_top10_points": pd.NA,
                "base_opportunity_points": pd.NA,
                "team_fit_multiplier": 0.7,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.25,
                "expected_points": 0.0,
                "actual_points": 40.0,
                "ev_gap": 40.0,
                "notes": "matched_via=normalized_name | history_missing",
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race Token",
                "category": "1.2",
                "start_date": "2026-03-04",
                "status": "completed",
                "historical_years_analyzed": pd.NA,
                "avg_top10_points": pd.NA,
                "base_opportunity_points": pd.NA,
                "team_fit_multiplier": 0.7,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.25,
                "expected_points": 0.0,
                "actual_points": 30.0,
                "ev_gap": 30.0,
                "notes": "matched_via=token_overlap | history_missing",
            },
        ]
    ).to_csv(team_ev_root / "alpha_team_2026_calendar_ev.csv", index=False)

    pd.DataFrame(
        [
            {
                "team_slug": "beta-team",
                "team_name": "Beta Team",
                "planning_year": 2026,
                "race_name": "Race Repeated",
                "category": "1.2",
                "start_date": "2026-03-02",
                "status": "completed",
                "historical_years_analyzed": pd.NA,
                "avg_top10_points": pd.NA,
                "base_opportunity_points": pd.NA,
                "team_fit_multiplier": 0.7,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.25,
                "expected_points": 0.0,
                "actual_points": 20.0,
                "ev_gap": 20.0,
                "notes": "matched_via=normalized_name | history_missing",
            }
        ]
    ).to_csv(team_ev_root / "beta_team_2026_calendar_ev.csv", index=False)

    artifacts = build_history_missing_backfill_priority_list(team_ev_root=team_ev_root)

    assert artifacts.summary["unique_backfill_races"] == 2
    assert artifacts.summary["p1_races"] == 1
    assert artifacts.priority_list.loc[0, "race_name"] == "Race Repeated"
    assert artifacts.priority_list.loc[0, "priority_tier"] == "P1"
    assert artifacts.priority_list.loc[0, "affected_teams"] == 2
    assert artifacts.priority_list.loc[0, "total_actual_points"] == 60.0
    assert "coverage" in artifacts.priority_list.loc[0, "likely_issue"].casefold()
    assert "aliases" in artifacts.priority_list.loc[1, "recommended_action"].casefold()


def test_write_history_missing_backfill_artifacts_persists_expected_files(tmp_path: Path) -> None:
    team_ev_root = tmp_path / "team_ev"
    team_ev_root.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race One",
                "category": "1.2",
                "start_date": "2026-03-01",
                "status": "completed",
                "historical_years_analyzed": pd.NA,
                "avg_top10_points": pd.NA,
                "base_opportunity_points": pd.NA,
                "team_fit_multiplier": 0.7,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.25,
                "expected_points": 0.0,
                "actual_points": 40.0,
                "ev_gap": 40.0,
                "notes": "matched_via=normalized_name | history_missing",
            }
        ]
    ).to_csv(team_ev_root / "alpha_team_2026_calendar_ev.csv", index=False)

    artifacts = build_history_missing_backfill_priority_list(team_ev_root=team_ev_root)
    written = write_history_missing_backfill_artifacts(artifacts, output_root=tmp_path / "audits")

    assert written["summary_path"].exists()
    assert written["report_path"].exists()
    assert written["priority_path"].exists()
    assert written["detail_path"].exists()
