"""Active instrument references, retry ancestry and authoritative selection families."""

import re

import pytest

from conftest import append_discovery, check, found
from guard_helpers import action, discovery, instrument, project, section, setting, shared


@pytest.mark.parametrize("field,guard,value", [
    ("Instrument", "G1", "I-A-01, I-A-99"),
    ("Instrument", "G3", "I-A-01, I-A-99"),
    ("Rejected_on", "G5", "I-A-99; fired: trace confirms execution"),
    ("Result", "G1", "quality=0.8 on I-A-01 cohort stable; quality=0.9 on I-A-99 cohort stable"),
    ("Result", "G3", "quality=0.8 on I-A-99 cohort stable"),
])
@pytest.mark.parametrize("exemption", [None, "historical", "disabled", "inapplicable"])
@pytest.mark.parametrize("mode", ["light", "strict"])
def test_active_instrument_citations_resolve(tmp_path, field, guard, value, exemption, mode):
    target = project(tmp_path, guard, mode=mode)
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(date="2026-09-30" if exemption == "historical" else "2026-10-24",
                                      **{field: value}))
    if exemption == "disabled":
        setting(target, "Guards", "off")
    if exemption == "inapplicable":
        shared(target, "Not applicable", f"{guard} — no applicable decision")
    issues = found(check(target), "ERROR", "evidence.instrument.dangling")
    assert [(issue.record, issue.field) for issue in issues] == (
        [] if exemption else [("D-A-001", field.replace("_", " "))])


def test_external_measurement_instrument_resolves_but_historical_citation_is_exempt(tmp_path):
    target = project(tmp_path, "G3")
    section(target, "External actions", action(result="quality=0.8 on I-A-99 cohort stable (observed 2026-10-24 09:00)"))
    assert found(check(target), "ERROR", "evidence.instrument.dangling")
    setting(target, "Guards", "light since 2026-10-25")
    assert not found(check(target), check_id="evidence.instrument.dangling")


def test_existing_historical_instrument_can_support_active_evidence(tmp_path):
    target = project(tmp_path, "G1,G3,G5")
    section(target, "Instruments", instrument() + "- Date: 2026-09-30\n")
    append_discovery(target, discovery(Instrument="I-A-01", Rejected_on="I-A-01; fired: trace confirms execution",
                                      Result="quality=0.8 on I-A-01 cohort stable"))
    assert not found(check(target), check_id="evidence.instrument.dangling")


@pytest.mark.parametrize("order", [(1, 2, 3), (3, 1, 2)])
def test_checker_accepts_three_attempt_retry_chain(tmp_path, order):
    target = project(tmp_path, "E1")
    records = {n: action(f"X-A-{n:03}", expected=f"success (written 2026-10-2{n} 08:00)",
                         result=f"{'failure' if n < 3 else 'success'} (observed 2026-10-2{n} 09:00)",
                         retry=f"X-A-{n - 1:03}" if n > 1 else None) for n in order}
    section(target, "External actions", "\n".join(records[n] for n in order))
    assert not found(check(target), check_id="external.retry.invalid")
    assert not found(check(target), check_id="ext.duplicate")


@pytest.mark.parametrize("invalid", ["dangling", "duplicate", "identity", "forward"])
def test_checker_rejects_inherited_retry_ancestry(tmp_path, invalid):
    target = project(tmp_path, "E1")
    original = action("X-A-001", expected="failure (written 2026-10-21 08:00)",
                      result="failed (observed 2026-10-21 09:00)",
                      retry="X-A-999" if invalid == "dangling" else None,
                      artifact_hash="different" if invalid == "identity" else "abc001")
    if invalid == "forward":
        original = original.replace("2026-10-21", "2026-10-25")
    middle = action("X-A-002", expected="failure (written 2026-10-22 08:00)",
                    result="failed (observed 2026-10-22 09:00)", retry="X-A-001")
    latest = action("X-A-003", expected="success (written 2026-10-23 08:00)",
                    result="success (observed 2026-10-23 09:00)", retry="X-A-002")
    section(target, "External actions", latest + middle + original + (original if invalid == "duplicate" else ""))
    invalid_ids = {issue.record for issue in found(check(target), "ERROR", "external.retry.invalid")}
    assert {"X-A-002", "X-A-003"} <= invalid_ids


@pytest.mark.parametrize("mode", ["light", "strict"])
@pytest.mark.parametrize("variant", ["same", "diverse", "justified", "missing-family", "missing-action", "false-inline"])
def test_selection_uses_required_action_families(tmp_path, mode, variant):
    target = project(tmp_path, "G11", mode=mode)
    first = action()
    second = action("X-A-002", artifact_hash="abc002", family="family-b" if variant == "diverse" else "family-a")
    if variant == "missing-family":
        second = re.sub(r"^- Family:.*\n", "", second, flags=re.M)
    if variant == "missing-action":
        second = ""
    section(target, "External actions", first + second)
    picks = "X-A-001, X-A-002"
    if variant == "justified":
        picks += " (rationale: different deployment constraints)"
    if variant in {"missing-family", "false-inline"}:
        picks += " (families: family-a, family-b)"
    shared(target, "Final picks", picks)
    checker = check(target)
    assert bool(found(checker, "ERROR", "guard.selection.family")) == (variant in {"missing-family", "missing-action"})
    assert bool(found(checker, "ERROR" if mode == "strict" else "WARN", "guard.selection.rationale")) == (
        variant in {"same", "false-inline"})


def test_selection_missing_family_preserves_historical_exemption(tmp_path):
    target = project(tmp_path, "G11")
    section(target, "External actions", re.sub(r"^- Family:.*\n", "", action(), flags=re.M))
    shared(target, "Final picks", "X-A-001")
    setting(target, "Guards", "light since 2026-10-25")
    assert not found(check(target), check_id="guard.selection.family")


@pytest.mark.parametrize("exemption", ["historical", "disabled", "inapplicable"])
def test_selection_rationale_preserves_guard_exemptions(tmp_path, exemption):
    target = project(tmp_path, "G11")
    section(target, "External actions", action() + action("X-A-002", artifact_hash="abc002"))
    shared(target, "Final picks", "X-A-001, X-A-002")
    if exemption == "historical":
        setting(target, "Guards", "light since 2026-10-25")
    elif exemption == "disabled":
        setting(target, "Guards", "off")
    else:
        shared(target, "Not applicable", "G11 — no final selection required")
    checker = check(target)
    assert not found(checker, check_id="guard.selection.family")
    assert not found(checker, check_id="guard.selection.rationale")
