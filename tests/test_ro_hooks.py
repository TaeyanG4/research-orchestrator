"""Shell grammar, host decisions, failure policy and bounded hook work."""

from __future__ import annotations

import builtins
import io
import itertools
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from conftest import FIXTURES, SCRIPTS
import ro
import ro_checks as checks
import ro_hooks as hooks
import ro_hook_runner as runner
import ro_evidence as evidence
from ro_state import Project, process_start


CHECK_IDS = ("shell.background", "shell.detach", "shell.heredoc", "shell.cd", "jobs.mutate-bound",
             "jobs.read-bound", "jobs.unmonitored", "records.timestamp", "records.id",
             "publish.scan", "external.gate", "ask.away", "brief.requirements")


def configured(mode: str = "block", selected: str | None = None, shell: str = "bash") -> dict[str, str]:
    return {"enforcement": mode, "block": selected if selected is not None else ",".join(CHECK_IDS),
            "environment": f"{'windows' if os.name == 'nt' else 'linux'}/{shell}",
            "autonomy": "away", "external_actions": "literal:release-tool publish", "brief_requirements": "none"}


def project_at(root: Path, mode: str = "block", selected: str | None = None) -> Project:
    root.mkdir(exist_ok=True)
    text = ("# Work — Agent Rules\n\n## Project settings\n"
            f"- Enforcement: {mode}\n- Block: {selected if selected is not None else ','.join(CHECK_IDS)}\n"
            f"- Environment: {configured()['environment']}\n"
            "- External actions: literal:release-tool publish\n- Autonomy: away\n")
    (root / "agents.md").write_text(text, encoding="utf-8")
    return Project(root, slot="A", session="hook-test-session")


def test_self_test_does_not_mislabel_a_valid_adapter_from_scheduler_delay(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    ticks = iter((0.0, 1.0))
    monkeypatch.setattr(hooks.time, 'perf_counter', lambda: next(ticks, 1.0))
    assert hooks.self_test(project) == {'status': 'active'}


def shell_payload(command: str, dialect: str = "bash", **extra) -> dict:
    return {"tool_name": "Bash" if dialect == "bash" else "PowerShell", "tool_input": {"command": command}, **extra}


def denied(response: dict) -> bool:
    return response.get("hookSpecificOutput", {}).get("permissionDecision") == "deny" or response.get("decision") == "block"


def warned(response: dict) -> bool:
    return bool(response.get("hookSpecificOutput", {}).get("additionalContext") or response.get("systemMessage"))


@pytest.mark.parametrize("tool,operand", [("Bash", {"command": "rm input.txt"}),
                                         ("PowerShell", {"command": "Remove-Item input.txt"}),
                                         ("Edit", {"file_path": "input.txt"})])
@pytest.mark.parametrize("directory_key", ["cwd", "workdir"])
@pytest.mark.parametrize("relative", [False, True])
def test_tool_directory_override_protects_bound_paths_and_allows_siblings(tmp_path, tool, operand, directory_key, relative):
    project = project_at(tmp_path)
    for name in ("bound", "scratch"):
        (tmp_path / name).mkdir()
    project.write_json("jobs.json", [{"id": "J-A-0001", "pid": os.getpid(), "start": process_start(os.getpid()),
                                     "status": "running", "bound": [str(tmp_path / "bound")]}])
    for name, expected in (("bound", True), ("scratch", False)):
        directory = name if relative else str(tmp_path / name)
        payload = {"cwd": str(tmp_path), "tool_name": tool, "tool_input": {**operand, directory_key: directory}}
        result = hooks.hook(project, "PreToolUse", payload)
        assert denied(result) is expected
        assert not warned(result)


@pytest.mark.parametrize("override", [{}, {"workdir": "$UNKNOWN"}, {"workdir": []},
                                      {"workdir": "bound", "cwd": "scratch"}])
def test_uncertain_tool_directory_warns_for_relative_targets(tmp_path, override):
    project = project_at(tmp_path)
    project.write_json("jobs.json", [{"id": "J-A-0001", "pid": os.getpid(), "start": process_start(os.getpid()),
                                     "status": "running", "bound": [str(tmp_path / "bound")]}])
    payload = {"tool_name": "Bash", "tool_input": {"command": "rm input.txt", **override}}
    if override:
        payload["cwd"] = str(tmp_path)
    result = hooks.hook(project, "PreToolUse", payload)
    assert warned(result) and not denied(result)
    assert "Working directory is uncertain" in str(result)


def test_absolute_tool_directory_does_not_need_an_envelope_cwd(tmp_path):
    project = project_at(tmp_path)
    bound = tmp_path / "bound"
    project.write_json("jobs.json", [{"id": "J-A-0001", "pid": os.getpid(), "start": process_start(os.getpid()),
                                     "status": "running", "bound": [str(bound)]}])
    payload = {"tool_name": "Bash", "tool_input": {"command": "rm input.txt", "workdir": str(bound)}}
    assert denied(hooks.hook(project, "PreToolUse", payload))
    payload["tool_input"] = {"command": f"rm '{bound.as_posix()}/input.txt'", "workdir": "$UNKNOWN"}
    assert denied(hooks.hook(project, "PreToolUse", payload))


@pytest.mark.parametrize("command,dialect,expected", [
    ("worker &", "bash", True), ("worker & wait", "bash", False),
    ("worker && finish", "bash", False), ("left |& right", "bash", False),
    ("worker &> output.log", "bash", False), ("worker >&2", "bash", False),
    ("worker 2>&1", "bash", False), ("echo $(worker &) now", "bash", False),
    ("echo `worker &` now", "bash", False), ("echo \\&", "bash", False),
    ("echo $(printf ')') &", "bash", True), ("echo $(printf '(') &", "bash", True),
    ("echo $(printf ')'; worker &)", "bash", False),
    ("& 'tool.exe'", "powershell", False), ("echo done; & 'tool.exe'", "powershell", False),
    ("echo done | & 'tool.exe'", "powershell", False), ("& { tool }", "powershell", False),
    ("(& 'tool.exe')", "powershell", False), ("tool &", "powershell", True),
    ("tool &; echo done", "powershell", True), ("bash worker.sh &", "bash", True),
    ("& { tool } &", "powershell", True),
    ("tool &\necho done", "powershell", True),
])
def test_background_grammar_has_exact_control_operator_exclusions(tmp_path, command, dialect, expected) -> None:
    findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, [], configured(shell=dialect))
    assert any(f.check == "shell.background" for f in findings) is expected


def test_word_disown_as_an_argument_is_not_a_detach_command(tmp_path) -> None:
    findings = checks.pre_checks(checks.Call("shell", "bash", "printf '%s' disown"), tmp_path, [], configured())
    assert not any(f.check == "shell.background" for f in findings)


@pytest.mark.parametrize("dialect,commands", [
    ("powershell", ["Set-Content -Path safe.txt -Value 'run/input.txt'", "Add-Content safe.txt 'run/input.txt'",
                    "Out-File -InputObject 'run/input.txt' -FilePath safe.txt",
                    "Copy-Item -Destination safe.txt -Path run/input.txt", "Write-Output `&"]),
    ("bash", ["cp -t safe-dir run/input.txt", 'echo "cat <<EOF"; echo ready']),
])
def test_literal_data_and_copy_sources_are_not_mutation_targets(tmp_path, dialect, commands):
    job = {"status": "running", "bound": [str(tmp_path / "run")], "run_dir": str(tmp_path / "run")}
    blocked = [command for command in commands if any(checks.outcome(f, configured()) == "block" for f in
               checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, [job], configured(shell=dialect)))]
    assert not blocked, f"{dialect}: {len(blocked)}/{len(commands)} false blocks: {blocked}"


def test_quoted_heredoc_bodies_do_not_execute_control_operators(tmp_path):
    for delimiter in (r"\EOF", "'E'OF", '"EOF"', "'EOF'", "'END-TEXT'"):
        ending = "END-TEXT" if "END-TEXT" in delimiter else "EOF"
        command = f"cat <<{delimiter}\nworker &\n`literal text`\n{ending}\necho ready\n"
        assert checks.pre_checks(checks.Call("shell", "bash", command), tmp_path, [], configured()) == [], delimiter


def test_heredoc_contents_are_checked_as_data_before_command_definitions(tmp_path):
    command = "cat <<EOF\nfunction cleanup { }\n`worker`\nEOF\n"
    findings = checks.pre_checks(checks.Call("shell", "bash", command), tmp_path, [], configured())
    assert [f.check for f in findings] == ["shell.heredoc"]
    comment = "echo ready # cat <<EOF\necho '`literal`'\n"
    assert checks.pre_checks(checks.Call("shell", "bash", comment), tmp_path, [], configured()) == []


def test_append_combined_output_redirect_protects_its_literal_destination(tmp_path):
    job = {"status": "running", "bound": [str(tmp_path / "run")], "run_dir": str(tmp_path / "run")}
    findings = checks.pre_checks(checks.Call("shell", "bash", "worker &>>run/output.log"), tmp_path, [job], configured())
    assert [f.check for f in findings] == ["jobs.mutate-bound"]


@pytest.mark.parametrize("command,dialect", [
    ("Set-Content -LiteralPath run/input.txt -Value ready", "powershell"),
    ("Copy-Item safe.txt -Destination run/input.txt", "powershell"),
    ("cp safe.txt --target-directory=run", "bash"),
    ("tee -a run/input.txt", "bash"),
])
def test_known_write_operands_protect_bound_inputs(tmp_path, command, dialect):
    job = {"status": "running", "bound": [str(tmp_path / "run")], "run_dir": str(tmp_path / "run")}
    findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, [job], configured(shell=dialect))
    assert any(f.check == "jobs.mutate-bound" and not f.uncertain for f in findings)


