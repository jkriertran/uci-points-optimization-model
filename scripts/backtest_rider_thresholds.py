from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.rider_threshold_backtest import (  # noqa: E402
    build_rider_threshold_backtest_artifacts,
    write_rider_threshold_backtest_artifacts,
)
from uci_points_model.rider_threshold_model import (  # noqa: E402
    DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    build_rider_season_panel,
    default_rider_season_panel_path,
    default_rider_threshold_output_root,
    write_rider_season_panel,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run expanding-window backtests for the rider threshold baseline models."
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Imported historical-data landing zone.",
    )
    parser.add_argument(
        "--panel-path",
        default=str(default_rider_season_panel_path()),
        help="CSV path for the rider-season panel.",
    )
    parser.add_argument(
        "--output-root",
        default=str(default_rider_threshold_output_root()),
        help="Directory for rider-threshold backtest summary, CSVs, and Markdown report.",
    )
    parser.add_argument(
        "--regularization",
        type=float,
        default=DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
        help="L2 regularization strength used for the logistic baselines.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rider_panel = _load_or_build_panel(
        panel_path=Path(args.panel_path),
        import_root=args.import_root,
    )
    artifacts = build_rider_threshold_backtest_artifacts(
        rider_panel,
        regularization_strength=args.regularization,
    )
    written_paths = write_rider_threshold_backtest_artifacts(
        artifacts,
        output_root=args.output_root,
    )

    winner_row = artifacts.benchmark_table.iloc[0]
    print(
        "BACKTEST"
        f" winner={winner_row['model_name']}"
        f" capture={winner_row['backtest_top_k_capture']:.3f}"
        f" brier={winner_row['backtest_brier_score']:.3f}"
        f" accuracy={winner_row['backtest_accuracy']:.3f}"
    )
    for _, row in artifacts.benchmark_table.iterrows():
        print(
            "MODEL"
            f" {row['model_name']}"
            f" features={row['feature_columns']}"
            f" capture={row['backtest_top_k_capture']:.3f}"
            f" brier={row['backtest_brier_score']:.3f}"
            f" folds={int(row['backtest_fold_count'])}"
        )
    for label, path in written_paths.items():
        print(f"WROTE {label}={path}")


def _load_or_build_panel(
    *,
    panel_path: Path,
    import_root: str,
) -> pd.DataFrame:
    if panel_path.exists():
        return pd.read_csv(panel_path, low_memory=False)

    panel = build_rider_season_panel(import_root=import_root)
    write_rider_season_panel(panel, output_path=panel_path)
    return panel


if __name__ == "__main__":
    main()
