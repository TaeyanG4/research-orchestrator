"""Fast grading contracts and negative controls; never start a Codex session."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.evals import checks, grade_evals as grade, run_evals as runner
from scripts.evals.evidence import EvidenceBroker
from scripts.evals import inventory


def test_eval_readme_inventory_matches_case_folders():
    assert inventory.main(["--check"]) == 0


def test_unregistered_90_assertion_cannot_silently_become_a_quality_judgment(tmp_path):
    case = runner.Case(tmp_path, "unregistered", "Task", "Result", (
        runner.Assertion(Path("90-registry-value.md"), "Registry value equals one"),))
    with pytest.raises(ValueError, match="No scripted check registered"):
        grade.assertion_modes(case)


def test_all_case_folders_match_skill_creator_format():
    cases = runner.load_cases(runner.DEFAULT_SKILL)
    assert {"work-project-start", "work-project-session-history", "unified-research-resume", "v2-rules-upgrade",
            "external-action-order", "owned-job-monitor", "competition-direction-review", "non-ml-replication", "project-language"} <= {
                case.name for case in cases}
    modes = [mode for case in cases for mode in grade.assertion_modes(case).values()]
    assert modes.count("scripted") >= 38
    assert modes.count("judged") >= 7
    for case in cases:
        files = case.path / "files"
        assert files.is_dir() and any(files.iterdir())
        assert len({a.text for a in case.assertions}) == len(case.assertions)
        for path in case.path.rglob("*"):
            if path.is_file():
                source = path.read_text(encoding="utf-8")
                assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[/\\]", source)


def test_judge_schema_requires_exact_complete_verdicts():
    good = {"expectations": [{"text": "A fact", "passed": True, "evidence": "artifact: value"}]}
    assert grade.parse_judgement("```json\n" + json.dumps(good) + "\n```", ["A fact"]) == good
    for results in ([], good["expectations"] * 2,
                    [{"text": "A fact", "passed": "true", "evidence": "artifact"}],
                    [{"text": "Other fact", "passed": True, "evidence": "artifact"}],
                    [{"text": "A fact", "passed": True, "evidence": ""}]):
        with pytest.raises(ValueError):
            grade.parse_judgement(json.dumps({"expectations": results}), ["A fact"])


def test_no_fixture_heading_contains_replacement_question_marks():
    fixtures = list((runner.DEFAULT_SKILL / "evals").glob("*/files/**/*.md"))
    fixtures += list((runner.ROOT / "tests" / "fixtures").rglob("*.md"))
    for path in fixtures:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                assert "??" not in line, f"{path}:{number}: {line}"


def test_judge_is_one_read_only_codex_session(tmp_path, monkeypatch):
    monkeypatch.setattr(grade, "configured_model_settings", lambda: {})
    creator = tmp_path / "creator"
    (creator / "agents").mkdir(parents=True)
    (creator / "agents" / "grader.md").write_text("Review evidence and cite it.", encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir()
    case = runner.Case(tmp_path, "example", "Complete a task", "A result", ())
    calls = []
    homes = {key: os.environ.get(key) for key in ("CODEX_HOME", "HOME", "USERPROFILE")}

    def execute(command, **kwargs):
        calls.append(command)
        assert command[command.index("-s") + 1] == "read-only"
        assert "--ignore-user-config" in command and "--ignore-rules" in command
        assert "--add-dir" not in command
        assert {key: kwargs["env"].get(key) for key in homes} == homes
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert command[command.index("--model") + 1] == "gpt-6-astra"
        assert "Review evidence and cite it." in command[-1]
        assert "Return the grading JSON as your final message" in command[-1]
        Path(command[command.index("-o") + 1]).write_text(json.dumps({"expectations": [
            {"text": "A fact", "passed": True, "evidence": "output.txt: a fact"}]}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="{}\n", stderr="")

    monkeypatch.setattr(grade.subprocess, "run", execute)
    data = grade.judge_run(case, run, ["A fact"], creator=creator, codex="codex", model="gpt-6-astra")
    assert len(calls) == 1 and data["expectations"][0]["passed"] is True
    assert data["isolation"]["writable_roots"] == [] and data["cleanup_errors"] == []
    assert not (run / "grading.json").exists()

    # A failed regrade cannot reuse a prior positive result.
    monkeypatch.setattr(grade.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="failure"))
    data = grade.judge_run(case, run, ["A fact"], creator=creator, codex="codex", model="gpt-6-astra")
    assert data["expectations"][0]["passed"] is False and data["grading_error"]
    assert not (run / "judge-final.json").exists()


def test_grading_combines_results_and_invalidates_failed_executor(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    (run / "outputs").mkdir()
    (run / "transcript.md").write_text("trace", encoding="utf-8")
    runner.write_json(run / "timing.json", {"total_duration_seconds": 2, "total_tokens": None})
    runner.write_json(run / "run.json", {"returncode": 0, "error": None})
    case = runner.Case(tmp_path, "work-project-start", "Task", "Result", (
        runner.Assertion(Path("01-checker-clean.md"), "Clean"),
        runner.Assertion(Path("90-quality.md"), "Useful")))
    monkeypatch.setitem(checks.SCRIPTED_CHECKS, (case.name, "01-checker-clean.md"), lambda ctx: (True, "No errors"))
    monkeypatch.setattr(grade, "judge_run", lambda *a, **kw: {
        "expectations": [grade.expectation("Useful", False, "Missing rationale")], "grader_duration_seconds": 1})
    data = grade.grade_run(case, run)
    assert data["summary"] == {"passed": 1, "failed": 1, "total": 2, "pass_rate": .5}
    assert all(set(row) == {"text", "passed", "evidence"} for row in data["expectations"])
    assert data["timing"]["total_duration_seconds"] == 3
    runner.write_json(run / "run.json", {"returncode": 1, "error": "executor failed"})
    assert grade.grade_run(case, run)["summary"]["passed"] == 0


@pytest.mark.parametrize("timing", [None, {}, {"total_duration_seconds": None}])
@pytest.mark.parametrize("excluded", [False, True])
def test_unavailable_executor_duration_stays_unknown_through_grading(tmp_path, monkeypatch, timing, excluded):
    monkeypatch.setattr(grade, "JUDGED_CHECKS", grade.JUDGED_CHECKS | {("example", "90-quality.md")})
    (tmp_path / "outputs").mkdir()
    (tmp_path / "transcript.md").write_text("Saved execution trace", encoding="utf-8")
    if timing is not None:
        runner.write_json(tmp_path / "timing.json", timing)
    run = {"returncode": 0}
    if excluded:
        run.update(excluded=True, exclusion_reason="Unavailable native trace")
    runner.write_json(tmp_path / "run.json", run)
    case = runner.Case(tmp_path, "example", "Task", "Result", (
        runner.Assertion(Path("90-quality.md"), "Useful"),))
    calls = []

    def judge(*args, **kwargs):
        calls.append(True)
        return {"expectations": [grade.expectation("Useful", True, "report.txt: supported result")],
                "grader_duration_seconds": 3}

    monkeypatch.setattr(grade, "judge_run", judge)
    data = grade.grade_run(case, tmp_path)
    assert data["timing"]["executor_duration_seconds"] is None
    assert data["timing"]["total_duration_seconds"] is None
    assert data["timing"]["grader_duration_seconds"] == (0 if excluded else 3)
    assert bool(calls) is not excluded
    saved = json.loads((tmp_path / "grading.json").read_text(encoding="utf-8"))
    assert saved["timing"] == data["timing"]


@pytest.mark.parametrize("exclusion", [{"excluded": True, "exclusion_reason": "transport failure"},
                                       {"failure_category": "transport"},
                                       {"failure_category": "setup/copy"},
                                       {"failure_category": "launch"}])
def test_transport_exclusion_skips_scripted_checks_and_judge(tmp_path, monkeypatch, exclusion):
    runner.write_json(tmp_path / "run.json", {"returncode": 1, "error": "Disconnected", **exclusion})
    runner.write_json(tmp_path / "timing.json", {"total_duration_seconds": 2})
    case = runner.Case(tmp_path, "work-project-start", "Task", "Result", (
        runner.Assertion(Path("01-checker-clean.md"), "Clean"),
        runner.Assertion(Path("90-quality.md"), "Useful")))

    def unexpected(*args, **kwargs):
        raise AssertionError("Excluded attempts must not run checks or a judge")

    monkeypatch.setitem(checks.SCRIPTED_CHECKS, (case.name, "01-checker-clean.md"), unexpected)
    monkeypatch.setattr(grade, "judge_run", unexpected)
    data = grade.grade_run(case, tmp_path)
    category = exclusion.get("failure_category")
    reason = f"infrastructure failure: {category}" if category in {"launch", "setup/copy"} else "transport failure"
    assert data["excluded"] and data["exclusion_reason"] == reason
    assert data["expectations"] == [] and data["summary"]["pass_rate"] is None
    assert data["timing"]["grader_duration_seconds"] == 0
    status = json.loads((tmp_path / "grading_status.json").read_text(encoding="utf-8"))
    assert status["excluded"] and status["resolved_model"] is None


@pytest.mark.parametrize("message", [
    "Selected model is at capacity. Please try a different model.",
    "unexpected status 503 Service Unavailable: session bridge cooling down after upstream timeouts.",
])
@pytest.mark.parametrize("category", [None, "executor"])
def test_service_outages_saved_as_executor_failures_are_not_graded(tmp_path, monkeypatch, message, category):
    monkeypatch.setattr(grade, "JUDGED_CHECKS", grade.JUDGED_CHECKS | {("example", "90-quality.md")})
    status = {"returncode": 1, "status": "failed", "error": "Codex exited with status 1; see stderr.txt"}
    if category:
        status["failure_category"] = category
    runner.write_json(tmp_path / "run.json", status)
    (tmp_path / "events.jsonl").write_text(json.dumps({"type": "turn.failed", "error": {"message": message}}),
                                           encoding="utf-8")
    case = runner.Case(tmp_path, "example", "Task", "Result", (
        runner.Assertion(Path("90-quality.md"), "Useful"),))
    monkeypatch.setattr(grade, "judge_run", lambda *a, **kw: pytest.fail("Outages cannot reach the judge"))
    result = grade.grade_run(case, tmp_path)
    assert result["excluded"] and result["exclusion_reason"] == "transport failure"
    assert result["expectations"] == [] and result["summary"]["pass_rate"] is None


def test_rule_region_normalizes_line_endings_and_excludes_next_section():
    first = b"generated\r\n## Project rules\r\n  keep spacing  \r\n## Other\r\nold\r\n"
    second = first.replace(b"generated", b"updated").replace(b"old", b"new")
    assert checks.rules_region(first) == checks.rules_region(second)
    assert checks.rules_region(first) == checks.rules_region(first.replace(b"\r\n", b"\n"))
    assert checks.rules_region(first) != checks.rules_region(first.replace(b"keep spacing", b"changed"))


def test_claim_requires_execution_evidence_not_a_prompt_mention(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "events.jsonl").write_text(json.dumps({"type": "item.completed", "item": {
        "type": "agent_message", "text": "ro.py claim H-A-01"}}), encoding="utf-8")
    ctx = checks.CheckContext(tmp_path, tmp_path, tmp_path, "python")
    assert checks.claim_recorded(ctx)[0] is False


def test_numeric_replication_and_record_parser_reject_wrong_results(tmp_path):
    (tmp_path / "outputs").mkdir()
    case = runner.DEFAULT_SKILL / "evals" / "non-ml-replication"
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, sys.executable)
    result = {"n": 8, "mean_difference": 2.5, "sample_sd": 1.6035674514745464,
              "standard_error": .5669467095138409, "t_statistic": 4.409585518440984,
              "degrees_freedom": 7, "ci95": [1.1593840616589195, 3.8406159383410805]}
    runner.write_json(ctx.outputs / "replication.json", result)
    assert checks.numeric_replication(ctx)[0]
    result["mean_difference"] = 0
    runner.write_json(ctx.outputs / "replication.json", result)
    assert not checks.numeric_replication(ctx)[0]
    text = "## Queue\n\n### H-A-01 — first\n- Claimed: none\n\n### H-A-02 — next\n- Sources: D-A-001\n\n## Other\n"
    parsed = checks.blocks(text, "H")
    assert list(parsed) == ["H-A-01", "H-A-02"]
    assert "H-A-02" not in parsed["H-A-01"]
    assert checks.fields(parsed["H-A-02"])["Sources"] == "D-A-001"
    assert checks.fields("- Reviews:\n- Kind: direction-review\n") == {"Reviews": "", "Kind": "direction-review"}


def execute_helper(ctx, script):
    with EvidenceBroker(ctx.case_dir, ctx.outputs, ctx.run_dir, Path(sys.executable)) as broker:
        responses = Path(broker.environment["RO_EVAL_EVIDENCE_DIR"])
        # The broker publishes a resolved directory (8.3 short names, /var -> /private/var).
        assert responses.is_relative_to(ctx.outputs.resolve())
        endpoint = json.loads((ctx.outputs / ".eval-evidence" / "endpoint.json").read_text(encoding="utf-8"))
        assert endpoint["evidence"] == str(responses)
        result = subprocess.run([sys.executable, str(ctx.outputs / script)], cwd=ctx.outputs,
                                capture_output=True, text=True, timeout=10,
                                env={**os.environ, **broker.environment})
        assert result.returncode == 0, result.stderr
        assert not broker.metadata["errors"]
        receipt, = responses.glob("*/receipt.json")
        record = json.loads(receipt.read_text(encoding="utf-8"))
        assert record == json.loads((broker.receipts / receipt.parent.name / "receipt.json").read_text(encoding="utf-8"))
        for name in record["artifacts"]:
            assert (receipt.parent / name).read_bytes() == (ctx.outputs / name).read_bytes()


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_record_parser_retains_fenced_bytes_for_preservation_checks(newline):
    record = ("## D-A-001 - Measured evidence\n- Finding: verified\n"
              "```text\n## D-A-099 - Quoted example\n- Finding: not live\n"
              "actual evidence\n```\n- Evidence: local log\n").replace("\n", newline)
    tail = "## Index" + newline
    parsed = checks.blocks(record + tail, "D")
    assert parsed == {"D-A-001": record}
    assert checks.fields(parsed["D-A-001"])["Finding"].strip() == "verified"
    assert parsed != checks.blocks(record.replace("actual evidence", "fabricated evidence") + tail, "D")


def external_context(tmp_path):
    case = runner.DEFAULT_SKILL / "evals" / "external-action-order"
    shutil.copytree(case / "files", tmp_path / "outputs")
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, sys.executable)
    digest = checks.digest((ctx.outputs / "release-note.txt").read_bytes())
    before = (f"## External actions\n\n### X-A-001 — local publication\n"
              f"- Candidate: release-note.txt, hash {digest}\n- Destination: mock://archive/release-note\n"
              "- Expected: one accepted artifact\n- Result: pending\n- Status: prepared\n")
    (ctx.outputs / "handoff.md").write_text(before, encoding="utf-8")
    return ctx, before


def test_external_check_uses_trusted_execution_and_artifact_identity(tmp_path):
    ctx, before = external_context(tmp_path)
    execute_helper(ctx, "simulate_external.py")
    (ctx.outputs / "handoff.md").write_text(before.replace("Result: pending", "Result: accepted").replace(
        "Status: prepared", "Status: done"), encoding="utf-8")
    assert checks.preaction_ledger(ctx)[0]
    assert checks.action_integrity(ctx)[0]
    assert checks.action_result(ctx)[0]
    (ctx.outputs / "action-before.md").write_text(before.replace("Result: pending", "Result: accepted"), encoding="utf-8")
    assert not checks.preaction_ledger(ctx)[0]
    assert not checks.action_integrity(ctx)[0]
    assert not checks.action_result(ctx)[0]


def test_mailbox_copies_cannot_replace_protected_evidence(tmp_path):
    ctx, _ = external_context(tmp_path)
    execute_helper(ctx, "simulate_external.py")
    assert ctx.execution("simulate_external.py")[0]
    response, = (ctx.outputs / ".eval-evidence" / "responses").iterdir()
    protected = ctx.run_dir / "evidence" / response.name
    original = (protected / "action-before.md").read_bytes()
    for path in (response / "action-before.md", ctx.outputs / "action-before.md"):
        path.write_text("Forged snapshot", encoding="utf-8")
    runner.write_json(response / "receipt.json", {"returncode": 0, "artifacts": {}})
    assert (protected / "action-before.md").read_bytes() == original
    assert not ctx.execution("simulate_external.py")[0]


@pytest.mark.parametrize("local_capture", [False, True])
def test_fabricated_external_outputs_cannot_substitute_for_execution(tmp_path, local_capture):
    ctx, before = external_context(tmp_path)
    (ctx.outputs / "action-before.md").write_text(before, encoding="utf-8")
    runner.write_json(ctx.outputs / "action-result.json", {
        "candidate_sha256": checks.digest((ctx.outputs / "release-note.txt").read_bytes()),
        "before_sha256": checks.digest((ctx.outputs / "action-before.md").read_bytes()),
        "executions": 1, "status": "accepted"})
    if local_capture:
        result = subprocess.run([sys.executable, str(ctx.outputs / "simulate_external.py"),
                                 "--capture", str(ctx.outputs)], capture_output=True, timeout=10)
        assert result.returncode != 0
        assert not (ctx.outputs / "action-executed.lock").exists()
    assert not checks.preaction_ledger(ctx)[0]
    assert not checks.action_integrity(ctx)[0]
    assert not checks.action_result(ctx)[0]


def test_external_postaction_snapshot_cannot_be_replaced_with_prepared_record(tmp_path):
    ctx, before = external_context(tmp_path)
    (ctx.outputs / "handoff.md").write_text(before.replace("Result: pending", "Result: accepted").replace(
        "Status: prepared", "Status: done"), encoding="utf-8")
    execute_helper(ctx, "simulate_external.py")
    assert not checks.preaction_ledger(ctx)[0]
    (ctx.outputs / "action-before.md").write_text(before, encoding="utf-8")
    result = ctx.data("action-result.json")
    result["before_sha256"] = checks.digest((ctx.outputs / "action-before.md").read_bytes())
    runner.write_json(ctx.outputs / "action-result.json", result)
    assert not checks.preaction_ledger(ctx)[0]
    assert not checks.action_integrity(ctx)[0]


def test_second_external_request_is_logged_and_rejected(tmp_path):
    ctx, _ = external_context(tmp_path)
    with EvidenceBroker(ctx.case_dir, ctx.outputs, ctx.run_dir, Path(sys.executable)) as broker:
        arguments = [sys.executable, str(ctx.outputs / "simulate_external.py")]
        first = subprocess.run(arguments, capture_output=True, timeout=10, env={**os.environ, **broker.environment})
        second = subprocess.run(arguments, capture_output=True, timeout=10, env={**os.environ, **broker.environment})
    assert first.returncode == 0 and second.returncode != 0
    records = [json.loads(line) for line in (ctx.run_dir / "evidence.jsonl").read_text().splitlines()]
    assert len(records) == 2 and records[0]["returncode"] == 0 and records[1]["returncode"] is None
    assert not checks.action_integrity(ctx)[0]


@pytest.mark.parametrize("configured_environment", [False, True])
@pytest.mark.parametrize("case_name,script", [
    ("external-action-order", "simulate_external.py"), ("unified-research-resume", "analyze.py")])
def test_direct_capture_before_preparation_then_broker_request_fails(tmp_path, case_name, script,
                                                                  configured_environment):
    case = runner.DEFAULT_SKILL / "evals" / case_name
    shutil.copytree(case / "files", tmp_path / "outputs")
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, sys.executable)
    with EvidenceBroker(case, ctx.outputs, ctx.run_dir, Path(sys.executable)) as broker:
        environment = dict(os.environ)
        environment.pop("RO_EVAL_EVIDENCE_DIR", None)
        if configured_environment:
            environment.update(broker.environment)
        denied = subprocess.run([sys.executable, str(ctx.outputs / script), "--capture", str(ctx.outputs)],
                                capture_output=True, text=True, timeout=10, env=environment)
        assert denied.returncode != 0 and "Direct --capture is forbidden" in denied.stderr
        assert not (ctx.outputs / "action-result.json").exists()
        assert not (ctx.outputs / "results" / "summary.json").exists()
        # Preparing a retrospective ledger/claim and using the ordinary helper
        # must not erase the earlier attempt or create a passing fresh capture.
        if script == "simulate_external.py":
            (ctx.outputs / "handoff.md").write_text(
                "## External actions\n\n### X-A-001\n- Expected: one accepted artifact\n"
                "- Result: pending\n- Status: prepared\n", encoding="utf-8")
        else:
            (ctx.outputs / "plan.md").write_text(
                ctx.text("plan.md").replace("Claimed: none", "Claimed: A since later"), encoding="utf-8")
        retried = subprocess.run([sys.executable, str(ctx.outputs / script)], capture_output=True,
                                 text=True, timeout=10, env=environment)
        assert retried.returncode != 0 and "second execution is forbidden" in retried.stderr
        assert not broker.metadata["errors"]
    invocations = [json.loads(line) for line in (ctx.run_dir / "helper-executions.jsonl").read_text().splitlines()]
    assert [row["mode"] for row in invocations] == ["capture", "request"]
    assert [row["sequence"] for row in invocations] == [1, 2]
    assert not ctx.execution(script)[0]
    if script == "simulate_external.py":
        assert not checks.preaction_ledger(ctx)[0]
        assert not checks.action_integrity(ctx)[0]
        assert not checks.action_result(ctx)[0]
    else:
        assert not checks.claim_recorded(ctx)[0]


def test_capture_capability_is_broker_private_and_required(tmp_path):
    ctx, _ = external_context(tmp_path)
    with EvidenceBroker(ctx.case_dir, ctx.outputs, ctx.run_dir, Path(sys.executable)) as broker:
        assert set(broker.environment) == {"RO_EVAL_EVIDENCE_DIR"}
        with pytest.raises(ValueError, match="per-run capability"):
            broker._capture("simulate_external.py", ctx.outputs, b"forged")
        assert not (ctx.outputs / "action-result.json").exists()


def test_invocation_log_is_required_independently_of_success_receipt(tmp_path):
    ctx, _ = external_context(tmp_path)
    execute_helper(ctx, "simulate_external.py")
    log = ctx.run_dir / "helper-executions.jsonl"
    invocation = json.loads(log.read_text(encoding="utf-8"))
    assert invocation["mode"] == "request"
    # A receipt alone cannot conceal a denied invocation from the separate log.
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**invocation, "mode": "capture", "sequence": 2}) + "\n")
    assert not checks.preaction_ledger(ctx)[0]
    assert not checks.action_integrity(ctx)[0]


@pytest.mark.parametrize("name", ["simulate_external.py", "release-note.txt"])
def test_broker_rejects_modified_helper_or_fixed_input(tmp_path, name):
    ctx, _ = external_context(tmp_path)
    path = ctx.outputs / name
    path.write_text(path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with EvidenceBroker(ctx.case_dir, ctx.outputs, ctx.run_dir, Path(sys.executable)) as broker:
        result = subprocess.run([sys.executable, str(ctx.outputs / "simulate_external.py")],
                                capture_output=True, text=True, timeout=10,
                                env={**os.environ, **broker.environment})
    assert result.returncode != 0 and "modified" in result.stderr
    record = json.loads((ctx.run_dir / "evidence.jsonl").read_text())
    assert record["returncode"] is None and not record["artifacts"]
    assert not checks.action_integrity(ctx)[0]


@pytest.mark.parametrize("claimed", [False, True])
def test_claim_requires_original_execution_snapshot(tmp_path, claimed):
    case = runner.DEFAULT_SKILL / "evals" / "unified-research-resume"
    shutil.copytree(case / "files", tmp_path / "outputs")
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, sys.executable)
    plan = ctx.text("plan.md")
    if claimed:
        (ctx.outputs / "plan.md").write_text(plan.replace("Claimed: none", "Claimed: A since now"), encoding="utf-8")
    execute_helper(ctx, "analyze.py")
    assert checks.claim_recorded(ctx)[0] is claimed
    # Claiming after computation, or fabricating a different claim snapshot,
    # cannot change what the harness captured at the actual observation time.
    (ctx.outputs / "results" / "claim-before.md").write_text(
        plan.replace("Claimed: none", "Claimed: A since later"), encoding="utf-8")
    assert not checks.claim_recorded(ctx)[0]


def test_fabricated_claim_snapshot_does_not_prove_execution(tmp_path):
    case = runner.DEFAULT_SKILL / "evals" / "unified-research-resume"
    shutil.copytree(case / "files", tmp_path / "outputs")
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, sys.executable)
    (ctx.outputs / "results").mkdir()
    (ctx.outputs / "results" / "claim-before.md").write_text(
        ctx.text("plan.md").replace("Claimed: none", "Claimed: A since now"), encoding="utf-8")
    assert not checks.claim_recorded(ctx)[0]


def test_discovery_finding_must_match_correct_computed_summary(tmp_path):
    (tmp_path / "outputs" / "results").mkdir(parents=True)
    ctx = checks.CheckContext(tmp_path, tmp_path, tmp_path, sys.executable)
    summary = {"n": 6, "overall_mean": 6, "source_means": {"alpha": 3, "beta": 9}}
    runner.write_json(ctx.outputs / "results" / "summary.json", summary)
    (ctx.outputs / "plan.md").write_text(
        "### H-A-02\n- Sources: D-A-001\n- Evidence: source means differ\n"
        "- Improvement: gather balanced observations\n", encoding="utf-8")
    def discovery(finding):
        (ctx.outputs / "discoveries.md").write_text(
            "### D-A-001\n- Evidence: results/summary.json\n- Finding: " + finding + "\n", encoding="utf-8")
    discovery(json.dumps(summary))
    assert checks.discovery_followups(ctx)[0]
    discovery(json.dumps({**summary, "source_means": {"alpha": 9, "beta": 3}}))
    assert not checks.discovery_followups(ctx)[0]
    discovery("The mean is 100 seconds and sources do not differ.")
    assert not checks.discovery_followups(ctx)[0]


def job_context(tmp_path, command, output="", exit_code=0):
    case = runner.DEFAULT_SKILL / "evals" / "owned-job-monitor"
    shutil.copytree(case / "files", tmp_path / "outputs")
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, "python")
    jobdir = ctx.outputs / "runs" / "owned"
    jobdir.mkdir(parents=True)
    (ctx.outputs / ".ro").mkdir()
    runner.write_json(ctx.outputs / ".ro" / "jobs.json", [{"id": "J-A-0001", "item": "H-A-01", "slot": "A",
        "pid": 123, "start": "identity", "confirmed": True, "status": "finished", "exit_code": 0,
        "monitor": {"active": False, "reason": "process exited"}}])
    runner.write_json(jobdir / "job-result.json", {"status": "completed", "started_at": "2026-10-25T00:00:00+00:00",
        "completed_at": "2026-10-25T00:00:08+00:00", "sample_count": 3})
    rows = [{"sampled_at": f"2026-10-25T00:00:0{second}+00:00", "current_host": "local", "current_user": "operator",
             "claim": "A since 2026-10-25 00:00", "active_compute": "CPU: A (H-A-01)"} for second in (1, 3, 7)]
    runner.write_json(jobdir / "ownership-samples.json", rows)
    # JSON events are one complete object per line, unlike pretty-printed metadata.
    (tmp_path / "events.jsonl").write_text(json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "exit_code": exit_code, "command": command,
        "aggregated_output": output}}) + "\n", encoding="utf-8")
    return ctx, rows


LAUNCH_OUTPUT = "J-A-0001 launched; confirmed alive; monitor with ro monitor J-A-0001\n"
MONITOR_OUTPUT = "- Job: J-A-0001; item H-A-01; outcome: process exited with code 0\n"


@pytest.mark.parametrize("suffix", ["\n", "\r\n", "; monitor with ro monitor J-A-0001\n"])
def test_owned_job_accepts_actual_launch_output_without_optional_hint(tmp_path, suffix):
    ctx, _ = job_context(tmp_path, "python ro.py launch --item H-A-01 --expect 8s -- task",
                         "J-A-0001 launched; confirmed alive" + suffix)
    assert checks.owned_job(ctx)[0]


@pytest.mark.parametrize("output", ["J-A-0001 launched; confirmed aliveish\n",
                                    "J-A-0099 launched; confirmed alive\n", ""])
def test_owned_job_rejects_missing_or_conflicting_confirmation(tmp_path, output):
    ctx, _ = job_context(tmp_path, "python ro.py launch --item H-A-01 --expect 8s -- task", output)
    assert not checks.owned_job(ctx)[0]


def test_domain_check_distinguishes_instrument_exclusions_from_experiments(tmp_path):
    case = runner.DEFAULT_SKILL / "evals" / "non-ml-replication"
    shutil.copytree(case / "files", tmp_path / "outputs")
    ctx = checks.CheckContext(case, tmp_path, runner.DEFAULT_SKILL, sys.executable)
    (ctx.outputs / "agents.md").write_text("- Profile: research\n- Competition: off\n", encoding="utf-8")
    for name in ("plan.md", "discoveries.md"):
        (ctx.outputs / name).write_text("# Records\n", encoding="utf-8")
    handoff = ctx.outputs / "handoff.md"
    handoff.write_text("## I-A-01\n- Not for: target-change, model-change\n", encoding="utf-8")
    assert checks.neutral_workflow(ctx)[0]
    with (ctx.outputs / "plan.md").open("a", encoding="utf-8") as stream:
        stream.write("### H-A-02\n- Hypothesis: predictive-model experiment\n")
    assert not checks.neutral_workflow(ctx)[0]


@pytest.mark.parametrize("command", [
    "python skill/ro.py --slot A launch --item H-A-01 --expect 8s -- python simulate_job.py; "
    "python skill/ro.py --slot A monitor J-A-0001; python skill/ro.py --slot A close",
    "$tool = Join-Path $root 'skill/ro.py'\n$python = 'python.exe'\n"
    "$launched = & $python $tool --slot=A launch --item H-A-01 --expect 8s -- python simulate_job.py\n"
    "$job = $Matches[1]\n& $python $tool --slot A monitor $job | Tee-Object monitor.txt\n"
    "& $python $tool --slot A close",
    "tool='skill/ro.py'; task='J-A-0001'; python3 $tool launch --item H-A-01 --expect 8s -- python simulate_job.py; "
    "python3 $tool monitor \"${task}\"; python3 $tool close",
])
def test_job_check_accepts_resolved_commands_and_rejects_early_release(tmp_path, command):
    ctx, rows = job_context(tmp_path, command, LAUNCH_OUTPUT + MONITOR_OUTPUT)
    assert checks.owned_job(ctx)[0] and checks.monitored_job(ctx)[0]
    assert checks.closed_after_completion(ctx)[0]
    rows[1]["current_host"] = "released"
    runner.write_json(ctx.outputs / "runs/owned/ownership-samples.json", rows)
    assert not checks.closed_after_completion(ctx)[0]


@pytest.mark.parametrize("command,output,exit_code", [
    ("Write-Output 'python ro.py monitor J-A-0001; python ro.py close'", MONITOR_OUTPUT, 0),
    ("python ro.py monitor --help; python ro.py close", MONITOR_OUTPUT, 0),
    ("python ro.py monitor J-A-9999; python ro.py close", MONITOR_OUTPUT, 0),
    ("$job='J-A-9999'; python ro.py monitor $job; python ro.py close", MONITOR_OUTPUT, 0),
    ("job='J-A-9999'; JOB='J-A-0001'; python ro.py monitor $job; python ro.py close", MONITOR_OUTPUT, 0),
    ("python ro.py monitor $unknown; python ro.py close", "", 0),
    ("python ro.py monitor J-A-0001; python ro.py close", MONITOR_OUTPUT, 1),
    ("python -c 'print(\"ro.py monitor J-A-0001\")'; python ro.py close", MONITOR_OUTPUT, 0),
])
def test_job_checks_reject_wrong_or_unexecuted_monitor(tmp_path, command, output, exit_code):
    ctx, _ = job_context(tmp_path, command, output, exit_code)
    assert not checks.monitored_job(ctx)[0]
    assert not checks.closed_after_completion(ctx)[0]


def test_job_close_order_uses_commands_not_close_in_session_argument(tmp_path):
    command = "python ro.py --session close monitor J-A-0001; python ro.py close"
    ctx, _ = job_context(tmp_path, command, MONITOR_OUTPUT)
    assert checks.closed_after_completion(ctx)[0]


@pytest.mark.parametrize("shell", [["pwsh.exe", "-NoProfile", "-Command"], ["bash", "-lc"]])
def test_job_commands_accept_serialized_shell_wrappers_and_quoted_arguments(tmp_path, shell):
    source = ("$tool = 'path with spaces/ro.py'\n$job = 'J-A-0001'\n"
              "& 'path with spaces/python.exe' $tool --session 'monitor close' monitor $job\n"
              "& 'path with spaces/python.exe' $tool close")
    ctx, _ = job_context(tmp_path, shlex.join([*shell, source]), MONITOR_OUTPUT)
    assert checks.monitored_job(ctx)[0]
    assert checks.closed_after_completion(ctx)[0]


def test_job_checks_reject_close_before_monitor_and_unrelated_launch(tmp_path):
    command = "python ro.py close; python ro.py launch --item H-A-99 --expect 8s -- task; python ro.py monitor J-A-0001"
    ctx, _ = job_context(tmp_path, command, LAUNCH_OUTPUT.replace("J-A-0001", "J-A-0099") + MONITOR_OUTPUT)
    assert checks.monitored_job(ctx)[0]
    assert not checks.owned_job(ctx)[0]
    assert not checks.closed_after_completion(ctx)[0]