@pytest.mark.parametrize("dialect,command", [("bash", "worker &"), ("powershell", "tool &")])
def test_host_background_flag_suppresses_background_finding(tmp_path, dialect, command) -> None:
    findings = checks.pre_checks(checks.Call("shell", dialect, command, background=True), tmp_path, [], configured(shell=dialect))
    assert not any(f.check == "shell.background" for f in findings)


@pytest.mark.parametrize("mode,selected,failure", itertools.product(
    ("off", "warn", "block"), (False, True), (False, True)))
def test_every_enforcement_table_cell(mode, selected, failure) -> None:
    values = configured(mode, "shell.background" if selected else "none")
    result = checks.outcome(checks.Finding("shell.background", "fixed finding"), values, failure=failure)
    if mode == "off":
        expected = "off"
    elif mode == "block" and selected and not failure:
        expected = "block"
    else:
        expected = "warn"
    assert result == expected


@pytest.mark.parametrize("mode", ["off", "warn", "block"])
def test_dynamic_paths_only_warn_even_when_the_check_is_selected(mode) -> None:
    finding = checks.Finding("jobs.mutate-bound", "unresolved variable", uncertain=True)
    for selected in (False, True):
        assert checks.outcome(finding, configured(mode, "jobs.mutate-bound" if selected else "none")) == (
            "off" if mode == "off" else "warn")


def test_warning_channel_never_emits_ask_or_allow(tmp_path) -> None:
    project = project_at(tmp_path / "warn-channel", "warn")
    result = hooks.hook(project, "PreToolUse", shell_payload("worker &"))
    assert warned(result) and not denied(result)
    assert "shell.background" in result["hookSpecificOutput"]["additionalContext"]
    rendered = json.dumps(result)
    assert '"ask"' not in rendered and '"allow"' not in rendered


def test_identical_warnings_are_deduplicated_across_processes_in_each_session(tmp_path):
    project = project_at(tmp_path, "warn")
    payload = shell_payload("cd scratch")
    assert warned(runner.run("PreToolUse", json.dumps(payload).encode(), project)[0])
    assert runner.run("PreToolUse", json.dumps(payload).encode(), project)[0] == {}
    other = Project(tmp_path, session="another-session")
    assert warned(runner.run("PreToolUse", json.dumps(payload).encode(), other)[0])
    hooks.best_effort_warning(project, "shell.cd: same warning")
    hooks.best_effort_warning(project, "shell.cd: same warning")
    assert (project.state / "warnings.log").read_text(encoding="utf-8").count("same warning") == 1


