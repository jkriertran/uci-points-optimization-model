from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .history_missing_audit import (
    DEFAULT_AUDIT_OUTPUT_ROOT,
    DEFAULT_TEAM_EV_ROOT,
    HistoryMissingAuditArtifacts,
    run_history_missing_race_audit,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class HistoryMissingBackfillArtifacts:
    summary: dict[str, object]
    priority_list: pd.DataFrame
    source_race_details: pd.DataFrame
    report_text: str


def build_history_missing_backfill_priority_list(
    *,
    team_ev_root: str | Path = DEFAULT_TEAM_EV_ROOT,
) -> HistoryMissingBackfillArtifacts:
    audit = run_history_missing_race_audit(team_ev_root=team_ev_root)
    race_details = audit.race_details.copy()
    no_fallback_completed = race_details.loc[
        race_details.get("missing_completed_ev_components_flag", pd.Series(False, index=race_details.index)).fillna(False)
    ].copy()

    priority_list = _build_priority_list(no_fallback_completed)
    summary = _build_summary(priority_list=priority_list, race_details=no_fallback_completed, audit=audit)
    report_text = _format_report(summary, priority_list)
    return HistoryMissingBackfillArtifacts(
        summary=summary,
        priority_list=priority_list,
        source_race_details=no_fallback_completed,
        report_text=report_text,
    )


def write_history_missing_backfill_artifacts(
    artifacts: HistoryMissingBackfillArtifacts,
    *,
    output_root: str | Path = DEFAULT_AUDIT_OUTPUT_ROOT,
    report_date: date | None = None,
) -> dict[str, Path]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    active_date = report_date or date.today()
    stem = f"history_missing_backfill_priority_{active_date.isoformat()}"

    summary_path = root / f"{stem}_summary.json"
    summary_path.write_text(json.dumps(artifacts.summary, indent=2, sort_keys=True) + "\n")

    report_path = root / f"{stem}.md"
    report_path.write_text(artifacts.report_text)

    priority_path = root / f"{stem}.csv"
    artifacts.priority_list.to_csv(priority_path, index=False)

    detail_path = root / f"{stem}_source_rows.csv"
    artifacts.source_race_details.to_csv(detail_path, index=False)

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "priority_path": priority_path,
        "detail_path": detail_path,
    }


