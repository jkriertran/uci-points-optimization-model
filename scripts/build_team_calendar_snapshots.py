from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.team_calendar import build_live_team_calendar, build_schedule_changelog
from uci_points_model.team_identity import canonicalize_team_slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build tracked team calendar snapshots and changelog files.")
    parser.add_argument("--team-slug", required=True, help="Stable team slug used inside the saved snapshots.")
    parser.add_argument(
        "--pcs-team-slug",
        default=None,
        help="Optional season-qualified PCS team slug used for live fetches.",
    )
    parser.add_argument("--planning-year", type=int, required=True, help="Planning year for the tracked team calendar.")
    parser.add_argument("--program-path", default=None, help="Optional local CSV file with program rows.")
    parser.add_argument(
        "--calendar-output",
        required=True,
        help="CSV path for the latest team calendar snapshot.",
    )
    parser.add_argument(
        "--changelog-output",
        required=True,
        help="CSV path for the team calendar changelog.",
    )
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Optional YYYY-MM-DD override for status calculation.",
    )
    return parser.parse_args()


def _load_previous_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    previous_df = pd.read_csv(path, low_memory=False)
    if "race_id" in previous_df.columns:
        previous_df["race_id"] = pd.to_numeric(previous_df["race_id"], errors="coerce").astype("Int64")
    return previous_df


def main() -> None:
    args = parse_args()
    team_slug = canonicalize_team_slug(args.team_slug, args.planning_year)
    pcs_team_slug = args.pcs_team_slug or args.team_slug
    calendar_output_path = Path(args.calendar_output)
    changelog_output_path = Path(args.changelog_output)
    calendar_output_path.parent.mkdir(parents=True, exist_ok=True)
    changelog_output_path.parent.mkdir(parents=True, exist_ok=True)

    previous_snapshot_df = _load_previous_snapshot(calendar_output_path)
    latest_snapshot_df = build_live_team_calendar(
        team_slug=team_slug,
        planning_year=args.planning_year,
        pcs_team_slug=pcs_team_slug,
        program_path=args.program_path,
        as_of_date=args.as_of_date,
    )
    if latest_snapshot_df.empty:
        raise RuntimeError(f"No team calendar rows were built for {team_slug} {args.planning_year}.")

    changelog_df = build_schedule_changelog(
        previous_df=previous_snapshot_df,
        latest_df=latest_snapshot_df,
        team_slug=team_slug,
        planning_year=args.planning_year,
    )

    latest_snapshot_df.to_csv(calendar_output_path, index=False)
    changelog_df.to_csv(changelog_output_path, index=False)
    print(f"Wrote {len(latest_snapshot_df)} latest calendar rows to {calendar_output_path}")
    print(f"Wrote {len(changelog_df)} changelog rows to {changelog_output_path}")


if __name__ == "__main__":
    main()
