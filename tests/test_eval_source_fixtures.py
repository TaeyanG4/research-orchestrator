"""Repository-only release checks are supplied verbatim to isolated future cases."""

import ast

import pytest

from conftest import ROOT, SKILL


@pytest.mark.parametrize("case,names", [
    ("publication-receipt-gate", {"check_release_receipt"}),
    ("general-reference-vocabulary", {"DOMAIN_VOCABULARY", "ADAPTER_POINTER", "VOCABULARY_SUFFIXES",
                                     "vocabulary_paths", "check_vocabulary"}),
])
def test_case_validator_excerpts_match_release_source(case, names):
    def excerpts(path):
        source = path.read_text(encoding="utf-8")
        segments = {}
        for node in ast.parse(source).body:
            name = node.name if isinstance(node, ast.FunctionDef) else (
                node.targets[0].id if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) else "")
            if name in names:
                segments[name] = ast.get_source_segment(source, node)
        assert set(segments) == names
        return segments
    fixture = SKILL / "evals" / case / "files/release_validator.py"
    assert excerpts(fixture) == excerpts(ROOT / "scripts/validate_release.py")
