from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .historical_data_import import (
    DEFAULT_IMPORTED_ROOT,
    DEFAULT_SOURCE_ROOT_CANDIDATES,
    get_historical_import_spec,
    load_imported_historical_dataset,
)
from .target_definitions import build_next_top5_targets

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "audits"
DEFAULT_TEAM_PANEL_PATH = PROJECT_ROOT / "data" / "model_inputs" / "team_season_panel.csv"
DEFAULT_RIDER_PANEL_PATH = PROJECT_ROOT / "data" / "model_inputs" / "rider_season_panel.csv"
DEFAULT_TEAM_EV_ROOT = PROJECT_ROOT / "data" / "team_ev"
DEFAULT_TEAM_CALENDAR_ROOT = PROJECT_ROOT / "data" / "team_calendars"
DEFAULT_TEAM_RESULTS_ROOT = PROJECT_ROOT / "data" / "team_results"

DEFAULT_TEAM_SAMPLE_SIZE = 10
DEFAULT_RIDER_SAMPLE_SIZE = 25
DEFAULT_RACE_SAMPLE_SIZE = 10
DEFAULT_RANDOM_SEED = 20260420
FLOAT_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class ManualSampleAuditArtifacts:
    summary: dict[str, object]
    team_audit: pd.DataFrame
    rider_audit: pd.DataFrame
    race_audit: pd.DataFrame
    report_text: str


def run_manual_sample_audits(
    *,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    upstream_root: str | Path | None = None,
    team_panel_path: str | Path = DEFAULT_TEAM_PANEL_PATH,
    rider_panel_path: str | Path = DEFAULT_RIDER_PANEL_PATH,
    team_ev_root: str | Path = DEFAULT_TEAM_EV_ROOT,
    team_calendar_root: str | Path = DEFAULT_TEAM_CALENDAR_ROOT,
    team_results_root: str | Path = DEFAULT_TEAM_RESULTS_ROOT,
    team_sample_size: int = DEFAULT_TEAM_SAMPLE_SIZE,
    rider_sample_size: int = DEFAULT_RIDER_SAMPLE_SIZE,
    race_sample_size: int = DEFAULT_RACE_SAMPLE_SIZE,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> ManualSampleAuditArtifacts:
    resolved_upstream_root = _resolve_upstream_root(upstream_root)

    team_panel = pd.read_csv(team_panel_path, low_memory=False)
    rider_panel = pd.read_csv(rider_panel_path, low_memory=False)

    imported_team = load_imported_historical_dataset(
        "historical_proteam_team_panel",
        import_root=import_root,
    )
    imported_rider = load_imported_historical_dataset(
        "historical_proteam_rider_panel",
        import_root=import_root,
    )
    imported_result_summary = load_imported_historical_dataset(
        "rider_season_result_summary",
        import_root=import_root,
    )
    imported_transfer = load_imported_historical_dataset(
        "rider_transfer_context_enriched",
        import_root=import_root,
    )

    upstream_team = _load_upstream_dataset("historical_proteam_team_panel", resolved_upstream_root)
    upstream_rider = _load_upstream_dataset("historical_proteam_rider_panel", resolved_upstream_root)
    upstream_result_summary = _load_upstream_dataset("rider_season_result_summary", resolved_upstream_root)
    upstream_transfer = _load_upstream_dataset("rider_transfer_context_enriched", resolved_upstream_root)
    next_top5_targets = build_next_top5_targets(import_root=import_root)

    team_audit = _run_team_sample_audit(
        team_panel=team_panel,
        imported_team=imported_team,
        upstream_team=upstream_team,
        imported_rider=imported_rider,
        next_top5_targets=next_top5_targets,
        sample_size=team_sample_size,
        random_seed=random_seed,
    )
    rider_audit = _run_rider_sample_audit(
        rider_panel=rider_panel,
        imported_rider=imported_rider,
        upstream_rider=upstream_rider,
        imported_result_summary=imported_result_summary,
        upstream_result_summary=upstream_result_summary,
        imported_transfer=imported_transfer,
        upstream_transfer=upstream_transfer,
        sample_size=rider_sample_size,
        random_seed=random_seed,
    )
    race_audit = _run_race_sample_audit(
        team_ev_root=Path(team_ev_root),
        team_calendar_root=Path(team_calendar_root),
        team_results_root=Path(team_results_root),
        sample_size=race_sample_size,
        random_seed=random_seed,
    )

    summary = _build_summary(
        resolved_upstream_root=resolved_upstream_root,
        team_audit=team_audit,
        rider_audit=rider_audit,
        race_audit=race_audit,
        random_seed=random_seed,
    )
    report_text = _format_report(summary, team_audit, rider_audit, race_audit)
    return ManualSampleAuditArtifacts(
        summary=summary,
        team_audit=team_audit,
        rider_audit=rider_audit,
        race_audit=race_audit,
        report_text=report_text,
    )


def write_manual_sample_audit_artifacts(
    artifacts: ManualSampleAuditArtifacts,
    *,
    output_root: str | Path = DEFAULT_AUDIT_OUTPUT_ROOT,
    report_date: date | None = None,
) -> dict[str, Path]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    active_date = report_date or date.today()
    stem = f"manual_sample_audit_{active_date.isoformat()}"

    summary_path = root / f"{stem}_summary.json"
    summary_path.write_text(json.dumps(artifacts.summary, indent=2, sort_keys=True) + "\n")

    report_path = root / f"{stem}.md"
    report_path.write_text(artifacts.report_text)

    team_path = root / f"{stem}_team.csv"
    artifacts.team_audit.to_csv(team_path, index=False)

    rider_path = root / f"{stem}_rider.csv"
    artifacts.rider_audit.to_csv(rider_path, index=False)

    race_path = root / f"{stem}_race_ev.csv"
    artifacts.race_audit.to_csv(race_path, index=False)

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "team_path": team_path,
        "rider_path": rider_path,
        "race_path": race_path,
    }


