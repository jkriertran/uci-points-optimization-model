# Codex Handoff: Team Default Profiles and User-Friendly Archetypes

This document is the implementation source of truth for team-profile archetypes in `uci-points-optimization-model`.

Companion document:

- `Team Default Profiles and Archetypes for .md` is product rationale only.
- This handoff is the implementation spec.

## Product goal

The Team Calendar EV model already supports team-specific fit adjustments through:

- `strength_weights`
- `team_fit_floor`
- `team_fit_range`
- `execution_rules`
- `participation_rules`

What is still missing is a clean, scalable way to:

1. assign default profiles across all tracked teams,
2. translate those defaults into a human-readable archetype,
3. surface that identity in the Streamlit app without duplicating or confusing the existing explainability flow.

After this work, the Team Calendar EV workspace should answer three questions quickly:

| User question | Expected UI answer |
| --- | --- |
| What kind of team is this? | Archetype badge and short summary |
| Why does the model think that? | Archetype rationale plus the existing weight/rule explainers |
| What does this change? | Clear note that the profile changes team fit, not raw race opportunity |

## Current repo state

The repo already contains most of the plumbing needed for Version 1.

| Existing artifact | Current role |
| --- | --- |
| `uci_points_model/calendar_ev.py` | Normalizes and applies team profiles inside EV calculations |
| `uci_points_model/team_calendar_artifacts.py` | Resolves merged team profiles and writes app-facing metadata |
| `uci_points_model/team_identity.py` | Defines the stable team slug contract |
| `data/team_profiles/default_proteam_2026_profile.json` | Shared default baseline profile |
| `data/team_profiles/unibet_rose_rockets_2026_profile.json` | Current team-specific override example |
| `config/tracked_proteams_2026.csv` | Tracked-team manifest with optional `profile_path` overrides |
| `data/team_ev/*.json` | Saved metadata artifacts already consumed by the app |
| `app.py` | Existing Team Calendar EV selector, explainer, and sandbox UI |

This implementation should extend that architecture, not replace it.

## Stable contracts

These contracts should remain unchanged for Version 1.

### Team identity

| Field | Rule | Example |
| --- | --- | --- |
| `team_slug` | Stable, yearless internal slug | `unibet-rose-rockets` |
| `pcs_team_slug` | Season-qualified external/team-calendar slug | `unibet-rose-rockets-2026` |
| `planning_year` | Explicit planning year integer | `2026` |

The current `canonicalize_team_slug()` behavior in `uci_points_model/team_identity.py` should stay authoritative.

### Profile file naming

Use the existing pattern:

| Pattern | Example |
| --- | --- |
| `{stable_slug_with_underscores}_{planning_year}_profile.json` | `unibet_rose_rockets_2026_profile.json` |

### Default-plus-override model

Version 1 should preserve the current merge model:

1. load `data/team_profiles/default_proteam_2026_profile.json`,
2. merge any team-specific override JSON,
3. inject `team_slug`, `pcs_team_slug`, `team_name`, and `planning_year`,
4. validate the merged result,
5. pass the merged profile downstream.

Do not require every team file to duplicate the full default profile.

## Scope

| In scope | Out of scope |
| --- | --- |
| Shared archetype catalog | Statistical estimation of team weights |
| Validation for merged profiles | Rebuilding EV formulas |
| Human-readable archetype fields | Replacing the existing explainability tables |
| Metadata propagation into saved artifacts | Major Streamlit navigation redesign |
| Compact archetype UI integrated into Team Calendar EV | Auto-learning archetypes from historical results |

## Desired end state

### 1. Shared archetype catalog

Add:

- `config/team_archetypes.json`

This file should hold canonical archetype metadata used by validation and UI rendering.

### 2. Team-profile helper module

Add:

- `uci_points_model/team_profiles.py`

This module should own archetype catalog loading, team-profile discovery, merged-profile validation, fallback inference, and app-ready description helpers.

### 3. Existing merge path stays central

Do not move merge responsibilities out of `uci_points_model/team_calendar_artifacts.py`.

That module should remain responsible for:

- resolving the default-plus-override profile,
- validating the merged profile,
- serializing archetype fields into saved metadata artifacts consumed by the app.

### 4. Archetype UI fits into the current workspace

