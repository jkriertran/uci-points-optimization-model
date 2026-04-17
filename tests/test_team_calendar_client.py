from uci_points_model.team_calendar_client import (
    build_team_in_race_points_url,
    extract_race_slug,
    parse_team_program_html,
    parse_team_race_points_html,
)


def test_parse_team_program_html_extracts_rows_and_slugs() -> None:
    html = """
    <html>
      <head><title>Program for Unibet Rose Rockets</title></head>
      <body>
        <table>
          <tr><th></th><th>Date</th><th>Race</th><th>Class</th></tr>
          <tr>
            <td>1</td>
            <td>2026-01-23</td>
            <td><a href="race/classica-camp-de-morvedre/2026/startlist">Classica Camp de Morvedre</a></td>
            <td>1.1</td>
          </tr>
          <tr>
            <td>2</td>
            <td>2026-05-08</td>
            <td><a href="race/giro-d-italia/2026/startlist">Giro d'Italia</a></td>
            <td>2.UWT</td>
          </tr>
        </table>
      </body>
    </html>
    """

    team_name, entries = parse_team_program_html(html)

    assert team_name == "Unibet Rose Rockets"
    assert len(entries) == 2
    assert entries[0].source_race_name == "Classica Camp de Morvedre"
    assert entries[0].pcs_race_slug == "classica-camp-de-morvedre"
    assert entries[1].category == "2.UWT"


def test_parse_team_race_points_html_handles_filled_and_empty_tables() -> None:
    filled_html = """
    <table>
      <tr><th>#</th><th>Rider</th><th>Points</th></tr>
      <tr><td>1</td><td>FELDMANN Karsten Larsen</td><td>12</td></tr>
      <tr><td>2</td><td>REINDERS Elmar</td><td>0</td></tr>
    </table>
    """
    empty_html = """
    <table>
      <tr><th>#</th><th>Rider</th><th>Points</th></tr>
    </table>
    """

    filled = parse_team_race_points_html(
        filled_html,
        team_slug="unibet-rose-rockets-2026",
        race_slug="ronde-van-limburg",
        source_url=build_team_in_race_points_url("unibet-rose-rockets-2026", "ronde-van-limburg"),
    )
    empty = parse_team_race_points_html(
        empty_html,
        team_slug="unibet-rose-rockets-2026",
        race_slug="giro-d-italia",
        source_url=build_team_in_race_points_url("unibet-rose-rockets-2026", "giro-d-italia"),
    )

    assert filled.has_rows is True
    assert filled.rider_count == 2
    assert filled.actual_points == 12.0
    assert empty.has_rows is False
    assert empty.rider_count == 0
    assert empty.actual_points == 0.0


def test_extract_race_slug_supports_relative_and_absolute_urls() -> None:
    assert extract_race_slug("race/giro-d-italia/2026/startlist") == "giro-d-italia"
    assert (
        extract_race_slug("https://www.procyclingstats.com/team-in-race/unibet-rose-rockets-2026/giro-d-italia/points-per-rider")
        == "giro-d-italia"
    )
