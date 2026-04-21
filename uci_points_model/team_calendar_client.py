from __future__ import annotations

from dataclasses import dataclass
import re
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
class TeamSeasonRider:
    rider_name: str
    rider_slug: str


@dataclass(frozen=True, slots=True)
class RiderSeasonResult:
    rider_slug: str
    race_slug: str
    race_name: str
    uci_points: float
    source_url: str


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
        self._team_season_uci_cache: dict[tuple[str, int], dict[str, TeamRacePoints]] = {}
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

    def get_team_race_uci_points(self, team_slug: str, race_slug: str, season_year: int) -> TeamRacePoints:
        cache_key = (team_slug, int(season_year))
        if cache_key not in self._team_season_uci_cache:
            self._team_season_uci_cache[cache_key] = self._build_team_season_uci_points(
                team_slug,
                season_year=int(season_year),
            )
        default_source_url = build_team_season_points_per_rider_url(team_slug)
        return self._team_season_uci_cache[cache_key].get(
            race_slug,
            TeamRacePoints(
                team_slug=team_slug,
                race_slug=race_slug,
                source_url=default_source_url,
                actual_points=0.0,
                rider_count=0,
                has_rows=False,
            ),
        )

    def _build_team_season_uci_points(self, team_slug: str, season_year: int) -> dict[str, TeamRacePoints]:
        source_url = build_team_season_points_per_rider_url(team_slug)
        riders = self.get_team_season_riders(team_slug)
        race_totals: dict[str, float] = {}
        race_scorers: dict[str, set[str]] = {}

        for rider in riders:
            for result in self.get_rider_season_uci_results(rider.rider_slug, season_year):
                race_totals[result.race_slug] = race_totals.get(result.race_slug, 0.0) + float(result.uci_points)
                race_scorers.setdefault(result.race_slug, set()).add(rider.rider_slug)

        return {
            race_slug: TeamRacePoints(
                team_slug=team_slug,
                race_slug=race_slug,
                source_url=source_url,
                actual_points=total_points,
                rider_count=len(race_scorers.get(race_slug, set())),
                has_rows=True,
            )
            for race_slug, total_points in race_totals.items()
        }

    def get_team_season_riders(self, team_slug: str) -> list[TeamSeasonRider]:
        html = self.fetch_html(build_team_season_points_per_rider_url(team_slug))
        return parse_team_season_riders_html(html)

    def get_rider_season_uci_results(self, rider_slug: str, season_year: int) -> list[RiderSeasonResult]:
        source_url = build_rider_season_results_url(rider_slug, season_year)
        html = self.fetch_html(source_url)
        return parse_rider_season_uci_results_html(
            html,
            rider_slug=rider_slug,
            source_url=source_url,
        )


def build_team_program_url(team_slug: str) -> str:
    return urljoin(BASE_URL, f"team/{team_slug}/program")


def build_team_in_race_points_url(team_slug: str, race_slug: str) -> str:
    return urljoin(BASE_URL, f"team-in-race/{team_slug}/{race_slug}/points-per-rider")


def build_team_season_points_per_rider_url(team_slug: str) -> str:
    return urljoin(BASE_URL, f"team/{team_slug}/season/points-per-rider")


def build_rider_season_results_url(rider_slug: str, season_year: int) -> str:
    return urljoin(BASE_URL, f"rider/{rider_slug}/{season_year}")


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


def parse_team_season_riders_html(html: str) -> list[TeamSeasonRider]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table_with_headers(soup, {"pos.", "rider", "points"})
    if table is None:
        raise ValueError("Could not find the PCS team season points-per-rider table.")

    riders: list[TeamSeasonRider] = []
    seen_rider_slugs: set[str] = set()
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        rider_cell = cells[1]
        rider_name = rider_cell.get_text(" ", strip=True)
        rider_link = rider_cell.find("a", href=True)
        rider_slug = _extract_slug(rider_link.get("href", ""), prefix="rider") if rider_link is not None else ""
        if not rider_name or not rider_slug or rider_slug in seen_rider_slugs:
            continue
        riders.append(TeamSeasonRider(rider_name=rider_name, rider_slug=rider_slug))
        seen_rider_slugs.add(rider_slug)
    return riders


def parse_rider_season_uci_results_html(
    html: str,
    rider_slug: str,
    source_url: str,
) -> list[RiderSeasonResult]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table_with_headers(soup, {"date", "race", "points uci"})
    if table is None:
        return []

    header_cells = table.find_all("tr")[0].find_all("th")
    header_labels = [cell.get_text(" ", strip=True).casefold() for cell in header_cells]
    try:
        race_idx = header_labels.index("race")
        uci_points_idx = header_labels.index("points uci")
    except ValueError as exc:
        raise ValueError("Could not locate rider season UCI result columns.") from exc

    results: list[RiderSeasonResult] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) <= max(race_idx, uci_points_idx):
            continue
        race_cell = cells[race_idx]
        race_name = race_cell.get_text(" ", strip=True)
        race_link = race_cell.find("a", href=True)
        race_slug = extract_race_slug(race_link.get("href", "")) if race_link is not None else ""
        uci_points = _parse_composite_number(cells[uci_points_idx].get_text(" ", strip=True))
        if not race_slug or uci_points <= 0:
            continue
        results.append(
            RiderSeasonResult(
                rider_slug=rider_slug,
                race_slug=race_slug,
                race_name=race_name,
                uci_points=uci_points,
                source_url=source_url,
            )
        )
    return results


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


def _parse_composite_number(value: str) -> float:
    cleaned = str(value).replace(",", "").strip()
    if cleaned in {"", "-", "--"}:
        return 0.0
    parts = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
    if not parts:
        return 0.0
    return float(sum(float(part) for part in parts))


def _extract_slug(href: str, prefix: str) -> str:
    if not href:
        return ""
    normalized = href.strip("/")
    parts = normalized.split("/")
    if len(parts) < 2 or parts[0] != prefix:
        return ""
    return parts[1]