@pytest.mark.parametrize("mode,command,decision,ids", [
    ("block", "worker &", "denied", ["shell.background"]),
    ("warn", "worker &", "warned", ["shell.background"]),
    ("block", "echo ready", "no hook decision", []),
])
def test_runner_diagnostics_report_decisions_without_commands(tmp_path, monkeypatch, mode, command, decision, ids):
    project = project_at(tmp_path, mode)
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    result, code = runner.run("PreToolUse", json.dumps(shell_payload(command)).encode(), project)
    assert code == 0
    assert denied(result) is (decision == "denied")
    records = (project.state / "hook-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in records] == [{"event": "PreToolUse", "checks": ids, "decision": decision}]


def test_runner_diagnostics_are_off_by_default(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    monkeypatch.delenv("RO_HOOK_DIAGNOSTICS", raising=False)
    result, code = runner.run("PreToolUse", json.dumps(shell_payload("worker &")).encode(), project)
    assert code == 0 and denied(result)
    assert not (project.state / "hook-diagnostics.jsonl").exists()


@pytest.mark.parametrize("mode,command,decision,ids", [
    ("block", "worker &", "denied", ["shell.background"]),
    ("warn", "worker &", "warned", ["shell.background"]),
    ("block", "echo ready", "no hook decision", []),
])
def test_project_marker_enables_diagnostics_without_environment(tmp_path, monkeypatch, mode, command, decision, ids):
    project = project_at(tmp_path, mode)
    project.state.mkdir(exist_ok=True)
    marker = project.state / "hook-diagnostics.on"
    marker.touch()
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.delenv("RO_HOOK_DIAGNOSTICS", raising=False)
    payload = {"workdir": str(nested), "tool_name": "Bash", "input": {"command": command}}
    result, code = runner.run("PreToolUse", json.dumps(payload).encode(), project)
    assert code == 0 and denied(result) is (decision == "denied")
    log = project.state / "hook-diagnostics.jsonl"
    recorded = log.read_text(encoding="utf-8")
    assert [json.loads(line) for line in recorded.splitlines()] == [
        {"event": "PreToolUse", "checks": ids, "decision": decision}]
    assert not (nested / ".ro").exists()
    marker.unlink()
    runner.run("PreToolUse", json.dumps(payload).encode(), project)
    assert log.read_text(encoding="utf-8") == recorded


def test_project_marker_records_malformed_input_without_changing_fail_open(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    project.state.mkdir(exist_ok=True)
    (project.state / "hook-diagnostics.on").touch()
    monkeypatch.delenv("RO_HOOK_DIAGNOSTICS", raising=False)
    result, code = runner.run("PreToolUse", b"invalid json", project)
    assert code == 0 and not denied(result)
    assert json.loads((project.state / "hook-diagnostics.jsonl").read_text()) == {
        "event": "PreToolUse", "checks": ["hooks.failure"], "decision": "unknown"}


def test_runner_diagnostics_append_once_per_call_and_ignore_session_brief(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    for event in ("SessionStart", "PreToolUse", "PreToolUse"):
        result, code = runner.run(event, json.dumps(shell_payload("worker &")).encode(), project)
        assert code == 0
        assert denied(result) is (event == "PreToolUse")
    records = [json.loads(line) for line in (project.state / "hook-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records == [{"event": "SessionStart", "checks": [], "decision": "no hook decision"},
                       *[{"event": "PreToolUse", "checks": ["shell.background"], "decision": "denied"}] * 2]


@pytest.mark.parametrize("raw", [b"{}", b"invalid json"])
def test_runner_diagnostics_record_fail_open_as_unknown(tmp_path, monkeypatch, raw):
    project = project_at(tmp_path)
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    result, code = runner.run("PreToolUse", raw, project, interpreter=str(tmp_path / "missing.exe"))
    assert code == 0 and not denied(result)
    records = (project.state / "hook-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in records] == [
        {"event": "PreToolUse", "checks": ["hooks.failure"], "decision": "unknown"}]


@pytest.mark.parametrize("event", ["PreToolUse", "SessionStart"])
def test_runner_diagnostics_recognize_child_fail_open_response(tmp_path, monkeypatch, event):
    project = project_at(tmp_path)
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    response = hooks.response(event, [], ["hooks.failure: hooks inactive: ValueError"])
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, json.dumps(response).encode()))
    assert runner.run(event, b"{}", project) == (response, 0)
    records = (project.state / "hook-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in records] == [
        {"event": event, "checks": ["hooks.failure"], "decision": "unknown"}]


def test_runner_diagnostics_write_failure_preserves_denial(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    project.state.mkdir(exist_ok=True)
    (project.state / "hook-diagnostics.jsonl").mkdir()
    result, code = runner.run("PreToolUse", json.dumps(shell_payload("worker &")).encode(), project)
    assert code == 0 and denied(result)


def test_runner_diagnostics_denial_ids_exclude_warned_checks(tmp_path, monkeypatch):
    project = project_at(tmp_path, selected="shell.background")
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    result, code = runner.run("PreToolUse", json.dumps(shell_payload("nohup worker &")).encode(), project)
    assert code == 0 and denied(result) and warned(result)
    assert "shell.detach:" in result["hookSpecificOutput"]["additionalContext"]
    records = (project.state / "hook-diagnostics.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in records] == [
        {"event": "PreToolUse", "checks": ["shell.background"], "decision": "denied"}]


def test_runner_diagnostics_follow_payload_project_root(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.setenv("RO_HOOK_DIAGNOSTICS", "1")
    payload = shell_payload("worker &", cwd=str(nested))
    result, code = runner.run("PreToolUse", json.dumps(payload).encode(), project)
    assert code == 0 and denied(result)
    assert (project.state / "hook-diagnostics.jsonl").exists()
    assert not (nested / ".ro" / "hook-diagnostics.jsonl").exists()


@pytest.mark.parametrize("context", [True, False])
@pytest.mark.parametrize("uncertain", [False, True])
def test_same_text_job_warnings_distinguish_jobs_and_paths(tmp_path, context, uncertain):
    project = project_at(tmp_path, "warn")
    values = configured("warn")
    first = {"id": "J-A-0001", "status": "running", "run_dir": str(tmp_path / "run")}
    second = {**first, "id": "J-A-0002"}
    payload = {"supports_additional_context": context}
    for jobs, path in (([first], "run/first.txt"), ([first], "run/second.txt"), ([second], "run/first.txt")):
        command = f"rm {path}" + ("; echo 'unfinished" if uncertain else "")
        findings = checks.pre_checks(checks.Call("shell", "bash", command), tmp_path, jobs, values)
        result = hooks._emit(project, "PreToolUse", findings, values, payload)
        if not context:
            assert result == {}
            result = hooks.hook(project, "PostToolUse", shell_payload("echo done"))
        assert result["hookSpecificOutput"]["additionalContext"].count("jobs.mutate-bound:") == 1
        assert hooks._emit(project, "PreToolUse", findings, values, payload) == {}
        if not context:
            assert hooks.hook(project, "PostToolUse", shell_payload("echo done")) == {}


def test_simultaneous_same_text_job_warnings_survive_state_failure(tmp_path, monkeypatch):
    project = project_at(tmp_path, "warn")
    jobs = [{"id": key, "status": "running", "run_dir": str(tmp_path / "run")}
            for key in ("J-A-0001", "J-A-0002")]
    findings = checks.path_checks(["run/input.txt"], "jobs.mutate-bound", tmp_path, jobs)
    assert len(findings) == 2
    def refuse(*args, **kwargs):
        raise PermissionError("unwritable")
    monkeypatch.setattr(project, "write_json", refuse)
    result = hooks._emit(project, "PreToolUse", findings + findings, configured("warn"), {})
    assert result["hookSpecificOutput"]["additionalContext"].count("jobs.mutate-bound:") == 2


def test_combined_hook_runs_all_checks_once_and_never_deduplicates_blocks(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    calls = []
    parse = hooks.command_parts
    monkeypatch.setattr(hooks, "command_parts", lambda *args: (calls.append("parse"), parse(*args))[1])
    monkeypatch.setattr(evidence, "scan_publish", lambda *args, **kwargs: (calls.append("scan"), ["Staged match."])[1])
    payload = shell_payload("worker & release-tool publish artifact.txt; git push")
    for _ in range(2):
        result = hooks.hook(project, "PreToolUse", payload)
        assert denied(result)
        reason = result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "shell.background" in reason and "external.gate" in reason and "publish.scan" not in reason
    assert calls == ["parse", "scan", "parse", "scan"]


def test_staged_push_precheck_only_warns_but_outgoing_history_still_blocks(tmp_path, monkeypatch):
    project = project_at(tmp_path, selected="publish.scan")
    monkeypatch.setattr(evidence, "scan_publish", lambda *args, **kwargs: ["Pattern matched."])
    result = hooks.hook(project, "PreToolUse", shell_payload("git push"))
    assert warned(result) and not denied(result)
    assert denied(hooks.hook(project, "pre-push", {}, refs="outgoing refs"))


def test_host_without_context_gets_warning_log_then_posttool_context(tmp_path) -> None:
    project = project_at(tmp_path / "logged-warnings", "warn")
    result = hooks.hook(project, "PreToolUse", shell_payload("worker &", supports_additional_context=False))
    assert result == {}
    assert "shell.background" in (project.state / "warnings.log").read_text(encoding="utf-8")
    post = hooks.hook(project, "PostToolUse", shell_payload("echo done"))
    assert "shell.background" in post["hookSpecificOutput"]["additionalContext"]
    assert hooks.hook(project, "PostToolUse", shell_payload("echo done")) == {}
    hooks.hook(project, "PreToolUse", shell_payload("cd scratch", supports_additional_context=False))
    post = hooks.hook(project, "PostToolUse", shell_payload("echo done"))
    assert "shell.cd" in str(post) and "shell.background" not in str(post)


def test_failure_logs_and_exposes_inactive_self_test_without_unrelated_block(tmp_path) -> None:
    project = project_at(tmp_path / "failed-hook")
    result = hooks.failure(project, "PreToolUse", shell_payload("echo done"), "RuntimeError")
    assert not denied(result)
    assert project.read_json("hooks-self-test.json")["status"] == "inactive"
    assert "RuntimeError" in (project.state / "warnings.log").read_text(encoding="utf-8")
    from ro_records import brief
    assert "RuntimeError" in brief(project)


@pytest.mark.parametrize("check", ["publish.scan", "external.gate"])
def test_per_call_protected_failure_routes_fail_open(tmp_path, check) -> None:
    project = project_at(tmp_path / "protected-failure", selected=check)
    action = "git push" if check == "publish.scan" else "release-tool publish artifact.txt"
    result = hooks.failure(project, "PreToolUse", shell_payload(action), "timeout", check)
    assert not denied(result)


def test_external_calls_require_the_wrapper_and_required_agent_lines_are_checked(tmp_path) -> None:
    values = configured()
    direct = checks.pre_checks(checks.Call("shell", "bash", "release-tool publish artifact.txt"), tmp_path, [], values)
    assert any(f.check == "external.gate" for f in direct)
    absolute = checks.pre_checks(checks.Call("shell", "powershell", "& 'H:/bin/release-tool.exe' publish artifact.txt"),
                                 tmp_path, [], values)
    assert any(f.check == "external.gate" for f in absolute)
    wrapped = checks.pre_checks(checks.Call("shell", "bash", "python ro.py external -- release-tool publish artifact.txt"),
                                tmp_path, [], values)
    assert not any(f.check == "external.gate" for f in wrapped)
    values["brief_requirements"] = "reviewer: Contract: C-01"
    agent = checks.Call("Agent", agent_type="reviewer", prompt="Review this artifact")
    assert any(f.check == "brief.requirements" for f in checks.pre_checks(agent, tmp_path, [], values))
    agent.prompt += "\nContract: C-01"
    assert checks.pre_checks(agent, tmp_path, [], values) == []


@pytest.mark.parametrize("command,dialect", [
    ("python tools/ro.py --project workspace --slot A --session fixture external -- release-tool publish artifact.txt", "bash"),
    ("env MODE=test python3 -S tools/ro.py --session fixture --project=workspace --slot=A external -- release-tool publish artifact.txt", "bash"),
    ("ro --project workspace --slot A --session fixture external -- release-tool publish artifact.txt", "bash"),
    ("& 'tools/ro.cmd' --project workspace --slot A --session fixture external -- release-tool publish artifact.txt", "powershell"),
    ("py -3 tools/ro.py --session fixture --slot A --project workspace external -- release-tool publish artifact.txt", "powershell"),
])
def test_external_regex_does_not_deny_sanctioned_wrapper_with_global_options(tmp_path, command, dialect):
    values = configured(shell=dialect)
    values["external_actions"] = "regex:release-tool publish"
    findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, [], values)
    assert not any(f.check == "external.gate" for f in findings)


@pytest.mark.parametrize("command", [
    "release-tool publish artifact.txt",
    "release-tool publish ro.py external artifact.txt",
    "python worker.py ro.py external release-tool publish artifact.txt",
    "python tools/ro.py --project workspace --slot A check-command release-tool publish artifact.txt",
    "python tools/ro.py --project workspace --slot A external -- safe-tool; release-tool publish artifact.txt",
    "ro --project --slot A external -- release-tool publish artifact.txt",
])
def test_external_regex_still_gates_direct_and_lookalike_calls(tmp_path, command):
    values = configured()
    values["external_actions"] = "regex:release-tool publish"
    findings = checks.pre_checks(checks.Call("shell", "bash", command), tmp_path, [], values)
    assert any(f.check == "external.gate" for f in findings)


@pytest.mark.parametrize("tool", ["Edit", "Write", "NotebookEdit", "Bash"])
def test_posttool_detects_new_future_dates_and_duplicate_ids_after_mtime_changes(tmp_path, monkeypatch, tool) -> None:
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 25, 12)
    monkeypatch.setattr(hooks.dt, "datetime", Clock)
    project = project_at(tmp_path / "changed-records", "warn")
    record = project.root / "discoveries.md"
    record.write_text("# Discoveries\n", encoding="utf-8")
    hooks._snapshot(project, report=False)
    future = (dt.datetime.now() + dt.timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M")
    record.write_text(f"# Discoveries\n### D-A-001 — first\n- Date: {future}\n### D-A-001 — duplicate\n",
                      encoding="utf-8")
    payload = {"tool_name": tool, "tool_input": {"file_path": str(record), "command": "echo changed"}}
    result = hooks.hook(project, "PostToolUse", payload)
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "records.timestamp" in context and "records.id" in context
    assert hooks.hook(project, "PostToolUse", payload) == {}


@pytest.mark.parametrize("change", ["date", "record", "file"])
def test_future_timestamp_warnings_distinguish_dates_records_and_files(tmp_path, change):
    project = project_at(tmp_path, "warn")
    record = project.root / "discoveries.md"
    future = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    first = f"# Discoveries\n### D-A-001 first\n- Date: {future}\n"
    record.write_text(first, encoding="utf-8")
    payload = json.dumps(shell_payload("echo changed")).encode()
    result = runner.run("PostToolUse", payload, project)[0]
    assert result["hookSpecificOutput"]["additionalContext"].count("records.timestamp:") == 1
    if change == "date":
        later = (dt.datetime.now() + dt.timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
        record.write_text(first.replace(future, later), encoding="utf-8")
    elif change == "record":
        record.write_text(first + f"### D-A-002 second\n- Date: {future}\n", encoding="utf-8")
    else:
        (project.root / "handoff.md").write_text(f"# Handoff\n### N-A-001 note\n- Date: {future}\n", encoding="utf-8")
    result = runner.run("PostToolUse", payload, project)[0]
    assert result["hookSpecificOutput"]["additionalContext"].count("records.timestamp:") == 1
    assert runner.run("PostToolUse", payload, project)[0] == {}


def test_simultaneous_future_timestamps_are_both_shown(tmp_path):
    project = project_at(tmp_path, "warn")
    dates = [(dt.datetime.now() + dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M") for days in (1, 2)]
    (project.root / "discoveries.md").write_text(
        f"### D-A-001 first\n- Date: {dates[0]}\n### D-A-002 second\n- Date: {dates[1]}\n", encoding="utf-8")
    result = hooks.hook(project, "PostToolUse", shell_payload("echo changed"))
    assert result["hookSpecificOutput"]["additionalContext"].count("records.timestamp:") == 2
    assert hooks.hook(project, "PostToolUse", shell_payload("echo changed")) == {}


def test_posttool_unchanged_snapshot_is_stat_only_and_skips_child(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    for name in hooks.FILES[1:]:
        (tmp_path / name).write_text("# Records\n", encoding="utf-8")
    hooks._snapshot(project, report=False)
    runner._RECORD_CACHE.clear()
    opened = []
    original = builtins.open

    def record_open(path, *args, **kwargs):
        opened.append(Path(path).name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", record_open)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("unchanged PostToolUse launched a child"))
    payload = json.dumps(shell_payload("echo ready")).encode()
    assert runner.run("PostToolUse", payload, project) == ({}, 0)
    assert opened == ["records-hook.json"]
    opened.clear()
    assert runner.run("PostToolUse", payload, project) == ({}, 0)
    assert opened == []


@pytest.mark.parametrize("change", ["mtime", "size", "added", "removed", "warning", "snapshot", "legacy", "shape"])
def test_posttool_quiet_snapshot_invalidates_before_skipping_work(tmp_path, change):
    project = project_at(tmp_path)
    record = tmp_path / "discoveries.md"
    record.write_text("# Records\n", encoding="utf-8")
    hooks._snapshot(project, report=False)
    assert runner.quiet("PostToolUse", {}, tmp_path)
    if change == "mtime":
        stat = record.stat()
        os.utime(record, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    elif change == "size":
        stat = record.stat()
        record.write_text("# Records\nnew content\n", encoding="utf-8")
        os.utime(record, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    elif change == "added":
        (tmp_path / "handoff.md").write_text("# Handoff\n", encoding="utf-8")
    elif change == "removed":
        record.unlink()
    elif change == "warning":
        (project.state / "warnings.log").write_text("pending warning\n", encoding="utf-8")
    elif change == "snapshot":
        (project.state / "records-hook.json").write_text("invalid JSON", encoding="utf-8")
    else:
        previous = project.read_json("records-hook.json")
        if change == "legacy":
            previous["agents.md"]["parser"] = 1
        else:
            previous["agents.md"].pop("ids")
        project.write_json("records-hook.json", previous)
    assert not runner.quiet("PostToolUse", {}, tmp_path)


def test_changed_posttool_records_still_report_then_resume_quiet_path(tmp_path):
    project = project_at(tmp_path, "warn")
    hooks._snapshot(project, report=False)
    assert runner.quiet("PostToolUse", {}, tmp_path)
    future = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    (tmp_path / "discoveries.md").write_text(f"### D-A-001 record\n- Date: {future}\n", encoding="utf-8")
    reply, code = runner.run("PostToolUse", json.dumps(shell_payload("echo changed")).encode(), project)
    assert code == 0 and "records.timestamp" in str(reply)
    assert runner.quiet("PostToolUse", {}, tmp_path)


def test_status_log_and_heartbeat_reads_are_allowed(tmp_path) -> None:
    job = {"status": "running", "run_dir": str(tmp_path / "run"), "bound": [str(tmp_path / "run")]}
    for filename in ("status.json", "worker.log", "heartbeat", "heartbeat-current"):
        assert checks.path_checks(["run/" + filename], "jobs.read-bound", tmp_path, [job]) == [], filename


def test_job_read_warnings_are_opt_in_without_changing_mutation_protection(tmp_path):
    import ro_settings as settings
    values = settings.resolve({}, None, configured())
    assert values["read_bound"] == "off"
    job = {"status": "running", "run_dir": str(tmp_path / "run"), "bound": [str(tmp_path / "run")]}
    for enabled in ("off", "on"):
        values["read_bound"] = enabled
        for call in (checks.Call("shell", "bash", "cat run/output.txt"), checks.Call("Read", paths=["run/output.txt"])):
            findings = checks.pre_checks(call, tmp_path, [job], values)
            assert bool(findings) is (enabled == "on")
            assert all(f.check == "jobs.read-bound" for f in findings)
        assert [f.check for f in checks.pre_checks(checks.Call("Write", paths=["run/input.txt"]),
                                                  tmp_path, [job], values)] == ["jobs.mutate-bound"]


def test_session_start_reuses_only_fresh_checker_results_with_unchanged_inputs(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import ro_records as records
    import ro_settings as settings
    project = project_at(tmp_path)
    calls = []
    monkeypatch.setattr(records, "_checker", lambda p: (calls.append(p), (SimpleNamespace(issues=[]), 0))[1])
    def start():
        assert "Checker: ERROR 0; WARN 0; INFO 0" in str(hooks.hook(project, "SessionStart", {}))
    start()
    start()
    assert len(calls) == 1
    for name in (*hooks.FILES, ".ro/checker-baseline.json", str(settings.TRANSACTION)):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        start()
    assert len(calls) == 1 + len(hooks.FILES) + 2
    previous = len(calls)
    clock = records.time.time()
    monkeypatch.setattr(records.time, "time", lambda: clock + 61)
    start()
    assert len(calls) == previous + 1
    project.write_json("checker-brief.json", {"stamp": "invalid"})
    start()
    assert len(calls) == previous + 2


@pytest.mark.parametrize("status", ["error", "attention"])
def test_live_job_inputs_stay_protected_after_a_monitor_signal(tmp_path, status) -> None:
    job = {"status": status, "pid": os.getpid(), "start": process_start(os.getpid()),
           "run_dir": str(tmp_path / "run"), "bound": [str(tmp_path / "run")]}
    findings = checks.path_checks(["run/input.txt"], "jobs.mutate-bound", tmp_path, [job])
    assert findings and all(f.check == "jobs.mutate-bound" for f in findings)


def test_fifty_clean_stops_emit_at_most_one_warning(tmp_path) -> None:
    project = project_at(tmp_path / "clean-stops")
    replies = [hooks.hook(project, "Stop", {"turn_id": str(turn)}) for turn in range(50)]
    assert sum(warned(reply) or denied(reply) for reply in replies) <= 1


def test_stop_blocks_once_per_unmonitored_job_then_warns(tmp_path) -> None:
    project = project_at(tmp_path / "stop-once", selected="jobs.unmonitored")
    project.write_json("jobs.json", [{"id": "J-A-0001", "slot": "A", "pid": os.getpid(),
                                     "start": process_start(os.getpid()), "status": "running", "monitor": None}])
    first = hooks.hook(project, "Stop", {"turn_id": "same-turn"})
    assert denied(first)
    assert "jobs.unmonitored" in first["reason"]
    second = hooks.hook(project, "Stop", {"turn_id": "same-turn"})
    assert not denied(second) and warned(second)
    project.write_json("jobs.json", project.read_json("jobs.json") + [{"id": "J-A-0002", "slot": "A",
                       "pid": os.getpid(), "start": process_start(os.getpid()), "status": "running", "monitor": None}])
    new_job = hooks.hook(project, "Stop", {"turn_id": "same-turn"})
    assert denied(new_job) and "J-A-0002" in new_job["reason"] and "J-A-0001" not in new_job["reason"]
    assert not denied(hooks.hook(project, "Stop", {"turn_id": "next-turn"}))
    # Reconstructing the adapter does not reset this session's block-once record.
    reloaded = Project(project.root, slot="A", session=project.session)
    assert warned(hooks.hook(reloaded, "Stop", {}))
    assert not denied(hooks.hook(reloaded, "Stop", {}))
    fresh_session = Project(project.root, slot="A", session="another-hook-session")
    assert denied(hooks.hook(fresh_session, "Stop", {}))


@pytest.mark.parametrize("mode,selected", [("block", "jobs.unmonitored"), ("warn", "jobs.unmonitored"),
                                          ("block", "shell.background"), ("off", "jobs.unmonitored")])
def test_stop_checks_ended_job_outcomes_on_every_attempt(tmp_path, mode, selected) -> None:
    import ro_jobs

    project = project_at(tmp_path, mode=mode, selected=selected)
    entry = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "status": "finished",
             "outcome": "process exited with code 0", "monitor": {"active": False, "ended": 1}}
    project.write_json("jobs.json", [entry, {"id": "J-B-0002", "slot": "B", "status": "finished"}])
    for attempt, payload in enumerate(({"turn_id": "same-turn"}, {"turn_id": "same-turn"}, {}, {})):
        reply = hooks.hook(project, "Stop", payload)
        if mode == "off":
            assert reply == {}
        else:
            assert denied(reply) == (attempt == 0 and mode == "block" and selected == "jobs.unmonitored")
            assert "J-A-0001" in str(reply) and "J-B-0002" not in str(reply)
            assert "record the outcome, then close" in str(reply)
    ro_jobs.monitor(project, entry["id"])
    assert hooks.hook(project, "Stop", {"turn_id": "same-turn"}) == {}


def test_live_monitor_makes_fifty_stops_silent(tmp_path) -> None:
    project = project_at(tmp_path / "monitored-stops")
    identity = process_start(os.getpid())
    project.write_json("jobs.json", [{"id": "J-A-0001", "slot": "A", "pid": os.getpid(), "start": identity,
                                     "status": "running", "monitor": {"pid": os.getpid(), "start": identity,
                                                                          "active": True}}])
    assert all(hooks.hook(project, "Stop", {"turn_id": str(turn)}) == {} for turn in range(50))


@pytest.mark.parametrize("raw", [b"{", b"[]", b"\xff", b"x" * (hooks.MAX_INPUT + 1)],
                         ids=["invalid-json", "array-root", "invalid-utf8", "oversized"])
def test_malformed_and_oversized_stdin_fails_open_even_for_protected_matcher(tmp_path, capsys, raw) -> None:
    project = project_at(tmp_path / "bad-input")
    args = ro.parser().parse_args(["--project", str(project.root), "hook", "PreToolUse", "--check", "external.gate"])
    assert ro.hook_main(args, raw) == 0
    reply = json.loads(capsys.readouterr().out)
    assert not denied(reply)


@pytest.mark.parametrize("payload,dialect,tool,path", [
    ({"tool_name": "Bash", "tool_input": {"command": "echo done"}}, "bash", "shell", None),
    ({"tool_name": "PowerShell", "tool_input": {"command": "& tool"}}, "powershell", "shell", None),
    ({"tool_name": "shell", "tool_input": {"command": ["pwsh", "-c", "& tool"]}}, "powershell", "shell", None),
    ({"tool_name": "shell", "tool_input": {"shell": "powershell", "cmd": "& tool"}}, "powershell", "shell", None),
    ({"tool_name": "apply_patch", "tool_input": "*** Begin Patch\n*** Update File: run/worker.py\n*** End Patch"},
     "bash", "Edit", "run/worker.py"),
    ({"tool_name": "Read", "tool_input": {"file_path": "run/status.json"}}, "bash", "Read", "run/status.json"),
])
def test_host_adapters_normalize_tool_names_and_paths(payload, dialect, tool, path) -> None:
    call = checks.adapt(payload)
    assert call.dialect == dialect and call.tool == tool
    if path:
        assert path in call.paths


CODEX_CASES = json.loads((FIXTURES / "codex-hooks" / "representative-payloads.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CODEX_CASES, ids=lambda case: case["id"])
def test_codex_payloads_reach_checks_through_supervisor_and_cli(tmp_path, capsys, case):
    project = project_at(tmp_path / "codex")
    rules = project.root / "agents.md"
    rules.write_text(rules.read_text(encoding="utf-8").replace("/bash", "/" + case["dialect"]), encoding="utf-8")
    fallback = project_at(tmp_path / "fallback", "off")
    run_dir = project.root / "run"
    run_dir.mkdir()
    target = run_dir / "input.txt"
    target.write_text("before", encoding="utf-8")
    project.write_json("jobs.json", [{"id": "J-A-0001", "status": "running", "pid": os.getpid(),
                                     "start": process_start(os.getpid()), "run_dir": str(run_dir), "bound": [str(target)]}])
    raw = json.dumps(case["payload"]).replace("$PROJECT", json.dumps(str(project.root))[1:-1]).encode()
    result, code = runner.run("PreToolUse", raw, fallback)
    assert code == 0 and denied(result), result
    assert case["check"] + ":" in result["hookSpecificOutput"]["permissionDecisionReason"]
    # The command-only fallback consumes the same host payload, too.
    args = ro.parser().parse_args(["--project", str(fallback.root), "hook", "PreToolUse"])
    assert ro.hook_main(args, raw) == 0
    assert denied(json.loads(capsys.readouterr().out))
    assert target.read_text(encoding="utf-8") == "before"


CAPTURED_CODEX = next(case["payload"] for case in CODEX_CASES if case["id"] == "codex-captured-powershell-background")


@pytest.mark.parametrize("shell", ["powershell", "bash"])
def test_codex_bash_tool_uses_the_declared_shell_but_claude_bash_stays_bash(shell):
    values = configured(shell=shell)
    codex = hooks.host_call(CAPTURED_CODEX, values)
    assert codex.tool == "shell" and codex.dialect == shell
    claude = {key: value for key, value in CAPTURED_CODEX.items() if key != "turn_id"}
    assert hooks.host_call(claude, values).dialect == "bash"
    # An explicit shell field or argv shell wrapper remains authoritative.
    explicit = {**CAPTURED_CODEX, "tool_input": {"command": "echo probe &", "shell": "bash"}}
    assert hooks.host_call(explicit, values).dialect == "bash"
    argv = {**CAPTURED_CODEX, "tool_input": {"command": ["bash", "-lc", "echo probe &"]}}
    assert hooks.host_call(argv, values).dialect == "bash"


def test_captured_codex_powershell_calls_are_enforced_and_claude_bash_is_not_reinterpreted(tmp_path):
    project = project_at(tmp_path)
    rules = project.root / "agents.md"
    rules.write_text(rules.read_text(encoding="utf-8").replace("/bash", "/powershell"), encoding="utf-8")
    payload = json.loads(json.dumps(CAPTURED_CODEX).replace("$PROJECT", json.dumps(str(project.root))[1:-1]))
    result = hooks.hook(project, "PreToolUse", payload)
    assert denied(result) and "shell.background:" in result["hookSpecificOutput"]["permissionDecisionReason"]
    # Claude Code's Bash keeps Bash grammar, including its own background operator.
    claude = {key: value for key, value in payload.items() if key != "turn_id"}
    assert denied(hooks.hook(project, "PreToolUse", claude))


def test_hook_self_test_exercises_the_codex_bash_shape(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    assert hooks.self_test(project)["status"] == "active"
    original = hooks.host_call
    monkeypatch.setattr(hooks, "host_call", lambda payload, values: (
        checks.adapt(payload) if "turn_id" in payload and values["environment"].endswith("/powershell")
        else original(payload, values)))
    rules = project.root / "agents.md"
    rules.write_text(rules.read_text(encoding="utf-8").replace("/bash", "/powershell"), encoding="utf-8")
    assert hooks.self_test(project) == {"status": "inactive", "reason": "ValueError"}


@pytest.mark.parametrize("raw_input", [
    {"command": "echo ready"}, "echo ready", {"command": "echo ready", "run_in_background": True},
])
def test_claude_canonical_payload_is_forwarded_unchanged(tmp_path, monkeypatch, raw_input):
    project = project_at(tmp_path)
    payload = {"cwd": str(project.root), "session_id": "claude-session", "tool_name": "Bash", "tool_input": raw_input,
               "workdir": None, "arguments": {"command": "worker &"}}
    raw = json.dumps(payload, indent=2).encode()
    seen = []

    def child(command, **kwargs):
        seen.append((kwargs["input"], kwargs["cwd"]))
        return subprocess.CompletedProcess(command, 0, b"{}")

    monkeypatch.setattr(subprocess, "run", child)
    assert runner.run("PreToolUse", raw, project) == ({}, 0)
    assert seen == [(raw, str(project.root))]


@pytest.mark.parametrize("payload", [
    {"tool_name": "Bash", "tool_input": {"command": ["bash", None, "worker &"]}},
    {"tool_name": "Bash", "workdir": []},
    {"tool_name": "Bash", "tool_input": None, "arguments": {"command": "worker &"}},
])
def test_invalid_codex_payloads_remain_visible_fail_open(tmp_path, payload):
    project = project_at(tmp_path)
    result, code = runner.run("PreToolUse", json.dumps(payload).encode(), project)
    assert code == 0 and not denied(result) and warned(result)
    assert "hooks inactive" in result["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("argv", [["printf", "%s", "&"], ["printf", "-c", "worker &"],
                                   ["python", "-c", "worker &"]])
def test_argv_data_does_not_become_a_shell_operator(tmp_path, argv):
    project = project_at(tmp_path)
    payload = {"tool_name": "Bash", "input": argv}
    assert runner.run("PreToolUse", json.dumps(payload).encode(), project) == ({}, 0)


def test_codex_background_flag_survives_normalization(tmp_path):
    project = project_at(tmp_path)
    payload = {"tool_name": "Bash", "arguments": {"command": ["bash", "-lc", "worker &"], "background": True}}
    assert runner.run("PreToolUse", json.dumps(payload).encode(), project) == ({}, 0)


@pytest.mark.parametrize("command,blocked", [("printf '%s\\n' ready && echo done", False),
                                           ("python worker.py &", True)])
def test_pretool_does_not_open_history_files(tmp_path, monkeypatch, command, blocked) -> None:
    project = project_at(tmp_path)
    history = {project.root / name for name in ("discoveries.md", "handoff.md")}
    for path in history:
        path.write_text("history\n", encoding="utf-8")
    attempted = []

    def guard_open(original):
        def checked_open(file, *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)):
                path = Path(os.fsdecode(file)).resolve()
                if path in history:
                    attempted.append(path)
                    raise AssertionError(f"PreToolUse opened history: {path.name}")
            return original(file, *args, **kwargs)
        return checked_open

    # pathlib delegates to io.open; also cover direct builtin/stream opens.
    monkeypatch.setattr(builtins, "open", guard_open(builtins.open))
    monkeypatch.setattr(io, "open", guard_open(io.open))
    result = hooks.hook(project, "PreToolUse", shell_payload(command))
    assert attempted == []  # Still fails if a hook catches the read exception.
    if blocked:
        assert denied(result)
        assert "shell.background:" in result["hookSpecificOutput"]["permissionDecisionReason"]
    else:
        assert result == {}


@pytest.mark.latency
def test_pretool_latency_does_not_depend_on_large_coordination_files(tmp_path) -> None:
    project = project_at(tmp_path / "large-project")
    (project.root / "discoveries.md").write_text("fact\n" * 280000, encoding="utf-8")
    (project.root / "handoff.md").write_text("event\n" * 83334, encoding="utf-8")
    payload = shell_payload("printf '%s\\n' ready && echo done")
    samples = []
    for _ in range(100):
        start = time.perf_counter()
        assert hooks.hook(project, "PreToolUse", payload) == {}
        samples.append(time.perf_counter() - start)
    p95 = sorted(samples)[94]
    assert p95 < .150, f"in-process hook p95 {p95 * 1000:.1f} ms >= 150 ms"
    # Include the production child's -E -S startup policy, parsing and JSON output.
    # Inherited PYTHONDONTWRITEBYTECODE otherwise defeats the per-user cache being measured.
    def invoke(baseline=False):
        args = ["-c", "pass"] if baseline else [str(SCRIPTS / "ro.py"), "--project", str(project.root),
                                                "hook", "PreToolUse"]
        result = subprocess.run([sys.executable, "-E", "-S", *args], input=json.dumps(payload), capture_output=True,
                                text=True, encoding="utf-8", timeout=10)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "" if baseline else json.loads(result.stdout) == {}, result.stderr
    # Compile into the isolated user cache before measuring repeated hook latency.
    for _ in range(2):
        invoke(baseline=True)
        invoke()
    batches = []
    baseline_batches = []
    for _ in range(3):
        process_samples = []
        baseline_samples = []
        for _ in range(20):
            # Adjacent calls share runner load; both include identical interpreter flags and pipes.
            start = time.perf_counter()
            invoke(baseline=True)
            baseline_samples.append(time.perf_counter() - start)
            start = time.perf_counter()
            invoke()
            process_samples.append(time.perf_counter() - start)
        batches.append(sorted(process_samples)[18])
        baseline_batches.append(sorted(baseline_samples)[18])
    p95_process = sorted(batches)[1]
    p95_baseline = sorted(baseline_batches)[1]
    overhead = p95_process - p95_baseline
    print(f"\nLATENCY subprocess hook p95={p95_process * 1000:.1f} ms; "
          f"interpreter p95={p95_baseline * 1000:.1f} ms; overhead={overhead * 1000:.1f} ms")
    if destination := os.environ.get("RO_LATENCY_REPORT"):
        path = Path(destination)
        report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        report["subprocess"] = {
            "layer": "direct-child", "samples_per_batch": 20, "warmups": 2,
            "batch_p95_ms": [value * 1000 for value in batches],
            "baseline_batch_p95_ms": [value * 1000 for value in baseline_batches],
            "p95_ms": p95_process * 1000, "baseline_p95_ms": p95_baseline * 1000,
            "overhead_ms": overhead * 1000, "overhead_budget_ms": 150, "absolute_budget_ms": 300,
            "in_process_p95_ms": p95 * 1000, "hook_output_correct": True,
            "passed": overhead < .150 and p95_process < .300,
        }
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert overhead < .150, (f"subprocess hook p95 {p95_process * 1000:.1f} ms minus interpreter "
                             f"baseline p95 {p95_baseline * 1000:.1f} ms = {overhead * 1000:.1f} ms "
                             ">= 150 ms overhead budget")
    assert p95_process < .300, f"subprocess hook p95 {p95_process * 1000:.1f} ms >= 300 ms absolute ceiling"


@pytest.fixture
def live_jobs(tmp_path):
    run = tmp_path / "runs" / "job-a"
    run.mkdir(parents=True)
    (run / "input.txt").write_text("bound input", encoding="utf-8")
    return [{"id": "J-A-0001", "status": "running", "pid": os.getpid(), "start": process_start(os.getpid()),
             "run_dir": str(run), "bound": [str(run)]}]


def inspect(tmp_path, live_jobs, command, dialect="bash"):
    return checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, live_jobs,
                             {"external_actions": "none", "environment": f"{'windows' if os.name == 'nt' else 'linux'}/{dialect}"})


def mutations(findings):
    return [finding for finding in findings if finding.check == "jobs.mutate-bound"]


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["cp safe.txt runs/job-a/input.txt >copy.log", "cp safe.txt runs/job-a/input.txt 2>copy.log",
              "2>copy.log cp safe.txt runs/job-a/input.txt", "cp 2 runs/job-a/input.txt >copy.log"]),
    ("powershell", ["Copy-Item safe.txt runs/job-a/input.txt >copy.log"]),
])
def test_redirects_never_replace_copy_mutation_operands(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        assert any(not f.uncertain for f in mutations(inspect(tmp_path, live_jobs, command, dialect))), command


def test_redirect_destinations_are_checked_independently_of_copy_operands(tmp_path, live_jobs):
    for command in ("cp safe.txt destination.txt >runs/job-a/output.log",
                    "cp runs/job-a/input.txt safe.txt >runs/job-a/output.log"):
        assert any(not f.uncertain for f in mutations(inspect(tmp_path, live_jobs, command))), command


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["cp runs/job-a/input.txt safe.txt >copy.log", "cp runs/job-a/input.txt safe.txt 2>&1"]),
    ("powershell", ["Copy-Item -LiteralPath runs/job-a/input.txt -Destination safe.txt >copy.log"]),
])
def test_redirects_do_not_turn_copy_sources_into_mutation_targets(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        assert mutations(inspect(tmp_path, live_jobs, command, dialect)) == [], command


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["cd runs/job-a; rm input.txt", "(cd runs/job-a); rm runs/job-a/input.txt",
              "pushd runs/job-a; popd; rm input.txt",
              "2>change.log cd runs/job-a; rm input.txt", "env -C runs/job-a rm input.txt",
              "env --chdir=runs/job-a rm input.txt", "env --chdir runs/job-a rm input.txt",
              "git -c color.ui=false -C elsewhere status; rm runs/job-a/input.txt",
              "make -C elsewhere; rm runs/job-a/input.txt"]),
    ("powershell", ["Set-Location runs/job-a; Remove-Item input.txt",
                    "Set-Location runs/job-a | Write-Output; Remove-Item input.txt",
                    "Push-Location runs/job-a; Remove-Item input.txt",
                    "pushd elsewhere; Remove-Item runs/job-a/input.txt",
                    "cd elsewhere; Remove-Item runs/job-a/input.txt"]),
])
def test_any_directory_change_makes_relative_mutations_uncertain(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        findings = mutations(inspect(tmp_path, live_jobs, command, dialect))
        assert findings and all(f.uncertain for f in findings), command
        assert all(checks.outcome(f, {"enforcement": "block", "block": "jobs.mutate-bound"}) == "warn"
                   for f in findings), command


def test_directory_change_preserves_absolute_and_pre_change_relative_mutations(tmp_path, live_jobs):
    target = tmp_path / "runs" / "job-a" / "input.txt"
    for command in (f"cd elsewhere && rm '{target}'", "rm runs/job-a/input.txt && cd elsewhere"):
        findings = mutations(inspect(tmp_path, live_jobs, command))
        assert findings and all(not f.uncertain for f in findings), command
        assert all(checks.outcome(f, {"enforcement": "block", "block": "jobs.mutate-bound"}) == "block"
                   for f in findings), command


@pytest.mark.parametrize("dialect,remove", [("bash", "rm"), ("powershell", "Remove-Item")])
def test_literal_cd_and_chain_resolves_relative_bound_operands(tmp_path, live_jobs, dialect, remove):
    prefixes = ["cd runs/job-a", "cd 'runs/job-a'"] + (["cd -- runs/job-a"] if dialect == "bash" else [])
    for prefix in prefixes:
        command = f"{prefix} && echo ready && {remove} input.txt"
        findings = inspect(tmp_path, live_jobs, command, dialect)
        assert "shell.cd" not in {f.check for f in findings}
        assert mutations(findings) and all(not f.uncertain for f in mutations(findings))
    safe = inspect(tmp_path, live_jobs, f"cd elsewhere && {remove} input.txt", dialect)
    assert safe == []


def test_literal_cd_checks_redirect_in_original_directory_and_reads_in_new_directory(tmp_path, live_jobs):
    findings = inspect(tmp_path, live_jobs, "cd runs/job-a >runs/job-a/change.log && cat input.txt")
    assert any(f.check == "jobs.mutate-bound" and not f.uncertain for f in findings)
    values = configured()
    values["read_bound"] = "on"
    findings = checks.pre_checks(checks.Call("shell", "bash", "cd runs/job-a && cat input.txt"),
                                 tmp_path, live_jobs, values)
    assert any(f.check == "jobs.read-bound" and not f.uncertain for f in findings)


@pytest.mark.parametrize("command", ["cd $TARGET && rm input.txt", "cd one && cd two && rm input.txt",
                                      "cd runs/job-a || rm input.txt", "cd runs/job-a && echo ready; rm input.txt",
                                      "true || cd runs/job-a && rm input.txt",
                                      "echo ready | cd runs/job-a && rm input.txt",
                                      "env cd runs/job-a && rm input.txt", "CDPATH=elsewhere cd runs/job-a && rm input.txt"])
def test_uncertain_cd_chains_warn_without_bare_cd_noise(tmp_path, live_jobs, command):
    findings = inspect(tmp_path, live_jobs, command)
    assert "shell.cd" not in {f.check for f in findings}
    assert mutations(findings) and all(f.uncertain for f in mutations(findings))


@pytest.mark.parametrize("command,warns", [("cd scratch", True), ("echo ready && cd scratch", True),
                                          ("cd scratch && echo ready", False), ("(cd scratch)", False),
                                          ("cd scratch &", False), ("echo ready | cd scratch", False)])
def test_shell_cd_applies_only_to_bare_trailing_directory_changes(tmp_path, command, warns):
    findings = inspect(tmp_path, [], command)
    assert ("shell.cd" in {f.check for f in findings}) is warns


def test_opaque_cwd_wrapper_still_warns(tmp_path, live_jobs):
    target = tmp_path / "runs" / "job-a" / "input.txt"
    for command in (f"env -C elsewhere rm '{target}'",):
        findings = mutations(inspect(tmp_path, live_jobs, command))
        assert findings and all(f.uncertain and "uncertain parse" in f.message for f in findings), command


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["rm `runs/job-a/input.txt`", "rm $(echo runs/job-a/input.txt)"]),
    ("bash", ["alias rm='echo'; rm runs/job-a/input.txt"]),
    ("powershell", ["Set-Alias Remove-Item Write-Output; Remove-Item runs/job-a/input.txt"]),
    ("bash", ["(cleanup() { rm runs/job-a/input.txt; })"]),
], ids=["substitution", "alias", "powershell-alias", "function-definition"])
def test_opaque_definitions_and_substituted_paths_cannot_block(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        findings = inspect(tmp_path, live_jobs, command, dialect)
        assert all(checks.outcome(f, {"enforcement": "block", "block": "jobs.mutate-bound"}) != "block"
                   for f in findings), command


def test_descriptor_duplication_is_neither_background_nor_a_file_write(tmp_path, live_jobs):
    for command in ("cat <&0", "worker >&2", "worker 2>&1", "worker 2>&1-", "worker >&-"):
        assert inspect(tmp_path, live_jobs, command) == [], command


def test_bash_combined_descriptor_redirect_to_file_protects_bound_destination(tmp_path, live_jobs):
    for command in ("worker >&runs/job-a/output.log", "worker 1>&runs/job-a/output.log"):
        assert [f.check for f in inspect(tmp_path, live_jobs, command)] == ["jobs.mutate-bound"], command


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["cp unrelated.txt .", "cp unrelated.txt runs", "cp -t runs unrelated.txt", "cp -r unrelated-dir ."]),
    ("powershell", ["Copy-Item unrelated.txt .", "Copy-Item -Path unrelated.txt -Destination runs"]),
])
def test_copy_destinations_use_source_basenames_instead_of_blocking_ancestors(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        assert mutations(inspect(tmp_path, live_jobs, command, dialect)) == [], command


def test_copy_effective_destinations_still_protect_bound_files(tmp_path, live_jobs):
    live_jobs[0]["bound"] = [str(tmp_path / "runs" / "job-a" / "input.txt")]
    for command in ("cp input.txt runs/job-a", "cp -t runs/job-a input.txt", "cp -r job-a runs",
                    "cp -T safe.txt runs/job-a/input.txt"):
        assert any(not f.uncertain for f in mutations(inspect(tmp_path, live_jobs, command))), command


def test_file_operations_do_not_protect_unaffected_descendants(tmp_path, live_jobs):
    live_jobs[0]["bound"] = [str(tmp_path / "runs" / "job-a" / "input.txt")]
    for command in ("tee .", "echo ready >.", "rm runs"):
        assert mutations(inspect(tmp_path, live_jobs, command)) == [], command


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["rm -rf runs", "mv runs elsewhere", "rm -R runs"]),
    ("powershell", ["Remove-Item -Recurse runs"]),
])
def test_operations_that_can_affect_descendants_protect_bound_ancestors(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        assert any(not f.uncertain for f in mutations(inspect(tmp_path, live_jobs, command, dialect))), command


@pytest.mark.parametrize("mode,selected", itertools.product(("off", "warn", "block"), (False, True)))
def test_pre_push_failure_decision_survives_unwritable_diagnostics(tmp_path, monkeypatch, mode, selected):
    project = project_at(tmp_path, mode, "publish.scan" if selected else "none")
    def refuse(*args, **kwargs):
        raise PermissionError("unwritable")
    monkeypatch.setattr(hooks, "warning", refuse)
    monkeypatch.setattr(project, "write_json", refuse)
    result = hooks.failure(project, "pre-push", {}, "scan crash")
    assert denied(result) is (mode == "block" and selected)


@pytest.mark.parametrize("route", ["pre-push", "PreToolUse"])
def test_scan_exception_and_logging_failure_preserve_route_policy(tmp_path, monkeypatch, route):
    project = project_at(tmp_path, selected="publish.scan")
    def refuse(*args, **kwargs):
        raise PermissionError("unwritable")
    monkeypatch.setattr(evidence, "scan_publish", refuse)
    monkeypatch.setattr(hooks, "warning", refuse)
    result = hooks.hook(project, route, shell_payload("git push"), check="publish.scan")
    assert denied(result) is (route == "pre-push")
    assert "publish.scan" in str(result)


@pytest.mark.parametrize("count,setting,retry", [
    (20, "secrets", 122),
    (20, "secrets; deadline=2m", 240),
    (20, "secrets; deadline=60m", 3600),
    (None, "secrets", 120),
    (None, "secrets; deadline=2m", 240),
])
def test_pre_push_timeout_response_preserves_safe_recovery_details(tmp_path, monkeypatch, count, setting, retry):
    project = project_at(tmp_path, selected="publish.scan")
    policy = project.root / "agents.md"
    policy.write_text(policy.read_text(encoding="utf-8") + f"- Publish scan: {setting}\n", encoding="utf-8")
    private_detail = "synthetic-untrusted-exception-content"

    def timeout(*args, **kwargs):
        raise ValueError("publish scan deadline exceeded: " + private_detail)

    def outgoing(*args):
        if count is None:
            timeout()
        return "\n".join(f"{number + 1:040x} content.txt" for number in range(count)).encode()

    monkeypatch.setattr(evidence, "_git", outgoing)
    monkeypatch.setattr(evidence, "_cache", timeout)
    result = hooks.hook(project, "pre-push", {}, refs=f"refs/heads/main {'1' * 40} refs/heads/main {'0' * 40}\n")
    assert denied(result)
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert (f"{count} outgoing objects" if count is not None else "outgoing object count unavailable") in reason
    assert f"deadline={retry}s" in reason
    assert ("maximum Publish scan setting" in reason) is (retry == 3600)
    assert private_detail not in json.dumps(result)
    assert private_detail not in (project.state / "warnings.log").read_text(encoding="utf-8")
    assert evidence._SCAN_PROGRESS.get() is None
    assert evidence._SCAN_DEADLINE.get() is None


def test_pre_push_does_not_forward_unstructured_exception_details(tmp_path, monkeypatch):
    project = project_at(tmp_path, selected="publish.scan")
    private_detail = "synthetic-untrusted-exception-content"

    def refuse(*args, **kwargs):
        raise ValueError("publish scan deadline exceeded: " + private_detail)

    monkeypatch.setattr(evidence, "scan_publish", refuse)
    result = hooks.hook(project, "pre-push", {}, refs="outgoing refs")
    assert denied(result)
    assert "Outgoing scan failed" in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert private_detail not in json.dumps(result)


def test_warning_log_failure_cannot_downgrade_an_existing_deny(tmp_path, monkeypatch):
    project = project_at(tmp_path, selected="shell.background")
    def refuse(*args, **kwargs):
        raise TimeoutError("locked")
    monkeypatch.setattr(hooks, "warning", refuse)
    result = hooks.hook(project, "PreToolUse", shell_payload("echo ready; worker &", supports_additional_context=False))
    assert denied(result)


@pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse", "Stop"])
def test_per_call_failures_open_with_unwritable_state(tmp_path, monkeypatch, event):
    project = project_at(tmp_path)
    def refuse(*args, **kwargs):
        raise PermissionError("unwritable")
    monkeypatch.setattr(hooks, "warning", refuse)
    monkeypatch.setattr(project, "write_json", refuse)
    assert not denied(hooks.failure(project, event, shell_payload("git push"), "timeout", "publish.scan"))


def test_pre_push_missing_child_interpreter_returns_nonzero(tmp_path):
    project = project_at(tmp_path, selected="publish.scan")
    result, code = runner.run("pre-push", b"", project, interpreter=str(tmp_path / "missing.exe"))
    assert denied(result) and code != 0


def test_actual_warning_lock_contention_preserves_pre_push_deny(tmp_path):
    project = project_at(tmp_path, selected="publish.scan")
    from ro_state import Project
    contender = Project(tmp_path, session="contender-session")
    with project.lock():
        assert denied(hooks.failure(contender, "pre-push", {}, "scan unavailable"))


@pytest.mark.parametrize("availability", ["missing", "unreadable", "empty", "no-section", "no-enforcement", "no-block"])
def test_pre_push_requires_available_policy_with_recovery_guidance(tmp_path, availability):
    project = project_at(tmp_path, selected="publish.scan")
    policy = project.root / "agents.md"
    policy.unlink()
    if availability == "unreadable":
        policy.mkdir()  # A directory cannot be read as policy, including with elevated file permissions.
    elif availability != "missing":
        policy.write_text({"empty": "", "no-section": "- Enforcement: off\n",
                           "no-enforcement": "## Project settings\n- Block: publish.scan\n",
                           "no-block": "## Project settings\n- Enforcement: block\n"}[availability], encoding="utf-8")
    result, code = runner.run("pre-push", b"", project)
    assert code != 0 and denied(result)
    message = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "restore a readable agents.md" in message and "own choice" in message
    assert denied(hooks.failure(project, "pre-push", {}, "scan unavailable"))


def test_pre_push_explicitly_disabled_enforcement_passes(tmp_path):
    project = project_at(tmp_path)
    (project.root / "agents.md").write_text("## Project settings\n- Enforcement: off\n", encoding="utf-8")
    result, code = runner.run("pre-push", b"", project)
    assert code == 0 and result == {}
    assert hooks.failure(project, "pre-push", {}, "scan unavailable") == {}


def test_per_call_hook_outside_a_project_keeps_fail_open_defaults(tmp_path):
    project = Project(tmp_path)
    payload = shell_payload("worker &")
    result, code = runner.run("PreToolUse", json.dumps(payload).encode(), project)
    assert code == 0 and result == {}
    assert hooks.failure(project, "PreToolUse", payload, "scan unavailable") == {}


def test_commands_after_here_string_terminators_are_still_checked(tmp_path, live_jobs):
    for quote in ("'", '"'):
        command = f"$text = @{quote}\n{quote}\nfunction data {{ Remove-Item safe.txt }}\n{quote}@.Trim(); Remove-Item runs/job-a/input.txt"
        findings = mutations(inspect(tmp_path, live_jobs, command, "powershell"))
        assert findings and all(not finding.uncertain for finding in findings), command


def test_opaque_bodies_preserve_outer_redirect_targets(tmp_path, live_jobs):
    for command, dialect in (("python -c \"print(1)\" >runs/job-a/input.txt", "bash"),
                             ("pwsh -Command { function data { Remove-Item safe.txt }; worker & } >runs/job-a/input.txt", "powershell"),
                             ('cmd /c "del safe.txt & worker" >runs/job-a/input.txt', "powershell"),
                             ("pwsh -Command { <# } #> Remove-Item runs/job-a/input.txt } >runs/job-a/input.txt", "powershell"),
                             ("& { Remove-Item safe.txt } >runs/job-a/input.txt", "powershell")):
        findings = inspect(tmp_path, live_jobs, command, dialect)
        assert [finding.check for finding in findings] == ["jobs.mutate-bound"], command
        assert not findings[0].uncertain


@pytest.mark.parametrize("command", [
    "Remove-Item runs/job-a/input.txt", "Copy-Item draft.txt -Destination runs/job-a/input.txt",
    "Move-Item draft.txt -Destination runs/job-a/input.txt", "Set-Content runs/job-a/input.txt ready",
    "Add-Content runs/job-a/input.txt ready", "Out-File -FilePath runs/job-a/input.txt -InputObject ready",
    "New-Item runs/job-a/input.txt", "Rename-Item runs/job-a/input.txt renamed.txt",
    "Clear-Content runs/job-a/input.txt",
])
def test_powershell_whatif_suppresses_mutations_but_still_checks_redirects(tmp_path, live_jobs, command):
    assert mutations(inspect(tmp_path, live_jobs, command, "powershell"))
    command += " -wHaTiF"
    assert inspect(tmp_path, live_jobs, command, "powershell") == []
    findings = mutations(inspect(tmp_path, live_jobs, command + " >runs/job-a/output.log", "powershell"))
    assert findings and all(not finding.uncertain for finding in findings)


def test_non_directory_options_do_not_make_relative_mutations_uncertain(tmp_path, live_jobs):
    for command in ("cmake -C cache.txt; rm runs/job-a/input.txt",
                    "sudo -C 3 true; rm runs/job-a/input.txt"):
        findings = mutations(inspect(tmp_path, live_jobs, command))
        assert findings and all(not finding.uncertain for finding in findings), command


@pytest.mark.parametrize("dialect,command", [
    ("bash", "env -i CHECK_MODE=ready sudo -n -u user nice -n 5 timeout -k 2 10 xargs -r -n 1 rm {target}"),
    ("powershell", "& Remove-Item {target}"),
    ("powershell", "Start-Process -FilePath tool.exe -Wait -ArgumentList ready >{target}"),
])
def test_certain_wrapper_options_preserve_blocks(tmp_path, live_jobs, dialect, command):
    command = command.format(target="runs/job-a/input.txt")
    values = configured(shell=dialect)
    findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, live_jobs, values)
    assert findings and all(checks.outcome(f, values) == "block" for f in findings)


