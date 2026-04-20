# Team Weight Optimizer

## Goal
Replace the heuristic team-profile weight updates with a constrained optimizer that fits `strength_weights` against saved EV artifacts and known actual points.

## Tasks
- [x] Add an optimizer module with bounded, sum-to-one search plus optional archetype prior and smoothness penalties. → Verify: optimizer tests prove weights stay valid and deterministic.
- [x] Add a script to fit and persist optimized weights back into team profile JSON using deterministic key order. → Verify: script can update a tracked team profile without breaking validation.
- [x] Propagate lightweight optimizer diagnostics into saved Team Calendar EV metadata. → Verify: rebuilt metadata JSON includes the fit method and summary.
- [x] Refit tracked team profiles and rebuild Team Calendar EV artifacts from saved calendars. → Verify: updated EV outputs and metadata exist on disk.
- [x] Run the full test suite. → Verify: `pytest -q` passes.

## Done When
- [x] Team profiles use optimizer-backed `strength_weights`.
- [x] Saved Team Calendar EV artifacts and metadata are refreshed.

## Notes
- Keep `strength_weights` bounded in `[0, 1]` and normalized to sum to `1.0`.
- Use only rows with known actual points when fitting.
- Regularize toward the archetype prior and away from overly spiky weight vectors.
