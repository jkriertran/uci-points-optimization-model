from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import DEFAULT_IMPORTED_ROOT, validate_historical_import  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate imported historical ProTeam datasets."
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Directory containing imported historical datasets.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = validate_historical_import(import_root=args.import_root)
    print(f"Validation passed: {report.passed}")
    for key, result in report.file_results.items():
        status = "PASS" if result.passed else "FAIL"
        print(f"{status}: {key} -> {result.destination_path}")
        for issue in result.issues:
            print(f"  - {issue}")
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
