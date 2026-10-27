"""Measurement claims require a harness observation, and byte promises stay exact."""

import json
from pathlib import Path
import shutil
import sys

import pytest

from conftest import SKILL
from scripts.evals import checks
from scripts.evals.evidence import EvidenceBroker


CASE = "posttool-unchanged-fast-path"


def context(tmp_path, case=CASE):
    source = SKILL / "evals" / case
    shutil.copytree(source / "files", tmp_path / "outputs")
    return checks.CheckContext(source, tmp_path, SKILL, sys.executable)


def measurement_verdicts(ctx):
    return [checks.SCRIPTED_CHECKS[CASE, path.name](ctx)[0]
            for path in sorted((ctx.case_dir / "graders").glob("*.md"))]


def test_plausible_measurement_json_without_execution_fails_every_assertion(tmp_path):
    ctx = context(tmp_path)
    plausible = {"unchanged": [{"coordination_body_reads": 0, "child_launches": 0,
                                "exit_code": 0, "reply": {}}] * 2,
                 "changed_record": {"systemMessage": "records.id: duplicate heading"},
                 "pending_warning": {"systemMessage": "pending operational warning"}}
    (ctx.outputs / "posttool-results.json").write_text(json.dumps(plausible), encoding="utf-8")
    assert measurement_verdicts(ctx) == [False] * 4
    # An agent-written receipt in its own tree cannot impersonate the broker log.
    (ctx.outputs / "evidence.jsonl").write_text(json.dumps({"returncode": 0, "error": None}), encoding="utf-8")
    assert measurement_verdicts(ctx) == [False] * 4


def test_canonical_measurement_capture_passes_and_tampering_fails(tmp_path, monkeypatch):
    ctx = context(tmp_path)
    request = "a" * 32
    from scripts.evals import evidence
    run = evidence.subprocess.run

    def isolated_run(*args, **kwargs):
        assert all(name not in kwargs["env"] for name in
                   ("CLAUDECODE", "CLAUDE_PROJECT_DIR", "CODEX_HOME", "RO_HOOK_PYTHON"))
        return run(*args, **kwargs)

    for name in ("CLAUDECODE", "CLAUDE_PROJECT_DIR", "CODEX_HOME", "RO_HOOK_PYTHON"):
        monkeypatch.setenv(name, "unrelated-host-override")
    monkeypatch.setattr(evidence.subprocess, "run", isolated_run)
    with EvidenceBroker(ctx.case_dir, ctx.outputs, ctx.run_dir, Path(sys.executable), SKILL) as broker:
        broker._execute(request, {"helper": "measure_posttool.py", "mode": "request"})
    (ctx.run_dir / "run.json").write_text(json.dumps({"evidence": broker.metadata}), encoding="utf-8")
    record = json.loads((ctx.run_dir / "evidence.jsonl").read_text(encoding="utf-8"))
    assert record["returncode"] == 0, record
    capture = ctx.run_dir / "evidence" / request
    for name in record["artifacts"]:
        target = ctx.outputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((capture / name).read_bytes())
    assert measurement_verdicts(ctx) == [True] * 4
    assert [row["reply"] for row in ctx.data("posttool-results.json")["unchanged"]] == [{}, {}]
    result_file = ctx.outputs / "posttool-results.json"
    original = result_file.read_bytes()
    result_file.write_bytes(original.replace(b'"child_launches": 0', b'"child_launches": 9', 1))
    assert measurement_verdicts(ctx) == [False] * 4
    result_file.write_bytes(original)
    log = ctx.run_dir / "evidence.jsonl"
    for identity in ("runtime_sha256", "collector_sha256"):
        log.write_text(json.dumps({**record, identity: "0" * 64}) + "\n", encoding="utf-8")
        assert measurement_verdicts(ctx) == [False] * 4
    log.write_text(json.dumps(record) + "\n", encoding="utf-8")
    (ctx.run_dir / "helper-executions.jsonl").write_text("", encoding="utf-8")
    assert measurement_verdicts(ctx) == [False] * 4


@pytest.mark.parametrize("problem", ["modified-helper", "missing-runtime"])
def test_broker_refuses_untrusted_measurement_inputs(tmp_path, problem):
    ctx = context(tmp_path)
    if problem == "modified-helper":
        (ctx.outputs / "measure_posttool.py").write_text("print('fabricated')\n", encoding="utf-8")
    runtime = None if problem == "missing-runtime" else SKILL
    with EvidenceBroker(ctx.case_dir, ctx.outputs, ctx.run_dir, Path(sys.executable), runtime) as broker:
        broker._execute("a" * 32, {"helper": "measure_posttool.py", "mode": "request"})
    record = json.loads((ctx.run_dir / "evidence.jsonl").read_text(encoding="utf-8"))
    assert record["returncode"] is None and record["error"] and not record["artifacts"]
    assert measurement_verdicts(ctx) == [False] * 4


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_brief_preservation_rejects_line_ending_only_mutation(tmp_path, newline):
    case = tmp_path / "work-project-start"
    (case / "files").mkdir(parents=True)
    (tmp_path / "outputs").mkdir()
    source = b"# Agreed scope" + newline + b"Keep source identifiers." + newline
    (case / "files" / "brief.md").write_bytes(source)
    output = tmp_path / "outputs" / "brief.md"
    output.write_bytes(source)
    ctx = checks.CheckContext(case, tmp_path, SKILL, sys.executable)
    assert checks.brief_preserved(ctx)[0]
    output.write_bytes(source.replace(b"\r\n", b"\n") if newline == b"\r\n"
                       else source.replace(b"\n", b"\r\n"))
    assert ctx.unchanged("brief.md")  # Source identity checks intentionally remain checkout-independent.
    assert not checks.brief_preserved(ctx)[0]


def test_active_history_checks_ignore_live_edits_but_reject_archive_changes(tmp_path):
    ctx = context(tmp_path, "active-record-history")
    target = ctx.outputs / "archive-project"
    target.mkdir()
    for name in ("plan.md", "handoff.md"):
        shutil.copyfile(ctx.case_dir / "files" / name, target / name)
    (ctx.outputs / "brief.txt").write_text("Slot A: taken; claims 1\nClaim H-A-02: 2026-10-25 09:00\n",
                                           encoding="utf-8")
    (ctx.outputs / "close.txt").write_text("Released claims: H-A-02\nSlot A: released\nOpen claims: none\n",
                                           encoding="utf-8")
    predicates = [checks.SCRIPTED_CHECKS[ctx.case_dir.name, name] for name in
                  ("03-live-brief.md", "04-close-live-only.md", "05-history-byte-preservation.md")]
    assert all(predicate(ctx)[0] for predicate in predicates)
    plan = target / "plan.md"
    original = plan.read_bytes()
    plan.write_bytes(original.replace(b"- Claimed: none", b"- Claimed: A since 2026-10-25 09:00"))
    assert predicates[-1](ctx)[0]
    plan.write_bytes(original.replace(b"\n", b"\r\n"))
    assert not predicates[-1](ctx)[0]
