"""New-project defaults and plugin CLI guidance, with isolated host detection."""

import shutil

import pytest

from conftest import SKILL, check, init, rs, run_init
from ro_records import brief
from ro_command import shim_install_command
from ro_state import Project


@pytest.mark.parametrize("preset", [[], ["--preset", "custom"]])
@pytest.mark.parametrize("markers,host", [({}, "local"), ({"CLAUDECODE": "1"}, "Claude Code"),
                                        ({"CODEX_THREAD_ID": "test"}, "Codex"),
                                        ({"GEMINI_CLI": "1"}, "Gemini CLI")])
def test_new_custom_projects_use_work_defaults_and_detected_host(tmp_path, monkeypatch, preset, markers, host):
    for key, value in markers.items():
        monkeypatch.setenv(key, value)
    result = run_init(tmp_path, *preset, "--user", "operator")
    assert result.returncode == 0, result.stderr
    values = rs.read_settings((tmp_path / "agents.md").read_text(encoding="utf-8")).values
    assert {key: values[key] for key in ("preset", "profile", "verification", "platforms", "enforcement")} == {
        "preset": "custom", "profile": "work", "verification": "self", "platforms": host, "enforcement": "block"}
    assert values["block"] == rs.DEFAULT_BLOCK
    assert "- Goal: <goal or question>" in (tmp_path / "plan.md").read_text(encoding="utf-8")
    assert check(tmp_path).code == 0


def test_new_defaults_preserve_explicit_choices_and_old_missing_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    result = run_init(tmp_path, "--preset", "custom", "--profile", "research", "--verification", "hybrid",
                      "--enforcement", "warn", "--platforms", "Chosen, Alternate")
    assert result.returncode == 0, result.stderr
    values = rs.read_settings((tmp_path / "agents.md").read_text(encoding="utf-8")).values
    assert [values[key] for key in ("profile", "verification", "platforms", "enforcement")] == [
        "research", "hybrid", "Chosen, Alternate", "warn"]
    before = (tmp_path / "agents.md").read_bytes()
    monkeypatch.setenv("CODEX_THREAD_ID", "other")
    assert run_init(tmp_path).returncode == 0
    assert (tmp_path / "agents.md").read_bytes() == before
    old = rs.resolve({}, None, {})
    assert (old["profile"], old["verification"], old["platforms"]) == (
        "research", "cross-host-once", rs.DEFAULT_PLATFORMS)
    multi = rs.resolve({"platform_mode": "multi"}, None, {}, new_project=True)
    assert multi["platforms"] == rs.DEFAULT_PLATFORMS


def test_solo_research_generates_queue_order_and_migration_keeps_one_header(tmp_path):
    result = run_init(tmp_path, "--preset", "solo-research", "--user", "operator")
    assert result.returncode == 0, result.stderr
    plan = (tmp_path / "plan.md").read_text(encoding="utf-8")
    assert init.plan_schedule(plan) == {"Ordering": "Ordering: queue"}
    assert plan.count("Ordering: queue") == 1
    assert "scores and Priority are optional" in plan
    settings = rs.resolve({"preset": "solo-research"}, rs.load_preset("solo-research"), {})
    rendered = init.render_plan(settings, "example", init.queue_section())
    preserved = init.retain_plan_schedule("# Plan\nOrdering: priority\n\n## Queue\n", rendered)
    assert init.plan_schedule(preserved) == {"Ordering": "Ordering: priority"}
    assert "Ordering: queue" not in preserved


@pytest.mark.parametrize("metadata", ["", "Ordering: priority\n", "Ordering: queue\n"])
def test_solo_preset_migration_preserves_existing_ordering(metadata):
    settings = rs.resolve({"preset": "solo-research"}, rs.load_preset("solo-research"), {})
    plan, count = init.plan_to_unified("# Plan\n" + metadata + "\n## Agent: A\n", settings, "example")
    assert count == 0
    assert ("scores and Priority are optional" in plan) is ("queue" in metadata)
    assert plan.count("Ordering:") == bool(metadata)
    if metadata:
        assert metadata.strip() in plan


@pytest.mark.parametrize("available", [False, True])
def test_brief_prints_plugin_shim_install_route_only_when_missing(tmp_path, monkeypatch, available):
    assert init.main([str(tmp_path), "--preset", "quick"]) == 0
    project = Project(tmp_path, session="test")
    project.write_json("hooks-self-test.json", {"status": "active"})
    monkeypatch.setattr(shutil, "which", lambda name: "ro" if available else None)
    result = brief(project)
    assert (shim_install_command("sh") in result) is not available
    assert "hooks active" in result


def test_compute_guide_covers_non_compute_exclusive_resources():
    text = (SKILL / "references/compute.md").read_text(encoding="utf-8")
    assert "exclusive resource" in text
    assert "shared database" in text and "licensed seat" in text