@pytest.mark.parametrize("dialect,command", [
    ("bash", "rm {target}; echo 'unfinished"),
    ("powershell", "Remove-Item {target}; $text=@'\nunfinished"),
    ("bash", "rm {target}; cat <<EOF\n`unfinished`"),
    ("powershell", "Remove-Item {target}; pwsh -Command {{ echo ready"),
    ("bash", "rm {target}; echo $(echo unfinished"),
    ("powershell", "Remove-Item {target}; <# unfinished"),
    ("powershell", "pwsh -Command {{\n<# nested <#\n}}\n#>\nRemove-Item {target}\n}} >{target}"),
    ("powershell", "Remove-Item {target}; pwsh -Command {{ echo ( }}"),
    ("bash", "env --help rm {target}"),
    ("bash", "env -Cscratch rm {target}"),
    ("powershell", "Start-Process -Unknown tool.exe -Wait >{target}"),
    ("powershell", "& $TOOL; Remove-Item {target}"),
    ("bash", "$OPAQUE >{target}"),
    ("bash", "cp --unknown draft.txt scratch.txt >{target}"),
    ("powershell", "Write-Output --% ready; Remove-Item {target}"),
    ("bash", "rm {target}; echo ready >"),
], ids=["quote", "here-string", "heredoc", "script-block", "substitution", "comment",
        "ambiguous-comment-boundary", "nested-boundary", "unknown-wrapper-option", "attached-wrapper-option",
        "process-wrapper-option", "dynamic-call-operator", "dynamic-command", "mutation-option", "unrecognised-construct", "missing-redirect-target"])
