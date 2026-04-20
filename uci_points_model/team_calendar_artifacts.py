from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from .calendar_ev import (
    DEFAULT_EV_WEIGHTS,
    build_actual_points_table,
    build_historical_target_summary,
    build_team_calendar_ev,
    normalize_team_profile,
    summarize_team_calendar_ev,
)
from .roster_scenarios import (
    ROSTER_SCENARIO_FORMULA,
    ROSTER_SCENARIO_SCOPE,
    get_roster_scenario_preset_version,
)
from .team_calendar import CHANGELOG_COLUMNS, build_live_team_calendar, build_schedule_changelog, derive_calendar_status
from .team_identity import build_team_artifact_stem, canonicalize_team_slug
from .team_profiles import load_team_archetypes, validate_team_profile

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACKED_PROTEAMS_MANIFEST = ROOT / "config" / "tracked_proteams_2026.csv"
DEFAULT_PROTEAM_PROFILE_PATH = ROOT / "data" / "team_profiles" / "default_proteam_2026_profile.json"
TEAM_CALENDARS_DIR = ROOT / "data" / "team_calendars"
TEAM_RESULTS_DIR = ROOT / "data" / "team_results"
TEAM_EV_DIR = ROOT / "data" / "team_ev"

MANIFEST_REQUIRED_COLUMNS = ["team_slug", "pcs_team_slug", "team_name", "planning_year"]
READABLE_BOOL_TRUE = {"", "1", "true", "yes", "y", "on"}
READABLE_BOOL_FALSE = {"0", "false", "no", "n", "off"}

OPPORTUNITY_WEIGHT_RATIONALE = {
    "avg_points_efficiency": "Highest weight because the model should favor races that have historically turned field quality into points efficiently.",
    "avg_top10_points": "Rewards broad scoring opportunity instead of only winner upside.",
    "avg_winner_points": "Keeps a smaller reward for races with real ceiling if the team lands a big result.",
    "avg_stage_top10_points": "Adds stage-race scoring depth without letting stage volume dominate the entire ranking.",
    "field_softness_score": "Rewards races whose historical top end has looked softer for the points on offer.",
}

TEAM_STRENGTH_RATIONALE = {
    "one_day": "How much the team profile should care about classic-style one-day signals.",
    "stage_hunter": "How much the profile should value stage-hunting or sprinter-friendly stage-race signals.",
    "gc": "How much the profile should care about GC-heavy stage-race opportunity.",
    "time_trial": "How much time-trial signals should influence team fit.",
    "all_round": "How much the profile should reward balanced, all-round stage-race opportunity.",
    "sprint_bonus": "Extra boost for sprint-sensitive opportunities when the roster is built to exploit them.",
}

PARTICIPATION_RULE_RATIONALE = {
    "completed": "Completed races get full participation confidence because the team actually started.",
    "program_confirmed": "A live team program listing is strong evidence, but still below a completed race.",
    "observed_startlist": "Observed startlists are nearly as strong as a program-confirmed entry.",
    "calendar_seed": "The planning calendar alone is a weaker signal, so future starts get a haircut.",
    "overlap_penalty": "When races overlap, confidence is capped because a team cannot fully commit to both.",
}

EXECUTION_RULE_RATIONALE = "Execution multipliers are conservative realization haircuts by race category. Bigger races keep a lower multiplier because historical opportunity does not fully translate into team-level realized points."


@dataclass(frozen=True)
class TrackedTeamConfig:
    team_slug: str
    pcs_team_slug: str
    team_name: str
    planning_year: int
    profile_path: Path | None = None
    enabled: bool = True
    notes: str = ""

    @property
    def artifact_stem(self) -> str:
        return build_team_artifact_stem(self.team_slug, self.planning_year)


@dataclass(frozen=True)
class TeamCalendarArtifactPaths:
    artifact_stem: str
    calendar_path: Path
    changelog_path: Path
    actual_points_path: Path
    ev_output_path: Path
    summary_output_path: Path
    metadata_output_path: Path
    readme_path: Path
    dictionary_path: Path


