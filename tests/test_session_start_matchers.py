"""Opt-in checks remain visible when only the lightweight plugin supplies hooks."""

import json
from pathlib import Path

import pytest

from conftest import unified_project
import ro_hooks
import ro_records
from ro_state import Project


@pytest.fixture
def plugin_project(tmp_path, monkeypatch):
    root = unified_project(tmp_path)
    project = Project(root, slot="A", session="plugin-session")
    project.register_slot()
    config = tmp_path / "host-config"
    config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    (config / "settings.json").write_text(json.dumps({
        "enabledPlugins": {"research-orchestrator@marketplace": True}}), encoding="utf-8")
    return project


@pytest.mark.parametrize("key,value,check", [
    ("autonomy", "away", "ask.away"),
    ("brief_requirements", "reviewer: Scope", "brief.requirements"),
    ("read_bound", "on", "jobs.read-bound"),
])
def test_plugin_reports_each_enabled_unsubscribed_check(plugin_project, key, value, check):
    notice = ro_records.plugin_matcher_guidance(plugin_project, {key: value})
    assert len(notice) == 1 and check in notice[0]
    assert "install.py --project ." in notice[0]


@pytest.mark.parametrize("matchers,expected", [
    (["AskUserQuestion|Agent", "Read|Glob|Grep"], set()),
    (["AskUserQuestion|Agent", "Read|Glob"], {"jobs.read-bound"}),
    (["Agent"], {"ask.away", "jobs.read-bound"}),
    (["[broken"], {"ask.away", "brief.requirements", "jobs.read-bound"}),
])
def test_manual_supplemental_matchers_remove_only_covered_notices(plugin_project, matchers, expected):
    folder = plugin_project.root / ".claude"
    folder.mkdir()
    (folder / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": matcher, "hooks": [{"type": "command", "command":
          'sh "${CLAUDE_PROJECT_DIR}/.claude/skills/research-orchestrator/hooks/ro-hook.sh" PreToolUse'}]}
        for matcher in matchers]}}), encoding="utf-8")
    notices = ro_records.plugin_matcher_guidance(plugin_project, {
        "autonomy": "away", "brief_requirements": "reviewer: Scope", "read_bound": "on"})
    actual = {check for check in ("ask.away", "brief.requirements", "jobs.read-bound")
              if any(check in notice for notice in notices)}
    assert actual == expected


@pytest.mark.parametrize("command", ["echo ready", "sh /plugin/hooks/ro-hook.sh PostToolUse"])
def test_unrelated_hook_does_not_mask_missing_subscription(plugin_project, command):
    folder = plugin_project.root / ".claude"
    folder.mkdir()
    (folder / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{
        "matcher": "AskUserQuestion", "hooks": [{"type": "command", "command": command}]}]}}), encoding="utf-8")
    assert ro_records.plugin_matcher_guidance(plugin_project, {"autonomy": "away"})


def test_disabled_plugin_and_default_settings_are_quiet(plugin_project):
    assert ro_records.plugin_matcher_guidance(plugin_project, {}) == []
    folder = plugin_project.root / ".claude"
    folder.mkdir()
    (folder / "settings.local.json").write_text(json.dumps({
        "enabledPlugins": {"research-orchestrator@marketplace": False}}), encoding="utf-8")
    assert ro_records.plugin_matcher_guidance(plugin_project, {"autonomy": "away"}) == []


def test_session_start_surfaces_missing_matchers(plugin_project, monkeypatch):
    path = plugin_project.root / "agents.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Autonomy: present", "- Autonomy: away"), encoding="utf-8")
    monkeypatch.setattr(ro_records, "publish_gate_guidance", lambda *_: [])
    result = ro_hooks.hook(plugin_project, "SessionStart", {"session_id": plugin_project.session})
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "ask.away" in context and "install.py --project ." in context
