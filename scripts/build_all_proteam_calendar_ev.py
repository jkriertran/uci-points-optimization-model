from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.team_calendar_artifacts import (  # noqa: E402
    DEFAULT_TRACKED_PROTEAMS_MANIFEST,
    build_tracked_team_calendar_ev,
    load_tracked_team_configs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build calendar snapshots and EV outputs for tracked 2026 ProTeams.")
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_TRACKED_PROTEAMS_MANIFEST),
        help="CSV manifest of tracked team-season builds.",
    )
    parser.add_argument(
        "--team-slug",
        default=None,
        help="Optional stable team slug filter for building a single manifest row.",
    )
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Optional YYYY-MM-DD override for status calculation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    team_configs = load_tracked_team_configs(args.manifest_path, enabled_only=True)
    outcomes = build_tracked_team_calendar_ev(
        team_configs,
        team_slug=args.team_slug,
        as_of_date=args.as_of_date,
    )
    if args.team_slug and not outcomes:
        raise SystemExit(f"No enabled tracked teams matched {args.team_slug}.")

    print("Tracked team build summary:")
    for outcome in outcomes:
        if outcome.success:
            print(f"SUCCESS {outcome.team_slug}")
        else:
            print(f"FAILED {outcome.team_slug}: {outcome.error}")

    failed_team_slugs = [outcome.team_slug for outcome in outcomes if not outcome.success]
    print(f"Built {len(outcomes) - len(failed_team_slugs)} successful team outputs out of {len(outcomes)} requested teams.")
    print(f"FAILED_TEAM_SLUGS={','.join(failed_team_slugs)}")

    if failed_team_slugs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
