"""`ro event`, `ro set-field`, `ro seal` and `ro external --check` (2026-11 enveda T1, T2, T3a)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import pytest

from conftest import check, item, set_queue, unified_project
import check_project
import ro_evidence as evidence
import ro_write
from ro_state import Project


EVENT = {"Action": "pilot on the sample", "Result": "pilot finished", "Discovery updates": "none — no experiment",
         "New plan items": "none — nothing follows"}


@pytest.fixture
def project(tmp_path) -> Project:
    p = Project(unified_project(tmp_path), slot="A", session="record-commands")
    p.register_slot()
    return p


def errors(root: Path) -> set:
    return {(i.check, i.record) for i in check(root).issues if i.severity == "ERROR"}


def test_event_takes_clock_time_and_slot_identity(project):
    before = errors(project.root)
    output = ro_write.event(project, "none", dict(EVENT))
    text = (project.root / "handoff.md").read_text(encoding="utf-8")
    today = dt.datetime.now().strftime("%Y-%m-%d")
    assert f"### {today} " in output and "- Host: Claude Code" in text and "- User: operator" in text
    assert text.index("— A — none") < text.index("## Archived history")
    assert errors(project.root) == before


@pytest.mark.parametrize("change,message", [
    ({"Result": None}, "event needs Result"),
    ({"Decision": "changed"}, "needs its discovery ID"),
    ({"Decision": "maybe"}, "Decision must be"),
    ({"Effort": "high"}, "unknown event fields"),
])
def test_event_refuses_incomplete_or_invalid_fields(project, change, message):
    fields = {**EVENT, **change}
    with pytest.raises(ValueError, match=message):
        ro_write.event(project, "none", fields)


def test_event_refuses_session_key_and_bad_keys(project):
    with pytest.raises(ValueError, match="updated in place"):
        ro_write.event(project, "session", dict(EVENT))
    with pytest.raises(ValueError, match="event key"):
        ro_write.event(project, "H-A-1", dict(EVENT))


def test_event_refuses_completing_an_item_still_queued(project):
    """A bare item heading means finished; the checker's own rule refuses it while the item is queued."""
    set_queue(project.root, item("H-A-01"))
    with pytest.raises(ValueError, match="event.finished.queued"):
        ro_write.event(project, "H-A-01", dict(EVENT))


def test_event_from_file_refuses_paragraphs_and_identity_fields(project, tmp_path):
    draft = tmp_path / "event.md"
    draft.write_text("- Action: x\nA free paragraph between fields\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2 is not"):
        ro_write.event(project, "none", {}, str(draft))
    draft.write_text("- Host: Somewhere\n- Action: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="comes from your slot"):
        ro_write.event(project, "none", {}, str(draft))
    with pytest.raises(ValueError, match="either --from"):
        ro_write.event(project, "none", {"Action": "x"}, str(draft))


def test_event_from_file_and_crlf_handoff(project, tmp_path):
    handoff = project.root / "handoff.md"
    handoff.write_bytes(handoff.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    draft = tmp_path / "event.md"
    draft.write_text("".join(f"- {k}: {v}\n" for k, v in EVENT.items()), encoding="utf-8")
    ro_write.event(project, "none", {}, str(draft))
    data = handoff.read_bytes()
    assert b"- Action: pilot on the sample\r\n" in data and data.count(b"\n") == data.count(b"\r\n")


def test_set_field_replaces_one_line_and_keeps_other_bytes(project):
    set_queue(project.root, item("H-A-01"), item("H-A-02"))
    plan = project.root / "plan.md"
    plan.write_bytes(plan.read_bytes().replace(b"\n", b"\r\n"))
    before = plan.read_bytes()
    output = ro_write.set_field(project, "H-A-02", "Next test", "a sharper test")
    after = plan.read_bytes()
    assert "a sharper test" in output
    assert after.count(b"- Next test: a test\r\n") == 1 and b"- Next test: a sharper test\r\n" in after
    assert len(after) - len(before) == len("a sharper test") - len("a test")


@pytest.mark.parametrize("record,field,message", [
    ("H-A-01", "Claimed", "ro claim"),
    ("H-A-01", "Nonexistent", "exactly one `- Nonexistent:`"),
    ("H-A-09", "Priority", "exactly one heading"),
    ("slot", "Current host", "session start"),
])
def test_set_field_refuses_owned_missing_or_unknown(project, record, field, message):
    set_queue(project.root, item("H-A-01"))
    with pytest.raises(ValueError, match=message):
        ro_write.set_field(project, record, field, "x")


def test_set_field_refuses_a_value_the_checker_rejects(project):
    set_queue(project.root, item("H-A-01"))
    with pytest.raises(ValueError, match="plan.score.range"):
        ro_write.set_field(project, "H-A-01", "Priority", "high")


def test_set_field_on_own_slot_section(project):
    output = ro_write.set_field(project, "slot", "Next action", "read the pilot log")
    assert "read the pilot log" in (project.root / "handoff.md").read_text(encoding="utf-8")
    assert "Next action" in output


def test_seal_records_machine_time_and_refuses_changed_bytes(project):
    prereg = project.root / "runs" / "prereg.json"
    prereg.parent.mkdir()
    prereg.write_text('{"threshold": 0.01}\n', encoding="utf-8")
    first = ro_write.seal(project, str(prereg))
    sidecar = json.loads((project.root / "runs" / "prereg.json.seal.json").read_text(encoding="utf-8"))
    assert first.startswith("sealed runs/prereg.json at ") and sidecar["sealed_at"] in first
    assert "already sealed at " + sidecar["sealed_at"] in ro_write.seal(project, str(prereg))
    assert "matches its seal" in ro_write.seal(project, str(prereg), check=True)
    prereg.write_text('{"threshold": 0.02}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="new file"):
        ro_write.seal(project, str(prereg))
    with pytest.raises(ValueError, match="changed after its seal"):
        ro_write.seal(project, str(prereg), check=True)


def test_seal_refuses_files_outside_the_project(project, tmp_path):
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="inside the project"):
        ro_write.seal(project, str(outside))


# T3a: a note after the hash passed the checker and failed only when ro external ran.
def test_prepared_candidate_note_fails_in_checker_and_external_check(tmp_path):
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    digest = prepared(project, name)
    handoff = project.root / "handoff.md"
    handoff.write_text(handoff.read_text(encoding="utf-8").replace(digest, digest + " (fold 3 build)"),
                       encoding="utf-8", newline="\n")
    args = argparse.Namespace(artifact=None, action="X-A-001", command=[], check=True)
    with pytest.raises(ValueError, match="nothing after the hash"):
        evidence.external(project, args)
    assert not evidence.PREPARED_CANDIDATE.fullmatch(f"{name}, hash {digest} (fold 3 build)")


def test_delegate_header_carries_the_marker_and_real_check_scope(project):
    """Half of the 2026-11 log came from delegated agents that never read the project's rules."""
    set_queue(project.root, item("H-A-01", stages="s1 pilot | s2 full"))
    header = ro_write.delegate(project, "H-A-01/s2")
    first = header.splitlines()[0]
    assert first == ro_write.DELEGATE_MARKER
    assert "# Delegated: H-A-01/s2" in header and "- Stages: s1 pilot | s2 full" in header
    assert "Delete nothing" in header and "never type or estimate a time" in header
    assert f"RO_SLOT={project.slot} " in header and "Verified vs inferred" in header
    with pytest.raises(ValueError, match="not an item"):
        ro_write.delegate(project, "H-A-07")


def test_delegate_marker_satisfies_the_preset_brief_requirement(project):
    import ro_checks as checks
    set_queue(project.root, item("H-A-01"))
    header = ro_write.delegate(project, "H-A-01")
    settings = {"brief_requirements": "general-purpose: ro-delegate: v1", "enforcement": "warn", "block": "none"}
    call = checks.Call("Agent", prompt=header + "\nDo the pilot.")
    assert checks.pre_checks(call, project.root, [], settings) == []


DISCOVERY = ("## D-A-001 — pilot effect\n- Date: 2026-11-01\n- Finding: +0.004 on panel v1\n"
             "- Cross-check: CHALLENGED\n- Correction: (2026-11-02 10:00) the effect is +0.0004\n"
             "- Current: D-A-002\n- Implication: keep\n")


def test_index_opens_plan_items_and_puts_corrections_first(project):
    import ro_records as records
    from conftest import append_discovery
    set_queue(project.root, item("H-A-01"))
    assert records.discovery_index(project, "H-A-01").startswith("### H-A-01")
    append_discovery(project.root, DISCOVERY)
    opened = records.discovery_index(project, "D-A-001").splitlines()
    assert opened[1].startswith("- Correction:") and opened[2] == "- Current: D-A-002"
    assert "- Current: D-A-002" in records.discovery_index(project)


def test_brief_names_finished_jobs_open_reviews_and_awaited_results(project):
    import ro_records as records
    from conftest import append_discovery
    append_discovery(project.root, DISCOVERY)
    project.write_json("jobs.json", [{"id": "J-A-0001", "item": "H-A-01", "slot": "A", "status": "finished",
                                      "exit_code": 0, "ended": 1.0, "tree_empty": True}])
    ro_write.set_field(project, "slot", "Next action", "wait for J-A-0001")
    handoff = project.root / "handoff.md"
    entry = ("### X-A-001 — release\n- Kind: release\n- Candidate: a.txt, hash " + "a" * 64 + "\n"
             "- Destination: endpoint\n- Expected: ok (written 2026-11-01 10:00)\n- Result: pending\n"
             "- Final: pending\n- Status: done\n\n")
    text = handoff.read_text(encoding="utf-8")
    text = (text.replace("## External actions\n\n", "## External actions\n\n" + entry, 1) if "## External actions\n" in text
            else text + "\n## External actions\n\n" + entry)
    handoff.write_text(text, encoding="utf-8", newline="\n")
    text = records.brief(project)
    assert "State notes cite finished jobs: J-A-0001" in text
    assert "Open reviews CHALLENGED: 1; IDs D-A-001" in text
    assert "Awaiting final results: 1; IDs X-A-001" in text
    assert "skill 8.0.0" in text.splitlines()[0]


def test_oversized_next_test_warns(project):
    set_queue(project.root, item("H-A-01", extra=[("Notes", "x")]).replace("- Next test: a test",
                                                                          "- Next test: " + "old step; " * 220))
    assert any(i.check == "plan.next.size" for i in check(project.root).issues)


CLOSE_DRAFT = """## D-A-001 — pilot effect
- Source: A
- Host: Claude Code
- User: operator
- Date: {date}
- Cross-check: PENDING
- Finding: the pilot moved the panel score by +0.004
- Evidence: runs/pilot/result.json
- Implication: run the full sample
- Reviews:

## Event
- Action: finished the pilot
- Result: effect holds on the sample; see D-A-001
- Discovery updates: D-A-001
- New plan items: H-A-02 — full run follows

## Follow-ups
### H-A-02 — full run
- Claimed: none
"""


def close_project(project):
    set_queue(project.root, item("H-A-01", claimed=f"A since 2026-11-01 10:00"))
    return project


def draft_file(tmp_path, text):
    path = tmp_path / "close.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_close_item_writes_everything_or_nothing(project, tmp_path):
    """2026-11-12 02:42, 2026-11-14 08:33, 2026-11-19 03:49: closing scripts stopped half way."""
    from conftest import PLAN_VALUES
    close_project(project)
    follow = "".join(f"- {name}: {value}\n" for name, value in PLAN_VALUES)
    text = CLOSE_DRAFT.format(date=dt.datetime.now().strftime("%Y-%m-%d")) + follow
    before = {name: (project.root / name).read_bytes() for name in ("plan.md", "discoveries.md", "handoff.md")}
    assert ro_write.close_item(project, "H-A-01", draft_file(tmp_path, text), dry_run=True).startswith("dry run")
    assert all((project.root / name).read_bytes() == data for name, data in before.items())
    output = ro_write.close_item(project, "H-A-01", draft_file(tmp_path, text))
    assert output.startswith("closed H-A-01")
    plan = (project.root / "plan.md").read_text(encoding="utf-8")
    assert "### H-A-01 — test item" not in plan and "### H-A-02 — full run" in plan
    assert "## D-A-001 — pilot effect" in (project.root / "discoveries.md").read_text(encoding="utf-8")
    assert "— A — H-A-01\n- Host: Claude Code" in (project.root / "handoff.md").read_text(encoding="utf-8")
    assert not (project.root / ".ro" / "migration.json").exists()
    assert not list(project.root.glob("*.pre-migrate"))
    assert not {i.check for i in check(project.root).issues if i.severity == "ERROR"}


def test_close_item_refuses_before_writing(project, tmp_path):
    close_project(project)
    before = {name: (project.root / name).read_bytes() for name in ("plan.md", "discoveries.md", "handoff.md")}
    unlisted = CLOSE_DRAFT.format(date="2026-11-01").replace("- Discovery updates: D-A-001", "- Discovery updates: none — x")
    with pytest.raises(ValueError, match="every drafted discovery"):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, unlisted))
    stray = "A paragraph\n" + CLOSE_DRAFT.format(date="2026-11-01")
    with pytest.raises(ValueError, match="before any section"):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, stray))
    project.write_json("jobs.json", [{"id": "J-A-0001", "item": "H-A-01/s1", "slot": "A", "status": "finished",
                                      "exit_code": 0, "ended": 1.0, "tree_empty": True}])
    with pytest.raises(ValueError, match="running or unreported jobs: J-A-0001"):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, CLOSE_DRAFT.format(date="2026-11-01")))
    assert all((project.root / name).read_bytes() == data for name, data in before.items())


