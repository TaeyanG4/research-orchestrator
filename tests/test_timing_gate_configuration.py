"""Timing gates run explicitly rather than making deterministic releases load-sensitive."""

import ast

from conftest import ROOT


def test_timing_functions_carry_the_separate_marker():
    for name in ("test_ro_cli.py", "test_ro_hooks.py"):
        module = ast.parse((ROOT / "tests" / name).read_text(encoding="utf-8"))
        measurements = [node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)
                        and node.name.startswith("test_") and "latency" in node.name]
        assert measurements
        for function in measurements:
            assert any(ast.unparse(marker) == "pytest.mark.latency" for marker in function.decorator_list)


def test_release_separates_timing_checks_from_deterministic_checks():
    module = ast.parse((ROOT / "scripts/validate_release.py").read_text(encoding="utf-8"))
    gate = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "check_tests")
    commands = [node.args[0] for node in ast.walk(gate) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "run"]
    assert len(commands) == 1 and isinstance(commands[0], ast.List)
    values = [node.value if isinstance(node, ast.Constant) else None for node in commands[0].elts]
    assert values[values.index("-m", values.index("pytest") + 1) + 1] == "not latency"
    workflow = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
    commands = [line for line in workflow.splitlines() if "run: python -m pytest" in line]
    timing = [command for command in commands if "-m latency" in command]
    assert len(timing) == 1
    assert "tests/test_ro_cli.py" in timing[0] and "tests/test_ro_hooks.py" in timing[0]
    # Any other pytest step (the failure report) stays deterministic.
    assert all('-m "not latency"' in command for command in commands if command not in timing)
