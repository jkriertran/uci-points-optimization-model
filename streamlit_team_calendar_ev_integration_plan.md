# Two-Phase Implementation Plan for Team Calendar EV in Streamlit

## Purpose

This plan is for the `uci-points-optimization-model` repository, not for `procycling-clean-scraped-data`.

The earlier version of this document assumed the Streamlit app, EV builder, and EV output files already lived in the current workspace. That was the wrong execution target. The right operating model is:

| Repo | Role |
| --- | --- |
| `uci-points-optimization-model` | Production home for the team calendar EV pipeline, persisted EV artifacts, and Streamlit app |
| `procycling-clean-scraped-data` | Research, calibration, exploratory analysis, and supporting datasets |

The two repos should not be merged at runtime. They should be connected through a stable data contract. If research from `procycling-clean-scraped-data` needs to influence the production app, promote only the minimal stable outputs, lookup tables, or documented assumptions into `uci-points-optimization-model`.

## Delivery strategy

This work should be executed in two explicit phases.

| Phase | Goal | Blocking question |
| --- | --- | --- |
| Phase 1 | Build and stabilize the team calendar EV artifacts | Do we have deterministic, documented outputs that the app can trust? |
| Phase 2 | Add a `Team Calendar EV` workspace in Streamlit | Can the UI load those outputs without recomputing business logic? |

Do not start Streamlit integration until Phase 1 has passed its gate.

## How to combine the two analysis tracks

The cleanest merge pattern is:

1. Keep research and experimentation in `procycling-clean-scraped-data`.
2. Move only stable, production-worthy logic or data products into `uci-points-optimization-model`.
3. Make `uci-points-optimization-model` the sole runtime dependency for the app.
4. Document the provenance of any promoted assumptions, weights, or lookup tables.

That means:

- Do not have the Streamlit app read files from `procycling-clean-scraped-data`.
- Do not make the app depend on notebooks or one-off analysis outputs from this repo.
- If a calibration study here produces a useful constant, mapping, or summary table, copy it into the production repo with documentation and tests.

## Phase 1: Normalize and stabilize the EV data product

### Goal

Produce a deterministic, documented team calendar EV data product inside `uci-points-optimization-model` that the Streamlit app can load directly.

This is a validation-and-normalization phase, not a greenfield rebuild. The repository already contains EV logic, a builder script, tests, and sample artifacts. Phase 1 should tighten the contract around those existing pieces, normalize naming and schema where needed, and document one stable build path.

### Phase 1 success criteria

Phase 1 is complete only when all of the following are true:

| Requirement | What done looks like |
| --- | --- |
| Canonical artifact location | EV outputs live in a predictable repo-owned directory such as `data/team_ev/` |
| Race-level artifact | At least one team-season race-level EV CSV exists and can be regenerated |
| Summary artifact | A matching team-season summary CSV exists and can be regenerated |
| Deterministic build path | A documented script or CLI regenerates the outputs without manual edits |
| Schema contract | Required columns are documented and stable |
| Metadata | An `as_of` date or equivalent refresh marker is persisted in the artifacts |
| Tests | Join logic and EV calculations are covered by unit tests |
| Documentation | A readme and data dictionary explain the saved outputs |

### Recommended Phase 1 file layout

Use consistent names even if the repo currently uses a slightly different naming pattern.

| File | Purpose |
| --- | --- |
| `uci_points_model/calendar_ev.py` | Deterministic EV computation logic |
| `scripts/build_team_calendar_ev.py` | CLI entry point to build or refresh saved outputs |
| `tests/test_calendar_ev.py` | Unit tests for joins, calculations, and summary behavior |
| `data/team_ev/<team_slug>_<planning_year>_calendar_ev.csv` | Race-level EV output |
| `data/team_ev/<team_slug>_<planning_year>_calendar_ev_summary.csv` | One-row team-season KPI summary output |
| `data/team_ev/<team_slug>_<planning_year>_calendar_ev_metadata.json` | Optional metadata file for `as_of`, build version, and source notes |
| `data/team_ev/README.md` | Artifact-level usage notes |
| `data/team_ev/data_dictionary.md` | Field definitions for race-level and summary outputs |

Identifier rule:

- `team_slug` is a stable team identifier and does not include the season year.
- `planning_year` is the explicit season field used in both schemas and filenames.
- Filenames must be derived from `team_slug` and `planning_year`; do not embed the season year inside `team_slug`.

### Canonical Phase 1 data contract

The UI should depend on a stable schema, not on informal expectations.

#### Race-level EV file

Required columns:

