# Roadmap

This file tracks planned upgrades for the UCI Points Optimization Model.

## Current Focus

The app already supports:

- explainable race-level scoring
- stage-race GC plus stage-result points
- category-aware race histories
- walk-forward calibration
- current-season calendar overlay for actionable recommendations
- beta route-profile x specialty-fit targeting
- a ProTeam key-man-risk monitor for counted UCI team-point concentration

## Planned

### 1. Statistical Coefficient Inference And Stability Analysis

Status: Planned, not implemented

Goal:

- move beyond heuristic or purely performance-calibrated coefficients
- estimate coefficient behavior more formally from historical data
- measure whether those coefficients are stable enough to trust

Why it matters:

- the current model weights are useful and backtested, but they are not yet framed as inferential coefficients with uncertainty estimates
- this future layer would help answer questions like:
  - which components are consistently important?
  - which coefficients are unstable across folds?
  - are some variables directionally useful but not reliable enough to emphasize heavily?

Proposed scope:

- fit a simple statistical side-model on historical data
- report coefficient means and uncertainty intervals
- measure sign stability across folds
- compare out-of-sample ranking performance against the current default model
- keep this as an analytical module first, not an automatic replacement for the production scoring model

Important note:

- the goal is not to chase p-values for their own sake
- for this app, out-of-sample usefulness and coefficient stability matter more than a single in-sample significance test

### 2. Route-Type Modeling

Status: Partially implemented in beta

Implemented in beta:

- event-structure-based route profiles
- one-day / TT / GC-heavy / balanced / stage-hunter labeling
- specialty-fit targeting overlay for user-selected team strengths

Still planned:

- sprint-stage versus mountain-stage identification
- full GPX or roadbook-derived route classification
- richer TT detection at the stage level
- race-route opportunity profiles grounded in actual parcours data

### 3. Team And Roster Fit Layer

Status: Partially implemented

Implemented:

- a ProTeam concentration monitor that shows how dependent a team is on its leading point scorers
- current-season and `2026-2028` rider-contribution views
- transparent concentration metrics like `Top-1 Share`, `Top-3 Share`, `Effective Contributors`, and shock tests

Still planned:

- expected team-specific points
- roster-dependent scenario comparisons
- probable lineup modeling
- public-roster versus private-team availability layers
- route-fit plus team-strength interaction

### 4. Travel And Scheduling Constraints

Status: Planned

Potential additions:

- overlapping race conflicts
- travel burden
- compact multi-race campaign planning
