## Project Title

**Unified Codex Handoff: ProTeam Top-5 Modeling, Rider Depth Forecasting, and Firecrawl-Aware Data Pipeline**

## Purpose

This document is the single implementation handoff for Codex. It combines the strategic framing, the official logistic-regression study result, the current repository audit, the verified upstream historical-data inventory, the source-map conclusions, and a practical data-acquisition plan that explicitly incorporates **Firecrawl** wherever scraping reliability or page interaction becomes important.

The goal is to move the project from a pure **race opportunity model** toward a broader and more useful system that answers the real decision problem:

> **How does a ProTeam build enough meaningful scorers, especially riders who can clear 150 UCI points, to finish in the top five ProTeams next season?**

A second goal is to explain that outcome at the rider level, not only the team level. The system should therefore estimate which riders are most likely to become real scorers, which races are the most accessible paths to those points, and how roster depth compounds into next-season team status.

## Executive Summary

The official study result changes the architecture. The project should no longer be framed as only **which races are worth the most expected points**. It should be framed as **how teams create scoring depth**. The strongest planning signal from the study is the number of riders on a roster who finish the season above a meaningful threshold, especially **150 UCI points**.

The production repository already contains a strong foundation for this transition. It already has a **FirstCycling race-opportunity pipeline**, a **PCS team-risk and rider-contribution pipeline**, and persisted **team calendar EV artifacts** for tracked teams. What it does **not** yet contain is the full **next-season team-depth panel**, **rider-threshold forecasting layer**, or a **Firecrawl-based resilient collection workflow** for pages that are dynamic, brittle, or difficult to scrape reliably with direct HTML requests alone.

The implementation should therefore become a **three-layer system**:

| Layer | Purpose | Status |
| --- | --- | --- |
| Race opportunity layer | Estimate accessible points in races and explain where opportunities exist | Already partly implemented in `uci-points-optimization-model` |
| Rider pathway layer | Estimate how individual riders accumulate points and whether they can cross key thresholds | Not yet implemented as a full pipeline |
| Team top-five ProTeam layer | Estimate whether the team can reach top-five ProTeam status next season | Not yet implemented as a formal model |

## Official Study Findings to Treat as Inputs

Codex should treat the attached logistic-regression study as an official design input. The earlier outline already translated the presentation into implementation implications, and that framing should now be considered canonical.

| Official finding | What Codex should do with it |
| --- | --- |
| The count of riders with at least 150 points is strongly predictive of next-season top-five ProTeam status | Make `n_riders_150_plus` a first-class feature, KPI, and planning target |
| Around ten riders above 150 points appears to correspond to top-five-caliber depth | Surface a planning-zone threshold around 8, 10, and 12 riders |
| Top-heavy teams are less robust than deep teams | Track concentration metrics such as `top1_share`, `top3_share`, `top5_share`, and effective-contributor breadth |
| A simple logistic specification is already powerful | Preserve a transparent baseline model before adding complexity |
| The signal is predictive rather than causal | Present outputs as decision support, not deterministic guarantees |

The product thesis should now be explicit.

> A ProTeam reaches top-five ProTeam status by building a deep, repeatable, and diversified scoring roster, not merely by having one star rider or targeting a few isolated high-value races.

## Repository Audit and What Already Exists

The current production repository is **`uci-points-optimization-model`**. It already contains important pieces that should be reused rather than rebuilt.

### What is already implemented

| Existing component | Evidence from repo audit | Reuse guidance |
| --- | --- | --- |
| FirstCycling calendar and race-edition scraping | `uci_points_model/fc_client.py` scrapes calendars, results tables, stage pages, and extended startlists | Reuse as the first-pass race-opportunity source |
| PCS team ranking and rider breakdown scraping | `uci_points_model/pcs_client.py` scrapes team rankings and rider counted / not-counted points | Reuse for team-depth and concentration features |
| Persisted race-opportunity snapshot | `data/race_editions_snapshot.csv` already exists | Reuse as a stable historical race-opportunity table |
| ProTeam risk monitor inputs | `data/proteam_risk_current_snapshot.csv` and `data/proteam_risk_cycle_2026_2028_snapshot.csv` already exist | Reuse for concentration and counted-points features |
| Team calendar EV artifacts | `data/team_ev/`, `data/team_calendars/`, and `data/team_results/` already exist for tracked teams | Reuse as the deterministic team-season planning layer |
| Team profile scaffolding | `data/team_profiles/` and related scripts already exist | Reuse as prior assumptions for team fit and participation |

### Data already present in the production repository

The repository already has nontrivial saved outputs and should not be treated as empty.