Do not create a second parallel explainer.

The app should add a compact Team Identity block inside the existing Team Calendar EV workspace, above the detailed saved-weight explainer and separate from the existing sandbox controls.

## Schema contract

The merged team profile should preserve current model-facing keys and add archetype fields on top.

### Existing fields to preserve

| Field | Required | Notes |
| --- | --- | --- |
| `team_slug` | Yes | Stable internal slug |
| `pcs_team_slug` | Yes | Season-qualified PCS/calendar slug |
| `planning_year` | Yes | Planning year |
| `team_name` | Yes | Display name |
| `strength_weights` | Yes | Six-axis team-fit weights |
| `team_fit_floor` | Yes | Lower bound for fit multiplier |
| `team_fit_range` | Yes | Range above the floor |
| `execution_rules` | Yes | Category realization multipliers |
| `participation_rules` | Yes | Participation confidence rules |

### Existing rationale fields to preserve

These should remain first-class because the current app already uses them in the saved explainability flow.

| Field | Required | Notes |
| --- | --- | --- |
| `strength_weight_rationale` | No | Dict keyed by strength axis |
| `team_fit_rationale` | No | Short text for fit-bound interpretation |
| `execution_rule_rationale` | No | Short text explaining execution multipliers |
| `participation_rule_rationale` | No | Dict keyed by participation signal |

### New archetype fields to add

| Field | Required | Notes |
| --- | --- | --- |
| `archetype_key` | Yes | Stable key matching `config/team_archetypes.json` |
| `archetype_label` | Yes | Human-readable label |
| `archetype_description` | Yes | One or two sentence summary |
| `profile_confidence` | No | Enum: `high`, `medium`, `low`, or `experimental` |
| `profile_rationale` | No | Array of short analyst-facing reasons |
| `profile_version` | No | Optional schema/content version |

### Example merged profile

```json
{
  "team_slug": "unibet-rose-rockets",
  "pcs_team_slug": "unibet-rose-rockets-2026",
  "planning_year": 2026,
  "team_name": "Unibet Rose Rockets",
  "archetype_key": "classic_sprint_opportunist",
  "archetype_label": "Classics + Sprint Opportunist",
  "archetype_description": "This profile favors one-day races and sprint-accessible opportunities, with some stage-hunting value but only limited GC emphasis.",
  "profile_confidence": "medium",
  "profile_rationale": [
    "The team profile leans toward one-day scoring opportunities.",
    "Sprint-accessible races remain an important conversion lane.",
    "GC-oriented stage-race upside is present, but not central."
  ],
  "strength_weights": {
    "one_day": 0.30,
    "stage_hunter": 0.15,
    "gc": 0.10,
    "time_trial": 0.05,
    "all_round": 0.15,
    "sprint_bonus": 0.25
  },
  "strength_weight_rationale": {
    "one_day": "The team has a stronger one-day scoring shape than a GC-led one.",
    "sprint_bonus": "Sprint-accessible finishes remain an important lane."
  },
  "team_fit_floor": 0.70,
  "team_fit_range": 0.30,
  "team_fit_rationale": "The multiplier is bounded so team fit remains an adjustment rather than overwhelming the opportunity anchor.",
  "execution_rules": {
    "1.1": 0.40,
    "1.Pro": 0.30,
    "1.UWT": 0.18,
    "2.1": 0.30,
    "2.Pro": 0.25,
    "2.UWT": 0.18
  },
  "execution_rule_rationale": "Execution multipliers are conservative realization haircuts by race category.",
  "participation_rules": {
    "completed": 1.00,
    "program_confirmed": 0.95,
    "observed_startlist": 0.95,
    "calendar_seed": 0.70,
    "overlap_penalty": 0.80
  },
  "participation_rule_rationale": {
    "calendar_seed": "Planning-calendar appearances are useful but less certain than confirmed starts."
  }
}
```

## Archetype catalog

Start with a small reusable catalog.

