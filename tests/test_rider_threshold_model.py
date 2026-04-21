from __future__ import annotations

from pathlib import Path

import pandas as pd

from uci_points_model.rider_threshold_model import (
    build_rider_season_panel,
    build_rider_threshold_baseline_artifacts,
    fit_rider_threshold_baseline,
    fit_rider_threshold_baseline_suite,
    score_rider_threshold_dataset,
    write_rider_threshold_baseline_artifacts,
)


def test_build_rider_season_panel_merges_enrichments_and_next_targets(tmp_path: Path) -> None:
    import_root = tmp_path / "imported"
    _build_rider_import_root(import_root)

    panel = build_rider_season_panel(import_root=import_root)

    alpha_row = panel.loc[
        (panel["season"] == 2021) & (panel["rider_slug"] == "rider-alpha")
    ].iloc[0]
    beta_row = panel.loc[
        (panel["season"] == 2021) & (panel["rider_slug"] == "rider-beta")
    ].iloc[0]

    assert int(alpha_row["team_n_riders_150_plus"]) == 1
    assert bool(alpha_row["result_summary_available"]) is True
    assert int(alpha_row["n_scoring_results"]) == 4
    assert bool(alpha_row["transfer_context_available"]) is True
    assert float(alpha_row["age_on_jan_1"]) == 24.5
    assert bool(alpha_row["has_observed_next_season"]) is True
    assert int(alpha_row["rider_reaches_150_next_season"]) == 1
    assert bool(alpha_row["same_team_base_next_season"]) is True
    assert bool(beta_row["has_observed_next_season"]) is False
    assert pd.isna(beta_row["rider_reaches_150_next_season"])


def test_build_rider_season_panel_keeps_current_team_context_in_season_space(tmp_path: Path) -> None:
    import_root = tmp_path / "imported"
    _build_rider_import_root(import_root)
    current_snapshot_df = pd.DataFrame(
        [
            {
                "scope": "current",
                "team_rank": 20,
                "team_name": "Team A 2026",
                "team_slug": "team-a-2026",
                "team_class": "PRT",
                "ranking_total_points": 180.0,
                "team_total_points": 180.0,
                "sanction_points_total": 0.0,
                "season_year": 2026,
                "rider_name": "Filler Rider 2026",
                "rider_slug": "filler-rider-2026",
                "team_rank_within_counted_list": 1,
                "points_counted": 120.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
                "is_placeholder_team_row": False,
            },
            {
                "scope": "current",
                "team_rank": 20,
                "team_name": "Team A 2026",
                "team_slug": "team-a-2026",
                "team_class": "PRT",
                "ranking_total_points": 180.0,
                "team_total_points": 180.0,
                "sanction_points_total": 0.0,
                "season_year": 2026,
                "rider_name": "Support Rider",
                "rider_slug": "support-rider",
                "team_rank_within_counted_list": 2,
                "points_counted": 60.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
                "is_placeholder_team_row": False,
            },
        ]
    )

    panel = build_rider_season_panel(import_root=import_root, current_snapshot_df=current_snapshot_df)

    current_row = panel.loc[
        (panel["season"] == 2026) & (panel["rider_slug"] == "filler-rider-2026")
    ].iloc[0]
    assert float(current_row["team_points_total"]) == 300.0
    assert int(current_row["team_n_riders_100_plus"]) == 1
    assert int(current_row["team_n_riders_150_plus"]) == 0
    assert float(current_row["uci_points"]) == 90.0


def test_fit_rider_threshold_baseline_learns_positive_points_signal() -> None:
    rider_panel = _synthetic_rider_panel()

    result = fit_rider_threshold_baseline(
        rider_panel,
        feature_columns=("uci_points",),
        model_name="baseline_prior_points",
    )

    assert result.converged
    assert result.coefficients["uci_points"] > 0
    assert result.in_sample_metrics["accuracy"] >= 0.8
    assert result.expanding_window_summary["eligible"] is True
    assert result.expanding_window_summary["test_seasons"] == [2023, 2024, 2025]


def test_score_rider_threshold_dataset_adds_probability_and_rank_columns() -> None:
    rider_panel = _synthetic_rider_panel()
    result = fit_rider_threshold_baseline(
        rider_panel,
        feature_columns=("uci_points",),
        model_name="baseline_prior_points",
    )

    scored = score_rider_threshold_dataset(
        rider_panel[rider_panel["season"] == 2024],
        result,
        evaluation_split="full_fit_panel",
        ranking_group_column="season",
    )

    assert "predicted_rider_reaches_150_probability" in scored.columns
    assert scored["predicted_rider_reaches_150_probability"].between(0.0, 1.0).all()
    assert set(scored["predicted_probability_rank"].dropna().astype(int)) == {1, 2, 3, 4}


def test_build_and_write_rider_threshold_baseline_artifacts(tmp_path: Path) -> None:
    rider_panel = _synthetic_rider_panel()

    summary, predictions, panel_scores = build_rider_threshold_baseline_artifacts(rider_panel)
    written_paths = write_rider_threshold_baseline_artifacts(
        summary,
        predictions,
        panel_scores=panel_scores,
        output_root=tmp_path / "model_outputs",
    )

    assert summary["anchor_model_name"] == "baseline_prior_points"
    assert len(summary["model_results"]) == 2
    assert {"full_fit", "expanding_window_test"} <= set(predictions["evaluation_split"])
    assert set(panel_scores["evaluation_split"]) == {"full_fit_panel"}
    assert all(path.exists() for path in written_paths.values())


def test_fit_rider_threshold_baseline_suite_returns_both_specs() -> None:
    rider_panel = _synthetic_rider_panel()

    results = fit_rider_threshold_baseline_suite(rider_panel)

    assert [result.model_name for result in results] == [
        "baseline_prior_points",
        "baseline_points_scoring_role",
    ]