def _run_team_sample_audit(
    *,
    team_panel: pd.DataFrame,
    imported_team: pd.DataFrame,
    upstream_team: pd.DataFrame,
    imported_rider: pd.DataFrame,
    next_top5_targets: pd.DataFrame,
    sample_size: int,
    random_seed: int,
) -> pd.DataFrame:
    working = team_panel.copy().reset_index(drop=True)
    sampled = _sample_with_segments(
        working,
        sample_size=sample_size,
        random_seed=random_seed,
        segments=(
            ("has_observed_next_season", 6),
            ("~has_observed_next_season", 4),
        ),
        sort_columns=("season", "team_name", "team_slug"),
    )

    rows: list[dict[str, object]] = []
    for _, sample in sampled.iterrows():
        season = int(sample["season"])
        team_slug = str(sample["team_slug"])
        imported_row = imported_team.loc[
            (pd.to_numeric(imported_team["season_year"], errors="coerce") == season)
            & (imported_team["team_slug"].astype(str) == team_slug)
        ]
        upstream_row = upstream_team.loc[
            (pd.to_numeric(upstream_team["season_year"], errors="coerce") == season)
            & (upstream_team["team_slug"].astype(str) == team_slug)
        ]
        riders = imported_rider.loc[
            (pd.to_numeric(imported_rider["season_year"], errors="coerce") == season)
            & (imported_rider["team_slug"].astype(str) == team_slug)
        ].copy()
        targets = next_top5_targets.loc[
            (pd.to_numeric(next_top5_targets["season"], errors="coerce") == season)
            & (next_top5_targets["prior_team_slug"].astype(str) == team_slug)
        ]

        row = {
            "season": season,
            "team_name": str(sample["team_name"]),
            "team_slug": team_slug,
            "team_panel_path": str(DEFAULT_TEAM_PANEL_PATH),
            "upstream_reference_path": str(
                _resolve_upstream_root(None) / get_historical_import_spec("historical_proteam_team_panel").source_path
            ),
            "imported_row_exists": not imported_row.empty,
            "upstream_row_exists": not upstream_row.empty,
        }
        row["import_matches_upstream_core"] = _compare_field_group(
            imported_row,
            upstream_row,
            [
                ("team_name", "team_name"),
                ("team_class", "team_class"),
                ("team_rank", "team_rank"),
                ("team_total_uci_points", "team_total_uci_points"),
                ("top1_share", "top1_share"),
                ("top3_share", "top3_share"),
                ("top5_share", "top5_share"),
                ("n_riders_100", "n_riders_100"),
                ("n_riders_150", "n_riders_150"),
                ("n_riders_250", "n_riders_250"),
                ("n_riders_400", "n_riders_400"),
            ],
        )
        row["panel_matches_imported_core"] = _compare_scalar_group(
            sample,
            imported_row,
            [
                ("team_name", "team_name"),
                ("team_class", "team_class"),
                ("proteam_rank", "team_rank"),
                ("team_points_total", "team_total_uci_points"),
                ("top1_share", "top1_share"),
                ("top3_share", "top3_share"),
                ("top5_share", "top5_share"),
                ("n_riders_100_plus", "n_riders_100"),
                ("n_riders_150_plus", "n_riders_150"),
                ("n_riders_250_plus", "n_riders_250"),
                ("n_riders_400_plus", "n_riders_400"),
            ],
        )
        row["team_points_match_rider_sum"] = _matches(
            sample["team_points_total"],
            pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0).sum(),
        )
        row["derived_50_match"] = _matches(
            sample["n_riders_50_plus"],
            (pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0) >= 50).sum(),
        )
        row["derived_100_match"] = _matches(
            sample["n_riders_100_plus"],
            (pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0) >= 100).sum(),
        )
        row["derived_150_match"] = _matches(
            sample["n_riders_150_plus"],
            (pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0) >= 150).sum(),
        )
        row["derived_250_match"] = _matches(
            sample["n_riders_250_plus"],
            (pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0) >= 250).sum(),
        )
        row["derived_300_match"] = _matches(
            sample["n_riders_300_plus"],
            (pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0) >= 300).sum(),
        )
        row["derived_400_match"] = _matches(
            sample["n_riders_400_plus"],
            (pd.to_numeric(riders["uci_points"], errors="coerce").fillna(0.0) >= 400).sum(),
        )
        if targets.empty:
            row["next_top5_label_match"] = bool(pd.isna(sample.get("next_top5_proteam")))
            row["next_team_slug_match"] = bool(pd.isna(sample.get("next_team_slug")))
        else:
            target_row = targets.iloc[0]
            row["next_top5_label_match"] = _matches(sample.get("next_top5_proteam"), target_row.get("next_top5_proteam"))
            row["next_team_slug_match"] = _matches(sample.get("next_team_slug"), target_row.get("next_team_slug"))
        row["all_checks_passed"] = all(
            bool(row[column])
            for column in (
                "imported_row_exists",
                "upstream_row_exists",
                "import_matches_upstream_core",
                "panel_matches_imported_core",
                "team_points_match_rider_sum",
                "derived_50_match",
                "derived_100_match",
                "derived_150_match",
                "derived_250_match",
                "derived_300_match",
                "derived_400_match",
                "next_top5_label_match",
                "next_team_slug_match",
            )
        )
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["season", "team_name"]).reset_index(drop=True)


