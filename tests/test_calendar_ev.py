import pandas as pd

from uci_points_model import calendar_ev as module

TEAM_PROFILE = {
    "strength_weights": {
        "one_day": 0.3,
        "stage_hunter": 0.15,
        "gc": 0.1,
        "time_trial": 0.05,
        "all_round": 0.15,
        "sprint_bonus": 0.25,
    },
    "team_fit_floor": 0.7,
    "team_fit_range": 0.3,
    "execution_rules": {
        "1.1": 0.4,
        "1.Pro": 0.3,
        "1.UWT": 0.18,
        "2.1": 0.3,
        "2.Pro": 0.25,
        "2.UWT": 0.18,
    },
    "participation_rules": {
        "completed": 1.0,
        "program_confirmed": 0.95,
        "observed_startlist": 0.95,
        "calendar_seed": 0.7,
        "overlap_penalty": 0.8,
    },
}


def build_calendar_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team_slug": "unibet-rose-rockets",
                "team_name": "Unibet Rose Rockets",
                "planning_year": 2026,
                "race_id": 1,
                "race_name": "Race One",
                "category": "1.1",
                "date_label": "01.01",
                "month": 1,
                "start_date": "2026-01-01",
                "end_date": "2026-01-01",
                "pcs_race_slug": "race-one",
                "status": "completed",
                "team_calendar_status": "active",
                "source": "team_program_live",
                "overlap_group": "",
                "notes": "",
            },
            {
                "team_slug": "unibet-rose-rockets",
                "team_name": "Unibet Rose Rockets",
                "planning_year": 2026,
                "race_id": 2,
                "race_name": "Race Two",
                "category": "1.Pro",
                "date_label": "02.01",
                "month": 1,
                "start_date": "2026-01-02",
                "end_date": "2026-01-02",
                "pcs_race_slug": "race-two",
                "status": "scheduled",
                "team_calendar_status": "active",
                "source": "team_program_live",
                "overlap_group": "",
                "notes": "",
            },
        ]
    )


def build_historical_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Race One",
                "historical_years_analyzed": 3,
                "latest_category": "1.1",
                "race_type": "One-day",
                "route_profile": "sprint-friendly one-day",
                "avg_top10_points": 120.0,
                "avg_winner_points": 40.0,
                "avg_points_efficiency": 3.0,
                "avg_stage_top10_points": 0.0,
                "avg_stage_count": 0.0,
                "avg_top10_field_form": 2.5,
                "base_opportunity_index": 0.4,
                "base_opportunity_points": 80.0,
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.5,
                "sprint_bonus_signal": 0.7,
                "field_softness_score": 0.8,
            }
        ]
    )


def test_build_team_calendar_ev_preserves_calendar_rows() -> None:
    calendar_df = build_calendar_rows()
    historical_df = build_historical_rows()

    result_df = module.build_team_calendar_ev(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=pd.DataFrame(),
    )

    assert len(result_df) == 2
    missing_row = result_df.loc[result_df["race_id"] == 2].iloc[0]
    assert "history_missing" in missing_row["notes"]


def test_expected_points_is_component_product() -> None:
    calendar_df = build_calendar_rows().iloc[[0]].copy()
    historical_df = build_historical_rows()

    result_df = module.build_team_calendar_ev(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=pd.DataFrame(),
    )

    row = result_df.iloc[0]
    expected = (
        float(row["base_opportunity_points"])
        * float(row["team_fit_multiplier"])
        * float(row["participation_confidence"])
        * float(row["execution_multiplier"])
    )

    assert float(row["expected_points"]) == expected


def test_team_fit_multiplier_is_bounded() -> None:
    calendar_df = build_calendar_rows().iloc[[0]].copy()
    historical_df = build_historical_rows()
    historical_df.loc[0, "one_day_signal"] = 3.0
    historical_df.loc[0, "sprint_bonus_signal"] = 3.0

    result_df = module.build_team_calendar_ev(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=pd.DataFrame(),
    )

    multiplier = float(result_df.iloc[0]["team_fit_multiplier"])
    assert multiplier >= 0.7
    assert multiplier <= 1.0


