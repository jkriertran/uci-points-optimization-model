from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.rider_race_allocation import (  # noqa: E402
    build_rider_race_allocation_artifacts,
    default_rider_race_allocation_output_root,
    write_rider_race_allocation_artifacts,
)
from uci_points_model.rider_race_allocation_batch import (  # noqa: E402
    RiderRaceAllocationBuildRequest,
    load_rider_scores_for_request,
    load_team_ev_for_request,
    resolve_saved_team_ev_path,
)

DEFAULT_TEAM_EV_ROOT = ROOT / "data" / "team_ev"
DEFAULT_RIDER_SCORES_PATH = ROOT / "data" / "model_outputs" / "rider_season_threshold_scores.csv"
DEFAULT_RIDER_BASELINE_SUMMARY_PATH = ROOT / "data" / "model_outputs" / "rider_threshold_baseline_summary.json"
DEFAULT_RIDER_BACKTEST_SUMMARY_PATH = ROOT / "data" / "model_outputs" / "rider_threshold_backtest_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic rider-to-race allocation artifacts from team EV and rider threshold scores."
    )
    parser.add_argument("--team-slug", required=True, help="Canonical team slug, e.g. bardiani-csf-7-saber.")
    parser.add_argument("--planning-year", type=int, required=True, help="Planning year for the saved team EV artifact.")
    parser.add_argument(
        "--team-ev-root",
        default=str(DEFAULT_TEAM_EV_ROOT),
        help="Directory containing saved *_calendar_ev.csv artifacts.",
    )
    parser.add_argument(
        "--rider-scores-path",
        default=str(DEFAULT_RIDER_SCORES_PATH),
        help="CSV path for rider threshold panel scores.",
    )
    parser.add_argument(
        "--rider-baseline-summary-path",
        default=str(DEFAULT_RIDER_BASELINE_SUMMARY_PATH),
        help="JSON path for the rider threshold baseline summary.",
    )
    parser.add_argument(
        "--rider-backtest-summary-path",
        default=str(DEFAULT_RIDER_BACKTEST_SUMMARY_PATH),
        help="JSON path for the rider threshold backtest summary.",
    )
    parser.add_argument(
        "--output-root",
        default=str(default_rider_race_allocation_output_root()),
        help="Directory for rider-race allocation outputs.",
    )
    parser.add_argument(
        "--roster-size",
        type=int,
        default=7,
        help="Number of riders to recommend per race.",
    )
    parser.add_argument(
        "--top-riders-per-race",
        type=int,
        default=3,
        help="How many top rider names to include in the race-plan summary table.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = RiderRaceAllocationBuildRequest(
        team_slug=args.team_slug,
        planning_year=args.planning_year,
        team_ev_path=resolve_saved_team_ev_path(args.team_ev_root, args.team_slug, args.planning_year),
    )
    team_ev_df = load_team_ev_for_request(request)
    rider_scores_df = load_rider_scores_for_request(
        request,
        rider_scores_path=args.rider_scores_path,
        rider_baseline_summary_path=args.rider_baseline_summary_path,
        rider_backtest_summary_path=args.rider_backtest_summary_path,
    )
    artifacts = build_rider_race_allocation_artifacts(
        team_ev_df,
        rider_scores_df,
        roster_size=args.roster_size,
        top_riders_per_race=args.top_riders_per_race,
    )
    written_paths = write_rider_race_allocation_artifacts(
        artifacts,
        output_root=args.output_root,
    )

    print(
        "ALLOCATION"
        f" team={artifacts.summary['team_slug']}"
        f" year={artifacts.summary['planning_year']}"
        f" model={artifacts.summary['rider_model_name']}"
        f" races={artifacts.summary['race_count']}"
        f" riders={artifacts.summary['rider_count']}"
        f" selected_pairings={artifacts.summary['selected_pairings']}"
    )
    if not artifacts.race_plan.empty:
        top_race = artifacts.race_plan.iloc[0]
        print(
            "TOP_RACE"
            f" race={top_race['race_name']}"
            f" race_leader={top_race['race_leader_rider']}"
            f" riders={top_race['top_recommended_riders']}"
            f" score={top_race['selected_allocation_score_total']:.3f}"
        )
    if not artifacts.rider_load_summary.empty:
        top_rider = artifacts.rider_load_summary.iloc[0]
        print(
            "TOP_RIDER"
            f" rider={top_rider['rider_name']}"
            f" race_leader_assignments={int(top_rider['race_leader_assignments'])}"
            f" best_race={top_rider['best_race_name']}"
            f" total_score={top_rider['allocation_score_total']:.3f}"
        )
    for label, path in written_paths.items():
        print(f"WROTE {label}={path}")


if __name__ == "__main__":
    main()
