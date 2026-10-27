"""Published trigger scores remain traceable to every original attempt."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

import pytest

from scripts.evals.export_evidence import verify_evidence
from scripts.trigger.run_trigger_eval import summarize


EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "trigger" / "evidence"


@pytest.mark.parametrize("name", sorted(json.loads((EVIDENCE / "coverage.json").read_text(encoding="utf-8"))))
def test_trigger_evidence_retains_attempt_records_traces_and_honest_metrics(name):
    archive_path = EVIDENCE / f"{name}.zip"
    assert verify_evidence(archive_path) > 0
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            assert not member.endswith(("events.jsonl", "transcript.md"))
        withheld = {row["path"]: row["source_sha256"] for row in json.loads(archive.read("manifest.json"))["omitted"]}
        report = json.loads(archive.read(f"{name}/results.json"))
        rows = report["metrics"]["all"]["results"]
        summary = json.loads((EVIDENCE / "coverage.json").read_text(encoding="utf-8"))[name]
        assert summary["archive_sha256"] == hashlib.sha256(archive_path.read_bytes()).hexdigest()
        for split, stored in report["metrics"].items():
            selected = [row for row in rows if split == "all" or row["split"] == split]
            recomputed = summarize(selected, report["threshold"])
            for metric in ("counts", "precision", "recall", "accuracy", "coverage"):
                assert stored[metric] == recomputed[metric]
                assert summary[split][metric] == recomputed[metric]
            for label, expected in (("positive", True), ("negative", False)):
                group = [row for row in selected if row["should_trigger"] is expected]
                scored = sum(row["predicted"] is not None for row in group)
                assert summary[split][f"{label}_coverage"] == {
                    "scored": scored, "total": len(group),
                    "fraction": scored / len(group) if group else None,
                }
        attempts = []
        for row in rows:
            assert len(row["runs"]) == report["repeats"]
            for repeat, run in enumerate(row["runs"], 1):
                for attempt in run["attempts"]:
                    folder = (f"{name}/query-{row['query_index'] + 1:02d}-repeat-{repeat}"
                              f"/attempt-{attempt['attempt']}")
                    assert json.loads(archive.read(f"{folder}/run.json")) == attempt
                    assert len(withheld[f"{folder}/events.jsonl"]) == 64
                    assert len(withheld[f"{folder}/stderr.txt"]) == 64
                    if attempt.get("measurement_protocol") == "first-selection-v1":
                        assert len(withheld[f"{folder}/events-after-selection.jsonl"]) == 64
                        boundary = attempt.get("selection_boundary")
                        if boundary:
                            assert boundary["event"] > 0
                            assert attempt["detection"]["triggered"]
                    if attempt["status"] != "ok":
                        assert attempt["triggered"] is None
                    attempts.append(f"{folder}/run.json")
        archived = [member for member in archive.namelist() if member.endswith("/run.json")]
        assert sorted(archived) == sorted(attempts)


def test_missing_positive_coverage_cannot_be_interpreted_as_full_recall():
    rows = [{"should_trigger": True, "runs": [{"triggered": True}] * 3},
            {"should_trigger": True, "runs": [{"triggered": True}, {"triggered": None},
                                               {"triggered": True}]},
            {"should_trigger": False, "runs": [{"triggered": False}] * 3}]
    metrics = summarize(rows, .5)
    assert metrics["recall"] == 1
    assert metrics["coverage"] == 2 / 3
    assert metrics["counts"]["inconclusive"] == 1
    assert metrics["results"][1]["predicted"] is None
