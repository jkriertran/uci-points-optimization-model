from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data_sources import load_historical_dataset
from .historical_data_import import DEFAULT_IMPORTED_ROOT
from .target_definitions import attach_next_top5_targets, default_top5_target_path
from .team_identity import canonicalize_team_slug

TEAM_DEPTH_PANEL_FILENAME = "team_season_panel.csv"
THRESHOLD_COLUMNS = {
    50: "n_riders_50_plus",
    100: "n_riders_100_plus",
    150: "n_riders_150_plus",
    250: "n_riders_250_plus",
    300: "n_riders_300_plus",
    400: "n_riders_400_plus",
}
ALIGNMENT_THRESHOLDS = (100, 150, 250, 400)
SCORE_DEPTH_WEIGHTS = {
    "n_riders_150_plus": 1.0,
    "n_riders_100_plus": 0.35,
    "n_riders_50_plus": 0.15,
    "n_riders_300_plus": 0.5,
    "effective_contributors": 0.5,
    "points_outside_top5": 0.002,
    "top1_share_penalty": 4.0,
}


def build_team_depth_panel(
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
    current_snapshot_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    imported_team_df, team_decision = load_historical_dataset(
        dataset_key="historical_proteam_team_panel",
        import_root=import_root,
    )
    imported_rider_df, rider_decision = load_historical_dataset(
        dataset_key="historical_proteam_rider_panel",
        import_root=import_root,
    )
    if imported_team_df.empty or imported_rider_df.empty:
        raise ValueError("Imported historical team and rider panels are required to build the team-depth panel.")

    team_panel = _normalize_imported_team_panel(imported_team_df)
    rider_features = _build_rider_derived_team_features(imported_rider_df)
    merged = team_panel.merge(
        rider_features,
        on=["season", "team_slug"],
        how="left",
        validate="one_to_one",
    )
    _validate_threshold_alignment(merged)

    for threshold, column_name in THRESHOLD_COLUMNS.items():
        derived_column = f"derived_{column_name}"
        merged[column_name] = pd.to_numeric(merged[derived_column], errors="coerce").fillna(0).astype(int)

    merged["points_outside_top5"] = pd.to_numeric(
        merged["derived_points_outside_top5"], errors="coerce"
    ).fillna(0.0)
    merged["n_riders_scoring"] = pd.to_numeric(
        merged["derived_n_riders_scoring"], errors="coerce"
    ).fillna(0).astype(int)
    merged["effective_contributors"] = pd.to_numeric(
        merged["derived_effective_contributors"], errors="coerce"
    ).fillna(0.0)
    merged = _apply_current_snapshot_team_overrides(
        merged,
        current_snapshot_df=current_snapshot_df,
    )
    merged["score_depth_index"] = _calculate_score_depth_index(merged)

    drop_columns = [column for column in merged.columns if column.startswith("derived_")]
    merged = merged.drop(columns=drop_columns)
    merged = attach_next_top5_targets(merged, import_root=import_root)
    merged["team_history_source"] = team_decision.selected_source
    merged["rider_history_source"] = rider_decision.selected_source
    return merged.sort_values(["season", "proteam_rank", "team_name"]).reset_index(drop=True)


def write_team_depth_panel(
    dataset: pd.DataFrame,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(output_path) if output_path is not None else default_team_depth_panel_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(path, index=False)
    return path


def default_team_depth_panel_path() -> Path:
    return default_top5_target_path(TEAM_DEPTH_PANEL_FILENAME)


def _normalize_imported_team_panel(imported_team_df: pd.DataFrame) -> pd.DataFrame:
    team_panel = imported_team_df.rename(
        columns={
            "season_year": "season",
            "team_total_uci_points": "team_points_total",
            "team_rank": "proteam_rank",
            "n_riders_100": "imported_n_riders_100_plus",
            "n_riders_150": "imported_n_riders_150_plus",
            "n_riders_250": "imported_n_riders_250_plus",
            "n_riders_400": "imported_n_riders_400_plus",
        }
    ).copy()
    team_panel["season"] = pd.to_numeric(team_panel["season"], errors="coerce").astype("Int64")
    team_panel["proteam_rank"] = pd.to_numeric(team_panel["proteam_rank"], errors="coerce").astype("Int64")
    team_panel["team_points_total"] = pd.to_numeric(team_panel["team_points_total"], errors="coerce").fillna(0.0)
    team_panel["team_base_slug"] = team_panel.apply(
        lambda row: canonicalize_team_slug(row["team_slug"], int(row["season"])),
        axis=1,
    )
    return team_panel


def _build_rider_derived_team_features(imported_rider_df: pd.DataFrame) -> pd.DataFrame:
    rider_df = imported_rider_df.copy()
    rider_df["season"] = pd.to_numeric(rider_df["season_year"], errors="coerce").astype("Int64")
    rider_df["uci_points"] = pd.to_numeric(rider_df["uci_points"], errors="coerce").fillna(0.0)
    rider_df["team_rank_within_roster"] = pd.to_numeric(
        rider_df["team_rank_within_roster"], errors="coerce"
    ).astype("Int64")

    rows: list[dict[str, object]] = []
    for (season, team_slug), group in rider_df.groupby(["season", "team_slug"], sort=False):
        points = group["uci_points"].astype(float)
        team_total = float(points.sum())
        sorted_group = group.sort_values(
            ["team_rank_within_roster", "uci_points", "rider_name"],
            ascending=[True, False, True],
            na_position="last",
        ).reset_index(drop=True)
        if sorted_group["team_rank_within_roster"].isna().all():
            sorted_group = sorted_group.sort_values(
                ["uci_points", "rider_name"],
                ascending=[False, True],
            ).reset_index(drop=True)
            sorted_group["team_rank_within_roster"] = range(1, len(sorted_group) + 1)

        shares = (points / team_total) if team_total else pd.Series(0.0, index=group.index)
        share_square_sum = float((shares.pow(2)).sum())
        effective_contributors = float(1.0 / share_square_sum) if share_square_sum > 0 else 0.0
        points_outside_top5 = float(
            sorted_group.loc[sorted_group["team_rank_within_roster"].astype("Int64") > 5, "uci_points"].sum()
        )

        row: dict[str, object] = {
            "season": season,
            "team_slug": team_slug,
            "derived_n_riders_scoring": int((points > 0).sum()),
            "derived_effective_contributors": effective_contributors,
            "derived_points_outside_top5": points_outside_top5,
        }
        for threshold, column_name in THRESHOLD_COLUMNS.items():
            row[f"derived_{column_name}"] = int((points >= float(threshold)).sum())
        rows.append(row)

    return pd.DataFrame(rows)


def _validate_threshold_alignment(team_panel: pd.DataFrame) -> None:
    mismatches: list[str] = []
    for threshold in ALIGNMENT_THRESHOLDS:
        imported_column = f"imported_n_riders_{threshold}_plus"
        derived_column = f"derived_n_riders_{threshold}_plus"
        if imported_column not in team_panel.columns or derived_column not in team_panel.columns:
            continue
        mask = (
            pd.to_numeric(team_panel[imported_column], errors="coerce").fillna(-1).astype(int)
            != pd.to_numeric(team_panel[derived_column], errors="coerce").fillna(-1).astype(int)
        )
        mismatch_count = int(mask.sum())
        if mismatch_count:
            mismatches.append(f"{threshold}+ mismatch rows: {mismatch_count}")

    if mismatches:
        raise ValueError(
            "Imported team panel threshold counts do not align with rider-derived counts: "
            + "; ".join(mismatches)
        )


def _calculate_score_depth_index(team_panel: pd.DataFrame) -> pd.Series:
    score = (
        (team_panel["n_riders_150_plus"] * SCORE_DEPTH_WEIGHTS["n_riders_150_plus"])
        + (team_panel["n_riders_100_plus"] * SCORE_DEPTH_WEIGHTS["n_riders_100_plus"])
        + (team_panel["n_riders_50_plus"] * SCORE_DEPTH_WEIGHTS["n_riders_50_plus"])
        + (team_panel["n_riders_300_plus"] * SCORE_DEPTH_WEIGHTS["n_riders_300_plus"])
        + (team_panel["effective_contributors"] * SCORE_DEPTH_WEIGHTS["effective_contributors"])
        + (team_panel["points_outside_top5"] * SCORE_DEPTH_WEIGHTS["points_outside_top5"])
        - (team_panel["top1_share"] * SCORE_DEPTH_WEIGHTS["top1_share_penalty"])
    )
    return score.round(6)


def _apply_current_snapshot_team_overrides(
    team_panel: pd.DataFrame,
    *,
    current_snapshot_df: pd.DataFrame | None,
) -> pd.DataFrame:
    # The live ProTeam risk snapshot is a rolling counted-ranking view. The team-depth
    # panel is intentionally season-only, so we do not overlay counted snapshot metrics here.
    _ = current_snapshot_df
    return team_panel.copy()
