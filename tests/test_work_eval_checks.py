"""Negative controls for the work-profile behavior assertions."""
from __future__ import annotations

import sys
import json

import pytest

from scripts.evals import checks, work_checks
from conftest import SKILL
from test_work_light import ITEM, SESSION


TRIAL_FINDING = {"selection_rule": "suffix-only", "decision": "reject",
                 "required_inputs": ["alpha.txt", "bravo.log", "charlie.txt"],
                 "omitted_inputs": ["bravo.log"]}


@pytest.fixture
def context(tmp_path):
    output = tmp_path / "outputs"
    output.mkdir()
    (output / "work-snapshot").mkdir()
    queue = ITEM + "- Stages: s1 inventory | s2 review\n\n" + ITEM.replace("H-A-01", "H-A-02") + "- Stages: s1 copy | s2 review\n"
    for name, text in {
        "plan.md": "# Plan\n\n## Queue\n\n" + queue,
        "queued-plan.md": queue,
        "handoff.md": "### Agent: A\n- Next action: H-A-01\n\n" + SESSION,
        "discoveries.md": "# Discoveries\n",
        "inventory.txt": "alpha.txt\nbravo.log\ncharlie.txt\n",
        "readiness.md": "Input count: 3\nConversion: not started\n",
        "agents.md": "- Preset: solo-research\n- Profile: research\n",
        "work-snapshot/handoff.md": SESSION,
        "work-snapshot/plan.md": "# Plan\n\n## Queue\n",
        "work-snapshot/discoveries.md": "## D-A-001 — Selection trial\n- Finding: " + json.dumps(TRIAL_FINDING) + "\n- Evidence: trial.md\n",
    }.items():
        (output / name).write_text(text, encoding="utf-8")
    return checks.CheckContext(tmp_path, tmp_path, SKILL, sys.executable)


def test_work_assertions_accept_compact_outputs(context):
    for group in work_checks.WORK_CHECKS.values():
        for name, check in group.items():
            if name != "05-checker-clean":
                assert check(context)[0], (name, check(context)[1])
    assert checks.staged_queue(context)[0]


@pytest.mark.parametrize("finding", [
    "bravo.log is optional; use suffix-only selection",
    "Reject suffix-only selection because it drops required bravo.log",  # missing requested structure
    json.dumps({**TRIAL_FINDING, "decision": "accept"}),
    json.dumps({**TRIAL_FINDING, "selection_rule": "explicit-inventory"}),
    json.dumps({**TRIAL_FINDING, "required_inputs": ["alpha.txt", "charlie.txt"]}),
    json.dumps({**TRIAL_FINDING, "omitted_inputs": []}),
    json.dumps({**TRIAL_FINDING, "omitted_inputs": ["alpha.txt"]}),
    json.dumps(TRIAL_FINDING) + " but bravo.log is optional",
    "[]", "null",
])
def test_reusable_discovery_rejects_reversed_or_incomplete_conclusions(context, finding):
    path = context.outputs / "work-snapshot/discoveries.md"
    path.write_text("## D-A-001 — Selection trial\n- Finding: " + finding + "\n- Evidence: trial.md\n", encoding="utf-8")
    assert not work_checks.reusable_discovery(context)[0]


def test_reusable_discovery_accepts_equivalent_json_layout(context):
    path = context.outputs / "work-snapshot/discoveries.md"
    path.write_text("## D-A-001 — Selection trial\n- Finding: "
                    + json.dumps(TRIAL_FINDING, sort_keys=True, separators=(",", ":"))
                    + "\n- Evidence: trial.md\n", encoding="utf-8")
    assert work_checks.reusable_discovery(context)[0]


def test_ordering_accepts_explicit_next_and_rejects_scores(context):
    plan = context.outputs / "plan.md"
    handoff = context.outputs / "handoff.md"
    handoff.write_text(context.text("handoff.md").replace("Next action: H-A-01", "Next action: H-A-02"), encoding="utf-8")
    assert not work_checks.light_ordering(context)[0]
    plan.write_text("Next: H-A-02\n" + context.text("plan.md"), encoding="utf-8")
    assert work_checks.light_ordering(context)[0]
    plan.write_text(context.text("plan.md").replace("- Next test:", "- Priority: 12\n- Next test:"), encoding="utf-8")
    assert not work_checks.light_ordering(context)[0]
    assert not work_checks.compact_items(context)[0]


@pytest.mark.parametrize("optional", [
    "- Ready by: 2026-11-02\n",
    "- Important stages: s2\n",
    "- Ready by: 2026-11-02\n- Important stages: s2\n",
])
@pytest.mark.parametrize("goal,step", [("Hypothesis", "Next test"), ("Goal", "Next step")])
def test_compact_items_accept_useful_operational_fields(context, optional, goal, step):
    path = context.outputs / "plan.md"
    path.write_text(context.text("plan.md").replace("Hypothesis:", f"{goal}:")
                    .replace("Next test:", f"{step}:").replace("- Stages:", optional + "- Stages:"),
                    encoding="utf-8")
    assert work_checks.compact_items(context)[0]


@pytest.mark.parametrize("redundant", [
    "- Resource: CPU\n", "- Parallel: NO\n", "- Other: NONE\n",
    "- Priority: 12\n", "- Status: queued\n",
    "- Goal: the archive can be reproduced\n", "- Next step: inventory the inputs\n",
    "- Evidence: the approved brief defines its inputs\n",
    "- Ready by: 2026-11-02\n- Ready by: 2026-11-02\n",
    "- Important stages: s2\n- Important stages: s2\n",
    "- Ready by: \n", "- Important stages: \n",
])
def test_compact_items_reject_redundant_or_empty_fields(context, redundant):
    path = context.outputs / "plan.md"
    path.write_text(context.text("plan.md").replace("- Stages:", redundant + "- Stages:"),
                    encoding="utf-8")
    assert not work_checks.compact_items(context)[0]


@pytest.mark.parametrize("required", ["Claimed", "Hypothesis", "Evidence", "Next test", "Stages"])
def test_compact_items_still_require_resume_content(context, required):
    path = context.outputs / "plan.md"
    path.write_text("\n".join(line for line in context.text("plan.md").splitlines()
                              if not line.startswith(f"- {required}:")), encoding="utf-8")
    assert not work_checks.compact_items(context)[0]


@pytest.mark.parametrize("name,path,old,new", [
    ("session_summary", "handoff.md", SESSION, SESSION + SESSION.replace(" — session", " — none")),
    ("no_routine_discovery", "discoveries.md", "# Discoveries", "## D-A-001 — Setup completed"),
    ("preparation_complete", "inventory.txt", "bravo.log\n", ""),
    ("preparation_complete", "readiness.md", "not started", "complete"),
    ("session_completions", "work-snapshot/plan.md", "# Plan", ITEM),
    ("reusable_discovery", "work-snapshot/discoveries.md", "trial.md", "unsupported"),
    ("history_preserved", "handoff.md", "inputs ready", "changed history"),
    ("compact_bookkeeping", "queued-plan.md", "- Next test:", "- Cost: 1\n- Next test:"),
    ("compact_bookkeeping", "work-snapshot/handoff.md", "- Completed:", "- Resource: none\n- Completed:"),
])
def test_work_assertions_reject_relevant_regressions(context, name, path, old, new):
    target = context.outputs / path
    target.write_text(target.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    assert not getattr(work_checks, name)(context)[0]


@pytest.mark.parametrize("next_field", ["Next test", "Next step"])
def test_work_assertions_accept_goal_alias_without_resource_ceremony(context, next_field):
    path = context.outputs / "plan.md"
    path.write_text(context.text("plan.md").replace("Hypothesis:", "Goal:").replace("Next test:", f"{next_field}:"),
                    encoding="utf-8")
    assert work_checks.compact_items(context)[0]
    assert checks.staged_queue(context)[0]
    path.write_text(context.text("plan.md").replace("Goal:", "Unrelated:"), encoding="utf-8")
    assert not work_checks.compact_items(context)[0]
    assert not checks.staged_queue(context)[0]


@pytest.mark.parametrize("marker", ["```", "~~~~"])
def test_fenced_sample_does_not_create_or_replace_a_discovery(context, marker):
    sample = (f"\n{marker}markdown\n## D-A-001 — Format sample\n"
              f"- Finding: ...\n- Evidence: ...\n{marker}\n")
    for name in ("discoveries.md", "work-snapshot/discoveries.md"):
        path = context.outputs / name
        path.write_text(context.text(name) + sample, encoding="utf-8")
    assert work_checks.no_routine_discovery(context)[0]
    assert work_checks.reusable_discovery(context)[0]
    path = context.outputs / "discoveries.md"
    path.write_text(context.text("discoveries.md") + "\n## D-A-002 — Actual routine completion\n", encoding="utf-8")
    assert not work_checks.no_routine_discovery(context)[0]


def test_work_event_accepts_explained_absence_but_rejects_empty_followup(context):
    path = context.outputs / "work-snapshot/handoff.md"
    original = context.text("work-snapshot/handoff.md")
    path.write_text(original + "- New plan items: none — authorized preparation is complete\n", encoding="utf-8")
    assert work_checks.compact_bookkeeping(context)[0]
    path.write_text(original + "- New plan items: none\n", encoding="utf-8")
    assert not work_checks.compact_bookkeeping(context)[0]


@pytest.mark.parametrize("marker", ["```", "~~~~"])
def test_history_preserves_fenced_evidence_and_detects_edits(context, marker):
    evidence = f"{marker}sh\necho actual evidence\n### not a record\n{marker}\n"
    original = SESSION.replace("- Result:", evidence + "- Result:")
    for name in ("work-snapshot/handoff.md", "handoff.md"):
        (context.outputs / name).write_text(original, encoding="utf-8")
    assert work_checks.history_preserved(context)[0]
    (context.outputs / "handoff.md").write_text(
        original.replace("actual evidence", "fabricated evidence"), encoding="utf-8")
    assert not work_checks.history_preserved(context)[0]