| Column | Purpose |
| --- | --- |
| `team_slug` | Team identifier |
| `planning_year` | Calendar season |
| `race_id` | Canonical join key when available |
| `race_name` | Display label |
| `category` | Race category |
| `start_date` | Planned or observed start date |
| `status` | Fixed enum: `completed`, `scheduled`, or `cancelled` |
| `source` | Calendar source or provenance marker |
| `base_opportunity_points` | Historical opportunity anchor |
| `team_fit_score` | Diagnostic fit score, if retained |
| `team_fit_multiplier` | Value used in the EV formula |
| `participation_confidence` | Confidence factor |
| `execution_multiplier` | Realization haircut |
| `expected_points` | Final deterministic EV |
| `actual_points` | Observed points when known; `0` only if confirmed zero |
| `ev_gap` | `actual_points - expected_points` |
| `overlap_group` | Optional overlapping-race grouping |
| `notes` | Optional diagnostic notes |
| `as_of_date` | Artifact freshness marker if not stored elsewhere |

Note on naming:

- If the model computes both `team_fit_score` and `team_fit_multiplier`, persist both.
- The UI should use `team_fit_multiplier` for EV math and treat `team_fit_score` as a diagnostic field.
- Do not make the Streamlit layer guess between competing names.

Canonical status and actual-points semantics:

- `completed` means the race is over relative to the persisted `as_of_date`.
- `scheduled` means the race is still upcoming or otherwise not yet complete relative to `as_of_date`.
- `cancelled` means the race should remain visible for auditability but must be excluded from forward-looking EV rollups if that is the chosen model rule.
- `actual_points = 0` means the zero is known, not missing.
- `actual_points = null` means the true value is unknown or not yet available.
- `ev_gap` must be null when `actual_points` is null.

#### Summary file

The summary CSV is the canonical KPI artifact for the Streamlit header row. It must contain exactly one row per `team_slug` and `planning_year`. Do not use a stacked multi-view summary file as the canonical contract.

Required columns:

| Column | Purpose |
| --- | --- |
| `team_slug` | Team identifier |
| `planning_year` | Calendar season |
| `as_of_date` | Freshness marker shown in the UI |
| `total_expected_points` | Full-season EV |
| `completed_expected_points` | EV from completed races |
| `remaining_expected_points` | EV from incomplete races |
| `actual_points_known` | Observed points summed only from races where actuals are known, including confirmed zero-point races |
| `ev_gap_known` | Known realized gap versus EV |
| `race_count` | Total scheduled races |
| `completed_race_count` | Completed races |
| `remaining_race_count` | Incomplete races |

Summary file rules:

- The summary file is for season-level KPIs only.
- Monthly and category charts should be derived in Streamlit from the race-level EV CSV, not persisted as additional row types inside the summary CSV.
- `remaining_expected_points` should exclude races whose `status` is `cancelled` unless a documented business rule says otherwise.

### Phase 1 implementation tasks

Execute Phase 1 in this order:

| Order | Task | Why first |
| --- | --- | --- |
| 1 | Audit the current `uci-points-optimization-model` EV implementation | Confirm what already exists in code, tests, and sample artifacts |
| 2 | Normalize identifiers, filenames, and schema | Prevent path churn and UI rewrites later |
| 3 | Normalize `calendar_ev.py` and the builder around the approved contract | Keep the deterministic logic in one place |
| 4 | Regenerate the race-level EV CSV from the normalized build path | Establish the canonical core artifact |
| 5 | Regenerate the one-row summary CSV | Give the app a stable KPI source |
| 6 | Persist metadata such as `as_of_date` | Support UI freshness messaging |
| 7 | Add or update tests | Lock in join, calculation, and summary behavior |
| 8 | Add or update the readme and data dictionary | Make the outputs handoff-friendly |

### Phase 1 decision rules

| Situation | Recommended action |
| --- | --- |
| EV artifacts already exist | Validate them against the contract above and backfill missing docs or columns |
| Builder exists but schema drifts | Normalize the saved outputs before any UI work |
| Actual points are incomplete | Still ship Phase 1, but preserve the `0` versus `null` distinction and document it explicitly |
| Useful research inputs live in `procycling-clean-scraped-data` | Promote only the minimal stable outputs into the production repo |

### Phase 1 exit gate

Only move to Phase 2 when the answer is "yes" to all of these:

1. Can the team calendar EV CSV be regenerated from a documented command?
2. Does the one-row summary CSV exist and match the documented schema?
3. Are `status`, `as_of_date`, and actual-points rules explicit and deterministic?
4. Do tests cover the fragile join and summary logic?
5. Could a Streamlit page load the artifacts without recomputing EV logic?

## Phase 2: Add the Streamlit workspace

### Goal

Add a new `Team Calendar EV` workspace in the `uci-points-optimization-model` Streamlit app that reads the saved artifacts from Phase 1.

### Phase 2 rule

The app must load prebuilt outputs. It must not rebuild the EV dataset on page load.

### Integration target

Implement Phase 2 in the actual Streamlit entrypoint and layout structure found in `uci-points-optimization-model`.

Do not assume the entry file is `app.py` until verified in that repo. If the app has already been reorganized, attach this feature to the real entrypoint, tab layout, and helper conventions that exist there.

### Recommended data-loading layer

