import uci_points_model.data as data_module


class _BrokenCalendarClient:
    def get_calendar_entries(self, year: int, categories=None, months=None):  # noqa: ANN001
        raise RuntimeError("calendar fetch failed")


def test_load_calendar_uses_bundled_snapshot_when_live_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr(data_module, "FirstCyclingClient", lambda: _BrokenCalendarClient())

    calendar = data_module.load_calendar(2026, categories=("1.Pro", "2.Pro", "1.1", "2.1"))

    assert not calendar.empty
    assert calendar.attrs["calendar_source"] == "snapshot"
    assert set(calendar["category"]).issubset({"1.Pro", "2.Pro", "1.1", "2.1"})


def test_load_calendar_marks_calendar_unavailable_without_live_or_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(data_module, "FirstCyclingClient", lambda: _BrokenCalendarClient())

    calendar = data_module.load_calendar(2099, categories=("1.Pro",))

    assert calendar.empty
    assert calendar.attrs["calendar_source"] == "unavailable"
