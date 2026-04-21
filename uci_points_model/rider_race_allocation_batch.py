from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .rider_race_allocation import (
    build_rider_race_allocation_artifacts,
    default_rider_race_allocation_output_root,
    rider_race_allocation_artifact_stem,
    write_rider_race_allocation_artifacts,
)


@dataclass(frozen=True)
class RiderRaceAllocationBuildRequest:
    team_slug: str
    planning_year: int
    team_ev_path: Path


@dataclass(frozen=True)
class RiderRaceAllocationBuildOutcome:
    team_slug: str
    planning_year: int
    success: bool
    error: str = ""
    summary: dict[str, object] | None = None
    written_paths: dict[str, Path] | None = None


def resolve_saved_team_ev_path(team_ev_root: str | Path, team_slug: str, planning_year: int) -> Path:
    root = Path(team_ev_root)
    artifact_stem = rider_race_allocation_artifact_stem(team_slug, planning_year)
    team_ev_path = root / f"{artifact_stem}_calendar_ev.csv"
    if not team_ev_path.exists():
        raise FileNotFoundError(f"Saved Team Calendar EV artifact not found: {team_ev_path}")
    return team_ev_path


def discover_rider_race_allocation_requests(team_ev_root: str | Path) -> list[RiderRaceAllocationBuildRequest]:
    root = Path(team_ev_root)
    if not root.exists():
        raise FileNotFoundError(f"Team Calendar EV directory not found: {root}")

    requests: list[RiderRaceAllocationBuildRequest] = []
    for team_ev_path in sorted(root.glob("*_calendar_ev.csv")):
        sample_df = pd.read_csv(team_ev_path, nrows=1, low_memory=False)
        if sample_df.empty:
            raise ValueError(f"Saved Team Calendar EV artifact is empty: {team_ev_path}")

        row = sample_df.iloc[0]
        team_slug = str(row.get("team_slug") or "").strip()
        planning_year = pd.to_numeric(row.get("planning_year"), errors="coerce")
        if not team_slug:
            raise ValueError(f"Saved Team Calendar EV artifact is missing team_slug: {team_ev_path}")
        if pd.isna(planning_year):
            raise ValueError(f"Saved Team Calendar EV artifact is missing planning_year: {team_ev_path}")

        requests.append(
            RiderRaceAllocationBuildRequest(
                team_slug=team_slug,
                planning_year=int(planning_year),
                team_ev_path=team_ev_path,
            )
        )

    return requests


def load_team_ev_for_request(request: RiderRaceAllocationBuildRequest) -> pd.DataFrame:
    if not request.team_ev_path.exists():
        raise FileNotFoundError(f"Saved Team Calendar EV artifact not found: {request.team_ev_path}")
    return pd.read_csv(request.team_ev_path, low_memory=False)


def preferred_rider_threshold_model_name(
    *,
    rider_baseline_summary_path: str | Path,
    rider_backtest_summary_path: str | Path,
) -> str:
    backtest_path = Path(rider_backtest_summary_path)
    if backtest_path.exists():
        payload = json.loads(backtest_path.read_text())
        winning_model_name = str(payload.get("winning_model_name") or "").strip()
        if winning_model_name:
            return winning_model_name

    baseline_path = Path(rider_baseline_summary_path)
    if baseline_path.exists():
        payload = json.loads(baseline_path.read_text())
        anchor_model_name = str(payload.get("anchor_model_name") or "").strip()
        if anchor_model_name:
            return anchor_model_name

    return "baseline_prior_points"


def load_rider_scores_for_request(
    request: RiderRaceAllocationBuildRequest,
    *,
    rider_scores_path: str | Path,
    rider_baseline_summary_path: str | Path,
    rider_backtest_summary_path: str | Path,
) -> pd.DataFrame:
    scores_path = Path(rider_scores_path)
    if not scores_path.exists():
        raise FileNotFoundError(f"Rider threshold score table not found: {scores_path}")

    scores_df = pd.read_csv(scores_path, low_memory=False)
    preferred_model_name = preferred_rider_threshold_model_name(
        rider_baseline_summary_path=rider_baseline_summary_path,
        rider_backtest_summary_path=rider_backtest_summary_path,
    )
    filtered = scores_df.loc[
        (scores_df.get("model_name", pd.Series("", index=scores_df.index)).astype(str) == preferred_model_name)
        & (scores_df.get("evaluation_split", pd.Series("", index=scores_df.index)).astype(str) == "full_fit_panel")
        & (pd.to_numeric(scores_df.get("season"), errors="coerce") == int(request.planning_year))
        & (scores_df.get("team_base_slug", pd.Series("", index=scores_df.index)).astype(str) == str(request.team_slug))
    ].copy()
    if filtered.empty:
        raise ValueError(
            "No rider threshold scores matched the requested team-season and preferred rider model: "
            f"team_slug={request.team_slug}, planning_year={request.planning_year}, model_name={preferred_model_name}"
        )
    return filtered.reset_index(drop=True)


def build_batch_rider_race_allocations(
    requests: list[RiderRaceAllocationBuildRequest],
    *,
    rider_scores_path: str | Path,
    rider_baseline_summary_path: str | Path,
    rider_backtest_summary_path: str | Path,
    output_root: str | Path | None = None,
    roster_size: int = 7,
    top_riders_per_race: int = 3,
    team_slug: str | None = None,
    planning_year: int | None = None,
) -> list[RiderRaceAllocationBuildOutcome]:
    filtered_requests = [
        request
        for request in requests
        if (team_slug is None or request.team_slug == team_slug)
        and (planning_year is None or request.planning_year == planning_year)
    ]
    resolved_output_root = Path(output_root) if output_root is not None else default_rider_race_allocation_output_root()

    outcomes: list[RiderRaceAllocationBuildOutcome] = []
    for request in filtered_requests:
        try:
            team_ev_df = load_team_ev_for_request(request)
            rider_scores_df = load_rider_scores_for_request(
                request,
                rider_scores_path=rider_scores_path,
                rider_baseline_summary_path=rider_baseline_summary_path,
                rider_backtest_summary_path=rider_backtest_summary_path,
            )
            artifacts = build_rider_race_allocation_artifacts(
                team_ev_df,
                rider_scores_df,
                roster_size=roster_size,
                top_riders_per_race=top_riders_per_race,
            )
            written_paths = write_rider_race_allocation_artifacts(
                artifacts,
                output_root=resolved_output_root,
            )
            outcomes.append(
                RiderRaceAllocationBuildOutcome(
                    team_slug=request.team_slug,
                    planning_year=request.planning_year,
                    success=True,
                    summary=artifacts.summary,
                    written_paths=written_paths,
                )
            )
        except Exception as exc:  # noqa: BLE001
            outcomes.append(
                RiderRaceAllocationBuildOutcome(
                    team_slug=request.team_slug,
                    planning_year=request.planning_year,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    return outcomes
