"""Exported evidence retains failures and trace/output identity without host paths."""
import hashlib
import json
import zipfile

import pytest

from scripts.evals.export_evidence import export_evidence, sanitize_text, verify_evidence


def test_evidence_export_preserves_exclusions_grades_and_raw_links(tmp_path):
    source = tmp_path / "iteration"
    run = source / "case" / "old_skill"
    outputs = run / "outputs"
    outputs.mkdir(parents=True)
    status = {"excluded": True, "exclusion_reason": "foreign source read", "status": "contaminated",
              "project": "C:/Users/researcher/task", "api_key": "do-not-export"}
    raw = json.dumps(status).encode()
    (run / "run.json").write_bytes(raw)
    (run / "events.jsonl").write_text(json.dumps({"text": "read C:/Users/researcher/task/input.csv"}) + "\n")
    (run / "grading.json").write_text(json.dumps({"expectations": [{"passed": False, "evidence": "absent"}]}))
    (outputs / "analysis.py").write_text("print('relative/input.csv')\n")
    (outputs / "binary.bin").write_bytes(b"\xff\x00")
    (source / "review.html").write_text("duplicate viewer")
    target = tmp_path / "audit.zip"
    manifest = export_evidence({"prior": source}, target, private_terms=("researcher",))
    assert verify_evidence(target) == 2
    with zipfile.ZipFile(target) as archive:
        saved = json.loads(archive.read("prior/case/old_skill/run.json"))
        assert saved["excluded"] and saved["status"] == "contaminated"
        assert saved["exclusion_reason"] == status["exclusion_reason"]
        assert saved["api_key"] == "<redacted>"
        assert "researcher" not in saved["project"]
        assert json.loads(archive.read("prior/case/old_skill/grading.json"))["expectations"][0]["passed"] is False
        assert not any("events" in name or "/outputs/" in name for name in archive.namelist())
        record = next(row for row in manifest["files"] if row["path"].endswith("/run.json"))
        assert record["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert len(manifest["omitted"]) == 4
    with pytest.raises(ValueError, match="exists"):
        export_evidence({"prior": source}, target)


@pytest.mark.parametrize("value", [r"C:\Users\name\project\input.csv", "/home/name/run", "/tmp/task/file", r"\\host\share\project"])
def test_sanitizer_masks_host_paths_with_stable_identity(value):
    result = sanitize_text(f"Read {value} then {value}")
    assert value not in result
    assert result.split()[1] == result.split()[3]
    assert sanitize_text("outputs/file.csv https://example.org/a") == "outputs/file.csv https://example.org/a"


def test_evidence_verifier_rejects_tampered_payload(tmp_path):
    source = tmp_path / "run"
    source.mkdir()
    (source / "run.json").write_text('{"excluded":true}')
    target = tmp_path / "audit.zip"
    export_evidence({"prior": source}, target)
    with zipfile.ZipFile(target) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["prior/run.json"] = b'{"excluded":false}'
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_evidence(target)


def test_output_export_preserves_substance_and_hashes_without_raw_streams(tmp_path):
    source = tmp_path / "saved"
    run = source / "case" / "with_skill"
    outputs = run / "outputs"
    outputs.mkdir(parents=True)
    raw = b'{"mean":2.5,"thread_id":"private-id","path":"/home/person/project/input.csv"}'
    (outputs / "result.json").write_bytes(raw)
    (outputs / "analysis.py").write_text("print(2.5)\n", encoding="utf-8", newline="\n")
    for name in ("events.jsonl", "transcript.md", "inventory.json", "review.html", "raw.zip"):
        (outputs / name).write_text("withheld material", encoding="utf-8")
    (run / "grading.json").write_text('{"expectations":[{"passed":false,"evidence":"wrong interval"}]}')
    (run / "timing.json").write_text('{"total_tokens":123,"duration_ms":456}')
    target = tmp_path / "outputs.zip"
    manifest = export_evidence({"adjudicated": source}, target, include_outputs=True)
    assert verify_evidence(target) == 4
    with zipfile.ZipFile(target) as archive:
        result = json.loads(archive.read("adjudicated/case/with_skill/outputs/result.json"))
        assert result["mean"] == 2.5 and "thread_id" not in result
        assert "/home/" not in result["path"]
        assert archive.read("adjudicated/case/with_skill/outputs/analysis.py") == b"print(2.5)\n"
        assert len(manifest["omitted"]) == 5
    row = next(row for row in manifest["files"] if row["path"].endswith("result.json"))
    assert row["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_retained_adjudicated_task_outputs_are_inspectable():
    from pathlib import Path
    evidence = Path(__file__).resolve().parents[1] / "docs" / "evals" / "evidence"
    summary = json.loads((evidence / "iteration-6-outputs.json").read_text(encoding="utf-8"))
    archive_path = evidence / summary["archive"]
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == summary["archive_sha256"]
    assert verify_evidence(archive_path) == summary["exported_files"]
    assert not summary["new_runs"] and not summary["new_grading"]
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert sum("/outputs/" in name for name in names) == summary["task_output_files"]
        assert any(name.endswith("/outputs/replication.json") for name in names)
        for configuration in ("with_skill", "old_skill"):
            assert any(f"/{configuration}/outputs/plan.md" in name for name in names)
            assert any(f"/{configuration}/grading.json" in name for name in names)
            assert any(f"/{configuration}/timing.json" in name for name in names)