def test_calculate_team_fit_components_uses_signal_columns() -> None:
    race_df = pd.DataFrame(
        [
            {
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.2,
                "gc_signal": 0.0,
                "time_trial_signal": 0.1,
                "all_round_signal": 0.4,
                "sprint_bonus_signal": 0.8,
            }
        ]
    )

    result_df = module.calculate_team_fit_components(race_df, TEAM_PROFILE)

    row = result_df.iloc[0]
    assert float(row["specialty_fit_score"]) > 0.0
    assert float(row["sprint_fit_bonus"]) > 0.0
    assert float(row["team_fit_multiplier"]) >= 0.7
    assert float(row["team_fit_multiplier"]) <= 1.0


def test_build_team_calendar_ev_preserves_team_signal_columns() -> None:
    calendar_df = build_calendar_rows().iloc[[0]].copy()
    historical_df = build_historical_rows()

    result_df = module.build_team_calendar_ev(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=pd.DataFrame(),
    )

    row = result_df.iloc[0]
    assert float(row["one_day_signal"]) == 1.0
    assert float(row["all_round_signal"]) == 0.5
    assert float(row["sprint_bonus_signal"]) == 0.7


def test_stage_races_use_stage_aware_history_fields(tmp_path) -> None:
    snapshot_df = pd.DataFrame(
        [
            {
                "race_id": 11,
                "race_name": "One Day Test",
                "year": 2024,
                "category": "1.1",
                "race_type": "One-day",
                "top10_points": 100.0,
                "winner_points": 30.0,
                "points_per_top10_form": 10.0,
                "stage_top10_points": 0.0,
                "stage_count": 0.0,
                "avg_top10_field_form": 5.0,
            },
            {
                "race_id": 12,
                "race_name": "Stage Race Test",
                "year": 2024,
                "category": "2.1",
                "race_type": "Stage race",
                "top10_points": 100.0,
                "winner_points": 30.0,
                "points_per_top10_form": 10.0,
                "stage_top10_points": 250.0,
                "stage_count": 5.0,
                "avg_top10_field_form": 5.0,
            },
        ]
    )
    snapshot_path = tmp_path / "race_editions_snapshot.csv"
    snapshot_df.to_csv(snapshot_path, index=False)

    summary_df = module.build_historical_target_summary(snapshot_path=snapshot_path, planning_year=2026)
    one_day_row = summary_df.loc[summary_df["race_id"] == 11].iloc[0]
    stage_row = summary_df.loc[summary_df["race_id"] == 12].iloc[0]

    assert float(stage_row["avg_stage_top10_points"]) > float(one_day_row["avg_stage_top10_points"])
    assert float(stage_row["base_opportunity_index"]) > float(one_day_row["base_opportunity_index"])


def test_attach_actual_points_calculates_ev_gap() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {"race_id": 1, "expected_points": 10.0},
            {"race_id": 2, "expected_points": 7.5},
        ]
    )
    actual_points_df = pd.DataFrame(
        [
            {"race_id": 1, "actual_points": 12.0},
        ]
    )

    result_df = module.attach_actual_points(calendar_ev_df, actual_points_df)
    row = result_df.loc[result_df["race_id"] == 1].iloc[0]

    assert float(row["actual_points"]) == 12.0
    assert float(row["ev_gap"]) == 2.0


def test_build_actual_points_table_marks_completed_empty_rows_as_zero() -> None:
    class StubClient:
        def get_team_race_uci_points(self, team_slug: str, race_slug: str, season_year: int):
            class Result:
                source_url = "https://example.com"
                actual_points = 0.0
                rider_count = 0
                has_rows = False

            return Result()

    actual_points_df = module.build_actual_points_table(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        team_calendar=build_calendar_rows().iloc[[0]].copy(),
        pcs_team_slug="unibet-rose-rockets-2026",
        client=StubClient(),
    )

    row = actual_points_df.iloc[0]
    assert row["status"] == "completed"
    assert float(row["actual_points"]) == 0.0
    assert row["notes"] == "uci_points_missing_after_race"


