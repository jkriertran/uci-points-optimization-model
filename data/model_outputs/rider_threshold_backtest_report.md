# Rider Threshold Backtest Report

This report evaluates the current `rider_reaches_150_next_season` baselines with expanding-window validation.

## Setup

- Training rows: 1517
- Positive rows: 343
- Next seasons: 2022, 2023, 2024, 2025, 2026
- Anchor model: `baseline_prior_points`
- Winning model by `backtest_top_k_capture`: `baseline_prior_points`

Top-k capture uses the held-out season's actual number of 150-point riders as the cutoff.

## Leaderboard

| benchmark_rank | model_name | feature_columns | backtest_fold_count | backtest_top_k_capture | backtest_brier_score | backtest_accuracy | in_sample_accuracy | coefficients |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | baseline_prior_points | uci_points | 4 | 0.624 | 0.135 | 0.818 | 0.813 | uci_points=0.005 |
| 2 | baseline_points_scoring_role | uci_points, n_scoring_results, team_rank_within_roster | 4 | 0.595 | 0.137 | 0.812 | 0.816 | uci_points=0.002, n_scoring_results=0.111, team_rank_within_roster=-0.035 |

## Fold Detail

| model_name | test_next_season | train_next_seasons | test_rows | actual_positive_rows | predicted_positive_rows | top_k_capture | brier_score | accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_prior_points | 2023 | 2022 | 241 | 53 | 23 | 0.547 | 0.139 | 0.826 |
| baseline_prior_points | 2024 | 2022, 2023 | 349 | 94 | 53 | 0.649 | 0.145 | 0.802 |
| baseline_prior_points | 2025 | 2022, 2023, 2024 | 353 | 108 | 54 | 0.704 | 0.142 | 0.785 |
| baseline_prior_points | 2026 | 2022, 2023, 2024, 2025 | 264 | 24 | 37 | 0.333 | 0.111 | 0.875 |
| baseline_points_scoring_role | 2023 | 2022 | 241 | 53 | 25 | 0.528 | 0.137 | 0.834 |
| baseline_points_scoring_role | 2024 | 2022, 2023 | 349 | 94 | 55 | 0.617 | 0.141 | 0.785 |
| baseline_points_scoring_role | 2025 | 2022, 2023, 2024 | 353 | 108 | 66 | 0.648 | 0.143 | 0.807 |
| baseline_points_scoring_role | 2026 | 2022, 2023, 2024, 2025 | 264 | 24 | 50 | 0.417 | 0.122 | 0.833 |
