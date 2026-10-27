"""Installed-host harness checks; model and host-version subprocesses stay mocked."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.host import dryrun
from conftest import ROOT, with_real_ps


def hook_response(decision="deny", reason="shell.background: foreground shell required"):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                   "permissionDecisionReason": reason}}


def test_structured_hook_response_in_completed_event():
    event = {"type": "item.completed", "item": {"type": "hook_response", "id": "call-a",
             "output": json.dumps(hook_response())}}
    assert dryrun.parse_decisions([event]) == [{
        "decision": "denied", "checks": ["shell.background"],
        "evidence": "shell.background: foreground shell required", "source": "event[0].item.output",
        "tool_call_id": "call-a"}]


def test_claude_hook_event_handles_warning_and_exit_two_deny():
    warning = {"type": "system", "subtype": "hook_response", "tool_use_id": "call-b", "exit_code": 0,
               "stdout": json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "additionalContext": "jobs.read-bound: use status or logs"}})}
    denial = {"type": "system", "subtype": "hook_response", "tool_use_id": "call-c", "exit_code": 2,
              "stderr": "jobs.mutate-bound: cannot delete a bound input"}
    values = dryrun.parse_decisions([warning, denial])
    assert [(item["decision"], item["checks"], item["tool_call_id"]) for item in values] == [
        ("warned", ["jobs.read-bound"], "call-b"), ("denied", ["jobs.mutate-bound"], "call-c")]


def test_claude_tool_error_denial_is_attributed_but_assistant_claim_is_not():
    message = "PreToolUse:Bash hook error: jobs.mutate-bound: Path overlaps a running job."
    events = [{"type": "assistant", "message": {"content": [{"type": "text", "text": message}]}},
              {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "use-1",
                                                          "is_error": True, "content": message}]}}]
    decisions = dryrun.parse_decisions(events)
    assert len(decisions) == 1
    assert decisions[0]["source"] == "event[1].tool_result"
    assert decisions[0]["tool_call_id"] == "use-1"
    assert decisions[0]["checks"] == ["jobs.mutate-bound"]
    assert dryrun.tool_calls(events)[0]['status'] == 'declined'


@pytest.mark.parametrize('name', ['benign', 'read-bound', 'unmonitored-stop', 'future-record'])
@pytest.mark.parametrize('has_diagnostic', [True, False])
def test_claude_warning_and_benign_need_runner_diagnostics(name, has_diagnostic):
    probe = next(row for row in dryrun.probes('bash') if row.name == name)
    events = [{'type': 'user', 'message': {'content': [{'type': 'tool_result',
               'tool_use_id': 'synthetic', 'content': 'completed', 'is_error': False}]}}]
    raw = json.dumps({'event': probe.event, 'checks': [probe.check] if probe.check else [],
                      'decision': probe.expected}) if has_diagnostic else ''
    decisions = dryrun.parse_diagnostics(raw, probe.event)
    assert dryrun.parse_decisions(events) == []
    actual = dryrun.summarize_codex(probe, decisions, {'future_record_written': True},
                                  'completed', dryrun.tool_calls(events))
    assert (actual == probe.expected) is has_diagnostic


def test_successful_stdout_prompt_echo_and_unrelated_failures_are_not_hook_evidence():
    text = json.dumps(hook_response())
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": text}},
              {"type": "item.completed", "item": {"type": "command_execution", "status": "completed",
                                                     "id": "echo", "aggregated_output": text, "exit_code": 0}},
              {"type": "item.completed", "item": {"type": "command_execution", "status": "failed",
                    "id": "fail", "aggregated_output": "permission denied; shell.background docs", "exit_code": 2}},
              {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "code",
                    "name": "Bash", "input": {"command": "echo PreToolUse hook error: shell.background"}}]}},
              {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": False,
                    "tool_use_id": "code", "content": "PreToolUse hook error: shell.background"}]}},
              {"type": "system", "subtype": "hook_response", "exit_code": 0, "stdout": "{}"}]
    assert dryrun.parse_decisions(events) == []
    probe = dryrun.probes("bash")[2]
    assert dryrun.summarize(probe, [], dryrun.tool_calls(events), "completed").startswith("unknown/inconclusive")


def test_failed_command_records_hook_denial_and_excludes_ordinary_shell_errors():
    events = [{"type": "item.completed", "item": {"type": "command_execution", "id": "c1",
              "status": "declined", "aggregated_output": "PreToolUse hook blocked: shell.background: avoid &"}}]
    assert dryrun.parse_decisions(events)[0]["decision"] == "denied"
    assert dryrun.tool_calls(events)[0]["status"] == "declined"


def test_generic_hook_crash_is_not_a_denial():
    event = {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True,
             "tool_use_id": "c1", "content": "PreToolUse:Bash hook error: ModuleNotFoundError"}]}}
    decisions = dryrun.parse_decisions([event])
    assert decisions[0]["decision"] == "unknown" and decisions[0]["checks"] == []
    event["message"]["content"][0]["content"] = "PreToolUse:Bash hook error: hooks.failure: hooks inactive"
    assert dryrun.parse_decisions([event])[0]["decision"] == "unknown"


def test_target_summary_does_not_misattribute_stop_warning():
    stop = {"type": "hook_response", "systemMessage": "jobs.unmonitored: synthetic job has no monitor"}
    decisions = dryrun.parse_decisions([stop])
    assert decisions[0]["decision"] == "warned"
    assert dryrun.summarize(dryrun.probes("bash")[0], decisions, [], "completed").startswith("unknown/inconclusive")


def test_runner_diagnostics_ignore_other_events_and_malformed_records():
    records = [
        {"event": "SessionStart", "checks": ["shell.background"], "decision": "warned"},
        {"event": "PreToolUse", "checks": ["shell.background"], "decision": "denied"},
        {"event": "PostToolUse", "checks": ["jobs.read-bound"], "decision": "warned"},
        {"event": "Stop", "checks": ["jobs.unmonitored"], "decision": "warned"},
        {"event": "PreToolUse", "checks": [], "decision": "no hook decision"},
        {"event": "PreToolUse", "checks": ["jobs.read-bound"], "decision": "warned"},
        {"event": "PreToolUse", "checks": ["hooks.failure"], "decision": "unknown"},
        {"event": "PreToolUse", "checks": "shell.background", "decision": "denied"},
        {"event": "PreToolUse", "checks": [{}], "decision": "denied"},
        {"event": "PreToolUse", "checks": ["shell.background"], "decision": "allow"},
        [], None,
    ]
    text = "\n".join(json.dumps(record) for record in records) + '\n{"event":\n'
    decisions = dryrun.parse_diagnostics(text)
    assert [(item["decision"], item["checks"]) for item in decisions] == [
        ("denied", ["shell.background"]), ("no hook decision", []),
        ("warned", ["jobs.read-bound"]), ("unknown", ["hooks.failure"])]
    assert decisions[0]["source"] == ".ro/hook-diagnostics.jsonl:2"


@pytest.mark.parametrize("diagnostic,exists,expected", [
    (True, True, "denied"), (True, False, "not blocked"),
    (False, True, "unknown/inconclusive"), (False, False, "not blocked"),
])
def test_codex_delete_requires_runner_denial_and_preserved_file(diagnostic, exists, expected):
    decisions = ([{"decision": "denied", "checks": ["jobs.mutate-bound"]}] if diagnostic else [])
    assert dryrun.summarize_codex(dryrun.probes("bash")[1], decisions,
                                  {"bound_file_exists": exists}, "completed").startswith(expected)


@pytest.mark.parametrize("status,code", [("completed", 0), ("failed", 1), ("failed", 2)])
def test_codex_runner_denial_does_not_hide_tool_execution(status, code):
    probe = dryrun.probes("powershell")[0]
    decisions = [{"decision": "denied", "checks": [probe.check]}]
    calls = [{"status": status, "exit_code": code}]
    assert dryrun.summarize_codex(probe, decisions, {}, "completed", calls).startswith("not blocked")


@pytest.mark.parametrize("name", ["benign", "read-bound"])
def test_codex_clean_or_warning_diagnostic_requires_successful_tool_execution(name):
    probe = next(probe for probe in dryrun.probes("bash") if probe.name == name)
    decisions = [{"decision": probe.expected, "checks": [probe.check] if probe.check else []}]
    for calls in ([], [{"status": "failed", "exit_code": 1}]):
        assert dryrun.summarize_codex(probe, decisions, {}, "completed", calls).startswith("unknown/inconclusive")
    assert dryrun.summarize_codex(probe, decisions, {}, "completed", [
        {"status": "completed", "exit_code": 0}]) == probe.expected


def test_codex_incomplete_or_retried_probe_is_not_a_pass():
    probe = dryrun.probes("bash")[0]
    decisions = [{"decision": "denied", "checks": [probe.check]}]
    assert dryrun.summarize_codex(probe, decisions, {}, "timeout").startswith("unknown/inconclusive")
    assert dryrun.summarize_codex(probe, decisions, {}, "completed", [
        {"status": "declined"}, {"status": "declined"}]).startswith("unknown/inconclusive")
    for status in ("in_progress", "failed", "unknown"):
        assert dryrun.summarize_codex(probe, decisions, {}, "completed", [
            {"status": status, "exit_code": None}]).startswith("unknown/inconclusive")


@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_project_fixture_binds_real_input_and_clones_codex_sample(tmp_path, shell):
    project = tmp_path / "project with spaces"
    configured = dryrun.prepare_project(project, "codex", f"windows/{shell}")
    settings = (project / "agents.md").read_text(encoding="utf-8")
    assert "- Enforcement: block\n- Block: shell.background, jobs.mutate-bound\n" in settings
    assert f"- Environment: windows/{shell}" in settings
    assert "- Read bound: on" in settings
    jobs = json.loads((project / ".ro" / "jobs.json").read_text(encoding="utf-8"))
    assert jobs[0]["status"] == "running" and jobs[0]["pid"] == os.getpid()
    assert jobs[0]["start"]
    assert Path(jobs[0]["bound"][0]).read_text(encoding="utf-8") == "synthetic dry-run input\n"
    sample = json.loads((ROOT / "hooks" / "codex-hooks.sample.json").read_text(encoding="utf-8"))
    for declarations in sample["hooks"].values():
        for declaration in declarations:
            for hook in declaration["hooks"]:
                for key in ("command", "commandWindows"):
                    hook[key] = hook[key].replace("/absolute/path/to/plugin", ROOT.as_posix())
    assert configured["hooks"] == sample
    assert json.loads((project / ".codex" / "hooks.json").read_text(encoding="utf-8")) == sample
    assert (project / ".codex" / "config.toml").read_bytes() == b""
    assert (project / ".ro" / "hook-diagnostics.on").read_bytes() == b""


@pytest.mark.parametrize("key", ["command", "commandWindows"])
def test_installed_sample_command_preserves_runner_input_and_diagnostics(tmp_path, key):
    if key == "commandWindows" and os.name != "nt":
        pytest.skip("Windows command string")
    configured = dryrun.prepare_project(tmp_path, "codex", dryrun.environment("codex", "bash"))
    hook = configured["hooks"]["hooks"]["PreToolUse"][0]["hooks"][0]
    command = (["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", hook[key]]
               if key == "commandWindows" else [shutil.which("sh"), "-c", hook[key]])
    payload = {"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "echo ready &"}}
    env = {**os.environ, "RO_HOOK_PYTHON": sys.executable,
           "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    env.pop("RO_HOOK_DIAGNOSTICS", None)
    result = subprocess.run(command, cwd=tmp_path, env=env, input=json.dumps(payload).encode(), capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    diagnostic = (tmp_path / ".ro" / "hook-diagnostics.jsonl").read_text(encoding="utf-8")
    assert [(item["decision"], item["checks"]) for item in dryrun.parse_diagnostics(diagnostic)] == [
        ("denied", ["shell.background"])]


def test_claude_fixture_uses_bash_without_writing_plugin_or_home_config(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert dryrun.environment("claude") == "windows/bash"
    assert dryrun.environment("codex") == "windows/powershell"
    assert dryrun.environment("codex", "bash") == "windows/bash"
    project = tmp_path / "claude"
    dryrun.prepare_project(project, "claude", dryrun.environment("claude"))
    assert not (project / ".claude").exists()
    assert not (project / ".codex").exists()
    assert not (project / ".ro" / "hook-diagnostics.on").exists()
    with pytest.raises(ValueError, match="require --shell bash"):
        dryrun.environment("claude", "powershell")


def test_fixture_commands_produce_target_findings_with_current_pure_checker(tmp_path):
    import ro_checks
    import ro_hooks
    import ro_state
    import ro_settings

    for shell in ("bash", "powershell"):
        project = tmp_path / shell
        setup = dryrun.prepare_project(project, "codex", dryrun.environment("codex", shell))
        values = {"enforcement": "block", "block": "shell.background,jobs.mutate-bound", "read_bound": "on",
                  "environment": setup["environment"], "external_actions": "none"}
        assert all(check in ro_settings.CHECK_IDS for check in values["block"].split(","))
        for probe in dryrun.probes(shell):
            if probe.event != "PreToolUse":
                continue
            call = ro_checks.Call("shell", shell, probe.command)
            findings = ro_checks.pre_checks(call, project, [setup["job"]], values)
            observed = [(finding.check, ro_checks.outcome(finding, values)) for finding in findings]
            expected = [(probe.check, "block" if probe.expected == "denied" else "warn")] if probe.check else []
            assert observed == expected
            # Go through the installed adapter's live-job filter as well: a
            # plausible-looking but stale fixture must not make this test pass.
            response = ro_hooks.hook(ro_state.Project(project), "PreToolUse", {
                "cwd": str(project), "tool_name": "Bash" if shell == "bash" else "PowerShell",
                "tool_input": {"command": probe.command}})
            if probe.expected == "denied":
                assert response["hookSpecificOutput"]["permissionDecision"] == "deny"
                assert probe.check in response["hookSpecificOutput"]["permissionDecisionReason"]
            elif probe.expected == "warned":
                assert probe.check in response["hookSpecificOutput"]["additionalContext"]
            else:
                assert response == {}


def test_startup_brief_is_not_a_warning_even_when_it_mentions_check_names():
    event = {"type": "hook_response", "output": {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": "Active Block checks: shell.background, jobs.mutate-bound"}}}
    assert dryrun.parse_decisions([event]) == []


def test_command_flags_are_session_only_and_prompts_are_literal_argv(tmp_path):
    probe = dryrun.probes("powershell")[0]
    command = dryrun.host_command("codex", "native-codex.exe", tmp_path, probe, "powershell", model="model-test")
    assert command[:4] == ["native-codex.exe", "exec", "--json", "--skip-git-repo-check"]
    assert command[command.index("-s") + 1] == "workspace-write"
    assert "--dangerously-bypass-hook-trust" in command
    assert "features.hooks=true" in command
    assert 'approval_policy="never"' in command
    trust = f'projects.{json.dumps(str(tmp_path))}.trust_level="trusted"'
    assert command[command.index(trust) - 1] == "-c"
    assert "--ephemeral" in command
    assert command[command.index("-C") + 1] == str(tmp_path)
    assert command[-1] == probe.prompt("powershell")
    claude = dryrun.host_command("claude.exe", "native-claude.exe", tmp_path, probe, "bash")
    assert claude[claude.index("--plugin-dir") + 1] == str(ROOT)
    assert claude[claude.index("--model") + 1] == "claude-haiku-5-5"
    assert claude[claude.index("--max-turns") + 1] == "3"
    assert claude[claude.index("--allowedTools") + 1] == "Bash"
    assert claude[claude.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in claude


@pytest.mark.parametrize("host", ["codex", "claude"])
def test_dry_print_has_no_subprocess_or_file_writes(tmp_path, monkeypatch, capsys, host):
    def forbidden(*args, **kwargs):
        pytest.fail("dry-print performed setup or launched a process")

    monkeypatch.setattr(dryrun.subprocess, "run", forbidden)
    monkeypatch.setattr(dryrun, "prepare_project", forbidden)
    monkeypatch.setattr(dryrun, "resolve_codex", forbidden)
    monkeypatch.setattr(dryrun, "resolve_claude", forbidden)
    monkeypatch.setattr(dryrun, "create_scratch", forbidden)
    output = tmp_path / "absent" / "report.md"
    assert dryrun.main(host, ["--dry-print", "--output", str(output)]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(lines) == 7
    assert lines[0]["argv"] == [host, "--version"]
    assert all("<temporary-project>" in line["cwd"] for line in lines[1:])
    assert not output.parent.exists()


def test_run_process_closes_stdin_and_keeps_failure_details(tmp_path, monkeypatch):
    def run(command, **kwargs):
        assert command == ["mock-codex", "exec"]
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["cwd"] == tmp_path and kwargs["timeout"] == 9
        assert kwargs.get("shell", False) is False
        return subprocess.CompletedProcess(command, 1, '{"type":"error"}\n', "transport failed")

    monkeypatch.setattr(dryrun.subprocess, "run", run)
    result = dryrun.run_process(["mock-codex", "exec"], tmp_path, 9, {})
    assert result["status"] == "failed" and result["returncode"] == 1
    assert result["stderr"] == "transport failed"


def test_timeout_retains_partial_events(tmp_path, monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b'{"type":"started"}', stderr=b"partial")

    monkeypatch.setattr(dryrun.subprocess, "run", run)
    result = dryrun.run_process(["mock"], tmp_path, 1, {})
    assert result["status"] == "timeout" and result["returncode"] is None
    assert result["stdout"] == '{"type":"started"}'


@pytest.mark.parametrize("host", ["codex", "claude"])
def test_mocked_end_to_end_generates_report_with_host_evidence(tmp_path, monkeypatch, host):
    def resolve(executable):
        return "mock-native"

    monkeypatch.setattr(dryrun, "resolve_codex", resolve)
    monkeypatch.setattr(dryrun, "resolve_claude", resolve)
    projects = []

    def run(command, **kwargs):
        assert kwargs["stdin"] is subprocess.DEVNULL
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "mock-host 123.4\n", "")
        project = Path(kwargs["cwd"])
        projects.append(project)
        assert (project / "run" / "input.txt").is_file()
        assert all((project.parent / case.name / ".ro" / "sessions").is_dir()
                   for case in dryrun.probes("bash"))
        assert kwargs["env"]["PATH"].startswith(str(Path(sys.executable).parent))
        name = project.name
        if host in {"codex", "claude"}:
            assert kwargs["env"]["RO_HOOK_DIAGNOSTICS"] == "1"
            probe = next(probe for probe in dryrun.probes("bash") if probe.name == name)
            diagnostic = {"event": probe.event, "checks": [probe.check] if probe.check else [],
                          "decision": probe.expected}
            (project / ".ro" / "hook-diagnostics.jsonl").write_text(json.dumps(diagnostic) + "\n", encoding="utf-8")
            # No hook lifecycle events are available in Codex exec JSON. Clean
            # and warned calls still require a successful foreground result.
            event = ({"type": "turn.completed"} if probe.expected == "denied" else
                     {"type": "item.completed", "item": {"type": "command_execution", "id": name,
                      "command": probe.command, "exit_code": 0, "status": "completed"}})
            if probe.event == "PostToolUse":
                with (project / "handoff.md").open("a", encoding="utf-8") as stream:
                    stream.write("### 2999-01-01 00:00 A\n")
        elif name == "unmonitored-stop":
            event = {"type": "hook_response", "systemMessage": "jobs.unmonitored: missing monitor"}
        elif name == "future-record":
            event = {"type": "hook_response", "output": {"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": "records.timestamp: future record"}}}
        elif name == "background":
            event = {"type": "hook_response", "output": hook_response()}
        elif name == "delete-bound":
            event = {"type": "hook_response", "output": hook_response(reason="jobs.mutate-bound: protected")}
        elif name == "read-bound":
            event = {"type": "hook_response", "output": {"hookSpecificOutput": {"additionalContext": "jobs.read-bound: protected"}}}
        else:
            event = {"type": "item.completed", "item": {"type": "command_execution", "id": "benign", "command": "echo ok",
                                                         "exit_code": 0, "status": "completed"}}
        return subprocess.CompletedProcess(command, 0, json.dumps(event) + "\n", "")

    monkeypatch.setattr(dryrun.subprocess, "run", with_real_ps(run))
    output = tmp_path / f"{host}.md"
    assert dryrun.main(host, ["--output", str(output), "--shell", "bash", "--temp-parent", str(tmp_path / "scratch")]) == 0
    text = output.read_text(encoding="utf-8")
    assert "mock-host 123.4" in text
    assert "| background | denied | denied |" in text
    assert "| delete-bound | denied | denied |" in text
    assert "| read-bound | warned | warned |" in text
    assert "| unmonitored-stop | warned | warned |" in text
    assert "| future-record | warned | warned |" in text
    assert "| benign | no hook decision | no hook decision |" in text
    assert ".ro/hook-diagnostics.jsonl:1" in text
    assert '"bound_file_exists": true' in text
    assert 'Host-output hook evidence' in text
    assert "Raw events:" in text
    assert len(set(projects)) == 6 and all(not project.exists() for project in projects)


@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_lifecycle_probes_target_stop_and_post_tool_use_without_running_host(shell):
    cases = {probe.name: probe for probe in dryrun.probes(shell)}
    stop = cases["unmonitored-stop"]
    post = cases["future-record"]
    assert (stop.event, stop.check, stop.expected) == ("Stop", "jobs.unmonitored", "warned")
    assert (post.event, post.check, post.expected) == ("PostToolUse", "records.timestamp", "warned")
    assert "--slot A brief" in stop.prompt(shell) and "SessionStart" in stop.prompt(shell)
    assert "2999-01-01 00:00" in post.command and "handoff.md" in post.command
    observations = "\n".join(json.dumps({"event": probe.event, "checks": [probe.check], "decision": probe.expected})
                              for probe in (stop, post))
    for probe in (stop, post):
        parsed = dryrun.parse_diagnostics(observations, probe.event)
        assert len(parsed) == 1 and parsed[0]["checks"] == [probe.check]
        assert dryrun.summarize_codex(probe, parsed, {"future_record_written": True}, "completed", [
            {"status": "completed", "exit_code": 0}]) == "warned"
    assert dryrun.parse_diagnostics(observations) == []


def test_post_tool_use_probe_requires_both_mutation_and_matching_event():
    probe = next(probe for probe in dryrun.probes("bash") if probe.event == "PostToolUse")
    text = json.dumps({"event": "Stop", "checks": [probe.check], "decision": "warned"})
    assert dryrun.parse_diagnostics(text, probe.event) == []
    decisions = [{"event": probe.event, "checks": [probe.check], "decision": "warned"}]
    assert dryrun.summarize_codex(probe, decisions, {"future_record_written": False}, "completed", [
        {"status": "completed", "exit_code": 0}]).startswith("unknown/inconclusive")


@pytest.mark.parametrize("diagnostic,delete", [(False, False), (False, True), (True, True)])
def test_codex_report_uses_diagnostics_and_side_effects_instead_of_exec_events(tmp_path, monkeypatch, diagnostic, delete):
    monkeypatch.setattr(dryrun, "resolve_codex", lambda executable: "mock-native")

    def run(command, **kwargs):
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "mock-host\n", "")
        project = Path(kwargs["cwd"])
        if project.name == "delete-bound":
            if diagnostic:
                record = {"event": "PreToolUse", "checks": ["jobs.mutate-bound"], "decision": "denied"}
                (project / ".ro" / "hook-diagnostics.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
            if delete:
                (project / "run" / "input.txt").unlink()
        # Even an apparent hook event is not the Codex outcome source.
        event = {"type": "hook_response", "output": hook_response(reason="jobs.mutate-bound: protected")}
        return subprocess.CompletedProcess(command, 0, json.dumps(event) + "\n", "")

    monkeypatch.setattr(dryrun.subprocess, "run", with_real_ps(run))
    output = tmp_path / "codex.md"
    assert dryrun.main("codex", ["--output", str(output), "--temp-parent", str(tmp_path / "scratch")]) == 1
    text = output.read_text(encoding="utf-8")
    expected = "not blocked (bound file was deleted)" if delete else "unknown/inconclusive"
    assert f"| delete-bound | denied | {expected}" in text
    assert "| benign | no hook decision | unknown/inconclusive" in text
    assert [path.name for path in (tmp_path / "scratch").iterdir()] == ["done"]


def test_markdown_fences_preserve_raw_event_backticks():
    rendered = dryrun.fence("contains ``` in event text", "jsonl")
    assert rendered.startswith("````jsonl\n") and rendered.endswith("\n````\n")


def test_native_claude_path_rejects_windows_shell_shims(monkeypatch):
    monkeypatch.setattr(dryrun.shutil, "which", lambda value: "C:/npm/claude.cmd")
    with pytest.raises(ValueError, match="native claude.exe"):
        dryrun.resolve_claude("claude")
