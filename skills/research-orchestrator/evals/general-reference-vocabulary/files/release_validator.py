"""Exact release-check excerpt for this isolated fixture; not a recorded execution."""
import os
from pathlib import Path
import re

ROOT = Path.cwd()


DOMAIN_VOCABULARY = re.compile(
    r"\b(?:leaderboards?|kaggle|labels?|folds?|submissions?|cross[- ]validation|hyperparameters?|"
    r"ensembles?|pre[- ]?trained|oof|groupkfold|kfold|training|inference|boosting)\b", re.I)


ADAPTER_POINTER = re.compile(r"(?:references/)?adapters/[A-Za-z0-9_.-]+\.md")


VOCABULARY_SUFFIXES = {".md", ".template"}


def vocabulary_paths(root: Path):
    """Keep general instructions domain-neutral; domain evidence and executable schemas use their own words."""
    skill = root / "skills" / "research-orchestrator"
    yield skill / "SKILL.md"
    for directory in (skill / "templates", skill / "references"):
        for path in directory.rglob("*"):
            relative = path.relative_to(directory)
            if ((directory.name == "templates" and re.fullmatch(r"v\d+(?:\.\d+)*", relative.parts[0]))
                    or path.is_relative_to(skill / "references" / "adapters")
                    or path == skill / "references" / "competition.md"):
                continue
            yield path


def check_vocabulary(errors: list[str], root: Path = ROOT) -> None:
    """Check general instructions; only competition guidance and adapters are domain-specific."""
    for path in sorted(vocabulary_paths(root)):
        if not path.is_file() or path.suffix.lower() not in VOCABULARY_SUFFIXES:
            continue
        for line_number, prose in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            prose = ADAPTER_POINTER.sub("<adapter-reference>", prose)
            terms = sorted({match.group(0).lower() for match in DOMAIN_VOCABULARY.finditer(prose)})
            if terms:
                errors.append(f"vocabulary: {path.relative_to(root)}:{line_number}: " + ", ".join(terms))
