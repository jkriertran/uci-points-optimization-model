from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.race_history_backfill import (  # noqa: E402
    DEFAULT_AUDIT_OUTPUT_ROOT,
    DEFAULT_BACKFILL_YEARS,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SNAPSHOT_PATH,
    run_race_history_backfill,
    write_race_history_backfill_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Targeted FirstCycling race-history backfill for priority history_missing races."
    )
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_MANIFEST_PATH),
        help="CSV manifest of priority races to backfill.",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        default=["P1"],
        help="Priority tiers from the manifest to include.",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=list(DEFAULT_BACKFILL_YEARS),
        help="Historical seasons to scrape.",
    )
    parser.add_argument(
        "--snapshot-path",
        default=str(DEFAULT_SNAPSHOT_PATH),
        help="Snapshot CSV to update in place.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_AUDIT_OUTPUT_ROOT),
        help="Directory for the coverage/match/scraped artifact outputs.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Concurrent workers for the race-edition scrape.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = run_race_history_backfill(
        manifest_path=args.manifest_path,
        tiers=args.tiers,
        years=args.years,
        snapshot_path=args.snapshot_path,
        max_workers=args.max_workers,
    )
    written = write_race_history_backfill_artifacts(
        artifacts,
        output_root=args.output_root,
    )

    print(
        "RACE_HISTORY_BACKFILL"
        f" tiers={','.join(args.tiers)}"
        f" manifest_races={artifacts.summary['manifest_races']}"
        f" matched_entries={artifacts.summary['matched_entries']}"
        f" scraped_editions={artifacts.summary['scraped_editions']}"
        f" full_coverage={artifacts.summary['races_with_full_year_coverage']}"
        f" partial_coverage={artifacts.summary['races_with_partial_coverage']}"
        f" calendar_errors={artifacts.summary['calendar_error_count']}"
        f" scrape_errors={artifacts.summary['scrape_error_count']}"
    )
    for label, path in written.items():
        print(f"WROTE {label}={path}")


if __name__ == "__main__":
    main()
