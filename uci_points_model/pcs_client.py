from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://www.procyclingstats.com/"
CURRENT_SCOPE = "current"
CYCLE_SCOPE = "cycle_2026_2028"
CURRENT_SCOPE_LABEL = "Current season"
CYCLE_SCOPE_LABEL = "2026-2028 license cycle"
CYCLE_LABEL = "2026-2028"

SCOPE_CONFIG: dict[str, dict[str, str]] = {
    CURRENT_SCOPE: {
        "ranking_path": "rankings/me/uci-teams",
        "breakdown_suffix": "results/uci-world-teams",
        "breakdown_label": "UCI World teams",
        "scope_label": CURRENT_SCOPE_LABEL,
        "cycle_label": "",
    },
    CYCLE_SCOPE: {
        "ranking_path": "rankings/ranking-2026-2028",
        "breakdown_suffix": "results/ranking-2026-2028",
        "breakdown_label": "UCI Teams (2026-2028)",
        "scope_label": CYCLE_SCOPE_LABEL,
        "cycle_label": CYCLE_LABEL,
    },
}


@dataclass(frozen=True, slots=True)
class TeamRankingEntry:
    team_rank: int
    team_name: str
    team_slug: str
    team_class: str
    ranking_points: float
    team_path: str
    breakdown_path: str


@dataclass(frozen=True, slots=True)
class TeamBreakdown:
    rows: list[dict[str, Any]]
    total_counted_points: float
    sanction_points_total: float
    source_url: str


class ProCyclingStatsClient:
    """PCS scraper for team rankings and rider contribution breakdowns."""

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

    def get_team_rankings(self, scope: str) -> list[TeamRankingEntry]:
        config = _scope_config(scope)
        html = self.fetch_html(config["ranking_path"])
        return _parse_team_rankings(html, scope=scope)

    def get_team_breakdown(self, team_path: str, scope: str) -> TeamBreakdown:
        config = _scope_config(scope)
        normalized_team_path = team_path.strip("/")
        breakdown_path = f"{normalized_team_path}/{config['breakdown_suffix']}"
        html = self.fetch_html(breakdown_path)
        breakdown = (
            _parse_current_breakdown(html, source_url=urljoin(BASE_URL, breakdown_path))
            if scope == CURRENT_SCOPE
            else _parse_cycle_breakdown(html, source_url=urljoin(BASE_URL, breakdown_path))
        )
        return breakdown


def _scope_config(scope: str) -> dict[str, str]:
    if scope not in SCOPE_CONFIG:
        raise ValueError(f"Unsupported PCS scope: {scope}")
    return SCOPE_CONFIG[scope]


def _parse_team_rankings(html: str, scope: str) -> list[TeamRankingEntry]:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table_with_headers(soup, {"#", "Team", "Class", "Points"})
    if table is None:
        raise ValueError("Could not find the PCS team rankings table.")

    config = _scope_config(scope)
    entries: list[TeamRankingEntry] = []

    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        team_rank = _parse_int(cells[0].get_text(" ", strip=True))
        team_name = cells[3].get_text(" ", strip=True)
        team_class = cells[4].get_text(" ", strip=True)
        ranking_points = _parse_number(cells[5].get_text(" ", strip=True))
        links = [link.get("href", "").strip("/") for link in row.find_all("a", href=True)]
        team_path = next((link for link in links if link.startswith("team/") and "/results/" not in link), "")

        if team_rank is None or not team_name or not team_class or not team_path:
            continue

        team_slug = team_path.split("/", 1)[1]
        entries.append(
            TeamRankingEntry(
                team_rank=team_rank,
                team_name=team_name,
                team_slug=team_slug,
                team_class=team_class,
                ranking_points=ranking_points,
                team_path=team_path,
                breakdown_path=f"{team_path}/{config['breakdown_suffix']}",
            )
        )

    return entries


