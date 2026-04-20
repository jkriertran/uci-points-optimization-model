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
- a saved `Team Calendar EV` workspace with team-season KPIs, race-level detail, and explainable metadata
- manifest-driven multi-team ProTeam profile support with archetype-aware defaults and overrides
- saved team-calendar changelog artifacts for tracking schedule changes across refreshes

## Planned

### 1. Team And Roster Fit Layer

Status: Foundation implemented, roster-aware expansion planned

Goal:

- turn the saved team-season EV workflow into a more realistic roster-aware planning system
- move beyond team-level defaults toward scenario-specific lineup expectations
- preserve the explainable saved-artifact workflow while improving realism

Why it matters:

- the repo now has a working team-season EV layer, but it still reasons mostly at the team-default level
- the next value unlock is to compare plausible race programs and roster assumptions, not just generic team fit
- this future layer should answer questions like:
  - which races stay attractive under conservative versus aggressive lineup assumptions?
  - how much of the season EV depends on a small set of likely starters?
  - which calendar choices still look good if the best-fit roster is unavailable?

Proposed scope:

- add roster-dependent scenario comparisons inside the `Team Calendar EV` workflow
- model probable lineup confidence separately from generic calendar participation confidence
- support conservative/base/aggressive roster scenarios before attempting full rider-level optimization
- compare scenario totals and race-level deltas against the saved baseline artifact
- keep the first version deterministic and explainable rather than overly ambitious

Important note:

- the immediate next step is scenario modeling, not full rider prediction
- the first milestone should reuse saved team artifacts and explicit planning assumptions before introducing deeper roster data dependencies

### 2. Statistical Coefficient Inference And Stability Analysis

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

### 3. Route-Type Modeling

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

### 4. Travel And Scheduling Constraints

Status: Planned

Potential additions:

- overlapping race conflicts
- travel burden
- compact multi-race campaign planning

### Implemented Team-Season Planning Foundation

The current repo already includes:

- a saved `Team Calendar EV` workflow that builds race-level and summary artifacts per tracked team-season
- `config/tracked_proteams_2026.csv` as the tracked-team manifest for batch refreshes
- archetype-aware default and override team profiles in `data/team_profiles/`
- a `Team Calendar EV` app workspace with KPI cards, charts, metadata explainers, and a non-persistent team-profile sandbox
- saved team-calendar changelog artifacts to monitor program drift between refreshes
- a ProTeam concentration monitor that shows how dependent a team is on its leading point scorers
- current-season and `2026-2028` rider-contribution views
- transparent concentration metrics like `Top-1 Share`, `Top-3 Share`, `Effective Contributors`, and shock tests

### Immediate Next Milestone

Ship a first roster-scenario layer on top of the existing team-season EV workflow.

Definition of done:

- roster-dependent scenario comparisons
- probable lineup confidence inputs or presets
- public-roster versus private-team availability layers
- scenario-aware race and season delta views inside the existing workspace
- documentation that clearly separates shipped team-level EV from planned roster-aware expansion
