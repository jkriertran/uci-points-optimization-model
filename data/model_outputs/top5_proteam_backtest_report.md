# Top-5 ProTeam Backtest Report

This report evaluates the current `next_top5_proteam` baselines with expanding-window validation.

## Setup

- Training rows: 61
- Positive rows: 18
- Next seasons: 2022, 2023, 2024, 2025
- Anchor model: `baseline_n_riders_150`
- Winning model by `backtest_top_k_capture`: `baseline_n_riders_150`

Top-k capture uses the held-out season's actual number of top-five ProTeams as the cutoff.

## Leaderboard

| benchmark_rank | model_name | feature_columns | backtest_fold_count | backtest_top_k_capture | backtest_brier_score | backtest_accuracy | in_sample_accuracy | coefficients |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | baseline_n_riders_150 | n_riders_150_plus | 3 | 0.769 | 0.143 | 0.844 | 0.836 | n_riders_150_plus=0.298 |
| 2 | baseline_depth_concentration | n_riders_150_plus, top5_share, effective_contributors | 3 | 0.692 | 0.150 | 0.867 | 0.836 | n_riders_150_plus=0.305, top5_share=-4.069, effective_contributors=-0.174 |

## Fold Detail

| model_name | test_next_season | train_next_seasons | test_rows | actual_positive_rows | predicted_positive_rows | top_k_capture | brier_score | accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_n_riders_150 | 2023 | 2022 | 12 | 3 | 1 | 0.333 | 0.232 | 0.667 |
| baseline_n_riders_150 | 2024 | 2022, 2023 | 16 | 5 | 3 | 0.800 | 0.127 | 0.875 |
| baseline_n_riders_150 | 2025 | 2022, 2023, 2024 | 17 | 5 | 4 | 1.000 | 0.094 | 0.941 |
| baseline_depth_concentration | 2023 | 2022 | 12 | 3 | 2 | 0.333 | 0.234 | 0.750 |
| baseline_depth_concentration | 2024 | 2022, 2023 | 16 | 5 | 3 | 0.600 | 0.145 | 0.875 |
| baseline_depth_concentration | 2025 | 2022, 2023, 2024 | 17 | 5 | 4 | 1.000 | 0.095 | 0.941 |
