"""Platform defaults and plugin startup guidance stay useful outside a checkout."""

import json
import os
import re
import shutil
import subprocess

import pytest

from conftest import SKILL, check, item, make_project, rs, run_init, set_queue
import ro_command
import ro_hooks
from ro_records import brief
from ro_state import Project


@pytest.mark.parametrize("identity,patterns", [
    ("kaggle/task-a", "kaggle competitions submit; kaggle kernels push"),
    ("KAGGLE/task-b", "kaggle competitions submit; kaggle kernels push"),
    ("hub/task-a", "none"), ("contest-lab/task-b", "none"), ("off", "none"),
])
def test_competition_default_uses_the_declared_platform(identity, patterns):
    values = rs.resolve({"profile": "competition", "competition": identity}, None, {}, new_project=True)
    assert values["external_actions"] == patterns
    assert values["_external_actions_source"] == "default"
    other_profile = rs.resolve({"profile": "work", "competition": identity}, None, {}, new_project=True)
    assert other_profile["external_actions"] == "none"


def test_platform_defaults_are_read_from_the_adapter_mapping(tmp_path, monkeypatch):
    adapters = tmp_path / "references/adapters"
    adapters.mkdir(parents=True)
    (adapters / "external-actions.json").write_text(json.dumps({"contest-lab": ["contest-tool submit"]}),
                                                   encoding="utf-8")
    monkeypatch.setattr(rs, "SKILL_ROOT", tmp_path)
    values = rs.resolve({"profile": "competition", "competition": "contest-lab/task-a"}, None, {})
    assert values["external_actions"] == "contest-tool submit"


@pytest.mark.parametrize("explicit", [None, "none", "release-tool publish"])
def test_platform_change_refreshes_only_inherited_defaults(tmp_path, explicit):
    flags = ["--external-actions", explicit] if explicit is not None else []
    target = make_project(tmp_path, "platform-change", "--preset", "competition-team",
                          "--competition", "kaggle/task-a", "--phase-clock", "off", *flags)
    result = run_init(target, "--reconfigure", "--competition", "contest-lab/task-b")
    assert result.returncode == 0, result.stderr
    values = rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values
    assert values["external_actions"] == (explicit if explicit is not None else "none")
    assert ("external gate inactive" in result.stdout) == (explicit in (None, "none"))
    result = run_init(target, "--reconfigure", "--competition", "kaggle/task-c")
    assert result.returncode == 0, result.stderr
    values = rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values
    assert values["external_actions"] == (explicit if explicit is not None else
                                           "kaggle competitions submit; kaggle kernels push")


@pytest.mark.parametrize("shell", ["sh", "powershell"])
@pytest.mark.parametrize("route", ["brief", "SessionStart", "unselected-SessionStart"])
def test_missing_shim_uses_resolved_plugin_root_for_each_startup_route(tmp_path, monkeypatch, shell, route):
    plugin = tmp_path / "plugin's $cache `entry"
    module = plugin / "skills/research-orchestrator/scripts/ro_command.py"
    module.parent.mkdir(parents=True)
    installer = plugin / "install.py"
    installer.write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(ro_command, "__file__", str(module))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "unrelated-root"))
    environment = "windows/powershell" if shell == "powershell" else "linux/bash"
    target = make_project(tmp_path, "startup", "--preset", "quick", "--environment", environment,
                          "--agents", "A,B")
    project = Project(target, slot="A", session="startup-test") if route != "unselected-SessionStart" else Project(
        target, session="unselected-session", require_slot=False)
    if route == "brief":
        result = brief(project)
    else:
        result = json.dumps(ro_hooks.hook(project, "SessionStart", {}))
        result = json.loads(result)["hookSpecificOutput"]["additionalContext"]
    expected = ro_command.command_prefix(installer, shell) + " --shim-only"
    assert expected in result
    assert "unrelated-root" not in result and "from the plugin checkout" not in result
    assert re.search(r"shim.{0,60}PATH", result, re.I)


@pytest.mark.parametrize("shell", ["sh", "powershell"])
def test_printed_shim_command_preserves_special_paths_from_another_directory(tmp_path, monkeypatch, shell):
    executable = shutil.which("sh") if shell == "sh" else (shutil.which("powershell") or shutil.which("pwsh"))
    if not executable:
        pytest.skip("shell is not installed")
    plugin = tmp_path / "plugin's $cache `entry"
    module = plugin / "skills/research-orchestrator/scripts/ro_command.py"
    module.parent.mkdir(parents=True)
    (plugin / "install.py").write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
    monkeypatch.setattr(ro_command, "__file__", str(module))
    command = ro_command.shim_install_command(shell)
    args = [executable, "-c", command] if shell == "sh" else [
        executable, "-NoProfile", "-NonInteractive", "-Command", command]
    result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, timeout=15,
                            env={**os.environ, "cache": "wrong", "PYTHONIOENCODING": "utf-8"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["--shim-only"]


def test_standalone_skill_does_not_print_a_nonexistent_plugin_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(ro_command, "__file__", str(tmp_path / ".claude/skills/research-orchestrator/scripts/ro_command.py"))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    target = make_project(tmp_path, "standalone", "--preset", "quick")
    result = brief(Project(target, slot="A", session="standalone-test"))
    assert re.search(r"(?:rerun|run again).{0,30}installer", result, re.I)
    assert "--shim-only" not in result


def test_non_compute_exclusive_resources_have_supported_plan_fields(tmp_path):
    target = make_project(tmp_path, "resource", "--preset", "quick", "--workflow", "unified")
    set_queue(target, item("H-A-01").replace("- Parallel: YES", "- Parallel: NO").replace(
        "- Other: NONE", "- Other: shared-database"))
    assert not [issue for issue in check(target).issues if issue.severity == "ERROR"]
    guide = (SKILL / "references/compute.md").read_text(encoding="utf-8")
    assert re.search(r"exclusive resources.{0,40}`Other`", guide, re.I)
    assert re.search(r"shared lock|scheduler reservation", guide)
    assert re.search(r"not.{0,20}`Other`", guide)
