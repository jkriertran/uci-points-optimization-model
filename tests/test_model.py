import pandas as pd

from uci_points_model.backtest import calibrate_weights
from uci_points_model.model import score_race_editions, summarize_historical_targets


def test_score_race_editions_rewards_soft_fields() -> None:
    dataset = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Soft High Payout",
                "year": 2025,
                "top10_points": 300,
                "winner_points": 125,
                "avg_top10_field_form": 4,
                "total_field_form": 40,
                "finish_rate": 0.8,
            },
            {
                "race_id": 2,
                "race_name": "Hard High Payout",
                "year": 2025,
                "top10_points": 300,
                "winner_points": 125,
                "avg_top10_field_form": 20,
                "total_field_form": 180,
                "finish_rate": 0.8,
            },
        ]
    )

    scored = score_race_editions(dataset)

    assert scored.iloc[0]["race_name"] == "Soft High Payout"


def test_summarize_historical_targets_groups_race_history() -> None:
    scored = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Target Race",
                "race_country": "France",
                "category": "1.1",
                "race_type": "One-day",
                "year": 2024,
                "month": 3,
                "arbitrage_score": 80.0,
                "top10_points": 200,
                "winner_points": 125,
                "total_points": 200,
                "gc_top10_points": 200,
                "stage_top10_points": 0,
                "stage_total_points": 0,
                "stage_count": 0,
                "stage_points_share": 0.0,
                "avg_top10_field_form": 4,
                "total_field_form": 50,
                "finish_rate": 0.75,
                "points_efficiency_index": 5.0,
                "startlist_size": 120,
            },
            {
                "race_id": 1,
                "race_name": "Target Race",
                "race_country": "France",
                "category": "1.1",
                "race_type": "One-day",
                "year": 2025,
                "month": 3,
                "arbitrage_score": 60.0,
                "top10_points": 180,
                "winner_points": 100,
                "total_points": 180,
                "gc_top10_points": 180,
                "stage_top10_points": 0,
                "stage_total_points": 0,
                "stage_count": 0,
                "stage_points_share": 0.0,
                "avg_top10_field_form": 8,
                "total_field_form": 70,
                "finish_rate": 0.8,
                "points_efficiency_index": 4.0,
                "startlist_size": 130,
            },
        ]
    )

    summary = summarize_historical_targets(scored)

    assert summary.iloc[0]["race_name"] == "Target Race"
    assert summary.iloc[0]["years_analyzed"] == 2
    assert summary.iloc[0]["avg_arbitrage_score"] == 70.0


def test_summarize_historical_targets_backfills_missing_stage_columns() -> None:
    scored = pd.DataFrame(
        [
            {
                "race_id": 9,
                "race_name": "Legacy Snapshot Race",
                "race_country": "Italy",
                "category": "1.1",
                "race_type": "One-day",
                "year": 2024,
                "month": 4,
                "arbitrage_score": 75.0,
                "top10_points": 220,
                "winner_points": 125,
                "total_points": 220,
                "avg_top10_field_form": 6,
                "total_field_form": 60,
                "finish_rate": 0.8,
                "points_efficiency_index": 4.5,
                "startlist_size": 130,
            }
        ]
    )

    summary = summarize_historical_targets(scored)

    assert summary.iloc[0]["race_name"] == "Legacy Snapshot Race"
    assert summary.iloc[0]["avg_stage_top10_points"] == 0.0
    assert summary.iloc[0]["avg_stage_count"] == 0.0


def test_calibrate_weights_prefers_field_aware_candidate() -> None:
    dataset = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Soft Race",
                "year": year,
                "month": 3,
                "category": "1.1",
                "race_type": "One-day",
                "race_country": "France",
                "top10_points": 260,
                "winner_points": 125,
                "avg_top10_field_form": 4,
                "total_field_form": 40,
                "finish_rate": 0.80,
                "points_per_top10_form": 6.5,
                "points_per_total_form": 1.6,
            }
            for year in [2021, 2022, 2023]
        ]
        + [
            {
                "race_id": 2,
                "race_name": "Hard Race",
                "year": year,
                "month": 3,
                "category": "1.1",
                "race_type": "One-day",
                "race_country": "Belgium",
                "top10_points": 300,
                "winner_points": 125,
                "avg_top10_field_form": 18,
                "total_field_form": 200,
                "finish_rate": 0.82,
                "points_per_top10_form": 1.7,
                "points_per_total_form": 0.4,
            }
            for year in [2021, 2022, 2023]
        ]
        + [
            {
                "race_id": 3,
                "race_name": "Medium Race",
                "year": year,
                "month": 3,
                "category": "1.1",
                "race_type": "One-day",
                "race_country": "Spain",
                "top10_points": 190,
                "winner_points": 80,
                "avg_top10_field_form": 7,
                "total_field_form": 70,
                "finish_rate": 0.75,
                "points_per_top10_form": 3.0,
                "points_per_total_form": 0.8,
            }
            for year in [2021, 2022, 2023]
        ]
    )

    points_only = {
        "top10_points": 0.8,
        "winner_points": 0.2,
        "field_softness": 0.0,
        "depth_softness": 0.0,
        "finish_rate": 0.0,
    }
    field_aware = {
        "top10_points": 0.35,
        "winner_points": 0.10,
        "field_softness": 0.35,
        "depth_softness": 0.20,
        "finish_rate": 0.0,
    }

    result = calibrate_weights(
        dataset,
        race_type="One-day",
        candidate_weights=[points_only, field_aware],
        min_train_years=2,
        min_fold_size=3,
    )

    assert result["eligible"] is True
    assert result["best"]["objective"] >= result["default"]["objective"]
    assert result["best"]["weights"]["field_softness"] == field_aware["field_softness"]