def test_close_item_recovers_an_interrupted_transaction(project, tmp_path, monkeypatch):
    import init_research_orchestrator as init
    from conftest import PLAN_VALUES
    close_project(project)
    follow = "".join(f"- {name}: {value}\n" for name, value in PLAN_VALUES)
    text = CLOSE_DRAFT.format(date=dt.datetime.now().strftime("%Y-%m-%d")) + follow
    before = {name: (project.root / name).read_bytes() for name in ("plan.md", "discoveries.md", "handoff.md")}
    real_apply = init.apply_transaction
    calls = {"n": 0}

    def crash(target, data):
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyboardInterrupt  # killed in the middle of the forward phase
        return real_apply(target, data)

    monkeypatch.setattr(init, "apply_transaction", crash)
    with pytest.raises(KeyboardInterrupt):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, text))
    monkeypatch.setattr(init, "apply_transaction", real_apply)
    assert all((project.root / name).read_bytes() == data for name, data in before.items())


def full_draft():
    from conftest import PLAN_VALUES
    follow = "".join(f"- {name}: {value}\n" for name, value in PLAN_VALUES)
    return CLOSE_DRAFT.format(date=dt.datetime.now().strftime("%Y-%m-%d")) + follow


def crash_close_item(project, draft, point="rename-1"):
    """Run close-item in a child process that dies at a transaction step, as a killed session would."""
    import os
    import subprocess
    import sys
    from conftest import SCRIPTS
    env = {**os.environ, "RO_TEST_CRASH_AT": point}
    result = subprocess.run([sys.executable, str(SCRIPTS / "ro.py"), "--project", str(project.root), "--slot", "A",
                             "--session", "record-commands", "close-item", "H-A-01", "--from", draft],
                            capture_output=True, text=True, encoding="utf-8", env=env)
    assert result.returncode == 75, result.stderr
    assert (project.root / ".ro" / "migration.json").is_file()


