from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://firstcycling.com/"
TARGET_CATEGORIES = ("1.Pro", "2.Pro", "1.1", "2.1")


@dataclass(frozen=True, slots=True)
class RaceCalendarEntry:
    race_id: int
    race_name: str
    category: str
    date_label: str
    month: int
    year: int


class FirstCyclingClient:
    """Small FirstCycling scraper tailored to the UCI points model."""

    def __init__(self, timeout: int = 45) -> None:
        self.timeout = timeout
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "darwin", "desktop": True}
        )

    def fetch_html(self, path: str, params: dict[str, str | int] | None = None) -> str:
        url = urljoin(BASE_URL, path)
        response = self.scraper.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def get_calendar_entries(
        self,
        year: int,
        categories: Iterable[str] | None = None,
        months: Iterable[int] | None = None,
    ) -> list[RaceCalendarEntry]:
        selected_categories = set(categories or TARGET_CATEGORIES)
        selected_months = list(months or range(1, 13))
        entries: dict[int, RaceCalendarEntry] = {}

        for month in selected_months:
            html = self.fetch_html("race.php", params={"t": 2, "y": year, "m": f"{month:02d}"})
            soup = BeautifulSoup(html, "html.parser")
            for row in soup.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 3:
                    continue

                link = row.find("a", href=True)
                if not link:
                    continue

                race_id = _extract_race_id(link.get("href", ""))
                if race_id is None:
                    continue

                category = cols[2].get_text(" ", strip=True)
                if category not in selected_categories:
                    continue

                entries[race_id] = RaceCalendarEntry(
                    race_id=race_id,
                    race_name=link.get_text(" ", strip=True),
                    category=category,
                    date_label=cols[1].get_text(" ", strip=True),
                    month=month,
                    year=year,
                )

        return sorted(entries.values(), key=lambda item: (item.year, item.month, item.race_name))

    def build_race_edition_record(self, entry: RaceCalendarEntry) -> dict[str, object]:
        results_html = self.fetch_html("race.php", params={"r": entry.race_id, "y": entry.year})
        startlist_html = self.fetch_html(
            "race.php", params={"r": entry.race_id, "y": entry.year, "k": 9}
        )

        results_soup = BeautifulSoup(results_html, "html.parser")
        startlist_soup = BeautifulSoup(startlist_html, "html.parser")
        results_table = _find_table_with_headers(results_soup, {"Pos", "Rider", "Team", "UCI"})
        startlist_table = _find_table_with_headers(
            startlist_soup, {"BiB", "Rider", "Starts", "Wins", "Podium", "Top 10"}
        )

        if results_table is None:
            raise ValueError(f"Could not find a results table for race {entry.race_id} ({entry.year}).")
        if startlist_table is None:
            raise ValueError(
                f"Could not find an extended startlist table for race {entry.race_id} ({entry.year})."
            )

        results_df = _html_table_to_dataframe(results_table)
        startlist_df = _html_table_to_dataframe(startlist_table)
        gc_results_metrics = _summarize_results(results_df)
        startlist_metrics = _summarize_startlist(startlist_df)
        header = _extract_header_metadata(results_soup)
        race_type = "One-day" if entry.category.startswith("1") else "Stage race"
        stage_metrics = (
            self._summarize_stage_results(entry, results_soup)
            if race_type == "Stage race"
            else _empty_stage_metrics()
        )
        results_metrics = _combine_event_results(gc_results_metrics, stage_metrics)

        return {
            "race_id": entry.race_id,
            "race_name": entry.race_name,
            "year": entry.year,
            "month": entry.month,
            "date_label": entry.date_label,
            "category": entry.category,
            "race_type": race_type,
            "race_country": header["country"],
            "race_subtitle": header["subtitle"],
            **results_metrics,
            **startlist_metrics,
        }

    def _summarize_stage_results(
        self, entry: RaceCalendarEntry, results_soup: BeautifulSoup
    ) -> dict[str, float | int]:
        stage_identifiers = _extract_stage_identifiers(results_soup)
        aggregate = _empty_stage_metrics()
        aggregate["stage_count"] = len(stage_identifiers)

        for stage_identifier in stage_identifiers:
            try:
                stage_html = self.fetch_html(
                    "race.php",
                    params={"r": entry.race_id, "y": entry.year, "e": stage_identifier},
                )
                stage_soup = BeautifulSoup(stage_html, "html.parser")
                stage_table = _find_table_with_headers(
                    stage_soup, {"Pos", "Rider", "Team", "UCI"}
                )
                if stage_table is None:
                    aggregate["stage_pages_missing"] += 1
                    continue

                stage_df = _html_table_to_dataframe(stage_table)
                stage_results = _summarize_results(stage_df)
            except Exception:  # noqa: BLE001
                aggregate["stage_pages_missing"] += 1
                continue

            aggregate["stage_pages_parsed"] += 1
            aggregate["stage_scoring_places"] += stage_results["scoring_places"]
            aggregate["stage_winner_points"] += stage_results["winner_points"]
            aggregate["stage_top10_points"] += stage_results["top10_points"]
            aggregate["stage_total_points"] += stage_results["total_points"]

        return aggregate


def _extract_race_id(href: str) -> int | None:
    if not href.startswith("race.php"):
        return None
    params = parse_qs(urlparse(href).query)
    race_id = params.get("r", [None])[0]
    return int(race_id) if race_id and race_id.isdigit() else None


