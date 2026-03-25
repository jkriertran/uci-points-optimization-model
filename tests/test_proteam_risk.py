import pandas as pd

from uci_points_model.pcs_client import CYCLE_SCOPE, CURRENT_SCOPE, TeamBreakdown, TeamRankingEntry
from uci_points_model.proteam_risk import (
    RISK_BAND_HIGH,
    RISK_BAND_LOWER,
    RISK_BAND_MEDIUM,
    aggregate_proteam_riders,
    build_proteam_risk_dataset,
    prepare_proteam_detail,
    risk_band,
    summarize_proteam_risk,
)


def test_summarize_proteam_risk_calculates_concentration_metrics() -> None:
    raw = pd.DataFrame(
        [
            {
                "scope": CURRENT_SCOPE,
                "cycle_label": "",
                "team_rank": 1,
                "team_name": "Risky Team",
                "team_slug": "risky-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 200.0,
                "team_total_points": 200.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2026,
                "rider_name": "Leader",
                "rider_slug": "leader",
                "team_rank_within_counted_list": 1,
                "points_counted": 100.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
            {
                "scope": CURRENT_SCOPE,
                "cycle_label": "",
                "team_rank": 1,
                "team_name": "Risky Team",
                "team_slug": "risky-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 200.0,
                "team_total_points": 200.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2026,
                "rider_name": "Second",
                "rider_slug": "second",
                "team_rank_within_counted_list": 2,
                "points_counted": 50.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
            {
                "scope": CURRENT_SCOPE,
                "cycle_label": "",
                "team_rank": 1,
                "team_name": "Risky Team",
                "team_slug": "risky-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 200.0,
                "team_total_points": 200.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2026,
                "rider_name": "Third",
                "rider_slug": "third",
                "team_rank_within_counted_list": 3,
                "points_counted": 30.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
            {
                "scope": CURRENT_SCOPE,
                "cycle_label": "",
                "team_rank": 1,
                "team_name": "Risky Team",
                "team_slug": "risky-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 200.0,
                "team_total_points": 200.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2026,
                "rider_name": "Fourth",
                "rider_slug": "fourth",
                "team_rank_within_counted_list": 4,
                "points_counted": 20.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
        ]
    )

    summary = summarize_proteam_risk(raw)

    assert len(summary) == 1
    assert summary.iloc[0]["leader_name"] == "Leader"
    assert summary.iloc[0]["top1_share"] == 0.5
    assert summary.iloc[0]["top3_share"] == 0.9
    assert summary.iloc[0]["top5_share"] == 1.0
    assert summary.iloc[0]["leader_shock_drop_points"] == 100.0
    assert summary.iloc[0]["leader_coleader_shock_drop_points"] == 150.0
    assert summary.iloc[0]["risk_band"] == RISK_BAND_HIGH


def test_prepare_proteam_detail_aggregates_cycle_rows_by_rider() -> None:
    raw = pd.DataFrame(
        [
            {
                "scope": CYCLE_SCOPE,
                "cycle_label": "2026-2028",
                "team_rank": 1,
                "team_name": "Cycle Team",
                "team_slug": "cycle-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 250.0,
                "team_total_points": 250.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2026,
                "rider_name": "Alpha",
                "rider_slug": "alpha",
                "team_rank_within_counted_list": 1,
                "points_counted": 100.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
            {
                "scope": CYCLE_SCOPE,
                "cycle_label": "2026-2028",
                "team_rank": 1,
                "team_name": "Cycle Team",
                "team_slug": "cycle-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 250.0,
                "team_total_points": 250.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2027,
                "rider_name": "Alpha",
                "rider_slug": "alpha",
                "team_rank_within_counted_list": 1,
                "points_counted": 50.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
            {
                "scope": CYCLE_SCOPE,
                "cycle_label": "2026-2028",
                "team_rank": 1,
                "team_name": "Cycle Team",
                "team_slug": "cycle-team-2026",
                "team_class": "PRT",
                "ranking_total_points": 250.0,
                "team_total_points": 250.0,
                "sanction_points_total": 0.0,
                "ranking_url": "https://example.com/ranking",
                "source_url": "https://example.com/team",
                "scraped_at": "2026-03-25T12:00:00+00:00",
                "season_year": 2026,
                "rider_name": "Beta",
                "rider_slug": "beta",
                "team_rank_within_counted_list": 2,
                "points_counted": 100.0,
                "points_not_counted": 0.0,
                "sanction_points": 0.0,
            },
        ]
    )

    aggregated = aggregate_proteam_riders(raw)
    detail = prepare_proteam_detail(raw, team_slug="cycle-team-2026")

    assert len(aggregated) == 2
    assert detail.iloc[0]["rider_name"] == "Alpha"
    assert detail.iloc[0]["points_counted"] == 150.0
    assert detail.iloc[0]["season_years"] == "2026, 2027"
    assert round(float(detail.iloc[0]["share_pct"]), 1) == 60.0
    assert round(float(detail.iloc[1]["cumulative_share_pct"]), 1) == 100.0


def test_risk_band_thresholds_are_deterministic() -> None:
    assert risk_band(0.35, 0.10) == RISK_BAND_HIGH
    assert risk_band(0.24, 0.30) == RISK_BAND_HIGH
    assert risk_band(0.25, 0.10) == RISK_BAND_MEDIUM
    assert risk_band(0.10, 0.20) == RISK_BAND_MEDIUM
    assert risk_band(0.10, 0.10) == RISK_BAND_LOWER


def test_build_dataset_keeps_zero_point_team_when_breakdown_is_empty() -> None:
    class FakeClient:
        def get_team_rankings(self, scope: str) -> list[TeamRankingEntry]:
            assert scope == CURRENT_SCOPE
            return [
                TeamRankingEntry(
                    team_rank=162,
                    team_name="Team Novo Nordisk",
                    team_slug="team-novo-nordisk-2026",
                    team_class="PRT",
                    ranking_points=0.0,
                    team_path="team/team-novo-nordisk-2026",
                    breakdown_path="team/team-novo-nordisk-2026/results/uci-world-teams",
                )
            ]

        def get_team_breakdown(self, team_path: str, scope: str) -> TeamBreakdown:
            assert team_path == "team/team-novo-nordisk-2026"
            assert scope == CURRENT_SCOPE
            return TeamBreakdown(
                rows=[],
                total_counted_points=0.0,
                sanction_points_total=0.0,
                source_url="https://example.com/team/team-novo-nordisk-2026/results/uci-world-teams",
            )

    dataset = build_proteam_risk_dataset(scope=CURRENT_SCOPE, client=FakeClient())
    summary = summarize_proteam_risk(dataset)
    detail = prepare_proteam_detail(dataset, team_slug="team-novo-nordisk-2026")

    assert len(dataset) == 1
    assert bool(dataset.iloc[0]["is_placeholder_team_row"]) is True
    assert len(summary) == 1
    assert summary.iloc[0]["team_name"] == "Team Novo Nordisk"
    assert summary.iloc[0]["counted_riders_found"] == 0
    assert summary.iloc[0]["leader_name"] == ""
    assert summary.iloc[0]["team_total_points"] == 0.0
    assert summary.iloc[0]["risk_band"] == RISK_BAND_LOWER
    assert detail.empty
