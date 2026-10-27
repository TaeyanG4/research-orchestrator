"""Keep shared instructions general without censoring domain evidence or executable schemas."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from conftest import ROOT

SPEC = importlib.util.spec_from_file_location("release_validation", ROOT / "scripts" / "validate_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def vocabulary_errors(root: Path, relative: str, text: str) -> list[str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    errors = []
    release.check_vocabulary(errors, root)
    return errors


@pytest.mark.parametrize("relative", ["SKILL.md", "templates/AGENTS.md.template", "references/compute.md",
                                     "references/competition-notes.md", "references/research-guards.md",
                                     "references/research-guards-next.md",
                                     "references/adapters-next/guide.md", "templates/v2-next/AGENTS.md.template"])
def test_general_instructions_reject_domain_vocabulary(tmp_path, relative):
    errors = vocabulary_errors(tmp_path, "skills/research-orchestrator/" + relative,
                               "Use labels, folds and SUBMISSIONS.\n")
    assert len(errors) == 1
    assert all(term in errors[0] for term in ("labels", "folds", "submissions"))


@pytest.mark.parametrize("term", ["leaderboard", "LEADERBOARDS", "Kaggle", "label", "labels", "fold", "folds",
                                  "submission", "submissions", "cross-validation", "hyperparameters", "ensemble",
                                  "pretrained", "OOF", "training", "inference", "boosting"])
def test_domain_lexicon_remains_complete(tmp_path, term):
    errors = vocabulary_errors(tmp_path, "skills/research-orchestrator/SKILL.md", f"Use {term}.\n")
    assert len(errors) == 1 and term.lower() in errors[0]


@pytest.mark.parametrize("relative", [
    "skills/research-orchestrator/references/competition.md",
    "skills/research-orchestrator/references/adapters/kaggle.md",
    "skills/research-orchestrator/templates/v2/AGENTS.md.template",
    "skills/research-orchestrator/templates/v3.0/AGENTS.md.template",
    "skills/research-orchestrator/scripts/check_project.py",
    "skills/research-orchestrator/scripts/ro_settings.py",
    "examples/team-research-cv-leakage/discoveries.md", "examples/competition-solo-tabular/plan.md",
    "examples/ordinary-study/plan.md", "scripts/helper.py", "tests/fixtures/replay/plan.md",
    "docs/plans/spec.md", "README.md", "plugin.json", "assets/readme/example.svg",
])
def test_specialized_guidance_evidence_and_code_keep_plain_domain_terms(tmp_path, relative):
    assert vocabulary_errors(tmp_path, relative, "labels folds submissions Kaggle training inference\n") == []


def test_general_instruction_adapter_paths_are_not_prose(tmp_path):
    assert vocabulary_errors(tmp_path, "skills/research-orchestrator/SKILL.md",
                             "Read [the adapter](references/adapters/kaggle.md).\n") == []


def test_repository_vocabulary_boundary():
    errors = []
    release.check_vocabulary(errors)
    assert errors == [], "\n".join(errors)
