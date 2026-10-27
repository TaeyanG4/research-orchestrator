"""Scratch folders inherit the caller's ACL and retain host-created evidence."""

from pathlib import Path
import sys
import uuid


def create_scratch(parent: Path, prefix: str) -> Path:
    # tempfile's protected Windows ACL excludes the separate host sandbox user.
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / (prefix + uuid.uuid4().hex)
    path.mkdir()
    return path


def retire_scratch(path: Path) -> Path:
    """Move, rather than recursively delete, files owned by another host user."""
    destination = path.parent / "done" / path.name
    try:
        destination.parent.mkdir(exist_ok=True)
        path.rename(destination)
        return destination
    except OSError as error:
        # A cleanup failure must not discard an otherwise useful probe report.
        print(f"Scratch retained at {path}: {error}", file=sys.stderr)
        return path
