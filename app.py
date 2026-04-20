from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from uci_points_model.backtest import calibrate_weights
from uci_points_model.calendar_ev import TEAM_PROFILE_SIGNAL_KEYS, calculate_team_fit_components
from uci_points_model.data import build_dataset, ensure_dataset_schema, load_calendar, load_snapshot
from uci_points_model.fc_client import PLANNING_CALENDAR_CATEGORIES, TARGET_CATEGORIES
from uci_points_model.model import (
    DEFAULT_SPECIALTY_WEIGHTS,
    DEFAULT_WEIGHTS,
    normalize_weights,
    normalize_specialty_weights,
    overlay_planning_calendar,
    score_race_editions,
    summarize_historical_targets,
)
from uci_points_model.pcs_client import CYCLE_SCOPE, CURRENT_SCOPE
from uci_points_model.proteam_risk import (
    build_proteam_risk_dataset,
    load_proteam_risk_snapshot,
    prepare_proteam_detail,
    summarize_proteam_risk,
)
from uci_points_model.roster_scenarios import (
    ROSTER_SCENARIO_FORMULA,
    ROSTER_SCENARIO_REQUIRED_COLUMNS,
    ROSTER_SCENARIO_SCOPE,
    build_roster_scenario_result,
    get_roster_scenario_preset_version,
    list_roster_scenario_presets,
)
from uci_points_model.team_profiles import describe_team_profile

SNAPSHOT_PATH = Path("data/race_editions_snapshot.csv")
PROTEAM_SCOPE_LABELS = {
    CURRENT_SCOPE: "Current season",
    CYCLE_SCOPE: "2026-2028 license cycle",
}
DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025]
DEFAULT_PLANNING_YEAR = date.today().year
WEIGHT_STATE_KEYS = {name: f"weight_{name}" for name in DEFAULT_WEIGHTS}
WEIGHT_DEFAULT_VERSION = "calibrated-one-day-v1"
DATASET_SCHEMA_VERSION = "stage-breakdown-v1"
PENDING_WEIGHT_STATE_KEY = "pending_weight_state"
CALIBRATION_RESULT_VERSION = "category-aware-v1"
TEAM_EV_DIR = Path("data/team_ev")
TEAM_PROFILE_DIR = Path("data/team_profiles")
DEFAULT_TEAM_PROFILE_PATH = Path("data/team_profiles/default_proteam_2026_profile.json")
TEAM_EV_DATASET_LABEL_KEY = "team_calendar_ev_dataset_label"
TEAM_EV_VIEW_MODE_OPTIONS = ["Active schedule", "Full saved calendar", "Completed races only"]
TEAM_EV_PRIMARY_METRIC_SPECS = (
    ("Total expected", "total_expected_points", 1, False),
    ("Actual points known", "actual_points_known", 1, False),
    ("Remaining expected", "remaining_expected_points", 1, False),
    ("EV gap known", "ev_gap_known", 1, True),
)
TEAM_EV_SECONDARY_FACT_SPECS = (
    ("Completed expected", "completed_expected_points", 1, False),
    ("Race count", "race_count", 0, False),
)
TEAM_EV_READER_DETAIL_COLUMNS = (
    "race_name",
    "category",
    "start_date",
    "status",
    "expected_points",
    "actual_points",
    "ev_gap",
    "notes",
)
TEAM_EV_ANALYST_DETAIL_COLUMNS = (
    "race_name",
    "category",
    "start_date",
    "status",
    "base_opportunity_points",
    "team_fit_multiplier",
    "participation_confidence",
    "execution_multiplier",
    "expected_points",
    "actual_points",
    "ev_gap",
    "source",
    "overlap_group",
    "notes",
)
TEAM_EV_DETAIL_VALUE_ROUNDING = {
    "base_opportunity_points": 1,
    "team_fit_multiplier": 3,
    "participation_confidence": 3,
    "execution_multiplier": 3,
    "expected_points": 1,
    "actual_points": 1,
    "ev_gap": 1,
}
CATEGORY_DISPLAY_ORDER = ["2.UWT", "1.UWT", "2.Pro", "1.Pro", "2.1", "1.1", "2.2", "1.2"]
TEAM_PROFILE_AXIS_LABELS = {
    "one_day": "One-day / classics",
    "stage_hunter": "Stage hunter / sprinter",
    "gc": "GC / climbing",
    "time_trial": "Time trial",
    "all_round": "All-round stage depth",
    "sprint_bonus": "Sprint bonus",
}
WORKSPACE_OPTIONS = [
    "Recommended Targets",
    "Edition Diagnostics",
    "Backtest & Calibration",
    "ProTeam Risk Monitor",
    "Team Calendar EV",
    "Data Sources",
]
TEAM_EV_BUILD_COMMAND = """python scripts/build_team_calendar_ev.py \\
  --team-slug <team-slug> \\
  --pcs-team-slug <pcs-team-slug> \\
  --planning-year <year> \\
  --team-profile-path data/team_profiles/<team_slug>_<year>_profile.json \\
  --calendar-path data/team_calendars/<team_slug>_<year>_latest.csv \\
  --actual-points-path data/team_results/<team_slug>_<year>_actual_points.csv \\
  --ev-output-path data/team_ev/<team_slug>_<year>_calendar_ev.csv \\
  --summary-output-path data/team_ev/<team_slug>_<year>_calendar_ev_summary.csv \\
  --readme-path data/team_ev/README.md \\
  --dictionary-path data/team_ev/data_dictionary.md"""


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def get_live_dataset(
    years: tuple[int, ...], categories: tuple[str, ...], max_races: int
) -> pd.DataFrame:
    return build_dataset(years=years, categories=categories, max_races=max_races)


@st.cache_data(show_spinner=False)
def get_calibration_result(
    dataset: pd.DataFrame, race_type: str, search_iterations: int, random_seed: int
) -> dict[str, object]:
    return calibrate_weights(
        dataset=dataset,
        race_type=race_type,
        search_iterations=search_iterations,
        random_seed=random_seed,
    )


@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)
def get_planning_calendar(year: int, categories: tuple[str, ...]) -> pd.DataFrame:
    return load_calendar(year=year, categories=categories)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def get_live_proteam_risk_dataset(scope: str) -> pd.DataFrame:
    dataset = build_proteam_risk_dataset(scope=scope)
    dataset.attrs["risk_data_source"] = "live"
    return dataset


@st.cache_data(show_spinner=False)
def load_local_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


@st.cache_data(show_spinner=False)
def load_local_json(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text())


@st.cache_data(show_spinner=False)
def load_default_team_profile() -> dict[str, object]:
    if not DEFAULT_TEAM_PROFILE_PATH.exists():
        return {}
    return load_local_json(str(DEFAULT_TEAM_PROFILE_PATH))


@st.cache_data(show_spinner=False)
def load_saved_team_profile(team_slug: str, planning_year: int) -> dict[str, object]:
    profile_path = TEAM_PROFILE_DIR / f"{team_slug.replace('-', '_')}_{int(planning_year)}_profile.json"
    if not profile_path.exists():
        return {}
    return load_local_json(str(profile_path))


@st.cache_data(show_spinner=False)
def discover_team_calendar_ev_datasets() -> pd.DataFrame:
    if not TEAM_EV_DIR.exists():
        return pd.DataFrame()

    datasets: list[dict[str, object]] = []
    for summary_path in sorted(TEAM_EV_DIR.glob("*_calendar_ev_summary.csv")):
        race_path = summary_path.with_name(summary_path.name.replace("_calendar_ev_summary.csv", "_calendar_ev.csv"))
        if not race_path.exists():
            continue

        try:
            summary_df = pd.read_csv(summary_path, low_memory=False)
            race_sample_df = pd.read_csv(race_path, low_memory=False, nrows=1)
        except Exception:  # noqa: BLE001
            continue

        if summary_df.empty:
            continue

        summary_row = summary_df.iloc[0]
        team_slug = str(summary_row.get("team_slug") or "").strip()
        planning_year = pd.to_numeric(summary_row.get("planning_year"), errors="coerce")
        if not team_slug or pd.isna(planning_year):
            continue

        team_name = ""
        if not race_sample_df.empty and "team_name" in race_sample_df.columns:
            team_name = str(race_sample_df["team_name"].iloc[0] or "").strip()
        if not team_name:
            team_name = team_slug.replace("-", " ").title()

        artifact_prefix = summary_path.name.replace("_calendar_ev_summary.csv", "")
        metadata_path = summary_path.with_name(summary_path.name.replace("_calendar_ev_summary.csv", "_calendar_ev_metadata.json"))
        calendar_path = Path("data/team_calendars") / f"{artifact_prefix}_latest.csv"
        actual_points_path = Path("data/team_results") / f"{artifact_prefix}_actual_points.csv"
        datasets.append(
            {
                "team_slug": team_slug,
                "planning_year": int(planning_year),
                "team_name": team_name,
                "label": f"{team_name} ({int(planning_year)})",
                "race_path": str(race_path),
                "summary_path": str(summary_path),
                "calendar_path": str(calendar_path) if calendar_path.exists() else "",
                "actual_points_path": str(actual_points_path) if actual_points_path.exists() else "",
                "metadata_path": str(metadata_path) if metadata_path.exists() else "",
            }
        )

    if not datasets:
        return pd.DataFrame()

    return (
        pd.DataFrame(datasets)
        .sort_values(["planning_year", "team_name"], ascending=[False, True])
        .reset_index(drop=True)
    )


def _select_team_calendar_dataset(team_slug: str, planning_year: int) -> pd.Series:
    datasets = discover_team_calendar_ev_datasets()
    if datasets.empty:
        raise KeyError("No Team Calendar EV datasets are available.")

    matches = datasets.loc[
        (datasets["team_slug"] == team_slug) & (datasets["planning_year"] == int(planning_year))
    ]
    if matches.empty:
        raise KeyError(f"Missing Team Calendar EV dataset for {team_slug} {planning_year}.")
    return matches.iloc[0]


@st.cache_data(show_spinner=False)
def load_team_calendar_ev(team_slug: str, planning_year: int) -> pd.DataFrame:
    dataset_row = _select_team_calendar_dataset(team_slug, planning_year)
    return pd.read_csv(dataset_row["race_path"], low_memory=False)


@st.cache_data(show_spinner=False)
def load_team_calendar_ev_summary(team_slug: str, planning_year: int) -> pd.DataFrame:
    dataset_row = _select_team_calendar_dataset(team_slug, planning_year)
    return pd.read_csv(dataset_row["summary_path"], low_memory=False)


@st.cache_data(show_spinner=False)
def load_team_calendar_ev_metadata(team_slug: str, planning_year: int) -> dict[str, object]:
    dataset_row = _select_team_calendar_dataset(team_slug, planning_year)
    metadata_path = str(dataset_row.get("metadata_path") or "").strip()
    metadata: dict[str, object] = {}
    if metadata_path:
        try:
            metadata = json.loads(Path(metadata_path).read_text())
        except Exception:  # noqa: BLE001
            metadata = {}

    fallback_profile = load_saved_team_profile(team_slug, planning_year)
    if fallback_profile:
        merged_profile = _merge_team_profile_defaults(dict(metadata.get("team_profile", {})), fallback_profile)
        metadata["team_profile"] = merged_profile
        metadata.setdefault("team_slug", team_slug)
        metadata.setdefault("planning_year", int(planning_year))
        if fallback_profile.get("team_name") and not metadata.get("team_name"):
            metadata["team_name"] = str(fallback_profile["team_name"])

    return metadata


@st.cache_data(show_spinner=False)
def load_team_calendar_snapshot(team_slug: str, planning_year: int) -> pd.DataFrame:
    dataset_row = _select_team_calendar_dataset(team_slug, planning_year)
    calendar_path = str(dataset_row.get("calendar_path") or "").strip()
    if not calendar_path:
        return pd.DataFrame()
    try:
        return pd.read_csv(calendar_path, low_memory=False)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def get_active_team_calendar_ev_dataset_row() -> pd.Series | None:
    datasets = discover_team_calendar_ev_datasets()
    if datasets.empty:
        return None

    selected_label = str(st.session_state.get(TEAM_EV_DATASET_LABEL_KEY) or "")
    matches = datasets.loc[datasets["label"] == selected_label]
    if matches.empty:
        return datasets.iloc[0]
    return matches.iloc[0]


def _filtered_team_calendar_ev(calendar_ev_df: pd.DataFrame, view_mode: str) -> pd.DataFrame:
    if calendar_ev_df.empty:
        return calendar_ev_df.copy()

    if view_mode == "Completed races only":
        return calendar_ev_df.loc[calendar_ev_df["status"] == "completed"].copy()
    if view_mode in {"Season so far", "Active schedule"}:
        return calendar_ev_df.loc[calendar_ev_df["status"] != "cancelled"].copy()
    return calendar_ev_df.copy()


def _team_calendar_ev_view_mode_labels() -> list[str]:
    return list(TEAM_EV_VIEW_MODE_OPTIONS)


def _format_team_calendar_ev_summary_value(value: object, *, decimals: int, signed: bool) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "Not available"

    if decimals <= 0:
        whole_value = int(round(float(numeric)))
        return f"{whole_value:+d}" if signed else f"{whole_value:d}"

    numeric_value = float(numeric)
    return f"{numeric_value:+.{decimals}f}" if signed else f"{numeric_value:.{decimals}f}"


def _team_calendar_ev_primary_metrics(summary_row: pd.Series | dict[str, object]) -> list[tuple[str, str]]:
    summary_mapping = dict(summary_row)
    return [
        (
            label,
            _format_team_calendar_ev_summary_value(
                summary_mapping.get(column),
                decimals=decimals,
                signed=signed,
            ),
        )
        for label, column, decimals, signed in TEAM_EV_PRIMARY_METRIC_SPECS
    ]


def _team_calendar_ev_secondary_facts(summary_row: pd.Series | dict[str, object]) -> list[str]:
    summary_mapping = dict(summary_row)
    return [
        f"{label}: {_format_team_calendar_ev_summary_value(summary_mapping.get(column), decimals=decimals, signed=signed)}"
        for label, column, decimals, signed in TEAM_EV_SECONDARY_FACT_SPECS
    ]


def _available_team_calendar_ev_columns(
    calendar_ev_df: pd.DataFrame,
    preferred_columns: tuple[str, ...],
) -> list[str]:
    return [column for column in preferred_columns if column in calendar_ev_df.columns]


def _team_calendar_ev_reader_detail_columns(calendar_ev_df: pd.DataFrame) -> list[str]:
    return _available_team_calendar_ev_columns(calendar_ev_df, TEAM_EV_READER_DETAIL_COLUMNS)


def _team_calendar_ev_analyst_detail_columns(calendar_ev_df: pd.DataFrame) -> list[str]:
    return _available_team_calendar_ev_columns(calendar_ev_df, TEAM_EV_ANALYST_DETAIL_COLUMNS)


def _merge_team_profile_defaults(
    saved_profile: dict[str, object],
    fallback_profile: dict[str, object],
) -> dict[str, object]:
    merged_profile = dict(fallback_profile)
    for key, value in saved_profile.items():
        if isinstance(value, dict) and isinstance(merged_profile.get(key), dict):
            nested_mapping = dict(merged_profile.get(key, {}))
            nested_mapping.update(value)
            merged_profile[key] = nested_mapping
            continue
        if isinstance(value, list):
            merged_profile[key] = value if value else list(merged_profile.get(key, []))
            continue
        if value not in (None, ""):
            merged_profile[key] = value
    return merged_profile


def _team_calendar_ev_explainability_label(value: object, *, bands: list[tuple[float, str]]) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "Not available"

    numeric_value = float(numeric)
    for threshold, label in bands:
        if numeric_value >= threshold:
            return f"{label} ({numeric_value:.2f})"
    return f"{bands[-1][1]} ({numeric_value:.2f})"


def _team_calendar_ev_participation_label(value: object, status: object) -> str:
    status_text = str(status or "").strip().lower()
    if status_text == "completed":
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.isna(numeric):
            return "Started"
        return f"Started ({float(numeric):.2f})"
    return _team_calendar_ev_explainability_label(
        value,
        bands=[
            (0.95, "Highly likely"),
            (0.85, "Likely"),
            (0.75, "Watch list"),
            (0.01, "Tentative"),
            (0.0, "Very unlikely"),
        ],
    )


