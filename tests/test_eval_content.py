"""Eval content hashes survive text checkout conversion and still reject edits."""

import json
from pathlib import Path
import shutil
import sys

import pytest

from conftest import SKILL
from scripts.evals.content import file_digest, normalize_text
from scripts.evals.evidence import EvidenceBroker


@pytest.mark.parametrize("source_crlf", [False, True])
@pytest.mark.parametrize("changed", [None, "simulate_external.py", "release-note.txt"])
def test_broker_uses_normalized_text_identity(tmp_path, source_crlf, changed):
    case = tmp_path / "external-action-order"
    source = case / "files"
    shutil.copytree(SKILL / "evals" / case.name / "files", source)
    project = tmp_path / "project"
    shutil.copytree(source, project)
    for path in source.iterdir():
        data = normalize_text(path.read_bytes())
        path.write_bytes(data.replace(b"\n", b"\r\n") if source_crlf else data)
        target = project / path.name
        target.write_bytes(data if source_crlf else data.replace(b"\n", b"\r\n"))
    (project / "handoff.md").write_bytes(b"## External actions\r\n\r\n- Status: prepared\r\n")
    if changed:
        path = project / changed
        path.write_bytes(path.read_bytes() + b"content change\n")
    run = tmp_path / "run"
    run.mkdir()
    with EvidenceBroker(case, project, run, Path(sys.executable)) as broker:
        broker._execute("a" * 32, {"helper": "simulate_external.py", "mode": "request"})
    capture = run / "evidence" / ("a" * 32)
    receipt = json.loads((capture / "receipt.json").read_text(encoding="utf-8"))
    if changed:
        assert receipt["returncode"] is None and "modified" in receipt["error"]
        return
    assert receipt["returncode"] == 0 and receipt["error"] is None
    assert receipt["helper_sha256"] == file_digest(source / "simulate_external.py")
    assert receipt["artifacts"] == {name: file_digest(capture / name) for name in receipt["artifacts"]}
    result = json.loads((capture / "action-result.json").read_text(encoding="utf-8"))
    assert result["candidate_sha256"] == file_digest(project / "release-note.txt")
    assert result["before_sha256"] == file_digest(project / "handoff.md")
