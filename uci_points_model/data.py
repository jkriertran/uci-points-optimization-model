from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from .fc_client import (
    FirstCyclingClient,
    PLANNING_CALENDAR_CATEGORIES,
    RaceCalendarEntry,
    TARGET_CATEGORIES,
)

OPTIONAL_STAGE_COLUMNS: dict[str, float | int] = {
    "gc_scoring_places": 0,
    "gc_winner_points": 0.0,
    "gc_top10_points": 0.0,
    "gc_total_points": 0.0,
    "stage_count": 0,
    "stage_pages_parsed": 0,
    "stage_pages_missing": 0,
    "stage_scoring_places": 0,
    "stage_winner_points": 0.0,
    "stage_top10_points": 0.0,
    "stage_total_points": 0.0,
    "gc_points_share": 0.0,
    "stage_points_share": 0.0,
}


def build_dataset(
    years: Iterable[int],
    categories: Iterable[str] | None = None,
    max_races: int | None = None,
    max_workers: int = 8,
) -> pd.DataFrame:
    categories = tuple(categories or TARGET_CATEGORIES)
    calendar_client = FirstCyclingClient()
    entries: list[RaceCalendarEntry] = []

    for year in sorted(set(years)):
        entries.extend(calendar_client.get_calendar_entries(year=year, categories=categories))

    entries = sorted(entries, key=lambda item: (item.year, item.month, item.race_name))
    if max_races is not None:
        entries = _limit_entries_across_years(entries, max_races)

    if not entries:
        return pd.DataFrame()

    records: list[dict[str, object]] = []
    errors: list[str] = []
    worker_count = min(max_workers, len(entries))

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_map = {pool.submit(_build_record, entry): entry for entry in entries}
        for future in as_completed(future_map):
            entry = future_map[future]
            try:
                records.append(future.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{entry.race_name} ({entry.year}): {exc}")

    dataset = pd.DataFrame(records)
    if dataset.empty:
        dataset.attrs["errors"] = errors
        dataset.attrs["error_count"] = len(errors)
        return dataset

    dataset = ensure_dataset_schema(dataset)
    dataset["finish_rate"] = dataset["finishers"] / dataset["startlist_size"].replace(0, pd.NA)
    dataset["points_per_top10_form"] = dataset["top10_points"] / dataset["top10_field_form"].replace(
        0, pd.NA
    )
    dataset["points_per_total_form"] = dataset["total_points"] / dataset["total_field_form"].replace(
        0, pd.NA
    )
    dataset = dataset.fillna(0)
    dataset = dataset.sort_values(["year", "month", "race_name"]).reset_index(drop=True)
    dataset.attrs["errors"] = errors
    dataset.attrs["error_count"] = len(errors)
    return dataset


def load_snapshot(
    snapshot_path: str | Path,
    years: Iterable[int] | None = None,
    categories: Iterable[str] | None = None,
) -> pd.DataFrame:
    path = Path(snapshot_path)
    if not path.exists():
        return pd.DataFrame()

    dataset = pd.read_csv(path)
    dataset = ensure_dataset_schema(dataset)
    if years:
        dataset = dataset[dataset["year"].isin(list(years))]
    if categories:
        dataset = dataset[dataset["category"].isin(list(categories))]
    return dataset.reset_index(drop=True)


def load_calendar(
    year: int,
    categories: Iterable[str] | None = None,
    months: Iterable[int] | None = None,
) -> pd.DataFrame:
    try:
        calendar_client = FirstCyclingClient()
        entries = calendar_client.get_calendar_entries(
            year=year,
            categories=categories or PLANNING_CALENDAR_CATEGORIES,
            months=months,
        )
    except Exception:  # noqa: BLE001
        return pd.DataFrame(
            columns=["race_id", "race_name", "category", "date_label", "month", "year"]
        )

    if not entries:
        return pd.DataFrame(
            columns=["race_id", "race_name", "category", "date_label", "month", "year"]
        )

    calendar = pd.DataFrame(asdict(entry) for entry in entries)
    return calendar.sort_values(["month", "race_name"]).reset_index(drop=True)


def write_snapshot(dataset: pd.DataFrame, snapshot_path: str | Path) -> None:
    path = Path(snapshot_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)


def _build_record(entry: RaceCalendarEntry) -> dict[str, object]:
    client = FirstCyclingClient()
    return client.build_race_edition_record(entry)


def _limit_entries_across_years(
    entries: list[RaceCalendarEntry], max_races: int
) -> list[RaceCalendarEntry]:
    if len(entries) <= max_races:
        return entries

    grouped: dict[int, list[RaceCalendarEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.year, []).append(entry)

    years = sorted(grouped)
    base_quota = max_races // len(years)
    remainder = max_races % len(years)
    selected: list[RaceCalendarEntry] = []
    leftovers: list[RaceCalendarEntry] = []

    for index, year in enumerate(years):
        quota = base_quota + (1 if index < remainder else 0)
        selected.extend(grouped[year][:quota])
        leftovers.extend(grouped[year][quota:])

    if len(selected) < max_races:
        selected.extend(leftovers[: max_races - len(selected)])

    return sorted(selected, key=lambda item: (item.year, item.month, item.race_name))


def ensure_dataset_schema(dataset: pd.DataFrame) -> pd.DataFrame:
    enriched = dataset.copy()
    for column_name, default_value in OPTIONAL_STAGE_COLUMNS.items():
        if column_name not in enriched.columns:
            enriched[column_name] = default_value
    return enriched