@dataclass
class TeamCalendarEvArtifacts:
    team: TrackedTeamConfig
    team_profile: dict[str, object]
    paths: TeamCalendarArtifactPaths
    calendar_df: pd.DataFrame
    changelog_df: pd.DataFrame
    actual_points_df: pd.DataFrame
    calendar_ev_df: pd.DataFrame
    summary_df: pd.DataFrame
    metadata: dict[str, object]
    readme_text: str
    dictionary_text: str


@dataclass(frozen=True)
class TeamBuildOutcome:
    team_slug: str
    success: bool
    error: str = ""
    paths: TeamCalendarArtifactPaths | None = None


def load_tracked_team_configs(
    manifest_path: str | Path = DEFAULT_TRACKED_PROTEAMS_MANIFEST,
    *,
    enabled_only: bool = False,
) -> list[TrackedTeamConfig]:
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Tracked-team manifest not found: {path}")

    manifest_df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing_columns = [column for column in MANIFEST_REQUIRED_COLUMNS if column not in manifest_df.columns]
    if missing_columns:
        raise ValueError(f"Tracked-team manifest missing required columns: {', '.join(missing_columns)}")

    configs: list[TrackedTeamConfig] = []
    for index, row in manifest_df.iterrows():
        line_number = index + 2
        raw_year = str(row.get("planning_year") or "").strip()
        if not raw_year:
            raise ValueError(f"Tracked-team manifest row {line_number} is missing planning_year.")
        planning_year = pd.to_numeric(raw_year, errors="coerce")
        if pd.isna(planning_year):
            raise ValueError(f"Tracked-team manifest row {line_number} has invalid planning_year: {raw_year}")

        team_slug = canonicalize_team_slug(str(row.get("team_slug") or "").strip(), int(planning_year))
        pcs_team_slug = str(row.get("pcs_team_slug") or "").strip()
        team_name = str(row.get("team_name") or "").strip()
        if not team_slug:
            raise ValueError(f"Tracked-team manifest row {line_number} is missing team_slug.")
        if not pcs_team_slug:
            raise ValueError(f"Tracked-team manifest row {line_number} is missing pcs_team_slug.")
        if not team_name:
            raise ValueError(f"Tracked-team manifest row {line_number} is missing team_name.")

        enabled = _parse_enabled_flag(str(row.get("enabled") or ""))
        if enabled_only and not enabled:
            continue

        profile_path_value = str(row.get("profile_path") or "").strip()
        configs.append(
            TrackedTeamConfig(
                team_slug=team_slug,
                pcs_team_slug=pcs_team_slug,
                team_name=team_name,
                planning_year=int(planning_year),
                profile_path=_resolve_repo_path(profile_path_value) if profile_path_value else None,
                enabled=enabled,
                notes=str(row.get("notes") or "").strip(),
            )
        )

    return configs


def resolve_team_artifact_paths(
    team_slug: str,
    planning_year: int,
    *,
    calendar_path: str | Path | None = None,
    changelog_path: str | Path | None = None,
    actual_points_path: str | Path | None = None,
    ev_output_path: str | Path | None = None,
    summary_output_path: str | Path | None = None,
    readme_path: str | Path | None = None,
    dictionary_path: str | Path | None = None,
) -> TeamCalendarArtifactPaths:
    artifact_stem = build_team_artifact_stem(team_slug, planning_year)
    resolved_summary_path = (
        Path(summary_output_path) if summary_output_path else TEAM_EV_DIR / f"{artifact_stem}_calendar_ev_summary.csv"
    )
    return TeamCalendarArtifactPaths(
        artifact_stem=artifact_stem,
        calendar_path=Path(calendar_path) if calendar_path else TEAM_CALENDARS_DIR / f"{artifact_stem}_latest.csv",
        changelog_path=Path(changelog_path) if changelog_path else TEAM_CALENDARS_DIR / f"{artifact_stem}_changelog.csv",
        actual_points_path=(
            Path(actual_points_path) if actual_points_path else TEAM_RESULTS_DIR / f"{artifact_stem}_actual_points.csv"
        ),
        ev_output_path=Path(ev_output_path) if ev_output_path else TEAM_EV_DIR / f"{artifact_stem}_calendar_ev.csv",
        summary_output_path=resolved_summary_path,
        metadata_output_path=_metadata_path_for_summary(resolved_summary_path),
        readme_path=Path(readme_path) if readme_path else TEAM_EV_DIR / "README.md",
        dictionary_path=Path(dictionary_path) if dictionary_path else TEAM_EV_DIR / "data_dictionary.md",
    )


