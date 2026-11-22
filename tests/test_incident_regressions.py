"""Regression cases drawn from the 2026-11 enveda mistake log (docs/mistakes in that project).

Each test names the incident it reproduces so a later change can tell which failure it reopens.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ro_checks as checks
import ro_hooks as hooks
from ro_state import Project, atomic_text


def values(environment: str = "windows/bash", **extra) -> dict[str, str]:
    base = {"enforcement": "warn", "block": "none", "environment": environment,
            "external_actions": "none", "brief_requirements": "none", "autonomy": "present"}
    base.update(extra)
    return base


def found(command: str, dialect: str = "bash", environment: str = "windows/bash", root: Path | None = None) -> set[str]:
    call = checks.Call("shell", dialect, command)
    root = root or Path.cwd()
    return {finding.check for finding in checks.pre_checks(call, root, [], values(environment))}


# 2026-11-08 15:48 and 2026-11-09 13:48: Codex sent PowerShell's call operator without a shell field,
# so `& 'python.exe' ...` was read as Bash and denied as a background job.
@pytest.mark.parametrize("command", ["& 'C:/Python312/python.exe' ro.py index D-A-001",
                                     "cd x; & 'C:/Python312/python.exe' ro.py index D-A-001"])
def test_statement_leading_ampersand_is_not_a_background_job(command):
    assert "shell.background" not in found(command)


@pytest.mark.parametrize("command", ["sleep 1 &", "cd x && sleep 1 &", "sleep 1 & echo next"])
def test_trailing_ampersand_still_starts_a_background_job(command):
    assert "shell.background" in found(command)


def test_powershell_call_operator_stays_allowed():
    assert "shell.background" not in found("& 'C:/Python312/python.exe' ro.py index D-A-001", dialect="powershell")


# 2026-10-29 17:14, 2026-10-30 14:09/19:25, 2026-11-13 15:47: the Windows Bash tool collapsed \\ to \
# inside quotes and quoted heredocs; the hook receives the text before the collapse (probe 2026-11-22).
def test_windows_bash_double_backslash_warns():
    assert "shell.backslash" in found("printf '%s' 'a\\\\b'")
    assert "shell.backslash" in found("python - <<'EOF'\nprint('C:\\\\data')\nEOF")


def test_backslash_warning_is_windows_bash_only():
    assert "shell.backslash" not in found("printf '%s' 'a\\\\b'", environment="linux/bash")
    assert "shell.backslash" not in found("Write-Output 'a\\\\b'", dialect="powershell")
    assert "shell.backslash" not in found("printf '%s' 'a\\b'")


# 2026-11-10 01:44 (folder deleted without approval), 2026-11-11 18:00 (`rm -f st_*` removed other tasks' files),
# 2026-11-13 19:48 and 2026-11-14 21:09 (sub-agents deleted their failed outputs).
@pytest.mark.parametrize("command,dialect", [("rm -rf runs/old", "bash"), ("rm -f st_*", "bash"),
                                             ("rm -r -f runs/old", "bash"), ("rm --recursive runs/old", "bash"),
                                             ("Remove-Item -Recurse runs/old", "powershell"),
                                             ("Remove-Item runs/*.json", "powershell")])
def test_broad_delete_warns(command, dialect):
    assert "fs.delete" in found(command, dialect=dialect)


@pytest.mark.parametrize("command,dialect", [("rm runs/old/result.json", "bash"), ("rm -f a.txt b.txt", "bash"),
                                             ("Remove-Item runs/old/result.json", "powershell")])
def test_exact_delete_is_ordinary(command, dialect):
    assert "fs.delete" not in found(command, dialect=dialect)


# H-A-60 C1: reads with `2>/dev/null` near running jobs produced 7-14 identical warnings per call.
def test_null_device_redirect_is_not_a_project_write(tmp_path):
    jobs = [{"id": "J-A-0001", "status": "running", "run_dir": str(tmp_path)}]
    call = checks.Call("shell", "bash", "ls run 2>/dev/null > NUL")
    findings = checks.pre_checks(call, tmp_path / "work", jobs, values("linux/bash"))
    assert not any(finding.check == "jobs.mutate-bound" for finding in findings)


def project_at(root: Path) -> Project:
    root.mkdir(exist_ok=True)
    (root / "agents.md").write_text("# Work\n\n## Project settings\n- Enforcement: warn\n- Block: none\n"
                                    "- Environment: linux/bash\n", encoding="utf-8")
    return Project(root, slot="A", session="incident-test")


def edit_payload(path: str, old: str, new: str) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new}}


# T1/T3a: hand-written event headings carried guessed times; ledger entries failed only at execution.
def test_hand_written_event_heading_points_to_ro_event(tmp_path):
    project = project_at(tmp_path)
    (tmp_path / "handoff.md").write_text("# H\n", encoding="utf-8")
    payload = edit_payload(str(tmp_path / "handoff.md"), "# H\n",
                           "# H\n\n### 2026-11-10 05:26 — A — H-A-01\n- Action: x\n")
    context = hooks.hook(project, "PostToolUse", payload).get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "records.direct" in context and "ro event" in context


def test_hand_written_ledger_entry_points_to_external_check(tmp_path):
    project = project_at(tmp_path)
    (tmp_path / "handoff.md").write_text("## External actions\n", encoding="utf-8")
    payload = edit_payload(str(tmp_path / "handoff.md"), "## External actions\n",
                           "## External actions\n\n### X-A-001 — submit\n- Kind: submit\n")
    context = hooks.hook(project, "PostToolUse", payload).get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "ro external --check" in context


def test_editing_an_existing_event_body_is_quiet(tmp_path):
    call = checks.Call("Edit", paths=[str(tmp_path / "handoff.md")],
                       removed="### 2026-11-10 05:26 — A — H-A-01\n- Action: x",
                       added="### 2026-11-10 05:26 — A — H-A-01\n- Action: y")
    assert checks.record_hints(call) == []
    other = checks.Call("Edit", paths=[str(tmp_path / "notes.md")], added="### 2026-11-10 05:26 — A — x\n")
    assert checks.record_hints(other) == []


# Brief requirements: an omitted agent type is the default writing agent; surrounding spaces do not matter.
def test_brief_requirement_applies_to_default_agent_type(tmp_path):
    settings = values(brief_requirements="general-purpose: ro-delegate: v1")
    missing = checks.Call("Agent", prompt="do the task")
    present = checks.Call("Agent", prompt="  ro-delegate: v1  \ndo the task")
    explore = checks.Call("Agent", agent_type="Explore", prompt="look around")
    assert [f.check for f in checks.pre_checks(missing, tmp_path, [], settings)] == ["brief.requirements"]
    assert checks.pre_checks(present, tmp_path, [], settings) == []
    assert checks.pre_checks(explore, tmp_path, [], settings) == []


# 2026-11-11 14:50 and 2026-11-15 04:20: rewriting a record converted its line endings.
@pytest.mark.parametrize("original,expected", [(b"a\r\nb\r\n", b"a\r\nb\r\nc\r\n"), (b"a\nb\n", b"a\nb\nc\n")])
def test_atomic_text_keeps_the_existing_line_endings(tmp_path, original, expected):
    path = tmp_path / "plan.md"
    path.write_bytes(original)
    atomic_text(path, path.read_text(encoding="utf-8") + "c\n")
    assert path.read_bytes() == expected


def test_atomic_text_new_file_keeps_caller_text(tmp_path):
    path = tmp_path / "new.md"
    atomic_text(path, "a\nb\n")
    assert path.read_bytes() == b"a\nb\n"


def test_atomic_text_writes_newline_preserving_text_exactly(tmp_path):
    path = tmp_path / "handoff.md"
    path.write_bytes(b"a\r\nb\nc\r\n")
    with path.open(encoding="utf-8", newline="") as source:
        text = source.read()
    atomic_text(path, text.replace("b", "B"))
    assert path.read_bytes() == b"a\r\nB\nc\r\n"


# ---- records: archive live items, next-id glued tokens, launch with an unrelated malformed event ----

from conftest import append_events, check, event, item, set_queue, unified_project  # noqa: E402
import ro_archive  # noqa: E402
import ro_records as records  # noqa: E402
import ro_stages  # noqa: E402


def unified(tmp_path) -> Project:
    project = Project(unified_project(tmp_path), slot="A", session="incident-records")
    project.register_slot()
    return project


# H-A-60 A3 and 2026-11-08 14:17: an ID merely cited in a live item kept that finished item's events
# and its archived `removed` evidence produced event.item.lost.
def test_event_archive_treats_only_item_headings_as_live(tmp_path):
    project = unified(tmp_path)
    set_queue(project.root, item("H-A-02", extra=[("Evidence", "builds on H-A-01")]))
    append_events(project.root, event("2026-09-01 10:00", "A", "H-A-01"), event("2026-09-02 10:00", "A", "none"),
                  event("2026-10-02 10:00", "A", "none"))
    output = ro_archive.archive_events(project, before="2026-10-15")
    assert "### 2026-09-01 10:00 — A — H-A-01" not in (project.root / "handoff.md").read_text(encoding="utf-8")
    assert output.startswith("Archived")


# 2026-11-14 22:57: "X-A-313" written next to "0.488" read as X-A-3130 and next-id jumped.
def test_next_id_ignores_an_id_glued_to_a_decimal(tmp_path):
    project = unified(tmp_path)
    handoff = project.root / "handoff.md"
    handoff.write_text(handoff.read_text(encoding="utf-8") + "\nReview note: X-A-0010.488 beat X-A-009\n",
                       encoding="utf-8", newline="\n")
    assert records.next_id(project, "X") == "X-A-010"


# 2026-10-31 03:46 and 2026-11-08 17:09: two Job lines in one unrelated event refused every launch.
def test_launch_review_ignores_a_malformed_unrelated_event(tmp_path):
    project = unified(tmp_path)
    set_queue(project.root, item("H-A-01", stages="s1 pilot | s2 full"), item("H-A-05"))
    append_events(project.root, event("2026-09-01 10:00", "A", "H-A-05",
                                      extra="- Job: J-A-0001; item H-A-05; outcome: done\n"
                                            "- Job: J-A-0002; item H-A-05; outcome: done\n"))
    ro_stages.launch_review(project, "H-A-01/s1", None)  # no ValueError
    append_events(project.root, event("2026-09-02 10:00", "A", "H-A-01/s1",
                                      extra="- Job: J-A-0003; item H-A-01/s1; outcome: done\n"
                                            "- Job: J-A-0004; item H-A-01/s1; outcome: done\n"))
    with pytest.raises(ValueError, match="2026-09-02 10:00.*one `- Job:` line per event"):
        ro_stages.launch_review(project, "H-A-01/s2", None)


# ---- false positives found in review (Fable round 1) ----

def test_bundled_shell_inline_options_are_not_script_paths(tmp_path):
    import ro_jobs
    run = tmp_path / "run"
    run.mkdir()
    ro_jobs._check_script(tmp_path, run, ["bash", "-lc", "source env.sh && python train.py"], "linux")
    ro_jobs._check_script(tmp_path, run, ["sh", "-ec", "make all"], "linux")
    with pytest.raises(ValueError, match="does not exist"):
        ro_jobs._check_script(tmp_path, run, ["bash", "missing.sh"], "linux")


def test_powershell_rm_force_is_not_a_recursive_delete():
    assert "fs.delete" not in found("rm -Force a.txt", dialect="powershell")
    assert "fs.delete" not in found("rm -ErrorAction SilentlyContinue a.txt", dialect="powershell")
    assert "fs.delete" in found("rm -Recurse runs/old", dialect="powershell")


def test_codex_patch_adding_an_event_heading_gets_the_hint(tmp_path):
    patch = ("*** Begin Patch\n*** Update File: handoff.md\n@@\n ## Archived history\n"
             "+### 2026-11-10 05:26 — A — none\n+- Action: x\n*** End Patch\n")
    call = checks.adapt({"tool_name": "apply_patch", "tool_input": {"patch": patch}})
    assert call.paths == ["handoff.md"]
    assert [f.check for f in checks.record_hints(call)] == ["records.direct"]


def test_replacing_one_event_heading_with_another_still_gets_the_hint(tmp_path):
    call = checks.Call("Edit", paths=[str(tmp_path / "handoff.md")],
                       removed="### 2026-11-10 05:26 — A — none\n", added="### 2026-11-10 05:31 — A — none\n")
    assert [f.check for f in checks.record_hints(call)] == ["records.direct"]
    fenced = checks.Call("Edit", paths=[str(tmp_path / "handoff.md")],
                         added="```markdown\n### YYYY-MM-DD HH:MM — A — H-A-01\n```\n".replace("YYYY-MM-DD HH:MM", "2026-11-10 05:26"))
    assert checks.record_hints(fenced) == []