Add small cached helpers that only load saved outputs:

| Helper | Purpose |
| --- | --- |
| `discover_team_calendar_ev_datasets()` | Scan the artifact directory and return available team-season options |
| `load_team_calendar_ev(team_slug, planning_year)` | Load the race-level EV CSV |
| `load_team_calendar_ev_summary(team_slug, planning_year)` | Load the summary CSV |
| `load_team_calendar_ev_metadata(team_slug, planning_year)` | Load optional metadata if stored separately |

### Recommended Streamlit layout

The page should have four layers.

#### 1. Selector row

| Control | Behavior |
| --- | --- |
| Team-season selector | File-driven selection from available artifacts |
| View mode selector | `Season so far`, `Full calendar`, or `Completed races only` |
| As-of note | Show `as_of_date` from summary or metadata |

Recommended filtering rules:

- `Season so far`: show completed races plus scheduled races already on the saved calendar, with KPIs anchored to the current `as_of_date`
- `Full calendar`: show all rows in the saved artifact
- `Completed races only`: filter to rows whose `status` maps to completed

#### 2. KPI row

Load these directly from the summary CSV:

| KPI | Source column |
| --- | --- |
| Total expected points | `total_expected_points` |
| Completed expected points | `completed_expected_points` |
| Remaining expected points | `remaining_expected_points` |
| Actual points known | `actual_points_known` |
| EV gap known | `ev_gap_known` |
| Race count | `race_count` |

#### 3. Core charts

Build from the race-level EV CSV:

| Chart | Why it matters |
| --- | --- |
| Cumulative actual vs expected points | Best single season checkpoint chart |
| Monthly actual vs expected | Shows timing and momentum |
| Points by category | Shows where the team is carrying value |
| Largest over- and under-expectation races | Makes the season story concrete |

#### 4. Detailed race table and downloads

Show a filterable table with identity, EV components, actuals, and diagnostics.

Suggested visible fields:

| Column group | Suggested fields |
| --- | --- |
| Race identity | `race_name`, `category`, `start_date`, `status` |
| EV core | `base_opportunity_points`, `team_fit_multiplier`, `participation_confidence`, `execution_multiplier`, `expected_points` |
| Actuals | `actual_points`, `ev_gap` |
| Diagnostics | `source`, `overlap_group`, `notes` |

Also include download buttons for the race-level CSV and summary CSV.

### Recommended UI behavior

| Situation | Recommended behavior |
| --- | --- |
| No EV artifacts found | Show an info message with the documented build command |
| Only one team-season exists | Auto-select it |
| Future races have no actual points | Display blanks and exclude them from known actual-gap totals |
| Some completed races lack EV fields | Show a warning count and surface `notes` where available |
| Metadata file is absent | Fall back to `as_of_date` in the summary CSV |

### Phase 2 implementation order

| Order | Task |
| --- | --- |
| 1 | Verify the real Streamlit entrypoint and tab layout in `uci-points-optimization-model` |
| 2 | Add cached data-discovery and load helpers |
| 3 | Add the `Team Calendar EV` workspace shell |
| 4 | Add KPI cards using the summary CSV |
| 5 | Add cumulative and category charts |
| 6 | Add monthly and race-gap charts |
| 7 | Add the detailed table and download buttons |
| 8 | Add empty-state, warning, and freshness messaging |
| 9 | Update intro copy or workspace guide text |

## Out of scope for this pass

Keep Version 2 narrow.

| Include now | Leave for later |
| --- | --- |
| File-driven team-season selector | Live rebuild button |
| KPI cards from summary CSV | In-app scraping or EV recomputation |
| Plotly charts from saved race-level data | Background jobs inside Streamlit |
| Filterable detailed race table | Cross-repo runtime dependencies |
| CSV downloads | Full multi-team portfolio comparison if only one team exists |

## Recommended instruction to Codex in the other folder

Use this as the implementation brief inside `uci-points-optimization-model`:

> First validate and normalize the existing team calendar EV data product in this repository. Do not start with Streamlit. Normalize the saved race-level EV CSV, the one-row summary CSV, the metadata or `as_of_date` field, and the documentation for the artifact schema. Make `team_slug` a stable team identifier, keep `planning_year` separate, and codify `status` plus `actual_points` semantics so `0` and `null` are never conflated. Add or update tests so the EV build path is deterministic and the join logic is protected. Only after those outputs are stable should you add a new `Team Calendar EV` workspace in the Streamlit app that loads the saved artifacts with cached helpers and presents KPIs, charts derived from the race-level CSV, downloads, and a detailed explainability table.

## Bottom line

Yes, implement this in the other folder.

The right sequence is:

1. `uci-points-optimization-model`: validate and normalize the EV artifacts.
2. `uci-points-optimization-model`: integrate those artifacts into Streamlit.
3. `procycling-clean-scraped-data`: remain the research source for calibration ideas, not the runtime home of the app.