def resolve_team_profile(
    team: TrackedTeamConfig,
    *,
    default_profile_path: str | Path = DEFAULT_PROTEAM_PROFILE_PATH,
) -> dict[str, object]:
    default_path = Path(default_profile_path)
    if not default_path.exists():
        raise FileNotFoundError(f"Default team profile not found: {default_path}")

    merged_profile = json.loads(default_path.read_text())
    if team.profile_path:
        if not team.profile_path.exists():
            raise FileNotFoundError(f"Team profile override not found: {team.profile_path}")
        merged_profile = _deep_merge_dicts(merged_profile, json.loads(team.profile_path.read_text()))

    merged_profile["team_slug"] = team.team_slug
    merged_profile["pcs_team_slug"] = team.pcs_team_slug
    merged_profile["team_name"] = team.team_name
    merged_profile["planning_year"] = int(team.planning_year)
    merged_profile = normalize_team_profile(merged_profile)
    return validate_team_profile(merged_profile, load_team_archetypes())


def build_team_calendar_ev_artifacts(
    team: TrackedTeamConfig,
    *,
    default_profile_path: str | Path = DEFAULT_PROTEAM_PROFILE_PATH,
    paths: TeamCalendarArtifactPaths | None = None,
    refresh_calendar: bool = False,
    refresh_actual_points: bool = True,
    program_path: str | Path | None = None,
    as_of_date: str | date | None = None,
    team_calendar_client=None,
    points_client=None,
    scraped_at_utc: str | None = None,
    detected_at_utc: str | None = None,
    checked_at_utc: str | None = None,
) -> TeamCalendarEvArtifacts:
    resolved_paths = paths or resolve_team_artifact_paths(team.team_slug, team.planning_year)
    team_profile = resolve_team_profile(team, default_profile_path=default_profile_path)
    calendar_df, changelog_df = _load_or_refresh_calendar(
        team=team,
        paths=resolved_paths,
        refresh_calendar=refresh_calendar,
        program_path=program_path,
        as_of_date=as_of_date,
        client=team_calendar_client,
        scraped_at_utc=scraped_at_utc,
        detected_at_utc=detected_at_utc,
    )
    if not refresh_actual_points and resolved_paths.actual_points_path.exists():
        actual_points_df = _load_actual_points_snapshot(resolved_paths.actual_points_path)
    else:
        actual_points_df = build_actual_points_table(
            team_slug=team.team_slug,
            planning_year=team.planning_year,
            team_calendar=calendar_df,
            pcs_team_slug=team.pcs_team_slug,
            client=points_client,
            checked_at_utc=checked_at_utc,
            as_of_date=as_of_date,
        )
    historical_summary_df = build_historical_target_summary(planning_year=team.planning_year)
    calendar_ev_df = build_team_calendar_ev(
        team_slug=team.team_slug,
        planning_year=team.planning_year,
        historical_summary=historical_summary_df,
        team_calendar=calendar_df,
        team_profile=team_profile,
        actual_points_df=actual_points_df,
        as_of_date=as_of_date,
    )
    summary_df = summarize_team_calendar_ev(calendar_ev_df)
    metadata = build_team_calendar_ev_metadata(
        team=team,
        team_profile=team_profile,
        summary_df=summary_df,
        calendar_rows=len(calendar_ev_df),
    )
    return TeamCalendarEvArtifacts(
        team=team,
        team_profile=team_profile,
        paths=resolved_paths,
        calendar_df=calendar_df,
        changelog_df=changelog_df,
        actual_points_df=actual_points_df,
        calendar_ev_df=calendar_ev_df,
        summary_df=summary_df,
        metadata=metadata,
        readme_text=build_shared_team_ev_readme(),
        dictionary_text=build_shared_team_ev_data_dictionary(),
    )


