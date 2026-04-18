# Team Calendar EV Dataset

This directory stores deterministic Team Calendar EV artifacts for tracked team-seasons.

## Artifact Set

- `data/team_calendars/<team_slug>_<year>_latest.csv`: latest team calendar snapshot
- `data/team_calendars/<team_slug>_<year>_changelog.csv`: schedule changelog against the prior saved snapshot
- `data/team_results/<team_slug>_<year>_actual_points.csv`: live PCS actual points by race when available
- `data/team_ev/<team_slug>_<year>_calendar_ev.csv`: race-level expected-value output
- `data/team_ev/<team_slug>_<year>_calendar_ev_summary.csv`: one-row team-season KPI summary
- `data/team_ev/<team_slug>_<year>_calendar_ev_metadata.json`: saved model assumptions and build metadata

## Build

Refresh a single team-season with:

```bash
python scripts/build_team_calendar_ev.py \
  --team-slug <team-slug> \
  --pcs-team-slug <pcs-team-slug> \
  --planning-year <year> \
  --team-profile-path data/team_profiles/<team_slug>_<year>_profile.json \
  --calendar-path data/team_calendars/<team_slug>_<year>_latest.csv \
  --actual-points-path data/team_results/<team_slug>_<year>_actual_points.csv \
  --ev-output-path data/team_ev/<team_slug>_<year>_calendar_ev.csv \
  --summary-output-path data/team_ev/<team_slug>_<year>_calendar_ev_summary.csv \
  --readme-path data/team_ev/README.md \
  --dictionary-path data/team_ev/data_dictionary.md
```

Refresh all tracked teams in the manifest with:

```bash
python scripts/build_all_proteam_calendar_ev.py --manifest-path config/tracked_proteams_2026.csv
```
