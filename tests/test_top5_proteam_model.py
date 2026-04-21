from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from uci_points_model.top5_proteam_model import (
    build_top5_proteam_baseline_artifacts,
    build_top5_proteam_training_table,
    fit_top5_proteam_baseline,
    fit_top5_proteam_baseline_suite,
    score_top5_proteam_dataset,
    write_top5_proteam_baseline_artifacts,
)


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _build_import_root(import_root: Path) -> None:
    _write_csv(
        import_root / "historical_proteam_team_panel.csv",
        [
            {
                "season_year": 2021,
                "team_name": "Team A 2021",
                "team_slug": "team-a-2021",
                "team_class": "PRT",
                "team_rank": 6,
                "team_total_uci_points": 590.0,
                "top1_share": 200.0 / 590.0,
                "top3_share": 470.0 / 590.0,
                "top5_share": 570.0 / 590.0,
                "n_riders_100": 3,
                "n_riders_150": 2,
                "n_riders_250": 0,
                "n_riders_400": 0,
                "avg_points_per_raceday": 3.0,
                "median_points_per_raceday": 1.0,
                "team_points_per_rider_raceday": 3.5,
                "archetype_anchor_count": 1,
                "archetype_engine_count": 2,
                "archetype_banker_count": 0,
            },
            {
                "season_year": 2022,
                "team_name": "Team A 2022",
                "team_slug": "team-a-2022",
                "team_class": "PRT",
                "team_rank": 4,
                "team_total_uci_points": 490.0,
                "top1_share": 300.0 / 490.0,
                "top3_share": 440.0 / 490.0,
                "top5_share": 1.0,
                "n_riders_100": 1,
                "n_riders_150": 1,
                "n_riders_250": 1,
                "n_riders_400": 0,
                "avg_points_per_raceday": 4.0,
                "median_points_per_raceday": 1.2,
                "team_points_per_rider_raceday": 4.2,
                "archetype_anchor_count": 1,
                "archetype_engine_count": 1,
                "archetype_banker_count": 1,
            },
        ],
        [
            "season_year",
            "team_name",
            "team_slug",
            "team_class",
            "team_rank",
            "team_total_uci_points",
            "top1_share",
            "top3_share",
            "top5_share",
            "n_riders_100",
            "n_riders_150",
            "n_riders_250",
            "n_riders_400",
            "avg_points_per_raceday",
            "median_points_per_raceday",
            "team_points_per_rider_raceday",
            "archetype_anchor_count",
            "archetype_engine_count",
            "archetype_banker_count",
        ],
    )
    team_panel_path = import_root / "historical_proteam_team_panel.csv"
    team_panel_df = pd.read_csv(team_panel_path)
    filler_team_rows = pd.DataFrame(
        [
            {
                "season_year": season,
                "team_name": f"Team A {season}",
                "team_slug": f"team-a-{season}",
                "team_class": "PRT",
                "team_rank": 5,
                "team_total_uci_points": 100.0,
                "top1_share": 1.0,
                "top3_share": 1.0,
                "top5_share": 1.0,
                "n_riders_100": 1,
                "n_riders_150": 0,
                "n_riders_250": 0,
                "n_riders_400": 0,
                "avg_points_per_raceday": 2.0,
                "median_points_per_raceday": 2.0,
                "team_points_per_rider_raceday": 2.0,
                "archetype_anchor_count": 1,
                "archetype_engine_count": 0,
                "archetype_banker_count": 0,
            }
            for season in range(2023, 2027)
        ]
    )
    pd.concat([team_panel_df, filler_team_rows], ignore_index=True).to_csv(team_panel_path, index=False)
    _write_csv(
        import_root / "historical_proteam_rider_panel.csv",
        [
            {
                "season_year": 2021,
                "team_name": "Team A 2021",
                "team_slug": "team-a-2021",
                "team_class": "PRT",
                "rider_name": name,
                "rider_slug": slug,
                "uci_points": points,
                "pcs_points": 0.0,
                "racedays": 50.0,
                "wins": 0.0,
                "points_per_raceday": points / 50.0,
                "team_total_uci_points": 590.0,
                "team_rank_within_roster": rank,
                "team_points_share": points / 590.0,
                "archetype": "mixed",
                "source_points_url": "",
                "source_racedays_url": "",
                "scraped_at": "2026-04-20T00:00:00+00:00",
                "parse_status": "ok",
            }
            for rank, (name, slug, points) in enumerate(
                [
                    ("Rider 1", "r1", 200.0),
                    ("Rider 2", "r2", 150.0),
                    ("Rider 3", "r3", 120.0),
                    ("Rider 4", "r4", 60.0),
                    ("Rider 5", "r5", 40.0),
                    ("Rider 6", "r6", 20.0),
                ],
                start=1,
            )
        ]
        + [
            {
                "season_year": 2022,
                "team_name": "Team A 2022",
                "team_slug": "team-a-2022",
                "team_class": "PRT",
                "rider_name": name,
                "rider_slug": slug,
                "uci_points": points,
                "pcs_points": 0.0,
                "racedays": 50.0,
                "wins": 0.0,
                "points_per_raceday": points / 50.0,
                "team_total_uci_points": 490.0,
                "team_rank_within_roster": rank,
                "team_points_share": points / 490.0,
                "archetype": "mixed",
                "source_points_url": "",
                "source_racedays_url": "",
                "scraped_at": "2026-04-20T00:00:00+00:00",
                "parse_status": "ok",
            }
            for rank, (name, slug, points) in enumerate(
                [
                    ("Rider 7", "r7", 300.0),
                    ("Rider 8", "r8", 90.0),
                    ("Rider 9", "r9", 50.0),
                    ("Rider 10", "r10", 40.0),
                    ("Rider 11", "r11", 10.0),
                ],
                start=1,
            )
        ],
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
            "source_points_url",
            "source_racedays_url",
            "scraped_at",
            "parse_status",
        ],
    )
    rider_panel_path = import_root / "historical_proteam_rider_panel.csv"
    rider_panel_df = pd.read_csv(rider_panel_path)
    filler_rider_rows = pd.DataFrame(
        [
            {
                "season_year": season,
                "team_name": f"Team A {season}",
                "team_slug": f"team-a-{season}",
                "team_class": "PRT",
                "rider_name": f"Filler Rider {season}",
                "rider_slug": f"filler-{season}",
                "uci_points": 100.0,
                "pcs_points": 0.0,
                "racedays": 50.0,
                "wins": 0.0,
                "points_per_raceday": 2.0,
                "team_total_uci_points": 100.0,
                "team_rank_within_roster": 1,
                "team_points_share": 1.0,
                "archetype": "anchor",
                "source_points_url": "",
                "source_racedays_url": "",
                "scraped_at": "2026-04-20T00:00:00+00:00",
                "parse_status": "ok",
            }
            for season in range(2023, 2027)
        ]
    )
    pd.concat([rider_panel_df, filler_rider_rows], ignore_index=True).to_csv(rider_panel_path, index=False)
    _write_csv(
        import_root / "transition_continuity_links.csv",
        [
            {
                "year_b": 2022,
                "next_team_slug": "team-a-2022",
                "next_team_name": "Team A 2022",
                "prior_team_slug": "team-a-2021",
                "year_a": 2021,
                "continuity_source": "pcs_prev_link",
                "cache_path": "/tmp/team-a-2022.md",
                "matched_prior_team": 1,
            },
            {
                "year_b": 2023,
                "next_team_slug": "team-a-2023",
                "next_team_name": "Team A 2023",
                "prior_team_slug": "team-a-2022",
                "year_a": 2022,
                "continuity_source": "pcs_prev_link",
                "cache_path": "/tmp/team-a-2023.md",
                "matched_prior_team": 1,
            },
        ],
        [
            "year_b",
            "next_team_slug",
            "next_team_name",
            "prior_team_slug",
            "year_a",
            "continuity_source",
            "cache_path",
            "matched_prior_team",
        ],
    )
    _write_csv(
        import_root / "ranking_predictor_study_data.csv",
        [
            {
                "team": "Team A 2021",
                "prior_team_base": "team-a",
                "year_a": 2021,
                "year_b": 2022,
                "prior_team_slug": "team-a-2021",
                "next_team_slug": "team-a-2022",
                "next_team_name": "Team A 2022",
                "continuity_source": "pcs_prev_link",
                "prior_total_pts": 590.0,
                "prior_rank": 6,
                "prior_n_scorers": 6,
                "prior_n_riders_150": 2,
                "prior_n_riders_250": 0,
                "prior_top1_share": 200.0 / 590.0,
                "prior_top3_share": 470.0 / 590.0,
                "prior_top5_share": 570.0 / 590.0,
                "prior_hhi": 0.0,
                "prior_eff_n": 0.0,
                "prior_gini": 0.0,
                "prior_avg_points_per_raceday": 3.0,
                "prior_team_points_per_rider_raceday": 3.5,
                "prior_archetype_anchor_count": 1,
                "prior_archetype_engine_count": 2,
                "prior_archetype_banker_count": 0,
                "rank_change": -2,
                "pts_change": -100.0,
                "next_rank": 4,
                "next_pts": 490.0,
                "next_top3": 0,
                "next_top5": 1,
                "next_top8": 1,
            }
        ],
        [
            "team",
            "prior_team_base",
            "year_a",
            "year_b",
            "prior_team_slug",
            "next_team_slug",
            "next_team_name",
            "continuity_source",
            "prior_total_pts",
            "prior_rank",
            "prior_n_scorers",
            "prior_n_riders_150",
            "prior_n_riders_250",
            "prior_top1_share",
            "prior_top3_share",
            "prior_top5_share",
            "prior_hhi",
            "prior_eff_n",
            "prior_gini",
            "prior_avg_points_per_raceday",
            "prior_team_points_per_rider_raceday",
            "prior_archetype_anchor_count",
            "prior_archetype_engine_count",
            "prior_archetype_banker_count",
            "rank_change",
            "pts_change",
            "next_rank",
            "next_pts",
            "next_top3",
            "next_top5",
            "next_top8",
        ],
    )


