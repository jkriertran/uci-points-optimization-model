# Deterministic V3 Next Steps for Team Calendar EV

The repository is now at an important transition point. V1 and V2 established the saved team-season EV workflow, archetype-aware team profiles, and a first deterministic roster-scenario overlay inside the app.[1] [2] [3] The next step for **deterministic V3** is not full rider prediction. The roadmap is explicit that the immediate milestone should be a roster-aware scenario layer that remains explainable, artifact-backed, and deterministic.[1]

## What V3 should mean

Deterministic V3 should be defined as a **saved-artifact, scenario-aware planning layer** that introduces more realistic lineup assumptions without turning the product into a probabilistic rider forecast engine.[1] [3]

In practical terms, V3 should answer three questions better than V2:

| Question | Why V2 only partially answers it | What deterministic V3 should add |
| --- | --- | --- |
| Which races still look good under weaker lineup assumptions? | V2 can shift team-fit and participation with generic presets, but those changes are still broad team-profile overrides. [3] | Scenario logic tied to explicit lineup-strength assumptions and race-level availability rules. |
| How much season EV depends on a small set of likely starters? | V2 does not explicitly separate team identity from roster availability. [1] [3] | A deterministic lineup-confidence layer and scenario deltas by race and season. |
| What happens when public roster assumptions differ from private team expectations? | V2 is UI-only and does not yet model public versus internal availability tracks. [1] | Separate assumption layers for public roster confidence and optional private planning overrides. |

## The most important design decision

The key decision is to **keep V3 deterministic and artifact-first**. The roadmap and scaffold plan both point in the same direction: reuse saved team EV artifacts, do not rebuild history on page load, and do not jump straight to rider-level optimization.[1] [2]

That means V3 should keep the current production boundary intact:

| Keep stable | Do not do yet |
| --- | --- |
| Saved race-level EV artifact remains the baseline contract | No live rider-level optimizer |
| Base opportunity stays anchored to the saved historical model | No probabilistic simulation engine |
| Execution multiplier stays explicit and explainable | No opaque machine-learned lineup selector |
| Scenario changes are driven by documented planning assumptions | No hidden ad hoc manual overrides in the UI |

## Recommended V3 implementation order

I would implement deterministic V3 in six steps.

### 1. Formalize the V3 scope as a new scenario contract

Today, `roster_scenarios.py` already recomputes `scenario_team_fit_multiplier`, `scenario_participation_confidence`, and `scenario_expected_points` while leaving `base_opportunity_points` and `execution_multiplier` fixed.[3] That is the correct base. The next step is to formalize V3 as a richer contract, not just a UI overlay.

The contract should explicitly distinguish these layers:

| Layer | Meaning | Status today | V3 action |
| --- | --- | --- | --- |
| `base_opportunity_points` | Historical payout opportunity anchor | Implemented | Keep fixed. [3] |
| `team_fit_multiplier` | Team-level fit from archetype/profile | Implemented | Keep, but allow lineup-aware scenario replacement. [3] |
| `participation_confidence` | Generic confidence that team starts meaningfully | Implemented | Split into more explicit components. [1] [3] |
| `execution_multiplier` | Category-level conversion haircut | Implemented | Keep fixed in deterministic V3. [3] |
| `lineup_confidence` | Confidence in actual usable roster strength | Not yet implemented | Add in V3. [1] |

The simplest V3 formula should therefore become:

> `scenario_expected_points = base_opportunity_points × scenario_team_fit_multiplier × scenario_participation_confidence × scenario_lineup_confidence × execution_multiplier`

This preserves interpretability while creating a clear new lever that is specifically about roster realism rather than general team attendance.

### 2. Add a deterministic lineup-confidence layer

The roadmap already says V3 should model probable lineup confidence separately from generic calendar participation confidence.[1] This is the single most important modeling addition.

I would implement it with deterministic rule-based inputs first.

| Input signal | Example deterministic interpretation | Why it fits V3 |
| --- | --- | --- |
| Public roster signal | Team has publicly named likely starters or a probable group | Reproducible and explainable |
| Availability assumption | Best rider available, mixed availability, depth-constrained | Matches the current preset philosophy |
| Race importance tier | Team is more likely to bring full strength to priority races | Still rule-based, not speculative simulation |
| Overlap pressure | Simultaneous races dilute top-end lineup quality | Aligns with existing overlap logic |
| Private override layer | Optional internal assumption for planning use | Supports public versus private planning split in roadmap |

This should produce a new `scenario_lineup_confidence` column and a `lineup_confidence_delta` versus baseline.

### 3. Expand presets from generic profile overrides into roster-aware assumption bundles

The current preset catalog includes `baseline_saved`, `depth_constrained`, and `best_available`, and it works by overriding team-profile weights and participation rules.[3] For V3, presets should evolve into **roster assumption bundles**.

Instead of only mutating fit bounds and participation rules, each preset should carry a broader deterministic structure.

| V2 style preset | V3 style preset extension |
| --- | --- |
| `baseline_saved` | Identity baseline with no additional lineup haircut |
| `depth_constrained` | Reduced lineup confidence at overlapping races and top-priority events without elite starters |
| `best_available` | Strong lineup confidence for priority races with minimal availability penalties |
| New `public_expected` | Uses only public roster evidence and conservative assumptions |
| New `internal_plan` | Allows optional private override inputs for internal planning |

Technically, this means extending `config/roster_scenario_presets.json` and `RosterScenarioPreset` so presets can override a lineup-confidence rule block, race-priority rule block, and availability rule block, not just team-profile fields.[3]