def _team_calendar_ev_guided_detail_frame(calendar_ev_df: pd.DataFrame) -> pd.DataFrame:
    if calendar_ev_df.empty:
        return pd.DataFrame(
            columns=[
                "Race",
                "Category",
                "Date",
                "Status",
                "Team fit read",
                "Start confidence",
                "Execution read",
                "Expected pts",
                "Actual pts",
                "EV gap",
                "Notes",
            ]
        )

    detail_df = calendar_ev_df.copy().sort_values(["start_date", "race_name"]).reset_index(drop=True)
    object_defaults = pd.Series("", index=detail_df.index, dtype="object")
    numeric_defaults = pd.Series(index=detail_df.index, dtype="float64")
    return pd.DataFrame(
        {
            "Race": detail_df.get("race_name", object_defaults).fillna("").astype(str),
            "Category": detail_df.get("category", object_defaults).fillna("").astype(str),
            "Date": detail_df.get("start_date", object_defaults).fillna("").astype(str),
            "Status": detail_df.get("status", object_defaults).fillna("").astype(str).str.replace("_", " ").str.title(),
            "Team fit read": detail_df.get("team_fit_multiplier", numeric_defaults).apply(
                lambda value: _team_calendar_ev_explainability_label(
                    value,
                    bands=[
                        (0.95, "Strong fit"),
                        (0.85, "Good fit"),
                        (0.75, "Neutral fit"),
                        (0.0, "Weak fit"),
                    ],
                )
            ),
            "Start confidence": [
                _team_calendar_ev_participation_label(value, status)
                for value, status in zip(
                    detail_df.get("participation_confidence", numeric_defaults),
                    detail_df.get("status", object_defaults),
                    strict=False,
                )
            ],
            "Execution read": detail_df.get("execution_multiplier", numeric_defaults).apply(
                lambda value: _team_calendar_ev_explainability_label(
                    value,
                    bands=[
                        (0.35, "Favorable conversion"),
                        (0.25, "Standard conversion"),
                        (0.01, "Difficult conversion"),
                        (0.0, "No conversion signal"),
                    ],
                )
            ),
            "Expected pts": pd.to_numeric(detail_df.get("expected_points"), errors="coerce"),
            "Actual pts": pd.to_numeric(detail_df.get("actual_points"), errors="coerce"),
            "EV gap": pd.to_numeric(detail_df.get("ev_gap"), errors="coerce"),
            "Notes": detail_df.get("notes", object_defaults).fillna("").astype(str),
        }
    )


def _ordered_category_summary(category_df: pd.DataFrame) -> pd.DataFrame:
    if category_df.empty:
        return pd.DataFrame(columns=["category", "expected_points", "actual_points"])

    summary_df = category_df.copy()
    summary_df["expected_points"] = pd.to_numeric(summary_df["expected_points"], errors="coerce").fillna(0.0)
    summary_df["actual_points"] = pd.to_numeric(summary_df["actual_points"], errors="coerce").fillna(0.0)
    summary_df = (
        summary_df.groupby("category", dropna=False, as_index=False)
        .agg(expected_points=("expected_points", "sum"), actual_points=("actual_points", "sum"))
    )
    summary_df["category"] = summary_df["category"].fillna("Unknown").astype(str)
    existing_categories = summary_df["category"].tolist()
    category_order = [category for category in CATEGORY_DISPLAY_ORDER if category in existing_categories]
    category_order.extend(sorted(category for category in existing_categories if category not in category_order))
    category_rank = {category: index for index, category in enumerate(category_order)}
    summary_df["category_rank"] = summary_df["category"].map(category_rank).fillna(len(category_order))
    return summary_df.sort_values(["category_rank", "category"]).drop(columns=["category_rank"]).reset_index(drop=True)


def _normalized_iso_date(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return pd.Timestamp(text).date().isoformat()
    except Exception:  # noqa: BLE001
        return text


def _team_calendar_ev_freshness_context(
    metadata: dict[str, object],
    summary_row: pd.Series | dict[str, object],
    calendar_snapshot_df: pd.DataFrame,
) -> dict[str, object]:
    summary_mapping = dict(summary_row)
    ev_as_of = str(metadata.get("as_of_date") or summary_mapping.get("as_of_date") or "").strip()

    calendar_scraped_at = ""
    if not calendar_snapshot_df.empty and "scraped_at_utc" in calendar_snapshot_df.columns:
        scraped_series = pd.to_datetime(calendar_snapshot_df["scraped_at_utc"], errors="coerce", utc=True).dropna()
        if not scraped_series.empty:
            calendar_scraped_at = scraped_series.max().isoformat()

    ev_as_of_date = _normalized_iso_date(ev_as_of)
    calendar_scraped_date = _normalized_iso_date(calendar_scraped_at)
    has_drift = bool(ev_as_of_date and calendar_scraped_date and ev_as_of_date != calendar_scraped_date)

    warning_message = ""
    if has_drift:
        if calendar_scraped_date > ev_as_of_date:
            warning_message = (
                "The saved Team Calendar EV artifact is older than the underlying team calendar snapshot. "
                "Refresh the Team Calendar EV build to bring the EV summary back in sync."
            )
        else:
            warning_message = (
                "The saved Team Calendar EV artifact and the underlying team calendar snapshot report different "
                "freshness dates. Refresh the Team Calendar EV build to bring them back in sync."
            )

    return {
        "ev_as_of": ev_as_of,
        "calendar_scraped_at": calendar_scraped_at,
        "has_drift": has_drift,
        "warning_message": warning_message,
    }


def _sensitive_data_source_fields(items: list[str]) -> list[str]:
    return [
        item
        for item in items
        if any(token in item.casefold() for token in ("url", "pcs"))
    ]


def _contains_sensitive_data_source_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).casefold() for token in ("url", "pcs"))
            or _contains_sensitive_data_source_value(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_data_source_value(item) for item in value)
    if isinstance(value, str):
        normalized = value.casefold().strip()
        return (
            normalized.startswith("http://")
            or normalized.startswith("https://")
            or "procyclingstats" in normalized
            or " pcs " in f" {normalized} "
        )
    return False


def _sanitize_data_source_frame(frame: pd.DataFrame) -> pd.DataFrame:
    sanitized = frame.copy()
    hidden_columns = set(_sensitive_data_source_fields([str(column) for column in sanitized.columns]))
    for column in sanitized.columns:
        sample_values = sanitized[column].dropna().head(200).tolist()
        if any(_contains_sensitive_data_source_value(value) for value in sample_values):
            hidden_columns.add(column)
    if hidden_columns:
        sanitized = sanitized.drop(columns=list(hidden_columns), errors="ignore")
    return sanitized


def _sanitize_data_source_json(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _sanitize_data_source_json(item)
            for key, item in value.items()
            if not any(token in str(key).casefold() for token in ("url", "pcs"))
            and not _contains_sensitive_data_source_value(item)
        }
    if isinstance(value, list):
        sanitized_items: list[object] = []
        for item in value:
            if isinstance(item, (dict, list)):
                sanitized_item = _sanitize_data_source_json(item)
                if sanitized_item not in ({}, []):
                    sanitized_items.append(sanitized_item)
            elif not _contains_sensitive_data_source_value(item):
                sanitized_items.append(item)
        return sanitized_items
    return value


def get_active_team_calendar_ev_metadata() -> dict[str, object]:
    dataset_row = get_active_team_calendar_ev_dataset_row()
    if dataset_row is None:
        return {}
    return load_team_calendar_ev_metadata(str(dataset_row["team_slug"]), int(dataset_row["planning_year"]))


def render_team_calendar_ev_weight_explainer(metadata: dict[str, object]) -> None:
    if not metadata:
        return

    opportunity_model = dict(metadata.get("opportunity_model", {}))
    opportunity_weights = dict(opportunity_model.get("weights", {}))
    opportunity_rationale = dict(opportunity_model.get("rationale", {}))

    team_profile = dict(metadata.get("team_profile", {}))
    strength_weights = dict(team_profile.get("strength_weights", {}))
    strength_rationale = dict(team_profile.get("strength_weight_rationale", {}))
    execution_rules = dict(team_profile.get("execution_rules", {}))
    participation_rules = dict(team_profile.get("participation_rules", {}))
    participation_rationale = dict(team_profile.get("participation_rule_rationale", {}))

    team_name = str(metadata.get("team_name") or metadata.get("team_slug") or "").strip()
    planning_year = metadata.get("planning_year")
    if team_name and planning_year:
        st.caption(f"Saved Team Calendar EV weight assumptions for `{team_name}` in `{planning_year}`.")

    st.markdown(
        """
        Expected points are built in four layers:

        `base_opportunity_points × team_fit_multiplier × participation_confidence × execution_multiplier`

        The first term is the historical race-opportunity anchor. The next three terms translate that opportunity into a team-specific expectation.
        """
    )

    formula = str(metadata.get("expected_points_formula") or "").strip()
    if formula:
        st.caption(f"Saved formula: `{formula}`")

    if opportunity_weights:
        st.markdown("**1. Historical opportunity weights**")
        opportunity_frame = pd.DataFrame(
            [
                {
                    "Component": component,
                    "Weight": float(weight),
                    "Why it matters": opportunity_rationale.get(component, ""),
                }
                for component, weight in opportunity_weights.items()
            ]
        )
        st.dataframe(opportunity_frame.round({"Weight": 2}), use_container_width=True, hide_index=True)
        st.caption(
            "The heaviest weight sits on points efficiency, which is the clearest signal of payout value relative to field strength. The smaller payout and stage terms keep raw upside in the model without letting it drown out efficiency."
        )

    if strength_weights:
        st.markdown("**2. Team-fit weights**")
        strength_frame = pd.DataFrame(
            [
                {
                    "Axis": axis,
                    "Weight": float(weight),
                    "Why it matters": strength_rationale.get(axis, ""),
                }
                for axis, weight in strength_weights.items()
            ]
        )
        st.dataframe(strength_frame.round({"Weight": 2}), use_container_width=True, hide_index=True)
        st.caption(
            f"Team fit is bounded rather than open-ended: floor `{float(team_profile.get('team_fit_floor', 0.70)):.2f}` plus range `{float(team_profile.get('team_fit_range', 0.30)):.2f}` times the team-fit score."
        )
        if team_profile.get("team_fit_rationale"):
            st.caption(str(team_profile["team_fit_rationale"]))

    if execution_rules:
        st.markdown("**3. Execution multipliers by category**")
        execution_frame = pd.DataFrame(
            [{"Category": category, "Multiplier": float(value)} for category, value in execution_rules.items()]
        ).sort_values("Category")
        st.dataframe(execution_frame.round({"Multiplier": 2}), use_container_width=True, hide_index=True)
        if team_profile.get("execution_rule_rationale"):
            st.caption(str(team_profile["execution_rule_rationale"]))

    if participation_rules:
        st.markdown("**4. Participation confidence rules**")
        participation_frame = pd.DataFrame(
            [
                {
                    "Signal": signal,
                    "Confidence": float(value),
                    "Why it matters": participation_rationale.get(signal, ""),
                }
                for signal, value in participation_rules.items()
            ]
        )
        st.dataframe(participation_frame.round({"Confidence": 2}), use_container_width=True, hide_index=True)
        st.caption(
            "These values express how sure the model is that the team actually starts the race. Completed races get full confidence; future races are discounted unless there is stronger evidence than the planning calendar alone."
        )


def _team_profile_identity_context(metadata: dict[str, object]) -> dict[str, object]:
    team_profile = dict(metadata.get("team_profile", {}))
    if not team_profile:
        return {}

    description = describe_team_profile(team_profile)
    return {
        "team_name": str(metadata.get("team_name") or metadata.get("team_slug") or "").strip(),
        "archetype_label": str(description.get("archetype_label") or "").strip(),
        "archetype_description": str(description.get("archetype_description") or "").strip(),
        "profile_confidence": str(description.get("profile_confidence") or "").strip(),
        "profile_rationale": list(description.get("profile_rationale", [])),
    }


def render_team_profile_identity_block(metadata: dict[str, object]) -> None:
    context = _team_profile_identity_context(metadata)
    if not context:
        return

    st.markdown("**Team Identity**")
    left_column, right_column = st.columns([3, 1])
    with left_column:
        if context["team_name"]:
            st.caption(f"Saved profile context for `{context['team_name']}`.")
        st.markdown(f"`{context['archetype_label']}`")
        st.write(context["archetype_description"])
    with right_column:
        confidence = str(context.get("profile_confidence") or "").strip()
        if confidence:
            st.metric("Profile confidence", confidence.title())

    st.caption("These are analyst-set planning defaults, not rider-level forecasts.")
    st.caption(
        "The team profile does not change how many points a race is worth in general. It changes how suitable that race looks for the selected team."
    )
    rationale = list(context.get("profile_rationale", []))
    if rationale:
        with st.expander("Why this default profile?", expanded=False):
            st.markdown("\n".join(f"- {reason}" for reason in rationale))


def _normalize_team_profile_weights(weights: dict[str, float]) -> dict[str, float]:
    normalized = {
        axis: max(0.0, float(weights.get(axis, 0.0)))
        for axis in TEAM_PROFILE_SIGNAL_KEYS
    }
    total = sum(normalized.values())
    if total <= 0:
        equal_weight = 1.0 / len(TEAM_PROFILE_SIGNAL_KEYS)
        return {axis: equal_weight for axis in TEAM_PROFILE_SIGNAL_KEYS}
    return {axis: value / total for axis, value in normalized.items()}


def _team_profile_state_prefix(team_slug: str, planning_year: int) -> str:
    return f"team_profile_sandbox_{team_slug}_{planning_year}"


def _apply_team_profile_preset(prefix: str, weights: dict[str, float], team_fit_floor: float, team_fit_range: float) -> None:
    normalized_weights = _normalize_team_profile_weights(weights)
    for axis, value in normalized_weights.items():
        st.session_state[f"{prefix}_{axis}"] = float(value)
    st.session_state[f"{prefix}_team_fit_floor"] = float(team_fit_floor)
    st.session_state[f"{prefix}_team_fit_range"] = float(team_fit_range)
    st.session_state[f"{prefix}_initialized"] = True


def _ensure_team_profile_sandbox_state(
    prefix: str,
    saved_profile: dict[str, object],
) -> None:
    normalized_weights = _normalize_team_profile_weights(dict(saved_profile.get("strength_weights", {})))
    missing_keys: list[tuple[str, float]] = []
    for axis, value in normalized_weights.items():
        state_key = f"{prefix}_{axis}"
        if state_key not in st.session_state:
            missing_keys.append((state_key, float(value)))

    floor_key = f"{prefix}_team_fit_floor"
    range_key = f"{prefix}_team_fit_range"
    if floor_key not in st.session_state:
        missing_keys.append((floor_key, float(saved_profile.get("team_fit_floor", 0.70))))
    if range_key not in st.session_state:
        missing_keys.append((range_key, float(saved_profile.get("team_fit_range", 0.30))))

    if not st.session_state.get(f"{prefix}_initialized") or missing_keys:
        for state_key, value in missing_keys:
            st.session_state[state_key] = value
        if not st.session_state.get(f"{prefix}_initialized") and not missing_keys:
            _apply_team_profile_preset(
                prefix,
                normalized_weights,
                float(saved_profile.get("team_fit_floor", 0.70)),
                float(saved_profile.get("team_fit_range", 0.30)),
            )
        else:
            st.session_state[f"{prefix}_initialized"] = True


def _team_profile_status_label(saved_profile: dict[str, object], default_profile: dict[str, object]) -> str:
    if not default_profile:
        return "Saved"
    saved_weights = _normalize_team_profile_weights(dict(saved_profile.get("strength_weights", {})))
    default_weights = _normalize_team_profile_weights(dict(default_profile.get("strength_weights", {})))
    saved_floor = float(saved_profile.get("team_fit_floor", 0.70))
    default_floor = float(default_profile.get("team_fit_floor", 0.70))
    saved_range = float(saved_profile.get("team_fit_range", 0.30))
    default_range = float(default_profile.get("team_fit_range", 0.30))
    same_weights = all(abs(saved_weights[axis] - default_weights[axis]) < 1e-9 for axis in TEAM_PROFILE_SIGNAL_KEYS)
    same_fit = abs(saved_floor - default_floor) < 1e-9 and abs(saved_range - default_range) < 1e-9
    return "Default-like" if same_weights and same_fit else "Custom"