def test_build_top5_proteam_training_table_filters_to_observed_transitions(tmp_path: Path) -> None:
    import_root = tmp_path / "imported"
    _build_import_root(import_root)

    training_df = build_top5_proteam_training_table(import_root=import_root)

    assert len(training_df) == 1
    row = training_df.iloc[0]
    assert int(row["prior_season"]) == 2021
    assert row["prior_team_slug"] == "team-a-2021"
    assert int(row["next_season"]) == 2022
    assert int(row["next_top5_proteam"]) == 1
    assert int(row["prior_n_riders_150"]) == 2
    assert row["target_source"] == "ranking_predictor_study_data"


def test_fit_top5_proteam_baseline_learns_positive_depth_signal() -> None:
    training_df = _synthetic_training_frame()

    result = fit_top5_proteam_baseline(
        training_df,
        feature_columns=("n_riders_150_plus",),
        model_name="baseline_n_riders_150",
    )

    assert result.converged
    assert result.coefficients["n_riders_150_plus"] > 0
    assert result.in_sample_metrics["accuracy"] >= 0.8
    assert result.expanding_window_summary["eligible"] is True
    assert result.expanding_window_summary["test_seasons"] == [2023, 2024, 2025]
    assert result.expanding_window_summary["top_k_capture"] >= 0.8


