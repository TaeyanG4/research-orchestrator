"""Competition setup defaults use adapter policy and an explicit deadline hint."""

import datetime as dt
from types import SimpleNamespace

import pytest

from conftest import NOW, check, found, init, rs


@pytest.fixture(autouse=True)
def fixed_setup_date(monkeypatch):
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 25)

    monkeypatch.setattr(rs, "dt", SimpleNamespace(date=FixedDate, datetime=dt.datetime, timedelta=dt.timedelta))


@pytest.mark.parametrize("preset", ["competition-solo", "competition-team"])
def test_adapter_deadline_answers_setup_without_extra_questions(tmp_path, preset, capsys):
    flags = {"competition": "kaggle/fixture-task deadline=2026-12-01", "environment": "linux/bash"}
    missing, defaults = rs.question_answers(rs.load_preset(preset), flags, {})
    assert missing == []
    assert defaults["external_actions"] == "kaggle competitions submit; kaggle kernels push"
    assert defaults["phase_clock"] == "start 2026-10-25, deadline 2026-12-01"
    target = tmp_path / "competition"
    target.mkdir()
    assert init.main([str(target), "--preset", preset, "--competition", flags["competition"],
                      "--environment", "linux/bash", "--user", "operator"]) == 0
    stderr = capsys.readouterr().err
    assert "asks for --external-actions" not in stderr
    assert "asks for --phase-clock" not in stderr
    values = rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values
    assert values["competition"] == "kaggle/fixture-task"
    assert values["external_actions"] == defaults["external_actions"]
    assert values["phase_clock"] == defaults["phase_clock"]
    assert not found(check(target, NOW), "ERROR")


@pytest.mark.parametrize("flags,stored,expected", [
    ({"phase_clock": "off"}, {}, "off"),
    ({"phase_clock": "2026-10-01,2026-11-01"}, {}, "start 2026-10-01, deadline 2026-11-01"),
    ({}, {"phase_clock": "off"}, "off"),
    ({}, {"phase_clock": "start 2026-10-01, deadline 2026-11-01"}, "start 2026-10-01, deadline 2026-11-01"),
])
def test_explicit_and_stored_phase_clocks_override_deadline_hint(flags, stored, expected):
    flags = {"competition": "kaggle/fixture-task deadline=2026-12-01", **flags}
    preset = rs.load_preset("competition-solo")
    assert "--phase-clock" not in rs.question_answers(preset, flags, stored)[0]
    assert rs.resolve(flags, preset, stored)["phase_clock"] == expected


@pytest.mark.parametrize("external", ["none", "release-tool publish"])
def test_deadline_adapter_defaults_preserve_explicit_external_policy(external):
    flags = {"competition": "kaggle/fixture-task deadline=2026-12-01", "external_actions": external}
    preset = rs.load_preset("competition-solo")
    assert "external_actions" not in rs.question_answers(preset, flags, {})[1]
    values = rs.resolve(flags, preset, {})
    assert values["external_actions"] == external
    assert values["_external_actions_source"] == "explicit"


def test_unmapped_platform_still_needs_command_patterns_with_deadline():
    flags = {"competition": "hub/fixture-task deadline=2026-12-01", "environment": "linux/bash"}
    missing, defaults = rs.question_answers(rs.load_preset("competition-solo"), flags, {})
    assert missing == ["--external-actions"]
    assert defaults["phase_clock"] == "start 2026-10-25, deadline 2026-12-01"


def test_competition_without_deadline_still_needs_phase_clock():
    missing, _defaults = rs.question_answers(rs.load_preset("competition-solo"),
        {"competition": "kaggle/fixture-task", "environment": "linux/bash"}, {})
    assert missing == ["--phase-clock"]


def test_adapter_default_does_not_answer_an_unmapped_reconfiguration():
    preset = rs.load_preset("competition-solo")
    stored = rs.resolve({"competition": "kaggle/task", "phase_clock": "off"}, preset, {})
    missing, _defaults = rs.question_answers(preset, {"competition": "hub/task"}, stored)
    assert missing == ["--external-actions"]
    stored["external_actions"] = "chosen-tool publish"
    assert rs.question_answers(preset, {"competition": "hub/task"}, stored)[0] == []
    assert rs.resolve({"competition": "hub/task"}, preset, stored)["external_actions"] == "chosen-tool publish"


@pytest.mark.parametrize("binding", ["kaggle/task deadline=2026-02-30", "kaggle/task deadline=soon",
                                     "kaggle/task deadline=2026-10-24", "off deadline=2026-12-01"])
def test_invalid_deadline_fails_before_setup_writes(tmp_path, binding):
    target = tmp_path / "invalid"
    target.mkdir()
    assert init.main([str(target), "--preset", "competition-solo", "--competition", binding,
                      "--environment", "linux/bash"]) == 2
    assert not list(target.iterdir())
