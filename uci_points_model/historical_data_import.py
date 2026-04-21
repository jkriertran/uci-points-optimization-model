from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMPORTED_ROOT = PROJECT_ROOT / "data" / "imported" / "procycling_clean_scraped_data"
DEFAULT_UPSTREAM_REPO = "jkriertran/procycling-clean-scraped-data"

_ENV_SOURCE_ROOT = os.getenv("PROCYCLING_CLEAN_SCRAPED_DATA_ROOT")
DEFAULT_SOURCE_ROOT_CANDIDATES = tuple(
    path
    for path in (
        Path(_ENV_SOURCE_ROOT).expanduser() if _ENV_SOURCE_ROOT else None,
        PROJECT_ROOT.parent / "procycling-clean-scraped-data",
    )
    if path is not None
)


class HistoricalImportError(RuntimeError):
    """Raised when the upstream historical import cannot be completed."""


@dataclass(frozen=True)
class HistoricalImportSpec:
    key: str
    source_path: str
    required_columns: tuple[str, ...]
    year_column: str | None = None
    expected_years: tuple[int, ...] = ()
    required: bool = True
    allow_empty: bool = False
    binary: bool = False

    @property
    def destination_name(self) -> str:
        return Path(self.source_path).name


@dataclass
class ImportedFileResult:
    key: str
    source_path: str
    destination_path: str
    byte_count: int
    source_mode: str


@dataclass
class FileValidationResult:
    key: str
    source_path: str
    destination_path: str
    exists: bool
    passed: bool
    row_count: int | None = None
    columns: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class HistoricalImportValidationReport:
    import_root: str
    checked_at_utc: str
    passed: bool
    file_results: dict[str, FileValidationResult]
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class HistoricalImportResult:
    import_root: str
    imported_at_utc: str
    source_mode: str
    source_root: str
    github_repo: str
    imported_files: list[ImportedFileResult]
    metadata_path: str
    validation_report: HistoricalImportValidationReport

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["validation_report"] = self.validation_report.to_dict()
        return payload


REQUIRED_HISTORICAL_IMPORT_SPECS: tuple[HistoricalImportSpec, ...] = (
    HistoricalImportSpec(
        key="historical_proteam_team_panel",
        source_path="data/historical_proteam_team_panel.csv",
        required_columns=(
            "season_year",
            "team_name",
            "team_slug",
            "team_rank",
            "team_total_uci_points",
            "top1_share",
            "top3_share",
            "top5_share",
            "n_riders_150",
        ),
        year_column="season_year",
        expected_years=(2021, 2022, 2023, 2024, 2025, 2026),
    ),
    HistoricalImportSpec(
        key="historical_proteam_rider_panel",
        source_path="data/historical_proteam_rider_panel.csv",
        required_columns=(
            "season_year",
            "team_slug",
            "rider_name",
            "rider_slug",
            "uci_points",
            "racedays",
            "team_points_share",
        ),
        year_column="season_year",
        expected_years=(2021, 2022, 2023, 2024, 2025, 2026),
    ),
    HistoricalImportSpec(
        key="ranking_predictor_study_data",
        source_path="data/procycling_proteam_analysis/ranking_predictor_study_data.csv",
        required_columns=(
            "prior_team_slug",
            "next_team_slug",
            "prior_n_riders_150",
            "next_top5",
        ),
    ),
    HistoricalImportSpec(
        key="transition_continuity_links",
        source_path="data/procycling_proteam_analysis/transition_continuity_links.csv",
        required_columns=(
            "year_a",
            "year_b",
            "prior_team_slug",
            "next_team_slug",
            "matched_prior_team",
        ),
    ),
    HistoricalImportSpec(
        key="historical_proteam_validation_summary",
        source_path="manifests/historical_proteam_validation_summary.csv",
        required_columns=("check_name", "status", "value", "notes"),
    ),
    HistoricalImportSpec(
        key="historical_proteam_missing_pages",
        source_path="manifests/historical_proteam_missing_pages.csv",
        required_columns=(
            "season_year",
            "team_slug",
            "team_name",
            "page_family",
            "source_url",
            "cache_path",
            "status",
            "status_code",
            "inventory_source",
            "seed_path",
            "error_message",
            "scraped_at",
            "credits_used",
        ),
        allow_empty=True,
    ),
)

