"""Localized free text survives UTF-8 records, public commands, and installed hooks."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from conftest import (SCRIPTS, append_discovery, append_events, check, event, found, item,
                      make_project, set_queue, set_slot)
import ro_hook_runner as runner
import ro_records as records
from ro_state import Project


@pytest.fixture(params=[
    ("ko", "반복 측정으로 차이를 확인한다", "세 번의 결과가 일치했다", "같은 조건에서 다시 확인한다"),
    ("ja", "反復測定で差を確認する", "三回の結果が一致した", "同じ条件でもう一度確認する"),
], ids=["korean", "japanese"])
def localized_project(tmp_path, request):
    language, hypothesis, evidence, next_test = request.param
    target = make_project(tmp_path, "localized", "--preset", "solo-research", "--language", language,
                          "--platforms", "Claude Code", "--user", "operator", "--agents", "2")
    set_slot(target, "A", "Claude Code")
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8") + f"\n- {next_test}\n", encoding="utf-8", newline="\n")
    set_queue(target, item("H-A-01").replace("a claim", hypothesis).replace("a reason", evidence)
              .replace("a test", next_test))
    append_discovery(target,
                     "## D-A-001 — Repeat measurement\n- Source: A\n- Host: Claude Code\n"
                     "- User: operator\n- Date: 2026-10-24\n- Session: session:source@2026-10-24T10:00\n"
                     f"- Cross-check: PENDING\n- Finding: {evidence}\n- Evidence: {evidence}\n"
                     f"- Implication: {next_test}\n- Reviews:\n")
    append_events(target, event("2026-10-24 11:00", "A", "none", discovery="D-A-001")
                  .replace("worked on it", hypothesis).replace("progress\n", evidence + "\n"))
    project = Project(target, slot="A", session="language-test-session")
    project.register_slot()
    return project, language, hypothesis, evidence, next_test


def command(project, *arguments):
    return subprocess.run([sys.executable, str(SCRIPTS / "ro.py"), "--project", str(project.root),
                           "--session", project.session, *arguments], text=True, capture_output=True,
                          encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=15)


def test_checker_accepts_localized_values_with_english_structure(localized_project):
    project, language, hypothesis, evidence, next_test = localized_project
    assert project.settings()["language"] == language
    expected = {"agents.md": next_test, "plan.md": hypothesis,
                "discoveries.md": evidence, "handoff.md": hypothesis}
    for name, value in expected.items():
        data = (project.root / name).read_bytes()
        assert value.encode("utf-8") in data
        assert value in data.decode("utf-8")
    checker = check(project.root)
    assert not found(checker, "ERROR") and not found(checker, "WARN"), [i.render() for i in checker.issues]

    # Translating a required field still fails; localized values do not loosen the schema.
    plan = project.root / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Hypothesis:", "- 仮説:"),
                    encoding="utf-8", newline="\n")
    assert any(issue.field == "Hypothesis" for issue in found(check(project.root), "ERROR", "plan.field.missing"))


def test_ro_commands_preserve_and_return_localized_free_text(localized_project):
    project, language, hypothesis, evidence, next_test = localized_project
    for arguments, expected in [(("dupcheck", hypothesis), hypothesis), (("index", "D-A-001"), evidence),
                                (("claim", "H-A-01"), "H-A-01: A since"),
                                (("release", "H-A-01"), "H-A-01: none")]:
        result = command(project, *arguments)
        assert result.returncode == 0, result.stderr
        assert expected in result.stdout
    result = command(project, "observe", "Capacity", evidence, "--source", next_test, "--ttl", "6h")
    assert result.returncode == 0, result.stderr
    handoff = (project.root / "handoff.md").read_text(encoding="utf-8")
    assert f"- Capacity: {evidence} (Observed at " in handoff and f"source {next_test})" in handoff
    assert f"- Hypothesis: {hypothesis}" in (project.root / "plan.md").read_text(encoding="utf-8")
    result = command(project, "brief")
    assert result.returncode == 0, result.stderr
    assert f"language={language}" in result.stdout


def test_supervised_hooks_accept_utf8_payload_and_check_localized_records(localized_project):
    project, _, _, evidence, _ = localized_project
    payload = {"cwd": str(project.root), "session_id": project.session, "tool_name": "Write",
               "tool_input": {"file_path": "discoveries.md", "content": evidence}}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    response, code = runner.run("SessionStart", raw, project)
    assert code == 0 and "additionalContext" in response["hookSpecificOutput"]
    assert project.read_json("hooks-self-test.json")["status"] == "active"

    reserved = records.next_id(project, "D")
    addition = f"\n## {reserved} — Repeat measurement\n- Finding: {evidence}\n"
    with (project.root / "discoveries.md").open("a", encoding="utf-8", newline="\n") as output:
        output.write(addition)
    response, code = runner.run("PostToolUse", raw, project)
    assert code == 0 and response == {}
    assert reserved not in project.read_json("ids.json")
    assert reserved in project.read_json("records-hook.json")["discoveries.md"]["ids"]

    # A real duplicate is still detected after the localized record is read through the child process.
    with (project.root / "discoveries.md").open("a", encoding="utf-8", newline="\n") as output:
        output.write(addition)
    response, code = runner.run("PostToolUse", raw, project)
    assert code == 0 and "records.id" in json.dumps(response)
    assert project.read_json("records-hook.json")["discoveries.md"]["duplicate"] == [reserved]


def test_redirected_output_is_utf8_without_an_encoding_override(localized_project, monkeypatch):
    """Agents capture `ro` output through pipes; a locale code page must not garble it."""
    import io
    from ro_console import utf8_output

    project, language, hypothesis, evidence, next_test = localized_project
    for name in ("stdout", "stderr"):
        buffer = io.BytesIO()
        monkeypatch.setattr(sys, name, io.TextIOWrapper(buffer, encoding="cp1252", newline="\n"))
        monkeypatch.delenv("PYTHONIOENCODING", raising=False)
        utf8_output()
        stream = getattr(sys, name)
        stream.write(hypothesis + " — ok\n")
        stream.flush()
        assert buffer.getvalue().decode("utf-8") == hypothesis + " — ok\n"
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buffer, encoding="cp1252", newline="\n"))
    utf8_output()
    sys.stdout.write(hypothesis)
    sys.stdout.flush()
    assert buffer.getvalue() == hypothesis.encode("cp1252", errors="backslashreplace")

    # The installed shim runs `python -E -S ro.py`; its captured bytes are strict UTF-8.
    env = {key: value for key, value in os.environ.items() if key != "PYTHONIOENCODING"}
    for script, arguments in [("ro.py", ["--project", str(project.root), "--session", project.session,
                                         "dupcheck", hypothesis]),
                              ("check_project.py", [str(project.root)])]:
        result = subprocess.run([sys.executable, "-E", "-S", str(SCRIPTS / script), *arguments],
                                capture_output=True, env=env, timeout=15)
        assert result.returncode == 0, result.stderr
        text = result.stdout.decode("utf-8")
        assert "\\u" not in text
        if script == "ro.py":
            assert hypothesis in text
