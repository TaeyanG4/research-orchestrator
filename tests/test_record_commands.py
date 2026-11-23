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
    assert "Verified vs inferred" in header and "RO_SLOT=" not in header
    # astra review 2026-11-22: commands name the project and slot, and the run folder is absolute.
    assert "--project " in header and "--slot A" in header and str(project.root / "runs") in header and "_h-a-01_s2" in header
    with pytest.raises(ValueError, match="not an item"):
        ro_write.delegate(project, "H-A-07")
    with pytest.raises(ValueError, match="not declared"):
        ro_write.delegate(project, "H-A-01/s9")


def test_delegate_header_uses_the_configured_shell(project):
    """astra review 2026-11-22: a PowerShell project got `RO_SLOT=A …` and `date '+…'`, which are Bash."""
    import re
    agents = project.root / "agents.md"
    agents.write_text(re.sub(r"(?m)^- Environment: .*$", "- Environment: windows/powershell",
                             agents.read_text(encoding="utf-8")), encoding="utf-8")
    set_queue(project.root, item("H-A-01"))
    header = ro_write.delegate(project, "H-A-01")
    assert "Get-Date -Format 'yyyy-MM-dd HH:mm'" in header and "date '+" not in header
    assert "`& '" in header and "'--project'" in header and "'--slot' 'A'" in header


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
    import ro_settings
    assert f"skill {ro_settings.SKILL_VERSION}" in text.splitlines()[0]


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
    assert set(ro_write.CHECK_SCOPE) == set(ro_settings.CHECK_IDS)  # every blockable check has its scope line
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
    assert "_task (create it)" in header and "## Item" not in header and "ask the delegating session" in header


def test_skill_version_matches_the_manifest_and_changelog():
    import ro_settings
    root = Path(__file__).resolve().parents[1]
    assert json.loads((root / "plugin.json").read_text(encoding="utf-8"))["version"] == ro_settings.SKILL_VERSION
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8").split("\n## ", 2)[1].startswith(ro_settings.SKILL_VERSION)


# ---- astra review 2026-11-22 ----

def test_dry_run_and_new_close_never_recover_a_pending_transaction(project, tmp_path):
    """A dry run used to complete the interrupted transaction, delete its journal, then report an error."""
    close_project(project)
    crash_close_item(project, draft_file(tmp_path, full_draft()))
    names = ("plan.md", "discoveries.md", "handoff.md")
    before = {name: (project.root / name).read_bytes() for name in names}
    for dry_run in (True, False):
        with pytest.raises(ValueError, match="close-item --recover"):
            ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft()), dry_run=dry_run)
    assert (project.root / ".ro" / "migration.json").is_file()
    assert all((project.root / name).read_bytes() == data for name, data in before.items())
    assert ro_write.close_item(project, "", recover=True) == "close-item recovery: completed"


@pytest.mark.parametrize("arrival", ["journal", "job"])
def test_close_item_rechecks_under_its_final_lock(project, tmp_path, monkeypatch, arrival):
    """astra review round 2: a journal or job that appeared after validation was overwritten or ignored."""
    close_project(project)
    names = ("plan.md", "discoveries.md", "handoff.md")
    before = {name: (project.root / name).read_bytes() for name in names}
    real_compare = ro_write._compare

    def compare_then_another_call_arrives(target, proposed):
        notes = real_compare(target, proposed)
        if arrival == "journal":
            project.write_json("migration.json", {"from": "close-item", "to": "H-A-02"})
        else:
            project.write_json("jobs.json", [{"id": "J-A-0001", "item": "H-A-01/s1", "slot": "A",
                                              "status": "starting"}])
        return notes

    monkeypatch.setattr(ro_write, "_compare", compare_then_another_call_arrives)
    with pytest.raises(ValueError, match="close-item --recover" if arrival == "journal" else "J-A-0001"):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft()))
    assert all((project.root / name).read_bytes() == data for name, data in before.items())
    if arrival == "journal":
        assert project.read_json("migration.json", {}) == {"from": "close-item", "to": "H-A-02"}


def test_close_item_refuses_dry_run_with_recover(project):
    with pytest.raises(ValueError, match="give one of them"):
        ro_write.close_item(project, "", dry_run=True, recover=True)


def test_delegate_header_for_important_stages_and_after_call_checks(project):
    """astra review round 2: the launch example lacked the receipt an important stage needs, and
    checks that run after a call were listed as blocking."""
    import re
    set_queue(project.root, item("H-A-01", stages="s1 pilot | s2 full") + "- Important stages: s2\n")
    agents = project.root / "agents.md"
    text = re.sub(r"(?m)^- Enforcement: .*$", "- Enforcement: block", agents.read_text(encoding="utf-8"))
    agents.write_text(re.sub(r"(?m)^- Block: .*$", "- Block: shell.background, records.direct", text), encoding="utf-8")
    assert "--require-receipt" in ro_write.delegate(project, "H-A-01/s2")
    assert "--require-receipt" not in ro_write.delegate(project, "H-A-01/s1")
    whole = ro_write.delegate(project, "H-A-01")
    assert "as a named stage" in whole and " launch --item H-A-01 " not in whole
    assert re.search(r"Hooks block .*`shell.background`", whole) and "`records.direct`" not in whole.split("Hooks block")[1].split("\n")[0]
    assert re.search(r"Hooks flag after the call.*`records.direct`", whole)


@pytest.mark.parametrize("field", ["Source", "Host"])
def test_set_field_keeps_discovery_attribution(project, field):
    from conftest import append_discovery
    append_discovery(project.root, CLOSE_DRAFT.split("## Event")[0].format(date="2026-11-01"))
    with pytest.raises(ValueError, match="original discovery"):
        ro_write.set_field(project, "D-A-001", field, "someone else")


def test_index_moves_only_real_correction_lines(project):
    """A fenced example of `- Current:` was moved above the body as if it were the discovery's pointer."""
    import ro_records as records
    from conftest import append_discovery
    append_discovery(project.root, "## D-A-001 — pilot effect\n- Date: 2026-11-01\n- Finding: +0.004\n"
                                   "```\n- Current: D-A-099\n```\n- Implication: keep\n")
    opened = records.discovery_index(project, "D-A-001").splitlines()
    fence = opened.index("```")
    assert opened[fence + 1] == "- Current: D-A-099" and opened[1] != "- Current: D-A-099"


@pytest.mark.parametrize("value,valid", [
    ("ok (written 2026-11-01 10:00)", True),
    ("ok (written 2026-11-01 10:00:30)", False),  # the checker's minute format (astra round 2)
    ("ok (written 2026-11-01 10:00) trailing note", False),
    ("ok (written 2026-11-01 10:00) (written 2099-01-01 00:00)", False),
    ("(written 2026-11-01 10:00)", False),
])
def test_expected_needs_one_final_written_stamp(value, valid):
    """The executor read the first stamp, so a second (future) stamp or trailing text passed it."""
    assert (evidence.expected_written(value) is not None) is valid


def test_external_check_refuses_a_second_expected_stamp(tmp_path):
    import re
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    # A valid receipt, so the old code reaches the stamp rule and reports `ready` (astra round 2).
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    handoff = project.root / "handoff.md"
    handoff.write_text(re.sub(r"(- Expected: .*\(written [^)]*\))", r"\1 (written 2099-01-01 00:00)",
                              handoff.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    args = argparse.Namespace(artifact=None, action="X-A-001", command=[], check=True)
    with pytest.raises(ValueError, match="end with one"):
        evidence.external(project, args)


@pytest.mark.parametrize("check_only", [True, False])
def test_unusable_success_regex_is_refused_before_anything_runs(tmp_path, check_only):
    """A pattern compiled after the command ran left the action in-flight with no result file."""
    import sys
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    marker = tmp_path / "ran.txt"
    command = [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('x')"]
    args = argparse.Namespace(artifact=None, action="X-A-001", command=command, check=check_only,
                              success_regex="(accepted)")
    with pytest.raises(ValueError, match="success-regex"):
        evidence.external(project, args)
    assert not marker.exists() and not (project.state / "external-attempts").exists()


def test_external_check_reports_ready_without_running(tmp_path):
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    args = argparse.Namespace(artifact=None, action="X-A-001", command=[], check=True)
    assert "ready" in evidence.external(project, args)
    assert not (project.state / "external-attempts").exists()


# ---- Fable re-review 2026-11-23 ----

def add_ledger_entry(root: Path, entry: str) -> None:
    handoff = root / "handoff.md"
    text = handoff.read_text(encoding="utf-8")
    text = (text.replace("## External actions\n\n", "## External actions\n\n" + entry, 1) if "## External actions\n" in text
            else text + "\n## External actions\n\n" + entry)
    handoff.write_text(text, encoding="utf-8", newline="\n")


def test_close_item_sets_a_new_best_and_points_to_shared_state(tmp_path):
    """M1: a discovery that sets a new best was refused (handoff.best.stale) with no way but a hand edit."""
    from conftest import make_project, set_slot
    root = make_project(tmp_path, "comp", "--preset", "competition-solo", "--platforms", "Claude Code",
                        "--user", "operator", "--competition", "hub/project", "--phase-clock", "off",
                        "--external-actions", "none")
    set_slot(root, "A", "Claude Code")
    project = Project(root, slot="A", session="record-commands")
    project.register_slot()
    close_project(project)
    draft = full_draft().replace("- Implication: run the full sample", "- Implication: New current best: 0.512")
    output = ro_write.close_item(project, "H-A-01", draft_file(tmp_path, draft))
    assert output.startswith("closed H-A-01") and "handoff.best.stale" in output and "set-field shared" in output
    ro_write.set_field(project, "shared", "Current best", "0.512 (D-A-001)")
    assert "handoff.best.stale" not in {i.check for i in check(root).issues}


def test_now_and_today_placeholders_take_the_clock(project, tmp_path):
    """M2: drafts and ledger stamps carried typed times; commands now fill {now} and {today}."""
    now = dt.datetime.now()
    add_ledger_entry(project.root, "### X-A-001 — release\n- Kind: release\n- Candidate: a.txt, hash " + "a" * 64 +
                     "\n- Destination: endpoint\n- Expected: ok (written 2026-11-01 10:00)\n- Result: pending\n"
                     "- Final: pending\n- Status: prepared\n\n")
    ro_write.set_field(project, "X-A-001", "Expected", "ok (written {now})")
    text = (project.root / "handoff.md").read_text(encoding="utf-8")
    assert "{now}" not in text and f"- Expected: ok (written {now:%Y-%m-%d} " in text
    close_project(project)
    ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft().replace(
        f"- Date: {now:%Y-%m-%d}", "- Date: {today}")))
    assert f"- Date: {now:%Y-%m-%d}\n" in (project.root / "discoveries.md").read_text(encoding="utf-8")


def test_close_item_refuses_a_future_discovery_date(project, tmp_path):
    close_project(project)
    future = (dt.datetime.now() + dt.timedelta(days=7)).strftime("%Y-%m-%d")
    draft = full_draft().replace(f"- Date: {dt.datetime.now():%Y-%m-%d}", f"- Date: {future}")
    with pytest.raises(ValueError, match="in the future; write `- Date: \\{today\\}`"):
        ro_write.close_item(project, "H-A-01", draft_file(tmp_path, draft), dry_run=True)


def test_close_item_draft_keeps_fenced_headings(project, tmp_path):
    """m4: a `## ` line inside a code block of a drafted discovery was read as a section."""
    close_project(project)
    draft = full_draft().replace("- Reviews:\n", "- Reviews:\n\n```markdown\n## not a section\n```\n")
    assert ro_write.close_item(project, "H-A-01", draft_file(tmp_path, draft), dry_run=True).startswith("dry run")


def test_state_warnings_come_back_as_notes(project):
    """m1: a long Next test is a state warning; the command reports it, as a hand edit would."""
    set_queue(project.root, item("H-A-01"))
    output = ro_write.set_field(project, "H-A-01", "Next test", "x" * 2200)
    assert "plan.next.size" in output and "x" * 2200 in (project.root / "plan.md").read_text(encoding="utf-8")


def test_brief_names_an_interrupted_transaction(project, tmp_path):
    """m6: a restart saw only an ERROR count while records and launches were refused."""
    import ro_records as records
    close_project(project)
    crash_close_item(project, draft_file(tmp_path, full_draft()))
    assert "Interrupted record transaction: run `ro close-item --recover`" in records.brief(project)


@pytest.mark.parametrize("command,expected", [("rm -- -r", False), ("rm 'literal*name'", False),
                                              ("rm *.tmp", True), ("rm -rf runs/old", True)])
def test_fs_delete_reads_operands_and_quotes(command, expected):
    """m2: after `--` words are paths, and a quoted `*` is a literal name."""
    import ro_checks as checks
    call = checks.Call("shell", "bash", command)
    settings = {"enforcement": "warn", "block": "none", "environment": "linux/bash", "external_actions": "none"}
    assert any(f.check == "fs.delete" for f in checks.pre_checks(call, Path.cwd(), [], settings)) is expected


# M3: behaviour the release claims, which mutation showed no test pinned.

@pytest.mark.parametrize("digest,status,flagged", [("a" * 64, "prepared", False), ("abc001", "prepared", True),
                                                    ("abc001", "complete", False)])
def test_checker_applies_the_prepared_candidate_rule(tmp_path, digest, status, flagged):
    """Fable re-review N3: only the prepared rule (64 hex) refuses a short hash; the general rule allows it."""
    from guard_helpers import action, project as guard_project, section
    target = guard_project(tmp_path, "E1")
    result = "pending" if status == "prepared" else "quality=0.81 (observed 2026-10-24 09:00)"
    entry = action(artifact_hash=digest, result=result).replace("- Status: complete", f"- Status: {status}")
    section(target, "External actions", entry)
    fields = {i.field for i in check(target).issues if i.check == "external.field.invalid"}
    assert ("Candidate" in fields) is flagged


@pytest.mark.parametrize("field,value", [("Candidate", "a.txt, hash " + "a" * 64 + " (fold 3 build)"),
                                         ("Kind", "banana"),
                                         ("Expected", "ok (written 2026-11-01 10:00) (written 2099-01-01 00:00)")])
def test_set_field_refuses_malformed_ledger_fields(tmp_path, field, value):
    """Fable N1 / astra round 6: narrowing the refusal let malformed ledger fields through as notes."""
    from guard_helpers import action, project as guard_project, section
    target = guard_project(tmp_path, "E1")
    section(target, "External actions", action(artifact_hash="a" * 64, result="pending")
            .replace("- Status: complete", "- Status: prepared"))
    project = Project(target, slot="A", session="record-commands")
    project.register_slot()
    with pytest.raises(ValueError, match="refused"):
        ro_write.set_field(project, "X-A-001", field, value)


def test_set_field_refuses_any_new_error(project):
    """Fable N2 / astra round 6: an ERROR outside the record prefixes was written with a note."""
    with pytest.raises(ValueError, match="refused; the checker would report:\n  ERROR agent"):
        ro_write.set_field(project, "shared", "Active agent(s)", "A, B, not a slot")


def test_events_go_before_the_real_archived_history(project, tmp_path):
    """astra round 6: a fenced example of `## Archived history` received the event, which the checker never saw."""
    handoff = project.root / "handoff.md"
    text = handoff.read_text(encoding="utf-8")
    example = "\nExample layout:\n\n```markdown\n## Archived history\n```\n"
    marker = text.index("## Archived history") if "## Archived history" in text else len(text)
    handoff.write_text(text[:marker] + example + "\n" + text[marker:], encoding="utf-8", newline="\n")
    ro_write.event(project, "none", dict(EVENT))
    written = handoff.read_text(encoding="utf-8")
    action = written.index("- Action: pilot on the sample")
    example_closed = written.index("```\n", written.index("Example layout"))  # the example's closing fence
    assert example_closed < action < written.rindex("## Archived history")


def test_placeholders_inside_fences_stay(project, tmp_path):
    """Fable N5: an example that prints `{today}` keeps its text."""
    close_project(project)
    draft = full_draft().replace("- Reviews:\n", "- Reviews:\n\n```python\nprint(f'{today}')\n```\n")
    ro_write.close_item(project, "H-A-01", draft_file(tmp_path, draft))
    assert "print(f'{today}')" in (project.root / "discoveries.md").read_text(encoding="utf-8")


def test_fenced_follow_up_headings_are_not_items(project, tmp_path):
    close_project(project)
    draft = full_draft() + "\n```markdown\n### H-A-09 — example only\n```\n"
    assert ro_write.close_item(project, "H-A-01", draft_file(tmp_path, draft), dry_run=True).startswith("dry run")


def test_success_regex_turns_an_exit_zero_refusal_into_unknown(tmp_path):
    import sys
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    args = argparse.Namespace(artifact=None, action="X-A-001", check=False, success_regex="accepted",
                              command=[sys.executable, "-c", "print('rejected: quota')"])
    with pytest.raises(ValueError, match="outcome unknown"):
        evidence.external(project, args)
    assert project.read_json("external-attempts/X-A-001.json", {})["status"] == "unknown"


def test_success_regex_reads_the_whole_stream_and_refuses_an_empty_pattern(tmp_path):
    """astra round 6: the bounded record drops the middle of long output, where acceptance may be printed."""
    import sys
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    noisy = "import sys; w=sys.stdout.write; w('x' * 300000 + '\\n'); w('accepted id=7\\n'); w('y' * 300000 + '\\n')"
    args = argparse.Namespace(artifact=None, action="X-A-001", check=False, success_regex="accepted",
                              command=[sys.executable, "-c", noisy])
    assert "done" in evidence.external(project, args)
    with pytest.raises(ValueError, match="success-regex"):
        evidence.external(project, argparse.Namespace(artifact=None, action="X-A-001", check=True, success_regex=""))


@pytest.mark.parametrize("pattern,parts,found", [
    ("accepted$", ["x" * 65528 + "accepted", "NO\n"], False),  # astra round 7: a read's end is not the stream's
    ("accepted$", ["x" * 65528 + "accepted"], True),
    ("accepted$", ["x" * 65527 + "accepted\n", "more"], False),  # $ also matches before a final newline
    ("^accepted", ["x" * 10, "accepted"], False),
    ("^accepted", ["acc", "epted"], True),
    ("accepted", ["x" * 65533 + "acc", "epted ok"], True),  # Fable P1: the carried tail joins two reads
    ("^accepted", ["x" * 1000, "accepted" + "y" * 506, "z"], False),  # Fable Q2: later reads search from 1
])
def test_stream_match_treats_reads_as_one_text(pattern, parts, found):
    import ro_settings
    matcher = evidence._StreamMatch(ro_settings.safe_regex(pattern))
    for index, part in enumerate(parts):
        matcher.feed(part, final=index == len(parts) - 1)
    assert matcher.found is found


def test_anchored_success_regex_is_not_fooled_by_a_read_boundary(tmp_path):
    import sys
    from test_ro_evidence import EvidenceProject, artifact, prepared
    project = EvidenceProject(tmp_path)
    name = artifact(project)
    prepared(project, name)
    evidence.receipt_add(project, name, "reviewer-session", "PASS", "X-A-001", "release endpoint")
    code = "import sys; sys.stdout.write('x' * (65536 - 8) + 'acceptedNO')"
    args = argparse.Namespace(artifact=None, action="X-A-001", check=False, success_regex="accepted$",
                              command=[sys.executable, "-c", code])
    with pytest.raises(ValueError, match="outcome unknown"):
        evidence.external(project, args)


def test_an_invalid_final_stamp_is_not_replaced_by_an_earlier_one():
    """astra round 7: month 13 in the last observation fell back to an earlier valid time."""
    assert evidence._last_stamp("a (observed 2026-11-01 10:00); b (observed 2026-13-01 10:00)", "observed") is None
    previous = {"Expected": "ok (written 2026-11-01 09:00)",
                "Result": "a (observed 2026-11-01 10:00); b (observed 2026-13-01 10:00)",
                "Reconciled": "not-accepted (observed 2026-11-01 11:00); service shows no run"}
    with pytest.raises(ValueError, match="Retry of requires"):
        evidence._retry_reconciled(previous, dt.datetime(2026, 11, 1, 12, 0))


def test_set_field_add_appends_a_missing_field_with_the_clock(project):
    """Fable re-review P3: a Correction line was the last hand edit with a typed time."""
    from conftest import append_discovery
    append_discovery(project.root, CLOSE_DRAFT.split("## Event")[0].format(date="2026-11-01"))
    with pytest.raises(ValueError, match="add a missing one with --add"):
        ro_write.set_field(project, "D-A-001", "Correction", "({now}) the effect is +0.0004")
    ro_write.set_field(project, "D-A-001", "Correction", "({now}) the effect is +0.0004", add=True)
    text = (project.root / "discoveries.md").read_text(encoding="utf-8")
    assert f"- Correction: ({dt.datetime.now():%Y-%m-%d} " in text and "{now}" not in text
    assert text.index("- Correction:") > text.index("- Reviews:")  # after the record's last field
    with pytest.raises(ValueError, match="already has"):
        ro_write.set_field(project, "D-A-001", "Correction", "again", add=True)
    with pytest.raises(ValueError, match="original discovery"):
        ro_write.set_field(project, "D-A-001", "Source", "B", add=True)


def test_set_field_add_keeps_review_lines_with_their_field(project):
    """Fable Q1 / astra round 8: a new field went between `- Reviews:` and its indented review lines."""
    from conftest import append_discovery
    append_discovery(project.root, CLOSE_DRAFT.split("## Event")[0].format(date="2026-11-01")
                     .replace("- Reviews:\n", "- Reviews:\n  - Claude Code (B): CLOSED — reran the pilot\n"))
    output = ro_write.set_field(project, "D-A-001", "Correction", "({now}) the effect is +0.0004", add=True)
    text = (project.root / "discoveries.md").read_text(encoding="utf-8")
    assert text.index("- Reviews:\n  - Claude Code (B): CLOSED") < text.index("- Correction:")
    assert "field.unknown" not in output
    unknown = ro_write.set_field(project, "D-A-001", "Corection", "typo", add=True)
    assert "discovery.field.unknown" in unknown  # Fable Q3: a typo is shown at once


def test_set_field_refuses_an_archived_discovery_stub(project):
    """astra round 8: an edit to the stub vanished when the discovery was restored."""
    from conftest import append_discovery
    append_discovery(project.root, "## D-A-001 — pilot effect\n- Date: 2026-11-01\n"
                                   "- Archived: docs/archive/discoveries-2026-11.md\n- Finding: +0.004\n")
    with pytest.raises(ValueError, match="ro archive restore D-A-001"):
        ro_write.set_field(project, "D-A-001", "Correction", "({now}) x", add=True)


def test_malformed_final_stamps_are_not_skipped():
    """astra round 8: `2026-11-3` did not count as a stamp, so an earlier valid one stood in."""
    assert evidence._last_stamp("a (observed 2026-11-01 10:00); b (observed 2026-11-3 10:00)", "observed") is None
    previous = {"Expected": "ok (written 2026-11-01 09:00)",
                "Result": "a (observed 2026-11-01 10:00); b (observed 2026-11-3 10:00)",
                "Reconciled": "not-accepted (observed 2026-11-01 11:00); service shows no run"}
    with pytest.raises(ValueError, match="Retry of requires"):
        evidence._retry_reconciled(previous, dt.datetime(2026, 11, 1, 12, 0))
    assert evidence._last_stamp("accepted (observed by the service log)", "observed") is None  # prose is not a stamp


def test_close_item_queues_follow_ups_past_a_fenced_section_example(project, tmp_path):
    """astra round 7: a fenced `## ` example inside another item was taken for the next section."""
    close_project(project)
    plan = project.root / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\n" + item("H-A-05")
                    + "\n```markdown\n## Agent: B\n```\n", encoding="utf-8", newline="\n")
    assert ro_write.close_item(project, "H-A-01", draft_file(tmp_path, full_draft())).startswith("closed H-A-01")
    text = plan.read_text(encoding="utf-8")
    assert "### H-A-02 — full run" in text


def test_set_field_refuses_a_malformed_shared_value(tmp_path):
    """astra round 7: `Active compute` and `Plan collection` format warnings were written as notes."""
    from conftest import make_project, set_slot
    root = make_project(tmp_path, "comp", "--preset", "competition-solo", "--platforms", "Claude Code",
                        "--user", "operator", "--competition", "hub/project", "--phase-clock", "off",
                        "--external-actions", "none")
    set_slot(root, "A", "Claude Code")
    project = Project(root, slot="A", session="record-commands")
    project.register_slot()
    for field in ("Active compute", "Plan collection"):
        with pytest.raises(ValueError, match="refused"):
            ro_write.set_field(project, "shared", field, "nonsense")


def test_retry_reconciliation_must_follow_every_prior_stamp():
    """astra round 6: the first observed stamp was compared, so a later observation was ignored."""
    previous = {"Expected": "ok (written 2026-11-01 10:00)",
                "Result": "first (observed 2026-11-01 11:00); final (observed 2026-11-01 13:00)",
                "Reconciled": "not-accepted (observed 2026-11-01 12:00); service shows no run"}
    with pytest.raises(ValueError, match="Retry of requires"):
        evidence._retry_reconciled(previous, dt.datetime(2026, 11, 1, 14, 0))
    previous["Reconciled"] = "not-accepted (observed 2026-11-01 13:30); service shows no run"
    evidence._retry_reconciled(previous, dt.datetime(2026, 11, 1, 14, 0))


