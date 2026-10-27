"""Executable reproducibility checks reject merely plausible saved artifacts."""
from __future__ import annotations

import json
import csv
import io
import math
from pathlib import Path
import shutil
import sys
import textwrap

import pytest

from scripts.evals import checks, replication_check as replication, run_evals as runner


ANALYSIS = textwrap.dedent('''\
    import csv, json, math, re
    from pathlib import Path
    with open("measurements.csv", newline="", encoding="utf-8") as source:
        values = [float(row["after"]) - float(row["before"]) for row in csv.DictReader(source)]
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((value - mean) ** 2 for value in values) / (n - 1))
    se = sd / math.sqrt(n)
    critical = float(re.search(r"t_critical=([0-9]+[.][0-9]+)", Path("paper-excerpt.md").read_text())[1])
    result = dict(n=n, mean_difference=mean, sample_sd=sd, standard_error=se,
                  t_statistic=mean / se, ci95=[mean-critical*se, mean+critical*se])
    Path("replication.json").write_text(json.dumps(result), encoding="utf-8")
''')


def context(tmp_path, code=ANALYSIS):
    case = tmp_path / "case"
    shutil.copytree(runner.DEFAULT_SKILL / "evals" / "non-ml-replication" / "files", case / "files")
    run = tmp_path / "run"
    shutil.copytree(case / "files", run / "outputs")
    ctx = checks.CheckContext(case, run, runner.DEFAULT_SKILL, sys.executable)
    (ctx.outputs / "analysis.py").write_text(code, encoding="utf-8")
    (ctx.outputs / "replication.json").write_text(
        json.dumps(replication.expected_replication(case / "files")), encoding="utf-8")
    (ctx.outputs / "discoveries.md").write_text(
        "## D-A-001 — Paired archive analysis\n- Evidence: replication.json, analysis.py\n", encoding="utf-8")
    (ctx.outputs / "handoff.md").write_text(
        "### 2026-10-25 completed H-A-01\n- Discovery updates: D-A-001\n"
        "- New plan items: H-A-02\n", encoding="utf-8")
    return ctx