| Artifact family | Approximate current count from audit | Meaning |
| --- | --- | --- |
| `data/team_calendars/` files | 32 | Saved team calendar snapshots and changelogs |
| `data/team_results/` files | 16 | Saved actual-points files for tracked teams |
| `data/team_ev/` files | 52 | Saved race-level EV files, summaries, metadata, and dictionaries |
| `data/team_profiles/` files | 17 | Default and team-specific profile assumptions |

### Important architectural conclusion

The repo already supports **race EV**, **team risk**, and **saved team-season planning artifacts**. What is missing is not basic scraping capability. What is missing is a **unified team-depth and rider-path modeling stack** that converts raw results into next-season top-five ProTeam predictions.

## Relationship to `procycling-clean-scraped-data`

The production repo contains a planning note that describes the intended separation of concerns between the two repositories.

| Repo | Intended role |
| --- | --- |
| `uci-points-optimization-model` | Production home for the app, deterministic pipelines, and stable artifacts |
| `procycling-clean-scraped-data` | Historical team/rider panels, calibration, exploratory analysis, and supporting datasets |

As of **April 20, 2026**, the private GitHub repo `jkriertran/procycling-clean-scraped-data` was accessible in this environment through authenticated GitHub and already contains the historical inputs needed to start implementation without a default rescrape.

### Verified upstream historical assets

| Upstream file | Verified coverage | New use in production repo |
| --- | --- | --- |
| `data/historical_proteam_team_panel.csv` | 100 ProTeam team-seasons across `2021`-`2026` | Seed canonical historical team-depth panel |
| `data/historical_proteam_rider_panel.csv` | 2,724 rider-seasons across `2021`-`2026` | Seed canonical historical rider-season panel |
| `data/procycling_proteam_analysis/ranking_predictor_study_data.csv` | 61 observed transitions from `2021->2022` through `2024->2025` | Baseline `next_top5_proteam` training table |
| `data/procycling_proteam_analysis/transition_continuity_links.csv` | Team continuity links across renamed teams | Resolve next-season team identity transitions |
| `manifests/historical_proteam_validation_summary.csv` | All listed checks currently `pass` | Import acceptance gate |
| `manifests/historical_proteam_missing_pages.csv` | Currently empty | Confirms no known missing upstream pages in this import set |

Codex should therefore follow this rule:

> **Import the stable historical outputs from `procycling-clean-scraped-data` into the production repo first. Do not rescrape historical ProTeam training data unless the import fails validation or required coverage is missing. Do not make the production app depend on the research repo at runtime.**

## Firecrawl Policy for This Project

The user explicitly wants Firecrawl incorporated into the data plan. Firecrawl is therefore a **day-one MCP requirement** for this project. The wrapper, caching, provenance, and fallback logic should ship in v1 even if the first sprint starts from imported historical data rather than live scraping.

At the same time, Firecrawl should **not** replace every current scraper or the verified upstream historical repo. The right architecture is a **tiered acquisition stack**.

| Priority | Acquisition path | Use case |
| --- | --- | --- |
| Tier 1 | Import validated historical outputs from `procycling-clean-scraped-data` | Default source for historical team/rider training data |
| Tier 2 | Reuse already-saved artifacts from local `data/` | Default source for current planning artifacts already saved in production |
| Tier 3 | Use existing direct scrapers (`fc_client.py`, `pcs_client.py`) | Use for refreshes, stable live pages, and current pipelines |
| Tier 4 | Use Firecrawl | Use when pages are dynamic, rate-limited, DOM-fragile, or need interaction / better extraction |
| Tier 5 | Use browser-assisted manual inspection or backup scrapers | Use only as fallback and for debugging |

Firecrawl should therefore be integrated as a **first-class day-one fallback and batch extraction layer**, not as a cosmetic add-on.

## What PCS Can Provide Versus What Must Be Engineered

PCS is highly useful but not sufficient by itself. It is strongest on **what happened**, especially rankings, team results, and rider point totals. It is weaker on **future accessibility**, **race fit**, and **counterfactual planning**.

### Field-by-field source map

