"""Sessions that never load the skill still find and follow the project's working rules (7.0.0)."""

from __future__ import annotations

import io
import contextlib

from conftest import make_project
import init_research_orchestrator as init
import ro_records as records
from ro_state import Project


def run_init(*args: str) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return init.main(list(args))


def test_generated_rules_follow_the_profile_and_settings(tmp_path):
    research = make_project(tmp_path, "research", "--preset", "solo-research", "--platforms", "Claude Code",
                            "--user", "operator")
    text = (research / "agents.md").read_text(encoding="utf-8")
    rules = text[text.index("## Working rules"):text.index("## Project rules")]
    for phrase in ("ro dupcheck <terms>", "ro next-id", "one per experiment, including negative and inconclusive",
                   "ro tools <terms>", "ro tools --init", "ro launch", "real clock", "Open consistency issues",
                   "history.size", "ro close", "~/.claude/skills/research-orchestrator"):
        assert phrase in rules, phrase
    assert "only reusable results" not in rules
    header = (research / "discoveries.md").read_text(encoding="utf-8").split("Discovery format:")[0]
    assert "one discovery per experiment, including negative" in header and "In the work profile" not in header
    work = make_project(tmp_path, "work", "--preset", "work-project", "--platforms", "Claude Code", "--user", "operator")
    rules = (work / "agents.md").read_text(encoding="utf-8").split("## Working rules")[1]
    assert "only reusable results" in rules and "one per experiment" not in rules
    assert "In the work profile" in (work / "discoveries.md").read_text(encoding="utf-8")


def test_init_links_claude_md_once_and_respects_existing_files(tmp_path):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert run_init(str(fresh), "-n", "fresh", "--preset", "quick", "--user", "operator") == 0
    assert (fresh / "CLAUDE.md").read_text(encoding="utf-8") == init.CLAUDE_LINE + "\n"
    assert run_init(str(fresh), "-n", "fresh", "--preset", "quick", "--user", "operator") == 0
    assert (fresh / "CLAUDE.md").read_text(encoding="utf-8").count("@agents.md") == 1  # idempotent

    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "CLAUDE.md").write_bytes(b"# Team notes\r\nKeep answers short.")
    assert run_init(str(existing), "-n", "existing", "--preset", "quick", "--user", "operator") == 0
    assert (existing / "CLAUDE.md").read_bytes() == (b"# Team notes\r\nKeep answers short.\r\n\r\n"
                                                    + init.CLAUDE_LINE.encode("utf-8") + b"\r\n")

    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "CLAUDE.md").write_text("Read agents.md first.\n", encoding="utf-8")
    assert run_init(str(linked), "-n", "linked", "--preset", "quick", "--user", "operator") == 0
    assert (linked / "CLAUDE.md").read_text(encoding="utf-8") == "Read agents.md first.\n"

    opted_out = tmp_path / "opted-out"
    opted_out.mkdir()
    assert run_init(str(opted_out), "-n", "opted", "--preset", "quick", "--user", "operator", "--no-claude-md") == 0
    assert not (opted_out / "CLAUDE.md").exists()
    # Upgrading an existing project adds the line too.
    assert run_init(str(opted_out), "--reconfigure") == 0
    assert "@agents.md" in (opted_out / "CLAUDE.md").read_text(encoding="utf-8")


def test_tools_init_creates_the_registry_with_its_rules_once(tmp_path):
    target = make_project(tmp_path, "tools", "--preset", "work-project", "--platforms", "Claude Code",
                          "--user", "operator")
    project = Project(target, slot="A", session="tools-session")
    assert records.tools_listing(project).startswith("No tool registry yet: `ro tools --init`")
    assert records.tools_init(project).startswith("Created docs/tools.md")
    text = (target / "docs/tools.md").read_text(encoding="utf-8")
    assert "Search here first (`ro tools <terms>`)" in text and "bump its `Version`" in text
    assert records.tool_entries(text) == []  # the fenced format is not an entry
    assert records.tools_listing(project) == "docs/tools.md lists no tools."
    assert records.tools_init(project) == "docs/tools.md already exists; add entries to it."


def test_session_start_brief_points_at_the_working_rules(tmp_path):
    target = make_project(tmp_path, "brief", "--preset", "quick", "--user", "operator")
    project = Project(target, slot="A", session="brief-session")
    project.register_slot()
    brief = records.brief(project)
    assert "Rules: follow agents.md (## Working rules) before editing the coordination files" in brief


def test_agents_size_warns_before_codex_cuts_the_user_rules(tmp_path):
    from conftest import check, found
    target = make_project(tmp_path, "size", "--preset", "work-project", "--platforms", "Claude Code",
                          "--user", "operator")
    agents = target / "agents.md"
    original = agents.read_text(encoding="utf-8")
    assert not found(check(target), "WARN", "agents.size")
    lesson = "- A recorded lesson that stays relevant to this project → enforced by none\n"
    for size, phrase in ((13 * 1024, "(limit 12 KiB) and loads in every session"),
                         (33 * 1024, "Codex reads only the first 32 KiB")):
        padding = lesson * (1 + (size - len(original.encode("utf-8"))) // len(lesson.encode("utf-8")))
        agents.write_text(original.replace("### Lessons\n", "### Lessons\n\n" + padding), encoding="utf-8", newline="\n")
        warnings = found(check(target), "WARN", "agents.size")
        assert len(warnings) == 1 and phrase in warnings[0].message and "docs/" in warnings[0].message
    project = Project(target, slot="A", session="size-session")
    project.register_slot()
    assert "agents.size: agents.md past its size limit" in records.brief(project)
