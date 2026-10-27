"""The published policy, saved-case oracle, and executable gates share one budget."""

import ast
import json
import re

from conftest import ROOT, SKILL


def test_every_latency_gate_uses_the_published_common_budget():
    documents = [ROOT / "docs/plans/v3-p3-spec.md", ROOT / "docs/evals/hook-latency-gatefix.md",
                 SKILL / "evals/hook-latency-budget/prompt.md", SKILL / "evals/hook-latency-budget/case.yaml"]
    declarations = []
    for path in documents:
        text = path.read_text(encoding="utf-8")
        values = re.findall(r"(?:p95 < |common )(\d+) ms", text)
        assert values, path
        declarations.extend(map(int, values))
    for filename in ("test_ro_cli.py", "test_ro_hooks.py"):
        tree = ast.parse((ROOT / "tests" / filename).read_text(encoding="utf-8"))
        values = [node.comparators[0].value * 1000 for node in ast.walk(tree)
                  if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                  and node.left.id in {"p95", "p95_process"}
                  and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)]
        assert values, filename
        declarations.extend(values)
    assert set(declarations) == {150}


def test_saved_latency_case_discriminates_boundary_and_incorrect_output():
    base = SKILL / "evals/hook-latency-budget"
    measurements = json.loads((base / "files/measurements.json").read_text(encoding="utf-8"))
    runs = measurements["runs"]
    p95s = {run["id"]: sorted(run["samples_ms"])[18] for run in runs}
    assert p95s == {"windows-supervisor": 183, "windows-supervisor-boundary": 225,
                   "windows-child": 151, "windows-in-process": 150, "linux-supervisor": 151,
                   "macos-supervisor": 149, "incorrect-output": 99}
    verdicts = {run["id"]: p95s[run["id"]] < 150 and run["hook_output_correct"] for run in runs}
    assert {name for name, passed in verdicts.items() if not passed} == {
        "windows-supervisor", "windows-supervisor-boundary", "windows-child", "windows-in-process",
        "linux-supervisor", "incorrect-output"}
    for path in (base / "graders").glob("*.md"):
        assert not re.search(r"225 ms (?:budget|limit)", path.read_text(encoding="utf-8")), path