def test_uncertain_parse_downgrades_every_finding_including_redirects(tmp_path, live_jobs, dialect, command):
    target = (tmp_path / "runs" / "job-a" / "input.txt").as_posix()
    command = command.format(target=f"'{target}'")
    values = configured(shell=dialect)
    findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path, live_jobs, values)
    assert findings and all(checks.outcome(f, values) == "warn" and "uncertain parse" in f.message for f in findings)


def test_command_uncertainty_also_downgrades_background_external_and_publish_findings(tmp_path, live_jobs, monkeypatch):
    values = configured()
    command = "env --help rm runs/job-a/input.txt; worker & release-tool publish artifact.txt"
    findings = checks.pre_checks(checks.Call("shell", "bash", command), tmp_path, live_jobs, values)
    assert {f.check for f in findings} >= {"jobs.mutate-bound", "shell.background", "external.gate"}
    assert all(checks.outcome(f, values) == "warn" and "uncertain parse" in f.message for f in findings)
    project = project_at(tmp_path, selected="publish.scan")
    monkeypatch.setattr(evidence, "scan_publish", lambda *args, **kwargs: ["Pattern matched."])
    result = hooks.hook(project, "PreToolUse", shell_payload("cp --unknown safe.txt target.txt; git push"))
    assert warned(result) and not denied(result)
    assert "uncertain parse" in str(result)