def test_build_team_calendar_ev_uses_category_fallback_for_missing_uwt_history() -> None:
    calendar_df = pd.DataFrame(
        [
            {
                "team_slug": "unibet-rose-rockets",
                "team_name": "Unibet Rose Rockets",
                "planning_year": 2026,
                "race_id": 50,
                "race_name": "Big WorldTour One Day",
                "category": "1.UWT",
                "date_label": "03.03",
                "month": 3,
                "start_date": "2026-03-03",
                "end_date": "2026-03-03",
                "pcs_race_slug": "big-worldtour-one-day",
                "status": "scheduled",
                "team_calendar_status": "active",
                "source": "team_program_live",
                "overlap_group": "",
                "notes": "",
            }
        ]
    )
    historical_df = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Comparable Pro One Day",
                "historical_years_analyzed": 4,
                "latest_category": "1.Pro",
                "race_type": "One-day",
                "route_profile": "hard one-day",
                "avg_top10_points": 140.0,
                "avg_winner_points": 50.0,
                "avg_points_efficiency": 3.5,
                "avg_stage_top10_points": 0.0,
                "avg_stage_count": 0.0,
                "avg_top10_field_form": 3.0,
                "base_opportunity_index": 0.5,
                "base_opportunity_points": 70.0,
                "one_day_signal": 0.9,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.4,
                "sprint_bonus_signal": 0.3,
                "field_softness_score": 0.2,
            }
        ]
    )

    result_df = module.build_team_calendar_ev(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=pd.DataFrame(),
    )

    row = result_df.iloc[0]
    assert float(row["base_opportunity_points"]) == 70.0
    assert "history_fallback_from=1.Pro" in row["notes"]
    assert "history_missing" in row["notes"]


def test_build_team_calendar_ev_uses_category_fallback_for_missing_1_2_history() -> None:
    calendar_df = pd.DataFrame(
        [
            {
                "team_slug": "solution-tech-nippo-rali",
                "team_name": "Solution Tech NIPPO Rali",
                "planning_year": 2026,
                "race_id": 501,
                "race_name": "Gran Premio Primavera-Ontur",
                "category": "1.2",
                "date_label": "22.03",
                "month": 3,
                "start_date": "2026-03-22",
                "end_date": "2026-03-22",
                "pcs_race_slug": "gran-premio-primavera-ontur",
                "status": "completed",
                "team_calendar_status": "active",
                "source": "team_program_live",
                "overlap_group": "",
                "notes": "",
            }
        ]
    )
    historical_df = pd.DataFrame(
        [
            {
                "race_id": 601,
                "race_name": "Comparable 1.1 One Day",
                "historical_years_analyzed": 4,
                "latest_category": "1.1",
                "race_type": "One-day",
                "route_profile": "hard one-day",
                "avg_top10_points": 90.0,
                "avg_winner_points": 30.0,
                "avg_points_efficiency": 2.4,
                "avg_stage_top10_points": 0.0,
                "avg_stage_count": 0.0,
                "avg_top10_field_form": 2.0,
                "base_opportunity_index": 0.45,
                "base_opportunity_points": 40.5,
                "one_day_signal": 0.75,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.35,
                "sprint_bonus_signal": 0.25,
                "field_softness_score": 0.35,
            }
        ]
    )
    actual_points_df = pd.DataFrame([{"race_id": 501, "actual_points": 15.0}])

    result_df = module.build_team_calendar_ev(
        team_slug="solution-tech-nippo-rali",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=actual_points_df,
    )

    row = result_df.iloc[0]
    assert float(row["base_opportunity_points"]) == 40.5
    assert float(row["expected_points"]) > 0.0
    assert "history_fallback_from=1.1" in row["notes"]
    assert "history_missing" in row["notes"]