def _build_rider_import_root(import_root: Path) -> None:
    team_rows = [
            {
                "season_year": 2021,
                "team_name": "Team A 2021",
                "team_slug": "team-a-2021",
                "team_rank": 4,
                "team_total_uci_points": 500.0,
                "top1_share": 0.30,
                "top3_share": 0.70,
                "top5_share": 0.90,
                "n_riders_100": 2,
                "n_riders_150": 1,
                "n_riders_250": 0,
                "n_riders_400": 0,
            },
            {
                "season_year": 2022,
                "team_name": "Team A 2022",
                "team_slug": "team-a-2022",
                "team_rank": 3,
                "team_total_uci_points": 640.0,
                "top1_share": 0.28,
                "top3_share": 0.68,
                "top5_share": 0.88,
                "n_riders_100": 2,
                "n_riders_150": 1,
                "n_riders_250": 0,
                "n_riders_400": 0,
            },
        ]
    team_rows.extend(
        {
            "season_year": season,
            "team_name": f"Team A {season}",
            "team_slug": f"team-a-{season}",
            "team_rank": 5,
            "team_total_uci_points": 300.0,
            "top1_share": 0.40,
            "top3_share": 0.80,
            "top5_share": 1.00,
            "n_riders_100": 1,
            "n_riders_150": 0,
            "n_riders_250": 0,
            "n_riders_400": 0,
        }
        for season in range(2023, 2027)
    )
    _write_csv(
        import_root / "historical_proteam_team_panel.csv",
        team_rows,
        [
            "season_year",
            "team_name",
            "team_slug",
            "team_rank",
            "team_total_uci_points",
            "top1_share",
            "top3_share",
            "top5_share",
            "n_riders_100",
            "n_riders_150",
            "n_riders_250",
            "n_riders_400",
        ],
    )
    rider_rows = [
            {
                "season_year": 2021,
                "team_name": "Team A 2021",
                "team_slug": "team-a-2021",
                "team_class": "PRT",
                "rider_name": "Rider Alpha",
                "rider_slug": "rider-alpha",
                "uci_points": 120.0,
                "pcs_points": 90.0,
                "racedays": 40.0,
                "wins": 1.0,
                "points_per_raceday": 3.0,
                "team_total_uci_points": 500.0,
                "team_rank_within_roster": 1,
                "team_points_share": 0.24,
                "archetype": "anchor",
            },
            {
                "season_year": 2021,
                "team_name": "Team A 2021",
                "team_slug": "team-a-2021",
                "team_class": "PRT",
                "rider_name": "Rider Beta",
                "rider_slug": "rider-beta",
                "uci_points": 35.0,
                "pcs_points": 20.0,
                "racedays": 38.0,
                "wins": 0.0,
                "points_per_raceday": 0.921053,
                "team_total_uci_points": 500.0,
                "team_rank_within_roster": 2,
                "team_points_share": 0.07,
                "archetype": "engine",
            },
            {
                "season_year": 2022,
                "team_name": "Team A 2022",
                "team_slug": "team-a-2022",
                "team_class": "PRT",
                "rider_name": "Rider Alpha",
                "rider_slug": "rider-alpha",
                "uci_points": 180.0,
                "pcs_points": 110.0,
                "racedays": 45.0,
                "wins": 2.0,
                "points_per_raceday": 4.0,
                "team_total_uci_points": 640.0,
                "team_rank_within_roster": 1,
                "team_points_share": 0.28125,
                "archetype": "anchor",
            },
        ]
    rider_rows.extend(
        {
            "season_year": season,
            "team_name": f"Team A {season}",
            "team_slug": f"team-a-{season}",
            "team_class": "PRT",
            "rider_name": f"Filler Rider {season}",
            "rider_slug": f"filler-rider-{season}",
            "uci_points": 90.0,
            "pcs_points": 50.0,
            "racedays": 35.0,
            "wins": 0.0,
            "points_per_raceday": 90.0 / 35.0,
            "team_total_uci_points": 300.0,
            "team_rank_within_roster": 1,
            "team_points_share": 0.30,
            "archetype": "engine",
        }
        for season in range(2023, 2027)
    )
    _write_csv(
        import_root / "historical_proteam_rider_panel.csv",
        rider_rows,
        [
            "season_year",
            "team_name",
            "team_slug",
            "team_class",
            "rider_name",
            "rider_slug",
            "uci_points",
            "pcs_points",
            "racedays",
            "wins",
            "points_per_raceday",
            "team_total_uci_points",
            "team_rank_within_roster",
            "team_points_share",
            "archetype",
        ],
    )
    summary_rows = [
            {
                "season_year": 2021,
                "rider_slug": "rider-alpha",
                "team_slug": "team-a-2021",
                "total_uci_points_detailed": 120.0,
                "total_pcs_points_detailed": 90.0,
                "uci_point_diff_vs_panel": 0.0,
                "points_match_within_1": True,
                "gap_classification": "match_within_1",
                "n_starts": 30,
                "n_started": 30,
                "n_finished": 26,
                "n_dnf": 4,
                "n_dns": 0,
                "n_wins": 1,
                "n_podiums": 2,
                "n_top10s": 6,
                "n_scoring_results": 4,
                "uci_points_from_stages": 10.0,
                "uci_points_from_gc": 20.0,
                "uci_points_from_one_day": 90.0,
                "uci_points_from_secondary_classifications": 0.0,
            },
            {
                "season_year": 2021,
                "rider_slug": "rider-beta",
                "team_slug": "team-a-2021",
                "total_uci_points_detailed": 35.0,
                "total_pcs_points_detailed": 20.0,
                "uci_point_diff_vs_panel": 0.0,
                "points_match_within_1": True,
                "gap_classification": "match_within_1",
                "n_starts": 28,
                "n_started": 28,
                "n_finished": 24,
                "n_dnf": 4,
                "n_dns": 0,
                "n_wins": 0,
                "n_podiums": 0,
                "n_top10s": 1,
                "n_scoring_results": 1,
                "uci_points_from_stages": 0.0,
                "uci_points_from_gc": 5.0,
                "uci_points_from_one_day": 30.0,
                "uci_points_from_secondary_classifications": 0.0,
            },
            {
                "season_year": 2022,
                "rider_slug": "rider-alpha",
                "team_slug": "team-a-2022",
                "total_uci_points_detailed": 180.0,
                "total_pcs_points_detailed": 110.0,
                "uci_point_diff_vs_panel": 0.0,
                "points_match_within_1": True,
                "gap_classification": "match_within_1",
                "n_starts": 32,
                "n_started": 32,
                "n_finished": 30,
                "n_dnf": 2,
                "n_dns": 0,
                "n_wins": 2,
                "n_podiums": 3,
                "n_top10s": 9,
                "n_scoring_results": 6,
                "uci_points_from_stages": 25.0,
                "uci_points_from_gc": 35.0,
                "uci_points_from_one_day": 120.0,
                "uci_points_from_secondary_classifications": 0.0,
            },
        ]
    summary_rows.extend(
        {
            "season_year": season,
            "rider_slug": f"filler-rider-{season}",
            "team_slug": f"team-a-{season}",
            "total_uci_points_detailed": 90.0,
            "total_pcs_points_detailed": 50.0,
            "uci_point_diff_vs_panel": 0.0,
            "points_match_within_1": True,
            "gap_classification": "match_within_1",
            "n_starts": 25,
            "n_started": 25,
            "n_finished": 22,
            "n_dnf": 3,
            "n_dns": 0,
            "n_wins": 0,
            "n_podiums": 0,
            "n_top10s": 2,
            "n_scoring_results": 2,
            "uci_points_from_stages": 0.0,
            "uci_points_from_gc": 15.0,
            "uci_points_from_one_day": 75.0,
            "uci_points_from_secondary_classifications": 0.0,
        }
        for season in range(2023, 2026)
    )
    _write_csv(
        import_root / "rider_season_result_summary.csv",
        summary_rows,
        [
            "season_year",
            "rider_slug",
            "team_slug",
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
            "uci_points_from_stages",
            "uci_points_from_gc",
            "uci_points_from_one_day",
            "uci_points_from_secondary_classifications",
        ],
    )
    _write_csv(
        import_root / "rider_transfer_context_enriched.csv",
        [
            {
                "rider_slug": "rider-alpha",
                "year_from": 2020,
                "year_to": 2021,
                "team_from_slug": "team-z-2020",
                "team_to_slug": "team-a-2021",
                "prior_year_uci_points": 80.0,
                "prior_year_n_starts": 22,
                "prior_year_scored_150_flag": False,
                "age_on_jan_1": 24.5,
                "specialty_primary": "oneday",
                "transfer_step_label": "step_up",
                "had_prior_year_trainee_with_team_to": False,
            }
        ],
        [
            "rider_slug",
            "year_from",
            "year_to",
            "team_from_slug",
            "team_to_slug",
            "prior_year_uci_points",
            "prior_year_n_starts",
            "prior_year_scored_150_flag",
            "age_on_jan_1",
            "specialty_primary",
            "transfer_step_label",
            "had_prior_year_trainee_with_team_to",
        ],
    )


