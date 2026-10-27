"""Deterministic hook shortcuts, timestamp boundaries and publish-gate disclosure."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from conftest import NOW, make_project
import check_project
import ro_command
import ro_hook_runner as runner
import ro_hooks as hooks
import ro_records as records
from ro_state import Project
from ro_time import FUTURE_TOLERANCE
from test_hook_root_termination import invoke, wrapper_command, wrapper_environment


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 25, 12)
    monkeypatch.setattr(dt, "datetime", Clock)


def project_at(root):
    (root / "agents.md").write_text(
        "# Rules\n## Project settings\n- Enforcement: warn\n- Environment: linux/bash\n", encoding="utf-8")
    return Project(root, slot="A", session="regression")


def test_warning_delivery_resumes_shortcut_and_rechecks_changed_bytes(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    hooks._snapshot(project, report=False)
    hooks.warning(project, "first warning")
    assert not runner.quiet("PostToolUse", {}, tmp_path)
    response = hooks.hook(project, "PostToolUse", {"tool_name": "Edit"})
    assert "first warning" in str(response)
    assert runner.quiet("PostToolUse", {}, tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("acknowledged log launched Python"))
    assert runner.run("PostToolUse", b'{"tool_name":"Edit"}', project) == ({}, 0)
    path = project.state / "warnings.log"
    stamp = path.stat()
    path.write_text(path.read_text(encoding="utf-8").replace("first", "other"), encoding="utf-8")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert not runner.quiet("PostToolUse", {}, tmp_path)


@pytest.mark.parametrize("shown", [None, "invalid", "[]", '{}', '{"sha256":"stale"}'])
def test_missing_or_invalid_warning_acknowledgment_keeps_delivery(tmp_path, shown):
    project = project_at(tmp_path)
    hooks._snapshot(project, report=False)
    (project.state / "warnings.log").write_text("pending\n", encoding="utf-8")
    if shown is not None:
        (project.state / "warnings-shown.json").write_text(shown, encoding="utf-8")
    assert not runner.quiet("PostToolUse", {}, tmp_path)


@pytest.mark.parametrize("seconds,expected", [(120, False), (180, False), (300, False), (360, True)])
def test_checker_and_notebook_hook_share_clock_skew_boundary(tmp_path, seconds, expected):
    project = project_at(tmp_path)
    moment = (NOW + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M")
    (tmp_path / "discoveries.md").write_text(f"## D-A-001 record\n- Date: {moment}\n", encoding="utf-8")
    assert check_project.FUTURE_TOLERANCE is hooks.FUTURE_TOLERANCE is FUTURE_TOLERANCE
    checker = check_project.Checker(tmp_path, now=NOW)
    checker.check_time(moment, "discoveries.md", "D-A-001", "Date")
    assert bool(checker.issues) is expected
    response = hooks.hook(project, "PostToolUse", {"tool_name": "NotebookEdit"})
    assert ("records.timestamp" in str(response)) is expected


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("registry", [None, "jobs.json", "recovery/jobs.json"])
@pytest.mark.parametrize("hint", [False, True])
def test_edit_wrapper_skips_only_absent_primary_and_recovery(tmp_path, wrapper, registry, hint):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    project = tmp_path / "project with spaces"
    nested = project / "child"
    nested.mkdir(parents=True)
    (project / "agents.md").write_text("# Rules\n", encoding="utf-8")
    if registry:
        path = project / ".ro" / registry
        path.parent.mkdir(parents=True)
        path.write_text("invalid registry still needs checking", encoding="utf-8")
    if hint:
        env["CLAUDE_PROJECT_DIR"] = str(nested)
    result = invoke([*command, "PreToolUse", "--tool", "edit"], tmp_path if hint else nested, env)
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert Path(env["RO_TEST_SENTINEL"]).exists() is bool(registry)
    if not registry:
        assert json.loads(result.stdout) == {}
    else:
        assert result.stdout.decode().splitlines()[-1] == '{"payload":"unchanged"}'


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_edit_wrapper_does_not_wait_for_stdin_without_jobs(tmp_path, wrapper):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    (tmp_path / "agents.md").write_text("# Rules\n", encoding="utf-8")
    process = subprocess.Popen([*command, "PreToolUse", "--tool", "edit"], cwd=tmp_path, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert process.wait(timeout=3) == 0  # The input pipe is still open and has no bytes.
        assert json.loads(process.stdout.read()) == {}
        assert not Path(env["RO_TEST_SENTINEL"]).exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


@pytest.mark.parametrize("lookup", ["basename", "path"])
def test_posix_wrapper_resolves_runner_without_slash_in_invocation(tmp_path, lookup):
    shell, original = wrapper_command("ro-hook.sh")
    env = wrapper_environment(tmp_path, "ro-hook.sh")
    directory = tmp_path / "installed with spaces" / "hooks"
    directory.mkdir(parents=True)
    wrapper = directory / "ro-hook.sh"
    wrapper.write_bytes(Path(original).read_bytes())
    wrapper.chmod(0o755)
    scripts = directory.parent / "scripts"
    scripts.mkdir()
    (scripts / "ro_hook_runner.py").write_text("# installed runner\n", encoding="utf-8")
    (directory.parent / "agents.md").write_text("# Rules\n", encoding="utf-8")
    env["RO_TEST_RUNNER"] = (scripts / "ro_hook_runner.py").as_posix()
    Path(env["RO_HOOK_PYTHON"]).write_text(
        '#!/bin/sh\nif [ "$3" -ef "$RO_TEST_RUNNER" ]; then printf "matched\\n"; '
        'else printf "%s\\n" "$3"; fi\n', encoding="utf-8")
    command = ([shell, wrapper.name, "PreToolUse"] if lookup == "basename" else
               [shell, "-c", 'ro_test_hooks=$PWD; cd ..; PATH="$ro_test_hooks:$PATH"; '
                'export PATH; ro-hook.sh PreToolUse'])
    result = invoke(command, directory, env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().strip() == "matched"


@pytest.mark.parametrize("route", ["brief", "SessionStart", "unselected-SessionStart", "unselected-brief"])
@pytest.mark.parametrize("registration", ["absent", "other", "this"])
@pytest.mark.parametrize("custom", [False, True])
def test_publish_gate_notice_matches_checkout_scope(tmp_path, monkeypatch, route, registration, custom):
    target = make_project(tmp_path, "publish", "--preset", "quick", "--agents", "A,B",
                          "--environment", "linux/bash")
    # A file covers linked worktrees as well as a directory for ordinary repositories.
    (target / ".git").write_text("gitdir: ../linked-metadata\n", encoding="utf-8")
    hooks_path = tmp_path / "shared hooks" if custom else target / ".git-hooks"
    if registration != "absent":
        scope = target if registration == "this" else tmp_path / "another checkout"
        digest = hashlib.sha256(os.path.normcase(str(scope.resolve())).encode()).hexdigest()
        path = hooks_path / "research-orchestrator/registrations" / (digest + ".json")
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
    calls = []
    def git(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 1
        return SimpleNamespace(stdout=str(hooks_path) if custom else ".git-hooks\n")
    monkeypatch.setattr(subprocess, "run", git)
    monkeypatch.setattr(records.shutil, "which", lambda name: "ro")
    monkeypatch.setattr(records, "_checker_brief", lambda p: ({"ERROR": 0, "WARN": 0, "INFO": 0}, 0, {}))
    selected = not route.startswith("unselected")
    project = Project(target, slot="A" if selected else None, session="notice-test", require_slot=False)
    result = records.brief(project) if route.endswith("brief") else str(hooks.hook(project, "SessionStart", {}))
    assert ("publish gate not installed" in result) is (registration != "this")
    if registration != "this":
        assert "install.py" in result and "--project ." in result
    assert calls == [["git", "-C", str(target), "rev-parse", "--git-path", "hooks"]]


def test_non_git_project_needs_no_gate_query(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("non-Git project queried Git"))
    assert records.publish_gate_guidance(Project(tmp_path, slot="A"), "sh") == []


@pytest.mark.parametrize("failure", [FileNotFoundError(), subprocess.TimeoutExpired("git", 1)])
def test_unavailable_git_and_standalone_runtime_keep_actionable_notice(tmp_path, monkeypatch, failure):
    (tmp_path / ".git").mkdir()
    def fail(*a, **kw):
        raise failure
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(ro_command, "__file__", str(tmp_path / "standalone/scripts/ro_command.py"))
    assert records.publish_gate_guidance(Project(tmp_path, slot="A"), "sh") == [
        "publish gate not installed — python <checkout>/install.py --project ."]
