"""Migration and setup policy regressions, independent of runner host and clock."""

import datetime as dt
import re
import shutil
from types import SimpleNamespace

import pytest

from conftest import (NOW, ROOT, append_events, check, check_project, event, found, init,
                      make_project, rs, set_slot)


@pytest.fixture(autouse=True)
def fixed_migration_clock(monkeypatch):
    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 25, 12)

    clock = SimpleNamespace(datetime=FixedDateTime, date=dt.date, time=dt.time, timedelta=dt.timedelta)
    monkeypatch.setattr(init, "dt", clock)
    monkeypatch.setattr(check_project, "dt", clock)


def test_nonempty_quick_example_migrates_to_solo_with_evidence_and_zero_errors(tmp_path):
    target = tmp_path / "project"
    shutil.copytree(ROOT / "examples/quick-script-cleanup", target)
    discoveries = (target / "discoveries.md").read_bytes()
    original = init.parse_plan_items((target / "plan.md").read_text(encoding="utf-8"))[0]
    assert not found(check(target, NOW), "ERROR")
    assert init.main([str(target), "--reconfigure", "--preset", "solo-research", "--migrate",
                      "--guards", "light since 2026-10-25", "--user", "operator"]) == 0
    checker = check(target, NOW)
    assert not found(checker, "ERROR"), [issue.render() for issue in checker.issues]
    assert checker.plan_header["Ordering"] == "queue"
    item = checker.plan_items[original.item_id]
    assert item.fields["Hypothesis"] == original.fields["Goal"]
    assert item.fields["Evidence"] == original.fields["Evidence"]
    assert item.fields["Sources"] == original.fields["Sources"]
    migrated = (target / "discoveries.md").read_bytes()
    newline = b"\r\n" if b"\r\n" in discoveries else b"\n"
    assert migrated.replace(b"- Cross-check: PENDING" + newline, b"").replace(b"- Reviews: none" + newline, b"") == discoveries
    assert (target / "discoveries.md.pre-migrate").read_bytes() == discoveries
    assert checker.discoveries["D-A-001"].fields["Cross-check"] == "PENDING"
    assert checker.discoveries["D-A-001"].fields["Reviews"] == "none"
    assert "discoveries.md.pre-migrate" in (target / "handoff.md").read_text(encoding="utf-8")


def test_compact_migration_preserves_order_and_normalizes_optional_fields(tmp_path):
    target = make_project(tmp_path, "project", "--preset", "quick", "--platforms", "Shell", "--user", "operator")
    plan = "# Plan\n\nNext: H-A-02\n\n## Agent: A\n\n"
    for key in ("H-A-02", "H-A-01"):
        plan += (f"### {key} — boundary\n- Goal: preserve empty inputs\n"
                 "- Evidence: the interface accepts empty input\n- Next step: test the boundary\n\n")
    (target / "plan.md").write_text(plan, encoding="utf-8")
    assert init.main([str(target), "--reconfigure", "--preset", "solo-research", "--migrate",
                      "--guards", "off", "--user", "operator"]) == 0
    checker = check(target, NOW)
    assert not found(checker, "ERROR"), [issue.render() for issue in checker.issues]
    assert list(checker.plan_items) == ["H-A-02", "H-A-01"]
    assert checker.plan_header == {"Ordering": "queue", "Next": "H-A-02"}
    assert checker.plan_items["H-A-02"].fields["Next test"] == "test the boundary"
    assert checker.plan_items["H-A-02"].fields["Sources"] == "none"


def test_invalid_proposed_migration_never_writes_or_creates_backups(tmp_path, monkeypatch, capsys):
    target = make_project(tmp_path, "project", "--preset", "quick", "--platforms", "Shell", "--user", "operator")
    before = {path: path.read_bytes() for path in target.rglob("*") if path.is_file()}
    render = init.plan_to_unified

    def invalid(*args):
        plan, count = render(*args)
        return plan.replace("## Queue", "## Wrong section"), count

    monkeypatch.setattr(init, "plan_to_unified", invalid)
    assert init.main([str(target), "--reconfigure", "--preset", "solo-research", "--migrate",
                      "--guards", "off", "--user", "operator"]) == 1
    assert "proposed migration" in capsys.readouterr().err
    assert {path: path.read_bytes() for path in target.rglob("*") if path.is_file()} == before


