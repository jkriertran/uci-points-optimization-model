from __future__ import annotations

from pathlib import Path

import pandas as pd

from uci_points_model.top5_proteam_backtest import (
    build_top5_proteam_backtest_artifacts,
    write_top5_proteam_backtest_artifacts,
)


def test_build_top5_proteam_backtest_artifacts_returns_leaderboard_and_folds() -> None:
    training_df = _synthetic_training_frame()

    artifacts = build_top5_proteam_backtest_artifacts(training_df)

    assert artifacts.summary["anchor_model_name"] == "baseline_n_riders_150"
    assert artifacts.summary["winning_model_name"] in {
        "baseline_n_riders_150",
        "baseline_depth_concentration",
    }
    assert artifacts.benchmark_table["benchmark_rank"].tolist() == [1, 2]
    assert set(artifacts.benchmark_table["model_name"]) == {
        "baseline_n_riders_150",
        "baseline_depth_concentration",
    }
    assert set(artifacts.fold_table["test_next_season"]) == {2023, 2024, 2025}
    assert set(artifacts.prediction_table["evaluation_split"]) == {"expanding_window_test"}
    assert "Top-5 ProTeam Backtest Report" in artifacts.report_text
    assert "baseline_n_riders_150" in artifacts.report_text


def test_write_top5_proteam_backtest_artifacts_persists_all_outputs(tmp_path: Path) -> None:
    training_df = _synthetic_training_frame()
    artifacts = build_top5_proteam_backtest_artifacts(training_df)

    written_paths = write_top5_proteam_backtest_artifacts(
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
    assert written_paths["report_path"].read_text().startswith("# Top-5 ProTeam Backtest Report")


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
