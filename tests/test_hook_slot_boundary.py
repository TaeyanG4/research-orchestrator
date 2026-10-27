"""Unselected host events protect bindings without taking an implicit owner slot."""
import builtins
import io
import json
from pathlib import Path
import pytest

import ro
from ro_command import command_prefix
from ro_state import Project
from conftest import set_slot, unified_project


@pytest.mark.parametrize('event', ['PreToolUse', 'PostToolUse'])
def test_pretool_unregistered_multislot_keeps_safety_without_history_reads(tmp_path, monkeypatch, capsys, event):
    root = unified_project(tmp_path)
    history = {root / "handoff.md", root / "discoveries.md"}
    def guarded(original):
        def opened(path, *args, **kwargs):
            if isinstance(path, (str, Path)):
                assert Path(path).resolve() not in history
            return original(path, *args, **kwargs)
        return opened
    monkeypatch.setattr(builtins, "open", guarded(builtins.open))
    monkeypatch.setattr(io, "open", guarded(io.open))
    args = ro.hook_arguments(["--project", str(root), "hook", event])
    payload = {"cwd": str(root), "session_id": "fresh-host-session", "tool_name": "Bash",
               "tool_input": {"command": "work &"}}
    assert ro.hook_main(args, json.dumps(payload).encode()) == 0
    response = json.loads(capsys.readouterr().out)
    if event == 'PreToolUse':
        assert response["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not list((root / ".ro" / "sessions").glob("*.json"))


def test_unselected_startup_prints_resolved_prefix_without_slot_history(tmp_path, capsys):
    root = unified_project(tmp_path)
    set_slot(root, "A", "released", user="none")  # Two candidates keep selection manual.
    args = ro.hook_arguments(["--project", str(root), "hook", "SessionStart"])
    assert ro.hook_main(args, json.dumps({"cwd": str(root), "session_id": "fresh-host-session"}).encode()) == 0
    response = json.loads(capsys.readouterr().out)
    text = str(response)
    assert "Slot not selected" in text and "ro command prefix:" in text
    # The project declares its shell; the test host's OS does not select quoting.
    environment = Project(root, require_slot=False).settings()["environment"]
    shell = "powershell" if environment.endswith("/powershell") else "sh"
    assert command_prefix(shell=shell) in response["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize('event', ['SessionStart', 'Stop'])
@pytest.mark.parametrize('multiple', [False, True])
def test_identity_free_owner_events_require_selection_only_for_multiple_slots(tmp_path, monkeypatch, capsys, event, multiple):
    for key in ('RO_SLOT', 'RO_SESSION', 'CODEX_THREAD_ID'):
        monkeypatch.delenv(key, raising=False)
    root = unified_project(tmp_path)
    handoff = root / 'handoff.md'
    handoff.write_text('# Handoff\n\n### Agent: A\n- Current host: local\n- Current user: operator\n' +
                       ('\n### Agent: B\n- Current host: local\n- Current user: operator\n' if multiple else ''), encoding='utf-8')
    args = ro.hook_arguments(['--project', str(root), 'hook', event])
    assert ro.hook_main(args, json.dumps({'cwd': str(root)}).encode()) == 0
    response = json.loads(capsys.readouterr().out)
    text = json.dumps(response).lower()
    if multiple:
        assert 'select' in text and '--slot' in text and 'ro_slot' in text
        assert 'Slot A:' not in str(response)
    else:
        assert 'select' not in text
