"""Wrapper quiet paths and token/session boundaries use deterministic local fixtures."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from conftest import ROOT, set_slot, unified_project
import ro
import ro_checks as checks
from ro_state import process_start


def wrapper_command(wrapper):
    if wrapper.endswith(".cmd"):
        if os.name != "nt":
            pytest.skip("cmd.exe wrapper requires Windows")
        return [os.environ["COMSPEC"], "/d", "/c", str(ROOT / "hooks" / wrapper)]
    shell = shutil.which("sh")
    assert shell, "A POSIX shell is required to test the POSIX wrapper"
    return [shell, (ROOT / "hooks" / wrapper).as_posix()]


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("source", ["cwd", "CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR", "absent"])
def test_wrapper_finds_project_ancestors_before_starting_interpreter(tmp_path, wrapper, source):
    command = wrapper_command(wrapper)
    project = tmp_path / "project with spaces"
    nested = project / "one" / "two"
    nested.mkdir(parents=True)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    if source != "absent":
        (project / "agents.md").write_text("# Rules\n", encoding="utf-8")
    else:
        # A directory with the same name is not project configuration.
        (project / "agents.md").mkdir()
    stub = tmp_path / ("interpreter.cmd" if wrapper.endswith(".cmd") else "interpreter")
    if wrapper.endswith(".cmd"):
        stub.write_text('@echo off\necho interpreter-started\necho %CD%\n'
                        'set /p payload=\necho %payload%\nexit /b 0\n', encoding="utf-8")
    else:
        stub.write_text('#!/bin/sh\nprintf "interpreter-started\\n%s\\n" "$PWD"\n'
                        'IFS= read -r payload; printf "%s\\n" "$payload"\n', encoding="utf-8")
        stub.chmod(0o755)
    env = {key: value for key, value in os.environ.items()
           if key not in ("CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR", "RO_HOOK_PYTHON")}
    env.update(RO_HOOK_PYTHON=str(stub), PATH=str(tmp_path / "empty-path"))
    cwd = nested if source == "cwd" else unrelated
    if source not in ("cwd", "absent"):
        env[source] = str(nested)
    if source == "absent":
        env.update(CLAUDE_PROJECT_DIR=str(nested), CODEX_PROJECT_DIR=str(tmp_path / "missing"))
    result = subprocess.run([*command, "PreToolUse"], cwd=cwd, env=env,
                            input=b'{"payload":"unchanged"}\n', capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    if source == "absent":
        assert json.loads(result.stdout) == {}
    else:
        lines = result.stdout.decode().splitlines()
        assert lines[0] == "interpreter-started"
        # No directory change leaks to the runner, including shell-native Windows paths.
        assert lines[1].replace("\\", "/").endswith(cwd.name)
        assert lines[2] == '{"payload":"unchanged"}'


@pytest.mark.parametrize("command", [r"find . -exec rm {} \; &", "cmd ${X} &",
                                      "worker --label {first,second} &", "cmd ${X#prefix} &",
                                      "echo { &", "echo } &", "echo { ; worker &"])
def test_opaque_brace_operands_keep_outer_background_denial(tmp_path, command):
    values = {"environment": "linux/bash", "enforcement": "block", "block": "shell.background"}
    findings = checks.pre_checks(checks.Call("shell", "bash", command), tmp_path, [], values)
    detached = [finding for finding in findings if finding.check == "shell.background"]
    assert detached and all(checks.outcome(finding, values) == "block" for finding in detached)


@pytest.mark.parametrize("operand", ["${TARGET}", "bound/{input,output}.txt", "{}"])
def test_opaque_brace_path_warns_without_weakening_outer_operator(tmp_path, operand):
    values = {"environment": "linux/bash", "enforcement": "block",
              "block": "shell.background,jobs.mutate-bound"}
    jobs = [{"id": "J-A-0001", "status": "running", "pid": os.getpid(),
             "start": process_start(os.getpid()), "bound": [str(tmp_path / "bound")]}]
    findings = checks.pre_checks(checks.Call("shell", "bash", f"rm {operand} &"), tmp_path, jobs, values)
    targets = [finding for finding in findings if finding.check == "jobs.mutate-bound"]
    assert targets and all(finding.uncertain and checks.outcome(finding, values) == "warn" for finding in targets)
    assert any(finding.check == "shell.background" and checks.outcome(finding, values) == "block"
               for finding in findings)


@pytest.mark.parametrize("events", [("SessionStart", "SessionStart", "Stop", "Stop"),
                                    ("Stop", "Stop", "SessionStart", "SessionStart")])
def test_slot_reminder_is_shared_across_events_and_persists_per_session(tmp_path, capsys, events):
    root = unified_project(tmp_path)
    set_slot(root, "A", "released", user="none")  # Two eligible slots leave selection manual.

    def invoke(event, session):
        args = ro.hook_arguments(["--project", str(root), "hook", event])
        assert ro.hook_main(args, json.dumps({"cwd": str(root), "session_id": session}).encode()) == 0
        return json.loads(capsys.readouterr().out)

    responses = [invoke(event, "session-one") for event in events]
    assert "--slot" in str(responses[0])
    assert all("--slot" not in str(response) and "Slot not selected" not in str(response)
               for response in responses[1:])
    assert all("Slot A:" not in str(response) and "Slot B:" not in str(response) for response in responses)
    assert "--slot" in str(invoke(events[0], "session-two"))

    # Persisted identities contain only hashes, not host identifiers or reminder prose.
    seen = list((root / ".ro" / "warnings-seen").glob("*.json"))
    assert len(seen) == 2
    assert all("session-one" not in path.read_text(encoding="utf-8") for path in seen)
