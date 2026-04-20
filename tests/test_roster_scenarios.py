import pandas as pd
import pytest

from uci_points_model.calendar_ev import calculate_participation_confidence, calculate_team_fit_components
from uci_points_model.roster_scenarios import (
    build_roster_scenario_result,
    list_roster_scenario_presets,
    validate_roster_scenario_inputs,
)

TEAM_PROFILE = {
    "strength_weights": {
        "one_day": 0.30,
        "stage_hunter": 0.15,
        "gc": 0.10,
        "time_trial": 0.05,
        "all_round": 0.15,
        "sprint_bonus": 0.25,
    },
    "team_fit_floor": 0.70,
    "team_fit_range": 0.30,
    "participation_rules": {
        "completed": 1.0,
        "program_confirmed": 0.95,
        "observed_startlist": 0.95,
        "calendar_seed": 0.70,
        "overlap_penalty": 0.80,
    },
}


def _build_saved_ev_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "race_name": "Completed Race",
                "status": "completed",
                "source": "team_program_live",
                "overlap_group": "",
                "base_opportunity_points": 40.0,
                "execution_multiplier": 0.4,
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.2,
                "sprint_bonus_signal": 0.8,
            },
            {
                "race_name": "Scheduled Race",
                "status": "scheduled",
                "source": "team_program_live",
                "overlap_group": "sunday-block",
                "base_opportunity_points": 50.0,
                "execution_multiplier": 0.3,
                "one_day_signal": 0.2,
                "stage_hunter_signal": 0.8,
                "gc_signal": 0.3,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.6,
                "sprint_bonus_signal": 0.5,
            },
        ]
    )
    frame = calculate_team_fit_components(frame, TEAM_PROFILE)
    frame["participation_confidence"] = calculate_participation_confidence(frame, TEAM_PROFILE)
    frame["expected_points"] = (
        frame["base_opportunity_points"]
        * frame["team_fit_multiplier"]
        * frame["participation_confidence"]
        * frame["execution_multiplier"]
    )
    return frame


def test_list_roster_scenario_presets_returns_expected_order() -> None:
    presets = list_roster_scenario_presets()

    assert [preset.key for preset in presets] == ["baseline_saved", "depth_constrained", "best_available"]
    assert presets[0].label == "Baseline Saved"


def test_build_roster_scenario_result_baseline_saved_is_identity() -> None:
    saved_ev_df = _build_saved_ev_frame()

    result = build_roster_scenario_result(saved_ev_df, TEAM_PROFILE, "baseline_saved")

    pd.testing.assert_series_equal(
        result.scenario_df["saved_expected_points"],
        result.scenario_df["scenario_expected_points"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        result.scenario_df["saved_team_fit_multiplier"],
        result.scenario_df["scenario_team_fit_multiplier"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        result.scenario_df["saved_participation_confidence"],
        result.scenario_df["scenario_participation_confidence"],
        check_names=False,
    )
    assert result.preset.key == "baseline_saved"


def test_build_roster_scenario_result_keeps_base_and_execution_frozen() -> None:
    saved_ev_df = _build_saved_ev_frame()

    result = build_roster_scenario_result(saved_ev_df, TEAM_PROFILE, "depth_constrained")

    pd.testing.assert_series_equal(
        saved_ev_df["base_opportunity_points"],
        result.scenario_df["base_opportunity_points"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        saved_ev_df["execution_multiplier"],
        result.scenario_df["execution_multiplier"],
        check_names=False,
    )
    assert any(result.scenario_df["expected_points_delta"].abs() > 1e-9)


def test_validate_roster_scenario_inputs_reports_missing_columns() -> None:
    with pytest.raises(ValueError, match="missing required roster scenario columns"):
        validate_roster_scenario_inputs(pd.DataFrame([{"race_name": "Incomplete"}]))
