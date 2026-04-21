from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.team_depth_features import (  # noqa: E402
    build_team_depth_panel,
    default_team_depth_panel_path,
    write_team_depth_panel,
)
from uci_points_model.top5_proteam_model import (  # noqa: E402
    DEFAULT_TOP5_BASELINE_REGULARIZATION,
    build_top5_proteam_baseline_artifacts,
    build_top5_proteam_training_table,
    default_top5_proteam_model_output_root,
    default_top5_proteam_training_table_path,
    write_top5_proteam_baseline_artifacts,
    write_top5_proteam_training_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit the baseline next_top5_proteam logistic models from imported historical team data."
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Imported historical-data landing zone.",
    )
    parser.add_argument(
        "--training-table-path",
        default=str(default_top5_proteam_training_table_path()),
        help="CSV path for the observed top-five ProTeam training table.",
    )
    parser.add_argument(
        "--team-panel-path",
        default=str(default_team_depth_panel_path()),
        help="CSV path for the canonical team-season panel used for full-fit scoring output.",
    )
    parser.add_argument(
        "--output-root",
        default=str(default_top5_proteam_model_output_root()),
        help="Directory for baseline summary and prediction artifacts.",
    )
    parser.add_argument(
        "--regularization",
        type=float,
        default=DEFAULT_TOP5_BASELINE_REGULARIZATION,
        help="L2 regularization strength used for the logistic baselines.",
    )
    parser.add_argument(
        "--skip-team-panel-scores",
        action="store_true",
        help="Skip writing full-fit scores for the canonical team-season panel.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    training_df = _load_or_build_training_table(
        training_table_path=Path(args.training_table_path),
        import_root=args.import_root,
    )
    team_panel_df = None if args.skip_team_panel_scores else _load_or_build_team_panel(
        team_panel_path=Path(args.team_panel_path),
        import_root=args.import_root,
    )

    summary, predictions, team_panel_scores = build_top5_proteam_baseline_artifacts(
        training_df,
        team_panel_df=team_panel_df,
        regularization_strength=args.regularization,
    )
    written_paths = write_top5_proteam_baseline_artifacts(
        summary,
        predictions,
        team_panel_scores=team_panel_scores,
        output_root=args.output_root,
    )

    for result in summary["model_results"]:
        in_sample = result["in_sample_metrics"]
        expanding = result["expanding_window_summary"]
        expanding_capture = expanding.get("top_k_capture")
        capture_text = (
            f"{expanding_capture:.3f}"
            if isinstance(expanding_capture, (int, float))
            else "n/a"
        )
        print(
            "FIT"
            f" {result['model_name']}"
            f" features={','.join(result['feature_columns'])}"
            f" train_rows={result['training_rows']}"
            f" accuracy={in_sample['accuracy']:.3f}"
            f" brier={in_sample['brier_score']:.3f}"
            f" expanding_top_k_capture={capture_text}"
        )

    for label, path in written_paths.items():
        print(f"WROTE {label}={path}")


def _load_or_build_training_table(
    *,
    training_table_path: Path,
    import_root: str,
) -> pd.DataFrame:
    if training_table_path.exists():
        return pd.read_csv(training_table_path, low_memory=False)

    training_df = build_top5_proteam_training_table(import_root=import_root)
    write_top5_proteam_training_table(training_df, output_path=training_table_path)
    return training_df


def _load_or_build_team_panel(
    *,
    team_panel_path: Path,
    import_root: str,
) -> pd.DataFrame:
    if team_panel_path.exists():
        return pd.read_csv(team_panel_path, low_memory=False)

    team_panel_df = build_team_depth_panel(import_root=import_root)
    write_team_depth_panel(team_panel_df, output_path=team_panel_path)
    return team_panel_df


if __name__ == "__main__":
    main()
