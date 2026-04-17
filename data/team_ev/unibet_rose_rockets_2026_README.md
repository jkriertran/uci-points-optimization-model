# Team Calendar EV Dataset

This dataset stores the deterministic Version 2 calendar expected-value build for `unibet-rose-rockets-2026` in `2026`.

## What It Contains

- One row per tracked race in the live PCS team program matched onto the bundled planning calendar
- Historical opportunity anchors derived from `data/race_editions_snapshot.csv`
- Transparent EV components: `base_opportunity_points`, `team_fit_score`, `participation_confidence`, and `execution_multiplier`
- Live PCS `team-in-race` actual points where a rider table is available, with zero-point completed races retained as zeroes

## Important Coverage Note

The team calendar comes from the live PCS team program page and is matched back to the bundled planning calendar with a small alias table. Future races stay in the snapshot as `scheduled`, while completed races are identified from their planning dates.

## Rebuild

1. Refresh the team calendar snapshot with `python scripts/build_team_calendar_snapshots.py`.
2. Rebuild the EV outputs with `python scripts/build_team_calendar_ev.py`.
