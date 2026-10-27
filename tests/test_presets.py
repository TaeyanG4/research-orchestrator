"""Preset generation, question defaults, and settings validation."""

from __future__ import annotations

import json

import pytest

from conftest import SKILL, append_events, check, event, found, init, item, make_project, rs, run_init, severities

# P1 settings with P3 enforcement activated for every preset.
EXPECTED = {
    "quick": ("work", "classic", "self", "short", "off", "block", "single", ["platforms", "git"]),
    "work-project": ("work", "unified", "independent-review", "staged", "light", "block", "single", ["platforms", "git"]),
    "solo-research": ("research", "unified", "independent-review", "staged", "light", "block", "single", ["platforms", "git"]),
    "team-research": ("research", "classic", "cross-host-once", "short", "light", "block", "multi", ["platforms", "git"]),
    "competition-solo": ("competition", "unified", "independent-review", "staged", "light", "block", "single",
                         ["platforms", "competition", "external_actions", "phase_clock", "git"]),
    "competition-team": ("competition", "classic", "hybrid", "short", "light", "block", "multi",
                         ["platforms", "competition", "external_actions", "phase_clock", "git"]),
}
ANSWERS = {
    "platforms": {"single": ["--platforms", "Claude Code"], "multi": ["--platforms", "Claude Code, Codex"]},
    "competition": ["--competition", "hub/task-a"],
    "external_actions": ["--external-actions", "release-tool publish"],
    "phase_clock": ["--phase-clock", "2026-10-01,2026-12-01"],
    "environment": ["--environment", "linux/bash"],
    "language": ["--language", "en"],
}


@pytest.mark.parametrize('profile,collector,severity', [
    ('work', 'off', 'INFO'), ('work', 'Codex/worker', 'ERROR'), ('research', 'off', 'INFO'),
    ('competition', 'off', 'ERROR')])
def test_optional_work_summaries_are_advice_only(tmp_path, profile, collector, severity):
    target = tmp_path / 'summary'
    target.mkdir()
    assert init.main([str(target), '--preset', 'quick', '--profile', profile,
                      '--platforms', 'Codex', '--collector', collector, '--user', 'operator']) == 0
    handoff = target / 'handoff.md'
    text = handoff.read_text(encoding='utf-8')
    labels = ('Current best', 'Active compute', 'Plan collection')
    assert all((f'- {label}:' not in text) == (profile in {'work', 'research'} and collector == 'off') for label in labels)
    handoff.write_text('\n'.join(line for line in text.splitlines()
                                  if not any(line.startswith(f'- {label}:') for label in labels)) + '\n', encoding='utf-8')
    issues = [i for i in check(target).issues if i.check == 'handoff.shared.missing' and i.field in labels]
    assert len(issues) == 3
    assert {i.severity for i in issues} == {severity}


def answers(name: str) -> list[str]:
    mode, asks = EXPECTED[name][6], EXPECTED[name][7]
    args: list[str] = []
    for key in asks:
        if key != "git":  # asked only inside a git repository
            args += ANSWERS["platforms"][mode] if key == "platforms" else ANSWERS[key]
    return args


def test_preset_files_list_every_key_with_the_spec_values() -> None:
    names = sorted(path.stem for path in (SKILL / "presets").glob("*.json"))
    assert names == sorted(EXPECTED)  # no custom.json: custom is the absence of a preset
    for name, (profile, workflow, verification, item_size, guards, enforcement, mode, asks) in EXPECTED.items():
        data = json.loads((SKILL / "presets" / f"{name}.json").read_text(encoding="utf-8"))
        optional = {"receipt_policy"} if name.startswith("competition-") else set()
        assert set(data) == set(rs.REQUIRED_PRESET_FILE_KEYS) | optional
        assert data["block"] == rs.DEFAULT_BLOCK + (", external.gate" if profile == "competition" else "")
        assert (data["profile"], data["workflow"], data["verification"], data["item_size"], data["guards"],
                data["enforcement"], data["platform_mode"], data["asks"]) == (
            profile, workflow, verification, item_size, guards, enforcement, mode, asks)
        assert (data["collector"], data["reviewer"], data["queue_limits"]) == ("off", "off", "stop at 50, resume at 5")
        assert data["fallback"] == rs.DEFAULT_FALLBACK[mode]
        assert (data["platforms"] is None) == (mode == "single")


