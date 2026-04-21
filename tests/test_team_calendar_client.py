from uci_points_model.team_calendar_client import (
    build_team_in_race_points_url,
    build_rider_season_results_url,
    extract_race_slug,
    parse_rider_season_uci_results_html,
    parse_team_program_html,
    parse_team_race_points_html,
    parse_team_season_riders_html,
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


def test_parse_team_season_riders_html_extracts_unique_rider_slugs() -> None:
    html = """
    <html>
      <body>
        <div>PCS Points</div>
        <table>
          <tr><th>Pos.</th><th>Rider</th><th></th><th>Points</th></tr>
          <tr><td>1</td><td><a href="rider/dylan-groenewegen">GROENEWEGEN Dylan</a></td><td>592</td><td>592</td></tr>
          <tr><td>2</td><td><a href="rider/clement-venturini">VENTURINI Clément</a></td><td>255</td><td>255</td></tr>
          <tr><td>3</td><td><a href="rider/dylan-groenewegen">GROENEWEGEN Dylan</a></td><td>592</td><td>592</td></tr>
        </table>
        <div>UCI Points</div>
        <table>
          <tr><th>Pos.</th><th>Rider</th><th></th><th>Points</th></tr>
          <tr><td>1</td><td><a href="rider/dylan-groenewegen">GROENEWEGEN Dylan</a></td><td>1080</td><td>1080</td></tr>
        </table>
      </body>
    </html>
    """

    riders = parse_team_season_riders_html(html)

    assert [rider.rider_slug for rider in riders] == ["dylan-groenewegen", "clement-venturini"]
    assert riders[0].rider_name == "GROENEWEGEN Dylan"


def test_parse_rider_season_uci_results_html_sums_composite_values() -> None:
    html = """
    <html>
      <body>
        <table>
          <tr>
            <th>Date</th><th># Result</th><th></th><th></th><th>Race</th><th>Distance</th><th>Points PCS</th><th>Points UCI</th><th></th>
          </tr>
          <tr>
            <td>08.02</td><td>12</td><td></td><td></td>
            <td><a href="race/etoile-de-besseges/2026/stage-4">S4 Stage 4 - Saint-Christol-lez-Alès › Vauvert</a></td>
            <td>100</td><td>5</td><td>5 +3</td><td>more</td>
          </tr>
          <tr>
            <td>10.04</td><td>4</td><td></td><td></td>
            <td><a href="race/region-pays-de-la-loire/2026/gc">General classification</a></td>
            <td>0</td><td>80</td><td>80</td><td>more</td>
          </tr>
          <tr>
            <td>12.04</td><td>88</td><td></td><td></td>
            <td><a href="race/paris-roubaix/2026/result">Paris-Roubaix Hauts-de-France</a></td>
            <td>259</td><td>-</td><td>-</td><td>more</td>
          </tr>
        </table>
      </body>
    </html>
    """

    rows = parse_rider_season_uci_results_html(
        html,
        rider_slug="lukas-kubis",
        source_url=build_rider_season_results_url("lukas-kubis", 2026),
    )

    assert len(rows) == 2
    assert rows[0].race_slug == "etoile-de-besseges"
    assert rows[0].uci_points == 8.0
    assert rows[1].race_slug == "region-pays-de-la-loire"
    assert rows[1].uci_points == 80.0
