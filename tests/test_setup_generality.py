"""General work vocabulary and conditional milestone scaffolding, without host or clock dependencies."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from conftest import SKILL, check, init, rs, set_queue


def initialize(target, *extra):
    target.mkdir()
    assert init.main([
        str(target), "--preset", "quick", "--platforms", "Codex", "--user", "operator",
        "--environment", "linux/bash", "--language", "en", "--git", "off", *extra,
    ]) == 0
    return target


def test_core_and_references_allow_decision_steps_and_exclusive_noncompute_resources():
    core = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    plan = (SKILL / "references" / "plan-items.md").read_text(encoding="utf-8")
    resources = (SKILL / "references" / "compute.md").read_text(encoding="utf-8")
    assert all(re.search(r"\b" + word + r"\b", core, re.I) for word in ("decision", "test", "comparison", "build", "draft"))
    assert re.search(r"record.{0,30}(?:findings|decisions)", core, re.I)
    prose = re.sub(r"```[^\n]*\n.*?```", "", plan, flags=re.S)
    assert {"Goal", "Evidence", "Next step"} <= set(re.findall(r"`([^`\n]+)`", prose))
    lead = resources.split("\n## ", 1)[0]
    assert all(word in lead for word in ("Exclusive resources", "compute", "shared database", "licensed seat"))
    assert "`Other: licensed-tool-seat`" in resources
    assert re.search(r"(?:shared lock|scheduler reservation)", resources)
    assert "shared-database" in resources and "Parallel: NO" in resources
    assert "GPU" not in "\n".join(re.findall(r"```[^\n]*\n(.*?)```", resources, re.S))


def test_work_goal_accepts_draft_step_and_named_exclusive_resource(tmp_path):
    target = initialize(tmp_path / "brief", "--workflow", "unified")
    set_queue(target, "### H-A-01 — Draft the review packet\n"
              "- Claimed: none\n- Goal: decide whether the proposed layout is ready for review\n"
              "- Evidence: the approved outline needs a rendered example\n"
              "- Parallel: NO\n- Other: licensed-tool-seat\n"
              "- Next step: draft and export one page using the reserved design seat\n")
    checker = check(target, now=dt.datetime(2026, 10, 25, 12))
    assert not [issue.render() for issue in checker.issues if issue.check.startswith("plan.")]
    fields = checker.plan_items["H-A-01"].fields
    assert fields["Resource"] == "CPU"
    assert fields["Parallel"] == "NO"
    assert fields["Other"] == "licensed-tool-seat"


@pytest.mark.parametrize("preset,platforms", [
    ("quick", "Codex"), ("competition-solo", "Codex"), ("competition-team", "Claude Code, Codex"),
])
@pytest.mark.parametrize("clock,thresholds,expected", [
    ("off", "milestones=10/25/75", None),
    ("2026-10-01,2026-10-31", "milestones=10/25/75", "10 pending; 25 pending; 75 pending"),
    ("2026-10-01,2026-10-31", "milestones=5/30/80", "5 pending; 30 pending; 80 pending"),
])
def test_fresh_handoff_scaffolds_only_configured_phase_clock_milestones(
        tmp_path, preset, platforms, clock, thresholds, expected):
    target = initialize(tmp_path / "schedule", "--preset", preset, "--platforms", platforms,
                        "--competition", "hub/task-a", "--external-actions", "release-tool publish", "--phase-clock", clock,
                        "--guard-thresholds", thresholds, "--guards", "light since 2026-10-01",
                        "--guard-set", "G8")
    handoff = (target / "handoff.md").read_text(encoding="utf-8")
    lines = re.findall(r"^- Milestones: (.*)$", handoff, re.M)
    assert lines == ([] if expected is None else [expected])
    assert "{{" not in handoff
    checker = check(target, now=dt.datetime(2026, 10, 25, 12))
    phase = [issue for issue in checker.issues if issue.check.startswith("guard.phase.")]
    if expected is None:
        assert not phase
    else:
        assert phase  # Due checkpoints remain unfinished; the scaffold never invents completion.
        assert all(issue.check == "guard.phase.milestone" and "(pending)" in issue.message for issue in phase)
    settings = rs.resolve({}, None, rs.read_settings((target / "agents.md").read_text(encoding="utf-8")).values)
    assert rs.conditions(settings)["phaseclock"] == ("off" if clock == "off" else "on")


def test_clock_reconfiguration_adds_missing_milestones_but_preserves_progress(tmp_path):
    target = initialize(tmp_path / "reconfigure")
    handoff = target / "handoff.md"
    assert "- Milestones:" not in handoff.read_text(encoding="utf-8")
    assert init.main([str(target), "--reconfigure", "--phase-clock", "2026-10-01,2026-10-31",
                      "--guard-thresholds", "milestones=5/30/80"]) == 0
    text = handoff.read_text(encoding="utf-8")
    assert "- Milestones: 5 pending; 30 pending; 80 pending\n" in text
    text = text.replace("5 pending; 30 pending; 80 pending", "5 complete; 30 blocked; 80 pending")
    handoff.write_text(text, encoding="utf-8", newline="\n")
    for extra in ([], ["--phase-clock", "off"]):
        assert init.main([str(target), "--reconfigure", *extra]) == 0
        assert handoff.read_text(encoding="utf-8") == text


def test_repair_uses_saved_clock_shares_without_rewriting_existing_records(tmp_path):
    target = initialize(tmp_path / "repair", "--phase-clock", "2026-10-01,2026-10-31",
                        "--guard-thresholds", "milestones=15/40/90")
    handoff = target / "handoff.md"
    before = {name: (target / name).read_bytes() for name in ("agents.md", "plan.md", "discoveries.md")}
    handoff.unlink()
    assert init.main([str(target), "--user", "operator"]) == 0
    assert "- Milestones: 15 pending; 40 pending; 90 pending\n" in handoff.read_text(encoding="utf-8")
    assert {name: (target / name).read_bytes() for name in before} == before
