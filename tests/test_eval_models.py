"""Model configuration passes through the harness without live Codex calls."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.evals import grade_evals as grade, run_evals as runner


@pytest.mark.parametrize("requested,cleanup_problem", [(None, False), ("explicit-model", True)])
def test_grader_uses_configured_model_and_records_resolved_model(tmp_path, monkeypatch, requested, cleanup_problem):
    monkeypatch.setattr(grade, "JUDGED_CHECKS", grade.JUDGED_CHECKS | {("example", "90-quality.md")})
    creator = tmp_path / "creator"
    (creator / "agents").mkdir(parents=True)
    (creator / "agents" / "grader.md").write_text("Grade the evidence.", encoding="utf-8")
    case = runner.Case(tmp_path / "case", "example", "Task", "Result", (
        runner.Assertion(Path("90-quality.md"), "Useful"),))
    run = tmp_path / "iteration-1" / case.name / "with_skill"
    (run / "outputs").mkdir(parents=True)
    (run / "transcript.md").write_text("trace", encoding="utf-8")
    runner.write_json(run / "run.json", {"returncode": 0, "error": None})
    runner.write_json(run / "timing.json", {"total_duration_seconds": 0})
    calls = []
    roots = []

    def execute(command, **kwargs):
        calls.append(command)
        if requested is None:
            assert "--model" not in command
        else:
            assert command[command.index("--model") + 1] == requested
        assert "--add-dir" not in command
        assert command[command.index("-s") + 1] == "read-only"
        assert "--ignore-user-config" in command and "features.plugins=false" in command
        assert "skills.include_instructions=false" in command
        roots.append(Path(kwargs["env"]["TMP"]).parent.parent)
        Path(command[command.index("-o") + 1]).write_text(json.dumps({"expectations": [
            {"text": "Useful", "passed": True, "evidence": "output: useful result"}]}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="{}\n", stderr="model: configured-model\n")

    monkeypatch.setattr(grade.subprocess, "run", execute)
    monkeypatch.setattr(grade, "resolve_codex", lambda value: value)
    monkeypatch.setattr(grade, "load_cases", lambda *args: [case])
    monkeypatch.setattr(grade, "configured_model_settings", lambda: {})
    original_cleanup = grade.cleanup

    def cleanup(root):
        problems = original_cleanup(root)
        return problems + (["simulated transient cleanup problem"] if cleanup_problem else [])

    monkeypatch.setattr(grade, "cleanup", cleanup)
    argv = ["--iteration", "1", "--workspace", str(tmp_path), "--skill-creator-dir", str(creator),
            "--configs", "with_skill"]
    if requested is not None:
        argv.extend(["--model", requested])
    assert grade.main(argv) == 0
    assert len(calls) == 1
    status = json.loads((run / "grading_status.json").read_text(encoding="utf-8"))
    assert status["requested_model"] == requested
    assert status["resolved_model"] == "configured-model"
    assert status["model"] == "configured-model"
    assert status["isolation"]["writable_roots"] == []
    assert status["isolation"]["fresh_codex_home"] is False
    assert status["isolation"]["fresh_user_home"] is False
    assert bool(status["cleanup_errors"]) == cleanup_problem
    assert status["error"] is None and all(not root.exists() for root in roots)
