"""Verification: sequential review state, eligibility per mode, reviewer identity (spec §6; test 5; review fixes 4-7)."""

from __future__ import annotations

import datetime as dt

import pytest

from check_project import Block, Checker, Review
from conftest import append_discovery, check, copy_fixture, found, make_project, run_init, set_slot, severities

SESSION = "session:source@2026-10-24T10:00"
REVIEWER_A = "subagent:reviewer-a@2026-10-24T11:00"
REVIEWER_B = "session:reviewer-b@2026-10-24T15:00"


def independent_project(parent):
    target = make_project(parent, "independent", "--preset", "solo-research", "--platforms", "Claude Code",
                          "--user", "operator", "--agents", "2")
    set_slot(target, "A", "Claude Code", user="operator")
    return target


def discovery(did: str, state: str, reviews: list[str], source: str = "A", host: str = "Claude Code",
              session: str | None = SESSION) -> str:
    lines = [f"## {did} — test finding", f"- Source: {source}", f"- Host: {host}", "- User: operator", "- Date: 2026-10-24"]
    if session:
        lines.append(f"- Session: {session}")
    lines += [f"- Cross-check: {state}", "- Finding: f", "- Evidence: e", "- Implication: i", "- Reviews:"]
    lines += [f"  - {review}" for review in reviews]
    return "\n".join(lines) + "\n"


def only(checker, severity: str) -> list[str]:
    return [i.check for i in found(checker, severity)]


def errors_by_record(checker) -> list[tuple[str, str]]:
    return [(i.check, i.record) for i in found(checker, "ERROR")]


# ---------- independent-review: identity ----------

def test_same_slot_review_with_a_distinct_session_identity_counts(tmp_path) -> None:
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [f"Claude Code (A): CLOSED — reviewer {REVIEWER_A} — ok"]))
    append_discovery(target, discovery("D-A-002", "VERIFIED", [f"Claude Code (A): CLOSED — reviewer {REVIEWER_B} — ok"]))
    checker = check(target)
    assert severities(checker) == {"ERROR": 0, "WARN": 0, "INFO": 0}, [i.render() for i in checker.issues]


def test_a_reviewer_equal_to_the_source_session_does_not_count(tmp_path) -> None:
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [f"Claude Code (A): CLOSED — reviewer {SESSION} — ok"]))
    checker = check(target)
    assert only(checker, "ERROR") == ["discovery.state.unbacked"]
    assert "discovery.review.self" in only(checker, "INFO")


def test_a_model_name_is_not_a_reviewer_identity(tmp_path) -> None:
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", ["Claude Code (A): CLOSED — reviewer sol — ok"]))
    append_discovery(target, discovery("D-A-002", "PENDING", ["Codex (B): CLOSED — reproduced"]))
    checker = check(target)
    assert [(i.check, i.record) for i in found(checker, "WARN")] == [
        ("discovery.review.identity", "D-A-001"), ("discovery.review.identity", "D-A-002")]
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]


@pytest.mark.parametrize("token", ["subagent:reviewer@2099-01-01T09:10",
                                  "subagent:reviewer@2026-10-25T12:01"])
def test_future_reviewer_session_cannot_verify_discovery(tmp_path, token):
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [
        f"Claude Code (A): CLOSED — reviewer {token} — reviewed 2026-10-25T11:00 — reproduced"]))
    checker = check(target)
    assert only(checker, "WARN") == ["discovery.review.identity"]
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]


@pytest.mark.parametrize("stamp", ["2026-10-25T12:01", "2026-10-23T23:59", "2026-10-22T10:00",
                                  "2026-02-30T12:00", "2026-10-24", "invalid"])
def test_recorded_review_time_must_follow_discovery_and_session_and_not_the_clock(tmp_path, stamp):
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [
        "Claude Code (A): CLOSED — reviewer subagent:reviewer@2026-10-23T08:00 "
        f"— reviewed {stamp} — reproduced"]))
    checker = check(target)
    assert only(checker, "WARN") == ["discovery.review.time"]
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]


