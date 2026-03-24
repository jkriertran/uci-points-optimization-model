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

## What the app does

- pulls race calendars month by month from FirstCycling
- scrapes result tables and extended startlists for each race edition
- scrapes individual stage-result pages for stage races
- computes pre-race field-form proxies from the extended startlist page
- scores each edition
- aggregates repeated editions into a shortlist of races worth targeting next season
- includes a walk-forward backtest that calibrates weights on prior years and checks them against future race editions

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
│   └── test_model.py
└── uci_points_model/
    ├── __init__.py
    ├── backtest.py
    ├── data.py
    ├── fc_client.py
    └── model.py
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

## Modeling notes

- One-day races are the cleanest use case.
- Stage races are modeled as one calendar target with `GC + stage-result` points rolled into the event-level payout.
- The model still does not understand route type, rider specialty, or team-specific roster fit.
- The startlist-strength proxy comes from FirstCycling's extended startlist stats (`Starts`, `Wins`, `Podium`, `Top 10`), not from private team power files or internal rankings.
