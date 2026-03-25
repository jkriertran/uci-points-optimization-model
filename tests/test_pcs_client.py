from uci_points_model.pcs_client import (
    CYCLE_SCOPE,
    CURRENT_SCOPE,
    _parse_current_breakdown,
    _parse_cycle_breakdown,
    _parse_team_rankings,
)


def test_parse_team_rankings_extracts_team_links_and_breakdowns() -> None:
    html = """
    <table>
      <tr>
        <th>#</th><th>Prev.</th><th>Diff.</th><th>Team</th><th>Class</th><th>Points</th>
      </tr>
      <tr>
        <td>10</td><td>20</td><td>▲10</td>
        <td><a href="team/cofidis-2026">Cofidis</a></td>
        <td>PRT</td>
        <td><a href="team/cofidis-2026/results/uci-world-teams">2340</a></td>
      </tr>
      <tr>
        <td>11</td><td>9</td><td>▼2</td>
        <td><a href="team/team-picnic-postnl-2026">Team Picnic PostNL</a></td>
        <td>WT</td>
        <td><a href="team/team-picnic-postnl-2026/results/uci-world-teams">500</a></td>
      </tr>
    </table>
    """

    entries = _parse_team_rankings(html, scope=CURRENT_SCOPE)

    assert len(entries) == 2
    assert entries[0].team_name == "Cofidis"
    assert entries[0].team_slug == "cofidis-2026"
    assert entries[0].team_class == "PRT"
    assert entries[0].ranking_points == 2340.0
    assert entries[0].breakdown_path.endswith("results/uci-world-teams")


def test_parse_current_breakdown_extracts_rows_and_footer_total() -> None:
    html = """
    <h2>2026 (PRT)</h2>
    <table>
      <tr>
        <th>#</th><th>rider</th><th>Points counted</th><th>Points not counted</th><th>Sanctions</th>
      </tr>
      <tr>
        <td>1</td><td><a href="rider/alex-aranburu">ARANBURU Alex</a></td><td>100</td><td>-</td><td>-</td>
      </tr>
      <tr>
        <td>2</td><td><a href="rider/bryan-coquard">COQUARD Bryan</a></td><td>50.5</td><td>5</td><td>2</td>
      </tr>
      <tr>
        <td></td><td></td><td>150.5</td><td></td><td></td>
      </tr>
    </table>
    """

    breakdown = _parse_current_breakdown(html, source_url="https://example.com/current")

    assert breakdown.total_counted_points == 150.5
    assert breakdown.sanction_points_total == 2.0
    assert len(breakdown.rows) == 2
    assert breakdown.rows[1]["season_year"] == 2026
    assert breakdown.rows[1]["rider_slug"] == "bryan-coquard"
    assert breakdown.rows[1]["points_not_counted"] == 5.0


def test_parse_cycle_breakdown_extracts_multi_year_rows_and_sanction_footer() -> None:
    html = """
    <table>
      <tr><th>Season</th><th>Points</th></tr>
      <tr><td>2026</td><td>200</td></tr>
      <tr><td>2027</td><td>100</td></tr>
    </table>
    <table>
      <tr>
        <th>Season</th><th>Rider</th><th>Nth best rider for team</th><th>Points counted</th><th>Not counted</th><th>Sanction points</th>
      </tr>
      <tr>
        <td>2026</td><td><a href="rider/alex-aranburu">ARANBURU Alex</a></td><td>1</td><td>200</td><td>-</td><td>-</td>
      </tr>
      <tr>
        <td>2027</td><td><a href="rider/alex-aranburu">ARANBURU Alex</a></td><td>1</td><td>100</td><td>10</td><td>5</td>
      </tr>
      <tr>
        <td></td><td></td><td></td><td>300</td><td></td><td>5</td>
      </tr>
    </table>
    """

    breakdown = _parse_cycle_breakdown(html, source_url="https://example.com/cycle")

    assert breakdown.total_counted_points == 300.0
    assert breakdown.sanction_points_total == 5.0
    assert len(breakdown.rows) == 2
    assert breakdown.rows[0]["season_year"] == 2026
    assert breakdown.rows[1]["team_rank_within_counted_list"] == 1
    assert breakdown.rows[1]["sanction_points"] == 5.0


def test_parse_team_rankings_supports_cycle_scope_breakdown_suffix() -> None:
    html = """
    <table>
      <tr>
        <th>#</th><th>Prev.</th><th>Diff.</th><th>Team</th><th>Class</th><th>Points</th><th></th>
      </tr>
      <tr>
        <td>14</td><td></td><td>-</td>
        <td><a href="team/tudor-pro-cycling-team-2026">Tudor Pro Cycling Team</a></td>
        <td>PRT</td>
        <td>1508</td>
        <td><a href="team/tudor-pro-cycling-team-2026/results/ranking-2026-2028">1508</a></td>
      </tr>
    </table>
    """

    entries = _parse_team_rankings(html, scope=CYCLE_SCOPE)

    assert len(entries) == 1
    assert entries[0].team_slug == "tudor-pro-cycling-team-2026"
    assert entries[0].breakdown_path.endswith("results/ranking-2026-2028")
