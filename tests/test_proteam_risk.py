import pandas as pd

from uci_points_model.pcs_client import CYCLE_SCOPE, CURRENT_SCOPE
from uci_points_model.proteam_risk import (
    RISK_BAND_HIGH,
    RISK_BAND_LOWER,
    RISK_BAND_MEDIUM,
    aggregate_proteam_riders,
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
