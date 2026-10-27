"""Recover only from trusted durable state and preserve user-owned file bytes."""

import json
import os
import time

import pytest

from conftest import init, make_project, rs
import ro_records as records
import ro_state as state


def project(tmp_path):
    root = make_project(tmp_path, "project", "--preset", "quick", "--guards", "off")
    return state.Project(root, slot="AA", session="state-repair-test")


@pytest.mark.parametrize("damaged", [b"torn {", b"\xff\xfe", b"[]", b'{"pid":null}'])
def test_corrupt_lock_repair_keeps_original_bytes_and_inode(tmp_path, damaged):
    p = project(tmp_path)
    directory = p.state / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "state.lock"
    lock.write_bytes(damaged)
    inode = lock.stat().st_ino
    with p.lock(timeout=.05):
        assert p._locks.held["state"] == 1
        assert lock.stat().st_ino == inode
    assert json.loads(lock.read_text()) == {}
    assert [path.read_bytes() for path in directory.glob("state.lock.corrupt-*")] == [damaged]


def test_corrupt_metadata_cannot_override_os_lock(tmp_path):
    p = project(tmp_path)
    lock = p.state / "locks" / "state.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"broken metadata")
    fd = os.open(lock, os.O_RDWR)
    state._file_lock(fd)
    try:
        with pytest.raises(ValueError, match="held"):
            with p.lock(timeout=.02):
                pytest.fail("OS lock was bypassed")
        assert not list(lock.parent.glob("*.corrupt-*"))
    finally:
        state._file_unlock(fd)
        os.close(fd)
    assert lock.read_bytes() == b"broken metadata"


def test_valid_live_owner_is_not_replaced_even_without_os_lock(tmp_path):
    p = project(tmp_path)
    lock = p.state / "locks" / "state.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "start": state.process_start(os.getpid())}))
    before = lock.read_bytes()
    with pytest.raises(ValueError, match="not proven dead"):
        with p.lock(timeout=.02):
            pytest.fail("live owner was taken over")
    assert lock.read_bytes() == before


@pytest.mark.parametrize("name", ["ids.json", "id-high-water.json"])
@pytest.mark.parametrize("damage", ["torn {", "[]", "missing"])
def test_id_metadata_recovery_never_reuses_issued_identifier(tmp_path, name, damage):
    p = project(tmp_path)
    assert records.next_id(p, "H") == "H-AA-01"
    path = p.state / name
    if damage == "missing":
        path.unlink()
    else:
        path.write_text(damage, encoding="utf-8")
    assert records.next_id(state.Project(p.root, slot="AA"), "H") == "H-AA-02"
    assert p.read_json("id-high-water.json")["H-AA"] == 2
    if damage != "missing":
        assert [item.read_text() for item in p.state.glob(f"{name}.corrupt-*")] == [damage]


def test_id_recovery_refuses_when_both_copies_are_corrupt(tmp_path):
    p = project(tmp_path)
    records.next_id(p, "D")
    for path in (p.state / "id-high-water.json", p.state / "recovery" / "id-high-water.json"):
        path.write_text("broken", encoding="utf-8")
    before = (p.state / "ids.json").read_bytes()
    with pytest.raises(ValueError, match="trusted backup"):
        records.next_id(p, "D")
    assert (p.state / "ids.json").read_bytes() == before


def test_expired_leases_and_removed_records_keep_high_water(tmp_path):
    p = project(tmp_path)
    assert records.next_id(p, "X") == "X-AA-001"
    p.write_json("ids.json", {"X-AA-001": {"expires": time.time() - 1}})
    records.reconcile_ids(p)
    assert not p.read_json("ids.json")
    assert records.next_id(p, "X") == "X-AA-002"
    archive = p.root / "docs" / "old.md"
    archive.parent.mkdir(exist_ok=True)
    archive.write_text("Retired: D-AA-081\n", encoding="utf-8")
    assert records.next_id(p, "D") == "D-AA-082"
    archive.unlink()
    p.write_json("ids.json", {})
    assert records.next_id(state.Project(p.root, slot="AA"), "D") == "D-AA-083"
    assert records.next_id(state.Project(p.root, slot="B"), "D") == "D-B-001"


def test_allocation_interruption_after_high_water_commit_skips_number(tmp_path, monkeypatch):
    p = project(tmp_path)
    original = p.write_json
    def interrupt(name, data, **kwargs):
        if name == "ids.json":
            raise OSError("interrupted reservation write")
        return original(name, data, **kwargs)
    monkeypatch.setattr(p, "write_json", interrupt)
    with pytest.raises(OSError, match="interrupted"):
        records.next_id(p, "I")
    assert records.next_id(state.Project(p.root, slot="AA"), "I") == "I-AA-02"


def test_metadata_repair_is_under_state_lock(tmp_path, monkeypatch):
    p = project(tmp_path)
    p.write_json("registry.json", {"observed": True}, recoverable=True)
    path = p.state / "registry.json"
    path.write_text("torn", encoding="utf-8")
    original = state.atomic_text
    observed = []
    def guarded(target, content):
        assert getattr(p._locks, "held", {}).get("state")
        observed.append(target)
        return original(target, content)
    monkeypatch.setattr(state, "atomic_text", guarded)
    assert p.read_json("registry.json") == {"observed": True}
    assert observed == [path]


@pytest.mark.parametrize("newline", [b"\r\n", b"\n"])
def test_reconfigure_preserves_exact_mixed_project_rules_suffix(tmp_path, newline):
    p = project(tmp_path)
    path = p.root / "agents.md"
    generated, _ = rs.split_agents(path.read_text(encoding="utf-8"))
    region = b"## Project rules\r\nKeep these bytes.  \n\r\n```text\r\nraw\n```\r\nlast line"
    path.write_bytes(generated.replace("\n", newline.decode()).encode() + region)
    other_files = {name: (p.root / name).read_bytes() for name in ("plan.md", "handoff.md", "discoveries.md")}
    assert init.main([str(p.root), "--reconfigure", "--language", "Korean"]) == 0
    after = path.read_bytes()
    assert after[after.index(b"## Project rules"):] == region
    generated_after = after[:after.index(b"## Project rules")]
    assert (b"\r\n" in generated_after) == (newline == b"\r\n")
    assert all((p.root / name).read_bytes() == before for name, before in other_files.items())


def test_guard_insertion_keeps_existing_crlf_handoff_bytes(tmp_path):
    p = project(tmp_path)
    path = p.root / "handoff.md"
    before = path.read_text(encoding="utf-8").replace("\n", "\r\n").encode()
    path.write_bytes(before)
    settings = {**p.settings(), "guards": "strict"}
    updated = init.ensure_guard_sections(init.read_raw_text(path), settings).encode()
    for added in (b"## Instruments\r\n\r\n", b"## External actions\r\n\r\n"):
        updated = updated.replace(added, b"")
    assert updated == before


def test_ignore_extension_preserves_crlf_and_trailing_blank_lines(tmp_path):
    p = project(tmp_path)
    path = p.root / ".gitignore"
    original = b"# local rules  \r\ncache/\r\n\r\n"
    path.write_bytes(original)
    init.ignore_tool_state(p.root, {"git": "local"})
    assert path.read_bytes() == original + b".ro/\r\n"


def test_migration_preserves_crlf_rules_and_original_backups(tmp_path):
    p = project(tmp_path)
    files = ("agents.md", "plan.md", "handoff.md", "discoveries.md")
    before = {}
    for name in files:
        path = p.root / name
        before[name] = path.read_text(encoding="utf-8").replace("\n", "\r\n").encode()
        path.write_bytes(before[name])
    workflow = "classic" if p.settings()["workflow"] == "unified" else "unified"
    assert init.main([str(p.root), "--reconfigure", "--workflow", workflow, "--migrate",
                      "--user", "operator"]) == 0
    assert (p.root / "discoveries.md").read_bytes() == before["discoveries.md"]
    for name in ("agents.md", "plan.md", "handoff.md"):
        assert (p.root / (name + ".pre-migrate")).read_bytes() == before[name]
        assert b"\n" not in (p.root / name).read_bytes().replace(b"\r\n", b"")
    original_rules = before["agents.md"].split(b"## Project rules", 1)[1]
    assert (p.root / "agents.md").read_bytes().split(b"## Project rules", 1)[1] == original_rules
