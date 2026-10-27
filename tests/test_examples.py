"""Every shipped example is checked, including warning-only and unreadable projects."""

from __future__ import annotations

import importlib.util
import datetime as dt
import re
import shlex

import pytest

from conftest import ROOT, check, item, make_project, run_check_cli, run_init, set_queue, set_slot


SPEC = importlib.util.spec_from_file_location("release_examples", ROOT / "scripts" / "validate_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)

EXAMPLES = {
    "quick-script-cleanup": ("quick", "classic"),
    "work-project-data-migration": ("work-project", "unified"),
    "solo-research-literature-replication": ("solo-research", "unified"),
    "team-research-cv-leakage": ("team-research", "classic"),
    "competition-solo-tabular": ("competition-solo", "unified"),
    "competition-team-forecasting": ("competition-team", "classic"),
}
COORDINATION_FILES = ("agents.md", "plan.md", "discoveries.md", "handoff.md")


def test_release_checks_multiple_example_directories_and_ignores_files(tmp_path) -> None:
    examples = tmp_path / "examples"
    examples.mkdir()
    for name in ("first", "second"):
        make_project(examples, name, "--preset", "quick", "--platforms", "Cedar Shell", "--git", "off")
    (examples / "notes.md").write_text("Example collection notes\n", encoding="utf-8")
    errors = []
    release.check_examples(errors, tmp_path)
    assert errors == []

    # Checking only the first directory would miss this structural failure.
    (examples / "second" / "plan.md").unlink()
    release.check_examples(errors, tmp_path)
    assert len(errors) == 1
    assert "examples/second:" in errors[0] and "missing plan.md" in errors[0]


def test_release_rejects_warning_only_example(tmp_path) -> None:
    examples = tmp_path / "examples"
    examples.mkdir()
    target = make_project(examples, "warned", "--preset", "solo-research", "--agents", "2",
                          "--platforms", "Cedar Shell", "--user", "luma", "--git", "off")
    set_slot(target, "A", "Cedar Shell", "luma")
    set_slot(target, "B", "released", "none")
    set_queue(target, item("H-A-01", "B since 2026-10-24 09:00"))
    ordinary = run_check_cli(target)
    assert ordinary.returncode == 0 and "WARN plan.claim.stale" in ordinary.stdout

    errors = []
    release.check_examples(errors, tmp_path)
    assert len(errors) == 1
    assert "examples/warned:" in errors[0] and "WARN plan.claim.stale" in errors[0]


def test_shipped_examples_pass_without_any_findings() -> None:
    errors = []
    release.check_examples(errors)
    assert errors == [], "\n".join(errors)


def test_release_rejects_info_only_example(tmp_path) -> None:
    examples = tmp_path / "examples"
    examples.mkdir()
    target = make_project(examples, "advice", "--preset", "solo-research", "--platforms", "Cedar Shell",
                          "--user", "operator", "--git", "off")
    set_queue(target, item("H-A-01", extra=[("Workshop note", "preserve the source archive")]))
    assert run_check_cli(target, "--strict").returncode == 0
    errors = []
    release.check_examples(errors, tmp_path)
    assert len(errors) == 1 and "INFO plan.field.unknown" in errors[0]


@pytest.mark.parametrize("name", EXAMPLES)
def test_documented_init_command_reproduces_example_settings(tmp_path, name) -> None:
    """Run the documented command against an empty directory, not a hand-built settings fixture."""
    example = ROOT / "examples" / name
    readme = (example / "README.md").read_text(encoding="utf-8")
    command = re.search(r"^python .*init_research_orchestrator\.py .+$", readme, re.M)
    assert command is not None
    args = shlex.split(command.group(0))
    assert args[:3] == ["python", "skills/research-orchestrator/scripts/init_research_orchestrator.py",
                        f"examples/{name}"]
    result = run_init(tmp_path, *args[3:])
    assert result.returncode == 0, result.stderr
    generated = (tmp_path / "agents.md").read_text(encoding="utf-8")
    assert generated == (example / "agents.md").read_text(encoding="utf-8")
    preset, workflow = EXAMPLES[name]
    assert f"- Preset: {preset}\n" in generated
    assert f"- Workflow: {workflow}\n" in generated


def test_examples_are_small_complete_and_cover_each_preset() -> None:
    examples = ROOT / "examples"
    assert {path.name for path in examples.iterdir() if path.is_dir()} == set(EXAMPLES)
    for name in EXAMPLES:
        example = examples / name
        assert {path.name for path in example.iterdir()} == {*COORDINATION_FILES, "README.md", ".ro"}
        # 7.0.0 adds about 2.4 KB of working rules to each generated agents.md.
        assert sum(len((example / file).read_bytes().replace(b"\r\n", b"\n"))
                   for file in COORDINATION_FILES) <= 14_500, name
        checker = check(example)
        assert not checker.issues, [issue.render() for issue in checker.issues]
        assert checker.plan_items and checker.discoveries and checker.events, name


@pytest.mark.parametrize("name", EXAMPLES)
def test_paused_examples_do_not_rot_with_the_wall_clock(name) -> None:
    checker = check(ROOT / "examples" / name, now=dt.datetime(2030, 1, 1))
    assert not checker.issues, [
        issue.render() for issue in checker.issues]


def test_recorded_direction_reviews_are_complete_when_the_cycle_resumes() -> None:
    # Paused snapshots suspend cadence only; independently check their records with GD enabled.
    for name in ("work-project-data-migration", "competition-solo-tabular"):
        checker = check(ROOT / "examples" / name)
        checker.guards.add("GD")
        checker.check_direction(list(checker.discoveries.values()), 7)
        assert not [issue for issue in checker.issues if issue.check.startswith("guard.direction")]


def test_literature_example_uses_only_general_statistical_prose() -> None:
    example = ROOT / "examples" / "solo-research-literature-replication"
    for path in example.glob("*.md"):
        assert release.DOMAIN_VOCABULARY.search(path.read_text(encoding="utf-8")) is None, path


def test_quick_example_omits_empty_review_ceremony():
    example = ROOT / "examples" / "quick-script-cleanup"
    checker = check(example)
    assert all(not ({"Cross-check", "Reviews"} & set(disc.fields)) for disc in checker.discoveries.values())
    assert all(not ({"Review verdict", "Resource", "Other executor"} & set(event.fields))
               for event in checker.events)


def test_research_example_uses_plain_domain_terms():
    example = ROOT / "examples" / "team-research-cv-leakage" / "discoveries.md"
    text = example.read_text(encoding="utf-8")
    assert all(term in text for term in ("cross-validation", "labels", "folds", "target encoding"))
    assert all(term not in text for term in ("grouped review", "record conversion", "baseline parser"))
