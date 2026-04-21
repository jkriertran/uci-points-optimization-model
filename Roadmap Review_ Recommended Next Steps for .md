# Roadmap Review: Recommended Next Steps for `uci-points-optimization-model`

I reviewed the current repository state and compared it against the roadmap, README, and app surface. The main conclusion is that the repo has moved forward materially on the **team calendar expected-value** side, but the roadmap and public app framing have not fully caught up yet.[1] [2] [3] [4]

## Executive view

The strongest immediate opportunity is not to invent a completely new modeling branch first. It is to **finish productizing what is already partially built**. The repository now contains a working team-calendar EV module, a team calendar builder, race-level EV outputs for Unibet Rose Rockets, and tests around that logic.[5] [6] [7] [8] At the same time, the main Streamlit app tabs still expose only the original race-targeting workflow, calibration, ProTeam risk, and raw data views.[4] The roadmap also still lists expected team-specific points as only partially planned language, even though a meaningful Version 2 foundation now exists in code and data.[1] [5] [6]

That means the next roadmap should separate **product completion**, **generalization**, and **next-generation modeling**.

## What appears complete or materially advanced

| Area | Current state | Evidence |
| --- | --- | --- |
| Historical race-opportunity model | Mature and already surfaced in app | README and app describe and expose this clearly [2] [4] |
| Walk-forward calibration | Implemented and exposed in app | README and `Backtest & Calibration` tab [2] [4] |
| ProTeam concentration monitor | Implemented and exposed in app | README and `ProTeam Risk Monitor` tab [2] [4] |
| Beta route-profile overlay | Implemented in lightweight form | README, roadmap, and app copy [1] [2] [4] |
| Team calendar EV foundation | Implemented in code and data, but not yet clearly productized in app | `calendar_ev.py`, `build_team_calendar_ev.py`, team EV outputs, tests [5] [6] [7] [8] |
| Team schedule diff tracking | Implemented in code | `team_calendar.py` changelog builder [9] |

## What is still not fully finished

| Area | Why it still feels incomplete |
| --- | --- |
| Team calendar EV in product UX | The main app tabs do not yet surface a Team Calendar EV workspace [4] |
| Team default profiles for many teams | The current codebase still looks centered on the Unibet example [5] [7] |
| User-facing explanation of team profiles | The archetype and explanation layer has been designed, but is not yet visible in the app [4] [5] |
| Roadmap and README alignment | Public docs still describe the older scope more than the newer EV layer [1] [2] |
| Roster-dependent planning | Still absent from app and roadmap implementation [1] [2] |
| Travel and overlap optimization | Still not modeled beyond simple overlap penalties in profile logic [1] [5] |

## Recommended roadmap order

I would prioritize the next steps in this order.

| Priority | Next step | Why this should come next |
| --- | --- | --- |
| 1 | Ship Team Calendar EV into the Streamlit app | Highest leverage because the model work already exists and is not yet fully visible to users |
| 2 | Generalize team profiles across all tracked teams | Makes the EV layer reusable instead of a one-team demonstration |
| 3 | Add archetype-based explainability in the app | Makes the team-profile system understandable and trustworthy |
| 4 | Update README and ROADMAP to reflect actual current scope | Reduces confusion between shipped capabilities and planned work |
| 5 | Add roster-dependent scenarios and probable lineup modeling | This is the logical modeling step after team-level defaults exist |
| 6 | Add statistical coefficient inference and stability analysis | Important scientifically, but less urgent than finishing the user-facing product layer |
| 7 | Add travel and multi-race campaign constraints | High value later, but depends on better roster and schedule realism first |

## Recommended next milestone

The next milestone should be **Team Calendar EV Productization**.

That milestone should include four concrete deliverables.

| Deliverable | Definition of done |
| --- | --- |
| Streamlit Team Calendar EV tab | Users can select a team and see KPIs, charts, and race-level EV tables |
| Multi-team default profile support | More than one team profile is available through a clean loader |
| Team archetype explanation layer | Users can understand what the profile means without reading raw coefficients |
| Documentation refresh | README and ROADMAP accurately describe the current shipped feature set |

This milestone would make the repo feel coherent. Right now, there is a visible gap between what the code can do and what the app and docs present as the product.

## Why I would not start with coefficient inference first

The roadmap lists statistical coefficient inference and stability analysis first among planned items.[1] I still think that work matters, but I would not make it the immediate next step unless your priority is methodology publication rather than product usefulness.

The reason is simple. The repo already has a valuable new planning feature in the team calendar EV layer, and that layer is much closer to user-facing payoff. Finishing the product loop around it should create more immediate value than adding a more formal inference wrapper to coefficients that most users cannot yet interact with directly.[4] [5] [6]

So I would treat coefficient inference as the **next analytical layer after the team EV workflow is fully surfaced and generalized**.

## Concrete next steps I would take now

| Order | Action |
| --- | --- |
| 1 | Add a `Team Calendar EV` section or tab to `app.py` |
| 2 | Build a team-profile loader so the UI can list available teams |
| 3 | Add profile archetypes and plain-English profile descriptions |
| 4 | Surface the existing EV outputs and charts for a selected team |
| 5 | Refresh `README.md` so it mentions the team calendar EV layer |
| 6 | Refresh `ROADMAP.md` so `expected team-specific points` becomes `implemented foundation, still to generalize` |
| 7 | Then begin Phase 2 modeling with roster scenarios and probable lineups |

## Suggested roadmap rewrite

I would revise the roadmap headings to reflect the current maturity more accurately.

| Roadmap section | Suggested new status |
| --- | --- |
| Statistical Coefficient Inference And Stability Analysis | Planned |
| Route-Type Modeling | Beta implemented, deepen with real parcours data |
| Team And Roster Fit Layer | Team calendar EV foundation implemented, multi-team and roster-aware expansion still planned |
| Travel And Scheduling Constraints | Planned |

That wording would better match the current repo reality.[1] [5] [6] [9]

## Bottom line

My recommendation is:

> **Do not jump straight to the next research feature. First finish turning the existing team calendar EV foundation into a clear product surface. Then generalize it across teams, then move into roster scenarios, and only after that prioritize coefficient inference and travel optimization.**

If you want the shortest version, the next three roadmap steps should be:

| Rank | Next step |
| --- | --- |
| 1 | Ship Team Calendar EV in Streamlit |
| 2 | Add all-team default profiles plus archetypes |
| 3 | Add roster-dependent scenario modeling |

## References

[1]: file:///home/ubuntu/uci-points-optimization-model/ROADMAP.md "ROADMAP.md"
[2]: file:///home/ubuntu/uci-points-optimization-model/README.md "README.md"
[3]: file:///home/ubuntu/uci-points-optimization-model/MODEL_STUDY_GUIDE.md "MODEL_STUDY_GUIDE.md"
[4]: file:///home/ubuntu/uci-points-optimization-model/app.py "app.py"
[5]: file:///home/ubuntu/uci-points-optimization-model/uci_points_model/calendar_ev.py "calendar_ev.py"
[6]: file:///home/ubuntu/uci-points-optimization-model/scripts/build_team_calendar_ev.py "build_team_calendar_ev.py"
[7]: file:///home/ubuntu/uci-points-optimization-model/data/team_ev/unibet_rose_rockets_2026_calendar_ev.csv "unibet_rose_rockets_2026_calendar_ev.csv"
[8]: file:///home/ubuntu/uci-points-optimization-model/tests/test_calendar_ev.py "test_calendar_ev.py"
[9]: file:///home/ubuntu/uci-points-optimization-model/uci_points_model/team_calendar.py "team_calendar.py"
