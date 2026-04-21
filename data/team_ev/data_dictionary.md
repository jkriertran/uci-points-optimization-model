# Team Calendar EV Data Dictionary

## Race-Level EV File

| Field | Description |
| --- | --- |
| `team_slug` | Stable team identifier shared across seasons. |
| `team_name` | Human-readable team name. |
| `planning_year` | Planning calendar year. |
| `race_id` | Planning calendar race identifier. |
| `race_name` | Planning calendar race name. |
| `category` | Current race category from the planning calendar. |
| `date_label` | Planning calendar date label. |
| `month` | Planning calendar month number. |
| `start_date` | Normalized planning start date. |
| `end_date` | Normalized planning end date. |
| `pcs_race_slug` | PCS race slug used to fetch the team-in-race points page. |
| `historical_years_analyzed` | Count of prior editions used in the historical summary. |
| `race_type` | Historical race type label from the race-edition snapshot. |
| `route_profile` | Lightweight race-profile label derived from historical structure. |
| `avg_top10_points` | Average historical top-10 points haul. |
| `avg_winner_points` | Average historical winner points. |
| `avg_points_efficiency` | Average historical points-per-top10-form efficiency. |
| `avg_stage_top10_points` | Average historical stage-race top-10 points component. |
| `avg_stage_count` | Average historical stage count. |
| `avg_top10_field_form` | Average historical top-10 field-form proxy. |
| `base_opportunity_index` | Normalized historical opportunity score. |
| `base_opportunity_points` | Points-space base opportunity anchor. |
| `one_day_signal` | Historical one-day fit signal used inside the team-fit layer. |
| `stage_hunter_signal` | Historical stage-hunter fit signal used inside the team-fit layer. |
| `gc_signal` | Historical GC fit signal used inside the team-fit layer. |
| `time_trial_signal` | Historical time-trial fit signal used inside the team-fit layer. |
| `all_round_signal` | Historical all-round fit signal used inside the team-fit layer. |
| `sprint_bonus_signal` | Historical sprint-sensitive fit signal used inside the team-fit layer. |
| `specialty_fit_score` | Team-fit score from non-sprint dimensions. |
| `sprint_fit_bonus` | Explicit sprint-sensitive team-fit add-on. |
| `team_fit_score` | Combined normalized team-fit score. |
| `team_fit_multiplier` | Bounded multiplier applied to base opportunity. |
| `participation_confidence` | Deterministic participation confidence factor. |
| `execution_multiplier` | Category-based conservative realization haircut. |
| `expected_points` | Final deterministic Version 2 expected-value estimate. |
| `actual_points` | Live PCS actual UCI points for the team in that race when known. |
| `ev_gap` | Actual minus expected points when actuals are known. |
| `status` | Calendar state such as completed or scheduled. |
| `team_calendar_status` | Current team calendar membership flag. |
| `source` | Snapshot source label. |
| `overlap_group` | Overlap flag for simultaneous race windows. |
| `notes` | Join or data quality notes. |
| `as_of_date` | Persisted freshness marker used for status derivation and UI messaging. |

## Summary File

| Field | Description |
| --- | --- |
| `team_slug` | Stable team identifier shared across seasons. |
| `planning_year` | Planning calendar year. |
| `as_of_date` | Freshness marker shown in the UI. |
| `total_expected_points` | Full-season expected-value total. |
| `completed_expected_points` | Expected points from races whose status is completed. |
| `remaining_expected_points` | Expected points from races whose status is scheduled. |
| `actual_points_known` | Observed points summed only from races with known actuals, including confirmed zeroes. |
| `ev_gap_known` | Observed minus expected points summed only where actuals are known. |
| `race_count` | Total number of tracked races in the saved season artifact. |
| `completed_race_count` | Number of completed races in the saved season artifact. |
| `remaining_race_count` | Number of scheduled races in the saved season artifact. |

## UI-Only Roster Scenario Overlay

The Streamlit `Team Calendar EV` workspace can recompute a non-persistent roster scenario overlay directly from the saved race-level EV artifact.

- Scope: `ui_only_saved_team_ev_overlay`
- Formula: `base_opportunity_points * scenario_team_fit_multiplier * scenario_participation_confidence * execution_multiplier`
- Preset catalog version: `deterministic-ui-v1`
- Saved artifact fields stay unchanged; the overlay adds scenario columns only inside the app and in the optional scenario download.
- The first version keeps `base_opportunity_points` and `execution_multiplier` fixed to the saved artifact and changes only team-fit plus participation assumptions.
