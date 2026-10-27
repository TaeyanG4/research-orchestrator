"""Work records keep resume context without imposing research bookkeeping."""

from __future__ import annotations

import datetime as dt

import pytest

from conftest import (NOW, append_discovery, append_events, check, check_project, event, found,
                      make_project, run_init, set_queue)
from guard_helpers import discovery


ITEM = """### H-A-01 — Prepare an archive
- Claimed: none
- Hypothesis: the archive can be reproduced
- Evidence: the approved brief defines its inputs
- Next test: inventory the inputs
"""

SESSION = """### 2026-10-25 10:00 — A — session
- Host: Shell
- User: operator
- Action: prepared H-A-01 and H-A-02
- Result: inputs ready; no remaining preparation
- Completed: H-A-01, H-A-02
"""


def work_project(parent, preset="work-project", **kwargs):
    return make_project(parent, "work", "--preset", preset, "--platforms", "Shell", "--user", "operator",
                        *[arg for key, value in kwargs.items() for arg in ("--" + key, value)])


@pytest.mark.parametrize("preset", ["work-project", "custom"])
def test_compact_work_items_accept_profile_overrides_and_next_pointer(tmp_path, preset):
    target = work_project(tmp_path, preset, profile="work", workflow="unified")
    set_queue(target, ITEM)
    path = target / "plan.md"
    path.write_text(path.read_text(encoding="utf-8").replace("\n## Queue\n", "\nNext: H-A-01\n\n## Queue\n"),
                    encoding="utf-8")
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")
    fields = checker.plan_items["H-A-01"].fields
    assert len(fields) == 7
    assert {name: fields[name] for name in check_project.WORK_ROUTING_DEFAULTS} == {
        "Resource": "CPU", "Parallel": "NO", "Other": "NONE"}


@pytest.mark.parametrize("field", ["Claimed", "Hypothesis", "Evidence", "Next test"])
def test_work_still_requires_resume_fields(tmp_path, field):
    target = work_project(tmp_path)
    set_queue(target, "\n".join(line for line in ITEM.splitlines() if not line.startswith(f"- {field}:")))
    missing = found(check(target), "ERROR")
    assert [(issue.check, issue.field) for issue in missing] == [
        ("plan.claim.missing" if field == "Claimed" else "plan.field.missing", field)]


@pytest.mark.parametrize("preset,profile", [("work-project", "work"), ("custom", "work"), ("quick", "research")])
def test_work_or_quick_accepts_goal_and_default_routing(tmp_path, preset, profile):
    target = work_project(tmp_path, preset, profile=profile, workflow="unified")
    set_queue(target, ITEM.replace("Hypothesis:", "Goal:"))
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")
    fields = checker.plan_items["H-A-01"].fields
    assert fields["Goal"] == "the archive can be reproduced"
    assert {name: fields[name] for name in check_project.WORK_ROUTING_DEFAULTS} == {
        "Resource": "CPU", "Parallel": "NO", "Other": "NONE"}


def test_explicit_work_routing_overrides_defaults(tmp_path):
    target = work_project(tmp_path)
    set_queue(target, ITEM + "- Resource: GPU\n- Parallel: YES\n- Other: remote-batch\n")
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")
    fields = checker.plan_items["H-A-01"].fields
    assert (fields["Resource"], fields["Parallel"], fields["Other"]) == ("GPU", "YES", "remote-batch")


@pytest.mark.parametrize("preset", ["solo-research", "competition-solo"])
def test_research_and_competition_require_hypothesis_but_default_routing(tmp_path, preset):
    target = work_project(tmp_path, preset, competition="hub/task-a", **{"phase-clock": "off", "external-actions": "release-tool publish"})
    set_queue(target, ITEM.replace("Hypothesis:", "Goal:"))
    missing = {issue.field for issue in found(check(target), "ERROR", "plan.field.missing")}
    assert "Hypothesis" in missing
    assert not {"Resource", "Parallel", "Other"} & missing


@pytest.mark.parametrize("preset", ["solo-research", "competition-solo"])
def test_compact_session_history_survives_reconfiguration_without_rewriting(tmp_path, preset):
    target = work_project(tmp_path)
    append_events(target, event("2026-10-25 09:00", "A", "none", host="Shell", new_items="H-A-01, H-A-02"),
                  SESSION)
    before = check(target)
    assert not found(before, "ERROR") and not found(before, "WARN")
    assert before.finished_items == {"H-A-01", "H-A-02"}

    result = run_init(target, "--reconfigure", "--preset", preset, "--platforms", "Shell",
                      "--competition", "hub/task-a", "--external-actions", "release-tool publish", "--phase-clock", "off")
    assert result.returncode == 0, result.stderr
    checker = check(target, max(NOW, dt.datetime.now()))
    assert not found(checker, "ERROR") and not found(checker, "WARN"), [i.render() for i in checker.issues]
    assert checker.finished_items == before.finished_items
    assert SESSION in (target / "handoff.md").read_text(encoding="utf-8")
    # The historical allowance does not weaken new research/competition items or per-item events.
    set_queue(target, ITEM.replace("H-A-01", "H-A-03"))
    append_events(target, SESSION.replace("— session", "— H-A-04").replace("- Completed: H-A-01, H-A-02\n", ""))
    checker = check(target, max(NOW, dt.datetime.now()))
    assert {i.field for i in found(checker, "ERROR", "plan.field.missing")} == (
        check_project.WORK_PLAN_OPTIONAL - set(check_project.WORK_ROUTING_DEFAULTS))
    assert {i.field for i in found(checker, "ERROR", "event.field.missing")} == check_project.SESSION_OPTIONAL


@pytest.mark.parametrize("field", ["Host", "User", "Action", "Result", "Completed"])
def test_compact_session_still_requires_resume_and_attribution_fields(tmp_path, field):
    target = work_project(tmp_path)
    append_events(target, "\n".join(line for line in SESSION.splitlines() if not line.startswith(f"- {field}:")))
    assert field in {i.field for i in found(check(target), "ERROR", "event.field.missing")}


@pytest.mark.parametrize("decision", ["changed", "unchanged"])
def test_compact_session_keeps_reusable_result_evidence(tmp_path, decision):
    target = work_project(tmp_path)
    append_events(target, SESSION + f"- Decision: {decision}\n")
    assert found(check(target), "WARN", "event.decision.discovery")
    append_discovery(target, discovery().replace("- Host: Claude Code", "- Host: Shell"))
    path = target / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Completed: H-A-01, H-A-02\n",
                    "- Discovery updates: D-A-001\n- Completed: H-A-01, H-A-02\n"), encoding="utf-8")
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")


def test_compact_session_rejects_completed_items_still_queued(tmp_path):
    target = work_project(tmp_path)
    set_queue(target, ITEM)
    append_events(target, SESSION)
    assert [i.record for i in found(check(target), "ERROR", "event.finished.queued")] == ["H-A-01"]


def test_session_stage_progress_is_recent_activity_without_completing_the_item(tmp_path):
    target = work_project(tmp_path)
    append_events(target, SESSION.replace("prepared H-A-01 and H-A-02", "completed H-A-01/s1").replace(
        "- Completed: H-A-01, H-A-02", "- Completed: none"))
    checker = check(target)
    assert checker.has_event_since("A", "H-A-01", NOW - dt.timedelta(days=8))
    assert not checker.finished_items
