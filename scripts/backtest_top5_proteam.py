from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.top5_proteam_backtest import (  # noqa: E402
    build_top5_proteam_backtest_artifacts,
    write_top5_proteam_backtest_artifacts,
)
from uci_points_model.top5_proteam_model import (  # noqa: E402
    DEFAULT_TOP5_BASELINE_REGULARIZATION,
    build_top5_proteam_training_table,
    default_top5_proteam_model_output_root,
    default_top5_proteam_training_table_path,
    write_top5_proteam_training_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run expanding-window backtests for the top-five ProTeam baseline models."
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
        "--output-root",
        default=str(default_top5_proteam_model_output_root()),
        help="Directory for backtest summary, CSVs, and Markdown report.",
    )
    parser.add_argument(
        "--regularization",
        type=float,
        default=DEFAULT_TOP5_BASELINE_REGULARIZATION,
        help="L2 regularization strength used for the logistic baselines.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    training_df = _load_or_build_training_table(
        training_table_path=Path(args.training_table_path),
        import_root=args.import_root,
    )
    artifacts = build_top5_proteam_backtest_artifacts(
        training_df,
        regularization_strength=args.regularization,
    )
    written_paths = write_top5_proteam_backtest_artifacts(
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


if __name__ == "__main__":
    main()