def test_killed_close_item_blocks_writes_until_recovered(project, tmp_path):
    """Fable review B2: a write between the kill and the recovery was overwritten by the recovery."""
    close_project(project)
    crash_close_item(project, draft_file(tmp_path, full_draft()))
    with pytest.raises(ValueError, match="close-item --recover"):
        ro_write.event(project, "none", dict(EVENT))
    with pytest.raises(ValueError, match="close-item --recover"):
        ro_write.set_field(project, "slot", "Next action", "x")
    assert ro_write.close_item(project, "", recover=True) == "close-item recovery: completed"
    assert "### H-A-01 — test item" not in (project.root / "plan.md").read_text(encoding="utf-8")
    assert "— A — H-A-01\n" in (project.root / "handoff.md").read_text(encoding="utf-8")
    assert not (project.root / ".ro" / "migration.json").exists()
    assert not {i.check for i in check(project.root).issues if i.severity == "ERROR"}
    ro_write.event(project, "none", dict(EVENT))  # writes work again


def test_recovery_never_overwrites_a_write_made_after_the_kill(project, tmp_path):
    close_project(project)
    crash_close_item(project, draft_file(tmp_path, full_draft()))
    handoff = project.root / "handoff.md"
    handoff.write_text(handoff.read_text(encoding="utf-8") + "\nhand edit after the crash\n", encoding="utf-8",
                       newline="\n")
    for _attempt in range(2):  # Fable round 2 N1: a second recovery used to roll back over the edit.
        with pytest.raises(OSError, match="changed after the transaction began"):
            ro_write.close_item(project, "", recover=True)
        assert "hand edit after the crash" in handoff.read_text(encoding="utf-8")
        assert (project.root / ".ro" / "migration.json").is_file()
    # The documented way out: keep the edit aside, restore the backup, recover (the refused forward
    # recovery switched the journal to rollback), then close the item again and reapply the edit.
    edited = handoff.read_text(encoding="utf-8")
    handoff.write_bytes((project.root / "handoff.md.close-backup").read_bytes())
    assert ro_write.close_item(project, "", recover=True) == "close-item recovery: rolled back"
    assert "### H-A-01 — test item" in (project.root / "plan.md").read_text(encoding="utf-8")
    assert not list(project.root.glob("*.close-backup")) and "hand edit" in edited
    assert ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft())).startswith("closed H-A-01")