### 4. Decide whether V3 stays derived-only or also writes scenario artifacts

This is the biggest product architecture choice. Right now, the scenario layer is intentionally UI-only and non-persistent.[2] [3] For V3, I would recommend a middle path.

| Option | Pros | Cons | Recommendation |
| --- | --- | --- | --- |
| Keep UI-only | Simple, no new artifact family | Harder to batch compare teams and dates; less reproducible outside app | Too limiting for V3 |
| Write full persistent scenario artifact families | Strong auditability and downstream use | More path and schema complexity | Premature if every preset becomes its own file family |
| Persist scenario outputs on demand or via batch companion artifact | Reproducible without exploding the contract | Requires careful schema design | **Best V3 path** |

My recommendation is to keep the baseline team-season artifact as the canonical source and add an **optional companion scenario comparison artifact** such as:

- `data/team_ev/<team_slug>_<planning_year>_scenario_compare.csv`
- `data/team_ev/<team_slug>_<planning_year>_scenario_summary.csv`

Those files should stack scenarios row-wise rather than minting a separate full artifact family per scenario. That keeps V3 deterministic, batch-friendly, and easy to diff.

### 5. Add scenario-aware views in the app without breaking the reader-first surface

The roadmap definition of done explicitly calls for scenario-aware race and season delta views inside the existing workspace.[1] The recent app cleanup created a strong reader-first structure, so V3 should respect that.

I would implement the UI in this order:

| UI addition | Why it should come first |
| --- | --- |
| Scenario selector with baseline, public, conservative, aggressive, internal-plan options | Creates a stable user entry point |
| Season delta summary cards | Gives immediate top-line meaning |
| Race mover table by scenario delta | Makes the change concrete |
| Scenario waterfall or decomposition table | Shows whether losses come from fit, participation, or lineup confidence |
| Advanced assumption panel | Keeps the main page readable |

The app should make one distinction very explicit: **team identity** explains what kind of races suit the team in general, while **lineup confidence** explains how much of that suitability is realistically available for a given scenario.

### 6. Lock the contract with tests and docs before adding deeper realism

V3 should be a contract-hardening milestone as much as a modeling milestone.

The minimum additions should be:

| Area | Required V3 tests or docs |
| --- | --- |
| Scenario engine | Identity baseline, deterministic lineup-confidence math, frozen baseline columns, reproducible deltas |
| Artifact layer | Stable scenario summary schema, metadata versioning, deterministic ordering of scenarios |
| App layer | Scenario selector behavior, correct delta cards, safe empty states |
| Docs | README, ROADMAP, and `data_dictionary.md` updated to explain baseline EV versus roster-aware deterministic scenarios |

## Recommended implementation sequence in code

If you want the practical coding order, I would do it like this.

| Order | File or area | Change |
| --- | --- | --- |
| 1 | `uci_points_model/roster_scenarios.py` | Add `scenario_lineup_confidence`, richer preset schema, and separated assumption components |
| 2 | `config/roster_scenario_presets.json` | Expand presets into roster-aware bundles |
| 3 | `uci_points_model/team_calendar_artifacts.py` | Add optional scenario comparison artifact builder and metadata fields |
| 4 | `scripts/build_team_calendar_ev.py` or a companion batch script | Allow deterministic scenario comparison build from saved baseline artifacts |
| 5 | `app.py` | Add scenario delta cards, race movers, and lineup-confidence explanations inside the current reader-first layout |
| 6 | `tests/test_roster_scenarios.py`, `tests/test_team_calendar_artifacts.py`, `tests/test_app_team_calendar_ev.py` | Lock the contract before expanding scope further |
| 7 | `README.md`, `ROADMAP.md`, `data/team_ev/data_dictionary.md` | Document what V3 is and what it is not |

## What I would not do in V3

To keep the milestone tight, I would explicitly leave these items out of deterministic V3:

| Leave out | Reason |
| --- | --- |
| Rider-level stochastic forecasts | Too large a jump from the current artifact-first workflow |
| Optimization over every possible lineup | Turns the product into a search problem before the scenario contract is stable |
| Travel cost and logistics optimization | Valuable, but better after lineup-confidence mechanics are stable |
| Statistical coefficient inference | Important later, but orthogonal to the immediate roster-aware product milestone |

## Bottom line

> The next step for deterministic V3 is to turn the current UI-only roster overlay into a **formal roster-aware scenario layer** with a new lineup-confidence component, richer deterministic presets, optional persisted scenario comparison artifacts, and scenario-aware delta views in the app.[1] [2] [3] [4]

If you want the shortest practical summary, I would do these three things next:

| Rank | Next step |
| --- | --- |
| 1 | Add a separate deterministic `lineup_confidence` layer |
| 2 | Expand presets into roster-aware public, conservative, aggressive, and internal-plan bundles |
| 3 | Add scenario comparison artifacts and app views that compare each scenario against the saved baseline |

## References

[1]: file:///mnt/desktop/uci-points-optimization-model/ROADMAP.md "ROADMAP.md"
[2]: file:///mnt/desktop/uci-points-optimization-model/roster-scenario-scaffold-plan.md "roster-scenario-scaffold-plan.md"
[3]: file:///mnt/desktop/uci-points-optimization-model/uci_points_model/roster_scenarios.py "roster_scenarios.py"
[4]: file:///mnt/desktop/uci-points-optimization-model/uci_points_model/team_calendar_artifacts.py "team_calendar_artifacts.py"