def _run_rider_sample_audit(
    *,
    rider_panel: pd.DataFrame,
    imported_rider: pd.DataFrame,
    upstream_rider: pd.DataFrame,
    imported_result_summary: pd.DataFrame,
    upstream_result_summary: pd.DataFrame,
    imported_transfer: pd.DataFrame,
    upstream_transfer: pd.DataFrame,
    sample_size: int,
    random_seed: int,
) -> pd.DataFrame:
    working = rider_panel.copy().reset_index(drop=True)
    sampled = _sample_with_segments(
        working,
        sample_size=sample_size,
        random_seed=random_seed,
        segments=(
            ("result_summary_available", 10),
            ("transfer_context_available", 10),
            ("has_observed_next_season", 5),
        ),
        sort_columns=("season", "team_name", "team_rank_within_roster", "rider_name"),
    )

    rows: list[dict[str, object]] = []
    for _, sample in sampled.iterrows():
        season = int(sample["season"])
        rider_slug = str(sample["rider_slug"])
        team_slug = str(sample["team_slug"])
        imported_row = imported_rider.loc[
            (pd.to_numeric(imported_rider["season_year"], errors="coerce") == season)
            & (imported_rider["team_slug"].astype(str) == team_slug)
            & (imported_rider["rider_slug"].astype(str) == rider_slug)
        ] if {"season_year", "team_slug", "rider_slug"}.issubset(imported_rider.columns) else pd.DataFrame()
        upstream_row = upstream_rider.loc[
            (pd.to_numeric(upstream_rider["season_year"], errors="coerce") == season)
            & (upstream_rider["team_slug"].astype(str) == team_slug)
            & (upstream_rider["rider_slug"].astype(str) == rider_slug)
        ] if {"season_year", "team_slug", "rider_slug"}.issubset(upstream_rider.columns) else pd.DataFrame()
        summary_imported_row = imported_result_summary.loc[
            (pd.to_numeric(imported_result_summary["season_year"], errors="coerce") == season)
            & (imported_result_summary["team_slug"].astype(str) == team_slug)
            & (imported_result_summary["rider_slug"].astype(str) == rider_slug)
        ] if {"season_year", "team_slug", "rider_slug"}.issubset(imported_result_summary.columns) else pd.DataFrame()
        summary_upstream_row = upstream_result_summary.loc[
            (pd.to_numeric(upstream_result_summary["season_year"], errors="coerce") == season)
            & (upstream_result_summary["team_slug"].astype(str) == team_slug)
            & (upstream_result_summary["rider_slug"].astype(str) == rider_slug)
        ] if {"season_year", "team_slug", "rider_slug"}.issubset(upstream_result_summary.columns) else pd.DataFrame()
        transfer_imported_row = imported_transfer.loc[
            (pd.to_numeric(imported_transfer["year_to"], errors="coerce") == season)
            & (imported_transfer["team_to_slug"].astype(str) == team_slug)
            & (imported_transfer["rider_slug"].astype(str) == rider_slug)
        ] if {"year_to", "team_to_slug", "rider_slug"}.issubset(imported_transfer.columns) else pd.DataFrame()
        transfer_upstream_row = upstream_transfer.loc[
            (pd.to_numeric(upstream_transfer["year_to"], errors="coerce") == season)
            & (upstream_transfer["team_to_slug"].astype(str) == team_slug)
            & (upstream_transfer["rider_slug"].astype(str) == rider_slug)
        ] if {"year_to", "team_to_slug", "rider_slug"}.issubset(upstream_transfer.columns) else pd.DataFrame()

        next_row = rider_panel.loc[
            (pd.to_numeric(rider_panel["season"], errors="coerce") == int(sample["next_season"]))
            & (rider_panel["rider_slug"].astype(str) == rider_slug)
        ]

        row = {
            "season": season,
            "rider_name": str(sample["rider_name"]),
            "rider_slug": rider_slug,
            "team_name": str(sample["team_name"]),
            "team_slug": team_slug,
            "source_points_url": _first_value(imported_row, "source_points_url"),
            "source_racedays_url": _first_value(imported_row, "source_racedays_url"),
            "imported_row_exists": not imported_row.empty,
            "upstream_row_exists": not upstream_row.empty,
            "import_matches_upstream_core": _compare_field_group(
                imported_row,
                upstream_row,
                [
                    ("rider_name", "rider_name"),
                    ("team_name", "team_name"),
                    ("team_class", "team_class"),
                    ("uci_points", "uci_points"),
                    ("pcs_points", "pcs_points"),
                    ("racedays", "racedays"),
                    ("team_rank_within_roster", "team_rank_within_roster"),
                    ("team_points_share", "team_points_share"),
                    ("archetype", "archetype"),
                ],
            ),
            "panel_matches_imported_core": _compare_scalar_group(
                sample,
                imported_row,
                [
                    ("rider_name", "rider_name"),
                    ("team_name", "team_name"),
                    ("team_class", "team_class"),
                    ("uci_points", "uci_points"),
                    ("pcs_points", "pcs_points"),
                    ("racedays", "racedays"),
                    ("team_rank_within_roster", "team_rank_within_roster"),
                    ("team_points_share", "team_points_share"),
                    ("archetype", "archetype"),
                ],
            ),
        }

        if _as_bool(sample.get("result_summary_available")):
            row["result_summary_import_exists"] = not summary_imported_row.empty
            row["result_summary_upstream_exists"] = not summary_upstream_row.empty
            row["result_summary_import_matches_upstream"] = _compare_field_group(
                summary_imported_row,
                summary_upstream_row,
                [
                    ("total_uci_points_detailed", "total_uci_points_detailed"),
                    ("uci_point_diff_vs_panel", "uci_point_diff_vs_panel"),
                    ("points_match_within_1", "points_match_within_1"),
                    ("n_starts", "n_starts"),
                    ("n_scoring_results", "n_scoring_results"),
                    ("uci_points_from_gc", "uci_points_from_gc"),
                    ("uci_points_from_one_day", "uci_points_from_one_day"),
                ],
            )
            row["panel_matches_result_summary"] = _compare_scalar_group(
                sample,
                summary_imported_row,
                [
                    ("total_uci_points_detailed", "total_uci_points_detailed"),
                    ("uci_point_diff_vs_panel", "uci_point_diff_vs_panel"),
                    ("points_match_within_1", "points_match_within_1"),
                    ("n_starts", "n_starts"),
                    ("n_scoring_results", "n_scoring_results"),
                    ("uci_points_from_gc", "uci_points_from_gc"),
                    ("uci_points_from_one_day", "uci_points_from_one_day"),
                ],
            )
        else:
            row["result_summary_import_exists"] = True
            row["result_summary_upstream_exists"] = True
            row["result_summary_import_matches_upstream"] = True
            row["panel_matches_result_summary"] = True

        if _as_bool(sample.get("transfer_context_available")):
            row["transfer_import_exists"] = not transfer_imported_row.empty
            row["transfer_upstream_exists"] = not transfer_upstream_row.empty
            row["transfer_import_matches_upstream"] = _compare_field_group(
                transfer_imported_row,
                transfer_upstream_row,
                [
                    ("age_on_jan_1", "age_on_jan_1"),
                    ("specialty_primary", "specialty_primary"),
                    ("transfer_step_label", "transfer_step_label"),
                    ("prior_year_uci_points", "prior_year_uci_points"),
                    ("prior_year_n_starts", "prior_year_n_starts"),
                    ("prior_year_scored_150_flag", "prior_year_scored_150_flag"),
                ],
            )
            row["panel_matches_transfer_context"] = _compare_scalar_group(
                sample,
                transfer_imported_row,
                [
                    ("age_on_jan_1", "age_on_jan_1"),
                    ("specialty_primary", "specialty_primary"),
                    ("transfer_step_label", "transfer_step_label"),
                    ("prior_year_uci_points", "prior_year_uci_points"),
                    ("prior_year_n_starts", "prior_year_n_starts"),
                    ("prior_year_scored_150_flag", "prior_year_scored_150_flag"),
                ],
            )
        else:
            row["transfer_import_exists"] = True
            row["transfer_upstream_exists"] = True
            row["transfer_import_matches_upstream"] = True
            row["panel_matches_transfer_context"] = True

        if _as_bool(sample.get("has_observed_next_season")):
            row["next_season_row_exists"] = not next_row.empty
            if not next_row.empty:
                next_panel_row = next_row.iloc[0]
                row["next_season_mapping_match"] = all(
                    _matches(sample[column_name], next_panel_row[next_column_name])
                    for column_name, next_column_name in (
                        ("next_team_slug", "team_slug"),
                        ("next_uci_points", "uci_points"),
                        ("next_racedays", "racedays"),
                        ("next_team_rank_within_roster", "team_rank_within_roster"),
                    )
                )
            else:
                row["next_season_mapping_match"] = False
        else:
            row["next_season_row_exists"] = True
            row["next_season_mapping_match"] = True

        row["all_checks_passed"] = all(
            bool(row[column])
            for column in (
                "imported_row_exists",
                "upstream_row_exists",
                "import_matches_upstream_core",
                "panel_matches_imported_core",
                "result_summary_import_exists",
                "result_summary_upstream_exists",
                "result_summary_import_matches_upstream",
                "panel_matches_result_summary",
                "transfer_import_exists",
                "transfer_upstream_exists",
                "transfer_import_matches_upstream",
                "panel_matches_transfer_context",
                "next_season_row_exists",
                "next_season_mapping_match",
            )
        )
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["season", "team_name", "rider_name"]).reset_index(drop=True)


