from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.team_calendar_artifacts import (  # noqa: E402
    DEFAULT_TRACKED_PROTEAMS_MANIFEST,
    TeamCalendarEvArtifacts,
    build_team_calendar_ev_artifacts,
    load_tracked_team_configs,
    resolve_team_artifact_paths,
    resolve_team_profile,
    write_shared_team_ev_docs,
    write_team_calendar_ev_artifacts,
)
from uci_points_model.team_profile_optimizer import fit_team_strength_weights  # noqa: E402
from uci_points_model.team_profiles import load_team_profile_by_path, write_team_profile_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit optimizer-backed team strength weights from saved Team Calendar EV artifacts.")
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_TRACKED_PROTEAMS_MANIFEST),
        help="CSV manifest of tracked team-season builds.",
    )
    parser.add_argument(
        "--team-slug",
        default=None,
        help="Optional stable team slug filter for fitting a single manifest row.",
    )
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Optional YYYY-MM-DD override for rebuild status calculation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    team_configs = load_tracked_team_configs(args.manifest_path, enabled_only=True)
    if args.team_slug:
        team_configs = [team for team in team_configs if team.team_slug == args.team_slug]
    if not team_configs:
        raise SystemExit("No enabled tracked teams matched the requested filter.")

    docs_source_bundle: TeamCalendarEvArtifacts | None = None
    failures: list[tuple[str, str]] = []

    for team in team_configs:
        if team.profile_path is None:
            failures.append((team.team_slug, "Missing profile_path in manifest."))
            continue
        try:
            paths = resolve_team_artifact_paths(team.team_slug, team.planning_year)
            calendar_ev_df = _load_saved_calendar_ev(paths.ev_output_path)
            resolved_profile = resolve_team_profile(team)
            fit_result = fit_team_strength_weights(calendar_ev_df, resolved_profile)

            raw_profile = load_team_profile_by_path(team.profile_path)
            updated_profile = dict(raw_profile)
            updated_profile["strength_weights"] = dict(fit_result.weights)
            updated_profile["weight_fit_method"] = fit_result.method
            updated_profile["weight_fit_summary"] = dict(fit_result.weight_fit_summary)
            updated_profile["profile_version"] = "v2_optimizer"
            write_team_profile_json(team.profile_path, updated_profile)

            bundle = build_team_calendar_ev_artifacts(
                team,
                refresh_calendar=False,
                refresh_actual_points=False,
                as_of_date=args.as_of_date,
            )
            write_team_calendar_ev_artifacts(bundle, write_changelog=False, write_shared_docs=False)
            if docs_source_bundle is None:
                docs_source_bundle = bundle

            fit_summary = fit_result.weight_fit_summary
            print(
                "FIT"
                f" {team.team_slug}"
                f" races={fit_summary['known_race_count']}"
                f" rmse={fit_summary['baseline_rmse']:.3f}->{fit_summary['rmse']:.3f}"
                f" season_gap={fit_summary['baseline_season_gap']:.3f}->{fit_summary['season_gap']:.3f}"
            )
        except Exception as exc:  # noqa: BLE001
            failures.append((team.team_slug, f"{type(exc).__name__}: {exc}"))

    if docs_source_bundle is not None:
        write_shared_team_ev_docs(
            docs_source_bundle.paths.readme_path,
            docs_source_bundle.paths.dictionary_path,
            docs_source_bundle.readme_text,
            docs_source_bundle.dictionary_text,
        )

    print(
        f"Optimized {len(team_configs) - len(failures)} profiles out of {len(team_configs)} requested teams."
    )
    if failures:
        for team_slug, error in failures:
            print(f"FAILED {team_slug}: {error}")
        raise SystemExit(1)


def _load_saved_calendar_ev(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Saved Team Calendar EV artifact not found: {path}")
    return pd.read_csv(path, low_memory=False)


if __name__ == "__main__":
    main()
