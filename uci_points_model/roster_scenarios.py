from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .calendar_ev import TEAM_PROFILE_SIGNAL_KEYS, calculate_participation_confidence, calculate_team_fit_components

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRESETS_PATH = ROOT / "config" / "roster_scenario_presets.json"
ROSTER_SCENARIO_FORMULA = (
    "base_opportunity_points * scenario_team_fit_multiplier * scenario_participation_confidence * execution_multiplier"
)
ROSTER_SCENARIO_SCOPE = "ui_only_saved_team_ev_overlay"
ROSTER_SCENARIO_REQUIRED_COLUMNS = [
    "base_opportunity_points",
    "team_fit_score",
    "team_fit_multiplier",
    "participation_confidence",
    "execution_multiplier",
    "expected_points",
    "status",
    "source",
    "overlap_group",
    *[f"{axis}_signal" for axis in TEAM_PROFILE_SIGNAL_KEYS],
]


@dataclass(frozen=True)
class RosterScenarioPreset:
    key: str
    label: str
    description: str
    profile_overrides: dict[str, Any]


@dataclass(frozen=True)
class RosterScenarioResult:
    preset: RosterScenarioPreset
    scenario_profile: dict[str, Any]
    scenario_df: pd.DataFrame


def get_roster_scenario_preset_version(path: str | Path = DEFAULT_PRESETS_PATH) -> str:
    catalog = load_roster_scenario_catalog(path)
    return str(catalog["preset_version"])


def list_roster_scenario_presets(path: str | Path = DEFAULT_PRESETS_PATH) -> list[RosterScenarioPreset]:
    catalog = load_roster_scenario_catalog(path)
    presets: list[RosterScenarioPreset] = []
    for item in catalog["presets"]:
        presets.append(
            RosterScenarioPreset(
                key=str(item["key"]),
                label=str(item["label"]),
                description=str(item["description"]),
                profile_overrides=dict(item.get("profile_overrides") or {}),
            )
        )
    return presets


def get_roster_scenario_preset(
    preset_key: str,
    path: str | Path = DEFAULT_PRESETS_PATH,
) -> RosterScenarioPreset:
    for preset in list_roster_scenario_presets(path):
        if preset.key == preset_key:
            return preset
    raise KeyError(f"Unknown roster scenario preset: {preset_key}")


def build_roster_scenario_result(
    calendar_ev_df: pd.DataFrame,
    saved_team_profile: dict[str, Any],
    preset_key: str,
    *,
    presets_path: str | Path = DEFAULT_PRESETS_PATH,
) -> RosterScenarioResult:
    validate_roster_scenario_inputs(calendar_ev_df)
    if not saved_team_profile:
        raise ValueError("saved_team_profile must not be empty.")

    preset = get_roster_scenario_preset(preset_key, presets_path)
    scenario_profile = build_roster_scenario_profile(saved_team_profile, preset)
    scenario_df = calendar_ev_df.copy()

    scenario_df["saved_specialty_fit_score"] = pd.to_numeric(
        scenario_df.get("specialty_fit_score"),
        errors="coerce",
    )
    scenario_df["saved_sprint_fit_bonus"] = pd.to_numeric(
        scenario_df.get("sprint_fit_bonus"),
        errors="coerce",
    )
    scenario_df["saved_team_fit_score"] = pd.to_numeric(scenario_df["team_fit_score"], errors="coerce")
    scenario_df["saved_team_fit_multiplier"] = pd.to_numeric(scenario_df["team_fit_multiplier"], errors="coerce")
    scenario_df["saved_participation_confidence"] = pd.to_numeric(
        scenario_df["participation_confidence"],
        errors="coerce",
    )
    scenario_df["saved_expected_points"] = pd.to_numeric(scenario_df["expected_points"], errors="coerce").fillna(0.0)

    recomputed_df = calculate_team_fit_components(scenario_df, scenario_profile)
    scenario_df["scenario_specialty_fit_score"] = pd.to_numeric(
        recomputed_df["specialty_fit_score"],
        errors="coerce",
    )
    scenario_df["scenario_sprint_fit_bonus"] = pd.to_numeric(
        recomputed_df["sprint_fit_bonus"],
        errors="coerce",
    )
    scenario_df["scenario_team_fit_score"] = pd.to_numeric(recomputed_df["team_fit_score"], errors="coerce")
    scenario_df["scenario_team_fit_multiplier"] = pd.to_numeric(
        recomputed_df["team_fit_multiplier"],
        errors="coerce",
    )
    scenario_df["scenario_participation_confidence"] = calculate_participation_confidence(
        scenario_df,
        scenario_profile,
    )
    scenario_df["scenario_expected_points"] = (
        pd.to_numeric(scenario_df["base_opportunity_points"], errors="coerce").fillna(0.0)
        * scenario_df["scenario_team_fit_multiplier"].fillna(1.0)
        * pd.to_numeric(scenario_df["scenario_participation_confidence"], errors="coerce").fillna(0.0)
        * pd.to_numeric(scenario_df["execution_multiplier"], errors="coerce").fillna(0.0)
    ).astype("Float64")
    scenario_df["expected_points_delta"] = (
        scenario_df["scenario_expected_points"] - scenario_df["saved_expected_points"]
    ).astype("Float64")
    scenario_df["team_fit_multiplier_delta"] = (
        scenario_df["scenario_team_fit_multiplier"] - scenario_df["saved_team_fit_multiplier"]
    ).astype("Float64")
    scenario_df["participation_confidence_delta"] = (
        pd.to_numeric(scenario_df["scenario_participation_confidence"], errors="coerce").fillna(0.0)
        - scenario_df["saved_participation_confidence"].fillna(0.0)
    ).astype("Float64")
    if "actual_points" in scenario_df.columns:
        scenario_df["scenario_ev_gap"] = (
            pd.to_numeric(scenario_df["actual_points"], errors="coerce")
            - scenario_df["scenario_expected_points"]
        ).astype("Float64")
    scenario_df["scenario_key"] = preset.key
    scenario_df["scenario_label"] = preset.label
    return RosterScenarioResult(preset=preset, scenario_profile=scenario_profile, scenario_df=scenario_df)


