from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uci_points_model.historical_data_import import (  # noqa: E402
    DEFAULT_IMPORTED_ROOT,
    DEFAULT_UPSTREAM_REPO,
    HistoricalImportError,
    import_historical_proteam_data,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import verified historical ProTeam datasets into the production repo."
    )
    parser.add_argument(
        "--source-root",
        default=None,
        help="Optional local checkout of procycling-clean-scraped-data. If omitted, the script tries local defaults before GitHub.",
    )
    parser.add_argument(
        "--github-repo",
        default=DEFAULT_UPSTREAM_REPO,
        help="GitHub repository to read when a local source root is unavailable.",
    )
    parser.add_argument(
        "--import-root",
        default=str(DEFAULT_IMPORTED_ROOT),
        help="Destination directory for imported files.",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also import optional rider/race enrichment files.",
    )
    parser.add_argument(
        "--allow-validation-failure",
        action="store_true",
        help="Write files and metadata even if post-import validation fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = import_historical_proteam_data(
            source_root=args.source_root,
            import_root=args.import_root,
            github_repo=args.github_repo,
            include_optional=args.include_optional,
            strict=not args.allow_validation_failure,
        )
    except HistoricalImportError as exc:
        raise SystemExit(str(exc)) from exc

    print(
        "Imported "
        f"{len(result.imported_files)} upstream files into {result.import_root} "
        f"using {result.source_mode} source mode."
    )
    print(f"Validation passed: {result.validation_report.passed}")
    print(f"Metadata written to {result.metadata_path}")


if __name__ == "__main__":
    main()