def _run_race_sample_audit(
    *,
    team_ev_root: Path,
    team_calendar_root: Path,
    team_results_root: Path,
    sample_size: int,
    random_seed: int,
) -> pd.DataFrame:
    race_frames: list[pd.DataFrame] = []
    for path in sorted(team_ev_root.glob("*_calendar_ev.csv")):
        df = pd.read_csv(path, low_memory=False)
        if df.empty:
            continue
        df["team_ev_path"] = str(path)
        df["artifact_stem"] = path.name.replace("_calendar_ev.csv", "")
        race_frames.append(df)
    if not race_frames:
        return pd.DataFrame()

    combined = pd.concat(race_frames, ignore_index=True)
    sampled = _sample_with_segments(
        combined,
        sample_size=sample_size,
        random_seed=random_seed,
        segments=(
            ("actual_points.notna()", 6),
            ("actual_points.isna()", 4),
        ),
        sort_columns=("team_slug", "planning_year", "start_date", "race_name"),
    )

    rows: list[dict[str, object]] = []
    for _, sample in sampled.iterrows():
        artifact_stem = str(sample["artifact_stem"])
        calendar_path = team_calendar_root / f"{artifact_stem}_latest.csv"
        actual_points_path = team_results_root / f"{artifact_stem}_actual_points.csv"
        calendar_df = pd.read_csv(calendar_path, low_memory=False) if calendar_path.exists() else pd.DataFrame()
        actual_df = pd.read_csv(actual_points_path, low_memory=False) if actual_points_path.exists() else pd.DataFrame()

        race_id = pd.to_numeric(sample["race_id"], errors="coerce")
        calendar_row = calendar_df.loc[pd.to_numeric(calendar_df.get("race_id"), errors="coerce") == race_id]
        actual_row = actual_df.loc[pd.to_numeric(actual_df.get("race_id"), errors="coerce") == race_id]

        recomputed_expected = (
            _coerce_scalar(sample.get("base_opportunity_points"))
            * _coerce_scalar(sample.get("team_fit_multiplier"))
            * _coerce_scalar(sample.get("participation_confidence"))
            * _coerce_scalar(sample.get("execution_multiplier"))
        )
        actual_points = pd.to_numeric(sample.get("actual_points"), errors="coerce")
        recomputed_gap = None if pd.isna(actual_points) else float(actual_points) - recomputed_expected

        row = {
            "team_slug": str(sample["team_slug"]),
            "team_name": str(sample["team_name"]),
            "planning_year": int(pd.to_numeric(sample["planning_year"], errors="coerce")),
            "race_id": int(race_id) if pd.notna(race_id) else "",
            "race_name": str(sample["race_name"]),
            "category": str(sample["category"]),
            "start_date": str(sample["start_date"]),
            "status": str(sample["status"]),
            "team_ev_path": str(sample["team_ev_path"]),
            "team_calendar_path": str(calendar_path),
            "actual_points_path": str(actual_points_path),
            "team_calendar_row_exists": not calendar_row.empty,
            "actual_points_row_exists_or_missing_ok": (not actual_row.empty) or pd.isna(actual_points),
            "expected_points_formula_match": _matches(sample.get("expected_points"), recomputed_expected, tolerance=1e-5),
            "ev_gap_formula_match": True if recomputed_gap is None else _matches(sample.get("ev_gap"), recomputed_gap, tolerance=1e-5),
            "calendar_status_match": _matches(sample.get("status"), _first_value(calendar_row, "status")),
            "calendar_slug_match": _matches(sample.get("pcs_race_slug"), _first_value(calendar_row, "pcs_race_slug")),
            "actual_points_match": True if actual_row.empty and pd.isna(actual_points) else _matches(
                sample.get("actual_points"),
                _first_value(actual_row, "actual_points"),
            ),
            "actual_status_match": True if actual_row.empty and pd.isna(actual_points) else _matches(
                sample.get("status"),
                _first_value(actual_row, "status"),
            ),
            "actual_source_url": _first_value(actual_row, "source_url"),
            "calendar_source_url": _first_value(calendar_row, "source_url"),
        }
        row["all_checks_passed"] = all(
            bool(row[column])
            for column in (
                "team_calendar_row_exists",
                "actual_points_row_exists_or_missing_ok",
                "expected_points_formula_match",
                "ev_gap_formula_match",
                "calendar_status_match",
                "calendar_slug_match",
                "actual_points_match",
                "actual_status_match",
            )
        )
        rows.append(row)

    return pd.DataFrame(rows).sort_values(["team_slug", "start_date", "race_name"]).reset_index(drop=True)


