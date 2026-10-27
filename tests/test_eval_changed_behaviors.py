"""New behavior cases reject fabricated review, language drift, and wrong job outcomes."""

import json
import shutil
import sys

import pytest

from conftest import SKILL, check, found
from scripts.evals import checks


def context(tmp_path, case):
    source = SKILL / "evals" / case
    shutil.copytree(source / "files", tmp_path / "outputs")
    return checks.CheckContext(source, tmp_path, SKILL, sys.executable)


def test_language_case_starts_clean_and_rejects_setting_drift(tmp_path):
    ctx = context(tmp_path, "project-language")
    assert not found(check(ctx.outputs), "ERROR")
    assert checks.project_language(ctx)[0]
    path = ctx.outputs / "agents.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Language: ko", "Language: en"), encoding="utf-8")
    assert not checks.project_language(ctx)[0]


@pytest.mark.parametrize("change", ["none", "wrong-mean", "bool", "input-edit"])
def test_language_comparison_checks_original_observations(tmp_path, change):
    ctx = context(tmp_path, "project-language")
    result = {"count": 4, "mean_current_seconds": 12, "mean_candidate_seconds": 9, "saved_seconds": 3}
    if change == "wrong-mean":
        result["mean_candidate_seconds"] = 8
    elif change == "bool":
        result["saved_seconds"] = True
    elif change == "input-edit":
        path = ctx.outputs / "timings.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("one,10,7", "one,11,7"), encoding="utf-8")
    (ctx.outputs / "comparison.json").write_text(json.dumps(result), encoding="utf-8")
    assert checks.timing_comparison(ctx)[0] is (change == "none")


@pytest.mark.parametrize("change", ["none", "missing", "verified", "claimed", "invented-review", "policy-self"])
def test_pending_review_requires_evidence_and_unchanged_policy(tmp_path, change):
    ctx = context(tmp_path, "non-ml-replication")
    discovery = ("## D-A-001 — Paired difference\n- Evidence: replication.json, analyze.py\n"
                 "- Cross-check: PENDING\n- Reviews:\n")
    if change == "missing":
        discovery = ""
    elif change == "verified":
        discovery = discovery.replace("PENDING", "VERIFIED")
    elif change == "claimed":
        discovery = discovery.replace("PENDING", "REVIEWING local (A)")
    elif change == "invented-review":
        discovery += "  - local (A): CLOSED — reviewer subagent:fake@2026-10-25T10:00 — checked\n"
    elif change == "policy-self":
        path = ctx.outputs / "agents.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Verification: independent-review", "Verification: self"), encoding="utf-8")
    (ctx.outputs / "discoveries.md").write_text(discovery, encoding="utf-8")
    assert checks.review_pending(ctx)[0] is (change == "none")


@pytest.mark.parametrize("change", ["none", "missing", "wrong-id", "wrong-outcome", "wrong-item"])
def test_job_handoff_reports_the_monitored_job(tmp_path, change):
    ctx = context(tmp_path, "owned-job-monitor")
    (ctx.outputs / ".ro").mkdir()
    job = {"id": "J-A-0001", "slot": "A", "item": "H-A-01", "monitor": {"reason": "process exited with code 0"}}
    (ctx.outputs / ".ro" / "jobs.json").write_text(json.dumps([job]), encoding="utf-8")
    line = "- Job: J-A-0001; item H-A-01; outcome: process exited with code 0\n"
    if change == "missing":
        line = ""
    elif change == "wrong-id":
        line = line.replace("J-A-0001", "J-A-0002")
    elif change == "wrong-outcome":
        line = line.replace("code 0", "code 1")
    elif change == "wrong-item":
        line = line.replace("H-A-01", "H-A-02")
    (ctx.outputs / "handoff.md").write_text(line, encoding="utf-8")
    assert checks.job_handoff(ctx)[0] is (change == "none")
