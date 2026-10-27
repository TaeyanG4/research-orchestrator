"""P2 guard settings, activation dates, thresholds, and generated reading lists."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from conftest import make_project, rs, run_init


@pytest.mark.parametrize("profile, expected", [
    ("work", {"G5", "G6", "GD", "E1"}),
    ("research", {"G1", "G5", "G6", "GD", "E1"}),
    ("competition", set(rs.GUARD_IDS) - {"G12"}),
])
def test_profile_guard_defaults_and_explicit_override(profile, expected) -> None:
    values = rs.resolve({"profile": profile, "guards": "light"}, None, {})
    assert rs.enabled_guards(values) == expected
    assert "G12" not in rs.enabled_guards(values)
    assert rs.enabled_guards({**values, "guard_set": "G12"}) == {"G12"}
    assert rs.enabled_guards({**values, "guards": "off", "guard_set": "G12"}) == set()


def test_guard_set_canonicalizes_distinct_ids() -> None:
    assert rs.parse_guard_set("g6, g1, E1") == "G1,G6,E1"
    assert rs.parse_guard_set(" AUTO ") == "auto"
    for raw in ("", "G1,G1", "G2", "G1,", "G1 G6"):
        with pytest.raises(ValueError):
            rs.parse_guard_set(raw)


def test_guard_thresholds_defaults_subsets_and_units() -> None:
    expected = {"saturation": 5, "direction-review": 7, "insight-due": 48, "effort": 55,
                "milestones": (10, 25, 75), "direction-parts": "profile"}
    assert rs.guard_thresholds(rs.DEFAULT_GUARD_THRESHOLDS) == expected
    assert rs.guard_thresholds("saturation=8") == {**expected, "saturation": 8}
    assert rs.guard_thresholds("direction-review=12h, insight-due=3d") == {
        **expected, "direction-review": 0.5, "insight-due": 72}
    assert rs.parse_guard_thresholds(" effort = 60%, saturation=7 ") == "saturation=7, effort=60%"
    assert rs.guard_thresholds("direction-parts=full")["direction-parts"] == "full"
    assert rs.parse_guard_thresholds("direction-parts=profile") == "direction-parts=profile"


@pytest.mark.parametrize("raw", [
    "", "unknown=5", "saturation=0", "saturation=2.5", "saturation=5,saturation=6",
    "direction-review=0d", "direction-review=7", "insight-due=-1h", "effort=101%", "effort=55",
    "milestones=10/25", "milestones=25/10/75", "milestones=10/25/101", "direction-parts=some",
])
def test_guard_thresholds_reject_invalid_grammar(raw) -> None:
    with pytest.raises(ValueError):
        rs.parse_guard_thresholds(raw)


def test_guards_dates_are_validated_and_only_writes_create_them() -> None:
    today = dt.date(2026, 10, 25)
    assert rs.resolve({"guards": "light"}, None, {})["guards"] == "light"
    assert rs.stamp_guards("light", "off", today) == "light since 2026-10-25"
    assert rs.stamp_guards("strict", "light since 2026-09-01", today) == "strict since 2026-09-01"
    assert rs.stamp_guards("off", "strict since 2026-09-01", today) == "off"
    assert rs.stamp_guards("light since 2026-10-01", "off", today) == "light since 2026-10-01"
    assert rs.guard_since("light since 2026-10-01") == dt.date(2026, 10, 1)
    for raw in ("maybe", "off since 2026-10-01", "strict since 2026-02-30", "light since yesterday"):
        with pytest.raises(ValueError):
            rs.parse_guards(raw)


@pytest.mark.parametrize("profile, instruments, actions", [
    ("work", False, True), ("research", True, True), ("competition", True, True),
])
def test_templates_activate_only_relevant_registries_and_references(tmp_path, profile, instruments, actions) -> None:
    target = make_project(tmp_path, profile, "--profile", profile, "--guards", "light")
    handoff = (target / "handoff.md").read_text(encoding="utf-8")
    assert ("\n## Instruments\n" in handoff) == instruments
    assert ("\n## External actions\n" in handoff) == actions
    agents = (target / "agents.md").read_text(encoding="utf-8")
    assert "references/research-guards.md" in agents
    assert ("references/competition.md" in agents) == (profile == "competition")
    assert "references/postmortem.md" not in agents  # the core owns operation-only guidance
    assert "- Guards: light since " in agents
    assert "- Guard set: auto\n" in agents
    assert "{{" not in handoff and "{{" not in agents


@pytest.mark.parametrize("profile", ["work", "research"])
def test_reconfigure_adds_registries_preserves_date_and_existing_records(tmp_path, profile) -> None:
    target = make_project(tmp_path, profile, "--profile", profile)
    path = target / "handoff.md"
    original = path.read_text(encoding="utf-8")
    assert "## Instruments" not in original and "## External actions" not in original
    enabled = run_init(target, "--reconfigure", "--guards", "light since 2026-10-01")
    assert enabled.returncode == 0, enabled.stderr
    assert "## External actions" in path.read_text(encoding="utf-8")
    upgraded = run_init(target, "--reconfigure", "--guards", "strict", "--guard-set", "G1,E1")
    assert upgraded.returncode == 0, upgraded.stderr
    values = rs.read_settings((target / "agents.md").read_text(encoding="utf-8")).values
    assert values["guards"] == "strict since 2026-10-01"
    text = path.read_text(encoding="utf-8")
    assert text.count("## Instruments") == 1 and text.count("## External actions") == 1
    assert original.split("## Active handoff", 1)[1] == text.split("## Active handoff", 1)[1]
    disabled = run_init(target, "--reconfigure", "--guards", "off")
    assert disabled.returncode == 0, disabled.stderr
    assert path.read_text(encoding="utf-8") == text


def test_reusable_preset_does_not_copy_a_projects_activation_date(tmp_path, isolated_home) -> None:
    target = make_project(tmp_path, "source", "--guards", "light since 2026-01-01")
    saved = run_init(target, "--save-preset", "dated")
    assert saved.returncode == 0, saved.stderr
    data = json.loads((isolated_home / "presets" / "dated.json").read_text(encoding="utf-8"))
    assert data["guards"] == "light"
    fresh = make_project(tmp_path, "fresh", "--preset", "user:dated")
    values = rs.read_settings((fresh / "agents.md").read_text(encoding="utf-8")).values
    assert values["guards"] == f"light since {dt.date.today().isoformat()}"
