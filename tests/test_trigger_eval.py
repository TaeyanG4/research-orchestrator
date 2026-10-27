"""Objective trigger-tool checks; all host execution is mocked."""
import json
from pathlib import Path
import subprocess

import pytest

from scripts.trigger import run_trigger_eval as trigger
from scripts.trigger.selection_stream import SelectionResult


NAME = "research-orchestrator"
SKILL = f'---\nname: {NAME}\ndescription: "Coordinate continuing work."\n---\n\n# Core\nRead references when needed.\n'


def event(kind, **item):
    return {"type": "item.completed", "item": {"type": kind, **item}}


def raw(*events):
    return "\n".join(json.dumps(e) for e in events)


def context(home):
    return {"user_home": str(home), "codex_home": str(home / ".codex"), "home_variables": {},
            "installed_skill_roots": [str(home / ".agents" / "skills")], "global_agents": {}}


def test_queries_balance_and_stratified_frozen_holdout():
    queries = trigger.load_queries(trigger.DEFAULT_QUERIES)
    assert len(queries) == 20
    assert sum(row["should_trigger"] for row in queries) == 10
    split = trigger.split_queries(queries)
    assert split == trigger.split_queries(queries)
    for part, count in (("train", 6), ("test", 4)):
        assert sum(split[i] == part and row["should_trigger"] for i, row in enumerate(queries)) == count
        assert sum(split[i] == part and not row["should_trigger"] for i, row in enumerate(queries)) == count
    assert all(NAME not in row["query"] for row in queries)  # No explicit invocation shortcut.


@pytest.mark.parametrize("description", ['Use work: "resume" paths.\nThen preserve decisions.', "Use continuing projects."])
def test_override_changes_only_description(description):
    name, actual, text = trigger.candidate_skill(SKILL, description)
    assert name == NAME and actual == description
    assert text.split("\n---\n", 1)[1] == SKILL.split("\n---\n", 1)[1]
    assert trigger.skill_field(text, "description")[0] == description
    assert trigger.candidate_skill(SKILL, None)[2] == SKILL


def test_folded_frontmatter_override_and_invalid_inputs(tmp_path):
    folded = SKILL.replace('"Coordinate continuing work."', '>\n  Coordinate continuing\n  work.')
    assert trigger.skill_field(folded, "description")[0] == "Coordinate continuing work."
    assert "  work." not in trigger.candidate_skill(folded, "Updated.")[2]
    with pytest.raises(ValueError):
        trigger.candidate_skill(SKILL, "")
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps([{"query": "same", "should_trigger": True}] * 2))
    with pytest.raises(ValueError, match="Duplicate"):
        trigger.load_queries(path)


def test_installed_copy_is_detected_disabled_and_not_modified(tmp_path, monkeypatch):
    host = tmp_path / "host"
    installed = host / ".agents" / "skills" / NAME / "SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_text(SKILL)
    project = tmp_path / "project"
    project.mkdir()
    real_stat = Path.stat
    def fixture_stat(path, *args, **kwargs):
        # Temp directories may live beneath a real user home with installed
        # skills. Inventory only this fixture, never machine-owned ancestors.
        if not path.is_relative_to(tmp_path):
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", fixture_stat)
    inventory = trigger.installed_inventory(NAME, project, context(host))
    assert not inventory["errors"]
    assert inventory["same_name_copies"] == [str(installed)]
    args = trigger.invocation_config({}, inventory)
    config = next(arg for arg in args if arg.startswith("skills.config="))
    assert json.dumps(str(installed)) in config and "enabled=false" in config
    assert "skills.include_instructions=true" in args
    assert "features.skip_host_skill_discovery=false" in args
    assert "skills.bundled.enabled=false" in args and "features.plugins=false" in args
    assert "--ignore-user-config" in args and "project_doc_max_bytes=0" in args
    assert installed.read_text() == SKILL


