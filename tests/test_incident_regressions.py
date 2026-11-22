"""Regression cases drawn from the 2026-11 enveda mistake log (docs/mistakes in that project).

Each test names the incident it reproduces so a later change can tell which failure it reopens.
"""

from __future__ import annotations

import json
import os
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


@pytest.mark.parametrize("command,dialect,expected", [
    ("rm 'reports here'/*.txt", "bash", True), ("rm 'literal*name'", "bash", False), ("rm \"a*b\"", "bash", False),
    ("rm a\\*b", "bash", False), ("Remove-Item -Path 'report-*.txt'", "powershell", True),
    ("Remove-Item 'report-*.txt'", "powershell", True), ("Remove-Item -LiteralPath 'report-*.txt'", "powershell", False),
])
def test_wildcards_follow_each_shells_quoting(command, dialect, expected):
    """astra round 6: a quoted path part hid a real pattern; PowerShell -Path expands quoted patterns."""
    assert ("fs.delete" in found(command, dialect=dialect)) is expected


@pytest.mark.parametrize("command,dialect,expected", [
    ("rm '-r' old", "bash", True), ("rm '--' -*.txt", "bash", True), ("rm -- -r", "bash", False),
    ("rm file[12].txt", "bash", True), ("rm 'file[12].txt'", "bash", False),
    ("Remove-Item -Path:report-*.txt", "powershell", True), ("Remove-Item old -Recurse:$true", "powershell", True),
    ("Remove-Item old -Recurse:$false", "powershell", False), ("Remove-Item -LiteralPath:'a*b'", "powershell", False),
    ("Remove-Item 'data[1].csv'", "powershell", True), ("Remove-Item -Force a.txt", "powershell", False),
])
def test_delete_check_reads_each_shells_syntax(command, dialect, expected):
    """astra round 7: quoted Bash options, PowerShell -Name:value arguments and [..] patterns were missed."""
    assert ("fs.delete" in found(command, dialect=dialect)) is expected


@pytest.mark.parametrize("command,expected", [
    ("Remove-Item -Path:report-*.txt", "block"), ("Remove-Item old -Recurse:$true", "block"),
    ("Remove-Item -Path 'report-*.txt'", "block"), ("Remove-Item a.txt -Exclude '*.bak'", None),
    ("Remove-Item 'data`[1`].csv'", None), ("Remove-Item -Path:a.txt", None),
    ("Remove-Item -Path:report-*.txt -WhatIf:$false", "block"),  # astra round 9: a real run, still blocked
    ("Remove-Item -Path:report-*.txt -WhatIf", None),            # a dry run deletes nothing
    ("Remove-Item -Path:report-*.txt -WhatIf:00", "block"),      # astra round 10: 00 is false too
    ("Remove-Item -Path:report-*.txt -WhatIf:1", None),
    ("Remove-Item -Path:report-*.txt -WhatIf:$x", "warn"),       # unknown: never skipped, but uncertain
    ("Remove-Item old -Recurse:$null", "block"),                 # astra round 11: $null binds as present
    ("Remove-Item old -Recurse:$false", None),
])
def test_powershell_colon_arguments_keep_a_configured_block(command, expected):
    """astra round 8: `-Name:value` made the parse uncertain, which turned the block into a warning."""
    settings = values("windows/powershell", enforcement="block", block="fs.delete")
    findings = [f for f in checks.pre_checks(checks.Call("shell", "powershell", command), Path.cwd(), [], settings)
                if f.check == "fs.delete"]
    assert (checks.outcome(findings[0], settings) if findings else None) == expected


@pytest.mark.parametrize("command,dialect", [("rm runs/old/result.json", "bash"), ("rm -f a.txt b.txt", "bash"),
                                             ("Remove-Item runs/old/result.json", "powershell")])
def test_exact_delete_is_ordinary(command, dialect):
    assert "fs.delete" not in found(command, dialect=dialect)


# H-A-60 C1: reads with `2>/dev/null` near running jobs produced 7-14 identical warnings per call.
def test_null_device_redirect_is_not_a_project_write(tmp_path):
    jobs = [{"id": "J-A-0001", "status": "running", "run_dir": str(tmp_path)}]
    for dialect, command in (("bash", "ls run 2>/dev/null"), ("powershell", "ls run 2> NUL")):
        findings = checks.pre_checks(checks.Call("shell", dialect, command), tmp_path / "work", jobs,
                                     values(f"windows/{dialect}"))
        assert not any(finding.check == "jobs.mutate-bound" for finding in findings), command


