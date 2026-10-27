"""Installation and measured host claims carry the same scope in every language."""

import re
from types import SimpleNamespace

import pytest

from conftest import ROOT, SKILL


def test_readmes_scope_candidate_record_and_explain_plugin_install():
    structures = []
    for filename in ("README.md", "README.ko.md", "README.ja.md", "README.zh-CN.md"):
        text = (ROOT / filename).read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| Claude Code |"))
        assert row.endswith("| `ro`, Git pre-push |")
        assert text.count("](docs/evals/README.md)") == 1
        assert "Windows:" in text and "Git Bash (`sh`)" in text
        paragraph = next(part for part in text.split("\n\n") if "`--shim-only`" in part)
        assert "SessionStart" in paragraph and "`ro brief`" in paragraph
        assert "python install.py --shim-only" not in paragraph
        cost = next(part for part in text.split("\n\n") if "`install.py --project .`" in part)
        assert all(tool in cost for tool in ("SessionStart", "Stop", "`install.py --project .`", "Python"))
        structures.append([(len(m[1])) for m in re.finditer(r"^(#+) ", text, re.M)])
    assert all(shape == structures[0] for shape in structures)


def test_dated_hook_cost_lives_in_evidence_not_installed_reference():
    hooks = (SKILL / "references/hooks.md").read_text(encoding="utf-8")
    evidence = (ROOT / "docs/evals/hook-runtime-cost-2026-10-27.md").read_text(encoding="utf-8")
    assert re.search(r"\b\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)? ms\b", evidence)
    assert not re.search(r"\b20\d{2}-\d{2}-\d{2}\b", hooks)
    assert "interpreter sentinel" in evidence
    assert re.search(r"\b\d+ calls", evidence)


@pytest.mark.parametrize("extra,missing,expected", [([], [], True), (["AskUserQuestion"], [], False),
                                                 (["Agent"], [], False), ([], ["Edit"], False)])
def test_plugin_matcher_assertion_distinguishes_default_from_project_scope(extra, missing, expected):
    from scripts.evals.runtime_checks import CHECKS
    tools = [tool for tool in ("Bash", "PowerShell", "Edit", "Write", "NotebookEdit") if tool not in missing]
    context = SimpleNamespace(data=lambda name: {"plugin": [*tools, *extra]})
    assert CHECKS["conditional-project-hook-matchers", "04-generic-scope.md"](context)[0] is expected
