# Team Calendar EV Implementation

## Goal
Normalize the existing Team Calendar EV pipeline, ship the saved-artifact Streamlit workspace, and verify the new contract end to end.

## Tasks
- [x] Normalize `calendar_ev.py` and the build scripts around stable `team_slug`, separate PCS slug handling, one-row summary output, and explicit `as_of_date` semantics. → Verify: builder functions emit the approved columns and summary shape in tests.
- [x] Regenerate the bundled Team Calendar EV sample artifacts with the normalized schema. → Verify: `data/team_ev/*calendar_ev*.csv` load cleanly and show the expected identifiers and KPI columns.
- [x] Add the `Team Calendar EV` Streamlit workspace with dataset discovery, KPI cards, charts from the race-level file, downloads, and empty-state messaging. → Verify: `app.py` contains the new workspace and file-backed loaders.
- [x] Update tests for summary semantics and stable-team-slug handling, then run targeted `pytest` coverage for calendar EV and team calendar code. → Verify: targeted test command passes.

## Done When
- [x] The builder, saved artifacts, and Streamlit workspace all use the same Team Calendar EV contract without guessing.
