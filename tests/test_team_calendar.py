import pandas as pd

from uci_points_model import team_calendar as module


def test_parse_date_label_supports_ranges() -> None:
    start_date, end_date = module.parse_date_label("04.02-08.02", 2026)

    assert start_date == "2026-02-04"
    assert end_date == "2026-02-08"


def test_match_observed_races_uses_alias_map() -> None:
    planning_df = pd.DataFrame(
        [
            {
                "race_id": 97,
                "race_name": "GP la Marseillaise",
                "category": "1.1",
                "date_label": "01.02",
                "month": 2,
                "planning_year": 2026,
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "normalized_race_name": module.normalize_race_name("GP la Marseillaise"),
            }
        ]
    )
    alias_df = pd.DataFrame(
        [
            {
                "team_slug": "unibet-rose-rockets-2026",
                "planning_year": 2026,
                "source_race_name": "Grand Prix Cycliste la Marseillaise",
                "canonical_race_name": "GP la Marseillaise",
                "race_id": 97,
                "normalized_source_race_name": module.normalize_race_name("Grand Prix Cycliste la Marseillaise"),
            }
        ]
    )
    observed_df = pd.DataFrame(
        [
            {
                "source_race_name": "Grand Prix Cycliste la Marseillaise",
                "observed_date": "2026-02-01",
                "pcs_race_slug": "gp-la-marseillaise",
            }
        ]
    )

    matched_df = module.match_observed_races(
        observed_df,
        planning_df,
        alias_df,
        team_slug="unibet-rose-rockets-2026",
        planning_year=2026,
    )

    row = matched_df.iloc[0]
    assert int(row["matched_race_id"]) == 97
    assert row["matched_via"] == "alias"


def test_overlap_flagging_and_changelog_track_changes() -> None:
    latest_df = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Race One",
                "date_label": "01.02-03.02",
                "category": "2.1",
                "status": "scheduled",
                "team_calendar_status": "active",
                "start_date": "2026-02-01",
                "end_date": "2026-02-03",
                "notes": "",
            },
            {
                "race_id": 2,
                "race_name": "Race Two",
                "date_label": "02.02",
                "category": "1.1",
                "status": "scheduled",
                "team_calendar_status": "active",
                "start_date": "2026-02-02",
                "end_date": "2026-02-02",
                "notes": "",
            },
        ]
    )
    previous_df = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Race One",
                "date_label": "01.02-03.02",
                "category": "2.1",
                "status": "completed",
                "team_calendar_status": "active",
                "start_date": "2026-02-01",
                "end_date": "2026-02-03",
                "notes": "",
            }
        ]
    )

    overlap_df = module.add_overlap_groups(latest_df)
    changelog_df = module.build_schedule_changelog(
        previous_df=previous_df,
        latest_df=latest_df,
        team_slug="unibet-rose-rockets-2026",
        planning_year=2026,
        detected_at_utc="2026-04-16T00:00:00+00:00",
    )

    assert len(overlap_df) == 2
    assert all(value == "overlap_2" for value in overlap_df["overlap_group"])
    assert "race_added" in changelog_df["change_type"].tolist()
    assert "status_changed" in changelog_df["change_type"].tolist()


def test_build_team_calendar_from_source_rows_derives_completed_status() -> None:
    source_rows_df = pd.DataFrame(
        [
            {
                "source_race_name": "GP la Marseillaise",
                "observed_date": "2026-02-01",
                "date_label": "2026-02-01",
                "category": "1.1",
                "source_url": "race/gp-la-marseillaise/2026/startlist",
                "pcs_race_slug": "gp-la-marseillaise",
            }
        ]
    )
    planning_df = pd.DataFrame(
        [
            {
                "race_id": 97,
                "race_name": "GP la Marseillaise",
                "category": "1.1",
                "date_label": "01.02",
                "month": 2,
                "year": 2026,
            }
        ]
    )

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmpdir:
        planning_path = f"{tmpdir}/planning_calendar_2026.csv"
        planning_df.to_csv(planning_path, index=False)
        result_df = module.build_team_calendar_from_source_rows(
            source_rows_df=source_rows_df,
            team_slug="unibet-rose-rockets-2026",
            planning_year=2026,
            team_name="Unibet Rose Rockets",
            planning_calendar_path=planning_path,
            as_of_date="2026-04-16",
        )

    row = result_df.iloc[0]
    assert row["status"] == "completed"
    assert row["pcs_race_slug"] == "gp-la-marseillaise"
