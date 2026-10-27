"""The user-owned rules region stays intact while bounded, dated guidance is checked."""

from __future__ import annotations

import pytest

from conftest import check, found, make_project, rs, run_init


def replace_rules(target, content):
    path = target / "agents.md"
    generated, _region = rs.split_agents(path.read_text(encoding="utf-8"))
    path.write_text(generated + content, encoding="utf-8", newline="\n")


def test_new_project_rules_and_summary_order(tmp_path):
    target = make_project(tmp_path, "example")
    text = (target / "agents.md").read_text(encoding="utf-8")
    headings = ["Summary: preset", "## Project settings", "## Rules for this project", "## Project rules",
                "### Standing rules", "### Active overrides", "### Lessons"]
    positions = [text.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert f"<!-- ro-template: {rs.CURRENT_TEMPLATE} -->" in text
    assert rs.read_settings(text).version == rs.CURRENT_TEMPLATE
    assert str(rs.STANDING_RULES_BUDGET) in text
    assert "Expires: YYYY-MM-DD" in text
    assert "<mistake> → enforced by <check id | none>" in text
    assert not found(check(target), "WARN")


@pytest.mark.parametrize("extra,warning", [("", False), ("x", True)])
def test_standing_rules_budget_counts_utf8_bytes(tmp_path, extra, warning):
    target = make_project(tmp_path, "example")
    # 2048 non-ASCII characters occupy exactly 4096 UTF-8 bytes.
    content = "é" * (rs.STANDING_RULES_BUDGET // 2) + extra
    region = "## Project rules\n\n### Standing rules\n\n<!-- guidance -->\n" + content + "\n\n"
    replace_rules(target, region)
    before = (target / "agents.md").read_bytes()
    checker = check(target)
    assert bool(found(checker, "WARN", "rules.standing.budget")) is warning
    assert (target / "agents.md").read_bytes() == before


def test_standing_rules_count_code_but_not_neighboring_sections(tmp_path):
    target = make_project(tmp_path, "example")
    region = ("## Project rules\n\n### Standing rules\n\n`````\n" + "x" * rs.STANDING_RULES_BUDGET
              + "\n`````\n\n### Lessons\n\nA small lesson.\n")
    replace_rules(target, region)
    assert found(check(target), "WARN", "rules.standing.budget")
    replace_rules(target, "## Project rules\n\n### Standing rules\n\nA short rule.\n\n### Lessons\n\n"
                  + "x" * (rs.STANDING_RULES_BUDGET + 1))
    assert not found(check(target), check_id="rules.standing.budget")


@pytest.mark.parametrize("entry,check_id", [
    ("- Temporary rule | Expires: 2026-10-24", "rules.override.expired"),
    ("- Temporary rule\n  Expires: 2026-10-24", "rules.override.expired"),
    ("- Temporary rule | Expires: 2026-10-25", None),
    ("- Temporary rule | Expires: 2026-10-26", None),
    ("- Temporary rule", "rules.override.expires"),
    ("- Temporary rule | Expires: 2026-02-30", "rules.override.expires"),
])
def test_active_overrides_require_valid_expiry_and_warn_after_that_date(tmp_path, entry, check_id):
    target = make_project(tmp_path, "example")
    region = "## Project rules\n\n### Active overrides\n\n" + entry + "\n  Reason: temporary constraint\n"
    replace_rules(target, region)
    checker = check(target)
    assert [issue.check for issue in found(checker, "WARN")] == ([check_id] if check_id else [])
    assert checker.code == 0
    assert run_init(target, "--reconfigure").returncode == 0
    assert rs.split_agents((target / "agents.md").read_text(encoding="utf-8"))[1] == region


def test_each_active_override_is_checked_and_examples_are_ignored(tmp_path):
    target = make_project(tmp_path, "example")
    region = ("## Project rules\n\n### Active overrides\n\n"
              "<!-- - Comment example | Expires: 2000-01-01 -->\n"
              "```text\n- Fenced example | Expires: 2000-01-01\n```\n"
              "- Old rule | Reason: temporary constraint | Expires: 2026-10-24\n"
              "- Current rule | Reason: temporary constraint | Expires: 2026-10-25\n"
              "- Undated rule | Reason: temporary constraint\n")
    replace_rules(target, region)
    assert [(issue.check, issue.record) for issue in found(check(target), "WARN")] == [
        ("rules.override.expired", "Old rule"), ("rules.override.expires", "Undated rule")]
