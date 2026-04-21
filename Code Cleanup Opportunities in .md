# Code Cleanup Opportunities in `uci-points-optimization-model`

The repository is in a good state functionally. It has clear domain modules, meaningful tests, and a working separation between data collection, modeling, and presentation. The main cleanup opportunities are therefore not about broken code. They are about **reducing future maintenance cost**, especially as the Streamlit app and the new team-calendar EV layer continue to grow.[1] [2] [3] [4]

## Executive view

The biggest cleanup opportunity is the **shape of the application layer**. `app.py` has become the coordination point for controls, data loading, scoring, tab rendering, formatting, and downloads. That works today, but it increases the cost of every future feature because all changes pass through one very large file.[1]

The second major opportunity is the **mixing of calculation logic and data-shaping logic inside the EV pipeline**. `calendar_ev.py` is still understandable, but it now contains historical summary construction, actual-points retrieval, EV assembly, summary generation, fallback rules, participation heuristics, route labeling, and team-fit logic in one module.[2]

The third major opportunity is the **use of loosely structured dictionaries and DataFrame metadata** where typed result objects or configuration models would make behavior more explicit and easier to validate.[2] [3] [4]

## Highest-value cleanup priorities

| Priority | Area | Why it matters now | Recommendation |
| --- | --- | --- | --- |
| 1 | `app.py` | New features will keep slowing down because UI, state, formatting, and orchestration live together | Split the Streamlit app into feature-oriented render modules and shared loaders |
| 2 | `calendar_ev.py` | The EV layer now mixes model math, scraping-side enrichment, and summary export concerns | Separate pure scoring logic from I/O and reporting helpers |
| 3 | Script layer | Build scripts contain orchestration plus documentation generation plus path bootstrapping | Move reusable logic into package services and keep scripts thin |
| 4 | Config and result typing | Dict lookups and DataFrame attrs make assumptions implicit | Introduce dataclasses or typed config models for profile rules and load results |
| 5 | Shared helper duplication | Date resolution and some fallback patterns are duplicated across modules | Centralize shared utilities and common status logic |

## 1. `app.py` is the clearest refactor target

The Streamlit entry point is the clearest cleanup candidate. It currently holds page setup, sidebar controls, dataset loading, state management, scoring calls, planning-calendar overlay, KPI construction, tab creation, and tab rendering in one file.[1]

That makes the app easy to run, but harder to evolve. The most likely future pain points are:

| Symptom | Why it will get worse |
| --- | --- |
| Adding a new workspace requires editing the main file directly | Feature work becomes merge-conflict prone |
| Data loading and rendering are coupled | It is harder to test business logic without Streamlit |
| Formatting code is interleaved with analytics code | Small UI changes require reading large blocks of model-adjacent logic |
| Session-state logic is embedded in page flow | Reuse becomes difficult if the app grows to multiple pages |

A good cleanup target is a structure like this:

| Module | Responsibility |
| --- | --- |
| `streamlit_app/loaders.py` | Cached dataset and EV file loading |
| `streamlit_app/state.py` | Weight and filter session-state helpers |
| `streamlit_app/tabs/targets.py` | Recommended-targets workspace |
| `streamlit_app/tabs/backtest.py` | Backtest and calibration workspace |
| `streamlit_app/tabs/proteam_risk.py` | ProTeam risk workspace |
| `streamlit_app/tabs/team_calendar_ev.py` | Team calendar EV workspace |

This is the single highest-value cleanup because it improves every future feature, including the Streamlit EV tab you want to add.[1]

## 2. `calendar_ev.py` is cohesive by topic, but overloaded by responsibility

The EV module is another strong cleanup target. It currently performs at least five jobs:

| Responsibility inside `calendar_ev.py` | Example functions |
| --- | --- |
| Historical opportunity summary building | `build_historical_target_summary()` |
| Live actual-points enrichment | `build_actual_points_table()` and `_build_actual_points_row()` |
| Team-level EV calculation | `build_team_calendar_ev()` |
| Summary output generation | `summarize_team_calendar_ev()` |
| Internal fallback and heuristic logic | `_apply_category_history_fallbacks()`, `_derive_participation_confidence()`, `_execution_multiplier_for_category()` |

