"""Replay: a real unified plan archive, structure only, parses under `unified` (spec §9; test 9; review fix 16).

The fixture keeps the headings, item IDs, field names, Claimed lines, and scores of an archived plan
that outgrew the v2 format, with every other text redacted, and uses the canonical '## Queue' heading.
Its extra fields (Status, Candidate, Exception, ...) made the v2 checker report every item;
under v3 they are INFO; Ready by is now a recognized optional date. A non-canonical queue heading is tested separately.
"""

from __future__ import annotations

import shutil

from conftest import FIXTURES, check, found, make_project

FIELD_CHECKS = {"plan.field.order", "plan.field.unknown", "plan.claim.order"}


def replay_project(tmp_path, fixture: str = "unified-plan-sample"):
    target = make_project(tmp_path, "replay", "--preset", "solo-research", "--platforms", "Claude Code",
                          "--agents", "2", "--user", "operator")
    shutil.copyfile(FIXTURES / fixture / "plan.md", target / "plan.md")
    return target


def test_extra_fields_parse_under_unified_without_errors(tmp_path) -> None:
    checker = check(replay_project(tmp_path))
    assert checker.code != 2
    assert checker.values["workflow"] == "unified"
    assert len(checker.plan_items) == 11
    assert all(item.section == "queue" for item in checker.plan_items.values())
    errors = found(checker, "ERROR")
    assert not [i for i in errors if i.check in FIELD_CHECKS], [i.render() for i in errors]
    assert not [i for i in errors if "Status" in i.message or "Candidate" in i.message]
    assert not [i for i in found(checker, "WARN") if i.check in FIELD_CHECKS]
    unknown = {i.field for i in found(checker, "INFO", "plan.field.unknown")}
    assert {"Status", "Candidate", "Exception", "Measured", "Latest user follow-through"} <= unknown
    assert "Ready by" not in unknown
    errors = found(checker, "ERROR")
    # One item lacks 'Next test'; source discoveries are absent and three archived scores are inconsistent.
    assert {i.check for i in errors} == {"plan.field.missing", "plan.sources.dangling", "plan.priority.mismatch"}
    assert {i.record for i in errors if i.check == "plan.priority.mismatch"} == {"H-B-219", "H-B-230", "H-B-231"}
    assert [(i.record, i.field) for i in errors if i.check == "plan.field.missing"] == [("H-B-219", "Next test")]
    # 'B (<host>, since …)' claims are non-canonical but still read: B is unassigned here, so they are stale.
    assert len(found(checker, "WARN", "plan.claim.format")) == 10
    assert len(found(checker, "WARN", "plan.claim.stale")) == 10
    # The six non-plan sections above the queue are one warning each.
    assert len(found(checker, "WARN", "plan.text.heading")) == 6


def test_a_non_canonical_queue_heading_is_an_error(tmp_path) -> None:
    checker = check(replay_project(tmp_path, "noncanonical-queue-heading"))
    assert [i.check for i in found(checker, "ERROR")] == ["plan.queue.missing"]
    assert [i.record for i in found(checker, "WARN", "plan.text.heading")] == ["section:Unified queue"]
