# UCI Points Optimization Model Study Guide

This guide is meant to help you explain the app clearly to another person, whether that person is technical or not.

Use it in layers:

- start with the 30-second version
- move to the 2-minute version if they want more detail
- use the math and FAQ sections if they push deeper

## 30-Second Explanation

This app has two main jobs:

- rank `.1` and `.Pro` races as historical UCI points opportunities
- monitor how concentrated a ProTeam's counted UCI points are across its rider base

It is not a rider-prediction tool.

It asks:
"Which races have historically offered the best UCI points opportunities relative to how hard the field looked?"

It does that by combining:

- how many points the race paid
- how strong the startlist looked before the race
- how reliable the race is as a scoring opportunity

Then it cross-checks those recommendations against the live planning-season calendar, so you can see whether a suggested target actually exists this year.

## 2-Minute Explanation

The core idea is that a "good" race is not simply a race with big UCI points.

A race is attractive when:

- the payout is strong
- the field is manageable
- the event tends to produce usable scoring opportunities

So the model tries to capture a practical team-planning question:

"Where can a team most efficiently score points?"

It uses public FirstCycling data and works at the race level.

That is important:

- it does not try to predict exactly what Rider A will do
- it does not try to forecast exact team points
- it is not trying to simulate a full roster strategy

Instead, it evaluates races as opportunities.

For each race edition, the app looks at:

- the actual points paid out in results
- the extended startlist
- for stage races, both GC points and individual stage-result points

Then it estimates field strength using a simple rider-form proxy, converts the inputs to percentiles so they are comparable, and combines them into one "arbitrage score." The app also includes a lightweight beta route-profile x specialty-fit overlay, but that layer is still intentionally simple and inferred from event structure rather than full GPX analysis.

Finally, it aggregates repeated race histories, handles category changes explicitly, checks whether a recommended race is actually on the current planning-season calendar, and includes a separate ProTeam Risk Monitor for rider-contribution concentration.

## What Problem The App Solves

The app is designed for a team or analyst asking:

- Which races should we target next season?
- Which events look like better points opportunities than they might appear at first glance?
- Where is the best balance of payout and manageable competition?

That is why the app is about race opportunity, not rider forecasting.

## What The App Is Not

It is important to say what this app does not do.

It is not:

- a rider-versus-rider model
- a team selection optimizer
- a travel-cost model
- a full route-GPX or parcours model
- a prediction of exact UCI points for a specific roster

If someone asks whether the model predicts what a specific team will score, the honest answer is:

"No. It ranks races as historical scoring opportunities."

## Unit Of Analysis

The unit of analysis is the race edition.

That means each historical row is one specific edition of one race in one year.

Examples:

- Tro-Bro Leon 2024
- Tour of Oman 2023
- Tour de Hongrie 2025

For stage races, the race is still one target, but the app now includes the scoring value of both:

- GC
- stage results

So a stage race is treated as one event with multiple scoring opportunities inside it.

## The Data Inputs

The race-targeting side of the app uses public FirstCycling pages:

- calendar pages
- results pages
- extended startlist pages
- stage-result pages for stage races

From those pages, it pulls:

- race identity
- category
- date
- results and UCI points
- startlist rider records like Starts, Wins, Podium, Top 10

The ProTeam monitor uses:

- rider-by-rider counted UCI team points as surfaced on ProCyclingStats
- bundled CSV snapshots of that PCS/UCI view for deployment stability

That distinction matters:

- the ProTeam monitor is about **UCI team points**
- PCS is mainly the delivery layer because it exposes rider-level team breakdowns
- it is not using a separate PCS proprietary ranking for that monitor

## The Main Modeling Logic

The model has five main steps.

### Step 1: Estimate Rider Form

The model uses a simple rider-form proxy based on the extended startlist.

Formula:

```text
rider_form
= 5 * wins
+ 2 * (podiums - wins)
+ 1 * (top10s - podiums)
+ 0.1 * starts
```

Plain-English meaning:

- wins matter the most
- podiums matter next
- top-10 depth matters too
- starts add a small amount of recent activity

Why this exists:

The app needs a public, explainable way to estimate how hard the field looked before the race.

This is not a perfect power rating. It is a transparent proxy.

### Step 2: Turn Rider Form Into Field Strength

Once every rider has a form score, the app creates field-level measures.

Formulas:

```text
top10_field_form = sum of the 10 strongest rider_form values
avg_top10_field_form = top10_field_form / 10
total_field_form = sum of all rider_form values in the field
```

Interpretation:

- `avg_top10_field_form` tells you how strong the sharp end of the field looked
- `total_field_form` tells you how strong the whole field looked

Lower values mean a softer field.

### Step 3: Measure Points Available

For one-day races, the app takes the points from the race result table.

For stage races, it adds together:

- GC points
- stage-result points

Conceptually:

```text
event_top10_points = gc_top10_points + sum(stage_top10_points)
event_winner_points = gc_winner_points + sum(stage_winner_points)
```

This matters because a stage race is not only a GC opportunity. It is a bundle of stage-level scoring opportunities too.

### Step 4: Convert Everything To Percentiles

The raw measures are on different scales, so the app converts them into percentiles inside the selected dataset.

The main percentile components are:

- top-10 points percentile
- winner-points percentile
- top-rider softness percentile
- full-field softness percentile
- finish-rate percentile

The "softness" percentiles reverse field strength so that softer fields score higher.

That means:

- more points is better
- softer field is better
- higher finish rate is better

Percentiles make the pieces comparable.

### Step 5: Combine The Components Into One Score

The app computes one final arbitrage score as a weighted combination of those percentiles.

Current default weights:

- top10_points = 0.2704
- winner_points = 0.1139
- field_softness = 0.1052
- depth_softness = 0.3074
- finish_rate = 0.2031

Conceptually:

```text
arbitrage_score
= weight_1 * top10_points_pct
+ weight_2 * winner_points_pct
+ weight_3 * field_softness_pct
+ weight_4 * depth_softness_pct
+ weight_5 * finish_rate_pct
```

Interpretation:

- higher score means a more attractive historical scoring opportunity
- the score is not a probability
- the score is a ranking device

## Why The Math Looks Like This

If someone asks "why this math?", the best answer is:

"Because the app is trying to balance reward and difficulty."

More specifically:

- points payout captures reward
- field-strength proxies capture difficulty
- finish rate captures event reliability

That is why the app does not just rank races by points and does not just rank races by weak fields. It tries to combine both sides of the tradeoff.

## Why Use Percentiles

Percentiles help because the raw metrics are very different.

For example:

- points may be in the hundreds
- finish rate is a proportion
- field-form values are synthetic scores

By converting each one to a 0-100 relative scale, the app makes the weighted combination easier to interpret and more stable.

## Why The Model Is Race-Level, Not Rider-Level

This is one of the most important ideas in the app.

The app is trying to answer:

"Which races are usually good opportunities?"

It is not trying to answer:

- "Will Rider X beat Rider Y?"
- "How many points will this exact seven-rider roster score?"

That is why the backtest and the ranking logic operate at the race level.

A good way to explain it:

"This app is about where to hunt, not exactly who will make the kill."

## How Stage Races Are Handled

Stage races stay as one planning target because a team enters the full event, not isolated stages.

But the app no longer treats them as GC-only.

Instead, it includes:

- GC points
- stage-result points

So the right explanation is:

"A stage race is one target with several internal scoring chances."

## How Category Changes Are Handled

This is another important point.

Races do not always keep the same category.

A race can move:

- from `1.1` to `1.Pro`
- from `2.1` to `2.Pro`
- down to `.2`

The app now handles that explicitly.

It does this by treating:

`race_id + category`

as the historical target, not just `race_id`.

That means:

- the `1.1` history of a race is separate from its `1.Pro` history
- the model does not blend those histories together as if nothing changed

For planning, the app keeps the latest known category as the current live target and shows the full category path for context.

Example:

```text
Figueira Champions Classic
Category History: 1.1 -> 1.Pro
```

## How The Current-Season Calendar Overlay Works

Historical recommendations are not enough by themselves.

A race might look attractive historically but not even exist on this year's calendar, or it may have moved out of scope.

So the app checks recommendations against the live planning-season calendar.

That gives you columns like:

- current-year category
- current-year date
- calendar status

Possible outcomes:

- on the current `.1/.Pro` calendar
- on the current calendar but out of scope, like `.2`
- not found on the current calendar

This makes the shortlist actionable instead of purely historical.

## How The ProTeam Risk Monitor Works

The ProTeam monitor is a separate lens on the same planning problem.

Instead of asking:

"Which races look attractive?"

it asks:

"How concentrated are a ProTeam's counted UCI points?"

That matters because a team can look healthy in the ranking table, but still be fragile if one rider is doing most of the work.

One important source detail:

- the monitor uses **UCI team points as shown on PCS**
- PCS is used because it exposes rider-by-rider counted-point breakdowns
- the official UCI site is the rules source, but PCS is the practical rider-breakdown source

The monitor therefore uses rider-by-rider counted team points and computes concentration metrics such as:

- `Top-1 Share`
- `Top-3 Share`
- `Top-5 Share`
- `Effective Contributors`
- leader shock tests

Simple examples:

- if one rider has 40% of the team's counted points, that is high concentration
- if removing the top 2 riders wipes out most of the team total, that is structural risk

This module is still not forecasting exact rider performance.

It is a monitoring dashboard that helps answer:

- how dependent is this team on one rider?
- how deep is the real scoring base?
- how vulnerable is the team if its leader gets injured or loses form?

### What The Data Check Flag Means

The `Data Check` flag is a source-reconciliation warning.

It does **not** mean:

- the team is risky
- the model is broken
- the team is bad

It means the team total shown in the ranking table did not fully match the total implied by the rider breakdown table.

In plain English:

- `OK` means the ranking-table total and rider breakdown mostly agree
- `Warning` means there is a noticeable gap between them

That can happen because PCS updated one table before the other, omitted a rider row, or handled a source-side reconciliation detail differently.

### Why Some Teams Can Have Zero Counted Riders

A team can still appear in the current-season monitor even if it has:

- `0` counted points
- `0` counted riders

That usually means the team is present in the ranking table but PCS does not yet show any counted rider rows for that scope.

The app now keeps those teams in the monitor instead of dropping them silently.

So if you see a team with no leader and no counted riders, the right interpretation is:

"This team exists in the ranking table, but it has not yet built a counted points base in this scope."

### How Freshness Works In The Deployed App

The deployed app is intentionally snapshot-first for the ProTeam monitor.

That means:

- the app normally reads the latest bundled snapshot
- it shows the snapshot refresh timestamp in the UI
- a scheduled GitHub Actions job refreshes those snapshots in the background

Why this exists:

- live PCS fetches can be blocked in hosted environments
- snapshots make the deployed app more stable

So the right explanation is:

"The monitor is designed to show the latest successful bundled refresh, not to depend on a live PCS request every time a user opens the tab."

## What The Backtest Is Doing

The backtest is trying to answer:

"Do these weights help identify good future race opportunities?"

It does this with walk-forward testing.

This is a time-aware backtest, not ordinary random k-fold cross-validation.

In plain English, that means:

- use only earlier years to train
- test on the next year
- then roll the window forward and repeat

If you want a general reference for the math behind this kind of time-series split, the [scikit-learn TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) is a good place to start.

Example:

- train on earlier years
- predict which races look attractive next year
- compare those predictions to what actually happened in the next year's edition

The backtest is still race-level.

It does not test rider predictions.

One important implication is that the earliest possible test year is the third loaded historical year, because the app requires two prior training years before it will score a fold.

Example:

- if you load `2021-2025`, the valid test years are `2023`, `2024`, and `2025`
- if you load `2020-2025`, the first possible test year becomes `2022`

The app also keeps `2020` available only as a sensitivity-check year, not in the default selection. That is because the COVID-disrupted 2020 calendar was unusually irregular, so it is a weaker baseline for normal-season planning.

## What The Backtest Uses As The Outcome

The main outcome is race efficiency:

```text
actual_points_efficiency = top10_points / top10_field_form
```

That is a simple way to express:

"How many points were available relative to how hard the top of the field was?"

It is not perfect, but it is aligned with the app's main planning question.

## How The Backtest Is Scored

The backtest combines three ideas:

- Spearman correlation
- Top-k precision
- Top-k value capture

Objective:

```text
objective
= 0.60 * normalized_spearman
+ 0.20 * top_k_precision
+ 0.20 * top_k_value_capture
```

Plain-English meaning:

- did the model rank races in roughly the right order?
- did it identify the best races near the top?
- did the shortlist capture a lot of the real value?

## How To Explain The Weights

The current default weights are calibrated, not just hand-picked.

That means:

- we started with intuitive weights
- then ran a walk-forward backtest
- and adopted the set that performed better on historical future folds

The important message is:

"The weights are not random, and they are not purely subjective anymore. They are empirically tuned against a race-level historical objective."

## The Best Defense Of The Model

If someone challenges the model, the strongest honest defense is:

1. It is transparent.
2. It uses public data.
3. It is aligned to a practical planning problem.
4. It is backtested.
5. It is explicit about what it does not model.

That is a better defense than pretending it predicts everything.

## Main Assumptions

These are the assumptions you should be ready to say out loud.

### Assumption 1: Public Startlist Stats Can Approximate Field Difficulty

This is a proxy assumption.

The model assumes that Starts, Wins, Podium, and Top 10 are enough to say something useful about field strength.

### Assumption 2: Historical Editions Tell Us Something About Future Opportunity

The model assumes repeated races have some continuity in their opportunity profile.

### Assumption 3: Race-Level Planning Is A Useful First Step

The model assumes a team first decides where to race, and only later decides exactly who to send.

