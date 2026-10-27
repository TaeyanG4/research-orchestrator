"""Exact release-check excerpt for this isolated fixture; not a recorded execution."""
import os
from pathlib import Path
import re

ROOT = Path.cwd()


def check_release_receipt(errors: list[str], root: Path = ROOT) -> None:
    """Require the coordinator's completed local receipt only at publication time."""
    if os.environ.get("RO_RELEASE_RECEIPT_REQUIRED") != "1":
        return
    path = root / "docs" / "evals" / "README.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    section = re.search(r"^## Release candidate test receipt\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    rows = re.findall(r"^\|([^\n]+)\|\s*$", section[1], re.M) if section else []
    fields = [field.strip().strip("`") for field in rows[-1].split("|")] if rows else []
    if (len(rows) != 3 or len(fields) != 5 or any(not field for field in fields)
            or any(re.search(r"<[^>]+>", field) for field in fields)
            or any(re.fullmatch(r"[-: ]+", field) for field in fields)):
        errors.append("release receipt: docs/evals/README.md needs a completed Release candidate test receipt "
                      "(date, interpreter, pytest summary, validate_release result, commit)")
