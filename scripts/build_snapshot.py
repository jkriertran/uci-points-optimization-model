from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.data import build_dataset, write_snapshot
from uci_points_model.fc_client import TARGET_CATEGORIES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a cached historical snapshot for the UCI points optimization app."
    )
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Years to scrape.")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(TARGET_CATEGORIES),
        help="Race categories to include.",
    )
    parser.add_argument(
        "--max-races",
        type=int,
        default=None,
        help="Optional cap on the number of race editions to scrape.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Concurrent workers to use while scraping.",
    )
    parser.add_argument(
        "--out",
        default="data/race_editions_snapshot.csv",
        help="CSV path for the saved snapshot.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = build_dataset(
        years=args.years,
        categories=args.categories,
        max_races=args.max_races,
        max_workers=args.max_workers,
    )
    write_snapshot(dataset, args.out)
    print(f"Wrote {len(dataset)} race editions to {args.out}")
    if dataset.attrs.get("error_count"):
        print(f"Skipped {dataset.attrs['error_count']} races due to scrape issues.")


if __name__ == "__main__":
    main()