def test_nul_is_an_ordinary_file_in_bash():
    """astra review 2026-11-22: on Linux `> NUL` writes a file named NUL, e.g. into a job's folder.
    Round 5: Git Bash on Windows does the same (the stray `nul` files), and `/DEV/NULL` is a path there."""
    bash = lambda command, family: checks.redirections(checks.tokens(command, "bash").parts, os_family=family,
                                                       shell="bash")[1]
    for family in ("linux", "windows"):
        assert bash("ls > NUL 2>/dev/null", family) == ["NUL"] and bash("ls > nul:", family) == ["nul:"]
        assert bash("ls > /DEV/NULL", family) == ["/DEV/NULL"] and bash("ls > /dev/null", family) == []
    # Round 2: a quoted '$null' names a file.
    writes = lambda command, family: checks.redirections(checks.tokens(command, "bash").parts, os_family=family)[1]
    assert writes("ls > '$null'", "linux") == ["$null"]
    # Round 3: unquoted `$null` is the null device only in PowerShell; in Bash it expands a variable.
    redirect = lambda command, shell: checks.redirections(checks.tokens(command, shell).parts, os_family="linux",
                                                          shell=shell)[1]
    assert redirect("ls > $null", "powershell") == [] and redirect("ls > $null", "bash") == ["$null"]
    # Round 4: native Windows PowerShell knows only NUL; /dev/null there is a path under the drive root.
    on_windows = lambda command, shell: checks.redirections(checks.tokens(command, shell).parts, os_family="windows",
                                                            shell=shell)[1]
    assert on_windows("ls > /dev/null", "powershell") == ["/dev/null"] and on_windows("ls > NUL", "powershell") == []
    assert on_windows("ls > nul:", "powershell") == [] and redirect("ls > /dev/null", "powershell") == []


def test_patch_hint_is_judged_per_file():
    """astra review round 2: added and removed lines of different files were mixed."""
    moved_in = ("*** Begin Patch\n*** Update File: notes.md\n@@\n-### 2026-11-10 05:26 — A — none\n"
                "*** Update File: handoff.md\n@@\n+### 2026-11-10 05:26 — A — none\n*** End Patch\n")
    moved_out = ("*** Begin Patch\n*** Update File: handoff.md\n@@\n-### 2026-11-10 05:26 — A — none\n"
                 "*** Update File: notes.md\n@@\n+### 2026-11-10 05:26 — A — none\n*** End Patch\n")
    hints = lambda patch: [f.check for f in checks.record_hints(checks.adapt({"tool_name": "apply_patch",
                                                                             "tool_input": {"patch": patch}}))]
    assert hints(moved_in) == ["records.direct"] and hints(moved_out) == []
    # Round 3: two handoff.md files are two files; Windows names ignore case.
    two_paths = ("*** Begin Patch\n*** Update File: docs/handoff.md\n@@\n-### 2026-11-10 05:26 — A — none\n"
                 "*** Update File: handoff.md\n@@\n+### 2026-11-10 05:26 — A — none\n*** End Patch\n")
    assert hints(two_paths) == ["records.direct"]
    upper = moved_in.replace("Update File: handoff.md", "Update File: HANDOFF.md")
    assert hints(upper) == (["records.direct"] if os.name == "nt" else [])


def test_only_the_projects_own_handoff_gets_the_hint(tmp_path):
    """astra review round 4: editing archive/handoff.md pointed at `ro event` although no record changed."""
    family = "windows" if os.name == "nt" else "linux"
    heading = "### 2026-11-10 05:26 — A — none\n"
    hint = lambda path, cwd: [f.check for f in checks.record_hints(checks.Call("Edit", paths=[path], added=heading),
                                                                    tmp_path, str(cwd), family)]
    (tmp_path / "archive").mkdir()
    assert hint(str(tmp_path / "archive" / "handoff.md"), tmp_path) == []
    assert hint("handoff.md", tmp_path / "archive") == []
    assert hint("handoff.md", tmp_path) == ["records.direct"]
    assert hint("../handoff.md", tmp_path / "archive") == ["records.direct"]
    assert hint(str(tmp_path / "handoff.md"), tmp_path / "archive") == ["records.direct"]
    # Round 5: host paths are literal; `[2026]` is part of a folder name, not a glob.
    (tmp_path / "archive[2026]").mkdir()
    assert hint("handoff.md", tmp_path / "archive[2026]") == []
    assert hint("../handoff.md", tmp_path / "archive[2026]") == ["records.direct"]


def test_relative_tool_workdir_starts_from_the_host_cwd(tmp_path):
    """astra round 6: a relative workdir was joined to the project root, so the real handoff was missed."""
    project = project_at(tmp_path)
    (tmp_path / "handoff.md").write_text("# H\n", encoding="utf-8")
    (tmp_path / "other" / "sub").mkdir(parents=True)
    patch = ("*** Begin Patch\n*** Update File: ../../handoff.md\n@@\n+### 2026-11-10 05:26 — A — none\n"
             "*** End Patch\n")
    payload = {"tool_name": "apply_patch", "tool_input": {"patch": patch, "workdir": "sub"},
               "cwd": str(tmp_path / "other")}
    context = hooks.hook(project, "PostToolUse", payload).get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "ro event" in context


