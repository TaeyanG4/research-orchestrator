"""Workflow migration classic <-> unified (spec §4; test 4; review fixes 1, 3, 10)."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from conftest import (SCRIPTS, check, copy_fixture, found, init, item, make_project, rs, run_init, set_queue, set_slot,
                      severities, unified_project)

FILES = ("agents.md", "plan.md", "discoveries.md", "handoff.md")


def records(plan_text: str) -> dict[str, dict[str, str]]:
    return {i.item_id: {k: v for k, v in i.fields.items() if k != "Claimed"} for i in init.parse_plan_items(plan_text)}


def quiescent_v3_project(tmp_path):
    target = copy_fixture("v2", tmp_path / "proj")
    (target / ".git").mkdir()
    assert run_init(target, "--reconfigure").returncode == 0
    set_slot(target, "A", "released", "none")
    set_slot(target, "B", "released", "none")
    handoff = target / "handoff.md"
    handoff.write_text(init.set_shared_line(handoff.read_text(encoding="utf-8"), "Active compute", "none"),
                       encoding="utf-8", newline="\n")
    discoveries = target / "discoveries.md"  # a released slot gives up its review claim too
    discoveries.write_text(discoveries.read_text(encoding="utf-8").replace(
        "- Cross-check: REVIEWING Codex (B)", "- Cross-check: PENDING"), encoding="utf-8", newline="\n")
    return target


def snapshot(target) -> dict[str, bytes]:
    return {name: (target / name).read_bytes() for name in FILES}


def test_round_trip_classic_unified_classic(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    original = (target / "plan.md").read_text(encoding="utf-8")
    before = check(target, dt.datetime.now())
    assert severities(before)["ERROR"] == 0

    to_unified = run_init(target, "--reconfigure", "--workflow", "unified", "--migrate")
    assert to_unified.returncode == 0, to_unified.stderr
    plan = (target / "plan.md").read_text(encoding="utf-8")
    assert plan.count("\n## Queue\n") == 1 and "## Agent:" not in plan
    queued = init.parse_plan_items(plan)
    assert [i.item_id for i in queued] == ["H-B-03", "H-A-04", "H-B-02"]  # priority, then lower cost
    assert all(i.lines[1] == "- Claimed: none" for i in queued)
    assert records(plan) == records(original)
    for name in ("agents.md", "plan.md", "handoff.md"):
        assert (target / f"{name}.pre-migrate").is_file()
    unified = check(target, dt.datetime.now())
    assert len(unified.events) == len(before.events) + 1
    assert unified.values["workflow"] == "unified"
    assert severities(unified)["ERROR"] == 0 and severities(unified)["WARN"] == 0, [i.render() for i in unified.issues]

    back = run_init(target, "--reconfigure", "--workflow", "classic", "--migrate")
    assert back.returncode == 0, back.stderr
    final = (target / "plan.md").read_text(encoding="utf-8")
    assert records(final) == records(original)
    for planned in init.parse_plan_items(final):
        assert planned.section == f"Agent: {init.item_prefix(planned.item_id)}"
        assert not any(line.startswith("- Claimed:") for line in planned.lines)
    assert re.findall(r"^## Agent: (\S+)", final, re.M) == ["A", "B", "C"]
    classic = check(target, dt.datetime.now())
    assert severities(classic)["ERROR"] == 0 and severities(classic)["WARN"] == 0, [i.render() for i in classic.issues]


def test_preflight_refuses_with_a_taken_slot(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "proj")
    (target / ".git").mkdir()
    assert run_init(target, "--reconfigure").returncode == 0
    before = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    refused = run_init(target, "--reconfigure", "--workflow", "unified", "--migrate")
    assert refused.returncode == 1
    # The prior upgrade's backups stay intact; refusal creates or changes nothing.
    assert {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()} == before


def test_preflight_refuses_when_the_checker_reports_errors(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    plan = target / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Sources: D-B-001\n", "- Sources: D-B-999\n"),
                    encoding="utf-8", newline="\n")
    before = snapshot(target)
    refused = run_init(target, "--reconfigure", "--workflow", "unified", "--migrate")
    assert refused.returncode == 1 and "plan.sources.dangling" in refused.stderr
    assert snapshot(target) == before


def test_workflow_change_needs_migrate(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    refused = run_init(target, "--reconfigure", "--workflow", "unified")
    assert refused.returncode == 1 and "--migrate" in refused.stderr
    via_preset = run_init(target, "--reconfigure", "--preset", "solo-research", "--platforms", "Claude Code")
    assert via_preset.returncode == 1 and "--migrate" in via_preset.stderr
    assert snapshot(target) == before


def test_interrupted_migration_restores_the_backups(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    real_replace = os.replace
    calls = {"n": 0}

    def failing_replace(src, dst):
        if Path(src).name.endswith(".migrate-tmp"):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("simulated crash between renames")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated crash"):
        init.main([str(target), "--reconfigure", "--workflow", "unified", "--migrate"])
    monkeypatch.setattr(os, "replace", real_replace)
    assert calls["n"] == 2
    assert snapshot(target) == before
    assert not list(target.glob("*.migrate-tmp"))


def test_unified_to_classic_creates_missing_sections(tmp_path) -> None:
    target = unified_project(tmp_path, agents="1")
    set_queue(target, item("H-A-01"), item("H-C-01"))
    set_slot(target, "A", "released", "none")
    assert severities(check(target, dt.datetime.now()))["ERROR"] == 0
    result = run_init(target, "--reconfigure", "--workflow", "classic", "--migrate")
    assert result.returncode == 0, result.stderr
    plan = (target / "plan.md").read_text(encoding="utf-8")
    assert re.findall(r"^## Agent: (\S+)", plan, re.M) == ["A", "C"]
    sections = {i.item_id: i.section for i in init.parse_plan_items(plan)}
    assert sections == {"H-A-01": "Agent: A", "H-C-01": "Agent: C"}
    handoff = (target / "handoff.md").read_text(encoding="utf-8")
    assert "- Active agent(s): A, C\n" in handoff and "### Agent: C\n- Current host: unassigned" in handoff
    checker = check(target, dt.datetime.now())
    assert severities(checker)["ERROR"] == 0, [i.render() for i in checker.issues]


def edit_workflow_line(target, value: str) -> None:
    agents = target / "agents.md"
    text = agents.read_text(encoding="utf-8")
    agents.write_text(re.sub(r"^- Workflow: \w+$", f"- Workflow: {value}", text, count=1, flags=re.M),
                      encoding="utf-8", newline="\n")


# ---------- review fix 1: a hand-edited Workflow line ----------

def test_hand_edited_workflow_line_migrates_classic_to_unified(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    edit_workflow_line(target, "unified")
    checker = check(target, dt.datetime.now())
    assert [i.check for i in found(checker, "ERROR")] == ["settings.workflow.unmigrated"]  # plan still read as classic
    refused = run_init(target, "--reconfigure")
    assert refused.returncode == 1 and "--migrate" in refused.stderr
    migrated = run_init(target, "--reconfigure", "--migrate")
    assert migrated.returncode == 0, migrated.stderr
    plan = (target / "plan.md").read_text(encoding="utf-8")
    assert plan.count("\n## Queue\n") == 1 and "## Agent:" not in plan
    after = check(target, dt.datetime.now())
    assert severities(after)["ERROR"] == 0 and severities(after)["WARN"] == 0, [i.render() for i in after.issues]


def test_hand_edited_workflow_line_migrates_unified_to_classic(tmp_path) -> None:
    target = unified_project(tmp_path, agents="1")
    set_queue(target, item("H-A-01"))
    set_slot(target, "A", "released", "none")
    edit_workflow_line(target, "classic")
    assert [i.check for i in found(check(target, dt.datetime.now()), "ERROR")] == ["settings.workflow.unmigrated"]
    migrated = run_init(target, "--reconfigure", "--migrate")
    assert migrated.returncode == 0, migrated.stderr
    plan = (target / "plan.md").read_text(encoding="utf-8")
    assert "## Agent: A\n" in plan and "## Queue" not in plan
    assert severities(check(target, dt.datetime.now()))["ERROR"] == 0


# ---------- review fix 3: crash recovery ----------

def migrate_with_crash(target, point: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "RO_TEST_CRASH_AT": point}
    return subprocess.run([sys.executable, str(SCRIPTS / "init_research_orchestrator.py"), str(target), "--reconfigure",
                           "--workflow", "unified", "--migrate"], text=True, capture_output=True, env=env,
                          encoding="utf-8", errors="replace")


@pytest.mark.parametrize("point", ["record", "before-rename-1", "rename-1", "before-rename-2", "rename-2",
                                   "before-rename-3", "rename-3"])
def test_a_killed_migration_is_completed_by_the_next_run(tmp_path, point: str) -> None:
    target = quiescent_v3_project(tmp_path)
    original = (target / "plan.md").read_text(encoding="utf-8")
    killed = migrate_with_crash(target, point)
    assert killed.returncode == 75, killed.stderr
    record = target / rs.TRANSACTION
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["to"] == "unified" and data["phase"] == "forward"
    assert [entry["name"] for entry in data["files"]] == ["agents.md", "plan.md", "handoff.md"]
    if point != "record":
        step = int(point[-1])
        assert data["files"][step - 1]["status"] == "installing"  # intent is durable before the rename
    assert "migration.unfinished" in [i.check for i in found(check(target, dt.datetime.now()), "ERROR")]

    recovered = run_init(target, "--reconfigure")
    assert recovered.returncode == 0, recovered.stderr
    assert not record.exists() and not list(target.glob("*.migrate-tmp"))
    plan = (target / "plan.md").read_text(encoding="utf-8")
    assert plan.count("\n## Queue\n") == 1 and records(plan) == records(original)
    checker = check(target, dt.datetime.now())
    assert severities(checker)["ERROR"] == 0, [i.render() for i in checker.issues]


def test_recovery_restores_the_backups_when_it_cannot_complete(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    assert migrate_with_crash(target, "rename-1").returncode == 75

    def refuse(src, dst):
        if Path(src).name.endswith(".migrate-tmp"):
            raise OSError("file is locked")
        return real_replace(src, dst)

    real_replace = os.replace
    monkeypatch.setattr(os, "replace", refuse)
    assert init.recover_transaction(target) == "rolled back"
    monkeypatch.undo()
    assert snapshot(target) == before
    assert not (target / rs.TRANSACTION).exists() and not list(target.glob("*.migrate-tmp"))


def test_an_unreadable_record_is_kept_without_changing_files(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    (target / ".ro").mkdir(exist_ok=True)
    (target / rs.TRANSACTION).write_text('{"version": 1, "fi', encoding="utf-8")
    (target / "plan.md.migrate-tmp").write_text("partial", encoding="utf-8")
    with pytest.raises(ValueError):
        init.recover_transaction(target)
    assert snapshot(target) == before
    assert (target / rs.TRANSACTION).is_file() and (target / "plan.md.migrate-tmp").is_file()


def leave_rollback_pending(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All three forward renames finish, then both forward completion and rollback are interrupted."""
    def interrupt(point: str) -> None:
        if point == "rename-3":
            raise OSError("forward completion failed")
        if point == "rollback":
            raise OSError("rollback interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(init, "crash_point", interrupt)
        with pytest.raises(OSError, match="rollback interrupted"):
            init.main([str(target), "--reconfigure", "--workflow", "unified", "--migrate"])
    assert json.loads((target / rs.TRANSACTION).read_text(encoding="utf-8"))["phase"] == "rollback"


@pytest.mark.parametrize("point", ["rollback", "before-restore-1", "restore-1", "before-restore-2", "restore-2",
                                   "before-restore-3", "restore-3"])
def test_a_killed_rollback_is_resumed_by_the_next_run(tmp_path, monkeypatch: pytest.MonkeyPatch, point: str) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    leave_rollback_pending(target, monkeypatch)
    assert all((target / name).read_bytes() != before[name] for name in ("agents.md", "plan.md", "handoff.md"))
    env = {**os.environ, "RO_TEST_CRASH_AT": point, "PYTHONIOENCODING": "utf-8"}
    killed = subprocess.run([sys.executable, str(SCRIPTS / "init_research_orchestrator.py"), str(target)],
                            text=True, capture_output=True, env=env, encoding="utf-8", errors="replace")
    assert killed.returncode == 75, killed.stderr
    record = target / rs.TRANSACTION
    data = json.loads(record.read_text(encoding="utf-8"))
    assert data["phase"] == "rollback"
    if point != "rollback":
        assert data["files"][int(point[-1]) - 1]["status"] == "restoring"
    recovered = run_init(target)
    assert recovered.returncode == 0, recovered.stderr
    assert snapshot(target) == before
    assert not record.exists() and not list(target.glob("*.migrate-tmp"))
    assert severities(check(target, dt.datetime.now()))["ERROR"] == 0


@pytest.mark.parametrize("name", ["agents.md", "plan.md", "handoff.md"])
def test_a_missing_temp_rolls_back_instead_of_assuming_installation(tmp_path, name: str) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    assert migrate_with_crash(target, "record").returncode == 75
    (target / f"{name}.migrate-tmp").unlink()
    recovered = run_init(target)
    assert recovered.returncode == 0, recovered.stderr
    assert snapshot(target) == before and not (target / rs.TRANSACTION).exists()


def test_a_consumed_temp_does_not_prove_the_target_was_installed(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    assert migrate_with_crash(target, "rename-1").returncode == 75
    (target / "agents.md").write_bytes(before["agents.md"])
    recovered = run_init(target)
    assert recovered.returncode == 0, recovered.stderr
    assert snapshot(target) == before and not (target / rs.TRANSACTION).exists()


@pytest.mark.parametrize("name", ["agents.md", "plan.md", "handoff.md"])
def test_a_failed_restoration_can_be_retried(tmp_path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    leave_rollback_pending(target, monkeypatch)
    real_copy = init.copy_durably

    def partial_copy(source: Path, destination: Path) -> None:
        if destination.name == name:
            destination.write_bytes(b"interrupted copy")
            raise OSError("restoration failed midway")
        real_copy(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(init, "copy_durably", partial_copy)
        with pytest.raises(OSError, match="restoration failed midway"):
            init.recover_transaction(target)
    data = json.loads((target / rs.TRANSACTION).read_text(encoding="utf-8"))
    assert data["phase"] == "rollback"
    assert next(entry for entry in data["files"] if entry["name"] == name)["status"] == "restoring"
    assert init.recover_transaction(target) == "rolled back"
    assert snapshot(target) == before and not (target / rs.TRANSACTION).exists()


def test_a_legacy_journal_is_recovered_as_rollback(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    before = snapshot(target)
    assert migrate_with_crash(target, "rename-1").returncode == 75
    record = target / rs.TRANSACTION
    data = json.loads(record.read_text(encoding="utf-8"))
    data.update(version=1, files=[entry["name"] for entry in data["files"]])
    data.pop("phase")
    record.write_text(json.dumps(data), encoding="utf-8")
    assert init.recover_transaction(target) == "rolled back"
    assert snapshot(target) == before and not record.exists()


# ---------- review fix 10: dropped lines are reported ----------

def test_migration_lists_the_non_item_lines_it_drops(tmp_path) -> None:
    target = quiescent_v3_project(tmp_path)
    plan = target / "plan.md"
    text = plan.read_text(encoding="utf-8").replace(
        "## Agent: B\n", "## Agent: B\n\nRemember: rerun with seed 11 first.\n", 1)
    plan.write_text(text + "\n## Notes\n\nLoose note kept only in the backup.\n", encoding="utf-8", newline="\n")
    assert severities(check(target, dt.datetime.now()))["ERROR"] == 0
    result = run_init(target, "--reconfigure", "--workflow", "unified", "--migrate")
    assert result.returncode == 0, result.stderr
    for line in ("[DROP] plan.md: Remember: rerun with seed 11 first.", "[DROP] plan.md: ## Notes",
                 "[DROP] plan.md: Loose note kept only in the backup."):
        assert line in result.stdout
    assert "Loose note kept only in the backup." in (target / "plan.md.pre-migrate").read_text(encoding="utf-8")


@pytest.mark.parametrize("source", ["classic", "unified"])
def test_migration_reports_actual_header_and_underscore_prose_except_exact_placeholders(tmp_path, source: str) -> None:
    target = make_project(tmp_path, "proj", "--workflow", source, "--user", "operator", "--agents", "2")
    plan = target / "plan.md"
    original = plan.read_text(encoding="utf-8")
    placeholders = [line for line in original.splitlines() if line.startswith("_")]
    assert placeholders
    custom_header = ["_Keep this header reminder._", "Header note: check the remaining work."]
    custom_section = ["_Keep this section reminder._", placeholders[0] + " "]  # not byte-identical
    header, sections = original.split("\n## ", 1)
    custom_title = "# Custom planning notes"
    header = header.replace(header.splitlines()[0], custom_title, 1)
    heading, body = sections.split("\n", 1)
    changed = (header + "\n\n" + "\n".join(custom_header) + "\n\n## " + heading + "\n\n" +
               "\n".join(custom_section) + "\n" + body)
    plan.write_text(changed, encoding="utf-8", newline="\n")
    destination = "unified" if source == "classic" else "classic"
    result = run_init(target, "--reconfigure", "--workflow", destination, "--migrate")
    assert result.returncode == 0, result.stderr
    dropped = [line.removeprefix("[DROP] plan.md: ") for line in result.stdout.splitlines()
               if line.startswith("[DROP] plan.md: ")]
    assert dropped == [custom_title] + custom_header + custom_section
    assert all(placeholder not in dropped for placeholder in placeholders)
    assert (target / "plan.md.pre-migrate").read_text(encoding="utf-8") == changed
