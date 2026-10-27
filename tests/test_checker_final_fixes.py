"""Decision outcomes and compact work records retain structural checks across prose languages."""

from __future__ import annotations

import pytest

from conftest import append_discovery, check, found, item, make_project
from guard_helpers import action, discovery, instrument, plan, project, section, shared


@pytest.mark.parametrize("finding", ["가설이 기각되었다", "仮説は支持されなかった", "The proposed change failed"])
@pytest.mark.parametrize("mode,severity", [("light", "WARN"), ("strict", "ERROR")])
def test_rejected_outcome_requires_execution_evidence_in_every_language(tmp_path, finding, mode, severity):
    target = project(tmp_path, "G5", mode=mode)
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(finding=finding, Decision_class="input-change", Outcome="rejected"))
    assert found(check(target), severity, "guard.rejection.evidence")
    path = target / "discoveries.md"
    path.write_text(path.read_text(encoding="utf-8") + "- Rejected on: I-A-01; fired: run.log records execution\n",
                    encoding="utf-8", newline="\n")
    assert not found(check(target), check_id="guard.rejection.evidence")


@pytest.mark.parametrize("outcome", ["supported", "inconclusive"])
def test_non_rejected_outcomes_do_not_require_rejection_evidence(tmp_path, outcome):
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(finding="the legacy claim does not hold", Decision_class="input-change",
                                      Outcome=outcome))
    assert not [i for i in check(target).issues if i.check.startswith(("guard.outcome", "guard.rejection"))]


@pytest.mark.parametrize("outcome", [None, "", "negative", "REJECTED"])
def test_missing_or_invalid_outcome_cannot_hide_localized_decision(tmp_path, outcome):
    target = project(tmp_path, "G5", mode="strict")
    fields = {} if outcome is None else {"Outcome": outcome}
    append_discovery(target, discovery(finding="가설이 기각되었다", Decision_class="input-change", **fields))
    check_id = "guard.outcome.missing" if outcome is None else "guard.outcome.invalid"
    assert found(check(target), "ERROR", check_id)


def test_legacy_english_rejection_still_checks_execution(tmp_path):
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(finding="the change does not hold", Decision_class="input-change"))
    assert found(check(target), check_id="guard.rejection.evidence")


@pytest.mark.parametrize("scope", ["operational", "other", "not-applicable"])
def test_outcome_requirement_respects_decision_applicability(tmp_path, scope):
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(Decision_class="input-change" if scope == "not-applicable" else scope))
    if scope == "not-applicable":
        shared(target, "Not applicable", "G5 — observational record has no decision")
    assert not [i for i in check(target).issues if i.check.startswith("guard.outcome")]


@pytest.mark.parametrize("verification", ["self", "independent-review"])
def test_only_self_verification_can_omit_review_fields(tmp_path, verification):
    target = make_project(tmp_path, "compact", "--preset", "quick", "--verification", verification,
                          "--platforms", "Claude Code")
    text = discovery().replace("- Cross-check: PENDING\n", "").replace("- Reviews: \n", "")
    append_discovery(target, text)
    issues = check(target).issues
    missing = {i.field for i in issues if i.check == "discovery.field.missing"}
    assert missing == ({"Cross-check", "Reviews"} if verification != "self" else set())
    assert not found(check(target), check_id="discovery.state.unknown")


def test_omitted_self_state_cannot_hide_a_standing_challenge(tmp_path):
    target = make_project(tmp_path, "challenged", "--preset", "quick", "--platforms", "Claude Code")
    text = discovery().replace("- Cross-check: PENDING\n", "")
    append_discovery(target, text + "  - Claude Code (A): CHALLENGED — evidence disagrees\n")
    assert found(check(target), "ERROR", "discovery.state.challenged")


@pytest.mark.parametrize("profile", ["work", "research"])
def test_next_step_alias_is_scoped_to_work(tmp_path, profile):
    target = project(tmp_path, "G5", profile=profile)
    plan(target, item("H-A-01").replace("- Next test:", "- Next step:"))
    issues = check(target).issues
    assert bool([i for i in issues if i.check == "plan.field.missing" and i.field == "Next test"]) == (profile != "work")


@pytest.mark.parametrize("status", ["in-flight", "unknown"])
def test_external_interruption_states_are_valid_checker_values(tmp_path, status):
    target = project(tmp_path, "E1")
    section(target, "External actions", action().replace("- Status: complete", f"- Status: {status}"))
    assert not [i for i in check(target).issues if i.check == "external.field.invalid" and i.field == "Status"]
