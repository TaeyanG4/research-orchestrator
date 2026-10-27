"""Project policy subscriptions survive plugin deduplication without host probes."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from types import SimpleNamespace

import pytest

from conftest import ROOT


SPEC = importlib.util.spec_from_file_location("plugin_supplement_installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class FixedDateTime(dt.datetime):
    @classmethod
    def now(cls):
        return cls(2026, 10, 27, 12, 0)


@pytest.mark.parametrize("plugin_active", [False, True])
@pytest.mark.parametrize("autonomy,brief,optional", [
    ("present", "none", set()),
    ("away", "none", {"AskUserQuestion"}),
    ("present", "reviewer: Inspect evidence", {"Agent"}),
    ("away", "reviewer: Inspect evidence", {"AskUserQuestion", "Agent"}),
])
@pytest.mark.parametrize("read_bound", ["off", "on"])
@pytest.mark.parametrize("edit_first", [False, True])
def test_installed_project_policy_matrix(tmp_path, monkeypatch, plugin_active, autonomy, brief, optional, read_bound,
                                        edit_first):
    monkeypatch.setattr(installer, "dt", SimpleNamespace(datetime=FixedDateTime))
    plugin = json.loads((installer.HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    if edit_first:
        plugin["PreToolUse"].reverse()
        source = tmp_path / "hooks"
        source.mkdir()
        (source / "hooks.json").write_text(json.dumps({"hooks": plugin}), encoding="utf-8")
        monkeypatch.setattr(installer, "HOOKS", source)
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    project.mkdir()
    rules = project / "agents.md"
    rules.write_text(f"## Project settings\n- Autonomy: {autonomy}\n- Brief requirements: {brief}\n"
                     f"- Read bound: {read_bound}\n", encoding="utf-8")
    settings = project / ".claude/settings.json"
    settings.parent.mkdir()
    foreign = {"matcher": "Write", "hooks": [{"type": "command", "command": "unrelated-check"}]}
    settings.write_text(json.dumps({"enabledPlugins": {"research-orchestrator@local": plugin_active},
                                    "hooks": {"PreToolUse": [foreign]}}), encoding="utf-8")
    setup = installer.Installer(installer.parser().parse_args(
        ["--home", str(home), "--project", str(project), "--host", "claude-code", "--no-shim"]))

    def register():
        template = setup.claude_template("${CLAUDE_PROJECT_DIR}/.claude/skills/research-orchestrator")
        setup.merge(settings, setup.hook_template("claude-code", template), project / "backups")
        return json.loads(settings.read_text(encoding="utf-8"))

    document = register()
    hooks = document["hooks"]
    owned = [entry for entry in hooks["PreToolUse"] if setup.owned(entry)]
    tools = [name for entry in owned for name in entry["matcher"].split("|")]
    reads = {"Glob", "Grep", "Read"} if read_bound == "on" else set()
    covered = {"Bash", "PowerShell", "Edit", "Write", "NotebookEdit"}
    assert set(tools) == optional | reads | (set() if plugin_active else covered)
    assert len(tools) == len(set(tools))
    assert set(hooks) == ({"PreToolUse"} if plugin_active else {"PreToolUse", "PostToolUse", "SessionStart", "Stop"})
    assert [entry for entry in hooks["PreToolUse"] if not setup.owned(entry)] == [foreign]
    assert document["enabledPlugins"] == {"research-orchestrator@local": plugin_active}
    assert all("${CLAUDE_PROJECT_DIR}/.claude/skills/research-orchestrator/hooks/ro-hook.sh" in hook["command"]
               for entry in owned for hook in entry["hooks"])

    for event in ("PreToolUse", "PostToolUse"):
        manual = [entry for entry in hooks.get(event, []) if setup.owned(entry)]
        provided = plugin[event] if plugin_active else []
        manual_tools = [name for entry in manual for name in entry["matcher"].split("|")]
        plugin_tools = [name for entry in provided for name in entry["matcher"].split("|")]
        assert set(manual_tools).isdisjoint(plugin_tools)
        effective_tools = manual_tools + plugin_tools
        assert len(effective_tools) == len(set(effective_tools))
        assert set(effective_tools) == covered | (optional | reads if event == "PreToolUse" else set())
        for entry in manual + provided:
            assert len(entry["hooks"]) == 1
            for name in entry["matcher"].split("|"):
                suffix = " --tool edit" if name in {"Edit", "Write", "NotebookEdit"} else ""
                if event == "PostToolUse":
                    suffix = " --general"
                assert entry["hooks"][0]["command"].endswith(f" {event}{suffix}")
    before = settings.read_bytes()
    assert register() == document
    assert settings.read_bytes() == before

    rules.write_text("## Project settings\n- Autonomy: present\n- Brief requirements: none\n- Read bound: off\n",
                     encoding="utf-8")
    refreshed = register()
    refreshed_tools = {name for entry in refreshed["hooks"]["PreToolUse"] if setup.owned(entry)
                       for name in entry["matcher"].split("|")}
    assert refreshed_tools == (set() if plugin_active else covered)
    assert [entry for entry in refreshed["hooks"]["PreToolUse"] if not setup.owned(entry)] == [foreign]


@pytest.mark.parametrize("plugin_active", [False, True])
def test_policy_subscriptions_only_add_tools_missing_from_shipped_matchers(tmp_path, monkeypatch, plugin_active):
    plugin = json.loads((installer.HOOKS / "hooks.json").read_text(encoding="utf-8"))
    general = next(entry for entry in plugin["hooks"]["PreToolUse"] if "Bash" in entry["matcher"].split("|"))
    general["matcher"] += "|AskUserQuestion|Read"
    source = tmp_path / "hooks"
    source.mkdir()
    (source / "hooks.json").write_text(json.dumps(plugin), encoding="utf-8")
    monkeypatch.setattr(installer, "HOOKS", source)
    project = tmp_path / "project"
    project.mkdir()
    (project / "agents.md").write_text(
        "## Project settings\n- Autonomy: away\n- Brief requirements: reviewer: Inspect evidence\n- Read bound: on\n",
        encoding="utf-8")
    setup = installer.Installer(installer.parser().parse_args(
        ["--home", str(tmp_path / "home"), "--project", str(project), "--host", "claude-code"]))
    monkeypatch.setattr(setup, "plugin_active", lambda host: plugin_active)
    template = setup.hook_template("claude-code", setup.claude_template("portable-root"))
    manual = [name for entry in template["PreToolUse"] for name in entry["matcher"].split("|")]
    covered = {"Bash", "PowerShell", "Edit", "Write", "NotebookEdit", "AskUserQuestion", "Read"}
    assert set(manual) == {"Agent", "Glob", "Grep"} | (set() if plugin_active else covered)
    assert len(manual) == len(set(manual))


def test_plugin_subtraction_tracks_retained_tools_per_event(tmp_path, monkeypatch):
    setup = installer.Installer(installer.parser().parse_args(["--home", str(tmp_path), "--host", "claude-code"]))
    monkeypatch.setattr(setup, "plugin_active", lambda host: True)
    template = setup.claude_template("portable-root")
    general = next(entry for entry in template["PreToolUse"] if entry["matcher"] == "Bash|PowerShell")
    template["PreToolUse"] += [{**general, "matcher": "AskUserQuestion|Read"},
                               {**general, "matcher": "Read|Agent|Agent|AskUserQuestion"}]
    template["PostToolUse"].append({**template["PostToolUse"][0], "matcher": "NotebookEdit|Read"})
    supplemental = setup.hook_template("claude-code", template)
    assert {event: [name for entry in entries for name in entry["matcher"].split("|")]
            for event, entries in supplemental.items()} == {
                "PreToolUse": ["AskUserQuestion", "Read", "Agent"], "PostToolUse": ["Read"]}
