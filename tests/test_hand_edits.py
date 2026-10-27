"""Hand-edit detection covers the whole generated part of agents.md (review fix 2)."""

from __future__ import annotations

import pytest

from conftest import check, copy_fixture, found, make_project, rs, run_init


def insert(target, anchor: str, text: str) -> str:
    agents = target / "agents.md"
    original = agents.read_text(encoding="utf-8")
    assert anchor in original
    edited = original.replace(anchor, anchor + text, 1)
    agents.write_text(edited, encoding="utf-8", newline="\n")
    return edited


@pytest.mark.parametrize("anchor, text", [
    ("— Agent Rules\n", "\nOur team note above the settings.\n"),               # before '## Project settings'
    ("- Cross-check fallback: same-host\n", "\nA sentence inside the settings section.\n"),
    ("- Reviewer: off\n", "- Owner: operator\n"),                                     # an unknown settings line
    ("## Rules for this project\n", "\nExtra rule in the reading list.\n"),
])
def test_prose_anywhere_above_project_rules_needs_force(tmp_path, anchor: str, text: str) -> None:
    target = make_project(tmp_path, "proj", "--preset", "solo-research", "--platforms", "Claude Code")
    edited = insert(target, anchor, text)
    refused = run_init(target, "--reconfigure")
    assert refused.returncode == 1 and "edited by hand" in refused.stderr
    assert (target / "agents.md").read_text(encoding="utf-8") == edited
    assert "agents.rules.edited" in [i.check for i in found(check(target), "WARN")]
    forced = run_init(target, "--reconfigure", "--force")
    assert forced.returncode == 0 and text.strip() not in (target / "agents.md").read_text(encoding="utf-8")


def test_prose_before_the_settings_needs_force(tmp_path) -> None:
    target = copy_fixture("classic", tmp_path / "classic")
    insert(target, "— Agent Rules\n", "\nOur team note.\n")
    refused = run_init(target, "--reconfigure")
    assert refused.returncode == 1 and "edited by hand" in refused.stderr


def test_editing_setting_values_is_not_a_hand_edit(tmp_path) -> None:
    target = make_project(tmp_path, "proj", "--preset", "solo-research", "--platforms", "Claude Code")
    agents = target / "agents.md"
    text = agents.read_text(encoding="utf-8")
    text = text.replace("- Reviewer: off", "- Reviewer: on — Claude Code / opus").replace(
        "- Item size: staged", "- Item size: short").replace("- Preset: solo-research", "- Preset: custom")
    agents.write_text(text, encoding="utf-8", newline="\n")
    warnings = sorted(i.check for i in found(check(target), "WARN"))
    assert warnings == ["agents.rules.stale", "agents.summary.stale"]
    applied = run_init(target, "--reconfigure")
    assert applied.returncode == 0, applied.stderr
    text = agents.read_text(encoding="utf-8")
    assert "- Item size: short\n" in text and "staged-items.md" not in text
    assert not found(check(target), "WARN")


def test_text_in_project_rules_is_never_a_hand_edit(tmp_path) -> None:
    target = make_project(tmp_path, "proj", "--preset", "team-research")
    agents = target / "agents.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n- Deploy only on Fridays.\n", encoding="utf-8",
                      newline="\n")
    region = rs.split_agents(agents.read_text(encoding="utf-8"))[1]
    assert not found(check(target), "WARN")
    assert run_init(target, "--reconfigure", "--git", "off").returncode == 0
    assert rs.split_agents(agents.read_text(encoding="utf-8"))[1] == region
