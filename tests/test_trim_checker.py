"""Trim ceremony while retaining ownership, experiment results and explicit override scope."""

from __future__ import annotations

import datetime as dt

import pytest

from conftest import (NOW, append_discovery, append_events, check, check_project, event, found, item,
                      make_project, run_init, set_queue, set_slot, unified_project)
from guard_helpers import discovery, plan, project, setting, shared
from test_project_rules import replace_rules


def unscored(item_id="H-A-01", claimed=None):
    return "\n".join(line for line in item(item_id, claimed=claimed).splitlines()
                     if not any(line.startswith(f"- {name}:") for name in check_project.PLAN_SCORES)) + "\n"


def quick_project(parent):
    target = make_project(parent, "quick", "--preset", "quick", "--platforms", "Shell", "--user", "operator")
    set_slot(target, "A", "Shell")
    return target


def session(completed="H-A-01, H-A-02", **kwargs):
    return event("2026-10-25 10:00", "A", "session", host="Shell", discovery="none", new_items="none",
                 extra=f"- Completed: {completed}\n" + kwargs.pop("extra", ""), **kwargs)


@pytest.mark.parametrize("preset", ["quick", "work-project", "solo-research", "team-research",
                                    "competition-solo", "competition-team"])
def test_work_profiles_and_queue_ordering_may_omit_scores_and_priority(tmp_path, preset):
    platforms = "Shell, Editor" if preset.endswith("team") or preset == "team-research" else "Shell"
    target = make_project(tmp_path, "example", "--preset", preset, "--platforms", platforms,
                          "--competition", "hub/task-a", "--external-actions", "release-tool publish", "--phase-clock", "off")
    claimed = "none" if check(target).unified else None
    plan(target, unscored(claimed=claimed))
    missing = found(check(target), "ERROR", "plan.field.missing")
    assert {issue.field for issue in missing} == (set() if preset in {"quick", "work-project", "solo-research"}
                                               else check_project.PLAN_SCORES)


def test_quick_session_accounts_for_multiple_completions_without_routine_discoveries(tmp_path):
    target = quick_project(tmp_path)
    append_events(target, event("2026-10-25 09:00", "A", "none", new_items="H-A-01, H-A-02", host="Shell"),
                  session())
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")
    assert checker.finished_items == {"H-A-01", "H-A-02"}
    assert {issue.field for issue in found(checker, "INFO", "event.reason.missing")} == {
        "Discovery updates", "New plan items"}
    plan(target, unscored("H-A-02"))
    assert [issue.record for issue in found(check(target), "ERROR", "event.finished.queued")] == ["H-A-02"]


@pytest.mark.parametrize("completed", ["", "H-A-01/s1", "H-A-01 and H-A-02", "finished H-A-01"])
def test_quick_session_completion_ids_are_explicit(tmp_path, completed):
    target = quick_project(tmp_path)
    append_events(target, session(completed))
    assert found(check(target), "ERROR", "event.completed.format")


@pytest.mark.parametrize("decision", ["changed", "unchanged"])
def test_quick_experiments_need_a_discovery_even_when_rejecting_a_change(tmp_path, decision):
    target = quick_project(tmp_path)
    append_events(target, session(extra=f"- Decision: {decision}\n"))
    assert found(check(target), "WARN", "event.decision.discovery")
    append_discovery(target, discovery().replace("- Host: Claude Code", "- Host: Shell"))
    path = target / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Discovery updates: none\n",
                                                           "- Discovery updates: D-A-001\n"), encoding="utf-8")
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")


@pytest.mark.parametrize("preset", ["work-project", "user:saved-quick", "user:saved-work"])
def test_quick_session_history_survives_preset_changes(tmp_path, preset):
    target = quick_project(tmp_path)
    if preset.startswith("user:"):
        source = target if preset.endswith("quick") else make_project(
            tmp_path, "saved-work", "--preset", "work-project", "--platforms", "Shell")
        saved = run_init(source, "--save-preset", preset.removeprefix("user:"))
        assert saved.returncode == 0, saved.stderr
    summary = session(extra="- Decision: unchanged\n").replace(
        "- Discovery updates: none\n", "- Discovery updates: D-A-001\n")
    append_events(target, event("2026-10-25 09:00", "A", "none", new_items="H-A-01, H-A-02", host="Shell"),
                  summary)
    append_discovery(target, discovery().replace("- Host: Claude Code", "- Host: Shell"))
    set_slot(target, "A", "released", "none")
    checker = check(target)
    assert not found(checker, "ERROR") and not found(checker, "WARN")

    result = run_init(target, "--reconfigure", "--preset", preset, "--platforms", "Shell", "--migrate")
    assert result.returncode == 0, result.stderr
    checker = check(target, max(NOW, dt.datetime.now()))
    assert checker.values["preset"] == preset and checker.work
    assert not found(checker, "ERROR") and not found(checker, "WARN"), [i.render() for i in checker.issues]
    assert checker.finished_items == {"H-A-01", "H-A-02"}
    assert summary in (target / "handoff.md").read_text(encoding="utf-8")

    # Historical session records still require evidence and validate completion syntax.
    path = target / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Discovery updates: D-A-001\n",
                                                           "- Discovery updates: none\n").replace(
        "- Completed: H-A-01, H-A-02\n", "- Completed: H-A-01 and H-A-02\n"), encoding="utf-8")
    checker = check(target, max(NOW, dt.datetime.now()))
    assert found(checker, "WARN", "event.decision.discovery")
    assert found(checker, "ERROR", "event.completed.format")