def test_alias_normalization_preserves_evidence_bullets_and_fenced_examples():
    settings = rs.resolve({"preset": "solo-research"}, rs.load_preset("solo-research"), {})
    plan = ("# Plan\n\n## Agent: A\n\n### H-A-01 — boundary\n- Goal: preserve input\n"
            "- Evidence: measured result\n  - All rows matched\n- Next step: repeat\n\n"
            "```text\n- Goal: sample stays unchanged\n```\n")
    result = init.normalize_plan_aliases(plan, settings)
    assert "- Evidence: measured result\n  - All rows matched\n- Improvement: none\n" in result
    assert "- Hypothesis: preserve input" in result
    assert "```text\n- Goal: sample stays unchanged\n```" in result


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("review_fields", ["", "- Cross-check: PENDING\n",
    "- Reviews: none\n", "- Cross-check: VERIFIED\n- Reviews: Shell (A): CLOSED — reproduced\n"])
def test_review_normalization_is_additive_preserving_existing_fields_fences_and_prose(newline, review_fields):
    text = ("# Discoveries\n\n```markdown\n## D-Z-999 — sample only\n- Finding: untouched\n```\n\n"
            "## D-A-001 — actual measurement\n- Source: A\n- Host: Shell\n- User: operator\n"
            "- Date: 2026-10-25\n" + review_fields + "- Finding: all six records matched\n"
            "- Evidence: measured 6/6\n  - Preserve this exact evidence detail.\n"
            "- Implication: retain the parser\n\nPreserve this trailing prose.\n").replace("\n", newline)
    result = init.normalize_discovery_review_fields(text)
    restored = result
    if "- Cross-check:" not in review_fields:
        assert result.count("- Cross-check: PENDING") == 1
        restored = restored.replace("- Cross-check: PENDING" + newline, "", 1)
    if "- Reviews:" not in review_fields:
        assert result.count("- Reviews: none") == 1
        restored = restored.replace("- Reviews: none" + newline, "", 1)
    assert restored == text
    assert init.normalize_discovery_review_fields(result) == result


