from __future__ import annotations

from pathlib import Path

import pandas as pd

from uci_points_model.rider_threshold_backtest import (
    build_rider_threshold_backtest_artifacts,
    write_rider_threshold_backtest_artifacts,
)


def test_build_rider_threshold_backtest_artifacts_returns_leaderboard_and_folds() -> None:
    rider_panel = _synthetic_rider_panel()

    artifacts = build_rider_threshold_backtest_artifacts(rider_panel)

    assert artifacts.summary["anchor_model_name"] == "baseline_prior_points"
    assert artifacts.summary["winning_model_name"] in {
        "baseline_prior_points",
        "baseline_points_scoring_role",
    }
    assert artifacts.benchmark_table["benchmark_rank"].tolist() == [1, 2]
    assert set(artifacts.benchmark_table["model_name"]) == {
        "baseline_prior_points",
        "baseline_points_scoring_role",
    }
    assert set(artifacts.fold_table["test_next_season"]) == {2023, 2024, 2025}
    assert set(artifacts.prediction_table["evaluation_split"]) == {"expanding_window_test"}
    assert "Rider Threshold Backtest Report" in artifacts.report_text
    assert "baseline_prior_points" in artifacts.report_text


def test_write_rider_threshold_backtest_artifacts_persists_all_outputs(tmp_path: Path) -> None:
    rider_panel = _synthetic_rider_panel()
    artifacts = build_rider_threshold_backtest_artifacts(rider_panel)

    written_paths = write_rider_threshold_backtest_artifacts(
        artifacts,
        output_root=tmp_path / "model_outputs",
    )

    assert set(written_paths) == {
        "summary_path",
        "benchmark_path",
        "fold_path",
        "predictions_path",
        "report_path",
    }
    assert all(path.exists() for path in written_paths.values())
    assert written_paths["report_path"].read_text().startswith("# Rider Threshold Backtest Report")


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
