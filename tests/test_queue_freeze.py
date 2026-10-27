"""Queue scope freezes are dated advice, compatible with older settings."""

import datetime as dt

import pytest

from conftest import check, found, item, make_project, rs, run_init, set_queue


@pytest.mark.parametrize("value", ["until tomorrow", "until 2026-02-30", "on", "until 2026-1-01", ""])
def test_queue_freeze_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="Queue freeze"):
        rs.resolve({"queue_freeze": value}, None, {})


@pytest.mark.parametrize("value,day,expired", [
    ("off", "2026-10-26", False),
    ("until 2026-10-26", "2026-10-25", False),
    ("until 2026-10-26", "2026-10-26", False),
    ("until 2026-10-26", "2026-10-27", True),
])
def test_queue_freeze_expiry_warns_after_inclusive_date(tmp_path, value, day, expired):
    target = make_project(tmp_path, "freeze", "--queue-freeze", value)
    result = check(target, dt.datetime.fromisoformat(day + "T12:00:00"))
    assert not found(result, "ERROR")
    assert bool(found(result, "WARN", "plan.freeze.expired")) is expired


def test_queue_freeze_absent_defaults_off_and_reconfigure_preserves_it(tmp_path):
    target = make_project(tmp_path, "freeze")
    path = target / "agents.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Queue freeze: off\n", ""), encoding="utf-8")
    result = check(target)
    assert result.values["queue_freeze"] == "off"
    assert not found(result, "ERROR") and not found(result, "WARN")
    assert run_init(target, "--reconfigure", "--queue-freeze", "until 2026-11-01").returncode == 0
    assert run_init(target, "--reconfigure").returncode == 0
    assert rs.read_settings(path.read_text(encoding="utf-8")).values["queue_freeze"] == "until 2026-11-01"


@pytest.mark.parametrize("value,invalid", [("2026-11-01", False), ("2026-02-30", True), ("tomorrow", True)])
def test_ready_by_is_optional_and_validates_dates(tmp_path, value, invalid):
    target = make_project(tmp_path, "delivery", "--workflow", "unified")
    set_queue(target, item("H-A-01", extra=[("Ready by", value)]))
    result = check(target)
    assert bool(found(result, "WARN", "plan.ready-by.invalid")) is invalid
    assert not found(result, "WARN", "plan.field.unknown")
