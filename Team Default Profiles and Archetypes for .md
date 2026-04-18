# Team Default Profiles and Archetypes for `uci-points-optimization-model`

This document is product rationale.

Implementation source of truth:

- `Codex Handoff_ Team Default Profiles and User-Friendly Archetypes.md`

## Executive recommendation

Yes, the model should have default team profiles for all tracked teams, and those profiles should be explained to users through a small archetype layer.

The key idea is simple:

1. keep the numeric profile for computation,
2. add an archetype for fast human understanding,
3. keep a short explanation of what that archetype changes in planning.

## Why archetypes help

The underlying weights are useful to the model, but they are not especially legible to users. A profile becomes much easier to understand when the app can say something like:

> **Archetype:** Classics + Sprint Opportunist
>
> **Meaning:** This team projects better into one-day races and sprint-accessible opportunities than into GC-led stage-race campaigns.

That framing helps users interpret the model without asking them to reason directly from six coefficients.

## Recommended user-facing model

The best Version 1 experience is a three-layer explanation stack.

| Layer | Purpose | What the user sees |
| --- | --- | --- |
| Team weights | Machine-readable model input | Weight bars or another compact profile view |
| Archetype label | Human-readable summary | A label such as `Classics + Sprint Opportunist` |
| Plain-language interpretation | Context and trust | A short sentence about what the profile changes |

This keeps the model structured for EV math while making the output understandable to non-technical users.

## Product principles

### 1. Archetypes should be additive

The archetype should not replace the current weight and rule explainers. It should sit on top of them as a faster summary layer.

### 2. The archetype library should stay small

The system works better if users can learn a small set of reusable team identities rather than a long tail of one-off labels.

### 3. Team fit should stay conceptually separate from race opportunity

The app should keep reinforcing the same message:

> The team profile does not change how many points a race is worth in general. It changes how suitable that race looks for the selected team.

That distinction is one of the most important trust-building pieces of the feature.

### 4. Analyst-set defaults are good enough for Version 1

This feature does not need automated profile estimation to be useful. The defaults only need to be directionally right, consistent, and easy to challenge.

## Recommended archetype starter set

| Archetype key | Label | Plain-English meaning |
| --- | --- | --- |
| `classic_sprint_opportunist` | Classics + Sprint Opportunist | Best suited to one-day races and sprint-friendly point collection |
| `classic_specialist` | Pure Classics Specialist | Built mainly for one-day racing and selective classics |
| `stage_hunter` | Stage Hunter | More dangerous in breakaways and stage-level grabs than GC campaigns |
| `gc_development` | GC Development Team | More aligned with stage-race structure and overall ambitions |
| `sprint_first` | Sprint-First Team | Relies heavily on sprint-accessible scoring opportunities |
| `balanced_opportunist` | Balanced Opportunist | Seeks points across multiple race shapes without one defining specialty |
| `time_trial_edge` | Time Trial Edge | Has an outsized edge in TT-shaped opportunities |

## Recommended user experience in Streamlit

The Team Calendar EV workspace already has a selector, a detailed saved-weight explainer, and a sandbox. The archetype layer should fit into that flow instead of competing with it.

Recommended UX:

| Area | Role |
| --- | --- |
| Team-season selector | Keep existing selection flow |
| Compact Team Identity block | Add archetype badge, summary, confidence, and rationale |
| Detailed explainer | Keep existing weight and rule transparency below |
| Sandbox | Keep existing what-if controls separate |

This approach avoids adding a second overlapping explanation panel.

## Recommendation for Version 1

| Decision | Recommendation |
| --- | --- |
| Number of archetypes | 6 to 8 total |
| Source of truth | Manual archetype assignment in team profiles |
| Validation | Rule-based inference helper used for consistency checks |
| Confidence field | Small enum such as `high`, `medium`, `low`, `experimental` |
| App behavior | Show the archetype as a summary layer, not a replacement explainer |

## Bottom line

An archetype layer is the right way to make team default weights understandable.

The product shape to aim for is:

> one shared archetype library, team defaults that remain structured for computation, and a compact identity block in the app that explains what the selected team profile means for planning.

## Repo references

- `uci_points_model/calendar_ev.py`
- `uci_points_model/team_calendar_artifacts.py`
- `scripts/build_team_calendar_ev.py`
- `app.py`
- `data/team_profiles/unibet_rose_rockets_2026_profile.json`
