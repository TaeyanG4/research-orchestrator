"""Checkout-independent text content without changing binary artifact bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path


def normalize_text(data: bytes) -> bytes:
    """Use LF for UTF-8 text; preserve binary data, including embedded NULs."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def file_digest(path: Path) -> str:
    return hashlib.sha256(normalize_text(path.read_bytes())).hexdigest()
