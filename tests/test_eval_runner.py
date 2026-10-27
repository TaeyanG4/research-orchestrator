"""Fast runner checks; Codex and git subprocesses are always mocked."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import stat
import threading

import pytest

from scripts.evals import aggregate_evals as aggregate, baseline, contamination, grade_evals as grade, isolation, run_evals as runner


def make_case(parent: Path) -> runner.Case:
    path = parent / "simple-case"
    (path / "graders").mkdir(parents=True)
    (path / "files" / ".ro").mkdir(parents=True)
    (path / "files" / ".ro" / "seed.json").write_text("{}", encoding="utf-8")
    (path / "files" / "notes.md").write_text("Original input", encoding="utf-8")
    (path / "prompt.md").write_text(runner.PROMPT_HEADER + "Complete this task.\n\nInput files: notes.md, .ro\n", encoding="utf-8")
    (path / "case.yaml").write_text(
        'schema_version: "1.1"\nname: simple-case\nexpected_outcome: |\n  A useful result.\n'
        "context:\n  scaffold_script: place-files.sh\n", encoding="utf-8")
    (path / "place-files.sh").write_text(runner.SCAFFOLD, encoding="utf-8")
    (path / "graders" / "01-result.md").write_text(runner.GRADER_HEADER + "The result is recorded.\n", encoding="utf-8")
    return runner.load_case(path)


def test_case_parser_keeps_metadata_prompt_and_rejects_unknown_settings(tmp_path):
    case = make_case(tmp_path)
    assert not case.prompt.startswith("---")
    assert case.assertions[0].text == "The result is recorded."
    assert case.expected_outcome == "A useful result."
    prompt = case.path / "prompt.md"
    prompt.write_text(prompt.read_text(encoding="utf-8").replace("max_turns:", "unknown:"), encoding="utf-8")
    with pytest.raises(ValueError, match="settings block"):
        runner.load_case(case.path)


@pytest.mark.parametrize("broken", ["unquoted-version", "unknown-case-key", "input-traversal", "bad-grader"])
def test_case_parser_rejects_malformed_templates(tmp_path, broken):
    case = make_case(tmp_path)
    if broken == "unquoted-version":
        path = case.path / "case.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace('"1.1"', "1.1"), encoding="utf-8")
    elif broken == "unknown-case-key":
        path = case.path / "case.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "profile: work\n", encoding="utf-8")
    elif broken == "input-traversal":
        path = case.path / "prompt.md"
        path.write_text(path.read_text(encoding="utf-8").replace("notes.md, .ro", "../notes.md"), encoding="utf-8")
    else:
        path = case.assertions[0].path
        path.write_text("The result is recorded.\n", encoding="utf-8")
    with pytest.raises(ValueError):
        runner.load_case(case.path)


def test_token_accounting_counts_per_turn_without_double_counting_cached_input():
    events = runner.parse_events('\n'.join([
        "Non-JSON startup message", "[]",
        '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":70,"output_tokens":20}}',
        '{"type":"turn.completed","usage":{"total_tokens":30}}',
        '{"type":"item.completed","usage":{"total_tokens":999}}',
    ]))
    assert runner.total_tokens(events) == 150
    assert runner.total_tokens([]) is None
    assert runner.total_tokens([{"type": "turn.completed", "usage": {"input_tokens": True, "output_tokens": 2}}]) is None


def test_windows_npm_shim_resolves_to_native_binary_without_shell(tmp_path, monkeypatch):
    shim = tmp_path / "codex.cmd"
    native = (tmp_path / "node_modules" / "@openai" / "codex" / "node_modules" / "@openai"
              / "codex-win32-x64" / "vendor" / "x86_64-pc-windows-msvc" / "bin" / "codex.exe")
    native.parent.mkdir(parents=True)
    native.write_bytes(b"")
    monkeypatch.setattr(runner.shutil, "which", lambda value: str(shim))
    monkeypatch.setattr(runner.platform, "machine", lambda: "AMD64")
    assert runner.resolve_codex("codex") == str(native.resolve())


@pytest.mark.parametrize("outcome", ["success", "exit-error", "timeout", "missing-executable", "cleanup-error"])
@pytest.mark.parametrize("model", [None, "explicit-model"])
def test_run_preserves_outputs_and_cleans_temporary_project(tmp_path, monkeypatch, outcome, model):
    case = make_case(tmp_path / "cases")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Runtime skill", encoding="utf-8")
    for name in ("evals", "tests/fixtures", "scripts/evals"):
        excluded = skill / name
        excluded.mkdir(parents=True)
        (excluded / "answer.txt").write_text("Private grader", encoding="utf-8")
    project_paths = []
    codex_home = tmp_path / "host-codex-home"
    codex_home.mkdir()
    (codex_home / "AGENTS.md").write_bytes(b"")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    homes = {key: os.environ.get(key) for key in ("CODEX_HOME", "HOME", "USERPROFILE")}
    monkeypatch.setattr(runner, "configured_model_settings", lambda: {"model": "configured-model"})
    if outcome == "cleanup-error":
        def cleanup_with_error(root):
            # Exercise independent reporting while still removing the test's directory.
            assert isolation.cleanup(root) == []
            return ["Simulated access denied during cleanup"]
        monkeypatch.setattr(runner, "cleanup", cleanup_with_error)

    def fake_run(command, **kwargs):
        project = Path(command[command.index("-C") + 1])
        project_paths.append(project)
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs.get("shell", False) is False
        assert command[command.index("-s") + 1] == "workspace-write"
        if model is None:
            assert "--model" not in command
        else:
            assert command[command.index("--model") + 1] == model
        grants = [command[index + 1] for index, value in enumerate(command) if value == "--add-dir"]
        assert grants == [str(Path("python.exe").resolve().parent), str(project.parent / "skill")]
        # The runner records resolved paths (8.3 short names, /var -> /private/var).
        assert project.parent.parent == (tmp_path / "workspace" / "_runs").resolve()
        assert "sandbox_workspace_write.writable_roots=[]" in command
        assert "sandbox_workspace_write.exclude_tmpdir_env_var=true" in command
        assert "sandbox_workspace_write.exclude_slash_tmp=true" in command
        assert "--ignore-user-config" in command and "--ignore-rules" in command and "--ephemeral" in command
        assert "skills.include_instructions=false" in command and "features.plugins=false" in command
        assert "features.skip_host_skill_discovery=true" in command
        runtime = project.parent / "skill"
        assert str(runtime) in command[-1] and str(skill) not in command[-1]
        assert not any(path.name in isolation.EXCLUDED for path in runtime.rglob("*"))
        assert not (runtime / "SKILL.md").stat().st_mode & stat.S_IWUSR
        recorded = json.loads((iteration / case.name / "with_skill" / "run.json").read_text(encoding="utf-8"))
        assert recorded["isolation"]["runtime_integrity"] == {
            "before_sha256": baseline.content_digest(runtime), "after_sha256": None, "unchanged": None}
        assert {key: kwargs["env"].get(key) for key in homes} == homes
        assert "Read its SKILL.md first" in command[-1]
        assert (project / "notes.md").read_text(encoding="utf-8") == "Original input"
        (project / "result.txt").write_text("Partial or complete result", encoding="utf-8")
        Path(command[command.index("-o") + 1]).write_text("Task completed.", encoding="utf-8")
        kwargs["stdout"].write('{"type":"turn.completed","usage":{"input_tokens":20,"output_tokens":5}}\n')
        kwargs["stdout"].write('{"type":"thread.started","model":"resolved-model"}\n')
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 600)
        if outcome == "missing-executable":
            raise FileNotFoundError("Codex executable missing")
        return subprocess.CompletedProcess(command, 2 if outcome == "exit-error" else 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    iteration = tmp_path / "workspace" / "iteration-1"
    status = runner.run_case(case, "with_skill", skill, iteration, python=Path("python.exe"), model=model)
    run = iteration / case.name / "with_skill"
    assert status["status"] == {"success": "completed", "cleanup-error": "completed", "timeout": "timeout"}.get(outcome, "failed")
    assert bool(status["cleanup_errors"]) == (outcome == "cleanup-error")
    assert status["requested_model"] == model
    assert status["resolved_model"] == status["model"] == "resolved-model"
    assert status["isolation"]["credential_files_accessed"] is False
    assert status["isolation"]["host_context"]["global_agents"]["empty"] is True
    assert status["isolation"]["host_context"]["global_agents"]["size_bytes"] == 0
    assert status["isolation"]["writable_roots"] == [
        str(project_paths[0]), str(Path("python.exe").resolve().parent), str(project_paths[0].parent / "skill")]
    integrity = status["isolation"]["runtime_integrity"]
    assert integrity["unchanged"] and integrity["before_sha256"] == integrity["after_sha256"]
    assert not status["contaminated"]
    assert (run / "outputs" / "result.txt").is_file()
    assert (run / "outputs" / ".ro" / "seed.json").read_text(encoding="utf-8") == "{}"
    assert (run / "outputs" / "final.md").read_text(encoding="utf-8") == "Task completed."
    assert "Task completed." in (run / "transcript.md").read_text(encoding="utf-8")
    assert json.loads((run / "timing.json").read_text(encoding="utf-8"))["total_tokens"] == 25
    saved = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert saved["status"] == status["status"]
    assert saved["isolation"]["host_context"] == status["isolation"]["host_context"]
    assert project_paths and all(not path.parent.exists() for path in project_paths)
    assert (case.path / "files" / "notes.md").read_text(encoding="utf-8") == "Original input"
    with pytest.raises(FileExistsError):
        runner.run_case(case, "with_skill", skill, iteration, python=Path("python.exe"))


@pytest.mark.parametrize("outcomes,retries,expected,archived", [
    (("disconnect-event", "success"), None, "completed", 1),
    (("disconnect-warning", "success"), None, "completed", 1),
    (("disconnect-warning",) * 4, None, "failed", 4),
    (("disconnect-event", "disconnect-stderr", "success"), None, "completed", 2),
    (("disconnect-event",) * 4, None, "failed", 4),
    (("plain-failure",), None, "failed", 0),
    (("timeout",), None, "timeout", 0),
    (("timeout-disconnect",), None, "timeout", 0),
    (("contaminated-disconnect",), None, "contaminated", 1),
    (("success-reconnected",), None, "completed", 0),
    (("quoted-disconnect",), None, "failed", 0),
    (("reconnecting", "success"), None, "completed", 1),
    (("incomplete-reconnect",), None, "failed", 0),
    (("disconnect-event",), 0, "failed", 1),
    (("disconnect-event",) * 2, 1, "failed", 2),
    (("recovered-failure",), None, "failed", 0),
    (("recovered-stderr-failure",), None, "failed", 0),
    (("recovered-timeout",), None, "timeout", 0),
    (("recovered-copy-failure",), None, "failed", 0),
    (("recovered-missing-final",), None, "failed", 0),
    (("rate-limit", "success"), None, "completed", 1),
    (("usage-limit", "rate-limit-stderr", "success"), None, "completed", 2),
    (("rate-limit",) * 4, 3, "failed", 4),
    (("rate-limit", "plain-failure"), None, "failed", 1),
    (("rate-limit",), 0, "failed", 1),
    (("contaminated-rate-limit",), None, "contaminated", 1),
    (("timeout-rate-limit",), None, "timeout", 0),
    (("quoted-rate-limit",), None, "failed", 0),
    (("success-rate-limit-recovered",), None, "completed", 0),
    (("model-capacity", "success"), None, "completed", 1),
    (("upstream-503", "success"), None, "completed", 1),
    (("model-capacity",) * 4, None, "failed", 4),
    (("upstream-503",), 0, "failed", 1),
])
def test_disconnect_retries_use_fresh_sessions_and_preserve_attempts(
        tmp_path, monkeypatch, outcomes, retries, expected, archived):
    case = make_case(tmp_path / "cases")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Runtime skill", encoding="utf-8")
    monkeypatch.setattr(runner, "configured_model_settings", lambda: {})
    monkeypatch.setattr(runner, "prepare_environment", lambda *args: ({}, {}))
    brokers, projects = [], []
    iteration = tmp_path / "workspace" / "iteration-1"
    run_dir = iteration / case.name / "with_skill"
    message = "stream disconnected before completion: Upstream websocket closed before response.completed"
    rate_message = "exceeded retry limit, last status: 429 Too Many Requests"
    clock, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    throttle = runner.RateLimitThrottle(clock=lambda: clock[0], sleep=sleep)

    class RecordingBroker(runner.EvidenceBroker):
        def __init__(self, *args):
            super().__init__(*args)
            # Enable the real mailbox lifecycle for this otherwise minimal case.
            self.helper = ("notes.md", (), ())
            brokers.append(self)

    monkeypatch.setattr(runner, "EvidenceBroker", RecordingBroker)
    copytree = runner.shutil.copytree

    def copy_outputs(source, destination, *args, **kwargs):
        if outcomes[-1] == "recovered-copy-failure" and Path(destination) == (run_dir / "outputs").resolve():
            copytree(source, destination, *args, **kwargs)
            raise OSError("Cannot copy final artifact")
        return copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "copytree", copy_outputs)

    def execute(command, **kwargs):
        number = len(projects) + 1
        outcome = outcomes[number - 1]  # Unexpected retries fail the test.
        assert command[1] == "exec" and "resume" not in command and "--ephemeral" in command
        assert kwargs["timeout"] == 17
        assert all(not project.parent.exists() for project in projects)
        project = Path(command[command.index("-C") + 1])
        assert project not in projects
        projects.append(project)
        assert (project / "notes.md").read_text(encoding="utf-8") == "Original input"
        assert not (project / "partial.txt").exists()
        assert (project.parent / "skill" / "SKILL.md").read_text(encoding="utf-8") == "Runtime skill"
        assert not Path(command[command.index("-o") + 1]).exists()
        broker = brokers[-1]
        assert not broker.seen and broker.attempts == 0 and not broker.stop.is_set()
        assert not list(broker.receipts.iterdir()) and not list(broker.responses.iterdir())
        assert (run_dir / "evidence.jsonl").read_text(encoding="utf-8") == ""
        assert (run_dir / "helper-executions.jsonl").read_text(encoding="utf-8") == ""
        assert kwargs["env"]["RO_EVAL_EVIDENCE_DIR"] == str(broker.responses.resolve())
        broker.seen.add("used-request")
        broker.attempts = 1
        (broker.receipts / "marker.txt").write_text(str(number), encoding="utf-8")
        for name in ("evidence.jsonl", "helper-executions.jsonl"):
            (run_dir / name).write_text(json.dumps({"attempt": number}) + "\n", encoding="utf-8")
        (project / "notes.md").write_text("Modified input", encoding="utf-8")
        (project / "result.txt").write_text(str(number), encoding="utf-8")
        if number == 1:
            (project / "partial.txt").write_text("First attempt only", encoding="utf-8")
        Path(command[command.index("-o") + 1]).write_text(f"Attempt {number}", encoding="utf-8")
        events = [{"type": "thread.started", "thread_id": f"session-{number}"},
                  {"type": "turn.completed", "usage": {"total_tokens": number}},
                  {"type": "turn.started"}]
        if outcome == "disconnect-warning":
            kwargs["stderr"].write("WARNING: optional startup helper unavailable\n")
        if outcome in {"disconnect-event", "disconnect-warning", "contaminated-disconnect"}:
            events.append({"type": "turn.failed", "error": {"message": message}})
        elif outcome == "quoted-disconnect":
            events.extend([
                {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
                {"type": "item.completed", "item": {"type": "command_execution",
                 "command": "run-tests", "aggregated_output": message, "exit_code": 1}},
            ])
        if outcome == "contaminated-disconnect":
            events.append({"type": "file_read", "path": str(runner.ROOT / "README.md"), "success": True})
        if outcome in {"rate-limit", "contaminated-rate-limit", "timeout-rate-limit"}:
            events.append({"type": "turn.failed", "error": {"message": rate_message}})
        elif outcome in {"model-capacity", "upstream-503"}:
            outage = ("Selected model is at capacity. Please try a different model."
                      if outcome == "model-capacity" else
                      "unexpected status 503 Service Unavailable: session bridge is cooling down")
            events.extend([{"type": "error", "message": outage},
                           {"type": "turn.failed", "error": {"message": outage}}])
        elif outcome == "usage-limit":
            events.append({"type": "error", "message": "You've hit your usage limit; Retry-After: 90"})
        elif outcome == "rate-limit-stderr":
            kwargs["stderr"].write(rate_message)
        elif outcome == "quoted-rate-limit":
            events.append({"type": "item.completed", "item": {"type": "agent_message", "text": rate_message}})
        elif outcome == "success-rate-limit-recovered":
            events.extend([{"type": "error", "message": rate_message}, {"type": "turn.completed"}])
        if outcome == "contaminated-rate-limit":
            events.append({"type": "file_read", "path": str(runner.ROOT / "README.md"), "success": True})
        if outcome.startswith("recovered"):
            events.extend([{"type": "error", "message": message},
                           {"type": "item.completed", "item": {"type": "agent_message", "text": "Resumed"}}])
            if outcome == "recovered-failure":
                events.append({"type": "turn.failed", "error": {"message": "Permission denied"}})
            elif outcome == "recovered-stderr-failure":
                kwargs["stderr"].write(message + "\nError: Permission denied\n")
            elif outcome == "recovered-missing-final":
                Path(command[command.index("-o") + 1]).unlink()
        kwargs["stdout"].write("".join(json.dumps(event) + "\n" for event in events))
        if outcome in {"disconnect-stderr", "timeout-disconnect", "success-reconnected"}:
            kwargs["stderr"].write(message + "\n")
        elif outcome in {"reconnecting", "incomplete-reconnect"}:
            kwargs["stderr"].write("Reconnecting... " + ("5/5" if outcome == "reconnecting" else "1/5") + "\n")
        elif outcome == "plain-failure":
            kwargs["stderr"].write("AssertionError: expected result missing\n")
        if outcome.startswith("timeout") or outcome == "recovered-timeout":
            raise subprocess.TimeoutExpired(command, 17)
        success = outcome.startswith("success") or outcome in {"recovered-copy-failure", "recovered-missing-final"}
        return subprocess.CompletedProcess(command, 0 if success else 1)

    monkeypatch.setattr(runner.subprocess, "run", execute)
    options = {} if retries is None else {"retries": retries}
    status = runner.run_case(case, "with_skill", skill, iteration, python=Path("python.exe"),
                             timeout=17, throttle=throttle, **options)
    assert status["status"] == expected
    runner.write_json(run_dir.parent / "eval_metadata.json", {"assertions": [a.text for a in case.assertions]})
    assert len(projects) == len(brokers) == len(status["attempts"]) == len(outcomes)
    assert all(broker.stop.is_set() and not broker.thread.is_alive() for broker in brokers)
    assert len({broker._capture_secret for broker in brokers}) == len(outcomes)
    assert all(not project.parent.exists() for project in projects)
    assert status["retries"] == (3 if retries is None else retries)
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8")) == status
    assert len(list((run_dir / "attempts").glob("attempt-*"))) == archived
    for number in range(1, archived + 1):
        attempt = run_dir / "attempts" / f"attempt-{number}"
        saved = json.loads((attempt / "run.json").read_text(encoding="utf-8"))
        assert saved["disconnect_evidence"] or saved["rate_limit_evidence"]
        assert saved["attempts"][-1]["number"] == number
        assert status["attempts"][number - 1]["disconnect_evidence"] == saved["disconnect_evidence"]
        assert status["attempts"][number - 1]["rate_limit_evidence"] == saved["rate_limit_evidence"]
        if saved["failure_category"] == "rate_limit":
            # The first retry is immediate in a fresh session; later ones back off.
            assert saved["retry_delay_seconds"] >= (0 if number <= 3 else min(60 * 2 ** (number - 4), 240))
        assert status["attempts"][number - 1]["path"] == f"attempts/attempt-{number}"
        assert json.loads((attempt / "timing.json").read_text(encoding="utf-8"))["total_tokens"] == number
        assert (attempt / "outputs" / "result.txt").read_text(encoding="utf-8") == str(number)
        assert (attempt / "outputs" / "final.md").read_text(encoding="utf-8") == f"Attempt {number}"
        assert (attempt / "evidence" / "marker.txt").read_text(encoding="utf-8") == str(number)
        assert all((attempt / name).is_file() for name in (
            "events.jsonl", "stderr.txt", "transcript.md", "evidence.jsonl", "helper-executions.jsonl"))
        assert not (attempt / "attempts").exists()
    assert (run_dir / "outputs" / "result.txt").read_text(encoding="utf-8") == str(len(outcomes))
    assert (run_dir / "outputs" / "partial.txt").exists() == (len(outcomes) == 1)
    assert (run_dir / "evidence" / "marker.txt").read_text(encoding="utf-8") == str(len(outcomes))
    assert json.loads((run_dir / "timing.json").read_text(encoding="utf-8"))["total_tokens"] == len(outcomes)
    assert f"session-{len(outcomes)}" in (run_dir / "events.jsonl").read_text(encoding="utf-8")
    if len(outcomes) > 1:
        assert "session-1" not in (run_dir / "transcript.md").read_text(encoding="utf-8")
    if expected == "completed":
        # Archived grades and outputs cannot affect grading or benchmark measurements.
        monkeypatch.setitem(grade.SCRIPTED_CHECKS, (case.name, "01-result.md"), lambda ctx: (
            (ctx.outputs / "result.txt").read_text(encoding="utf-8") == str(len(outcomes)), "Last attempt"))
        for attempt in (run_dir / "attempts").glob("attempt-*"):
            runner.write_json(attempt / "grading.json", {"summary": {"pass_rate": 0}})
        assert grade.grade_run(case, run_dir)["summary"]["pass_rate"] == 1
        benchmark = aggregate.generate_benchmark(iteration)
        assert benchmark["excluded_runs"] == [] and len(benchmark["runs"]) == 1
        assert benchmark["run_summary"]["with_skill"]["pass_rate"]["mean"] == 1
        assert benchmark["run_summary"]["with_skill"]["tokens"]["mean"] == len(outcomes)
    elif outcomes[-1] in {"disconnect-event", "disconnect-stderr", "disconnect-warning", "rate-limit",
                         "model-capacity", "upstream-503"}:
        assert status["failure_category"] == ("rate_limit" if outcomes[-1] in
                                               {"rate-limit", "model-capacity", "upstream-503"} else "transport")
        assert status["excluded"] and status["exclusion_reason"] == "transport failure"

        def unexpected(*args, **kwargs):
            raise AssertionError("Transport failures must not be graded")

        monkeypatch.setitem(grade.SCRIPTED_CHECKS, (case.name, "01-result.md"), unexpected)
        monkeypatch.setattr(grade, "judge_run", unexpected)
        # Aggregation must reject the run even before grading has recorded an exclusion.
        for graded in (False, True):
            if graded:
                data = grade.grade_run(case, run_dir)
                assert data["excluded"] and data["exclusion_reason"] == "transport failure"
                assert data["expectations"] == [] and data["summary"]["pass_rate"] is None
            benchmark = aggregate.generate_benchmark(iteration)
            assert benchmark["runs"] == []
            assert [row["reason"] for row in benchmark["excluded_runs"]] == ["transport failure"]
    elif outcomes[-1].startswith("recovered"):
        assert status["disconnect_evidence"] and not status.get("excluded")
        assert status["failure_category"] != "transport"
        monkeypatch.setitem(grade.SCRIPTED_CHECKS, (case.name, "01-result.md"), lambda ctx: (True, "Partial output"))
        graded = grade.grade_run(case, run_dir)
        if status["failure_category"] == "setup/copy":
            assert graded["excluded"] and graded["summary"]["pass_rate"] is None
            assert aggregate.generate_benchmark(iteration)["runs"] == []
        else:
            assert graded["summary"]["pass_rate"] == 0
            benchmark = aggregate.generate_benchmark(iteration)
            assert benchmark["excluded_runs"] == [] and len(benchmark["runs"]) == 1
    expected_wait = sum(entry["retry_delay_seconds"] for entry in status["attempts"][:-1])
    assert sum(sleeps) == expected_wait


def test_negative_retries_are_rejected_before_creating_a_run(tmp_path):
    case = make_case(tmp_path / "cases")
    iteration = tmp_path / "workspace" / "iteration-1"
    with pytest.raises(ValueError, match="retries"):
        runner.run_case(case, "with_skill", tmp_path / "skill", iteration, python=Path("python.exe"), retries=-1)
    assert not iteration.exists()
    with pytest.raises(SystemExit) as exc:
        runner.main(["--iteration", "1", "--retries", "-1", "--validate-only"])
    assert exc.value.code == 2


@pytest.mark.parametrize("message", [
    "stream disconnected before completion", "Upstream websocket closed before response.completed",
    "Reconnecting... 5/5", "Reconnecting\u2026 3 / 3",
])
@pytest.mark.parametrize("kind", ["error", "turn.failed", "item.error", "raw", "stderr"])
def test_disconnect_diagnostics_record_source_and_message(message, kind):
    event = {"type": "error", "message": message}
    if kind == "turn.failed":
        event = {"type": kind, "error": {"message": message}}
    elif kind == "item.error":
        event = {"type": "item.completed", "item": event}
    raw = message if kind == "raw" else json.dumps(event)
    evidence = runner.disconnect_evidence("" if kind == "stderr" else raw,
                                          message if kind == "stderr" else "")
    assert evidence == [{"source": "stderr.txt:1" if kind == "stderr" else "events.jsonl:1", "message": message}]


@pytest.mark.parametrize("ending,stderr,expected", [
    ([], "", True),
    ([{"type": "turn.failed", "error": {"message": "Permission denied"}}], "", False),
    ([{"type": "turn.completed"}], "stream disconnected before completion", False),
    ([{"type": "item.completed", "item": {"type": "agent_message", "text": "Resumed"}}], "", False),
    ([], "stream disconnected before completion\nError: Permission denied", False),
    ([{"type": "turn.completed"}, {"type": "turn.started"},
      {"type": "turn.failed", "error": {"message": "stream disconnected before completion"}}], "", True),
])
def test_terminal_transport_requires_an_unresolved_disconnect(ending, stderr, expected):
    events = [{"type": "error", "message": "stream disconnected before completion"}, *ending]
    assert runner.terminal_transport_failure("\n".join(map(json.dumps, events)), stderr) is expected


@pytest.mark.parametrize("stderr,expected", [
    ("WARNING: optional startup helper unavailable", True),
    ("WARN startup helper returned an error: unavailable", True),
    ("stream disconnected before completion\nWARNING: optional helper unavailable", True),
    ("stream disconnected before completion\nError: Permission denied\nWARNING: shutting down", False),
    ("stream disconnected before completion\nAssertionError: expected result missing", False),
    ("stream disconnected before completion\n2026-10-25T12:00:00Z ERROR codex: Permission denied", False),
    ("stream disconnected before completion\nFatal: Permission denied", False),
    ("Error: Permission denied\nstream disconnected before completion\nWARNING: shutting down", True),
])
@pytest.mark.parametrize("terminal_event", [False, True])
def test_terminal_disconnect_ignores_stderr_warnings_but_not_later_errors(stderr, expected, terminal_event):
    raw = json.dumps({"type": "turn.failed", "error": {"message": "stream disconnected before completion"}})
    assert runner.terminal_transport_failure(raw if terminal_event else "", stderr) is (
        expected and (terminal_event or "stream disconnected before completion" in stderr))


def test_validate_only_has_no_workspace_or_subprocess_side_effects(tmp_path, monkeypatch):
    skill = tmp_path / "skill"
    make_case(skill / "evals")

    def unexpected(*args, **kwargs):
        raise AssertionError("No subprocess may run during validation")

    monkeypatch.setattr(runner.subprocess, "run", unexpected)
    workspace = tmp_path / "workspace"
    assert runner.main(["--iteration", "1", "--skill-dir", str(skill), "--workspace", str(workspace), "--validate-only"]) == 0
    assert not workspace.exists()


@pytest.mark.parametrize("change,outcome", [("edit", "completed"), ("add", "completed"),
                                           ("delete", "completed"), ("remove-runtime", "completed"),
                                           ("edit", "timeout")])
def test_runtime_changes_contaminate_runs_and_remain_excluded_after_cleanup(tmp_path, monkeypatch, change, outcome):
    case = make_case(tmp_path / "cases")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Runtime skill", encoding="utf-8")
    monkeypatch.setattr(runner, "configured_model_settings", lambda: {})
    monkeypatch.setattr(runner, "prepare_environment", lambda *args: ({}, {}))

    def execute(command, **kwargs):
        runtime = Path(command[command.index("-C") + 1]).parent / "skill"
        runtime.chmod(runtime.stat().st_mode | stat.S_IWUSR)
        entry = runtime / "SKILL.md"
        entry.chmod(entry.stat().st_mode | stat.S_IWUSR)
        if change == "edit":
            entry.write_text("Modified runtime", encoding="utf-8")
        elif change == "add":
            (runtime / "extra.md").write_text("Extra instructions", encoding="utf-8")
        else:
            entry.unlink()
            if change == "remove-runtime":
                runtime.rmdir()
        Path(command[command.index("-o") + 1]).write_text("Complete", encoding="utf-8")
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 600)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", execute)
    iteration = tmp_path / "workspace" / "iteration-1"
    status = runner.run_case(case, "with_skill", skill, iteration, python=Path("python.exe"))
    assert status["status"] == "contaminated" and status["executor_status"] == outcome
    integrity = status["isolation"]["runtime_integrity"]
    assert integrity["unchanged"] is False
    assert integrity["before_sha256"] != integrity["after_sha256"]
    assert not Path(status["isolation"]["runtime_skill"]).parent.exists()
    run = iteration / case.name / "with_skill"
    saved = json.loads((run / "run.json").read_text(encoding="utf-8"))
    report = contamination.audit_saved_run(run, saved)
    assert report["contaminated"]
    assert report["findings"][0]["reason"] == "runtime skill modified"
    runner.write_json(run / "grading.json", {"summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1}})
    benchmark = aggregate.generate_benchmark(iteration)
    assert benchmark["runs"] == []
    assert benchmark["excluded_runs"][0]["reason"] == "contaminated"
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "Runtime skill"


def test_runner_accepts_minimal_isolation_metadata(tmp_path, monkeypatch):
    case = make_case(tmp_path / "cases")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Runtime skill", encoding="utf-8")
    monkeypatch.setattr(runner, "configured_model_settings", lambda: {})
    monkeypatch.setattr(runner, "prepare_environment", lambda *args: ({}, {}))

    def execute(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text("Complete", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", execute)
    status = runner.run_case(case, "with_skill", skill, tmp_path / "workspace" / "iteration-1",
                             python=Path("python.exe"))
    assert status["status"] == "completed"
    assert status["isolation"]["residual_risks"]
    assert status["isolation"]["writable_roots"][1] == str(Path("python.exe").resolve().parent)


@pytest.mark.parametrize("reason", ["eval_or_grader_path", "installed_skill", "global_agents"])
def test_runner_audits_successful_executor_before_reporting_completion(tmp_path, monkeypatch, reason):
    case = make_case(tmp_path / "cases")
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("Runtime skill", encoding="utf-8")
    monkeypatch.setattr(runner, "configured_model_settings", lambda: {})
    home = tmp_path / "host-home"
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True)
    agents = codex_home / "AGENTS.md"
    agents.write_bytes(b"Synthetic global instructions")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    # The host context records resolved home roots, as an executor's $HOME spelling expands to.
    target = {"eval_or_grader_path": "graders/01-result.md",
              "installed_skill": str(home.resolve() / ".agents" / "skills" / "installed" / "SKILL.md"),
              "global_agents": str(agents.resolve())}[reason]

    def execute(command, **kwargs):
        agents.unlink()  # The audit must use the snapshot taken before execution.
        Path(command[command.index("-o") + 1]).write_text("Complete", encoding="utf-8")
        kwargs["stdout"].write(json.dumps({"type": "item.completed", "item": {
            "type": "command_execution", "command": f'Get-Content "{target}"', "exit_code": 1}}) + "\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", execute)
    iteration = tmp_path / "workspace" / "iteration-1"
    status = runner.run_case(case, "with_skill", skill, iteration, python=Path("python.exe"))
    assert status["status"] == "contaminated" and status["executor_status"] == "completed"
    assert status["contaminated"] and status["returncode"] == 0
    assert status["contamination"]["findings"][0]["reason"] == reason
    assert status["isolation"]["host_context"]["global_agents"]["empty"] is False
    assert status["contamination"]["policy"]["host_context"] == status["isolation"]["host_context"]
    assert json.loads((iteration / case.name / "with_skill" / "run.json").read_text(
        encoding="utf-8"))["contaminated"]


@pytest.mark.parametrize("retries", [None, 0, 3])
def test_main_launches_both_configs_together_writes_metadata_and_refuses_overwrite(tmp_path, monkeypatch, retries):
    skill = tmp_path / "skill"
    case = make_case(skill / "evals")
    (skill / "SKILL.md").write_text("# Current skill", encoding="utf-8")
    old_skill = tmp_path / "baseline"
    old_skill.mkdir()
    (old_skill / "SKILL.md").write_text("# Released skill", encoding="utf-8")
    monkeypatch.setattr(baseline, "BASELINE_DIGEST", baseline.content_digest(old_skill))
    barrier = threading.Barrier(2, timeout=2)
    calls = []

    def fake_run(case, config, skill_dir, iteration_dir, **kwargs):
        assert kwargs["retries"] == (3 if retries is None else retries)
        calls.append((case.name, config, skill_dir))
        (iteration_dir / case.name / config).mkdir()
        barrier.wait()
        return {"status": "completed"}

    monkeypatch.setattr(runner, "run_case", fake_run)
    workspace = tmp_path / "workspace"
    args = ["--iteration", "1", "--skill-dir", str(skill), "--old-skill-dir", str(old_skill),
            "--workspace", str(workspace), "--jobs", "2"]
    if retries is not None:
        args.extend(["--retries", str(retries)])
    assert runner.main(args) == 0
    assert {(config, directory) for _, config, directory in calls} == {
        ("with_skill", skill.resolve()), ("old_skill", old_skill.resolve())}
    metadata = json.loads((workspace / "iteration-1" / case.name / "eval_metadata.json").read_text(encoding="utf-8"))
    assert metadata == {"eval_name": case.name, "prompt": case.prompt, "assertions": [case.assertions[0].text]}
    assert runner.main(args) == 1
    assert len(calls) == 2