def test_atomic_text_refuses_records_while_a_transaction_is_pending(project):
    from ro_state import atomic_text
    project.write_json("migration.json", {"from": "close-item", "to": "H-A-01"})
    with pytest.raises(ValueError, match="close-item --recover"):
        atomic_text(project.root / "plan.md", "# replaced\n")
    (project.state / "migration.json").unlink()


@pytest.mark.parametrize("changes", [1, 2])
def test_validated_write_rechecks_the_file_under_the_lock(project, monkeypatch, changes):
    """A write lands only on the bytes that were validated; a file changed on every try is refused."""
    real_compare, calls = ro_write._compare, {"n": 0}

    def compare_while_another_session_writes(target, proposed):
        notes = real_compare(target, proposed)
        calls["n"] += 1
        if calls["n"] <= changes:
            handoff = target.root / "handoff.md"
            handoff.write_text(handoff.read_text(encoding="utf-8") + f"\nother session {calls['n']}\n",
                               encoding="utf-8", newline="\n")
        return notes

    monkeypatch.setattr(ro_write, "_compare", compare_while_another_session_writes)
    if changes == 1:
        ro_write.event(project, "none", dict(EVENT))
        text = (project.root / "handoff.md").read_text(encoding="utf-8")
        assert "other session 1" in text and "- Action: pilot on the sample" in text
    else:
        with pytest.raises(ValueError, match="changed while it was being validated"):
            ro_write.event(project, "none", dict(EVENT))