| Archetype key | Label | Description |
| --- | --- | --- |
| `classic_sprint_opportunist` | Classics + Sprint Opportunist | Strong one-day orientation with real sprint-accessible scoring value |
| `classic_specialist` | Pure Classics Specialist | Built mainly for one-day racing and selective classics |
| `stage_hunter` | Stage Hunter | More dangerous in stage-level opportunities than full GC campaigns |
| `gc_development` | GC Development Team | More aligned with stage-race structure and general classification ambitions |
| `sprint_first` | Sprint-First Team | Sprint-accessible races are the primary scoring lane |
| `balanced_opportunist` | Balanced Opportunist | No single dominant specialty, broad point-seeking profile |
| `time_trial_edge` | Time Trial Edge | Has an outsized edge in TT-shaped scoring opportunities |

Suggested structure:

```json
{
  "classic_sprint_opportunist": {
    "label": "Classics + Sprint Opportunist",
    "description": "Strong in one-day races and sprint-accessible opportunities, with limited GC emphasis.",
    "color": "#2563eb"
  },
  "classic_specialist": {
    "label": "Pure Classics Specialist",
    "description": "Built mainly for one-day racing and selective classics.",
    "color": "#0f766e"
  }
}
```

`color` is optional. If used, it should be UI metadata only.

## Required code changes

### 1. Add `uci_points_model/team_profiles.py`

Recommended functions:

| Function | Responsibility |
| --- | --- |
| `profile_dir()` | Return the team profile directory |
| `archetype_catalog_path()` | Return the archetype catalog path |
| `load_team_archetypes()` | Load the shared archetype catalog |
| `load_team_profile_by_path(path)` | Load a raw profile override JSON file |
| `list_available_team_profiles()` | Enumerate tracked profiles and their metadata |
| `validate_team_profile(profile, archetypes)` | Validate the merged profile contract |
| `infer_archetype(profile)` | Rule-based fallback inference from weights |
| `describe_team_profile(profile)` | Return app-ready archetype summary strings |
| `strength_weights_table(profile)` | Return tidy chart data for weights |

This module should not duplicate merge logic already handled elsewhere.

### 2. Update `uci_points_model/team_calendar_artifacts.py`

This is the primary integration seam.

Required changes:

- keep `resolve_team_profile()` as the authoritative merge point,
- validate the merged profile before it is used downstream,
- propagate archetype fields into the saved metadata payload,
- preserve the existing rationale fields in metadata,
- keep backward compatibility with current profiles by filling archetype values from defaults or migration-safe fallbacks where necessary.

The app already reads saved metadata. If these fields do not pass through this module, the UI work will be incomplete.

### 3. Keep `uci_points_model/calendar_ev.py` mostly unchanged

`calendar_ev.py` should continue to handle normalized team-profile math.

Allowed changes:

- light convenience imports if needed,
- small compatibility updates if validation requires them.

Do not bury archetype interpretation or UI-facing description logic in this module.

### 4. Update `scripts/build_team_calendar_ev.py`

Minimum requirement:

- keep `--team-profile-path` working exactly as it does today.

Preferred enhancement:

- allow profile discovery from `--team-slug` plus `--planning-year` when `--team-profile-path` is omitted.

That enhancement is optional for the first PR if it materially expands scope.

### 5. Update `app.py`

Integrate the new UI into the existing Team Calendar EV flow.

Recommended placement:

1. keep the existing team-season selector,
2. add a compact Team Identity block near the top of the workspace,
3. keep the current saved-weight explainer below it,
4. keep the Team Profile Sandbox separate as a what-if tool.

Recommended Team Identity block content:

| Element | Requirement |
| --- | --- |
| Team name | Reuse selected team-season context |
| Archetype badge | Show `archetype_label` prominently |
| Description | Show `archetype_description` in plain English |
| Confidence | Show `profile_confidence` if present |
| Rationale | Show `profile_rationale` in a short expander if present |
| Model note | Explain that the profile changes fit, not raw race opportunity |

Required explainer copy should stay close to:

> The team profile does not change how many points a race is worth in general. It changes how suitable that race looks for the selected team.

Also add a short note that these are analyst-set planning defaults, not rider-level forecasts.

## Validation requirements

Validation should run on the merged profile.

