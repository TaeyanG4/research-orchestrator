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
    real = "CONSISTENCY: OK (1 plan items, 0 discoveries, 1 events, workflow classic, verification self)\n"
    assert checks.clean_text(real) and checks.clean_text(real, info=True)
    with_info = real.replace("self)", "self; 1 info)") + "- INFO record.order: advice\n"
    assert checks.clean_text(with_info) and not checks.clean_text(with_info, info=True)
    # Invented, clipped and unreadable summaries are not checker results.
    assert not checks.clean_text("CONSISTENCY: PASS\n")
    assert not checks.clean_text("CONSISTENCY: 1 problem(s)\n")
    assert not checks.clean_text("CONSISTENCY: 0 error(s), 2 warning(s), 0 info (1 plan items)\n")
    assert not checks.clean_text("CONSISTENCY: cannot read the project files: denied\n")
    assert not checks.clean_text("CONSISTENCY: PASS\nWARN guard.direction.stale handoff.md: due\n")
    assert not checks.clean_text("CONSISTENCY: OK\n- INFO guard.control.missing discoveries.md: control\n", info=True)


def test_registered_clean_predicates_agree_with_the_labelled_checker_outputs(context):
    """Every registered cleanliness predicate grades the summary-integrity samples as labelled."""
    from scripts.evals import deterministic_artifacts
    samples = json.loads((SKILL / "evals/checker-summary-integrity/files/checker-outputs.json")
                         .read_text(encoding="utf-8"))
    expected = {"clean": True, "info": True, "warning": False, "clipped-warning": False, "error": False,
                "contradictory": False, "unreadable": False, "invented-pass": False}
    assert set(samples) == set(expected)
    clean_report = checks.CHECKS["quick-goal-routing", "90-checker-clean.md"]
    for key, text in samples.items():
        assert checks.clean_text(text) is expected[key], key
        write(context, "check.txt", text)
        assert deterministic_artifacts.clean_check(context, "check.txt") is expected[key], key
        write(context, "checker.txt", text)
        assert clean_report(context)[0] is expected[key], key


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


SIZE = ("- WARN history.size discoveries.md: the startup discovery index is 70 KiB (limit 48 KiB); run `ro archive discoveries`\n"
        "- WARN history.size handoff.md: handoff.md is 214 KiB (limit 192 KiB); run `ro archive events`\n")
PENDING = "- INFO discovery.review.pending [A] discoveries.md:{}: D-A-301 awaits review\n"
GUARD = "- INFO guard.direction.stale: 1 issue(s); examples: none; direction review is due\n"
INVALID = {"unreadable": "CONSISTENCY: cannot read the project files: denied\n", "invented": "CONSISTENCY: PASS\n",
           "clipped": "CONSISTENCY: 0 error(s), 1 warning(s), 0 info (1 plan items)\n", "missing": None}


def report(warnings: str = "", infos: str = "") -> str:
    """Checker output whose summary counts match its listed findings."""
    w = warnings.count("\n- WARN ") + warnings.startswith("- WARN ")
    i = sum(int(line.split(": ", 1)[1].split(" ")[0]) if " issue(s); examples:" in line else 1
            for line in infos.splitlines() if line.startswith("- INFO "))
    head = (f"CONSISTENCY: 0 error(s), {w} warning(s), {i} info (1 plan items)" if w else
            "CONSISTENCY: OK (1 plan items" + (f"; {i} info" if i else "") + ")")
    return head + "\n" + warnings + infos


def capture(ctx, name, text):
    path = ctx.outputs / name
    if text is None:
        path.unlink(missing_ok=True)
    else:
        write(ctx, name, text)


def test_history_archive_predicates_separate_real_archiving_from_controls(context):
    write(context, "history-checks/index.txt", "Discovery index: 1 live (VERIFIED 1), 0 archived.\n\n## D-A-001 — x\n- Finding: short\n")
    assert checks.compact_index(context)[0]
    write(context, "history-checks/index.txt", "## D-A-001 — x\n- Finding: " + "x" * 200 + "\n")
    assert not checks.compact_index(context)[0]
    write(context, "history-checks/check-before.txt", report(SIZE, PENDING.format(3922) + GUARD))
    assert checks.size_warnings(context)[0]
    write(context, "history-checks/check-after-discoveries.txt",
          report(SIZE.splitlines(keepends=True)[1], PENDING.format(1200) + GUARD))
    assert checks.findings_preserved(context)[0]  # moved line numbers are not changed findings
    write(context, "history-checks/check-after-discoveries.txt", report(SIZE, GUARD))
    assert not checks.findings_preserved(context)[0]
    write(context, "history-checks/check-after.txt", report("", PENDING.format(1200) + GUARD))
    assert checks.limits_restored(context)[0]
    write(context, "history-checks/check-after.txt", report(SIZE))
    assert not checks.limits_restored(context)[0]
    full = "- Source: A\n- Cross-check: {}\n- Finding: f\n- Evidence: e\n"
    entries = ["## D-A-001 — a\n- Archived: docs/archive/discoveries-2026-08.md\n- Cross-check: VERIFIED\n- Finding: f\n"]
    entries += [f"## D-A-{n:03d} — x\n" + full.format("PENDING") for n in range(301, 332)]
    write(context, "project/discoveries.md", "# Discoveries\n\n" + "\n".join(entries))
    assert checks.settled_only(context)[0]
    write(context, "project/discoveries.md", "# Discoveries\n\n" + "\n".join(entries).replace(
        "## D-A-331 — x\n- Source: A", "## D-A-331 — x\n- Archived: docs/archive/x.md\n- Source: A"))
    assert not checks.settled_only(context)[0]
    write(context, "history-checks/opened.txt", "## D-A-001 — a\n- Evidence: e\n\n(archived in docs/archive/discoveries-2026-08.md)\n")
    write(context, "history-checks/dupcheck.txt", "docs/archive/discoveries-2026-08.md:5: ## D-A-001 — a\n")
    assert checks.archived_findable(context)[0]
    write(context, "history-checks/dupcheck.txt", "discoveries.md:5: ## D-A-001 — a\n")
    assert not checks.archived_findable(context)[0]
    kept = ("### 2026-09-24 13:00 — A — H-A-01/s1\n### 2026-09-28 13:00 — A — none\n### 2026-09-28 15:00 — B — none\n\n"
            "## Archived history\n- [docs/archive/handoff-2026-08.md](docs/archive/handoff-2026-08.md): 300 events, x\n")
    write(context, "project/handoff.md", kept)
    assert checks.event_archive(context)[0]
    write(context, "project/handoff.md", kept.replace("### 2026-09-24 13:00 — A — H-A-01/s1\n", ""))
    assert not checks.event_archive(context)[0]


