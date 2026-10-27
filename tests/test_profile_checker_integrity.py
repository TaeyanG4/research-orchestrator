"""Scheduling, review and milestone boundary regressions."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from conftest import (append_discovery, check, found, init, item, make_project, rs, run_init,
                      set_queue, set_slot)
from guard_helpers import discovery, project, review, setting, shared


@pytest.mark.parametrize("state", ["pending", "blocked", "incomplete", "pendng", "complete later", ""])
def test_overdue_milestone_requires_complete(tmp_path, state):
    target = project(tmp_path, "G8", mode="strict")
    setting(target, "Phase clock", "start 2026-10-01, deadline 2026-10-31")
    shared(target, "Milestones", f"10 {state}; 25 complete; 75 complete")
    checker = check(target)
    assert len(found(checker, "WARN", "guard.phase.milestone")) == 1


@pytest.mark.parametrize("state", ["pendng", "complete later", "unknown"])
def test_malformed_milestone_is_reported_even_before_due(tmp_path, state):
    target = project(tmp_path, "G8")
    setting(target, "Phase clock", "start 2026-10-25, deadline 2026-11-25")
    shared(target, "Milestones", f"10 {state}; 25 pending; 75 pending")
    checker = check(target)
    assert found(checker, "WARN", "guard.phase.state")
    assert not found(checker, check_id="guard.phase.milestone")


def test_completed_milestones_satisfy_overdue_checkpoints(tmp_path):
    target = project(tmp_path, "G8", mode="strict")
    setting(target, "Phase clock", "start 2026-10-01, deadline 2026-10-31")
    shared(target, "Milestones", "baseline complete; core family complete; freeze complete")
    assert not [issue for issue in check(target).issues if issue.check.startswith("guard.phase.")]


def compact_item(key, claimed=True):
    return (f"### {key} — restore archive\n" + ("- Claimed: none\n" if claimed else "") +
            "- Goal: preserve an archive\n- Evidence: the source archive is immutable\n"
            "- Next test: compare every restored record\n")


def test_work_migration_keeps_mixed_queue_order_and_next_through_round_trip(tmp_path):
    target = make_project(tmp_path, "archive", "--preset", "work-project", "--workflow", "classic",
                          "--platforms", "Cedar Shell", "--git", "off", "--user", "operator")
    set_slot(target, "A", "released", "none")
    plan = target / "plan.md"
    plan.write_text("# Archive — Plan\n\nNext: H-A-01\n\n## Agent: A\n\n" +
                    compact_item("H-A-01", False) + "\n" + item("H-A-02", claimed=None), encoding="utf-8")
    for workflow in ("unified", "classic"):
        result = run_init(target, "--reconfigure", "--workflow", workflow, "--migrate", "--user", "operator")
        assert result.returncode == 0, result.stdout + result.stderr
        text = plan.read_text(encoding="utf-8")
        assert [block.item_id for block in init.parse_plan_items(text)] == ["H-A-01", "H-A-02"]
        assert "\nNext: H-A-01\n" in text
        assert not found(check(target), "ERROR")


@pytest.mark.parametrize("profile,ordering,expected", [
    ("work", "", ["H-A-01", "H-A-02"]),
    ("research", "", ["H-A-02", "H-A-01"]),
    ("competition", "", ["H-A-02", "H-A-01"]),
    ("research", "Ordering: queue\n", ["H-A-01", "H-A-02"]),
    ("competition", "Ordering: queue\n", ["H-A-01", "H-A-02"]),
])
def test_migration_respects_profile_and_explicit_queue(profile, ordering, expected):
    settings = rs.resolve({"profile": profile, "workflow": "unified"}, None, {})
    text = "# Archive\n\n" + ordering + "Next: H-A-01\n\n## Agent: A\n\n"
    text += item("H-A-01", claimed=None).replace("- Impact: 1", "- Impact: 0").replace("- Priority: 9", "- Priority: 7")
    text += "\n" + item("H-A-02", claimed=None)
    rendered, count = init.plan_to_unified(text, settings, "Archive")
    assert count == 2
    assert [block.item_id for block in init.parse_plan_items(rendered)] == expected
    assert "\nNext: H-A-01\n" in rendered
    if ordering:
        assert ordering in rendered


@pytest.mark.parametrize("profile", ["work", "research", "competition"])
def test_queue_ordering_and_default_routing_are_valid_in_every_profile(tmp_path, profile):
    target = project(tmp_path, "GD", profile=profile)
    shared(target, "Not applicable", "GD — fixed archive restoration has no strategic review cycle")
    text = item("H-A-01")
    optional = {"Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority",
                "Resource", "Parallel", "Other"}
    text = "\n".join(line for line in text.splitlines() if line[2:].split(":", 1)[0] not in optional) + "\n"
    set_queue(target, text)
    path = target / "plan.md"
    path.write_text(path.read_text(encoding="utf-8").replace("\n## Queue", "\nOrdering: queue\nNext: H-A-01\n\n## Queue"),
                    encoding="utf-8")
    checker = check(target)
    assert not [issue for issue in checker.issues if issue.check.startswith("plan.")]
    assert {key: checker.plan_items["H-A-01"].fields[key] for key in ("Resource", "Parallel", "Other")} == {
        "Resource": "CPU", "Parallel": "NO", "Other": "NONE"}


@pytest.mark.parametrize("field,value,expected", [
    ("Impact", "999", "plan.score.range"), ("Cost", "-1", "plan.score.range"),
    ("Confidence", "1.5", "plan.score.range"), ("Priority", "999999", "plan.score.range"),
    ("Priority", "8", "plan.priority.mismatch"),
])
def test_optional_scores_are_validated_when_supplied(tmp_path, field, value, expected):
    target = project(tmp_path, "GD", profile="work")
    text = re.sub(rf"^- {field}:.*$", f"- {field}: {value}", item("H-A-01"), flags=re.M)
    set_queue(target, text)
    assert found(check(target), "ERROR", expected)


def test_priority_without_factors_and_dangling_next_are_rejected(tmp_path):
    target = project(tmp_path, "GD", profile="work")
    set_queue(target, compact_item("H-A-01") + "- Priority: 9\n")
    path = target / "plan.md"
    path.write_text(path.read_text(encoding="utf-8").replace("\n## Queue", "\nNext: H-ZZ-9999\n\n## Queue"),
                    encoding="utf-8")
    checker = check(target)
    assert found(checker, "ERROR", "plan.priority.inputs")
    assert found(checker, "ERROR", "plan.next.invalid")


def test_research_direction_requires_core_evidence_but_other_parts_are_advice(tmp_path):
    target = project(tmp_path, "GD", mode="strict")
    append_discovery(target, discovery(Kind="direction-review", Gap="precision of printed means is unknown",
                                      Decisions="bound all rounding endpoints", Data_audit="only printed aggregates are available"))
    checker = check(target)
    assert not found(checker, check_id="guard.direction.incomplete")
    assert found(checker, "INFO", "guard.direction.advice")
    setting(target, "Guard thresholds", "direction-parts=full")
    assert found(check(target), "ERROR", "guard.direction.incomplete")


@pytest.mark.parametrize("part", ["Gap", "Decisions", "Data audit"])
def test_research_direction_needs_each_core_part(tmp_path, part):
    target = project(tmp_path, "GD", mode="strict")
    append_discovery(target, review(omit=part))
    assert found(check(target), "ERROR", "guard.direction.incomplete")


@pytest.mark.parametrize("token", ["fake:", "x@y", "subagent:reviewer", "Subagent:reviewer@2026-10-24T12:00",
                                  "subagent:reviewer@2026-02-30T12:00", "subagent:reviewer@2099-01-01T12:00",
                                  "subagent:reviewer@2026-10-24", "subagent:reviewer@2026-10-24T24:00"])
def test_reviewer_identity_requires_complete_current_timestamp(tmp_path, token):
    target = project(tmp_path, "GD")
    setting(target, "Verification", "independent-review")
    text = discovery(Session="session:source@2026-10-24T09:00").replace("- Cross-check: PENDING", "- Cross-check: VERIFIED")
    text = text.replace("- Reviews: \n", f"- Reviews: \n  - Claude Code (A): CLOSED — reviewer {token} — recomputed the evidence\n")
    append_discovery(target, text)
    checker = check(target)
    assert found(checker, "WARN", "discovery.review.identity")
    assert found(checker, "ERROR", "discovery.state.unbacked")


def test_missing_cross_check_gets_only_the_missing_field_diagnostic(tmp_path):
    target = make_project(tmp_path, "review", "--preset", "team-research", "--platforms", "Cedar Shell, Maple Shell",
                          "--user", "operator", "--git", "off")
    append_discovery(target, discovery().replace("- Cross-check: PENDING\n", ""))
    checker = check(target)
    related = [issue for issue in checker.issues if issue.record == "D-A-001" and issue.field == "Cross-check"]
    assert [issue.check for issue in related] == ["discovery.field.missing"]
