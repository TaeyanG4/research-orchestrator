"""Launch reservations use current ownership, never archived snapshots."""

import argparse
import contextlib
import datetime as dt
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from check_project import Checker
import ro_jobs as jobs
from ro_markdown import unfenced
import ro_state as state
from conftest import check, found, make_project


NOW = dt.datetime(2026, 10, 27, 12, 0)
HISTORY = Path(__file__).resolve().parents[1] / "skills/research-orchestrator/evals/active-record-history/files"


def test_history_fixture_passes_complete_checker_for_current_operator(tmp_path):
    project = make_project(tmp_path, "history", "--preset", "quick", "--workflow", "unified",
                           "--platforms", "Shell", "--git", "off")
    for name in ("plan.md", "handoff.md"):
        (project / name).write_bytes((HISTORY / name).read_bytes())
    checker = check(project, NOW)
    assert not found(checker, "ERROR") and not found(checker, "WARN"), [i.render() for i in checker.issues]
    assert checker.handoff_sections["A"].fields["Current host"] == "Shell"


@pytest.fixture
def launch_project(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.platform, "node", lambda: "fixture-machine")
    monkeypatch.setattr(jobs, "process_start", lambda _pid: "fixture-process")
    monkeypatch.setattr(state, "process_start", lambda _pid: "fixture-process")
    monkeypatch.setattr(jobs.time, "time", lambda: NOW.timestamp())
    project = state.Project(tmp_path, slot="A", session="fixture-session")
    values = project.settings()
    values.update(workflow="classic", environment="windows/powershell" if os.name == "nt" else "linux/bash")
    monkeypatch.setattr(project, "settings", lambda **_kw: values)
    (tmp_path / "handoff.md").write_text(
        "# Handoff\n## Shared state\n- Active compute: none\n\n## Active handoff\n"
        "### Agent: A\n- Current host: Shell\n- Current user: operator\n\n"
        "### Agent: B\n- Current host: Shell\n- Current user: collaborator\n\n"
        "## Archived history\n", encoding="utf-8")
    spawned = []

    def completed_runner(command, **_kwargs):
        spawned.append(command)
        entries = project.read_json("jobs.json")
        entries[-1].update(status="finished", ended=NOW.timestamp(), exit_code=0,
                           outcome="process exited with code 0")
        project.write_json("jobs.json", entries)
        return SimpleNamespace(stdin=io.BytesIO())

    monkeypatch.setattr(jobs.subprocess, "Popen", completed_runner)
    project.spawned = spawned
    return project


def plan(project, workflow, owner="A", identifier="H-A-01", claim=None):
    project.settings()["workflow"] = workflow
    heading = "Queue" if workflow == "unified" else f"Agent: {owner}"
    fields = f"- Claimed: {claim or owner + ' since 2026-10-27 11:00'}\n" if workflow == "unified" else ""
    (project.root / "plan.md").write_text(
        f"# Plan\n## {heading}\n### {identifier} — current task\n{fields}"
        "- Goal: inspect the current task\n- Stages: s1 inspect\n", encoding="utf-8")


def options(item="H-A-01"):
    return argparse.Namespace(cmd=["fixture-worker"], item=item, expect="10s", confirm="0s")


def reservation_snapshot(project):
    return {name: (project.state / name).read_bytes() if (project.state / name).exists() else None
            for name in ("job-sequence.json", "jobs.json")}


@pytest.mark.parametrize("workflow,claim,item", [
    ("classic", None, "H-B-01"), ("classic", None, "H-B-01/s1"),
    ("unified", "B since 2026-10-27 11:00", "H-A-01"),
    ("unified", "B since 2026-10-27 11:00", "H-A-01/s1"),
    ("unified", "none", "H-A-01"), ("unified", "A", "H-A-01"),
])
@pytest.mark.parametrize("existing_registry", [False, True])
def test_launch_refuses_foreign_or_missing_ownership_without_reserving_or_spawning(
        launch_project, workflow, claim, item, existing_registry):
    project = launch_project
    plan(project, workflow, owner="B", identifier=item.split("/", 1)[0], claim=claim)
    if existing_registry:
        project.write_json("job-sequence.json", {"last": 4})
        project.write_json("jobs.json", [{"id": "J-A-0004", "status": "finished", "exit_code": 0}])
    before = reservation_snapshot(project)
    with pytest.raises(ValueError, match="must be (claimed by slot A|in slot A's plan section)"):
        jobs.launch(project, options(item))
    assert reservation_snapshot(project) == before
    assert project.spawned == []
    assert not (project.state / "logs").exists()


@pytest.mark.parametrize("workflow,item", [("classic", "H-A-01"), ("classic", "H-A-01/s1"),
                                           ("unified", "H-B-01"), ("unified", "H-B-01/s1")])
