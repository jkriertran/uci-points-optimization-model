from pathlib import Path

import pandas as pd

from uci_points_model.fc_client import RaceCalendarEntry
from uci_points_model.race_history_backfill import (
    build_backfill_coverage,
    find_manifest_calendar_matches,
    load_backfill_manifest,
    merge_backfill_snapshot,
    scrape_matched_race_history,
)


class _FakeClient:
    def __init__(self, entries_by_year, record_overrides=None):
        self.entries_by_year = entries_by_year
        self.record_overrides = record_overrides or {}

    def get_calendar_entries(self, year, categories=None, months=None):  # noqa: D401
        allowed = set(categories or [])
        entries = list(self.entries_by_year.get(year, []))
        if not allowed:
            return entries
        return [entry for entry in entries if entry.category in allowed]

    def build_race_edition_record(self, entry):  # noqa: D401
        override = self.record_overrides.get((entry.race_id, entry.year), {})
        base = {
            "race_id": entry.race_id,
            "race_name": entry.race_name,
            "year": entry.year,
            "month": entry.month,
            "date_label": entry.date_label,
            "category": entry.category,
            "race_type": "One-day" if entry.category.startswith("1.") else "Stage race",
            "race_country": "Test",
            "race_subtitle": "",
            "finishers": 100,
            "scoring_places": 10,
            "winner_points": 125.0,
            "top10_points": 250.0,
            "total_points": 400.0,
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
            "startlist_size": 100,
            "experienced_riders": 50,
            "total_startlist_starts": 1000,
            "total_startlist_wins": 50,
            "total_startlist_podiums": 100,
            "total_startlist_top10s": 200,
            "total_field_form": 1000.0,
            "top10_field_form": 400.0,
            "avg_top10_field_form": 40.0,
            "finish_rate": 1.0,
            "points_per_top10_form": 0.625,
            "points_per_total_form": 0.4,
        }
        base.update(override)
        return base


class _FailingCalendarClient(_FakeClient):
    def get_calendar_entries(self, year, categories=None, months=None):  # noqa: D401
        raise RuntimeError(f"blocked-{year}")


def test_load_backfill_manifest_filters_requested_tiers(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.csv"
    pd.DataFrame(
        [
            {"priority_tier": "P1", "race_name": "Race One", "category": "1.2", "aliases": "", "notes": ""},
            {"priority_tier": "P2", "race_name": "Race Two", "category": "2.2", "aliases": "", "notes": ""},
        ]
    ).to_csv(manifest_path, index=False)

    manifest = load_backfill_manifest(manifest_path, tiers=["P1"])

    assert manifest["race_name"].tolist() == ["Race One"]


def test_find_manifest_calendar_matches_uses_normalized_aliases() -> None:
    manifest = pd.DataFrame(
        [
            {
                "priority_tier": "P1",
                "race_name": "Clásica de Pascua-Padron",
                "category": "1.2",
                "aliases": "Clasica de Pascua-Padron",
                "notes": "",
            }
        ]
    )
    client = _FakeClient(
        {
            2024: [
                RaceCalendarEntry(
                    race_id=101,
                    race_name="Clasica de Pascua-Padron",
                    category="1.2",
                    date_label="2024-04-01",
                    month=4,
                    year=2024,
                )
            ]
        }
    )

    matched = find_manifest_calendar_matches(manifest, years=[2024], client=client)

    assert len(matched) == 1
    assert matched.loc[0, "manifest_race_name"] == "Clásica de Pascua-Padron"
    assert matched.loc[0, "entry_race_name"] == "Clasica de Pascua-Padron"


def test_scrape_and_merge_race_history_backfill_updates_snapshot(tmp_path: Path) -> None:
    matched = pd.DataFrame(
        [
            {
                "priority_tier": "P1",
                "manifest_race_name": "Race Repeated",
                "manifest_category": "1.2",
                "manifest_notes": "",
                "match_alias": "Race Repeated",
                "year": 2024,
                "race_id": 101,
                "entry_race_name": "Race Repeated",
                "entry_category": "1.2",
                "entry_date_label": "2024-03-01",
                "entry_month": 3,
                "exact_name_match": True,
            }
        ]
    )
    client = _FakeClient({2024: []})
    scraped = scrape_matched_race_history(matched, client=client, max_workers=1)
    assert len(scraped) == 1

    snapshot_path = tmp_path / "snapshot.csv"
    pd.DataFrame(
        [
            {
                "race_id": 101,
                "race_name": "Race Repeated",
                "year": 2023,
                "month": 3,
                "date_label": "2023-03-01",
                "category": "1.2",
                "race_type": "One-day",
                "race_country": "Test",
                "race_subtitle": "",
                "finishers": 90,
                "scoring_places": 10,
                "winner_points": 100.0,
                "top10_points": 200.0,
                "total_points": 300.0,
                "startlist_size": 90,
                "experienced_riders": 45,
                "total_startlist_starts": 900,
                "total_startlist_wins": 45,
                "total_startlist_podiums": 90,
                "total_startlist_top10s": 180,
                "total_field_form": 900.0,
                "top10_field_form": 360.0,
                "avg_top10_field_form": 36.0,
                "finish_rate": 1.0,
                "points_per_top10_form": 0.555,
                "points_per_total_form": 0.333,
            }
        ]
    ).to_csv(snapshot_path, index=False)

    merged = merge_backfill_snapshot(scraped, snapshot_path=snapshot_path)

    assert len(merged) == 2
    assert sorted(merged["year"].tolist()) == [2023, 2024]


def test_build_backfill_coverage_reports_missing_years() -> None:
    manifest = pd.DataFrame(
        [
            {"priority_tier": "P1", "race_name": "Race One", "category": "1.2", "aliases": "", "notes": ""},
            {"priority_tier": "P1", "race_name": "Race Two", "category": "2.2", "aliases": "", "notes": ""},
        ]
    )
    matched = pd.DataFrame(
        [
            {"manifest_race_name": "Race One", "year": 2024, "entry_race_name": "Race One"},
            {"manifest_race_name": "Race One", "year": 2025, "entry_race_name": "Race One"},
        ]
    )

    coverage = build_backfill_coverage(manifest, matched, years=[2024, 2025])

    assert coverage.loc[coverage["race_name"] == "Race One", "missing_years"].iloc[0] == ""
    assert coverage.loc[coverage["race_name"] == "Race Two", "missing_years"].iloc[0] == "2024 | 2025"


def test_find_manifest_calendar_matches_captures_calendar_errors() -> None:
    manifest = pd.DataFrame(
        [
            {"priority_tier": "P1", "race_name": "Race One", "category": "1.2", "aliases": "", "notes": ""},
        ]
    )

    matched = find_manifest_calendar_matches(
        manifest,
        years=[2024],
        client=_FailingCalendarClient({}),
    )

    assert matched.empty
    assert matched.attrs["calendar_errors"] == ["2024: RuntimeError: blocked-2024"]
