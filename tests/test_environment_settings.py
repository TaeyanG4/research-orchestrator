"""Use a reported environment default and ask only when detection cannot resolve it."""

from __future__ import annotations

import pytest

from conftest import check, found, init, make_project, rs, run_init


@pytest.mark.parametrize("system,shell,expected", [
    ("win32", "", "windows/powershell"),
    ("linux", "", "linux/bash"),
    ("darwin", "", "macos/bash"),
    ("win32", r"C:\tools\bash.exe", "windows/bash"),
    ("darwin", "/bin/zsh", "macos/bash"),
    ("linux", "/bin/sh", "linux/bash"),
    ("linux", "/usr/bin/pwsh", "linux/powershell"),
])
def test_default_detects_os_and_usual_shell(monkeypatch, system, shell, expected):
    monkeypatch.setattr(rs.sys, "platform", system)
    monkeypatch.setenv("SHELL", shell)
    assert rs.detect_environment() == expected
    assert rs.resolve({}, None, {})["environment"] == expected


def test_every_preset_reports_environment_without_asking_when_detection_succeeds(monkeypatch):
    monkeypatch.setattr(rs, "detect_environment", lambda: "macos/bash")
    for name in rs.BUILTIN_PRESETS:
        preset = rs.load_preset(name)
        assert "environment" not in preset["asks"], name
        _missing, defaults = rs.question_answers(preset, {}, {})
        assert defaults["environment"] == "macos/bash", name
        assert "environment" not in rs.question_answers(preset, {"environment": "linux/bash"}, {})[1], name
        assert "environment" not in rs.question_answers(preset, {}, {"environment": "linux/bash"})[1], name


def test_user_presets_can_omit_environment_question():
    preset = rs.load_preset("quick")
    assert "environment" not in preset["asks"]
    assert rs.validate_preset(preset, "user preset") == preset


@pytest.mark.parametrize("system,shell", [("unknown-os", "bash"), ("linux", "/bin/fish"),
                                         ("win32", "cmd.exe")])
def test_unknown_environment_requires_an_answer_instead_of_a_guessed_default(monkeypatch, system, shell):
    monkeypatch.setattr(rs.sys, "platform", system)
    monkeypatch.setenv("SHELL", shell)
    assert rs.detect_environment() is None
    preset = rs.load_preset("quick")
    missing, defaults = rs.question_answers(preset, {}, {})
    assert missing == ["--environment"] and "environment" not in defaults
    for flags, stored in [({"environment": "linux/bash"}, {}), ({}, {"environment": "macos/bash"})]:
        assert rs.question_answers(preset, flags, stored)[0] == []
        assert rs.resolve(flags, preset, stored)["environment"] == (flags or stored)["environment"]


def test_unavailable_environment_stops_setup_before_writing_and_explicit_answer_recovers(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "detect_environment", lambda: None)
    assert init.main([str(tmp_path), "--preset", "quick", "--user", "operator"]) == 2
    assert not (tmp_path / "agents.md").exists()
    assert init.main([str(tmp_path), "--preset", "quick", "--user", "operator",
                      "--environment", "linux/bash"]) == 0


def test_quick_reports_environment_and_language_without_extra_questions(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rs, "detect_environment", lambda: "linux/bash")
    monkeypatch.setattr(init, "in_repository", lambda target: False)
    assert init.main([str(tmp_path), "--preset", "quick", "--user", "operator"]) == 0
    messages = capsys.readouterr().err
    assert "Info: Environment: linux/bash (default; override with --environment)" in messages
    assert "Info: Language: en (default; override with --language)" in messages
    assert "asks for --environment" not in messages and "asks for --language" not in messages
    assert "--git" not in messages


def test_initializer_stores_detected_default_and_preserves_a_declared_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "detect_environment", lambda: "macos/bash")
    target = tmp_path / "environment"
    target.mkdir()
    assert init.main([str(target), "--preset", "team-research"]) == 0
    path = target / "agents.md"
    assert "- Environment: macos/bash\n" in path.read_text(encoding="utf-8")
    monkeypatch.setattr(rs, "detect_environment", lambda: "windows/powershell")
    assert init.main([str(target), "--reconfigure", "--preset", "team-research"]) == 0
    assert "- Environment: macos/bash\n" in path.read_text(encoding="utf-8")
    assert init.main([str(target), "--reconfigure", "--environment", "linux/powershell"]) == 0
    assert "- Environment: linux/powershell\n" in path.read_text(encoding="utf-8")


def test_supported_environments_are_valid_settings(tmp_path):
    for environment in rs.SETTING["environment"].choices:
        target = make_project(tmp_path, environment.replace("/", "-"), "--environment", environment)
        assert rs.read_settings((target / "agents.md").read_text(encoding="utf-8")).values["environment"] == environment
        assert not found(check(target), check_id="settings.value"), environment


def test_invalid_environment_is_rejected_before_writing(tmp_path):
    for environment in ("windows/cmd", "unix/bash", "linux", "bash/linux"):
        result = run_init(tmp_path, "--environment", environment)
        assert result.returncode == 2, environment
        assert not (tmp_path / "agents.md").exists(), environment


def test_invalid_stored_environment_is_a_checker_error(tmp_path):
    target = make_project(tmp_path, "environment", "--environment", "linux/bash")
    path = target / "agents.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- Environment: linux/bash", "- Environment: linux/cmd"),
                    encoding="utf-8", newline="\n")
    assert [(issue.severity, issue.field) for issue in found(check(target), check_id="settings.value")] == [
        ("ERROR", "Environment")]
