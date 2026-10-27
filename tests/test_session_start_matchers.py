"""Startup installs are requested only for the missing checkout publication gate."""

import json

import pytest

from conftest import unified_project
import ro_gate
import ro_hooks
import ro_records
from ro_state import Project


@pytest.mark.parametrize("policy", ["defaults", "away", "brief", "read-bound"])
@pytest.mark.parametrize("gate", ["non-git", "missing", "registered"])
@pytest.mark.parametrize("route", ["SessionStart", "brief"])
def test_governing_settings_do_not_add_project_reinstallation_notices(tmp_path, monkeypatch, policy, gate, route):
    root = unified_project(tmp_path)
    project = Project(root, slot="A", session="plugin-session")
    project.register_slot()
    path = root / "agents.md"
    settings = {"away": ("Autonomy", "present", "away"),
                "brief": ("Brief requirements", "none", "reviewer: Scope"),
                "read-bound": ("Read bound", "off", "on")}
    if policy in settings:
        label, before, after = settings[policy]
        path.write_text(path.read_text(encoding="utf-8").replace(
            f"- {label}: {before}", f"- {label}: {after}"), encoding="utf-8")
    config = tmp_path / "host-config"
    config.mkdir()
    (config / "settings.json").write_text(json.dumps({
        "enabledPlugins": {"research-orchestrator@marketplace": True}}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setattr(ro_gate, "registration", lambda _: (None if gate == "non-git" else root,
                                                          gate == "registered"))
    monkeypatch.setattr(ro_records.shutil, "which", lambda _: "ro")
    if route == "SessionStart":
        context = ro_hooks.hook(project, route, {"session_id": project.session})[
            "hookSpecificOutput"]["additionalContext"]
    else:
        context = ro_records.brief(project)
    # The notice names the checkout root rather than "." (nested --project paths are refused).
    assert ("--project " in context) is (gate == "missing")
    assert "--project ." not in context
    assert ("publish gate not installed" in context) is (gate == "missing")
    assert "not subscribed" not in context