def _has_team_profile_sandbox_inputs(race_df: pd.DataFrame) -> bool:
    required_columns = {
        "base_opportunity_points",
        "participation_confidence",
        "execution_multiplier",
        "expected_points",
        "team_fit_score",
        "team_fit_multiplier",
        *{f"{axis}_signal" for axis in TEAM_PROFILE_SIGNAL_KEYS},
    }
    return required_columns.issubset(set(race_df.columns))


def _has_roster_scenario_inputs(race_df: pd.DataFrame) -> bool:
    return set(ROSTER_SCENARIO_REQUIRED_COLUMNS).issubset(set(race_df.columns))


def _build_team_profile_sandbox_frame(race_df: pd.DataFrame, sandbox_profile: dict[str, object]) -> pd.DataFrame:
    scenario_df = race_df.copy()
    scenario_df["saved_expected_points"] = pd.to_numeric(scenario_df["expected_points"], errors="coerce").fillna(0.0)
    scenario_df["saved_team_fit_score"] = pd.to_numeric(scenario_df["team_fit_score"], errors="coerce")
    scenario_df["saved_team_fit_multiplier"] = pd.to_numeric(scenario_df["team_fit_multiplier"], errors="coerce")
    scenario_df = calculate_team_fit_components(scenario_df, sandbox_profile)
    scenario_df["sandbox_expected_points"] = (
        pd.to_numeric(scenario_df["base_opportunity_points"], errors="coerce").fillna(0.0)
        * pd.to_numeric(scenario_df["team_fit_multiplier"], errors="coerce").fillna(1.0)
        * pd.to_numeric(scenario_df["participation_confidence"], errors="coerce").fillna(0.0)
        * pd.to_numeric(scenario_df["execution_multiplier"], errors="coerce").fillna(0.0)
    )
    scenario_df["expected_points_delta"] = scenario_df["sandbox_expected_points"] - scenario_df["saved_expected_points"]
    scenario_df = scenario_df.rename(
        columns={
            "specialty_fit_score": "sandbox_specialty_fit_score",
            "sprint_fit_bonus": "sandbox_sprint_fit_bonus",
            "team_fit_score": "sandbox_team_fit_score",
            "team_fit_multiplier": "sandbox_team_fit_multiplier",
        }
    )
    return scenario_df


def _build_roster_scenario_assumption_frame(
    saved_profile: dict[str, object],
    scenario_profile: dict[str, object],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "Setting": "Team-fit floor",
            "Saved profile": float(saved_profile.get("team_fit_floor", 0.70)),
            "Scenario": float(scenario_profile.get("team_fit_floor", 0.70)),
        },
        {
            "Setting": "Team-fit range",
            "Saved profile": float(saved_profile.get("team_fit_range", 0.30)),
            "Scenario": float(scenario_profile.get("team_fit_range", 0.30)),
        },
    ]

    saved_rules = dict(saved_profile.get("participation_rules", {}))
    scenario_rules = dict(scenario_profile.get("participation_rules", {}))
    for rule_key, label in [
        ("completed", "Participation: completed"),
        ("program_confirmed", "Participation: program confirmed"),
        ("observed_startlist", "Participation: observed startlist"),
        ("calendar_seed", "Participation: calendar seed"),
        ("overlap_penalty", "Participation: overlap penalty"),
    ]:
        rows.append(
            {
                "Setting": label,
                "Saved profile": float(saved_rules.get(rule_key, 0.0)),
                "Scenario": float(scenario_rules.get(rule_key, 0.0)),
            }
        )

    saved_weights = _normalize_team_profile_weights(dict(saved_profile.get("strength_weights", {})))
    scenario_weights = _normalize_team_profile_weights(dict(scenario_profile.get("strength_weights", {})))
    for axis in TEAM_PROFILE_SIGNAL_KEYS:
        if abs(saved_weights[axis] - scenario_weights[axis]) < 1e-9:
            continue
        rows.append(
            {
                "Setting": f"Weight: {TEAM_PROFILE_AXIS_LABELS[axis]}",
                "Saved profile": saved_weights[axis],
                "Scenario": scenario_weights[axis],
            }
        )

    return pd.DataFrame(rows)