def _parse_current_breakdown(html: str, source_url: str) -> TeamBreakdown:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_table_with_headers(
        soup, {"#", "rider", "Points counted", "Points not counted", "Sanctions"}
    )
    if table is None:
        raise ValueError("Could not find the PCS current UCI world teams breakdown table.")

    total_counted_points = 0.0
    rows: list[dict[str, Any]] = []

    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        rank_text = cells[0].get_text(" ", strip=True)
        rider_name = cells[1].get_text(" ", strip=True)
        if rank_text == "" and rider_name == "":
            total_counted_points = _parse_number(cells[2].get_text(" ", strip=True))
            continue

        rider_rank = _parse_int(rank_text)
        if rider_rank is None or not rider_name:
            continue

        rider_link = row.find("a", href=True)
        rider_slug = _extract_slug(rider_link.get("href", ""), prefix="rider")
        rows.append(
            {
                "season_year": _extract_year_from_team_heading(soup),
                "rider_name": rider_name,
                "rider_slug": rider_slug,
                "team_rank_within_counted_list": rider_rank,
                "points_counted": _parse_number(cells[2].get_text(" ", strip=True)),
                "points_not_counted": _parse_number(cells[3].get_text(" ", strip=True)),
                "sanction_points": _parse_number(cells[4].get_text(" ", strip=True)),
            }
        )

    return TeamBreakdown(
        rows=rows,
        total_counted_points=total_counted_points or sum(row["points_counted"] for row in rows),
        sanction_points_total=sum(row["sanction_points"] for row in rows),
        source_url=source_url,
    )


def _parse_cycle_breakdown(html: str, source_url: str) -> TeamBreakdown:
    soup = BeautifulSoup(html, "html.parser")
    rider_table = _find_table_with_headers(
        soup,
        {"Season", "Rider", "Nth best rider for team", "Points counted", "Not counted", "Sanction points"},
    )
    if rider_table is None:
        raise ValueError("Could not find the PCS cycle ranking breakdown table.")

    total_counted_points = 0.0
    sanction_points_total = 0.0
    rows: list[dict[str, Any]] = []

    for row in rider_table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        season_text = cells[0].get_text(" ", strip=True)
        rider_name = cells[1].get_text(" ", strip=True)
        if season_text == "" and rider_name == "":
            total_counted_points = _parse_number(cells[3].get_text(" ", strip=True))
            sanction_points_total = _parse_number(cells[5].get_text(" ", strip=True))
            continue

        season_year = _parse_int(season_text)
        rider_rank = _parse_int(cells[2].get_text(" ", strip=True))
        if season_year is None or rider_rank is None or not rider_name:
            continue

        rider_link = row.find("a", href=True)
        rider_slug = _extract_slug(rider_link.get("href", ""), prefix="rider")
        rows.append(
            {
                "season_year": season_year,
                "rider_name": rider_name,
                "rider_slug": rider_slug,
                "team_rank_within_counted_list": rider_rank,
                "points_counted": _parse_number(cells[3].get_text(" ", strip=True)),
                "points_not_counted": _parse_number(cells[4].get_text(" ", strip=True)),
                "sanction_points": _parse_number(cells[5].get_text(" ", strip=True)),
            }
        )

    if sanction_points_total == 0.0:
        sanction_points_total = sum(row["sanction_points"] for row in rows)

    return TeamBreakdown(
        rows=rows,
        total_counted_points=total_counted_points or sum(row["points_counted"] for row in rows),
        sanction_points_total=sanction_points_total,
        source_url=source_url,
    )


def _find_table_with_headers(soup: BeautifulSoup, required_headers: set[str]) -> BeautifulSoup | None:
    normalized_required = {header.casefold() for header in required_headers}
    for table in soup.find_all("table"):
        headers = {th.get_text(" ", strip=True).casefold() for th in table.find_all("th")}
        if normalized_required.issubset(headers):
            return table
    return None


def _parse_number(text: str) -> float:
    cleaned = text.replace(",", "").strip()
    if cleaned in {"", "-"}:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_int(text: str) -> int | None:
    cleaned = text.strip()
    return int(cleaned) if cleaned.isdigit() else None


def _extract_slug(href: str, prefix: str) -> str:
    if not href:
        return ""
    normalized = href.strip("/")
    parts = normalized.split("/")
    if len(parts) < 2 or parts[0] != prefix:
        return ""
    return parts[1]


def _extract_year_from_team_heading(soup: BeautifulSoup) -> int | None:
    heading = soup.find("h2")
    if heading is None:
        return None
    text = heading.get_text(" ", strip=True)
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None