def test_owned_item_reaches_runner_after_locked_ownership_check(launch_project, monkeypatch, workflow, item):
    project = launch_project
    plan(project, workflow, identifier=item.split("/", 1)[0])
    verify, checked = jobs._launch_ownership, []

    def under_lock(project, item):
        assert getattr(project._locks, "held", {}).get("state", 0) > 0
        checked.append(item)
        verify(project, item)

    monkeypatch.setattr(jobs, "_launch_ownership", under_lock)
    assert "J-A-0001" in jobs.launch(project, options(item))
    assert checked == [item]
    assert len(project.spawned) == 1
    assert project.read_json("job-sequence.json") == {"last": 1}
    assert project.read_json("jobs.json")[0]["item"] == item


def test_launch_rechecks_claim_after_acquiring_reservation_lock(launch_project, monkeypatch):
    project = launch_project
    plan(project, "unified")
    original_lock = project.lock

    @contextlib.contextmanager
    def transferred_before_acquire(*args, **kwargs):
        with original_lock(*args, **kwargs):
            path = project.root / "plan.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "Claimed: A since", "Claimed: B since"), encoding="utf-8")
            yield

    monkeypatch.setattr(project, "lock", transferred_before_acquire)
    before = reservation_snapshot(project)
    with pytest.raises(ValueError, match="must be claimed by slot A"):
        jobs.launch(project, options())
    assert reservation_snapshot(project) == before
    assert project.spawned == []


@pytest.mark.parametrize("archive_first", [False, True])
def test_frozen_active_record_history_uses_current_operator_and_preserves_history(launch_project, archive_first):
    project = launch_project
    project.settings()["workflow"] = "unified"
    for name in ("plan.md", "handoff.md"):
        text = (HISTORY / name).read_text(encoding="utf-8")
        if name == "plan.md":
            text = text.replace("- Claimed: none", "- Claimed: A since 2026-10-27 11:00")
        if name == "handoff.md" and archive_first:
            live, history = text.split("## Archived history", 1)
            title, live = live.split("\n", 1)
            text = title + "\n\n## Archived history" + history + "\n" + live
        (project.root / name).write_text(text, encoding="utf-8")
    before = {name: (project.root / name).read_bytes() for name in ("plan.md", "handoff.md")}
    checker = Checker(project.root, now=NOW)
    checker.values = project.settings()
    checker.parse_plan(unfenced((project.root / "plan.md").read_text(encoding="utf-8")))
    checker.parse_handoff(unfenced((project.root / "handoff.md").read_text(encoding="utf-8")))
    assert set(checker.plan_items) == {"H-A-02"}
    assert checker.handoff_sections["A"].fields["Current host"] == "Shell"
    assert "Active compute" not in checker.shared
    assert not [issue for issue in checker.issues if "duplicate" in issue.check]
    assert jobs._launch_identity(project) == ("Shell", "operator")
    with pytest.raises(ValueError, match="exactly one active plan record"):
        jobs.launch(project, options("H-A-01"))
    assert "J-A-0001" in jobs.launch(project, options("H-A-02"))
    assert len(project.spawned) == 1
    assert before == {name: (project.root / name).read_bytes() for name in before}


def test_shared_state_live_compute_still_blocks_launch(launch_project):
    project = launch_project
    plan(project, "unified")
    path = project.root / "plan.md"
    path.write_text(path.read_text(encoding="utf-8") +
        "### H-B-01 — live worker\n- Claimed: B since 2026-10-27 11:00\n- Parallel: NO\n", encoding="utf-8")
    path = project.root / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Active compute: none",
        "- Active compute: CPU — B (H-B-01, since 2026-10-27 11:00)"), encoding="utf-8")
    before = reservation_snapshot(project)
    with pytest.raises(ValueError, match="handoff claim for H-B-01"):
        jobs.launch(project, options())
    assert reservation_snapshot(project) == before
    assert project.spawned == []


def test_genuine_live_duplicate_slot_is_reported_and_blocks_launch(launch_project):
    project = launch_project
    plan(project, "classic")
    path = project.root / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("## Archived history",
        "### Agent: A\n- Current host: Shell\n- Current user: second operator\n\n## Archived history"),
        encoding="utf-8")
    checker = Checker(project.root, now=NOW)
    checker.parse_handoff(unfenced(path.read_text(encoding="utf-8")))
    assert [issue.check for issue in checker.issues] == ["handoff.section.duplicate"]
    before = reservation_snapshot(project)
    with pytest.raises(ValueError, match="taken host and user"):
        jobs.launch(project, options())
    assert reservation_snapshot(project) == before
    assert project.spawned == []


def test_genuine_live_duplicate_item_is_reported_and_blocks_launch(launch_project):
    project = launch_project
    plan(project, "unified")
    path = project.root / "plan.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text + text[text.index("### H-A-01"):], encoding="utf-8")
    checker = Checker(project.root, now=NOW)
    checker.values = project.settings()
    checker.parse_plan(unfenced(path.read_text(encoding="utf-8")))
    assert [issue.check for issue in checker.issues] == ["plan.id.duplicate"]
    before = reservation_snapshot(project)
    with pytest.raises(ValueError, match="exactly one active plan record"):
        jobs.launch(project, options())
    assert reservation_snapshot(project) == before
    assert project.spawned == []
