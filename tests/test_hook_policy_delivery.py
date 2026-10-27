"""Real wrapper policy delivery and deterministic quiet-path boundaries."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

import ro_evidence
import ro_gate
import ro_hook_runner as runner
import ro_hooks as hooks
from ro_state import Project
from test_hook_cache_delivery import prepare_cache
from test_hook_root_termination import HINTS, wrapper_command, wrapper_environment


def configured(root):
    root.mkdir(exist_ok=True)
    environment = "windows/bash" if os.name == "nt" else "linux/bash"
    (root / "agents.md").write_text(
        "# Rules\n## Project settings\n- Enforcement: block\n"
        "- Block: shell.background, jobs.mutate-bound, ask.away, brief.requirements, publish.scan\n"
        f"- Environment: {environment}\n- Autonomy: away\n- Brief requirements: reviewer: Scope\n",
        encoding="utf-8")
    return Project(root, slot="A", session="delivery")


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("hint", HINTS)
def test_real_wrappers_apply_hint_policy_and_keep_command_directory(tmp_path, wrapper, hint):
    command = wrapper_command(wrapper)
    project = configured(tmp_path / "policy with spaces")
    nested = project.root / "nested"
    nested.mkdir()
    cwd = tmp_path / "command with spaces"
    bound, scratch = cwd / "protected", cwd / "scratch"
    bound.mkdir(parents=True)
    scratch.mkdir()
    project.write_json("jobs.json", [{"id": "J-A-0001", "status": "running", "bound": [str(bound)]}])
    env = {key: value for key, value in os.environ.items()
           if key not in (*HINTS, "PWD", "CDPATH", "ENV", "BASH_ENV", "RO_SLOT", "CODEX_THREAD_ID")}
    env.update(RO_HOOK_PYTHON=sys.executable, RO_SESSION="delivery", **{hint: str(nested)})
    scenarios = [("echo work &", {}, "shell.background", True),
                 ("rm input.txt", {"workdir": "protected"}, "jobs.mutate-bound", True),
                 ("rm input.txt", {"workdir": "scratch"}, None, True),
                 ("rm protected/input.txt", {}, "jobs.mutate-bound", True),
                 ("rm protected/input.txt", {}, "jobs.mutate-bound", False),
                 ("rm input.txt", {"workdir": "protected"}, "jobs.mutate-bound", False),
                 ("rm input.txt", {"workdir": "scratch"}, None, False)]
    for shell_command, extra, check, explicit_cwd in scenarios:
        payload = {"tool_name": "Bash", "tool_input": {"command": shell_command, **extra}}
        if explicit_cwd:
            payload["cwd"] = str(cwd)
        result = subprocess.run([*command, "PreToolUse"], cwd=cwd, env=env,
                                input=json.dumps(payload).encode(), capture_output=True, timeout=15)
        assert result.returncode == 0, result.stderr
        response = json.loads(result.stdout)
        specific = response.get("hookSpecificOutput", {})
        assert (specific.get("permissionDecision") == "deny") is bool(check), response
        if check:
            assert check in specific["permissionDecisionReason"]
        else:
            assert response == {}


@pytest.mark.parametrize("in_process", [False, True])
@pytest.mark.parametrize("explicit_cwd", [False, True])
def test_policy_root_survives_both_runner_dispatch_modes(tmp_path, in_process, explicit_cwd):
    project = configured(tmp_path / "policy")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    project.write_json("jobs.json", [{"id": "J-A-0001", "status": "running", "bound": [str(cwd / "input.txt")]}])
    payload = {"tool_name": "Bash", "tool_input": {"command": "rm input.txt"}}
    if explicit_cwd:
        payload["cwd"] = str(cwd)
    payload = json.dumps(payload).encode()
    result, code = runner.run("PreToolUse", payload, SimpleNamespace(root=str(cwd), slot="A", session="delivery"),
                              in_process=in_process, policy_root=str(project.root))
    assert code == 0
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "jobs.mutate-bound" in result["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("hint,tool,label,active,inactive", [
    ("CLAUDE_PROJECT_DIR", "ask", "Autonomy", "away", "present"),
    ("CODEX_PROJECT_DIR", "agent", "Brief requirements", "reviewer: Scope", "none"),
])
@pytest.mark.parametrize("value", ["absent", "inactive", "active", "ambiguous"])
def test_policy_shortcut_uses_no_interpreter_only_for_inactive_settings(
        tmp_path, wrapper, hint, tool, label, active, inactive, value):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    if wrapper.endswith(".sh"):
        grep = shutil.which("grep")
        assert grep, "POSIX wrapper policy shortcuts require grep"
        env["PATH"] = str(Path(grep).parent)
    project = tmp_path / "policy"
    project.mkdir()
    setting = {"absent": "", "inactive": f"- {label}: {inactive}\n",
               "active": f"- {label}: {active}\n",
               "ambiguous": f"- {label}: {inactive}\n- {label}: {active}\n"}[value]
    (project / "agents.md").write_text("## Project settings\n" + setting, encoding="utf-8")
    env[hint] = str(project)
    result = subprocess.run([*command, "PreToolUse", "--tool", tool], cwd=tmp_path, env=env,
                            input=b'{"payload":"unchanged"}\n', capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert Path(env["RO_TEST_SENTINEL"]).exists() is (value in {"active", "ambiguous"})
    if value in {"absent", "inactive"}:
        assert json.loads(result.stdout) == {}
    else:
        assert result.stdout.decode().splitlines()[-1] == '{"payload":"unchanged"}'


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
@pytest.mark.parametrize("tool", ["ask", "agent"])
def test_inactive_policy_wrapper_returns_with_open_stdin(tmp_path, wrapper, tool):
    command = wrapper_command(wrapper)
    env = wrapper_environment(tmp_path, wrapper)
    if wrapper.endswith(".sh"):
        env["PATH"] = str(Path(shutil.which("grep")).parent)
    (tmp_path / "agents.md").write_text("## Project settings\n- Autonomy: present\n- Brief requirements: none\n",
                                       encoding="utf-8")
    process = subprocess.Popen([*command, "PreToolUse", "--tool", tool], cwd=tmp_path, env=env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert process.wait(timeout=5) == 0
        assert json.loads(process.stdout.read()) == {}
        assert not Path(env["RO_TEST_SENTINEL"]).exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


@pytest.mark.parametrize("age,ready", [(-1, False), (0, False), (1, False), (1.999, False), (2, True), (3, True)])
def test_wrapper_witness_requires_two_second_timestamp_window(tmp_path, monkeypatch, age, ready):
    project = prepare_cache(tmp_path)
    path = tmp_path / "plan.md"
    now = 1800000000
    os.utime(path, (now - age, now - age))
    hooks._snapshot(project)
    os.utime(project.state / "records-hook.json", (now - 10, now - 10))
    monkeypatch.setattr(hooks.time, "time", lambda: now)
    hooks._wrapper_snapshot(project)
    assert (project.state / "records-hook.ready").exists() is ready
    assert (project.state / "records-hook-stamps/plan.md").exists() is ready


@pytest.mark.parametrize("wrapper", ["ro-hook.sh", "ro-hook.cmd"])
def test_same_size_same_second_record_edit_reaches_interpreter(tmp_path, monkeypatch, wrapper):
    project = prepare_cache(tmp_path)
    command = wrapper_command(wrapper)
    environment = wrapper_environment(tmp_path, wrapper)
    path = tmp_path / "plan.md"
    before = "## H-A-01\n## H-A-02\n"
    path.write_text(before, encoding="utf-8", newline="\n")
    second = 1800000000
    os.utime(path, ns=(second * 10**9 + 100_000_000,) * 2)
    monkeypatch.setattr(hooks.time, "time", lambda: second + 0.2)
    hooks._snapshot(project)
    os.utime(project.state / "records-hook.json", (second - 10, second - 10))
    hooks._wrapper_snapshot(project)
    assert not (project.state / "records-hook.ready").exists()
    path.write_text(before.replace("H-A-02", "H-A-01"), encoding="utf-8", newline="\n")
    os.utime(path, ns=(second * 10**9 + 300_000_000,) * 2)
    assert path.stat().st_size == len(before.encode())
    result = subprocess.run([*command, "PostToolUse"], cwd=tmp_path, env=environment,
                            input=b'{"payload":"unchanged"}\n', capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert Path(environment["RO_TEST_SENTINEL"]).read_text().splitlines() == ["started"]
    assert result.stdout.decode().splitlines()[-1] == '{"payload":"unchanged"}'
    assert any(finding.check == "records.id" for finding in hooks._snapshot(project))


def test_unchanged_wrapper_runner_publishes_witnesses_after_clock_window(tmp_path, monkeypatch):
    project = prepare_cache(tmp_path)
    ready = project.state / "records-hook.ready"
    ready.unlink()
    now = 1700000061
    monkeypatch.setattr(hooks.time, "time", lambda: now)
    payload = json.dumps({"cwd": str(tmp_path), "tool_name": "Edit"}).encode()
    assert runner.run("PostToolUse", payload, project, policy_root=str(project.root)) == ({}, 0)
    assert not ready.exists()
    now += 2
    assert runner.run("PostToolUse", payload, project, policy_root=str(project.root)) == ({}, 0)
    assert ready.read_text() == "records-hook-v1\n"


@pytest.mark.parametrize("registered", [False, True])
def test_push_precheck_skips_only_scoped_registration_and_gate_still_scans(tmp_path, monkeypatch, registered):
    project = configured(tmp_path)
    (tmp_path / ".git").mkdir()
    calls = []
    monkeypatch.setattr(ro_gate, "registration", lambda root: (root, registered))
    monkeypatch.setattr(ro_evidence, "scan_publish", lambda *args, **kwargs: calls.append(kwargs) or ["sensitive content"])
    payload = {"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    result = hooks.hook(project, "PreToolUse", payload)
    assert len(calls) == (0 if registered else 1)
    assert ("publish.scan" in str(result)) is (not registered)
    calls.clear()
    result = hooks.hook(project, "pre-push", {}, refs="exact refs\n", remote="origin")
    assert calls == [{"refs": "exact refs\n", "remote": "origin"}]
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("general,check", [(True, None), (False, "external.gate")])
def test_nonpublication_push_matcher_does_not_query_gate(tmp_path, monkeypatch, general, check):
    project = configured(tmp_path)
    monkeypatch.setattr(ro_gate, "registration", lambda *_: pytest.fail("unrelated matcher queried Git"))
    result = hooks.hook(project, "PreToolUse", {
        "cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "git push"}},
        check=check, general=general)
    assert result == {}


@pytest.mark.parametrize("problem", ["non-git", "git-unavailable", "git-timeout", "missing-registration"])
def test_gate_lookup_preserves_missing_gate_guidance_on_lookup_failure(tmp_path, monkeypatch, problem):
    if problem != "non-git":
        (tmp_path / ".git").mkdir()
    calls = []
    def query(command, **kwargs):
        calls.append((command, kwargs))
        if problem == "git-unavailable":
            raise OSError("Git unavailable")
        if problem == "git-timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(stdout=".git/hooks\n")
    monkeypatch.setattr(ro_gate.subprocess, "run", query)
    assert ro_gate.registration(tmp_path) == (None if problem == "non-git" else tmp_path, False)
    if problem == "non-git":
        assert calls == []
    else:
        assert len(calls) == 1
        assert calls[0][0] == ["git", "-C", str(tmp_path), "rev-parse", "--git-path", "hooks"]
        assert calls[0][1]["timeout"] == 1


@pytest.mark.parametrize("hook_state,expected", [("missing", False), ("replaced", False), ("dispatcher", True)])
def test_gate_registration_requires_the_installed_dispatcher(tmp_path, monkeypatch, hook_state, expected):
    import hashlib
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    monkeypatch.setattr(ro_gate.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=".git/hooks\n"))
    key = hashlib.sha256(os.path.normcase(str(tmp_path.resolve())).encode("utf-8")).hexdigest()
    registrations = tmp_path / ".git" / "hooks" / "research-orchestrator" / "registrations"
    registrations.mkdir(parents=True)
    (registrations / (key + ".json")).write_text("{}", encoding="utf-8")
    hook = tmp_path / ".git" / "hooks" / "pre-push"
    if hook_state == "replaced":
        hook.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
    elif hook_state == "dispatcher":
        hook.write_text("#!/bin/sh\n" + ro_gate.DISPATCH_MARK + "\n", encoding="utf-8")
    assert ro_gate.registration(tmp_path) == (tmp_path, expected)


def test_push_precheck_uses_the_command_checkout_not_the_policy_root(tmp_path, monkeypatch):
    project = configured(tmp_path / "policy")
    other = tmp_path / "other-checkout"
    other.mkdir()
    asked, scans = [], []
    monkeypatch.setattr(ro_gate, "registration", lambda root: asked.append(Path(root)) or (root, Path(root) == project.root))
    monkeypatch.setattr(ro_evidence, "scan_publish", lambda *args, **kwargs: scans.append(kwargs.get("checkout")) or [])
    payload = {"cwd": str(other), "tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    hooks.hook(project, "PreToolUse", payload)
    # The staged pre-check reads the pushing checkout, not the policy root.
    assert asked and asked[-1] == other and len(scans) == 1 and Path(scans[0]) == other
    asked.clear(); scans.clear()
    payload["cwd"] = str(project.root)
    hooks.hook(project, "PreToolUse", payload)
    assert asked[-1] == project.root and scans == []


@pytest.mark.parametrize("command", ["git -C ../other push origin main", "git --git-dir=../other/.git push",
                                     "git --work-tree ../other push", "cd ../other && git push origin main",
                                     "env -C ../other git push", "env -C../other git push", "git -C../other push",
                                     "env --chdir=../other git push", "sudo -D ../other git push",
                                     "sudo --chdir=../other git push",
                                     "GIT_DIR=../other/.git git push", "export GIT_WORK_TREE=../other; git push"])
def test_push_that_selects_its_checkout_in_the_command_keeps_the_advisory(tmp_path, monkeypatch, command):
    project = configured(tmp_path / "policy")
    asked, scans = [], []
    # The policy root's own gate is installed; it does not cover a checkout the command moves to.
    monkeypatch.setattr(ro_gate, "registration", lambda root: asked.append(Path(root)) or (root, True))
    monkeypatch.setattr(ro_evidence, "scan_publish", lambda *args, **kwargs: scans.append(1) or [])
    payload = {"cwd": str(project.root), "tool_name": "Bash", "tool_input": {"command": command}}
    result = str(hooks.hook(project, "PreToolUse", payload))
    # The hook cwd's staged changes are not what this push sends: advise without scanning them.
    assert asked == [] and scans == []
    assert "selects its checkout inside the command" in result


@pytest.mark.parametrize("command", ["git -c core.pager=cat push", "git status && git push", "time git push",
                                     "sudo -C 3 git push", "sudo -C3 git push", "nice -n 5 git push"])
def test_push_in_the_hook_directory_is_not_reported_as_moved(command):
    import ro_checks
    parsed = ro_checks.command_parts(ro_checks.Call("shell", "bash", command), {"environment": "linux/bash"})
    assert ro_checks.git_push(parsed.parts, "linux")
    assert not ro_checks.push_target_moved(parsed.parts, "linux")
