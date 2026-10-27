"""Designated launch stages require scoped review; routine progress stays lightweight."""

import argparse
import contextlib
import datetime as dt
import sys

import pytest

import ro_evidence as evidence
import ro_jobs as jobs
import ro_stages as stages
from check_project import Block, Checker
from test_ro_evidence import EvidenceProject
from conftest import append_discovery, append_events, check, event, found, make_project, set_slot
from guard_helpers import discovery, plan


@pytest.fixture
def project(tmp_path):
    project = EvidenceProject(tmp_path)
    project.slot = "A"
    project.values.update(environment="linux / local", receipt_policy="self", workflow="unified")
    (tmp_path / "plan.md").write_text(
        "## Queue\n### H-A-01 — staged migration\n- Stages: s1 dry run | s2 cut-over | s3 report\n"
        "- Important stages: s2\n", encoding="utf-8")
    (tmp_path / "contract.md").write_text("reviewed launch contract\n", encoding="utf-8")
    (tmp_path / "result.md").write_text("observed evidence\n", encoding="utf-8")
    return project


def receipt(project, scope, artifact="contract.md", reviewer="independent-reviewer", verdict="PASS"):
    evidence.receipt_add(project, artifact, reviewer, verdict, scope)


def options(item="H-A-01/s2", require_receipt="contract.md"):
    return argparse.Namespace(cmd=[sys.executable, "-c", "pass"], item=item, expect="10s",
                              confirm="0s", require_receipt=require_receipt)


@pytest.mark.parametrize("invalid", ["absent", "wrong-stage", "wrong-phase", "self", "padded-self", "changed", "failed"])
def test_important_stage_refuses_without_current_independent_scoped_receipt(project, monkeypatch, invalid):
    scope = {"wrong-stage": "H-A-01/s3:before", "wrong-phase": "H-A-01/s2:after"}.get(invalid, "H-A-01/s2:before")
    if invalid != "absent":
        reviewer = (" " + project.session + " " if invalid == "padded-self" else
                    project.session if invalid == "self" else "independent-reviewer")
        receipt(project, scope, reviewer=reviewer)
    if invalid == "changed":
        (project.root / "contract.md").write_text("unreviewed changes\n", encoding="utf-8")
    if invalid == "failed":
        receipt(project, scope, verdict="FAIL")
    launched = []
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *a, **k: launched.append(a))
    before = {str(path.relative_to(project.root)): path.read_bytes() for path in project.root.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="no current independent PASS"):
        jobs.launch(project, options())
    assert launched == []
    assert before == {str(path.relative_to(project.root)): path.read_bytes() for path in project.root.rglob("*") if path.is_file()}
    assert not (project.state / "jobs.json").exists()
    assert not (project.state / "job-sequence.json").exists()


@pytest.mark.parametrize("item,artifact", [("H-A-01/s2", "contract.md"), ("H-A-01/s1", None)])
def test_reviewed_important_stage_and_unreviewed_routine_stage_reach_launch_reservation(project, monkeypatch, item, artifact):
    if artifact:
        receipt(project, item + ":before")
    # Stop at the first reservation operation: reaching it proves the review gate passed
    # without launching a background process as part of this deterministic test.
    calls = []
    def reserve(_project):
        calls.append(item)
        raise RuntimeError("reservation reached")
    monkeypatch.setattr(jobs, "_launch_identity", reserve)
    monkeypatch.setattr(jobs, "process_start", lambda pid: "known-process")
    with pytest.raises(RuntimeError, match="reservation reached"):
        jobs.launch(project, options(item, artifact))
    assert calls == [item]


@pytest.mark.parametrize("invalid", ["typo", "undeclared", "missing", "duplicate", "no-plan", "fenced",
                                      "archived", "bare", "wrong-workflow", "wrong-title-separator"])
