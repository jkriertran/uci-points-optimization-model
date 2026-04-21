from __future__ import annotations

import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from .data import ensure_dataset_schema, write_snapshot
from .fc_client import FirstCyclingClient, RaceCalendarEntry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "config" / "history_missing_backfill_manifest.csv"
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "race_editions_snapshot.csv"
DEFAULT_AUDIT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "audits"
DEFAULT_BACKFILL_YEARS = (2021, 2022, 2023, 2024, 2025)


@dataclass(frozen=True, slots=True)
class RaceHistoryBackfillArtifacts:
    summary: dict[str, object]
    manifest: pd.DataFrame
    matched_entries: pd.DataFrame
    scraped_dataset: pd.DataFrame
    coverage: pd.DataFrame
    merged_snapshot: pd.DataFrame


def run_race_history_backfill(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    tiers: Sequence[str] | None = None,
    years: Sequence[int] = DEFAULT_BACKFILL_YEARS,
    snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH,
    max_workers: int = 8,
    client: FirstCyclingClient | None = None,
) -> RaceHistoryBackfillArtifacts:
    manifest = load_backfill_manifest(manifest_path, tiers=tiers)
    if manifest.empty:
        raise ValueError("Backfill manifest is empty after applying the requested tier filter.")

    matched_entries = find_manifest_calendar_matches(
        manifest,
        years=years,
        client=client,
    )
    scraped_dataset = scrape_matched_race_history(
        matched_entries,
        client=client,
        max_workers=max_workers,
    )
    merged_snapshot = merge_backfill_snapshot(
        scraped_dataset,
        snapshot_path=snapshot_path,
    )
    coverage = build_backfill_coverage(manifest, matched_entries, years=years)
    summary = _build_summary(
        manifest=manifest,
        matched_entries=matched_entries,
        scraped_dataset=scraped_dataset,
        merged_snapshot=merged_snapshot,
        coverage=coverage,
        years=years,
        snapshot_path=snapshot_path,
    )
    return RaceHistoryBackfillArtifacts(
        summary=summary,
        manifest=manifest,
        matched_entries=matched_entries,
        scraped_dataset=scraped_dataset,
        coverage=coverage,
        merged_snapshot=merged_snapshot,
    )


def write_race_history_backfill_artifacts(
    artifacts: RaceHistoryBackfillArtifacts,
    *,
    output_root: str | Path = DEFAULT_AUDIT_OUTPUT_ROOT,
    report_date: date | None = None,
) -> dict[str, Path]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    active_date = report_date or date.today()
    tier_label = _tier_label(artifacts.manifest)
    stem = f"race_history_backfill_{tier_label}_{active_date.isoformat()}"

    summary_path = root / f"{stem}_summary.json"
    summary_path.write_text(json.dumps(artifacts.summary, indent=2, sort_keys=True) + "\n")

    coverage_path = root / f"{stem}_coverage.csv"
    artifacts.coverage.to_csv(coverage_path, index=False)

    matches_path = root / f"{stem}_matches.csv"
    artifacts.matched_entries.to_csv(matches_path, index=False)

    scraped_path = root / f"{stem}_scraped_editions.csv"
    artifacts.scraped_dataset.to_csv(scraped_path, index=False)

    return {
        "summary_path": summary_path,
        "coverage_path": coverage_path,
        "matches_path": matches_path,
        "scraped_path": scraped_path,
    }


def load_backfill_manifest(
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    tiers: Sequence[str] | None = None,
) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_path).copy()
    manifest["priority_tier"] = manifest.get("priority_tier", pd.Series("", index=manifest.index)).astype(str).str.strip()
    manifest["race_name"] = manifest.get("race_name", pd.Series("", index=manifest.index)).astype(str).str.strip()
    manifest["category"] = manifest.get("category", pd.Series("", index=manifest.index)).astype(str).str.strip()
    manifest["aliases"] = manifest.get("aliases", pd.Series("", index=manifest.index)).fillna("").astype(str)
    manifest["notes"] = manifest.get("notes", pd.Series("", index=manifest.index)).fillna("").astype(str)
    if tiers:
        selected = {str(value).strip() for value in tiers if str(value).strip()}
        manifest = manifest.loc[manifest["priority_tier"].isin(selected)].copy()
    manifest = manifest.loc[manifest["race_name"].str.strip() != ""].reset_index(drop=True)
    return manifest


