from pathlib import Path

import pandas as pd
import pytest

import app as app_module


def test_discover_team_calendar_ev_datasets_finds_multiple_team_seasons(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    team_ev_dir = Path("data/team_ev")
    team_calendars_dir = Path("data/team_calendars")
    team_results_dir = Path("data/team_results")
    team_ev_dir.mkdir(parents=True)
    team_calendars_dir.mkdir(parents=True)
    team_results_dir.mkdir(parents=True)

    _write_team_ev_artifacts(
        artifact_stem="alpha_team_2026",
        team_slug="alpha-team",
        team_name="Alpha Team",
        planning_year=2026,
    )
    _write_team_ev_artifacts(
        artifact_stem="beta_team_2026",
        team_slug="beta-team",
        team_name="Beta Team",
        planning_year=2026,
    )

    app_module.discover_team_calendar_ev_datasets.clear()
    datasets = app_module.discover_team_calendar_ev_datasets()

    assert len(datasets) == 2
    assert datasets["label"].tolist() == ["Alpha Team (2026)", "Beta Team (2026)"]
    assert datasets["team_slug"].tolist() == ["alpha-team", "beta-team"]


def test_normalize_team_profile_weights_returns_relative_emphasis() -> None:
    normalized = app_module._normalize_team_profile_weights(  # noqa: SLF001
        {"one_day": 2.0, "stage_hunter": 1.0, "gc": 0.0, "time_trial": 0.0, "all_round": 1.0, "sprint_bonus": 0.0}
    )

    assert round(sum(normalized.values()), 6) == 1.0
    assert normalized["one_day"] > normalized["stage_hunter"]
    assert normalized["stage_hunter"] == normalized["all_round"]


def test_team_calendar_ev_view_mode_labels_use_reader_first_copy() -> None:
    assert app_module._team_calendar_ev_view_mode_labels() == [  # noqa: SLF001
        "Active schedule",
        "Full saved calendar",
        "Completed races only",
    ]


def test_filtered_team_calendar_ev_active_schedule_excludes_cancelled() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {"race_name": "Open", "status": "scheduled"},
            {"race_name": "Done", "status": "completed"},
            {"race_name": "Off", "status": "cancelled"},
        ]
    )

    filtered_df = app_module._filtered_team_calendar_ev(calendar_ev_df, "Active schedule")  # noqa: SLF001

    assert filtered_df["race_name"].tolist() == ["Open", "Done"]


def test_team_calendar_ev_primary_metrics_demote_secondary_facts() -> None:
    summary_row = {
        "total_expected_points": 100.0,
        "completed_expected_points": 50.0,
        "remaining_expected_points": 50.0,
        "actual_points_known": 48.0,
        "ev_gap_known": -2.0,
        "race_count": 10,
    }

    primary_metrics = app_module._team_calendar_ev_primary_metrics(summary_row)  # noqa: SLF001
    secondary_facts = app_module._team_calendar_ev_secondary_facts(summary_row)  # noqa: SLF001

    assert primary_metrics == [
        ("Total expected", "100.0"),
        ("Actual points known", "48.0"),
        ("Remaining expected", "50.0"),
        ("EV gap known", "-2.0"),
    ]
    assert secondary_facts == ["Completed expected: 50.0", "Race count: 10"]


def test_team_calendar_ev_primary_metrics_use_counted_snapshot_when_available(monkeypatch) -> None:
    summary_row = {
        "total_expected_points": 100.0,
        "completed_expected_points": 50.0,
        "remaining_expected_points": 50.0,
        "actual_points_known": 2882.0,
        "ev_gap_known": -2.0,
        "race_count": 10,
    }
    metadata = {"pcs_team_slug": "unibet-rose-rockets-2026"}

    monkeypatch.setattr(
        app_module,
        "load_proteam_risk_snapshot",
        lambda scope: pd.DataFrame(
            [
                {
                    "team_slug": "unibet-rose-rockets-2026",
                    "team_total_points": 2864.0,
                }
            ]
        ),
    )

    primary_metrics = app_module._team_calendar_ev_primary_metrics(summary_row, metadata)  # noqa: SLF001
    secondary_facts = app_module._team_calendar_ev_secondary_facts(summary_row, metadata)  # noqa: SLF001

    assert primary_metrics == [
        ("Total expected", "100.0"),
        ("Actual points known", "2864.0"),
        ("Remaining expected", "50.0"),
        ("EV gap known", "-2.0"),
    ]
    assert secondary_facts == [
        "All UCI points tracked: 2882.0",
        "Non-counted UCI points: 18.0",
        "Completed expected: 50.0",
        "Race count: 10",
    ]


