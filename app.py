from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from uci_points_model.backtest import calibrate_weights
from uci_points_model.data import build_dataset, ensure_dataset_schema, load_calendar, load_snapshot
from uci_points_model.fc_client import PLANNING_CALENDAR_CATEGORIES, TARGET_CATEGORIES
from uci_points_model.model import (
    DEFAULT_WEIGHTS,
    normalize_weights,
    overlay_planning_calendar,
    score_race_editions,
    summarize_historical_targets,
)

SNAPSHOT_PATH = Path("data/race_editions_snapshot.csv")
DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025]
DEFAULT_PLANNING_YEAR = date.today().year
WEIGHT_STATE_KEYS = {name: f"weight_{name}" for name in DEFAULT_WEIGHTS}
WEIGHT_DEFAULT_VERSION = "calibrated-one-day-v1"
DATASET_SCHEMA_VERSION = "stage-breakdown-v1"
PENDING_WEIGHT_STATE_KEY = "pending_weight_state"
CALIBRATION_RESULT_VERSION = "category-aware-v1"


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def get_live_dataset(
    years: tuple[int, ...], categories: tuple[str, ...], max_races: int
) -> pd.DataFrame:
    return build_dataset(years=years, categories=categories, max_races=max_races)


@st.cache_data(show_spinner=False)
def get_calibration_result(
    dataset: pd.DataFrame, race_type: str, search_iterations: int, random_seed: int
) -> dict[str, object]:
    return calibrate_weights(
        dataset=dataset,
        race_type=race_type,
        search_iterations=search_iterations,
        random_seed=random_seed,
    )


@st.cache_data(show_spinner=False, ttl=60 * 60 * 12)
def get_planning_calendar(year: int, categories: tuple[str, ...]) -> pd.DataFrame:
    return load_calendar(year=year, categories=categories)


def initialize_weight_state() -> None:
    stored_version = st.session_state.get("weight_default_version")
    should_reset = stored_version != WEIGHT_DEFAULT_VERSION
    for weight_name, default_value in DEFAULT_WEIGHTS.items():
        session_key = WEIGHT_STATE_KEYS[weight_name]
        if should_reset or session_key not in st.session_state:
            st.session_state[session_key] = float(default_value)
    st.session_state["weight_default_version"] = WEIGHT_DEFAULT_VERSION


def apply_pending_weight_state() -> None:
    pending_weights = st.session_state.pop(PENDING_WEIGHT_STATE_KEY, None)
    if pending_weights is None:
        return
    apply_weight_state(pending_weights)


def initialize_dataset_state() -> None:
    if "dataset" in st.session_state:
        st.session_state["dataset"] = ensure_dataset_schema(st.session_state["dataset"])
    st.session_state["dataset_schema_version"] = DATASET_SCHEMA_VERSION


def current_weight_state() -> dict[str, float]:
    return normalize_weights(
        {weight_name: float(st.session_state[session_key]) for weight_name, session_key in WEIGHT_STATE_KEYS.items()}
    )


def apply_weight_state(weights: dict[str, float]) -> None:
    normalized = normalize_weights(weights)
    for weight_name, value in normalized.items():
        st.session_state[WEIGHT_STATE_KEYS[weight_name]] = float(value)


def queue_weight_state(weights: dict[str, float]) -> None:
    st.session_state[PENDING_WEIGHT_STATE_KEY] = normalize_weights(weights)


def dataset_signature(dataset: pd.DataFrame) -> tuple[int, tuple[int, ...], tuple[str, ...]]:
    if dataset.empty:
        return (0, tuple(), tuple())
    years = tuple(sorted(dataset["year"].unique().tolist()))
    categories = tuple(sorted(dataset["category"].unique().tolist()))
    return (len(dataset), years, categories)


def calibration_signature(
    calibration_dataset_source: str,
    calibration_dataset: pd.DataFrame,
    years: list[int],
    categories: list[str],
    calibration_race_type: str,
    search_iterations: int,
    random_seed: int,
) -> tuple[object, ...]:
    return (
        CALIBRATION_RESULT_VERSION,
        calibration_dataset_source,
        dataset_signature(calibration_dataset),
        tuple(sorted(years)),
        tuple(sorted(categories)),
        calibration_race_type,
        search_iterations,
        random_seed,
    )


def prepare_backtest_fold_detail(fold_detail: pd.DataFrame, selected_fold: int) -> pd.DataFrame:
    year_detail = fold_detail[fold_detail["test_year"] == selected_fold].copy()
    year_detail = year_detail.rename(
        columns={
            "race_name": "Race",
            "category": "Category",
            "category_history": "Category History",
            "race_country": "Country",
            "train_editions": "Train Editions",
            "train_years": "Train Years",
            "predicted_score": "Predicted Score",
            "actual_points_efficiency": "Actual Efficiency",
            "actual_top10_points": "Actual Top-10 Points",
            "actual_top10_field_form": "Actual Top-10 Field Form",
            "predicted_rank": "Predicted Rank",
            "actual_rank": "Actual Rank",
        }
    )

    if "Category History" not in year_detail.columns:
        if "Category" in year_detail.columns:
            year_detail["Category History"] = year_detail["Category"]
        else:
            year_detail["Category History"] = "Unknown"

    required_columns = [
        "Race",
        "Category",
        "Category History",
        "Country",
        "Train Editions",
        "Train Years",
        "Predicted Score",
        "Actual Efficiency",
        "Actual Top-10 Points",
        "Actual Top-10 Field Form",
        "Predicted Rank",
        "Actual Rank",
    ]
    for column_name in required_columns:
        if column_name not in year_detail.columns:
            year_detail[column_name] = "Unknown"

    return year_detail[required_columns]


def render_model_explainer(weights: dict[str, float], dataset: pd.DataFrame) -> None:
    error_count = int(dataset.attrs.get("error_count", 0))
    source_count = len(dataset)
    stage_race_count = int((dataset.get("race_type", pd.Series(dtype=str)) == "Stage race").sum())
    missing_stage_pages = int(dataset.get("stage_pages_missing", pd.Series(0)).sum())
    category_change_races = (
        int(dataset.groupby("race_id")["category"].nunique().gt(1).sum()) if not dataset.empty else 0
    )

    with st.expander("How the model works: idea, methods, and math", expanded=True):
        st.markdown("**What this app is actually for**")
        st.markdown(
            """
            - This app is **not** trying to predict exactly how many points a specific rider or team will score.
            - It is **not** a rider-vs-rider forecast model.
            - It **is** trying to rank races as **historical points opportunities**.
            - In plain language: it asks, "Which races have usually been the best value for scoring points?"
            """
        )

        st.markdown(
            """
            This app is trying to answer a practical racing question:
            for a team chasing UCI points, which `.1` and `.Pro` races have historically offered
            the best tradeoff between **points available** and **how hard the field looked**?
            """
        )

        overview_col, method_col = st.columns(2)

        with overview_col:
            st.markdown("**Overall idea**")
            st.markdown(
                """
                - High-value races are not just races with big payouts.
                - They are races where the payout has been strong **relative to the level of the field**.
                - The model therefore rewards high points and penalizes historically strong startlists.
                - Output should be treated as a targeting shortlist for planners, not an autopilot schedule.
                """
            )

            st.markdown("**What gets scraped**")
            st.markdown(
                """
                - Race calendar pages to find eligible `.1` and `.Pro` events.
                - Race result pages to capture actual UCI points paid out.
                - Individual stage-result pages for stage races, so stage points are not collapsed into GC only.
                - Extended startlist pages to estimate pre-race field strength.
                """
            )

            st.markdown("**How stage races are handled**")
            st.markdown(
                """
                - The app still ranks **whole races**, because a team chooses whether to enter the full stage race.
                - For stage races, the payout side now includes **GC points plus the sum of all parsed stage-result points**.
                - That means a seven-stage race is treated as one target with several internal scoring chances, not seven separate targets.
                """
            )

            st.markdown("**How category changes are handled**")
            st.markdown(
                """
                - If a race changes class, the model no longer blends those editions into one uninterrupted history.
                - A `1.1` version and a later `1.Pro` version are treated as different historical targets.
                - For planning, the app keeps the **latest known category** as the live recommendation and shows the full category path for context.
                """
            )

        with method_col:
            st.markdown("**Trust checklist**")
            st.markdown(
                f"""
                - The current run is based on **{source_count}** historical race editions.
                - Any score is built from observable fields in the scraped dataset shown in the `Raw Data` tab.
                - The opportunity score is explainable because every component is exposed below.
                - Stage races in this run: **{stage_race_count}**. Missing stage pages inside parsed stage races: **{missing_stage_pages}**.
                - Races with at least one category change inside this run: **{category_change_races}**.
                - Skipped races in this run: **{error_count}**.
                """
            )

            st.markdown("**Main limitations**")
            st.markdown(
                """
                - Startlist strength is a proxy, not a perfect measure of rider level.
                - Stage races now include GC plus stage-result points, but the model still does not understand stage type, route fit, or team-specific rider roles.
                - Latest-category planning is based on the latest category visible in the selected data window, so a later drop to `.2` is only visible if that category is included in the dataset.
                - The model does not yet include travel cost, route fit, internal team goals, or roster conflicts.
                """
            )

        st.markdown("**Step 1: Build a rider form proxy from the extended startlist**")
        st.latex(
            r"""
            \text{rider\_form}
            =
            5 \cdot \text{wins}
            + 2 \cdot (\text{podiums} - \text{wins})
            + 1 \cdot (\text{top10s} - \text{podiums})
            + 0.1 \cdot \text{starts}
            """
        )
        st.markdown(
            """
            This intentionally weights wins most heavily, then podium depth, then top-10 frequency,
            with a small reward for recent race volume.
            """
        )

        st.markdown("**Step 2: Turn rider form into field-strength measures**")
        st.latex(
            r"""
            \text{top10\_field\_form}
            =
            \sum_{i=1}^{10} \text{rider\_form}_{(i)}
            \qquad
            \text{avg\_top10\_field\_form}
            =
            \frac{\text{top10\_field\_form}}{10}
            \qquad
            \text{total\_field\_form}
            =
            \sum_{j=1}^{N} \text{rider\_form}_j
            """
        )
        st.markdown(
            """
            Lower values mean a historically softer field. In the final score, lower field strength is
            converted into a higher "softness" percentile.
            """
        )

        st.markdown("**Step 3: Convert raw measures into comparable 0-100 percentiles**")
        st.markdown("**Stage-race payout treatment**")
        st.latex(
            r"""
            \text{event\_top10\_points}
            =
            \text{gc\_top10\_points}
            +
            \sum_{s=1}^{S} \text{stage\_top10\_points}_s
            \qquad
            \text{event\_winner\_points}
            =
            \text{gc\_winner\_points}
            +
            \sum_{s=1}^{S} \text{stage\_winner\_points}_s
            """
        )
        st.markdown(
            """
            One-day races have no stage component, so their event-level payout is just the final result table.
            Stage races keep one row in the model, but that row now carries both the GC and stage payout totals.
            """
        )

        st.markdown("**Step 4: Convert raw measures into comparable 0-100 percentiles**")
        st.latex(
            r"""
            \text{top10\_points\_pct} = \text{percentile}(\text{top10\_points})
            \qquad
            \text{winner\_points\_pct} = \text{percentile}(\text{winner\_points})
            """
        )
        st.latex(
            r"""
            \text{field\_softness\_pct} = 100 - \text{percentile}(\text{avg\_top10\_field\_form})
            \qquad
            \text{depth\_softness\_pct} = 100 - \text{percentile}(\text{total\_field\_form})
            """
        )
        st.latex(
            r"""
            \text{finish\_rate\_pct} = \text{percentile}(\text{finish\_rate})
            """
        )

        st.markdown("**Step 5: Combine the components into the arbitrage score**")
        st.latex(
            rf"""
            \text{{arbitrage\_score}}
            =
            \frac{{
            {weights["top10_points"]:.2f}\cdot\text{{top10\_points\_pct}}
            +
            {weights["winner_points"]:.2f}\cdot\text{{winner\_points\_pct}}
            +
            {weights["field_softness"]:.2f}\cdot\text{{field\_softness\_pct}}
            +
            {weights["depth_softness"]:.2f}\cdot\text{{depth\_softness\_pct}}
            +
            {weights["finish_rate"]:.2f}\cdot\text{{finish\_rate\_pct}}
            }}{{
            {sum(weights.values()):.2f}
            }}
            """
        )

        weight_frame = pd.DataFrame(
            {
                "Component": [
                    "Top-10 payout",
                    "Winner upside",
                    "Softness of top riders",
                    "Softness of full field",
                    "Finish-rate reliability",
                ],
                "Current weight": [
                    weights["top10_points"],
                    weights["winner_points"],
                    weights["field_softness"],
                    weights["depth_softness"],
                    weights["finish_rate"],
                ],
            }
        )
        st.dataframe(weight_frame, use_container_width=True, hide_index=True)
        st.caption(
            "Sidebar weights are normalized before scoring, so they act as relative emphasis rather than fixed coefficients."
        )
        st.caption(
            "These startup defaults are the current one-day calibrated weights from the bundled 2021-2025 walk-forward backtest."
        )

        st.markdown("**Interpretation guide**")
        st.markdown(
            """
            - A higher `Arbitrage Score` means the race has looked attractive on a payout-versus-field basis.
            - A high `Avg Top-10 Points` with a low `Avg Top-10 Field Form` is usually the sweet spot.
            - `Points per Field-Form` is a simpler efficiency view: payout divided by the strength proxy of the top of the field.
            """
        )


def render_backtest_tab(dataset: pd.DataFrame, years: list[int], categories: list[str]) -> None:
    st.subheader("Backtest & Calibration")
    st.markdown(
        """
        The calibration module checks whether **past race history** helps identify **future high-efficiency races**.
        It does that with a walk-forward test:
        train on prior years, predict which races should look attractive next season, then compare those predictions
        with what actually happened in the next year's edition.
        """
    )
    st.markdown(
        """
        It still works at the **race level**, not the rider level.
        The question is:
        "Did the model rank the best points opportunities near the top?"
        """
    )
    st.caption(
        "Calibration is now category-aware: a race's `1.1` history and `1.Pro` history are treated as separate target histories."
    )

    with st.form("calibration_form"):
        calibration_dataset_source = st.radio(
            "Calibration data",
            options=["Bundled snapshot", "Current analysis dataset"],
            index=0 if SNAPSHOT_PATH.exists() else 1,
            horizontal=True,
            help=(
                "Use the bundled snapshot for the most stable calibration. "
                "A capped live scrape can be too sparse for walk-forward testing."
            ),
        )
        calibration_race_type = st.radio(
            "Calibration scope",
            options=["One-day", "All", "Stage race"],
            index=0,
            horizontal=True,
            help="One-day is still recommended because stage races now include stage points but do not yet model stage type or roster fit.",
        )
        search_iterations = st.slider(
            "Random weight candidates",
            min_value=100,
            max_value=1500,
            value=600,
            step=100,
            help="More candidates means a broader search, but it takes longer.",
        )
        random_seed = st.number_input("Random seed", min_value=1, max_value=9999, value=7, step=1)
        run_backtest = st.form_submit_button("Run walk-forward backtest")

    if calibration_dataset_source == "Bundled snapshot" and SNAPSHOT_PATH.exists():
        calibration_dataset = load_snapshot(SNAPSHOT_PATH, years=years, categories=categories)
    else:
        calibration_dataset = dataset

    current_signature = calibration_signature(
        calibration_dataset_source=calibration_dataset_source,
        calibration_dataset=calibration_dataset,
        years=years,
        categories=categories,
        calibration_race_type=calibration_race_type,
        search_iterations=search_iterations,
        random_seed=random_seed,
    )
    if run_backtest:
        result = get_calibration_result(
            calibration_dataset, calibration_race_type, search_iterations, random_seed
        )
        st.session_state["calibration_result"] = result
        st.session_state["calibration_signature"] = current_signature

    result = st.session_state.get("calibration_result")
    result_signature = st.session_state.get("calibration_signature")

    if result is None:
        st.info("Run the backtest to compare the default weights against calibrated weights.")
        return

    if result_signature != current_signature:
        st.warning(
            "The calibration setup has changed since the last run. Run the backtest again to refresh the results."
        )
        return

    if not result.get("eligible", False):
        st.warning(result["message"])
        filtered_rows = result.get("filtered_rows", 0)
        st.caption(f"Eligible historical rows after filtering: {filtered_rows}")
        if calibration_dataset_source == "Current analysis dataset":
            st.caption(
                "This usually means the current live scrape does not contain enough repeated race editions across years. "
                "Switching calibration data to `Bundled snapshot` should fix it."
            )
        return

    default_eval = result["default"]
    best_eval = result["best"]

    metric_left, metric_mid, metric_right, metric_far = st.columns(4)
    metric_left.metric("Calibration folds", result["fold_count"])
    metric_mid.metric("Default objective", f"{default_eval['objective']:.3f}")
    metric_right.metric("Calibrated objective", f"{best_eval['objective']:.3f}")
    metric_far.metric("Improvement", f"{result['improvement']:+.3f}")

    st.markdown("**How the backtest is scored**")
    st.markdown(
        """
        - `Spearman`: does the predicted race ranking match the realized race-efficiency ranking?
        - `Top-k precision`: how often did the model's shortlist overlap with the actual best races?
        - `Top-k value capture`: how much of the actual top-race efficiency did the shortlist capture?
        """
    )
    st.latex(
        r"""
        \text{objective}
        =
        0.60 \cdot \frac{\text{Spearman} + 1}{2}
        +
        0.20 \cdot \text{Top-k Precision}
        +
        0.20 \cdot \text{Top-k Value Capture}
        """
    )

    comparison_frame = pd.DataFrame(
        [
            {
                "Set": "Default",
                "Objective": default_eval["objective"],
                "Spearman": default_eval["spearman"],
                "Top-k Precision": default_eval["top_k_precision"],
                "Top-k Value Capture": default_eval["top_k_value_capture"],
                **default_eval["weights"],
            },
            {
                "Set": "Calibrated",
                "Objective": best_eval["objective"],
                "Spearman": best_eval["spearman"],
                "Top-k Precision": best_eval["top_k_precision"],
                "Top-k Value Capture": best_eval["top_k_value_capture"],
                **best_eval["weights"],
            },
        ]
    )
    st.dataframe(
        comparison_frame.round(3),
        use_container_width=True,
        hide_index=True,
    )

    if st.button("Use calibrated weights in this session", key="apply_calibrated_weights"):
        queue_weight_state(best_eval["weights"])
        st.rerun()

    fold_options = [int(year) for year in result["fold_years"]]
    selected_fold = st.selectbox("Inspect test year", options=fold_options, index=len(fold_options) - 1)

    default_fold_table = default_eval["folds"].copy()
    default_fold_table["Weight Set"] = "Default"
    calibrated_fold_table = best_eval["folds"].copy()
    calibrated_fold_table["Weight Set"] = "Calibrated"
    fold_comparison = pd.concat([default_fold_table, calibrated_fold_table], ignore_index=True)
    st.dataframe(
        fold_comparison.round(3),
        use_container_width=True,
        hide_index=True,
    )

    fold_detail = best_eval["fold_details"]
    if not fold_detail.empty:
        year_detail = prepare_backtest_fold_detail(fold_detail, selected_fold)
        st.markdown("**Calibrated ranking versus actual next-year outcome**")
        st.dataframe(
            year_detail.round(
                {
                    "Predicted Score": 3,
                    "Actual Efficiency": 3,
                    "Actual Top-10 Points": 1,
                    "Actual Top-10 Field Form": 1,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("**Top candidate weight sets**")
    leaderboard = result["leaderboard"].copy()
    leaderboard = leaderboard.rename(
        columns={
            "objective": "Objective",
            "spearman": "Spearman",
            "top_k_precision": "Top-k Precision",
            "top_k_value_capture": "Top-k Value Capture",
            "top10_points": "Top-10 Payout",
            "winner_points": "Winner Upside",
            "field_softness": "Top-Rider Softness",
            "depth_softness": "Field Softness",
            "finish_rate": "Finish Reliability",
        }
    )
    st.dataframe(leaderboard.round(3), use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(
        page_title="UCI Points Optimization Model",
        page_icon=":bike:",
        layout="wide",
    )

    st.title("UCI Points Optimization Model")
    st.caption(
        "Score .1 and .Pro races by balancing historical points payout against historical "
        "startlist strength, then surface the best relegation-battle opportunities."
    )
    st.info(
        "This version uses FirstCycling results plus the extended startlist page. "
        "Stage races now roll up GC points and individual stage-result points into one event-level opportunity score, "
        "but route type and team-specific rider fit are still outside the model. "
        "Recommendations can also be checked against a live planning-season calendar."
    )
    initialize_weight_state()
    apply_pending_weight_state()
    initialize_dataset_state()

    with st.sidebar.form("controls"):
        st.subheader("Model Controls")
        years = st.multiselect(
            "Historical years",
            options=list(range(2020, 2027)),
            default=DEFAULT_YEARS,
            help="Use past editions to estimate which races are attractive next season.",
        )
        categories = st.multiselect(
            "Race categories",
            options=list(TARGET_CATEGORIES),
            default=list(TARGET_CATEGORIES),
        )
        planning_year = int(
            st.number_input(
                "Planning season",
                min_value=2020,
                max_value=2035,
                value=DEFAULT_PLANNING_YEAR,
                step=1,
                help="Cross-check recommendations against this season's live calendar.",
            )
        )
        data_source = st.radio(
            "Dataset source",
            options=["Bundled snapshot", "Live scrape"],
            index=0 if SNAPSHOT_PATH.exists() else 1,
            help="Use the CSV snapshot when available for fast startup, or scrape live from FirstCycling.",
        )
        max_races = st.slider(
            "Max race editions to scrape live",
            min_value=20,
            max_value=250,
            value=80,
            step=10,
            help="Lower values keep the app responsive. Use the snapshot builder for full-season exports.",
        )

        st.markdown("**Scoring weights**")
        st.slider(
            "Top-10 payout",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["top10_points"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["top10_points"],
        )
        st.slider(
            "Winner upside",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["winner_points"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["winner_points"],
        )
        st.slider(
            "Softness of top riders",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["field_softness"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["field_softness"],
        )
        st.slider(
            "Softness of full field",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["depth_softness"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["depth_softness"],
        )
        st.slider(
            "Finish-rate reliability",
            0.0,
            1.0,
            float(st.session_state[WEIGHT_STATE_KEYS["finish_rate"]]),
            0.05,
            key=WEIGHT_STATE_KEYS["finish_rate"],
        )

        submitted = st.form_submit_button("Analyze races")

    if not years:
        st.warning("Choose at least one year to build the model.")
        return
    if not categories:
        st.warning("Choose at least one category to analyze.")
        return

    weights = current_weight_state()

    if submitted or "dataset" not in st.session_state:
        with st.spinner("Loading race history and scoring opportunities..."):
            if data_source == "Bundled snapshot" and SNAPSHOT_PATH.exists():
                dataset = load_snapshot(SNAPSHOT_PATH, years=years, categories=categories)
            else:
                dataset = get_live_dataset(tuple(years), tuple(categories), max_races)
            st.session_state["dataset"] = ensure_dataset_schema(dataset)
            st.session_state["weights"] = weights

    dataset = ensure_dataset_schema(st.session_state.get("dataset", pd.DataFrame()))
    st.session_state["dataset"] = dataset
    if dataset.empty:
        st.warning(
            "No race data was loaded. Try live scraping, widen the category/year filters, or generate a snapshot first."
        )
        return

    scored_editions = score_race_editions(dataset, weights)
    target_summary = summarize_historical_targets(scored_editions)
    planning_calendar = get_planning_calendar(planning_year, tuple(PLANNING_CALENDAR_CATEGORIES))
    target_summary = overlay_planning_calendar(target_summary, planning_calendar, planning_year)
    target_summary = target_summary.sort_values(
        ["on_planning_calendar", "avg_arbitrage_score", "avg_top10_points"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    render_model_explainer(weights, dataset)

    left, middle, right, far_right, farthest = st.columns(5)
    left.metric("Race editions analyzed", f"{len(scored_editions):,}")
    middle.metric("Category-aware targets", f"{len(target_summary):,}")
    right.metric(
        f"On {planning_year} .1/.Pro calendar",
        f"{int(target_summary['on_planning_calendar'].sum()):,}",
    )
    far_right.metric("Average top-10 payout", f"{scored_editions['top10_points'].mean():.1f}")
    farthest.metric("Average startlist size", f"{scored_editions['startlist_size'].mean():.0f}")

    top_targets = target_summary.copy()
    top_targets["avg_arbitrage_score"] = top_targets["avg_arbitrage_score"].round(1)
    top_targets["avg_top10_points"] = top_targets["avg_top10_points"].round(1)
    top_targets["avg_stage_top10_points"] = top_targets["avg_stage_top10_points"].round(1)
    top_targets["avg_stage_count"] = top_targets["avg_stage_count"].round(1)
    top_targets["avg_top10_field_form"] = top_targets["avg_top10_field_form"].round(1)
    top_targets["avg_points_efficiency"] = top_targets["avg_points_efficiency"].round(2)
    top_targets["planning_scope_match"] = top_targets["planning_scope_match"].map(
        {True: "Same category", False: "Category changed"}
    )
    top_targets.loc[~top_targets["on_planning_calendar"], "planning_scope_match"] = "No in-scope match"
    top_targets = top_targets.rename(
        columns={
            "race_name": "Race",
            "race_country": "Country",
            "category": "Category",
            "race_type": "Race Type",
            "category_history": "Category History",
            "years_analyzed": "Same-Category Editions",
            "years": "Years",
            "avg_arbitrage_score": "Arbitrage Score",
            "avg_top10_points": "Avg Top-10 Points",
            "avg_stage_top10_points": "Avg Stage Top-10 Points",
            "avg_stage_count": "Avg Stage Days",
            "avg_top10_field_form": "Avg Top-10 Field Form",
            "avg_points_efficiency": "Points per Field-Form",
            "planning_category": f"{planning_year} Category",
            "planning_date_label": f"{planning_year} Date",
            "planning_calendar_status": f"{planning_year} Calendar Status",
            "planning_scope_match": f"{planning_year} Match",
        }
    )

    tab_targets, tab_diagnostics, tab_backtest, tab_raw = st.tabs(
        ["Recommended Targets", "Edition Diagnostics", "Backtest & Calibration", "Raw Data"]
    )

    with tab_targets:
        st.subheader("Best Races to Target Next Season")
        show_active_only = st.checkbox(
            f"Only show races on the {planning_year} .1/.Pro calendar",
            value=True,
            help="Hide recommendations that are not on this season's in-scope calendar.",
        )
        display_targets = top_targets.copy()
        if show_active_only:
            display_targets = display_targets[
                display_targets[f"{planning_year} Calendar Status"].str.contains(
                    rf"On {planning_year} \.1/\.Pro calendar", regex=True
                )
            ].copy()
        display_targets = display_targets.head(15)

        if display_targets.empty:
            st.info(
                f"No recommended targets matched the {planning_year} .1/.Pro calendar under the current filters. "
                "Turn off the checkbox to inspect out-of-scope or missing races."
            )

        st.dataframe(
            display_targets[
                [
                    "Race",
                    "Country",
                    "Category",
                    f"{planning_year} Category",
                    f"{planning_year} Date",
                    f"{planning_year} Match",
                    f"{planning_year} Calendar Status",
                    "Category History",
                    "Race Type",
                    "Same-Category Editions",
                    "Years",
                    "Arbitrage Score",
                    "Avg Top-10 Points",
                    "Avg Stage Top-10 Points",
                    "Avg Stage Days",
                    "Avg Top-10 Field Form",
                    "Points per Field-Form",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(
            "The model lifts races that consistently offer strong top-10 points while historically "
            "drawing softer startlists. Stage races are still ranked as one target each, but their "
            "points totals now include both GC and stage-result payouts. If a race changed category, "
            "the recommendation uses the latest known category and shows the full category history alongside it. "
            f"The extra {planning_year} columns tell you whether that race is actually on this season's calendar."
        )

    with tab_diagnostics:
        st.subheader("Edition-Level Opportunity Map")
        chart_frame = scored_editions.copy()
        chart_frame["label"] = chart_frame["race_name"] + " (" + chart_frame["year"].astype(str) + ")"
        figure = px.scatter(
            chart_frame,
            x="avg_top10_field_form",
            y="top10_points",
            color="category",
            size="arbitrage_score",
            hover_name="label",
            hover_data={
                "startlist_size": True,
                "finish_rate": ":.2f",
                "winner_points": True,
                "total_points": True,
                "gc_top10_points": True,
                "stage_top10_points": True,
                "stage_count": True,
                "stage_points_share": ":.2f",
                "arbitrage_score": ":.1f",
                "avg_top10_field_form": ":.1f",
                "top10_points": ":.1f",
            },
            labels={
                "avg_top10_field_form": "Top-10 field-form strength",
                "top10_points": "Top-10 points payout",
            },
        )
        figure.update_layout(height=520, legend_title_text="Category")
        st.plotly_chart(figure, use_container_width=True)

        edition_table = scored_editions[
            [
                "race_name",
                "year",
                "category",
                "race_type",
                "race_country",
                "arbitrage_score",
                "top10_points",
                "winner_points",
                "gc_top10_points",
                "stage_top10_points",
                "stage_count",
                "stage_points_share",
                "avg_top10_field_form",
                "total_field_form",
                "finish_rate",
                "startlist_size",
            ]
        ].copy()
        edition_table = edition_table.rename(
            columns={
                "race_name": "Race",
                "year": "Year",
                "category": "Category",
                "race_type": "Race Type",
                "race_country": "Country",
                "arbitrage_score": "Score",
                "top10_points": "Top-10 Points",
                "winner_points": "Winner Points",
                "gc_top10_points": "GC Top-10 Points",
                "stage_top10_points": "Stage Top-10 Points",
                "stage_count": "Stage Days",
                "stage_points_share": "Stage Share",
                "avg_top10_field_form": "Top-10 Field Form",
                "total_field_form": "Total Field Form",
                "finish_rate": "Finish Rate",
                "startlist_size": "Startlist Size",
            }
        )
        st.dataframe(
            edition_table.round(
                {
                    "Score": 1,
                    "Top-10 Points": 1,
                    "Winner Points": 1,
                    "GC Top-10 Points": 1,
                    "Stage Top-10 Points": 1,
                    "Stage Days": 0,
                    "Stage Share": 2,
                    "Top-10 Field Form": 1,
                    "Total Field Form": 1,
                    "Finish Rate": 2,
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with tab_backtest:
        render_backtest_tab(dataset, years, categories)

    with tab_raw:
        st.subheader("Scraped Dataset")
        st.dataframe(dataset, use_container_width=True, hide_index=True)
        st.download_button(
            "Download current dataset as CSV",
            data=dataset.to_csv(index=False).encode("utf-8"),
            file_name="uci_points_race_editions.csv",
            mime="text/csv",
        )
        error_count = dataset.attrs.get("error_count", 0)
        if error_count:
            st.caption(f"{error_count} races were skipped during scraping because one or more pages were missing.")


if __name__ == "__main__":
    main()
