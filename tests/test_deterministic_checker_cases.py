"""Negative controls for pure saved-artifact predicates; no behavior runs are launched."""
from __future__ import annotations

import json
import sys

import pytest

from conftest import SKILL
from scripts.evals.checks import CheckContext
from scripts.evals import deterministic_checker_cases as checks


@pytest.fixture
def context(tmp_path):
    (tmp_path / "outputs").mkdir()
    return CheckContext(tmp_path, tmp_path, SKILL, sys.executable)


def write(ctx, name, value):
    path = ctx.outputs / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def test_migration_predicate_rejects_reordered_queue_and_stale_pointer(context):
    text = "# Plan\nNext: H-A-01\n\n## Queue\n### H-A-01 — first\n- Goal: first\n### H-A-02 — next\n- Goal: next\n"
    for name in ("original-plan.md", "unified-plan.md", "classic-plan.md"):
        write(context, name, text)
    assert checks.migration_order(context)[0] and checks.migration_next(context)[0]
    write(context, "unified-plan.md", text.replace("H-A-01", "H-A-03"))
    assert not checks.migration_order(context)[0] and not checks.migration_next(context)[0]


@pytest.mark.parametrize("replacement", ["- Resource: CPU\n", "- Priority: 9\n", "- Impact: 1\n"])
def test_lean_queue_rejects_silent_restoration_of_optional_fields(context, replacement):
    text = "# Plan\nOrdering: queue\nNext: H-A-01\n\n## Queue\n### H-A-01 — first\n- Claimed: none\n- Hypothesis: count\n"
    write(context, "project/plan.md", text)
    assert checks.lean_queue(context)[0]
    write(context, "project/plan.md", text + replacement)
    assert not checks.lean_queue(context)[0]


def test_example_counts_reject_missing_examples_and_nonzero_info(context):
    values = {name: {"ERROR": 0, "WARN": 0, "INFO": 0} for name in checks.EXAMPLES}
    write(context, "results.json", values)
    assert checks.example_counts(context)[0]
    values["quick-script-cleanup"]["INFO"] = 1
    write(context, "results.json", values)
    assert not checks.example_counts(context)[0]
    values.pop("quick-script-cleanup")
    write(context, "results.json", values)
    assert not checks.example_counts(context)[0]


