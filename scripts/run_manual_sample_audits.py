from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.manual_sample_audit import (  # noqa: E402
    DEFAULT_AUDIT_OUTPUT_ROOT,
    DEFAULT_RANDOM_SEED,
    DEFAULT_RACE_SAMPLE_SIZE,
    DEFAULT_RIDER_SAMPLE_SIZE,
    DEFAULT_TEAM_SAMPLE_SIZE,
    run_manual_sample_audits,
    write_manual_sample_audit_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic team, rider, and race-EV manual sample audits."
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_AUDIT_OUTPUT_ROOT),
        help="Directory for the Markdown report, summary JSON, and sampled CSV outputs.",
    )
    parser.add_argument(
        "--upstream-root",
        default="",
        help="Optional local checkout of procycling-clean-scraped-data. Uses the importer default when omitted.",
    )
    parser.add_argument(
        "--team-sample-size",
        type=int,
        default=DEFAULT_TEAM_SAMPLE_SIZE,
        help="Number of team-season rows to audit.",
    )
    parser.add_argument(
        "--rider-sample-size",
        type=int,
        default=DEFAULT_RIDER_SAMPLE_SIZE,
        help="Number of rider-season rows to audit.",
    )
    parser.add_argument(
        "--race-sample-size",
        type=int,
        default=DEFAULT_RACE_SAMPLE_SIZE,
        help="Number of Team Calendar EV race rows to audit.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Deterministic sampling seed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = run_manual_sample_audits(
        upstream_root=args.upstream_root or None,
        team_sample_size=args.team_sample_size,
        rider_sample_size=args.rider_sample_size,
        race_sample_size=args.race_sample_size,
        random_seed=args.random_seed,
    )
    written_paths = write_manual_sample_audit_artifacts(
        artifacts,
        output_root=args.output_root,
    )

    print(
        "AUDIT"
        f" overall_pass={artifacts.summary['all_checks_passed']}"
        f" team={artifacts.summary['team_audit']['passed_rows']}/{artifacts.summary['team_audit']['sample_rows']}"
        f" rider={artifacts.summary['rider_audit']['passed_rows']}/{artifacts.summary['rider_audit']['sample_rows']}"
        f" race={artifacts.summary['race_audit']['passed_rows']}/{artifacts.summary['race_audit']['sample_rows']}"
    )
    for label, path in written_paths.items():
        print(f"WROTE {label}={path}")

    if not artifacts.summary["all_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