| Field or feature | PCS | FirstCycling | Firecrawl | Other official / external | Internal engineering required | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| Team season points | Strong | Weak | Optional | UCI rankings can validate | Low | Pull from PCS first, validate with UCI where needed |
| Rider season points | Strong | Partial | Optional | UCI sometimes validates top-level rankings | Low | Pull from PCS first |
| Rider counted vs not-counted points | Strong | Weak | Optional | None obvious | Low | Pull from PCS |
| Team ranking by season | Strong | Weak | Optional | UCI official rankings | Low | Pull from PCS and optionally validate with UCI |
| Team ranking cycle totals | Strong | Weak | Optional | UCI official cycle rankings | Low | Pull from PCS, validate with UCI |
| Team roster by season | Strong | Partial | Optional | Team websites possible | Medium for normalization | Pull from PCS first |
| Team race calendars | Strong | Partial | Strong for brittle cases | Team websites and official race sites can help | Medium | Use PCS and existing saved calendars first, then Firecrawl if needed |
| Team race results | Strong | Partial | Strong | Official race pages can validate | Medium | Use PCS first |
| Team-in-race rider points attribution | Strong | Weak | Strong if DOM is inconsistent | None obvious | Low | Use PCS team-in-race pages |
| Rider threshold counts such as 50+, 100+, 150+, 300+ | Derivable | Partial | Optional | None | High | Engineer internally from rider-season points |
| Concentration metrics such as top-1, top-3, top-5 share | Derivable | Weak | Optional | None | High | Engineer internally from rider points |
| Effective contributors | Derivable | Weak | Optional | None | High | Engineer internally |
| Historical participation patterns | Strong | Partial | Strong | None | Medium | Use PCS schedules and results |
| Race category and metadata | Strong | Strong | Optional | UCI rules and calendars | Low | Use FirstCycling plus PCS with normalization |
| Historical race payout opportunity | Partial | Strong | Optional | UCI rules PDF and regulations | Medium | Use FirstCycling plus canonical internal payout tables |
| Extended historical startlist form | Weak | Strong | Strong if direct scraper breaks | None | Medium | Use FirstCycling, with Firecrawl fallback |
| Field softness / startlist strength score | Not native | Derivable | Helpful | None | High | Engineer internally from startlists and rider form proxies |
| Route structure proxies | Partial | Partial | Strong | Official race sites may help | High | Use hybrid internal engineering |
| Rider archetypes such as banker, engine, sprinter, GC | Weak | Weak | Optional | Team sites and media profiles can help | High | Engineer internally |
| Future lineup certainty | Weak | Weak | Limited | Team announcements, media sources | High | Treat as scenario input, not observed truth |
| Organizer invitation behavior | Weak | Weak | Possible via announcements | UCI, race websites, historical invites | High | Engineer with caution and document assumptions |
| Transfer effects and roster continuity | Partial | Weak | Possible | PCS transfers pages, team sites | High | Engineer internally |
| Team top-five target labels | Partial | Weak | Optional | UCI rules and ranking definitions | High | Create an internal target table |

## Practical Data-Source Rules for Codex

Codex should follow the following source hierarchy when building the new system.

### Rule 0: Import validated historical datasets from `procycling-clean-scraped-data` first

Before scraping historical ProTeam data, import and validate the stable upstream tables that already exist.

| Upstream file | Use in new model | Minimum acceptance gate |
| --- | --- | --- |
| `data/historical_proteam_team_panel.csv` | Historical team-depth features | Required columns for team rank, points, and threshold counts exist |
| `data/historical_proteam_rider_panel.csv` | Historical rider panel | Required columns for rider points, racedays, and team linkage exist |
| `data/procycling_proteam_analysis/ranking_predictor_study_data.csv` | Baseline `next_top5_proteam` model training | Required columns for `prior_n_riders_150` and `next_top5` exist |
| `data/procycling_proteam_analysis/transition_continuity_links.csv` | Rename and continuity joins | Team continuity keys import cleanly |
| `manifests/historical_proteam_validation_summary.csv` | Upstream validation evidence | All listed checks are `pass` |
| `manifests/historical_proteam_missing_pages.csv` | Missing-page audit | File is empty or any rows are explicitly triaged |

Imported historical files should land under `data/imported/procycling_clean_scraped_data/` together with import metadata that records source repo, source path, fetch date, and validation status.

If any required upstream file fails validation, Codex should write an explicit rejection note and only then scrape the missing component.

### Rule 1: Reuse saved production artifacts next

After upstream historical imports are landed, inspect and reuse these local data families if they already contain the necessary information.

| Existing artifact | Likely use in new model |
| --- | --- |
| `data/race_editions_snapshot.csv` | Historical race-opportunity features |
| `data/proteam_risk_current_snapshot.csv` | Current team concentration metrics |
| `data/proteam_risk_cycle_2026_2028_snapshot.csv` | Multi-season counted-points context |
| `data/team_calendars/*.csv` | Team participation histories and planning calendars |
| `data/team_results/*.csv` | Actual team points by race |
| `data/team_ev/*.csv` | Team-season race-level expected-value history |
| `data/team_profiles/*.json` | Team priors and scenario assumptions |

