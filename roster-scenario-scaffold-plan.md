# Roster Scenario Scaffold

## Goal
Add a first deterministic, UI-only roster-scenario layer that recomputes scenario EV from saved team-season artifacts without requiring rider-level data or live rebuilds.

## Tasks
- [ ] Add `uci_points_model/roster_scenarios.py` for scenario schema, preset loading, and reusable recomputation helpers that turn a saved race-level EV frame plus a scenario override into scenario `team_fit_multiplier`, `participation_confidence`, and `expected_points`. → Verify: unit tests prove the `baseline_saved` scenario is identity and that an override changes only scenario columns.
- [ ] Add `config/roster_scenario_presets.json` with an ordered first-pass catalog: `baseline_saved`, `depth_constrained`, and `best_available`. Each preset should be a partial override on top of the saved `team_profile`, limited to `strength_weights`, `team_fit_floor`, `team_fit_range`, and `participation_rules`. → Verify: loader returns deterministic key order and each preset resolves into a valid scenario profile.
- [ ] Reuse the existing saved EV columns rather than rebuilding history. The scenario helper should require `base_opportunity_points`, all `*_signal` columns, `team_fit_multiplier`, `participation_confidence`, `execution_multiplier`, `expected_points`, `status`, `source`, and `overlap_group`. → Verify: helper raises a clear error when required columns are missing and passes against current Team Calendar EV fixtures.
- [ ] Add lightweight scenario metadata helpers in `uci_points_model/team_calendar_artifacts.py` so the app can describe the overlay formula and preset catalog version without minting new artifact families yet. → Verify: metadata tests assert deterministic JSON fields such as `roster_scenario_formula`, `roster_scenario_scope`, and `roster_scenario_preset_version`.
- [ ] Wire the `Team Calendar EV` workspace in `app.py` to show a `Roster Scenario` control near the existing sandbox, with KPI deltas, top race movers, and an optional download of the scenario-adjusted race table. → Verify: app tests cover preset selection, identity totals, and changed race-level deltas.
- [ ] Keep the v1 scope intentionally narrow: scenario math may change only `team_fit` and `participation_confidence`; `base_opportunity_points` and `execution_multiplier` remain frozen to the saved artifact. → Verify: tests assert those frozen columns are unchanged across scenarios.
- [ ] Update `README.md`, `ROADMAP.md`, and `data/team_ev/data_dictionary.md` so the feature is described as a deterministic overlay on saved EV artifacts, not a rider-level forecast. → Verify: docs mention the scope boundary and the app entry point.
- [ ] Verification is last: run targeted pytest for `tests/test_calendar_ev.py`, `tests/test_team_calendar_artifacts.py`, and `tests/test_app_team_calendar_ev.py`, then expand to `pytest -q` if shared helpers changed. → Verify: test runs pass.

## Done When
- [ ] A saved team-season EV artifact can be reopened in the app and compared against at least three deterministic roster scenarios without rebuilding the artifact.
- [ ] Scenario outputs are explainable, reproducible, and download-ready.
- [ ] The first version clearly separates saved team identity defaults from roster-scenario overrides.

## Notes
- Start app-side and artifact-backed; do not block v1 on rider-level PCS roster scraping.
- Keep v1 UI-only and non-persistent; downloading scenario-adjusted tables is allowed, but writing new scenario artifact families is out of scope.
- `baseline_saved` is the required identity preset and should exactly match the saved artifact totals.
- Reuse `calculate_team_fit_components` and the existing sandbox math path instead of duplicating fit logic.
- Preserve deterministic serialization and stable preset names so scenario outputs remain easy to diff and cache.