def test_close_item_keeps_migration_backups_and_crlf(project, tmp_path):
    """Fable review M1 and m8: close-item reused and deleted *.pre-migrate; CRLF records had no test."""
    close_project(project)
    for name in ("plan.md", "discoveries.md", "handoff.md"):
        path = project.root / name
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    (project.root / "plan.md.pre-migrate").write_text("evidence of an earlier migration\n", encoding="utf-8")
    ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft()))
    assert (project.root / "plan.md.pre-migrate").read_text(encoding="utf-8") == "evidence of an earlier migration\n"
    assert not list(project.root.glob("*.close-backup")) and not list(project.root.glob("*.close-tmp"))
    for name in ("plan.md", "discoveries.md", "handoff.md"):
        data = (project.root / name).read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), name


def test_close_item_refusal_names_the_next_step(project, tmp_path):
    close_project(project)
    other = Project(project.root, slot="B", session="other-session")
    ro_write.set_field(other, "slot", "Next action", "review H-A-01 output")
    with pytest.raises(ValueError, match="(?s)handoff.slot.dangling.*next: a slot's Current thread"):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft()))


def test_set_field_on_discoveries_and_ledger_entries(project):
    """Fable review m8: D- and X- records; ledger Final stays editable, attempted history does not."""
    from conftest import append_discovery
    append_discovery(project.root, CLOSE_DRAFT.split("## Event")[0].format(date="2026-11-01"))
    ro_write.set_field(project, "D-A-001", "Implication", "run the full sample twice")
    assert "- Implication: run the full sample twice" in (project.root / "discoveries.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="verification workflow"):
        ro_write.set_field(project, "D-A-001", "Cross-check", "CLOSED")
    handoff = project.root / "handoff.md"
    entry = ("### X-A-001 — release\n- Kind: release\n- Candidate: a.txt, hash " + "a" * 64 + "\n"
             "- Destination: endpoint\n- Expected: ok (written 2026-11-01 10:00)\n"
             "- Result: accepted (observed 2026-11-01 11:00)\n- Final: pending\n- Status: done\n\n")
    text = handoff.read_text(encoding="utf-8")
    text = (text.replace("## External actions\n\n", "## External actions\n\n" + entry, 1) if "## External actions\n" in text
            else text + "\n## External actions\n\n" + entry)
    handoff.write_text(text, encoding="utf-8", newline="\n")
    ro_write.set_field(project, "X-A-001", "Final", "0.512 (observed 2026-11-02 09:00)")
    assert "- Final: 0.512 (observed 2026-11-02 09:00)" in handoff.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="history"):
        ro_write.set_field(project, "X-A-001", "Candidate", "b.txt, hash " + "b" * 64)
    with pytest.raises(ValueError, match="ro external"):
        ro_write.set_field(project, "X-A-001", "Status", "complete")


