"""Selection controls are optional evidence with bounded, applicable advice."""

import pytest

from conftest import append_discovery, check, found
from guard_helpers import discovery, instrument, project, replay, section, setting, shared


@pytest.mark.parametrize("decision", ["model-change", "input-change", "combination"])
@pytest.mark.parametrize("mode,severity", [("light", "INFO"), ("strict", "WARN")])
def test_selected_decision_without_control_reports_expected_severity(tmp_path, decision, mode, severity):
    target = project(tmp_path, "G1", mode)
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(Decision_class=decision, Instrument="I-A-01"))
    issues = found(check(target), check_id="guard.control.missing")
    assert len(issues) == 1 and issues[0].severity == severity
    assert issues[0].record == "D-A-001" and issues[0].field == "Control"


@pytest.mark.parametrize("profile", ["work", "research", "competition"])
@pytest.mark.parametrize("control", ["artifacts/placebo.json; selection gain 0.003",
                                    "artifacts/control.csv; selection gain -1.2e-3 score",
                                    "not applicable — exhaustive comparison; alternative: analytic error bound"])
def test_control_evidence_or_explained_alternative_clears_finding(tmp_path, profile, control):
    target = project(tmp_path, "G1", "strict", profile)
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(Decision_class="model-change", Instrument="I-A-01", Control=control))
    checker = check(target)
    assert not found(checker, check_id="guard.control.missing")
    assert not found(checker, check_id="discovery.field.unknown")


@pytest.mark.parametrize("control", ["", "none", "control.csv", "control.csv; selection gain unknown",
                                    "none; selection gain 0.1", "pending; selection gain 0.01"])
def test_empty_or_unmeasured_control_does_not_hide_missing_evidence(tmp_path, control):
    target = project(tmp_path)
    append_discovery(target, discovery(Decision_class="combination", Control=control))
    assert found(check(target), "INFO", "guard.control.missing")


@pytest.mark.parametrize("exemption", ["off", "inapplicable", "historical", "operational", "target-change"])
def test_control_advice_respects_guard_scope_and_activation(tmp_path, exemption):
    target = project(tmp_path)
    if exemption == "off":
        setting(target, "Guards", "off")
    elif exemption == "inapplicable":
        shared(target, "Not applicable", "G1 — no measured decisions")
    append_discovery(target, discovery(Decision_class=exemption if exemption in {"operational", "target-change"}
                                      else "input-change", date="2026-09-20" if exemption == "historical" else "2026-10-24"))
    assert not found(check(target), check_id="guard.control.missing")


def test_selection_control_replay_and_counter_replay(tmp_path):
    target = replay(tmp_path, "replay-selection-control", profile="research")
    assert len(found(check(target), "INFO", "guard.control.missing")) == 1
    path = target / "discoveries.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Outcome: inconclusive",
                    "- Outcome: inconclusive\n- Control: artifacts/placebo.json; selection gain 0.006"),
                    encoding="utf-8", newline="\n")
    assert not found(check(target), check_id="guard.control.missing")
