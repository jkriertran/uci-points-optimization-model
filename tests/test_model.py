import pandas as pd

from uci_points_model.backtest import calibrate_weights
from uci_points_model.model import overlay_planning_calendar, score_race_editions, summarize_historical_targets


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


def test_summarize_historical_targets_separates_category_changes_and_keeps_latest() -> None:
    scored = pd.DataFrame(
        [
            {
                "race_id": 14,
                "race_name": "Moving Race",
                "race_country": "Portugal",
                "category": "1.1",
                "race_type": "One-day",
                "year": 2023,
                "month": 2,
                "arbitrage_score": 68.0,
                "top10_points": 180,
                "winner_points": 80,
                "total_points": 180,
                "avg_top10_field_form": 6,
                "total_field_form": 60,
                "finish_rate": 0.82,
                "points_efficiency_index": 3.0,
                "startlist_size": 120,
            },
            {
                "race_id": 14,
                "race_name": "Moving Race",
                "race_country": "Portugal",
                "category": "1.Pro",
                "race_type": "One-day",
                "year": 2024,
                "month": 2,
                "arbitrage_score": 74.0,
                "top10_points": 320,
                "winner_points": 200,
                "total_points": 320,
                "avg_top10_field_form": 12,
                "total_field_form": 120,
                "finish_rate": 0.84,
                "points_efficiency_index": 2.7,
                "startlist_size": 130,
            },
        ]
    )

    latest_summary = summarize_historical_targets(scored)
    full_summary = summarize_historical_targets(scored, latest_only=False)

    assert len(latest_summary) == 1
    assert latest_summary.iloc[0]["category"] == "1.Pro"
    assert latest_summary.iloc[0]["category_history"] == "1.1 -> 1.Pro"
    assert latest_summary.iloc[0]["years_analyzed"] == 1
    assert set(full_summary["category"]) == {"1.1", "1.Pro"}


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


def test_calibrate_weights_uses_same_category_history_only() -> None:
    dataset = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Moving Race",
                "year": 2021,
                "month": 3,
                "category": "1.1",
                "race_type": "One-day",
                "race_country": "France",
                "top10_points": 180,
                "winner_points": 80,
                "avg_top10_field_form": 6,
                "total_field_form": 60,
                "finish_rate": 0.80,
                "points_per_top10_form": 3.0,
                "points_per_total_form": 0.8,
            },
            {
                "race_id": 1,
                "race_name": "Moving Race",
                "year": 2022,
                "month": 3,
                "category": "1.Pro",
                "race_type": "One-day",
                "race_country": "France",
                "top10_points": 320,
                "winner_points": 200,
                "avg_top10_field_form": 14,
                "total_field_form": 130,
                "finish_rate": 0.82,
                "points_per_top10_form": 2.3,
                "points_per_total_form": 0.7,
            },
            {
                "race_id": 2,
                "race_name": "Stable Race",
                "year": 2021,
                "month": 4,
                "category": "1.1",
                "race_type": "One-day",
                "race_country": "Belgium",
                "top10_points": 210,
                "winner_points": 125,
                "avg_top10_field_form": 5,
                "total_field_form": 50,
                "finish_rate": 0.81,
                "points_per_top10_form": 4.2,
                "points_per_total_form": 1.1,
            },
            {
                "race_id": 2,
                "race_name": "Stable Race",
                "year": 2022,
                "month": 4,
                "category": "1.1",
                "race_type": "One-day",
                "race_country": "Belgium",
                "top10_points": 215,
                "winner_points": 125,
                "avg_top10_field_form": 5,
                "total_field_form": 52,
                "finish_rate": 0.83,
                "points_per_top10_form": 4.1,
                "points_per_total_form": 1.0,
            },
        ]
    )

    result = calibrate_weights(
        dataset,
        race_type="One-day",
        candidate_weights=[
            {
                "top10_points": 0.4,
                "winner_points": 0.2,
                "field_softness": 0.2,
                "depth_softness": 0.1,
                "finish_rate": 0.1,
            }
        ],
        min_train_years=1,
        min_fold_size=1,
    )

    fold_detail = result["best"]["fold_details"]

    assert result["eligible"] is True
    assert set(fold_detail["race_name"]) == {"Stable Race"}
    assert set(fold_detail["category"]) == {"1.1"}


def test_overlay_planning_calendar_marks_current_scope_and_category_changes() -> None:
    target_summary = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Same Category Race",
                "category": "1.1",
                "avg_arbitrage_score": 80.0,
            },
            {
                "race_id": 2,
                "race_name": "Promoted Race",
                "category": "1.1",
                "avg_arbitrage_score": 78.0,
            },
            {
                "race_id": 3,
                "race_name": "Dropped Race",
                "category": "1.Pro",
                "avg_arbitrage_score": 76.0,
            },
            {
                "race_id": 4,
                "race_name": "Missing Race",
                "category": "2.1",
                "avg_arbitrage_score": 70.0,
            },
        ]
    )
    planning_calendar = pd.DataFrame(
        [
            {
                "race_id": 1,
                "race_name": "Same Category Race",
                "category": "1.1",
                "date_label": "12.04",
                "month": 4,
                "year": 2026,
            },
            {
                "race_id": 2,
                "race_name": "Promoted Race",
                "category": "1.Pro",
                "date_label": "19.04",
                "month": 4,
                "year": 2026,
            },
            {
                "race_id": 3,
                "race_name": "Dropped Race",
                "category": "1.2",
                "date_label": "25.04",
                "month": 4,
                "year": 2026,
            },
        ]
    )

    annotated = overlay_planning_calendar(target_summary, planning_calendar, planning_year=2026)

    same = annotated.loc[annotated["race_id"] == 1].iloc[0]
    promoted = annotated.loc[annotated["race_id"] == 2].iloc[0]
    dropped = annotated.loc[annotated["race_id"] == 3].iloc[0]
    missing = annotated.loc[annotated["race_id"] == 4].iloc[0]

    assert same["planning_calendar_status"] == "On 2026 .1/.Pro calendar"
    assert bool(same["on_planning_calendar"]) is True
    assert promoted["planning_calendar_status"] == "On 2026 .1/.Pro calendar (category changed to 1.Pro)"
    assert bool(promoted["on_planning_calendar"]) is True
    assert dropped["planning_calendar_status"] == "On 2026 calendar but out of scope (1.2)"
    assert bool(dropped["on_planning_calendar"]) is False
    assert missing["planning_calendar_status"] == "Not found on 2026 calendar"
    assert bool(missing["on_planning_calendar"]) is False
