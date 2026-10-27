"""Baseline integrity checks; no Codex or git subprocesses are launched."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from scripts.evals import baseline


@pytest.fixture
def released_skill(tmp_path, monkeypatch):
    skill = tmp_path / "released"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(b"# Released skill\n")
    (skill / "scripts" / "check.py").write_bytes(b"print('release')\n")
    monkeypatch.setattr(baseline, "BASELINE_DIGEST", baseline.content_digest(skill))
    return skill


def archive_bytes(skill: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        archive.add(skill, arcname=baseline.SKILL_SUBTREE)
    return buffer.getvalue()


def test_fresh_snapshot_uses_pinned_commit_and_revalidates_on_reuse(tmp_path, monkeypatch, released_skill):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert command[-4:] == ["archive", "--format=tar", baseline.BASELINE_REVISION, baseline.SKILL_SUBTREE]
        assert kwargs["check"] is True and kwargs["stdin"] == subprocess.DEVNULL
        return subprocess.CompletedProcess(command, 0, stdout=archive_bytes(released_skill))

    monkeypatch.setattr(baseline.subprocess, "run", fake_run)
    workspace = tmp_path / "workspace"
    skill, revision = baseline.snapshot_old_skill(tmp_path / "repository", workspace)
    assert revision == "713088d79745589b053ae02996670dc7147a8ee1"
    metadata = json.loads((workspace / "old-skill-snapshot" / "snapshot.json").read_text(encoding="utf-8"))
    assert metadata["content_sha256"] == baseline.BASELINE_DIGEST
    assert metadata["release"] == "5.1.0"
    assert baseline.snapshot_old_skill(tmp_path / "repository", workspace) == (skill, revision)
    assert len(calls) == 1
    (skill / "scripts" / "check.py").write_bytes(b"print('tampered')\n")
    with pytest.raises(ValueError, match="content digest mismatch"):
        baseline.snapshot_old_skill(tmp_path / "repository", workspace)
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["edit", "extra", "missing", "rename", "empty-directory"])
def test_explicit_snapshot_rejects_content_changes(released_skill, change):
    assert baseline.validate_old_skill(released_skill) == baseline.BASELINE_REVISION
    script = released_skill / "scripts" / "check.py"
    if change == "edit":
        script.write_bytes(b"print('other')\n")
    elif change == "extra":
        (released_skill / "AGENTS.md").write_bytes(b"Unexpected instructions\n")
    elif change == "missing":
        script.unlink()
    elif change == "rename":
        script.rename(script.with_name("other.py"))
    else:
        (released_skill / "extra").mkdir()
    with pytest.raises(ValueError, match="content digest mismatch"):
        baseline.validate_old_skill(released_skill)


def test_snapshot_digest_ignores_checkout_line_endings(released_skill):
    for path in released_skill.rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert baseline.validate_old_skill(released_skill) == baseline.BASELINE_REVISION


@pytest.mark.parametrize("data", [b"\x00binary\r\n", b"\xffbinary\r\n"])
def test_snapshot_digest_preserves_binary_line_endings(released_skill, data):
    binary = released_skill / "artifact.bin"
    binary.write_bytes(data)
    before = baseline.content_digest(released_skill)
    binary.write_bytes(data.replace(b"\r\n", b"\n"))
    assert baseline.content_digest(released_skill) != before


def test_fresh_mismatched_archive_is_refused_and_staging_is_removed(tmp_path, monkeypatch, released_skill):
    (released_skill / "SKILL.md").write_bytes(b"Not the released version\n")
    monkeypatch.setattr(baseline.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, stdout=archive_bytes(released_skill)))
    workspace = tmp_path / "workspace"
    with pytest.raises(ValueError, match="content digest mismatch"):
        baseline.snapshot_old_skill(tmp_path / "repository", workspace)
    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize("kind", ["traversal", "symlink"])
def test_unsafe_archive_is_refused_before_extraction(tmp_path, monkeypatch, kind):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("../escape" if kind == "traversal" else baseline.SKILL_SUBTREE + "/link")
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "../outside"
        archive.addfile(member)
    monkeypatch.setattr(baseline.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, stdout=buffer.getvalue()))
    workspace = tmp_path / "workspace"
    with pytest.raises(ValueError, match="Unsafe member"):
        baseline.snapshot_old_skill(tmp_path / "repository", workspace)
    assert list(workspace.iterdir()) == []


def test_reused_snapshot_rejects_other_revision_even_with_correct_content(tmp_path, released_skill):
    workspace = tmp_path / "workspace"
    target = workspace / "old-skill-snapshot"
    skill = target / baseline.SKILL_SUBTREE
    skill.parent.mkdir(parents=True)
    released_skill.rename(skill)
    (target / "snapshot.json").write_text(json.dumps({"revision": "a" * 40}), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata does not match"):
        baseline.snapshot_old_skill(tmp_path / "repository", workspace)


@pytest.mark.parametrize("digest", [None, baseline.LEGACY_BASELINE_DIGEST])
def test_legacy_metadata_still_requires_pinned_content(tmp_path, released_skill, digest):
    workspace = tmp_path / "workspace"
    target = workspace / "old-skill-snapshot"
    skill = target / baseline.SKILL_SUBTREE
    skill.parent.mkdir(parents=True)
    released_skill.rename(skill)
    metadata = {"revision": baseline.BASELINE_REVISION, "ref": "main"}
    if digest:
        metadata["content_sha256"] = digest
    (target / "snapshot.json").write_text(json.dumps(metadata), encoding="utf-8")
    assert baseline.snapshot_old_skill(tmp_path / "repository", workspace) == (skill, baseline.BASELINE_REVISION)
    (skill / "SKILL.md").write_bytes(b"changed")
    with pytest.raises(ValueError, match="content digest mismatch"):
        baseline.snapshot_old_skill(tmp_path / "repository", workspace)
