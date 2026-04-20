from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .calendar_ev import TEAM_PROFILE_SIGNAL_KEYS
from .team_profiles import load_team_archetypes, validate_team_profile

OPTIMIZER_METHOD = "projected_quadratic_fit_v1"
SIGNAL_COLUMNS = [f"{axis}_signal" for axis in TEAM_PROFILE_SIGNAL_KEYS]
TRAINING_COLUMNS = [
    "base_opportunity_points",
    "participation_confidence",
    "execution_multiplier",
    "actual_points",
    *SIGNAL_COLUMNS,
]


@dataclass(frozen=True)
class TeamWeightFitConfig:
    prior_strength: float = 0.3
    concentration_strength: float = 0.05
    level_weight: float = 0.35
    min_time_trial_weight: float = 0.01
    max_iterations: int = 256
    tolerance: float = 1e-9


@dataclass(frozen=True)
class TeamWeightFitResult:
    method: str
    weights: dict[str, float]
    weight_fit_summary: dict[str, Any]


def build_weight_fit_training_frame(calendar_ev_df: pd.DataFrame) -> pd.DataFrame:
    missing_columns = [column for column in TRAINING_COLUMNS if column not in calendar_ev_df.columns]
    if missing_columns:
        raise ValueError(
            "Calendar EV data is missing required optimizer columns: " + ", ".join(missing_columns)
        )

    training_df = calendar_ev_df[TRAINING_COLUMNS].copy()
    numeric_columns = [
        "base_opportunity_points",
        "participation_confidence",
        "execution_multiplier",
        "actual_points",
        *SIGNAL_COLUMNS,
    ]
    for column in numeric_columns:
        training_df[column] = pd.to_numeric(training_df[column], errors="coerce")

    training_df = training_df.loc[training_df["actual_points"].notna()].reset_index(drop=True)
    if training_df.empty:
        raise ValueError("Calendar EV data has no rows with known actual_points.")
    return training_df


