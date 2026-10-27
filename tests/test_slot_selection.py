"""Ambiguous projects need an explicit or durably registered slot."""

import pytest

from ro_state import Project


@pytest.fixture
def slots(tmp_path, monkeypatch):
    monkeypatch.delenv("RO_SLOT", raising=False)
    monkeypatch.delenv("RO_SESSION", raising=False)
    (tmp_path / "handoff.md").write_text(
        "# Handoff\n\n### Agent: A\n- Current host: unassigned\n\n"
        "### Agent: B\n- Current host: unassigned\n", encoding="utf-8")
    return tmp_path


def test_multislot_project_refuses_implicit_selection_before_writing_state(slots):
    with pytest.raises(ValueError, match="select a slot"):
        Project(slots)
    with pytest.raises(ValueError, match="select a slot"):
        Project(slots, session="new-session")
    assert not (slots / ".ro").exists()


def test_explicit_and_environment_selection_work_for_multiple_slots(slots, monkeypatch):
    assert Project(slots, slot="B").slot == "B"
    monkeypatch.setenv("RO_SLOT", "B")
    assert Project(slots).slot == "B"
    assert Project(slots, slot="A").slot == "A"


def test_registered_selection_precedes_environment_for_multiple_slots(slots, monkeypatch):
    selected = Project(slots, slot="B", session="selected-session")
    selected.register_slot()
    monkeypatch.setenv("RO_SLOT", "A")
    restored = Project(slots, session="selected-session")
    assert restored.slot == "B" and restored.slot_registered


def test_single_slot_default_ignores_fenced_example_slots(slots):
    (slots / "handoff.md").write_text(
        "### Agent: A\n- Current host: unassigned\n\n```markdown\n### Agent: B\n```\n", encoding="utf-8")
    assert Project(slots).slot == "A"