OPTIONAL_HISTORICAL_IMPORT_SPECS: tuple[HistoricalImportSpec, ...] = (
    HistoricalImportSpec(
        key="rider_season_result_summary",
        source_path="data/procycling_proteam_analysis/rider_season_result_summary.csv",
        required_columns=(
            "season_year",
            "rider_slug",
            "team_slug",
            "total_uci_points_detailed",
            "n_starts",
            "n_scoring_results",
        ),
        year_column="season_year",
        expected_years=(2021, 2022, 2023, 2024, 2025),
        required=False,
    ),
    HistoricalImportSpec(
        key="rider_transfer_context_enriched",
        source_path="data/procycling_proteam_analysis/rider_transfer_context_enriched.csv",
        required_columns=(
            "rider_slug",
            "year_from",
            "year_to",
            "team_from_slug",
            "team_to_slug",
            "prior_year_uci_points",
        ),
        required=False,
    ),
    HistoricalImportSpec(
        key="race_entries_pts_v2",
        source_path="data/procycling_proteam_analysis/race_entries_pts_v2.csv",
        required_columns=("race", "year", "team_norm", "slug", "points_scored"),
        required=False,
    ),
    HistoricalImportSpec(
        key="race_page_rider_results",
        source_path="data/procycling_proteam_analysis/race_page_rider_results.csv.gz",
        required_columns=(),
        required=False,
        binary=True,
    ),
)

ALL_HISTORICAL_IMPORT_SPECS = REQUIRED_HISTORICAL_IMPORT_SPECS + OPTIONAL_HISTORICAL_IMPORT_SPECS
HISTORICAL_IMPORT_SPEC_BY_KEY = {spec.key: spec for spec in ALL_HISTORICAL_IMPORT_SPECS}


def get_historical_import_specs(include_optional: bool = False) -> tuple[HistoricalImportSpec, ...]:
    if include_optional:
        return ALL_HISTORICAL_IMPORT_SPECS
    return REQUIRED_HISTORICAL_IMPORT_SPECS


def get_historical_import_spec(key: str) -> HistoricalImportSpec:
    try:
        return HISTORICAL_IMPORT_SPEC_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown historical import key: {key}") from exc


def imported_dataset_path(
    key: str,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
) -> Path:
    spec = get_historical_import_spec(key)
    return Path(import_root) / spec.destination_name


def resolve_local_source_root(source_root: str | Path | None = None) -> Path | None:
    if source_root is not None:
        explicit_path = Path(source_root).expanduser().resolve()
        if explicit_path.exists():
            return explicit_path
        return None

    candidates: list[Path] = []
    candidates.extend(DEFAULT_SOURCE_ROOT_CANDIDATES)

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None


def import_historical_proteam_data(
    source_root: str | Path | None = None,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    github_repo: str = DEFAULT_UPSTREAM_REPO,
    include_optional: bool = False,
    strict: bool = True,
) -> HistoricalImportResult:
    specs = get_historical_import_specs(include_optional=include_optional)
    destination_root = Path(import_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    resolved_source_root = resolve_local_source_root(source_root)
    if source_root is not None and resolved_source_root is None:
        raise HistoricalImportError(
            f"Provided source root does not exist: {Path(source_root).expanduser()}"
        )
    source_mode = "local" if resolved_source_root is not None else "github"
    source_root_display = str(resolved_source_root) if resolved_source_root is not None else ""
    imported_at_utc = datetime.now(timezone.utc).isoformat()

    imported_files: list[ImportedFileResult] = []
    for spec in specs:
        raw_bytes = _read_upstream_bytes(
            source_path=spec.source_path,
            source_root=resolved_source_root,
            github_repo=github_repo,
        )
        destination_path = destination_root / spec.destination_name
        destination_path.write_bytes(raw_bytes)
        imported_files.append(
            ImportedFileResult(
                key=spec.key,
                source_path=spec.source_path,
                destination_path=str(destination_path),
                byte_count=len(raw_bytes),
                source_mode=source_mode,
            )
        )

    validation_report = validate_historical_import(
        import_root=destination_root,
        specs=specs,
    )
    metadata_path = destination_root / "import_metadata.json"
    result = HistoricalImportResult(
        import_root=str(destination_root),
        imported_at_utc=imported_at_utc,
        source_mode=source_mode,
        source_root=source_root_display,
        github_repo=github_repo,
        imported_files=imported_files,
        metadata_path=str(metadata_path),
        validation_report=validation_report,
    )
    metadata_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if strict and not validation_report.passed:
        raise HistoricalImportError(
            "Imported historical data failed validation. See "
            f"{metadata_path} for details."
        )

    return result


def validate_historical_import(
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    specs: Iterable[HistoricalImportSpec] | None = None,
) -> HistoricalImportValidationReport:
    selected_specs = tuple(specs or REQUIRED_HISTORICAL_IMPORT_SPECS)
    checked_at_utc = datetime.now(timezone.utc).isoformat()
    root = Path(import_root)
    file_results: dict[str, FileValidationResult] = {}
    report_issues: list[str] = []

    for spec in selected_specs:
        destination_path = root / spec.destination_name
        result = _validate_imported_file(spec=spec, destination_path=destination_path)
        file_results[spec.key] = result
        if not result.passed:
            report_issues.extend(result.issues)

    return HistoricalImportValidationReport(
        import_root=str(root),
        checked_at_utc=checked_at_utc,
        passed=not report_issues,
        file_results=file_results,
        issues=report_issues,
    )


def load_imported_historical_dataset(
    key: str,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
) -> pd.DataFrame:
    path = imported_dataset_path(key=key, import_root=import_root)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, compression="infer")