def test_require_seal_resolves_against_the_run_dir_and_names_the_path(project):
    """Fable round 2 N3 / round 3 m-b: the message names the resolved path once."""
    missing = str(project.root / "runs" / "missing.json")
    with pytest.raises(ValueError) as refused:
        ro_write.seal(project, missing, check=True)
    assert str(refused.value).count("missing.json") == 1 and "inside the project" in str(refused.value)


def test_delegate_check_scope_matches_the_hooks_table():
    """Fable round 3 m-e: the header's check scopes and references/hooks.md must not drift apart."""
    import ro_settings
    hooks = (Path(ro_settings.SKILL_ROOT) / "references" / "hooks.md").read_text(encoding="utf-8")
    rows = [line for line in hooks.splitlines() if line.startswith("| `")]
    for check_id in [*ro_write.CHECK_SCOPE, *ro_settings.CHECK_IDS]:
        if check_id in ("jobs.unmonitored", "publish.scan", "external.gate"):
            continue  # Covered by their own references (operations-safety, publication, external actions).
        assert any(f"`{check_id}`" in row for row in rows), check_id


def test_external_refuses_before_journaling_while_a_transaction_is_pending(tmp_path):
    """Fable round 2 N2: the attempt journal was written, then the ledger update refused."""
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    (project.state / "migration.json").write_text("{}", encoding="utf-8")
    args = argparse.Namespace(artifact=None, action="X-A-001", command=["true"], check=False)
    with pytest.raises(ValueError, match="close-item --recover"):
        evidence.external(project, args)
    assert not (project.state / "external-attempts").exists()


def test_reconfigure_mentions_the_new_brief_default(tmp_path):
    from conftest import make_project, run_init
    target = make_project(tmp_path, "old", "--preset", "solo-research", "--platforms", "Claude Code",
                          "--user", "operator", "--brief-requirements", "none")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    assert "Brief requirements is none" in result.stderr


def test_delegate_outside_the_plan(project):
    header = ro_write.delegate(project, "none")
    assert header.splitlines()[0] == ro_write.DELEGATE_MARKER
    assert "_task/" in header and "## Item" not in header and "ask the delegating session" in header


def test_skill_version_matches_the_manifest_and_changelog():
    import ro_settings
    root = Path(__file__).resolve().parents[1]
    assert json.loads((root / "plugin.json").read_text(encoding="utf-8"))["version"] == ro_settings.SKILL_VERSION
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8").split("\n## ", 2)[1].startswith(ro_settings.SKILL_VERSION)


def test_external_check_reports_ready_without_running(tmp_path):
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    args = argparse.Namespace(artifact=None, action="X-A-001", command=[], check=True)
    assert "ready" in evidence.external(project, args)
    assert not (project.state / "external-attempts").exists()