@pytest.mark.parametrize("preset,profile,compact", [("quick", "research", True), ("quick", "competition", True),
                                                   ("custom", "work", True), ("custom", "research", False)])
def test_plan_template_matches_compact_work_or_quick_rule(preset, profile, compact):
    values = rs.resolve({"preset": preset, "profile": profile}, None, {})
    text = init.render_plan(values, "routine", init.agent_sections(["A"]))
    assert ("- Goal: <goal or question>" in text) is compact
    assert ("- Resource: CPU | GPU | EITHER" in text) is not compact
    assert "{{" not in text


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_preset_generates_a_clean_project(tmp_path, name: str) -> None:
    target = make_project(tmp_path, name, "--preset", name, "--user", "operator", *answers(name))
    checker = check(target)
    assert checker.code == 0
    assert severities(checker)["ERROR"] == 0 and severities(checker)["WARN"] == 0, [i.render() for i in checker.issues]
    agents = (target / "agents.md").read_text(encoding="utf-8")
    profile, workflow, verification = EXPECTED[name][:3]
    assert f"- Preset: {name}\n" in agents and f"- Workflow: {workflow}\n" in agents
    stored = rs.read_settings(agents).values
    assert (stored["profile"], stored["workflow"], stored["verification"]) == (profile, workflow, verification)
    assert ("references/workflow-unified.md" in agents) == (workflow == "unified")
    assert "references/workflow-classic.md" not in agents
    for reference in ("sessions", "plan-items", "records", "project-rules", "presets"):
        assert f"references/{reference}.md" not in agents
    assert ("references/verification.md" in agents) == (verification not in {"cross-host-once", "self"})
    assert ("references/research-guards.md" in agents) == (EXPECTED[name][4] != "off")
    assert ("references/competition.md" in agents) == (profile == "competition")
    assert ("references/staged-items.md" in agents) == (EXPECTED[name][3] == "staged")
    assert "references/plan-collector.md" not in agents
    assert ("references/external-actions.md" in agents) == (stored["external_actions"] != "none")
    assert "references/compute.md" not in agents
    assert (SKILL / "references" / f"workflow-{workflow}.md").is_file()
    if verification == "independent-review":
        assert "references/staged-items.md" in agents
    plan = (target / "plan.md").read_text(encoding="utf-8")
    if workflow == "unified":
        assert plan.count("\n## Queue\n") == 1 and "## Agent:" not in plan
    else:
        assert "## Agent: A" in plan and "## Queue" not in plan
    if name == "quick":
        assert "including Sources, Hypothesis" not in plan
        assert "- Goal: <goal or question>" in plan
    assert "{{" not in agents


def test_preset_questions_must_be_answered(tmp_path) -> None:
    target = tmp_path / "ask"
    target.mkdir()
    result = run_init(target, "--preset", "competition-solo", "--platforms", "Claude Code")
    assert result.returncode == 2
    assert "--competition" in result.stderr and "--phase-clock" in result.stderr
    assert not any(target.iterdir())
    two_hosts = run_init(target, "--preset", "quick", "--platforms", "Claude Code, Codex")
    assert two_hosts.returncode == 2 and "--platforms" in two_hosts.stderr


@pytest.mark.parametrize("markers,host", [({}, "local"), ({"CLAUDECODE": "1"}, "Claude Code"),
                                        ({"CODEX_THREAD_ID": "thread-test"}, "Codex"),
                                        ({"GEMINI_CLI": "1"}, "Gemini CLI")])
def test_single_host_preset_reports_detected_default(tmp_path, monkeypatch, markers, host):
    for key, value in markers.items():
        monkeypatch.setenv(key, value)
    assert rs.detect_host() == host
    preset = rs.load_preset("quick")
    assert rs.question_answers(preset, {}, {})[1]["platforms"] == host
    assert rs.resolve({}, preset, {})["platforms"] == host
    result = run_init(tmp_path, "--preset", "quick", "--user", "operator")
    assert result.returncode == 0, result.stderr
    assert f"--platforms; using its default '{host}'" in result.stderr
    assert rs.read_settings((tmp_path / "agents.md").read_text(encoding="utf-8")).values["platforms"] == host