def test_invalid_launch_target_has_no_receipt_reservation_or_process_side_effects(project, monkeypatch, invalid):
    path = project.root / "plan.md"
    item = "H-A-01/s22" if invalid == "typo" else "H-A-01/s2"
    if invalid == "undeclared":
        path.write_text("## Queue\n### H-A-01 — ordinary work\n- Goal: inspect files\n", encoding="utf-8")
    elif invalid == "missing":
        item = "H-A-99/s2"
    elif invalid == "duplicate":
        path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")
    elif invalid == "no-plan":
        path.unlink()
    elif invalid == "fenced":
        path.write_text("```markdown\n" + path.read_text(encoding="utf-8") + "```\n", encoding="utf-8")
    elif invalid in ("archived", "bare", "wrong-workflow", "wrong-title-separator"):
        original = path.read_text(encoding="utf-8")
        replacement = {"archived": "## Archived history", "bare": "# Plan", "wrong-workflow": "## Agent: A"}
        text = (original.replace(" — ", " - ") if invalid == "wrong-title-separator" else
                original.replace("## Queue", replacement[invalid]))
        path.write_text(text, encoding="utf-8")
    calls = []
    monkeypatch.setattr(stages, "_valid_receipt", lambda *a, **kw: calls.append("receipt"))
    monkeypatch.setattr(stages, "receipt_check", lambda *a, **kw: calls.append("receipt"))
    monkeypatch.setattr(jobs, "_launch_identity", lambda *a: calls.append("reservation"))
    monkeypatch.setattr(jobs, "process_start", lambda *a: calls.append("process identity"))
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *a, **kw: calls.append("process"))
    before = {str(p.relative_to(project.root)): p.read_bytes() for p in project.root.rglob("*") if p.is_file()}
    message = "not declared" if invalid in ("typo", "undeclared") else "exactly one active plan record"
    with pytest.raises(ValueError, match=message):
        jobs.launch(project, options(item, "contract.md"))
    assert calls == []
    assert before == {str(p.relative_to(project.root)): p.read_bytes() for p in project.root.rglob("*") if p.is_file()}
    assert not (project.state / "jobs.json").exists()
    assert not (project.state / "job-sequence.json").exists()


@pytest.mark.parametrize("workflow,heading", [("unified", "## Queue"), ("classic", "## Agent: A")])
def test_only_live_workflow_section_counts_when_archived_and_fenced_ids_repeat(project, workflow, heading):
    project.values["workflow"] = workflow
    path = project.root / "plan.md"
    live = path.read_text(encoding="utf-8").replace("## Queue", heading)
    path.write_text(live + "\n## Archived history\n### H-A-01 — old trial\n- Stages: s7 archived\n"
                    "\n```markdown\n" + live + "```\n", encoding="utf-8")
    stages.launch_review(project, "H-A-01/s1", None)
    with pytest.raises(ValueError, match="not declared"):
        stages.launch_review(project, "H-A-01/s7", None)


@pytest.mark.parametrize("change", ["important-policy", "receipt", "removed-item", "removed-stage"])
def test_launch_rechecks_policy_and_receipt_inside_reservation_lock(project, monkeypatch, change):
    item = "H-A-01/s1" if change == "important-policy" else "H-A-01/s2"
    artifact = None if change == "important-policy" else "contract.md"
    if artifact:
        receipt(project, item + ":before")

    @contextlib.contextmanager
    def changed_lock(*args):
        path = project.root / "plan.md"
        text = path.read_text(encoding="utf-8")
        if change == "important-policy":
            path.write_text(text.replace("Important stages: s2", "Important stages: s1 | s2"), encoding="utf-8")
        elif change == "receipt":
            (project.root / "contract.md").write_text("changed after early validation\n", encoding="utf-8")
        elif change == "removed-item":
            path.write_text("## Queue\n", encoding="utf-8")
        else:
            path.write_text(text.replace(" | s2 cut-over", ""), encoding="utf-8")
        yield

    calls = []
    monkeypatch.setattr(project, "lock", changed_lock)
    monkeypatch.setattr(jobs, "_launch_identity", lambda *a: calls.append("reservation"))
    monkeypatch.setattr(jobs, "process_start", lambda *a: "known-process")
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *a, **kw: calls.append("process"))
    message = {"important-policy": "requires --require-receipt", "receipt": "no current independent PASS",
               "removed-item": "exactly one active plan record", "removed-stage": "not declared"}[change]
    with pytest.raises(ValueError, match=message):
        jobs.launch(project, options(item, artifact))
    assert calls == []
    assert not (project.state / "jobs.json").exists()
    assert not (project.state / "job-sequence.json").exists()


def test_important_stage_cannot_be_hidden_by_bare_item_or_missing_artifact(project):
    with pytest.raises(ValueError, match="explicit item/sN"):
        stages.launch_review(project, "H-A-01", None)
    with pytest.raises(ValueError, match="requires --require-receipt"):
        stages.launch_review(project, "H-A-01/s2", None)


@pytest.mark.parametrize("field", ["s4", "s2 | s2", "important"])
def test_important_stage_designation_requires_distinct_declared_stages(field):
    with pytest.raises(ValueError, match="distinct declared stages"):
        stages.important_stages({"Stages": "s1 pilot | s2 expand", "Important stages": field})


