from uci_points_model.fc_client import FirstCyclingClient, RaceCalendarEntry


def test_build_race_edition_record_rolls_stage_points_into_stage_races(monkeypatch) -> None:
    entry = RaceCalendarEntry(
        race_id=42,
        race_name="Test Stage Race",
        category="2.1",
        date_label="01.05",
        month=5,
        year=2025,
    )

    results_html = """
    <html>
      <body>
        <h2>UCI, Stage race, Testland</h2>
        <select name="e">
          <option value="">GC</option>
          <option value="1">Stage: 01</option>
          <option value="2">Stage: 02</option>
        </select>
        <table>
          <tr><th>Pos</th><th>Rider</th><th>Team</th><th>UCI</th></tr>
          <tr><td>1</td><td>GC Winner</td><td>A</td><td>20</td></tr>
          <tr><td>2</td><td>GC Runner-up</td><td>B</td><td>10</td></tr>
        </table>
      </body>
    </html>
    """
    startlist_html = """
    <html>
      <body>
        <table>
          <tr><th>BiB</th><th>Rider</th><th>Starts</th><th>Wins</th><th>Podium</th><th>Top 10</th></tr>
          <tr><td>1</td><td>Rider One</td><td>10</td><td>2</td><td>4</td><td>6</td></tr>
          <tr><td>2</td><td>Rider Two</td><td>8</td><td>1</td><td>2</td><td>5</td></tr>
        </table>
      </body>
    </html>
    """
    stage_1_html = """
    <html>
      <body>
        <table>
          <tr><th>Pos</th><th>Rider</th><th>Team</th><th>UCI</th></tr>
          <tr><td>1</td><td>Stage Winner</td><td>A</td><td>14</td></tr>
          <tr><td>2</td><td>Stage Runner-up</td><td>B</td><td>5</td></tr>
          <tr><td>3</td><td>Stage Third</td><td>C</td><td>0</td></tr>
        </table>
      </body>
    </html>
    """
    stage_2_html = """
    <html>
      <body>
        <table>
          <tr><th>Pos</th><th>Rider</th><th>Team</th><th>UCI</th></tr>
          <tr><td>1</td><td>Second Stage Winner</td><td>A</td><td>14</td></tr>
          <tr><td>2</td><td>Second Stage Runner-up</td><td>B</td><td>5</td></tr>
        </table>
      </body>
    </html>
    """

    def fake_fetch_html(path: str, params: dict[str, object] | None = None) -> str:
        params = params or {}
        if params.get("k") == 9:
            return startlist_html
        if params.get("e") == "1":
            return stage_1_html
        if params.get("e") == "2":
            return stage_2_html
        return results_html

    client = FirstCyclingClient()
    monkeypatch.setattr(client, "fetch_html", fake_fetch_html)

    record = client.build_race_edition_record(entry)

    assert record["race_type"] == "Stage race"
    assert record["gc_top10_points"] == 30.0
    assert record["stage_top10_points"] == 38.0
    assert record["top10_points"] == 68.0
    assert record["winner_points"] == 48.0
    assert record["total_points"] == 68.0
    assert record["stage_count"] == 2
    assert record["stage_pages_parsed"] == 2
    assert record["stage_pages_missing"] == 0
    assert record["stage_points_share"] == 38.0 / 68.0
