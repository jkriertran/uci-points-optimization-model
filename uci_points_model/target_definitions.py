from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data_sources import load_historical_dataset
from .historical_data_import import DEFAULT_IMPORTED_ROOT

MODEL_INPUTS_ROOT = Path(__file__).resolve().parent.parent / "data" / "model_inputs"


def build_next_top5_targets(
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
) -> pd.DataFrame:
    continuity_df, continuity_decision = load_historical_dataset(
        dataset_key="transition_continuity_links",
        import_root=import_root,
    )
    ranking_df, ranking_decision = load_historical_dataset(
        dataset_key="ranking_predictor_study_data",
        import_root=import_root,
    )
    if continuity_df.empty:
        raise ValueError("Imported transition continuity links are required to build next-season targets.")

    continuity = continuity_df.loc[continuity_df["matched_prior_team"].fillna(0).astype(int) == 1].copy()
    continuity = continuity.rename(
        columns={
            "year_a": "season",
            "year_b": "next_season",
        }
    )
    continuity = continuity[
        [
            "season",
            "next_season",
            "prior_team_slug",
            "next_team_slug",
            "next_team_name",
            "continuity_source",
        ]
    ].drop_duplicates(subset=["season", "prior_team_slug"], keep="first")

    if ranking_df.empty:
        ranking = pd.DataFrame(
            columns=[
                "season",
                "next_season",
                "prior_team_slug",
                "next_team_slug",
                "next_team_name",
                "continuity_source",
                "next_proteam_rank",
                "next_team_points_total",
                "next_top3_proteam",
                "next_top5_proteam",
                "next_top8_proteam",
            ]
        )
    else:
        ranking = ranking_df.rename(
            columns={
                "year_a": "season",
                "year_b": "next_season",
                "next_rank": "next_proteam_rank",
                "next_pts": "next_team_points_total",
                "next_top3": "next_top3_proteam",
                "next_top5": "next_top5_proteam",
                "next_top8": "next_top8_proteam",
            }
        ).copy()
        ranking = ranking[
            [
                "season",
                "next_season",
                "prior_team_slug",
                "next_team_slug",
                "next_team_name",
                "continuity_source",
                "next_proteam_rank",
                "next_team_points_total",
                "next_top3_proteam",
                "next_top5_proteam",
                "next_top8_proteam",
            ]
        ].drop_duplicates(subset=["season", "prior_team_slug"], keep="first")

    targets = continuity.merge(
        ranking,
        on=["season", "next_season", "prior_team_slug", "next_team_slug"],
        how="left",
        suffixes=("_continuity", "_ranking"),
        validate="one_to_one",
    )
    targets["next_team_name"] = targets["next_team_name_ranking"].combine_first(
        targets["next_team_name_continuity"]
    )
    targets["continuity_source"] = targets["continuity_source_ranking"].combine_first(
        targets["continuity_source_continuity"]
    )
    targets = targets.drop(
        columns=[
            "next_team_name_continuity",
            "next_team_name_ranking",
            "continuity_source_continuity",
            "continuity_source_ranking",
        ]
    )
    for column in ("season", "next_season", "next_proteam_rank"):
        targets[column] = pd.to_numeric(targets[column], errors="coerce").astype("Int64")
    targets["next_team_points_total"] = pd.to_numeric(
        targets["next_team_points_total"], errors="coerce"
    )
    for column in ("next_top3_proteam", "next_top5_proteam", "next_top8_proteam"):
        targets[column] = pd.to_numeric(targets[column], errors="coerce").astype("Int64")
    targets.attrs["sources"] = {
        "continuity": continuity_decision.selected_source,
        "ranking": ranking_decision.selected_source,
    }
    return targets.sort_values(["season", "prior_team_slug"]).reset_index(drop=True)


def attach_next_top5_targets(
    team_panel: pd.DataFrame,
    import_root: str | Path = DEFAULT_IMPORTED_ROOT,
) -> pd.DataFrame:
    if team_panel.empty:
        return team_panel.copy()

    targets = build_next_top5_targets(import_root=import_root)
    enriched = team_panel.merge(
        targets,
        left_on=["season", "team_slug"],
        right_on=["season", "prior_team_slug"],
        how="left",
        validate="one_to_one",
    )
    enriched = enriched.drop(columns=["prior_team_slug"])
    enriched["has_observed_next_season"] = enriched["next_top5_proteam"].notna()
    return enriched


def default_top5_target_path(filename: str) -> Path:
    return MODEL_INPUTS_ROOT / filename
