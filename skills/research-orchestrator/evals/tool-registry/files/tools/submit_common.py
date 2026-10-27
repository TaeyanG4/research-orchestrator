"""Helpers shared by the upload tools."""

from __future__ import annotations

import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
