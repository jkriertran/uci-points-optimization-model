from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.rider_race_allocation import default_rider_race_allocation_output_root  # noqa: E402
from uci_points_model.rider_race_allocation_batch import (  # noqa: E402
    build_batch_rider_race_allocations,
    discover_rider_race_allocation_requests,
)

DEFAULT_TEAM_EV_ROOT = ROOT / "data" / "team_ev"
DEFAULT_RIDER_SCORES_PATH = ROOT / "data" / "model_outputs" / "rider_season_threshold_scores.csv"
DEFAULT_RIDER_BASELINE_SUMMARY_PATH = ROOT / "data" / "model_outputs" / "rider_threshold_baseline_summary.json"
DEFAULT_RIDER_BACKTEST_SUMMARY_PATH = ROOT / "data" / "model_outputs" / "rider_threshold_backtest_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic rider-to-race allocation artifacts for all saved Team Calendar EV team-seasons."
    )
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
        "--team-slug",
        default=None,
        help="Optional stable team slug filter for rebuilding a single saved team-season family.",
    )
    parser.add_argument(
        "--planning-year",
        type=int,
        default=None,
        help="Optional planning-year filter for rebuilding a single saved season.",
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
    requests = discover_rider_race_allocation_requests(args.team_ev_root)
    outcomes = build_batch_rider_race_allocations(
        requests,
        rider_scores_path=args.rider_scores_path,
        rider_baseline_summary_path=args.rider_baseline_summary_path,
        rider_backtest_summary_path=args.rider_backtest_summary_path,
        output_root=args.output_root,
        roster_size=args.roster_size,
        top_riders_per_race=args.top_riders_per_race,
        team_slug=args.team_slug,
        planning_year=args.planning_year,
    )

    if (args.team_slug or args.planning_year is not None) and not outcomes:
        filter_bits = []
        if args.team_slug:
            filter_bits.append(f"team_slug={args.team_slug}")
        if args.planning_year is not None:
            filter_bits.append(f"planning_year={args.planning_year}")
        filter_summary = ", ".join(filter_bits) if filter_bits else "the requested filters"
        raise SystemExit(f"No saved Team Calendar EV artifacts matched {filter_summary}.")

    print("Batch rider-race allocation summary:")
    for outcome in outcomes:
        if outcome.success:
            summary = outcome.summary or {}
            print(
                "SUCCESS"
                f" {outcome.team_slug}"
                f" {outcome.planning_year}"
                f" model={summary.get('rider_model_name', '')}"
                f" races={summary.get('race_count', 0)}"
                f" riders={summary.get('rider_count', 0)}"
                f" selected_pairings={summary.get('selected_pairings', 0)}"
            )
        else:
            print(f"FAILED {outcome.team_slug} {outcome.planning_year}: {outcome.error}")

    failed_team_seasons = [
        f"{outcome.team_slug}:{outcome.planning_year}"
        for outcome in outcomes
        if not outcome.success
    ]
    print(
        f"Built {len(outcomes) - len(failed_team_seasons)} successful allocation outputs "
        f"out of {len(outcomes)} requested team-seasons."
    )
    print(f"FAILED_TEAM_SEASONS={','.join(failed_team_seasons)}")

    if failed_team_seasons:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
