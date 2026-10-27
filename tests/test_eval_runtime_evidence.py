"""Runtime artifact discrimination uses saved fixtures; no evaluators are run."""

import json
from pathlib import Path
import sys

import pytest

from scripts.evals import checks, grade_evals as grade, run_evals
from scripts.evals.runtime_checks import CHECKS, EXECUTION_ASSERTIONS


CASES = tuple(EXECUTION_ASSERTIONS)


def artifacts(case):
    if case == "stop-once-per-job":
        replies = [
            {"decision": "block", "reason": "J-A-0001"},
            {"systemMessage": "J-A-0001"},
            {"decision": "block", "reason": "J-A-0002"},
            {"systemMessage": "J-A-0001 J-A-0002"},
        ]
        jobs = [{"id": job, "status": "finished"} for job in ("J-A-0001", "J-A-0002")]
        return "stop-results.json", replies, {"project/.ro/jobs.json": jobs}
    if case == "conditional-project-hook-matchers":
        tools = ["Bash", "PowerShell", "Edit", "Write", "NotebookEdit", "AskUserQuestion", "Agent"]
        return "matcher-results.json", {key: tools for key in ("initial", "refreshed", "plugin")}, {}
    if case == "installer-runtime-selection":
        runtimes = {"upgrade": "/sandbox/home/.codex/skills/research-orchestrator/scripts/ro.py",
                    "fallback": "/sandbox/home/.claude/skills/research-orchestrator/scripts/ro.py"}
        result = {name: {"installer_arguments": ["--host", "codex"], "shim_text": f'#!/bin/sh\nexec python "{path}" "$@"\n',
                         "shim_help_exit_code": 0, "surviving_runtime": path} for name, path in runtimes.items()}
        result["upgrade"]["pre_push_runtime"] = runtimes["upgrade"]
        return "runtime-results.json", result, {"upgrade-help.txt": "Research Orchestrator",
                                                "fallback-help.txt": "Research Orchestrator"}
    refs = b"refs/heads/main abc refs/heads/main def\r\n".hex()
    result = {"override_command": ["fixture-python"], "refs_hex": refs, "remote": "origin"}
    for name, command in (("override", ["fixture-python"]), ("python3", ["python3"]),
                          ("python", ["python"]), ("py", ["py", "-3"]),
                          ("unavailable", []), ("denied", ["registered-python"])):
        result[name] = {
            "selected_command": command,
            "exit_code": 17 if name == "denied" else 1 if name == "unavailable" else 0,
            "stderr": "Python 3.12+; set RO_HOOK_PYTHON" if name == "unavailable" else "",
            "scanner_calls": [{"stdin_hex": refs, "remote": "origin"}] if command else [],
        }
    return "recovery.json", result, {}