### Assumption 4: Latest Known Category Matters More Than Older Categories

The model assumes that if a race changed class, the latest version is the relevant one for planning.

## Main Limitations

These are the biggest limitations.

- startlist form is a proxy, not a true power model
- route and rider fit are still only a lightweight beta overlay inferred from event structure, not full GPX-based route modeling
- no team roster simulation yet
- no travel or logistics costs
- no conflict modeling across multiple simultaneous race options
- no guarantee that a historically soft race will stay soft
- the ProTeam monitor depends on PCS exposing rider-level UCI point breakdowns cleanly

If someone asks whether the model is perfect, the right answer is:

"No. It is a transparent decision-support tool, not a crystal ball."

## Likely Questions And Strong Answers

### "Why not just rank races by UCI points?"

Because points alone miss difficulty.

A race can pay well and still be a terrible target if the field is too strong. The app is trying to estimate value, not just size of prize.

### "Why not just rank races by weak fields?"

Because weak fields alone miss payout.

A very soft race is not automatically attractive if the points on offer are too small.

### "Why not predict exact team points?"

That is a much harder and more assumption-heavy problem.

You would need:

- team rosters
- rider specialties
- route fit
- travel decisions
- team tactics

This app is designed as the race-selection layer that comes before that.

### "Are the ProTeam points official UCI points or PCS points?"

For the ProTeam monitor, they are **UCI team points as surfaced by PCS**.

That is an important distinction:

- the ranking logic is about UCI points
- PCS is used because it exposes the rider-by-rider team breakdown
- sometimes PCS tables do not reconcile perfectly, which is why the app includes the `Data Check` flag

So the clean answer is:

"The monitor is about UCI team points, but PCS is the practical source for the rider-level breakdown."

### "Why use percentiles instead of raw values?"

Because the model combines variables with different scales. Percentiles make them comparable and easier to combine.

### "Why is it called an arbitrage score?"

Because the idea is to find races where the points opportunity looks better than the difficulty would suggest.

### "How do you handle races that change category?"

We separate the history by `race + category`, then keep the latest known category for planning.

### "How do you know a recommendation is still relevant this season?"

The app now checks the recommendation against the live planning-season calendar and tells you whether it is on the current `.1/.Pro` calendar, out of scope, or missing.

### "How should a team actually use this?"

As a shortlist generator.

A team should use it to narrow the universe of possible races, then combine it with team-specific knowledge.

## A Good 5-Minute Presentation Script

Here is a clean explanation you can say almost word-for-word.

"This app is a UCI race-targeting tool. It does not predict exact rider outcomes. Instead, it ranks races by how attractive they have historically been as points opportunities."

"The logic is simple: a good target race is one where the payout is strong relative to how hard the field looks. So the model looks at actual historical points paid out and balances that against a public field-strength proxy built from the extended startlist."

"For each race edition, it calculates a rider-form score from wins, podiums, top-10s, and starts. It then turns that into top-end and full-field strength measures. On the payout side, it uses result-table points, and for stage races it now includes both GC and stage-result points."

"Those raw components are converted into percentiles so they can be compared on the same scale. Then the app combines them into a weighted arbitrage score. The current default weights were calibrated using a walk-forward backtest that checks whether past race history helps identify future efficient races."

"The app also handles category changes explicitly. If a race moved from 1.1 to 1.Pro, those histories are not blended together. And because historical recommendations are not enough by themselves, the app overlays the live planning-season calendar so you can see whether a recommended race actually exists this year and whether it is still in scope."

"Separately, the app now includes a ProTeam Risk Monitor. That module is not about forecasting riders. It uses rider-by-rider counted UCI team points, as exposed by PCS, to show how dependent a ProTeam is on one rider or a small core."

"So the best way to think about the app is: it is an explainable historical race-opportunity model, plus a ProTeam concentration monitor, that helps a team decide where to look first before doing roster-specific planning."

## What To Say If Someone Asks "What Would Improve This Next?"

The strongest answers are:

- add route-type modeling
- add rider-specialty or roster-fit modeling
- add team-level simulation
- add travel and scheduling constraints
- add uncertainty bands around recommendations

That shows you understand both the current value and the next frontier.

## Final Summary To Remember

If you only memorize one paragraph, memorize this:

"The app is an explainable, backtested race-selection model with a separate ProTeam concentration monitor. It ranks races by balancing historical points payout against historical field difficulty, using public FirstCycling data. It works at the race level, includes stage-race stage points, handles category changes explicitly, and checks whether recommended races are actually on the current-season calendar. Its ProTeam tab uses UCI team points as surfaced by PCS to show key-man risk. It is a decision-support tool, not an exact rider-performance predictor."