def _build_summary(
    *,
    resolved_upstream_root: Path,
    team_audit: pd.DataFrame,
    rider_audit: pd.DataFrame,
    race_audit: pd.DataFrame,
    random_seed: int,
) -> dict[str, object]:
    return {
        "artifact_version": "manual_sample_audit_v1",
        "audit_date": date.today().isoformat(),
        "random_seed": int(random_seed),
        "upstream_root": str(resolved_upstream_root),
        "team_audit": _audit_summary(team_audit),
        "rider_audit": _audit_summary(rider_audit),
        "race_audit": _audit_summary(race_audit),
        "all_checks_passed": bool(
            _audit_summary(team_audit)["all_checks_passed"]
            and _audit_summary(rider_audit)["all_checks_passed"]
            and _audit_summary(race_audit)["all_checks_passed"]
        ),
    }


def _audit_summary(audit_df: pd.DataFrame) -> dict[str, object]:
    if audit_df.empty:
        return {
            "sample_rows": 0,
            "passed_rows": 0,
            "failed_rows": 0,
            "all_checks_passed": False,
        }
    passed_rows = int(audit_df["all_checks_passed"].fillna(False).astype(bool).sum())
    sample_rows = int(len(audit_df))
    return {
        "sample_rows": sample_rows,
        "passed_rows": passed_rows,
        "failed_rows": int(sample_rows - passed_rows),
        "all_checks_passed": bool(passed_rows == sample_rows),
    }