def build_tracked_team_calendar_ev(
    team_configs: list[TrackedTeamConfig],
    *,
    team_slug: str | None = None,
    default_profile_path: str | Path = DEFAULT_PROTEAM_PROFILE_PATH,
    as_of_date: str | date | None = None,
    build_bundle_fn: Callable[..., TeamCalendarEvArtifacts] = build_team_calendar_ev_artifacts,
    write_bundle_fn: Callable[..., None] = None,
    write_shared_docs_fn: Callable[..., None] = None,
) -> list[TeamBuildOutcome]:
    bundle_writer = write_bundle_fn or write_team_calendar_ev_artifacts
    docs_writer = write_shared_docs_fn or write_shared_team_ev_docs

    selected_teams = _filter_team_configs(team_configs, team_slug=team_slug)
    outcomes: list[TeamBuildOutcome] = []
    docs_source_bundle: TeamCalendarEvArtifacts | None = None

    for team in selected_teams:
        try:
            bundle = build_bundle_fn(
                team,
                default_profile_path=default_profile_path,
                as_of_date=as_of_date,
                refresh_calendar=True,
            )
            bundle_writer(bundle, write_changelog=True, write_shared_docs=False)
            if docs_source_bundle is None:
                docs_source_bundle = bundle
            outcomes.append(TeamBuildOutcome(team_slug=team.team_slug, success=True, paths=bundle.paths))
        except Exception as exc:  # noqa: BLE001
            outcomes.append(
                TeamBuildOutcome(
                    team_slug=team.team_slug,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    if docs_source_bundle is not None:
        docs_writer(
            docs_source_bundle.paths.readme_path,
            docs_source_bundle.paths.dictionary_path,
            docs_source_bundle.readme_text,
            docs_source_bundle.dictionary_text,
        )

    return outcomes


def write_team_calendar_ev_artifacts(
    bundle: TeamCalendarEvArtifacts,
    *,
    write_changelog: bool = True,
    write_shared_docs: bool = True,
) -> None:
    for output_path in [
        bundle.paths.calendar_path,
        bundle.paths.actual_points_path,
        bundle.paths.ev_output_path,
        bundle.paths.summary_output_path,
        bundle.paths.metadata_output_path,
    ]:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    bundle.calendar_df.to_csv(bundle.paths.calendar_path, index=False)
    if write_changelog:
        bundle.paths.changelog_path.parent.mkdir(parents=True, exist_ok=True)
        bundle.changelog_df.to_csv(bundle.paths.changelog_path, index=False)
    bundle.actual_points_df.to_csv(bundle.paths.actual_points_path, index=False)
    bundle.calendar_ev_df.to_csv(bundle.paths.ev_output_path, index=False)
    bundle.summary_df.to_csv(bundle.paths.summary_output_path, index=False)
    bundle.paths.metadata_output_path.write_text(json.dumps(bundle.metadata, indent=2, sort_keys=True) + "\n")

    if write_shared_docs:
        write_shared_team_ev_docs(
            bundle.paths.readme_path,
            bundle.paths.dictionary_path,
            bundle.readme_text,
            bundle.dictionary_text,
        )


def write_shared_team_ev_docs(
    readme_path: str | Path,
    dictionary_path: str | Path,
    readme_text: str | None = None,
    dictionary_text: str | None = None,
) -> None:
    resolved_readme = Path(readme_path)
    resolved_dictionary = Path(dictionary_path)
    resolved_readme.parent.mkdir(parents=True, exist_ok=True)
    resolved_dictionary.parent.mkdir(parents=True, exist_ok=True)
    resolved_readme.write_text(readme_text or build_shared_team_ev_readme())
    resolved_dictionary.write_text(dictionary_text or build_shared_team_ev_data_dictionary())


def build_shared_team_ev_readme() -> str:
    return """# Team Calendar EV Dataset

This directory stores deterministic Team Calendar EV artifacts for tracked team-seasons.

## Artifact Set

- `data/team_calendars/<team_slug>_<year>_latest.csv`: latest team calendar snapshot
- `data/team_calendars/<team_slug>_<year>_changelog.csv`: schedule changelog against the prior saved snapshot
- `data/team_results/<team_slug>_<year>_actual_points.csv`: live PCS actual points by race when available
- `data/team_ev/<team_slug>_<year>_calendar_ev.csv`: race-level expected-value output
- `data/team_ev/<team_slug>_<year>_calendar_ev_summary.csv`: one-row team-season KPI summary
- `data/team_ev/<team_slug>_<year>_calendar_ev_metadata.json`: saved model assumptions and build metadata

## Build

Refresh a single team-season with:

```bash
python scripts/build_team_calendar_ev.py \\
  --team-slug <team-slug> \\
  --pcs-team-slug <pcs-team-slug> \\
  --planning-year <year> \\
  --team-profile-path data/team_profiles/<team_slug>_<year>_profile.json \\
  --calendar-path data/team_calendars/<team_slug>_<year>_latest.csv \\
  --actual-points-path data/team_results/<team_slug>_<year>_actual_points.csv \\
  --ev-output-path data/team_ev/<team_slug>_<year>_calendar_ev.csv \\
  --summary-output-path data/team_ev/<team_slug>_<year>_calendar_ev_summary.csv \\
  --readme-path data/team_ev/README.md \\
  --dictionary-path data/team_ev/data_dictionary.md
```

Refresh all tracked teams in the manifest with:

```bash
python scripts/build_all_proteam_calendar_ev.py --manifest-path config/tracked_proteams_2026.csv
```
"""


def build_shared_team_ev_data_dictionary() -> str:
    race_level_rows = [
        ("team_slug", "Stable team identifier shared across seasons."),
        ("team_name", "Human-readable team name."),
        ("planning_year", "Planning calendar year."),
        ("race_id", "Planning calendar race identifier."),
        ("race_name", "Planning calendar race name."),
        ("category", "Current race category from the planning calendar."),
        ("date_label", "Planning calendar date label."),
        ("month", "Planning calendar month number."),
        ("start_date", "Normalized planning start date."),
        ("end_date", "Normalized planning end date."),
        ("pcs_race_slug", "PCS race slug used to fetch the team-in-race points page."),
        ("historical_years_analyzed", "Count of prior editions used in the historical summary."),
        ("race_type", "Historical race type label from the race-edition snapshot."),
        ("route_profile", "Lightweight race-profile label derived from historical structure."),
        ("avg_top10_points", "Average historical top-10 points haul."),
        ("avg_winner_points", "Average historical winner points."),
        ("avg_points_efficiency", "Average historical points-per-top10-form efficiency."),
        ("avg_stage_top10_points", "Average historical stage-race top-10 points component."),
        ("avg_stage_count", "Average historical stage count."),
        ("avg_top10_field_form", "Average historical top-10 field-form proxy."),
        ("base_opportunity_index", "Normalized historical opportunity score."),
        ("base_opportunity_points", "Points-space base opportunity anchor."),
        ("one_day_signal", "Historical one-day fit signal used inside the team-fit layer."),
        ("stage_hunter_signal", "Historical stage-hunter fit signal used inside the team-fit layer."),
        ("gc_signal", "Historical GC fit signal used inside the team-fit layer."),
        ("time_trial_signal", "Historical time-trial fit signal used inside the team-fit layer."),
        ("all_round_signal", "Historical all-round fit signal used inside the team-fit layer."),
        ("sprint_bonus_signal", "Historical sprint-sensitive fit signal used inside the team-fit layer."),
        ("specialty_fit_score", "Team-fit score from non-sprint dimensions."),
        ("sprint_fit_bonus", "Explicit sprint-sensitive team-fit add-on."),
        ("team_fit_score", "Combined normalized team-fit score."),
        ("team_fit_multiplier", "Bounded multiplier applied to base opportunity."),
        ("participation_confidence", "Deterministic participation confidence factor."),
        ("execution_multiplier", "Category-based conservative realization haircut."),
        ("expected_points", "Final deterministic Version 2 expected-value estimate."),
        ("actual_points", "Live PCS actual UCI points for the team in that race when known."),
        ("ev_gap", "Actual minus expected points when actuals are known."),
        ("status", "Calendar state such as completed or scheduled."),
        ("team_calendar_status", "Current team calendar membership flag."),
        ("source", "Snapshot source label."),
        ("overlap_group", "Overlap flag for simultaneous race windows."),
        ("notes", "Join or data quality notes."),
        ("as_of_date", "Persisted freshness marker used for status derivation and UI messaging."),
    ]
    summary_rows = [
        ("team_slug", "Stable team identifier shared across seasons."),
        ("planning_year", "Planning calendar year."),
        ("as_of_date", "Freshness marker shown in the UI."),
        ("total_expected_points", "Full-season expected-value total."),
        ("completed_expected_points", "Expected points from races whose status is completed."),
        ("remaining_expected_points", "Expected points from races whose status is scheduled."),
        ("actual_points_known", "Observed points summed only from races with known actuals, including confirmed zeroes."),
        ("ev_gap_known", "Observed minus expected points summed only where actuals are known."),
        ("race_count", "Total number of tracked races in the saved season artifact."),
        ("completed_race_count", "Number of completed races in the saved season artifact."),
        ("remaining_race_count", "Number of scheduled races in the saved season artifact."),
    ]
    lines = ["# Team Calendar EV Data Dictionary", "", "## Race-Level EV File", "", "| Field | Description |", "| --- | --- |"]
    lines.extend(f"| `{field}` | {description} |" for field, description in race_level_rows)
    lines.extend(["", "## Summary File", "", "| Field | Description |", "| --- | --- |"])
    lines.extend(f"| `{field}` | {description} |" for field, description in summary_rows)
    lines.extend(
        [
            "",
            "## UI-Only Roster Scenario Overlay",
            "",
            "The Streamlit `Team Calendar EV` workspace can recompute a non-persistent roster scenario overlay directly from the saved race-level EV artifact.",
            "",
            f"- Scope: `{ROSTER_SCENARIO_SCOPE}`",
            f"- Formula: `{ROSTER_SCENARIO_FORMULA}`",
            f"- Preset catalog version: `{get_roster_scenario_preset_version()}`",
            "- Saved artifact fields stay unchanged; the overlay adds scenario columns only inside the app and in the optional scenario download.",
            "- The first version keeps `base_opportunity_points` and `execution_multiplier` fixed to the saved artifact and changes only team-fit plus participation assumptions.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_team_calendar_ev_metadata(
    *,
    team: TrackedTeamConfig,
    team_profile: dict[str, object],
    summary_df: pd.DataFrame,
    calendar_rows: int,
) -> dict[str, object]:
    summary_row = summary_df.iloc[0].to_dict() if not summary_df.empty else {}
    strength_weights = {
        key: float(value)
        for key, value in dict(team_profile.get("strength_weights", {})).items()
    }
    execution_rules = {
        key: float(value)
        for key, value in dict(team_profile.get("execution_rules", {})).items()
    }
    participation_rules = {
        key: float(value)
        for key, value in dict(team_profile.get("participation_rules", {})).items()
    }
    profile_rationale = [str(item).strip() for item in list(team_profile.get("profile_rationale", [])) if str(item).strip()]
    weight_fit_summary = _json_ready_mapping(dict(team_profile.get("weight_fit_summary", {})))
    strength_rationale = dict(team_profile.get("strength_weight_rationale", {})) or TEAM_STRENGTH_RATIONALE
    participation_rationale = dict(team_profile.get("participation_rule_rationale", {})) or PARTICIPATION_RULE_RATIONALE
    execution_rule_rationale = str(team_profile.get("execution_rule_rationale") or EXECUTION_RULE_RATIONALE).strip()
    team_fit_rationale = str(
        team_profile.get("team_fit_rationale")
        or "The multiplier is bounded as floor + range * team_fit_score, which keeps team fit as an adjustment rather than letting it overwhelm the historical opportunity anchor."
    ).strip()
    return {
        "artifact_row_count": int(calendar_rows),
        "as_of_date": str(summary_row.get("as_of_date") or ""),
        "expected_points_formula": "base_opportunity_points * team_fit_multiplier * participation_confidence * execution_multiplier",
        "opportunity_model": {
            "rationale": OPPORTUNITY_WEIGHT_RATIONALE,
            "weights": {key: float(value) for key, value in DEFAULT_EV_WEIGHTS.items()},
        },
        "pcs_team_slug": team.pcs_team_slug,
        "planning_year": int(team.planning_year),
        "roster_scenario_formula": ROSTER_SCENARIO_FORMULA,
        "roster_scenario_preset_version": get_roster_scenario_preset_version(),
        "roster_scenario_scope": ROSTER_SCENARIO_SCOPE,
        "team_name": team.team_name,
        "team_profile": {
            "archetype_description": str(team_profile.get("archetype_description") or "").strip(),
            "archetype_key": str(team_profile.get("archetype_key") or "").strip(),
            "archetype_label": str(team_profile.get("archetype_label") or "").strip(),
            "execution_rule_rationale": execution_rule_rationale,
            "execution_rules": execution_rules,
            "participation_rule_rationale": participation_rationale,
            "participation_rules": participation_rules,
            "profile_confidence": str(team_profile.get("profile_confidence") or "").strip(),
            "profile_rationale": profile_rationale,
            "profile_version": str(team_profile.get("profile_version") or "").strip(),
            "strength_weight_rationale": strength_rationale,
            "strength_weights": strength_weights,
            "team_fit_floor": float(team_profile.get("team_fit_floor", 0.70)),
            "team_fit_range": float(team_profile.get("team_fit_range", 0.30)),
            "team_fit_rationale": team_fit_rationale,
            "weight_fit_method": str(team_profile.get("weight_fit_method") or "").strip(),
            "weight_fit_summary": weight_fit_summary,
        },
        "team_slug": team.team_slug,
    }


def _filter_team_configs(team_configs: list[TrackedTeamConfig], team_slug: str | None = None) -> list[TrackedTeamConfig]:
    if not team_slug:
        return list(team_configs)

    filtered: list[TrackedTeamConfig] = []
    for team in team_configs:
        if canonicalize_team_slug(team_slug, team.planning_year) == team.team_slug:
            filtered.append(team)
    return filtered


def _load_or_refresh_calendar(
    *,
    team: TrackedTeamConfig,
    paths: TeamCalendarArtifactPaths,
    refresh_calendar: bool,
    program_path: str | Path | None,
    as_of_date: str | date | None,
    client,
    scraped_at_utc: str | None,
    detected_at_utc: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    previous_snapshot_df = _load_previous_snapshot(paths.calendar_path)
    if refresh_calendar or not paths.calendar_path.exists():
        latest_snapshot_df = build_live_team_calendar(
            team_slug=team.team_slug,
            planning_year=team.planning_year,
            pcs_team_slug=team.pcs_team_slug,
            client=client,
            program_path=str(program_path) if program_path is not None else None,
            team_name=team.team_name,
            scraped_at_utc=scraped_at_utc,
            as_of_date=as_of_date,
        )
        if latest_snapshot_df.empty:
            raise RuntimeError(f"No team calendar rows were built for {team.team_slug} {team.planning_year}.")
        latest_snapshot_df["team_slug"] = team.team_slug
        latest_snapshot_df["team_name"] = team.team_name
        latest_snapshot_df["planning_year"] = int(team.planning_year)
        changelog_df = build_schedule_changelog(
            previous_df=previous_snapshot_df,
            latest_df=latest_snapshot_df,
            team_slug=team.team_slug,
            planning_year=team.planning_year,
            detected_at_utc=detected_at_utc,
        )
        return latest_snapshot_df, changelog_df

    loaded_snapshot_df = pd.read_csv(paths.calendar_path, low_memory=False)
    if "race_id" in loaded_snapshot_df.columns:
        loaded_snapshot_df["race_id"] = pd.to_numeric(loaded_snapshot_df["race_id"], errors="coerce").astype("Int64")
    if "end_date" in loaded_snapshot_df.columns:
        loaded_snapshot_df["status"] = loaded_snapshot_df["end_date"].map(
            lambda value: derive_calendar_status(value, as_of_date)
        )
    loaded_snapshot_df["team_slug"] = team.team_slug
    loaded_snapshot_df["team_name"] = team.team_name
    loaded_snapshot_df["planning_year"] = int(team.planning_year)
    return loaded_snapshot_df, _load_changelog(paths.changelog_path)


def _load_previous_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    previous_df = pd.read_csv(path, low_memory=False)
    if "race_id" in previous_df.columns:
        previous_df["race_id"] = pd.to_numeric(previous_df["race_id"], errors="coerce").astype("Int64")
    return previous_df


def _load_changelog(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CHANGELOG_COLUMNS)
    return pd.read_csv(path, low_memory=False)


def _load_actual_points_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    actual_points_df = pd.read_csv(path, low_memory=False)
    if "race_id" in actual_points_df.columns:
        actual_points_df["race_id"] = pd.to_numeric(actual_points_df["race_id"], errors="coerce").astype("Int64")
    if "actual_points" in actual_points_df.columns:
        actual_points_df["actual_points"] = pd.to_numeric(actual_points_df["actual_points"], errors="coerce").astype("Float64")
    if "rider_count" in actual_points_df.columns:
        actual_points_df["rider_count"] = pd.to_numeric(actual_points_df["rider_count"], errors="coerce").astype("Int64")
    return actual_points_df


def _metadata_path_for_summary(summary_output_path: Path) -> Path:
    if summary_output_path.name.endswith("_calendar_ev_summary.csv"):
        return summary_output_path.with_name(
            summary_output_path.name.replace("_calendar_ev_summary.csv", "_calendar_ev_metadata.json")
        )
    return summary_output_path.with_suffix(".json")


def _json_ready_mapping(mapping: dict[str, object]) -> dict[str, object]:
    ready: dict[str, object] = {}
    for key, value in mapping.items():
        if isinstance(value, bool):
            ready[str(key)] = value
        elif isinstance(value, int):
            ready[str(key)] = int(value)
        elif isinstance(value, float):
            ready[str(key)] = float(value)
        else:
            ready[str(key)] = str(value).strip()
    return ready


def _parse_enabled_flag(raw_value: str) -> bool:
    normalized = str(raw_value or "").strip().lower()
    if normalized in READABLE_BOOL_TRUE:
        return True
    if normalized in READABLE_BOOL_FALSE:
        return False
    raise ValueError(f"Unsupported enabled value: {raw_value}")


def _resolve_repo_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / path


def _deep_merge_dicts(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged
