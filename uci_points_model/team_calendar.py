from __future__ import annotations

from datetime import date, datetime, timezone
import re
import unicodedata
from pathlib import Path

import pandas as pd

from .team_calendar_client import (
    ProCyclingStatsTeamCalendarClient,
    TeamProgramEntry,
    load_team_program_rows,
)

PLANNING_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "data" / "planning_calendar_2026.csv"
TEAM_CALENDAR_ALIAS_PATH = Path(__file__).resolve().parent.parent / "config" / "team_calendar_race_aliases.csv"
PROTEAM_RISK_PATH = Path(__file__).resolve().parent.parent / "data" / "proteam_risk_current_snapshot.csv"

TEAM_CALENDAR_COLUMNS = [
    "team_slug",
    "team_name",
    "planning_year",
    "source",
    "scraped_at_utc",
    "race_id",
    "race_name",
    "category",
    "date_label",
    "month",
    "start_date",
    "end_date",
    "status",
    "team_calendar_status",
    "source_url",
    "pcs_race_slug",
    "observed_race_name",
    "matched_via",
    "notes",
    "overlap_group",
]

CHANGELOG_COLUMNS = [
    "team_slug",
    "planning_year",
    "detected_at_utc",
    "change_type",
    "race_id",
    "race_name",
    "old_value",
    "new_value",
    "source",
    "notes",
]

_COMMON_STOP_WORDS = {
    "a",
    "al",
    "and",
    "at",
    "by",
    "c",
    "calida",
    "centre",
    "clasica",
    "classic",
    "classica",
    "club",
    "de",
    "del",
    "des",
    "du",
    "el",
    "et",
    "for",
    "from",
    "gp",
    "gran",
    "grand",
    "groupama",
    "interior",
    "la",
    "le",
    "los",
    "me",
    "of",
    "p",
    "premi",
    "premio",
    "prix",
    "pro",
    "pv",
    "saxo",
    "the",
    "to",
    "tour",
    "val",
    "we",
}


def normalize_race_name(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
    normalized = re.sub(r"\b(ME|WE|WWT|MJ|WU)\b", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def build_name_variants(value: str | None) -> list[str]:
    raw = "" if value is None else str(value).strip()
    variants: list[str] = []

    def append(candidate: str) -> None:
        normalized = normalize_race_name(candidate)
        if normalized and normalized not in variants:
            variants.append(normalized)

    append(raw)
    append(re.sub(r"\s+\b(ME|WE|WWT|MJ|WU)\b$", "", raw, flags=re.IGNORECASE))
    if " - " in raw:
        append(raw.split(" - ", 1)[0])
    if " / " in raw:
        append(raw.split(" / ", 1)[0])
    append(re.sub(r"[\"“”].*?[\"“”]", "", raw))
    return variants


def race_name_tokens(value: str | None) -> set[str]:
    normalized = normalize_race_name(value)
    return {
        token
        for token in normalized.split()
        if token and token not in _COMMON_STOP_WORDS and not token.isdigit()
    }


def parse_date_label(date_label: str | None, planning_year: int) -> tuple[str, str]:
    value = "" if date_label is None else str(date_label).strip()
    if not value:
        return "", ""

    def parse_fragment(fragment: str, year: int) -> pd.Timestamp:
        parts = fragment.split(".")
        if len(parts) != 2:
            raise ValueError(f"Unsupported planning date fragment: {fragment}")
        day, month = (int(part) for part in parts)
        return pd.Timestamp(year=year, month=month, day=day)

    if "-" not in value:
        timestamp = parse_fragment(value, planning_year)
        iso_value = timestamp.date().isoformat()
        return iso_value, iso_value

    start_fragment, end_fragment = (fragment.strip() for fragment in value.split("-", 1))
    start_ts = parse_fragment(start_fragment, planning_year)
    end_ts = parse_fragment(end_fragment, planning_year)
    if end_ts < start_ts:
        end_ts = parse_fragment(end_fragment, planning_year + 1)
    return start_ts.date().isoformat(), end_ts.date().isoformat()


def load_planning_calendar(
    planning_year: int,
    calendar_path: str | Path | None = None,
) -> pd.DataFrame:
    path = Path(calendar_path) if calendar_path else PLANNING_CALENDAR_PATH
    planning_df = pd.read_csv(path).copy()
    if "year" in planning_df.columns:
        planning_df = planning_df.loc[planning_df["year"].astype("Int64") == int(planning_year)].copy()
    planning_df["planning_year"] = int(planning_year)
    planning_df["race_id"] = planning_df["race_id"].astype("Int64")
    planning_df["normalized_race_name"] = planning_df["race_name"].map(normalize_race_name)
    parsed_dates = planning_df["date_label"].map(lambda value: parse_date_label(value, planning_year))
    planning_df["start_date"] = parsed_dates.map(lambda value: value[0])
    planning_df["end_date"] = parsed_dates.map(lambda value: value[1])
    return planning_df.reset_index(drop=True)


def load_team_calendar_aliases(alias_path: str | Path | None = None) -> pd.DataFrame:
    path = Path(alias_path) if alias_path else TEAM_CALENDAR_ALIAS_PATH
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "team_slug",
                "planning_year",
                "source_race_name",
                "canonical_race_name",
                "race_id",
                "normalized_source_race_name",
            ]
        )
    alias_df = pd.read_csv(path).copy()
    if "team_slug" not in alias_df.columns:
        alias_df["team_slug"] = ""
    if "planning_year" not in alias_df.columns:
        alias_df["planning_year"] = pd.NA
    if "canonical_race_name" not in alias_df.columns:
        alias_df["canonical_race_name"] = ""
    alias_df["normalized_source_race_name"] = alias_df["source_race_name"].map(normalize_race_name)
    alias_df["planning_year"] = pd.to_numeric(alias_df["planning_year"], errors="coerce").astype("Int64")
    alias_df["race_id"] = pd.to_numeric(alias_df["race_id"], errors="coerce").astype("Int64")
    return alias_df


def team_name_from_snapshot(team_slug: str, snapshot_path: str | Path | None = None) -> str:
    path = Path(snapshot_path) if snapshot_path else PROTEAM_RISK_PATH
    if not path.exists():
        return team_slug
    snapshot_df = pd.read_csv(path, usecols=["team_slug", "team_name"], low_memory=False)
    matches = snapshot_df.loc[snapshot_df["team_slug"] == team_slug, "team_name"]
    if matches.empty:
        return team_slug
    return str(matches.iloc[0])


def build_live_team_calendar(
    team_slug: str,
    planning_year: int,
    pcs_team_slug: str | None = None,
    client: ProCyclingStatsTeamCalendarClient | None = None,
    program_path: str | None = None,
    planning_calendar_path: str | Path | None = None,
    alias_path: str | Path | None = None,
    as_of_date: str | date | None = None,
) -> pd.DataFrame:
    pcs_client = client or ProCyclingStatsTeamCalendarClient()
    pcs_lookup_slug = pcs_team_slug or team_slug
    if program_path:
        source_rows_df = load_team_program_rows(program_path)
        team_name = team_name_from_snapshot(pcs_lookup_slug)
        source_label = "team_program_file"
    else:
        team_name, entries = pcs_client.get_team_program_entries(pcs_lookup_slug)
        source_rows_df = program_entries_to_frame(entries)
        source_label = "team_program_live"

    return build_team_calendar_from_source_rows(
        source_rows_df=source_rows_df,
        team_slug=team_slug,
        planning_year=planning_year,
        team_name=team_name,
        source_label=source_label,
        planning_calendar_path=planning_calendar_path,
        alias_path=alias_path,
        as_of_date=as_of_date,
    )


def program_entries_to_frame(entries: list[TeamProgramEntry]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_race_name": entry.source_race_name,
                "observed_date": entry.date_label,
                "date_label": entry.date_label,
                "category": entry.category,
                "source_url": entry.source_url,
                "pcs_race_slug": entry.pcs_race_slug,
            }
            for entry in entries
        ]
    )


def _score_candidate(
    source_name: str,
    observed_date: str,
    candidate_row: pd.Series,
) -> tuple[int, int, int]:
    source_tokens = race_name_tokens(source_name)
    candidate_tokens = race_name_tokens(candidate_row.get("race_name"))
    overlap = len(source_tokens & candidate_tokens)
    if overlap == 0:
        return (0, 0, 0)

    date_bonus = 0
    if observed_date:
        observed_ts = pd.to_datetime(observed_date, errors="coerce")
        candidate_start = pd.to_datetime(candidate_row.get("start_date"), errors="coerce")
        candidate_end = pd.to_datetime(candidate_row.get("end_date"), errors="coerce")
        if pd.notna(observed_ts) and pd.notna(candidate_start) and pd.notna(candidate_end):
            if candidate_start <= observed_ts <= candidate_end:
                date_bonus = 3
            elif observed_ts == candidate_start or observed_ts == candidate_end:
                date_bonus = 2

    exact_prefix_bonus = 1 if normalize_race_name(source_name).startswith(
        normalize_race_name(candidate_row.get("race_name"))
    ) else 0
    return (overlap + date_bonus + exact_prefix_bonus, overlap, date_bonus)


def match_observed_races(
    observed_df: pd.DataFrame,
    planning_df: pd.DataFrame,
    alias_df: pd.DataFrame,
    team_slug: str,
    planning_year: int,
    source_name_column: str = "source_race_name",
    observed_date_column: str = "observed_date",
) -> pd.DataFrame:
    if observed_df.empty:
        return observed_df.copy()

    scoped_alias_df = alias_df.loc[
        ((alias_df["team_slug"].fillna("") == "") | (alias_df["team_slug"] == team_slug))
        & (alias_df["planning_year"].isna() | (alias_df["planning_year"].astype("Int64") == int(planning_year)))
    ].copy()
    planning_lookup = planning_df.set_index("race_id")[["race_name"]]

    matched_rows: list[dict] = []
    for row in observed_df.to_dict(orient="records"):
        source_name = str(row.get(source_name_column, "") or "")
        observed_date = str(row.get(observed_date_column, "") or "")
        normalized_name = normalize_race_name(source_name)
        race_id = pd.NA
        canonical_race_name = ""
        matched_via = ""

        alias_match = scoped_alias_df.loc[scoped_alias_df["normalized_source_race_name"] == normalized_name]
        if not alias_match.empty:
            race_id = alias_match["race_id"].iloc[0]
            canonical_race_name = str(alias_match["canonical_race_name"].iloc[0] or "")
            matched_via = "alias"
        else:
            exact_match = pd.DataFrame()
            for variant in build_name_variants(source_name):
                exact_match = planning_df.loc[planning_df["normalized_race_name"] == variant]
                if len(exact_match) == 1:
                    break
            if len(exact_match) == 1:
                race_id = exact_match["race_id"].iloc[0]
                canonical_race_name = str(exact_match["race_name"].iloc[0])
                matched_via = "normalized_name"
            else:
                scored_candidates: list[tuple[tuple[int, int, int], pd.Series]] = []
                for _, candidate_row in planning_df.iterrows():
                    score = _score_candidate(source_name, observed_date, candidate_row)
                    if score[0] > 0:
                        scored_candidates.append((score, candidate_row))
                scored_candidates.sort(key=lambda item: item[0], reverse=True)
                if scored_candidates:
                    best_score, best_candidate = scored_candidates[0]
                    second_score = scored_candidates[1][0] if len(scored_candidates) > 1 else (-1, -1, -1)
                    if best_score[0] >= 3 and best_score > second_score:
                        race_id = best_candidate["race_id"]
                        canonical_race_name = str(best_candidate["race_name"])
                        matched_via = "token_overlap"

        row["matched_race_id"] = race_id
        row["canonical_race_name"] = canonical_race_name or (
            planning_lookup.loc[race_id, "race_name"] if pd.notna(race_id) and race_id in planning_lookup.index else ""
        )
        row["matched_via"] = matched_via
        row["match_status"] = "matched" if pd.notna(race_id) else "unmatched"
        matched_rows.append(row)

    return pd.DataFrame(matched_rows)


def add_overlap_groups(calendar_df: pd.DataFrame) -> pd.DataFrame:
    if calendar_df.empty:
        result_df = calendar_df.copy()
        result_df["overlap_group"] = pd.Series(dtype="string")
        return result_df

    sorted_df = calendar_df.sort_values(["start_date", "end_date", "race_id"], na_position="last").reset_index(drop=True)
    groups: list[int] = []
    current_group = 0
    current_group_end = pd.NaT

    for row in sorted_df.itertuples(index=False):
        row_start = pd.to_datetime(getattr(row, "start_date"), errors="coerce")
        row_end = pd.to_datetime(getattr(row, "end_date"), errors="coerce")
        if pd.isna(row_start) or pd.isna(row_end) or pd.isna(current_group_end) or row_start > current_group_end:
            current_group += 1
            current_group_end = row_end
        else:
            current_group_end = max(current_group_end, row_end)
        groups.append(current_group)

    sorted_df["overlap_group_raw"] = groups
    group_sizes = sorted_df.groupby("overlap_group_raw")["race_id"].transform("size")
    sorted_df["overlap_group"] = group_sizes.map(lambda size: "" if size <= 1 else f"overlap_{size}")
    return sorted_df.drop(columns=["overlap_group_raw"])


def build_team_calendar_from_source_rows(
    source_rows_df: pd.DataFrame,
    team_slug: str,
    planning_year: int,
    team_name: str | None = None,
    source_label: str = "team_program_live",
    planning_calendar_path: str | Path | None = None,
    alias_path: str | Path | None = None,
    scraped_at_utc: str | None = None,
    as_of_date: str | date | None = None,
) -> pd.DataFrame:
    planning_df = load_planning_calendar(planning_year, planning_calendar_path)
    alias_df = load_team_calendar_aliases(alias_path)
    effective_team_name = team_name or team_name_from_snapshot(team_slug)
    source_df = source_rows_df.copy()
    if source_df.empty:
        return pd.DataFrame(columns=TEAM_CALENDAR_COLUMNS)

    if "source_race_name" not in source_df.columns and "race_name" in source_df.columns:
        source_df = source_df.rename(columns={"race_name": "source_race_name"})
    if "source_url" not in source_df.columns:
        source_df["source_url"] = ""
    if "pcs_race_slug" not in source_df.columns:
        source_df["pcs_race_slug"] = ""
    if "observed_date" not in source_df.columns:
        source_df["observed_date"] = source_df.get("date_label", "")
    matched_df = match_observed_races(source_df, planning_df, alias_df, team_slug, planning_year)

    matched_only_df = matched_df.loc[matched_df["match_status"] == "matched"].copy()
    if matched_only_df.empty:
        return pd.DataFrame(columns=TEAM_CALENDAR_COLUMNS)

    planning_join_df = planning_df[
        ["race_id", "race_name", "category", "date_label", "month", "start_date", "end_date", "planning_year"]
    ].rename(
        columns={
            "race_name": "planning_race_name",
            "category": "planning_category",
            "date_label": "planning_date_label",
            "month": "planning_month",
            "start_date": "planning_start_date",
            "end_date": "planning_end_date",
        }
    )
    base_df = matched_only_df.merge(
        planning_join_df,
        left_on="matched_race_id",
        right_on="race_id",
        how="left",
    )
    base_df["team_slug"] = team_slug
    base_df["team_name"] = effective_team_name
    base_df["source"] = source_label
    base_df["scraped_at_utc"] = scraped_at_utc or utc_now_iso()

    canonical_race_name = (
        base_df["canonical_race_name"] if "canonical_race_name" in base_df.columns else pd.Series(pd.NA, index=base_df.index)
    )
    source_category = base_df["category"] if "category" in base_df.columns else pd.Series(pd.NA, index=base_df.index)
    source_date_label = base_df["date_label"] if "date_label" in base_df.columns else pd.Series(pd.NA, index=base_df.index)
    base_df["race_name"] = base_df["planning_race_name"].astype("object")
    race_name_missing = base_df["race_name"].isna() | (base_df["race_name"].astype(str).str.strip() == "")
    base_df.loc[race_name_missing, "race_name"] = canonical_race_name.loc[race_name_missing]

    base_df["category"] = base_df["planning_category"].astype("object")
    category_missing = base_df["category"].isna() | (base_df["category"].astype(str).str.strip() == "")
    base_df.loc[category_missing, "category"] = source_category.loc[category_missing]

    base_df["date_label"] = base_df["planning_date_label"].astype("object")
    date_label_missing = base_df["date_label"].isna() | (base_df["date_label"].astype(str).str.strip() == "")
    base_df.loc[date_label_missing, "date_label"] = source_date_label.loc[date_label_missing]
    base_df["month"] = base_df["planning_month"]
    base_df["start_date"] = base_df["planning_start_date"]
    base_df["end_date"] = base_df["planning_end_date"]
    base_df["status"] = base_df["end_date"].map(
        lambda value: derive_calendar_status(value, as_of_date=as_of_date)
    )
    base_df["team_calendar_status"] = "active"
    base_df["observed_race_name"] = base_df["source_race_name"]
    base_df["notes"] = base_df["matched_via"].map(lambda value: f"matched_via={value}" if value else "")
    base_df["race_id"] = base_df["race_id"].astype("Int64")
    base_df["pcs_race_slug"] = base_df["pcs_race_slug"].fillna("")
    base_df = base_df[
        [
            "team_slug",
            "team_name",
            "planning_year",
            "source",
            "scraped_at_utc",
            "race_id",
            "race_name",
            "category",
            "date_label",
            "month",
            "start_date",
            "end_date",
            "status",
            "team_calendar_status",
            "source_url",
            "pcs_race_slug",
            "observed_race_name",
            "matched_via",
            "notes",
        ]
    ].drop_duplicates(subset=["race_id"])

    enriched_df = add_overlap_groups(base_df).reset_index(drop=True)
    return enriched_df[TEAM_CALENDAR_COLUMNS]


def derive_calendar_status(end_date: str | None, as_of_date: str | date | None = None) -> str:
    comparison_date = _resolve_as_of_date(as_of_date)
    end_ts = pd.to_datetime(end_date, errors="coerce")
    if pd.notna(end_ts) and end_ts.date() < comparison_date:
        return "completed"
    return "scheduled"


def build_schedule_changelog(
    previous_df: pd.DataFrame,
    latest_df: pd.DataFrame,
    team_slug: str,
    planning_year: int,
    detected_at_utc: str | None = None,
    source: str = "team_calendar_refresh",
) -> pd.DataFrame:
    detected_at = detected_at_utc or utc_now_iso()
    tracked_columns = ["date_label", "category", "status", "team_calendar_status"]
    previous_indexed = previous_df.set_index("race_id", drop=False) if not previous_df.empty else pd.DataFrame()
    latest_indexed = latest_df.set_index("race_id", drop=False) if not latest_df.empty else pd.DataFrame()
    previous_ids = set(previous_indexed.index.tolist()) if not previous_df.empty else set()
    latest_ids = set(latest_indexed.index.tolist()) if not latest_df.empty else set()

    changes: list[dict] = []

    for race_id in sorted(latest_ids - previous_ids):
        row = latest_indexed.loc[race_id]
        changes.append(
            {
                "team_slug": team_slug,
                "planning_year": planning_year,
                "detected_at_utc": detected_at,
                "change_type": "race_added",
                "race_id": int(race_id),
                "race_name": row["race_name"],
                "old_value": "",
                "new_value": row["status"],
                "source": source,
                "notes": row.get("notes", ""),
            }
        )

    for race_id in sorted(previous_ids - latest_ids):
        row = previous_indexed.loc[race_id]
        changes.append(
            {
                "team_slug": team_slug,
                "planning_year": planning_year,
                "detected_at_utc": detected_at,
                "change_type": "race_removed",
                "race_id": int(race_id),
                "race_name": row["race_name"],
                "old_value": row["status"],
                "new_value": "",
                "source": source,
                "notes": row.get("notes", ""),
            }
        )

    for race_id in sorted(previous_ids & latest_ids):
        previous_row = previous_indexed.loc[race_id]
        latest_row = latest_indexed.loc[race_id]
        for column in tracked_columns:
            old_value = "" if pd.isna(previous_row[column]) else str(previous_row[column])
            new_value = "" if pd.isna(latest_row[column]) else str(latest_row[column])
            if old_value == new_value:
                continue
            change_type = {
                "date_label": "date_changed",
                "category": "category_changed",
                "status": "status_changed",
                "team_calendar_status": "calendar_status_changed",
            }[column]
            changes.append(
                {
                    "team_slug": team_slug,
                    "planning_year": planning_year,
                    "detected_at_utc": detected_at,
                    "change_type": change_type,
                    "race_id": int(race_id),
                    "race_name": latest_row["race_name"],
                    "old_value": old_value,
                    "new_value": new_value,
                    "source": source,
                    "notes": latest_row.get("notes", ""),
                }
            )

    return pd.DataFrame(changes, columns=CHANGELOG_COLUMNS)


def _resolve_as_of_date(as_of_date: str | date | None) -> date:
    if isinstance(as_of_date, date):
        return as_of_date
    if isinstance(as_of_date, str) and as_of_date.strip():
        return pd.Timestamp(as_of_date).date()
    return datetime.now(timezone.utc).date()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
