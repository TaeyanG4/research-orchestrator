"""Dialect, lifecycle, relocation and interpreter-free record-cache regressions."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from conftest import ROOT
import ro_checks as checks
import ro_hooks as hooks
from ro_state import Project
from test_hook_root_termination import wrapper_command, wrapper_environment, invoke
from test_install import installer


@pytest.mark.parametrize("environment,dialect,command", [
    ("windows/bash", "powershell", "Remove-Item runs/job-a/input.txt"),
    ("windows/powershell", "bash", "rm runs/job-a/input.txt"),
    ("linux/bash", "powershell", "Remove-Item runs/job-a/input.txt"),
    ("macos/powershell", "bash", "rm runs/job-a/input.txt"),
])
def test_tool_dialect_preserves_bound_path_denial(tmp_path, environment, dialect, command):
    values = {"environment": environment, "enforcement": "block", "block": "jobs.mutate-bound"}
    # Lexical path semantics are selected by the fixture, never the test host.
    root = "Q:/fixture" if environment.startswith("windows/") else "/fixture"
    jobs = [{"status": "running", "bound": [root + "/runs/job-a/input.txt"]}]
    findings = checks.pre_checks(checks.Call("shell", dialect, command), root, jobs, values)
    assert any(f.check == "jobs.mutate-bound" and checks.outcome(f, values) == "block" for f in findings)
    uncertain = checks.command_parts(checks.Call("shell", "other", command), values)
    assert uncertain.uncertain


def prepare_cache(root):
    for name in hooks.FILES:
        text = ("# Rules\n\n## Project settings\n- Enforcement: warn\n- Environment: windows/bash\n"
                if name == "agents.md" else "# Record\n")
        (root / name).write_text(text, encoding="utf-8")
        os.utime(root / name, (1700000000, 1700000000))
    project = Project(root, slot="A", session="cache-test")
    hooks._snapshot(project)
    # Fixed, distinct minutes exercise cmd's conservative timestamp comparison.
    os.utime(project.state / "records-hook.json", (1700000060, 1700000060))
    hooks._wrapper_snapshot(project)
    os.utime(project.state / "records-hook.ready", (1700000300, 1700000300))
    return project


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("change", ["none", *hooks.FILES, "same-time-size", "remove", "add", "warning", "cache", "malformed", "diagnostics"])
def test_post_wrapper_cache_preserves_changes_and_input(tmp_path, wrapper, change):
    command = wrapper_command(wrapper)
    environment = wrapper_environment(tmp_path, wrapper)
    project = prepare_cache(tmp_path)
    if change in hooks.FILES:
        path = tmp_path / change
        path.write_text("# Changed\n", encoding="utf-8")
        os.utime(path, (1700000600, 1700000600))
    elif change == "same-time-size":
        path = tmp_path / "plan.md"
        path.write_text("# Changed size\n", encoding="utf-8")
        os.utime(path, (1700000000, 1700000000))
    elif change == "remove":
        (tmp_path / "handoff.md").unlink()
    elif change == "add":
        (tmp_path / "handoff.md").unlink()
        hooks._snapshot(project)
        hooks._wrapper_snapshot(project)
        (tmp_path / "handoff.md").write_text("# New\n", encoding="utf-8")
    elif change == "warning":
        (project.state / "warnings.log").write_text("pending warning\n", encoding="utf-8")
    elif change == "cache":
        (project.state / "records-hook.json").write_text("invalid\n", encoding="utf-8")
    elif change == "malformed":
        (project.state / "records-hook.ready").write_text("invalid\n", encoding="utf-8")
    elif change == "diagnostics":
        environment["RO_HOOK_DIAGNOSTICS"] = "1"
    result = invoke([*command, "PostToolUse", "--general"], tmp_path, environment)
    assert result.returncode == 0, result.stderr
    if change == "none":
        assert json.loads(result.stdout) == {}
        assert not Path(environment["RO_TEST_SENTINEL"]).exists()
    else:
        assert Path(environment["RO_TEST_SENTINEL"]).read_text().splitlines() == ["started"]
        assert result.stdout.decode().splitlines()[-1] == '{"payload":"unchanged"}'


def test_pending_warning_cannot_publish_clean_cache(tmp_path):
    project = prepare_cache(tmp_path)
    (project.state / "warnings.log").write_text("pending warning\n", encoding="utf-8")
    hooks._wrapper_snapshot(project)
    assert not (project.state / "records-hook.ready").exists()


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_post_cache_counts_utf8_crlf_and_unterminated_lines_without_path_tools(tmp_path, wrapper):
    command = wrapper_command(wrapper)
    environment = wrapper_environment(tmp_path, wrapper)
    project = prepare_cache(tmp_path)
    plan = tmp_path / "plan.md"
    plan.write_bytes("# Caf\u00e9\r\n\r\nUnterminated \u03bb".encode("utf-8"))
    os.utime(plan, (1700000000, 1700000000))
    hooks._snapshot(project)
    os.utime(project.state / "records-hook.json", (1700000060, 1700000060))
    hooks._wrapper_snapshot(project)
    os.utime(project.state / "records-hook.ready", (1700000300, 1700000300))
    assert (project.state / "records-hook-stamps/plan.md").read_bytes() == str(plan.stat().st_size).encode() + b"\n"
    result = invoke([*command, "PostToolUse"], tmp_path, environment)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {}
    assert not Path(environment["RO_TEST_SENTINEL"]).exists()


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_post_cache_keeps_project_path_characters_literal(tmp_path, wrapper):
    command = wrapper_command(wrapper)
    environment = wrapper_environment(tmp_path, wrapper)
    environment["RO_CACHE_NAME"] = "wrong-project"
    project = tmp_path / "cache %RO_CACHE_NAME% & $literal"
    project.mkdir()
    prepare_cache(project)
    result = invoke([*command, "PostToolUse"], project, environment)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {}
    assert not Path(environment["RO_TEST_SENTINEL"]).exists()


def test_post_hook_acknowledges_warning_then_publishes_witnesses(tmp_path):
    project = prepare_cache(tmp_path)
    hooks.warning(project, "Review the pending record")
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo ready"}, "cwd": str(tmp_path)}
    result = hooks.hook(project, "PostToolUse", payload)
    assert "Review the pending record" in str(result)
    assert (project.state / "records-hook.ready").read_text() == "records-hook-v1\n"
    assert (project.state / "records-hook-stamps/warnings.log").exists()


@pytest.mark.skipif(os.name != "nt", reason="cmd timestamp precision")
def test_cmd_same_minute_cache_conservatively_runs_python(tmp_path):
    environment = wrapper_environment(tmp_path, "ro-hook.cmd")
    project = prepare_cache(tmp_path)
    os.utime(project.state / "records-hook.ready", (1700000000, 1700000000))
    result = invoke([*wrapper_command("ro-hook.cmd"), "PostToolUse"], tmp_path, environment)
    assert result.returncode == 0
    assert Path(environment["RO_TEST_SENTINEL"]).exists()


@pytest.mark.parametrize("filename", ["hooks.json", "codex-hooks.sample.json"])
def test_clear_is_a_registered_start_event(filename):
    template = json.loads((ROOT / "hooks" / filename).read_text(encoding="utf-8"))
    assert "clear" in template["hooks"]["SessionStart"][0]["matcher"].split("|")


@pytest.mark.parametrize("dialect", ["sh", "powershell"])
def test_missing_codex_registration_prints_literal_reinstall_command(tmp_path, dialect):
    shell = shutil.which(dialect if dialect == "sh" else "pwsh") or (shutil.which("powershell") if dialect != "sh" else None)
    if not shell:
        pytest.skip("Requested shell is unavailable")
    project = tmp_path / "moved project"
    project.mkdir()
    setup = installer.Installer(installer.parser().parse_args(["--project", str(project), "--home", str(tmp_path / "home")]))
    skill = tmp_path / "old-$team-'quoted" / ".codex/skills/research-orchestrator"
    template = setup.codex_template(skill)
    field = "command" if dialect == "sh" else "commandWindows"
    command = template["SessionStart"][0]["hooks"][0][field]
    argv = [shell, "-c", command] if dialect == "sh" else [shell, "-NoProfile", "-NonInteractive", "-Command", command]
    result = subprocess.run(argv, cwd=project, input="{}", text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    expected = "python " + installer.literal(installer.posix(ROOT / "install.py"), dialect) + " --project . --host codex"
    assert context.endswith(expected)
    assert "registered installation is missing" in context