def test_score_top5_proteam_dataset_adds_probability_and_rank_columns() -> None:
    training_df = _synthetic_training_frame()
    result = fit_top5_proteam_baseline(
        training_df,
        feature_columns=("n_riders_150_plus",),
        model_name="baseline_n_riders_150",
    )

    scored = score_top5_proteam_dataset(
        training_df[training_df["next_season"] == 2025],
        result,
        evaluation_split="full_fit",
        ranking_group_column="next_season",
    )

    assert "predicted_next_top5_probability" in scored.columns
    assert "predicted_probability_rank" in scored.columns
    assert scored["predicted_next_top5_probability"].between(0.0, 1.0).all()
    assert set(scored["predicted_probability_rank"].dropna().astype(int)) == {1, 2, 3, 4}


def test_fit_top5_proteam_baseline_rejects_constant_target() -> None:
    training_df = _synthetic_training_frame()
    training_df["next_top5_proteam"] = 0

    with pytest.raises(ValueError, match="both positive and negative"):
        fit_top5_proteam_baseline(
            training_df,
            feature_columns=("n_riders_150_plus",),
            model_name="baseline_n_riders_150",
        )


def test_build_and_write_top5_proteam_baseline_artifacts(tmp_path: Path) -> None:
    training_df = _synthetic_training_frame()
    team_panel_df = training_df.rename(columns={"prior_season": "season"}).copy()

    summary, predictions, team_panel_scores = build_top5_proteam_baseline_artifacts(
        training_df,
        team_panel_df=team_panel_df,
    )
    written_paths = write_top5_proteam_baseline_artifacts(
        summary,
        predictions,
        team_panel_scores=team_panel_scores,
        output_root=tmp_path / "model_outputs",
    )

    assert summary["anchor_model_name"] == "baseline_n_riders_150"
    assert len(summary["model_results"]) == 2
    assert {"full_fit", "expanding_window_test"} <= set(predictions["evaluation_split"])
    assert set(team_panel_scores["evaluation_split"]) == {"full_fit_team_panel"}
    assert written_paths["summary_path"].exists()
    assert written_paths["predictions_path"].exists()
    assert written_paths["team_panel_scores_path"].exists()


