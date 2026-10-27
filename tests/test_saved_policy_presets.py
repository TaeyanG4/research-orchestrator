"""Saved presets retain effective reusable policies without carrying project identity."""

import datetime as dt
import json

import pytest

from conftest import make_project, rs, run_init
import ro_hooks
from ro_state import Project


POLICY = {
    "autonomy": "away",
    "language": "ko",
    "environment": "linux/bash",
    "guard_set": "G5,E1",
    "guard_thresholds": "saturation=3, direction-review=2d, insight-due=12h, effort=60%, milestones=15/40/80",
    "read_bound": "on",
    "external_actions": "deploytool publish; release-client send",
    "publish_scan": "secrets; literal:INTERNAL-ONLY",
    "brief_requirements": "work: Acceptance",
    "git": "commit",
    "enforcement": "block",
    "block": "external.gate, publish.scan",
}


def stored(target):
    return rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values


def save_policy(tmp_path):
    (tmp_path / ".git").mkdir(exist_ok=True)  # Git preferences apply only inside an existing repository.
    flags = [part for key, value in POLICY.items() for part in (rs.SETTING[key].flag, value)]
    source = make_project(tmp_path, "source-identity", "--preset", "team-research", *flags,
                          "--guards", "strict since 2001-01-01", "--competition", "hub/source-identity",
                          "--phase-clock", "2001-01-01,2001-02-01", "--queue-freeze", "until 2099-12-31")
    before = {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}
    result = run_init(source, "--save-preset", "portable-policy")
    assert result.returncode == 0, result.stderr
    assert {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()} == before
    return source, rs.load_preset("user:portable-policy")


def test_saved_policy_round_trip_keeps_preferences_and_effective_gate(tmp_path):
    source, data = save_policy(tmp_path)
    assert {key: data.get(key) for key in POLICY} == POLICY
    target = make_project(tmp_path, "new-project", "--preset", "user:portable-policy")
    values = stored(target)
    assert {key: values[key] for key in POLICY} == POLICY
    assert values["_external_actions_source"] == "explicit"
    assert stored(source)["guards"] == "strict since 2001-01-01"
    assert values["guards"] == f"strict since {dt.date.today().isoformat()}"
    for command, denied in [("deploytool publish artifact.txt", True), ("deploytool inspect artifact.txt", False)]:
        result = ro_hooks.hook(Project(target, slot="A", session="saved-policy"), "PreToolUse",
                               {"tool_name": "Bash", "cwd": str(target), "tool_input": {"command": command}},
                               check="external.gate")
        output = result.get("hookSpecificOutput", {})
        assert (output.get("permissionDecision") == "deny") == denied
        if denied:
            assert "external.gate" in output["permissionDecisionReason"]


def test_saved_policy_excludes_project_identity_and_dates(tmp_path):
    _, data = save_policy(tmp_path)
    assert not {"preset", "competition", "phase_clock", "queue_freeze"} & data.keys()
    assert data["guards"] == "strict"
    serialized = json.dumps(data)
    assert all(value not in serialized for value in ("source-identity", "2001-01-01", "2001-02-01", "2099-12-31"))
    target = make_project(tmp_path, "new-identity", "--preset", "user:portable-policy")
    values = stored(target)
    assert all(values[key] == "off" for key in ("competition", "phase_clock", "queue_freeze"))


def test_saved_policy_precedence_and_explicit_none_survive_profile_changes(tmp_path):
    save_policy(tmp_path)
    target = make_project(tmp_path, "recipient", "--preset", "team-research", "--language", "ja")
    result = run_init(target, "--reconfigure", "--preset", "user:portable-policy", "--language", "zh-CN")
    assert result.returncode == 0, result.stderr
    values = stored(target)
    assert values["language"] == "zh-CN"
    assert {key: values[key] for key in POLICY if key != "language"} == {key: value for key, value in POLICY.items()
                                                                            if key != "language"}
    result = run_init(target, "--reconfigure", "--external-actions", "none", "--save-preset", "opt-out")
    assert result.returncode == 0, result.stderr
    target2 = make_project(tmp_path, "recipient-two", "--preset", "user:opt-out")
    result = run_init(target2, "--reconfigure", "--profile", "competition", "--competition", "hub/new",
                      "--phase-clock", "off")
    assert result.returncode == 0, result.stderr
    assert stored(target2)["external_actions"] == "none"
    assert stored(target2)["_external_actions_source"] == "explicit"
    assert "external gate inactive" in result.stdout


def test_saved_policy_language_is_used_by_questions_and_list(tmp_path):
    _, data = save_policy(tmp_path)
    missing, defaults = rs.question_answers(data, {}, {})
    assert not missing
    assert defaults["language"] == "ko" and defaults["environment"] == "linux/bash" and defaults["git"] == "commit"
    result = run_init(tmp_path, "--list-presets")
    row = next(line for line in result.stdout.splitlines() if line.startswith("user:portable-policy "))
    assert row.split()[4] == "ko"


@pytest.mark.parametrize("key,value", [("autonomy", "away"), ("language", "es-419"), ("environment", "macos/bash"),
                                      ("guard_set", "G5,E1"), ("guard_thresholds", "saturation=2"),
                                      ("read_bound", "on"), ("external_actions", "deploytool publish"),
                                      ("publish_scan", "literal:PRIVATE"), ("brief_requirements", "work: Acceptance"),
                                      ("git", "commit")])
def test_preset_accepts_valid_optional_policy_fields(key, value):
    data = dict(rs.load_preset("team-research"), **{key: value})
    assert rs.validate_preset(data, "saved policy")[key] == value
    assert rs.resolve({}, data, {})[key] == value


@pytest.mark.parametrize("key,value", [("autonomy", "asleep"), ("language", "bad_language"),
                                      ("guard_set", "G999"), ("guard_thresholds", "saturation=0"),
                                      ("read_bound", "maybe"), ("external_actions", None),
                                      ("publish_scan", "unknown"), ("brief_requirements", "missing separator"),
                                      ("git", "sync"), ("environment", "unknown/bash")])
def test_preset_rejects_invalid_optional_policy_fields(key, value):
    data = dict(rs.load_preset("team-research"), **{key: value})
    with pytest.raises(ValueError):
        rs.validate_preset(data, "saved policy")


@pytest.mark.parametrize("key,value", [("competition", "hub/old"), ("phase_clock", "2001-01-01,2001-02-01"),
                                      ("queue_freeze", "until 2099-12-31"), ("preset", "quick"),
                                      ("guards", "strict since 2001-01-01")])
def test_presets_reject_project_binding_or_activation_dates(key, value):
    data = dict(rs.load_preset("team-research"), **{key: value})
    with pytest.raises(ValueError):
        rs.validate_preset(data, "project-bound preset")


def test_legacy_preset_without_optional_policy_fields_still_loads(tmp_path, isolated_home):
    data = rs.load_preset("team-research")
    destination = isolated_home / "presets" / "legacy.json"
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(data), encoding="utf-8")
    target = make_project(tmp_path, "legacy", "--preset", "user:legacy")
    values = stored(target)
    assert values["autonomy"] == "present" and values["language"] == "en"