This is not disastrous, but it does mean that the same file owns both **core model math** and **pipeline support behavior**.[2]

A cleaner split would be:

| Proposed module | Responsibility |
| --- | --- |
| `calendar_ev_history.py` | Historical opportunity summaries and fallback baselines |
| `calendar_ev_scoring.py` | Team-fit, participation, execution, and expected-points math |
| `calendar_ev_actuals.py` | Actual-points retrieval and normalization |
| `calendar_ev_summary.py` | Overview, monthly, and category summaries |

The best rule here is simple:

> Pure calculations should be isolated from network-dependent enrichment and from output-formatting helpers.

That would make the EV model easier to test, easier to benchmark, and easier to explain.

## 3. The script layer should be thinner

`scripts/build_team_calendar_ev.py` is useful, but it is carrying too much responsibility. It parses arguments, manipulates `sys.path`, decides whether to load or build the calendar, runs the EV pipeline, stacks summary outputs, writes CSVs, and generates Markdown documentation in one place.[5]

That shape is common in early project growth, but it becomes awkward once more scripts appear. Two smells stand out.

| Smell | Why it matters |
| --- | --- |
| `sys.path` insertion at runtime | Packaging boundaries are not yet clean |
| Markdown README and data dictionary generation inside the script | Documentation generation is coupled to orchestration |

A better shape would be a package-level service function, such as `build_team_calendar_ev_artifacts(...)`, that returns a structured artifact bundle. The script would then become a thin wrapper around that service.[5]

That would also make the logic reusable from Streamlit, tests, notebooks, or future automation.

## 4. Typed config would improve safety and readability

Several important behaviors are currently driven by plain dictionaries. For example, team profile settings in `calendar_ev.py` use dictionary lookups for `strength_weights`, `participation_rules`, `execution_rules`, `team_fit_floor`, and `team_fit_range`.[2] The data module also stores important state in DataFrame `attrs`, such as `calendar_source`, `errors`, and `error_count`.[4]

This is flexible, but it hides contract expectations.

| Current pattern | Cleanup opportunity |
| --- | --- |
| `team_profile.get("strength_weights", {})` | Replace with a validated `TeamProfile` dataclass or model |
| `rules.get("completed", 1.00)` | Replace with typed rule objects and defaults in one place |
| `dataset.attrs["error_count"]` | Return a typed load result with `frame`, `source`, and `errors` |

The payoff is not just cleaner code. It is **safer change management**. When the EV model grows to more teams or more profile dimensions, typed config will reduce silent breakage.

## 5. Shared utility duplication is small, but worth fixing early

There are already duplicated helpers such as `_resolve_as_of_date()` in both `calendar_ev.py` and `team_calendar.py`.[2] [3] On their own, these are minor issues. But they are early signs that the repo is starting to accumulate shared logic informally.

I would move these into a small utility module, something like `utils/dates.py` or `common.py`, before more duplication builds up.

## 6. `team_calendar.py` has good logic, but it would benefit from more explicit sub-steps

`team_calendar.py` is reasonably well scoped, but `build_team_calendar_from_source_rows()` now performs normalization, column repair, race matching, planning-calendar joining, fallback field filling, status derivation, note generation, and overlap tagging in one flow.[3]

That is still manageable, but it is trending toward a pipeline that would be easier to reason about if broken into named transformation steps. For example:

| Proposed helper | Purpose |
| --- | --- |
| `prepare_source_rows()` | Normalize columns coming from PCS or CSV |
| `match_source_rows_to_calendar()` | Produce match IDs and diagnostics |
| `merge_with_planning_calendar()` | Join canonical race metadata |
| `finalize_team_calendar_fields()` | Derive status, notes, and standardized output columns |

