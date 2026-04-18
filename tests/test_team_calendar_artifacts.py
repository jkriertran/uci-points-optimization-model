import argparse
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from uci_points_model import team_calendar_artifacts as module

ROOT = Path(__file__).resolve().parents[1]


def test_load_tracked_team_configs_filters_enabled_and_uses_blank_as_true(tmp_path) -> None:
    manifest_path = tmp_path / "tracked_proteams_2026.csv"
    manifest_path.write_text(
        "team_slug,pcs_team_slug,team_name,planning_year,profile_path,enabled,notes\n"
        "alpha-team-2026,alpha-team-2026,Alpha Team,2026,,,blank enabled stays true\n"
        "beta-team,beta-team-2026,Beta Team,2026,,false,disabled\n"
    )

    configs = module.load_tracked_team_configs(manifest_path, enabled_only=True)

    assert len(configs) == 1
    assert configs[0].team_slug == "alpha-team"
    assert configs[0].artifact_stem == "alpha_team_2026"
    assert configs[0].profile_path is None


def test_load_tracked_team_configs_rejects_missing_required_values(tmp_path) -> None:
    manifest_path = tmp_path / "tracked_proteams_2026.csv"
    manifest_path.write_text(
        "team_slug,pcs_team_slug,team_name,planning_year,profile_path,enabled,notes\n"
        "alpha-team,alpha-team-2026,,2026,,true,\n"
    )

    with pytest.raises(ValueError, match="missing team_name"):
        module.load_tracked_team_configs(manifest_path)


def test_resolve_team_profile_merges_defaults_and_manifest_identity_wins(tmp_path) -> None:
    default_profile_path = tmp_path / "default_profile.json"
    default_profile_path.write_text(
        """
{
  "archetype_key": "balanced_opportunist",
  "archetype_label": "Balanced Opportunist",
  "archetype_description": "No single dominant specialty, with a broad point-seeking profile across multiple race shapes.",
  "team_slug": "",
  "pcs_team_slug": "",
  "planning_year": 2026,
  "team_name": "Default Team",
  "strength_weights": {
    "one_day": 0.2,
    "stage_hunter": 0.2,
    "gc": 0.2,
    "time_trial": 0.1,
    "all_round": 0.2,
    "sprint_bonus": 0.1
  },
  "team_fit_floor": 0.7,
  "team_fit_range": 0.3,
  "execution_rules": {
    "1.1": 0.4,
    "1.Pro": 0.3
  },
  "participation_rules": {
    "completed": 1.0,
    "calendar_seed": 0.7
  }
}
""".strip()
    )
    override_path = tmp_path / "override_profile.json"
    override_path.write_text(
        """
{
  "team_slug": "wrong-team",
  "pcs_team_slug": "wrong-team-2026",
  "team_name": "Wrong Team",
  "strength_weights": {
    "one_day": 0.55,
    "stage_hunter": 0.10,
    "gc": 0.10,
    "time_trial": 0.05,
    "all_round": 0.10,
    "sprint_bonus": 0.10
  },
  "execution_rules": {
    "1.Pro": 0.42
  }
}
""".strip()
    )
    team = module.TrackedTeamConfig(
        team_slug="demo-team",
        pcs_team_slug="demo-team-2026",
        team_name="Demo Team",
        planning_year=2026,
        profile_path=override_path,
    )

    resolved_profile = module.resolve_team_profile(team, default_profile_path=default_profile_path)

    assert resolved_profile["team_slug"] == "demo-team"
    assert resolved_profile["pcs_team_slug"] == "demo-team-2026"
    assert resolved_profile["team_name"] == "Demo Team"
    assert resolved_profile["planning_year"] == 2026
    assert resolved_profile["strength_weights"]["one_day"] == 0.55
    assert resolved_profile["strength_weights"]["gc"] == 0.1
    assert resolved_profile["execution_rules"]["1.1"] == 0.4
    assert resolved_profile["execution_rules"]["1.Pro"] == 0.42
    assert resolved_profile["participation_rules"]["calendar_seed"] == 0.7
    assert resolved_profile["archetype_label"]