def test_trigger_evidence_requires_completed_read_or_use_statement(tmp_path):
    candidate = tmp_path / ".agents" / "skills" / NAME / "SKILL.md"
    ctx = context(tmp_path / "host")
    positives = [event("command_execution", command=f'Get-Content "{candidate}"', exit_code=0, status="completed"),
                 event("command_execution", command=f'cat {candidate}', exit_code=0, status="completed"),
                 event("agent_message", text=f"I am using {NAME} so we do not duplicate experiments."),
                 event("agent_message", text=f"Using {NAME} to resume without losing notes."),
                 event("agent_message", text=f"I’m using the {NAME} skill to resume work.")]
    for positive in positives:
        detected = trigger.detect_trigger([positive], candidate, NAME, tmp_path, ctx)
        assert detected["triggered"] and not detected["other_skill_paths"]
    negatives = [event("agent_message", text=f"I will not use {NAME} for this question."),
                 event("agent_message", text=f"The text mentions {NAME}."),
                 event("agent_message", text=f"You can use {NAME} if this becomes a longer project."),
                 event("agent_message", text=f"The docs say to use {NAME}."),
                 event("command_execution", command=f'echo "{candidate}"', exit_code=0),
                 event("command_execution", command=f'echo "cat {candidate}"', exit_code=0),
                 event("command_execution", command=f'echo "{candidate}"; cat unrelated.txt', exit_code=0),
                 event("command_execution", command=f'cat "{candidate}"', exit_code=1),
                 event("command_execution", command=f'cat "{candidate}"'),
                 event("command_execution", command=f'cat --help "{candidate}"', exit_code=0),
                 event("command_execution", command=f'rg --files "{candidate}"', exit_code=0),
                 event("file_read", path=str(candidate), success=False, error="permission denied"),
                 {"type": "item.started", "item": positives[0]["item"]},
                 {"type": "user_message", "text": f"Use {NAME}"},
                 event("command_execution", command="echo hello", aggregated_output=f"Using {NAME}", exit_code=0)]
    assert not trigger.detect_trigger(negatives, candidate, NAME, tmp_path, ctx)["triggered"]


def test_external_copy_cannot_count_as_candidate_read(tmp_path):
    ctx = context(tmp_path / "host")
    candidate = tmp_path / "project" / ".agents" / "skills" / NAME / "SKILL.md"
    outsider = f"~/.agents/skills/{NAME}/SKILL.md"
    installed = tmp_path / "host" / ".agents" / "skills" / NAME / "SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_text(SKILL)
    result = trigger.detect_trigger([event("command_execution", command=f"cat {outsider}", exit_code=0)],
                                    candidate, NAME, candidate.parents[3], ctx)
    assert not result["triggered"] and result["other_skill_paths"]


def test_metrics_do_not_treat_execution_errors_as_negative_predictions():
    rows = [{"should_trigger": actual, "runs": [{"triggered": value} for value in values]}
            for actual, values in [(True, [True, True, False]), (False, [True, True, True]),
                                   (True, [False, False, True]), (False, [False, False, False]),
                                   (False, [False, None, False])]]
    result = trigger.summarize(rows, 0.5)
    assert result["counts"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 1, "inconclusive": 1}
    assert result["precision"] == result["recall"] == result["accuracy"] == 0.5
    assert result["coverage"] == 0.8
    assert result["results"][-1]["pass"] is None