@pytest.mark.parametrize("time_field", ["", "reviewed 2026-10-24T12:00 — "])
def test_older_independent_session_can_review_on_a_later_day(tmp_path, time_field):
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [
        "Claude Code (A): CLOSED — reviewer subagent:reviewer@2026-10-23T08:00 "
        f"— {time_field}reproduced"]))
    checker = check(target)
    assert severities(checker) == {"ERROR": 0, "WARN": 0, "INFO": 0}


def test_review_chronology_compares_offset_aware_instants(tmp_path):
    checker = Checker(tmp_path, now=dt.datetime(2026, 10, 25, 12, tzinfo=dt.timezone.utc))
    disc = Block("D-A-001", 1, fields={"Date": "2026-10-24", "Session": SESSION})
    token = "subagent:reviewer@2026-10-25T20:00+09:00"
    review = Review("Claude Code", "A", "CLOSED", False,
                    f"reviewer {token} — reviewed 2026-10-25T21:00+09:00 — reproduced", token)
    assert checker.independent_rule(disc, review)[0]
    review.rest = f"reviewer {token} — reviewed 2026-10-25T21:01+09:00 — reproduced"
    assert checker.independent_rule(disc, review)[2] == "discovery.review.time"


@pytest.mark.parametrize("stamp,accepted", [
    ("2026-10-23T23:30-02:00", True),
    ("2026-10-24T00:30+02:00", False),
])
def test_discovery_day_boundary_uses_the_checker_timezone(tmp_path, stamp, accepted):
    checker = Checker(tmp_path, now=dt.datetime(2026, 10, 25, 12, tzinfo=dt.timezone.utc))
    disc = Block("D-A-001", 1, fields={"Date": "2026-10-24", "Session": SESSION})
    token = "subagent:reviewer@2026-10-23T12:00Z"
    review = Review("Claude Code", "A", "CLOSED", False,
                    f"reviewer {token} — reviewed {stamp} — reproduced", token)
    result = checker.independent_rule(disc, review)
    assert result[0] is accepted
    if not accepted:
        assert result[2] == "discovery.review.time"


@pytest.mark.parametrize("token", ["subagent:reviewer@0001-01-01T00:00", "subagent:reviewer@0001-01-01T00:00+09:00"])
def test_valid_old_session_date_does_not_depend_on_host_timestamp_range(tmp_path, token):
    checker = Checker(tmp_path, now=dt.datetime(2026, 10, 25, 12))
    disc = Block("D-A-001", 1, fields={"Date": "2026-10-24", "Session": SESSION})
    review = Review("Claude Code", "A", "CLOSED", False,
                    f"reviewer {token} — reviewed 2026-10-25T11:00 — reproduced", token)
    assert checker.independent_rule(disc, review)[0]


@pytest.mark.parametrize("mode", ["self", "cross-host-once", "independent-review", "hybrid"])
@pytest.mark.parametrize("session", [SESSION, None])
@pytest.mark.parametrize("invalid", ["future-session", "future-review", "malformed-identity"])
def test_recorded_review_chronology_cannot_bypass_via_policy_or_legacy(tmp_path, mode, session, invalid):
    target = independent_project(tmp_path)
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace(
        "- Verification: independent-review", f"- Verification: {mode}"), encoding="utf-8")
    token = {"future-session": "subagent:reviewer@2099-01-01T12:00", "future-review": REVIEWER_A,
             "malformed-identity": "reviewer-name"}[invalid]
    reviewed = "2099-01-01T12:00" if invalid == "future-review" else "2026-10-24T12:00"
    append_discovery(target, discovery("D-A-001", "VERIFIED", [
        f"Codex (B): CLOSED — reviewer {token} — reviewed {reviewed} — reproduced"], session=session))
    checker = check(target)
    expected = "discovery.review.time" if invalid == "future-review" else "discovery.review.identity"
    assert found(checker, "WARN", expected)
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]


def test_recorded_future_review_time_is_checked_without_a_reviewer_token(tmp_path):
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [
        "Codex (B): CLOSED — reviewed 2099-01-01T12:00 — reproduced"], session=None))
    checker = check(target)
    assert found(checker, "WARN", "discovery.review.time")
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]