def _synthetic_rider_panel() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rider_id = 1
    season_templates = {
        2022: [
            ("Rider Alpha", 230, 10, 1, 1),
            ("Rider Beta", 180, 7, 2, 1),
            ("Rider Gamma", 85, 3, 7, 0),
            ("Rider Delta", 25, 1, 12, 0),
        ],
        2023: [
            ("Rider Epsilon", 260, 11, 1, 1),
            ("Rider Zeta", 170, 6, 3, 1),
            ("Rider Eta", 90, 3, 8, 0),
            ("Rider Theta", 35, 1, 13, 0),
        ],
        2024: [
            ("Rider Iota", 275, 12, 1, 1),
            ("Rider Kappa", 165, 6, 4, 1),
            ("Rider Lambda", 92, 4, 9, 0),
            ("Rider Mu", 40, 1, 14, 0),
        ],
        2025: [
            ("Rider Nu", 290, 12, 1, 1),
            ("Rider Xi", 175, 7, 3, 1),
            ("Rider Omicron", 96, 4, 8, 0),
            ("Rider Pi", 45, 1, 15, 0),
        ],
    }
    for next_season, template_rows in season_templates.items():
        for rider_name, points, scoring_results, team_rank, target in template_rows:
            rows.append(
                {
                    "season": next_season - 1,
                    "next_season": next_season,
                    "rider_name": rider_name,
                    "rider_slug": f"rider-{rider_id}",
                    "uci_points": points,
                    "n_scoring_results": scoring_results,
                    "team_rank_within_roster": team_rank,
                    "rider_reaches_150_next_season": target,
                }
            )
            rider_id += 1
    return pd.DataFrame(rows)


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
