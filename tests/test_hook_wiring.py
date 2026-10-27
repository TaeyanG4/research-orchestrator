"""Shipped hook declarations use supervised installed code and bounded host timeouts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT


@pytest.mark.parametrize("name", ["hooks.json", "codex-hooks.sample.json"])
def test_hook_samples_have_all_events_and_ten_second_timeouts(name):
    document = json.loads((ROOT / "hooks" / name).read_text(encoding="utf-8"))
    assert set(document) == {"hooks"}
    data = document["hooks"]
    assert set(data) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
    assert data["SessionStart"][0]["matcher"] == "startup|resume|clear|compact"
    for event, declarations in data.items():
        assert isinstance(declarations, list) and declarations
        for declaration in declarations:
            assert set(declaration) == ({"hooks"} if event == "Stop" and name == "hooks.json"
                                        else {"matcher", "hooks"})
            if "matcher" in declaration:
                assert isinstance(declaration["matcher"], str) and declaration["matcher"]
            assert isinstance(declaration["hooks"], list) and declaration["hooks"]
            for hook in declaration["hooks"]:
                fields = {"type", "command", "timeout"}
                if name == "codex-hooks.sample.json":
                    fields.add("commandWindows")
                assert set(hook) == fields
                assert hook["type"] == "command"
                assert hook["timeout"] == 10
                assert isinstance(hook["command"], str)
                root = "${CLAUDE_PLUGIN_ROOT}" if name == "hooks.json" else "/absolute/path/to/plugin"
                prefix = f'sh "{root}/hooks/ro-hook.sh" {event}'
                suffix = hook["command"].removeprefix(prefix)
                assert hook["command"].startswith(prefix)
                expected = " --tool edit" if declaration.get("matcher") == "Edit|Write|NotebookEdit" else ""
                assert suffix == (expected if event == "PreToolUse" else " --general")
                if name == "codex-hooks.sample.json":
                    assert isinstance(hook["commandWindows"], str)
                    assert hook["commandWindows"] == f'& "{root}/hooks/ro-hook.cmd" {event}{suffix}'


def test_codex_hooks_use_host_tool_and_lifecycle_matchers():
    document = json.loads((ROOT / "hooks" / "codex-hooks.sample.json").read_text(encoding="utf-8"))
    expected = {"SessionStart": "startup|resume|clear|compact", "PreToolUse": "Bash|apply_patch",
                "PostToolUse": "Bash|apply_patch", "Stop": "*"}
    for event, matcher in expected.items():
        declarations = document["hooks"][event]
        assert len(declarations) == 1
        assert declarations[0]["matcher"] == matcher
        assert len(declarations[0]["hooks"]) == 1


def test_claude_hooks_use_fixed_plugin_root_and_required_tool_matchers():
    text = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
    data = json.loads(text)["hooks"]
    tools = {tool for entry in data["PreToolUse"] for tool in entry["matcher"].split("|")}
    assert tools == {"Bash", "PowerShell", "Edit", "Write", "NotebookEdit"}
    assert len(data["PreToolUse"]) == 2
    assert data["PostToolUse"][0]["matcher"] == "Edit|Write|NotebookEdit|Bash|PowerShell"
    assert all(re.fullmatch(r"[A-Za-z]+(?:\|[A-Za-z]+)*", entry["matcher"])
               for event in ("SessionStart", "PreToolUse", "PostToolUse") for entry in data[event])
    assert "onFailure" not in text
    for declarations in data.values():
        for declaration in declarations:
            for hook in declaration["hooks"]:
                assert '${CLAUDE_PLUGIN_ROOT}/hooks/ro-hook.sh' in hook["command"]


@pytest.mark.parametrize("name,tool", [("hooks.json", "Bash"), ("hooks.json", "PowerShell"),
                                      ("hooks.json", "Edit"), ("hooks.json", "Write"),
                                      ("hooks.json", "NotebookEdit"),
                                      ("codex-hooks.sample.json", "Bash"),
                                      ("codex-hooks.sample.json", "apply_patch")])
def test_shell_call_has_one_pre_and_one_post_runner(name, tool):
    data = json.loads((ROOT / "hooks" / name).read_text(encoding="utf-8"))["hooks"]
    counts = [sum(len(entry["hooks"]) for entry in data[event] if re.fullmatch(entry["matcher"], tool))
              for event in ("PreToolUse", "PostToolUse")]
    assert counts == [1, 1]  # One installed runner per event; the watchdog path needs no child.


def test_pre_push_sample_preserves_exact_stdin_and_uses_authoritative_command():
    text = (ROOT / "hooks" / "pre-push.sample").read_text(encoding="utf-8")
    command = next(line for line in text.splitlines() if line.startswith("exec "))
    assert command.endswith('ro.py" hook pre-push --remote "$1"')
    assert "|" not in command and "<" not in command
    assert "/absolute/path/to/plugin/" in command


def test_pre_push_script_itself_refuses_a_missing_interpreter(tmp_path):
    shell = shutil.which("sh")
    if not shell:
        git = shutil.which("git")
        from pathlib import Path
        shell = str(Path(git).parent.parent / "bin" / "sh.exe") if git else None
    assert shell, "A Git-compatible shell is required for the pre-push sample"
    script = (ROOT / "hooks" / "pre-push.sample").read_text(encoding="utf-8")
    script = script.replace("exec python ", "exec ro-definitely-absent-interpreter ")
    result = subprocess.run([shell, "-c", script], cwd=tmp_path, input=b"", capture_output=True)
    assert result.returncode != 0


@pytest.mark.parametrize("available,selected", [(["python3", "python", "py"], "python3"),
                                               (["python"], "python"), (["py"], "py"), ([], None)])
def test_posix_hook_wrapper_selects_interpreter_and_preserves_input(tmp_path, available, selected):
    (tmp_path / "agents.md").write_text("# Rules\n", encoding="utf-8")
    shell = shutil.which("sh")
    assert shell, "A POSIX shell is required for the installed hook wrapper"
    for name in available:
        stub = tmp_path / name
        stub.write_text('#!/bin/sh\nif [ "$1" = "-3" ]; then printf "%s\\n" "$0"; exit 0; fi\n'
                        'printf "%s\\n" "' + name + '" "$@"\n'
                        'while IFS= read -r line; do printf "%s\\n" "$line"; done\n'
                        'printf "%s\\n" "$RO_HOOK_PYTHON"\n', encoding="utf-8")
        stub.chmod(0o755)
    # PWD yields a shell-native absolute PATH, including under Git Bash on Windows.
    command = 'PATH="$PWD"; export PATH; . "$1" PreToolUse'
    payload = b'{"cwd":"a path with spaces","tool_input":{"command":"echo ready"}}\n'
    env = {key: value for key, value in os.environ.items() if key != "RO_HOOK_PYTHON"}
    result = subprocess.run([shell, "-c", command, (ROOT / "hooks" / "ro-hook.sh").as_posix(),
                             (ROOT / "hooks" / "ro-hook.sh").as_posix()], cwd=tmp_path,
                            input=payload, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr
    if selected:
        lines = result.stdout.decode().splitlines()
        assert lines[0] == selected, result.stderr
        offset = 1
        assert lines[offset:offset + 2] == ["-E", "-S"]
        assert Path(lines[offset + 2]).resolve() == ROOT / "skills/research-orchestrator/scripts/ro_hook_runner.py"
        assert lines[offset + 3] == "PreToolUse"
        assert lines[offset + 4] == payload.decode().strip()
        assert lines[offset + 5].replace("\\", "/").endswith("/" + selected)
    else:
        assert json.loads(result.stdout) == {}
        assert b"missing Python 3 interpreter" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows command wrapper")
@pytest.mark.parametrize("available,selected", [(["python3", "python", "py"], "python3"),
                                               (["python"], "python"), (["py"], "py"), ([], None)])
def test_windows_hook_wrapper_selects_interpreter_and_preserves_input(tmp_path, available, selected):
    (tmp_path / "agents.md").write_text("# Rules\n", encoding="utf-8")
    for name in available:
        (tmp_path / (name + ".cmd")).write_text('@echo off\nif "%1"=="-3" goto resolve\necho ' + name + "\necho %*\n"
                                               "set /p hook_payload=\necho %hook_payload%\necho %RO_HOOK_PYTHON%\nexit /b 0\n"
                                               ":resolve\necho %~f0\nexit /b 0\n",
                                               encoding="utf-8")
    env = {**os.environ, "PATH": str(tmp_path) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")}
    env.pop("RO_HOOK_PYTHON", None)
    result = subprocess.run([os.environ["COMSPEC"], "/d", "/c", str(ROOT / "hooks" / "ro-hook.cmd"),
                             "PostToolUse", "--general"], cwd=tmp_path, env=env,
                            input=b'{"tool_name":"Bash"}\n', capture_output=True)
    assert result.returncode == 0, result.stderr
    if selected:
        lines = result.stdout.decode().splitlines()
        assert lines[0] == selected, result.stderr
        assert lines[1].startswith("-E -S ")
        assert 'ro_hook_runner.py" PostToolUse --general' in lines[1]
        assert lines[2] == '{"tool_name":"Bash"}'
        assert Path(lines[3]) == tmp_path / (selected + ".cmd")
    else:
        assert json.loads(result.stdout) == {}
        assert b"missing Python 3 interpreter" in result.stderr


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_default_wrapper_dispatches_in_process_with_resolved_python(tmp_path, wrapper):
    if wrapper.endswith(".cmd") and os.name != "nt":
        pytest.skip("Windows command wrapper")
    installed = tmp_path / "installed"
    (installed / "hooks").mkdir(parents=True)
    scripts = installed / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "hooks" / wrapper, installed / "hooks" / wrapper)
    shutil.copyfile(ROOT / "skills/research-orchestrator/scripts/ro_hook_runner.py", scripts / "ro_hook_runner.py")
    (scripts / "ro.py").write_text(
        "import json, os, sys\n"
        "def hook_main(args, raw):\n"
        "    print(json.dumps({'in_process': True, 'resolved': "
        "os.path.realpath(os.environ['RO_HOOK_PYTHON']) == os.path.realpath(sys.executable)}))\n"
        "    return 0\n"
        "if __name__ == '__main__': print(json.dumps({'in_process': False}))\n", encoding="utf-8")
    (tmp_path / "agents.md").write_text("## Project settings\n- Enforcement: block\n", encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if key != "RO_HOOK_PYTHON"}
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    path = installed / "hooks" / wrapper
    command = ([os.environ["COMSPEC"], "/d", "/c", str(path)] if wrapper.endswith(".cmd") else
               [shutil.which("sh"), path.as_posix()])
    result = subprocess.run([*command, "PreToolUse"], cwd=tmp_path, env=environment,
                            input=b'{"tool_name":"Bash"}', capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"in_process": True, "resolved": True}


def test_hook_capability_matrix_reflects_codex_exec_record():
    guide = (ROOT / "skills/research-orchestrator/references/hooks.md").read_text(encoding="utf-8")
    assert "hooks-capabilities.md" in guide
    capability = (ROOT / "skills/research-orchestrator/references/hooks-capabilities.md").read_text(encoding="utf-8")
    assert "docs/evals/README.md" in capability
    document = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
    evidence = ROOT / "docs/host-dry-runs/codex-2026-10-27.md"
    record = evidence.read_text(encoding="utf-8")
    assert "verified on 2026-10-27" in document and "Codex CLI 0.154.0" in document
    assert evidence.name in document
    assert "persisted `/hooks` trust route was not exercised" in document
    for value in ("Codex CLI 0.154.0", "gpt-6.1-sol", "windows/powershell"):
        assert value in record
    outcomes = {"background": ("denied", ["shell.background"]),
                "delete-bound": ("denied", ["jobs.mutate-bound"]),
                "benign": ("no hook decision", []),
                "read-bound": ("warned", ["jobs.read-bound"]),
                "unmonitored-stop": ("warned", ["jobs.unmonitored"]),
                "future-record": ("warned", ["records.timestamp"])}
    for case, (decision, checks) in outcomes.items():
        assert f"| {case} | {decision} | {decision} |" in record
        section = record.split(f"\n## {case}\n", 1)[1].split("\n## ", 1)[0]
        blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", section, re.S)]
        observations = blocks[0]
        event = {"unmonitored-stop": "Stop", "future-record": "PostToolUse"}.get(case, "PreToolUse")
        assert len(observations["hook_evidence"]) == 1
        observation = observations["hook_evidence"][0]
        assert {key: observation[key] for key in ('event', 'decision', 'checks')} == {
            'event': event, 'decision': decision, 'checks': checks}
        assert observation['source'].startswith('.ro/hook-diagnostics.jsonl:')
        assert observations["side_effects"]["bound_file_exists"] is True
        if decision == "denied":
            assert observations["tool_calls"] == []
        else:
            calls = observations["tool_calls"]
            assert len(calls) == 1 and calls[0]["status"] == "completed" and calls[0]["exit_code"] == 0
    assert not re.search(r"\b[A-Za-z]:[\\/]|/(?:Users|home)/[^/\s]+", record)
    for older in evidence.parent.glob("codex*.md"):
        if older != evidence:
            assert evidence.name in older.read_text(encoding="utf-8").splitlines()[0]
    matrix = capability.split("| Check |", 1)[1].split("\n\n", 1)[0]
    assert "Antigravity has no hook adapter" in document
    observed = {
        "shell.background": "Denial verified",
        "jobs.mutate-bound": "Denial verified",
        "jobs.read-bound": "Warning verified",
        "jobs.unmonitored": "Warning verified",
        "records.timestamp": "Warning verified",
    }
    for row in matrix.splitlines()[2:]:
        cells = [cell.strip() for cell in row.split("|")]
        check = cells[1].strip("`")
        if check in observed:
            assert cells[4] == observed[check]
        else:
            assert cells[4].startswith(("Unverified", "No declared"))
    assert "`--dangerously-bypass-hook-trust`" in document
    assert "The persisted `/hooks` trust route was not exercised" in document
    assert "rely on `ro` commands and Git pre-push" in document


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_portable_hook_wrapper_preserves_enforcement(tmp_path, wrapper):
    if wrapper.endswith(".cmd") and os.name != "nt":
        pytest.skip("Windows command wrapper")
    (tmp_path / "agents.md").write_text("# Agent rules\n\n## Project settings\n"
                                       "- Enforcement: block\n- Block: shell.background\n"
                                       f"- Environment: {'windows' if os.name == 'nt' else 'linux'}/bash\n",
                                       encoding="utf-8")
    path = ROOT / "hooks" / wrapper
    command = ([os.environ["COMSPEC"], "/d", "/c", str(path)] if wrapper.endswith(".cmd")
               else [shutil.which("sh"), path.as_posix()])
    env = {**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    payload = {"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "echo ready &"}}
    result = subprocess.run([*command, "PreToolUse"], cwd=tmp_path, env=env,
                            input=json.dumps(payload).encode(), capture_output=True)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "shell.background" in output["permissionDecisionReason"]


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("available", [True, False])
def test_wrapper_honors_configured_python_outside_path(tmp_path, wrapper, available):
    if wrapper.endswith(".cmd") and os.name != "nt":
        pytest.skip("Windows command wrapper")
    install = tmp_path / "plugin with spaces"
    shutil.copytree(ROOT / "hooks", install / "hooks")
    shutil.copytree(ROOT / "skills/research-orchestrator/scripts",
                    install / "skills/research-orchestrator/scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "skills/research-orchestrator/templates",
                    install / "skills/research-orchestrator/templates")
    project = tmp_path / "project"
    project.mkdir()
    (project / "agents.md").write_text("# Rules\n\n## Project settings\n"
                                       "- Enforcement: block\n- Block: shell.background\n"
                                       f"- Environment: {'windows' if os.name == 'nt' else 'linux'}/bash\n",
                                       encoding="utf-8")
    path = install / "hooks" / wrapper
    command = ([os.environ["COMSPEC"], "/d", "/c", str(path)] if wrapper.endswith(".cmd")
               else [shutil.which("sh"), path.as_posix()])
    env = {**os.environ, "PATH": str(tmp_path / "empty-path"),
           "CLAUDE_PROJECT_DIR": str(project),
           "RO_HOOK_PYTHON": sys.executable if available else str(tmp_path / "missing python")}
    payload = {"cwd": str(project), "tool_name": "Bash", "tool_input": {"command": "echo ready &"}}
    result = subprocess.run([*command, "PreToolUse"], cwd=tmp_path, env=env,
                            input=json.dumps(payload).encode(), capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    if available:
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "shell.background:" in output["hookSpecificOutput"]["permissionDecisionReason"]
        invalid = subprocess.run([*command, "invalid-event"], cwd=tmp_path, env=env,
                                 input=b"{}", capture_output=True, timeout=15)
        assert invalid.returncode == 2 and not invalid.stdout
    else:
        assert output == {}
        assert b"configured Python interpreter unavailable" in result.stderr
