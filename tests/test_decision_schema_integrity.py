"""Decision vocabulary, exhaustive evidence, applicability, and isolated imports."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from conftest import NOW, SCRIPTS, append_discovery, check, check_project, found
from guard_helpers import discovery, instrument, project, section, setting, shared


@pytest.mark.parametrize("decision", ["model-changes", "MODEL-CHANGE", "Method-change", "", "unknown"])
@pytest.mark.parametrize("mode", ["light", "strict"])
def test_invalid_class_is_structural_and_never_eligible(tmp_path, decision, mode):
    target = project(tmp_path, "G1", mode=mode)
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(Decision_class=decision, Instrument="I-A-01"))
    checker = check(target)
    assert found(checker, "ERROR", "guard.decision.invalid")
    assert not checker.eligible_instrument(checker.discoveries["D-A-001"])


@pytest.mark.parametrize("guard", ["G3", "G5", "G6", "GD", "G8", "G11", "G12", "E1"])
def test_decision_consumer_validates_class_without_g1(tmp_path, guard):
    target = project(tmp_path, guard)
    append_discovery(target, discovery(Decision_class="MODEL-CHANGE"))
    assert found(check(target), "ERROR", "guard.decision.invalid")


@pytest.mark.parametrize("decision", sorted(check_project.DECISION_CLASSES))
def test_every_allowed_class_accepts_independent_evidence(tmp_path, decision):
    target = project(tmp_path, "G1", mode="strict")
    section(target, "Instruments", instrument())
    append_discovery(target, discovery(Decision_class=decision, Instrument="I-A-01",
                                      Control="control.csv; selection gain 0.01"))
    checker = check(target)
    assert not found(checker, check_id="guard.decision.invalid")
    assert checker.eligible_instrument(checker.discoveries["D-A-001"])
    assert not found(checker, "ERROR") and not found(checker, "WARN")


@pytest.mark.parametrize("decision,not_for", [
    ("outcome-definition-change", "target-change, model-change"),
    ("method-change", "target-change, model-change"),
    ("target-change", "outcome-definition-change, method-change"),
    ("model-change", "outcome-definition-change, method-change"),
])
def test_aliases_preserve_provenance_restrictions(tmp_path, decision, not_for):
    target = project(tmp_path, "G1", mode="strict")
    section(target, "Instruments", instrument(provenance="own-lineage", not_for=not_for,
                                               coverage="complete", agreement="unmeasured",
                                               resolution="unmeasured"))
    append_discovery(target, discovery(Decision_class=decision, Instrument="I-A-01"))
    checker = check(target)
    assert found(checker, "ERROR", "guard.instrument.circular")
    assert not found(checker, check_id="guard.instrument.schema")
    assert not checker.eligible_instrument(checker.discoveries["D-A-001"])


@pytest.mark.parametrize("decision,not_for", [("combined", "combination"), ("combination", "combined"),
                                            ("data-change", "input-change"), ("input-change", "data-change")])
def test_aliases_preserve_explicit_exclusions(tmp_path, decision, not_for):
    target = project(tmp_path, "G1", mode="strict")
    section(target, "Instruments", instrument(not_for=not_for))
    append_discovery(target, discovery(Decision_class=decision, Instrument="I-A-01"))
    assert found(check(target), "ERROR", "guard.instrument.circular")


@pytest.mark.parametrize("coverage,eligible", [("complete", True), ("held-out", False),
                                               ("in-sample", False), ("external", False)])
def test_only_complete_measurement_needs_no_estimated_agreement(tmp_path, coverage, eligible):
    target = project(tmp_path, "G1", mode="strict")
    section(target, "Instruments", instrument(coverage=coverage, agreement="unmeasured", resolution="unmeasured"))
    append_discovery(target, discovery(Decision_class="data-change", Instrument="I-A-01",
                                      Control="not applicable — full inventory; alternative: exhaustive checksum"))
    checker = check(target)
    assert checker.eligible_instrument(checker.discoveries["D-A-001"]) is eligible
    assert bool(found(checker, "ERROR", "guard.instrument.circular")) is not eligible
    assert not found(checker, check_id="guard.instrument.schema")


@pytest.mark.parametrize("disabled", ["off", "inapplicable", "historical"])
def test_decision_schema_respects_guard_activation(tmp_path, disabled):
    target = project(tmp_path, "G1")
    append_discovery(target, discovery(Decision_class="MODEL-CHANGE",
                                      date="2026-09-30" if disabled == "historical" else "2026-10-24"))
    if disabled == "off":
        setting(target, "Guards", "off")
    elif disabled == "inapplicable":
        shared(target, "Not applicable", "G1 — no measured decisions")
    assert not found(check(target), check_id="guard.decision.invalid")


@pytest.mark.parametrize("mode", ["light", "strict", "off"])
def test_unused_applicability_declaration_is_info(tmp_path, mode):
    target = project(tmp_path, "G1")
    if mode == "off":
        setting(target, "Guards", "off")
    else:
        setting(target, "Guards", f"{mode} since 2026-10-01")
    shared(target, "Not applicable", "G3 — no series")
    checker = check(target)
    assert found(checker, "INFO", "guard.applicability.disabled")
    assert not found(checker, "ERROR") and not found(checker, "WARN")


def test_enabled_applicability_declaration_has_no_unused_notice(tmp_path):
    target = project(tmp_path, "G1")
    shared(target, "Not applicable", "G1 — no measurements")
    assert not found(check(target), check_id="guard.applicability.disabled")


def test_unused_applicability_notices_are_aggregated(tmp_path, capsys):
    target = project(tmp_path, "G1")
    shared(target, "Not applicable", "G3 — no series; G8 — no deadline; G11 — no final choice")
    checker = check_project.Checker(target, now=NOW)
    checker.run()
    lines = [line for line in capsys.readouterr().out.splitlines() if "guard.applicability.disabled" in line]
    assert len(lines) == 1
    assert len(found(checker, "INFO", "guard.applicability.disabled")) == 3


@pytest.mark.parametrize("missing", ["ro_ids.py", "ro_markdown.py"])
def test_broken_install_reports_local_import_without_traceback(tmp_path, missing):
    copied = tmp_path / "scripts"
    shutil.copytree(SCRIPTS, copied, ignore=shutil.ignore_patterns("__pycache__"))
    (copied / missing).unlink()
    result = subprocess.run([sys.executable, "-I", str(copied / "check_project.py"), "--help"],
                            text=True, capture_output=True, check=False)
    assert result.returncode == 2
    assert "installation is broken" in result.stdout
    assert missing.removesuffix(".py") in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


def test_checker_prioritizes_its_local_imports_under_runpy(tmp_path):
    for name in ("ro_ids.py", "ro_markdown.py"):
        (tmp_path / name).write_text("raise AssertionError('foreign local module loaded')\n", encoding="utf-8")
    code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    result = subprocess.run([sys.executable, "-I", "-c", code, str(tmp_path),
                             str(SCRIPTS / "check_project.py"), "--help"], text=True, capture_output=True,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout
