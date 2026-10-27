"""Repair keeps stored layouts; profile defaults do not erase explicit external policy."""

import re

import pytest

from conftest import check, make_project, rs, run_init, severities
import ro_hooks
from ro_state import Project


def file_bytes(target):
    return {str(path.relative_to(target)): path.read_bytes() for path in target.rglob("*") if path.is_file()}


def stored_values(target):
    return rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values


@pytest.mark.parametrize("flags", [("--workflow", "unified"), ("--preset", "quick", "--platforms", "Codex"),
                                  ("--verification", "independent-review"), ("--name", "renamed")])
def test_repair_refuses_conflicting_overrides_without_writes(tmp_path, flags):
    target = make_project(tmp_path, "repair")
    (target / "plan.md").unlink()
    before = file_bytes(target)
    result = run_init(target, *flags)
    assert result.returncode == 2 and "--reconfigure" in result.stderr and "--migrate" in result.stderr
    assert file_bytes(target) == before


@pytest.mark.parametrize("workflow", ["classic", "unified"])
@pytest.mark.parametrize("missing", ["plan.md", "handoff.md", "discoveries.md"])
def test_repair_matches_stored_settings_and_preserves_existing_bytes(tmp_path, workflow, missing):
    target = make_project(tmp_path, "repair", "--workflow", workflow, "--name", "stored title")
    (target / missing).unlink()
    before = file_bytes(target)
    flags = ["--agents", "A"] if workflow == "unified" and missing == "handoff.md" else []
    result = run_init(target, "--workflow", workflow, *flags)
    assert result.returncode == 0, result.stderr
    assert all((target / name).read_bytes() == content for name, content in before.items())
    assert "stored title" in (target / missing).read_text(encoding="utf-8")
    checker = check(target)
    assert severities(checker)["ERROR"] == severities(checker)["WARN"] == 0
    if missing == "plan.md":
        assert ("## Queue\n" in (target / missing).read_text(encoding="utf-8")) == (workflow == "unified")


@pytest.mark.parametrize("missing", ["plan.md", "handoff.md"])
def test_repair_recovers_nondefault_classic_roster_from_surviving_records(tmp_path, missing):
    target = make_project(tmp_path, "multi-slot", "--agents", "B,AA", "--user", "lee")
    (target / missing).unlink()
    before = file_bytes(target)
    result = run_init(target)
    assert result.returncode == 0, result.stderr
    assert all((target / name).read_bytes() == content for name, content in before.items())
    checker = check(target)
    assert severities(checker)["ERROR"] == severities(checker)["WARN"] == 0
    text = (target / missing).read_text(encoding="utf-8")
    assert "Agent: B\n" in text and "Agent: AA\n" in text and "Agent: A\n" not in text


@pytest.mark.parametrize("flags", [("--agents", "A"), ("--user", "newuser")])
def test_repair_refuses_roster_or_user_overrides_without_writes(tmp_path, flags):
    target = make_project(tmp_path, "identities", "--agents", "B,AA", "--user", "lee")
    (target / "plan.md").unlink()
    before = file_bytes(target)
    result = run_init(target, *flags)
    assert result.returncode == 2 and "repair preserves" in result.stderr
    assert file_bytes(target) == before


def test_repair_preserves_a_surviving_user_list_and_ignores_fenced_roster_samples(tmp_path):
    target = make_project(tmp_path, "users", "--agents", "B,AA", "--user", "lee")
    handoff = target / "handoff.md"
    handoff.write_text(handoff.read_text(encoding="utf-8").replace("- Users: lee", "- Users: lee, kim") +
                       "\n```markdown\n### Agent: Z\n- Users: example\n```\n", encoding="utf-8")
    (target / "plan.md").unlink()
    before = file_bytes(target)
    result = run_init(target, "--user", "kim", "--agents", "B,AA")
    assert result.returncode == 0, result.stderr
    assert all((target / name).read_bytes() == content for name, content in before.items())
    assert "user lee, kim" in result.stdout
    assert "Agent: Z\n" not in (target / "plan.md").read_text(encoding="utf-8")


