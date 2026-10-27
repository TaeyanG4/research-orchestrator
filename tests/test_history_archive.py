"""Bounded startup reads: the compact index, size warnings and `ro archive` (7.0.0)."""

from __future__ import annotations

from collections import Counter

import pytest

from conftest import append_discovery, append_events, check, event, found, item, set_queue, unified_project
import ro_archive
import ro_records as records
from ro_state import Project


def discovery(key: str, state: str = "VERIFIED", date: str = "2026-09-01", finding: str = "a settled result") -> str:
    return (f"## {key} — {finding[:40]}\n- Source: A\n- Host: Claude Code\n- User: operator\n- Date: {date}\n"
            f"- Cross-check: {state}\n- Finding: {finding}\n- Evidence: hidden {key} evidence\n"
            f"- Implication: none\n- Reviews:\n")


def project(tmp_path, *entries: str) -> Project:
    p = Project(unified_project(tmp_path), slot="A", session="archive-session")
    p.register_slot()
    for entry in entries:
        append_discovery(p.root, entry)
    return p


def issues(target) -> Counter:
    return Counter((i.severity, i.check, i.record) for i in check(target).issues if i.check != "history.size")


def test_index_keeps_whole_findings_until_it_passes_its_limit(tmp_path, monkeypatch):
    long = "measured " + "x" * 400 + " under the cold cache only"
    p = project(tmp_path, discovery("D-A-001", finding=long), discovery("D-A-002", state="PENDING"))
    index = records.discovery_index(p)
    # A small index keeps the conditions at the end of each finding: they decide duplicates.
    assert index.startswith("Discovery index: 2 live (PENDING 1, VERIFIED 1), 0 archived.")
    assert f"- Finding: {long}" in index and "clipped" not in index
    assert "Evidence" not in index and "hidden" not in index
    monkeypatch.setattr(records, "INDEX_LIMIT_BYTES", 200)
    index = records.discovery_index(p)
    assert "findings clipped to 160 characters because the whole index passes" in index
    line = next(row for row in index.splitlines() if row.startswith("- Finding: measured"))
    assert len(line) == records.FINDING_CLIP and line.endswith("…")
    assert f"- Finding: {long}" in records.discovery_index(p, full=True)


def test_archived_discoveries_leave_the_index_but_stay_findable(tmp_path):
    p = project(tmp_path, discovery("D-A-001", finding="old distinctive result"),
                discovery("D-A-002", finding="newer settled result", date="2026-10-01"),
                discovery("D-A-003", state="PENDING", finding="awaiting review"))
    before = issues(p.root)
    original = {key: records.discovery_index(p, key) for key in ("D-A-001", "D-A-002")}
    output = ro_archive.archive_discoveries(p, before="2026-09-15")
    assert "1 discoveries to docs/archive/discoveries-2026-09.md (D-A-001)" in output
    text = (p.root / "discoveries.md").read_text(encoding="utf-8")
    assert "- Archived: docs/archive/discoveries-2026-09.md" in text and "hidden D-A-001 evidence" not in text
    assert (p.root / "docs/archive/discoveries-2026-09.md").read_text(encoding="utf-8").count("## D-A-001 ") == 1
    # The checker reads the archived entry, so archiving changes no finding.
    assert issues(p.root) == before
    index = records.discovery_index(p)
    assert "D-A-001" not in index and "1 archived" in index and "D-A-002" in index
    assert "D-A-001 — old distinctive result (archived" in records.discovery_index(p, full=True)
    opened = records.discovery_index(p, "D-A-001")
    assert opened.startswith(original["D-A-001"]) and "(archived in docs/archive/discoveries-2026-09.md)" in opened
    # dupcheck finds the full archived entry once, not the stub.
    matches = records.dupcheck(p, ["distinctive"]).splitlines()
    assert matches and all(row.startswith("docs/archive/discoveries-2026-09.md:") for row in matches)
    # Archived numbers are never reissued.
    assert records.next_id(p, "D") == "D-A-004"