### Rule 2: Use direct scrapers when stable and simple

Use the current direct scrapers for reproducible pipelines that already work.

| Existing client | What it already does | Keep or replace? |
| --- | --- | --- |
| `uci_points_model/fc_client.py` | Pulls calendars, race results, stage pages, and extended startlist stats from FirstCycling | Keep and extend |
| `uci_points_model/pcs_client.py` | Pulls team rankings and rider counted / not-counted breakdowns from PCS | Keep and extend |

### Rule 3: Ship Firecrawl in v1 and use it whenever reliability or depth matters

Firecrawl should be introduced for the following cases.

| Firecrawl use case | Why it is needed |
| --- | --- |
| Dynamic or DOM-fragile pages on PCS or FirstCycling | More resilient extraction than brittle handcrafted parsing alone |
| Batch crawling of season pages or team pages | Better managed structured extraction across many URLs |
| Pages requiring richer DOM understanding, screenshots, or interaction | Fits the intended strength of Firecrawl |
| Official UCI regulations, ranking pages, PDFs, or linked documents | Firecrawl can be used to capture and normalize hard-to-parse content |
| Debugging mismatches between saved data and live site pages | Firecrawl can provide a second extraction path and a stronger audit trail |

The important implementation point is that Firecrawl should exist in the repo from day one, but it should be invoked **after** imported historical data, saved production artifacts, and stable direct scrapers have been considered.

### Rule 4: Engineer planning features internally

No public source will hand you the final planning dataset ready-made. The most important features must be computed internally.

| Internally engineered feature | Why it must be built in-house |
| --- | --- |
| `n_riders_150_plus` and related thresholds | This is an aggregate planning metric, not a native source field |
| `score_depth_index` | Composite metric specific to your thesis |
| Concentration and fragility metrics | Derived from rider scoring distribution |
| Rider archetype labels | Requires project-specific definitions |
| Field softness scores | Requires combining startlists and rider proxies |
| `next_top5_proteam` target labels | Requires explicit business-rule definitions and continuity handling |
| Rider-to-race pathway attribution | Requires custom allocation logic |

## Unified Target Architecture

Codex should build a multi-level model stack instead of a single monolithic prediction.

| Model | Unit | Primary target | Role |
| --- | --- | --- | --- |
| Model A | race-edition or team-race | accessible points / expected points | Measures opportunity |
| Model B | rider-season | rider reaches 150 points next season | Explains rider development and scoring pathways |
| Model C | team-season | `next_top5_proteam` | Gives the executive answer |

The stack should flow from the bottom upward.

> Race opportunity should feed rider scoring pathways, and rider pathways should feed team-depth and top-five ProTeam forecasts.

## Canonical Targets to Build

Codex should create explicit targets and not rely on only one label.

| Target | Unit | Definition |
| --- | --- | --- |
| `next_top5_proteam` | team-season | 1 if team finishes top five among ProTeams next season |
| `n_riders_50_plus` | team-season | Count of riders with at least 50 points |
| `n_riders_100_plus` | team-season | Count of riders with at least 100 points |
| `n_riders_150_plus` | team-season | Count of riders with at least 150 points |
| `n_riders_300_plus` | team-season | Count of riders with at least 300 points |
| `rider_reaches_150_next_season` | rider-season | 1 if rider clears 150 points next season |
| `rider_next_points` | rider-season | Rider total points next season |

## Canonical Data Tables to Build

### 1. Team-season panel

This is the executive planning table.

| Field | Description |
| --- | --- |
| `team_slug` | Stable team identifier |
| `season` | Current season |
| `next_season` | Following season |
| `team_points_total` | Current season total team points |
| `proteam_rank` | Current ProTeam rank |
| `next_proteam_rank` | Next-season ProTeam rank |
| `next_top5_proteam` | Binary target |
| `n_riders_50_plus` | Threshold count |
| `n_riders_100_plus` | Threshold count |
| `n_riders_150_plus` | Threshold count |
| `n_riders_300_plus` | Threshold count |
| `top1_share` | Share of team points from top rider |
| `top3_share` | Share from top three riders |
| `top5_share` | Share from top five riders |
| `effective_contributors` | Breadth metric |
| `points_outside_top5` | Non-core scoring depth |
| `score_depth_index` | Composite internal depth metric |
| `banker_count` | Count of banker-type riders if archetyping is added |
| `engine_count` | Count of engine-type riders if archetyping is added |

### 2. Rider-season panel

This is the rider pathway table.

