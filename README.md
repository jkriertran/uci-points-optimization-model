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

If you want a presentation-ready explanation of the model, see `MODEL_STUDY_GUIDE.md`.
Planned future work is tracked in `ROADMAP.md`.

## Project structure

```text
.
├── app.py
├── data/
│   └── race_editions_snapshot.csv
├── requirements.txt
├── scripts/
│   └── build_snapshot.py
├── tests/
│   ├── test_fc_client.py
│   ├── test_model.py
│   ├── test_pcs_client.py
│   └── test_proteam_risk.py
└── uci_points_model/
    ├── __init__.py
    ├── backtest.py
    ├── data.py
    ├── fc_client.py
    ├── model.py
    ├── pcs_client.py
    └── proteam_risk.py
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

## Modeling notes

- One-day races are the cleanest use case.
- Stage races are modeled as one calendar target with `GC + stage-result` points rolled into the event-level payout.
- Race-category changes are handled explicitly, so a historical `1.1` version and a later `1.Pro` version are not blended into one uninterrupted target history.
- The app now includes a lightweight beta route-profile x specialty-fit overlay, but it is inferred from event structure rather than full GPX or gradient data.
- The ProTeam monitor is a concentration-risk dashboard, not a rider-performance model.
- The model still does not do true team-specific roster optimization, probable lineups, or internal role planning.
- The startlist-strength proxy comes from FirstCycling's extended startlist stats (`Starts`, `Wins`, `Podium`, `Top 10`), not from private team power files or internal rankings.
