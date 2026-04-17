from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://www.procyclingstats.com/"


@dataclass(frozen=True, slots=True)
class TeamProgramEntry:
    source_race_name: str
    date_label: str
    category: str
    source_url: str
    pcs_race_slug: str


@dataclass(frozen=True, slots=True)
class TeamRacePoints:
    team_slug: str
    race_slug: str
    source_url: str
    actual_points: float
    rider_count: int
    has_rows: bool


class ProCyclingStatsTeamCalendarClient:
    """PCS scraper for live team program and race-level points pages."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "darwin", "desktop": True}
        )

    def fetch_html(self, path: str) -> str:
        url = path if path.startswith("http") else urljoin(BASE_URL, path)
        response = self.scraper.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def get_team_program_entries(self, team_slug: str) -> tuple[str, list[TeamProgramEntry]]:
        html = self.fetch_html(f"team/{team_slug}/program")
        return parse_team_program_html(html)

    def get_team_race_points(self, team_slug: str, race_slug: str) -> TeamRacePoints:
        source_url = build_team_in_race_points_url(team_slug, race_slug)
        html = self.fetch_html(source_url)
        return parse_team_race_points_html(
            html,
            team_slug=team_slug,
            race_slug=race_slug,
            source_url=source_url,
        )


def build_team_program_url(team_slug: str) -> str:
    return urljoin(BASE_URL, f"team/{team_slug}/program")


def build_team_in_race_points_url(team_slug: str, race_slug: str) -> str:
    return urljoin(BASE_URL, f"team-in-race/{team_slug}/{race_slug}/points-per-rider")


def extract_race_slug(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""

    parsed = urlparse(text)
    path = parsed.path if parsed.scheme else text
    parts = path.strip("/").split("/")
    if len(parts) >= 4 and parts[0] == "race":
        return parts[1]
    if len(parts) >= 4 and parts[0] == "team-in-race":
        return parts[2]
    return ""


def parse_team_program_html(html: str) -> tuple[str, list[TeamProgramEntry]]:
    soup = BeautifulSoup(html, "html.parser")
    team_name = _extract_team_name(soup)
    table = _find_table_with_headers(soup, {"date", "race", "class"})
    if table is None:
        raise ValueError("Could not find the PCS team program table.")

    entries: list[TeamProgramEntry] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        race_cell = cells[2]
        race_name = race_cell.get_text(" ", strip=True)
        category = cells[3].get_text(" ", strip=True)
        if not race_name:
            continue

        race_link = race_cell.find("a", href=True)
        source_url = race_link.get("href", "").strip() if race_link is not None else ""
        entries.append(
            TeamProgramEntry(
                source_race_name=race_name,
                date_label=cells[1].get_text(" ", strip=True),
                category=category,
                source_url=source_url,
                pcs_race_slug=extract_race_slug(source_url),
            )
        )

    return team_name, entries


def parse_team_race_points_html(
    html: str,
    team_slug: str,
    race_slug: str,
    source_url: str,
) -> TeamRacePoints:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table_with_headers(soup, {"#", "rider", "points"})
    if table is None:
        return TeamRacePoints(
            team_slug=team_slug,
            race_slug=race_slug,
            source_url=source_url,
            actual_points=0.0,
            rider_count=0,
            has_rows=False,
        )

    actual_points = 0.0
    rider_count = 0
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        rider_name = cells[1].get_text(" ", strip=True)
        if not rider_name:
            continue
        rider_count += 1
        actual_points += _parse_number(cells[2].get_text(" ", strip=True))

    return TeamRacePoints(
        team_slug=team_slug,
        race_slug=race_slug,
        source_url=source_url,
        actual_points=actual_points,
        rider_count=rider_count,
        has_rows=rider_count > 0,
    )


def load_team_program_rows(path: str) -> pd.DataFrame:
    program_df = pd.read_csv(path).copy()
    if "source_race_name" not in program_df.columns and "race_name" in program_df.columns:
        program_df = program_df.rename(columns={"race_name": "source_race_name"})
    if "source_url" not in program_df.columns:
        program_df["source_url"] = ""
    if "pcs_race_slug" not in program_df.columns:
        program_df["pcs_race_slug"] = program_df["source_url"].map(extract_race_slug)
    return program_df


def _extract_team_name(soup: BeautifulSoup) -> str:
    if soup.title is None:
        return ""
    title = soup.title.get_text(" ", strip=True)
    if title.startswith("Program for "):
        return title.replace("Program for ", "", 1).strip()
    if " for " in title:
        return title.rsplit(" for ", 1)[-1].strip()
    return ""


def _find_table_with_headers(soup: BeautifulSoup, required_headers: set[str]) -> BeautifulSoup | None:
    normalized_required = {header.casefold() for header in required_headers}
    for table in soup.find_all("table"):
        headers = {th.get_text(" ", strip=True).casefold() for th in table.find_all("th")}
        if normalized_required.issubset(headers):
            return table
    return None


def _parse_number(value: str) -> float:
    cleaned = (
        str(value)
        .replace(",", "")
        .replace("\xa0", " ")
        .replace("−", "-")
        .replace("–", "-")
        .strip()
    )
    if cleaned in {"", "-", "--"}:
        return 0.0
    return float(cleaned)
