from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from .pcs_client import CYCLE_LABEL, CYCLE_SCOPE, CURRENT_SCOPE, ProCyclingStatsClient

SNAPSHOT_FILENAMES = {
    CURRENT_SCOPE: "proteam_risk_current_snapshot.csv",
    CYCLE_SCOPE: "proteam_risk_cycle_2026_2028_snapshot.csv",
}

RISK_BAND_HIGH = "High"
RISK_BAND_MEDIUM = "Medium"
RISK_BAND_LOWER = "Lower"
TEAM_OVERRIDE_THRESHOLDS = (50, 100, 150, 250, 300, 400)


def default_proteam_snapshot_path(scope: str) -> Path:
    if scope not in SNAPSHOT_FILENAMES:
        raise ValueError(f"Unsupported ProTeam risk scope: {scope}")
    return Path(__file__).resolve().parent.parent / "data" / SNAPSHOT_FILENAMES[scope]


def build_proteam_risk_dataset(
    scope: str,
    team_classes: Iterable[str] = ("PRT",),
    client: ProCyclingStatsClient | None = None,
) -> pd.DataFrame:
    pcs_client = client or ProCyclingStatsClient()
    ranking_entries = pcs_client.get_team_rankings(scope=scope)
    selected_classes = set(team_classes)
    scraped_at = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, object]] = []
    for entry in ranking_entries:
        if entry.team_class not in selected_classes:
            continue

        breakdown = pcs_client.get_team_breakdown(team_path=entry.team_path, scope=scope)
        total_counted_points = float(breakdown.total_counted_points or entry.ranking_points)
        team_payload = {
            "scope": scope,
            "cycle_label": CYCLE_LABEL if scope == CYCLE_SCOPE else "",
            "team_rank": entry.team_rank,
            "team_name": entry.team_name,
            "team_slug": entry.team_slug,
            "team_class": entry.team_class,
            "ranking_total_points": float(entry.ranking_points),
            "team_total_points": total_counted_points,
            "sanction_points_total": float(breakdown.sanction_points_total),
            "ranking_url": entry.breakdown_path if scope == CYCLE_SCOPE else entry.breakdown_path,
            "source_url": breakdown.source_url,
            "scraped_at": scraped_at,
        }

        if breakdown.rows:
            for breakdown_row in breakdown.rows:
                rows.append(
                    {
                        **team_payload,
                        "is_placeholder_team_row": False,
                        **breakdown_row,
                    }
                )
        else:
            rows.append(
                {
                    **team_payload,
                    "season_year": pd.NA,
                    "rider_name": "",
                    "rider_slug": "",
                    "team_rank_within_counted_list": 0,
                    "points_counted": 0.0,
                    "points_not_counted": 0.0,
                    "sanction_points": 0.0,
                    "is_placeholder_team_row": True,
                }
            )

    dataset = pd.DataFrame(rows)
    if dataset.empty:
        return dataset

    dataset["is_placeholder_team_row"] = dataset["is_placeholder_team_row"].fillna(False).astype(bool)
    dataset["season_year"] = pd.to_numeric(dataset["season_year"], errors="coerce").astype("Int64")
    return dataset.sort_values(["team_rank", "season_year", "team_rank_within_counted_list"]).reset_index(
        drop=True
    )


def write_proteam_risk_snapshot(
    dataset: pd.DataFrame,
    scope: str,
    snapshot_path: str | Path | None = None,
) -> Path:
    path = Path(snapshot_path) if snapshot_path is not None else default_proteam_snapshot_path(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)
    return path