def test_fit_top5_proteam_baseline_suite_returns_both_specs() -> None:
    training_df = _synthetic_training_frame()

    results = fit_top5_proteam_baseline_suite(training_df)

    assert [result.model_name for result in results] == [
        "baseline_n_riders_150",
        "baseline_depth_concentration",
    ]


def _synthetic_training_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    team_id = 1
    season_templates = {
        2022: [
            ("Depth Alpha", 10, 0.58, 12.5, 1),
            ("Depth Beta", 8, 0.60, 11.1, 1),
            ("Thin Gamma", 3, 0.79, 6.8, 0),
            ("Thin Delta", 1, 0.86, 4.9, 0),
        ],
        2023: [
            ("Depth Epsilon", 11, 0.56, 13.1, 1),
            ("Depth Zeta", 9, 0.62, 10.8, 1),
            ("Thin Eta", 4, 0.77, 6.4, 0),
            ("Thin Theta", 2, 0.84, 5.1, 0),
        ],
        2024: [
            ("Depth Iota", 12, 0.55, 13.7, 1),
            ("Depth Kappa", 9, 0.61, 11.4, 1),
            ("Thin Lambda", 4, 0.76, 6.7, 0),
            ("Thin Mu", 2, 0.83, 5.0, 0),
        ],
        2025: [
            ("Depth Nu", 13, 0.54, 14.2, 1),
            ("Depth Xi", 10, 0.60, 11.6, 1),
            ("Thin Omicron", 5, 0.74, 7.2, 0),
            ("Thin Pi", 3, 0.81, 5.8, 0),
        ],
    }
    for next_season, template_rows in season_templates.items():
        for team_name, riders_150, top5_share, effective_contributors, target in template_rows:
            rows.append(
                {
                    "prior_season": next_season - 1,
                    "next_season": next_season,
                    "prior_team_name": team_name,
                    "prior_team_slug": f"team-{team_id}",
                    "n_riders_150_plus": riders_150,
                    "top5_share": top5_share,
                    "effective_contributors": effective_contributors,
                    "next_top5_proteam": target,
                }
            )
            team_id += 1
    return pd.DataFrame(rows)