| Field | Description |
| --- | --- |
| `rider_slug` | Stable rider identifier |
| `rider_name` | Rider name |
| `team_slug` | Current team |
| `season` | Current season |
| `age` | Rider age |
| `points_total` | Current season total points |
| `race_days` | Number of race days if available |
| `starts` | Starts or events if available |
| `scoring_races` | Races with points |
| `avg_points_per_scoring_race` | Efficiency metric |
| `points_one_day` | One-day points if derivable |
| `points_stage` | Stage-race-related points if derivable |
| `points_gc` | GC-related points if derivable |
| `points_tt` | Time-trial-related points if derivable |
| `category_mix_*` | Shares by race category |
| `rider_reaches_150_next_season` | Binary target |
| `rider_next_points` | Regression target |

### 3. Rider-race opportunity table

This is the bridge table that does not yet really exist in production form and should be added.

| Field | Description |
| --- | --- |
| `team_slug` | Team identifier |
| `rider_slug` | Rider identifier |
| `planning_year` | Season |
| `race_id` | Race identifier |
| `race_name` | Race name |
| `category` | Race category |
| `expected_team_points_race` | Team EV already available or derived |
| `rider_fit_score` | Rider-specific race fit |
| `rider_fit_multiplier` | Deterministic multiplier |
| `start_probability` | Probability rider starts that race |
| `share_of_team_opportunity` | Deterministic allocation share |
| `expected_rider_points_race` | Rider race-level EV |
| `pathway_to_150_contribution` | Share of rider seasonal threshold path attributable to that race |

## Firecrawl-Aware Data Acquisition Build Plan

Codex should add a dedicated data-acquisition layer that can choose between imported upstream history, saved production data, direct scrapers, and Firecrawl.

### Proposed file additions

```text
uci_points_model/
  data_sources.py
  firecrawl_client.py
  historical_data_import.py
  source_registry.py
  team_depth_features.py
  rider_threshold_model.py
  top5_proteam_model.py
  rider_race_pathways.py
  target_definitions.py

scripts/
  audit_existing_data_assets.py
  import_historical_proteam_data.py
  validate_historical_import.py
  build_team_depth_panel.py
  build_rider_season_panel.py
  build_rider_race_opportunities.py
  build_top5_proteam_training_table.py
  fit_top5_proteam_baseline.py
  fit_rider_threshold_baseline.py
  backtest_top5_proteam.py
  backtest_rider_thresholds.py
```

### Historical import landing zone

Imported upstream historical files should be copied into a stable local landing zone so production builds are reproducible without a live dependency on the research repo.

```text
data/
  imported/
    procycling_clean_scraped_data/
      historical_proteam_team_panel.csv
      historical_proteam_rider_panel.csv
      ranking_predictor_study_data.csv
      transition_continuity_links.csv
      import_metadata.json
```

The `import_metadata.json` file should record source repo, source path, fetch date, validation checks performed, and whether the import passed or failed.

### Source registry contract

Codex should create a small registry that decides where each field comes from.

| Component | Responsibility |
| --- | --- |
| `historical_data_import.py` | Imports validated upstream historical tables from local checkout or authenticated GitHub |
| `source_registry.py` | Maps fields to preferred source and fallback order by use case |
| `data_sources.py` | Loads imported upstream history and existing artifacts first, then chooses scraper path |
| `firecrawl_client.py` | Wraps Firecrawl extraction calls and structured outputs |

### Firecrawl integration requirements

The Firecrawl wrapper should support the following.

| Requirement | Description |
| --- | --- |
| URL batch crawling | Crawl many team pages, ranking pages, or race pages |
| Structured extraction | Return normalized records rather than raw HTML only |
| Screenshots or debug snapshots | Preserve auditability for brittle extractions |
| Retry and caching | Prevent unnecessary repeated requests |
| Save raw extracts | Persist raw or semi-raw outputs for reproducibility |
| Day-one availability | The wrapper must ship in the first sprint even if historical imports satisfy most early builds |
| Respect fallback order | Only call Firecrawl when saved data or direct scrapers are insufficient |

## Concrete Order of Execution for Codex

Codex should execute the project in the following order.

### Phase 1: Audit and reuse what already exists

| Step | Task | Expected output |
| --- | --- | --- |
| 1 | Verify access to `procycling-clean-scraped-data` via local checkout or authenticated GitHub | Upstream access note |
| 2 | Import `historical_proteam_team_panel.csv`, `historical_proteam_rider_panel.csv`, `ranking_predictor_study_data.csv`, and `transition_continuity_links.csv` into `data/imported/procycling_clean_scraped_data/` | Imported stable tables |
| 3 | Validate required columns, season coverage, and upstream manifests | Import validation report |
| 4 | Inspect local `data/` assets and identify which current-planning panels already exist | Asset inventory report |
| 5 | If any required upstream table fails validation, produce a scrape-gap list before scraping | Explicit rejection or scrape-gap note |