@pytest.mark.parametrize("heading", ["H-A-01/s1", "session"])
def test_decision_changed_result_requires_review_before_next_launch(project, heading):
    text = (f"## Completed / review log\n### 2020-01-01 08:00 — A — {heading}\n"
            "- Action: completed H-A-01/s1\n- Result: pilot reverses the rollout decision\n"
            "- Decision: changed\n- Review artifact: result.md\n")
    (project.root / "handoff.md").write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="no current independent PASS"):
        stages.launch_review(project, "H-A-01/s3", None)
    receipt(project, "H-A-01/s1:before", "result.md")
    with pytest.raises(ValueError, match="no current independent PASS"):
        stages.launch_review(project, "H-A-01/s3", None)
    receipt(project, "H-A-01/s1:after", "result.md")
    stages.launch_review(project, "H-A-01/s3", None)
    (project.root / "result.md").write_text("revised result\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no current independent PASS"):
        stages.launch_review(project, "H-A-01/s3", None)


def test_changed_result_cannot_reuse_receipt_from_before_result(project):
    receipt(project, "H-A-01/s1:after", "result.md")
    data = project.read_json("receipts.json", {})
    data["receipts"][0]["created_at"] = 1
    project.write_json("receipts.json", data)
    with pytest.raises(ValueError, match="predates"):
        stages.result_review(project, "H-A-01/s1", {"Decision": "changed", "Review artifact": "result.md"},
                             "2020-01-01 08:00")


def test_routine_result_and_unrelated_item_do_not_require_review(project):
    (project.root / "handoff.md").write_text(
        "### 2020-01-01 08:00 — A — H-A-01/s1\n- Decision: operational\n"
        "### 2020-01-01 09:00 — A — H-B-02/s1\n- Decision: changed\n", encoding="utf-8")
    stages.launch_review(project, "H-A-01/s3", None)


def test_missing_result_artifact_reports_review_gap(project):
    with pytest.raises(ValueError, match="Review artifact"):
        stages.result_review(project, "H-A-01/s1", {"Decision": "changed"})


def test_result_checker_adapter_is_read_only_and_handles_missing_receipts(tmp_path):
    (tmp_path / "result.md").write_text("observed evidence\n", encoding="utf-8")
    issue = stages.result_review_issue(tmp_path, "H-A-01/s1",
                                       {"Decision": "changed", "Review artifact": "result.md"})
    assert "no current independent PASS" in issue
    assert not (tmp_path / ".ro").exists()
    assert stages.result_review_issue(tmp_path, "H-A-01/s1", {"Decision": "operational"}) is None


def test_changed_stage_result_blocks_before_next_job_reservation(project, monkeypatch):
    (project.root / "handoff.md").write_text(
        "### 2020-01-01 08:00 — A — H-A-01/s1\n- Decision: changed\n"
        "- Review artifact: result.md\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(jobs, "_launch_identity", lambda *args: calls.append("reserve"))
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *args, **kwargs: calls.append("execute"))
    before = (project.root / "handoff.md").read_bytes()
    with pytest.raises(ValueError, match="no current independent PASS"):
        jobs.launch(project, options("H-A-01/s3", None))
    assert calls == []
    assert (project.root / "handoff.md").read_bytes() == before
    assert not (project.state / "jobs.json").exists()


@pytest.mark.parametrize('decision,reviewed,expected', [('operational', False, False),
                                                       ('changed', False, True), ('changed', True, False)])