def test_proposed_discovery_changes_are_validated_before_atomic_migration(tmp_path, monkeypatch):
    target = tmp_path / "project"
    shutil.copytree(ROOT / "examples/quick-script-cleanup", target)
    before = {path: path.read_bytes() for path in target.rglob("*") if path.is_file()}
    normalize = init.normalize_discovery_review_fields
    monkeypatch.setattr(init, "normalize_discovery_review_fields", lambda text:
                        normalize(text).replace("- Evidence:", "- Missing evidence:"))
    assert init.main([str(target), "--reconfigure", "--preset", "solo-research", "--migrate",
                      "--guards", "off", "--user", "operator"]) == 1
    assert {path: path.read_bytes() for path in target.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("host", ["Claude Code", "Codex", "Other host"])
@pytest.mark.parametrize("platforms,mode,severity", [("local", "single", "WARN"),
                                                    ("local, Peer", "multi", "ERROR"),
                                                    ("Named host", "single", "ERROR")])
def test_local_single_host_accepts_real_session_with_warning(tmp_path, host, platforms, mode, severity):
    target = make_project(tmp_path, "project", "--preset", "quick", "--platforms", platforms,
                          "--platform", mode, "--user", "operator")
    set_slot(target, "A", host)
    append_events(target, event("2026-10-25 10:00", "A", "none", host=host))
    issues = found(check(target, NOW), check_id="host.unlisted")
    assert len(issues) == 2 and {issue.severity for issue in issues} == {severity}


@pytest.mark.parametrize("commands,block,expected", [("none", "external.gate", True),
    ("release-tool publish", "external.gate", False), ("none", "none", False)])
def test_checker_warns_when_external_gate_has_no_patterns(tmp_path, commands, block, expected):
    target = make_project(tmp_path, "project", "--preset", "quick", "--external-actions", commands,
                          "--block", block, "--platforms", "Shell")
    assert bool(found(check(target, NOW), "WARN", "settings.external.inactive")) is expected


@pytest.mark.parametrize("preset", ["competition-solo", "competition-team"])
@pytest.mark.parametrize("platform,explicit,missing", [("hub/task", None, True),
    ("kaggle/task", None, False), ("hub/task", "none", False),
    ("hub/task", "release-tool publish", False)])
def test_competition_questions_require_unknown_platform_commands(preset, platform, explicit, missing):
    flags = {"competition": platform, "phase_clock": "off", "external_actions": explicit}
    questions, defaults = rs.question_answers(rs.load_preset(preset), flags, {})
    assert ("--external-actions" in questions) is missing
    if platform == "kaggle/task":
        assert defaults["external_actions"] == "kaggle competitions submit; kaggle kernels push"


@pytest.mark.parametrize("source,missing", [("default", True), ("explicit", False)])
def test_competition_reconfiguration_distinguishes_inherited_and_explicit_none(source, missing):
    questions, _ = rs.question_answers(rs.load_preset("competition-solo"),
        {"competition": "hub/task", "phase_clock": "off"},
        {"external_actions": "none", "_external_actions_source": source})
    assert ("--external-actions" in questions) is missing


def test_presets_guidance_explains_host_and_inactive_gate():
    text = (ROOT / "skills/research-orchestrator/references/presets.md").read_text(encoding="utf-8")
    assert "Run init inside the host session" in text
    assert "settings.external.inactive" in text


def transition_project(tmp_path, workflow, newline="\n"):
    target = make_project(tmp_path, "transition", "--profile", "work", "--workflow", workflow,
                          "--verification", "self", "--guards", "off", "--platforms", "Shell",
                          "--environment", "linux/bash", "--user", "operator")
    section = "Queue" if workflow == "unified" else "Agent: A"
    plan = f"# Plan\n\nNext: H-A-02\n\n## {section}\n\n"
    for key in ("H-A-02", "H-A-01"):
        plan += f"### {key} — boundary\n"
        if workflow == "unified":
            plan += "- Claimed: none\n"
        plan += ("- Goal: preserve empty inputs\n- Evidence: six records matched\n"
                 "  - Keep this measurement detail.\n- Next step: test the boundary\n\n")
    discovery = ("# Discoveries\n\n## D-A-001 — measurement\n- Source: A\n- Host: Shell\n"
                 "- User: operator\n- Date: 2026-10-25\n- Finding: six records matched\n"
                 "- Evidence: fixture comparison passed 6/6\n  - Preserve exact bytes.\n"
                 "- Implication: retain the parser\n\nTrailing context stays here.\n")
    for name, text in (("plan.md", plan), ("discoveries.md", discovery)):
        (target / name).write_bytes(text.replace("\n", newline).encode("utf-8"))
    assert not found(check(target, NOW), "ERROR")
    return target


def apply_transition(target, key, value, edited):
    args = [str(target), "--reconfigure"]
    if edited:
        path = target / "agents.md"
        text = path.read_text(encoding="utf-8")
        text = re.sub(rf"^- {rs.SETTING[key].label}: .*", f"- {rs.SETTING[key].label}: {value}", text, flags=re.M)
        path.write_text(text, encoding="utf-8", newline="\n")
    else:
        args.extend((rs.SETTING[key].flag, value))
    return init.main(args)


@pytest.mark.parametrize("workflow", ["classic", "unified"])
@pytest.mark.parametrize("edited", [False, True])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_profile_only_transition_preserves_layout_queue_evidence_and_backups(tmp_path, workflow, edited, newline):
    target = transition_project(tmp_path, workflow, newline)
    original = {name: (target / name).read_bytes() for name in init.COORDINATION_FILES}
    assert apply_transition(target, "profile", "research", edited) == 0
    checker = check(target, NOW)
    assert not found(checker, "ERROR"), [issue.render() for issue in checker.issues]
    assert checker.values["workflow"] == workflow and checker.values["verification"] == "self"
    assert checker.plan_header == {"Next": "H-A-02", "Ordering": "queue"}
    assert list(checker.plan_items) == ["H-A-02", "H-A-01"]
    for item in checker.plan_items.values():
        assert item.fields["Hypothesis"] == "preserve empty inputs"
        assert item.fields["Next test"] == "test the boundary"
        assert item.fields["Sources"] == item.fields["Improvement"] == "none"
    plan = (target / "plan.md").read_bytes()
    assert ("- Evidence: six records matched\n  - Keep this measurement detail.\n".replace("\n", newline)
            .encode("utf-8")) in plan
    assert b"\r\r\n" not in plan
    assert (target / "plan.md.pre-migrate").read_bytes() == original["plan.md"]
    agents_before = (original["agents.md"].replace(b"- Profile: work", b"- Profile: research")
                     if edited else original["agents.md"])
    if (target / "agents.md").read_bytes() != agents_before:
        assert (target / "agents.md.pre-migrate").read_bytes() == agents_before
    else:
        assert not (target / "agents.md.pre-migrate").exists()
    assert (target / "discoveries.md").read_bytes() == original["discoveries.md"]
    assert (target / "handoff.md").read_bytes() == original["handoff.md"]


@pytest.mark.parametrize("workflow", ["classic", "unified"])
@pytest.mark.parametrize("edited", [False, True])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_review_only_transition_is_pending_additive_and_backed_up(tmp_path, workflow, edited, newline):
    target = transition_project(tmp_path, workflow, newline)
    original = {name: (target / name).read_bytes() for name in init.COORDINATION_FILES}
    assert apply_transition(target, "verification", "independent-review", edited) == 0
    checker = check(target, NOW)
    assert not found(checker, "ERROR"), [issue.render() for issue in checker.issues]
    assert checker.values["workflow"] == workflow and checker.values["profile"] == "work"
    assert checker.discoveries["D-A-001"].fields["Cross-check"] == "PENDING"
    assert checker.discoveries["D-A-001"].fields["Reviews"] == "none"
    after = (target / "discoveries.md").read_bytes()
    assert after.replace(("- Cross-check: PENDING" + newline).encode(), b"").replace(
        ("- Reviews: none" + newline).encode(), b"") == original["discoveries.md"]
    assert (target / "discoveries.md.pre-migrate").read_bytes() == original["discoveries.md"]
    assert (target / "plan.md").read_bytes() == original["plan.md"]
    assert (target / "handoff.md").read_bytes() == original["handoff.md"]
    assert not (target / "plan.md.pre-migrate").exists()


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_incompatible_same_layout_transition_preserves_all_files_and_metadata(tmp_path, workflow, capsys):
    target = transition_project(tmp_path, workflow)
    original = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    assert init.main([str(target), "--reconfigure", "--platforms", "Different host"]) == 1
    assert "host.unlisted" in capsys.readouterr().err
    assert {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()} == original


def test_goal_normalization_leaves_nonitem_prose_and_fenced_samples_unchanged():
    plan = ("# Plan\n\n- Goal: unchanged preface\n\n## Agent: A\n\n"
            "### H-A-01 — boundary\n- Goal: preserve input\n- Evidence: observed\n- Next step: repeat\n\n"
            "## Notes\n- Goal: unchanged notes\n```text\n- Goal: unchanged sample\n```\n")
    settings = rs.resolve({"profile": "research"}, None, {})
    updated = init.normalize_plan_aliases(plan, settings)
    assert "- Hypothesis: preserve input" in updated
    assert all(f"- Goal: unchanged {part}" in updated for part in ("preface", "notes", "sample"))


def test_goal_normalization_does_not_modify_an_identical_fenced_item():
    block = ("### H-A-01 — boundary\n- Hypothesis: preserve input\n"
             "- Evidence: observed\n- Next test: repeat\n")
    sample = "```markdown\n" + block + "```\n"
    plan = "# Plan\n\n" + sample + "\n## Agent: A\n\n" + block
    updated = init.normalize_plan_aliases(plan, rs.resolve({"profile": "research"}, None, {}))
    assert sample in updated
    live = updated.split("## Agent: A\n", 1)[1]
    assert "- Sources: none\n- Hypothesis: preserve input" in live
    assert "- Improvement: none\n- Next test: repeat" in live
    assert init.normalize_plan_aliases(updated, rs.resolve({"profile": "research"}, None, {})) == updated


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_profile_transition_with_quick_preset_normalizes_work_only_next_step(tmp_path, workflow):
    target = transition_project(tmp_path, workflow)
    assert init.main([str(target), "--reconfigure", "--preset", "quick", "--workflow", workflow]) == 0
    before = (target / "plan.md").read_bytes()
    assert init.main([str(target), "--reconfigure", "--profile", "research"]) == 0
    checker = check(target, NOW)
    assert not found(checker, "ERROR"), [issue.render() for issue in checker.issues]
    assert checker.values["preset"] == "quick"
    assert (target / "plan.md").read_bytes() == before.replace(b"- Next step:", b"- Next test:")
    assert (target / "plan.md.pre-migrate").read_bytes() == before


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_review_policy_rejects_previously_self_verified_claim_without_rewriting_it(tmp_path, workflow, capsys):
    target = transition_project(tmp_path, workflow)
    path = target / "discoveries.md"
    text = path.read_text(encoding="utf-8").replace("- Finding:", "- Cross-check: VERIFIED\n- Finding:")
    text = text.replace("\nTrailing context", "- Reviews:\n  - Shell (A): CLOSED — reproduced\n\nTrailing context")
    path.write_text(text, encoding="utf-8", newline="\n")
    assert not found(check(target, NOW), "ERROR")
    original = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    assert init.main([str(target), "--reconfigure", "--verification", "independent-review"]) == 1
    assert "discovery.state.unbacked" in capsys.readouterr().err
    assert {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()} == original
