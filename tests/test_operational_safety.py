"""One-to-one anonymised source-log replay; measured recall excludes judgement aspects."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

from conftest import FIXTURES, SKILL, with_real_ps
import ro_checks as checks
import ro_evidence as evidence
import ro_hooks as hooks
import ro_jobs as jobs
import ro_records as records
from ro_state import Project, process_start


CORPUS_ROOT = FIXTURES / "operational-safety"
ENTRIES = json.loads((CORPUS_ROOT / "mistake-patterns.json").read_text(encoding="utf-8"))
DETERMINISTIC = [entry for entry in ENTRIES if entry["classification"] == "deterministic"]
JUDGEMENT = [entry for entry in ENTRIES if entry["classification"] == "judgement"]
OUT_OF_SCOPE = [entry for entry in ENTRIES if entry["classification"] == "out-of-scope"]
CASES = [(entry["source_entry"], case) for entry in DETERMINISTIC for case in entry["cases"]]
REMOVED_CASES = [(entry["source_entry"], case) for entry in ENTRIES
                 for case in entry.get("out_of_scope_cases", [])]
BENIGN = {shell: json.loads((CORPUS_ROOT / f"benign-{shell}.json").read_text(encoding="utf-8"))
          for shell in ("bash", "powershell")}
CHECKS = "shell.background,shell.heredoc,jobs.mutate-bound,publish.scan,external.gate"


def project_at(root: Path, shell: str = "bash") -> Project:
    environment = f"{'windows' if os.name == 'nt' else 'linux'}/{shell}"
    (root / "agents.md").write_text("# Agent rules\n\n## Project settings\n"
                                    f"- Enforcement: block\n- Block: {CHECKS}\n"
                                    f"- Environment: {environment}\n"
                                    "- External actions: literal:release-tool publish\n",
                                    encoding="utf-8")
    (root / "handoff.md").write_text("# Handoff\n\n## Shared state\n\n"
                                     "## External actions\n\n## Archived history\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "worker-a.sh").write_text("worker-a\n", encoding="utf-8")
    (root / "runs" / "job-a").mkdir(parents=True)
    (root / "runs" / "job-a" / "input.txt").write_text("input\n", encoding="utf-8")
    # These replays inspect an already selected owner's jobs and observations.
    return Project(root, slot="A", session="author-session")


def live_job(project: Project) -> dict:
    entry = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "pid": os.getpid(),
             "start": process_start(os.getpid()), "status": "running", "monitor": None,
             "run_dir": str(project.root / "runs" / "job-a"),
             "bound": [str(project.root / "runs" / "job-a"), str(project.root / "scripts" / "worker-a.sh")],
             "started": time.time(), "expect": 60, "errors": []}
    project.write_json("jobs.json", [entry])
    return entry


def assert_hook_check(response: dict, check: str) -> None:
    # A concrete caught finding must be communicated to the caller, not just logged.
    assert check in json.dumps(response), response
    assert (response.get("decision") == "block" or
            response.get("hookSpecificOutput", {}).get("permissionDecision") == "deny" or
            response.get("systemMessage") or
            response.get("hookSpecificOutput", {}).get("additionalContext")), response


def prepared_action(project: Project, artifact: str) -> None:
    digest = evidence.hash_artifact(project, artifact)["sha256"]
    before = (dt.datetime.now() - dt.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
    path = project.root / "handoff.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("## External actions\n", "## External actions\n\n### X-A-001 delivery\n"
                        f"- Candidate: {artifact}, hash {digest}\n- Destination: endpoint-a\n"
                        f"- Expected: successful delivery (written {before})\n- Status: prepared\n")
    path.write_text(text, encoding="utf-8")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def report_metric(request, message: str) -> None:
    reporter = request.config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(message)


def test_real_log_corpus_has_exact_source_coverage_and_explicit_limits():
    assert [entry["source_entry"] for entry in ENTRIES] == list(range(1, 29))
    assert (len(DETERMINISTIC), len(JUDGEMENT), len(OUT_OF_SCOPE), len(CASES)) == (16, 10, 2, 23)
    assert len({entry["name"] for entry in ENTRIES}) == 28
    assert len({case["name"] for _, case in CASES}) == 23
    assert {number for number, _ in REMOVED_CASES} == {4, 6, 26}
    for entry in DETERMINISTIC:
        assert entry["deterministic_aspects"] and entry["judgement_aspects"] and entry["cases"]
    raw = (CORPUS_ROOT / "mistake-patterns.json").read_text(encoding="utf-8")
    assert not re.search(r"https?://|[A-Za-z]:[/\\]|/home/|/Users/|\\\\", raw)
    readme = (CORPUS_ROOT / "README.md").read_text(encoding="utf-8")
    assert re.search(r"anonymised.*mistake log", readme)
    for entry in JUDGEMENT:
        assert entry["cases"] == [] and entry["reason"], entry["source_entry"]


@pytest.mark.parametrize("shell", ["bash", "powershell"])
@pytest.mark.parametrize("bindings", ["none", "run-directory", "bound-file"])
def test_benign_shell_corpus(tmp_path, request, shell, bindings):
    project = project_at(tmp_path, shell)
    entries = [] if bindings == "none" else [live_job(project)]
    if entries and bindings == "bound-file":
        entries[0]["bound"] = [str(project.root / "runs" / "job-a" / "input.txt")]
    values = project.settings()
    blocks, warnings = [], []
    corpus = BENIGN[shell]
    assert len(corpus) >= 300
    assert len({case["name"] for case in corpus}) == len(corpus)
    assert {case["dialect"] for case in corpus} == {shell}
    for case in corpus:
        findings = checks.pre_checks(checks.Call("shell", shell, case["command"]), tmp_path, entries, values)
        levels = [checks.outcome(finding, values) for finding in findings]
        if "block" in levels:
            blocks.append(case["name"])
        elif "warn" in levels:
            warnings.append(case["name"])
    summary = (f"Benign {shell} ({bindings}): block false positives {len(blocks)}/{len(corpus)} "
               f"({len(blocks) / len(corpus):.1%}); warnings {len(warnings)}/{len(corpus)} "
               f"({len(warnings) / len(corpus):.1%})")
    report_metric(request, summary)
    assert not blocks and len(warnings) / len(corpus) <= .02, f"{summary}; blocked IDs={blocks}; warned IDs={warnings}"


LIMIT_CASES = json.loads((CORPUS_ROOT / "out-of-scope-commands.json").read_text(encoding="utf-8"))
TOOL_DIALECT_CASES = json.loads((CORPUS_ROOT / "tool-dialect-commands.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", TOOL_DIALECT_CASES, ids=lambda case: case["name"])
def test_known_tool_dialect_is_checked_even_when_project_declares_another(tmp_path, case):
    project = project_at(tmp_path, case["declared_shell"])
    live_job(project)
    # Hosts report the physical cwd; live_job binds under the resolved project root.
    result = hooks.hook(project, "PreToolUse", {
        "cwd": str(project.root), "tool_name": "Bash" if case["dialect"] == "bash" else "PowerShell",
        "tool_input": {"command": case["command"]}})
    assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    assert "shell.background" in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "jobs.mutate-bound" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_out_of_scope_commands_and_removed_source_subcases_do_not_block(tmp_path, request):
    document = (SKILL / "references" / "hooks.md").read_text(encoding="utf-8")
    exclusions = document.split("## Shell certainty\n", 1)[1].split("\n## ", 1)[0]
    for construct in ("junction resolution", "here-strings", "Nested interpreter bodies", "script blocks"):
        assert construct in exclusions, construct
    excluded = [*LIMIT_CASES, *[{**case, "name": f"source-{number:02d}-{case['name']}",
                               "dialect": "bash" if case["tool"] == "Bash" else "powershell"}
                              for number, case in REMOVED_CASES]]
    blocked = []
    for index, case in enumerate(excluded):
        root = tmp_path / str(index)
        root.mkdir()
        project = project_at(root, case.get("declared_shell", case["dialect"]))
        live_job(project)
        result = hooks.hook(project, "PreToolUse", {
            "tool_name": "Bash" if case["dialect"] == "bash" else "PowerShell",
            "tool_input": {"command": case["command"]}})
        if (result.get("decision") == "block" or
                result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"):
            blocked.append(case["name"])
        assert "jobs.kill-broad" not in json.dumps(result), case["name"]
    assert all(case["reason"] for case in LIMIT_CASES)
    summary = f"Out-of-scope false positives: {len(blocked)}/{len(excluded)} ({len(blocked) / len(excluded):.1%})"
    report_metric(request, summary)
    assert not blocked, f"{summary}; blocked IDs={blocked}"


def replay_deterministic_case(tmp_path, monkeypatch, case):
    project = project_at(tmp_path)
    method = case["method"]
    if method == "pre":
        if case["check"] == "jobs.read-bound":
            with (project.root / "agents.md").open("a", encoding="utf-8") as stream:
                stream.write("- Read bound: on\n")  # This advisory check is now opt-in.
        live_job(project)
        tool_input = {"command": case.get("command", "")}
        if case.get("path"):
            tool_input["file_path"] = case["path"]
        result = hooks.hook(project, "PreToolUse", {"tool_name": case["tool"], "tool_input": tool_input})
        assert_hook_check(result, case["check"])
        return "uncertain parse" in json.dumps(result)
    elif method == "unmonitored":
        live_job(project)
        assert_hook_check(hooks.hook(project, "Stop", {"turn_id": "turn-a"}), case["check"])
    elif method == "kill_identity":
        entry = live_job(project)
        entry["start"] = "different-creation-identity"
        project.write_json("jobs.json", [entry])
        attempted = []
        monkeypatch.setattr(jobs.subprocess, "run", with_real_ps(lambda *args, **kwargs: attempted.append(args)))
        with pytest.raises(ValueError):
            jobs.kill(project, entry["id"])
        assert attempted == []
    elif method == "failed_launch":
        (tmp_path / "plan.md").write_text("## Agent: A\n### H-A-01\n- Goal: run the bounded test worker\n", encoding="utf-8")
        handoff = tmp_path / "handoff.md"
        handoff.write_text(handoff.read_text(encoding="utf-8").replace("## Archived history\n",
                          "## Active handoff\n\n### Agent: A\n- Current host: codex\n- Current user: test-user\n\n## Archived history\n"),
                          encoding="utf-8")
        options = argparse.Namespace(item="H-A-01", expect="10s", confirm="0s",
                                     command=[str(tmp_path / "missing-worker-a.exe")])
        try:
            result = jobs.launch(project, options)
            entry = project.read_json("jobs.json")[-1]
            assert entry["id"] in result and not entry["confirmed"]
            assert entry["id"] not in (tmp_path / "handoff.md").read_text(encoding="utf-8")
            assert not entry.get("child_started")
        finally:
            # Only entries created by this test's launch may reach the kill wrapper.
            for entry in project.read_json("jobs.json", []):
                if jobs.running_job(entry):
                    jobs.kill(project, entry["id"])
    elif method == "duplicate_id":
        path = tmp_path / "discoveries.md"
        path.write_text("## D-A-001 first finding\n", encoding="utf-8")
        payload = {"tool_name": "Write", "tool_input": {"file_path": "discoveries.md"}}
        hooks.hook(project, "PostToolUse", payload)
        path.write_text("## D-A-001 first finding\n## D-A-001 second finding\n", encoding="utf-8")
        assert_hook_check(hooks.hook(project, "PostToolUse", payload), case["check"])
    elif method == "next_id":
        (tmp_path / "discoveries.md").write_text("## D-A-003 existing finding\n", encoding="utf-8")
        assert records.next_id(project, "D") == "D-A-004"
        assert records.next_id(project, "D") == "D-A-005"
    elif method == "overrun":
        entry = live_job(project)
        entry.update(started=time.time() - 31, expect=10)
        project.write_json("jobs.json", [entry])
        result = jobs.monitor(project, entry["id"])
        stopped = project.read_json("jobs.json")[0]
        assert stopped["outcome"] and stopped["outcome"] in result
        assert not jobs.live_monitor(stopped)
    elif method == "failed_receipt":
        (tmp_path / "artifact.txt").write_text("reviewed bytes", encoding="utf-8")
        prepared_action(project, "artifact.txt")
        for verdict in ("PASS", "FAIL"):
            evidence.receipt_add(project, "artifact.txt", "reviewer-session", verdict, "X-A-001", "endpoint-a")
        executions = []
        monkeypatch.setattr(evidence.subprocess, "run", with_real_ps(lambda *args, **kwargs: executions.append(args)))
        args = argparse.Namespace(artifact="artifact.txt", action="X-A-001", command=["release-tool", "publish"])
        with pytest.raises(ValueError):
            evidence.external(project, args)
        assert executions == []
        assert "Status: prepared" in (tmp_path / "handoff.md").read_text(encoding="utf-8")
    elif method == "stale_observation":
        path = tmp_path / "handoff.md"
        text = path.read_text(encoding="utf-8").replace("## Shared state\n", "## Shared state\n"
                   "- Budget: 1 (Observed at 2000-01-01 00:00; TTL 1h; source counter-a)\n")
        path.write_text(text, encoding="utf-8")
        result = hooks.hook(project, "SessionStart", {})
        assert "2000-01-01 00:00" in json.dumps(result) and "1h" in json.dumps(result)
    elif method == "publish_history":
        assert shutil.which("git"), "git is required for authoritative corpus replay"
        git(tmp_path, "init", "--initial-branch=main")
        git(tmp_path, "config", "user.name", "fixture")
        git(tmp_path, "config", "user.email", "fixture@example.invalid")
        path = tmp_path / "content.txt"

        def commit(text):
            path.write_text(text, encoding="utf-8")
            git(tmp_path, "add", "content.txt")
            git(tmp_path, "commit", "-m", "change")
            return git(tmp_path, "rev-parse", "HEAD")

        agents = tmp_path / "agents.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "- Publish scan: literal:restricted-marker-a\n",
                          encoding="utf-8")
        baseline = commit("SHA256" + "ab12" * 16 + " ordinary-checksum\n")
        clean_refs = f"refs/heads/main {baseline} refs/heads/main {'0' * 40}\n"
        assert evidence.scan_publish(project, clean_refs) == []
        forbidden = commit("restricted-marker-a\n")
        tip = commit("clean again\n")
        outgoing = f"refs/heads/main {tip} refs/heads/main {baseline}\n"
        findings = evidence.scan_publish(project, outgoing)
        assert any(forbidden[:12] in finding for finding in findings)
        assert all("redacted" in finding for finding in findings)
        assert "restricted-marker-a" not in "\n".join(findings)
    elif method == "required_brief":
        path = tmp_path / "agents.md"
        path.write_text(path.read_text(encoding="utf-8") +
                        "- Brief requirements: reviewer:Report every required view or its written exclusion.\n",
                        encoding="utf-8")
        missing = {"tool_name": "Agent", "tool_input": {"subagent_type": "reviewer", "prompt": "Review artifact-a."}}
        assert_hook_check(hooks.hook(project, "PreToolUse", missing), case["check"])
        missing["tool_input"]["prompt"] += "\nReport every required view or its written exclusion."
        assert case["check"] not in json.dumps(hooks.hook(project, "PreToolUse", missing))
    else:
        pytest.fail(f"Unimplemented corpus method: {method}")


def test_real_log_deterministic_recall(tmp_path, monkeypatch, request):
    failures, passed, uncertain = [], set(), []
    for number, case in CASES:
        case_id = (number, case["name"])
        root = tmp_path / case["name"]
        root.mkdir()
        try:
            with monkeypatch.context() as isolated:
                if replay_deterministic_case(root, isolated, case):
                    uncertain.append(case["name"])
        except (Exception, pytest.fail.Exception) as error:
            failures.append(f"source-{number:02d}-{case['name']}: {type(error).__name__}: {error}")
        else:
            passed.add(case_id)
    covered = sum(all((entry["source_entry"], case["name"]) in passed for case in entry["cases"])
                  for entry in DETERMINISTIC)
    summary = (f"Operational-safety recall: {len(passed)}/{len(CASES)} deterministic subcases "
               f"({len(passed) / len(CASES):.0%}); {covered}/{len(DETERMINISTIC)} source entries; "
               f"{len(JUDGEMENT)} judgement entries and {len(REMOVED_CASES)} removed subcases excluded")
    report_metric(request, summary)
    report_metric(request, f"In-scope uncertain parses: {len(uncertain)}/{len(CASES)}; " + ", ".join(uncertain))
    assert not failures and len(passed) == 23 and covered == 16, f"{summary}; failing IDs:\n" + "\n".join(failures)
