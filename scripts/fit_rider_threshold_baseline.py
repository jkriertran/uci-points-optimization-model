from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.rider_threshold_model import (  # noqa: E402
    DEFAULT_RIDER_THRESHOLD_REGULARIZATION,
    build_rider_season_panel,
    build_rider_threshold_baseline_artifacts,
    default_rider_season_panel_path,
    default_rider_threshold_output_root,
    write_rider_season_panel,
    write_rider_threshold_baseline_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit baseline rider threshold models for rider_reaches_150_next_season."
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
        help="Directory for rider-threshold model artifacts.",
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
    summary, predictions, panel_scores = build_rider_threshold_baseline_artifacts(
        rider_panel,
        regularization_strength=args.regularization,
    )
    written_paths = write_rider_threshold_baseline_artifacts(
        summary,
        predictions,
        panel_scores=panel_scores,
        output_root=args.output_root,
    )

    for result in summary["model_results"]:
        in_sample = result["in_sample_metrics"]
        expanding = result["expanding_window_summary"]
        capture = expanding.get("top_k_capture")
        capture_text = f"{capture:.3f}" if isinstance(capture, (int, float)) else "n/a"
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
