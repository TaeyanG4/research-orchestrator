"""Native sessions retain distinct slots across commands and installed hook children."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from conftest import SCRIPTS, item, set_queue, set_slot, unified_project
from ro_state import Project


def command(root, *args, env=None):
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"RO_SLOT", "RO_SESSION", "CODEX_THREAD_ID"}}
    return subprocess.run([sys.executable, str(SCRIPTS / "ro.py"), "--project", str(root), *args],
                          env={**environment, **(env or {})}, text=True, encoding="utf-8",
                          capture_output=True, timeout=20)


def native_hook(root, event, session=None, *, env=None, user=None):
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"RO_SLOT", "RO_SESSION", "CODEX_THREAD_ID"}}
    payload = {"cwd": str(root)}
    if session is not None:
        payload["session_id"] = session
    if user is not None:
        payload["user"] = user
    result = subprocess.run([sys.executable, str(SCRIPTS / "ro_hook_runner.py"), event],
                            cwd=root, env={**environment, **(env or {})}, text=True, encoding="utf-8",
                            input=json.dumps(payload),
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_native_session_slot_mapping_controls_brief_launch_and_stop(tmp_path):
    root = unified_project(tmp_path)
    set_slot(root, "B", "Codex")
    set_queue(root, item("H-A-01") + item("H-B-01"))
    policy = root / "agents.md"
    lines = policy.read_text(encoding="utf-8").splitlines()
    for key, value in (("Enforcement", "block"), ("Block", "jobs.unmonitored")):
        lines = [f"- {key}: {value}" if line.startswith(f"- {key}:") else line for line in lines]
    policy.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for slot in ("A", "B"):
        selected = command(root, "--session", "native-" + slot, "--slot", slot, "brief")
        assert selected.returncode == 0, selected.stderr
        claimed = command(root, "--session", "native-" + slot, "claim", "H-" + slot + "-01")
        assert claimed.returncode == 0, claimed.stderr
        context = native_hook(root, "SessionStart", "native-" + slot, env={"RO_SLOT": "A"})
        brief = context["hookSpecificOutput"]["additionalContext"]
        assert f"Slot {slot}: taken; claims 1" in brief
        assert f"Claim H-{slot}-01:" in brief
        assert f"Claim H-{'B' if slot == 'A' else 'A'}-01:" not in brief
    job_id = ""
    try:
        launched = command(root, "--session", "native-B", "launch", "--item", "H-B-01", "--expect", "30s",
                           "--confirm", "0s", "--", sys.executable, "-c", "import time; time.sleep(30)",
                           env={"RO_SLOT": "A"})
        assert launched.returncode == 0, launched.stderr
        job = Project(root, slot="B").read_json("jobs.json")[-1]
        job_id = job["id"]
        assert job["slot"] == "B" and job["session"] == "native-B" and job_id.startswith("J-B-")
        assert native_hook(root, "Stop", "native-A", env={"RO_SLOT": "B"}) == {}
        stopped = native_hook(root, "Stop", "native-B", env={"RO_SLOT": "A"})
        assert stopped.get("decision") == "block" and job_id in stopped["reason"]
        assert command(root, "--session", "native-B", "kill", job_id).returncode == 0
        assert command(root, "--session", "native-B", "monitor", job_id).returncode == 0
        assert native_hook(root, "Stop", "native-B") == {}
    finally:
        if job_id:
            command(root, "--session", "native-B", "kill", job_id)


def test_unknown_native_session_has_no_a_startup_context(tmp_path):
    root = unified_project(tmp_path)
    set_slot(root, "A", "released", user="none")  # Two free slots are ambiguous.
    context = native_hook(root, "SessionStart", "new-native-session")
    brief = context["hookSpecificOutput"]["additionalContext"]
    assert "Host session: new-native-session" in brief
    assert "--session new-native-session --slot <slot> brief" in brief
    assert "Slot not selected" in brief and "Slot A:" not in brief


def test_startup_registers_unique_free_slot_without_changing_handoff(tmp_path):
    root = unified_project(tmp_path)
    before = (root / "handoff.md").read_bytes()
    result = native_hook(root, "SessionStart", "new-native-session")
    assert "Slot B:" in result["hookSpecificOutput"]["additionalContext"]
    assert Project(root, session="new-native-session").slot == "B"
    assert command(root, "--session", "new-native-session", "next-id", "H").stdout.strip() == "H-B-01"
    assert (root / "handoff.md").read_bytes() == before


@pytest.mark.parametrize("identity_source", ["payload", "environment"])
def test_startup_registers_unique_current_user_slot(tmp_path, identity_source):
    root = unified_project(tmp_path)
    set_slot(root, "B", "Codex", user="collaborator")
    kwargs = {"user": "collaborator"} if identity_source == "payload" else {"env": {"RO_USER": "collaborator"}}
    result = native_hook(root, "SessionStart", "resuming-native", **kwargs)
    assert "Slot B:" in result["hookSpecificOutput"]["additionalContext"]
    assert Project(root, session="resuming-native").slot == "B"


@pytest.mark.parametrize("identity", [None, "operator"])
def test_startup_never_guesses_ambiguous_or_other_user_taken_slot(tmp_path, identity):
    root = unified_project(tmp_path)
    set_slot(root, "B", "Codex", user="operator")
    result = native_hook(root, "SessionStart", "new-native", user=identity)
    assert "Slot not selected" in result["hookSpecificOutput"]["additionalContext"]
    assert not Project(root, session="new-native", require_slot=False).slot_registered


def test_startup_without_native_identity_does_not_automatically_register(tmp_path):
    root = unified_project(tmp_path)
    native_hook(root, "SessionStart", user="operator")
    assert not list((root / ".ro/sessions").glob("*.json"))


def test_slot_selection_is_project_local_and_native_environment_resolves_commands(tmp_path):
    root = unified_project(tmp_path)
    other = unified_project(tmp_path, "other")
    assert command(root, "--session", "native-B", "--slot", "B", "brief").returncode == 0
    assert command(root, "next-id", "H", env={"CODEX_THREAD_ID": "native-B"}).stdout.strip() == "H-B-01"
    assert command(root, "next-id", "H", env={"RO_SESSION": "native-B", "RO_SLOT": "A"}).stdout.strip() == "H-B-02"
    assert command(other, "--session", "native-B", "next-id", "H").returncode == 1
    assert command(root, "--session", "native-A", "next-id", "H").returncode == 1
    assert command(other, "--session", "native-B", "--slot", "A", "next-id", "H").stdout.strip() == "H-A-01"
    assert command(root, "--session", "native-A", "--slot", "A", "next-id", "H").stdout.strip() == "H-A-01"
    assert command(root, "--session", "native-B", "--slot", "AA", "brief").returncode == 0
    assert command(root, "--session", "native-B", "next-id", "H").stdout.strip() == "H-AA-01"


def test_default_session_command_registers_slot_for_later_native_hooks(tmp_path):
    root = unified_project(tmp_path, agents="1")
    assert command(root, "--session", "default-native", "next-id", "H").stdout.strip() == "H-A-01"
    assert Project(root, session="default-native").slot_registered
    context = native_hook(root, "SessionStart", "default-native")["hookSpecificOutput"]["additionalContext"]
    assert "Slot A:" in context and "Slot not selected" not in context


@pytest.mark.parametrize("identity_variable", ["RO_SESSION", "CODEX_THREAD_ID"])
def test_hook_environment_identity_resolves_saved_slot_before_stale_environment(tmp_path, identity_variable):
    root = unified_project(tmp_path)
    assert command(root, "--session", "native-B", "--slot", "B", "brief").returncode == 0
    context = native_hook(root, "SessionStart", env={identity_variable: "native-B", "RO_SLOT": "A"})
    brief = context["hookSpecificOutput"]["additionalContext"]
    assert "Slot B:" in brief and "Slot A:" not in brief
    assert Project(root, session="native-B").slot == "B"


@pytest.mark.parametrize("slot", ["A", "B"])
def test_hook_without_host_identity_preserves_legacy_slot_context(tmp_path, slot):
    root = unified_project(tmp_path)
    context = native_hook(root, "SessionStart", env={"RO_SLOT": slot})
    brief = context["hookSpecificOutput"]["additionalContext"]
    assert f"Slot {slot}:" in brief
    assert "Host session: local:" not in brief and "Slot not selected" not in brief
    assert not list((root / ".ro" / "sessions").glob("*.json"))


def test_corrupt_session_association_is_visible_fail_open_for_hooks(tmp_path):
    root = unified_project(tmp_path)
    project = Project(root, slot="B", session="corrupt-native")
    project.register_slot()
    project._state_path(project.session_file).write_text("{", encoding="utf-8")
    result = native_hook(root, "Stop", "corrupt-native")
    assert result.get("decision") != "block" and "hooks inactive" in str(result)
    assert command(root, "--session", "corrupt-native", "next-id", "H").returncode == 1
    assert command(root, "--session", "corrupt-native", "--slot", "B", "brief").returncode == 0
    assert Project(root, session="corrupt-native").slot == "B"