def test_team_calendar_ev_secondary_facts_handle_counted_points_above_tracked_total(monkeypatch) -> None:
    summary_row = {
        "total_expected_points": 100.0,
        "completed_expected_points": 50.0,
        "remaining_expected_points": 50.0,
        "actual_points_known": 48.0,
        "ev_gap_known": -2.0,
        "race_count": 10,
    }
    metadata = {"pcs_team_slug": "alpha-team-2026"}

    monkeypatch.setattr(
        app_module,
        "load_proteam_risk_snapshot",
        lambda scope: pd.DataFrame(
            [
                {
                    "team_slug": "alpha-team-2026",
                    "team_total_points": 60.0,
                }
            ]
        ),
    )

    primary_metrics = app_module._team_calendar_ev_primary_metrics(summary_row, metadata)  # noqa: SLF001
    secondary_facts = app_module._team_calendar_ev_secondary_facts(summary_row, metadata)  # noqa: SLF001

    assert primary_metrics == [
        ("Total expected", "100.0"),
        ("Actual points known", "60.0"),
        ("Remaining expected", "50.0"),
        ("EV gap known", "-2.0"),
    ]
    assert secondary_facts == [
        "All UCI points tracked: 48.0",
        "Counted points outside tracked set: 12.0",
        "Completed expected: 50.0",
        "Race count: 10",
    ]


def test_team_calendar_ev_detail_columns_split_reader_from_analyst_view() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {
                "race_name": "Race One",
                "category": "1.1",
                "start_date": "2026-04-17",
                "status": "completed",
                "base_opportunity_points": 40.0,
                "team_fit_multiplier": 0.85,
                "participation_confidence": 0.95,
                "execution_multiplier": 0.4,
                "expected_points": 12.9,
                "actual_points": 10.0,
                "ev_gap": -2.9,
                "source": "team_program_live",
                "overlap_group": "",
                "notes": "Held back by weather.",
            }
        ]
    )

    reader_columns = app_module._team_calendar_ev_reader_detail_columns(calendar_ev_df)  # noqa: SLF001
    analyst_columns = app_module._team_calendar_ev_analyst_detail_columns(calendar_ev_df)  # noqa: SLF001

    assert reader_columns == [
        "race_name",
        "category",
        "start_date",
        "status",
        "expected_points",
        "actual_points",
        "ev_gap",
        "notes",
    ]
    assert analyst_columns == [
        "race_name",
        "category",
        "start_date",
        "status",
        "base_opportunity_points",
        "team_fit_multiplier",
        "participation_confidence",
        "execution_multiplier",
        "expected_points",
        "actual_points",
        "ev_gap",
        "source",
        "overlap_group",
        "notes",
    ]


def test_team_calendar_ev_guided_detail_frame_adds_plain_language_reads() -> None:
    calendar_ev_df = pd.DataFrame(
        [
            {
                "race_name": "Race One",
                "category": "1.1",
                "start_date": "2026-04-17",
                "status": "scheduled",
                "team_fit_multiplier": 0.97,
                "participation_confidence": 0.92,
                "execution_multiplier": 0.38,
                "expected_points": 12.9,
                "actual_points": 10.0,
                "ev_gap": -2.9,
                "notes": "Held back by weather.",
            },
            {
                "race_name": "Race Two",
                "category": "2.Pro",
                "start_date": "2026-04-18",
                "status": "completed",
                "team_fit_multiplier": 0.73,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.22,
                "expected_points": 8.4,
                "actual_points": 11.0,
                "ev_gap": 2.6,
                "notes": "",
            },
        ]
    )

    guided_df = app_module._team_calendar_ev_guided_detail_frame(calendar_ev_df)  # noqa: SLF001

    assert guided_df.columns.tolist() == [
        "Race",
        "Category",
        "Date",
        "Status",
        "Team fit read",
        "Start confidence",
        "Execution read",
        "Expected pts",
        "Actual pts",
        "EV gap",
        "Notes",
    ]
    assert guided_df.iloc[0]["Team fit read"] == "Strong fit (0.97)"
    assert guided_df.iloc[0]["Start confidence"] == "Likely (0.92)"
    assert guided_df.iloc[0]["Execution read"] == "Favorable conversion (0.38)"
    assert guided_df.iloc[1]["Team fit read"] == "Weak fit (0.73)"
    assert guided_df.iloc[1]["Start confidence"] == "Started (1.00)"
    assert guided_df.iloc[1]["Execution read"] == "Difficult conversion (0.22)"


def test_load_team_calendar_ev_metadata_falls_back_to_saved_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    team_ev_dir = Path("data/team_ev")
    team_profiles_dir = Path("data/team_profiles")
    team_calendars_dir = Path("data/team_calendars")
    team_results_dir = Path("data/team_results")
    team_ev_dir.mkdir(parents=True)
    team_profiles_dir.mkdir(parents=True)
    team_calendars_dir.mkdir(parents=True)
    team_results_dir.mkdir(parents=True)

    _write_team_ev_artifacts(
        artifact_stem="unibet_rose_rockets_2026",
        team_slug="unibet-rose-rockets",
        team_name="Unibet Rose Rockets",
        planning_year=2026,
    )
    (team_ev_dir / "unibet_rose_rockets_2026_calendar_ev_metadata.json").write_text(
        """
{
  "team_slug": "unibet-rose-rockets",
  "planning_year": 2026,
  "team_name": "Unibet Rose Rockets",
  "team_profile": {
    "strength_weights": {
      "one_day": 0.3
    },
    "execution_rules": {
      "1.1": 0.4
    }
  }
}
""".strip()
        + "\n"
    )
    (team_profiles_dir / "unibet_rose_rockets_2026_profile.json").write_text(
        """
{
  "team_slug": "unibet-rose-rockets",
  "planning_year": 2026,
  "team_name": "Unibet Rose Rockets",
  "archetype_label": "Classics + Sprint Opportunist",
  "archetype_description": "One-day and sprint-accessible profile.",
  "profile_confidence": "medium",
  "profile_rationale": ["Sprint-accessible races remain important."],
  "strength_weights": {
    "one_day": 0.28,
    "stage_hunter": 0.12
  },
  "participation_rules": {
    "completed": 1.0
  }
}
""".strip()
        + "\n"
    )

    app_module.discover_team_calendar_ev_datasets.clear()
    app_module.load_saved_team_profile.clear()
    app_module.load_team_calendar_ev_metadata.clear()

    metadata = app_module.load_team_calendar_ev_metadata("unibet-rose-rockets", 2026)

    assert metadata["team_profile"]["archetype_label"] == "Classics + Sprint Opportunist"
    assert metadata["team_profile"]["archetype_description"] == "One-day and sprint-accessible profile."
    assert metadata["team_profile"]["execution_rules"] == {"1.1": 0.4}
    assert metadata["team_profile"]["participation_rules"] == {"completed": 1.0}
    assert metadata["team_profile"]["strength_weights"]["one_day"] == 0.3
    assert metadata["team_profile"]["strength_weights"]["stage_hunter"] == 0.12


