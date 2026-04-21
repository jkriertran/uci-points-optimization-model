from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.rider_threshold_model import (  # noqa: E402
    build_rider_season_panel,
    default_rider_season_panel_path,
    write_rider_season_panel,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the canonical rider-season panel from imported historical ProTeam rider data."
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Imported historical-data landing zone.",
    )
    parser.add_argument(
        "--output-path",
        default=str(default_rider_season_panel_path()),
        help="CSV path for the rider-season panel.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    panel = build_rider_season_panel(import_root=args.import_root)
    output_path = write_rider_season_panel(panel, output_path=args.output_path)
    observed_rows = int(panel["has_observed_next_season"].fillna(False).astype(bool).sum())
    positive_rows = int(panel["rider_reaches_150_next_season"].fillna(0).sum())
    print(f"Wrote rider-season panel to {output_path}")
    print(
        "Rows="
        f"{len(panel)} observed_next={observed_rows} "
        f"target_150_positive={positive_rows}"
    )


if __name__ == "__main__":
    main()
