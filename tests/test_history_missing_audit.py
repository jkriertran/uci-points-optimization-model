from pathlib import Path

import pandas as pd

from uci_points_model.history_missing_audit import (
    run_history_missing_race_audit,
    write_history_missing_audit_artifacts,
)


def test_run_history_missing_race_audit_builds_team_and_detail_outputs(tmp_path: Path) -> None:
    team_ev_root = tmp_path / "team_ev"
    team_ev_root.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race One",
                "category": "1.1",
                "start_date": "2026-03-01",
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
                "notes": "matched_via=normalized_name | history_missing",
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race Two",
                "category": "2.1",
                "start_date": "2026-03-05",
                "status": "completed",
                "historical_years_analyzed": 3,
                "avg_top10_points": 150.0,
                "base_opportunity_points": 120.0,
                "team_fit_multiplier": 0.8,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.3,
                "expected_points": 28.8,
                "actual_points": 12.0,
                "ev_gap": -16.8,
                "notes": "matched_via=token_overlap | history_fallback_from=2.1 | history_missing",
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race Three",
                "category": "1.2",
                "start_date": "2026-03-09",
                "status": "scheduled",
                "historical_years_analyzed": 4,
                "avg_top10_points": 90.0,
                "base_opportunity_points": 80.0,
                "team_fit_multiplier": 0.9,
                "participation_confidence": 0.8,
                "execution_multiplier": 0.25,
                "expected_points": 14.4,
                "actual_points": pd.NA,
                "ev_gap": pd.NA,
                "notes": "",
            },
        ]
    ).to_csv(team_ev_root / "alpha_team_2026_calendar_ev.csv", index=False)

    pd.DataFrame(
        [
            {
                "team_slug": "beta-team",
                "team_name": "Beta Team",
                "planning_year": 2026,
                "race_name": "Beta Race",
                "category": "1.1",
                "start_date": "2026-04-01",
                "status": "scheduled",
                "historical_years_analyzed": pd.NA,
                "avg_top10_points": pd.NA,
                "base_opportunity_points": pd.NA,
                "team_fit_multiplier": 0.7,
                "participation_confidence": 0.8,
                "execution_multiplier": 0.25,
                "expected_points": 0.0,
                "actual_points": pd.NA,
                "ev_gap": pd.NA,
                "notes": "matched_via=normalized_name | history_missing",
            }
        ]
    ).to_csv(team_ev_root / "beta_team_2026_calendar_ev.csv", index=False)

    artifacts = run_history_missing_race_audit(team_ev_root=team_ev_root)

    assert artifacts.summary["scanned_team_files"] == 2
    assert artifacts.summary["teams_with_history_missing"] == 2
    assert artifacts.summary["total_history_missing_races"] == 3
    assert artifacts.summary["completed_history_missing_races"] == 2
    assert artifacts.summary["history_missing_with_fallback"] == 1
    assert artifacts.summary["history_missing_with_zero_expected"] == 2
    assert artifacts.summary["completed_missing_ev_components"] == 1

    assert artifacts.team_summary["team_name"].tolist() == ["Alpha Team", "Beta Team"]
    alpha_summary = artifacts.team_summary.loc[artifacts.team_summary["team_slug"] == "alpha-team"].iloc[0]
    assert int(alpha_summary["history_missing_races"]) == 2
    assert int(alpha_summary["completed_missing_ev_components"]) == 1
    assert float(alpha_summary["actual_points_scored_in_history_missing_races"]) == 42.0

    race_details = artifacts.race_details.sort_values(["team_slug", "race_name"]).reset_index(drop=True)
    assert race_details["race_name"].tolist() == ["Race One", "Race Two", "Beta Race"]
    assert race_details.loc[race_details["race_name"] == "Race One", "matched_via"].iloc[0] == "normalized_name"
    assert race_details.loc[race_details["race_name"] == "Race Two", "history_fallback_from"].iloc[0] == "2.1"


def test_write_history_missing_audit_artifacts_persists_expected_files(tmp_path: Path) -> None:
    team_ev_root = tmp_path / "team_ev"
    team_ev_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Race One",
                "category": "1.1",
                "start_date": "2026-03-01",
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
                "notes": "matched_via=normalized_name | history_missing",
            }
        ]
    ).to_csv(team_ev_root / "alpha_team_2026_calendar_ev.csv", index=False)

    artifacts = run_history_missing_race_audit(team_ev_root=team_ev_root)
    written = write_history_missing_audit_artifacts(artifacts, output_root=tmp_path / "audits")

    assert written["summary_path"].exists()
    assert written["report_path"].exists()
    assert written["team_summary_path"].exists()
    assert written["race_details_path"].exists()