def test_build_team_profile_sandbox_frame_recomputes_expected_points() -> None:
    race_df = pd.DataFrame(
        [
            {
                "race_name": "Race One",
                "status": "scheduled",
                "base_opportunity_points": 40.0,
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.0,
                "sprint_bonus_signal": 0.0,
                "team_fit_score": 0.5,
                "team_fit_multiplier": 0.85,
                "expected_points": 13.6,
                "participation_confidence": 1.0,
                "execution_multiplier": 0.4,
            }
        ]
    )
    sandbox_profile = {
        "strength_weights": {
            "one_day": 1.0,
            "stage_hunter": 0.0,
            "gc": 0.0,
            "time_trial": 0.0,
            "all_round": 0.0,
            "sprint_bonus": 0.0,
        },
        "team_fit_floor": 0.7,
        "team_fit_range": 0.3,
    }

    scenario_df = app_module._build_team_profile_sandbox_frame(race_df, sandbox_profile)  # noqa: SLF001

    row = scenario_df.iloc[0]
    assert float(row["sandbox_team_fit_multiplier"]) == 1.0
    assert float(row["sandbox_expected_points"]) == 16.0
    assert float(row["expected_points_delta"]) == pytest.approx(2.4)


def test_ensure_team_profile_sandbox_state_repairs_missing_keys(monkeypatch) -> None:
    session_state = {
        "team_profile_sandbox_demo-team_2026_initialized": True,
        "team_profile_sandbox_demo-team_2026_one_day": 0.4,
    }
    monkeypatch.setattr(app_module.st, "session_state", session_state)

    app_module._ensure_team_profile_sandbox_state(  # noqa: SLF001
        "team_profile_sandbox_demo-team_2026",
        {
            "strength_weights": {
                "one_day": 0.2,
                "stage_hunter": 0.15,
                "gc": 0.15,
                "time_trial": 0.05,
                "all_round": 0.2,
                "sprint_bonus": 0.25,
            },
            "team_fit_floor": 0.7,
            "team_fit_range": 0.3,
        },
    )

    assert session_state["team_profile_sandbox_demo-team_2026_one_day"] == 0.4
    assert session_state["team_profile_sandbox_demo-team_2026_stage_hunter"] == 0.15
    assert session_state["team_profile_sandbox_demo-team_2026_team_fit_floor"] == 0.7
    assert session_state["team_profile_sandbox_demo-team_2026_team_fit_range"] == 0.3
    assert session_state["team_profile_sandbox_demo-team_2026_initialized"] is True


def test_team_profile_identity_context_reads_archetype_metadata() -> None:
    context = app_module._team_profile_identity_context(  # noqa: SLF001
        {
            "team_name": "Unibet Rose Rockets",
            "team_profile": {
                "archetype_key": "classic_sprint_opportunist",
                "archetype_label": "Classics + Sprint Opportunist",
                "archetype_description": "This profile favors one-day races and sprint-accessible opportunities.",
                "profile_confidence": "medium",
                "profile_rationale": ["Sprint-accessible races remain an important conversion lane."],
                "strength_weights": {
                    "one_day": 0.30,
                    "stage_hunter": 0.15,
                    "gc": 0.10,
                    "time_trial": 0.05,
                    "all_round": 0.15,
                    "sprint_bonus": 0.25,
                },
                "team_fit_floor": 0.7,
                "team_fit_range": 0.3,
                "execution_rules": {
                    "1.1": 0.4,
                    "1.Pro": 0.3,
                    "1.UWT": 0.18,
                    "2.1": 0.3,
                    "2.Pro": 0.25,
                    "2.UWT": 0.18,
                },
                "participation_rules": {
                    "completed": 1.0,
                    "program_confirmed": 0.95,
                    "observed_startlist": 0.95,
                    "calendar_seed": 0.7,
                    "overlap_penalty": 0.8,
                },
            },
        }
    )

    assert context["team_name"] == "Unibet Rose Rockets"
    assert context["archetype_label"] == "Classics + Sprint Opportunist"
    assert context["profile_confidence"] == "medium"
    assert context["profile_rationale"] == ["Sprint-accessible races remain an important conversion lane."]


