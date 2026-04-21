from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.history_missing_audit import DEFAULT_AUDIT_OUTPUT_ROOT, DEFAULT_TEAM_EV_ROOT  # noqa: E402
from uci_points_model.history_missing_backfill import (  # noqa: E402
    build_history_missing_backfill_priority_list,
    write_history_missing_backfill_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a prioritized backfill list for completed no-fallback history_missing EV races."
    )
    parser.add_argument(
        "--team-ev-root",
        default=str(DEFAULT_TEAM_EV_ROOT),
        help="Directory containing saved *_calendar_ev.csv files.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_AUDIT_OUTPUT_ROOT),
        help="Directory for the Markdown report, summary JSON, and CSV outputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = build_history_missing_backfill_priority_list(team_ev_root=args.team_ev_root)
    written_paths = write_history_missing_backfill_artifacts(
        artifacts,
        output_root=args.output_root,
    )

    print(
        "HISTORY_MISSING_BACKFILL"
        f" unique_races={artifacts.summary['unique_backfill_races']}"
        f" p1={artifacts.summary['p1_races']}"
        f" p2={artifacts.summary['p2_races']}"
        f" p3={artifacts.summary['p3_races']}"
        f" top_race={artifacts.summary['top_priority_race']}"
    )
    for label, path in written_paths.items():
        print(f"WROTE {label}={path}")


if __name__ == "__main__":
    main()
