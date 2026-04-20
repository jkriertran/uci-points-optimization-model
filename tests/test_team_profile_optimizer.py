import math

import pandas as pd
import pytest

from uci_points_model import team_profile_optimizer as module


def test_fit_team_strength_weights_is_deterministic_and_improves_baseline() -> None:
    target_weights = {
        "one_day": 0.31,
        "stage_hunter": 0.11,
        "gc": 0.08,
        "time_trial": 0.04,
        "all_round": 0.17,
        "sprint_bonus": 0.29,
    }
    calendar_ev_df = _synthetic_calendar_ev(target_weights)
    profile = _base_profile()

    result_one = module.fit_team_strength_weights(calendar_ev_df, profile)
    result_two = module.fit_team_strength_weights(calendar_ev_df, profile)

    assert result_one == result_two
    assert math.isclose(sum(result_one.weights.values()), 1.0, rel_tol=0, abs_tol=1e-5)
    assert result_one.weights["time_trial"] >= 0.01
    assert result_one.weight_fit_summary["rmse"] < result_one.weight_fit_summary["baseline_rmse"]
    assert result_one.weight_fit_summary["objective"] < 0.03
    assert abs(result_one.weights["one_day"] - target_weights["one_day"]) < 0.08
    assert abs(result_one.weights["sprint_bonus"] - target_weights["sprint_bonus"]) < 0.08


def test_fit_team_strength_weights_rejects_missing_actuals() -> None:
    calendar_ev_df = _synthetic_calendar_ev(_base_profile()["strength_weights"])
    calendar_ev_df["actual_points"] = pd.NA

    with pytest.raises(ValueError, match="known actual_points"):
        module.fit_team_strength_weights(calendar_ev_df, _base_profile())


def test_apply_weight_fit_to_profile_updates_optimizer_fields() -> None:
    result = module.TeamWeightFitResult(
        method=module.OPTIMIZER_METHOD,
        weights={
            "one_day": 0.2,
            "stage_hunter": 0.15,
            "gc": 0.15,
            "time_trial": 0.05,
            "all_round": 0.2,
            "sprint_bonus": 0.25,
        },
        weight_fit_summary={"known_race_count": 12, "rmse": 4.2},
    )

    updated_profile = module.apply_weight_fit_to_profile({"archetype_key": "balanced_opportunist"}, result)

    assert updated_profile["profile_version"] == "v2_optimizer"
    assert updated_profile["weight_fit_method"] == module.OPTIMIZER_METHOD
    assert updated_profile["weight_fit_summary"]["known_race_count"] == 12
    assert updated_profile["strength_weights"]["sprint_bonus"] == 0.25


def _synthetic_calendar_ev(target_weights: dict[str, float]) -> pd.DataFrame:
    signals = [
        (0.92, 0.10, 0.06, 0.00, 0.18, 0.84),
        (0.78, 0.25, 0.12, 0.02, 0.22, 0.70),
        (0.15, 0.74, 0.22, 0.04, 0.58, 0.48),
        (0.08, 0.30, 0.86, 0.08, 0.72, 0.12),
        (0.05, 0.08, 0.34, 0.88, 0.28, 0.06),
        (0.32, 0.52, 0.18, 0.04, 0.76, 0.42),
        (0.64, 0.12, 0.10, 0.03, 0.42, 0.63),
        (0.28, 0.26, 0.68, 0.06, 0.80, 0.18),
    ]
    exposures = [40.0, 52.0, 47.0, 64.0, 35.0, 59.0, 43.0, 56.0]
    target_vector = [target_weights[key] for key in module.TEAM_PROFILE_SIGNAL_KEYS]
    rows: list[dict[str, float | int]] = []
    for race_id, (row_signals, exposure) in enumerate(zip(signals, exposures, strict=True), start=1):
        weighted_signal = sum(weight * signal for weight, signal in zip(target_vector, row_signals, strict=True))
        actual_points = exposure * (0.7 + 0.3 * weighted_signal)
        rows.append(
            {
                "race_id": race_id,
                "base_opportunity_points": exposure,
                "participation_confidence": 1.0,
                "execution_multiplier": 1.0,
                "actual_points": round(actual_points, 6),
                "one_day_signal": row_signals[0],
                "stage_hunter_signal": row_signals[1],
                "gc_signal": row_signals[2],
                "time_trial_signal": row_signals[3],
                "all_round_signal": row_signals[4],
                "sprint_bonus_signal": row_signals[5],
            }
        )
    return pd.DataFrame(rows)


def _base_profile() -> dict[str, object]:
    return {
        "archetype_key": "classic_sprint_opportunist",
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
        "strength_weights": {
            "one_day": 0.18,
            "stage_hunter": 0.15,
            "gc": 0.15,
            "time_trial": 0.05,
            "all_round": 0.22,
            "sprint_bonus": 0.25,
        },
        "team_fit_floor": 0.7,
        "team_fit_range": 0.3,
    }
