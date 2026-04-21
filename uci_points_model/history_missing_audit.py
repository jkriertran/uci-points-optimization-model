from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEAM_EV_ROOT = PROJECT_ROOT / "data" / "team_ev"
DEFAULT_AUDIT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "audits"

TEAM_EV_FILE_GLOB = "*_calendar_ev.csv"
HISTORY_MISSING_TOKEN = "history_missing"
HISTORY_FALLBACK_PATTERN = re.compile(r"history_fallback_from=([^|]+)")
MATCHED_VIA_PATTERN = re.compile(r"matched_via=([^|]+)")


@dataclass(frozen=True, slots=True)
class HistoryMissingAuditArtifacts:
    summary: dict[str, object]
    team_summary: pd.DataFrame
    race_details: pd.DataFrame
    report_text: str


def run_history_missing_race_audit(
    *,
    team_ev_root: str | Path = DEFAULT_TEAM_EV_ROOT,
) -> HistoryMissingAuditArtifacts:
    root = Path(team_ev_root)
    detail_frames: list[pd.DataFrame] = []
    scanned_team_files = 0

    for path in sorted(root.glob(TEAM_EV_FILE_GLOB)):
        scanned_team_files += 1
        team_frame = pd.read_csv(path, low_memory=False)
        prepared = _prepare_team_history_missing_frame(team_frame, source_path=path)
        if not prepared.empty:
            detail_frames.append(prepared)

    race_details = (
        pd.concat(detail_frames, ignore_index=True)
        if detail_frames
        else pd.DataFrame(columns=_detail_columns())
    )
    team_summary = _build_team_summary(race_details)
    summary = _build_summary(
        race_details=race_details,
        team_summary=team_summary,
        team_ev_root=root,
        scanned_team_files=scanned_team_files,
    )
    report_text = _format_report(summary, team_summary, race_details)
    return HistoryMissingAuditArtifacts(
        summary=summary,
        team_summary=team_summary,
        race_details=race_details,
        report_text=report_text,
    )


def write_history_missing_audit_artifacts(
    artifacts: HistoryMissingAuditArtifacts,
    *,
    output_root: str | Path = DEFAULT_AUDIT_OUTPUT_ROOT,
    report_date: date | None = None,
) -> dict[str, Path]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    active_date = report_date or date.today()
    stem = f"history_missing_race_audit_{active_date.isoformat()}"

    summary_path = root / f"{stem}_summary.json"
    summary_path.write_text(json.dumps(artifacts.summary, indent=2, sort_keys=True) + "\n")

    report_path = root / f"{stem}.md"
    report_path.write_text(artifacts.report_text)

    team_summary_path = root / f"{stem}_team_summary.csv"
    artifacts.team_summary.to_csv(team_summary_path, index=False)

    race_details_path = root / f"{stem}_race_details.csv"
    artifacts.race_details.to_csv(race_details_path, index=False)

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "team_summary_path": team_summary_path,
        "race_details_path": race_details_path,
    }


def _prepare_team_history_missing_frame(team_frame: pd.DataFrame, *, source_path: Path) -> pd.DataFrame:
    if team_frame.empty:
        return pd.DataFrame(columns=_detail_columns())

    working = team_frame.copy()
    for column in (
        "team_slug",
        "team_name",
        "planning_year",
        "race_name",
        "category",
        "start_date",
        "status",
        "notes",
    ):
        if column not in working.columns:
            working[column] = pd.NA

    for column in (
        "historical_years_analyzed",
        "avg_top10_points",
        "base_opportunity_points",
        "team_fit_multiplier",
        "participation_confidence",
        "execution_multiplier",
        "expected_points",
        "actual_points",
        "ev_gap",
    ):
        working[column] = pd.to_numeric(working.get(column), errors="coerce")

    working["notes"] = working["notes"].fillna("").astype(str)
    history_missing_mask = working["notes"].str.contains(HISTORY_MISSING_TOKEN, case=False, na=False)
    if not history_missing_mask.any():
        return pd.DataFrame(columns=_detail_columns())

    filtered = working.loc[history_missing_mask].copy()
    filtered["source_path"] = str(source_path)
    filtered["matched_via"] = filtered["notes"].map(_extract_matched_via)
    filtered["history_fallback_from"] = filtered["notes"].map(_extract_history_fallback_from)
    filtered["history_fallback_flag"] = filtered["history_fallback_from"].notna()
    filtered["zero_expected_points_flag"] = filtered["expected_points"].fillna(0.0).eq(0.0)
    filtered["positive_actual_points_flag"] = filtered["actual_points"].fillna(0.0).gt(0.0)
    filtered["missing_historical_anchor_flag"] = (
        filtered["historical_years_analyzed"].isna() | filtered["base_opportunity_points"].isna()
    )
    filtered["missing_completed_ev_components_flag"] = (
        filtered["status"].astype(str).eq("completed")
        & (
            filtered["expected_points"].isna()
            | filtered["base_opportunity_points"].isna()
            | filtered["team_fit_multiplier"].isna()
            | filtered["participation_confidence"].isna()
            | filtered["execution_multiplier"].isna()
        )
    )

    available_columns = [column for column in _detail_columns() if column in filtered.columns]
    return filtered[available_columns].sort_values(
        ["team_name", "planning_year", "start_date", "race_name"],
        na_position="last",
    ).reset_index(drop=True)