def test_build_team_calendar_ev_uses_category_fallback_for_missing_2_2_history() -> None:
    calendar_df = pd.DataFrame(
        [
            {
                "team_slug": "solution-tech-nippo-rali",
                "team_name": "Solution Tech NIPPO Rali",
                "planning_year": 2026,
                "race_id": 701,
                "race_name": "Tour of Sharjah",
                "category": "2.2",
                "date_label": "23.01",
                "month": 1,
                "start_date": "2026-01-23",
                "end_date": "2026-01-27",
                "pcs_race_slug": "tour-of-sharjah",
                "status": "completed",
                "team_calendar_status": "active",
                "source": "team_program_live",
                "overlap_group": "",
                "notes": "",
            }
        ]
    )
    historical_df = pd.DataFrame(
        [
            {
                "race_id": 801,
                "race_name": "Comparable 2.1 Stage Race",
                "historical_years_analyzed": 3,
                "latest_category": "2.1",
                "race_type": "Stage race",
                "route_profile": "short stage race",
                "avg_top10_points": 180.0,
                "avg_winner_points": 45.0,
                "avg_points_efficiency": 2.8,
                "avg_stage_top10_points": 120.0,
                "avg_stage_count": 4.0,
                "avg_top10_field_form": 3.2,
                "base_opportunity_index": 0.50,
                "base_opportunity_points": 90.0,
                "one_day_signal": 0.15,
                "stage_hunter_signal": 0.55,
                "gc_signal": 0.45,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.50,
                "sprint_bonus_signal": 0.20,
                "field_softness_score": 0.40,
            }
        ]
    )
    actual_points_df = pd.DataFrame([{"race_id": 701, "actual_points": 30.0}])

    result_df = module.build_team_calendar_ev(
        team_slug="solution-tech-nippo-rali",
        planning_year=2026,
        historical_summary=historical_df,
        team_calendar=calendar_df,
        team_profile=TEAM_PROFILE,
        actual_points_df=actual_points_df,
    )

    row = result_df.iloc[0]
    assert float(row["base_opportunity_points"]) == 90.0
    assert float(row["expected_points"]) > 0.0
    assert "history_fallback_from=2.1" in row["notes"]
    assert "history_missing" in row["notes"]


def test_build_actual_points_table_marks_completed_errors_as_unknown() -> None:
    class StubClient:
        def get_team_race_uci_points(self, team_slug: str, race_slug: str, season_year: int):
            raise RuntimeError("boom")

    actual_points_df = module.build_actual_points_table(
        team_slug="unibet-rose-rockets",
        planning_year=2026,
        team_calendar=build_calendar_rows().iloc[[0]].copy(),
        pcs_team_slug="unibet-rose-rockets-2026",
        client=StubClient(),
    )

    row = actual_points_df.iloc[0]
    assert pd.isna(row["actual_points"])
    assert row["notes"] == "uci_points_error=RuntimeError"


def test_summarize_team_calendar_ev_returns_one_row_kpis() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {
                "team_slug": "unibet-rose-rockets",
                "planning_year": 2026,
                "as_of_date": "2026-04-17",
                "status": "completed",
                "expected_points": 10.0,
                "actual_points": 12.0,
                "ev_gap": 2.0,
            },
            {
                "team_slug": "unibet-rose-rockets",
                "planning_year": 2026,
                "as_of_date": "2026-04-17",
                "status": "scheduled",
                "expected_points": 8.0,
                "actual_points": pd.NA,
                "ev_gap": pd.NA,
            },
            {
                "team_slug": "unibet-rose-rockets",
                "planning_year": 2026,
                "as_of_date": "2026-04-17",
                "status": "cancelled",
                "expected_points": 6.0,
                "actual_points": pd.NA,
                "ev_gap": pd.NA,
            },
        ]
    )

    summary_df = module.summarize_team_calendar_ev(calendar_ev_df)

    assert len(summary_df) == 1
    row = summary_df.iloc[0]
    assert row["team_slug"] == "unibet-rose-rockets"
    assert row["as_of_date"] == "2026-04-17"
    assert float(row["total_expected_points"]) == 24.0
    assert float(row["completed_expected_points"]) == 10.0
    assert float(row["remaining_expected_points"]) == 8.0
    assert float(row["actual_points_known"]) == 12.0
    assert float(row["ev_gap_known"]) == 2.0
    assert int(row["race_count"]) == 3
    assert int(row["completed_race_count"]) == 1
    assert int(row["remaining_race_count"]) == 1