def render_team_profile_sandbox(
    race_df: pd.DataFrame,
    metadata: dict[str, object],
    team_slug: str,
    planning_year: int,
    view_mode: str,
) -> None:
    team_profile = dict(metadata.get("team_profile", {}))
    strength_weights = dict(team_profile.get("strength_weights", {}))
    if not team_profile or not strength_weights:
        return

    default_profile = load_default_team_profile()
    default_strength_weights = dict(default_profile.get("strength_weights", {}))
    saved_weights = _normalize_team_profile_weights(strength_weights)
    default_weights = _normalize_team_profile_weights(default_strength_weights or strength_weights)
    saved_profile_status = _team_profile_status_label(team_profile, default_profile)

    with st.expander("Team Profile Sandbox", expanded=False):
        st.caption(
            f"Saved profile type: `{saved_profile_status}`. The KPI summary and story charts above stay tied to the saved artifact. "
            "The sandbox below is a non-persistent what-if view for this workspace only."
        )
        st.markdown(
            """
            Use this to stress-test how the team-specific fit layer changes the saved EV view.

            - `Historical opportunity` stays fixed.
            - `Participation confidence` and `execution multipliers` stay fixed.
            - Only the `team_fit` layer is being changed here.
            """
        )
        if not _has_team_profile_sandbox_inputs(race_df):
            st.info(
                "This saved artifact does not include the raw team-fit signal columns needed for the sandbox yet. "
                "Refresh the team artifact to enable live team-profile what-if analysis."
            )
            return

        prefix = _team_profile_state_prefix(team_slug, planning_year)
        _ensure_team_profile_sandbox_state(prefix, team_profile)

        action_left, action_mid, action_right = st.columns([1, 1, 2])
        with action_left:
            if st.button("Load saved profile", key=f"{prefix}_load_saved"):
                _apply_team_profile_preset(
                    prefix,
                    saved_weights,
                    float(team_profile.get("team_fit_floor", 0.70)),
                    float(team_profile.get("team_fit_range", 0.30)),
                )
                st.rerun()
        with action_mid:
            if st.button("Load default profile", key=f"{prefix}_load_default"):
                _apply_team_profile_preset(
                    prefix,
                    default_weights,
                    float(default_profile.get("team_fit_floor", 0.70)),
                    float(default_profile.get("team_fit_range", 0.30)),
                )
                st.rerun()
        with action_right:
            st.caption("Sandbox sliders are normalized to relative emphasis, just like the main race-opportunity controls.")

        slider_columns = st.columns(2)
        for index, axis in enumerate(TEAM_PROFILE_SIGNAL_KEYS):
            with slider_columns[index % 2]:
                st.slider(
                    TEAM_PROFILE_AXIS_LABELS[axis],
                    min_value=0.0,
                    max_value=1.0,
                    value=float(st.session_state[f"{prefix}_{axis}"]),
                    step=0.05,
                    key=f"{prefix}_{axis}",
                )

        with st.expander("Advanced fit bounds", expanded=False):
            st.slider(
                "Team-fit floor",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state[f"{prefix}_team_fit_floor"]),
                step=0.05,
                key=f"{prefix}_team_fit_floor",
                help="Minimum team-fit multiplier when the fit score is weakest.",
            )
            st.slider(
                "Team-fit range",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state[f"{prefix}_team_fit_range"]),
                step=0.05,
                key=f"{prefix}_team_fit_range",
                help="How much team fit is allowed to move the multiplier above the floor.",
            )

        sandbox_weights = _normalize_team_profile_weights(
            {axis: float(st.session_state[f"{prefix}_{axis}"]) for axis in TEAM_PROFILE_SIGNAL_KEYS}
        )
        sandbox_profile = dict(team_profile)
        sandbox_profile["strength_weights"] = sandbox_weights
        sandbox_profile["team_fit_floor"] = float(st.session_state[f"{prefix}_team_fit_floor"])
        sandbox_profile["team_fit_range"] = float(st.session_state[f"{prefix}_team_fit_range"])
        scenario_df = _build_team_profile_sandbox_frame(race_df, sandbox_profile)

        comparison_frame = pd.DataFrame(
            [
                {
                    "Axis": TEAM_PROFILE_AXIS_LABELS[axis],
                    "Default profile": default_weights[axis],
                    "Saved artifact": saved_weights[axis],
                    "Sandbox": sandbox_weights[axis],
                }
                for axis in TEAM_PROFILE_SIGNAL_KEYS
            ]
        )
        st.dataframe(comparison_frame.round(3), use_container_width=True, hide_index=True)

        saved_total_expected = float(scenario_df["saved_expected_points"].sum())
        sandbox_total_expected = float(scenario_df["sandbox_expected_points"].sum())
        delta_total_expected = sandbox_total_expected - saved_total_expected
        metric_left, metric_mid, metric_right = st.columns(3)
        metric_left.metric("Saved expected", f"{saved_total_expected:.1f}")
        metric_mid.metric("Sandbox expected", f"{sandbox_total_expected:.1f}")
        metric_right.metric("Sandbox delta", f"{delta_total_expected:+.1f}")
        st.caption(f"Sandbox totals follow the current `{view_mode}` filter, not the full saved season summary row above.")

        movers_df = (
            scenario_df.assign(delta_abs=lambda df: df["expected_points_delta"].abs())
            .sort_values(["delta_abs", "sandbox_expected_points"], ascending=[False, False])
            .head(10)
        )
        mover_columns = [
            "race_name",
            "route_profile",
            "saved_team_fit_score",
            "sandbox_team_fit_score",
            "saved_team_fit_multiplier",
            "sandbox_team_fit_multiplier",
            "saved_expected_points",
            "sandbox_expected_points",
            "expected_points_delta",
        ]
        st.markdown("**Biggest race moves under the sandbox profile**")
        st.dataframe(
            movers_df[mover_columns].round(
                {
                    "saved_team_fit_score": 3,
                    "sandbox_team_fit_score": 3,
                    "saved_team_fit_multiplier": 3,
                    "sandbox_team_fit_multiplier": 3,
                    "saved_expected_points": 1,
                    "sandbox_expected_points": 1,
                    "expected_points_delta": 1,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        sandbox_profile_preview = {
            "archetype_description": str(team_profile.get("archetype_description") or ""),
            "archetype_key": str(team_profile.get("archetype_key") or ""),
            "archetype_label": str(team_profile.get("archetype_label") or ""),
            "profile_confidence": str(team_profile.get("profile_confidence") or ""),
            "profile_rationale": list(team_profile.get("profile_rationale", [])),
            "team_slug": str(metadata.get("team_slug") or team_slug),
            "team_name": str(metadata.get("team_name") or team_slug),
            "planning_year": int(metadata.get("planning_year") or planning_year),
            "strength_weights": sandbox_weights,
            "team_fit_floor": float(sandbox_profile["team_fit_floor"]),
            "team_fit_range": float(sandbox_profile["team_fit_range"]),
            "execution_rules": dict(team_profile.get("execution_rules", {})),
            "participation_rules": dict(team_profile.get("participation_rules", {})),
        }
        st.download_button(
            "Download sandbox profile JSON",
            data=(json.dumps(sandbox_profile_preview, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            file_name=f"{team_slug}_{planning_year}_sandbox_profile.json",
            mime="application/json",
        )


def render_roster_scenario_overlay(
    race_df: pd.DataFrame,
    metadata: dict[str, object],
    team_slug: str,
    planning_year: int,
    view_mode: str,
) -> None:
    team_profile = dict(metadata.get("team_profile", {}))
    if not team_profile:
        return

    with st.expander("Roster Scenario Overlay", expanded=False):
        st.caption(
            "This is a UI-only deterministic what-if layer built from the saved Team Calendar EV artifact. "
            "It does not rebuild history or write new scenario artifacts."
        )

        if not _has_roster_scenario_inputs(race_df):
            st.info(
                "This saved artifact does not include the full set of columns needed for the roster scenario overlay yet. "
                "Refresh the Team Calendar EV artifact to enable deterministic roster scenarios."
            )
            return

        presets = list_roster_scenario_presets()
        preset_keys = [preset.key for preset in presets]
        preset_lookup = {preset.key: preset for preset in presets}
        selected_preset_key = st.selectbox(
            "Roster scenario",
            options=preset_keys,
            index=0,
            format_func=lambda key: preset_lookup[key].label,
            key=f"roster_scenario_{team_slug}_{planning_year}",
        )
        scenario_result = build_roster_scenario_result(race_df, team_profile, selected_preset_key)
        preset = scenario_result.preset
        scenario_profile = scenario_result.scenario_profile
        scenario_df = scenario_result.scenario_df

        scenario_formula = str(metadata.get("roster_scenario_formula") or ROSTER_SCENARIO_FORMULA).strip()
        scenario_scope = str(metadata.get("roster_scenario_scope") or ROSTER_SCENARIO_SCOPE).strip()
        preset_version = str(metadata.get("roster_scenario_preset_version") or get_roster_scenario_preset_version()).strip()
        st.caption(preset.description)
        st.caption(
            f"Scope `{scenario_scope}`. Preset catalog `{preset_version}`. "
            f"The scenario formula is `{scenario_formula}`."
        )

        metric_left, metric_mid, metric_right, metric_far = st.columns(4)
        saved_total_expected = float(scenario_df["saved_expected_points"].sum())
        scenario_total_expected = float(scenario_df["scenario_expected_points"].sum())
        delta_total_expected = scenario_total_expected - saved_total_expected
        changed_race_count = int((scenario_df["expected_points_delta"].abs() > 1e-9).sum())
        metric_left.metric("Saved expected", f"{saved_total_expected:.1f}")
        metric_mid.metric("Scenario expected", f"{scenario_total_expected:.1f}")
        metric_right.metric("Scenario delta", f"{delta_total_expected:+.1f}")
        metric_far.metric("Races moved", changed_race_count)
        st.caption(f"Scenario totals follow the current `{view_mode}` filter, not the full saved season summary row above.")

        assumption_frame = _build_roster_scenario_assumption_frame(team_profile, scenario_profile)
        st.dataframe(assumption_frame.round(3), use_container_width=True, hide_index=True)

        movers_df = (
            scenario_df.assign(delta_abs=lambda df: df["expected_points_delta"].abs())
            .sort_values(["delta_abs", "scenario_expected_points"], ascending=[False, False])
            .head(10)
        )
        mover_columns = [
            "race_name",
            "route_profile",
            "saved_team_fit_multiplier",
            "scenario_team_fit_multiplier",
            "saved_participation_confidence",
            "scenario_participation_confidence",
            "saved_expected_points",
            "scenario_expected_points",
            "expected_points_delta",
        ]
        available_mover_columns = [column for column in mover_columns if column in movers_df.columns]
        st.markdown("**Biggest race moves under the selected roster scenario**")
        st.dataframe(
            movers_df[available_mover_columns].round(
                {
                    "saved_team_fit_multiplier": 3,
                    "scenario_team_fit_multiplier": 3,
                    "saved_participation_confidence": 3,
                    "scenario_participation_confidence": 3,
                    "saved_expected_points": 1,
                    "scenario_expected_points": 1,
                    "expected_points_delta": 1,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download scenario-adjusted CSV",
            data=scenario_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{team_slug}_{planning_year}_{preset.key}_scenario.csv",
            mime="text/csv",
        )


def render_team_calendar_ev_workspace() -> None:
    st.subheader("Team Calendar EV")
    datasets = discover_team_calendar_ev_datasets()
    if datasets.empty:
        st.info("No Team Calendar EV artifacts are available yet.")
        st.caption("Build the saved artifacts first, then this workspace will discover them automatically.")
        st.code(TEAM_EV_BUILD_COMMAND, language="bash")
        return

    selector_left, selector_mid, selector_right = st.columns([2, 1, 1])
    options = datasets["label"].tolist()
    if TEAM_EV_DATASET_LABEL_KEY not in st.session_state or st.session_state[TEAM_EV_DATASET_LABEL_KEY] not in options:
        st.session_state[TEAM_EV_DATASET_LABEL_KEY] = options[0]
    with selector_left:
        selected_label = st.selectbox(
            "Team-season",
            options=options,
            key=TEAM_EV_DATASET_LABEL_KEY,
            disabled=len(options) == 1,
        )
    dataset_row = datasets.loc[datasets["label"] == selected_label].iloc[0]
    team_slug = str(dataset_row["team_slug"])
    planning_year = int(dataset_row["planning_year"])

    with selector_mid:
        view_mode = st.selectbox(
            "View mode",
            options=_team_calendar_ev_view_mode_labels(),
            index=0,
        )

    race_df = load_team_calendar_ev(team_slug, planning_year)
    summary_df = load_team_calendar_ev_summary(team_slug, planning_year)
    metadata = load_team_calendar_ev_metadata(team_slug, planning_year)
    calendar_snapshot_df = load_team_calendar_snapshot(team_slug, planning_year)

    if race_df.empty or summary_df.empty:
        st.warning("The selected Team Calendar EV artifact is missing required race-level or summary data.")
        return

    summary_row = summary_df.iloc[0]
    freshness_context = _team_calendar_ev_freshness_context(metadata, summary_row, calendar_snapshot_df)
    as_of_date = str(freshness_context["ev_as_of"] or "")
    with selector_right:
        st.markdown("**Freshness**")
        st.caption(f"EV artifact as of: `{as_of_date or 'Not available'}`")
        st.caption(
            "Calendar scraped: "
            f"`{str(freshness_context['calendar_scraped_at'] or 'Not available')}`"
        )

    filtered_df = _filtered_team_calendar_ev(race_df, view_mode)
    if filtered_df.empty:
        st.info("No races matched the current Team Calendar EV view.")
        return

    if freshness_context["has_drift"]:
        st.warning(str(freshness_context["warning_message"]))

    st.caption(
        f"The summary cards reflect the saved `{planning_year}` team-season snapshot. The story charts and tables "
        f"below follow the current `{view_mode}` filter unless a section says otherwise."
    )

    primary_metrics = _team_calendar_ev_primary_metrics(summary_row)
    metric_top_left, metric_top_right = st.columns(2)
    metric_bottom_left, metric_bottom_right = st.columns(2)
    metric_columns = [metric_top_left, metric_top_right, metric_bottom_left, metric_bottom_right]
    for metric_column, (label, value) in zip(metric_columns, primary_metrics):
        metric_column.metric(label, value)
    st.caption("Secondary facts: " + " | ".join(_team_calendar_ev_secondary_facts(summary_row)))
    st.caption("Weight details for this EV model live in the `How the model works: idea, methods, and math` expander above.")
    render_team_profile_identity_block(metadata)

    completed_missing_ev = filtered_df.loc[
        (filtered_df["status"] == "completed")
        & (
            filtered_df["expected_points"].isna()
            | filtered_df["base_opportunity_points"].isna()
            | filtered_df["team_fit_multiplier"].isna()
            | filtered_df["participation_confidence"].isna()
            | filtered_df["execution_multiplier"].isna()
        )
    ]
    if not completed_missing_ev.empty:
        st.warning(
            f"{len(completed_missing_ev)} completed races are missing one or more EV components. Check the detail table notes."
        )

    cumulative_df = filtered_df.copy().sort_values(["start_date", "race_name"]).reset_index(drop=True)
    cumulative_df["expected_points"] = pd.to_numeric(cumulative_df["expected_points"], errors="coerce").fillna(0.0)
    cumulative_df["actual_points"] = pd.to_numeric(cumulative_df["actual_points"], errors="coerce")
    cumulative_df["expected_cumulative"] = cumulative_df["expected_points"].cumsum()
    cumulative_df["actual_cumulative"] = cumulative_df["actual_points"].fillna(0.0).cumsum()
    cumulative_plot_df = cumulative_df.melt(
        id_vars=["race_name", "start_date"],
        value_vars=["expected_cumulative", "actual_cumulative"],
        var_name="series",
        value_name="points",
    )
    cumulative_plot_df["series"] = cumulative_plot_df["series"].map(
        {
            "expected_cumulative": "Expected cumulative",
            "actual_cumulative": "Actual cumulative",
        }
    )
    cumulative_chart = px.line(
        cumulative_plot_df,
        x="start_date",
        y="points",
        color="series",
        markers=True,
        hover_data={"race_name": True},
        labels={"start_date": "Race date", "points": "Points", "series": "Series"},
        title="Cumulative actual vs expected points",
    )
    cumulative_chart.update_layout(height=360)
    st.plotly_chart(cumulative_chart, use_container_width=True)

    known_gap_df = filtered_df.loc[filtered_df["ev_gap"].notna()].copy()
    if known_gap_df.empty:
        st.info("No races in this view have known actual points yet, so there is no race-gap chart to show.")
    else:
        known_gap_df["ev_gap"] = pd.to_numeric(known_gap_df["ev_gap"], errors="coerce").fillna(0.0)
        gap_chart_df = pd.concat(
            [
                known_gap_df.nlargest(5, "ev_gap"),
                known_gap_df.nsmallest(5, "ev_gap"),
            ],
            ignore_index=True,
        ).drop_duplicates(subset=["race_id"]).sort_values("ev_gap")
        gap_chart = px.bar(
            gap_chart_df,
            x="ev_gap",
            y="race_name",
            orientation="h",
            color="ev_gap",
            color_continuous_scale=["#b23a48", "#f0f0f0", "#3d8b5a"],
            labels={"ev_gap": "Actual minus expected", "race_name": "Race"},
            title="Largest over- and under-expectation races",
        )
        gap_chart_height = max(440, 28 * len(gap_chart_df) + 160)
        gap_chart.update_layout(height=gap_chart_height, coloraxis_showscale=False)
        st.plotly_chart(gap_chart, use_container_width=True)

    st.markdown("**Race detail**")
    st.caption(
        "This default table translates the raw EV multipliers into plain-language reads. Use `Team fit read`, `Start confidence`, and `Execution read` to see why the model is optimistic or cautious on each race before you open the analyst grid."
    )
    st.caption(
        "`Strong fit` means the saved team profile matches the race well. `Highly likely` means the start signal is stronger than the planning calendar alone. `Favorable conversion` means the race category is easier to turn into realized points than the biggest, most conservative events."
    )
    detail_df = _team_calendar_ev_guided_detail_frame(filtered_df)
    st.dataframe(
        detail_df.round({"Expected pts": 1, "Actual pts": 1, "EV gap": 1}),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Team fit read": st.column_config.TextColumn(
                "Team fit read",
                help="Plain-language read of how well the saved team profile matches this race.",
            ),
            "Start confidence": st.column_config.TextColumn(
                "Start confidence",
                help="Interpretation of the participation-confidence signal for whether the team is likely to line up in a points-relevant way.",
            ),
            "Execution read": st.column_config.TextColumn(
                "Execution read",
                help="Interpretation of the execution multiplier, which is the model's conservative haircut for how hard the race is to convert into actual points.",
            ),
            "Expected pts": st.column_config.NumberColumn(
                "Expected pts",
                help="Saved expected points after the historical opportunity anchor is adjusted for fit, participation, and execution.",
                format="%.1f",
            ),
            "Actual pts": st.column_config.NumberColumn(
                "Actual pts",
                help="Known PCS points from the race when results are available.",
                format="%.1f",
            ),
            "EV gap": st.column_config.NumberColumn(
                "EV gap",
                help="Actual points minus expected points for races with known results.",
                format="%.1f",
            ),
        },
    )

    with st.expander("Analyst detail columns", expanded=False):
        st.caption("Open the full diagnostic grid for the raw EV inputs, overlap diagnostics, and source provenance behind the guided table.")
        analyst_detail_columns = _team_calendar_ev_analyst_detail_columns(filtered_df)
        analyst_detail_df = filtered_df[analyst_detail_columns].copy().sort_values(["start_date", "race_name"])
        st.dataframe(
            analyst_detail_df.round(TEAM_EV_DETAIL_VALUE_ROUNDING),
            use_container_width=True,
            hide_index=True,
            column_config={
                "base_opportunity_points": st.column_config.NumberColumn(
                    "Base opp. pts",
                    help="Historical opportunity anchor before any team-specific fit, participation, or execution adjustments.",
                    format="%.1f",
                ),
                "team_fit_multiplier": st.column_config.NumberColumn(
                    "Team fit x",
                    help="Raw multiplier describing how well the saved team profile matches the race.",
                    format="%.3f",
                ),
                "participation_confidence": st.column_config.NumberColumn(
                    "Participation conf.",
                    help="Raw confidence that the team starts the race in a points-relevant way.",
                    format="%.3f",
                ),
                "execution_multiplier": st.column_config.NumberColumn(
                    "Execution x",
                    help="Raw category-based realization haircut for how hard the race is to convert into actual points.",
                    format="%.3f",
                ),
                "expected_points": st.column_config.NumberColumn("Expected pts", format="%.1f"),
                "actual_points": st.column_config.NumberColumn("Actual pts", format="%.1f"),
                "ev_gap": st.column_config.NumberColumn("EV gap", format="%.1f"),
                "overlap_group": st.column_config.TextColumn(
                    "Overlap group",
                    help="Shared scheduling bucket used when overlapping races compete for team attention.",
                ),
            },
        )

    with st.expander("More breakdowns", expanded=False):
        monthly_df = filtered_df.copy()
        monthly_df["expected_points"] = pd.to_numeric(monthly_df["expected_points"], errors="coerce").fillna(0.0)
        monthly_df["actual_points"] = pd.to_numeric(monthly_df["actual_points"], errors="coerce").fillna(0.0)
        monthly_df["month_label"] = pd.to_datetime(monthly_df["start_date"], errors="coerce").dt.strftime("%b")
        monthly_summary = (
            monthly_df.groupby("month_label", dropna=False, as_index=False)
            .agg(expected_points=("expected_points", "sum"), actual_points=("actual_points", "sum"))
        )
        monthly_summary["month_order"] = pd.to_datetime(monthly_summary["month_label"], format="%b", errors="coerce").dt.month
        monthly_summary = monthly_summary.sort_values(["month_order", "month_label"]).drop(columns=["month_order"])
        monthly_plot_df = monthly_summary.melt(
            id_vars=["month_label"],
            value_vars=["expected_points", "actual_points"],
            var_name="series",
            value_name="points",
        )
        monthly_plot_df["series"] = monthly_plot_df["series"].map(
            {"expected_points": "Expected", "actual_points": "Actual"}
        )
        monthly_chart = px.bar(
            monthly_plot_df,
            x="month_label",
            y="points",
            color="series",
            barmode="group",
            labels={"month_label": "Month", "points": "Points", "series": "Series"},
            title="Monthly actual vs expected",
        )
        monthly_chart.update_layout(height=360)
        st.plotly_chart(monthly_chart, use_container_width=True)

        category_chart_view = st.radio(
            "Category view",
            options=["Results so far", "Season plan"],
            index=0,
            horizontal=True,
            key="team_ev_category_chart_view",
        )
        if category_chart_view == "Season plan":
            category_summary = _ordered_category_summary(race_df)
            if category_summary.empty:
                st.info("No category totals are available for the saved team-season artifact yet.")
            else:
                category_chart = px.bar(
                    category_summary,
                    x="category",
                    y="expected_points",
                    labels={"category": "Category", "expected_points": "Points"},
                    title="Projected points by category (full schedule)",
                    category_orders={"category": category_summary["category"].tolist()},
                )
                category_chart.update_traces(marker_color="#176dbd")
                category_chart.update_xaxes(type="category")
                category_chart.update_layout(height=360)
                st.plotly_chart(category_chart, use_container_width=True)
                st.caption("This view shows projected points from the full saved team-season schedule.")
        else:
            completed_category_df = race_df.loc[race_df["status"] == "completed"].copy()
            completed_unknown_actuals = int(completed_category_df["actual_points"].isna().sum())
            category_summary = _ordered_category_summary(completed_category_df)
            if category_summary.empty:
                st.info("No completed races are available yet, so there is no results-so-far category view to show.")
            else:
                category_plot_df = category_summary.melt(
                    id_vars=["category"],
                    value_vars=["expected_points", "actual_points"],
                    var_name="series",
                    value_name="points",
                )
                category_plot_df["series"] = category_plot_df["series"].map(
                    {"expected_points": "Projected", "actual_points": "Actual"}
                )
                category_chart = px.bar(
                    category_plot_df,
                    x="category",
                    y="points",
                    color="series",
                    barmode="group",
                    labels={"category": "Category", "points": "Points", "series": "Series"},
                    title="Projected vs actual points by category (completed races)",
                    category_orders={"category": category_summary["category"].tolist()},
                    color_discrete_map={"Projected": "#176dbd", "Actual": "#79b4e6"},
                )
                category_chart.update_xaxes(type="category")
                category_chart.update_layout(height=360)
                st.plotly_chart(category_chart, use_container_width=True)
                st.caption(
                    "`Projected` is the model expectation for completed races only. `Actual` is the known PCS result total for those same completed races."
                )
                if completed_unknown_actuals:
                    st.caption(
                        f"`Actual` currently excludes {completed_unknown_actuals} completed race(s) whose PCS "
                        "actual points are still missing, so those rows contribute `0` until the artifact is refreshed."
                    )

    team_profile = dict(metadata.get("team_profile", {}))
    if team_profile:
        with st.expander("Analyst tools", expanded=False):
            render_roster_scenario_overlay(filtered_df, metadata, team_slug, planning_year, view_mode)
            render_team_profile_sandbox(filtered_df, metadata, team_slug, planning_year, view_mode)

    with st.expander("Data and downloads", expanded=False):
        st.caption(
            "Download the saved CSV artifacts driving this workspace. The separate `Data Sources` workspace remains the best place to inspect raw artifact contents side by side."
        )
        download_left, download_right = st.columns(2)
        with download_left:
            st.download_button(
                "Download race-level CSV",
                data=race_df.to_csv(index=False).encode("utf-8"),
                file_name=f"{team_slug}_{planning_year}_calendar_ev.csv",
                mime="text/csv",
            )
        with download_right:
            st.download_button(
                "Download summary CSV",
                data=summary_df.to_csv(index=False).encode("utf-8"),
                file_name=f"{team_slug}_{planning_year}_calendar_ev_summary.csv",
                mime="text/csv",
            )


def render_data_sources_tab(
    dataset: pd.DataFrame,
    dataset_source_label: str,
    planning_calendar: pd.DataFrame,
    planning_calendar_source: str,
    planning_year: int,
) -> None:
    st.subheader("Data Sources")
    st.caption(
        "Inspect the actual datasets currently driving the app. Historical race editions stay separate from the "
        "current-season planning calendar, ProTeam monitor snapshots, and saved Team Calendar EV artifacts."
    )

    sources: list[dict[str, object]] = []

    sources.append(
        {
            "label": "Historical race editions",
            "kind": "dataframe",
            "data": dataset,
            "description": "The current historical analysis dataset used for Recommended Targets, Diagnostics, and Backtesting.",
            "source_note": (
                "Loaded from the bundled snapshot and filtered to the current sidebar year/category settings."
                if dataset_source_label == "Bundled snapshot"
                else "Loaded from the current live FirstCycling scrape using the current sidebar year/category settings."
            ),
            "path": str(SNAPSHOT_PATH) if dataset_source_label == "Bundled snapshot" and SNAPSHOT_PATH.exists() else "",
            "download_name": "uci_points_race_editions.csv",
        }
    )

    planning_calendar_path = Path("data") / f"planning_calendar_{planning_year}.csv"
    planning_calendar_note = {
        "live": "Loaded from the live FirstCycling planning calendar fetch used to cross-check current-season targets.",
        "snapshot": f"Loaded from the bundled planning-calendar fallback for {planning_year}.",
        "unavailable": f"The {planning_year} planning calendar is unavailable in this session.",
    }.get(planning_calendar_source, "Planning calendar source status is unknown.")
    sources.append(
        {
            "label": f"{planning_year} planning calendar",
            "kind": "dataframe",
            "data": planning_calendar,
            "description": f"The planning calendar used to label which targets are on the {planning_year} .1/.Pro schedule.",
            "source_note": planning_calendar_note,
            "path": str(planning_calendar_path) if planning_calendar_source == "snapshot" and planning_calendar_path.exists() else "",
            "download_name": f"planning_calendar_{planning_year}.csv",
        }
    )

    for scope, scope_label in PROTEAM_SCOPE_LABELS.items():
        raw_snapshot = load_proteam_risk_snapshot(scope)
        if raw_snapshot.empty:
            continue
        sources.append(
            {
                "label": f"ProTeam risk raw snapshot ({scope_label})",
                "kind": "dataframe",
                "data": raw_snapshot,
                "description": f"The raw PCS rider-contribution snapshot used by the ProTeam Risk Monitor for the {scope_label.lower()} view.",
                "source_note": f"Bundled snapshot with latest scrape timestamp `{raw_snapshot['scraped_at'].max()}`.",
                "path": str(raw_snapshot.attrs.get("snapshot_path") or ""),
                "download_name": Path(str(raw_snapshot.attrs.get("snapshot_path") or f"proteam_risk_{scope}.csv")).name,
            }
        )

    active_team_dataset = get_active_team_calendar_ev_dataset_row()
    if active_team_dataset is not None:
        team_label = str(active_team_dataset["label"])
        team_slug = str(active_team_dataset["team_slug"])
        team_year = int(active_team_dataset["planning_year"])
        calendar_path = str(active_team_dataset.get("calendar_path") or "")
        actual_points_path = str(active_team_dataset.get("actual_points_path") or "")
        metadata_path = str(active_team_dataset.get("metadata_path") or "")

        if calendar_path:
            team_calendar_df = load_local_csv(calendar_path)
            sources.append(
                {
                    "label": f"Team calendar snapshot ({team_label})",
                    "kind": "dataframe",
                    "data": team_calendar_df,
                    "description": "The saved team schedule/program snapshot used as the base input to the Team Calendar EV build.",
                    "source_note": "This is the current matched team calendar artifact, including race status, PCS slugs, and overlap flags.",
                    "path": calendar_path,
                    "download_name": Path(calendar_path).name,
                }
            )

        if actual_points_path:
            actual_points_df = load_local_csv(actual_points_path)
            sources.append(
                {
                    "label": f"Team actual points ({team_label})",
                    "kind": "dataframe",
                    "data": actual_points_df,
                    "description": "The saved race-level actual-points table pulled from PCS team-in-race pages for the selected team-season.",
                    "source_note": "Completed zero-point races stay as `0`; unknown or unavailable actuals stay blank.",
                    "path": actual_points_path,
                    "download_name": Path(actual_points_path).name,
                }
            )

        team_ev_df = load_team_calendar_ev(team_slug, team_year)
        sources.append(
            {
                "label": f"Team Calendar EV race-level output ({team_label})",
                "kind": "dataframe",
                "data": team_ev_df,
                "description": "The saved race-level Team Calendar EV output used for the workspace charts and detailed table.",
                "source_note": "This artifact combines historical opportunity, team fit, participation confidence, execution multipliers, and actuals when known.",
                "path": str(active_team_dataset["race_path"]),
                "download_name": Path(str(active_team_dataset["race_path"])).name,
            }
        )

        team_summary_df = load_team_calendar_ev_summary(team_slug, team_year)
        sources.append(
            {
                "label": f"Team Calendar EV summary ({team_label})",
                "kind": "dataframe",
                "data": team_summary_df,
                "description": "The one-row summary artifact used for the Team Calendar EV KPI cards.",
                "source_note": "This row stores season-level totals for expected points, known actual points, EV gap, and race counts.",
                "path": str(active_team_dataset["summary_path"]),
                "download_name": Path(str(active_team_dataset["summary_path"])).name,
            }
        )

        if metadata_path:
            team_metadata = load_local_json(metadata_path)
            sources.append(
                {
                    "label": f"Team Calendar EV metadata ({team_label})",
                    "kind": "json",
                    "data": team_metadata,
                    "description": "The saved explainability metadata for the selected Team Calendar EV artifact, including weights and rationale.",
                    "source_note": "This JSON powers the Team Calendar EV explanation shown in the main model explainer.",
                    "path": metadata_path,
                    "download_name": Path(metadata_path).name,
                }
            )

    selected_label = st.selectbox(
        "Dataset",
        options=[str(source["label"]) for source in sources],
        index=0,
        key="data_sources_dataset_label",
    )
    selected_source = next(source for source in sources if source["label"] == selected_label)
    selected_kind = str(selected_source["kind"])
    selected_path = str(selected_source.get("path") or "")
    url_hidden = False

    meta_left, meta_mid, meta_right = st.columns(3)
    if selected_kind == "dataframe":
        raw_frame = pd.DataFrame(selected_source["data"])
        selected_frame = _sanitize_data_source_frame(raw_frame)
        url_hidden = len(selected_frame.columns) != len(raw_frame.columns)
        meta_left.metric("Rows", f"{len(selected_frame):,}")
        meta_mid.metric("Columns", len(selected_frame.columns))
    else:
        raw_json = dict(selected_source["data"])
        selected_json = _sanitize_data_source_json(raw_json)
        url_hidden = selected_json != raw_json
        meta_left.metric("Top-level keys", len(selected_json))
        meta_mid.metric("JSON type", "object")
    meta_right.markdown("**What this is**")
    meta_right.caption(str(selected_source["description"]))

    if selected_source.get("source_note"):
        st.caption(str(selected_source["source_note"]))
    if selected_path:
        st.caption(f"Path: `{selected_path}`")
    if url_hidden:
        st.caption("URL fields are hidden in this viewer and its download.")

    if selected_kind == "dataframe":
        st.download_button(
            "Download this dataset as CSV",
            data=selected_frame.to_csv(index=False).encode("utf-8"),
            file_name=str(selected_source["download_name"]),
            mime="text/csv",
        )
        st.dataframe(selected_frame, use_container_width=True, hide_index=True)
    else:
        json_text = json.dumps(selected_json, indent=2, sort_keys=True)
        st.download_button(
            "Download this dataset as JSON",
            data=json_text.encode("utf-8"),
            file_name=str(selected_source["download_name"]),
            mime="application/json",
        )
        st.json(selected_json, expanded=False)


def initialize_weight_state() -> None:
    stored_version = st.session_state.get("weight_default_version")
    should_reset = stored_version != WEIGHT_DEFAULT_VERSION
    for weight_name, default_value in DEFAULT_WEIGHTS.items():
        session_key = WEIGHT_STATE_KEYS[weight_name]
        if should_reset or session_key not in st.session_state:
            st.session_state[session_key] = float(default_value)
    st.session_state["weight_default_version"] = WEIGHT_DEFAULT_VERSION


def apply_pending_weight_state() -> None:
    pending_weights = st.session_state.pop(PENDING_WEIGHT_STATE_KEY, None)
    if pending_weights is None:
        return
    apply_weight_state(pending_weights)


def initialize_dataset_state() -> None:
    if "dataset" in st.session_state:
        st.session_state["dataset"] = ensure_dataset_schema(st.session_state["dataset"])
    st.session_state["dataset_schema_version"] = DATASET_SCHEMA_VERSION


def current_weight_state() -> dict[str, float]:
    return normalize_weights(
        {weight_name: float(st.session_state[session_key]) for weight_name, session_key in WEIGHT_STATE_KEYS.items()}
    )


def apply_weight_state(weights: dict[str, float]) -> None:
    normalized = normalize_weights(weights)
    for weight_name, value in normalized.items():
        st.session_state[WEIGHT_STATE_KEYS[weight_name]] = float(value)


def queue_weight_state(weights: dict[str, float]) -> None:
    st.session_state[PENDING_WEIGHT_STATE_KEY] = normalize_weights(weights)


def dataset_signature(dataset: pd.DataFrame) -> tuple[int, tuple[int, ...], tuple[str, ...]]:
    if dataset.empty:
        return (0, tuple(), tuple())
    years = tuple(sorted(dataset["year"].unique().tolist()))
    categories = tuple(sorted(dataset["category"].unique().tolist()))
    return (len(dataset), years, categories)


def calibration_signature(
    calibration_dataset_source: str,
    calibration_dataset: pd.DataFrame,
    years: list[int],
    categories: list[str],
    calibration_race_type: str,
    search_iterations: int,
    random_seed: int,
) -> tuple[object, ...]:
    return (
        CALIBRATION_RESULT_VERSION,
        calibration_dataset_source,
        dataset_signature(calibration_dataset),
        tuple(sorted(years)),
        tuple(sorted(categories)),
        calibration_race_type,
        search_iterations,
        random_seed,
    )


def prepare_backtest_fold_detail(fold_detail: pd.DataFrame, selected_fold: int) -> pd.DataFrame:
    year_detail = fold_detail[fold_detail["test_year"] == selected_fold].copy()
    year_detail = year_detail.rename(
        columns={
            "race_name": "Race",
            "category": "Category",
            "category_history": "Category History",
            "race_country": "Country",
            "train_editions": "Train Editions",
            "train_years": "Train Years",
            "predicted_score": "Predicted Score",
            "actual_points_efficiency": "Actual Efficiency",
            "actual_top10_points": "Actual Top-10 Points",
            "actual_top10_field_form": "Actual Top-10 Field Form",
            "predicted_rank": "Predicted Rank",
            "actual_rank": "Actual Rank",
        }
    )

    if "Category History" not in year_detail.columns:
        if "Category" in year_detail.columns:
            year_detail["Category History"] = year_detail["Category"]
        else:
            year_detail["Category History"] = "Unknown"

    required_columns = [
        "Race",
        "Category",
        "Category History",
        "Country",
        "Train Editions",
        "Train Years",
        "Predicted Score",
        "Actual Efficiency",
        "Actual Top-10 Points",
        "Actual Top-10 Field Form",
        "Predicted Rank",
        "Actual Rank",
    ]
    for column_name in required_columns:
        if column_name not in year_detail.columns:
            year_detail[column_name] = "Unknown"

    return year_detail[required_columns]


def render_start_here() -> None:
    st.markdown("**Start Here**")
    left, middle, right = st.columns(3)
    with left:
        st.markdown(
            """
            **What this app does**

            Ranks `.1` and `.Pro` races as historical UCI points opportunities and adds a separate ProTeam concentration monitor.
            """
        )
    with middle:
        st.markdown(
            """
            **What it does not do**

            It does not forecast exact rider results or tell a team exactly how many points it will score.
            """
        )
    with right:
        st.markdown(
            """
            **Best way to use it**

            Start with `Recommended Targets`, then use the other tabs for diagnostics, backtesting, and ProTeam risk.
            """
        )
    st.caption(
        "The deeper idea, methods, and math are available in the collapsed explainer below whenever you want the full logic."
    )


def render_workspace_guide(planning_year: int) -> None:
    st.markdown("**Choose A Workspace Below**")
    st.caption("Use the workspace selector below to move through the app. Start with `Recommended Targets` if you're new.")
    st.markdown(
        f"""
        - `Recommended Targets`: the best races to target next season, cross-checked against the `{planning_year}` calendar.
        - `Edition Diagnostics`: inspect one historical race edition and see its payout, field softness, and route-fit context.
        - `Backtest & Calibration`: see how the model performs on future years and compare default versus calibrated weights.
        - `ProTeam Risk Monitor`: track how concentrated each ProTeam's counted UCI points are across its rider core.
        - `Team Calendar EV`: load saved team-season EV artifacts with KPIs, charts, and explainable race detail.
        - `Data Sources`: inspect the historical dataset plus the planning, ProTeam, and Team Calendar EV artifacts currently driving the app.
        """
    )


def _render_model_explainer_legacy(
    weights: dict[str, float],
    specialty_weights: dict[str, float],
    fit_emphasis: float,
    dataset: pd.DataFrame,
    team_calendar_ev_metadata: dict[str, object] | None = None,
) -> None:
    error_count = int(dataset.attrs.get("error_count", 0))
    source_count = len(dataset)
    stage_race_count = int((dataset.get("race_type", pd.Series(dtype=str)) == "Stage race").sum())
    missing_stage_pages = int(dataset.get("stage_pages_missing", pd.Series(0)).sum())
    category_change_races = (
        int(dataset.groupby("race_id")["category"].nunique().gt(1).sum()) if not dataset.empty else 0
    )

    with st.expander("How the model works: idea, methods, and math", expanded=False):
        st.markdown("**What this app is actually for**")
        st.markdown(
            """
            - This app is **not** trying to predict exactly how many points a specific rider or team will score.
            - It is **not** a rider-vs-rider forecast model.
            - It **is** trying to rank races as **historical points opportunities**.
            - In plain language: it asks, "Which races have usually been the best value for scoring points?"
            """
        )

        st.markdown(
            """
            This app is trying to answer a practical racing question:
            for a team chasing UCI points, which `.1` and `.Pro` races have historically offered
            the best tradeoff between **points available** and **how hard the field looked**?
            """
        )

        overview_col, method_col = st.columns(2)

        with overview_col:
            st.markdown("**Overall idea**")
            st.markdown(
                """
                - High-value races are not just races with big payouts.
                - They are races where the payout has been strong **relative to the level of the field**.
                - The model therefore rewards high points and penalizes historically strong startlists.
                - Output should be treated as a targeting shortlist for planners, not an autopilot schedule.
                """
            )

            st.markdown("**What gets scraped**")
            st.markdown(
                """
                - Race calendar pages to find eligible `.1` and `.Pro` events.
                - Race result pages to capture actual UCI points paid out.
                - Individual stage-result pages for stage races, so stage points are not collapsed into GC only.
                - Extended startlist pages to estimate pre-race field strength.
                """
            )

            st.markdown("**How stage races are handled**")
            st.markdown(
                """
                - The app still ranks **whole races**, because a team chooses whether to enter the full stage race.
                - For stage races, the payout side now includes **GC points plus the sum of all parsed stage-result points**.
                - That means a seven-stage race is treated as one target with several internal scoring chances, not seven separate targets.
                """
            )

            st.markdown("**How category changes are handled**")
            st.markdown(
                """
                - If a race changes class, the model no longer blends those editions into one uninterrupted history.
                - A `1.1` version and a later `1.Pro` version are treated as different historical targets.
                - For planning, the app keeps the **latest known category** as the live recommendation and shows the full category path for context.
                """
            )

        with method_col:
            st.markdown("**Trust checklist**")
            st.markdown(
                f"""
                - The current run is based on **{source_count}** historical race editions.
                - Any score is built from observable fields shown in the `Data Sources` tab.
                - The opportunity score is explainable because every component is exposed below.
                - Stage races in this run: **{stage_race_count}**. Missing stage pages inside parsed stage races: **{missing_stage_pages}**.
                - Races with at least one category change inside this run: **{category_change_races}**.
                - Skipped races in this run: **{error_count}**.
                """
            )

            st.markdown("**Main limitations**")
            st.markdown(
                """
                - Startlist strength is a proxy, not a perfect measure of rider level.
                - The new route-and-specialty layer is a beta overlay inferred from event structure and time-trial keywords, not a full GPS or gradient model.
                - Latest-category planning is based on the latest category visible in the selected data window, so a later drop to `.2` is only visible if that category is included in the dataset.
                - The model still does not include travel cost, full route fit, internal team goals, or roster conflicts.
                """
            )

        st.markdown("**Step 1: Build a rider form proxy from the extended startlist**")
        st.latex(
            r"""
            \text{rider\_form}
            =
            5 \cdot \text{wins}
            + 2 \cdot (\text{podiums} - \text{wins})
            + 1 \cdot (\text{top10s} - \text{podiums})
            + 0.1 \cdot \text{starts}
            """
        )
        st.markdown(
            """
            This intentionally weights wins most heavily, then podium depth, then top-10 frequency,
            with a small reward for recent race volume.
            """
        )

        st.markdown("**Step 2: Turn rider form into field-strength measures**")
        st.latex(
            r"""
            \text{top10\_field\_form}
            =
            \sum_{i=1}^{10} \text{rider\_form}_{(i)}
            \qquad
            \text{avg\_top10\_field\_form}
            =
            \frac{\text{top10\_field\_form}}{10}
            \qquad
            \text{total\_field\_form}
            =
            \sum_{j=1}^{N} \text{rider\_form}_j
            """
        )
        st.markdown(
            """
            Lower values mean a historically softer field. In the final score, lower field strength is
            converted into a higher "softness" percentile.
            """
        )

        st.markdown("**Step 3: Convert raw measures into comparable 0-100 percentiles**")
        st.markdown("**Stage-race payout treatment**")
        st.latex(
            r"""
            \text{event\_top10\_points}
            =
            \text{gc\_top10\_points}
            +
            \sum_{s=1}^{S} \text{stage\_top10\_points}_s
            \qquad
            \text{event\_winner\_points}
            =
            \text{gc\_winner\_points}
            +
            \sum_{s=1}^{S} \text{stage\_winner\_points}_s
            """
        )
        st.markdown(
            """
            One-day races have no stage component, so their event-level payout is just the final result table.
            Stage races keep one row in the model, but that row now carries both the GC and stage payout totals.
            """
        )

        st.markdown("**Step 4: Convert raw measures into comparable 0-100 percentiles**")
        st.latex(
            r"""
            \text{top10\_points\_pct} = \text{percentile}(\text{top10\_points})
            \qquad
            \text{winner\_points\_pct} = \text{percentile}(\text{winner\_points})
            """
        )
        st.latex(
            r"""
            \text{field\_softness\_pct} = 100 - \text{percentile}(\text{avg\_top10\_field\_form})
            \qquad
            \text{depth\_softness\_pct} = 100 - \text{percentile}(\text{total\_field\_form})
            """
        )
        st.latex(
            r"""
            \text{finish\_rate\_pct} = \text{percentile}(\text{finish\_rate})
            """
        )

        st.markdown("**Step 5: Combine the components into the arbitrage score**")
        st.latex(
            rf"""
            \text{{arbitrage\_score}}
            =
            \frac{{
            {weights["top10_points"]:.2f}\cdot\text{{top10\_points\_pct}}
            +
            {weights["winner_points"]:.2f}\cdot\text{{winner\_points\_pct}}
            +
            {weights["field_softness"]:.2f}\cdot\text{{field\_softness\_pct}}
            +
            {weights["depth_softness"]:.2f}\cdot\text{{depth\_softness\_pct}}
            +
            {weights["finish_rate"]:.2f}\cdot\text{{finish\_rate\_pct}}
            }}{{
            {sum(weights.values()):.2f}
            }}
            """
        )

        weight_frame = pd.DataFrame(
            {
                "Component": [
                    "Top-10 payout",
                    "Winner upside",
                    "Softness of top riders",
                    "Softness of full field",
                    "Finish-rate reliability",
                ],
                "Current weight": [
                    weights["top10_points"],
                    weights["winner_points"],
                    weights["field_softness"],
                    weights["depth_softness"],
                    weights["finish_rate"],
                ],
            }
        )
        st.dataframe(weight_frame, use_container_width=True, hide_index=True)
        st.caption(
            "Sidebar weights are normalized before scoring, so they act as relative emphasis rather than fixed coefficients."
        )
        st.caption(
            "These startup defaults are the current one-day calibrated weights from the bundled 2021-2025 walk-forward backtest."
        )

        st.markdown("**Optional beta: route profile x specialty fit**")
        st.markdown(
            """
            The app now adds a lightweight overlay that infers a race profile from event structure:

            - `One-day classic`: non-TT one-day races
            - `Time trial`: TT keyword found in the race name or subtitle
            - `GC-heavy stage race`: most points come from GC rather than stages
            - `Balanced stage race`: GC and stage scoring are more evenly mixed
            - `Stage-hunter stage race`: a large share of points comes from stages
            """
        )
        st.latex(
            rf"""
            \text{{targeting\_score}}
            =
            (1 - {fit_emphasis:.2f}) \cdot \text{{arbitrage\_score}}
            +
            {fit_emphasis:.2f} \cdot \text{{specialty\_fit\_score}}
            """
        )

        specialty_frame = pd.DataFrame(
            {
                "Specialty axis": [
                    "One-day / classics",
                    "GC / climbing",
                    "Stage hunter / sprinter",
                    "Time trial",
                    "All-round stage depth",
                ],
                "Current weight": [
                    specialty_weights["one_day"],
                    specialty_weights["gc"],
                    specialty_weights["stage_hunter"],
                    specialty_weights["time_trial"],
                    specialty_weights["all_round"],
                ],
            }
        )
        st.dataframe(specialty_frame.round(3), use_container_width=True, hide_index=True)
        st.caption(
            "These specialty weights are normalized inside the fit score. If you leave them equal, the beta overlay stays neutral."
        )
        st.caption(
            "This beta fit layer is not part of the walk-forward calibration yet, because it is a team-specific planning overlay rather than a historical baseline."
        )

        if team_calendar_ev_metadata:
            render_team_calendar_ev_weight_explainer(team_calendar_ev_metadata)

        st.markdown("**Interpretation guide**")
        st.markdown(
            """
            - A higher `Arbitrage Score` means the race has looked attractive on a payout-versus-field basis.
            - A higher `Specialty Fit` means the race profile better matches the specialty mix you selected in the sidebar.
            - `Targeting Score` is the blended planning score: historical opportunity plus your chosen specialty-fit emphasis.
            - A high `Avg Top-10 Points` with a low `Avg Top-10 Field Form` is usually the sweet spot.
            - `Points per Field-Form` is a simpler efficiency view: payout divided by the strength proxy of the top of the field.
            """
        )


def render_model_explainer(
    weights: dict[str, float],
    specialty_weights: dict[str, float],
    fit_emphasis: float,
    dataset: pd.DataFrame,
    team_calendar_ev_metadata: dict[str, object] | None = None,
) -> None:
    error_count = int(dataset.attrs.get("error_count", 0))
    source_count = len(dataset)
    stage_race_count = int((dataset.get("race_type", pd.Series(dtype=str)) == "Stage race").sum())
    missing_stage_pages = int(dataset.get("stage_pages_missing", pd.Series(0)).sum())
    category_change_races = (
        int(dataset.groupby("race_id")["category"].nunique().gt(1).sum()) if not dataset.empty else 0
    )

    with st.expander("How the model works: idea, methods, and math", expanded=False):
        st.markdown("**What This App Is Doing**")
        st.markdown(
            """
            - This app is **not** trying to predict exactly how many points a specific rider or team will score.
            - It is **not** a rider-vs-rider forecast model.
            - It **is** trying to rank races as **historical points opportunities**.
            - In plain language: it asks, "Which races have usually been the best value for scoring points?"
            """
        )
        st.markdown(
            """
            The practical question is:
            for a team chasing UCI points, which `.1` and `.Pro` races have historically offered
            the best tradeoff between **points available** and **how hard the field looked**?
            """
        )

        overview_col, trust_col = st.columns(2)
        with overview_col:
            st.markdown("**Overall idea**")
            st.markdown(
                """
                - High-value races are not just races with big payouts.
                - They are races where the payout has been strong **relative to the level of the field**.
                - The model therefore rewards high points and penalizes historically strong startlists.
                - Output should be treated as a targeting shortlist for planners, not an autopilot schedule.
                """
            )
            st.markdown("**What gets scraped**")
            st.markdown(
                """
                - Race calendar pages to find eligible `.1` and `.Pro` events.
                - Race result pages to capture actual UCI points paid out.
                - Individual stage-result pages for stage races, so stage points are not collapsed into GC only.
                - Extended startlist pages to estimate pre-race field strength.
                """
            )
        with trust_col:
            st.markdown("**Trust checklist**")
            st.markdown(
                f"""
                - The current run is based on **{source_count}** historical race editions.
                - Any score is built from observable fields shown in the `Data Sources` tab.
                - The opportunity score is explainable because every component is exposed below.
                - Stage races in this run: **{stage_race_count}**. Missing stage pages inside parsed stage races: **{missing_stage_pages}**.
                - Races with at least one category change inside this run: **{category_change_races}**.
                - Skipped races in this run: **{error_count}**.
                """
            )
            st.markdown("**Main limitations**")
            st.markdown(
                """
                - Startlist strength is a proxy, not a perfect measure of rider level.
                - The route-and-specialty layer is a beta overlay inferred from event structure and time-trial keywords, not a full GPS or gradient model.
                - Latest-category planning is based on the latest category visible in the selected data window, so a later drop to `.2` is only visible if that category is included in the dataset.
                - The model still does not include travel cost, full route fit, internal team goals, or roster conflicts.
                """
            )

        st.divider()
        st.markdown("**Historical Opportunity Model**")
        st.markdown(
            """
            The historical model works in five moves:

            1. build a rider-form proxy from past results,
            2. turn that into field-strength measures,
            3. measure how much a race paid out,
            4. convert those raw measures into comparable percentiles,
            5. combine them into one opportunity score.
            """
        )

        history_left, history_right = st.columns(2)
        with history_left:
            st.markdown("**Stage races**")
            st.markdown(
                """
                - The app still ranks **whole races**, because a team chooses whether to enter the full stage race.
                - For stage races, the payout side includes **GC points plus the sum of parsed stage-result points**.
                - That means a seven-stage race is one target with several internal scoring chances, not seven separate targets.
                """
            )
        with history_right:
            st.markdown("**Category changes**")
            st.markdown(
                """
                - If a race changes class, the model no longer blends those editions into one uninterrupted history.
                - A `1.1` version and a later `1.Pro` version are treated as different historical targets.
                - For planning, the app keeps the **latest known category** as the live recommendation and shows the category path for context.
                """
            )

        with st.expander("Advanced formulas for the historical opportunity model", expanded=False):
            st.markdown("**Step 1: Build a rider form proxy from the extended startlist**")
            st.latex(
                r"""
                \text{rider\_form}
                =
                5 \cdot \text{wins}
                + 2 \cdot (\text{podiums} - \text{wins})
                + 1 \cdot (\text{top10s} - \text{podiums})
                + 0.1 \cdot \text{starts}
                """
            )
            st.markdown(
                """
                This intentionally weights wins most heavily, then podium depth, then top-10 frequency,
                with a small reward for recent race volume.
                """
            )

            st.markdown("**Step 2: Turn rider form into field-strength measures**")
            st.latex(
                r"""
                \text{top10\_field\_form}
                =
                \sum_{i=1}^{10} \text{rider\_form}_{(i)}
                \qquad
                \text{avg\_top10\_field\_form}
                =
                \frac{\text{top10\_field\_form}}{10}
                \qquad
                \text{total\_field\_form}
                =
                \sum_{j=1}^{N} \text{rider\_form}_j
                """
            )
            st.markdown(
                """
                Lower values mean a historically softer field. In the final score, lower field strength is
                converted into a higher softness percentile.
                """
            )

            st.markdown("**Step 3: Stage-race payout treatment**")
            st.latex(
                r"""
                \text{event\_top10\_points}
                =
                \text{gc\_top10\_points}
                +
                \sum_{s=1}^{S} \text{stage\_top10\_points}_s
                \qquad
                \text{event\_winner\_points}
                =
                \text{gc\_winner\_points}
                +
                \sum_{s=1}^{S} \text{stage\_winner\_points}_s
                """
            )
            st.markdown(
                """
                One-day races have no stage component, so their event-level payout is just the final result table.
                Stage races keep one row in the model, but that row carries both the GC and stage payout totals.
                """
            )

            st.markdown("**Step 4: Convert raw measures into comparable percentiles**")
            st.latex(
                r"""
                \text{top10\_points\_pct} = \text{percentile}(\text{top10\_points})
                \qquad
                \text{winner\_points\_pct} = \text{percentile}(\text{winner\_points})
                """
            )
            st.latex(
                r"""
                \text{field\_softness\_pct} = 100 - \text{percentile}(\text{avg\_top10\_field\_form})
                \qquad
                \text{depth\_softness\_pct} = 100 - \text{percentile}(\text{total\_field\_form})
                """
            )
            st.latex(
                r"""
                \text{finish\_rate\_pct} = \text{percentile}(\text{finish\_rate})
                """
            )

            st.markdown("**Step 5: Combine the components into the arbitrage score**")
            st.latex(
                rf"""
                \text{{arbitrage\_score}}
                =
                \frac{{
                {weights["top10_points"]:.2f}\cdot\text{{top10\_points\_pct}}
                +
                {weights["winner_points"]:.2f}\cdot\text{{winner\_points\_pct}}
                +
                {weights["field_softness"]:.2f}\cdot\text{{field\_softness\_pct}}
                +
                {weights["depth_softness"]:.2f}\cdot\text{{depth\_softness\_pct}}
                +
                {weights["finish_rate"]:.2f}\cdot\text{{finish\_rate\_pct}}
                }}{{
                {sum(weights.values()):.2f}
                }}
                """
            )

            weight_frame = pd.DataFrame(
                {
                    "Component": [
                        "Top-10 payout",
                        "Winner upside",
                        "Softness of top riders",
                        "Softness of full field",
                        "Finish-rate reliability",
                    ],
                    "Current weight": [
                        weights["top10_points"],
                        weights["winner_points"],
                        weights["field_softness"],
                        weights["depth_softness"],
                        weights["finish_rate"],
                    ],
                }
            )
            st.dataframe(weight_frame, use_container_width=True, hide_index=True)
            st.caption(
                "Sidebar weights are normalized before scoring, so they act as relative emphasis rather than fixed coefficients."
            )
            st.caption(
                "These startup defaults are the current one-day calibrated weights from the bundled 2021-2025 walk-forward backtest."
            )

        st.divider()
        st.markdown("**Route & Specialty Fit**")
        st.markdown(
            """
            The app adds a lightweight overlay that infers a race profile from event structure:

            - `One-day classic`: non-TT one-day races
            - `Time trial`: TT keyword found in the race name or subtitle
            - `GC-heavy stage race`: most points come from GC rather than stages
            - `Balanced stage race`: GC and stage scoring are more evenly mixed
            - `Stage-hunter stage race`: a large share of points comes from stages
            """
        )
        st.latex(
            rf"""
            \text{{targeting\_score}}
            =
            (1 - {fit_emphasis:.2f}) \cdot \text{{arbitrage\_score}}
            +
            {fit_emphasis:.2f} \cdot \text{{specialty\_fit\_score}}
            """
        )

        specialty_frame = pd.DataFrame(
            {
                "Specialty axis": [
                    "One-day / classics",
                    "GC / climbing",
                    "Stage hunter / sprinter",
                    "Time trial",
                    "All-round stage depth",
                ],
                "Current weight": [
                    specialty_weights["one_day"],
                    specialty_weights["gc"],
                    specialty_weights["stage_hunter"],
                    specialty_weights["time_trial"],
                    specialty_weights["all_round"],
                ],
            }
        )
        st.dataframe(specialty_frame.round(3), use_container_width=True, hide_index=True)
        st.caption(
            "These specialty weights are normalized inside the fit score. If you leave them equal, the beta overlay stays neutral."
        )
        st.caption(
            "This beta fit layer is not part of the walk-forward calibration yet, because it is a team-specific planning overlay rather than a historical baseline."
        )

        if team_calendar_ev_metadata:
            st.divider()
            st.markdown("**Team Calendar EV Model**")
            st.markdown(
                """
                The Team Calendar EV workspace takes the historical opportunity idea and turns it into a saved team-season expectation.

                - `base_opportunity_points` is the historical opportunity anchor for the race.
                - `team_fit_multiplier` adjusts that anchor to the selected team's specialty profile.
                - `participation_confidence` discounts future races when start certainty is weaker.
                - `execution_multiplier` is a conservative haircut by race category.
                """
            )
            with st.expander("Advanced Team Calendar EV weights and assumptions", expanded=False):
                render_team_calendar_ev_weight_explainer(team_calendar_ev_metadata)

        st.divider()
        st.markdown("**Interpretation Guide**")
        st.markdown(
            """
            - A higher `Arbitrage Score` means the race has looked attractive on a payout-versus-field basis.
            - A higher `Specialty Fit` means the race profile better matches the specialty mix you selected in the sidebar.
            - `Targeting Score` is the blended planning score: historical opportunity plus your chosen specialty-fit emphasis.
            - A high `Avg Top-10 Points` with a low `Avg Top-10 Field Form` is usually the sweet spot.
            - `Points per Field-Form` is a simpler efficiency view: payout divided by the strength proxy of the top of the field.
            """
        )


def render_backtest_tab(dataset: pd.DataFrame, years: list[int], categories: list[str]) -> None:
    st.subheader("Backtest & Calibration")
    st.markdown(
        """
        The calibration module checks whether **past race history** helps identify **future high-efficiency races**.
        It does that with a walk-forward test:
        train on prior years, predict which races should look attractive next season, then compare those predictions
        with what actually happened in the next year's edition.
        """
    )
    st.markdown(
        """
        It still works at the **race level**, not the rider level.
        The question is:
        "Did the model rank the best points opportunities near the top?"
        """
    )
    st.caption(
        "Calibration is now category-aware: a race's `1.1` history and `1.Pro` history are treated as separate target histories."
    )
    st.caption(
        "The walk-forward backtest calibrates only the core arbitrage model. The new route-and-specialty fit layer is a user/team overlay and is not backtested here."
    )
    st.markdown(
        "This is a **walk-forward / time-series** backtest, not ordinary random k-fold cross-validation. "
        "If you want the general math behind the idea, the "
        "[scikit-learn TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) "
        "is a good reference."
    )

    with st.form("calibration_form"):
        calibration_dataset_source = st.radio(
            "Calibration data",
            options=["Bundled snapshot", "Current analysis dataset"],
            index=0 if SNAPSHOT_PATH.exists() else 1,
            horizontal=True,
            help=(
                "Use the bundled snapshot for the most stable calibration. "
                "A capped live scrape can be too sparse for walk-forward testing."
            ),
        )
        calibration_race_type = st.radio(
            "Calibration scope",
            options=["One-day", "All", "Stage race"],
            index=0,
            horizontal=True,
            help="One-day is still recommended because stage races now include stage points but do not yet model stage type or roster fit.",
        )
        search_iterations = st.slider(
            "Random weight candidates",
            min_value=100,
            max_value=1500,
            value=600,
            step=100,
            help="More candidates means a broader search, but it takes longer.",
        )
        random_seed = st.number_input("Random seed", min_value=1, max_value=9999, value=7, step=1)
        run_backtest = st.form_submit_button("Run walk-forward backtest")

    if calibration_dataset_source == "Bundled snapshot" and SNAPSHOT_PATH.exists():
        calibration_dataset = load_snapshot(SNAPSHOT_PATH, years=years, categories=categories)
    else:
        calibration_dataset = dataset

    current_signature = calibration_signature(
        calibration_dataset_source=calibration_dataset_source,
        calibration_dataset=calibration_dataset,
        years=years,
        categories=categories,
        calibration_race_type=calibration_race_type,
        search_iterations=search_iterations,
        random_seed=random_seed,
    )
    if run_backtest:
        result = get_calibration_result(
            calibration_dataset, calibration_race_type, search_iterations, random_seed
        )
        st.session_state["calibration_result"] = result
        st.session_state["calibration_signature"] = current_signature

    result = st.session_state.get("calibration_result")
    result_signature = st.session_state.get("calibration_signature")

    if result is None:
        st.info("Run the backtest to compare the default weights against calibrated weights.")
        return

    if result_signature != current_signature:
        st.warning(
            "The calibration setup has changed since the last run. Run the backtest again to refresh the results."
        )
        return

    if not result.get("eligible", False):
        st.warning(result["message"])
        filtered_rows = result.get("filtered_rows", 0)
        st.caption(f"Eligible historical rows after filtering: {filtered_rows}")
        if calibration_dataset_source == "Current analysis dataset":
            st.caption(
                "This usually means the current live scrape does not contain enough repeated race editions across years. "
                "Switching calibration data to `Bundled snapshot` should fix it."
            )
        return

    default_eval = result["default"]
    best_eval = result["best"]

    metric_left, metric_mid, metric_right, metric_far = st.columns(4)
    metric_left.metric("Calibration folds", result["fold_count"])
    metric_mid.metric("Default objective", f"{default_eval['objective']:.3f}")
    metric_right.metric("Calibrated objective", f"{best_eval['objective']:.3f}")
    metric_far.metric("Improvement", f"{result['improvement']:+.3f}")

    st.markdown("**How the backtest is scored**")
    st.markdown(
        """
        - `Spearman`: does the predicted race ranking match the realized race-efficiency ranking?
        - `Top-k precision`: how often did the model's shortlist overlap with the actual best races?
        - `Top-k value capture`: how much of the actual top-race efficiency did the shortlist capture?
        """
    )
    st.latex(
        r"""
        \text{objective}
        =
        0.60 \cdot \frac{\text{Spearman} + 1}{2}
        +
        0.20 \cdot \text{Top-k Precision}
        +
        0.20 \cdot \text{Top-k Value Capture}
        """
    )

    comparison_frame = pd.DataFrame(
        [
            {
                "Set": "Default",
                "Objective": default_eval["objective"],
                "Spearman": default_eval["spearman"],
                "Top-k Precision": default_eval["top_k_precision"],
                "Top-k Value Capture": default_eval["top_k_value_capture"],
                **default_eval["weights"],
            },
            {
                "Set": "Calibrated",
                "Objective": best_eval["objective"],
                "Spearman": best_eval["spearman"],
                "Top-k Precision": best_eval["top_k_precision"],
                "Top-k Value Capture": best_eval["top_k_value_capture"],
                **best_eval["weights"],
            },
        ]
    )
    st.dataframe(
        comparison_frame.round(3),
        use_container_width=True,
        hide_index=True,
    )

    if st.button("Use calibrated weights in this session", key="apply_calibrated_weights"):
        queue_weight_state(best_eval["weights"])
        st.rerun()

    calibration_years = sorted(calibration_dataset["year"].unique().tolist())
    fold_options = [int(year) for year in result["fold_years"]]
    if len(calibration_years) >= 3:
        earliest_possible_test_year = calibration_years[2]
        st.caption(
            f"Walk-forward backtesting requires two prior training years, so the earliest possible "
            f"`test_year` for the current calibration dataset is `{earliest_possible_test_year}`. "
            f"That is why the first loaded years, such as `{calibration_years[0]}` and `{calibration_years[1]}`, "
            "do not appear as test years."
        )
    selected_fold = st.selectbox("Inspect test year", options=fold_options, index=len(fold_options) - 1)

    default_fold_table = default_eval["folds"].copy()
    default_fold_table["Weight Set"] = "Default"
    calibrated_fold_table = best_eval["folds"].copy()
    calibrated_fold_table["Weight Set"] = "Calibrated"
    fold_comparison = pd.concat([default_fold_table, calibrated_fold_table], ignore_index=True)
    st.dataframe(
        fold_comparison.round(3),
        use_container_width=True,
        hide_index=True,
    )

    fold_detail = best_eval["fold_details"]
    if not fold_detail.empty:
        year_detail = prepare_backtest_fold_detail(fold_detail, selected_fold)
        st.markdown("**Calibrated ranking versus actual next-year outcome**")
        st.dataframe(
            year_detail.round(
                {
                    "Predicted Score": 3,
                    "Actual Efficiency": 3,
                    "Actual Top-10 Points": 1,
                    "Actual Top-10 Field Form": 1,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("**Top candidate weight sets**")
    leaderboard = result["leaderboard"].copy()
    leaderboard = leaderboard.rename(
        columns={
            "objective": "Objective",
            "spearman": "Spearman",
            "top_k_precision": "Top-k Precision",
            "top_k_value_capture": "Top-k Value Capture",
            "top10_points": "Top-10 Payout",
            "winner_points": "Winner Upside",
            "field_softness": "Top-Rider Softness",
            "depth_softness": "Field Softness",
            "finish_rate": "Finish Reliability",
        }
    )
    st.dataframe(leaderboard.round(3), use_container_width=True, hide_index=True)


def render_proteam_risk_tab() -> None:
    st.subheader("ProTeam Risk Monitor")
    st.markdown(
        """
        This monitor is about **points concentration**, not rider forecasting.
        It asks a simple question:
        **how dependent is a ProTeam on one rider, or a very small core, for its counted UCI points?**
        """
    )
    st.caption(
        "High concentration can create vulnerability to injury, transfer, illness, or loss of form. "
        "The current-season and 2026-2028 views answer different planning questions."
    )

    scope_label = st.radio(
        "Points view",
        options=[PROTEAM_SCOPE_LABELS[CURRENT_SCOPE], PROTEAM_SCOPE_LABELS[CYCLE_SCOPE]],
        index=0,
        horizontal=True,
    )
    scope = next(key for key, value in PROTEAM_SCOPE_LABELS.items() if value == scope_label)

    fallback_reason = ""
    raw_dataset = load_proteam_risk_snapshot(scope)
    if not raw_dataset.empty:
        data_source = "snapshot"
    else:
        try:
            with st.spinner("Loading ProTeam contributions from ProCyclingStats..."):
                raw_dataset = get_live_proteam_risk_dataset(scope)
            data_source = "live"
        except Exception as exc:  # noqa: BLE001
            fallback_reason = str(exc)
            data_source = "unavailable"

    if raw_dataset.empty:
        if data_source == "unavailable":
            st.error(
                "The ProTeam monitor could not load a bundled snapshot for this scope, and the live PCS fallback was unavailable."
            )
            if fallback_reason:
                st.caption(f"Latest live-fetch error: {fallback_reason}")
        else:
            st.info("No ProTeam monitor rows were available for the current settings.")
        return

    if data_source == "live":
        scraped_at = str(raw_dataset["scraped_at"].max())
        st.caption(f"Using live PCS data. Latest scrape timestamp: `{scraped_at}`.")
    elif data_source == "snapshot":
        scraped_at = str(raw_dataset["scraped_at"].max())
        st.caption(
            f"Showing the latest bundled ProTeam snapshot. Last refresh timestamp: `{scraped_at}`."
        )
        st.caption(
            "These ProTeam snapshots are intended to stay fresh via the scheduled GitHub Actions refresh job, "
            "so the deployed app does not depend on live PCS access during each user session."
        )

    st.caption(
        "Risk thresholds: `High` if Top-1 Share >= 35% or Leader Shock >= 30%; "
        "`Medium` if Top-1 Share >= 25% or Leader Shock >= 20%; otherwise `Lower`."
    )
    st.caption(
        "`Effective N` is the effective number of equally important contributors: "
        "`1 / sum(share^2)`. Higher values usually mean deeper, less concentrated scoring support."
    )

    summary = summarize_proteam_risk(raw_dataset)
    if summary.empty:
        st.info("No ProTeam summary rows were available after processing the PCS data.")
        return

    summary["Top-1 Share %"] = (summary["top1_share"] * 100).round(1)
    summary["Top-3 Share %"] = (summary["top3_share"] * 100).round(1)
    summary["Top-5 Share %"] = (summary["top5_share"] * 100).round(1)
    summary["Leader Shock %"] = (summary["leader_shock_drop_pct"] * 100).round(1)
    summary["Leader+Coleader Shock %"] = (summary["leader_coleader_shock_drop_pct"] * 100).round(1)

    metric_left, metric_mid, metric_right, metric_far, metric_farthest = st.columns(5)
    metric_left.metric("ProTeams monitored", len(summary))
    metric_mid.metric("High risk teams", int((summary["risk_band"] == "High").sum()))
    metric_right.metric("Median Top-1 Share", f"{summary['Top-1 Share %'].median():.1f}%")
    metric_far.metric("Max Top-1 Share", f"{summary['Top-1 Share %'].max():.1f}%")
    metric_farthest.metric("Median Effective N", f"{summary['effective_contributors'].median():.2f}")

    chart_frame = summary.sort_values("Top-1 Share %", ascending=False).copy()
    chart = px.bar(
        chart_frame,
        x="Top-1 Share %",
        y="team_name",
        color="risk_band",
        orientation="h",
        hover_data={
            "team_total_points": ":.1f",
            "leader_name": True,
            "Top-3 Share %": ":.1f",
            "Leader Shock %": ":.1f",
            "Leader+Coleader Shock %": ":.1f",
            "effective_contributors": ":.2f",
            "data_check": True,
        },
        labels={
            "team_name": "ProTeam",
            "risk_band": "Risk",
        },
        title=f"ProTeam key-man concentration ({scope_label})",
        color_discrete_map={"High": "#b23a48", "Medium": "#d99a2b", "Lower": "#3d8b5a"},
    )
    chart.update_layout(height=560, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(chart, use_container_width=True)

    if int((summary["data_check"] == "Warning").sum()):
        st.warning(
            "One or more teams had a noticeable gap between the ranking-table total and the summed rider breakdown. "
            "Those rows are flagged in `Data Check`."
        )

    summary_export_columns = [
        "team_rank",
        "team_name",
        "team_class",
        "team_total_points",
        "leader_name",
        "Top-1 Share %",
        "Top-3 Share %",
        "Top-5 Share %",
        "Leader Shock %",
        "Leader+Coleader Shock %",
        "effective_contributors",
        "counted_riders_found",
        "risk_band",
        "data_check",
        "source_url",
        "scraped_at",
    ]
    summary_export_frame = summary[summary_export_columns].rename(
        columns={"effective_contributors": "Effective N"}
    )
    st.download_button(
        "Download ProTeam summary as CSV",
        data=summary_export_frame.to_csv(index=False).encode("utf-8"),
        file_name=f"proteam_risk_summary_{scope}.csv",
        mime="text/csv",
    )

    summary_table = summary[
        [
            "team_rank",
            "team_name",
            "team_total_points",
            "leader_name",
            "Top-1 Share %",
            "Top-3 Share %",
            "Top-5 Share %",
            "Leader Shock %",
            "Leader+Coleader Shock %",
            "effective_contributors",
            "counted_riders_found",
            "risk_band",
            "data_check",
        ]
    ].rename(
        columns={
            "team_rank": "Rank",
            "team_name": "Team",
            "team_total_points": "Points",
            "leader_name": "Leader",
            "effective_contributors": "Effective N",
            "counted_riders_found": "Counted Riders",
            "risk_band": "Risk",
            "data_check": "Data Check",
        }
    )
    st.dataframe(
        summary_table.round({"Points": 1, "Effective N": 2}),
        use_container_width=True,
        hide_index=True,
    )

    selected_team_name = st.selectbox(
        "Inspect team",
        options=summary["team_name"].tolist(),
        index=0,
    )
    selected_team_slug = summary.loc[summary["team_name"] == selected_team_name, "team_slug"].iloc[0]
    selected_summary = summary.loc[summary["team_slug"] == selected_team_slug].iloc[0]
    detail = prepare_proteam_detail(raw_dataset, team_slug=selected_team_slug)

    st.markdown("**Team detail**")
    detail_left, detail_mid, detail_right, detail_far, detail_farthest = st.columns(5)
    detail_left.metric(
        "Leader",
        selected_summary["leader_name"] or "None yet",
        delta=f"{selected_summary['Top-1 Share %']:.1f}% of team points",
    )
    detail_mid.metric("Top-3 Share", f"{selected_summary['Top-3 Share %']:.1f}%")
    detail_right.metric(
        "Effective N",
        f"{selected_summary['effective_contributors']:.2f}",
    )
    detail_far.metric(
        "Without rider #1",
        f"{selected_summary['leader_shock_remaining_points']:.1f} pts",
        delta=f"-{selected_summary['Leader Shock %']:.1f}%",
    )
    detail_farthest.metric(
        "Without riders #1-2",
        f"{selected_summary['leader_coleader_shock_remaining_points']:.1f} pts",
        delta=f"-{selected_summary['Leader+Coleader Shock %']:.1f}%",
    )

    if detail.empty:
        st.info(
            "This team is present in the ranking table, but PCS does not currently list any counted rider rows for it. "
            "That usually means the team has not scored counted points yet in this scope."
        )
        return

    bar_chart = px.bar(
        detail.sort_values("points_counted", ascending=True),
        x="points_counted",
        y="rider_name",
        orientation="h",
        text="points_counted",
        color="share_pct",
        labels={
            "points_counted": "Counted points",
            "rider_name": "Rider",
            "share_pct": "Share of team (%)",
        },
        title=f"{selected_team_name}: counted-point contribution by rider",
    )
    bar_chart.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    bar_chart.update_layout(height=max(420, 24 * len(detail) + 120), coloraxis_showscale=False)
    st.plotly_chart(bar_chart, use_container_width=True)

    cumulative_chart = px.line(
        detail,
        x="team_rank_within_counted_list",
        y="cumulative_share_pct",
        markers=True,
        labels={
            "team_rank_within_counted_list": "Rider rank within team",
            "cumulative_share_pct": "Cumulative share of team points (%)",
        },
        title=f"{selected_team_name}: how quickly the rider core reaches 50%, 75%, and 90%",
    )
    cumulative_chart.add_hline(y=50, line_dash="dash", line_color="#8b5cf6")
    cumulative_chart.add_hline(y=75, line_dash="dash", line_color="#d97706")
    cumulative_chart.add_hline(y=90, line_dash="dash", line_color="#b91c1c")
    cumulative_chart.update_layout(height=360)
    st.plotly_chart(cumulative_chart, use_container_width=True)

    detail_table = detail[
        [
            "team_rank_within_counted_list",
            "rider_name",
            "season_years",
            "points_counted",
            "share_pct",
            "cumulative_share_pct",
            "points_not_counted",
            "sanction_points",
        ]
    ].rename(
        columns={
            "team_rank_within_counted_list": "Rank",
            "rider_name": "Rider",
            "season_years": "Seasons",
            "points_counted": "Counted Points",
            "share_pct": "Share of Team (%)",
            "cumulative_share_pct": "Cumulative Share (%)",
            "points_not_counted": "Not Counted",
            "sanction_points": "Sanctions",
        }
    )
    st.download_button(
        "Download selected team rider breakdown as CSV",
        data=detail_table.to_csv(index=False).encode("utf-8"),
        file_name=f"proteam_risk_{selected_team_slug}_{scope}.csv",
        mime="text/csv",
    )
    st.dataframe(
        detail_table.round(
            {
                "Counted Points": 1,
                "Share of Team (%)": 1,
                "Cumulative Share (%)": 1,
                "Not Counted": 1,
                "Sanctions": 1,
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="UCI Points Optimization Model",
        page_icon=":bike:",
        layout="wide",
    )

    st.title("UCI Points Optimization Model")
    st.caption(
        "An explainable race-opportunity and ProTeam-risk app for `.1` and `.Pro` road racing."
    )
    render_start_here()
    initialize_weight_state()
    apply_pending_weight_state()
    initialize_dataset_state()

    with st.sidebar.form("controls"):
        st.subheader("Model Controls")
        years = st.multiselect(
            "Historical years",
            options=list(range(2020, 2027)),
            default=DEFAULT_YEARS,
            help="Use past editions to estimate which races are attractive next season.",
        )
        st.caption(
            "`2020` is available for sensitivity checks, but it is excluded from the default selection because the COVID-disrupted calendar was unusually irregular."
        )
        categories = st.multiselect(
            "Race categories",
            options=list(TARGET_CATEGORIES),
            default=list(TARGET_CATEGORIES),
        )
        planning_year = int(
            st.number_input(
                "Planning season",
                min_value=2020,
                max_value=2035,
                value=DEFAULT_PLANNING_YEAR,
                step=1,
                help="Cross-check recommendations against this season's live calendar.",
            )
        )
        data_source = st.radio(
            "Dataset source",
            options=["Bundled snapshot", "Live scrape"],
            index=0 if SNAPSHOT_PATH.exists() else 1,
            help="Use the CSV snapshot when available for fast startup, or scrape live from FirstCycling.",
        )
        max_races = st.slider(
            "Max race editions to scrape live",
            min_value=20,
            max_value=250,
            value=80,
            step=10,
            help="Lower values keep the app responsive. Use the snapshot builder for full-season exports.",
        )

        st.markdown("**Scoring weights**")
        st.slider(
            "Top-10 payout",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["top10_points"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["top10_points"],
        )
        st.slider(
            "Winner upside",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["winner_points"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["winner_points"],
        )
        st.slider(
            "Softness of top riders",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["field_softness"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["field_softness"],
        )
        st.slider(
            "Softness of full field",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["depth_softness"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["depth_softness"],
        )
        st.slider(
            "Finish-rate reliability",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["finish_rate"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["finish_rate"],
        )
        st.markdown("**Route & specialty fit (beta)**")
        fit_emphasis = st.slider(
            "Fit emphasis",
            0.0,
            1.0,
            0.25,
            0.05,
            help="Blend the beta specialty-fit overlay into the final targeting score. Equal specialty weights keep the overlay neutral.",
        )
        specialty_one_day = st.slider(
            "One-day / classics strength", 0.0, 1.0, DEFAULT_SPECIALTY_WEIGHTS["one_day"], 0.05
        )
        specialty_gc = st.slider("GC / climbing strength", 0.0, 1.0, DEFAULT_SPECIALTY_WEIGHTS["gc"], 0.05)
        specialty_stage_hunter = st.slider(
            "Stage hunter / sprinter strength",
            0.0,
            1.0,
            DEFAULT_SPECIALTY_WEIGHTS["stage_hunter"],
            0.05,
        )
        specialty_time_trial = st.slider(
            "Time-trial strength", 0.0, 1.0, DEFAULT_SPECIALTY_WEIGHTS["time_trial"], 0.05
        )
        specialty_all_round = st.slider(
            "All-round stage depth", 0.0, 1.0, DEFAULT_SPECIALTY_WEIGHTS["all_round"], 0.05
        )

        submitted = st.form_submit_button("Analyze races")

    if not years:
        st.warning("Choose at least one year to build the model.")
        return
    if not categories:
        st.warning("Choose at least one category to analyze.")
        return

    weights = current_weight_state()
    specialty_weights = normalize_specialty_weights(
        {
            "one_day": specialty_one_day,
            "gc": specialty_gc,
            "stage_hunter": specialty_stage_hunter,
            "time_trial": specialty_time_trial,
            "all_round": specialty_all_round,
        }
    )

    if submitted or "dataset" not in st.session_state:
        with st.spinner("Loading race history and scoring opportunities..."):
            if data_source == "Bundled snapshot" and SNAPSHOT_PATH.exists():
                dataset = load_snapshot(SNAPSHOT_PATH, years=years, categories=categories)
            else:
                dataset = get_live_dataset(tuple(years), tuple(categories), max_races)
            st.session_state["dataset"] = ensure_dataset_schema(dataset)
            st.session_state["dataset_source_label"] = data_source
            st.session_state["weights"] = weights

    dataset = ensure_dataset_schema(st.session_state.get("dataset", pd.DataFrame()))
    st.session_state["dataset"] = dataset
    st.session_state.setdefault("dataset_source_label", data_source)
    if dataset.empty:
        st.warning(
            "No race data was loaded. Try live scraping, widen the category/year filters, or generate a snapshot first."
        )
        return

    scored_editions = score_race_editions(
        dataset,
        weights,
        specialty_weights=specialty_weights,
        fit_emphasis=fit_emphasis,
    )
    target_summary = summarize_historical_targets(scored_editions)
    planning_calendar = get_planning_calendar(planning_year, tuple(PLANNING_CALENDAR_CATEGORIES))
    planning_calendar_source = planning_calendar.attrs.get("calendar_source", "live")
    planning_calendar_available = not planning_calendar.empty
    target_summary = overlay_planning_calendar(target_summary, planning_calendar, planning_year)
    target_summary = target_summary.sort_values(
        ["on_planning_calendar", "avg_targeting_score", "avg_arbitrage_score", "avg_top10_points"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    render_model_explainer(
        weights,
        specialty_weights,
        fit_emphasis,
        dataset,
        team_calendar_ev_metadata=get_active_team_calendar_ev_metadata(),
    )

    left, middle, right, far_right, farthest = st.columns(5)
    left.metric("Race editions analyzed", f"{len(scored_editions):,}")
    middle.metric("Category-aware targets", f"{len(target_summary):,}")
    right.metric(
        f"On {planning_year} .1/.Pro calendar",
        f"{int(target_summary['on_planning_calendar'].sum()):,}",
    )
    far_right.metric("Average top-10 payout", f"{scored_editions['top10_points'].mean():.1f}")
    farthest.metric("Average startlist size", f"{scored_editions['startlist_size'].mean():.0f}")
    render_workspace_guide(planning_year)

    top_targets = target_summary.copy()
    top_targets["avg_targeting_score"] = top_targets["avg_targeting_score"].round(1)
    top_targets["avg_arbitrage_score"] = top_targets["avg_arbitrage_score"].round(1)
    top_targets["avg_specialty_fit_score"] = top_targets["avg_specialty_fit_score"].round(1)
    top_targets["avg_top10_points"] = top_targets["avg_top10_points"].round(1)
    top_targets["avg_stage_top10_points"] = top_targets["avg_stage_top10_points"].round(1)
    top_targets["avg_stage_count"] = top_targets["avg_stage_count"].round(1)
    top_targets["avg_top10_field_form"] = top_targets["avg_top10_field_form"].round(1)
    top_targets["avg_points_efficiency"] = top_targets["avg_points_efficiency"].round(2)
    top_targets["planning_scope_match"] = top_targets["planning_scope_match"].map(
        {True: "Same category", False: "Category changed"}
    )
    top_targets.loc[~top_targets["on_planning_calendar"], "planning_scope_match"] = "No in-scope match"
    top_targets = top_targets.rename(
        columns={
            "race_name": "Race",
            "race_country": "Country",
            "category": "Category",
            "race_type": "Race Type",
            "route_profile": "Route Profile",
            "profile_reason": "Profile Reason",
            "category_history": "Category History",
            "years_analyzed": "Same-Category Editions",
            "years": "Years",
            "avg_targeting_score": "Targeting Score",
            "avg_arbitrage_score": "Arbitrage Score",
            "avg_specialty_fit_score": "Specialty Fit",
            "avg_top10_points": "Avg Top-10 Points",
            "avg_stage_top10_points": "Avg Stage Top-10 Points",
            "avg_stage_count": "Avg Stage Days",
            "avg_top10_field_form": "Avg Top-10 Field Form",
            "avg_points_efficiency": "Points per Field-Form",
            "planning_category": f"{planning_year} Category",
            "planning_date_label": f"{planning_year} Date",
            "planning_calendar_status": f"{planning_year} Calendar Status",
            "planning_scope_match": f"{planning_year} Match",
        }
    )

    selected_workspace = st.segmented_control(
        "Workspace",
        options=WORKSPACE_OPTIONS,
        default=WORKSPACE_OPTIONS[0],
        key="workspace_selection",
        label_visibility="collapsed",
        width="stretch",
    )

    if selected_workspace == "Recommended Targets":
        st.subheader("Best Races to Target Next Season")
        if planning_calendar_source == "snapshot":
            st.caption(
                f"Using the bundled {planning_year} planning-calendar snapshot because the live calendar fetch "
                "was unavailable in this session."
            )
        elif planning_calendar_source == "unavailable":
            st.warning(
                f"The {planning_year} planning calendar could not be loaded right now, so the in-season calendar "
                "filter is temporarily disabled."
            )
        show_active_only = st.checkbox(
            f"Only show races on the {planning_year} .1/.Pro calendar",
            value=planning_calendar_available,
            disabled=not planning_calendar_available,
            help="Hide recommendations that are not on this season's in-scope calendar.",
        )
        target_columns = [
            "Race",
            "Country",
            "Category",
            "Route Profile",
            f"{planning_year} Category",
            f"{planning_year} Date",
            f"{planning_year} Match",
            f"{planning_year} Calendar Status",
            "Category History",
            "Race Type",
            "Same-Category Editions",
            "Years",
            "Targeting Score",
            "Arbitrage Score",
            "Specialty Fit",
            "Avg Top-10 Points",
            "Avg Stage Top-10 Points",
            "Avg Stage Days",
            "Avg Top-10 Field Form",
            "Points per Field-Form",
        ]
        export_targets = top_targets.copy()
        if show_active_only:
            export_targets = export_targets[
                export_targets[f"{planning_year} Calendar Status"].str.contains(
                    rf"On {planning_year} \.1/\.Pro calendar", regex=True
                )
            ].copy()
        display_targets = export_targets.head(15)

        if display_targets.empty:
            st.info(
                f"No recommended targets matched the {planning_year} .1/.Pro calendar under the current filters. "
                "Turn off the checkbox to inspect out-of-scope or missing races."
            )
        else:
            st.caption(
                f"Showing {len(display_targets)} races in the app. The CSV export includes {len(export_targets)} races "
                "from the current filter state."
            )
            st.download_button(
                "Download recommended targets as CSV",
                data=export_targets[target_columns].to_csv(index=False).encode("utf-8"),
                file_name=f"uci_points_recommended_targets_{planning_year}.csv",
                mime="text/csv",
            )

        st.dataframe(
            display_targets[target_columns],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(
            "The model lifts races that consistently offer strong top-10 points while historically "
            "drawing softer startlists. Stage races are still ranked as one target each, but their "
            "points totals now include both GC and stage-result payouts. If a race changed category, "
            "the recommendation uses the latest known category and shows the full category history alongside it. "
            f"The extra {planning_year} columns tell you whether that race is actually on this season's calendar. "
            "The beta route-profile overlay then lets you tilt the shortlist toward the kinds of events your chosen specialty mix should suit better."
        )

    if selected_workspace == "Edition Diagnostics":
        st.subheader("Edition-Level Opportunity Map")
        chart_frame = scored_editions.copy()
        chart_frame["label"] = chart_frame["race_name"] + " (" + chart_frame["year"].astype(str) + ")"
        figure = px.scatter(
            chart_frame,
            x="avg_top10_field_form",
            y="top10_points",
            color="category",
            size="arbitrage_score",
            hover_name="label",
            hover_data={
                "startlist_size": True,
                "finish_rate": ":.2f",
                "winner_points": True,
                "total_points": True,
                "targeting_score": ":.1f",
                "specialty_fit_score": ":.1f",
                "route_profile": True,
                "gc_top10_points": True,
                "stage_top10_points": True,
                "stage_count": True,
                "stage_points_share": ":.2f",
                "arbitrage_score": ":.1f",
                "avg_top10_field_form": ":.1f",
                "top10_points": ":.1f",
            },
            labels={
                "avg_top10_field_form": "Top-10 field-form strength",
                "top10_points": "Top-10 points payout",
            },
        )
        figure.update_layout(height=520, legend_title_text="Category")
        st.plotly_chart(figure, use_container_width=True)

        edition_table = scored_editions[
            [
                "race_name",
                "year",
                "category",
                "race_type",
                "race_country",
                "route_profile",
                "profile_reason",
                "targeting_score",
                "specialty_fit_score",
                "arbitrage_score",
                "top10_points",
                "winner_points",
                "gc_top10_points",
                "stage_top10_points",
                "stage_count",
                "stage_points_share",
                "avg_top10_field_form",
                "total_field_form",
                "finish_rate",
                "startlist_size",
            ]
        ].copy()
        edition_table = edition_table.rename(
            columns={
                "race_name": "Race",
                "year": "Year",
                "category": "Category",
                "race_type": "Race Type",
                "race_country": "Country",
                "route_profile": "Route Profile",
                "profile_reason": "Profile Reason",
                "targeting_score": "Targeting Score",
                "specialty_fit_score": "Specialty Fit",
                "arbitrage_score": "Score",
                "top10_points": "Top-10 Points",
                "winner_points": "Winner Points",
                "gc_top10_points": "GC Top-10 Points",
                "stage_top10_points": "Stage Top-10 Points",
                "stage_count": "Stage Days",
                "stage_points_share": "Stage Share",
                "avg_top10_field_form": "Top-10 Field Form",
                "total_field_form": "Total Field Form",
                "finish_rate": "Finish Rate",
                "startlist_size": "Startlist Size",
            }
        )
        st.dataframe(
            edition_table.round(
                {
                    "Targeting Score": 1,
                    "Specialty Fit": 1,
                    "Score": 1,
                    "Top-10 Points": 1,
                    "Winner Points": 1,
                    "GC Top-10 Points": 1,
                    "Stage Top-10 Points": 1,
                    "Stage Days": 0,
                    "Stage Share": 2,
                    "Top-10 Field Form": 1,
                    "Total Field Form": 1,
                    "Finish Rate": 2,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    if selected_workspace == "Backtest & Calibration":
        render_backtest_tab(dataset, years, categories)

    if selected_workspace == "ProTeam Risk Monitor":
        render_proteam_risk_tab()

    if selected_workspace == "Team Calendar EV":
        render_team_calendar_ev_workspace()

    if selected_workspace == "Data Sources":
        render_data_sources_tab(
            dataset=dataset,
            dataset_source_label=str(st.session_state.get("dataset_source_label") or data_source),
            planning_calendar=planning_calendar,
            planning_calendar_source=planning_calendar_source,
            planning_year=planning_year,
        )


if __name__ == "__main__":
    main()