def fit_team_strength_weights(
    calendar_ev_df: pd.DataFrame,
    team_profile: dict[str, Any],
    *,
    fit_config: TeamWeightFitConfig | None = None,
    archetypes: dict[str, dict[str, Any]] | None = None,
) -> TeamWeightFitResult:
    config = fit_config or TeamWeightFitConfig()
    catalog = archetypes or load_team_archetypes()
    prepared_profile = validate_team_profile(team_profile, catalog)
    training_df = build_weight_fit_training_frame(calendar_ev_df)

    signal_matrix = training_df[SIGNAL_COLUMNS].fillna(0.0).clip(lower=0.0, upper=1.0).to_numpy(dtype=float)
    actual_points = training_df["actual_points"].to_numpy(dtype=float)
    exposure = (
        training_df["base_opportunity_points"].fillna(0.0).to_numpy(dtype=float)
        * training_df["participation_confidence"].fillna(0.0).to_numpy(dtype=float)
        * training_df["execution_multiplier"].fillna(0.0).to_numpy(dtype=float)
    )
    team_fit_floor = float(prepared_profile.get("team_fit_floor", 0.70))
    team_fit_range = float(prepared_profile.get("team_fit_range", 0.30))

    current_weights = _weights_to_array(prepared_profile["strength_weights"])
    prior_weights, prior_source = _resolve_prior_weights(prepared_profile, catalog)
    floor_vector = np.zeros(len(TEAM_PROFILE_SIGNAL_KEYS), dtype=float)
    floor_vector[TEAM_PROFILE_SIGNAL_KEYS.index("time_trial")] = float(config.min_time_trial_weight)

    baseline_weights = _project_to_simplex_with_floors(current_weights, floor_vector)
    prior_weights = _project_to_simplex_with_floors(prior_weights, floor_vector)

    effective_prior_strength = float(config.prior_strength) * max(1.0, 24.0 / float(len(training_df)))
    effective_concentration_strength = float(config.concentration_strength) * max(1.0, 18.0 / float(len(training_df)))
    target_multiplier = np.full(len(training_df), team_fit_floor, dtype=float)
    positive_exposure = exposure > 0
    target_multiplier[positive_exposure] = np.clip(
        actual_points[positive_exposure] / exposure[positive_exposure],
        team_fit_floor,
        1.0,
    )
    race_weights = np.sqrt(np.maximum(actual_points, 0.0) + 1.0)
    multiplier_matrix = team_fit_range * signal_matrix
    multiplier_offset = np.full(len(training_df), team_fit_floor, dtype=float)

    baseline_metrics = _objective_metrics(
        baseline_weights,
        multiplier_matrix=multiplier_matrix,
        multiplier_offset=multiplier_offset,
        race_weights=race_weights,
        target_multiplier=target_multiplier,
        exposure=exposure,
        actual_points=actual_points,
        prior_weights=prior_weights,
        prior_source=prior_source,
        effective_prior_strength=effective_prior_strength,
        effective_concentration_strength=effective_concentration_strength,
        level_weight=float(config.level_weight),
    )

    optimized_weights = _optimize_projected_weights(
        starting_weights=baseline_weights,
        prior_weights=prior_weights,
        floor_vector=floor_vector,
        multiplier_matrix=multiplier_matrix,
        multiplier_offset=multiplier_offset,
        race_weights=race_weights,
        target_multiplier=target_multiplier,
        effective_prior_strength=effective_prior_strength,
        effective_concentration_strength=effective_concentration_strength,
        level_weight=float(config.level_weight),
        max_iterations=int(config.max_iterations),
        tolerance=float(config.tolerance),
    )
    optimized_metrics = _objective_metrics(
        optimized_weights,
        multiplier_matrix=multiplier_matrix,
        multiplier_offset=multiplier_offset,
        race_weights=race_weights,
        target_multiplier=target_multiplier,
        exposure=exposure,
        actual_points=actual_points,
        prior_weights=prior_weights,
        prior_source=prior_source,
        effective_prior_strength=effective_prior_strength,
        effective_concentration_strength=effective_concentration_strength,
        level_weight=float(config.level_weight),
    )

    if optimized_metrics["objective"] > baseline_metrics["objective"]:
        chosen_weights = baseline_weights
        chosen_metrics = baseline_metrics
    else:
        chosen_weights = optimized_weights
        chosen_metrics = optimized_metrics

    summary = {
        "known_race_count": int(len(training_df)),
        "actual_points_total": round(float(chosen_metrics["actual_points_total"]), 3),
        "predicted_points_total": round(float(chosen_metrics["predicted_points_total"]), 3),
        "season_gap": round(float(chosen_metrics["season_gap"]), 3),
        "mae": round(float(chosen_metrics["mae"]), 3),
        "rmse": round(float(chosen_metrics["rmse"]), 3),
        "objective": round(float(chosen_metrics["objective"]), 6),
        "baseline_mae": round(float(baseline_metrics["mae"]), 3),
        "baseline_rmse": round(float(baseline_metrics["rmse"]), 3),
        "baseline_season_gap": round(float(baseline_metrics["season_gap"]), 3),
        "prior_source": prior_source,
        "effective_prior_strength": round(effective_prior_strength, 6),
        "effective_concentration_strength": round(effective_concentration_strength, 6),
    }
    return TeamWeightFitResult(
        method=OPTIMIZER_METHOD,
        weights={axis: round(float(value), 6) for axis, value in zip(TEAM_PROFILE_SIGNAL_KEYS, chosen_weights, strict=True)},
        weight_fit_summary=summary,
    )


def apply_weight_fit_to_profile(
    raw_profile: dict[str, Any],
    fit_result: TeamWeightFitResult,
    *,
    profile_version: str = "v2_optimizer",
) -> dict[str, Any]:
    updated_profile = dict(raw_profile)
    updated_profile["profile_version"] = profile_version
    updated_profile["strength_weights"] = dict(fit_result.weights)
    updated_profile["weight_fit_method"] = fit_result.method
    updated_profile["weight_fit_summary"] = dict(fit_result.weight_fit_summary)
    return updated_profile


def _resolve_prior_weights(
    team_profile: dict[str, Any],
    archetypes: dict[str, dict[str, Any]],
) -> tuple[np.ndarray, str]:
    archetype_key = str(team_profile.get("archetype_key") or "").strip()
    catalog_entry = dict(archetypes.get(archetype_key) or {})
    if catalog_entry.get("strength_weight_prior"):
        return _weights_to_array(catalog_entry["strength_weight_prior"]), f"archetype:{archetype_key}"
    return _weights_to_array(team_profile["strength_weights"]), "current_profile"


def _weights_to_array(weights: dict[str, Any]) -> np.ndarray:
    return np.asarray([float(weights.get(axis, 0.0)) for axis in TEAM_PROFILE_SIGNAL_KEYS], dtype=float)


