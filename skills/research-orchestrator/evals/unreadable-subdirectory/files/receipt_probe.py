"""Inject a portable enumeration failure into actual receipt and execution operations."""

import argparse
import errno
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
import ro_evidence as evidence
from ro_state import Project

project = Project(Path.cwd(), session="release-author")
# The positive control exceeds the old cap, without retaining a large fixture in Git.
large = project.root / "large-artifact.bin"
chunk = b"\0" + b"a" * (1024 * 1024 - 1)
expected_digest = hashlib.sha256()
with large.open("wb") as output:
    for _ in range(65):
        output.write(chunk)
        expected_digest.update(chunk)
large_digest = evidence.hash_artifact(project, large.name)
large.unlink()
digest = evidence.hash_artifact(project, "bundle")["sha256"]
ledger = project.root / "handoff.md"
ledger.write_text("## External actions\n\n### X-A-001 local release\n"
                  f"- Candidate: bundle, hash {digest}\n- Destination: local mock\n"
                  "- Expected: local success (written 2020-01-01 08:00)\n"
                  "- Result: pending\n- Final: pending\n- Status: prepared\n", encoding="utf-8")
evidence.receipt_add(project, "bundle", "release-reviewer", "PASS", "X-A-001", "local mock")
receipt = project.state / "receipts.json"
before = {"receipts": receipt.read_bytes(), "ledger": ledger.read_bytes()}
scandir = evidence.os.scandir


def deny_references(path):
    if Path(path).resolve() == (project.root / "bundle" / "references").resolve():
        raise PermissionError(errno.EACCES, "directory enumeration denied", str(path))
    return scandir(path)


args = argparse.Namespace(artifact="bundle", action="X-A-001", command=[
    sys.executable, "-c", "from pathlib import Path; Path('executed.txt').touch()"])
operations = {
    "add": lambda: evidence.receipt_add(project, "bundle", "release-reviewer", "PASS", "X-A-001", "local mock"),
    "check": lambda: evidence.receipt_check(project, "bundle", "X-A-001", "local mock"),
    "external": lambda: evidence.external(project, args),
}
results = {"large_artifact_hashed": large_digest["sha256"] == expected_digest.hexdigest(),
           "large_artifact_bytes": large_digest.get("bytes")}
with patch.object(evidence.os, "scandir", deny_references):
    for name, operation in operations.items():
        try:
            operation()
            results[name] = {"refused": False, "error_type": None}
        except (OSError, ValueError) as error:
            results[name] = {"refused": True, "error_type": type(error).__name__}
results["receipts_unchanged"] = receipt.read_bytes() == before["receipts"]
results["ledger_unchanged"] = ledger.read_bytes() == before["ledger"]
results["executed"] = (project.root / "executed.txt").exists()
results["before_sha256"] = {name: hashlib.sha256(data).hexdigest() for name, data in before.items()}
results["after_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for name, path in (("receipts", receipt), ("ledger", ledger))}
Path("receipt-probe.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, sort_keys=True))