def run_mock(tmp_path, monkeypatch, responses, throttle=None):
    calls = []
    home = tmp_path / "host"
    monkeypatch.setattr(trigger.isolation, "host_instruction_context", lambda: context(home))
    monkeypatch.setattr(trigger, "installed_inventory", lambda *args: {
        "roots": [str(home / ".agents" / "skills")], "disabled_manifests": [],
        "same_name_copies": [], "errors": []})

    def execute(command, **kwargs):
        assert command[1:4] == ["exec", "--json", "--skip-git-repo-check"]
        assert "--strict-config" in command
        assert command[command.index("-s") + 1] == "read-only"
        root = Path(command[command.index("-C") + 1])
        assert kwargs["cwd"] == root
        candidate = root / ".agents" / "skills" / NAME / "SKILL.md"
        assert candidate.read_text(encoding="utf-8") == SKILL
        assert list(candidate.parent.iterdir()) == [candidate]
        assert (root / ".git").is_dir()
        calls.append(root)
        response = responses[len(calls) - 1]
        if callable(response):
            response = response(candidate)
        if isinstance(response, subprocess.TimeoutExpired):
            output = response.stdout or ""
            stderr = response.stderr or ""
            return SelectionResult(output.decode() if isinstance(output, bytes) else output,
                                   stderr.decode() if isinstance(stderr, bytes) else stderr, -1, True)
        if isinstance(response, Exception):
            raise response
        code, output, stderr = response
        events, prefix, boundary = [], [], None
        lines = output.splitlines(keepends=True)
        for index, line in enumerate(lines):
            prefix.append(line)
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                events.append(value)
                if kwargs["on_event"](events):
                    boundary = len(events)
                    return SelectionResult("".join(prefix), stderr, code, False, boundary,
                                           "".join(lines[index + 1:]))
        return SelectionResult(output, stderr, code)

    monkeypatch.setattr(trigger, "stream_selection", execute)
    result = trigger.run_query("Resume my project", name=NAME, skill_text=SKILL,
                               run_dir=tmp_path / "result", temp_parent=tmp_path, codex="codex",
                               settings={}, model=None, timeout=2, retries=2, throttle=throttle)
    assert all(not root.exists() for root in calls)
    return result, calls


def successful(candidate):
    return (0, raw(event("command_execution", command=f'cat "{candidate}"', exit_code=0),
                   {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 3}}), "")


def test_disconnect_fresh_retry_preserves_every_attempt(tmp_path, monkeypatch):
    result, calls = run_mock(tmp_path, monkeypatch, [
        (1, raw({"type": "error", "message": "stream disconnected before completion"}), ""), successful])
    assert len(calls) == 2 and calls[0] != calls[1]
    assert result["status"] == "ok" and result["triggered"] is True
    assert result["attempts"][0]["disconnect_evidence"]
    assert (tmp_path / "result" / "attempt-1" / "events.jsonl").is_file()


@pytest.mark.parametrize("ending", ["success", "exhausted", "real-failure"])
def test_rate_limit_fresh_retry_waits_and_preserves_attempts(tmp_path, monkeypatch, ending):
    clock, waits = [0.0], []

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    throttle = trigger.RateLimitThrottle(clock=lambda: clock[0], sleep=sleep)
    failure = (1, raw({"type": "turn.failed", "error": {
        "message": "exceeded retry limit, last status: 429 Too Many Requests", "retry_after": 90}}), "")
    responses = {"success": [failure, successful], "exhausted": [failure] * 3,
                 "real-failure": [failure, (1, raw({"type": "turn.failed", "error": {"message": "task failed"}}), "")]}[ending]
    result, calls = run_mock(tmp_path, monkeypatch, responses, throttle=throttle)
    assert len(calls) == len(set(calls)) == len(responses)
    assert result["status"] == ("ok" if ending == "success" else "error")
    assert result["triggered"] is (True if ending == "success" else None)
    # The explicit 90 s hint wins over the immediate first retry and the 60 s second backoff.
    assert sum(waits) == 0  # All attempts are within the first three fresh-session retries.
    for number, record in enumerate(result["attempts"], 1):
        folder = tmp_path / "result" / f"attempt-{number}"
        assert json.loads((folder / "run.json").read_text()) == record
        assert (folder / "events.jsonl").is_file()
    first = result["attempts"][0]
    assert first["failure_category"] == "rate_limit" and first["retry_delay_seconds"] == 0
    assert first["rate_limit_evidence"]


@pytest.mark.parametrize("response", [
    (1, raw({"type": "error", "message": "429"}, {"type": "turn.failed", "error": {"message": "real failure"}}), ""),
    (0, raw({"type": "error", "message": "429"}, {"type": "turn.completed"}), ""),
    subprocess.TimeoutExpired("mock-codex", 2, output=raw({"type": "error", "message": "429"})),
])
def test_rate_limit_does_not_retry_recovery_or_timeout(tmp_path, monkeypatch, response):
    result, calls = run_mock(tmp_path, monkeypatch, [response])
    assert len(calls) == 1
    assert not result["attempts"][0]["retryable"]