def _format_report(
    summary: dict[str, object],
    team_audit: pd.DataFrame,
    rider_audit: pd.DataFrame,
    race_audit: pd.DataFrame,
) -> str:
    lines = [
        "# Manual Sample Audit Report",
        "",
        f"- Audit date: `{summary['audit_date']}`",
        f"- Random seed: `{summary['random_seed']}`",
        f"- Upstream root: `{summary['upstream_root']}`",
        f"- Overall pass: `{summary['all_checks_passed']}`",
        "",
        "## Summary",
        "",
        f"- Team sample audit: `{summary['team_audit']['passed_rows']}/{summary['team_audit']['sample_rows']}` passed",
        f"- Rider sample audit: `{summary['rider_audit']['passed_rows']}/{summary['rider_audit']['sample_rows']}` passed",
        f"- Race EV sample audit: `{summary['race_audit']['passed_rows']}/{summary['race_audit']['sample_rows']}` passed",
        "",
    ]

    lines.extend(_format_failure_section("Team sample audit", team_audit, ["season", "team_name", "team_slug"]))
    lines.extend(_format_failure_section("Rider sample audit", rider_audit, ["season", "rider_name", "team_name"]))
    lines.extend(_format_failure_section("Race EV sample audit", race_audit, ["team_slug", "race_name", "start_date"]))
    return "\n".join(lines).rstrip() + "\n"