def build_roster_scenario_profile(
    saved_team_profile: dict[str, Any],
    preset: RosterScenarioPreset,
) -> dict[str, Any]:
    profile = dict(saved_team_profile)
    overrides = dict(preset.profile_overrides or {})

    if "strength_weights" in overrides:
        merged_weights = dict(saved_team_profile.get("strength_weights", {}))
        merged_weights.update(dict(overrides["strength_weights"] or {}))
        profile["strength_weights"] = _normalize_weights(merged_weights)

    if "team_fit_floor" in overrides:
        profile["team_fit_floor"] = float(overrides["team_fit_floor"])
    if "team_fit_range" in overrides:
        profile["team_fit_range"] = float(overrides["team_fit_range"])

    if "participation_rules" in overrides:
        merged_participation = dict(saved_team_profile.get("participation_rules", {}))
        merged_participation.update(
            {key: float(value) for key, value in dict(overrides["participation_rules"] or {}).items()}
        )
        profile["participation_rules"] = merged_participation

    return profile


def validate_roster_scenario_inputs(calendar_ev_df: pd.DataFrame) -> None:
    missing_columns = [column for column in ROSTER_SCENARIO_REQUIRED_COLUMNS if column not in calendar_ev_df.columns]
    if missing_columns:
        raise ValueError(
            "Calendar EV data is missing required roster scenario columns: " + ", ".join(missing_columns)
        )


def _normalize_weights(weights: dict[str, Any]) -> dict[str, float]:
    normalized = {
        axis: max(0.0, float(weights.get(axis, 0.0)))
        for axis in TEAM_PROFILE_SIGNAL_KEYS
    }
    total = sum(normalized.values())
    if total <= 0:
        equal_weight = 1.0 / len(TEAM_PROFILE_SIGNAL_KEYS)
        return {axis: equal_weight for axis in TEAM_PROFILE_SIGNAL_KEYS}
    return {axis: value / total for axis, value in normalized.items()}


@lru_cache(maxsize=4)
def _load_catalog_text(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Roster scenario preset catalog not found: {path}")
    raw_catalog = json.loads(path.read_text())
    if not isinstance(raw_catalog, dict):
        raise ValueError("Roster scenario preset catalog must be a JSON object.")
    return raw_catalog


def load_roster_scenario_catalog(path: str | Path = DEFAULT_PRESETS_PATH) -> dict[str, Any]:
    catalog = dict(_load_catalog_text(str(Path(path).resolve())))
    preset_version = str(catalog.get("preset_version") or "").strip()
    if not preset_version:
        raise ValueError("Roster scenario preset catalog must include preset_version.")

    preset_scope = str(catalog.get("roster_scenario_scope") or "").strip()
    if preset_scope and preset_scope != ROSTER_SCENARIO_SCOPE:
        raise ValueError(
            "Roster scenario preset catalog scope "
            f"`{preset_scope}` does not match expected `{ROSTER_SCENARIO_SCOPE}`."
        )

    raw_presets = list(catalog.get("presets") or [])
    if not raw_presets:
        raise ValueError("Roster scenario preset catalog must include at least one preset.")

    seen_keys: set[str] = set()
    normalized_presets: list[dict[str, Any]] = []
    for item in raw_presets:
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or "").strip()
        description = str(item.get("description") or "").strip()
        if not key or not label or not description:
            raise ValueError("Each roster scenario preset must include key, label, and description.")
        if key in seen_keys:
            raise ValueError(f"Duplicate roster scenario preset key: {key}")
        seen_keys.add(key)
        normalized_presets.append(
            {
                "key": key,
                "label": label,
                "description": description,
                "profile_overrides": dict(item.get("profile_overrides") or {}),
            }
        )

    if "baseline_saved" not in seen_keys:
        raise ValueError("Roster scenario preset catalog must include baseline_saved.")

    return {
        "preset_version": preset_version,
        "roster_scenario_scope": ROSTER_SCENARIO_SCOPE,
        "presets": normalized_presets,
    }