def load_proteam_risk_snapshot(
    scope: str,
    snapshot_path: str | Path | None = None,
) -> pd.DataFrame:
    path = Path(snapshot_path) if snapshot_path is not None else default_proteam_snapshot_path(scope)
    if not path.exists():
        return pd.DataFrame()
    dataset = pd.read_csv(path)
    if "is_placeholder_team_row" in dataset.columns:
        dataset["is_placeholder_team_row"] = dataset["is_placeholder_team_row"].fillna(False).astype(bool)
    else:
        dataset["is_placeholder_team_row"] = False
    if "season_year" in dataset.columns:
        dataset["season_year"] = pd.to_numeric(dataset["season_year"], errors="coerce").astype("Int64")
    dataset.attrs["snapshot_path"] = str(path)
    return dataset


def aggregate_proteam_riders(raw_dataset: pd.DataFrame) -> pd.DataFrame:
    if raw_dataset.empty:
        return pd.DataFrame()

    dataset = raw_dataset.copy()
    if "is_placeholder_team_row" in dataset.columns:
        dataset["is_placeholder_team_row"] = dataset["is_placeholder_team_row"].fillna(False).astype(bool)
    else:
        dataset["is_placeholder_team_row"] = False
    dataset["season_year"] = pd.to_numeric(dataset["season_year"], errors="coerce").astype("Int64")
    group_columns = [
        "scope",
        "cycle_label",
        "team_rank",
        "team_name",
        "team_slug",
        "team_class",
        "ranking_total_points",
        "team_total_points",
        "sanction_points_total",
        "ranking_url",
        "source_url",
        "scraped_at",
        "rider_name",
        "rider_slug",
        "is_placeholder_team_row",
    ]
    aggregated = (
        dataset.groupby(group_columns, dropna=False, as_index=False)
        .agg(
            points_counted=("points_counted", "sum"),
            points_not_counted=("points_not_counted", "sum"),
            sanction_points=("sanction_points", "sum"),
            season_years=(
                "season_year",
                lambda years: ", ".join(str(int(year)) for year in sorted({year for year in years.dropna()})),
            ),
        )
        .sort_values(["team_rank", "points_counted", "rider_name"], ascending=[True, False, True])
        .reset_index(drop=True)
    )
    aggregated["team_rank_within_counted_list"] = 0
    non_placeholder_mask = ~aggregated["is_placeholder_team_row"]
    aggregated.loc[non_placeholder_mask, "team_rank_within_counted_list"] = (
        aggregated.loc[non_placeholder_mask]
        .groupby("team_slug")
        .cumcount()
        .add(1)
        .astype(int)
    )
    team_totals = pd.to_numeric(aggregated["team_total_points"], errors="coerce")
    points_counted = pd.to_numeric(aggregated["points_counted"], errors="coerce")
    aggregated["share_of_team"] = points_counted.div(team_totals.where(team_totals != 0)).fillna(0.0)
    aggregated["cumulative_share"] = aggregated.groupby("team_slug")["share_of_team"].cumsum()
    return aggregated