def snapshot(directory):
    return {path.relative_to(directory): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def test_saved_analysis_recreates_result_without_editing_evidence(tmp_path):
    ctx = context(tmp_path)
    before = snapshot(ctx.outputs)
    passed, evidence = checks.evidence_followups(ctx)
    assert passed, evidence
    assert "independently calculated canonical results: True" in evidence
    assert "independently calculated changed observations results: True" in evidence
    assert "independently calculated changed critical value results: True" in evidence
    assert snapshot(ctx.outputs) == before
    assert not list(ctx.run_dir.glob(".replication-check-*"))


@pytest.mark.parametrize("code", [
    "# Saved but never implemented\npass\n",
    "print('unrelated report generator')\n",
    "from pathlib import Path\nprint(Path('replication.json').read_text())\n",
    "import json\nprint(json.dumps({'n': 8, 'mean_difference': 2.5}))\n",
    "raise RuntimeError('failed analysis')\n",
    "from pathlib import Path\nPath('replication.json').write_text('{}')\n",
    ANALYSIS.replace('float(row["after"]) - float(row["before"])',
                     'float(row["before"]) - float(row["after"])'),
])
def test_unrelated_noop_failed_and_wrong_analysis_do_not_pass_from_saved_json(tmp_path, code):
    ctx = context(tmp_path, code)
    assert checks.numeric_replication(ctx)[0]
    before = snapshot(ctx.outputs)
    assert not checks.evidence_followups(ctx)[0]
    assert snapshot(ctx.outputs) == before


def test_citing_the_grader_module_is_not_reproducible_analysis(tmp_path):
    ctx = context(tmp_path)
    shutil.copyfile(Path(checks.__file__), ctx.outputs / "analysis.py")
    assert not checks.evidence_followups(ctx)[0]


def test_hardcoded_correct_output_fails_the_changed_observation_control(tmp_path):
    ctx = context(tmp_path)
    answer = json.dumps(replication.expected_replication(ctx.case_dir / "files"))
    (ctx.outputs / "analysis.py").write_text(
        "from pathlib import Path\nPath('replication.json').write_text(" + repr(answer) + ")\n", encoding="utf-8")
    assert checks.numeric_replication(ctx)[0]
    passed, evidence = checks.evidence_followups(ctx)
    assert not passed
    assert "canonical results: True" in evidence and "changed observations results: False" in evidence


def test_hardcoded_critical_value_fails_when_only_the_method_changes(tmp_path):
    code = ANALYSIS.replace('float(re.search(r"t_critical=([0-9]+[.][0-9]+)", Path("paper-excerpt.md").read_text())[1])',
                            "2.364624251")
    assert code != ANALYSIS
    passed, evidence = checks.evidence_followups(context(tmp_path, code))
    assert not passed
    assert "changed observations results: True" in evidence and "changed critical value results: False" in evidence


def test_hardcoded_sample_size_fails_when_observation_count_changes(tmp_path):
    code = ANALYSIS.replace("n = len(values)", "n = 8")
    passed, evidence = checks.evidence_followups(context(tmp_path, code))
    assert not passed
    assert "canonical results: True" in evidence and "changed observations results: False" in evidence


def test_input_variants_are_deterministic_separate_and_leave_source_inputs_unchanged(tmp_path):
    ctx = context(tmp_path)
    before = snapshot(ctx.case_dir / "files")
    variants = replication._input_variants(ctx.case_dir / "files")
    assert variants == replication._input_variants(ctx.case_dir / "files")
    canonical, observations, method = [inputs for label, inputs in variants]
    assert canonical["measurements.csv"] != observations["measurements.csv"]
    assert canonical["paper-excerpt.md"] != observations["paper-excerpt.md"]
    assert canonical["measurements.csv"] == method["measurements.csv"]
    assert canonical["paper-excerpt.md"] != method["paper-excerpt.md"]
    rows = list(csv.DictReader(io.StringIO(observations["measurements.csv"].decode("utf-8"))))
    assert len({row["pair_id"] for row in rows}) == len(rows)
    assert f"For {len(rows) - 1} degrees of freedom" in observations["paper-excerpt.md"].decode("utf-8")
    for inputs in (observations, method):
        assert inputs["paper-excerpt.md"].startswith(b"Synthetic arithmetic sensitivity control:")
        assert b"no statistical coverage claim" in inputs["paper-excerpt.md"]
    assert snapshot(ctx.case_dir / "files") == before


def test_count_probe_respects_declared_degrees_of_freedom(tmp_path):
    validation = ('df = int(re.search(r"For (\\d+) degrees of freedom", '
                  'Path("paper-excerpt.md").read_text())[1])\n'
                  'if df != n - 1:\n    raise ValueError("Inconsistent sample metadata")\n')
    code = ANALYSIS.replace("mean = sum(values) / n", validation + "mean = sum(values) / n")
    passed, evidence = checks.evidence_followups(context(tmp_path, code))
    assert passed, evidence


def test_oracle_uses_canonical_measurements_and_critical_value(tmp_path):
    ctx = context(tmp_path)
    measurements = ctx.case_dir / "files" / "measurements.csv"
    measurements.write_text(measurements.read_text().replace("8,14,19", "8,14,23"), encoding="utf-8")
    excerpt = ctx.case_dir / "files" / "paper-excerpt.md"
    excerpt.write_text(excerpt.read_text().replace("t_critical=2.364624251", "t_critical=3.0"), encoding="utf-8")
    expected = replication.expected_replication(ctx.case_dir / "files")
    assert expected["mean_difference"] == 3
    assert expected["ci95"][1] == 3 + 3 * expected["standard_error"]
    assert not checks.numeric_replication(ctx)[0]  # The old saved answer is stale.
    assert checks.evidence_followups(ctx)[0]  # Re-execution reads the canonical inputs.


def test_rerun_supports_saved_sibling_helper_modules(tmp_path):
    ctx = context(tmp_path, "import calculator\n")
    (ctx.outputs / "calculator.py").write_text(ANALYSIS, encoding="utf-8")
    assert checks.evidence_followups(ctx)[0]


def test_analysis_mutating_canonical_inputs_fails_and_preserves_originals(tmp_path):
    ctx = context(tmp_path, ANALYSIS + "Path('measurements.csv').write_text('changed')\n")
    before = snapshot(ctx.outputs)
    passed, evidence = checks.evidence_followups(ctx)
    assert not passed and "changed the canonical inputs" in evidence
    assert snapshot(ctx.outputs) == before


def test_analysis_timeout_is_a_failed_assertion_and_cleans_workspace(tmp_path, monkeypatch):
    ctx = context(tmp_path, "import time\ntime.sleep(30)\n")
    monkeypatch.setattr(replication, "ANALYSIS_TIMEOUT", .1)
    passed, evidence = checks.evidence_followups(ctx)
    assert not passed and "analysis timeout" in evidence
    assert not list(ctx.run_dir.glob(".replication-check-*"))


def test_large_stdout_cannot_overflow_capture_or_replace_result(tmp_path):
    ctx = context(tmp_path, "print('x' * 2_000_000)\n" + ANALYSIS)
    assert checks.evidence_followups(ctx)[0]


def test_oversized_json_is_rejected_before_parsing(tmp_path):
    ctx = context(tmp_path, "from pathlib import Path\nPath('replication.json').write_text(' ' * 70000)\n")
    passed, evidence = checks.evidence_followups(ctx)
    assert not passed and "bounded replication.json" in evidence


@pytest.mark.parametrize("name", ["../outside.py", "/outside.py"])
def test_analysis_cannot_be_a_path_outside_saved_outputs(tmp_path, name):
    assert not replication.rerun_analysis(context(tmp_path), name)[0]


@pytest.mark.parametrize("value", [True, False, math.nan, math.inf, "2.5", None])
def test_non_numeric_and_nonfinite_statistics_fail(tmp_path, value):
    expected = replication.expected_replication(context(tmp_path).case_dir / "files")
    result = {**expected, "mean_difference": value}
    assert not replication.matches_replication(result, expected)
