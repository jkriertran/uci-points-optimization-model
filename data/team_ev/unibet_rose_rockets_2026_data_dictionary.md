# Team Calendar EV Data Dictionary

| Field | Description |
| --- | --- |
| `team_slug` | Stable team-season slug. |
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
| `specialty_fit_score` | Team-fit score from non-sprint dimensions. |
| `sprint_fit_bonus` | Explicit sprint-sensitive team-fit add-on. |
| `team_fit_score` | Combined normalized team-fit score. |
| `team_fit_multiplier` | Bounded multiplier applied to base opportunity. |
| `participation_confidence` | Deterministic participation confidence factor. |
| `execution_multiplier` | Category-based conservative realization haircut. |
| `expected_points` | Final deterministic Version 2 expected-value estimate. |
| `actual_points` | Live PCS actual UCI points for the team in that race when known. |
| `ev_gap` | Actual minus expected points. |
| `status` | Calendar state such as completed or scheduled. |
| `team_calendar_status` | Current team calendar membership flag. |
| `source` | Snapshot source label. |
| `overlap_group` | Overlap flag for simultaneous race windows. |
| `notes` | Join or data quality notes. |