def _optimize_projected_weights(
    *,
    starting_weights: np.ndarray,
    prior_weights: np.ndarray,
    floor_vector: np.ndarray,
    multiplier_matrix: np.ndarray,
    multiplier_offset: np.ndarray,
    race_weights: np.ndarray,
    target_multiplier: np.ndarray,
    effective_prior_strength: float,
    effective_concentration_strength: float,
    level_weight: float,
    max_iterations: int,
    tolerance: float,
) -> np.ndarray:
    weights = starting_weights.copy()
    weight_total = max(float(race_weights.sum()), 1e-9)
    diagonal_weights = race_weights[:, None]
    mean_vector = (multiplier_matrix.T @ race_weights) / weight_total

    hessian = (2.0 / weight_total) * (multiplier_matrix.T @ (diagonal_weights * multiplier_matrix))
    hessian += 2.0 * level_weight * np.outer(mean_vector, mean_vector)
    hessian += (2.0 * effective_prior_strength / float(len(TEAM_PROFILE_SIGNAL_KEYS))) * np.eye(len(TEAM_PROFILE_SIGNAL_KEYS))
    hessian += (2.0 * effective_concentration_strength) * np.eye(len(TEAM_PROFILE_SIGNAL_KEYS))
    lipschitz = max(float(np.linalg.eigvalsh(hessian).max()), 1e-9)

    for _ in range(max_iterations):
        predictions = multiplier_offset + multiplier_matrix @ weights
        residuals = predictions - target_multiplier
        weighted_mean_gap = float(np.dot(race_weights, residuals) / weight_total)
        gradient = (
            (2.0 / weight_total) * (multiplier_matrix.T @ (race_weights * residuals))
            + (2.0 * level_weight * weighted_mean_gap) * mean_vector
            + (2.0 * effective_prior_strength / float(len(TEAM_PROFILE_SIGNAL_KEYS))) * (weights - prior_weights)
            + (2.0 * effective_concentration_strength) * weights
        )
        candidate = _project_to_simplex_with_floors(weights - (gradient / lipschitz), floor_vector)
        if float(np.max(np.abs(candidate - weights))) <= tolerance:
            return candidate
        weights = candidate
    return weights


def _objective_metrics(
    weights: np.ndarray,
    *,
    multiplier_matrix: np.ndarray,
    multiplier_offset: np.ndarray,
    race_weights: np.ndarray,
    target_multiplier: np.ndarray,
    exposure: np.ndarray,
    actual_points: np.ndarray,
    prior_weights: np.ndarray,
    prior_source: str,
    effective_prior_strength: float,
    effective_concentration_strength: float,
    level_weight: float,
) -> dict[str, Any]:
    predicted_multiplier = multiplier_offset + multiplier_matrix @ weights
    multiplier_residuals = predicted_multiplier - target_multiplier
    weight_total = max(float(race_weights.sum()), 1e-9)
    weighted_squared_error = float(np.dot(race_weights, np.square(multiplier_residuals)) / weight_total)
    weighted_mean_gap = float(np.dot(race_weights, multiplier_residuals) / weight_total)
    prior_penalty = float(np.mean(np.square(weights - prior_weights)))
    concentration_penalty = float(np.sum(np.square(weights)))
    objective = (
        weighted_squared_error
        + level_weight * (weighted_mean_gap**2)
        + effective_prior_strength * prior_penalty
        + effective_concentration_strength * concentration_penalty
    )
    predicted_points = exposure * predicted_multiplier
    point_residuals = predicted_points - actual_points
    return {
        "actual_points_total": float(actual_points.sum()),
        "predicted_points_total": float(predicted_points.sum()),
        "season_gap": float(predicted_points.sum() - actual_points.sum()),
        "mae": float(np.mean(np.abs(point_residuals))),
        "rmse": float(np.sqrt(np.mean(np.square(point_residuals)))),
        "objective": objective,
        "prior_source": prior_source,
    }


def _project_to_simplex_with_floors(weights: np.ndarray, floor_vector: np.ndarray) -> np.ndarray:
    residual_total = 1.0 - float(floor_vector.sum())
    if residual_total <= 0:
        raise ValueError("Weight floors must sum to less than 1.0.")
    return floor_vector + _project_to_simplex(weights - floor_vector, total=residual_total)


def _project_to_simplex(values: np.ndarray, *, total: float = 1.0) -> np.ndarray:
    if total <= 0:
        raise ValueError("Simplex total must be positive.")
    shifted = np.asarray(values, dtype=float)
    if shifted.size == 1:
        return np.asarray([total], dtype=float)
    sorted_values = np.sort(shifted)[::-1]
    cumulative = np.cumsum(sorted_values) - total
    indices = np.arange(1, shifted.size + 1, dtype=float)
    condition = sorted_values - (cumulative / indices) > 0
    rho = int(indices[condition][-1]) if condition.any() else 1
    theta = cumulative[rho - 1] / float(rho)
    return np.maximum(shifted - theta, 0.0)
