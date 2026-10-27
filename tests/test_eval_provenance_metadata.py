"""Case schema and routing validation without evaluating or grading any scenario."""

from pathlib import Path

import pytest

from conftest import ROOT, SKILL
from scripts.evals import grade_evals as grade, inventory, run_evals as runner


NEW_CASES = {
    "decision-changing-draft", "exclusive-license-routing", "installed-capability-matrix",
    "phase-clock-scaffold", "hook-edit-warning-fast-paths", "record-clock-tolerance",
    "hook-basename-dispatch", "publish-gate-startup-notice", "installer-edit-policy-routing",
}


def test_new_cases_have_strict_schema_and_explicit_trace_routing():
    cases = runner.load_cases(SKILL, sorted(NEW_CASES))
    assert {case.name for case in cases} == NEW_CASES
    for case in cases:
        assert case.assertions
        assert (case.path / "files").is_dir()
        assert len({assertion.text for assertion in case.assertions}) == len(case.assertions)
        modes = grade.assertion_modes(case)
        assert modes == {assertion.path.name: "judged" for assertion in case.assertions}
        assert all((case.name, assertion.path.name) in grade.JUDGED_CHECKS for assertion in case.assertions)


def test_case_inventory_reads_metadata_without_running_evaluations_or_graders(monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError("Inventory must not execute a scenario or grader")

    monkeypatch.setattr(grade, "grade_run", prohibited)
    monkeypatch.setattr(grade, "judge_run", prohibited)
    monkeypatch.setattr(grade.subprocess, "run", prohibited)
    monkeypatch.setattr(grade, "SCRIPTED_CHECKS", {key: prohibited for key in grade.SCRIPTED_CHECKS})
    rendered = inventory.render_inventory(SKILL)
    readme = (ROOT / "scripts/evals/README.md").read_text(encoding="utf-8")
    saved = inventory.START + readme.split(inventory.START, 1)[1].split(inventory.END, 1)[0] + inventory.END
    assert rendered == saved
    for name in NEW_CASES:
        assert f"| {name} |" in rendered


def test_new_unregistered_assertions_still_require_an_explicit_routing_decision(tmp_path):
    case = runner.Case(tmp_path, "installed-capability-matrix", "Lookup", "Observed scope", (
        runner.Assertion(Path("99-unregistered.md"), "An unsupported claim receives no automatic pass."),))
    with pytest.raises(ValueError, match="No scripted check registered"):
        grade.assertion_modes(case)