### Phase 2: Normalize raw team and rider history

| Step | Task | Expected output |
| --- | --- | --- |
| 6 | Build canonical `team_season_panel.csv` from imported team history plus local production artifacts where needed | One row per team-season |
| 7 | Build canonical `rider_season_panel.csv` from imported rider history plus richer rider result tables where needed | One row per rider-season |
| 8 | Build threshold counts and concentration features | Derived depth metrics |
| 9 | Build target labels for next-season top-five ProTeam status | Labeled training panel |

### Phase 3: Add Firecrawl-backed acquisition where needed

| Step | Task | Expected output |
| --- | --- | --- |
| 10 | Wrap Firecrawl in a reusable project client | `firecrawl_client.py` |
| 11 | Add fallback extraction for PCS and FirstCycling pages that fail direct parsing or are not covered upstream | More robust scraping path |
| 12 | Add audit logging for source choice on every extracted table | Source provenance columns |
| 13 | Persist raw Firecrawl outputs and import metadata where they affect stable datasets | Reproducible extraction cache |

### Phase 4: Build the rider and team modeling stack

| Step | Task | Expected output |
| --- | --- | --- |
| 14 | Reproduce the baseline logistic model for `next_top5_proteam` from `ranking_predictor_study_data.csv` using `n_riders_150_plus` | Transparent baseline model |
| 15 | Extend to a multivariate interpretable model with depth and concentration features | Improved but interpretable model |
| 16 | Fit rider-level threshold model for `rider_reaches_150_next_season` using imported rider history and transfer context where available | Rider-development model |
| 17 | Build deterministic rider-race allocation logic | Rider-race opportunity table |
| 18 | Aggregate rider forecasts back to team-level next-season depth projections | Team forecast features |

### Phase 5: Evaluation and productization

| Step | Task | Expected output |
| --- | --- | --- |
| 19 | Backtest team model across the 61 observed upstream transitions first, then expand when new seasons close | Team-model evaluation report |
| 20 | Backtest rider-threshold model across rolling rider seasons available in imported history | Rider-model evaluation report |
| 21 | Compare simple baseline versus richer stack | Benchmark table |
| 22 | Add app views or exported reports for top-five ProTeam planning | Product-facing outputs |
| 23 | Update docs, dictionaries, runbooks, and import metadata | Handoff-ready documentation |

## Detailed Modeling Guidance

### Team model baseline

Start simple. The first baseline should replicate the logic of the study from `data/imported/procycling_clean_scraped_data/ranking_predictor_study_data.csv` with as little complexity as possible.

| Baseline model | Inputs |
| --- | --- |
| Logistic regression | `n_riders_150_plus` only |
| Logistic regression plus concentration | `n_riders_150_plus`, `top5_share`, `effective_contributors` |
| Optional richer interpretable model | Add total team points, threshold counts, and continuity features |

The baseline model must remain in the repository permanently as the anchor benchmark.

### Rider model baseline

The rider model should start as a threshold model and not jump directly to an overfit points regression.

| Rider target | Suggested baseline |
| --- | --- |
| `rider_reaches_150_next_season` | Logistic regression or monotonic tree model |
| `rider_next_points` | Secondary regression target after threshold model works |

Suggested first-pass rider features should come from the imported historical rider files first, especially `historical_proteam_rider_panel.csv`, `rider_season_result_summary.csv`, and `rider_transfer_context_enriched.csv` where available. Suggested features include age, prior points, prior scoring races, category mix, route-type exposure, counted versus not-counted status where applicable, and continuity features such as same-team next season if available.

### Deterministic rider-race bridge

This is the most important new planning feature.

Codex should create a deterministic allocation layer that distributes a team’s race-level opportunity across riders using rider fit, start probability, and team-role heuristics. The first version does not need to be perfect. It needs to be explicit, testable, and scenario-friendly.

A simple first-pass formula can be:

> `expected_rider_points_race = expected_team_points_race * start_probability * rider_fit_multiplier * role_share`, with the final shares normalized within each team-race to avoid exceeding team-level opportunity.

That formula should be documented, versioned, and intentionally interpretable.

## Existing Production Assets That Should Feed the New System

Codex should explicitly reuse existing production files rather than recreating them.

