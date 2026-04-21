from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT  # noqa: E402
from uci_points_model.top5_proteam_model import (  # noqa: E402
    build_top5_proteam_training_table,
    default_top5_proteam_training_table_path,
    write_top5_proteam_training_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the top-five ProTeam model training table from canonical team-season history."
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Directory containing imported historical ProTeam datasets.",
    )
    parser.add_argument(
        "--out",
        default=str(default_top5_proteam_training_table_path()),
        help="Destination CSV path for the top-five ProTeam training table.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_top5_proteam_training_table(import_root=args.import_root)
    path = write_top5_proteam_training_table(dataset, args.out)
    print(f"Wrote {len(dataset)} training rows to {path}")


if __name__ == "__main__":
    main()