def _read_upstream_bytes(
    source_path: str,
    source_root: Path | None,
    github_repo: str,
) -> bytes:
    if source_root is not None:
        local_path = source_root / source_path
        if not local_path.exists():
            raise HistoricalImportError(f"Missing upstream file in local source root: {local_path}")
        return local_path.read_bytes()
    return _read_github_bytes(github_repo=github_repo, source_path=source_path)


def _read_github_bytes(github_repo: str, source_path: str) -> bytes:
    try:
        download_url = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{github_repo}/contents/{source_path}",
                "--jq",
                ".download_url",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except FileNotFoundError as exc:
        raise HistoricalImportError("The `gh` CLI is required for GitHub-backed historical imports.") from exc
    except subprocess.CalledProcessError as exc:
        raise HistoricalImportError(
            f"Failed to resolve GitHub download URL for {source_path}: {exc.stderr.strip()}"
        ) from exc

    if not download_url:
        raise HistoricalImportError(f"No download URL returned for upstream file: {source_path}")

    with urllib.request.urlopen(download_url) as response:  # noqa: S310
        return response.read()


def _validate_imported_file(
    spec: HistoricalImportSpec,
    destination_path: Path,
) -> FileValidationResult:
    result = FileValidationResult(
        key=spec.key,
        source_path=spec.source_path,
        destination_path=str(destination_path),
        exists=destination_path.exists(),
        passed=True,
    )

    if not destination_path.exists():
        result.passed = False
        result.issues.append(f"[{spec.key}] Missing imported file: {destination_path}")
        return result

    if spec.binary:
        if destination_path.stat().st_size == 0:
            result.passed = False
            result.issues.append(f"[{spec.key}] Imported binary file is empty: {destination_path}")
        return result

    dataset = pd.read_csv(destination_path)
    result.row_count = len(dataset)
    result.columns = dataset.columns.tolist()

    missing_columns = sorted(set(spec.required_columns) - set(dataset.columns))
    if missing_columns:
        result.passed = False
        result.issues.append(f"[{spec.key}] Missing required columns: {', '.join(missing_columns)}")

    if not spec.allow_empty and dataset.empty:
        result.passed = False
        result.issues.append(f"[{spec.key}] Imported dataset is empty.")

    if spec.year_column and spec.expected_years and spec.year_column in dataset.columns and not dataset.empty:
        observed_years = sorted(
            {
                int(year)
                for year in pd.to_numeric(dataset[spec.year_column], errors="coerce").dropna().astype(int)
            }
        )
        missing_years = [year for year in spec.expected_years if year not in observed_years]
        if missing_years:
            result.passed = False
            result.issues.append(
                f"[{spec.key}] Missing expected {spec.year_column} values: {missing_years}"
            )

    if spec.key == "historical_proteam_validation_summary" and "status" in dataset.columns and not dataset.empty:
        non_pass_rows = dataset.loc[dataset["status"].astype(str).str.lower() != "pass"]
        if not non_pass_rows.empty:
            result.passed = False
            result.issues.append(
                "[historical_proteam_validation_summary] Upstream validation summary contains non-pass rows."
            )

    if spec.key == "historical_proteam_missing_pages" and not dataset.empty:
        result.passed = False
        result.issues.append(
            "[historical_proteam_missing_pages] Upstream missing-pages manifest is not empty."
        )

    if spec.key == "ranking_predictor_study_data" and "next_top5" in dataset.columns and not dataset.empty:
        next_top5_values = {
            str(value)
            for value in pd.to_numeric(dataset["next_top5"], errors="coerce").dropna().astype(int).tolist()
        }
        if not next_top5_values.issubset({"0", "1"}):
            result.passed = False
            result.issues.append(
                "[ranking_predictor_study_data] `next_top5` contains values outside {0, 1}."
            )

    return result