def test_resolve_team_profile_raises_for_missing_override_file(tmp_path) -> None:
    default_profile_path = tmp_path / "default_profile.json"
    default_profile_path.write_text('{"team_slug":"","pcs_team_slug":"","planning_year":2026,"team_name":"Default"}')
    team = module.TrackedTeamConfig(
        team_slug="missing-team",
        pcs_team_slug="missing-team-2026",
        team_name="Missing Team",
        planning_year=2026,
        profile_path=tmp_path / "missing_override.json",
    )

    with pytest.raises(FileNotFoundError):
        module.resolve_team_profile(team, default_profile_path=default_profile_path)


def test_build_team_calendar_ev_artifacts_and_write_outputs(monkeypatch, tmp_path) -> None:
    default_profile_path = _write_default_profile(tmp_path)
    override_path = tmp_path / "override_profile.json"
    override_path.write_text(
        '{"weight_fit_method":"projected_quadratic_fit_v1","weight_fit_summary":{"known_race_count":8,"rmse":4.2}}'
    )
    team = module.TrackedTeamConfig(
        team_slug="demo-team",
        pcs_team_slug="demo-team-2026",
        team_name="Demo Team",
        planning_year=2026,
        profile_path=override_path,
    )
    paths = module.resolve_team_artifact_paths(
        team.team_slug,
        team.planning_year,
        calendar_path=tmp_path / "team_calendars" / "demo_team_2026_latest.csv",
        changelog_path=tmp_path / "team_calendars" / "demo_team_2026_changelog.csv",
        actual_points_path=tmp_path / "team_results" / "demo_team_2026_actual_points.csv",
        ev_output_path=tmp_path / "team_ev" / "demo_team_2026_calendar_ev.csv",
        summary_output_path=tmp_path / "team_ev" / "demo_team_2026_calendar_ev_summary.csv",
        readme_path=tmp_path / "team_ev" / "README.md",
        dictionary_path=tmp_path / "team_ev" / "data_dictionary.md",
    )

    monkeypatch.setattr(module, "build_live_team_calendar", _fake_live_team_calendar)
    monkeypatch.setattr(module, "build_actual_points_table", _fake_actual_points_table)
    monkeypatch.setattr(module, "build_historical_target_summary", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(module, "build_team_calendar_ev", _fake_calendar_ev)
    monkeypatch.setattr(module, "summarize_team_calendar_ev", _fake_summary)

    bundle = module.build_team_calendar_ev_artifacts(
        team,
        default_profile_path=default_profile_path,
        paths=paths,
        refresh_calendar=True,
        as_of_date="2026-04-17",
        scraped_at_utc="2026-04-17T00:00:00+00:00",
        detected_at_utc="2026-04-17T00:00:00+00:00",
        checked_at_utc="2026-04-17T00:00:00+00:00",
    )

    assert len(bundle.calendar_df) == 1
    assert len(bundle.changelog_df) == 1
    assert len(bundle.actual_points_df) == 1
    assert len(bundle.calendar_ev_df) == 1
    assert len(bundle.summary_df) == 1
    assert "built_at_utc" not in bundle.metadata
    assert bundle.metadata["team_profile"]["archetype_key"] == "balanced_opportunist"
    assert bundle.metadata["team_profile"]["archetype_label"] == "Balanced Opportunist"
    assert bundle.metadata["team_profile"]["profile_confidence"] == "low"
    assert bundle.metadata["team_profile"]["weight_fit_method"] == "projected_quadratic_fit_v1"
    assert bundle.metadata["team_profile"]["weight_fit_summary"]["known_race_count"] == 8

    module.write_team_calendar_ev_artifacts(bundle, write_changelog=True, write_shared_docs=True)

    assert paths.calendar_path.exists()
    assert paths.changelog_path.exists()
    assert paths.actual_points_path.exists()
    assert paths.ev_output_path.exists()
    assert paths.summary_output_path.exists()
    assert paths.metadata_output_path.exists()
    assert paths.readme_path.exists()
    assert paths.dictionary_path.exists()


def test_build_team_calendar_ev_artifacts_metadata_is_stable(monkeypatch, tmp_path) -> None:
    default_profile_path = _write_default_profile(tmp_path)
    override_path = tmp_path / "override_profile.json"
    override_path.write_text("{}")
    team = module.TrackedTeamConfig(
        team_slug="stable-team",
        pcs_team_slug="stable-team-2026",
        team_name="Stable Team",
        planning_year=2026,
        profile_path=override_path,
    )

    monkeypatch.setattr(module, "build_live_team_calendar", _fake_live_team_calendar)
    monkeypatch.setattr(module, "build_actual_points_table", _fake_actual_points_table)
    monkeypatch.setattr(module, "build_historical_target_summary", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(module, "build_team_calendar_ev", _fake_calendar_ev)
    monkeypatch.setattr(module, "summarize_team_calendar_ev", _fake_summary)

    bundle_one = module.build_team_calendar_ev_artifacts(
        team,
        default_profile_path=default_profile_path,
        refresh_calendar=True,
        as_of_date="2026-04-17",
        scraped_at_utc="2026-04-17T00:00:00+00:00",
        detected_at_utc="2026-04-17T00:00:00+00:00",
        checked_at_utc="2026-04-17T00:00:00+00:00",
    )
    bundle_two = module.build_team_calendar_ev_artifacts(
        team,
        default_profile_path=default_profile_path,
        refresh_calendar=True,
        as_of_date="2026-04-17",
        scraped_at_utc="2026-04-17T00:00:00+00:00",
        detected_at_utc="2026-04-17T00:00:00+00:00",
        checked_at_utc="2026-04-17T00:00:00+00:00",
    )

    assert bundle_one.metadata == bundle_two.metadata
    assert bundle_one.metadata["team_profile"]["archetype_description"]
    assert bundle_one.metadata["team_profile"]["strength_weight_rationale"]["one_day"]


def test_build_team_calendar_ev_artifacts_can_reuse_saved_actual_points(monkeypatch, tmp_path) -> None:
    default_profile_path = _write_default_profile(tmp_path)
    override_path = tmp_path / "override_profile.json"
    override_path.write_text("{}")
    team = module.TrackedTeamConfig(
        team_slug="saved-actuals-team",
        pcs_team_slug="saved-actuals-team-2026",
        team_name="Saved Actuals Team",
        planning_year=2026,
        profile_path=override_path,
    )
    paths = module.resolve_team_artifact_paths(
        team.team_slug,
        team.planning_year,
        calendar_path=tmp_path / "team_calendars" / "saved_actuals_team_2026_latest.csv",
        changelog_path=tmp_path / "team_calendars" / "saved_actuals_team_2026_changelog.csv",
        actual_points_path=tmp_path / "team_results" / "saved_actuals_team_2026_actual_points.csv",
        ev_output_path=tmp_path / "team_ev" / "saved_actuals_team_2026_calendar_ev.csv",
        summary_output_path=tmp_path / "team_ev" / "saved_actuals_team_2026_calendar_ev_summary.csv",
        readme_path=tmp_path / "team_ev" / "README.md",
        dictionary_path=tmp_path / "team_ev" / "data_dictionary.md",
    )
    paths.actual_points_path.parent.mkdir(parents=True, exist_ok=True)
    paths.actual_points_path.write_text(
        "team_slug,team_name,planning_year,race_id,race_name,category,date_label,status,actual_points,rider_count,source_url,pcs_race_slug,checked_at_utc,notes\n"
        "saved-actuals-team,Saved Actuals Team,2026,97,GP la Marseillaise,1.1,01.02,completed,19.0,6,https://example.com,gp-la-marseillaise,2026-04-17T00:00:00+00:00,\n"
    )

    monkeypatch.setattr(module, "build_live_team_calendar", _fake_live_team_calendar)
    monkeypatch.setattr(module, "build_actual_points_table", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not refresh actuals")))
    monkeypatch.setattr(module, "build_historical_target_summary", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(module, "build_team_calendar_ev", _fake_calendar_ev)
    monkeypatch.setattr(module, "summarize_team_calendar_ev", _fake_summary)

    bundle = module.build_team_calendar_ev_artifacts(
        team,
        default_profile_path=default_profile_path,
        paths=paths,
        refresh_calendar=True,
        refresh_actual_points=False,
        as_of_date="2026-04-17",
    )

    assert float(bundle.actual_points_df.iloc[0]["actual_points"]) == 19.0


def test_build_tracked_team_calendar_ev_keeps_going_on_failures(tmp_path) -> None:
    success_team = module.TrackedTeamConfig(
        team_slug="alpha-team",
        pcs_team_slug="alpha-team-2026",
        team_name="Alpha Team",
        planning_year=2026,
    )
    failing_team = module.TrackedTeamConfig(
        team_slug="beta-team",
        pcs_team_slug="beta-team-2026",
        team_name="Beta Team",
        planning_year=2026,
    )
    writes: list[str] = []
    docs_writes: list[str] = []

    def fake_build_bundle(team, **kwargs):
        if team.team_slug == "beta-team":
            raise RuntimeError("boom")
        return _build_dummy_bundle(team, tmp_path)

    def fake_write_bundle(bundle, **kwargs):
        writes.append(bundle.team.team_slug)

    def fake_write_shared_docs(readme_path, dictionary_path, readme_text, dictionary_text):
        docs_writes.append(f"{readme_path}|{dictionary_path}")

    outcomes = module.build_tracked_team_calendar_ev(
        [success_team, failing_team],
        build_bundle_fn=fake_build_bundle,
        write_bundle_fn=fake_write_bundle,
        write_shared_docs_fn=fake_write_shared_docs,
    )

    assert [outcome.team_slug for outcome in outcomes] == ["alpha-team", "beta-team"]
    assert [outcome.success for outcome in outcomes] == [True, False]
    assert writes == ["alpha-team"]
    assert len(docs_writes) == 1
    assert "RuntimeError: boom" in outcomes[1].error


def test_batch_script_reports_failed_team_slugs(monkeypatch, capsys) -> None:
    script = _load_batch_script_module()
    monkeypatch.setattr(
        script,
        "parse_args",
        lambda: argparse.Namespace(manifest_path="config/tracked_proteams_2026.csv", team_slug=None, as_of_date=None),
    )
    monkeypatch.setattr(script, "load_tracked_team_configs", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        script,
        "build_tracked_team_calendar_ev",
        lambda *args, **kwargs: [
            module.TeamBuildOutcome(team_slug="alpha-team", success=True),
            module.TeamBuildOutcome(team_slug="beta-team", success=False, error="RuntimeError: boom"),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        script.main()

    assert exc.value.code == 1
    stdout = capsys.readouterr().out
    assert "SUCCESS alpha-team" in stdout
    assert "FAILED beta-team: RuntimeError: boom" in stdout
    assert "FAILED_TEAM_SLUGS=beta-team" in stdout


def _write_default_profile(tmp_path: Path) -> Path:
    default_profile_path = tmp_path / "default_profile.json"
    default_profile_path.write_text(
        """
{
  "archetype_key": "balanced_opportunist",
  "archetype_label": "Balanced Opportunist",
  "archetype_description": "No single dominant specialty, with a broad point-seeking profile across multiple race shapes.",
  "profile_confidence": "low",
  "profile_rationale": [
    "This is the generic baseline when a team-specific override has not been authored yet."
  ],
  "team_slug": "",
  "pcs_team_slug": "",
  "planning_year": 2026,
  "team_name": "Default Team",
  "strength_weights": {
    "one_day": 0.2,
    "stage_hunter": 0.2,
    "gc": 0.2,
    "time_trial": 0.1,
    "all_round": 0.2,
    "sprint_bonus": 0.1
  },
  "team_fit_floor": 0.7,
  "team_fit_range": 0.3,
  "execution_rules": {
    "1.1": 0.4,
    "1.Pro": 0.3
  },
  "participation_rules": {
    "completed": 1.0,
    "calendar_seed": 0.7
  }
}
""".strip()
    )
    return default_profile_path


def _fake_live_team_calendar(*args, **kwargs) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "team_slug": kwargs["team_slug"],
                "team_name": kwargs["team_name"],
                "planning_year": kwargs["planning_year"],
                "source": "team_program_live",
                "scraped_at_utc": kwargs["scraped_at_utc"] or "2026-04-17T00:00:00+00:00",
                "race_id": 97,
                "race_name": "GP la Marseillaise",
                "category": "1.1",
                "date_label": "01.02",
                "month": 2,
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "status": "completed",
                "team_calendar_status": "active",
                "source_url": "https://example.com",
                "pcs_race_slug": "gp-la-marseillaise",
                "observed_race_name": "GP la Marseillaise",
                "matched_via": "normalized_name",
                "notes": "matched_via=normalized_name",
                "overlap_group": "",
            }
        ]
    )


def _fake_actual_points_table(*args, **kwargs) -> pd.DataFrame:
    team_calendar = kwargs["team_calendar"]
    row = team_calendar.iloc[0]
    return pd.DataFrame(
        [
            {
                "team_slug": row["team_slug"],
                "team_name": row["team_name"],
                "planning_year": int(row["planning_year"]),
                "race_id": int(row["race_id"]),
                "race_name": row["race_name"],
                "category": row["category"],
                "date_label": row["date_label"],
                "status": row["status"],
                "actual_points": 12.0,
                "rider_count": 6,
                "source_url": row["source_url"],
                "pcs_race_slug": row["pcs_race_slug"],
                "checked_at_utc": kwargs["checked_at_utc"] or "2026-04-17T00:00:00+00:00",
                "notes": "",
            }
        ]
    )


def _fake_calendar_ev(*args, **kwargs) -> pd.DataFrame:
    row = kwargs["team_calendar"].iloc[0]
    return pd.DataFrame(
        [
            {
                "team_slug": row["team_slug"],
                "team_name": row["team_name"],
                "planning_year": int(row["planning_year"]),
                "race_id": int(row["race_id"]),
                "race_name": row["race_name"],
                "category": row["category"],
                "date_label": row["date_label"],
                "month": int(row["month"]),
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "pcs_race_slug": row["pcs_race_slug"],
                "historical_years_analyzed": 3,
                "race_type": "One-day",
                "route_profile": "one-day",
                "avg_top10_points": 80.0,
                "avg_winner_points": 30.0,
                "avg_points_efficiency": 2.0,
                "avg_stage_top10_points": 0.0,
                "avg_stage_count": 0.0,
                "avg_top10_field_form": 4.5,
                "base_opportunity_index": 0.5,
                "base_opportunity_points": 40.0,
                "specialty_fit_score": 0.5,
                "sprint_fit_bonus": 0.1,
                "team_fit_score": 0.6,
                "team_fit_multiplier": 0.88,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.4,
                "expected_points": 14.08,
                "actual_points": 12.0,
                "ev_gap": -2.08,
                "status": row["status"],
                "team_calendar_status": row["team_calendar_status"],
                "source": row["source"],
                "overlap_group": row["overlap_group"],
                "notes": row["notes"],
                "as_of_date": kwargs["as_of_date"] or "2026-04-17",
            }
        ]
    )


def _fake_summary(calendar_ev_df: pd.DataFrame) -> pd.DataFrame:
    row = calendar_ev_df.iloc[0]
    return pd.DataFrame(
        [
            {
                "team_slug": row["team_slug"],
                "planning_year": int(row["planning_year"]),
                "as_of_date": row["as_of_date"],
                "total_expected_points": float(row["expected_points"]),
                "completed_expected_points": float(row["expected_points"]),
                "remaining_expected_points": 0.0,
                "actual_points_known": float(row["actual_points"]),
                "ev_gap_known": float(row["ev_gap"]),
                "race_count": 1,
                "completed_race_count": 1,
                "remaining_race_count": 0,
            }
        ]
    )


def _build_dummy_bundle(team: module.TrackedTeamConfig, tmp_path: Path) -> module.TeamCalendarEvArtifacts:
    paths = module.resolve_team_artifact_paths(
        team.team_slug,
        team.planning_year,
        calendar_path=tmp_path / f"{team.team_slug}_latest.csv",
        changelog_path=tmp_path / f"{team.team_slug}_changelog.csv",
        actual_points_path=tmp_path / f"{team.team_slug}_actual_points.csv",
        ev_output_path=tmp_path / f"{team.team_slug}_calendar_ev.csv",
        summary_output_path=tmp_path / f"{team.team_slug}_calendar_ev_summary.csv",
        readme_path=tmp_path / "README.md",
        dictionary_path=tmp_path / "data_dictionary.md",
    )
    empty_df = pd.DataFrame()
    summary_df = pd.DataFrame([{"team_slug": team.team_slug, "planning_year": team.planning_year, "as_of_date": "2026-04-17"}])
    return module.TeamCalendarEvArtifacts(
        team=team,
        team_profile={},
        paths=paths,
        calendar_df=empty_df,
        changelog_df=empty_df,
        actual_points_df=empty_df,
        calendar_ev_df=empty_df,
        summary_df=summary_df,
        metadata={"team_slug": team.team_slug},
        readme_text="readme",
        dictionary_text="dictionary",
    )


def _load_batch_script_module():
    module_path = ROOT / "scripts" / "build_all_proteam_calendar_ev.py"
    spec = importlib.util.spec_from_file_location("build_all_proteam_calendar_ev_test", module_path)
    assert spec is not None and spec.loader is not None
    script_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script_module)
    return script_module