def summarize_proteam_risk(raw_dataset: pd.DataFrame) -> pd.DataFrame:
    rider_dataset = aggregate_proteam_riders(raw_dataset)
    if rider_dataset.empty:
        return pd.DataFrame()

    summary_rows: list[dict[str, object]] = []
    for _, group in rider_dataset.groupby("team_slug", sort=False):
        sorted_group = group.sort_values(["points_counted", "rider_name"], ascending=[False, True]).reset_index(drop=True)
        real_group = sorted_group.loc[~sorted_group["is_placeholder_team_row"]].reset_index(drop=True)
        scoring_group = real_group if not real_group.empty else sorted_group.iloc[0:0]

        team_total_points = float(sorted_group["team_total_points"].iloc[0])
        ranking_total_points = float(sorted_group["ranking_total_points"].iloc[0])
        leader_points = float(scoring_group["points_counted"].iloc[0]) if not scoring_group.empty else 0.0
        top3_points = float(scoring_group["points_counted"].head(3).sum())
        top5_points = float(scoring_group["points_counted"].head(5).sum())
        top2_points = float(scoring_group["points_counted"].head(2).sum())
        share_series = (scoring_group["points_counted"] / team_total_points) if team_total_points else pd.Series(0.0)
        effective_contributors = (
            float(1.0 / (share_series.pow(2).sum())) if team_total_points and share_series.pow(2).sum() else 0.0
        )
        leader_shock_remaining = team_total_points - leader_points
        coleader_shock_remaining = team_total_points - top2_points
        leader_shock_pct = (leader_points / team_total_points) if team_total_points else 0.0
        coleader_shock_pct = (top2_points / team_total_points) if team_total_points else 0.0
        top1_share = leader_shock_pct
        top3_share = (top3_points / team_total_points) if team_total_points else 0.0
        top5_share = (top5_points / team_total_points) if team_total_points else 0.0
        reconciliation_gap = team_total_points - ranking_total_points

        summary_rows.append(
            {
                "scope": sorted_group["scope"].iloc[0],
                "cycle_label": sorted_group["cycle_label"].iloc[0],
                "team_rank": int(sorted_group["team_rank"].iloc[0]),
                "team_name": sorted_group["team_name"].iloc[0],
                "team_slug": sorted_group["team_slug"].iloc[0],
                "team_class": sorted_group["team_class"].iloc[0],
                "team_total_points": team_total_points,
                "ranking_total_points": ranking_total_points,
                "counted_riders_found": int(len(real_group)),
                "leader_name": scoring_group["rider_name"].iloc[0] if not scoring_group.empty else "",
                "leader_points": leader_points,
                "top1_share": top1_share,
                "top3_share": top3_share,
                "top5_share": top5_share,
                "effective_contributors": effective_contributors,
                "leader_shock_remaining_points": leader_shock_remaining,
                "leader_shock_drop_points": leader_points,
                "leader_shock_drop_pct": leader_shock_pct,
                "leader_coleader_shock_remaining_points": coleader_shock_remaining,
                "leader_coleader_shock_drop_points": top2_points,
                "leader_coleader_shock_drop_pct": coleader_shock_pct,
                "risk_band": risk_band(top1_share, leader_shock_pct),
                "reconciliation_gap": reconciliation_gap,
                "data_check": "Warning" if abs(reconciliation_gap) > 1.0 else "OK",
                "sanction_points_total": float(sorted_group["sanction_points_total"].iloc[0]),
                "ranking_url": sorted_group["ranking_url"].iloc[0],
                "source_url": sorted_group["source_url"].iloc[0],
                "scraped_at": sorted_group["scraped_at"].iloc[0],
            }
        )

    summary = pd.DataFrame(summary_rows)
    return summary.sort_values(
        ["top1_share", "leader_shock_drop_pct", "team_total_points"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def prepare_proteam_detail(raw_dataset: pd.DataFrame, team_slug: str) -> pd.DataFrame:
    rider_dataset = aggregate_proteam_riders(raw_dataset)
    if "is_placeholder_team_row" in rider_dataset.columns:
        rider_dataset = rider_dataset.loc[~rider_dataset["is_placeholder_team_row"]].copy()
    detail = rider_dataset[rider_dataset["team_slug"] == team_slug].copy()
    if detail.empty:
        return detail
    detail["share_pct"] = detail["share_of_team"] * 100
    detail["cumulative_share_pct"] = detail["cumulative_share"] * 100
    return detail.sort_values(["team_rank_within_counted_list"]).reset_index(drop=True)


def build_current_team_metric_overrides(raw_dataset: pd.DataFrame) -> pd.DataFrame:
    if raw_dataset.empty:
        rider_dataset = pd.DataFrame()
    else:
        dataset = raw_dataset.copy()
        required_defaults: dict[str, object] = {
            "cycle_label": "",
            "ranking_url": "",
            "source_url": "",
            "scraped_at": "",
            "season_year": pd.NA,
            "points_counted": 0.0,
            "points_not_counted": 0.0,
            "sanction_points": 0.0,
            "team_rank_within_counted_list": 0,
            "is_placeholder_team_row": False,
            "ranking_total_points": 0.0,
            "team_total_points": 0.0,
            "sanction_points_total": 0.0,
        }
        for column, default_value in required_defaults.items():
            if column not in dataset.columns:
                dataset[column] = default_value
        rider_dataset = aggregate_proteam_riders(dataset)
    if rider_dataset.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "team_slug",
                "snapshot_team_points_total",
                "snapshot_top1_share",
                "snapshot_top3_share",
                "snapshot_top5_share",
                "snapshot_n_riders_scoring",
                "snapshot_effective_contributors",
                "snapshot_points_outside_top5",
                "snapshot_n_riders_50_plus",
                "snapshot_n_riders_100_plus",
                "snapshot_n_riders_150_plus",
                "snapshot_n_riders_250_plus",
                "snapshot_n_riders_300_plus",
                "snapshot_n_riders_400_plus",
            ]
        )

    override_rows: list[dict[str, object]] = []
    for _, group in rider_dataset.groupby("team_slug", sort=False):
        scoring_group = group.loc[~group["is_placeholder_team_row"]].copy()
        if scoring_group.empty:
            continue
        scoring_group["points_counted"] = pd.to_numeric(scoring_group["points_counted"], errors="coerce").fillna(0.0)
        scoring_group["team_rank_within_counted_list"] = pd.to_numeric(
            scoring_group["team_rank_within_counted_list"],
            errors="coerce",
        ).astype("Int64")
        scoring_group = scoring_group.sort_values(
            ["team_rank_within_counted_list", "points_counted", "rider_name"],
            ascending=[True, False, True],
            na_position="last",
        ).reset_index(drop=True)
        season_values: set[int] = set()
        for raw_years in scoring_group.get("season_years", pd.Series("", index=scoring_group.index)).astype(str):
            for year_value in raw_years.split(","):
                cleaned = year_value.strip()
                if cleaned.isdigit():
                    season_values.add(int(cleaned))
        if not season_values:
            continue

        team_total_points = float(pd.to_numeric(scoring_group["team_total_points"], errors="coerce").iloc[0])
        share_series = (
            scoring_group["points_counted"].div(team_total_points).fillna(0.0)
            if team_total_points
            else pd.Series(0.0, index=scoring_group.index, dtype=float)
        )
        share_square_sum = float((share_series.pow(2)).sum())
        override_row: dict[str, object] = {
            "season": int(max(season_values)),
            "team_slug": str(scoring_group["team_slug"].iloc[0]),
            "snapshot_team_points_total": team_total_points,
            "snapshot_top1_share": float(scoring_group["points_counted"].head(1).sum() / team_total_points)
            if team_total_points
            else 0.0,
            "snapshot_top3_share": float(scoring_group["points_counted"].head(3).sum() / team_total_points)
            if team_total_points
            else 0.0,
            "snapshot_top5_share": float(scoring_group["points_counted"].head(5).sum() / team_total_points)
            if team_total_points
            else 0.0,
            "snapshot_n_riders_scoring": int((scoring_group["points_counted"] > 0).sum()),
            "snapshot_effective_contributors": float(1.0 / share_square_sum) if share_square_sum > 0 else 0.0,
            "snapshot_points_outside_top5": float(scoring_group["points_counted"].iloc[5:].sum()),
        }
        for threshold in TEAM_OVERRIDE_THRESHOLDS:
            override_row[f"snapshot_n_riders_{threshold}_plus"] = int(
                (scoring_group["points_counted"] >= float(threshold)).sum()
            )
        override_rows.append(override_row)

    return pd.DataFrame(override_rows)


def risk_band(top1_share: float, leader_shock_pct: float) -> str:
    if top1_share >= 0.35 or leader_shock_pct >= 0.30:
        return RISK_BAND_HIGH
    if top1_share >= 0.25 or leader_shock_pct >= 0.20:
        return RISK_BAND_MEDIUM
    return RISK_BAND_LOWER