def test_archive_keeps_unsettled_and_cited_discoveries(tmp_path, monkeypatch):
    p = project(tmp_path, *(discovery(f"D-A-00{n}") for n in range(1, 4)),
                discovery("D-A-004", state="HOLD"), discovery("D-A-005", state="CHALLENGED"))
    set_queue(p.root, item("H-A-01").replace("- Sources: none", "- Sources: D-A-002"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)  # archive everything eligible
    assert "(D-A-001, D-A-003)" in ro_archive.archive_discoveries(p)
    stubs = [entry[0] for entry in records._discovery_entries((p.root / "discoveries.md").read_text(encoding="utf-8"))
             if entry[4]]
    assert stubs == ["D-A-001", "D-A-003"]
    assert ro_archive.archive_discoveries(p).startswith("Nothing to archive: no settled (VERIFIED)")


def test_self_verification_archives_unreviewed_entries(tmp_path, monkeypatch):
    from conftest import make_project
    target = make_project(tmp_path, "self", "--preset", "solo-research", "--platforms", "Claude Code",
                          "--user", "operator", "--verification", "self")
    p = Project(target, slot="A", session="archive-session")
    assert p.settings().get("verification") == "self"
    append_discovery(target, discovery("D-A-001", state="PENDING"))
    append_discovery(target, discovery("D-A-002", state="HOLD"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    assert "(D-A-001)" in ro_archive.archive_discoveries(p)


def test_dry_run_changes_nothing_and_rerun_after_a_crash_is_safe(tmp_path, monkeypatch):
    p = project(tmp_path, discovery("D-A-001"), discovery("D-A-002"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    snapshot = {path: path.read_bytes() for path in p.root.rglob("*.md")}
    assert ro_archive.archive_discoveries(p, dry_run=True).startswith("Would archive 2 discoveries")
    assert {path: path.read_bytes() for path in p.root.rglob("*.md")} == snapshot
    # A crash after the archive write but before discoveries.md changed: the rerun completes it.
    real = p.atomic_text
    calls = []

    def crash(path, text):
        calls.append(path.name)
        if path.name == "discoveries.md":
            raise OSError("interrupted")
        real(path, text)
    monkeypatch.setattr(p, "atomic_text", crash)
    with pytest.raises(OSError):
        ro_archive.archive_discoveries(p)
    monkeypatch.setattr(p, "atomic_text", real)
    assert "Archived 2 discoveries" in ro_archive.archive_discoveries(p)
    archive = (p.root / "docs/archive/discoveries-2026-09.md").read_text(encoding="utf-8")
    assert archive.count("## D-A-001 ") == 1 and archive.count("## D-A-002 ") == 1


def test_broken_archive_link_is_an_error_and_a_stale_stub_state_a_warning(tmp_path, monkeypatch):
    p = project(tmp_path, discovery("D-A-001"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    ro_archive.archive_discoveries(p)
    stub = p.root / "discoveries.md"
    text = stub.read_text(encoding="utf-8")
    stub.write_text(text.replace("- Cross-check: VERIFIED\n- Finding: a settled", "- Cross-check: HOLD\n- Finding: a settled"),
                    encoding="utf-8", newline="\n")
    assert found(check(p.root), "WARN", "discovery.archive.mismatch")
    (p.root / "docs/archive/discoveries-2026-09.md").unlink()
    stub.write_text(text, encoding="utf-8", newline="\n")
    assert found(check(p.root), "ERROR", "discovery.archive.missing")
    with pytest.raises(ValueError, match="not a file under docs/"):
        records.discovery_index(p, "D-A-001")


def test_size_warning_names_the_archive_command_in_checker_and_brief(tmp_path, monkeypatch):
    p = project(tmp_path, discovery("D-A-001", finding="y" * 300))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 64)
    monkeypatch.setattr(ro_archive, "HANDOFF_WARN_BYTES", 64)
    sizes = found(check(p.root), "WARN", "history.size")
    assert {issue.record for issue in sizes} == {"discoveries.md", "handoff.md"}
    assert any("ro archive discoveries" in issue.message for issue in sizes)
    brief = records.brief(p)
    assert ("history.size: discoveries.md past its startup-read limit, run ro archive discoveries; "
            "handoff.md past its startup-read limit, run ro archive events") in brief
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 48 * 1024)
    monkeypatch.setattr(ro_archive, "HANDOFF_WARN_BYTES", 192 * 1024)
    assert not found(check(p.root), "WARN", "history.size")


def test_warning_and_archiving_follow_the_whole_index_that_decides_clipping(tmp_path, monkeypatch):
    """Once findings are clipped the checker warns, even though the clipped index itself fits."""
    p = project(tmp_path, *(discovery(f"D-A-00{n}", finding="long " + "x" * 900) for n in range(1, 4)))
    text = (p.root / "discoveries.md").read_text(encoding="utf-8")
    whole = len(records.index_text(text, clip=False).encode("utf-8"))
    clipped = len(records.index_text(text, clip=True).encode("utf-8"))
    limit = (whole + clipped) // 2
    monkeypatch.setattr(records, "INDEX_LIMIT_BYTES", limit)
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", limit)
    assert "findings clipped" in records.discovery_index(p)
    assert found(check(p.root), "WARN", "history.size")
    assert "Archived" in ro_archive.archive_discoveries(p)
    assert not found(check(p.root), "WARN", "history.size")


def test_event_archive_keeps_live_items_latest_events_and_adds_history(tmp_path, monkeypatch):
    p = project(tmp_path)
    set_queue(p.root, item("H-A-02"))
    append_events(p.root, event("2026-09-01 10:00", "A", "H-A-01"), event("2026-09-02 10:00", "A", "H-A-02/s1"),
                  event("2026-09-03 10:00", "B", "none"), event("2026-09-04 10:00", "A", "none"),
                  event("2026-10-01 10:00", "B", "none"), event("2026-10-02 10:00", "A", "none"))
    before = check(p.root)
    output = ro_archive.archive_events(p, before="2026-10-15")
    assert output.startswith("Archived 3 events to docs/archive/handoff-2026-09.md")
    handoff = (p.root / "handoff.md").read_text(encoding="utf-8")
    kept = [line for line in handoff.splitlines() if line.startswith("### 2026-")]
    # The live item's stage event and each slot's latest event stay; older ones move.
    assert kept == ["### 2026-09-02 10:00 — A — H-A-02/s1", "### 2026-10-01 10:00 — B — none",
                    "### 2026-10-02 10:00 — A — none"]
    archive = (p.root / "docs/archive/handoff-2026-09.md").read_text(encoding="utf-8")
    assert all(f"### 2026-09-0{day} 10:00" in archive for day in (1, 3, 4))
    assert ("- [docs/archive/handoff-2026-09.md](docs/archive/handoff-2026-09.md): 3 events, "
            "2026-09-01 10:00 to 2026-09-04 10:00") in handoff
    after = check(p.root)
    assert not {(i.check, i.record) for i in after.issues if i.severity == "ERROR"} - {
        (i.check, i.record) for i in before.issues if i.severity == "ERROR"}
    assert ro_archive.archive_events(p, before="2026-10-15").startswith("Nothing to archive")


def test_event_archive_keeps_the_finish_of_an_item_a_kept_event_queued(tmp_path):
    """A kept event's New plan items must still resolve, or the checker reports the item lost."""
    p = project(tmp_path)
    set_queue(p.root, item("H-A-01"))
    append_events(p.root, event("2026-08-30 10:00", "B", "none"),
                  event("2026-09-01 10:00", "A", "H-A-01/s1", new_items="H-A-07"),
                  event("2026-09-02 10:00", "B", "H-A-07"), event("2026-09-03 10:00", "B", "none"),
                  event("2026-09-04 10:00", "A", "none"))
    errors = lambda: {(i.check, i.record) for i in check(p.root).issues if i.severity == "ERROR"}
    before = errors()
    assert "Archived 1 events" in ro_archive.archive_events(p, before="2026-10-01")
    handoff = (p.root / "handoff.md").read_text(encoding="utf-8")
    assert "### 2026-09-02 10:00 — B — H-A-07" in handoff and "### 2026-08-30 10:00" not in handoff
    assert errors() == before


def test_a_concurrent_edit_is_never_overwritten(tmp_path, monkeypatch):
    """Sessions edit coordination files without the project lock; archiving re-reads before replacing."""
    p = project(tmp_path, discovery("D-A-001"), discovery("D-A-002"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    real = ro_archive._with_stubs

    def edit_meanwhile(text, chosen):
        append_discovery(p.root, discovery("D-A-003", state="PENDING", finding="written by another session"))
        return real(text, chosen)
    monkeypatch.setattr(ro_archive, "_with_stubs", edit_meanwhile)
    with pytest.raises(ValueError, match="changed while archiving"):
        ro_archive.archive_discoveries(p)
    text = (p.root / "discoveries.md").read_text(encoding="utf-8")
    assert "written by another session" in text and "- Archived:" not in text
    monkeypatch.setattr(ro_archive, "_with_stubs", real)
    assert "Archived 2 discoveries" in ro_archive.archive_discoveries(p)
    assert "written by another session" in (p.root / "discoveries.md").read_text(encoding="utf-8")


def test_restore_revise_and_archive_again(tmp_path, monkeypatch):
    p = project(tmp_path, discovery("D-A-001", finding="first wording"), discovery("D-A-002"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    ro_archive.archive_discoveries(p)
    archive = p.root / "docs/archive/discoveries-2026-09.md"
    original = records.archived_entry(p, "D-A-001", "docs/archive/discoveries-2026-09.md")
    assert ro_archive.restore_discovery(p, "D-A-001").startswith("Restored D-A-001")
    assert records.discovery_index(p, "D-A-001") == original  # the full entry is live again
    assert "## D-A-001 " not in archive.read_text(encoding="utf-8") and "## D-A-002 " in archive.read_text(encoding="utf-8")
    path = p.root / "discoveries.md"
    path.write_text(path.read_text(encoding="utf-8").replace("first wording", "revised wording"), encoding="utf-8",
                    newline="\n")
    assert "Archived 1 discoveries" in ro_archive.archive_discoveries(p)
    text = archive.read_text(encoding="utf-8")
    assert text.count("## D-A-001 ") == 1 and "revised wording" in text and "first wording" not in text
    assert issues(p.root) == issues(p.root)  # stable and resolvable after the round trip
    assert not found(check(p.root), "ERROR", "discovery.archive.missing")


def test_interrupted_restore_completes_on_rerun_and_conflicts_still_refuse(tmp_path, monkeypatch):
    p = project(tmp_path, discovery("D-A-001"), discovery("D-A-002"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    ro_archive.archive_discoveries(p)
    monkeypatch.setattr(ro_archive, "_drop_block", lambda *a: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(OSError):
        ro_archive.restore_discovery(p, "D-A-001")
    monkeypatch.undo()
    archive = p.root / "docs/archive/discoveries-2026-09.md"
    assert "## D-A-001 " in archive.read_text(encoding="utf-8")  # both copies exist after the interruption
    assert ro_archive.restore_discovery(p, "D-A-001").startswith("Finished restoring D-A-001")
    assert "## D-A-001 " not in archive.read_text(encoding="utf-8")
    assert ro_archive.restore_discovery(p, "D-A-001") == "Nothing to restore: D-A-001 is not archived."
    # Copying an entry back by hand leaves the archived copy; archiving a revision then refuses.
    stub = p.root / "discoveries.md"
    text = stub.read_text(encoding="utf-8")
    manual = records.archived_entry(p, "D-A-002", "docs/archive/discoveries-2026-09.md")
    start = text.index("## D-A-002 ")
    stub.write_text(text[:start] + manual.replace("a settled result", "edited by hand", 1) + "\n", encoding="utf-8",
                    newline="\n")
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    with pytest.raises(ValueError, match="ro archive restore D-A-002"):
        ro_archive.archive_discoveries(p)


def test_archive_preserves_crlf_records(tmp_path, monkeypatch):
    p = project(tmp_path, discovery("D-A-001"), discovery("D-A-002"))
    path = p.root / "discoveries.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    monkeypatch.setattr(ro_archive, "INDEX_WARN_BYTES", 0)
    ro_archive.archive_discoveries(p)
    data = path.read_bytes()
    assert b"- Archived: docs/archive/discoveries-2026-09.md\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