def test_future_source_session_cannot_support_a_review(tmp_path):
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", [
        f"Claude Code (A): CLOSED — reviewer {REVIEWER_A} — reproduced"],
        session="session:source@2099-01-01T10:00"))
    checker = check(target)
    assert found(checker, "WARN", "discovery.review.identity")
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]


def test_legacy_discovery_reviews_by_another_slot_still_count(tmp_path) -> None:
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "VERIFIED", ["Claude Code (B): CLOSED — reproduced"],
                                       session=None))
    append_discovery(target, discovery("D-A-002", "PENDING", [f"Claude Code (A): CLOSED — reviewer {REVIEWER_A} — ok"],
                                       session=None))
    checker = check(target)
    assert only(checker, "ERROR") == [] and only(checker, "WARN") == []
    legacy = [i.record for i in found(checker, "INFO", "discovery.review.legacy-session")]
    assert legacy == ["D-A-001", "D-A-002"]
    # A legacy discovery whose only review comes from its own slot cannot be VERIFIED.
    append_discovery(target, discovery("D-A-003", "VERIFIED", [f"Claude Code (A): CLOSED — reviewer {REVIEWER_A} — ok"],
                                       session=None))
    assert errors_by_record(check(target)) == [("discovery.state.unbacked", "D-A-003")]


def test_v2_project_switched_to_independent_review_keeps_verified_discoveries(tmp_path) -> None:
    target = copy_fixture("v2", tmp_path / "v2")
    (target / ".git").mkdir()
    result = run_init(target, "--reconfigure", "--verification", "independent-review")
    assert result.returncode == 0, result.stderr
    checker = check(target)
    assert severities(checker)["ERROR"] == 0 and severities(checker)["WARN"] == 0, [i.render() for i in checker.issues]
    assert "D-B-001" in [i.record for i in found(checker, "INFO", "discovery.review.legacy-session")]


# ---------- sequential state and challenges ----------

def test_closed_challenged_hold_after_challenge_cannot_be_verified(tmp_path) -> None:
    target = independent_project(tmp_path)
    reviews = [f"Claude Code (A): CLOSED — reviewer {REVIEWER_A} — ok",
               f"Claude Code (A): CHALLENGED — reviewer {REVIEWER_B} — leak in step 3",
               f"Claude Code (A): HOLD after challenge — reviewer {REVIEWER_A} — leak fixed, rerun needed"]
    append_discovery(target, discovery("D-A-001", "VERIFIED", reviews))
    append_discovery(target, discovery("D-A-002", "HOLD", reviews))
    assert errors_by_record(check(target)) == [("discovery.state.mismatch", "D-A-001")]


def test_resolution_outcomes(tmp_path) -> None:
    target = independent_project(tmp_path)
    challenge = f"Claude Code (A): CHALLENGED — reviewer {REVIEWER_A} — leak in step 3"
    for did, resolution, state in (("D-A-001", "CLOSED after challenge", "VERIFIED"),
                                   ("D-A-002", "VERIFIED after challenge", "VERIFIED"),
                                   ("D-A-003", "HOLD after challenge", "HOLD")):
        append_discovery(target, discovery(did, state, [challenge, f"Claude Code (A): {resolution} — reviewer {REVIEWER_B} — "
                                                                   "fixed"]))
    append_discovery(target, discovery("D-A-004", "CHALLENGED", [challenge, f"Claude Code (A): CLOSED after challenge "
                                                                            f"— reviewer {REVIEWER_B} — fixed"]))
    assert errors_by_record(check(target)) == [("discovery.state.superseded", "D-A-004")]