def test_rate_limit_never_replaces_a_contaminated_trigger_attempt(tmp_path, monkeypatch):
    response = (1, raw(event("command_execution", command=f'cat "{trigger.ROOT / "README.md"}"', exit_code=0),
                       {"type": "turn.failed", "error": {"message": "429 Too Many Requests"}}), "")
    throttle = trigger.RateLimitThrottle(sleep=lambda seconds: pytest.fail("Contaminated attempt retried"))
    result, calls = run_mock(tmp_path, monkeypatch, [response], throttle=throttle)
    assert len(calls) == 1 and result["status"] == "contaminated" and result["triggered"] is None
    assert result["attempts"][0]["failure_category"] == "rate_limit"
    assert not result["attempts"][0]["retryable"]


@pytest.mark.parametrize("exists,command,code", [(False, "cat", 1), (False, "cat", 0),
                                                (True, "cat", 1), (True, "echo", 0)])
def test_guessed_or_unread_other_manifest_is_only_a_finding(tmp_path, exists, command, code):
    candidate = tmp_path / "project" / ".agents" / "skills" / NAME / "SKILL.md"
    guessed = tmp_path / "source" / NAME / "SKILL.md"
    if exists:
        guessed.parent.mkdir(parents=True)
        guessed.write_text(SKILL)
    result = trigger.detect_trigger([event("command_execution", command=f'{command} "{guessed}"', exit_code=code)],
                                    candidate, NAME, candidate.parents[3], context(tmp_path / "host"))
    assert not result["other_skill_paths"] and result["unconfirmed_skill_paths"]


@pytest.mark.parametrize("response", [
    (1, raw(event("agent_message", text="stream disconnected before completion")), ""),
    (1, raw({"type": "error", "message": "task failed"}), ""),
    (0, "not json", ""),
    subprocess.TimeoutExpired("codex", 2, output=b"", stderr=b"")])
def test_nontransport_failure_never_retries_or_scores(tmp_path, monkeypatch, response):
    result, calls = run_mock(tmp_path, monkeypatch, [response])
    assert len(calls) == 1 and result["triggered"] is None
    assert result["status"] in {"error", "timeout"}


def test_success_after_reconnect_not_retried(tmp_path, monkeypatch):
    def recovered(candidate):
        _, output, _ = successful(candidate)
        return (0, raw({"type": "error", "message": "stream disconnected before completion"}) + "\n" + output, "")
    result, calls = run_mock(tmp_path, monkeypatch, [recovered])
    assert len(calls) == 1 and result["status"] == "ok"


def test_installed_access_is_contaminated_even_with_announcement(tmp_path, monkeypatch):
    response = (0, raw(event("command_execution", command=f"cat ~/.agents/skills/{NAME}/SKILL.md", exit_code=0),
                       event("agent_message", text=f"I am using {NAME}."),
                       {"type": "turn.completed"}), "")
    result, calls = run_mock(tmp_path, monkeypatch, [response])
    assert result["status"] == "contaminated" and result["triggered"] is None
    assert len(calls) == 1


def test_candidate_mutation_is_not_a_valid_trigger(tmp_path, monkeypatch):
    def mutate(candidate):
        candidate.write_text("changed")
        return successful(candidate)
    result, _ = run_mock(tmp_path, monkeypatch, [mutate])
    assert result["status"] == "contaminated" and result["triggered"] is None


def test_exhausted_disconnects_preserve_attempts_without_scoring(tmp_path, monkeypatch):
    failure = (1, raw({"type": "error", "message": "Reconnecting... 5/5"}), "")
    result, calls = run_mock(tmp_path, monkeypatch, [failure] * 3)
    assert len(calls) == len(set(calls)) == 3
    assert result["triggered"] is None and result["status"] == "error"
    assert all((tmp_path / "result" / f"attempt-{i}" / "run.json").is_file() for i in range(1, 4))