def test_guard_start_date_ignores_a_second_written_stamp():
    """astra review round 3: an older second stamp dated an entry before the guards' start."""
    from types import SimpleNamespace
    import check_project
    block = lambda expected: SimpleNamespace(fields={"Expected": expected, "Result": "pending"}, heading_date="")
    day = check_project.Checker.record_day
    assert str(day(block("ok (written 2026-11-03 10:00)"))) == "2026-11-03"
    assert day(block("ok (written 2026-10-15 10:00) (written 2026-11-03 10:00)")) is None  # undated stays checked
    assert str(day(block("ok (written 2026-11-03 10:00) note"))) == "2026-11-03"  # one stamp: dated as before
    # Round 4: an external action is dated by its later stamp; an added Date or a reversed pair cannot exempt it.
    action = SimpleNamespace(section="external actions", heading_date="",
                             fields={"Date": "2026-10-01", "Expected": "ok (written 2026-11-03 10:00)",
                                     "Result": "accepted (observed 2026-10-15 09:00)"})
    assert str(day(action)) == "2026-11-03"
    # Round 5: the stamp that ends Result dates it; two written stamps leave the entry undated (checked).
    quoted = SimpleNamespace(section="external actions", heading_date="",
                             fields={"Expected": "ok (written 2026-10-15 08:00)",
                                     "Result": "first (observed 2026-10-15 09:00); final (observed 2026-11-03 10:00)"})
    assert str(day(quoted)) == "2026-11-03"
    doubled = SimpleNamespace(section="external actions", heading_date="",
                              fields={"Expected": "ok (written 2026-10-14 08:00) (written 2026-10-15 08:00)",
                                      "Result": "accepted (observed 2026-10-15 09:00)"})
    assert day(doubled) is None


def test_brief_header_carries_custom_required_lines(tmp_path):
    """astra review round 3: a custom required line was missing from the header, and the hook's hint
    claimed the header contained it."""
    import re
    import ro_write
    from conftest import unified_project
    project = Project(unified_project(tmp_path), slot="A", session="incident-test")
    project.register_slot()
    agents = project.root / "agents.md"
    agents.write_text(re.sub(r"(?m)^- Brief requirements: .*$",
                             "- Brief requirements: general-purpose: ro-delegate: v1; general-purpose: Budget: 2 CPU workers",
                             agents.read_text(encoding="utf-8")), encoding="utf-8")
    header = ro_write.delegate(project, "none")
    settings = project.settings()
    assert "Budget: 2 CPU workers" in header.splitlines()[:3]
    assert checks.pre_checks(checks.Call("Agent", prompt=header), project.root, [], settings) == []
    missing = checks.pre_checks(checks.Call("Agent", prompt="ro-delegate: v1\nDo it."), project.root, [], settings)
    assert "`Budget: 2 CPU workers`" in missing[0].message


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


# ---- astra review 2026-11-22 ----

def test_handoff_edit_reaches_python_even_when_another_hook_refreshed_the_snapshot(tmp_path, monkeypatch):
    """The fast path returned {} for the edit because another call had already recorded its stamps."""
    import ro_hook_runner as runner
    project_at(tmp_path)
    monkeypatch.setattr(runner, "unchanged_records", lambda path: True)
    edit = edit_payload(str(tmp_path / "handoff.md"), "# H\n", "# H\n\n### 2026-11-10 05:26 — A — none\n")
    patch = {"tool_name": "apply_patch", "tool_input": "*** Begin Patch\n*** Update File: handoff.md\n@@\n+x\n*** End Patch\n"}
    other = edit_payload(str(tmp_path / "notes.md"), "a", "b")
    assert not runner.quiet("PostToolUse", edit, tmp_path) and not runner.quiet("PostToolUse", patch, tmp_path)
    assert runner.quiet("PostToolUse", other, tmp_path)


def test_r_and_julia_scripts_are_checked_before_launch(tmp_path):
    import ro_jobs
    run = tmp_path / "run"
    run.mkdir()
    for command in (["Rscript", "missing.R"], ["julia", "missing.jl"]):
        with pytest.raises(ValueError, match="does not exist"):
            ro_jobs._check_script(tmp_path, run, command, "linux")


def test_brief_counts_delete_warnings():
    import ro_records
    assert ro_records.CHECK.findall("fs.delete: Recursive or wildcard delete") == ["fs.delete"]
