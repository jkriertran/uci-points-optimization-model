from __future__ import annotations

from pathlib import Path

import pandas as pd

from uci_points_model.target_definitions import attach_next_top5_targets, build_next_top5_targets


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _build_import_root(import_root: Path) -> None:
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
                "prior_top1_share": 0.338983,
                "prior_top3_share": 0.79661,
                "prior_top5_share": 0.966102,
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


def test_build_next_top5_targets_preserves_continuity_without_observed_label(tmp_path: Path) -> None:
    import_root = tmp_path / "imported"
    _build_import_root(import_root)

    targets = build_next_top5_targets(import_root=import_root)

    observed_row = targets.loc[targets["prior_team_slug"] == "team-a-2021"].iloc[0]
    continuity_only_row = targets.loc[targets["prior_team_slug"] == "team-a-2022"].iloc[0]

    assert int(observed_row["next_top5_proteam"]) == 1
    assert int(observed_row["next_proteam_rank"]) == 4
    assert observed_row["next_team_slug"] == "team-a-2022"
    assert pd.isna(continuity_only_row["next_top5_proteam"])
    assert continuity_only_row["next_team_slug"] == "team-a-2023"


def test_attach_next_top5_targets_merges_labels_onto_team_panel(tmp_path: Path) -> None:
    import_root = tmp_path / "imported"
    _build_import_root(import_root)
    panel = pd.DataFrame(
        [
            {"season": 2021, "team_slug": "team-a-2021", "team_name": "Team A 2021"},
            {"season": 2022, "team_slug": "team-a-2022", "team_name": "Team A 2022"},
        ]
    )

    enriched = attach_next_top5_targets(panel, import_root=import_root)

    assert list(enriched["next_team_slug"]) == ["team-a-2022", "team-a-2023"]
    assert list(enriched["has_observed_next_season"]) == [True, False]
