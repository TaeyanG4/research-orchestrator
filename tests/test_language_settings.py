"""Language defaults, validation, setup questions, and persistent project preferences."""

from __future__ import annotations

import pytest

from conftest import FIXTURES, check, found, make_project, rs, run_init


def test_default_and_legacy_settings_use_english():
    legacy = rs.read_settings((FIXTURES / "v2" / "agents.md").read_text(encoding="utf-8"))
    assert rs.resolve({}, None, {})["language"] == "en"
    assert rs.resolve({}, None, legacy.values)["language"] == "en"


def test_every_preset_reports_language_without_requiring_a_question(tmp_path):
    for name in rs.BUILTIN_PRESETS:
        preset = rs.load_preset(name)
        assert "language" not in preset["asks"]
        assert rs.question_answers(preset, {}, {})[1]["language"] == "en"
        assert "language" not in rs.question_answers(preset, {"language": "ko"}, {})[1]
        assert "language" not in rs.question_answers(preset, {}, {"language": "ja"})[1]
        assert rs.validate_preset(preset, "user preset") == preset
    listed = run_init(tmp_path, "--list-presets")
    assert listed.returncode == 0, listed.stderr
    assert "language" in listed.stdout.splitlines()[0]
    for name in rs.BUILTIN_PRESETS:
        row = next(line for line in listed.stdout.splitlines() if line.startswith(name + " "))
        assert row.split()[4] == "en"


@pytest.mark.parametrize("language", ["en", "ko", "ja", "zh-CN", "zh-Hant-TW", "es-419", "EN-us"])
def test_language_code_round_trips_through_cli_and_checker(tmp_path, language):
    result = run_init(tmp_path, "--language", language)
    assert result.returncode == 0, result.stderr
    agents = (tmp_path / "agents.md").read_bytes()
    assert f"- Language: {language}\n".encode("utf-8") in agents
    assert b"\r\n" not in agents
    checked = check(tmp_path)
    assert checked.values["language"] == language
    assert not found(checked, "ERROR") and not found(checked, "WARN")


@pytest.mark.parametrize("language", ["", "e", "englishlong", "en_US", "en--US", "en-", "en-abcdefghi",
                                     "123", "한국어", "en us", "en\n- Git sync: push"])
def test_invalid_language_fails_before_writes(tmp_path, language):
    result = run_init(tmp_path, "--language", language)
    assert result.returncode == 2 and "Language" in result.stderr
    assert not (tmp_path / "agents.md").exists()


def test_reconfigure_keeps_language_across_presets_unless_passed(tmp_path):
    target = make_project(tmp_path, "language", "--preset", "quick", "--platforms", "Codex", "--language", "ko")
    records = {name: (target / name).read_bytes() for name in ("plan.md", "discoveries.md", "handoff.md")}
    for args, expected in [([], "ko"), (["--preset", "team-research", "--guards", "off"], "ko"),
                           (["--language", "ja"], "ja")]:
        result = run_init(target, "--reconfigure", *args)
        assert result.returncode == 0, result.stderr
        assert check(target).values["language"] == expected
        assert {name: (target / name).read_bytes() for name in records} == records


def test_default_is_reported_and_saved_presets_preserve_language_without_asking(tmp_path):
    result = run_init(tmp_path, "--preset", "team-research", "--save-preset", "team")
    assert result.returncode == 0, result.stderr
    assert "Info: Language: en (default; override with --language)" in result.stderr
    saved = rs.load_preset("user:team")
    assert "language" not in saved["asks"] and saved["language"] == "en"
    assert check(tmp_path).values["language"] == "en"


def test_ambiguous_language_needs_an_answer_only_without_an_existing_choice(monkeypatch):
    original = rs.default_value
    monkeypatch.setattr(rs, "default_value", lambda key, values: None if key == "language" else original(key, values))
    preset = rs.load_preset("quick")
    assert rs.question_answers(preset, {}, {})[0] == ["--language"]
    for flags, stored in [({"language": "ko"}, {}), ({}, {"language": "ja"})]:
        assert rs.question_answers(preset, flags, stored)[0] == []
    preset["language"] = "zh-CN"
    missing, defaults = rs.question_answers(preset, {}, {})
    assert not missing and defaults["language"] == "zh-CN"


def test_direct_edit_applies_immediately_and_invalid_code_is_a_checker_error(tmp_path):
    target = make_project(tmp_path, "language")
    path = target / "agents.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("- Language: en", "- Language: zh-CN"), encoding="utf-8", newline="\n")
    checked = check(target)
    assert checked.values["language"] == "zh-CN"
    assert not found(checked, "ERROR")
    assert [issue.check for issue in found(checked, "WARN")] == ["agents.rules.stale"]
    path.write_text(original.replace("- Language: en", "- Language: en_US"), encoding="utf-8", newline="\n")
    assert [(issue.severity, issue.field) for issue in found(check(target), check_id="settings.value")] == [
        ("ERROR", "Language")]
