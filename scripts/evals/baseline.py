"""Pin and verify the released v2 skill used by the evaluation harness."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

if __package__:
    from .content import file_digest
    from .proc import no_window_flags
else:
    from content import file_digest
    from proc import no_window_flags


BASELINE_REVISION = "713088d79745589b053ae02996670dc7147a8ee1"
BASELINE_RELEASE = "5.1.0"
BASELINE_DIGEST = "b2c01f24428b04d8a31225e0f7a3aaed0cc819b52715292c165a264a943588c4"
LEGACY_BASELINE_DIGEST = "e917188bec6fc9ea39b3b0cc04f25f3558da9304d1e1d231befebdb74a0fbed0"
SKILL_SUBTREE = "skills/research-orchestrator-skill"


def content_digest(skill: Path) -> str:
    """SHA-256 of a sorted JSON manifest of paths, kinds, and file SHA-256s.

    UTF-8 text uses LF so checkout conversion cannot invalidate a frozen skill.
    Binary bytes are exact; filesystem metadata does not affect the digest.
    """
    if skill.is_symlink() or skill.is_junction() or not skill.is_dir():
        raise ValueError(f"Baseline must be a plain directory: {skill}")
    manifest = []
    for path in sorted(skill.rglob("*"), key=lambda entry: entry.relative_to(skill).as_posix()):
        relative = path.relative_to(skill).as_posix()
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Links are not supported in baseline snapshots: {path}")
        if path.is_dir():
            manifest.append([relative, "dir"])
        elif path.is_file():
            manifest.append([relative, "file", file_digest(path)])
        else:
            raise ValueError(f"Unsupported baseline entry: {path}")
    encoded = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_old_skill(skill: Path) -> str:
    """Verify fresh, reused, and caller-supplied snapshots against the same pin."""
    actual = content_digest(skill)
    if actual != BASELINE_DIGEST:
        raise ValueError(f"Baseline content digest mismatch in {skill}: expected {BASELINE_DIGEST}, got {actual}")
    return BASELINE_REVISION


def snapshot_old_skill(repository: Path, workspace: Path) -> tuple[Path, str]:
    """Archive release 5.1.0 once, verifying its immutable content on every use."""
    target = workspace / "old-skill-snapshot"
    skill = target / SKILL_SUBTREE
    metadata = target / "snapshot.json"
    if target.exists():
        stored = json.loads(metadata.read_text(encoding="utf-8"))
        if (not isinstance(stored, dict) or stored.get("revision") != BASELINE_REVISION
                or stored.get("content_sha256", BASELINE_DIGEST) not in (BASELINE_DIGEST, LEGACY_BASELINE_DIGEST)):
            raise ValueError(f"Baseline metadata does not match release {BASELINE_RELEASE}: {target}")
        return skill, validate_old_skill(skill)
    workspace.mkdir(parents=True, exist_ok=True)
    git = ["git", "-c", f"safe.directory={repository.as_posix()}", "-C", str(repository)]
    archive = subprocess.run(git + ["archive", "--format=tar", BASELINE_REVISION, SKILL_SUBTREE],
                             capture_output=True, check=True, stdin=subprocess.DEVNULL,
                             creationflags=no_window_flags()).stdout
    with tempfile.TemporaryDirectory(prefix=".baseline-", dir=workspace) as temporary:
        staging = Path(temporary) / "snapshot"
        staging.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
            names = set()
            for member in source.getmembers():
                rel = PurePosixPath(member.name)
                if (rel.is_absolute() or ".." in rel.parts or "\\" in member.name or ":" in member.name
                        or not (member.isfile() or member.isdir()) or member.name in names
                        or not (member.name == "skills" or member.name.rstrip("/") == SKILL_SUBTREE
                                or member.name.startswith(SKILL_SUBTREE + "/"))):
                    raise ValueError(f"Unsafe member in baseline archive: {member.name}")
                names.add(member.name)
            source.extractall(staging, filter="data")
        validate_old_skill(staging / SKILL_SUBTREE)
        (staging / "snapshot.json").write_text(json.dumps({
            "revision": BASELINE_REVISION, "release": BASELINE_RELEASE,
            "subtree": SKILL_SUBTREE, "content_sha256": BASELINE_DIGEST,
            "digest_format": "sha256-json-path-kind-lf-text-file-sha256-v1",
        }, indent=2) + "\n", encoding="utf-8")
        staging.rename(target)  # Never merge into or overwrite an existing snapshot.
    return skill, BASELINE_REVISION