def context(tmp_path, case, command="python fixture_driver.py", output=None, exit_code=0):
    filename, result, extras = artifacts(case)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    for name, data in {filename: result, **extras}.items():
        path = outputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    events = [] if command is None else [{
        "type": "item.completed",
        "item": {"type": "command_execution", "command": command, "exit_code": exit_code,
                 "aggregated_output": json.dumps(result) if output is None else output},
    }]
    (tmp_path / "events.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    (tmp_path / "transcript.md").write_text("", encoding="utf-8")
    return checks.CheckContext(run_evals.DEFAULT_SKILL / "evals" / case, tmp_path,
                               run_evals.DEFAULT_SKILL, sys.executable)


def verdicts(ctx, case):
    return [check(ctx)[0] for (name, _), check in CHECKS.items() if name == case]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("command", [None, "echo 'python fixture_driver.py'",
                                     "Get-Content fixture_driver.py", "python --help",
                                     "python --version fixture_driver.py", 1,
                                     'python -c \'print("cached response")\''])
def test_correct_looking_json_without_requested_invocation_fails(tmp_path, case, command):
    ctx = context(tmp_path, case, command)
    assert not any(verdicts(ctx, case))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("output,exit_code", [("unrelated command output", 0), ("", 0), (None, 1),
                                             (None, False), (None, "0"), ([], 0)])
def test_invocation_without_retained_successful_response_fails(tmp_path, case, output, exit_code):
    ctx = context(tmp_path, case, output=output, exit_code=exit_code)
    assert not any(verdicts(ctx, case))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("command", ["python different_driver.py", "python3 'harness with spaces.py'",
                                     "python -c 'import driver; driver.run()'"])
def test_matching_command_observations_are_eligible_for_trace_review(tmp_path, case, command):
    ctx = context(tmp_path, case, command)
    assert all(verdicts(ctx, case))


@pytest.mark.parametrize("case", CASES)
def test_changed_report_cannot_reuse_independent_response(tmp_path, case):
    ctx = context(tmp_path, case)
    filename, data, _ = artifacts(case)
    if isinstance(data, list):
        data[0]["extra"] = "altered"
    else:
        data["extra"] = "altered"
    (ctx.outputs / filename).write_text(json.dumps(data), encoding="utf-8")
    assert not any(verdicts(ctx, case))


@pytest.mark.parametrize("order", [(0, 1, 2, 3), (0, 2, 1, 3), (0, 1, 2)])
def test_stop_requires_all_four_independent_responses_in_order(tmp_path, order):
    case = "stop-once-per-job"
    _, replies, _ = artifacts(case)
    ctx = context(tmp_path, case, output="\n".join(json.dumps(replies[index]) for index in order))
    assert all(verdicts(ctx, case)) is (order == (0, 1, 2, 3))


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("execution_passed", [False, True, None])
@pytest.mark.parametrize("capture", [False, True])
def test_trace_execution_prerequisite_governs_every_runtime_assertion(tmp_path, case, execution_passed, capture):
    ctx = context(tmp_path, case, command="python fixture_driver.py" if capture else None)
    execution_name = EXECUTION_ASSERTIONS[case]
    assertions = (run_evals.Assertion(Path("01-result.md"), "Reported behavior"),
                  run_evals.Assertion(Path(execution_name), "Requested execution"))
    fixture = run_evals.Case(Path(case), case, "Task", "Result", assertions)
    results = {"Reported behavior": grade.expectation("Reported behavior", True, "Matching raw JSON")}
    if execution_passed is not None:
        results["Requested execution"] = grade.expectation(
            "Requested execution", execution_passed,
            "Runtime called" if execution_passed else "Unrelated command printed fabricated output")
    gated = grade.require_runtime_execution(fixture, results, ctx)
    assert all(result["passed"] for result in gated.values()) is (capture and execution_passed is True)


def test_runtime_cases_route_requested_execution_to_trace_review():
    cases = {case.name: case for case in run_evals.load_cases(run_evals.DEFAULT_SKILL)}
    for case, name in EXECUTION_ASSERTIONS.items():
        assert grade.assertion_modes(cases[case])[name] == "judged"


@pytest.mark.parametrize("case_name", CASES)
def test_saved_run_with_no_capture_earns_no_credit_even_with_positive_judge(tmp_path, monkeypatch, case_name):
    context(tmp_path, case_name, command=None)
    run_evals.write_json(tmp_path / "run.json", {"returncode": 0})
    cases = {case.name: case for case in run_evals.load_cases(run_evals.DEFAULT_SKILL)}
    case = cases[case_name]
    def positive_judge(case, run_dir, texts, **kwargs):
        return {"expectations": [grade.expectation(text, True, "Assumed the report was real") for text in texts],
                "grader_duration_seconds": 0}
    monkeypatch.setattr(grade, "judge_run", positive_judge)
    result = grade.grade_run(case, tmp_path)
    assert result["summary"]["passed"] == 0
    assert result["summary"]["failed"] == len(case.assertions)
    assert all("capture unavailable" in item["evidence"] for item in result["expectations"])