def _build_priority_list(no_fallback_completed: pd.DataFrame) -> pd.DataFrame:
    if no_fallback_completed.empty:
        return pd.DataFrame(columns=_priority_columns())

    grouped = (
        no_fallback_completed.groupby(["race_name", "category"], dropna=False)
        .agg(
            affected_rows=("race_name", "size"),
            affected_teams=("team_name", "nunique"),
            total_actual_points=("actual_points", lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0.0).sum())),
            teams=("team_name", lambda s: " | ".join(sorted(set(str(value) for value in s.dropna())))),
            matched_via=("matched_via", lambda s: " | ".join(sorted(set(str(value) for value in s.dropna())))),
            first_seen_date=("start_date", lambda s: min(str(value) for value in s.dropna()) if s.dropna().any() else ""),
            last_seen_date=("start_date", lambda s: max(str(value) for value in s.dropna()) if s.dropna().any() else ""),
        )
        .reset_index()
    )

    grouped["likely_issue"] = grouped.apply(_likely_issue, axis=1)
    grouped["recommended_action"] = grouped.apply(_recommended_action, axis=1)
    grouped["priority_score"] = grouped.apply(_priority_score, axis=1)
    grouped["priority_tier"] = grouped.apply(_priority_tier, axis=1)

    grouped = grouped.sort_values(
        ["priority_score", "affected_teams", "total_actual_points", "race_name"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    grouped["priority_rank"] = range(1, len(grouped) + 1)

    available_columns = [column for column in _priority_columns() if column in grouped.columns]
    return grouped[available_columns]


def _priority_score(row: pd.Series) -> float:
    affected_teams = float(pd.to_numeric(row.get("affected_teams"), errors="coerce") or 0.0)
    affected_rows = float(pd.to_numeric(row.get("affected_rows"), errors="coerce") or 0.0)
    total_actual_points = float(pd.to_numeric(row.get("total_actual_points"), errors="coerce") or 0.0)
    matched_via = str(row.get("matched_via") or "")

    score = affected_teams * 100.0 + affected_rows * 20.0 + total_actual_points
    if "token_overlap" in matched_via:
        score += 15.0
    if total_actual_points == 0.0:
        score -= 20.0
    return round(score, 3)


def _priority_tier(row: pd.Series) -> str:
    affected_teams = int(pd.to_numeric(row.get("affected_teams"), errors="coerce") or 0)
    total_actual_points = float(pd.to_numeric(row.get("total_actual_points"), errors="coerce") or 0.0)

    if affected_teams >= 3:
        return "P1"
    if affected_teams >= 2 and total_actual_points >= 40.0:
        return "P1"
    if affected_teams >= 2 or total_actual_points >= 40.0:
        return "P2"
    return "P3"


def _likely_issue(row: pd.Series) -> str:
    matched_via = str(row.get("matched_via") or "")
    affected_teams = int(pd.to_numeric(row.get("affected_teams"), errors="coerce") or 0)

    if "token_overlap" in matched_via:
        return "Likely race identity/alias gap plus missing historical coverage"
    if affected_teams >= 2:
        return "Likely missing historical race-opportunity coverage"
    return "Likely one-off historical coverage gap or genuinely new race"


def _recommended_action(row: pd.Series) -> str:
    matched_via = str(row.get("matched_via") or "")
    category = str(row.get("category") or "")

    if "token_overlap" in matched_via:
        return (
            "Review race identity and aliases first, then backfill historical results and expected-opportunity summaries "
            f"for prior `{category}` editions."
        )
    return (
        "Backfill historical results and expected-opportunity summaries for prior "
        f"`{category}` editions, then add a canonical race record for reuse across teams."
    )


def _build_summary(
    *,
    priority_list: pd.DataFrame,
    race_details: pd.DataFrame,
    audit: HistoryMissingAuditArtifacts,
) -> dict[str, object]:
    return {
        "audit_date": date.today().isoformat(),
        "team_ev_root": str(DEFAULT_TEAM_EV_ROOT),
        "source_completed_missing_ev_rows": int(len(race_details)),
        "unique_backfill_races": int(len(priority_list)),
        "p1_races": int((priority_list.get("priority_tier", pd.Series(dtype=object)) == "P1").sum()),
        "p2_races": int((priority_list.get("priority_tier", pd.Series(dtype=object)) == "P2").sum()),
        "p3_races": int((priority_list.get("priority_tier", pd.Series(dtype=object)) == "P3").sum()),
        "total_actual_points_in_scope": round(
            float(pd.to_numeric(race_details.get("actual_points"), errors="coerce").fillna(0.0).sum()),
            6,
        ),
        "top_priority_race": str(priority_list.iloc[0]["race_name"]) if not priority_list.empty else "",
        "history_missing_audit_summary": audit.summary,
    }


def _format_report(summary: dict[str, object], priority_list: pd.DataFrame) -> str:
    lines = [
        "# History-Missing Backfill Priority List",
        "",
        f"Audit date: `{summary['audit_date']}`",
        "",
        "## Overview",
        "",
        f"- Source completed no-fallback rows: `{summary['source_completed_missing_ev_rows']}`",
        f"- Unique races to backfill: `{summary['unique_backfill_races']}`",
        f"- P1 races: `{summary['p1_races']}`",
        f"- P2 races: `{summary['p2_races']}`",
        f"- P3 races: `{summary['p3_races']}`",
        f"- Actual points in scope: `{summary['total_actual_points_in_scope']}`",
        "",
        "## Priority Queue",
        "",
    ]

    if priority_list.empty:
        lines.append("No completed no-fallback `history_missing` races were found.")
        lines.append("")
        return "\n".join(lines)

    lines.extend(_markdown_table(priority_list))
    lines.append("")
    return "\n".join(lines)


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    prepared = frame.copy()
    for column in prepared.columns:
        if pd.api.types.is_float_dtype(prepared[column]):
            prepared[column] = prepared[column].map(
                lambda value: "" if pd.isna(value) else f"{float(value):.3f}".rstrip("0").rstrip(".")
            )
        else:
            prepared[column] = prepared[column].fillna("").astype(str)
    lines = [
        "| " + " | ".join(prepared.columns.astype(str).tolist()) + " |",
        "| " + " | ".join(["---"] * len(prepared.columns)) + " |",
    ]
    for _, row in prepared.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in prepared.columns) + " |")
    return lines


def _priority_columns() -> list[str]:
    return [
        "priority_rank",
        "priority_tier",
        "race_name",
        "category",
        "affected_rows",
        "affected_teams",
        "total_actual_points",
        "matched_via",
        "likely_issue",
        "recommended_action",
        "priority_score",
        "teams",
        "first_seen_date",
        "last_seen_date",
    ]