def find_manifest_calendar_matches(
    manifest: pd.DataFrame,
    *,
    years: Sequence[int],
    client: FirstCyclingClient | None = None,
) -> pd.DataFrame:
    manifest_rows = _prepare_manifest_rows(manifest)
    categories = sorted({row["category"] for row in manifest_rows if row["category"]})
    fc_client = client or FirstCyclingClient()
    matched_rows: list[dict[str, object]] = []
    calendar_errors: list[str] = []

    for year in sorted({int(value) for value in years}):
        try:
            entries = fc_client.get_calendar_entries(year=year, categories=categories)
        except Exception as exc:  # noqa: BLE001
            calendar_errors.append(f"{year}: {type(exc).__name__}: {exc}")
            continue
        for entry in entries:
            normalized_entry_name = _normalize_name(entry.race_name)
            for manifest_row in manifest_rows:
                if manifest_row["category"] and entry.category != manifest_row["category"]:
                    continue
                alias_hit = next(
                    (
                        alias
                        for alias, normalized_alias in manifest_row["normalized_aliases"]
                        if normalized_alias == normalized_entry_name
                    ),
                    None,
                )
                if alias_hit is None:
                    continue
                matched_rows.append(
                    {
                        "priority_tier": manifest_row["priority_tier"],
                        "manifest_race_name": manifest_row["race_name"],
                        "manifest_category": manifest_row["category"],
                        "manifest_notes": manifest_row["notes"],
                        "match_alias": alias_hit,
                        "year": int(year),
                        "race_id": int(entry.race_id),
                        "entry_race_name": entry.race_name,
                        "entry_category": entry.category,
                        "entry_date_label": entry.date_label,
                        "entry_month": int(entry.month),
                        "exact_name_match": alias_hit == manifest_row["race_name"],
                    }
                )
                break

    matched = pd.DataFrame(matched_rows)
    if matched.empty:
        matched.attrs["calendar_errors"] = calendar_errors
        return matched
    matched = matched.sort_values(
        ["priority_tier", "manifest_race_name", "year", "entry_month", "entry_race_name"],
    ).drop_duplicates(subset=["manifest_race_name", "year", "race_id"]).reset_index(drop=True)
    matched.attrs["calendar_errors"] = calendar_errors
    return matched


def scrape_matched_race_history(
    matched_entries: pd.DataFrame,
    *,
    client: FirstCyclingClient | None = None,
    max_workers: int = 8,
) -> pd.DataFrame:
    if matched_entries.empty:
        return pd.DataFrame()

    entries = [
        RaceCalendarEntry(
            race_id=int(row.race_id),
            race_name=str(row.entry_race_name),
            category=str(row.entry_category),
            date_label=str(row.entry_date_label),
            month=int(row.entry_month),
            year=int(row.year),
        )
        for row in matched_entries.itertuples(index=False)
    ]
    worker_count = max(1, min(int(max_workers), len(entries)))
    records: list[dict[str, object]] = []
    errors: list[str] = []

    if client is not None:
        for entry in entries:
            try:
                records.append(client.build_race_edition_record(entry))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{entry.race_name} ({entry.year}): {exc}")
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            future_map = {
                pool.submit(_build_record_for_entry, entry): entry
                for entry in entries
            }
            for future in as_completed(future_map):
                entry = future_map[future]
                try:
                    records.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{entry.race_name} ({entry.year}): {exc}")

    scraped = pd.DataFrame(records)
    if scraped.empty:
        scraped.attrs["errors"] = errors
        scraped.attrs["error_count"] = len(errors)
        return scraped
    scraped = ensure_dataset_schema(scraped)
    scraped = scraped.sort_values(["year", "month", "race_name"]).drop_duplicates(
        subset=["race_id", "year"],
        keep="last",
    ).reset_index(drop=True)
    scraped.attrs["errors"] = errors
    scraped.attrs["error_count"] = len(errors)
    return scraped


def merge_backfill_snapshot(
    scraped_dataset: pd.DataFrame,
    *,
    snapshot_path: str | Path = DEFAULT_SNAPSHOT_PATH,
) -> pd.DataFrame:
    path = Path(snapshot_path)
    existing = pd.read_csv(path, low_memory=False) if path.exists() else pd.DataFrame()
    existing = ensure_dataset_schema(existing) if not existing.empty else existing
    scraped = ensure_dataset_schema(scraped_dataset) if not scraped_dataset.empty else scraped_dataset
    combined = pd.concat([existing, scraped], ignore_index=True) if not existing.empty else scraped.copy()
    if combined.empty:
        return combined
    combined = ensure_dataset_schema(combined)
    combined = combined.sort_values(["year", "month", "race_name"]).drop_duplicates(
        subset=["race_id", "year"],
        keep="last",
    ).reset_index(drop=True)
    write_snapshot(combined, path)
    return combined


