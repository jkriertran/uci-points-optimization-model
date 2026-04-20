from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.team_calendar_artifacts import (  # noqa: E402
    DEFAULT_PROTEAM_PROFILE_PATH,
    TrackedTeamConfig,
    build_team_calendar_ev_artifacts,
    resolve_team_artifact_paths,
    write_team_calendar_ev_artifacts,
)
from uci_points_model.team_identity import canonicalize_team_slug  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic team calendar expected value outputs.")
    parser.add_argument("--team-slug", required=True, help="Stable team slug used inside the saved artifacts.")
    parser.add_argument(
        "--pcs-team-slug",
        default=None,
        help="Optional season-qualified PCS team slug used for live fetches. Defaults to the profile value or team slug.",
    )
    parser.add_argument("--planning-year", type=int, required=True, help="Planning year for the EV build.")
    parser.add_argument("--team-profile-path", required=True, help="JSON path for the team EV profile.")
    parser.add_argument("--calendar-path", required=True, help="Latest team calendar snapshot CSV.")
    parser.add_argument("--actual-points-path", required=True, help="Output CSV for race-level actual points.")
    parser.add_argument("--ev-output-path", required=True, help="Output CSV for the race-level calendar EV table.")
    parser.add_argument("--summary-output-path", required=True, help="Output CSV for calendar EV summaries.")
    parser.add_argument("--readme-path", required=True, help="Markdown readme path for the EV dataset.")
    parser.add_argument("--dictionary-path", required=True, help="Markdown data dictionary path for the EV dataset.")
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Optional YYYY-MM-DD override for status calculation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    team_slug = canonicalize_team_slug(args.team_slug, args.planning_year)
    raw_profile = json.loads(Path(args.team_profile_path).read_text())
    team = TrackedTeamConfig(
        team_slug=team_slug,
        pcs_team_slug=str(args.pcs_team_slug or raw_profile.get("pcs_team_slug") or args.team_slug),
        team_name=str(raw_profile.get("team_name") or team_slug.replace("-", " ").title()),
        planning_year=args.planning_year,
        profile_path=Path(args.team_profile_path),
    )
    paths = resolve_team_artifact_paths(
        team_slug=team_slug,
        planning_year=args.planning_year,
        calendar_path=args.calendar_path,
        actual_points_path=args.actual_points_path,
        ev_output_path=args.ev_output_path,
        summary_output_path=args.summary_output_path,
        readme_path=args.readme_path,
        dictionary_path=args.dictionary_path,
    )
    bundle = build_team_calendar_ev_artifacts(
        team,
        paths=paths,
        default_profile_path=DEFAULT_PROTEAM_PROFILE_PATH,
        refresh_calendar=not Path(args.calendar_path).exists(),
        as_of_date=args.as_of_date,
    )
    write_team_calendar_ev_artifacts(bundle, write_changelog=False, write_shared_docs=True)

    print(f"Wrote {len(bundle.actual_points_df)} actual-points rows to {bundle.paths.actual_points_path}")
    print(f"Wrote {len(bundle.calendar_ev_df)} race-level EV rows to {bundle.paths.ev_output_path}")
    print(f"Wrote {len(bundle.summary_df)} summary rows to {bundle.paths.summary_output_path}")
    print(f"Wrote metadata to {bundle.paths.metadata_output_path}")


if __name__ == "__main__":
    main()
