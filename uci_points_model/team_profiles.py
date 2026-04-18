from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .calendar_ev import TEAM_PROFILE_SIGNAL_KEYS
from .team_identity import build_team_artifact_stem, canonicalize_team_slug

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACKED_PROTEAMS_MANIFEST = ROOT / "config" / "tracked_proteams_2026.csv"
DEFAULT_PROFILE_PATH = ROOT / "data" / "team_profiles" / "default_proteam_2026_profile.json"

PROFILE_AXIS_LABELS = {
    "one_day": "One-day / classics",
    "stage_hunter": "Stage hunter / sprinter",
    "gc": "GC / climbing",
    "time_trial": "Time trial",
    "all_round": "All-round stage depth",
    "sprint_bonus": "Sprint bonus",
}

PROFILE_CONFIDENCE_LEVELS = {"high", "medium", "low", "experimental"}
TEAM_PROFILE_TOP_LEVEL_ORDER = [
    "team_slug",
    "pcs_team_slug",
    "planning_year",
    "team_name",
    "archetype_key",
    "archetype_label",
    "archetype_description",
    "profile_confidence",
    "profile_rationale",
    "profile_version",
    "strength_weights",
    "team_fit_floor",
    "team_fit_range",
    "execution_rules",
    "participation_rules",
    "weight_fit_method",
    "weight_fit_summary",
    "strength_weight_rationale",
    "team_fit_rationale",
    "execution_rule_rationale",
    "participation_rule_rationale",
]
PROFILE_NESTED_KEY_ORDER = {
    "strength_weights": TEAM_PROFILE_SIGNAL_KEYS,
    "strength_weight_prior": TEAM_PROFILE_SIGNAL_KEYS,
    "execution_rules": ["1.1", "1.Pro", "1.UWT", "2.1", "2.Pro", "2.UWT"],
    "participation_rules": ["completed", "program_confirmed", "observed_startlist", "calendar_seed", "overlap_penalty"],
    "weight_fit_summary": [
        "known_race_count",
        "actual_points_total",
        "predicted_points_total",
        "season_gap",
        "mae",
        "rmse",
        "objective",
        "baseline_mae",
        "baseline_rmse",
        "baseline_season_gap",
        "prior_source",
        "effective_prior_strength",
        "effective_concentration_strength",
    ],
    "strength_weight_rationale": TEAM_PROFILE_SIGNAL_KEYS,
    "participation_rule_rationale": ["completed", "program_confirmed", "observed_startlist", "calendar_seed", "overlap_penalty"],
}


def profile_dir() -> Path:
    return ROOT / "data" / "team_profiles"


def archetype_catalog_path() -> Path:
    return ROOT / "config" / "team_archetypes.json"


def load_team_archetypes() -> dict[str, dict[str, Any]]:
    path = archetype_catalog_path()
    if not path.exists():
        raise FileNotFoundError(f"Team archetype catalog not found: {path}")
    raw_catalog = json.loads(path.read_text())
    if not isinstance(raw_catalog, dict) or not raw_catalog:
        raise ValueError("Team archetype catalog must be a non-empty object.")

    catalog: dict[str, dict[str, Any]] = {}
    for key, value in raw_catalog.items():
        entry = dict(value or {})
        label = str(entry.get("label") or "").strip()
        description = str(entry.get("description") or "").strip()
        if not label or not description:
            raise ValueError(f"Archetype catalog entry `{key}` must include non-empty label and description.")
        if entry.get("strength_weight_prior") is not None:
            entry["strength_weight_prior"] = _normalize_strength_weight_mapping(
                entry.get("strength_weight_prior"),
                field_name=f"team_archetypes.{key}.strength_weight_prior",
            )
        catalog[str(key)] = entry
    return catalog


def load_team_profile_by_path(path: str | Path) -> dict[str, Any]:
    profile_path = Path(path)
    if not profile_path.exists():
        raise FileNotFoundError(f"Team profile not found: {profile_path}")
    raw_profile = json.loads(profile_path.read_text())
    if not isinstance(raw_profile, dict):
        raise ValueError(f"Team profile at {profile_path} must be a JSON object.")
    return raw_profile