def test_journal_fields_require_exact_actions_and_real_values(context):
    rows = [{"action": key, "status_at_start": "in-flight", "journal_key": "shared-key",
             "child_key": "shared-key", "deadline_seconds": 30} for key in ("X-A-001", "X-A-002")]
    write(context, "attempt-state.jsonl", "\n".join(map(json.dumps, rows)))
    assert all(check(context)[0] for check in (checks.journal_started, checks.journal_key, checks.journal_deadline))
    rows[0].update(status_at_start="done", child_key="different", deadline_seconds=0)
    write(context, "attempt-state.jsonl", "\n".join(map(json.dumps, rows)))
    assert all(not check(context)[0] for check in (checks.journal_started, checks.journal_key, checks.journal_deadline))
    rows[1]["action"] = "X-A-001"
    write(context, "attempt-state.jsonl", "\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError):
        checks.attempt_state(context)


def test_retained_response_needs_all_response_components(context):
    assertion = checks.response("X-A-002", 7, "archive-uncertain-731", "acknowledgement lost")
    value = {"action": "X-A-002", "returncode": 7, "stdout": "remote-id: archive-uncertain-731",
             "stderr": "acknowledgement lost after acceptance"}
    path = ".ro/external-results/X-A-002.json"
    write(context, path, value)
    assert assertion(context)[0]
    value["returncode"] = 0
    write(context, path, value)
    assert not assertion(context)[0]


def test_reconciliation_report_binds_remote_result_to_each_action(context):
    text = ("X-A-001: archive-accepted-482, exit code 0; receipt stored; response complete.\n\n"
            "X-A-002: archive-uncertain-731, exit code 7; acknowledgement lost after acceptance; reconcile before retry.\n")
    write(context, "reconciliation.md", text)
    assert checks.reconciliation_report(context)[0]
    write(context, "reconciliation.md", text.replace("archive-uncertain-731", "archive-accepted-482"))
    assert not checks.reconciliation_report(context)[0]


def test_report_cleanliness_does_not_accept_empty_or_warning_report(context):
    resumed = checks.CHECKS["direction-review-grace", "90-resumed-due.md"]
    write(context, "resumed-check.txt", "INFO guard.direction.stale: review due\n")
    assert resumed(context)[0]
    write(context, "resumed-check.txt", "WARN guard.direction.stale: review due\n")
    assert not resumed(context)[0]
    assert not checks.clean_text("")
    assert not checks.clean_text("0 errors, 0 warnings")
    assert checks.clean_text("CONSISTENCY: PASS\n")
    assert not checks.clean_text("CONSISTENCY: PASS\nWARN guard.direction.stale handoff.md: due\n")
    assert not checks.clean_text("CONSISTENCY: OK\n- INFO guard.control.missing discoveries.md: control\n", info=True)
    assert not checks.clean_text("CONSISTENCY: PASS\nINFO guard.control.missing discoveries.md: control\n", info=True)


def test_retry_defect_classification_uses_ledger_not_scenario_folder_names():
    base = "### X-A-001 — action\n- Status: prepared\n- Candidate: a, hash 123\n- Destination: local\n- Expected: count 3 (written 2026-10-24 10:00)\n"
    assert "missing" in checks.retry_defects(base + "- Retry of: X-A-099\n")
    assert "self" in checks.retry_defects(base + "- Retry of: X-A-001\n")
    other = base.replace("X-A-001", "X-A-002").replace("10:00", "11:00")
    assert "forward" in checks.retry_defects(base + "- Retry of: X-A-002\n" + other)
    assert "cyclic" in checks.retry_defects(base + "- Retry of: X-A-002\n" + other + "- Retry of: X-A-001\n")
    assert "ambiguous" in checks.retry_defects(base + base)


def test_preservation_rejects_added_file_and_changed_hash(context):
    before = {"agents.md": "a" * 64, "nested/source.txt": "b" * 64}
    write(context, "before.json", before)
    write(context, "after.json", before)
    assert checks.snapshot_preservation(context)[0]
    write(context, "after.json", {**before, "added.txt": "c" * 64})
    assert not checks.snapshot_preservation(context)[0]
    write(context, "after.json", {**before, "nested/source.txt": "c" * 64})
    assert not checks.snapshot_preservation(context)[0]


def test_quick_goal_search_requires_item_identity_and_matching_goal(context):
    write(context, "project/plan.md", "### H-A-01 — Empty archive\n- Goal: amber-crate accepts empty input\n"
          "- Evidence: empty input untested\n- Next test: run empty fixture\n")
    write(context, "duplicate-check.txt", "H-A-01 Goal: amber-crate accepts empty input\n")
    assert checks.simple_shape(context)[0] and checks.goal_search(context)[0]
    write(context, "duplicate-check.txt", "H-A-99 Goal: amber-crate accepts empty input\n")
    assert not checks.goal_search(context)[0]


def test_saved_pointer_checks_require_a_real_settings_snapshot(context):
    write(context, "before-agents.md", "## Project settings\n- Preset: quick\n- Plan collector: off\n"
          "The core operation table owns the general reading list.\n## Project rules\n")
    assert checks.pointers(context, enabled=False, core=True)[0]
    assert not checks.pointers(context, enabled=True)[0]
    write(context, "enabled-agents.md", "## Project settings\n- Preset: quick\n- Plan collector: local/model\n"
          "- references/plan-collector.md\n## Project rules\n")
    assert checks.pointers(context, enabled=True)[0]


def test_read_only_reviewer_rejects_mutations_and_project_check_commands(context):
    (context.case_dir / "files").mkdir()
    (context.case_dir / "files/evidence.md").write_bytes(b"source evidence\n")
    (context.outputs / "evidence.md").write_bytes(b"source evidence\n")
    write(context, "final.md", "HOLD until the missing comparison is provided.\n")
    path = context.run_dir / "events.jsonl"
    def trace(command):
        path.write_text(json.dumps({"type": "item.completed", "item": {"type": "command_execution",
                        "command": command, "exit_code": 0, "aggregated_output": "source evidence"}}), encoding="utf-8")
    trace("cat evidence.md")
    assert checks.reviewer_read_only(context)[0]
    trace("python check_project.py .")
    assert not checks.reviewer_read_only(context)[0]
    trace("cat evidence.md")
    write(context, "evidence.md", "changed evidence\n")
    assert not checks.reviewer_read_only(context)[0]


def test_no_review_wait_rejects_structured_agent_launch(context):
    write(context, "final.md", "The replication is recorded and remains PENDING.\n")
    path = context.run_dir / "events.jsonl"
    path.write_text(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}), encoding="utf-8")
    assert checks.no_unavailable_review(context)[0]
    path.write_text(json.dumps({"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent"}}), encoding="utf-8")
    assert not checks.no_unavailable_review(context)[0]