| Existing asset | New use |
| --- | --- |
| `data/team_ev/*_calendar_ev.csv` | Team-race opportunity anchors |
| `data/team_results/*_actual_points.csv` | Realized team-race points |
| `data/team_calendars/*_latest.csv` | Participation histories and scheduling context |
| `data/proteam_risk_current_snapshot.csv` | Concentration features |
| `data/proteam_risk_cycle_2026_2028_snapshot.csv` | Multi-season counted-points context |
| `uci_points_model/pcs_client.py` | PCS acquisition for rankings and rider contribution breakdowns |
| `uci_points_model/fc_client.py` | FirstCycling acquisition for race-edition and startlist form data |

## Verified Upstream Historical Assets That Should Feed the New System

Codex should also explicitly import the already-built historical repo outputs before defaulting to new scraping.

| Upstream asset | New use |
| --- | --- |
| `data/historical_proteam_team_panel.csv` | Historical team-depth seed table |
| `data/historical_proteam_rider_panel.csv` | Historical rider-season seed table |
| `data/procycling_proteam_analysis/ranking_predictor_study_data.csv` | Baseline `next_top5_proteam` training table |
| `data/procycling_proteam_analysis/transition_continuity_links.csv` | Team rename and continuity mapping |
| `data/procycling_proteam_analysis/rider_season_result_summary.csv` | Rider-level starts, finishes, scoring splits, and detailed point breakdowns |
| `data/procycling_proteam_analysis/rider_transfer_context_enriched.csv` | Transfer and continuity covariates for the rider model |
| `data/procycling_proteam_analysis/race_page_rider_results.csv.gz` | Detailed rider-race result history for rider-pathway work |
| `data/procycling_proteam_analysis/race_entries_pts_v2.csv` | Team-in-race points context for rider-race bridge construction |

## Files Codex Should Create or Update

### New modules

| File | Purpose |
| --- | --- |
| `uci_points_model/firecrawl_client.py` | Firecrawl wrapper and extraction helpers |
| `uci_points_model/historical_data_import.py` | Import and validation helpers for upstream historical datasets |
| `uci_points_model/source_registry.py` | Field-to-source mapping and fallback order |
| `uci_points_model/team_depth_features.py` | Team-season threshold and concentration features |
| `uci_points_model/rider_threshold_model.py` | Rider 150-plus threshold modeling |
| `uci_points_model/top5_proteam_model.py` | Team next-season top-five ProTeam model |
| `uci_points_model/rider_race_pathways.py` | Deterministic rider-race opportunity allocation |
| `uci_points_model/target_definitions.py` | Explicit target labels and business rules |

### New scripts

| File | Purpose |
| --- | --- |
| `scripts/audit_existing_data_assets.py` | Scan current repo assets and schemas |
| `scripts/import_historical_proteam_data.py` | Import stable upstream historical data into the production repo |
| `scripts/validate_historical_import.py` | Validate imported upstream schemas, coverage, and manifest status |
| `scripts/build_team_depth_panel.py` | Create team-season depth panel |
| `scripts/build_rider_season_panel.py` | Create rider-season panel |
| `scripts/build_rider_race_opportunities.py` | Build rider-race bridge table |
| `scripts/build_top5_proteam_training_table.py` | Assemble team model training data |
| `scripts/fit_top5_proteam_baseline.py` | Fit baseline team model |
| `scripts/fit_rider_threshold_baseline.py` | Fit baseline rider model |
| `scripts/backtest_top5_proteam.py` | Backtest team top-five model |
| `scripts/backtest_rider_thresholds.py` | Backtest rider threshold model |

### New documentation

| File | Purpose |
| --- | --- |
| `docs/unified_top5_proteam_model_spec.md` | Master modeling specification |
| `docs/historical_import_contract.md` | Upstream import workflow, validation gates, and fallback policy |
| `docs/source_map_and_data_contract.md` | Source map, field definitions, fallback rules |
| `docs/firecrawl_integration.md` | Firecrawl usage, caching, provenance, and failure policy |
| `docs/rider_race_pathways_spec.md` | Deterministic rider-race allocation logic |

## Required Test Plan

The new surface area should ship with an explicit pytest track instead of only relying on manual inspection.

| Test layer | What must be covered |
| --- | --- |
| Upstream contract tests | Imported files have required columns, expected season coverage, and passing manifest status |
| Transform unit tests | Threshold counts, concentration metrics, continuity joins, and target definitions are correct on small fixtures |
| Script smoke tests | Team-depth, rider-season, and top-five training-table scripts run end to end on tiny fixture inputs |
| Acquisition fallback tests | Source registry order, Firecrawl fallback, caching, and provenance columns behave as expected without live network dependency |