def load_team_profile(team_slug: str, planning_year: int | None = None) -> dict[str, Any]:
    stable_slug = canonicalize_team_slug(team_slug, planning_year or 0) if planning_year is not None else str(team_slug).strip()
    if not stable_slug:
        raise ValueError("team_slug must not be blank.")

    if planning_year is not None:
        profile_path = profile_dir() / f"{build_team_artifact_stem(stable_slug, planning_year)}_profile.json"
        return load_team_profile_by_path(profile_path)

    pattern = f"{stable_slug.replace('-', '_')}_*_profile.json"
    matches = sorted(profile_dir().glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No team profile override found for {stable_slug}.")
    if len(matches) > 1:
        raise ValueError(f"Multiple team profiles matched `{stable_slug}`; provide planning_year explicitly.")
    return load_team_profile_by_path(matches[0])


def list_available_team_profiles(
    manifest_path: str | Path = DEFAULT_TRACKED_PROTEAMS_MANIFEST,
    *,
    default_profile_path: str | Path = DEFAULT_PROFILE_PATH,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    archetypes = load_team_archetypes()
    default_profile = load_team_profile_by_path(default_profile_path)
    path = Path(manifest_path)

    if path.exists():
        manifest_df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for _, row in manifest_df.iterrows():
            raw_year = str(row.get("planning_year") or "").strip()
            if not raw_year:
                continue
            planning_year = int(raw_year)
            team_slug = canonicalize_team_slug(str(row.get("team_slug") or "").strip(), planning_year)
            profile_path_value = str(row.get("profile_path") or "").strip()
            profile_path = ROOT / profile_path_value if profile_path_value else None
            merged_profile = _deep_merge_dicts(
                default_profile,
                load_team_profile_by_path(profile_path) if profile_path else {},
            )
            merged_profile["team_slug"] = team_slug
            merged_profile["pcs_team_slug"] = str(row.get("pcs_team_slug") or "").strip()
            merged_profile["team_name"] = str(row.get("team_name") or "").strip()
            merged_profile["planning_year"] = planning_year
            prepared = validate_team_profile(merged_profile, archetypes)
            rows.append(
                {
                    "team_slug": team_slug,
                    "team_name": merged_profile["team_name"],
                    "planning_year": planning_year,
                    "profile_path": str(profile_path) if profile_path else "",
                    "archetype_key": prepared["archetype_key"],
                    "archetype_label": prepared["archetype_label"],
                    "profile_confidence": prepared.get("profile_confidence", ""),
                }
            )
        return pd.DataFrame(rows)

    for profile_path in sorted(profile_dir().glob("*_profile.json")):
        raw_profile = load_team_profile_by_path(profile_path)
        prepared = validate_team_profile(raw_profile, archetypes)
        rows.append(
            {
                "team_slug": str(raw_profile.get("team_slug") or ""),
                "team_name": str(raw_profile.get("team_name") or ""),
                "planning_year": raw_profile.get("planning_year"),
                "profile_path": str(profile_path),
                "archetype_key": prepared["archetype_key"],
                "archetype_label": prepared["archetype_label"],
                "profile_confidence": prepared.get("profile_confidence", ""),
            }
        )
    return pd.DataFrame(rows)


def validate_team_profile(
    profile: dict[str, Any],
    archetypes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("Team profile must be a dictionary.")

    catalog = archetypes or load_team_archetypes()
    prepared = _prepare_team_profile(profile, catalog)

    required_fields = [
        "strength_weights",
        "team_fit_floor",
        "team_fit_range",
        "execution_rules",
        "participation_rules",
        "archetype_key",
        "archetype_label",
        "archetype_description",
    ]
    missing_fields = [field for field in required_fields if field not in prepared]
    if missing_fields:
        raise ValueError(f"Team profile missing required fields: {', '.join(missing_fields)}")

    weights = dict(prepared.get("strength_weights") or {})
    missing_weight_keys = [key for key in TEAM_PROFILE_SIGNAL_KEYS if key not in weights]
    if missing_weight_keys:
        raise ValueError(f"Team profile missing strength weights for: {', '.join(missing_weight_keys)}")

    normalized_weights: dict[str, float] = {}
    for key in TEAM_PROFILE_SIGNAL_KEYS:
        value = _coerce_float(weights.get(key), f"strength_weights.{key}")
        if value < 0 or value > 1:
            raise ValueError(f"strength_weights.{key} must be between 0 and 1.")
        normalized_weights[key] = value
    if abs(sum(normalized_weights.values()) - 1.0) > 0.02:
        raise ValueError("Strength weights must sum to about 1.0.")
    prepared["strength_weights"] = normalized_weights

    for field_name in ["team_fit_floor", "team_fit_range"]:
        value = _coerce_float(prepared.get(field_name), field_name)
        if value < 0 or value > 1:
            raise ValueError(f"{field_name} must be between 0 and 1.")
        prepared[field_name] = value

    archetype_key = str(prepared.get("archetype_key") or "").strip()
    if archetype_key not in catalog:
        raise ValueError(f"Unknown archetype_key `{archetype_key}`.")
    catalog_entry = catalog[archetype_key]
    expected_label = str(catalog_entry.get("label") or "").strip()
    actual_label = str(prepared.get("archetype_label") or "").strip()
    if actual_label != expected_label:
        raise ValueError(f"archetype_label `{actual_label}` does not match catalog label `{expected_label}`.")
    if not str(prepared.get("archetype_description") or "").strip():
        raise ValueError("archetype_description must not be blank.")

    profile_confidence = str(prepared.get("profile_confidence") or "").strip()
    if profile_confidence and profile_confidence not in PROFILE_CONFIDENCE_LEVELS:
        raise ValueError(
            f"profile_confidence must be one of: {', '.join(sorted(PROFILE_CONFIDENCE_LEVELS))}."
        )
    if profile_confidence:
        prepared["profile_confidence"] = profile_confidence

    profile_rationale = prepared.get("profile_rationale", [])
    if not isinstance(profile_rationale, list):
        raise ValueError("profile_rationale must be a list of strings.")
    prepared["profile_rationale"] = [str(item).strip() for item in profile_rationale if str(item).strip()]

    for field_name in ["execution_rules", "participation_rules"]:
        numeric_rules = _validate_numeric_mapping(prepared.get(field_name), field_name)
        prepared[field_name] = numeric_rules

    for field_name in ["strength_weight_rationale", "participation_rule_rationale"]:
        if field_name in prepared and prepared[field_name] is not None:
            mapping = prepared[field_name]
            if not isinstance(mapping, dict):
                raise ValueError(f"{field_name} must be a mapping when present.")
            prepared[field_name] = {str(key): str(value).strip() for key, value in mapping.items() if str(value).strip()}

    for field_name in ["team_fit_rationale", "execution_rule_rationale", "profile_version"]:
        if field_name in prepared and prepared[field_name] is not None:
            prepared[field_name] = str(prepared[field_name]).strip()

    if "weight_fit_method" in prepared and prepared["weight_fit_method"] is not None:
        prepared["weight_fit_method"] = str(prepared["weight_fit_method"]).strip()
    if "weight_fit_summary" in prepared and prepared["weight_fit_summary"] is not None:
        summary = prepared["weight_fit_summary"]
        if not isinstance(summary, dict):
            raise ValueError("weight_fit_summary must be a mapping when present.")
        normalized_summary: dict[str, Any] = {}
        for key, value in summary.items():
            summary_key = str(key).strip()
            if not summary_key:
                continue
            if isinstance(value, bool):
                normalized_summary[summary_key] = value
            elif isinstance(value, (int, float)):
                normalized_summary[summary_key] = float(value)
            else:
                normalized_summary[summary_key] = str(value).strip()
        prepared["weight_fit_summary"] = normalized_summary

    return prepared


def infer_archetype(profile: dict[str, Any]) -> str:
    weights = _normalized_strength_weights(profile)
    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    top_key, top_value = ranked[0]
    second_key, second_value = ranked[1]

    if top_key == "sprint_bonus" and top_value - second_value >= 0.08:
        return "sprint_first"
    if top_key == "time_trial" and top_value >= 0.22:
        return "time_trial_edge"
    if {top_key, second_key} == {"one_day", "sprint_bonus"}:
        return "classic_sprint_opportunist"
    if top_key == "one_day" and weights["one_day"] - max(weights["gc"], weights["stage_hunter"]) >= 0.08:
        return "classic_specialist"
    if top_key == "stage_hunter" and weights["gc"] <= 0.2:
        return "stage_hunter"
    if weights["gc"] + weights["all_round"] >= 0.45 and top_key in {"gc", "all_round"}:
        return "gc_development"
    return "balanced_opportunist"


def describe_team_profile(profile: dict[str, Any]) -> dict[str, Any]:
    catalog = load_team_archetypes()
    prepared = validate_team_profile(profile, catalog)
    catalog_entry = dict(catalog.get(str(prepared["archetype_key"]), {}))
    return {
        "archetype_key": prepared["archetype_key"],
        "archetype_label": prepared["archetype_label"],
        "archetype_description": prepared["archetype_description"],
        "archetype_color": str(catalog_entry.get("color") or "").strip(),
        "profile_confidence": str(prepared.get("profile_confidence") or "").strip(),
        "profile_rationale": list(prepared.get("profile_rationale", [])),
    }


def format_team_profile_json(profile: dict[str, Any]) -> str:
    ordered_profile = _order_mapping(profile)
    return json.dumps(ordered_profile, indent=2) + "\n"


def write_team_profile_json(path: str | Path, profile: dict[str, Any]) -> None:
    profile_path = Path(path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(format_team_profile_json(profile))


def strength_weights_table(profile: dict[str, Any]) -> pd.DataFrame:
    prepared = validate_team_profile(profile, load_team_archetypes())
    return pd.DataFrame(
        [
            {
                "axis_key": axis,
                "Axis": PROFILE_AXIS_LABELS.get(axis, axis.replace("_", " ").title()),
                "Weight": float(prepared["strength_weights"][axis]),
            }
            for axis in TEAM_PROFILE_SIGNAL_KEYS
        ]
    )


def _prepare_team_profile(profile: dict[str, Any], archetypes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prepared = json.loads(json.dumps(profile))
    archetype_key = str(prepared.get("archetype_key") or "").strip()
    if not archetype_key:
        archetype_key = infer_archetype(prepared)
        prepared["archetype_key"] = archetype_key

    if archetype_key not in archetypes:
        raise ValueError(f"Unknown archetype_key `{archetype_key}`.")

    catalog_entry = archetypes[archetype_key]
    if not str(prepared.get("archetype_label") or "").strip():
        prepared["archetype_label"] = str(catalog_entry.get("label") or "").strip()
    if not str(prepared.get("archetype_description") or "").strip():
        prepared["archetype_description"] = str(catalog_entry.get("description") or "").strip()
    if "profile_rationale" not in prepared or prepared.get("profile_rationale") is None:
        prepared["profile_rationale"] = []
    return prepared


def _normalized_strength_weights(profile: dict[str, Any]) -> dict[str, float]:
    raw_weights = dict(profile.get("strength_weights") or {})
    numeric_weights = {
        key: max(0.0, float(raw_weights.get(key, 0.0)))
        for key in TEAM_PROFILE_SIGNAL_KEYS
    }
    total = sum(numeric_weights.values())
    if total <= 0:
        equal_weight = 1.0 / len(TEAM_PROFILE_SIGNAL_KEYS)
        return {key: equal_weight for key in TEAM_PROFILE_SIGNAL_KEYS}
    return {key: value / total for key, value in numeric_weights.items()}


def _normalize_strength_weight_mapping(value: Any, *, field_name: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a mapping.")
    normalized_weights: dict[str, float] = {}
    for key in TEAM_PROFILE_SIGNAL_KEYS:
        numeric_value = _coerce_float(value.get(key), f"{field_name}.{key}")
        if numeric_value < 0 or numeric_value > 1:
            raise ValueError(f"{field_name}.{key} must be between 0 and 1.")
        normalized_weights[key] = numeric_value
    if abs(sum(normalized_weights.values()) - 1.0) > 0.02:
        raise ValueError(f"{field_name} must sum to about 1.0.")
    return normalized_weights


def _validate_numeric_mapping(value: Any, field_name: str) -> dict[str, float]:
    mapping = dict(value or {})
    numeric_mapping: dict[str, float] = {}
    for key, raw_value in mapping.items():
        numeric_value = _coerce_float(raw_value, f"{field_name}.{key}")
        if numeric_value < 0 or numeric_value > 1:
            raise ValueError(f"{field_name}.{key} must be between 0 and 1.")
        numeric_mapping[str(key)] = numeric_value
    return numeric_mapping


def _coerce_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric.") from exc


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _order_mapping(mapping: dict[str, Any], *, parent_key: str | None = None) -> dict[str, Any]:
    preferred_keys = list(TEAM_PROFILE_TOP_LEVEL_ORDER if parent_key is None else PROFILE_NESTED_KEY_ORDER.get(parent_key, []))
    ordered: dict[str, Any] = {}
    for key in preferred_keys:
        if key in mapping:
            ordered[key] = _order_value(mapping[key], parent_key=key)
    for key in sorted(mapping.keys()):
        if key not in ordered:
            ordered[key] = _order_value(mapping[key], parent_key=key)
    return ordered


def _order_value(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        return _order_mapping(value, parent_key=parent_key)
    if isinstance(value, list):
        return [_order_value(item) for item in value]
    return value
