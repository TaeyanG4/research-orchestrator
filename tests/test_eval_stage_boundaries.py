"""Regression fixtures for saved evidence checks, without executing an agent or grader run."""

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from scripts.evals.checks import CheckContext, SCRIPTED_CHECKS


SKILL = Path(__file__).resolve().parents[1] / "skills/research-orchestrator"


def context(tmp_path, case):
    source = SKILL / "evals" / case
    run = tmp_path / "run"
    shutil.copytree(source / "files", run / "outputs")
    (run / "events.jsonl").write_text("", encoding="utf-8")
    return CheckContext(source, run, SKILL, sys.executable)


def commands(ctx, rows):
    events = [{"type": "item.completed", "item": {"type": "command_execution", **row}} for row in rows]
    (ctx.run_dir / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")


def write_json(ctx, name, data):
    path = ctx.outputs / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def checked(ctx, filename):
    return SCRIPTED_CHECKS[ctx.case_dir.name, filename + ".md"](ctx)[0]


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("change", ["none", "success", "wrong-error", "wrong-command", "no-report"])
def test_duplicate_history_refusal_requires_actual_completed_failure(tmp_path, explicit, change):
    ctx = context(tmp_path, "external-historical-duplicate-id")
    row = {"command": "python ro.py external --artifact release-note.txt " +
           ("--action X-A-002 " if explicit else "") + "-- python mock_archive.py",
           "exit_code": 2, "aggregated_output": "external ledger ID X-A-001 must have exactly one heading"}
    if change == "success":
        row["exit_code"] = 0
    if change == "wrong-error":
        row["aggregated_output"] = "unrelated parser failure"
    if change == "wrong-command":
        row["command"] = "echo ro external"
    commands(ctx, [row])
    if change != "no-report":
        (ctx.outputs / "validation-report.md").write_text(row["aggregated_output"], encoding="utf-8")
    assert checked(ctx, "01-explicit-refusal" if explicit else "02-inferred-refusal") is (change == "none")


@pytest.mark.parametrize("journal", [None, "external-attempts/X-A-002.json", "external-results/partial.txt"])
def test_duplicate_history_requires_no_journal_of_any_name(tmp_path, journal):
    ctx = context(tmp_path, "external-historical-duplicate-id")
    commands(ctx, [{"command": "python ro.py external " + selected + " -- python mock_archive.py",
                    "exit_code": 2, "aggregated_output": "X-A-001 must have exactly one heading"}
                   for selected in ("--action X-A-002", "")])
    if journal:
        write_json(ctx, ".ro/" + journal, {"status": "in-flight"})
    assert checked(ctx, "04-no-attempt-journal") is (journal is None)


@pytest.mark.parametrize("change", ["none", "scope", "reviewer", "hash", "late", "missing-job"])
def test_stage_receipt_check_binds_scope_identity_bytes_and_order(tmp_path, change):
    ctx = context(tmp_path, "important-stage-review")
    digest = hashlib.sha256((ctx.outputs / "contract.md").read_bytes()).hexdigest()
    receipt = {"scope": "H-A-01/s2:before", "verdict": "PASS", "sha256": digest,
               "author_session": "fixture-stage-author", "reviewer": "fixture-stage-reviewer", "created_at": 10}
    if change == "scope":
        receipt["scope"] = "H-A-01/s2:after"
    if change == "reviewer":
        receipt["reviewer"] = receipt["author_session"]
    if change == "hash":
        receipt["sha256"] = "f" * 64
    if change == "late":
        receipt["created_at"] = 30
    write_json(ctx, ".ro/receipts.json", {"receipts": [receipt]})
    write_json(ctx, ".ro/jobs.json", [] if change == "missing-job" else
               [{"item": "H-A-01/s2", "started": 20, "exit_code": 0, "status": "finished"}])
    assert checked(ctx, "03-scope-bound-review") is (change == "none")


@pytest.mark.parametrize("change", ["none", "pre-reviewed", "no-job", "extra-execution"])
def test_routine_control_does_not_pass_without_its_actual_job(tmp_path, change):
    ctx = context(tmp_path, "stage-decision-review")
    write_json(ctx, ".ro/jobs.json", [] if change == "no-job" else
               [{"item": "H-A-02/s1", "started": 20, "exit_code": 0, "status": "finished"}])
    if change == "pre-reviewed":
        write_json(ctx, ".ro/receipts.json", {"receipts": [{"scope": "H-A-02/s1:before"}]})
    (ctx.outputs / "stage-executions.log").write_text(
        "routine\n" + ("dependent\n" if change == "extra-execution" else ""), encoding="utf-8")
    assert checked(ctx, "02-routine-control") is (change == "none")


@pytest.mark.parametrize("case", ["external-historical-duplicate-id", "important-stage-review", "stage-decision-review"])
def test_stage_saved_checks_reject_empty_outputs(tmp_path, case):
    ctx = context(tmp_path, case)
    empty = tmp_path / "empty"
    empty.mkdir()
    ctx.run_dir = empty
    (empty / "outputs").mkdir()
    # Preservation/no-fabrication checks also require their supplied evidence; no vacuous pass.
    for (name, assertion), check in SCRIPTED_CHECKS.items():
        if name == case:
            assert check(ctx)[0] is False, assertion