def test_repair_requires_an_explicit_roster_if_unified_handoff_is_missing(tmp_path):
    target = make_project(tmp_path, "unified-roster", "--workflow", "unified", "--agents", "B,AA")
    (target / "handoff.md").unlink()
    before = file_bytes(target)
    refused = run_init(target)
    assert refused.returncode == 2 and "complete agent roster" in refused.stderr
    assert file_bytes(target) == before
    repaired = run_init(target, "--agents", "B,AA", "--user", "lee")
    assert repaired.returncode == 0, repaired.stderr
    assert "- Active agent(s): B, AA" in (target / "handoff.md").read_text(encoding="utf-8")
    assert "- Users: lee" in (target / "handoff.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("workflow", ["classic", "unified"])
def test_repair_refuses_missing_settings_file_without_overwriting_existing_layout(tmp_path, workflow):
    target = make_project(tmp_path, "missing-settings", "--workflow", workflow)
    (target / "agents.md").unlink()
    before = file_bytes(target)
    result = run_init(target, "--preset", "quick", "--platforms", "Codex")
    assert result.returncode == 2 and "restore it from a backup" in result.stderr
    assert file_bytes(target) == before


def transition(target, *flags):
    return run_init(target, "--reconfigure", "--preset", "competition-team", "--competition", "kaggle/challenge",
                    "--phase-clock", "off", *flags)


def test_competition_transition_replaces_inherited_none_with_adapter_patterns(tmp_path):
    target = make_project(tmp_path, "inherited", "--preset", "team-research")
    assert stored_values(target)["external_actions"] == "none"
    result = transition(target)
    assert result.returncode == 0, result.stderr
    values = stored_values(target)
    assert values["external_actions"] == rs.default_value("external_actions", values)
    assert values["_external_actions_source"] == "default"
    assert "external.gate" in values["block"] and values["enforcement"] == "block"
    assert "external gate inactive" not in result.stdout


@pytest.mark.parametrize("patterns", ["none", "release-client publish; delivery-tool send"])
def test_competition_transition_preserves_explicit_external_choices(tmp_path, patterns):
    target = make_project(tmp_path, "explicit", "--preset", "team-research", "--external-actions", patterns)
    result = transition(target)
    assert result.returncode == 0, result.stderr
    values = stored_values(target)
    assert values["external_actions"] == patterns and values["_external_actions_source"] == "explicit"
    assert ("external gate inactive: no command patterns" in result.stdout) == (patterns == "none")
    again = run_init(target, "--reconfigure")
    assert again.returncode == 0 and stored_values(target)["external_actions"] == patterns


@pytest.mark.parametrize("choice", ["inherited", "custom", "opted-out", "legacy"])
def test_transition_gate_enforces_the_resulting_command_policy(tmp_path, choice):
    flags = {"custom": ["--external-actions", "release-client publish; delivery-tool send"],
             "opted-out": ["--external-actions", "none"]}.get(choice, [])
    target = make_project(tmp_path, choice, "--preset", "team-research", *flags)
    if choice == "legacy":
        agents = target / "agents.md"
        agents.write_text(re.sub(r" external_actions_source=\w+", "", agents.read_text(encoding="utf-8")),
                          encoding="utf-8")
    result = transition(target)
    assert result.returncode == 0, result.stderr
    adapter_command = rs.default_value("external_actions", {"profile": "competition", "competition": "kaggle/challenge"}).split("; ")[0]
    command = adapter_command if choice == "inherited" else "release-client publish"
    response = ro_hooks.hook(Project(target, slot="A", session="transition-test"), "PreToolUse",
                             {"tool_name": "Bash", "cwd": str(target),
                              "tool_input": {"command": command + " artifact.txt"}}, check="external.gate")
    output = response.get("hookSpecificOutput", {})
    assert (output.get("permissionDecision") == "deny") == (choice in ("inherited", "custom"))
    if choice in ("inherited", "custom"):
        assert "external.gate" in output["permissionDecisionReason"]


def test_competition_transition_preserves_hand_edited_patterns(tmp_path):
    target = make_project(tmp_path, "hand-edit", "--preset", "team-research")
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace("- External actions: none",
                      "- External actions: release-client publish"), encoding="utf-8")
    result = transition(target)
    assert result.returncode == 0, result.stderr
    assert stored_values(target)["external_actions"] == "release-client publish"
    assert stored_values(target)["_external_actions_source"] == "explicit"


def test_competition_transition_retains_legacy_none_and_reports_inactive_gate(tmp_path):
    target = make_project(tmp_path, "legacy", "--preset", "team-research")
    agents = target / "agents.md"
    (target / ".ro" / "template-render.json").unlink()  # Legacy provenance was never recorded.
    result = transition(target)
    assert result.returncode == 0, result.stderr
    assert stored_values(target)["external_actions"] == "none"
    assert "external gate inactive: no command patterns" in result.stdout and "--external-actions" in result.stdout


def test_transition_flag_can_opt_out_of_an_inherited_default(tmp_path):
    target = make_project(tmp_path, "opt-out", "--preset", "team-research")
    result = transition(target, "--external-actions", "none")
    assert result.returncode == 0, result.stderr
    assert stored_values(target)["external_actions"] == "none"
    assert stored_values(target)["_external_actions_source"] == "explicit"
    assert "external gate inactive" in result.stdout


def test_external_patterns_do_not_claim_blocking_when_enforcement_is_off(tmp_path):
    target = make_project(tmp_path, "disabled", "--preset", "team-research")
    result = transition(target, "--enforcement", "off")
    assert result.returncode == 0, result.stderr
    assert "external gate does not block: Enforcement is off" in result.stdout
