import argparse
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from uci_points_model import rider_race_allocation_batch as batch_module
from uci_points_model.rider_race_allocation import RiderRaceAllocationArtifacts

ROOT = Path(__file__).resolve().parents[1]


def test_discover_rider_race_allocation_requests_reads_saved_team_ev_artifacts(tmp_path: Path) -> None:
    team_ev_dir = tmp_path / "team_ev"
    team_ev_dir.mkdir(parents=True)
    pd.DataFrame([{"team_slug": "alpha-team", "planning_year": 2026, "race_name": "Alpha Classic"}]).to_csv(
        team_ev_dir / "alpha_team_2026_calendar_ev.csv",
        index=False,
    )
    pd.DataFrame([{"team_slug": "beta-team", "planning_year": 2027, "race_name": "Beta Classic"}]).to_csv(
        team_ev_dir / "beta_team_2027_calendar_ev.csv",
        index=False,
    )

    requests = batch_module.discover_rider_race_allocation_requests(team_ev_dir)

    assert [(request.team_slug, request.planning_year) for request in requests] == [
        ("alpha-team", 2026),
        ("beta-team", 2027),
    ]


def test_build_batch_rider_race_allocations_keeps_going_on_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requests = [
        batch_module.RiderRaceAllocationBuildRequest(
            team_slug="alpha-team",
            planning_year=2026,
            team_ev_path=tmp_path / "alpha_team_2026_calendar_ev.csv",
        ),
        batch_module.RiderRaceAllocationBuildRequest(
            team_slug="beta-team",
            planning_year=2026,
            team_ev_path=tmp_path / "beta_team_2026_calendar_ev.csv",
        ),
    ]
    writes: list[Path] = []

    monkeypatch.setattr(
        batch_module,
        "load_team_ev_for_request",
        lambda request: pd.DataFrame([{"team_slug": request.team_slug, "planning_year": request.planning_year}]),
    )

    def fake_load_rider_scores_for_request(request, **kwargs):
        if request.team_slug == "beta-team":
            raise ValueError("missing rider scores")
        return pd.DataFrame([{"rider_name": "Rider Alpha"}])

    monkeypatch.setattr(batch_module, "load_rider_scores_for_request", fake_load_rider_scores_for_request)
    monkeypatch.setattr(
        batch_module,
        "build_rider_race_allocation_artifacts",
        lambda team_ev_df, rider_scores_df, **kwargs: RiderRaceAllocationArtifacts(
            summary={
                "team_slug": str(team_ev_df.iloc[0]["team_slug"]),
                "planning_year": int(team_ev_df.iloc[0]["planning_year"]),
                "rider_model_name": "baseline_prior_points",
                "race_count": 4,
                "rider_count": len(rider_scores_df),
                "selected_pairings": 12,
            },
            allocation_table=pd.DataFrame(),
            race_plan=pd.DataFrame(),
            rider_load_summary=pd.DataFrame(),
        ),
    )

    def fake_write_rider_race_allocation_artifacts(artifacts, *, output_root=None):
        output_root_path = Path(output_root or tmp_path / "out")
        output_root_path.mkdir(parents=True, exist_ok=True)
        summary_path = output_root_path / f"{artifacts.summary['team_slug']}.json"
        writes.append(summary_path)
        summary_path.write_text("{}\n")
        return {"summary_path": summary_path}

    monkeypatch.setattr(batch_module, "write_rider_race_allocation_artifacts", fake_write_rider_race_allocation_artifacts)

    outcomes = batch_module.build_batch_rider_race_allocations(
        requests,
        rider_scores_path=tmp_path / "scores.csv",
        rider_baseline_summary_path=tmp_path / "baseline.json",
        rider_backtest_summary_path=tmp_path / "backtest.json",
        output_root=tmp_path / "allocations",
    )

    assert [(outcome.team_slug, outcome.success) for outcome in outcomes] == [
        ("alpha-team", True),
        ("beta-team", False),
    ]
    assert outcomes[0].summary == {
        "team_slug": "alpha-team",
        "planning_year": 2026,
        "rider_model_name": "baseline_prior_points",
        "race_count": 4,
        "rider_count": 1,
        "selected_pairings": 12,
    }
    assert "ValueError: missing rider scores" == outcomes[1].error
    assert writes == [tmp_path / "allocations" / "alpha-team.json"]


def test_batch_script_reports_failed_team_seasons(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_batch_script_module()
    monkeypatch.setattr(
        script,
        "parse_args",
        lambda: argparse.Namespace(
            team_ev_root="data/team_ev",
            rider_scores_path="data/model_outputs/rider_season_threshold_scores.csv",
            rider_baseline_summary_path="data/model_outputs/rider_threshold_baseline_summary.json",
            rider_backtest_summary_path="data/model_outputs/rider_threshold_backtest_summary.json",
            output_root="data/model_outputs/rider_race_allocations",
            team_slug=None,
            planning_year=None,
            roster_size=7,
            top_riders_per_race=3,
        ),
    )
    monkeypatch.setattr(script, "discover_rider_race_allocation_requests", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        script,
        "build_batch_rider_race_allocations",
        lambda *args, **kwargs: [
            batch_module.RiderRaceAllocationBuildOutcome(
                team_slug="alpha-team",
                planning_year=2026,
                success=True,
                summary={"rider_model_name": "baseline_prior_points", "race_count": 4, "rider_count": 10, "selected_pairings": 28},
            ),
            batch_module.RiderRaceAllocationBuildOutcome(
                team_slug="beta-team",
                planning_year=2026,
                success=False,
                error="RuntimeError: boom",
            ),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        script.main()

    assert exc.value.code == 1
    stdout = capsys.readouterr().out
    assert "SUCCESS alpha-team 2026 model=baseline_prior_points races=4 riders=10 selected_pairings=28" in stdout
    assert "FAILED beta-team 2026: RuntimeError: boom" in stdout
    assert "FAILED_TEAM_SEASONS=beta-team:2026" in stdout


def _load_batch_script_module():
    module_path = ROOT / "scripts" / "build_all_rider_race_allocations.py"
    spec = importlib.util.spec_from_file_location("build_all_rider_race_allocations_test", module_path)
    assert spec is not None and spec.loader is not None
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)
    return script_module