def test_an_ordinary_verdict_after_a_challenge_leaves_it_challenged(tmp_path) -> None:
    target = independent_project(tmp_path)
    reviews = [f"Claude Code (A): CHALLENGED — reviewer {REVIEWER_A} — leak", f"Claude Code (A): CLOSED — reviewer {REVIEWER_B} — ok"]
    append_discovery(target, discovery("D-A-001", "VERIFIED", reviews))
    append_discovery(target, discovery("D-A-002", "CHALLENGED", reviews))
    append_discovery(target, discovery("D-A-003", "PENDING", reviews[:1]))  # a revision does not reset a challenge
    assert errors_by_record(check(target)) == [("discovery.state.challenged", "D-A-001"),
                                               ("discovery.state.challenged", "D-A-003")]


def test_later_reviews_after_a_resolution_set_the_state(tmp_path) -> None:
    target = independent_project(tmp_path)
    reviews = [f"Claude Code (A): CHALLENGED — reviewer {REVIEWER_A} — leak",
               f"Claude Code (A): CLOSED after challenge — reviewer {REVIEWER_B} — fixed",
               f"Claude Code (A): HOLD — reviewer {REVIEWER_A} — new data needed"]
    append_discovery(target, discovery("D-A-001", "HOLD", reviews))
    append_discovery(target, discovery("D-A-002", "VERIFIED", reviews))
    append_discovery(target, discovery("D-A-003", "PENDING", [f"Claude Code (A): HOLD — reviewer {REVIEWER_A} — more data"]))
    assert errors_by_record(check(target)) == [("discovery.state.mismatch", "D-A-002")]


def test_withdrawing_a_challenge_resolution_review_restores_challenged(tmp_path) -> None:
    target = independent_project(tmp_path)
    reviews = [f"Claude Code (A): CHALLENGED — reviewer {REVIEWER_A} — evidence missing"]
    append_discovery(target, discovery("D-A-001", "REVIEWING Claude Code (B)", reviews))
    checker = check(target)
    stale = found(checker, "WARN", "discovery.reviewing.stale")
    assert [issue.record for issue in stale] == ["D-A-001"]
    path = target / "discoveries.md"
    path.write_text(path.read_text(encoding="utf-8").replace("REVIEWING Claude Code (B)", "CHALLENGED"),
                    encoding="utf-8", newline="\n")
    assert severities(check(target)) == {"ERROR": 0, "WARN": 0, "INFO": 0}


def test_withdrawing_a_review_restores_each_prior_effective_state(tmp_path) -> None:
    target = independent_project(tmp_path)
    for number, verdict in ((1, None), (2, "CLOSED"), (3, "HOLD")):
        reviews = [] if verdict is None else [f"Claude Code (A): {verdict} — reviewer {REVIEWER_A} — evidence checked"]
        append_discovery(target, discovery(f"D-A-{number:03}", "REVIEWING Claude Code (B)", reviews))
    checker = check(target)
    stale = found(checker, "WARN", "discovery.reviewing.stale")
    assert [issue.record for issue in stale] == ["D-A-001", "D-A-002", "D-A-003"]
    assert only(checker, "ERROR") == []
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8")
    for state in ("PENDING", "VERIFIED", "HOLD"):
        text = text.replace("REVIEWING Claude Code (B)", state, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    restored = check(target)
    assert only(restored, "ERROR") == [] and only(restored, "WARN") == []


# ---------- cross-host-once and hybrid eligibility ----------

def test_multi_needs_a_different_host(tmp_path) -> None:
    target = make_project(tmp_path, "team", "--preset", "team-research", "--user", "operator")
    append_discovery(target, discovery("D-A-001", "VERIFIED", ["Codex (B): CLOSED — reproduced"], session=None))
    append_discovery(target, discovery("D-A-002", "VERIFIED", ["Claude Code (B): CLOSED — same host — reproduced"],
                                       session=None))
    append_discovery(target, discovery("D-A-003", "VERIFIED", ["Claude Code (B): CLOSED — reproduced"], session=None))
    append_discovery(target, discovery("D-A-004", "VERIFIED", ["Codex (A): CLOSED — reproduced"], session=None))
    checker = check(target)
    assert [(i.check, i.record) for i in found(checker, "WARN")] == [
        ("discovery.review.ineligible", "D-A-002"), ("discovery.review.same-host", "D-A-003"),
        ("discovery.review.ineligible", "D-A-004")]  # D-A-004: the source slot itself, from another host
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-002"), ("discovery.state.unbacked", "D-A-003"),
                                         ("discovery.state.unbacked", "D-A-004")]
    assert only(checker, "INFO") == []  # PENDING raises nothing under cross-host-once


