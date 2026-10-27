import json
from pathlib import Path

from scripts.evals.reconstruct_snapshot import reconstruct

ROOT = Path(__file__).resolve().parents[1]


def test_headline_evidence_is_reconstructible_without_transcripts():
    result = reconstruct(ROOT / "docs/evals/evidence/iteration-6.zip")
    assert result["matched_cases"] == 31 and result["excluded_runs"] == 18
    assert result["matched_mean_percent"] == {"with_skill": 99.71, "old_skill": 56.31}
    assert result["assertions"] == {"with_skill": {"passed": 231, "total": 232},
                                    "old_skill": {"passed": 110, "total": 207}}
    original = reconstruct(ROOT / "docs/evals/evidence/iteration-6.zip", "original")
    assert original["excluded_runs"] == 19


def test_neutral_interface_metadata_matches_between_plugins():
    generic = json.loads((ROOT / "plugin.json").read_text())["extensions"]["com.openai"]["interface"]
    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())["interface"]
    assert generic == codex
    assert generic["capabilities"] == ["Queue and prioritize work", "Preserve findings", "Route long jobs", "Resume any project"]
    assert "work queue" in generic["defaultPrompt"][1]


def test_owner_scope_and_minimal_evidence_links_are_consistent():
    for name in ["docs/plans/v3-plan.md", "docs/plans/v3-p4-spec.md", "docs/evals/evidence/regrade-procedure.md"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "2026-10-26" in text and "no further scenario runs or description optimisation" in text
        assert "owner validates in real use" in text
    for path in ROOT.glob("README*.md"):
        text = path.read_text(encoding="utf-8")
        assert text.count("](docs/evals/README.md)") == 1
        assert "231/232" in (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
        assert "--remove-hooks" in text and "Python 3.12+" in text
        assert "python install.py --host claude-code" in text
        assert "python install.py --host codex" in text
        disclosure = next(part for part in text.split("\n\n") if "](docs/evals/README.md)" in part)
        assert len(disclosure.splitlines()) == 1
        assert "docs/evals/evidence/" not in text


def test_hook_capabilities_are_read_on_demand():
    reference = ROOT / "skills/research-orchestrator/references"
    daily = (reference / "hooks.md").read_text(encoding="utf-8")
    detail = (reference / "hooks-capabilities.md").read_text(encoding="utf-8")
    assert "hooks-capabilities.md" in daily
    evidence = (ROOT / "docs/evals/README.md").read_text(encoding="utf-8")
    assert "Claude Code observation" not in daily and "Claude Code observation" in detail
    assert '../../skills/research-orchestrator/references/hooks-capabilities.md' in evidence
    assert "docs/evals/README.md" in detail
    assert len(daily.encode("utf-8")) <= 5000
    assert "2026-10-27" in evidence and "Unverified" in detail
