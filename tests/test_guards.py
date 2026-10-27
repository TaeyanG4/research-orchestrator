"""Guard rules: evidence, applicability, severity, precedence and bounded output."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from conftest import NOW, append_discovery, append_events, check, check_project, event, found, item, run_init
from guard_helpers import (action, append_measurements, discovery, effort_events, instrument, plan, project,
                           review, section, setting, shared)

RULES = {
    "guard.instrument.missing": ("G1", "WARN", "ERROR"),
    "guard.instrument.circular": ("G1", "WARN", "ERROR"),
    "guard.instrument.insample": ("G1", "WARN", "WARN"),
    "guard.instrument.schema": ("G1", "WARN", "ERROR"),
    "guard.family.saturated": ("G3", "WARN", "ERROR"),
    "guard.override.open": ("G5", "INFO", "INFO"),
    "guard.override.recheck": ("G5", "WARN", "ERROR"),
    "guard.rejection.evidence": ("G5", "WARN", "ERROR"),
    "guard.insight.overdue": ("G6", "WARN", "ERROR"),
    "guard.insight.rejection": ("G6", "WARN", "WARN"),
    "guard.direction.stale": ("GD", "WARN", "ERROR"),
    "guard.direction.incomplete": ("GD", "WARN", "ERROR"),
    "guard.phase.milestone": ("G8", "WARN", "WARN"),
    "guard.selection.rationale": ("G11", "WARN", "ERROR"),
    "guard.effort.share": ("G12", "INFO", "WARN"),
    "ext.expected": ("E1", "WARN", "ERROR"),
    "ext.duplicate": ("E1", "WARN", "ERROR"),
    "guard.new-best.consistency": ("G1", "INFO", "INFO"),
}


def guard_issues(checker):
    return [issue for issue in checker.issues if issue.check.startswith(("guard.", "ext."))]


def case(parent, check_id: str, counter: bool = False, mode: str = "light"):
    guard = RULES[check_id][0]
    guards = "G1, G6" if check_id == "guard.insight.rejection" else guard
    target = project(parent, guards, mode)
    if check_id == "guard.instrument.missing":
        section(target, "Instruments", instrument())
        fields = {"Instrument": "I-A-01"} if counter else {}
        append_discovery(target, discovery(Decision_class="model-change", **fields))
    elif check_id == "guard.instrument.circular":
        section(target, "Instruments", instrument(provenance="independent" if counter else "derived-from-targets",
                                                   not_for="none" if counter else "target-change"))
        append_discovery(target, discovery(Decision_class="target-change", Instrument="I-A-01"))
    elif check_id == "guard.instrument.insample":
        section(target, "Instruments", instrument(coverage="held-out" if counter else "in-sample"))
        append_discovery(target, discovery(Decision_class="input-change", Instrument="I-A-01"))
    elif check_id == "guard.instrument.schema":
        section(target, "Instruments", instrument(provenance="own-lineage",
                                                   not_for="target-change, model-change" if counter else "target-change"))
    elif check_id == "guard.family.saturated":
        section(target, "Instruments", instrument())
        append_measurements(target)
        fields = [("Family", "family-a")]
        if counter:
            append_discovery(target, review("D-A-006"))
            fields.append(("Saturation exit", "structural: replace the core procedure (review D-A-006)"))
        plan(target, item("H-A-01", extra=fields))
    elif check_id in {"guard.override.open", "guard.override.recheck"}:
        trigger = "" if check_id == "guard.override.recheck" and not counter else "; re-check: independent result changes"
        append_discovery(target, discovery(Override="registered rule said stop; decided proceed because scope changed" +
                                          trigger + "; expires 2026-10-30"))
        if check_id == "guard.override.open" and counter:
            append_discovery(target, discovery("D-A-002", Override_resolved="D-A-001"))
    elif check_id == "guard.rejection.evidence":
        fields = {"Rejected_on": "I-A-01; fired: trace D-Z-990 confirms execution"} if counter else {}
        append_discovery(target, discovery(finding="the claimed benefit does not hold", Decision_class="input-change",
                                          **fields))
    elif check_id == "guard.insight.overdue":
        append_discovery(target, discovery(Kind="insight", Status="open",
                                          Due="2026-10-25 20:00" if counter else "2026-10-24 12:00"))
    elif check_id == "guard.insight.rejection":
        section(target, "Instruments", instrument(agreement="0.91 agreement, D-Z-990" if counter else "unmeasured"))
        append_discovery(target, discovery(Decision_class="model-change", Instrument="I-A-01"))
        append_discovery(target, discovery("D-A-002", Kind="insight", Due="2026-10-25 20:00",
                                          Status="rejected — D-A-001 shows the diagnosis is unsupported"))
    elif check_id == "guard.direction.stale":
        append_events(target, event("2026-10-24 12:00", "A", "H-A-01"))
        if counter:
            append_discovery(target, review())
            shared(target, "Last direction review", "D-A-001 (2026-10-24)")
    elif check_id == "guard.direction.incomplete":
        append_discovery(target, review(omit=None if counter else "Decisions"))
        shared(target, "Last direction review", "D-A-001 (2026-10-24)")
    elif check_id == "guard.phase.milestone":
        setting(target, "Phase clock", "start 2026-10-01, deadline 2026-10-31")
        state = "complete" if counter else "pending"
        shared(target, "Milestones", "; ".join(f"{share} {state}" for share in (10, 25, 75)))
    elif check_id == "guard.selection.rationale":
        section(target, "External actions", action() + "\n" + action("X-A-002", artifact_hash="abc002"))
        explanation = "; rationale: independent cohort evidence favors both" if counter else ""
        shared(target, "Final picks", "X-A-001, X-A-002 (families: family-a, family-a" + explanation + ")")
    elif check_id == "guard.effort.share":
        effort_events(target, ["research", "research", "research"] if counter else ["infra", "process", None])
    elif check_id == "ext.expected":
        section(target, "External actions", action(expected="quality above 0.80 (written 2026-10-24 08:00)"
                                                     if counter else None))
    elif check_id == "ext.duplicate":
        section(target, "External actions", action() + "\n" + action(
            "X-A-002", retry="X-A-001" if counter else None,
            expected="quality above 0.80 (written 2026-10-24 10:00)",
            result="quality=0.81 on I-A-01 cohort stable (observed 2026-10-24 11:00)"))
    elif check_id == "guard.new-best.consistency":
        fields = {"Consistency": "4/5 cohorts"} if counter else {}
        append_discovery(target, discovery(implication="new current best: quality=0.81", **fields))
        shared(target, "Current best", "quality=0.81 (D-A-001)")
    else:
        raise AssertionError(check_id)
    return target


@pytest.mark.parametrize("check_id", RULES)
def test_each_rule_fires_on_a_minimal_record(tmp_path, check_id) -> None:
    checker = check(case(tmp_path, check_id))
    issues = found(checker, check_id=check_id)
    assert issues, [issue.render() for issue in checker.issues]
    assert {issue.severity for issue in issues} == {RULES[check_id][1]}
    assert all(issue.severity != "ERROR" for issue in guard_issues(checker))
    assert not found(checker, "ERROR"), [issue.render() for issue in checker.issues]


@pytest.mark.parametrize("check_id", RULES)
def test_each_rule_has_a_counter_record(tmp_path, check_id) -> None:
    checker = check(case(tmp_path, check_id, counter=True))
    assert not found(checker, check_id=check_id), [issue.render() for issue in checker.issues]
    if check_id == "guard.family.saturated":
        assert not found(checker, "ERROR")


@pytest.mark.parametrize("check_id", RULES)
def test_each_rule_is_silenced_by_the_shared_applicability_declaration(tmp_path, check_id) -> None:
    target = case(tmp_path, check_id)
    shared(target, "Not applicable", f"{RULES[check_id][0]} — this record is outside the project's decision process")
    assert not found(check(target), check_id=check_id)


@pytest.mark.parametrize("check_id", RULES)
def test_strict_guard_mode_changes_exactly_the_specified_cells(tmp_path, check_id) -> None:
    checker = check(case(tmp_path, check_id, mode="strict"))
    issues = found(checker, check_id=check_id)
    assert issues and {issue.severity for issue in issues} == {RULES[check_id][2]}


@pytest.mark.parametrize("decision_class", ["operational", "other"])
def test_operational_and_other_findings_need_no_decision_instrument_or_rejection(tmp_path, decision_class) -> None:
    target = project(tmp_path, "G1, G5")
    append_discovery(target, discovery(finding="the change does not hold", Decision_class=decision_class))
    assert not [issue for issue in guard_issues(check(target)) if issue.check != "guard.since.exempt"]


@pytest.mark.parametrize("provenance,not_for", [("derived-from-targets", "none"), ("own-lineage", "model-change")])
def test_schema_enforces_provenance_exclusions(tmp_path, provenance, not_for) -> None:
    target = project(tmp_path)
    section(target, "Instruments", instrument(provenance=provenance, not_for=not_for))
    assert found(check(target), check_id="guard.instrument.schema")


@pytest.mark.parametrize("dynamics,resolution", [(None, "±0.01 (D-Z-991)"), ("refresh each day", "unmeasured")])
def test_external_feedback_requires_dynamics_and_numeric_resolution(tmp_path, dynamics, resolution) -> None:
    target = project(tmp_path)
    section(target, "Instruments", instrument(provenance="external-feedback", coverage="external",
                                               dynamics=dynamics, resolution=resolution))
    assert found(check(target), check_id="guard.instrument.schema")


def test_only_one_measured_eligible_instrument_is_needed(tmp_path) -> None:
    target = project(tmp_path)
    section(target, "Instruments", instrument(provenance="derived-from-targets", not_for="target-change") +
            instrument("I-A-02", agreement="unmeasured") + instrument("I-A-03"))
    append_discovery(target, discovery(Decision_class="target-change", Instrument="I-A-01, I-A-02, I-A-03"))
    assert not found(check(target), check_id="guard.instrument.circular")


def test_an_unmeasured_eligible_instrument_cannot_rescue_a_derived_panel(tmp_path) -> None:
    target = project(tmp_path)
    section(target, "Instruments", instrument(provenance="derived-from-targets", not_for="target-change") +
            instrument("I-A-02", agreement="unmeasured"))
    append_discovery(target, discovery(Decision_class="target-change", Instrument="I-A-01, I-A-02"))
    assert found(check(target), check_id="guard.instrument.circular")


@pytest.mark.parametrize("part", ["metric", "instrument", "cohort"])
def test_saturation_requires_the_same_comparable_measurement_key(tmp_path, part) -> None:
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument() + instrument("I-A-02"))
    for index in range(5):
        metric = f"quality{index}" if part == "metric" else "quality"
        iid = "I-A-02" if part == "instrument" and index == 4 else "I-A-01"
        cohort = f"cohort{index}" if part == "cohort" else "stable"
        append_discovery(target, discovery(f"D-A-{index + 1:03}", Family="family-a",
                                          Result=f"{metric}=0.81 on {iid} cohort {cohort}"))
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert not found(check(target), check_id="guard.family.saturated")


def test_metric_names_with_a_shared_last_word_are_distinct_series(tmp_path) -> None:
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument())
    for number in range(5):
        metric = "error rate" if number < 4 else "success rate"
        append_discovery(target, discovery(f"D-A-{number + 1:03}", Family="family-a",
                                          Result=f"{metric}=0.81 on I-A-01 cohort stable"))
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert not found(check(target), check_id="guard.family.saturated")


def test_saturation_uses_range_not_two_times_resolution(tmp_path) -> None:
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument(resolution="±0.01 (D-Z-991)"))
    append_measurements(target, values=[0.800, 0.800, 0.800, 0.800, 0.815])
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert not found(check(target), check_id="guard.family.saturated")


def test_saturation_threshold_is_configurable(tmp_path) -> None:
    target = project(tmp_path, "G3")
    setting(target, "Guard thresholds", "saturation=3")
    section(target, "Instruments", instrument())
    append_measurements(target, count=3)
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert found(check(target), check_id="guard.family.saturated")


def test_an_instrument_saturation_exit_is_accepted(tmp_path) -> None:
    target = case(tmp_path, "guard.family.saturated")
    section(target, "Instruments", instrument("I-A-02"))
    plan(target, item("H-A-01", extra=[("Family", "family-a"), ("Saturation exit", "instrument I-A-02")]))
    assert not found(check(target), check_id="guard.family.saturated")


def test_saturation_orders_by_record_date_before_file_order(tmp_path) -> None:
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument())
    for index, (day, value) in enumerate([(24, 0.81), (20, 0.70), (21, 0.81), (22, 0.81), (23, 0.81), (25, 0.81)]):
        append_discovery(target, discovery(f"D-A-{index + 1:03}", date=f"2026-10-{day}", Family="family-a",
                                          Result=f"quality={value} on I-A-01 cohort stable"))
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert found(check(target), check_id="guard.family.saturated")


@pytest.mark.parametrize("last_value,saturated", [(0.81, True), (0.70, False)])
def test_saturation_uses_file_order_when_record_dates_tie(tmp_path, last_value, saturated) -> None:
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument())
    values = [0.70, 0.81, 0.81, 0.81, 0.81, last_value]
    for index, value in enumerate(values):
        append_discovery(target, discovery(f"D-A-{index + 1:03}", Family="family-a",
                                          Result=f"quality={value} on I-A-01 cohort stable"))
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert bool(found(check(target), check_id="guard.family.saturated")) is saturated


def test_saturation_combines_discoveries_with_the_external_actions_ledger(tmp_path) -> None:
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument())
    append_measurements(target, count=3)
    section(target, "External actions", action() + action("X-A-002", artifact_hash="abc002"))
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    assert found(check(target), check_id="guard.family.saturated")


def test_rejection_instrument_alone_does_not_prove_execution(tmp_path) -> None:
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(finding="the claimed benefit does not hold", Decision_class="model-change",
                                      Rejected_on="I-A-01"))
    assert found(check(target), check_id="guard.rejection.evidence")


def test_override_needs_a_valid_expiry_as_well_as_a_trigger(tmp_path) -> None:
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(Override="rule said stop; decided proceed because scope; re-check: new result"))
    assert found(check(target), check_id="guard.override.recheck")


def test_an_expired_override_still_needs_recheck_with_a_trigger(tmp_path) -> None:
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(Override="rule said stop; decided proceed because of scope; re-check: changed gap; "
                                      "expires 2026-10-24"))
    assert found(check(target), check_id="guard.override.recheck")


def test_a_resolved_override_is_no_longer_open_or_overdue(tmp_path) -> None:
    target = case(tmp_path, "guard.override.recheck")
    append_discovery(target, discovery("D-A-002", Override_resolved="D-A-001"))
    checker = check(target)
    assert not found(checker, check_id="guard.override.open") and not found(checker, check_id="guard.override.recheck")


def test_a_resolution_dated_before_the_override_does_not_close_it(tmp_path) -> None:
    target = case(tmp_path, "guard.override.open")
    append_discovery(target, discovery("D-A-002", date="2026-10-23", Override_resolved="D-A-001"))
    assert found(check(target), check_id="guard.override.open")


def test_a_later_dated_resolution_closes_even_when_earlier_in_file_order(tmp_path) -> None:
    target = project(tmp_path, "G5")
    append_discovery(target, discovery("D-A-002", date="2026-10-24", Override_resolved="D-A-001"))
    append_discovery(target, discovery(date="2026-10-23", Override="rule said stop; decided proceed because of scope; "
                                      "re-check: changed gap; expires 2026-10-24"))
    checker = check(target)
    assert not found(checker, check_id="guard.override.open") and not found(checker, check_id="guard.override.recheck")


def test_a_planned_insight_requires_an_existing_or_completed_item(tmp_path) -> None:
    target = project(tmp_path, "G6")
    append_discovery(target, discovery(Kind="insight", Status="planned H-A-01", Due="2026-10-24 12:00"))
    assert found(check(target), check_id="guard.insight.overdue")
    plan(target, item("H-A-01"))
    assert not found(check(target), check_id="guard.insight.overdue")


def test_stage_progress_does_not_complete_a_planned_insights_missing_item(tmp_path) -> None:
    target = project(tmp_path, "G6")
    append_discovery(target, discovery(Kind="insight", Status="planned H-A-01", Due="2026-10-24 12:00"))
    append_events(target, event("2026-10-24 10:00", "A", "H-A-01/s1"))
    assert found(check(target), check_id="guard.insight.overdue")
    append_events(target, event("2026-10-24 11:00", "A", "H-A-01"))
    assert not found(check(target), check_id="guard.insight.overdue")


def test_insight_due_cannot_bypass_the_threshold(tmp_path) -> None:
    target = project(tmp_path, "G6")
    append_discovery(target, discovery(Kind="insight", Status="open", Due="2026-11-01 12:00"))
    assert found(check(target), check_id="guard.insight.overdue")


def test_the_first_direction_review_needs_a_data_audit(tmp_path) -> None:
    target = project(tmp_path, "GD")
    append_discovery(target, review(omit="Data audit"))
    shared(target, "Last direction review", "D-A-001 (2026-10-24)")
    assert found(check(target), check_id="guard.direction.incomplete")


def test_later_direction_reviews_can_reuse_the_first_data_audit(tmp_path) -> None:
    target = project(tmp_path, "GD")
    append_discovery(target, review(date="2026-10-20"))
    append_discovery(target, review("D-A-002", omit="Data audit"))
    shared(target, "Last direction review", "D-A-002 (2026-10-24)")
    assert not found(check(target), check_id="guard.direction.incomplete")


def test_direction_parts_need_a_reason_for_inapplicability(tmp_path) -> None:
    target = project(tmp_path, "GD", profile="competition")
    append_discovery(target, review().replace("- Intake: no new methods seen", "- Intake: not applicable"))
    assert found(check(target), check_id="guard.direction.incomplete")


def test_direction_review_parts_accept_explained_inapplicability(tmp_path) -> None:
    target = project(tmp_path, "GD", profile="work")
    fields = {name: "not applicable — a direct operational decision" for name in
              ("Gap", "Decomposition", "Core_families", "Data_audit", "Intake", "Rejected_consistent_gains", "Decisions")}
    append_discovery(target, discovery(Kind="direction-review", **fields))
    shared(target, "Last direction review", "D-A-001 (2026-10-24)")
    assert not [issue for issue in guard_issues(check(target)) if issue.check != "guard.since.exempt"]


def test_direction_review_age_threshold_is_configurable(tmp_path) -> None:
    target = project(tmp_path, "GD")
    setting(target, "Guard thresholds", "direction-review=2d")
    append_discovery(target, review(date="2026-10-20"))
    shared(target, "Last direction review", "D-A-001 (2026-10-20)")
    assert found(check(target), check_id="guard.direction.stale")


def test_phase_clock_off_silences_milestones(tmp_path) -> None:
    target = case(tmp_path, "guard.phase.milestone")
    setting(target, "Phase clock", "off")
    assert not found(check(target), check_id="guard.phase.milestone")


def test_effort_reports_unknown_events_without_inventing_their_tags(tmp_path) -> None:
    checker = check(case(tmp_path, "guard.effort.share"))
    issue = found(checker, check_id="guard.effort.share")[0]
    assert "unknown" in issue.message.lower() and "1" in issue.message


def test_outward_result_uses_the_observed_timestamp_not_dates_in_its_description(tmp_path) -> None:
    target = project(tmp_path, "E1")
    section(target, "External actions", action(expected=None,
            result="reference from 2020-01-01; quality 0.81 (observed 2026-10-24 09:00)"))
    assert found(check(target), check_id="ext.expected")


@pytest.mark.parametrize("expected", ["written 2026-10-24 09:00", "written 2026-10-24 10:00"])
def test_expectation_must_precede_result_not_equal_it(tmp_path, expected) -> None:
    target = project(tmp_path, "E1")
    section(target, "External actions", action(expected=f"quality above 0.80 ({expected})"))
    assert found(check(target), check_id="ext.expected")


def test_actions_to_different_destinations_are_not_duplicates(tmp_path) -> None:
    target = project(tmp_path, "E1")
    section(target, "External actions", action() + action("X-A-002", destination="another endpoint"))
    assert not found(check(target), check_id="ext.duplicate")


def test_historical_final_picks_are_exempt(tmp_path) -> None:
    target = project(tmp_path, "G11")
    setting(target, "Guards", "light since 2026-10-25")
    section(target, "External actions", action() + action("X-A-002", artifact_hash="abc002"))
    shared(target, "Final picks", "X-A-001, X-A-002 (families: family-a)")
    assert not found(check(target), check_id="guard.selection.rationale")


def test_consistency_accepts_an_explicit_not_applicable_value(tmp_path) -> None:
    target = project(tmp_path)
    append_discovery(target, discovery(implication="new current best: one-time approval",
                                      Consistency="not applicable — a single irreversible decision"))
    shared(target, "Current best", "approved (D-A-001)")
    assert not found(check(target), check_id="guard.new-best.consistency")


def test_the_run_strict_flag_fails_on_a_light_guard_warning(tmp_path) -> None:
    target = case(tmp_path, "guard.instrument.missing")
    checker = check_project.Checker(target, now=NOW)
    assert checker.run(quiet=True) == 0
    strict_checker = check_project.Checker(target, now=NOW)
    assert strict_checker.run(quiet=True, strict=True) == 1
    assert found(strict_checker, "WARN", "guard.instrument.missing")


def test_a_baseline_never_hides_or_downgrades_a_guard_warning(tmp_path) -> None:
    target = case(tmp_path, "guard.instrument.missing")
    initial = check_project.Checker(target, now=NOW)
    assert initial.run(quiet=True, baseline_update=True) == 0
    current = check_project.Checker(target, now=NOW)
    assert current.run(quiet=True, strict=True) == 1
    assert found(current, "WARN", "guard.instrument.missing") and not found(current, check_id="baseline.new")


def test_new_since_baseline_warns_even_for_an_info_guard_and_strict_fails(tmp_path) -> None:
    target = project(tmp_path)
    initial = check_project.Checker(target, now=NOW)
    assert initial.run(quiet=True, baseline_update=True) == 0
    append_discovery(target, discovery(implication="new current best: quality=0.81"))
    shared(target, "Current best", "quality=0.81 (D-A-001)")
    current = check_project.Checker(target, now=NOW)
    assert current.run(quiet=True, strict=True) == 1
    assert found(current, "INFO", "guard.new-best.consistency") and found(current, "WARN", "baseline.new")


def test_two_hundred_historical_discoveries_generate_one_info_line(tmp_path, capsys) -> None:
    target = project(tmp_path)
    setting(target, "Guards", "light since 2026-10-25")
    for number in range(205):
        append_discovery(target, discovery(f"D-A-{number + 1:03}", date="2026-10-24", Decision_class="model-change"))
    checker = check_project.Checker(target, now=NOW)
    checker.run()
    lines = [line for line in capsys.readouterr().out.splitlines() if re.search(r"\b(?:guard\.|ext\.)", line)]
    assert len(lines) == 1 and "INFO" in lines[0] and "207" in lines[0]
    assert not found(checker, "WARN") and not found(checker, "ERROR")


def test_the_since_day_is_included_and_older_actions_and_events_are_counted(tmp_path) -> None:
    target = project(tmp_path, "G1, E1, G12")
    setting(target, "Guards", "light since 2026-10-24")
    append_discovery(target, discovery(date="2026-10-24", Decision_class="model-change"))
    append_discovery(target, discovery("D-A-002", date="2026-10-23", Decision_class="model-change"))
    section(target, "External actions", action(expected=None,
                                               result="quality=0.81 (observed 2026-10-23 09:00)"))
    append_events(target, event("2026-10-23 10:00", "A", "none", extra="- Effort: infra\n"))
    checker = check(target)
    assert [issue.record for issue in found(checker, check_id="guard.instrument.missing")] == ["D-A-001"]
    assert not found(checker, check_id="ext.expected")
    exempt = found(checker, "INFO", "guard.since.exempt")
    assert len(exempt) == 1 and "5" in exempt[0].message


def test_each_guard_check_renders_once_with_count_and_at_most_three_example_ids(tmp_path, capsys) -> None:
    target = project(tmp_path)
    for number in range(8):
        append_discovery(target, discovery(f"D-A-{number + 1:03}", Decision_class="model-change"))
    checker = check_project.Checker(target, now=NOW)
    checker.run()
    lines = [line for line in capsys.readouterr().out.splitlines() if "guard.instrument.missing" in line]
    assert len(lines) == 1 and "8" in lines[0]
    assert len(set(re.findall(r"\bD-A-\d+\b", lines[0]))) <= 3
    assert len(found(checker, check_id="guard.instrument.missing")) == 8  # fingerprints remain per record


def dated_action(xid, day, **kwargs):
    return action(xid, expected=f"quality above 0.80 (written 2026-10-{day} 08:00)",
                  result=f"quality=0.81 on I-A-01 cohort stable (observed 2026-10-{day} 09:00)", **kwargs)


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_identity_is_chronological_in_both_file_orders(tmp_path, reverse):
    target = project(tmp_path, "E1")
    records = [dated_action("X-A-002", 23), dated_action("X-A-001", 24)]
    section(target, "External actions", "\n".join(reversed(records) if reverse else records))
    checker = check(target)
    assert [i.record for i in found(checker, check_id="ext.duplicate")] == ["X-A-001"]


@pytest.mark.parametrize("reverse", [False, True])
def test_active_duplicate_is_found_when_historical_original_is_last(tmp_path, reverse):
    target = project(tmp_path, "E1")
    setting(target, "Guards", "light since 2026-10-24")
    records = [dated_action("X-A-002", 23), dated_action("X-A-001", 24)]
    section(target, "External actions", "\n".join(reversed(records) if reverse else records))
    assert [i.record for i in found(check(target), check_id="ext.duplicate")] == ["X-A-001"]


@pytest.mark.parametrize("case", ["forward", "cyclic", "same-time", "different-identity", "dangling", "self"])
def test_retry_requires_an_earlier_matching_acyclic_action(tmp_path, case):
    target = project(tmp_path, "E1")
    first_retry = "X-A-002" if case in {"forward", "cyclic"} else None
    second_retry = {"dangling": "X-A-999", "self": "X-A-002"}.get(case, "X-A-001")
    first = dated_action("X-A-001", 23, retry=first_retry)
    second = dated_action("X-A-002", 23 if case == "same-time" else 24, retry=second_retry,
                          artifact_hash="other" if case == "different-identity" else "abc001")
    if case == "forward":
        second = dated_action("X-A-002", 24)
    section(target, "External actions", second + first)
    checker = check(target)
    invalid = {i.record for i in found(checker, "ERROR", "external.retry.invalid")}
    assert invalid == ({"X-A-001", "X-A-002"} if case == "cyclic" else
                       {"X-A-001"} if case == "forward" else {"X-A-002"})
    if case == "different-identity":
        assert not found(checker, check_id="ext.duplicate")


def test_retry_to_an_earlier_action_survives_reversed_order(tmp_path):
    target = project(tmp_path, "E1")
    section(target, "External actions", dated_action("X-A-002", 24, retry="X-A-001") +
            dated_action("X-A-001", 23))
    checker = check(target)
    assert not found(checker, check_id="ext.duplicate")
    assert not found(checker, "ERROR")


def test_action_chronology_uses_observed_time_even_if_forecasts_were_written_in_reverse(tmp_path):
    target = project(tmp_path, "E1")
    first = dated_action("X-A-001", 23)
    second = dated_action("X-A-002", 24, retry="X-A-001").replace(
        "written 2026-10-24 08:00", "written 2026-10-22 08:00")
    section(target, "External actions", second + first)
    checker = check(target)
    assert not found(checker, check_id="ext.duplicate")
    assert not found(checker, "ERROR")


@pytest.mark.parametrize("field,mode", [
    *[(field, "light") for field in ("Kind", "Candidate", "Destination", "Expected", "Result", "Final", "Status")],
    ("Kind", "off"), ("Kind", "strict"), ("Expected", "off"),
])
def test_external_required_fields_follow_guard_mode(tmp_path, field, mode):
    target = project(tmp_path, "E1")
    setting(target, "Guards", mode)
    section(target, "External actions", re.sub(rf"^- {field}:.*\n", "", action(), flags=re.M))
    checker = check(target)
    check_id = "ext.expected" if field == "Expected" else "external.field.missing"
    if mode == "off":
        assert not found(checker, check_id=check_id)
    else:
        severity = "ERROR" if mode == "strict" else "WARN"
        assert {i.field for i in found(checker, severity, check_id)} == {field}
        if mode == "light":
            assert not found(checker, "ERROR")
    if field == "Expected":
        assert not found(checker, check_id="external.field.missing")
        if mode != "off":
            assert {issue.check for issue in checker.issues if issue.severity != "INFO"} == {"ext.expected"}


@pytest.mark.parametrize("field,value,mode,severity", [
    ("Kind", "unknown", "light", "WARN"), ("Kind", "unknown", "strict", "ERROR"),
    *[(field, value, "light", "WARN") for field, value in [
        ("Candidate", "candidate without identity"), ("Destination", ""),
        ("Expected", "quality above 0.80"), ("Expected", "quality (written 2026-02-30 08:00)"),
        ("Result", ""), ("Result", "quality above 0.80"), ("Final", ""), ("Status", "unrecognized"),
        ("Result", "(observed 2026-10-24 09:00)"), ("Expected", "(written 2026-10-24 08:00)"),
    ]],
])
def test_external_schema_rejects_malformed_field_values(tmp_path, field, value, mode, severity):
    target = project(tmp_path, "E1", mode=mode)
    section(target, "External actions", re.sub(rf"^- {field}:.*$", f"- {field}: {value}", action(), flags=re.M))
    checker = check(target)
    check_id = "ext.expected" if field == "Expected" else "external.field.invalid"
    assert field in {i.field for i in found(checker, severity, check_id)}
    if mode == "light":
        assert not found(checker, "ERROR")


@pytest.mark.parametrize("xid", ["X-A-01", "X-a-001", "X-AAA-001", "not-an-id"])
def test_external_schema_requires_a_slot_prefixed_three_digit_id(tmp_path, xid):
    target = project(tmp_path, "E1")
    section(target, "External actions", action(xid))
    assert found(check(target), "ERROR", "external.id.format")


def test_external_schema_reports_field_order_and_unknown_fields_as_info(tmp_path):
    target = project(tmp_path, "E1")
    text = action().replace("- Kind: release\n", "").replace("- Final: pending", "- Kind: release\n- Final: pending")
    section(target, "External actions", text + "- Local note: preserved extension\n")
    checker = check(target)
    assert found(checker, "INFO", "external.field.order")
    assert found(checker, "INFO", "external.field.unknown")
    assert not found(checker, "ERROR")


def test_missing_result_is_not_explicit_pending(tmp_path):
    target = project(tmp_path, "E1")
    pending = action(result="pending")
    section(target, "External actions", pending)
    assert not found(check(target), check_id="ext.expected")
    path = target / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Result: pending\n", ""), encoding="utf-8")
    checker = check(target)
    assert found(checker, "WARN", "external.field.missing")
    assert not found(checker, "ERROR")
    assert found(checker, check_id="ext.expected")


def test_duplicate_identity_uses_the_artifact_hash_after_the_candidate_name(tmp_path):
    target = project(tmp_path, "E1")
    records = dated_action("X-A-001", 23).replace("Candidate: candidate,", "Candidate: hash draft,")
    records += dated_action("X-A-002", 24).replace("Candidate: candidate,", "Candidate: hash final,")
    section(target, "External actions", records)
    checker = check(target)
    assert [i.record for i in found(checker, check_id="ext.duplicate")] == ["X-A-002"]
    assert not found(checker, "ERROR")


@pytest.mark.parametrize("field", ["Agreement", "Resolution"])
def test_instrument_evidence_must_resolve_and_never_counts_when_dangling(tmp_path, field):
    target = project(tmp_path, "G1, G3")
    value = "0.91 agreement, D-A-999" if field == "Agreement" else "±0.01 (D-A-999)"
    section(target, "Instruments", instrument(**{field.lower(): value}))
    append_discovery(target, discovery(Decision_class="model-change", Instrument="I-A-01"))
    append_measurements(target, start=2)
    plan(target, item("H-A-01", extra=[("Family", "family-a")]))
    checker = check(target)
    assert found(checker, "ERROR", "evidence.discovery.dangling")
    if field == "Agreement":
        assert found(checker, check_id="guard.instrument.circular")
    else:
        assert not found(checker, check_id="guard.family.saturated")


def test_dangling_rejection_does_not_supply_execution_evidence(tmp_path):
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(finding="the change does not hold", Decision_class="model-change",
                                      Rejected_on="I-A-01; fired: trace D-A-999"))
    checker = check(target)
    assert found(checker, "ERROR", "evidence.discovery.dangling")
    assert found(checker, check_id="guard.rejection.evidence")


@pytest.mark.parametrize("part", ["Gap", "Decomposition", "Core families", "Data audit", "Intake",
                                  "Rejected consistent gains", "Decisions"])
def test_direction_evidence_parts_reject_dangling_discoveries(tmp_path, part):
    target = project(tmp_path, "GD", profile="competition")
    text = re.sub(rf"^- {part}:.*$", f"- {part}: supported by D-A-999", review(), flags=re.M)
    append_discovery(target, text)
    checker = check(target)
    assert found(checker, "ERROR", "evidence.discovery.dangling")
    assert found(checker, check_id="guard.direction.incomplete")


@pytest.mark.parametrize("exit_rule", ["instrument I-A-01", "instrument I-A-99",
                                      "structural: revise core (review D-A-999)",
                                      "structural:   (review D-A-001)",
                                      "structural: revise core (review D-A-001)"])
def test_saturation_exit_requires_a_different_existing_instrument_or_real_review(tmp_path, exit_rule):
    target = project(tmp_path, "G3")
    section(target, "Instruments", instrument())
    append_measurements(target)
    plan(target, item("H-A-01", extra=[("Family", "family-a"), ("Saturation exit", exit_rule)]))
    checker = check(target)
    assert found(checker, check_id="guard.family.saturated")
    if "D-A-999" in exit_rule:
        assert found(checker, "ERROR", "evidence.discovery.dangling")
    if "I-A-99" in exit_rule:
        assert found(checker, "ERROR", "evidence.instrument.dangling")


@pytest.mark.parametrize("status", [None, "done", "planned H-A-01 extra", "rejected — D-Z-990",
                                   "rejected — D-A-999 no support", "rejected — D-Z-990 also cites D-A-999"])
def test_invalid_insight_status_cannot_bypass_due_enforcement(tmp_path, status):
    target = project(tmp_path, "G6")
    fields = {"Status": status} if status is not None else {}
    append_discovery(target, discovery(Kind="insight", Due="2026-10-24 12:00", **fields))
    checker = check(target)
    if status and "D-A-999" in status:
        assert found(checker, "ERROR", "evidence.discovery.dangling")
    else:
        assert not found(checker, "ERROR")
    assert found(checker, "WARN", "guard.insight.overdue")


def test_rejected_insight_needs_real_evidence_and_reason(tmp_path):
    target = project(tmp_path, "G6")
    append_discovery(target, discovery(Kind="insight", Status="rejected — D-Z-990 contradicts the premise",
                                      Due="2026-10-24 12:00"))
    checker = check(target)
    assert not found(checker, "ERROR")
    assert not found(checker, check_id="guard.insight.overdue")


def test_recent_review_before_activation_still_keeps_direction_fresh(tmp_path):
    target = project(tmp_path, "GD")
    setting(target, "Guards", "light since 2026-10-25")
    append_discovery(target, review(date="2026-10-24", omit="Intake"))
    checker = check(target)
    assert not found(checker, check_id="guard.direction.stale")
    assert not found(checker, check_id="guard.direction.incomplete")
    assert found(checker, "INFO", "guard.since.exempt")


def test_historical_incomplete_actions_and_insights_produce_one_info(tmp_path, capsys):
    target = project(tmp_path, "G1, G3, G5, G6, E1", mode="strict")
    setting(target, "Guards", "strict since 2026-10-25")
    records = []
    for number in range(100):
        records.append(re.sub(r"^- (Kind|Candidate|Destination|Final|Status):.*\n", "",
                              action(f"bad-{number}", expected=None, retry="X-A-999"), flags=re.M))
        append_discovery(target, discovery(f"D-A-{number + 1:03}", Kind="insight",
                                          Rejected_on="I-A-01; fired: D-A-999"))
    # Both physical occurrences of a historical duplicate count once, without a duplicate ERROR.
    records.append(records[0])
    section(target, "External actions", "\n".join(records))
    section(target, "Instruments", instrument("bad-id", agreement="D-A-999") + "- Date: 2026-10-24\n")
    checker = check_project.Checker(target, now=NOW)
    assert checker.run() == 0
    output = capsys.readouterr().out
    lines = [line for line in output.splitlines() if line.startswith("- ")]
    assert len(lines) == 1 and "INFO guard.since.exempt" in lines[0]
    assert "204" in lines[0]
    assert not found(checker, "ERROR") and not found(checker, "WARN")


def test_missing_insight_status_is_completeness_even_before_a_future_due(tmp_path):
    target = project(tmp_path, "G6")
    append_discovery(target, discovery(Kind="insight", Due="2026-10-25 20:00"))
    checker = check(target)
    assert found(checker, "WARN", "guard.insight.overdue")
    assert not found(checker, "ERROR")


@pytest.mark.parametrize("disabled", ["off", "not-applicable", "unselected"])
def test_schema_and_reference_checks_respect_applicability(tmp_path, disabled):
    target = project(tmp_path, "G1, G3, G5, G6, E1")
    section(target, "External actions", action("invalid-id", expected=None, retry="X-A-999") * 2)
    section(target, "Instruments", instrument("invalid-id", agreement="D-A-999") * 2)
    append_discovery(target, discovery(Kind="insight", Status="invalid", Rejected_on="D-A-999"))
    if disabled == "off":
        setting(target, "Guards", "off")
    elif disabled == "not-applicable":
        shared(target, "Not applicable", "; ".join(f"{g} — no measured decisions" for g in
                                                  ("G1", "G3", "G5", "G6", "E1")))
    else:
        setting(target, "Guard set", "G12")
    checker = check(target)
    assert not [i for i in checker.issues if i.severity in {"WARN", "ERROR"}], \
        [i.render() for i in checker.issues]


@pytest.mark.parametrize("mode", ["light", "strict"])
def test_schema_and_reference_diagnostics_are_aggregated_with_three_examples(tmp_path, capsys, mode):
    target = project(tmp_path, "G1, G3, G5, G6, E1", mode=mode)
    actions = []
    instruments = []
    items = []
    for number in range(8):
        text = action(f"bad-{number}", expected=None, retry="X-A-999")
        text = text.replace("- Kind: release\n", "").replace("- Status: complete", "- Status: invalid")
        text = text.replace("- Final: pending\n- Status: invalid", "- Status: invalid\n- Final: pending")
        text += "- Local note: extension\n"
        actions += [text, text]
        instruments.append(instrument(f"invalid-{number}", agreement="D-A-999"))
        items.append(item(f"H-A-{number + 1:02}", extra=[("Saturation exit", "instrument I-A-99")]))
        append_discovery(target, discovery(f"D-A-{number + 1:03}", Kind="insight", Status="invalid",
                                          Rejected_on="I-A-01; fired: D-A-999"))
    section(target, "External actions", "\n".join(actions))
    section(target, "Instruments", "\n".join(instruments))
    plan(target, *items)
    checker = check_project.Checker(target, now=NOW)
    checker.run()
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("- ")]
    checks = {i.check for i in checker.issues}
    assert {"external.field.missing", "external.field.invalid", "external.field.unknown", "external.field.order",
            "external.id.format", "external.retry.invalid", "handoff.id.duplicate", "instrument.id.format",
            "evidence.discovery.dangling", "evidence.instrument.dangling", "guard.insight.overdue", "ext.expected"} <= checks
    assert len(lines) == len(checks)
    for check_id in checks:
        grouped = [line for line in lines if f" {check_id}:" in line]
        assert len(grouped) == 1
        records = {issue.record for issue in checker.issues if issue.check == check_id and issue.record}
        displayed = {record for record in records
                     if re.search(rf"(?<![\w-]){re.escape(record)}(?![\w-])", grouped[0])}
        assert len(displayed) <= 3, grouped[0]
    errors = {i.check for i in found(checker, "ERROR")}
    if mode == "light":
        assert errors <= {"external.id.format", "instrument.id.format", "handoff.id.duplicate",
                          "external.retry.invalid", "evidence.discovery.dangling", "evidence.instrument.dangling"}


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_id_with_one_historical_record_reports_the_active_record(tmp_path, reverse):
    target = project(tmp_path, "E1")
    setting(target, "Guards", "light since 2026-10-24")
    old = action(retry="X-A-999").replace("2026-10-24", "2026-10-23")
    current = action()
    section(target, "External actions", current + old if reverse else old + current)
    checker = check(target)
    issues = found(checker, "ERROR", "handoff.id.duplicate")
    assert len(issues) == 1
    assert not found(checker, check_id="external.retry.invalid")
    assert issues[0].where.endswith(":" + str(next(b.line for b in checker.guard_records
                                                   if checker.record_day(b).isoformat() == "2026-10-24")))


@pytest.mark.parametrize("profile,preset", [("work", "work-project"), ("research", "solo-research")])
def test_ordinary_projects_without_guard_data_have_no_errors(tmp_path, profile, preset):
    target = tmp_path / profile
    target.mkdir()
    result = run_init(target, "-n", "ordinary", "--preset", preset, "--user", "operator",
                      "--platforms", "Claude Code")
    assert result.returncode == 0, result.stderr
    checker = check(target)
    assert not checker.external_actions and not checker.instruments and not checker.discoveries
    assert not found(checker, "ERROR"), [i.render() for i in checker.issues]
    assert found(checker, "INFO", "guard.direction.stale")
    assert not found(checker, "WARN"), [i.render() for i in checker.issues]


@pytest.mark.parametrize("mode", ["light", "strict"])
def test_first_direction_review_uses_activation_date_and_threshold(tmp_path, mode):
    target = project(tmp_path, "GD", mode=mode)
    append_events(target, event("2026-10-24 12:00", "A", "H-A-01"))
    setting(target, "Guards", f"{mode} since 2026-10-24")
    setting(target, "Guard thresholds", "direction-review=2d")
    before = check(target, dt.datetime(2026, 10, 25, 23, 59))
    assert found(before, "INFO", "guard.direction.stale")
    assert not found(before, "WARN") and not found(before, "ERROR")
    due = check(target, dt.datetime(2026, 10, 26))
    assert found(due, "ERROR" if mode == "strict" else "WARN", "guard.direction.stale")


def test_first_direction_review_uses_project_start_without_activation_date(tmp_path):
    target = project(tmp_path, "GD")
    append_events(target, event("2026-10-24 12:00", "A", "H-A-01"))
    path = target / "agents.md"
    path.write_text(path.read_text(encoding="utf-8").replace("light since 2026-10-01", "light"), encoding="utf-8")
    shared(target, "Started", "2026-10-24")
    assert found(check(target), "INFO", "guard.direction.stale")
    shared(target, "Started", "2026-10-01")
    assert found(check(target), "WARN", "guard.direction.stale")


@pytest.mark.parametrize("has_review", [False, True])
def test_paused_projects_suspend_direction_cadence_until_resumed(tmp_path, has_review):
    target = project(tmp_path, "GD")
    append_events(target, event("2026-10-24 12:00", "A", "H-A-01"))
    if has_review:
        append_discovery(target, review(date="2026-10-01"))
    assert found(check(target), "WARN", "guard.direction.stale")
    shared(target, "Paused", "2026-10-02")
    assert not found(check(target), check_id="guard.direction.stale")
    path = target / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Paused: 2026-10-02\n", ""), encoding="utf-8")
    assert found(check(target), "WARN", "guard.direction.stale")


@pytest.mark.parametrize("paused", ["2026-02-30", "later", "2026-10-26"])
def test_invalid_or_future_pause_cannot_silence_direction_review(tmp_path, paused):
    target = project(tmp_path, "GD")
    append_events(target, event("2026-10-24 12:00", "A", "H-A-01"))
    shared(target, "Paused", paused)
    checker = check(target)
    assert found(checker, "WARN", "guard.direction.pause.invalid")
    assert found(checker, "WARN", "guard.direction.stale")


def test_paused_project_still_checks_review_completeness(tmp_path):
    target = project(tmp_path, "GD")
    shared(target, "Paused", "2026-10-01")
    append_discovery(target, review(omit="Decisions"))
    assert found(check(target), "WARN", "guard.direction.incomplete")


def test_complete_coverage_accepts_exhaustive_measurements_without_weakening_provenance(tmp_path):
    target = project(tmp_path, "G1", mode="strict")
    section(target, "Instruments", instrument(coverage="complete"))
    append_discovery(target, discovery(Decision_class="input-change", Instrument="I-A-01",
                                      Control="not applicable — exhaustive measurement; alternative: analytic bound"))
    checker = check(target)
    assert not found(checker, "WARN") and not found(checker, "ERROR")
    path = target / "handoff.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Provenance: independent", "- Provenance: own-lineage"),
                    encoding="utf-8")
    assert found(check(target), "ERROR", "guard.instrument.schema")


@pytest.mark.parametrize("execution", ["trace.log confirms execution", "run 42 executed the change on 18 cases",
                                       "trace D-Z-990 confirms execution"])
def test_rejection_accepts_concrete_execution_evidence_with_optional_discovery(tmp_path, execution):
    target = project(tmp_path, "G5")
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(finding="the change does not hold", Decision_class="input-change",
                                      Rejected_on=f"I-A-01; fired: {execution}"))
    checker = check(target)
    assert not found(checker, check_id="guard.rejection.evidence")
    assert not found(checker, "ERROR")


@pytest.mark.parametrize("execution", ["", "n/a", "N/A.", "yes", "none", "pending", "tbd"])
def test_rejection_placeholders_are_not_execution_evidence(tmp_path, execution):
    target = project(tmp_path, "G5")
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(finding="the change does not hold", Decision_class="input-change",
                                      Rejected_on=f"I-A-01; fired: {execution}"))
    checker = check(target)
    assert found(checker, "WARN", "guard.rejection.evidence")
    assert not found(checker, "ERROR")


def test_rejection_dangling_optional_citation_remains_a_structural_error(tmp_path):
    target = project(tmp_path, "G5")
    append_discovery(target, discovery(finding="the change does not hold", Decision_class="input-change",
                                      Rejected_on="I-A-01; fired: trace.log confirms execution D-A-999"))
    checker = check(target)
    assert found(checker, "ERROR", "evidence.discovery.dangling")
    assert found(checker, check_id="guard.rejection.evidence")