@pytest.mark.parametrize("marker", ["CLAUDECODE", "CODEX_THREAD_ID"])
def test_explicit_and_stored_hosts_override_detection(monkeypatch, marker):
    monkeypatch.setenv(marker, "test-session")
    preset = rs.load_preset("quick")
    for flags, stored in [({"platforms": "Chosen"}, {}), ({}, {"platforms": "Saved"})]:
        assert "platforms" not in rs.question_answers(preset, flags, stored)[1]
        assert rs.resolve(flags, preset, stored)["platforms"] == (flags or stored)["platforms"]


@pytest.mark.parametrize("marker,host,other", [("CLAUDECODE", "Claude Code", "Codex"),
                                             ("CODEX_THREAD_ID", "Codex", "Claude Code")])
def test_detected_host_requires_matching_collector_unless_platform_is_explicit(
        tmp_path, monkeypatch, marker, host, other):
    monkeypatch.setenv(marker, "test-session")
    result = run_init(tmp_path, "--preset", "quick", "--collector", f"{other}/worker")
    assert result.returncode == 2
    assert f"--collector platform '{other}' is not in --platforms ({host})" in result.stderr
    assert not (tmp_path / "agents.md").exists()
    result = run_init(tmp_path, "--preset", "quick", "--collector", f"{other}/worker",
                      "--platforms", other)
    assert result.returncode == 0, result.stderr
    stored = rs.read_settings((tmp_path / "agents.md").read_text(encoding="utf-8")).values
    assert stored["platforms"] == other
    assert stored["collector"] == f"on — {other} / worker"


@pytest.mark.parametrize("start_on", [False, True])
def test_collector_pointer_reconfiguration_preserves_full_setting(tmp_path, start_on):
    initial = "local/model" if start_on else "off"
    changed = "off" if start_on else "on — local / model"
    target = make_project(tmp_path, "collector", "--preset", "quick", "--platforms", "local", "--collector", initial)
    path = target / "agents.md"
    before = path.read_text(encoding="utf-8")
    assert ("references/plan-collector.md" in before) == start_on
    old = "on — local / model" if start_on else "off"
    path.write_text(before.replace(f"- Plan collector: {old}", f"- Plan collector: {changed}"),
                    encoding="utf-8", newline="\n")
    assert found(check(target), "WARN", "agents.rules.stale")
    assert not found(check(target), check_id="agents.rules.edited")
    result = run_init(target, "--reconfigure")
    assert result.returncode == 0, result.stderr
    after = path.read_text(encoding="utf-8")
    assert ("references/plan-collector.md" in after) != start_on
    assert rs.read_settings(after).values["collector"] == changed


def test_list_presets_lists_the_six_presets(tmp_path) -> None:
    result = run_init(tmp_path, "--list-presets")
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    for name, (profile, workflow, verification, *_rest) in EXPECTED.items():
        row = next(line for line in lines if line.startswith(name + " "))
        assert profile in row and workflow in row and verification in row


def test_template_conditions_accept_hyphenated_values_and_nesting() -> None:
    text = ("{{#if verification=independent-review,hybrid}}\nA\n{{#if itemsize=staged}}\nB\n{{/if}}\n{{/if}}\n"
            "x{{#if verification=cross-host-once}}C{{/if}}y{{#if verification=independent-review}}D{{/if}}\n")
    assert init.apply_conditions(text, {"verification": "independent-review", "itemsize": "staged"}) == "A\nB\nxyD\n"
    assert init.apply_conditions(text, {"verification": "hybrid", "itemsize": "short"}) == "A\nxy\n"
    assert init.apply_conditions(text, {"verification": "cross-host-once", "itemsize": "staged"}) == "xCy\n"


def test_competition_profile_without_competition_warns(tmp_path) -> None:
    target = make_project(tmp_path, "comp", "--preset", "competition-team", "--competition", "off",
                          "--phase-clock", "off")
    checker = check(target)
    assert [i.check for i in checker.issues if i.severity == "WARN"] == [
        "settings.competition", "settings.external.inactive"]
    assert checker.code == 0


def test_stored_only_settings_are_validated(tmp_path) -> None:
    target = make_project(tmp_path, "bad", "--preset", "quick", "--platforms", "Codex")
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace("- Guards: off", "- Guards: maybe"),
                      encoding="utf-8", newline="\n")
    checker = check(target)
    assert [(i.severity, i.check, i.field) for i in checker.issues] == [("ERROR", "settings.value", "Guards")]
    for bad in (["--phase-clock", "2026-12-01,2026-10-01"], ["--competition", "no-slug"], ["--workflow", "both"],
                ["--preset", "nope"], ["--profile", "sport"]):
        fresh = tmp_path / f"bad-{len(list(tmp_path.iterdir()))}"
        fresh.mkdir()
        result = run_init(fresh, *bad)
        assert result.returncode == 2 and not any(fresh.iterdir()), bad


def test_profile_aliases_are_stored_in_canonical_form(tmp_path) -> None:
    for alias, canonical in rs.ALIASES["profile"].items():
        target = make_project(tmp_path, f"alias-{alias}", "--profile", alias)
        assert f"- Profile: {canonical}\n" in (target / "agents.md").read_text(encoding="utf-8")
    # A stored alias is accepted but non-canonical.
    target = tmp_path / "alias-normal"
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace("- Profile: work", "- Profile: normal"),
                      encoding="utf-8", newline="\n")
    assert [(i.severity, i.check) for i in check(target).issues] == [("WARN", "settings.canonical")]


def test_question_defaults_are_reported_and_git_is_asked_only_in_repositories(tmp_path, monkeypatch, capsys) -> None:
    in_repo = tmp_path / "repo"
    in_repo.mkdir()
    (in_repo / ".git").mkdir()
    result = run_init(in_repo, "--preset", "team-research")
    assert result.returncode == 0, result.stderr
    assert all(flag in result.stderr for flag in ("--platforms", "--git", "--environment"))
    stored = rs.read_settings((in_repo / "agents.md").read_text(encoding="utf-8")).values
    assert stored["platforms"] == rs.load_preset("team-research")["platforms"]
    assert stored["git"] == "off" and stored["environment"] == rs.detect_environment()
    outside = tmp_path / "plain"
    outside.mkdir()
    # Model the absent repository explicitly: the temporary root may itself be inside a checkout.
    real_exists = init.Path.exists
    monkeypatch.setattr(init.Path, "exists", lambda path: path.name != ".git" and real_exists(path))
    assert init.main([str(outside), "--preset", "team-research", "--platforms", "Claude Code, Codex",
                      "--environment", "linux/bash"]) == 0
    assert "--git" not in capsys.readouterr().err


def test_classic_staged_items_validate_event_stages(tmp_path) -> None:
    assert (SKILL / "references" / "staged-items.md").is_file()
    target = make_project(tmp_path, "staged", "--preset", "team-research", "--item-size", "staged", "--user", "operator")
    agents = (target / "agents.md").read_text(encoding="utf-8")
    assert "references/staged-items.md" in agents and "workflow-classic.md" not in agents
    plan = target / "plan.md"
    text = plan.read_text(encoding="utf-8")
    plan.write_text(text.replace("## Agent: A\n\n", "## Agent: A\n\n" + item("H-A-01", claimed=None,
                                 stages="s1 dry run | s2 cut-over") + "\n", 1), encoding="utf-8", newline="\n")
    append_events(target, event("2026-10-25 10:00", "A", "H-A-01/s1", host="Claude Code", user="operator"),
                  event("2026-10-25 10:30", "A", "H-A-01/s3", host="Claude Code", user="operator"))
    checker = check(target)
    assert [i.check for i in found(checker, "WARN")] == ["event.stage.beyond"]
    assert severities(checker)["ERROR"] == 0, [i.render() for i in checker.issues]
