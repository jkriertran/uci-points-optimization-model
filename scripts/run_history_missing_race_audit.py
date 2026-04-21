from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.history_missing_audit import (  # noqa: E402
    DEFAULT_AUDIT_OUTPUT_ROOT,
    DEFAULT_TEAM_EV_ROOT,
    run_history_missing_race_audit,
    write_history_missing_audit_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit all saved Team Calendar EV races currently marked history_missing."
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
    artifacts = run_history_missing_race_audit(team_ev_root=args.team_ev_root)
    written_paths = write_history_missing_audit_artifacts(
        artifacts,
        output_root=args.output_root,
    )

    print(
        "HISTORY_MISSING_AUDIT"
        f" teams={artifacts.summary['teams_with_history_missing']}"
        f" races={artifacts.summary['total_history_missing_races']}"
        f" completed={artifacts.summary['completed_history_missing_races']}"
        f" zero_expected={artifacts.summary['history_missing_with_zero_expected']}"
        f" completed_missing_ev_components={artifacts.summary['completed_missing_ev_components']}"
    )
    for label, path in written_paths.items():
        print(f"WROTE {label}={path}")


if __name__ == "__main__":
    main()
