"""Settings precedence and user presets (spec §2, §3; test 6)."""

from __future__ import annotations

import json

from conftest import make_project, rs, run_init


def settings_of(target) -> dict[str, str]:
    return rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values


def edit_lines(target, **lines: str) -> None:
    agents = target / "agents.md"
    text = agents.read_text(encoding="utf-8")
    for label, value in lines.items():
        label = rs.SETTING[label].label
        start = text.index(f"\n- {label}: ") + 1
        end = text.index("\n", start)
        text = text[:start] + f"- {label}: {value}" + text[end:]
    agents.write_text(text, encoding="utf-8", newline="\n")


def test_new_project_flag_beats_preset_beats_v2_default(tmp_path) -> None:
    target = make_project(tmp_path, "new", "--preset", "solo-research", "--platforms", "Claude Code",
                          "--verification", "self")
    values = settings_of(target)
    assert values["verification"] == "self"            # flag
    assert values["workflow"] == "unified"             # preset
    assert values["git"] == "off" and values["autonomy"] == "present" and values["phase_clock"] == "off"  # v2 defaults
    assert values["preset"] == "solo-research"
    plain = make_project(tmp_path, "plain")
    assert settings_of(plain)["preset"] == "custom" and settings_of(plain)["workflow"] == "classic"


def test_reconfigure_without_preset_flag_beats_stored_beats_default(tmp_path) -> None:
    target = make_project(tmp_path, "team", "--preset", "team-research")
    edit_lines(target, guards="strict", reviewer="on — Codex / sol")
    result = run_init(target, "--reconfigure", "--item-size", "staged")
    assert result.returncode == 0, result.stderr
    values = settings_of(target)
    assert values["item_size"] == "staged"                                     # flag
    assert rs.guard_mode(values["guards"]) == "strict" and values["reviewer"] == "on — Codex / sol"  # stored
    assert values["preset"] == "team-research" and values["workflow"] == "classic"   # stored
    assert values["autonomy"] == "present"                                     # stored (= v2 default)


def test_reconfigure_with_preset_flag_beats_preset_beats_stored(tmp_path) -> None:
    target = make_project(tmp_path, "team", "--preset", "team-research")
    edit_lines(target, guards="strict", autonomy="away")
    result = run_init(target, "--reconfigure", "--preset", "competition-team", "--competition", "hub/task-a", "--external-actions", "release-tool publish",
                      "--phase-clock", "off", "--enforcement", "off")
    assert result.returncode == 0, result.stderr
    values = settings_of(target)
    assert values["enforcement"] == "off"                    # flag beats the preset's warn
    assert rs.guard_mode(values["guards"]) == "light"         # preset beats the stored strict
    assert values["profile"] == "competition" and values["verification"] == "hybrid"
    assert values["autonomy"] == "away"                      # not covered by presets: stored
    assert values["competition"] == "hub/task-a" and values["preset"] == "competition-team"


def test_a_preset_file_edited_later_never_changes_a_project(tmp_path, isolated_home) -> None:
    source = make_project(tmp_path, "src", "--preset", "team-research", "--guards", "strict")
    assert run_init(source, "--save-preset", "mine").returncode == 0
    target = make_project(tmp_path, "uses", "--preset", "user:mine")
    path = isolated_home / "presets" / "mine.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["guards"] = "off"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert run_init(target, "--reconfigure").returncode == 0
    assert rs.guard_mode(settings_of(target)["guards"]) == "strict"  # resolved values are persisted in agents.md


def test_user_preset_round_trip(tmp_path, isolated_home) -> None:
    source = make_project(tmp_path, "src", "--preset", "competition-team", "--competition", "hub/task-a", "--external-actions", "release-tool publish",
                          "--phase-clock", "2026-10-01,2026-12-01", "--verification", "cross-host-once",
                          "--guards", "strict", "--collector", "Claude Code/sonnet")
    saved = run_init(source, "--save-preset", "my-competition")
    assert saved.returncode == 0, saved.stderr
    path = isolated_home / "presets" / "my-competition.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data) == list(rs.PRESET_FILE_KEYS)
    source_values = settings_of(source)
    expected = {key: source_values[key] for key in rs.PRESET_KEYS}
    expected["guards"] = rs.guard_mode(expected["guards"])
    assert {key: data[key] for key in rs.PRESET_KEYS} == expected
    assert data["asks"] == ["platforms", "competition", "phase_clock", "git"]

    listed = run_init(tmp_path, "--list-presets")
    assert "user:my-competition" in listed.stdout

    missing = tmp_path / "missing"
    missing.mkdir()
    asked = run_init(missing, "--preset", "user:my-competition")
    questions = asked.stderr.split("Example:", 1)[0]
    assert asked.returncode == 2 and "--competition" in questions and "--platforms" not in questions

    target = make_project(tmp_path, "reuse", "--preset", "user:my-competition",
                          "--competition", "hub/task-b", "--phase-clock", "off")
    values = settings_of(target)
    assert {key: values[key] for key in rs.PRESET_KEYS} == {key: source_values[key] for key in rs.PRESET_KEYS}
    assert values["preset"] == "user:my-competition" and values["competition"] == "hub/task-b"


def test_save_preset_while_initializing_and_unknown_user_preset(tmp_path, isolated_home) -> None:
    make_project(tmp_path, "fresh", "--preset", "quick", "--platforms", "Codex", "--save-preset", "quick-codex")
    data = json.loads((isolated_home / "presets" / "quick-codex.json").read_text(encoding="utf-8"))
    assert data["platforms"] == "Codex" and data["verification"] == "self"
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    result = run_init(nowhere, "--preset", "user:absent")
    assert result.returncode == 2 and "not found" in result.stderr


def test_a_single_platform_preset_does_not_inherit_several_hosts(tmp_path) -> None:
    target = make_project(tmp_path, "team", "--preset", "team-research")
    before = (target / "agents.md").read_bytes()
    refused = run_init(target, "--reconfigure", "--preset", "competition-solo", "--competition", "hub/task-a", "--external-actions", "release-tool publish",
                       "--phase-clock", "off")
    assert refused.returncode == 2
    assert "preset competition-solo is single-platform; pass --platforms <one host>" in refused.stderr
    assert (target / "agents.md").read_bytes() == before
    answered = run_init(target, "--reconfigure", "--preset", "competition-solo", "--competition", "hub/task-a", "--external-actions", "release-tool publish",
                        "--phase-clock", "off", "--platforms", "Claude Code")
    assert answered.returncode == 1 and "--migrate" in answered.stderr  # next check: the workflow changes


def test_saved_single_platform_preset_hosts_beat_stored_hosts_and_yield_to_flags(tmp_path) -> None:
    make_project(tmp_path, "source", "--preset", "quick", "--platforms", "Codex",
                 "--save-preset", "single-host")
    target = make_project(tmp_path, "team", "--preset", "team-research")
    applied = run_init(target, "--reconfigure", "--preset", "user:single-host")
    assert applied.returncode == 0, applied.stderr
    assert settings_of(target)["platforms"] == "Codex"
    overridden = run_init(target, "--reconfigure", "--preset", "user:single-host",
                          "--platforms", "Claude Code")
    assert overridden.returncode == 0, overridden.stderr
    assert settings_of(target)["platforms"] == "Claude Code"
    refused = run_init(target, "--reconfigure", "--preset", "user:single-host",
                       "--platforms", "Claude Code, Codex")
    assert refused.returncode == 2 and "is single-platform" in refused.stderr