def test_single_needs_a_different_slot_and_the_marker(tmp_path) -> None:
    target = make_project(tmp_path, "single", "--platform", "single", "--platforms", "Claude Code", "--user", "operator",
                          "--verification", "cross-host-once")
    append_discovery(target, discovery("D-A-001", "VERIFIED", ["Claude Code (B): CLOSED — same host — reproduced"],
                                       session=None))
    append_discovery(target, discovery("D-A-002", "VERIFIED", ["Claude Code (A): CLOSED — same host — reproduced"],
                                       session=None))
    append_discovery(target, discovery("D-A-003", "VERIFIED", ["Claude Code (B): CLOSED — reproduced"], session=None))
    checker = check(target)
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-002"), ("discovery.state.unbacked", "D-A-003")]
    assert [(i.check, i.record) for i in found(checker, "WARN")] == [
        ("discovery.review.ineligible", "D-A-002"), ("discovery.review.same-host", "D-A-003")]


def test_adaptive_counts_same_host_reviews_only_with_the_same_host_fallback(tmp_path) -> None:
    review = ["Claude Code (B): CLOSED — same host — reproduced"]
    allowed = make_project(tmp_path, "fallback", "--platform", "adaptive", "--fallback", "same-host", "--user", "operator",
                           "--verification", "cross-host-once", "--platforms", "Claude Code, Codex")
    append_discovery(allowed, discovery("D-A-001", "VERIFIED", review, session=None))
    assert severities(check(allowed))["ERROR"] == 0
    waiting = make_project(tmp_path, "wait", "--platform", "adaptive", "--fallback", "wait", "--user", "operator",
                           "--verification", "cross-host-once", "--platforms", "Claude Code, Codex")
    append_discovery(waiting, discovery("D-A-001", "VERIFIED", review, session=None))
    checker = check(waiting)
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-001")]
    assert only(checker, "WARN") == ["discovery.review.ineligible"]


def test_hybrid_accepts_either_form(tmp_path) -> None:
    target = make_project(tmp_path, "hyb", "--preset", "competition-team", "--user", "operator",
                          "--competition", "hub/task-a", "--external-actions", "release-tool publish", "--phase-clock", "off")
    append_discovery(target, discovery("D-A-001", "VERIFIED", ["Codex (B): CLOSED — reproduced"], session=None))
    append_discovery(target, discovery("D-A-002", "VERIFIED", [f"Claude Code (A): CLOSED — reviewer {REVIEWER_A} — ok"]))
    append_discovery(target, discovery("D-A-003", "VERIFIED", ["Claude Code (A): CLOSED — reproduced"]))
    checker = check(target)
    assert errors_by_record(checker) == [("discovery.state.unbacked", "D-A-003")]
    assert [(i.check, i.record) for i in found(checker, "WARN")] == [("discovery.review.ineligible", "D-A-003")]


def test_self_needs_no_review(tmp_path) -> None:
    target = make_project(tmp_path, "self", "--preset", "quick", "--platforms", "Claude Code", "--user", "operator")
    append_discovery(target, discovery("D-A-001", "PENDING", [], session=None))
    append_discovery(target, discovery("D-A-002", "VERIFIED", ["Claude Code (A): CLOSED — checked my own work"],
                                       session=None))
    checker = check(target)
    assert severities(checker) == {"ERROR": 0, "WARN": 0, "INFO": 0}, [i.render() for i in checker.issues]


def test_pending_under_independent_review_is_never_an_error(tmp_path) -> None:
    target = independent_project(tmp_path)
    append_discovery(target, discovery("D-A-001", "PENDING", []))
    checker = check(target)
    assert checker.code == 0 and only(checker, "INFO") == ["discovery.review.pending"]