def test_team_calendar_ev_freshness_context_flags_drift_when_calendar_is_newer() -> None:
    context = app_module._team_calendar_ev_freshness_context(  # noqa: SLF001
        {"as_of_date": "2026-04-17"},
        {"as_of_date": "2026-04-17"},
        pd.DataFrame([{"scraped_at_utc": "2026-04-18T00:28:20+00:00"}]),
    )

    assert context["ev_as_of"] == "2026-04-17"
    assert context["calendar_scraped_at"] == "2026-04-18T00:28:20+00:00"
    assert context["has_drift"] is True
    assert "older than the underlying team calendar snapshot" in context["warning_message"]


def test_team_calendar_ev_freshness_context_treats_same_day_as_in_sync() -> None:
    context = app_module._team_calendar_ev_freshness_context(  # noqa: SLF001
        {"as_of_date": "2026-04-18"},
        {"as_of_date": "2026-04-18"},
        pd.DataFrame([{"scraped_at_utc": "2026-04-18T14:22:00+00:00"}]),
    )

    assert context["has_drift"] is False
    assert context["warning_message"] == ""


def test_has_roster_scenario_inputs_requires_expected_columns() -> None:
    race_df = pd.DataFrame(
        [
            {
                "base_opportunity_points": 40.0,
                "team_fit_score": 0.5,
                "team_fit_multiplier": 0.85,
                "participation_confidence": 0.95,
                "execution_multiplier": 0.4,
                "expected_points": 12.9,
                "status": "scheduled",
                "source": "team_program_live",
                "overlap_group": "",
                "one_day_signal": 1.0,
                "stage_hunter_signal": 0.0,
                "gc_signal": 0.0,
                "time_trial_signal": 0.0,
                "all_round_signal": 0.2,
                "sprint_bonus_signal": 0.5,
            }
        ]
    )

    assert app_module._has_roster_scenario_inputs(race_df)  # noqa: SLF001
    assert not app_module._has_roster_scenario_inputs(race_df.drop(columns=["source"]))  # noqa: SLF001


def test_build_roster_scenario_assumption_frame_lists_fit_and_participation_rules() -> None:
    frame = app_module._build_roster_scenario_assumption_frame(  # noqa: SLF001
        {
            "team_fit_floor": 0.7,
            "team_fit_range": 0.3,
            "participation_rules": {
                "completed": 1.0,
                "program_confirmed": 0.95,
                "observed_startlist": 0.95,
                "calendar_seed": 0.7,
                "overlap_penalty": 0.8,
            },
            "strength_weights": {
                "one_day": 0.30,
                "stage_hunter": 0.15,
                "gc": 0.10,
                "time_trial": 0.05,
                "all_round": 0.15,
                "sprint_bonus": 0.25,
            },
        },
        {
            "team_fit_floor": 0.62,
            "team_fit_range": 0.22,
            "participation_rules": {
                "completed": 1.0,
                "program_confirmed": 0.82,
                "observed_startlist": 0.88,
                "calendar_seed": 0.55,
                "overlap_penalty": 0.65,
            },
            "strength_weights": {
                "one_day": 0.30,
                "stage_hunter": 0.15,
                "gc": 0.10,
                "time_trial": 0.05,
                "all_round": 0.15,
                "sprint_bonus": 0.25,
            },
        },
    )

    assert frame["Setting"].tolist()[:2] == ["Team-fit floor", "Team-fit range"]
    assert "Participation: calendar seed" in frame["Setting"].tolist()


