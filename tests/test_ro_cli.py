"""The public commands and installed supervisor preserve the enforcement contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
import platform

import pytest

from conftest import SCRIPTS, item, make_project, run_init, set_queue, unified_project, with_real_ps
import ro
import ro_hook_runner as runner
import ro_hooks
from ro_state import Project, process_start


def project_at(tmp_path, mode="block", block="shell.background, publish.scan, external.gate"):
    target = unified_project(tmp_path)
    agents = target / "agents.md"
    text = agents.read_text(encoding="utf-8")
    lines = text.splitlines()
    for key, value in (("Enforcement", mode), ("Block", block), ("External actions", "release-tool publish"),
                       ("Environment", f"{'windows' if os.name == 'nt' else 'linux'}/bash")):
        lines = [f"- {key}: {value}" if line.startswith(f"- {key}:") else line for line in lines]
    agents.write_text("\n".join(lines) + "\n", encoding="utf-8")
    project = Project(target, slot="A", session="author-session")
    project.register_slot()
    return project


def payload(project, command="work &"):
    return {"cwd": str(project.root), "session_id": project.session,
            "tool_name": "Bash", "tool_input": {"command": command}}


def denied(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_public_record_commands_operate_on_one_project(tmp_path, capsys):
    project = project_at(tmp_path)
    base = ["--project", str(project.root), "--session", project.session]
    assert ro.main([*base, "next-id", "H", "--slot", "B"]) == 0
    assert "H-B-01" in capsys.readouterr().out
    set_queue(project.root, item("H-A-01"))
    assert ro.main([*base, "claim", "H-A-01"]) == 0
    assert ro.main([*base, "release", "H-A-01"]) == 0
    assert ro.main([*base, "dupcheck", "claim"]) == 0
    assert ro.main([*base, "index"]) == 0
    assert ro.main([*base, "observe", "Capacity", "2", "--ttl", "6h"]) == 0
    assert ro.main([*base, "jobs"]) == 0
    assert ro.main([*base, "brief", "--max", "8000"]) == 0
    assert ro.main([*base, "close"]) == 0


@pytest.mark.parametrize("mode", ["commit", "push"])
def test_git_sync_initialisation_ignores_only_local_tool_state_and_keeps_existing_rules(tmp_path, mode):
    target = tmp_path / "synced-project"
    target.mkdir()
    (target / ".git").mkdir()
    (target / ".gitignore").write_text("existing-rule/\n", encoding="utf-8")
    result = run_init(target, "--git", mode)
    assert result.returncode == 0, result.stderr
    assert (target / ".gitignore").read_text(encoding="utf-8") == "existing-rule/\n.ro/\n"
    assert run_init(target, "--reconfigure").returncode == 0
    assert (target / ".gitignore").read_text(encoding="utf-8").count(".ro/") == 1


def test_git_sync_off_does_not_create_an_ignore_file(tmp_path):
    target = make_project(tmp_path, "unsynced-project", "--git", "off")
    assert not (target / ".gitignore").exists()


def test_public_receipts_shell_check_and_external_gate(tmp_path, capsys):
    project = project_at(tmp_path)
    artifact = project.root / "artifact.txt"
    artifact.write_text("reviewed bytes\n", encoding="utf-8")
    base = ["--project", str(project.root), "--session", project.session]
    assert ro.main([*base, "receipt", "add", "artifact.txt", "--reviewer", "reviewer-session", "--verdict", "PASS",
                    "--scope", "contract"]) == 0
    assert ro.main([*base, "receipt", "check", "artifact.txt", "--scope", "contract"]) == 0
    assert ro.main([*base, "check", "work &"]) == 1
    assert "shell.background" in capsys.readouterr().out
    command = [sys.executable, "-c", "from pathlib import Path; Path('executed.txt').touch()"]
    assert ro.main([*base, "external", "--artifact", "artifact.txt", "--action", "X-A-001", "--", *command]) == 1
    assert not (project.root / "executed.txt").exists()


@pytest.mark.parametrize("mode,returncode,output", [
    ("block", 9, b""), ("block", 0, b"{"), ("block", 0, b"[]"), ("off", 9, b""),
], ids=["child-crash", "invalid-json", "invalid-response", "disabled-diagnostics"])
def test_supervisor_child_failures_are_visible_and_fail_open(tmp_path, monkeypatch, mode, returncode, output):
    project = project_at(tmp_path, mode)
    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], returncode, output, b"child unavailable")
    monkeypatch.setattr(subprocess, "run", with_real_ps(failed))
    result, code = runner.run("PreToolUse", json.dumps(payload(project)).encode(), project)
    assert code == 0 and not denied(result)
    if mode == "off":
        assert result == {} and not (project.state / "warnings.log").exists()
    else:
        assert project.read_json("hooks-self-test.json")["status"] == "inactive"
        assert (project.state / "warnings.log").read_text(encoding="utf-8")


def test_real_missing_child_interpreter_is_visible_and_fail_open_for_general_check(tmp_path):
    project = project_at(tmp_path)
    result, code = runner.run("PreToolUse", json.dumps(payload(project)).encode(), project,
                              interpreter=str(project.root / "absent-interpreter.exe"))
    assert code == 0 and not denied(result)
    assert project.read_json("hooks-self-test.json")["status"] == "inactive"


def test_real_child_timeout_is_visible_and_per_call_action_fails_open(tmp_path):
    project = project_at(tmp_path)
    result, _ = runner.run("PreToolUse", json.dumps(payload(project, "git push")).encode(), project,
                           check="publish.scan", timeout=.000001)
    assert not denied(result)
    assert project.read_json("hooks-self-test.json")["status"] == "inactive"


@pytest.mark.parametrize("raw", [b"[" * 5000, b"[]", b"x" * (ro_hooks.MAX_INPUT + 1)],
                         ids=["deep-nesting", "array-root", "oversized"])
def test_supervisor_malformed_inputs_fail_open_without_starting_child(tmp_path, monkeypatch, raw):
    project = project_at(tmp_path)
    def unexpected(*args, **kwargs):
        raise AssertionError("malformed stdin started a child")
    monkeypatch.setattr(subprocess, "run", with_real_ps(unexpected))
    result, code = runner.run("PreToolUse", raw, project, "external.gate")
    assert code == 0 and not denied(result)


@pytest.mark.parametrize("invalid", [{"cwd": None}, {"cwd": []}, {"slot": "invalid"}, {"tool_input": []},
                                    {"tool_name": {}}, {"cwd": ""}])
def test_malformed_envelopes_fail_open_before_using_their_paths(tmp_path, monkeypatch, capsys, invalid):
    project = project_at(tmp_path)
    data = json.dumps(invalid).encode()
    def unexpected(*args, **kwargs):
        raise AssertionError("invalid envelope started a child")
    monkeypatch.setattr(subprocess, "run", with_real_ps(unexpected))
    result, code = runner.run("PreToolUse", data, project, "external.gate")
    assert code == 0 and not denied(result)
    args = ro.parser().parse_args(["--project", str(project.root), "hook", "PreToolUse", "--check", "external.gate"])
    assert ro.hook_main(args, data) == 0
    assert not denied(json.loads(capsys.readouterr().out))


def test_session_start_returns_bounded_context_and_persists_self_test(tmp_path, capsys):
    project = project_at(tmp_path)
    args = ro.parser().parse_args(["--project", str(project.root), "hook", "SessionStart"])
    assert ro.hook_main(args, json.dumps(payload(project, "echo ready")).encode()) == 0
    result = json.loads(capsys.readouterr().out)
    context = result["hookSpecificOutput"]["additionalContext"]
    assert context and len(context) <= 8000
    assert project.read_json("hooks-self-test.json")["status"] == "active"


def test_discovery_heading_reconciles_reservation_and_new_duplicate(tmp_path):
    project = project_at(tmp_path)
    from ro_records import next_id
    reserved = next_id(project, "D")
    ro_hooks._snapshot(project, report=False)
    path = project.root / "discoveries.md"
    with path.open("a", encoding="utf-8") as output:
        output.write(f"\n## {reserved} — recorded fact\n\n## {reserved} — duplicate fact\n")
    findings = ro_hooks._snapshot(project)
    assert any(f.check == "records.id" for f in findings)
    assert reserved not in project.read_json("ids.json")


def test_stale_pid_binding_does_not_block_an_edit(tmp_path):
    project = project_at(tmp_path, block="jobs.mutate-bound")
    project.write_json("jobs.json", [{"id": "J-A-0001", "pid": os.getpid(), "start": "reused-start",
                                     "status": "running", "bound": [str(project.root)]}])
    result = ro_hooks.hook(project, "PreToolUse", {"tool_name": "Edit", "tool_input": {"file_path": "input.txt"}})
    assert result == {}


def test_nested_host_workdir_finds_settings_and_resolves_relative_targets_from_cwd(tmp_path, capsys):
    project = project_at(tmp_path, block="jobs.mutate-bound")
    run = project.root / "run"
    run.mkdir()
    sibling = project.root / "scratch"
    sibling.mkdir()
    project.write_json("jobs.json", [{"id": "J-A-0001", "pid": os.getpid(), "start": process_start(os.getpid()),
                                     "status": "running", "bound": [str(run)]}])
    data = {"cwd": str(run), "tool_name": "shell", "tool_input": {"command": "rm input.txt"}}
    args = ro.parser().parse_args(["hook", "PreToolUse"])
    assert ro.hook_main(args, json.dumps(data).encode()) == 0
    assert denied(json.loads(capsys.readouterr().out))
    data["cwd"] = str(sibling)
    assert ro.hook_main(args, json.dumps(data).encode()) == 0
    assert not denied(json.loads(capsys.readouterr().out))
    data["tool_input"]["command"] = "rm ../run/input.txt"
    assert ro.hook_main(args, json.dumps(data).encode()) == 0
    assert denied(json.loads(capsys.readouterr().out))


def test_hook_literal_is_data_in_search_observation_and_global_options(tmp_path, capsys):
    project = project_at(tmp_path)
    discoveries = project.root / "discoveries.md"
    discoveries.write_text(discoveries.read_text(encoding="utf-8") + "\n## D-A-01 hook adapter\n", encoding="utf-8")
    base = ["--project", str(project.root), "--session", "hook", "--slot", "A"]
    assert ro.main([*base, "dupcheck", "hook"]) == 0
    assert "D-A-01 hook adapter" in capsys.readouterr().out
    assert ro.main([*base, "observe", "Adapter", "hook"]) == 0
    assert "- Adapter: hook (Observed at " in (project.root / "handoff.md").read_text(encoding="utf-8")


def test_hook_literal_in_child_arguments_reaches_launch_unchanged(tmp_path, monkeypatch, capsys):
    import ro_jobs
    project = project_at(tmp_path)
    command = [sys.executable, "-c", "import sys; print(sys.argv[1])", "hook"]
    def launch(owner, args):
        assert owner.root == project.root
        assert args.command == ["--", *command]
        return subprocess.run(args.command[1:], check=True, capture_output=True, text=True).stdout.strip()
    monkeypatch.setattr(ro_jobs, "launch", launch)
    assert ro.main(["--project", str(project.root), "--slot", "A", "launch", "--item", "H-A-01", "--expect", "10s", "--", *command]) == 0
    assert capsys.readouterr().out == "hook\n"


@pytest.mark.parametrize("global_args", [["--session", "hook"], ["--session=hook"], ["--project", "hook"]])
def test_actual_hook_subcommand_keeps_hook_parser_with_global_option_values(global_args, monkeypatch):
    monkeypatch.setattr(ro, "hook_main", lambda args: 17 if args.event == "PreToolUse" else 1)
    assert ro.main([*global_args, "hook", "PreToolUse"]) == 17


@pytest.mark.latency
def test_supervised_installed_hook_latency_is_bounded_on_large_project(tmp_path):
    project = project_at(tmp_path)
    (project.root / "discoveries.md").write_text("fact\n" * 280000, encoding="utf-8")
    (project.root / "handoff.md").write_text("event\n" * 83334, encoding="utf-8")
    command = [sys.executable, "-E", "-S", str(SCRIPTS / "ro_hook_runner.py"), "PreToolUse"]
    env = {**os.environ, "RO_HOOK_PYTHON": sys.executable}
    data = json.dumps(payload(project, "echo ready"))
    # Warm bytecode and filesystem caches, then take the median of three batch p95s.
    # This retains tail sensitivity while rejecting a single unrelated scheduler/load spike.
    for _ in range(2):
        result = subprocess.run(command, input=data, text=True, capture_output=True, cwd=project.root, timeout=10, env=env)
        assert result.returncode == 0 and json.loads(result.stdout) == {}, result.stderr
    batches = []
    for _ in range(3):
        samples = []
        for _ in range(20):
            start = time.perf_counter()
            result = subprocess.run(command, input=data, text=True, capture_output=True, cwd=project.root, timeout=10, env=env)
            assert result.returncode == 0 and json.loads(result.stdout) == {}, result.stderr
            samples.append(time.perf_counter() - start)
        batches.append(sorted(samples)[18])
    p95 = sorted(batches)[1]
    print(f"\nLATENCY supervised PreToolUse p95={p95 * 1000:.1f} ms")
    if destination := os.environ.get("RO_LATENCY_REPORT"):
        report = {"os": platform.system(), "python": platform.python_version(), "layer": "installed-watchdog",
                  "samples_per_batch": 20, "warmups": 2, "batch_p95_ms": [value * 1000 for value in batches],
                  "p95_ms": p95 * 1000, "budget_ms": 150, "hook_output_correct": True, "passed": p95 < .150}
        Path(destination).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # The same 150 ms budget applies to every OS and layer.
    assert p95 < .150, f"supervised hook p95 {p95 * 1000:.1f} ms >= 150 ms"


def test_in_process_hook_preserves_decision_without_spawning_child(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    raw = json.dumps(payload(project)).encode()
    expected = runner.run("PreToolUse", raw, project)
    def unexpected(*args, **kwargs):
        raise AssertionError("configured hook started a second interpreter")
    monkeypatch.setattr(subprocess, "run", unexpected)
    assert runner.run("PreToolUse", raw, project, in_process=True) == expected
    assert denied(expected[0])


@pytest.mark.parametrize("event,code,decision", [("PreToolUse", 0, None), ("pre-push", 1, "deny")])
def test_configured_interpreter_watchdog_terminates_a_stalled_hook(tmp_path, event, code, decision):
    source = ("import sys,threading; sys.path.insert(0,sys.argv.pop(1)); "
              "import ro_hook_runner as runner; runner.DEADLINE=.05; "
              "runner.run=lambda *a,**k:threading.Event().wait(30); "
              "raise SystemExit(runner.main())")
    result = subprocess.run([sys.executable, "-E", "-S", "-c", source, str(SCRIPTS), event],
                            input="{}", text=True, capture_output=True, cwd=tmp_path, timeout=5,
                            env={**os.environ, "RO_HOOK_PYTHON": sys.executable})
    assert result.returncode == code, result.stderr
    output = json.loads(result.stdout)
    assert output.get("hookSpecificOutput", {}).get("permissionDecision") == decision
    assert "deadline exceeded" in result.stdout


def test_session_start_reports_exact_trusted_runtime_prefix(tmp_path, capsys):
    from ro_command import command_prefix
    project = project_at(tmp_path)
    args = ro.parser().parse_args(["--project", str(project.root), "hook", "SessionStart"])
    assert ro.hook_main(args, json.dumps(payload(project)).encode()) == 0
    context = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "ro command prefix: " + command_prefix(shell="sh") in context


@pytest.mark.parametrize("settings,tool,starts", [
    ("- Enforcement: off\n", "Bash", False),
    ("- Enforcement: block\n- Read bound: off\n", "Read", False),
    ("- Enforcement: block\n", "Grep", False),
    ("- Enforcement: block\n- Read bound: on\n", "Glob", True),
    ("- Enforcement: block\n- Autonomy: present\n", "AskUserQuestion", False),
    ("- Enforcement: block\n- Autonomy: away\n", "AskUserQuestion", True),
    ("- Enforcement: block\n", "Agent", False),
    ("- Enforcement: block\n- Brief requirements: reviewer: Scope\n", "Agent", True),
    ("- Enforcement: block\n", "Bash", True),
    ("```\n- Enforcement: off\n```\n- Enforcement: block\n", "Bash", True),
    ("- Enforcement: warn\n<!-- - Read bound: on -->\n", "Read", True),
], ids=["off", "read-quiet", "read-default", "read-bound-on", "question-present", "question-away",
        "agent-default", "agent-brief", "shell", "fenced-off-example", "commented-read-bound"])
def test_supervisor_starts_no_child_when_no_enabled_check_can_apply(tmp_path, monkeypatch, settings, tool, starts):
    (tmp_path / "agents.md").write_text("# Probe — Agent Rules\n\n## Project settings\n" + settings, encoding="utf-8")
    started = []

    def child(command, **kwargs):
        started.append(command)
        return subprocess.CompletedProcess(command, 0, b"{}")
    monkeypatch.setattr(subprocess, "run", child)
    data = json.dumps({"cwd": str(tmp_path), "session_id": "s", "tool_name": tool, "tool_input": {"command": "x"}})
    assert runner.run("PreToolUse", data.encode(), Project(tmp_path, session="s")) == ({}, 0)
    assert bool(started) is starts


def test_supervisor_quiet_path_covers_missing_policy_but_not_startup_or_slot_selection(tmp_path, monkeypatch):
    started = []

    def child(command, **kwargs):
        started.append(command[command.index("hook") + 1])
        return subprocess.CompletedProcess(command, 0, b"{}")
    monkeypatch.setattr(subprocess, "run", child)
    data = {"cwd": str(tmp_path), "session_id": "s", "tool_name": "Bash", "tool_input": {"command": "x"}}
    for event in ("PreToolUse", "PostToolUse", "Stop"):
        runner.run(event, json.dumps(data).encode(), Project(tmp_path, session="s"))
    assert started == []  # No agents.md: enforcement defaults to off.
    runner.run("SessionStart", json.dumps(data).encode(), Project(tmp_path, session="s"))
    runner.run("PreToolUse", json.dumps({**data, "slot": "B"}).encode(), Project(tmp_path, session="s"))
    assert started == ["SessionStart", "PreToolUse"]


@pytest.mark.parametrize("tool", ["Edit", "Write"])
@pytest.mark.parametrize("registry,starts", [
    (None, False), ([], False), ([{"status": "finished"}], False),
    ([{"status": "running"}], True), ([{"status": "attention"}], True),
    ([{"status": "error"}], True), ([{"status": "starting"}], True),
    ([{"status": "finished", "tree_owned": True}], True),
    ({"jobs": []}, True), ([None], True), ("malformed", True),
])
def test_edit_write_skip_child_only_without_protected_jobs(tmp_path, monkeypatch, tool, registry, starts):
    (tmp_path / "agents.md").write_text("## Project settings\n- Enforcement: block\n", encoding="utf-8")
    project = Project(tmp_path, session="edit-session")
    if registry is not None:
        project.write_json("jobs.json", registry)
        if registry == "malformed":
            (project.state / "jobs.json").write_text("{", encoding="utf-8")
    started = []

    def child(command, **kwargs):
        started.append(command)
        return subprocess.CompletedProcess(command, 0, b"{}")
    monkeypatch.setattr(subprocess, "run", child)
    data = json.dumps({"cwd": str(tmp_path), "tool_name": tool, "tool_input": {"file_path": "target.txt"}}).encode()
    assert runner.run("PreToolUse", data, project) == ({}, 0)
    assert bool(started) is starts
    started.clear()
    runner.run("PostToolUse", data, project)
    assert started  # PostToolUse still checks changed records and pending warnings.


def test_missing_registry_with_recovery_snapshot_does_not_skip_edit_checks(tmp_path):
    (tmp_path / "agents.md").write_text("## Project settings\n- Enforcement: block\n", encoding="utf-8")
    recovery = tmp_path / ".ro/recovery"
    recovery.mkdir(parents=True)
    (recovery / "jobs.json").write_text('[{"status":"running"}]', encoding="utf-8")
    assert not runner.quiet("PreToolUse", {"tool_name": "Edit"}, tmp_path)


@pytest.mark.parametrize("argv", [
    ["hook", "PreToolUse"], ["--project", "p", "--session", "s", "--slot", "B", "hook", "Stop", "--general"],
    ["--session=hook", "hook", "pre-push", "--remote", "origin"], ["--project", "hook", "hook", "PostToolUse"],
    ["hook", "PreToolUse", "--check", "external.gate"], ["--session=", "hook", "SessionStart"],
])
def test_fast_hook_arguments_match_argparse(argv, monkeypatch):
    monkeypatch.delenv("RO_SESSION", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    fast = ro.hook_arguments(argv)
    slow = ro.parser(hooks_only=True).parse_args(argv)
    assert fast is not None
    for name in ("project", "slot", "session", "event", "check", "general", "remote"):
        assert getattr(fast, name) == getattr(slow, name), name


@pytest.mark.parametrize("argv", [["hook", "PreToolUse", "--check", "unknown"], ["--proj", "x", "hook", "Stop"],
                                  ["hook"], ["hook", "PreToolUse", "--check=publish.scan"], ["next-id", "D"],
                                  ["--session", "--slot", "hook", "Stop"]])
def test_unusual_hook_arguments_fall_back_to_argparse(argv):
    assert ro.hook_arguments(argv) is None


@pytest.mark.parametrize("session", [None, "", "   "])
def test_receipt_cli_refuses_missing_author_session(tmp_path, session):
    (tmp_path / "artifact.txt").write_text("reviewed bytes", encoding="utf-8")
    env = dict(os.environ)
    env.pop("RO_SESSION", None)
    env.pop("CODEX_THREAD_ID", None)
    if session is not None:
        env["RO_SESSION"] = session
    result = subprocess.run([sys.executable, str(SCRIPTS / "ro.py"), "--project", str(tmp_path),
                             "receipt", "add", "artifact.txt", "--reviewer", "reviewer-session",
                             "--verdict", "PASS", "--scope", "contract"],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert not (tmp_path / ".ro" / "receipts.json").exists()


@pytest.mark.parametrize("source", ["argument", "environment"])
def test_receipt_cli_uses_explicit_author_session(tmp_path, source):
    (tmp_path / "artifact.txt").write_text("reviewed bytes", encoding="utf-8")
    env = dict(os.environ)
    env.pop("RO_SESSION", None)
    command = [sys.executable, str(SCRIPTS / "ro.py"), "--project", str(tmp_path)]
    if source == "argument":
        command.extend(["--session", "stable-author-session"])
    else:
        env["RO_SESSION"] = "stable-author-session"
    command.extend(["receipt", "add", "artifact.txt", "--reviewer", "reviewer-session",
                    "--verdict", "PASS", "--scope", "contract"])
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    project = Project(tmp_path)
    receipt = project.read_json("receipts.json")["receipts"][0]
    assert receipt["author_session"] == "stable-author-session"
