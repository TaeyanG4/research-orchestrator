"""The docs/tools.md registry: search before writing, checker findings and brief facts (7.0.0)."""

from __future__ import annotations

import os

from conftest import check, found, unified_project
import ro_records as records
from ro_state import Project

REGISTRY = """# Tools

```markdown
## example — fenced samples are not entries
- Path: tools/example.py
```

## submit-once — one guarded upload per candidate
- Path: tools/submit_once.py
- Version: 1.3.0
- Usage: python tools/submit_once.py <file> --message "<text>"
- Tests: tests/test_submit_once.py
- Files: tools/submit_common.py
- Status: active

## submit-legacy — the first uploader
- Path: tools/submit_legacy.py
- Usage: python tools/submit_legacy.py <file>
- Status: superseded by submit-once
"""


def project(tmp_path) -> Project:
    p = Project(unified_project(tmp_path), slot="A", session="tools-session")
    p.register_slot()
    tools = p.root / "tools"
    tools.mkdir()
    for name in ("submit_once.py", "submit_common.py", "submit_legacy.py", "_private.py", "test_helper.py",
                 "notes.txt"):
        (tools / name).write_text("pass\n", encoding="utf-8")
    (p.root / "docs").mkdir()
    (p.root / "docs/tools.md").write_text(REGISTRY, encoding="utf-8", newline="\n")
    return p


def tool_issues(target):
    return [(i.check, i.record) for i in check(target).issues if i.check.startswith("tools.")]


def test_search_lists_matching_tools_and_dupcheck_finds_them(tmp_path):
    p = project(tmp_path)
    listing = records.tools_listing(p, ["upload"])
    assert "submit-once — one guarded upload per candidate | tools/submit_once.py | 1.3.0 | active" in listing
    assert "Usage: python tools/submit_once.py" in listing and "example" not in listing
    assert records.tools_listing(p, ["superseded"]).count("submit-legacy") == 1
    assert records.tools_listing(p, ["nothing-like-this"]) == "No matching tools."
    # Usage words alone find the tool next to plan items and discoveries.
    assert "docs/tools.md:8: ## submit-once" in records.dupcheck(p, ["--message"])


def test_registered_project_is_clean_and_unregistered_siblings_are_reported(tmp_path):
    p = project(tmp_path)
    assert tool_issues(p.root) == []
    (p.root / "tools/submit_v2.py").write_text("pass\n", encoding="utf-8")
    (p.root / "tools/nested").mkdir()
    (p.root / "tools/nested/deep.py").write_text("pass\n", encoding="utf-8")  # only siblings are scanned
    (p.root / "root_script.py").write_text("pass\n", encoding="utf-8")      # the project root is not scanned
    assert tool_issues(p.root) == [("tools.unregistered", "tools/submit_v2.py")]
    brief = records.brief(p)
    assert "tools.unregistered: 1 script(s) beside registered tools lack a docs/tools.md entry" in brief
    assert "Tools: 2 registered (1 active) in docs/tools.md; search `ro tools <terms>`" in brief


def test_registry_field_status_path_and_duplicate_findings(tmp_path):
    p = project(tmp_path)
    registry = p.root / "docs/tools.md"
    registry.write_text(REGISTRY + "\n## broken — no usage\n- Path: tools/missing.py\n- Status: active\n"
                        "\n## odd — unknown state\n- Path: tools/submit_once.py\n- Usage: x\n- Status: draft\n"
                        "\n## twin — same file\n- Path: tools/submit_once.py\n- Usage: y\n- Status: active\n",
                        encoding="utf-8", newline="\n")
    found_issues = tool_issues(p.root)
    assert ("tools.field", "broken") in found_issues and ("tools.field", "odd") in found_issues
    assert ("tools.path.missing", "broken") in found_issues
    assert ("tools.path.duplicate", "twin") in found_issues
    assert all(i.severity == "WARN" for i in check(p.root).issues if i.check.startswith("tools."))


def test_projects_without_a_registry_get_no_tool_findings_or_brief_line(tmp_path):
    p = Project(unified_project(tmp_path), slot="A", session="tools-session")
    p.register_slot()
    (p.root / "scripts").mkdir()
    (p.root / "scripts/build.py").write_text("pass\n", encoding="utf-8")
    assert tool_issues(p.root) == []
    assert "Tools:" not in records.brief(p)
    assert records.tools_listing(p).startswith("No tool registry yet: `ro tools --init` creates docs/tools.md")


def test_compact_brief_notices_a_new_script_beside_registered_tools(tmp_path):
    p = project(tmp_path)
    assert "tools.unregistered" not in records.brief(p)
    assert "tools.unregistered" not in records.brief(p, compact=True)
    created = p.root / "tools/fresh_copy.py"
    created.write_text("pass\n", encoding="utf-8")
    stat = (p.root / "tools").stat()
    os.utime(p.root / "tools", ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert "tools.unregistered: 1" in records.brief(p, compact=True)
