from __future__ import annotations

from dataclasses import dataclass

SOURCE_IMPORTED_HISTORY = "imported_history"
SOURCE_LOCAL_ARTIFACT = "local_artifact"
SOURCE_DIRECT_SCRAPE = "direct_scrape"
SOURCE_FIRECRAWL = "firecrawl"
SOURCE_MANUAL = "manual"


@dataclass(frozen=True)
class DatasetSourcePolicy:
    dataset_key: str
    description: str
    fallback_order: tuple[str, ...]
    import_key: str | None = None


SOURCE_POLICIES = {
    "historical_proteam_team_panel": DatasetSourcePolicy(
        dataset_key="historical_proteam_team_panel",
        description="Historical team-depth seed table for top-five ProTeam modeling.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="historical_proteam_team_panel",
    ),
    "historical_proteam_rider_panel": DatasetSourcePolicy(
        dataset_key="historical_proteam_rider_panel",
        description="Historical rider-season seed table for rider-threshold modeling.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="historical_proteam_rider_panel",
    ),
    "ranking_predictor_study_data": DatasetSourcePolicy(
        dataset_key="ranking_predictor_study_data",
        description="Observed transition table for the top-five ProTeam baseline model.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="ranking_predictor_study_data",
    ),
    "transition_continuity_links": DatasetSourcePolicy(
        dataset_key="transition_continuity_links",
        description="Continuity mapping for renamed ProTeams across adjacent seasons.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="transition_continuity_links",
    ),
    "rider_season_result_summary": DatasetSourcePolicy(
        dataset_key="rider_season_result_summary",
        description="Rider-season result aggregates used to enrich the rider-threshold panel.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="rider_season_result_summary",
    ),
    "rider_transfer_context_enriched": DatasetSourcePolicy(
        dataset_key="rider_transfer_context_enriched",
        description="Transfer and continuity covariates for rider-threshold modeling.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="rider_transfer_context_enriched",
    ),
    "race_entries_pts_v2": DatasetSourcePolicy(
        dataset_key="race_entries_pts_v2",
        description="Team-in-race points context for later rider-race allocation work.",
        fallback_order=(
            SOURCE_IMPORTED_HISTORY,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
        import_key="race_entries_pts_v2",
    ),
    "planning_calendar": DatasetSourcePolicy(
        dataset_key="planning_calendar",
        description="Local planning-calendar artifact used by the race-opportunity workspace.",
        fallback_order=(
            SOURCE_LOCAL_ARTIFACT,
            SOURCE_DIRECT_SCRAPE,
            SOURCE_FIRECRAWL,
            SOURCE_MANUAL,
        ),
    ),
}


def get_source_policy(dataset_key: str) -> DatasetSourcePolicy:
    try:
        return SOURCE_POLICIES[dataset_key]
    except KeyError as exc:
        raise KeyError(f"Unknown dataset source policy: {dataset_key}") from exc