def test_preferred_rider_threshold_model_name_uses_backtest_winner(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_rider_threshold_artifacts()

    app_module.load_rider_threshold_summary.clear()
    app_module.load_rider_threshold_backtest_summary.clear()

    assert app_module._preferred_rider_threshold_model_name() == "baseline_points_scoring_role"  # noqa: SLF001


def test_preferred_top5_proteam_model_name_uses_backtest_winner(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_top5_proteam_artifacts()

    app_module.load_top5_proteam_summary.clear()
    app_module.load_top5_proteam_backtest_summary.clear()

    assert app_module._preferred_top5_proteam_model_name() == "baseline_n_riders_150"  # noqa: SLF001


def test_team_top5_proteam_row_filters_active_team_and_season(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_top5_proteam_artifacts()

    app_module.load_team_season_top5_scores.clear()
    app_module.load_top5_proteam_summary.clear()
    app_module.load_top5_proteam_backtest_summary.clear()

    score_row = app_module._team_top5_proteam_row("alpha-team", 2026)  # noqa: SLF001

    assert score_row is not None
    assert str(score_row["team_base_slug"]) == "alpha-team"
    assert int(score_row["season"]) == 2026
    assert float(score_row["predicted_next_top5_probability"]) == 0.64
    assert str(score_row["model_name"]) == "baseline_n_riders_150"


def test_team_continuity_history_frame_keeps_observed_links_and_current_cycle_inference(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_top5_proteam_artifacts()

    app_module.load_team_season_panel.clear()
    app_module.load_team_season_top5_scores.clear()
    app_module.load_top5_proteam_summary.clear()
    app_module.load_top5_proteam_backtest_summary.clear()

    continuity_df = app_module._team_continuity_history_frame("alpha-team", 2026)  # noqa: SLF001

    assert continuity_df["season"].tolist() == [2024, 2025, 2026]
    assert continuity_df["team_name"].tolist() == ["Alpha Legacy", "Alpha Team", "Alpha Team"]
    assert continuity_df.loc[continuity_df["season"] == 2024, "next_team_name"].iloc[0] == "Alpha Team"
    assert continuity_df.loc[continuity_df["season"] == 2024, "continuity_source"].iloc[0] == "pcs_prev_link"
    assert continuity_df.loc[continuity_df["season"] == 2024, "next_proteam_rank"].iloc[0] == 4
    assert continuity_df.loc[continuity_df["season"] == 2025, "next_team_name"].iloc[0] == "Alpha Team"
    assert continuity_df.loc[continuity_df["season"] == 2025, "next_proteam_rank"].iloc[0] == 3
    assert (
        continuity_df.loc[continuity_df["season"] == 2025, "continuity_source"].iloc[0]
        == "base_slug_inferred_current_cycle"
    )
    assert pd.isna(continuity_df.loc[continuity_df["season"] == 2025, "next_top5_proteam"].iloc[0])
    assert continuity_df.loc[continuity_df["season"] == 2026, "continuity_status"].iloc[0] == "current_team_season"


def test_team_continuity_history_frame_uses_alias_for_current_cycle_rename(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    model_inputs_dir = Path("data/model_inputs")
    model_outputs_dir = Path("data/model_outputs")
    model_inputs_dir.mkdir(parents=True, exist_ok=True)
    model_outputs_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "season": 2025,
                "team_name": "Q36.5 Pro Cycling Team",
                "team_slug": "q365-pro-cycling-team-2025",
                "team_base_slug": "q365-pro-cycling-team",
                "proteam_rank": 4,
                "n_riders_150_plus": 5,
                "top5_share": 0.61,
                "next_season": pd.NA,
                "next_team_name": "",
                "next_team_slug": "",
                "next_proteam_rank": pd.NA,
                "next_top5_proteam": pd.NA,
                "continuity_source": "",
                "has_observed_next_season": False,
            },
            {
                "season": 2026,
                "team_name": "Pinarello Q36.5 Pro Cycling Team",
                "team_slug": "pinarello-q365-pro-cycling-team-2026",
                "team_base_slug": "pinarello-q365-pro-cycling-team",
                "proteam_rank": 2,
                "n_riders_150_plus": 4,
                "top5_share": 0.79,
                "next_season": pd.NA,
                "next_team_name": "",
                "next_team_slug": "",
                "next_proteam_rank": pd.NA,
                "next_top5_proteam": pd.NA,
                "continuity_source": "",
                "has_observed_next_season": False,
            },
        ]
    ).to_csv(model_inputs_dir / "team_season_panel.csv", index=False)
    pd.DataFrame(
        [
            {
                "season": 2026,
                "team_name": "Pinarello Q36.5 Pro Cycling Team",
                "team_slug": "pinarello-q365-pro-cycling-team-2026",
                "team_base_slug": "pinarello-q365-pro-cycling-team",
                "proteam_rank": 2,
                "n_riders_150_plus": 4,
                "top5_share": 0.79,
                "predicted_next_top5_probability": 0.18,
                "predicted_next_top5_label": 0,
                "model_name": "baseline_n_riders_150",
                "evaluation_split": "full_fit_team_panel",
            }
        ]
    ).to_csv(model_outputs_dir / "team_season_top5_scores.csv", index=False)
    (model_outputs_dir / "top5_proteam_baseline_summary.json").write_text('{"anchor_model_name":"baseline_n_riders_150"}\n')
    (model_outputs_dir / "top5_proteam_backtest_summary.json").write_text('{"winning_model_name":"baseline_n_riders_150"}\n')

    app_module.load_team_season_panel.clear()
    app_module.load_team_season_top5_scores.clear()
    app_module.load_top5_proteam_summary.clear()
    app_module.load_top5_proteam_backtest_summary.clear()

    continuity_df = app_module._team_continuity_history_frame("pinarello-q365-pro-cycling-team", 2026)  # noqa: SLF001

    assert continuity_df["season"].tolist() == [2025, 2026]
    assert continuity_df.loc[continuity_df["season"] == 2025, "team_name"].iloc[0] == "Q36.5 Pro Cycling Team"
    assert continuity_df.loc[continuity_df["season"] == 2025, "next_team_name"].iloc[0] == "Pinarello Q36.5 Pro Cycling Team"
    assert continuity_df.loc[continuity_df["season"] == 2025, "next_proteam_rank"].iloc[0] == 2
    assert (
        continuity_df.loc[continuity_df["season"] == 2025, "continuity_source"].iloc[0]
        == "identity_alias_inferred_current_cycle"
    )


def test_team_continuity_history_frame_uses_linked_panel_rank_for_observed_next_rank(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    model_inputs_dir = Path("data/model_inputs")
    model_outputs_dir = Path("data/model_outputs")
    model_inputs_dir.mkdir(parents=True, exist_ok=True)
    model_outputs_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "season": 2024,
                "team_name": "Alpha Legacy",
                "team_slug": "alpha-legacy-2024",
                "team_base_slug": "alpha-team",
                "proteam_rank": 6,
                "n_riders_150_plus": 3,
                "top5_share": 0.41,
                "next_season": 2025,
                "next_team_name": "Alpha Team",
                "next_team_slug": "alpha-team-2025",
                "next_proteam_rank": 99,
                "next_top5_proteam": 1,
                "continuity_source": "pcs_prev_link",
                "has_observed_next_season": True,
            },
            {
                "season": 2025,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2025",
                "team_base_slug": "alpha-team",
                "proteam_rank": 4,
                "n_riders_150_plus": 5,
                "top5_share": 0.49,
                "next_season": pd.NA,
                "next_team_name": "",
                "next_team_slug": "",
                "next_proteam_rank": pd.NA,
                "next_top5_proteam": pd.NA,
                "continuity_source": "",
                "has_observed_next_season": False,
            },
        ]
    ).to_csv(model_inputs_dir / "team_season_panel.csv", index=False)
    pd.DataFrame(
        [
            {
                "season": 2025,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2025",
                "team_base_slug": "alpha-team",
                "proteam_rank": 4,
                "n_riders_150_plus": 5,
                "top5_share": 0.49,
                "predicted_next_top5_probability": 0.58,
                "predicted_next_top5_label": 1,
                "model_name": "baseline_n_riders_150",
                "evaluation_split": "full_fit_team_panel",
            }
        ]
    ).to_csv(model_outputs_dir / "team_season_top5_scores.csv", index=False)
    (model_outputs_dir / "top5_proteam_baseline_summary.json").write_text('{"anchor_model_name":"baseline_n_riders_150"}\n')
    (model_outputs_dir / "top5_proteam_backtest_summary.json").write_text('{"winning_model_name":"baseline_n_riders_150"}\n')

    app_module.load_team_season_panel.clear()
    app_module.load_team_season_top5_scores.clear()
    app_module.load_top5_proteam_summary.clear()
    app_module.load_top5_proteam_backtest_summary.clear()

    continuity_df = app_module._team_continuity_history_frame("alpha-team", 2025)  # noqa: SLF001

    assert continuity_df["season"].tolist() == [2024, 2025]
    assert continuity_df.loc[continuity_df["season"] == 2024, "next_proteam_rank"].iloc[0] == 4