| Check | Rule |
| --- | --- |
| Required keys | All required model-facing and archetype fields must exist after merge |
| Weight presence | All expected `strength_weights` keys must exist |
| Weight range | Every strength weight must be between `0` and `1` |
| Weight sum | Strength weights should sum to about `1.0`, such as `abs(sum - 1.0) <= 0.02` |
| Fit bounds | `team_fit_floor` and `team_fit_range` should each be between `0` and `1` |
| Archetype key | Must exist in `config/team_archetypes.json` |
| Label consistency | `archetype_label` should match the catalog label unless intentionally derived from it |
| Description presence | `archetype_description` must not be blank |
| Confidence enum | If present, must be one of `high`, `medium`, `low`, `experimental` |
| Execution rules | Known categories should be between `0` and `1` |
| Participation rules | Values should be between `0` and `1` |

Validation failures should raise a clear `ValueError`.

## Archetype inference helper

Manual assignment remains the source of truth for Version 1, but a simple inference helper is still useful for validation and fallback.

Suggested rules:

| Condition | Inferred archetype |
| --- | --- |
| `one_day` and `sprint_bonus` are top two weights | `classic_sprint_opportunist` |
| `one_day` dominates and sprint is not strongly co-leading | `classic_specialist` |
| `stage_hunter` dominates and `gc` is modest | `stage_hunter` |
| `gc` plus `all_round` dominate | `gc_development` |
| `sprint_bonus` clearly dominates | `sprint_first` |
| `time_trial` is unusually high versus peers | `time_trial_edge` |
| No clear dominance | `balanced_opportunist` |

## Rollout strategy

Prefer a staged rollout that matches the current architecture.

### PR 1

- add `config/team_archetypes.json`,
- add `uci_points_model/team_profiles.py`,
- validate merged profiles,
- migrate the Unibet override to include archetype fields,
- propagate archetype data into saved metadata,
- add the compact Team Identity block in the app,
- add tests.

### PR 2

- add archetype-bearing overrides for the rest of the tracked teams,
- validate all tracked merged profiles,
- ensure the app renders all tracked teams cleanly.

### PR 3

- optional inference refinement,
- optional CLI validation helper,
- optional UI polish such as color badges or exported profile summaries.

## Tests to add

Likely new module:

- `tests/test_team_profiles.py`

Minimum coverage:

| Test | Purpose |
| --- | --- |
| Load archetype catalog | Verify catalog parsing works |
| Load raw profile override | Verify JSON loading works |
| Validate merged good profile | Verify valid schema passes |
| Reject bad weight sum | Verify invalid schema fails clearly |
| Reject unknown archetype key | Verify catalog consistency |
| Reject invalid confidence enum | Verify display metadata stays constrained |
| Infer archetype from Unibet-like weights | Verify fallback helper behavior |
| Build strength weights table | Verify chart helper output is stable |
| Metadata propagation | Verify archetype fields reach saved Team Calendar EV metadata |

Update existing artifact tests if needed so merged-profile validation is covered in the current build path.

## Acceptance criteria

The work is complete when all of the following are true.

| Acceptance criterion | Definition of done |
| --- | --- |
| Shared archetype catalog exists | File added and used by code |
| Merged-profile validation exists | Default-plus-override profiles are validated before downstream use |
| Unibet override migrated | Current example profile includes archetype fields |
| Metadata propagation works | Saved Team Calendar EV metadata includes archetype and rationale fields |
| App shows team identity clearly | Archetype summary appears without duplicating the existing explainer |
| Existing explainability stays intact | Weight/rule rationale views still work |
| Model behavior is preserved | EV calculations still run through the current profile pipeline |

## Guardrails

| Do this | Do not do this |
| --- | --- |
| Extend the current profile pipeline | Do not replace the default-plus-override architecture |
| Preserve the current slug contract | Do not redefine `team_slug` as season-qualified |
| Keep rationale fields first-class | Do not replace current explainability with archetype copy alone |
| Keep EV math stable | Do not redesign expected-points formulas in this task |
| Integrate into the current UI flow | Do not create a second overlapping explainer section |

## Repo references

- `uci_points_model/team_identity.py`
- `uci_points_model/team_calendar_artifacts.py`
- `uci_points_model/calendar_ev.py`
- `scripts/build_team_calendar_ev.py`
- `app.py`
- `config/tracked_proteams_2026.csv`
- `data/team_profiles/default_proteam_2026_profile.json`
- `data/team_profiles/unibet_rose_rockets_2026_profile.json`
