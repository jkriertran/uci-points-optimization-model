# Team Profile Archetypes

## Goal
Implement the handoff by adding archetype-aware team profiles without replacing the existing default-plus-override Team Calendar EV pipeline.

## Tasks
- [ ] Add `config/team_archetypes.json` and `uci_points_model/team_profiles.py` for catalog loading, validation, inference, and display helpers. → Verify: helper tests can load the catalog and validate a merged profile.
- [ ] Update `uci_points_model/team_calendar_artifacts.py` to validate merged profiles and propagate archetype fields into saved metadata. → Verify: artifact tests assert archetype fields survive into metadata.
- [ ] Update the default and Unibet team profile JSON files to include archetype metadata. → Verify: merged profiles resolve with explicit archetype fields.
- [ ] Add a compact Team Identity block to the Team Calendar EV workspace and keep the existing detailed explainer/sandbox intact. → Verify: app helper tests return the expected identity summary.
- [ ] Add targeted pytest coverage for helper validation, metadata propagation, and app-facing profile context. → Verify: targeted pytest runs pass.

## Done When
- [ ] Archetype metadata is validated, saved into Team Calendar EV metadata, and shown in the app.
- [ ] Existing team-fit math and explainability still work.

## Notes
- Keep `team_slug` stable and yearless; keep `pcs_team_slug` season-qualified.
- Preserve the default-plus-override merge path in `uci_points_model/team_calendar_artifacts.py`.