def test_team_rider_threshold_outlook_frame_filters_active_team_and_season(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_rider_threshold_artifacts()

    app_module.load_rider_season_threshold_scores.clear()
    app_module.load_rider_threshold_summary.clear()
    app_module.load_rider_threshold_backtest_summary.clear()

    outlook_df = app_module._team_rider_threshold_outlook_frame("alpha-team", 2026)  # noqa: SLF001

    assert outlook_df["rider_name"].tolist() == ["Rider Alpha", "Rider Beta"]
    assert outlook_df["predicted_rider_reaches_150_probability"].tolist() == [0.71, 0.42]
    assert (outlook_df["team_base_slug"] == "alpha-team").all()
    assert (outlook_df["season"] == 2026).all()


def test_team_rider_race_plan_frame_filters_team_and_view_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_rider_race_allocation_artifacts()

    app_module.load_rider_race_allocation_summary.clear()
    app_module.load_rider_race_plan.clear()
    app_module.load_rider_load_summary.clear()
    app_module.load_rider_race_allocations.clear()

    active_df = app_module._team_rider_race_plan_frame("alpha-team", 2026, "Active schedule")  # noqa: SLF001
    completed_df = app_module._team_rider_race_plan_frame("alpha-team", 2026, "Completed races only")  # noqa: SLF001

    assert active_df["race_name"].tolist() == ["Alpha Classic", "Alpha Tour"]
    assert completed_df["race_name"].tolist() == ["Alpha Classic"]
    assert (active_df["race_leader_rider"] == "Rider Alpha").all()
    assert (active_df["status"] != "cancelled").all()


def _write_team_ev_artifacts(*, artifact_stem: str, team_slug: str, team_name: str, planning_year: int) -> None:
    pd.DataFrame(
        [
            {
                "team_slug": team_slug,
                "planning_year": planning_year,
                "as_of_date": "2026-04-17",
                "total_expected_points": 100.0,
                "completed_expected_points": 50.0,
                "remaining_expected_points": 50.0,
                "actual_points_known": 48.0,
                "ev_gap_known": -2.0,
                "race_count": 10,
                "completed_race_count": 5,
                "remaining_race_count": 5,
            }
        ]
    ).to_csv(Path("data/team_ev") / f"{artifact_stem}_calendar_ev_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "team_slug": team_slug,
                "team_name": team_name,
                "planning_year": planning_year,
                "race_id": 1,
                "race_name": "Race One",
                "category": "1.1",
            }
        ]
    ).to_csv(Path("data/team_ev") / f"{artifact_stem}_calendar_ev.csv", index=False)
    pd.DataFrame([{"team_slug": team_slug}]).to_csv(Path("data/team_calendars") / f"{artifact_stem}_latest.csv", index=False)
    pd.DataFrame([{"team_slug": team_slug}]).to_csv(Path("data/team_results") / f"{artifact_stem}_actual_points.csv", index=False)


