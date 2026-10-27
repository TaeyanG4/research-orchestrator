"""Review-loop guidance: fixed exit criteria, a round cap and carried-over findings stay documented."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "skills" / "research-orchestrator" / "references"


def text(name: str) -> str:
    return (REFS / name).read_text(encoding="utf-8")


def test_review_loops_states_exit_criterion_cap_and_scope():
    body = text("review-loops.md")
    assert "no BLOCKER or MAJOR finding" in body
    assert "Do not use a score threshold" in body
    assert "round cap" in body
    assert "out of scope" in body
    assert "one reviewer per round" in body.lower()
    assert "full test suite once" in body


def test_review_loops_is_reachable_and_reviewer_carries_findings_over():
    assert "(review-loops.md)" in text("staged-items.md")
    reviewer = text("reviewer.md")
    assert "(review-loops.md)" in reviewer
    assert "previous round" in reviewer
    assert "only new BLOCKER or MAJOR" in reviewer
