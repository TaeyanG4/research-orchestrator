"""Latency gates separate interpreter startup from hook work without hiding regressions."""

import ast
import json
import re
import subprocess
import sys

import pytest

from conftest import ROOT, SKILL


def test_latency_gates_use_the_published_layer_budgets():
    documents = [ROOT / "docs/plans/v3-p3-spec.md", ROOT / "docs/evals/hook-latency-gatefix.md",
                 ROOT / "docs/evals/README.md", SKILL / "references/hooks-capabilities.md",
                 SKILL / "evals/hook-latency-budget/case.yaml"]
    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert "150 ms" in text and "300 ms" in text and "bare-interpreter" in text, path
        assert "every host and hook layer" not in text, path
    for filename in ("test_ro_cli.py", "test_ro_hooks.py"):
        tree = ast.parse((ROOT / "tests" / filename).read_text(encoding="utf-8"))
        values = {node.left.id: node.comparators[0].value * 1000 for node in ast.walk(tree)
                  if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                  and node.left.id in {"p95", "p95_process", "overhead"}
                  and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)}
        assert values == ({"p95": 150} if filename == "test_ro_cli.py" else
                          {"p95": 150, "overhead": 150, "p95_process": 300})


def test_saved_latency_case_discriminates_boundary_and_incorrect_output():
    base = SKILL / "evals/hook-latency-budget"
    measurements = json.loads((base / "files/measurements.json").read_text(encoding="utf-8"))
    runs = measurements["runs"]
    p95s = {run["id"]: sorted(run["samples_ms"])[18] for run in runs}
    assert p95s == {"windows-supervisor": 183, "windows-supervisor-boundary": 225,
                   "windows-child": 151, "windows-in-process": 150, "linux-supervisor": 151,
                   "macos-supervisor": 149, "incorrect-output": 99,
                   "child-overhead-boundary": 230, "child-absolute-boundary": 300}
    verdicts = {}
    for run in runs:
        p95 = p95s[run["id"]]
        verdict = p95 < 150
        if run["path"] == "direct-child":
            baseline = sorted(run["baseline_samples_ms"])[18]
            verdict = p95 - baseline < 150 and p95 < 300
        verdicts[run["id"]] = verdict and run["hook_output_correct"]
    assert {name for name, passed in verdicts.items() if not passed} == {
        "windows-supervisor", "windows-supervisor-boundary", "windows-in-process",
        "linux-supervisor", "incorrect-output", "child-overhead-boundary", "child-absolute-boundary"}
    for path in (base / "graders").glob("*.md"):
        assert not re.search(r"225 ms (?:budget|limit)", path.read_text(encoding="utf-8")), path


@pytest.mark.parametrize("scenario,hook_batches,baseline_batches,error", [
    ("batch-aggregation", [.150, .200, .180], [.050, .080, .020], None),
    ("slow-startup", [.280] * 3, [.180] * 3, None),
    ("overhead-boundary", [.230] * 3, [.080] * 3, "150 ms overhead budget"),
    ("absolute-boundary", [.300] * 3, [.220] * 3, "300 ms absolute ceiling"),
    ("incorrect-output", [.100] * 3, [.030] * 3, "unexpected"),
])
def test_subprocess_gate_measures_startup_and_retains_failure_report(
        tmp_path, monkeypatch, scenario, hook_batches, baseline_batches, error):
    import test_ro_hooks as subject

    project = subject.project_at(tmp_path / "project")
    monkeypatch.setattr(subject, "project_at", lambda _: project)
    monkeypatch.setattr(subject.hooks, "hook", lambda *args: {})
    destination = tmp_path / "latency.json"
    installed = {"layer": "installed-watchdog", "p95_ms": 60, "budget_ms": 150, "passed": True}
    destination.write_text(json.dumps(installed), encoding="utf-8")
    monkeypatch.setenv("RO_LATENCY_REPORT", str(destination))
    calls = {True: [], False: []}
    elapsed = 0.
    clock_reads = 0

    def clock():
        nonlocal clock_reads
        clock_reads += 1
        # Each measured call starts at zero, avoiding accumulated floating point drift.
        return 0. if clock_reads % 2 else elapsed

    def run(command, **kwargs):
        nonlocal elapsed
        assert command[:3] == [sys.executable, "-E", "-S"]
        baseline = command[3:] == ["-c", "pass"]
        if not baseline:
            assert command[3:] == [str(subject.SCRIPTS / "ro.py"), "--project", str(project.root),
                                   "hook", "PreToolUse"]
        calls[baseline].append(kwargs)
        index = len(calls[baseline]) - 3  # Two unmeasured warm-ups per command.
        batches = baseline_batches if baseline else hook_batches
        p95 = batches[max(0, index) // 20]
        # Eighteen lower samples, the p95 sample, and a larger tail outlier.
        elapsed = p95 + (.5 if index % 20 == 19 else 0 if index % 20 == 18 else -.010)
        output = "" if baseline else '{"unexpected": true}' if scenario == "incorrect-output" else "{}"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subject.time, "perf_counter", clock)
    monkeypatch.setattr(subject.subprocess, "run", run)
    if error is None:
        subject.test_pretool_latency_does_not_depend_on_large_coordination_files(tmp_path)
    else:
        with pytest.raises(AssertionError, match=None if scenario == "incorrect-output" else error):
            subject.test_pretool_latency_does_not_depend_on_large_coordination_files(tmp_path)
    report = json.loads(destination.read_text(encoding="utf-8"))
    assert {key: report[key] for key in installed} == installed
    if scenario == "incorrect-output":
        assert "subprocess" not in report
        return
    assert len(calls[True]) == len(calls[False]) == 62
    assert calls[True] == calls[False]
    assert calls[True][0] == dict(input=json.dumps(subject.shell_payload("printf '%s\\n' ready && echo done")),
                                  capture_output=True, text=True, encoding="utf-8", timeout=10)
    measured = report["subprocess"]
    hook = sorted(hook_batches)[1] * 1000
    baseline = sorted(baseline_batches)[1] * 1000
    assert measured["batch_p95_ms"] == pytest.approx([v * 1000 for v in hook_batches])
    assert measured["baseline_batch_p95_ms"] == pytest.approx([v * 1000 for v in baseline_batches])
    assert measured["p95_ms"] == pytest.approx(hook)
    assert measured["baseline_p95_ms"] == pytest.approx(baseline)
    assert measured["overhead_ms"] == pytest.approx(hook - baseline)
    assert measured["overhead_budget_ms"] == 150 and measured["absolute_budget_ms"] == 300
    assert measured["passed"] is (error is None)


def test_installed_latency_report_preserves_prior_subprocess_measurements(tmp_path, monkeypatch):
    import test_ro_cli as subject

    project = subject.project_at(tmp_path)
    monkeypatch.setattr(subject, "project_at", lambda _: project)
    destination = tmp_path / "latency.json"
    direct = {"p95_ms": 165, "baseline_p95_ms": 60, "overhead_ms": 105, "passed": True}
    destination.write_text(json.dumps({"subprocess": direct}), encoding="utf-8")
    monkeypatch.setenv("RO_LATENCY_REPORT", str(destination))
    monkeypatch.setattr(subject.time, "perf_counter", lambda: 0.)
    monkeypatch.setattr(subject.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, "{}", ""))
    subject.test_supervised_installed_hook_latency_is_bounded_on_large_project(tmp_path)
    report = json.loads(destination.read_text(encoding="utf-8"))
    assert report["subprocess"] == direct
    assert report["layer"] == "installed-watchdog" and report["budget_ms"] == 150 and report["passed"]