def build_backfill_coverage(
    manifest: pd.DataFrame,
    matched_entries: pd.DataFrame,
    *,
    years: Sequence[int],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    year_values = sorted({int(value) for value in years})
    for row in manifest.itertuples(index=False):
        manifest_matches = matched_entries.loc[
            matched_entries.get("manifest_race_name", pd.Series("", index=matched_entries.index)).astype(str)
            == str(row.race_name)
        ].copy() if not matched_entries.empty else pd.DataFrame()
        year_series = (
            pd.to_numeric(manifest_matches["year"], errors="coerce")
            if "year" in manifest_matches.columns
            else pd.Series(dtype="Float64")
        )
        matched_years = sorted(
            {int(value) for value in year_series.dropna().astype(int)}
        )
        missing_years = [year for year in year_values if year not in matched_years]
        rows.append(
            {
                "priority_tier": str(row.priority_tier),
                "race_name": str(row.race_name),
                "category": str(row.category),
                "matched_editions": int(len(manifest_matches)),
                "matched_years": " | ".join(str(year) for year in matched_years),
                "missing_years": " | ".join(str(year) for year in missing_years),
                "matched_entry_names": " | ".join(
                    sorted({str(value) for value in manifest_matches.get("entry_race_name", pd.Series(dtype=object)).dropna()})
                ),
            }
        )
    coverage = pd.DataFrame(rows)
    return coverage.sort_values(["priority_tier", "race_name"]).reset_index(drop=True)


def _prepare_manifest_rows(manifest: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in manifest.itertuples(index=False):
        aliases = [str(row.race_name).strip()]
        aliases.extend(
            alias.strip()
            for alias in str(getattr(row, "aliases", "") or "").split("|")
            if alias.strip()
        )
        deduped_aliases = list(dict.fromkeys(aliases))
        rows.append(
            {
                "priority_tier": str(row.priority_tier),
                "race_name": str(row.race_name),
                "category": str(row.category),
                "notes": str(getattr(row, "notes", "") or ""),
                "normalized_aliases": [(alias, _normalize_name(alias)) for alias in deduped_aliases if alias],
            }
        )
    return rows


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return "".join(character for character in ascii_only.casefold() if character.isalnum())


def _build_record_for_entry(entry: RaceCalendarEntry) -> dict[str, object]:
    client = FirstCyclingClient()
    return client.build_race_edition_record(entry)


def _build_summary(
    *,
    manifest: pd.DataFrame,
    matched_entries: pd.DataFrame,
    scraped_dataset: pd.DataFrame,
    merged_snapshot: pd.DataFrame,
    coverage: pd.DataFrame,
    years: Sequence[int],
    snapshot_path: str | Path,
) -> dict[str, object]:
    errors = list(scraped_dataset.attrs.get("errors", [])) if hasattr(scraped_dataset, "attrs") else []
    calendar_errors = list(matched_entries.attrs.get("calendar_errors", [])) if hasattr(matched_entries, "attrs") else []
    return {
        "audit_date": date.today().isoformat(),
        "manifest_path": str(DEFAULT_MANIFEST_PATH),
        "snapshot_path": str(Path(snapshot_path)),
        "requested_tiers": sorted(manifest["priority_tier"].astype(str).dropna().unique().tolist()),
        "requested_years": sorted({int(value) for value in years}),
        "manifest_races": int(len(manifest)),
        "matched_entries": int(len(matched_entries)),
        "scraped_editions": int(len(scraped_dataset)),
        "snapshot_rows_after_merge": int(len(merged_snapshot)),
        "races_with_full_year_coverage": int((coverage["missing_years"].fillna("").astype(str) == "").sum()) if not coverage.empty else 0,
        "races_with_partial_coverage": int((coverage["missing_years"].fillna("").astype(str) != "").sum()) if not coverage.empty else 0,
        "calendar_error_count": int(len(calendar_errors)),
        "calendar_errors": calendar_errors[:50],
        "scrape_error_count": int(len(errors)),
        "scrape_errors": errors[:50],
    }


def _tier_label(manifest: pd.DataFrame) -> str:
    tiers = sorted({str(value).strip().lower() for value in manifest.get("priority_tier", pd.Series(dtype=object)).dropna() if str(value).strip()})
    return "_".join(tiers) if tiers else "all"
