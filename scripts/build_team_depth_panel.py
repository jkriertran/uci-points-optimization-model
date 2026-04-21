from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.team_depth_features import (  # noqa: E402
    build_team_depth_panel,
    default_team_depth_panel_path,
    write_team_depth_panel,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the canonical historical ProTeam team-season panel."
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Directory containing imported historical ProTeam datasets.",
    )
    parser.add_argument(
        "--out",
        default=str(default_team_depth_panel_path()),
        help="Destination CSV path for the canonical team-season panel.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_team_depth_panel(import_root=args.import_root)
    path = write_team_depth_panel(dataset, args.out)
    print(f"Wrote {len(dataset)} team-season rows to {path}")


if __name__ == "__main__":
    main()
