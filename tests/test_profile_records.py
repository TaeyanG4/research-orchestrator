"""Optional research state, explicit queue ordering, and relevant reading pointers."""
import pytest

from conftest import ROOT, check, init, rs, run_init


@pytest.mark.parametrize("preset", ["solo-research", "team-research", "work-project"])
@pytest.mark.parametrize("collector", ["off", "Shell/worker"])
def test_summary_omission_depends_on_collector(tmp_path, preset, collector):
    assert init.main([str(tmp_path), "--preset", preset, "--platforms", "Shell",
                      "--platform", "single", "--collector", collector, "--guards", "off"]) == 0
    path = tmp_path / "handoff.md"
    text = path.read_text(encoding="utf-8")
    names = ("Current best", "Active compute", "Plan collection")
    assert all((f"- {name}:" in text) == (collector != "off") for name in names)
    path.write_text("\n".join(line for line in text.splitlines()
                              if not any(line.startswith(f"- {name}:") for name in names)) + "\n",
                    encoding="utf-8")
    missing = [issue for issue in check(tmp_path).issues if issue.check == "handoff.shared.missing"]
    assert {issue.field for issue in missing} == set(names)
    assert {issue.severity for issue in missing} == ({"INFO"} if collector == "off" else {"ERROR"})


@pytest.mark.parametrize("ordering", ["queue", "priority"])
def test_team_research_can_choose_order_at_init(tmp_path, ordering):
    result = run_init(tmp_path, "--preset", "team-research", "--platforms", "Shell, Other", "--guards", "off",
                      "--agents", "2", "--ordering", ordering)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "plan.md"
    text = path.read_text(encoding="utf-8")
    assert ("Ordering: queue" in text) == (ordering == "queue")
    assert ("- Impact:" in text) == (ordering == "priority")
    if ordering == "queue":
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n### H-A-01 — Replicate the archive counts\n- Sources: none\n"
                         "- Hypothesis: the counts agree\n- Evidence: archive index\n"
                         "- Improvement: none\n- Next test: recount each section\n")
        # Team presets default to two slots; place the item under its matching owner.
        path.write_text(path.read_text(encoding="utf-8").replace("### H-A-01 — Replicate", "### H-B-01 — Replicate"),
                        encoding="utf-8")
        assert not [i for i in check(tmp_path).issues if i.check.startswith("plan.") and i.severity == "ERROR"]
    before = path.read_bytes()
    refusal = run_init(tmp_path, "--ordering", ordering)
    assert refusal.returncode != 0 and path.read_bytes() == before


@pytest.mark.parametrize("verification", ["self", "independent-review", "hybrid"])
def test_reading_pointers_follow_verification_policy(tmp_path, verification):
    assert init.main([str(tmp_path), "--preset", "quick", "--verification", verification]) == 0
    for name in ("agents.md", "discoveries.md"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert ("references/verification.md" in text) == (verification != "self")
    values = rs.resolve({"verification": "self", "reviewer": "Claude Code/reviewer"}, None, {})
    assert "verification" not in rs.reading_pointer_ids(values)


def test_all_shipped_examples_use_neutral_decision_classes():
    legacy = {"target-change", "model-change", "input-change", "combination"}
    neutral = {"outcome-definition-change", "method-change", "data-change", "combined", "operational", "other"}
    seen = set()
    for path in (ROOT / "examples").rglob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Decision class:"):
                value = line.split(":", 1)[1].strip()
                assert value in neutral and value not in legacy, path
                seen.add(value)
    assert {"method-change", "data-change"} <= seen


def test_enabling_collector_adds_missing_summaries_without_touching_history(tmp_path):
    assert init.main([str(tmp_path), "--preset", "solo-research", "--platforms", "Shell", "--guards", "off"]) == 0
    path = tmp_path / "handoff.md"
    original = path.read_text(encoding="utf-8").replace("- Current project state: initialized",
                    "- Current project state: initialized\n- Current best: none yet — pending tally")
    archive = "\n## Archived history\n- Active compute: GPU — B (H-B-01, since 2026-10-25 09:00)\n"
    path.write_text(original + archive, encoding="utf-8", newline="\n")
    result = run_init(tmp_path, "--reconfigure", "--collector", "Shell/worker")
    assert result.returncode == 0, result.stderr
    updated = path.read_text(encoding="utf-8")
    assert "- Current best: none yet — pending tally" in updated
    assert updated.endswith(archive)
    assert not [issue for issue in check(tmp_path).issues if issue.check == "handoff.shared.missing"]
    assert run_init(tmp_path, "--reconfigure", "--collector", "off").returncode == 0
    assert path.read_text(encoding="utf-8") == updated
