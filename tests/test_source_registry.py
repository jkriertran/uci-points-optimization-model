from __future__ import annotations

from pathlib import Path

import pandas as pd

from uci_points_model.data_sources import load_historical_dataset, select_dataset_source
from uci_points_model.historical_data_import import import_historical_proteam_data
from uci_points_model.source_registry import (
    SOURCE_DIRECT_SCRAPE,
    SOURCE_IMPORTED_HISTORY,
    get_source_policy,
)


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def _build_minimal_upstream_source(source_root: Path) -> None:
    team_rows = [
        {
            "season_year": year,
            "team_name": f"Team {year}",
            "team_slug": f"team-{year}",
            "team_rank": 1,
            "team_total_uci_points": 1000.0 + year,
            "top1_share": 0.2,
            "top3_share": 0.5,
            "top5_share": 0.7,
            "n_riders_150": 8,
        }
        for year in range(2021, 2027)
    ]
    _write_csv(
        source_root / "data" / "historical_proteam_team_panel.csv",
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
            "n_riders_150",
        ],
    )

    rider_rows = [
        {
            "season_year": year,
            "team_slug": f"team-{year}",
            "rider_name": f"Rider {year}",
            "rider_slug": f"rider-{year}",
            "uci_points": 200.0,
            "racedays": 50,
            "team_points_share": 0.2,
        }
        for year in range(2021, 2027)
    ]
    _write_csv(
        source_root / "data" / "historical_proteam_rider_panel.csv",
        rider_rows,
        [
            "season_year",
            "team_slug",
            "rider_name",
            "rider_slug",
            "uci_points",
            "racedays",
            "team_points_share",
        ],
    )

    _write_csv(
        source_root / "data" / "procycling_proteam_analysis" / "ranking_predictor_study_data.csv",
        [
            {
                "prior_team_slug": "team-2021",
                "next_team_slug": "team-2022",
                "prior_n_riders_150": 8,
                "next_top5": 1,
            }
        ],
        ["prior_team_slug", "next_team_slug", "prior_n_riders_150", "next_top5"],
    )

    _write_csv(
        source_root / "data" / "procycling_proteam_analysis" / "transition_continuity_links.csv",
        [
            {
                "year_a": 2021,
                "year_b": 2022,
                "prior_team_slug": "team-2021",
                "next_team_slug": "team-2022",
                "matched_prior_team": 1,
            }
        ],
        ["year_a", "year_b", "prior_team_slug", "next_team_slug", "matched_prior_team"],
    )

    _write_csv(
        source_root / "manifests" / "historical_proteam_validation_summary.csv",
        [{"check_name": "duplicate_keys", "status": "pass", "value": 0.0, "notes": ""}],
        ["check_name", "status", "value", "notes"],
    )

    _write_csv(
        source_root / "manifests" / "historical_proteam_missing_pages.csv",
        [],
        [
            "season_year",
            "team_slug",
            "team_name",
            "page_family",
            "source_url",
            "cache_path",
            "status",
            "status_code",
            "inventory_source",
            "seed_path",
            "error_message",
            "scraped_at",
            "credits_used",
        ],
    )

    _write_csv(
        source_root / "data" / "procycling_proteam_analysis" / "rider_season_result_summary.csv",
        [
            {
                "season_year": year,
                "rider_slug": f"rider-{year}",
                "team_slug": f"team-{year}",
                "total_uci_points_detailed": 200.0,
                "n_starts": 30,
                "n_scoring_results": 4,
            }
            for year in range(2021, 2026)
        ],
        [
            "season_year",
            "rider_slug",
            "team_slug",
            "total_uci_points_detailed",
            "n_starts",
            "n_scoring_results",
        ],
    )

    _write_csv(
        source_root / "data" / "procycling_proteam_analysis" / "rider_transfer_context_enriched.csv",
        [
            {
                "rider_slug": "rider-2021",
                "year_from": 2020,
                "year_to": 2021,
                "team_from_slug": "team-2020",
                "team_to_slug": "team-2021",
                "prior_year_uci_points": 100.0,
            }
        ],
        [
            "rider_slug",
            "year_from",
            "year_to",
            "team_from_slug",
            "team_to_slug",
            "prior_year_uci_points",
        ],
    )

    _write_csv(
        source_root / "data" / "procycling_proteam_analysis" / "race_entries_pts_v2.csv",
        [
            {
                "race": "Sample Race",
                "year": 2024,
                "team_norm": "Team 2024",
                "slug": "sample-race",
                "points_scored": 12.0,
            }
        ],
        ["race", "year", "team_norm", "slug", "points_scored"],
    )
    race_page_path = source_root / "data" / "procycling_proteam_analysis" / "race_page_rider_results.csv.gz"
    race_page_path.parent.mkdir(parents=True, exist_ok=True)
    race_page_path.write_bytes(b"placeholder")


def test_historical_team_panel_prefers_imported_history(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    import_root = tmp_path / "imported"
    _build_minimal_upstream_source(source_root)
    import_historical_proteam_data(source_root=source_root, import_root=import_root)

    decision = select_dataset_source(
        dataset_key="historical_proteam_team_panel",
        import_root=import_root,
    )

    assert decision.selected_source == SOURCE_IMPORTED_HISTORY
    dataset, returned_decision = load_historical_dataset(
        dataset_key="historical_proteam_team_panel",
        import_root=import_root,
    )
    assert returned_decision.selected_source == SOURCE_IMPORTED_HISTORY
    assert not dataset.empty
    assert dataset.attrs["source_decision"]["selected_source"] == SOURCE_IMPORTED_HISTORY


def test_historical_team_panel_falls_back_to_direct_scrape_when_import_is_invalid(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    import_root = tmp_path / "imported"
    _build_minimal_upstream_source(source_root)
    import_historical_proteam_data(source_root=source_root, import_root=import_root)

    broken_path = import_root / "historical_proteam_team_panel.csv"
    pd.read_csv(broken_path).drop(columns=["n_riders_150"]).to_csv(broken_path, index=False)

    decision = select_dataset_source(
        dataset_key="historical_proteam_team_panel",
        import_root=import_root,
    )

    assert decision.selected_source == SOURCE_DIRECT_SCRAPE
    assert "direct scrape" in decision.reason.lower()


def test_source_policy_for_historical_team_panel_starts_with_imported_history() -> None:
    policy = get_source_policy("historical_proteam_team_panel")

    assert policy.fallback_order[0] == SOURCE_IMPORTED_HISTORY


def test_optional_rider_result_summary_prefers_imported_history(tmp_path: Path) -> None:
    source_root = tmp_path / "upstream"
    import_root = tmp_path / "imported"
    _build_minimal_upstream_source(source_root)
    import_historical_proteam_data(source_root=source_root, import_root=import_root, include_optional=True)

    decision = select_dataset_source(
        dataset_key="rider_season_result_summary",
        import_root=import_root,
    )

    assert decision.selected_source == SOURCE_IMPORTED_HISTORY
    dataset, returned_decision = load_historical_dataset(
        dataset_key="rider_season_result_summary",
        import_root=import_root,
    )
    assert returned_decision.selected_source == SOURCE_IMPORTED_HISTORY
    assert not dataset.empty