def test_checker_reports_changed_result_review_without_mutation(project, decision, reviewed, expected):
    if reviewed:
        receipt(project, 'H-A-01/s1:after', 'result.md')
    event = Block(key='H-A-01/s1', line=1, heading_date='2020-01-01 08:00', owner='A',
                  fields={'Decision': decision, 'Review artifact': 'result.md', 'Discovery updates': 'D-A-001'})
    before = {str(p.relative_to(project.root)): p.read_bytes() for p in project.root.rglob('*') if p.is_file()}
    checker = Checker(project.root)
    checker.check_decision(event, 'handoff.md:1', event.key)
    assert any(issue.check == 'event.stage.review' for issue in checker.issues) is expected
    assert before == {str(p.relative_to(project.root)): p.read_bytes() for p in project.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize("preset", ["quick", "work-project"])
@pytest.mark.parametrize("same_item", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_work_changed_stages_keep_independent_reviews_after_summary_edit(tmp_path, monkeypatch,
                                                                       preset, same_item, mixed):
    root = make_project(tmp_path, "staged-work", "--preset", preset, "--platforms", "Shell",
                        "--user", "operator", "--guards", "off")
    set_slot(root, "A", "Shell")
    project = EvidenceProject(root)
    project.slot = "A"
    project.values.update(profile="work", workflow="classic" if preset == "quick" else "unified",
                          environment="linux/bash", receipt_policy="self")
    claim = "" if preset == "quick" else "- Claimed: none\n"
    plan(root, "".join(f"### {key} — staged task\n{claim}- Goal: verify a change\n"
                       "- Evidence: preserved observations\n- Next test: inspect dependent result\n"
                       "- Stages: s1 sample | s2 compare | s3 finish\n"
                       for key in ("H-A-01", "H-A-02", "H-A-03")))
    keys = ["H-A-01/s1", "H-A-01/s2" if same_item else "H-A-02/s1"]
    histories = []
    for index, key in enumerate(keys, 1):
        artifact = f"result-{index}.md"
        (root / artifact).write_text(f"observation {index}\n", encoding="utf-8")
        append_discovery(root, discovery(f"D-A-{index:03}").replace("Host: Claude Code", "Host: Shell"))
        histories.append(event(f"2020-01-01 0{index + 7}:00", "A", key, host="Shell",
                               discovery=f"D-A-{index:03}",
                               extra=f"- Decision: changed\n- Review artifact: {artifact}\n"))
    if mixed:
        histories.append(event("2020-01-01 10:00", "A", "H-A-03/s1", host="Shell",
                               extra="- Decision: operational\n"))
    summary = ("### 2020-01-01 11:00 — A — session\n- Host: Shell\n- User: operator\n"
               f"- Action: completed {', '.join(keys)}" + (", H-A-03/s1" if mixed else "") + "\n"
               "- Result: results recorded; dependent work remains\n- Completed: none\n")
    append_events(root, *histories, summary)
    path = root / "handoff.md"
    before = path.read_text(encoding="utf-8")
    assert len(found(check(root), check_id="event.stage.review")) == 2
    # Summaries can lose every stage ID without changing the immutable evidence or gate.
    shortened = summary.replace(summary.splitlines()[3], "- Action: session results recorded")
    path.write_text(before.replace(summary, shortened), encoding="utf-8", newline="\n")
    expected_history = path.read_bytes()
    assert all(history in path.read_text(encoding="utf-8") for history in histories)

    def blocked(item):
        before_state = {p.name: p.read_bytes() for p in project.state.iterdir() if p.is_file()}
        with pytest.raises(ValueError, match="no current independent PASS|predates"):
            jobs.launch(project, options(item, None))
        assert before_state == {p.name: p.read_bytes() for p in project.state.iterdir() if p.is_file()}
        assert path.read_bytes() == expected_history

    monkeypatch.setattr(jobs, "_launch_identity", lambda *_: pytest.fail("blocked launch reserved a job"))
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda *a, **kw: pytest.fail("blocked launch started a process"))
    dependent = [key.split("/")[0] + "/s3" for key in keys]
    for item in dependent:
        blocked(item)
    # An operational history adds no result-review obligation for its own item.
    stages.launch_review(project, "H-A-03/s3", None)
    receipt(project, keys[0] + ":after", "result-1.md")
    if same_item:
        blocked(dependent[0])
    else:
        stages.launch_review(project, dependent[0], None)
    blocked(dependent[1])
    # Correct artifact with the wrong scope, self review, and a pre-observation receipt
    # cannot discharge the other stage's obligation.
    receipt(project, keys[0] + ":after", "result-2.md")
    blocked(dependent[1])
    receipt(project, keys[1] + ":after", "result-2.md", reviewer=project.session)
    blocked(dependent[1])
    receipt(project, keys[1] + ":after", "result-2.md")
    ledger = project.read_json("receipts.json", {})
    ledger["receipts"][-1]["created_at"] = dt.datetime(2020, 1, 1, 7).timestamp()
    project.write_json("receipts.json", ledger)
    blocked(dependent[1])
    receipt(project, keys[1] + ":after", "result-2.md")
    for item in dependent:
        stages.launch_review(project, item, None)
    checker = check(root)
    assert not found(checker, "ERROR") and not found(checker, "WARN"), [i.render() for i in checker.issues]
    assert checker.finished_items == set()
    assert path.read_bytes() == expected_history
    (root / "result-2.md").write_text("changed bytes\n", encoding="utf-8")
    blocked(dependent[1])