def test_bash_arithmetic_and_conditional_bodies_are_data(tmp_path, live_jobs):
    for command in ("(( flags & 1 )) && echo on", "(( flags < 8 && flags > 0 )) && echo in-range",
                    "printf '%s' $(( (flags & 1) << 2 ))", "(( 16#ff & 1 )) && echo on",
                    "[[ first < second && third > runs/job-a/input.txt ]]",
                    "[[ name == [[]* && first > runs/job-a/input.txt ]]",
                    "[[ name =~ [(&] && first > runs/job-a/input.txt ]]",
                    "[[ -f runs/job-a/input.txt && first > second ]] && echo present"):
        assert inspect(tmp_path, live_jobs, command) == [], command
    for command in ("(( flags & 1 ))", "echo $(( flags << 1 ))", "[[ first < second ]]",
                    "[[ name == [[]* ]]", "[[ name =~ [(] ]]"):
        findings = mutations(inspect(tmp_path, live_jobs, command + "; rm runs/job-a/input.txt"))
        assert findings and all(checks.outcome(f, configured()) == "block" for f in findings), command


@pytest.mark.parametrize("dialect,commands", [
    ("bash", ["if [ -f {target} ]; then rm {target}; fi",
              "if false; then echo ready; elif [ -f {target} ]; then rm {target}; fi",
              "if false; then echo ready; else rm {target}; fi",
              "while [ -f {target} ]; do rm {target}; done",
              "until [ ! -f {target} ]; do rm {target}; done",
              "! rm {target}", "time rm {target}", "time -p rm {target}", "time {{ rm {target}; }}",
              "{{ rm {target}; }}", "(rm {target})",
              "if true; then {{ (rm {target}); }}; fi"]),
    ("powershell", ["if (Test-Path {target}) {{ Remove-Item {target} }}",
                    "if ($false) {{ Write-Output ready }} elseif (Test-Path {target}) {{ Remove-Item {target} }}",
                    "if ($false) {{ Write-Output ready }} else {{ Remove-Item {target} }}",
                    "foreach ($path in @('scratch.txt')) {{ Remove-Item {target} }}",
                    "for ($i=0; $i -lt 1; $i++) {{ Remove-Item {target} }}",
                    "while (Test-Path {target}) {{ Remove-Item {target} }}",
                    "switch ($mode) {{ ready {{ Remove-Item {target} }} default {{ Write-Output ready }} }}",
                    "try {{ Remove-Item {target} }} catch {{ Write-Output failed }}",
                    "try {{ Write-Output ready }} catch {{ Remove-Item {target} }}",
                    "try {{ Write-Output ready }} finally {{ Remove-Item {target} }}",
                    "Get-ChildItem scratch | ForEach-Object {{ Remove-Item {target} }}",
                    "if ($ready) {{ foreach ($path in $paths) {{ Remove-Item {target} }} }}"]),
])
def test_compound_command_mutations_warn_instead_of_passing_or_blocking(tmp_path, live_jobs, dialect, commands):
    for command in commands:
        command = command.format(target="runs/job-a/input.txt")
        findings = inspect(tmp_path, live_jobs, command, dialect)
        assert mutations(findings), command
        assert all(f.uncertain and checks.outcome(f, configured(shell=dialect)) == "warn" for f in findings), command