def _write_rider_threshold_artifacts() -> None:
    model_outputs_dir = Path("data/model_outputs")
    model_outputs_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "model_name": "baseline_points_scoring_role",
                "evaluation_split": "full_fit_panel",
                "season": 2026,
                "team_base_slug": "alpha-team",
                "rider_name": "Rider Alpha",
                "predicted_rider_reaches_150_probability": 0.71,
            },
            {
                "model_name": "baseline_points_scoring_role",
                "evaluation_split": "full_fit_panel",
                "season": 2026,
                "team_base_slug": "alpha-team",
                "rider_name": "Rider Beta",
                "predicted_rider_reaches_150_probability": 0.42,
            },
            {
                "model_name": "baseline_points_scoring_role",
                "evaluation_split": "full_fit_panel",
                "season": 2026,
                "team_base_slug": "beta-team",
                "rider_name": "Rider Gamma",
                "predicted_rider_reaches_150_probability": 0.88,
            },
            {
                "model_name": "baseline_prior_points",
                "evaluation_split": "full_fit_panel",
                "season": 2026,
                "team_base_slug": "alpha-team",
                "rider_name": "Legacy Rider",
                "predicted_rider_reaches_150_probability": 0.99,
            },
        ]
    ).to_csv(model_outputs_dir / "rider_season_threshold_scores.csv", index=False)
    (model_outputs_dir / "rider_threshold_baseline_summary.json").write_text(
        """
{
  "anchor_model_name": "baseline_prior_points"
}
""".strip()
        + "\n"
    )
    (model_outputs_dir / "rider_threshold_backtest_summary.json").write_text(
        """
{
  "winning_model_name": "baseline_points_scoring_role"
}
""".strip()
        + "\n"
    )


def _write_top5_proteam_artifacts() -> None:
    model_inputs_dir = Path("data/model_inputs")
    model_outputs_dir = Path("data/model_outputs")
    model_inputs_dir.mkdir(parents=True, exist_ok=True)
    model_outputs_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "season": 2024,
                "team_name": "Alpha Legacy",
                "team_slug": "alpha-legacy-2024",
                "team_base_slug": "alpha-team",
                "proteam_rank": 6,
                "n_riders_150_plus": 3,
                "top5_share": 0.41,
                "next_season": 2025,
                "next_team_name": "Alpha Team",
                "next_team_slug": "alpha-team-2025",
                "next_proteam_rank": 4,
                "next_top5_proteam": 1,
                "continuity_source": "pcs_prev_link",
                "has_observed_next_season": True,
            },
            {
                "season": 2025,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2025",
                "team_base_slug": "alpha-team",
                "proteam_rank": 4,
                "n_riders_150_plus": 5,
                "top5_share": 0.49,
                "next_season": pd.NA,
                "next_team_name": "",
                "next_team_slug": "",
                "next_proteam_rank": pd.NA,
                "next_top5_proteam": pd.NA,
                "continuity_source": "",
                "has_observed_next_season": False,
            },
            {
                "season": 2026,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2026",
                "team_base_slug": "alpha-team",
                "proteam_rank": 3,
                "n_riders_150_plus": 6,
                "top5_share": 0.53,
                "next_season": pd.NA,
                "next_team_name": "",
                "next_team_slug": "",
                "next_proteam_rank": pd.NA,
                "next_top5_proteam": pd.NA,
                "continuity_source": "",
                "has_observed_next_season": False,
            },
            {
                "season": 2026,
                "team_name": "Beta Team",
                "team_slug": "beta-team-2026",
                "team_base_slug": "beta-team",
                "proteam_rank": 1,
                "n_riders_150_plus": 8,
                "top5_share": 0.66,
                "next_season": pd.NA,
                "next_team_name": "",
                "next_team_slug": "",
                "next_proteam_rank": pd.NA,
                "next_top5_proteam": pd.NA,
                "continuity_source": "",
                "has_observed_next_season": False,
            },
        ]
    ).to_csv(model_inputs_dir / "team_season_panel.csv", index=False)
    pd.DataFrame(
        [
            {
                "prior_season": 2024,
                "next_season": 2025,
                "prior_team_name": "Alpha Legacy",
                "prior_team_slug": "alpha-legacy-2024",
                "team_base_slug": "alpha-team",
                "next_team_slug": "alpha-team-2025",
                "next_team_name": "Alpha Team",
                "continuity_source": "pcs_prev_link",
                "n_riders_150_plus": 3,
                "top5_share": 0.41,
                "next_top5_proteam": 1,
            }
        ]
    ).to_csv(model_inputs_dir / "top5_proteam_training_table.csv", index=False)
    pd.DataFrame(
        [
            {
                "season": 2025,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2025",
                "team_base_slug": "alpha-team",
                "proteam_rank": 4,
                "n_riders_150_plus": 5,
                "top5_share": 0.49,
                "predicted_next_top5_probability": 0.58,
                "predicted_next_top5_label": 1,
                "model_name": "baseline_n_riders_150",
                "evaluation_split": "full_fit_team_panel",
            },
            {
                "season": 2026,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2026",
                "team_base_slug": "alpha-team",
                "proteam_rank": 3,
                "n_riders_150_plus": 6,
                "top5_share": 0.53,
                "predicted_next_top5_probability": 0.64,
                "predicted_next_top5_label": 1,
                "model_name": "baseline_n_riders_150",
                "evaluation_split": "full_fit_team_panel",
            },
            {
                "season": 2026,
                "team_name": "Alpha Team",
                "team_slug": "alpha-team-2026",
                "team_base_slug": "alpha-team",
                "proteam_rank": 3,
                "n_riders_150_plus": 6,
                "top5_share": 0.53,
                "predicted_next_top5_probability": 0.21,
                "predicted_next_top5_label": 0,
                "model_name": "baseline_depth_concentration",
                "evaluation_split": "full_fit_team_panel",
            },
            {
                "season": 2026,
                "team_name": "Beta Team",
                "team_slug": "beta-team-2026",
                "team_base_slug": "beta-team",
                "proteam_rank": 1,
                "n_riders_150_plus": 8,
                "top5_share": 0.66,
                "predicted_next_top5_probability": 0.88,
                "predicted_next_top5_label": 1,
                "model_name": "baseline_n_riders_150",
                "evaluation_split": "full_fit_team_panel",
            },
        ]
    ).to_csv(model_outputs_dir / "team_season_top5_scores.csv", index=False)
    (model_outputs_dir / "top5_proteam_baseline_summary.json").write_text(
        """
{
  "anchor_model_name": "baseline_depth_concentration"
}
""".strip()
        + "\n"
    )
    (model_outputs_dir / "top5_proteam_backtest_summary.json").write_text(
        """
{
  "winning_model_name": "baseline_n_riders_150"
}
""".strip()
        + "\n"
    )
    pd.DataFrame(
        [
            {
                "model_name": "baseline_n_riders_150",
                "backtest_top_k_capture": 0.77,
            }
        ]
    ).to_csv(model_outputs_dir / "top5_proteam_backtest_benchmark.csv", index=False)