def _format_failure_section(title: str, audit_df: pd.DataFrame, identity_columns: list[str]) -> list[str]:
    lines = [f"## {title}", ""]
    if audit_df.empty:
        lines.append("- No sampled rows were available.")
        lines.append("")
        return lines

    failed = audit_df.loc[~audit_df["all_checks_passed"].astype(bool)].copy()
    if failed.empty:
        lines.append("- All sampled rows passed.")
        lines.append("")
        return lines

    lines.append(f"- Failed sampled rows: `{len(failed)}`")
    for _, row in failed.iterrows():
        identity = ", ".join(f"{column}={row[column]}" for column in identity_columns if column in row.index)
        failing_checks = [
            column
            for column in audit_df.columns
            if column.endswith("_match")
            or column.endswith("_exists")
            or column.endswith("_passed")
            or column.endswith("_ok")
        ]
        failed_columns = [column for column in failing_checks if not bool(row.get(column))]
        lines.append(f"- `{identity}` failed: {', '.join(failed_columns)}")
    lines.append("")
    return lines


def _resolve_upstream_root(upstream_root: str | Path | None) -> Path:
    if upstream_root is not None:
        resolved = Path(upstream_root).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Upstream root does not exist: {resolved}")
        return resolved
    for candidate in DEFAULT_SOURCE_ROOT_CANDIDATES:
        resolved = Path(candidate).expanduser().resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError("Could not resolve upstream `procycling-clean-scraped-data` checkout.")