def _find_table_with_headers(
    soup: BeautifulSoup, required_headers: set[str]
) -> BeautifulSoup | None:
    for table in soup.find_all("table"):
        headers = {th.get_text(" ", strip=True) for th in table.find_all("th")}
        if required_headers.issubset(headers):
            return table
    return None


def _html_table_to_dataframe(table: BeautifulSoup) -> pd.DataFrame:
    frame = pd.read_html(StringIO(str(table)), decimal=",")[0]
    frame = frame.dropna(how="all", axis=1)
    return frame


def _extract_header_metadata(soup: BeautifulSoup) -> dict[str, str]:
    subtitle = ""
    country = ""
    heading = soup.find("h2")
    if heading:
        subtitle = heading.get_text(" ", strip=True)
        parts = [part.strip() for part in subtitle.split(",") if part.strip()]
        if parts:
            country = parts[-1]
    return {"subtitle": subtitle, "country": country}


def _extract_stage_identifiers(soup: BeautifulSoup) -> list[str]:
    stage_select = soup.find("select", attrs={"name": "e"})
    if stage_select is None:
        return []

    stage_identifiers: list[str] = []
    seen: set[str] = set()
    for option in stage_select.find_all("option"):
        value = str(option.get("value", "")).strip()
        if not value or value in seen:
            continue
        stage_identifiers.append(value)
        seen.add(value)

    return stage_identifiers


def _summarize_results(results_df: pd.DataFrame) -> dict[str, float | int]:
    uci_points = pd.to_numeric(results_df.get("UCI"), errors="coerce").fillna(0)
    finishers = int(len(results_df))
    scoring_places = int((uci_points > 0).sum())

    return {
        "finishers": finishers,
        "scoring_places": scoring_places,
        "winner_points": float(uci_points.iloc[0]) if finishers else 0.0,
        "top10_points": float(uci_points.head(10).sum()),
        "total_points": float(uci_points.sum()),
    }


def _empty_stage_metrics() -> dict[str, float | int]:
    return {
        "stage_count": 0,
        "stage_pages_parsed": 0,
        "stage_pages_missing": 0,
        "stage_scoring_places": 0,
        "stage_winner_points": 0.0,
        "stage_top10_points": 0.0,
        "stage_total_points": 0.0,
    }


def _combine_event_results(
    gc_results_metrics: dict[str, float | int], stage_metrics: dict[str, float | int]
) -> dict[str, float | int]:
    gc_total_points = float(gc_results_metrics["total_points"])
    stage_total_points = float(stage_metrics["stage_total_points"])
    event_total_points = gc_total_points + stage_total_points

    gc_top10_points = float(gc_results_metrics["top10_points"])
    stage_top10_points = float(stage_metrics["stage_top10_points"])

    return {
        "finishers": int(gc_results_metrics["finishers"]),
        "scoring_places": int(gc_results_metrics["scoring_places"]) + int(stage_metrics["stage_scoring_places"]),
        "winner_points": float(gc_results_metrics["winner_points"])
        + float(stage_metrics["stage_winner_points"]),
        "top10_points": gc_top10_points + stage_top10_points,
        "total_points": event_total_points,
        "gc_scoring_places": int(gc_results_metrics["scoring_places"]),
        "gc_winner_points": float(gc_results_metrics["winner_points"]),
        "gc_top10_points": gc_top10_points,
        "gc_total_points": gc_total_points,
        "stage_count": int(stage_metrics["stage_count"]),
        "stage_pages_parsed": int(stage_metrics["stage_pages_parsed"]),
        "stage_pages_missing": int(stage_metrics["stage_pages_missing"]),
        "stage_scoring_places": int(stage_metrics["stage_scoring_places"]),
        "stage_winner_points": float(stage_metrics["stage_winner_points"]),
        "stage_top10_points": stage_top10_points,
        "stage_total_points": stage_total_points,
        "gc_points_share": (gc_total_points / event_total_points) if event_total_points else 0.0,
        "stage_points_share": (stage_total_points / event_total_points) if event_total_points else 0.0,
    }


def _summarize_startlist(startlist_df: pd.DataFrame) -> dict[str, float | int]:
    numeric_columns = ["Starts", "Wins", "Podium", "Top 10"]
    for column in numeric_columns:
        startlist_df[column] = pd.to_numeric(startlist_df.get(column), errors="coerce").fillna(0)

    startlist_df["podium_only"] = (startlist_df["Podium"] - startlist_df["Wins"]).clip(lower=0)
    startlist_df["top10_only"] = (startlist_df["Top 10"] - startlist_df["Podium"]).clip(lower=0)
    startlist_df["form_score"] = (
        (5.0 * startlist_df["Wins"])
        + (2.0 * startlist_df["podium_only"])
        + (1.0 * startlist_df["top10_only"])
        + (0.1 * startlist_df["Starts"])
    )

    ordered_scores = startlist_df["form_score"].sort_values(ascending=False).reset_index(drop=True)
    top_10_scores = ordered_scores.head(10)
    startlist_size = int(len(startlist_df))

    return {
        "startlist_size": startlist_size,
        "experienced_riders": int((startlist_df["form_score"] > 0).sum()),
        "total_startlist_starts": float(startlist_df["Starts"].sum()),
        "total_startlist_wins": float(startlist_df["Wins"].sum()),
        "total_startlist_podiums": float(startlist_df["Podium"].sum()),
        "total_startlist_top10s": float(startlist_df["Top 10"].sum()),
        "total_field_form": float(startlist_df["form_score"].sum()),
        "top10_field_form": float(top_10_scores.sum()),
        "avg_top10_field_form": float(top_10_scores.mean()) if not top_10_scores.empty else 0.0,
    }
