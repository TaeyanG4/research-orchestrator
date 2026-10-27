"""Checker baseline: fingerprints, new-issue WARN, never hiding a finding (spec §7; test 7)."""

from __future__ import annotations

import json

from conftest import check, found, item, run_check_cli, set_queue, set_slot, unified_project


def stale_project(tmp_path):
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "B since 2026-10-24 09:00"), item("H-A-02"))
    set_slot(target, "B", "released", "none")
    return target


def findings(checker) -> set[tuple[str, str, str, str]]:
    return {(i.severity, i.check, i.record, i.field) for i in checker.issues if not i.check.startswith("baseline.")}


def test_baseline_update_then_same_fingerprints_report_nothing_new(tmp_path) -> None:
    target = stale_project(tmp_path)
    before = findings(check(target))
    result = run_check_cli(target, "--baseline-update")
    assert result.returncode == 0 and "plan.claim.stale" in result.stdout and "[BASELINE]" in result.stdout
    data = json.loads((target / ".ro" / "checker-baseline.json").read_text(encoding="utf-8"))
    assert data["fingerprints"] == ["plan.claim.stale|H-A-01|Claimed"]
    again = check(target)
    assert not found(again, check_id="baseline.new")
    assert findings(again) == before  # the baseline hides nothing and downgrades nothing
    plan = target / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("- Claimed: none\n", ""), encoding="utf-8", newline="\n")
    with_baseline = check(target)
    assert before <= findings(with_baseline)  # every earlier finding is still reported at its severity
    assert ("ERROR", "plan.claim.missing", "H-A-02", "Claimed") in findings(with_baseline)
    assert with_baseline.code == 1


def test_a_new_fingerprint_is_reported_as_a_warning(tmp_path) -> None:
    target = stale_project(tmp_path)
    assert run_check_cli(target, "--baseline-update").returncode == 0
    set_queue(target, item("H-A-01", "B since 2026-10-24 09:00"), item("H-A-02", "B since 2026-10-24 09:05"))
    checker = check(target)
    new = found(checker, "WARN", "baseline.new")
    assert len(new) == 1 and "1 new issue(s)" in new[0].message and "plan.claim.stale|H-A-02|Claimed" in new[0].message
    assert len(found(checker, "WARN", "plan.claim.stale")) == 2


def test_an_unreadable_baseline_is_a_warning(tmp_path) -> None:
    target = stale_project(tmp_path)
    (target / ".ro").mkdir(exist_ok=True)
    (target / ".ro" / "checker-baseline.json").write_text("{not json", encoding="utf-8")
    assert found(check(target), "WARN", "baseline.unreadable")


def test_text_outside_items_is_one_issue_per_section(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01"), "Loose note one.\n", "Loose note two.\n",
              extra_sections="\n## Notes\n\nSome text.\n- a bullet\n")
    checker = check(target)
    outside = found(checker, "WARN", "plan.text.outside")
    heading = found(checker, "WARN", "plan.text.heading")
    assert [(i.record, "2 line(s)" in i.message) for i in outside] == [("section:Queue", True)]
    assert [i.record for i in heading] == ["section:Notes"]


def test_editing_lines_above_creates_no_new_issues(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "B since 2026-10-24 09:00"), "Loose note.\n",
              extra_sections="\n## Notes\n\nSome text.\n")
    set_slot(target, "B", "released", "none")
    assert run_check_cli(target, "--baseline-update").returncode == 0
    plan = target / "plan.md"
    text = plan.read_text(encoding="utf-8").replace("## Queue\n\n", "## Queue\n\n" + item("H-A-09") + "\n\n\n", 1)
    plan.write_text("\n\n" + text, encoding="utf-8", newline="\n")  # every line moves down
    checker = check(target)
    assert not found(checker, check_id="baseline.new"), [i.render() for i in checker.issues]
    assert {i.check for i in found(checker, "WARN")} == {"plan.claim.stale", "plan.text.outside", "plan.text.heading"}


def test_an_info_only_addition_is_new_since_the_baseline(tmp_path) -> None:
    target = stale_project(tmp_path)
    assert run_check_cli(target, "--baseline-update").returncode == 0
    set_queue(target, item("H-A-01", "B since 2026-10-24 09:00"), item("H-A-02", extra=[("Status", "running")]))
    new = found(check(target), "WARN", "baseline.new")
    assert len(new) == 1 and "plan.field.unknown|H-A-02|Status" in new[0].message