def test_quick_session_completion_satisfies_a_planned_insight(tmp_path):
    target = quick_project(tmp_path)
    setting(target, "Guards", "light")
    setting(target, "Guard set", "G6")
    shared(target, "Not applicable", "none")
    append_discovery(target, discovery(Kind="insight", Status="planned H-A-01").replace(
        "- Host: Claude Code", "- Host: Shell"))
    append_events(target, session())
    assert not found(check(target), check_id="guard.insight.overdue")


def test_completion_history_is_parsed_once_per_event(tmp_path, monkeypatch):
    target = unified_project(tmp_path)
    append_events(target, *(event("2026-10-25 10:00", "A", f"H-A-{number:04}") for number in range(100)))
    original = check_project.Checker.completed_items
    calls = []

    def counted(self, record):
        calls.append(record.key)
        return original(self, record)

    monkeypatch.setattr(check_project.Checker, "completed_items", counted)
    checker = check(target)
    assert len(calls) == len(checker.events)
    assert not found(checker, "ERROR")


@pytest.mark.parametrize("profile", ["work", "research", "competition"])
def test_work_direction_review_needs_only_gap_and_decisions(tmp_path, profile):
    target = project(tmp_path, "GD", profile=profile)
    append_discovery(target, discovery(Kind="direction-review", Gap="the output still needs a clear owner",
                                      Decisions="assign the owner before extending scope"))
    missing = found(check(target), check_id="guard.direction.incomplete")
    assert bool(missing) is (profile != "work")


def override(target, checks, *, reason="temporary constraint", expiry="2026-10-25", record=""):
    replace_rules(target, "## Project rules\n\n### Active overrides\n\n"
                  f"- Temporary exception | Checks: {checks} | Record: {record} | Reason: {reason} | Expires: {expiry}\n")


@pytest.mark.parametrize("reason,expiry", [("temporary constraint", "2026-10-25"), ("", "2026-10-25"),
                                         ("temporary constraint", "2026-10-24"),
                                         ("temporary constraint", "invalid")])
def test_process_override_needs_reason_and_live_expiry(tmp_path, reason, expiry):
    target = project(tmp_path, "GD", mode="strict")
    append_events(target, event("2026-10-24 12:00", "A", "H-A-01"))
    override(target, "guard.direction.stale", reason=reason, expiry=expiry)
    checker = check(target)
    issue = found(checker, check_id="guard.direction.stale")[0]
    valid = bool(reason) and expiry == "2026-10-25"
    assert issue.severity == ("INFO" if valid else "ERROR")
    assert ("active override" in issue.message) is valid


def test_ranking_override_applies_to_only_its_named_field_and_record(tmp_path):
    target = unified_project(tmp_path)
    path = target / "plan.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Ordering: queue", "Ordering: priority"), encoding="utf-8")
    set_queue(target, unscored("H-A-01", claimed="none"), unscored("H-A-02", claimed="none"))
    override(target, "plan.field.missing:Priority", record="H-A-01")
    checker = check(target)
    waived = found(checker, "INFO", "plan.field.missing")
    assert [(issue.record, issue.field) for issue in waived] == [("H-A-01", "Priority")]
    assert len(found(checker, "ERROR", "plan.field.missing")) == 13


@pytest.mark.parametrize("check_id", ["jobs.mutate-bound", "jobs.unmonitored", "external.uncertain",
                                    "external.gate", "plan.claim.missing", "plan.field.missing",
                                    "plan.field.missing:Sources", "guard.instrument.circular", "ext.expected"])
def test_safety_and_structural_checks_cannot_be_waived(tmp_path, check_id):
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", claimed=None))
    override(target, check_id)
    checker = check(target)
    assert found(checker, "ERROR", "rules.override.scope")
    assert found(checker, "ERROR", "plan.claim.missing")
