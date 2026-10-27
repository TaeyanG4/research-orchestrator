"""The unified workflow: queue, claims, unknown fields, stages (spec §5, §7; test 3)."""

from __future__ import annotations

from conftest import (append_events, check, event, found, item, make_project, set_queue, set_slot, severities,
                      unified_project)


def checks(checker, severity: str) -> list[str]:
    return [i.check for i in found(checker, severity)]


def test_clean_unified_queue(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "A since 2026-10-25 09:00", stages="s1 build | s2 run"), item("H-B-01"))
    checker = check(target)
    assert checker.code == 0 and severities(checker) == {"ERROR": 0, "WARN": 0, "INFO": 0}, \
        [i.render() for i in checker.issues]


def test_claim_by_a_released_slot_is_stale(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "B since 2026-10-25 09:00"))
    set_slot(target, "B", "released", "none")
    checker = check(target)
    stale = found(checker, "WARN", "plan.claim.stale")
    assert len(stale) == 1 and stale[0].record == "H-A-01" and stale[0].fingerprint == "plan.claim.stale|H-A-01|Claimed"
    assert checker.code == 0


def test_missing_claimed_line_is_an_error(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", claimed=None))
    checker = check(target)
    assert checks(checker, "ERROR") == ["plan.claim.missing"] and checker.code == 1


def test_two_queue_sections_are_an_error(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01"), extra_sections="\n## Queue\n\n" + item("H-A-02"))
    checker = check(target)
    assert "plan.queue.duplicate" in checks(checker, "ERROR")


def test_agent_sections_in_a_unified_plan_are_an_error(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01"), extra_sections="\n## Agent: A\n\n" + item("H-A-02"))
    errors = checks(check(target), "ERROR")
    assert "plan.section.workflow" in errors and "plan.item.section" in errors


def test_unknown_fields_are_info_not_errors(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", extra=[("Status", "running on GPU"), ("Candidate (v2)", "release 3")]))
    checker = check(target)
    assert checker.code == 0 and severities(checker)["WARN"] == 0
    unknown = found(checker, "INFO", "plan.field.unknown")
    assert sorted(i.field for i in unknown) == ["Candidate", "Status"]


def test_required_fields_out_of_order_are_info_and_missing_ones_error(tmp_path) -> None:
    target = unified_project(tmp_path)
    swapped = item("H-A-01").replace("- Impact: 1\n- Information: 1\n", "- Information: 1\n- Impact: 1\n")
    missing = item("H-A-02").replace("- Next test: a test\n", "")
    set_queue(target, swapped, missing)
    checker = check(target)
    assert checks(checker, "INFO") == ["plan.field.order"]
    assert not checks(checker, "WARN")
    assert [(i.check, i.record, i.field) for i in found(checker, "ERROR")] == [("plan.field.missing", "H-A-02", "Next test")]


def test_stage_events_record_progress_only(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "A since 2026-10-25 09:00", stages="s1 build | s2 run"),
              item("H-A-02", "A since 2026-10-25 09:00"))
    append_events(target,
                  event("2026-10-25 10:00", "A", "H-A-01/s1"),
                  event("2026-10-25 10:30", "A", "H-A-01/s3"),
                  event("2026-10-25 10:40", "A", "H-A-02/s1"))
    checker = check(target)
    assert sorted(checks(checker, "WARN")) == ["event.stage.beyond", "event.stage.undeclared"]
    assert "event.finished.queued" not in checks(checker, "ERROR")  # /sN never completes the item
    assert checker.code == 0

    # The bare ID completes the item, so it must have left plan.md.
    append_events(target, event("2026-10-25 11:00", "A", "H-A-01"))
    assert "event.finished.queued" in checks(check(target), "ERROR")


def test_a_stage_event_does_not_account_for_a_lost_item(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-02"))
    append_events(target, event("2026-10-25 09:00", "A", "none", new_items="H-A-01"),
                  event("2026-10-25 10:00", "A", "H-A-01/s1"))
    lost = found(check(target), "ERROR", "event.item.lost")
    assert [i.record for i in lost] == ["H-A-01"]


def test_decision_changed_needs_a_discovery(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "A since 2026-10-25 09:00", stages="s1 build | s2 run"))
    append_events(target, event("2026-10-25 10:00", "A", "H-A-01/s1", extra="- Decision: changed\n"))
    assert checks(check(target), "WARN") == ["event.stage.review", "event.decision.discovery"]


def test_idle_and_future_claims(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "A since 2026-10-01 09:00"), item("H-A-02", "A since 2026-10-26 09:00"))
    checker = check(target)
    assert [i.record for i in found(checker, "INFO", "plan.claim.idle")] == ["H-A-01"]
    assert [i.record for i in found(checker, "WARN", "time.future")] == ["H-A-02"]
    # An event naming the item after the claim time keeps the claim alive.
    append_events(target, event("2026-10-20 09:00", "A", "H-A-01/s1"))
    assert not found(check(target), "INFO", "plan.claim.idle")


def test_non_canonical_claim_is_a_warning_and_still_read(tmp_path) -> None:
    target = unified_project(tmp_path)
    set_queue(target, item("H-A-01", "B (Claude Code, since 2026-10-20 04:03)"))
    set_slot(target, "B", "released", "none")
    warnings = checks(check(target), "WARN")
    assert sorted(warnings) == ["plan.claim.format", "plan.claim.stale"]


def test_classic_project_with_a_queue_is_an_error(tmp_path) -> None:
    target = make_project(tmp_path, "classic", "--preset", "team-research")
    plan = target / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\n## Queue\n", encoding="utf-8", newline="\n")
    assert "plan.section.workflow" in checks(check(target), "ERROR")