def _load_upstream_dataset(dataset_key: str, upstream_root: Path) -> pd.DataFrame:
    spec = get_historical_import_spec(dataset_key)
    path = upstream_root / spec.source_path
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, compression="infer", low_memory=False)


def _sample_with_segments(
    dataset: pd.DataFrame,
    *,
    sample_size: int,
    random_seed: int,
    segments: tuple[tuple[str, int], ...],
    sort_columns: tuple[str, ...],
) -> pd.DataFrame:
    if dataset.empty:
        return dataset.copy()

    working = dataset.copy().reset_index(drop=True)
    working["_sample_row_id"] = range(len(working))
    chosen_ids: list[int] = []

    for offset, (expression, target_count) in enumerate(segments):
        available = working.loc[~working["_sample_row_id"].isin(chosen_ids)].copy()
        if available.empty or target_count <= 0:
            continue
        mask = _evaluate_segment_expression(available, expression)
        subset = available.loc[mask].copy()
        if subset.empty:
            continue
        take = min(int(target_count), len(subset))
        sampled_subset = subset.sort_values(list(sort_columns)).sample(
            n=take,
            random_state=random_seed + offset,
        )
        chosen_ids.extend(sampled_subset["_sample_row_id"].tolist())

    if len(chosen_ids) < sample_size:
        available = working.loc[~working["_sample_row_id"].isin(chosen_ids)].copy()
        if not available.empty:
            take = min(int(sample_size - len(chosen_ids)), len(available))
            filler = available.sort_values(list(sort_columns)).sample(
                n=take,
                random_state=random_seed + len(segments) + 1,
            )
            chosen_ids.extend(filler["_sample_row_id"].tolist())

    sampled = working.loc[working["_sample_row_id"].isin(chosen_ids)].copy()
    sampled = sampled.drop(columns=["_sample_row_id"])
    return sampled.sort_values(list(sort_columns)).reset_index(drop=True)


def _evaluate_segment_expression(dataset: pd.DataFrame, expression: str) -> pd.Series:
    if expression.startswith("~"):
        return ~_evaluate_segment_expression(dataset, expression[1:])
    if expression.endswith(".notna()"):
        column_name = expression[:-8]
        return dataset[column_name].notna()
    if expression.endswith(".isna()"):
        column_name = expression[:-7]
        return dataset[column_name].isna()
    return dataset[expression].map(_as_bool)


def _compare_field_group(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    field_pairs: list[tuple[str, str]],
) -> bool:
    if left_df.empty or right_df.empty:
        return False
    left_row = left_df.iloc[0]
    right_row = right_df.iloc[0]
    return all(_matches(left_row[left_name], right_row[right_name]) for left_name, right_name in field_pairs)


def _compare_scalar_group(
    scalar_row: pd.Series,
    comparison_df: pd.DataFrame,
    field_pairs: list[tuple[str, str]],
) -> bool:
    if comparison_df.empty:
        return False
    comparison_row = comparison_df.iloc[0]
    return all(_matches(scalar_row[left_name], comparison_row[right_name]) for left_name, right_name in field_pairs)


def _matches(left_value: object, right_value: object, *, tolerance: float = FLOAT_TOLERANCE) -> bool:
    if pd.isna(left_value) and pd.isna(right_value):
        return True
    left_numeric = pd.to_numeric(left_value, errors="coerce")
    right_numeric = pd.to_numeric(right_value, errors="coerce")
    if not pd.isna(left_numeric) and not pd.isna(right_numeric):
        return abs(float(left_numeric) - float(right_numeric)) <= float(tolerance)
    return str(left_value).strip() == str(right_value).strip()


def _first_value(dataset: pd.DataFrame, column_name: str) -> object:
    if dataset.empty or column_name not in dataset.columns:
        return ""
    return dataset.iloc[0][column_name]


def _coerce_scalar(value: object) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return 0.0
    return float(numeric)


def _as_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return bool(value)
