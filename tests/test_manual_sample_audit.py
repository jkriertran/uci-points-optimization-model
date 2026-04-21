import pandas as pd

from uci_points_model import manual_sample_audit as module


def test_as_bool_handles_csv_style_strings() -> None:
    assert module._as_bool(True) is True  # noqa: SLF001
    assert module._as_bool(False) is False  # noqa: SLF001
    assert module._as_bool("True") is True  # noqa: SLF001
    assert module._as_bool("False") is False  # noqa: SLF001
    assert module._as_bool("1") is True  # noqa: SLF001
    assert module._as_bool("0") is False  # noqa: SLF001


def test_run_rider_sample_audit_uses_destination_side_transfer_join() -> None:
    rider_panel = pd.DataFrame(
        [
            {
                "season": 2021,
                "next_season": 2022,
                "rider_name": "Rider Example",
                "rider_slug": "rider-example",
                "team_name": "Current Team",
                "team_slug": "current-team-2021",
                "team_class": "PRT",
                "uci_points": 110.0,
                "pcs_points": 90.0,
                "racedays": 50.0,
                "team_rank_within_roster": 3,
                "team_points_share": 0.12,
                "archetype": "engine",
                "result_summary_available": False,
                "transfer_context_available": True,
                "age_on_jan_1": 24.0,
                "specialty_primary": "gc",
                "transfer_step_label": "step_up",
                "prior_year_uci_points": 75.0,
                "prior_year_n_starts": 40.0,
                "prior_year_scored_150_flag": False,
                "has_observed_next_season": False,
            }
        ]
    )
    imported_rider = pd.DataFrame(
        [
            {
                "season_year": 2021,
                "rider_name": "Rider Example",
                "rider_slug": "rider-example",
                "team_name": "Current Team",
                "team_slug": "current-team-2021",
                "team_class": "PRT",
                "uci_points": 110.0,
                "pcs_points": 90.0,
                "racedays": 50.0,
                "team_rank_within_roster": 3,
                "team_points_share": 0.12,
                "archetype": "engine",
                "source_points_url": "https://example.com/points",
                "source_racedays_url": "https://example.com/racedays",
            }
        ]
    )
    imported_transfer = pd.DataFrame(
        [
            {
                "year_from": 2020,
                "year_to": 2021,
                "rider_slug": "rider-example",
                "team_from_slug": "old-team-2020",
                "team_to_slug": "current-team-2021",
                "age_on_jan_1": 24.0,
                "specialty_primary": "gc",
                "transfer_step_label": "step_up",
                "prior_year_uci_points": 75.0,
                "prior_year_n_starts": 40.0,
                "prior_year_scored_150_flag": False,
            }
        ]
    )

    audit_df = module._run_rider_sample_audit(  # noqa: SLF001
        rider_panel=rider_panel,
        imported_rider=imported_rider,
        upstream_rider=imported_rider.copy(),
        imported_result_summary=pd.DataFrame(),
        upstream_result_summary=pd.DataFrame(),
        imported_transfer=imported_transfer,
        upstream_transfer=imported_transfer.copy(),
        sample_size=1,
        random_seed=7,
    )

    assert len(audit_df) == 1
    row = audit_df.iloc[0]
    assert row["transfer_import_exists"]
    assert row["transfer_upstream_exists"]
    assert row["panel_matches_transfer_context"]
    assert row["all_checks_passed"]