def _build_team_summary(race_details: pd.DataFrame) -> pd.DataFrame:
    if race_details.empty:
        return pd.DataFrame(columns=_team_summary_columns())

    rows: list[dict[str, object]] = []
    group_columns = ["team_slug", "team_name", "planning_year"]
    for (team_slug, team_name, planning_year), group in race_details.groupby(group_columns, sort=False):
        status = group["status"].fillna("").astype(str)
        row = {
            "team_slug": str(team_slug),
            "team_name": str(team_name),
            "planning_year": int(pd.to_numeric(planning_year, errors="coerce")),
            "history_missing_races": int(len(group)),
            "completed_history_missing_races": int(status.eq("completed").sum()),
            "scheduled_history_missing_races": int(status.eq("scheduled").sum()),
            "cancelled_history_missing_races": int(status.eq("cancelled").sum()),
            "history_missing_with_fallback": int(group["history_fallback_flag"].fillna(False).sum()),
            "history_missing_with_zero_expected": int(group["zero_expected_points_flag"].fillna(False).sum()),
            "history_missing_with_positive_actual_points": int(group["positive_actual_points_flag"].fillna(False).sum()),
            "completed_missing_ev_components": int(group["missing_completed_ev_components_flag"].fillna(False).sum()),
            "actual_points_scored_in_history_missing_races": round(float(group["actual_points"].fillna(0.0).sum()), 6),
            "expected_points_in_history_missing_races": round(float(group["expected_points"].fillna(0.0).sum()), 6),
            "ev_gap_sum_in_history_missing_races": round(float(group["ev_gap"].fillna(0.0).sum()), 6),
            "earliest_history_missing_race_date": str(group["start_date"].dropna().astype(str).min() or ""),
            "latest_history_missing_race_date": str(group["start_date"].dropna().astype(str).max() or ""),
        }
        rows.append(row)

    summary = pd.DataFrame(rows)
    return summary.sort_values(
        [
            "history_missing_races",
            "completed_missing_ev_components",
            "actual_points_scored_in_history_missing_races",
            "team_name",
        ],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)


def _build_summary(
    *,
    race_details: pd.DataFrame,
    team_summary: pd.DataFrame,
    team_ev_root: Path,
    scanned_team_files: int,
) -> dict[str, object]:
    return {
        "audit_date": date.today().isoformat(),
        "team_ev_root": str(team_ev_root),
        "scanned_team_files": int(scanned_team_files),
        "teams_with_history_missing": int(len(team_summary)),
        "total_history_missing_races": int(len(race_details)),
        "completed_history_missing_races": int(
            race_details.get("status", pd.Series(dtype=object)).fillna("").astype(str).eq("completed").sum()
        ),
        "scheduled_history_missing_races": int(
            race_details.get("status", pd.Series(dtype=object)).fillna("").astype(str).eq("scheduled").sum()
        ),
        "cancelled_history_missing_races": int(
            race_details.get("status", pd.Series(dtype=object)).fillna("").astype(str).eq("cancelled").sum()
        ),
        "history_missing_with_fallback": int(race_details.get("history_fallback_flag", pd.Series(dtype=bool)).fillna(False).sum()),
        "history_missing_with_zero_expected": int(race_details.get("zero_expected_points_flag", pd.Series(dtype=bool)).fillna(False).sum()),
        "history_missing_with_positive_actual_points": int(
            race_details.get("positive_actual_points_flag", pd.Series(dtype=bool)).fillna(False).sum()
        ),
        "completed_missing_ev_components": int(
            race_details.get("missing_completed_ev_components_flag", pd.Series(dtype=bool)).fillna(False).sum()
        ),
        "actual_points_scored_in_history_missing_races": round(
            float(pd.to_numeric(race_details.get("actual_points"), errors="coerce").fillna(0.0).sum()),
            6,
        ),
        "expected_points_in_history_missing_races": round(
            float(pd.to_numeric(race_details.get("expected_points"), errors="coerce").fillna(0.0).sum()),
            6,
        ),
        "ev_gap_sum_in_history_missing_races": round(
            float(pd.to_numeric(race_details.get("ev_gap"), errors="coerce").fillna(0.0).sum()),
            6,
        ),
    }