def test_powershell_array_constructors_warn_without_commas(tmp_path):
    jobs = [{"status": "running", "bound": [str(tmp_path / "run" / "input.txt")]}]
    for command in ("Remove-Item -LiteralPath @(\n  'scratch.txt'\n  'run/input.txt'\n)",
                    "Set-Content -LiteralPath @('run/input.txt') -Value ''",
                    "Set-Content -LiteralPath @{ path = 'run/input.txt' } -Value ''"):
        findings = inspect(tmp_path, jobs, command, "powershell")
        assert mutations(findings), command
        assert all(f.uncertain and checks.outcome(f, configured(shell="powershell")) == "warn" for f in findings), command
    for quote in ("'", '"'):
        for value in (f"{quote}@({quote}", f"{quote}@{{{quote}", f"@{quote}\n@( @{{\n{quote}@"):
            command = f"Set-Content -LiteralPath scratch.txt -Value {value}"
            assert not checks.tokens(command, "powershell").uncertain, command
            assert inspect(tmp_path, jobs, command, "powershell") == [], command


def test_powershell_array_mutations_warn_and_quoted_commas_remain_literal(tmp_path, live_jobs):
    for command in ("Remove-Item -LiteralPath 'scratch.txt','runs/job-a/input.txt'",
                    'Remove-Item scratch.txt,runs/job-a/input.txt',
                    'Remove-Item -LiteralPath "runs/job-a/input.txt", "scratch.txt"',
                    "Set-Content -Path scratch.txt, runs/job-a/input.txt -Value ready",
                    "Copy-Item draft.txt -Destination scratch.txt,runs/job-a/input.txt"):
        findings = inspect(tmp_path, live_jobs, command, "powershell")
        assert mutations(findings), command
        assert all(f.uncertain and checks.outcome(f, configured(shell="powershell")) == "warn" for f in findings), command
    for quote in ("'", '"'):
        command = f"Remove-Item -LiteralPath {quote}scratch.txt,runs/job-a/input.txt{quote}"
        assert inspect(tmp_path, live_jobs, command, "powershell") == []
        jobs = [{"status": "running", "bound": [str(tmp_path / "scratch,old.txt")]}]
        command = f"Remove-Item -LiteralPath {quote}scratch,old.txt{quote}"
        findings = inspect(tmp_path, jobs, command, "powershell")
        assert mutations(findings) and all(checks.outcome(f, configured()) == "block" for f in findings)