def test_inventory_failure_prevents_host_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(trigger.isolation, "host_instruction_context", lambda: context(tmp_path / "home"))
    monkeypatch.setattr(trigger, "installed_inventory", lambda *args: {
        "roots": [], "disabled_manifests": [], "same_name_copies": [], "errors": ["Unreadable skill root"]})
    monkeypatch.setattr(trigger, "stream_selection", lambda *args, **kwargs: pytest.fail("Unsafe host launch"))
    result = trigger.run_query("resume", name=NAME, skill_text=SKILL, run_dir=tmp_path / "results",
                               temp_parent=tmp_path, codex="codex", settings={}, model=None, timeout=2, retries=2)
    assert result["triggered"] is None and len(result["attempts"]) == 1
    assert "Unreadable" in result["attempts"][0]["error"]


def test_main_writes_comparable_split_metrics_with_mocked_hosts(tmp_path, monkeypatch):
    monkeypatch.setattr(trigger, "resolve_codex", lambda name: "mock-codex")
    monkeypatch.setattr(trigger.isolation, "configured_model_settings", lambda: {})
    monkeypatch.setattr(trigger.isolation, "host_instruction_context", lambda: context(tmp_path / "home"))
    monkeypatch.setattr(trigger, "installed_inventory", lambda *args: {
        "roots": [], "disabled_manifests": [], "same_name_copies": [], "errors": []})
    calls = []
    gates = []
    run_query = trigger.run_query

    def record_gate(*args, **kwargs):
        gates.append(kwargs["throttle"])
        return run_query(*args, **kwargs)

    monkeypatch.setattr(trigger, "run_query", record_gate)

    def execute(command, **kwargs):
        calls.append(command)
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "mock-codex 1", "")
        return SelectionResult(raw({"type": "turn.completed"}), "", 0)

    monkeypatch.setattr(trigger.subprocess, "run", execute)
    monkeypatch.setattr(trigger, "stream_selection", execute)
    output = tmp_path / "output"
    assert trigger.main(["--output", str(output), "--temp-parent", str(tmp_path / "scratch"),
                         "--repeats", "2", "--jobs", "3", "--split", "test"]) == 0
    report = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert report["host_version"] == "mock-codex 1"
    assert len(calls) == 17  # One version read plus eight held-out queries twice.
    assert len(gates) == 16 and all(gate is gates[0] for gate in gates)
    assert report["metrics"]["test"]["counts"] == {"tp": 0, "fp": 0, "tn": 4, "fn": 4, "inconclusive": 0}
    assert report["metrics"]["test"]["recall"] == 0
    assert report["metrics"]["test"]["precision"] is None
    assert report["metrics"]["test"]["coverage"] == 1
    assert report["description_sha256"] and report["queries_sha256"]
    assert report["measurement_protocol"] == "first-selection-v1"


def test_trigger_endpoint_preserves_tail_without_running_the_task(tmp_path, monkeypatch):
    def selected(candidate):
        return (-9, raw(event("command_execution", command=f'cat "{candidate}"', exit_code=0),
                        event("command_execution", command=f'cat "{trigger.ROOT / "README.md"}"', exit_code=0)), "")
    result, calls = run_mock(tmp_path, monkeypatch, [selected])
    assert len(calls) == 1 and result["status"] == "ok" and result["triggered"] is True
    attempt = result["attempts"][0]
    assert attempt["selection_boundary"] == {"event": 1, "process_stopped": True}
    assert attempt["returncode"] == -9 and attempt["failure_category"] is None
    folder = tmp_path / "result" / "attempt-1"
    assert "README.md" not in (folder / "events.jsonl").read_text()
    assert "README.md" in (folder / "events-after-selection.jsonl").read_text()


def test_contaminating_read_in_selection_command_still_invalidates_prefix(tmp_path, monkeypatch):
    def mixed(candidate):
        return (0, raw(event("command_execution", command=f'cat "{candidate}"; cat "{trigger.ROOT / "README.md"}"',
                             exit_code=0)), "")
    result, _ = run_mock(tmp_path, monkeypatch, [mixed])
    assert result["status"] == "contaminated" and result["triggered"] is None
