from pathlib import Path

import pandas as pd
import pytest

import app as app_module


def test_discover_team_calendar_ev_datasets_finds_multiple_team_seasons(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    team_ev_dir = Path("data/team_ev")
    team_calendars_dir = Path("data/team_calendars")
    team_results_dir = Path("data/team_results")
    team_ev_dir.mkdir(parents=True)
    team_calendars_dir.mkdir(parents=True)
    team_results_dir.mkdir(parents=True)

    _write_team_ev_artifacts(
        artifact_stem="alpha_team_2026",
        team_slug="alpha-team",
        team_name="Alpha Team",
        planning_year=2026,
    )
    _write_team_ev_artifacts(
        artifact_stem="beta_team_2026",
        team_slug="beta-team",
        team_name="Beta Team",
        planning_year=2026,
    )

    app_module.discover_team_calendar_ev_datasets.clear()
    datasets = app_module.discover_team_calendar_ev_datasets()

    assert len(datasets) == 2
    assert datasets["label"].tolist() == ["Alpha Team (2026)", "Beta Team (2026)"]
    assert datasets["team_slug"].tolist() == ["alpha-team", "beta-team"]


def test_normalize_team_profile_weights_returns_relative_emphasis() -> None:
    normalized = app_module._normalize_team_profile_weights(  # noqa: SLF001
        {"one_day": 2.0, "stage_hunter": 1.0, "gc": 0.0, "time_trial": 0.0, "all_round": 1.0, "sprint_bonus": 0.0}
    )

    assert round(sum(normalized.values()), 6) == 1.0
    assert normalized["one_day"] > normalized["stage_hunter"]
    assert normalized["stage_hunter"] == normalized["all_round"]


def test_build_team_profile_sandbox_frame_recomputes_expected_points() -> None:
    race_df = pd.DataFrame(
        [
            {
                "race_name": "Race One",
                "status": "scheduled",
                "base_opportunity_points": 40.0,
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.0,
                "sprint_bonus_signal": 0.0,
                "team_fit_score": 0.5,
                "team_fit_multiplier": 0.85,
                "expected_points": 13.6,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.4,
            }
        ]
    )
    sandbox_profile = {
        "strength_weights": {
            "one_day": 1.0,
            "stage_hunter": 0.0,
            "gc": 0.0,
            "time_trial": 0.0,
            "all_round": 0.0,
            "sprint_bonus": 0.0,
        },
        "team_fit_floor": 0.7,
        "team_fit_range": 0.3,
    }

    scenario_df = app_module._build_team_profile_sandbox_frame(race_df, sandbox_profile)  # noqa: SLF001

    row = scenario_df.iloc[0]
    assert float(row["sandbox_team_fit_multiplier"]) == 1.0
    assert float(row["sandbox_expected_points"]) == 16.0
    assert float(row["expected_points_delta"]) == pytest.approx(2.4)


def test_ensure_team_profile_sandbox_state_repairs_missing_keys(monkeypatch) -> None:
    session_state = {
        "team_profile_sandbox_demo-team_2026_initialized": True,
        "team_profile_sandbox_demo-team_2026_one_day": 0.4,
    }
    monkeypatch.setattr(app_module.st, "session_state", session_state)

    app_module._ensure_team_profile_sandbox_state(  # noqa: SLF001
        "team_profile_sandbox_demo-team_2026",
        {
            "strength_weights": {
                "one_day": 0.2,
                "stage_hunter": 0.15,
                "gc": 0.15,
                "time_trial": 0.05,
                "all_round": 0.2,
                "sprint_bonus": 0.25,
            },
            "team_fit_floor": 0.7,
            "team_fit_range": 0.3,
        },
    )

    assert session_state["team_profile_sandbox_demo-team_2026_one_day"] == 0.4
    assert session_state["team_profile_sandbox_demo-team_2026_stage_hunter"] == 0.15
    assert session_state["team_profile_sandbox_demo-team_2026_team_fit_floor"] == 0.7
    assert session_state["team_profile_sandbox_demo-team_2026_team_fit_range"] == 0.3
    assert session_state["team_profile_sandbox_demo-team_2026_initialized"] is True


def test_team_profile_identity_context_reads_archetype_metadata() -> None:
    context = app_module._team_profile_identity_context(  # noqa: SLF001
        {
            "team_name": "Unibet Rose Rockets",
            "team_profile": {
                "archetype_key": "classic_sprint_opportunist",
                "archetype_label": "Classics + Sprint Opportunist",
                "archetype_description": "This profile favors one-day races and sprint-accessible opportunities.",
                "profile_confidence": "medium",
                "profile_rationale": ["Sprint-accessible races remain an important conversion lane."],
                "strength_weights": {
                    "one_day": 0.30,
                    "stage_hunter": 0.15,
                    "gc": 0.10,
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
            },
        }
    )

    assert context["team_name"] == "Unibet Rose Rockets"
    assert context["archetype_label"] == "Classics + Sprint Opportunist"
    assert context["profile_confidence"] == "medium"
    assert context["profile_rationale"] == ["Sprint-accessible races remain an important conversion lane."]


def test_team_calendar_ev_freshness_context_flags_drift_when_calendar_is_newer() -> None:
    context = app_module._team_calendar_ev_freshness_context(  # noqa: SLF001
        {"as_of_date": "2026-04-17"},
        {"as_of_date": "2026-04-17"},
        pd.DataFrame([{"scraped_at_utc": "2026-04-18T00:28:20+00:00"}]),
    )

    assert context["ev_as_of"] == "2026-04-17"
    assert context["calendar_scraped_at"] == "2026-04-18T00:28:20+00:00"
    assert context["has_drift"] is True
    assert "older than the underlying team calendar snapshot" in context["warning_message"]


def test_team_calendar_ev_freshness_context_treats_same_day_as_in_sync() -> None:
    context = app_module._team_calendar_ev_freshness_context(  # noqa: SLF001
        {"as_of_date": "2026-04-18"},
        {"as_of_date": "2026-04-18"},
        pd.DataFrame([{"scraped_at_utc": "2026-04-18T14:22:00+00:00"}]),
    )

    assert context["has_drift"] is False
    assert context["warning_message"] == ""


def test_has_roster_scenario_inputs_requires_expected_columns() -> None:
    race_df = pd.DataFrame(
        [
            {
                "base_opportunity_points": 40.0,
                "team_fit_score": 0.5,
                "team_fit_multiplier": 0.85,
                "participation_confidence": 0.95,
                "execution_multiplier": 0.4,
                "expected_points": 12.9,
                "status": "scheduled",
                "source": "team_program_live",
                "overlap_group": "",
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.2,
                "sprint_bonus_signal": 0.5,
            }
        ]
    )

    assert app_module._has_roster_scenario_inputs(race_df)  # noqa: SLF001
    assert not app_module._has_roster_scenario_inputs(race_df.drop(columns=["source"]))  # noqa: SLF001


def test_build_roster_scenario_assumption_frame_lists_fit_and_participation_rules() -> None:
    frame = app_module._build_roster_scenario_assumption_frame(  # noqa: SLF001
        {
            "team_fit_floor": 0.7,
            "team_fit_range": 0.3,
            "participation_rules": {
                "completed": 1.0,
                "program_confirmed": 0.95,
                "observed_startlist": 0.95,
                "calendar_seed": 0.7,
                "overlap_penalty": 0.8,
            },
            "strength_weights": {
                "one_day": 0.30,
                "stage_hunter": 0.15,
                "gc": 0.10,
                "time_trial": 0.05,
                "all_round": 0.15,
                "sprint_bonus": 0.25,
            },
        },
        {
            "team_fit_floor": 0.62,
            "team_fit_range": 0.22,
            "participation_rules": {
                "completed": 1.0,
                "program_confirmed": 0.82,
                "observed_startlist": 0.88,
                "calendar_seed": 0.55,
                "overlap_penalty": 0.65,
            },
            "strength_weights": {
                "one_day": 0.30,
                "stage_hunter": 0.15,
                "gc": 0.10,
                "time_trial": 0.05,
                "all_round": 0.15,
                "sprint_bonus": 0.25,
            },
        },
    )

    assert frame["Setting"].tolist()[:2] == ["Team-fit floor", "Team-fit range"]
    assert "Participation: calendar seed" in frame["Setting"].tolist()


def _write_team_ev_artifacts(*, artifact_stem: str, team_slug: str, team_name: str, planning_year: int) -> None:
    pd.DataFrame(
        [
            {
                "team_slug": team_slug,
                "planning_year": planning_year,
                "as_of_date": "2026-04-17",
                "total_expected_points": 100.0,
                "completed_expected_points": 50.0,
                "remaining_expected_points": 50.0,
                "actual_points_known": 48.0,
                "ev_gap_known": -2.0,
                "race_count": 10,
                "completed_race_count": 5,
                "remaining_race_count": 5,
            }
        ]
    ).to_csv(Path("data/team_ev") / f"{artifact_stem}_calendar_ev_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "team_slug": team_slug,
                "team_name": team_name,
                "planning_year": planning_year,
                "race_id": 1,
                "race_name": "Race One",
                "category": "1.1",
            }
        ]
    ).to_csv(Path("data/team_ev") / f"{artifact_stem}_calendar_ev.csv", index=False)
    pd.DataFrame([{"team_slug": team_slug}]).to_csv(Path("data/team_calendars") / f"{artifact_stem}_latest.csv", index=False)
    pd.DataFrame([{"team_slug": team_slug}]).to_csv(Path("data/team_results") / f"{artifact_stem}_actual_points.csv", index=False)
