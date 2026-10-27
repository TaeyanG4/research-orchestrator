"""Wall-clock age alone does not turn idle work into a direction-review warning."""

import datetime as dt
import pytest
from conftest import append_events, check, event, found, set_queue, set_slot, unified_project, item
from guard_helpers import project, setting
import ro_records
from ro_state import Project


@pytest.mark.parametrize("profile", ["work", "research", "competition"])
@pytest.mark.parametrize("mode", ["light", "strict"])
@pytest.mark.parametrize("kind,stamp,worked", [("none", "2026-10-02 12:00", False),
    ("session", "2026-10-02 12:00", False), ("H-A-01", "2026-09-30 12:00", False),
    ("H-A-01", "2026-11-01 12:00", False), ("H-A-01", "2026-10-02 12:00", True)])
def test_stale_direction_requires_dated_item_activity(tmp_path, profile, mode, kind, stamp, worked):
    root = project(tmp_path, "GD", mode=mode, profile=profile)
    append_events(root, event(stamp, "A", kind))
    issues = found(check(root, dt.datetime(2026, 10, 27, 12)), check_id="guard.direction.stale")
    severity = ("ERROR" if mode == "strict" else "WARN") if worked or profile == "competition" else "INFO"
    assert [issue.severity for issue in issues] == [severity]


@pytest.mark.parametrize("pending,other_taken", [(False, False), (True, False), (False, True)])
def test_close_pauses_only_empty_idle_project(tmp_path, monkeypatch, pending, other_taken):
    root = unified_project(tmp_path)
    set_queue(root, *([item("H-A-01")] if pending else []))
    set_slot(root, "B", "local" if other_taken else "released")
    class Date(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 27)
    monkeypatch.setattr(ro_records.dt, "date", Date)
    ro_records.close(Project(root, slot="A"))
    text = (root / "handoff.md").read_text(encoding="utf-8")
    assert ("- Paused: 2026-10-27" in text) is (not pending and not other_taken)
    assert ro_records._slot_sections(text)["A"]["Current host"] == "released"