This is not the first cleanup I would do, but it is a good second-wave refactor because the underlying logic is already solid.[3]

## 7. The data-loading layer works, but metadata handling could be more explicit

`data.py` is not large, but it mixes scraping, concurrency, derived metric creation, fallback loading, and metadata attachment through DataFrame `attrs`.[4]

The current approach is pragmatic, but a more explicit return type would reduce hidden behavior. For example, `load_calendar()` currently signals whether data came from live fetch, snapshot, or unavailability through `calendar.attrs["calendar_source"]`.[4]

That is easy to forget and easy to break when copying or slicing DataFrames. A small typed result object would make the contract clearer.

## 8. Test strategy is decent, but the app and script boundaries remain lightly protected

The repo has solid test coverage for core modules such as model logic, team calendar transforms, EV calculations, PCS parsing, and ProTeam risk.[2] [3] [6] [7] [8] [9] [10] That is a strength.

The weaker area is around **application integration boundaries**. The Streamlit app and the orchestration scripts carry meaningful behavior, but most tests focus on lower-level functions. That means cleanup in those layers can be riskier than necessary.

A useful next step would be a few high-value integration tests around:

| Test type | What it would protect |
| --- | --- |
| EV artifact build smoke test | Script-to-package integration |
| Streamlit loader smoke test | File discovery and summary loading |
| Snapshot fallback regression test | User-facing reliability in degraded network cases |

## Recommended cleanup order

If you want the highest return on effort, I would do the cleanup in this order.

| Order | Action | Why first |
| --- | --- | --- |
| 1 | Split `app.py` into render modules and shared loaders | Biggest long-term maintenance win |
| 2 | Extract pure EV scoring logic from `calendar_ev.py` | Makes the new feature easier to trust and reuse |
| 3 | Turn `build_team_calendar_ev.py` into a thin CLI wrapper | Improves reuse and packaging cleanliness |
| 4 | Introduce typed profile and load-result models | Reduces silent contract drift |
| 5 | Centralize shared utilities like date resolution and status helpers | Prevents future duplication |
| 6 | Add a few integration tests around app and artifact building | Protects refactors from regressions |

## Bottom line

Yes, there are definitely meaningful cleanup opportunities. The repo does **not** look messy in the sense of being undisciplined. It looks like a healthy project that has grown quickly and now needs a round of **architectural tidying**.

The most important insight is this:

> The codebase’s next bottleneck is not the core model math. It is the increasing amount of orchestration and presentation logic sitting at the edges of the system.

If you clean up the app boundary, thin the script layer, and split the EV module into purer parts, the repository will be in a much stronger position for Version 3 work.

If you want, I can do the next step and produce a **Codex-ready refactor plan** that breaks this into concrete PR-sized tasks.

## References

[1]: file:///home/ubuntu/uci-points-optimization-model/app.py "app.py"
[2]: file:///home/ubuntu/uci-points-optimization-model/uci_points_model/calendar_ev.py "calendar_ev.py"
[3]: file:///home/ubuntu/uci-points-optimization-model/uci_points_model/team_calendar.py "team_calendar.py"
[4]: file:///home/ubuntu/uci-points-optimization-model/uci_points_model/data.py "data.py"
[5]: file:///home/ubuntu/uci-points-optimization-model/scripts/build_team_calendar_ev.py "build_team_calendar_ev.py"
[6]: file:///home/ubuntu/uci-points-optimization-model/tests/test_calendar_ev.py "test_calendar_ev.py"
[7]: file:///home/ubuntu/uci-points-optimization-model/tests/test_model.py "test_model.py"
[8]: file:///home/ubuntu/uci-points-optimization-model/tests/test_team_calendar.py "test_team_calendar.py"
[9]: file:///home/ubuntu/uci-points-optimization-model/tests/test_proteam_risk.py "test_proteam_risk.py"
[10]: file:///home/ubuntu/uci-points-optimization-model/tests/test_pcs_client.py "test_pcs_client.py"