Suggested initial pytest files:

- `tests/test_historical_data_import.py`
- `tests/test_target_definitions.py`
- `tests/test_team_depth_features.py`
- `tests/test_source_registry.py`
- `tests/test_firecrawl_client.py`
- `tests/test_build_team_depth_panel.py`
- `tests/test_build_rider_season_panel.py`
- `tests/test_top5_proteam_model.py`

## Acceptance Criteria

Codex should consider the project complete only when the following are true.

| Requirement | Done means |
| --- | --- |
| Upstream historical import exists | Validated copies of the required upstream team, rider, transition, and continuity files exist under `data/imported/procycling_clean_scraped_data/` with metadata |
| Team-depth table exists | There is a deterministic team-season panel with threshold counts and concentration features |
| Rider-season table exists | There is a deterministic rider-season panel with threshold labels |
| Firecrawl is integrated | A project wrapper exists in v1 and is used when direct scrapers fail or when configured by source rules |
| Saved assets are reused | The pipeline preferentially loads imported upstream data and existing repo data before scraping |
| Baseline team model exists | `n_riders_150_plus` baseline can be fit and reproduced for `next_top5_proteam` |
| Rider model exists | A baseline model predicts whether a rider reaches 150 points next season |
| Rider-race bridge exists | A deterministic pathway from race opportunity to rider opportunity is implemented |
| Source provenance is explicit | Every built dataset includes source markers and extraction timestamps |
| Tests exist and pass | Contract, transform, smoke, and fallback tests cover the new modules and scripts |
| Documentation is complete | A human can understand fields, targets, assumptions, and caveats |

## Non-Negotiable Implementation Rules

| Rule | Meaning |
| --- | --- |
| Start from imported historical repo data | Do not rescrape historical ProTeam training data unless the upstream import fails validation or is missing required coverage |
| Reuse existing production artifacts first | Do not rescrape what is already saved and good enough |
| Do not depend on the research repo at runtime | Promote only stable outputs if needed |
| Integrate Firecrawl as a day-one real fallback layer | Do not mention Firecrawl without wiring it into the pipeline in v1 |
| Preserve interpretability | Keep the simple team-depth baseline permanently |
| Separate observed from forecast data | Do not blur realized points with projected points |
| Separate team-level and rider-level logic | Do not hide rider pathways inside opaque team totals |
| Keep scenario logic deterministic in v1 | Favor explicit rules over premature complexity |

## Locked Decisions

| Decision | Canonical choice |
| --- | --- |
| Team-level target | Use `next_top5_proteam` only |
| Historical training-data source | Import from `procycling-clean-scraped-data` before scraping |
| Firecrawl | Required in v1 as a day-one MCP-backed fallback layer |
| Invitation behavior | Out of scope for v1 target definition |
| Rider target priority | Forecast threshold crossing first, points regression second |

## Remaining Open Questions

| Question | Why it matters |
| --- | --- |
| Whether rider transfers should enter the v1 rider model as required features or only as opportunistic enrichment | Affects how hard the rider baseline depends on transfer context coverage |
| Whether partial `2026` rider-season data should be training-disabled until the season closes | Prevents leakage and inconsistent labels |
| Whether the first rider-race bridge should use only deterministic role shares or also imported race-entry history | Affects v1 complexity and explainability |

## Recommended First Codex Sprint

If Codex should start with only one sprint, it should do this:

1. Import and validate the upstream historical datasets from `procycling-clean-scraped-data`.
2. Audit the existing production repo data assets and map the joins to those imported tables.
3. Build the canonical team-season panel and reproduce the `next_top5_proteam` baseline study inside the production repo.
4. Add Firecrawl as a day-one acquisition layer with caching, provenance, and explicit fallback order.
5. Build the rider-season panel and a first-pass `rider_reaches_150_next_season` model from imported history plus richer rider result tables.
6. Ship the import-contract tests, transform tests, and script smoke tests with the first sprint.

That sprint will convert the current project from a race EV tool into the first real version of a **top-five ProTeam planning system** without opening with a broad historical rescrape.

## Final Instruction to Codex

Codex should treat this project as an **evolutionary build**, not a rewrite. The current repository already contains meaningful production logic, saved artifacts, and source-specific scrapers, and the upstream historical repo already contains the first training panels needed to start. The job is to **reuse what exists, import validated historical data before rescraping, fill the depth-modeling gap, add Firecrawl where it improves data reliability, and create a clean bridge from race opportunity to rider depth to top-five ProTeam probability**.