@pytest.mark.parametrize("hook_first", [False, True])
def test_next_id_warns_about_a_jump(project, capsys, hook_first):
    """Round 6: a record hook that raised the mark first used to swallow the warning."""
    import ro_records as records
    from conftest import append_discovery
    records.next_id(project, "D")
    append_discovery(project.root, "## D-A-150 — typo\n- Date: 2026-11-01\n- Finding: x\n")
    if hook_first:
        records.reconcile_ids(project)  # what the PostToolUse snapshot does after the edit
    records.next_id(project, "D")
    assert "jumped from 1 to 150" in capsys.readouterr().err
    records.next_id(project, "D")
    assert "jumped" not in capsys.readouterr().err  # reported once


def test_archived_ids_skip_glued_decimals(project):
    import ro_records as records
    archive = project.root / "docs" / "archive"
    archive.mkdir(parents=True)
    (archive / "handoff-2026-10.md").write_text("- Result: X-A-313 0.488, then X-A-3130.488 by a typo\n",
                                                encoding="utf-8")
    assert records._archived_ids(project) == {"X-A-313"}


def test_brief_shows_a_pending_transaction_before_the_slot_choice(project, monkeypatch):
    import ro_records as records
    import ro_sessions
    monkeypatch.setattr(ro_sessions, "startup", lambda *a, **k: "Choose a slot: A or B")
    project.write_json("migration.json", {"from": "close-item", "to": "H-A-01"})
    text = records.brief(project)
    assert text.index("Interrupted record transaction") < text.index("Choose a slot")
    (project.state / "migration.json").unlink()