def _write_rider_race_allocation_artifacts() -> None:
    allocation_dir = Path("data/model_outputs/rider_race_allocations")
    allocation_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 1,
                "race_name": "Alpha Classic",
                "category": "1.1",
                "start_date": "2026-03-01",
                "status": "completed",
                "race_leader_rider": "Rider Alpha",
                "race_leader_specialty": "oneday",
                "top_recommended_riders": "Rider Alpha | Rider Beta",
                "selected_breakout_probability_mean": 0.64,
                "selected_specialty_match_mean": 0.71,
                "selected_allocation_score_total": 82.0,
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 2,
                "race_name": "Alpha Tour",
                "category": "2.1",
                "start_date": "2026-04-01",
                "status": "scheduled",
                "race_leader_rider": "Rider Alpha",
                "race_leader_specialty": "gc",
                "top_recommended_riders": "Rider Alpha | Rider Gamma",
                "selected_breakout_probability_mean": 0.58,
                "selected_specialty_match_mean": 0.69,
                "selected_allocation_score_total": 77.5,
            },
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_id": 3,
                "race_name": "Alpha Cancelled",
                "category": "1.2",
                "start_date": "2026-05-01",
                "status": "cancelled",
                "race_leader_rider": "Rider Delta",
                "race_leader_specialty": "sprint",
                "top_recommended_riders": "Rider Delta | Rider Epsilon",
                "selected_breakout_probability_mean": 0.41,
                "selected_specialty_match_mean": 0.52,
                "selected_allocation_score_total": 34.0,
            }
        ]
    ).to_csv(allocation_dir / "alpha_team_2026_rider_race_plan.csv", index=False)
    pd.DataFrame(
        [
            {
                "team_slug": "beta-team",
                "team_name": "Beta Team",
                "planning_year": 2026,
                "race_id": 4,
                "race_name": "Beta Race",
                "category": "1.1",
                "start_date": "2026-03-15",
                "status": "scheduled",
                "race_leader_rider": "Rider Beta",
                "race_leader_specialty": "oneday",
                "top_recommended_riders": "Rider Beta | Rider Zeta",
                "selected_breakout_probability_mean": 0.74,
                "selected_specialty_match_mean": 0.76,
                "selected_allocation_score_total": 88.0,
            }
        ]
    ).to_csv(allocation_dir / "beta_team_2026_rider_race_plan.csv", index=False)
    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "rider_name": "Rider Alpha",
                "specialty_primary": "oneday",
                "recommended_race_count": 2,
                "race_leader_assignments": 2,
                "best_race_name": "Alpha Classic",
                "allocation_score_total": 120.0,
            }
        ]
    ).to_csv(allocation_dir / "alpha_team_2026_rider_load_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "team_slug": "alpha-team",
                "team_name": "Alpha Team",
                "planning_year": 2026,
                "race_name": "Alpha Classic",
                "rider_name": "Rider Alpha",
                "allocation_score": 44.0,
            }
        ]
    ).to_csv(allocation_dir / "alpha_team_2026_rider_race_allocations.csv", index=False)
    (allocation_dir / "alpha_team_2026_rider_race_allocation_summary.json").write_text(
        """
{
  "team_slug": "alpha-team",
  "planning_year": 2026,
  "rider_model_name": "baseline_prior_points",
  "race_count": 3,
  "rider_count": 5,
  "selected_pairings": 14
}
""".strip()
        + "\n"
    )