def test_tool_registry_predicates_need_real_checker_output(context):
    write(context, "check.txt", report("", "- INFO handoff.shared.missing handoff.md: x\n"))
    assert checks.no_tool_findings(context)[0]
    write(context, "check.txt", report("- WARN tools.field docs/tools.md:3: x\n"))
    assert not checks.no_tool_findings(context)[0]
    write(context, "control-check.txt", report("- WARN tools.unregistered tools/submit_v2.py: tools/submit_v2.py sits beside\n"))
    assert checks.unregistered_control(context)[0]
    write(context, "control-check.txt", report())
    assert not checks.unregistered_control(context)[0]


@pytest.mark.parametrize("kind", sorted(INVALID))
def test_checker_predicates_reject_unreadable_invented_clipped_and_missing_output(context, kind):
    """Each registered 7.0.0 checker predicate first requires a complete, real checker report."""
    valid = {"history-checks/check-before.txt": report(SIZE), "history-checks/check-after-discoveries.txt": report(SIZE),
             "history-checks/check-after.txt": report(), "check.txt": report(),
             "control-check.txt": report("- WARN tools.unregistered tools/submit_v2.py: x\n")}
    routes = {("history-archive", "02-size-warning.md"): ["history-checks/check-before.txt"],
              ("history-archive", "04-findings-preserved.md"): ["history-checks/check-before.txt",
                                                                "history-checks/check-after-discoveries.txt"],
              ("history-archive", "07-limits-restored.md"): ["history-checks/check-after.txt"],
              ("tool-registry", "03-clean-registry.md"): ["check.txt"],
              ("tool-registry", "04-unregistered-control.md"): ["control-check.txt"]}
    for key, names in routes.items():
        for name, text in valid.items():
            write(context, name, text)
        predicate = checks.CHECKS[key]
        assert predicate(context)[0], key
        for name in names:
            capture(context, name, INVALID[kind])
            assert not predicate(context)[0], (key, name)
            write(context, name, valid[name])


def test_review_cache_variant_predicates_need_both_briefs_and_bounded_growth(context):
    review = "Checker: ERROR 0; WARN 1; INFO 0\nevent.stage.review: 1; IDs H-A-01\n"
    for n in (1, 2):
        write(context, f"cache-checks/unreadable-brief-{n}.txt", review)
    assert checks.unreadable_briefs(context)[0]
    write(context, "cache-checks/unreadable-brief-2.txt", "Checker: ERROR 0; WARN 0; INFO 0\n")  # cached clean result
    assert not checks.unreadable_briefs(context)[0]
    runs = [{"moment": "before-open", "error": "artifact changed while hashing", "bytes_read": 0},
            {"moment": "while-reading", "error": "artifact changed while hashing", "bytes_read": 2}]
    write(context, "cache-checks/growth.json", runs)
    assert checks.growth_bound(context)[0]
    for broken in ([runs[0]], [runs[0], {**runs[1], "error": ""}], [runs[0], {**runs[1], "bytes_read": 100}],
                   [runs[0], {**runs[1], "bytes_read": "2"}]):
        write(context, "cache-checks/growth.json", broken)
        assert not checks.growth_bound(context)[0], broken
    write(context, "cache-checks/growth.json", "not json")
    assert not checks.growth_bound(context)[0]


def test_restore_rearchive_predicate_needs_the_revision_and_one_archived_copy(context):
    opened = "## D-A-002 — x\n- Finding: base. Revised after a second run.\n\n(archived in docs/archive/discoveries-2026-08.md)\n"
    write(context, "history-checks/rearchived.txt", opened)
    write(context, "project/docs/archive/discoveries-2026-08.md", "# Archived\n\n## D-A-002 — x\n- Finding: revised\n")
    assert checks.restore_rearchive(context)[0]
    write(context, "project/docs/archive/discoveries-2026-09.md", "# Archived\n\n## D-A-002 — old copy\n- Finding: base\n")
    assert not checks.restore_rearchive(context)[0]  # a leftover second copy
    (context.outputs / "project/docs/archive/discoveries-2026-09.md").unlink()
    write(context, "history-checks/rearchived.txt", opened.replace(" Revised after a second run.", ""))
    assert not checks.restore_rearchive(context)[0]
