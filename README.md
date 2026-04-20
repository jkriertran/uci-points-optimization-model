# UCI Points Optimization Model

An explainable Streamlit app for ranking `.1` and `.Pro` road races as historical UCI points opportunities.

It scrapes historical `.1` and `.Pro` races from FirstCycling, estimates how soft or hard each historical startlist was, and ranks races by an explainable "arbitrage score" that balances:

- top-10 points payout
- winner upside
- softness of the top end of the field
- softness of the full field
- finish-rate reliability

It is a **race-opportunity model**, not a rider-prediction model. The core question is:
"Which races usually offer the best points-scoring opportunities relative to how hard the field looks?"

The recommendation layer is **category-aware**. If a race changes class across years, the app treats each `race + category` history separately and keeps the **latest known category** as the live planning target.

## What the app does

- pulls race calendars month by month from FirstCycling
- scrapes result tables and extended startlists for each race edition
- scrapes individual stage-result pages for stage races
- computes pre-race field-form proxies from the extended startlist page
- scores each edition
- infers a lightweight beta route profile from event structure and TT keywords
- lets users blend a chosen specialty mix into a fit-aware `Targeting Score`
- aggregates repeated editions into a shortlist of races worth targeting next season
- includes a walk-forward backtest that calibrates weights on prior years and checks them against future race editions
- includes a `ProTeam Risk Monitor` tab that shows how concentrated counted UCI team points are across ProTeam riders
- includes a `Team Calendar EV` tab that loads saved multi-team team-season EV artifacts from disk
- includes archetype-aware team profiles plus optimizer-backed strength weights for tracked ProTeams
- includes a UI-only deterministic roster-scenario overlay for saved team-season EV artifacts
- includes a `Data Sources` tab for inspecting the live data currently driving each workspace

If you want a presentation-ready explanation of the model, see `MODEL_STUDY_GUIDE.md`.
Planned future work is tracked in `ROADMAP.md`.

## Project structure

```text
.
├── app.py
├── config/
│   ├── roster_scenario_presets.json
│   ├── team_archetypes.json
│   ├── team_calendar_race_aliases.csv
│   └── tracked_proteams_2026.csv
├── data/
│   ├── proteam_risk_current_snapshot.csv
│   ├── proteam_risk_cycle_2026_2028_snapshot.csv
│   ├── race_editions_snapshot.csv
│   ├── team_calendars/
│   ├── team_ev/
│   ├── team_profiles/
│   └── team_results/
├── requirements.txt
├── scripts/
│   ├── build_all_proteam_calendar_ev.py
│   ├── build_proteam_risk_snapshot.py
│   ├── build_snapshot.py
│   ├── build_team_calendar_ev.py
│   ├── build_team_calendar_snapshots.py
│   └── fit_team_profile_weights.py
├── tests/
│   ├── test_app_team_calendar_ev.py
│   ├── test_calendar_ev.py
│   ├── test_data.py
│   ├── test_fc_client.py
│   ├── test_model.py
│   ├── test_pcs_client.py
│   ├── test_proteam_risk.py
│   ├── test_roster_scenarios.py
│   ├── test_team_calendar.py
│   ├── test_team_calendar_artifacts.py
│   ├── test_team_calendar_client.py
│   ├── test_team_profile_optimizer.py
│   └── test_team_profiles.py
└── uci_points_model/
    ├── __init__.py
    ├── backtest.py
    ├── calendar_ev.py
    ├── data.py
    ├── fc_client.py
    ├── model.py
    ├── pcs_client.py
    ├── proteam_risk.py
    ├── roster_scenarios.py
    ├── team_calendar.py
    ├── team_calendar_artifacts.py
    ├── team_calendar_client.py
    ├── team_identity.py
    ├── team_profile_optimizer.py
    └── team_profiles.py
```

## Local run

```bash
python3 -m pip install -r requirements.txt
streamlit run app.py
```

## Snapshot workflow

Live scraping works, but a CSV snapshot makes deployment and startup much faster.

Build one with:

```bash
PYTHONPATH=. python3 scripts/build_snapshot.py --years 2024 2025 --out data/race_editions_snapshot.csv
```

Optional flags:

- `--categories 1.Pro 2.Pro 1.1 2.1`
- `--max-races 120`
- `--max-workers 8`

This repository already includes a bundled snapshot at `data/race_editions_snapshot.csv`, so the app can start quickly and the backtest can run out of the box.

The ProTeam monitor also ships with bundled PCS snapshots:

- `data/proteam_risk_current_snapshot.csv`
- `data/proteam_risk_cycle_2026_2028_snapshot.csv`

Refresh them with:

```bash
PYTHONPATH=. python3 scripts/build_proteam_risk_snapshot.py
```

This repo now also includes a GitHub Actions workflow at `.github/workflows/refresh_proteam_snapshots.yml`
that refreshes those two files on a daily schedule. It is intentionally `latest only`:
the fixed snapshot filenames are overwritten in place rather than archived by date.
If the scheduled refresh fails, the workflow opens or updates a GitHub issue so the failure is visible without opening the app.

## App workspaces

The Streamlit app is organized around five workspaces:

- `Recommended Targets`: race-level historical opportunity ranking with the current planning calendar overlay
- `Backtest & Calibration`: walk-forward evaluation plus default-versus-calibrated weight comparison
- `ProTeam Risk Monitor`: concentration analysis on counted team points
- `Team Calendar EV`: saved team-season EV artifacts, explainability, profile transparency, and roster scenarios
- `Data Sources`: the raw datasets currently driving the active analysis

## Team Calendar EV pipeline

The repo also includes a saved-artifact `Team Calendar EV` workflow for tracked `2026` ProTeams.

The operating model is:

- `config/tracked_proteams_2026.csv` is the manifest of tracked teams
- `config/team_archetypes.json` is the catalog of reusable team profile archetypes
- `data/team_profiles/default_proteam_2026_profile.json` provides the default ProTeam assumptions
- `data/team_profiles/<team_slug>_2026_profile.json` can override the default for specific teams
- `scripts/build_all_proteam_calendar_ev.py` refreshes the full tracked-team set
- `scripts/fit_team_profile_weights.py` refits team strength weights from saved EV artifacts and writes them back into the team profiles
- `app.py` stays file-driven and discovers every saved team-season artifact automatically from `data/team_ev/`

Each team profile can carry:

- archetype metadata and rationale
- bounded team-fit assumptions
- participation and execution rules
- optimizer diagnostics such as `weight_fit_method` and `weight_fit_summary`

Each tracked team-season produces:

- `data/team_calendars/<team_slug>_<year>_latest.csv`
- `data/team_calendars/<team_slug>_<year>_changelog.csv`
- `data/team_results/<team_slug>_<year>_actual_points.csv`
- `data/team_ev/<team_slug>_<year>_calendar_ev.csv`
- `data/team_ev/<team_slug>_<year>_calendar_ev_summary.csv`
- `data/team_ev/<team_slug>_<year>_calendar_ev_metadata.json`

Refresh all tracked teams with:

```bash
python scripts/build_all_proteam_calendar_ev.py --manifest-path config/tracked_proteams_2026.csv
```

Refit optimizer-backed team profile weights from the saved EV artifacts with:

```bash
python scripts/fit_team_profile_weights.py --manifest-path config/tracked_proteams_2026.csv
```

Refresh one saved team-season with the existing single-team CLI:

```bash
python scripts/build_team_calendar_ev.py \
  --team-slug unibet-rose-rockets \
  --pcs-team-slug unibet-rose-rockets-2026 \
  --planning-year 2026 \
  --team-profile-path data/team_profiles/unibet_rose_rockets_2026_profile.json \
  --calendar-path data/team_calendars/unibet_rose_rockets_2026_latest.csv \
  --actual-points-path data/team_results/unibet_rose_rockets_2026_actual_points.csv \
  --ev-output-path data/team_ev/unibet_rose_rockets_2026_calendar_ev.csv \
  --summary-output-path data/team_ev/unibet_rose_rockets_2026_calendar_ev_summary.csv \
  --readme-path data/team_ev/README.md \
  --dictionary-path data/team_ev/data_dictionary.md
```

The scheduled refresh job lives at `.github/workflows/refresh_team_calendars.yml` and now runs the manifest-driven batch build instead of a single hard-coded team.
The app reads the saved EV artifact freshness from the summary/metadata files and also shows the underlying calendar `scraped_at_utc` timestamp so stale EV builds are easier to spot.

## Streamlit deployment

This repo is ready for Streamlit Community Cloud:

1. Push the project to GitHub.
2. Set the app entrypoint to `app.py`.
3. Keep `requirements.txt` in the repo root.
4. Optionally commit `data/race_editions_snapshot.csv` so the app starts with a bundled dataset.

## Backtest and calibration

The app now includes a `Backtest & Calibration` tab.

That module:

- trains on earlier years
- predicts which races should be attractive in the next season
- tests those predictions against the next year's realized race efficiency
- compares the default weights with calibrated weights

The backtest is intentionally done at the **race level**. It does not forecast exact rider outcomes.

## ProTeam risk monitor

The app also includes a `ProTeam Risk Monitor` tab.

That module:

- loads current-season UCI team ranking data and the `2026-2028` team-ranking cycle
- filters to `PRT` teams
- reads each team's rider-by-rider counted-points breakdown
- computes concentration metrics like `Top-1 Share`, `Top-3 Share`, `Effective Contributors`, and shock tests

It is designed to answer:

"How dependent is a ProTeam on one rider, or a tiny rider core, for its counted UCI points?"

## Team Calendar EV workspace

The app also includes a `Team Calendar EV` tab.

That module:

- discovers saved team-season EV artifacts from `data/team_ev/`
- shows one-row KPI summaries plus race-level detail
- loads saved metadata to explain the EV weights and team-profile assumptions
- shows a `Team Identity` block for archetype-aware profile context
- includes a non-persistent `Team Profile Sandbox` for team-fit what-if analysis
- includes a UI-only deterministic roster-scenario overlay with `baseline_saved`, `depth_constrained`, and `best_available` presets
- shows both the saved EV `as of` date and the underlying team calendar `scraped_at_utc`, with a warning when they drift
- does not rebuild EV live in the UI

## Modeling notes

- One-day races are the cleanest use case.
- Stage races are modeled as one calendar target with `GC + stage-result` points rolled into the event-level payout.
- Race-category changes are handled explicitly, so a historical `1.1` version and a later `1.Pro` version are not blended into one uninterrupted target history.
- The app now includes a lightweight beta route-profile x specialty-fit overlay, but it is inferred from event structure rather than full GPX or gradient data.
- The ProTeam monitor is a concentration-risk dashboard, not a rider-performance model.
- Team profiles are archetype-aware planning defaults, not rider-level forecasts.
- Optimizer-backed team weights are fit from saved EV rows with known actual points and regularized toward the current profile or archetype prior.
- The roster-scenario overlay is deterministic and UI-only. It reuses saved Team Calendar EV artifacts, keeps `base_opportunity_points` and `execution_multiplier` fixed, and changes only team-fit plus participation assumptions.
- The model still does not do true team-specific roster optimization, probable lineups, or internal role planning.
- The startlist-strength proxy comes from FirstCycling's extended startlist stats (`Starts`, `Wins`, `Podium`, `Top 10`), not from private team power files or internal rankings.