def _format_report(
    summary: dict[str, object],
    team_summary: pd.DataFrame,
    race_details: pd.DataFrame,
) -> str:
    lines = [
        "# History-Missing Race Audit",
        "",
        f"Audit date: `{summary['audit_date']}`",
        f"Team EV root: `{summary['team_ev_root']}`",
        "",
        "## Overview",
        "",
        f"- Team EV files scanned: `{summary['scanned_team_files']}`",
        f"- Teams with at least one `history_missing` race: `{summary['teams_with_history_missing']}`",
        f"- Total races marked `history_missing`: `{summary['total_history_missing_races']}`",
        f"- Completed `history_missing` races: `{summary['completed_history_missing_races']}`",
        f"- Scheduled `history_missing` races: `{summary['scheduled_history_missing_races']}`",
        f"- `history_missing` races with category/history fallback: `{summary['history_missing_with_fallback']}`",
        f"- `history_missing` races with zero expected points: `{summary['history_missing_with_zero_expected']}`",
        f"- Completed races missing EV components by the app warning rule: `{summary['completed_missing_ev_components']}`",
        f"- Actual points scored in `history_missing` races: `{summary['actual_points_scored_in_history_missing_races']}`",
        "",
        "## Team Summary",
        "",
    ]

    if team_summary.empty:
        lines.append("No races are currently marked `history_missing` in the saved Team Calendar EV files.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(
        _markdown_table(
            team_summary[
                [
                    "team_name",
                    "planning_year",
                    "history_missing_races",
                    "completed_history_missing_races",
                    "history_missing_with_fallback",
                    "history_missing_with_zero_expected",
                    "completed_missing_ev_components",
                    "actual_points_scored_in_history_missing_races",
                ]
            ]
        )
    )
    lines.extend(["", "## Race Details", ""])

    for _, team_row in team_summary.iterrows():
        team_name = str(team_row["team_name"])
        planning_year = int(team_row["planning_year"])
        lines.append(f"### {team_name} ({planning_year})")
        lines.append("")
        lines.append(
            f"- `history_missing` races: `{int(team_row['history_missing_races'])}` | "
            f"completed: `{int(team_row['completed_history_missing_races'])}` | "
            f"fallback: `{int(team_row['history_missing_with_fallback'])}` | "
            f"zero expected: `{int(team_row['history_missing_with_zero_expected'])}`"
        )
        lines.append("")
        team_detail = race_details.loc[
            (race_details["team_name"].astype(str) == team_name)
            & (pd.to_numeric(race_details["planning_year"], errors="coerce") == planning_year)
        ].copy()
        lines.extend(
            _markdown_table(
                team_detail[
                    [
                        "start_date",
                        "race_name",
                        "status",
                        "expected_points",
                        "actual_points",
                        "ev_gap",
                        "history_fallback_from",
                        "missing_completed_ev_components_flag",
                        "notes",
                    ]
                ]
            )
        )
        lines.append("")

    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return ["No rows."]
    prepared = frame.copy()
    for column in prepared.columns:
        if pd.api.types.is_float_dtype(prepared[column]):
            prepared[column] = prepared[column].map(lambda value: "" if pd.isna(value) else f"{float(value):.3f}".rstrip("0").rstrip("."))
        else:
            prepared[column] = prepared[column].fillna("").astype(str)
    headers = [str(column) for column in prepared.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in prepared.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in prepared.columns) + " |")
    return lines


def _extract_history_fallback_from(notes: str) -> str | None:
    match = HISTORY_FALLBACK_PATTERN.search(str(notes))
    if not match:
        return None
    return match.group(1).strip()


def _extract_matched_via(notes: str) -> str | None:
    match = MATCHED_VIA_PATTERN.search(str(notes))
    if not match:
        return None
    return match.group(1).strip()


def _detail_columns() -> list[str]:
    return [
        "team_slug",
        "team_name",
        "planning_year",
        "race_name",
        "category",
        "start_date",
        "status",
        "historical_years_analyzed",
        "avg_top10_points",
        "base_opportunity_points",
        "team_fit_multiplier",
        "participation_confidence",
        "execution_multiplier",
        "expected_points",
        "actual_points",
        "ev_gap",
        "matched_via",
        "history_fallback_from",
        "history_fallback_flag",
        "zero_expected_points_flag",
        "positive_actual_points_flag",
        "missing_historical_anchor_flag",
        "missing_completed_ev_components_flag",
        "notes",
        "source_path",
    ]


def _team_summary_columns() -> list[str]:
    return [
        "team_slug",
        "team_name",
        "planning_year",
        "history_missing_races",
        "completed_history_missing_races",
        "scheduled_history_missing_races",
        "cancelled_history_missing_races",
        "history_missing_with_fallback",
        "history_missing_with_zero_expected",
        "history_missing_with_positive_actual_points",
        "completed_missing_ev_components",
        "actual_points_scored_in_history_missing_races",
        "expected_points_in_history_missing_races",
        "ev_gap_sum_in_history_missing_races",
        "earliest_history_missing_race_date",
        "latest_history_missing_race_date",
    ]
