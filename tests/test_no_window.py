"""Windows console children start without their own window, so hooks and scans never flash one."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

import ro_evidence as evidence
import ro_hook_runner as runner
import ro_proc
from conftest import ROOT, SCRIPTS
from test_ro_hooks import project_at

SENTINEL = 0x08000000


@pytest.mark.parametrize("name,flags", [("nt", SENTINEL), ("posix", 0)])
def test_no_window_flags_hide_children_on_windows(monkeypatch, name, flags):
    monkeypatch.setattr(ro_proc, "os", SimpleNamespace(name=name))
    assert ro_proc.no_window_flags() == flags
    assert SENTINEL == getattr(subprocess, "CREATE_NO_WINDOW", SENTINEL)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console attachment")
def test_detached_windows_process_reports_no_console_and_hides_children():
    code = "import ro_proc; print(ro_proc.no_window_flags())"
    flags = {name: subprocess.run([sys.executable, "-c", code], cwd=SCRIPTS, capture_output=True, text=True,
                                  creationflags=value).stdout.strip()
             for name, value in (("console", SENTINEL), ("detached", subprocess.DETACHED_PROCESS))}
    assert flags == {"console": str(SENTINEL), "detached": str(SENTINEL)}


def test_hook_runner_child_starts_without_a_window(tmp_path, monkeypatch):
    project = project_at(tmp_path)
    monkeypatch.setattr(ro_proc, "no_window_flags", lambda: SENTINEL)
    seen = []

    def child(command, **kwargs):
        seen.append(kwargs.get("creationflags"))
        return subprocess.CompletedProcess(command, 0, b"{}")
    monkeypatch.setattr(subprocess, "run", child)
    payload = {"cwd": str(project.root), "tool_name": "Bash", "tool_input": {"command": "echo ready"}}
    assert runner.run("PreToolUse", json.dumps(payload).encode(), project) == ({}, 0)
    assert seen == [SENTINEL]


def test_publish_scan_git_calls_start_without_a_window(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "no_window_flags", lambda: SENTINEL)
    seen = []

    def refuse(command, **kwargs):
        seen.append((command[0], kwargs.get("creationflags")))
        raise OSError("git unavailable")
    monkeypatch.setattr(evidence.subprocess, "run", refuse)
    monkeypatch.setattr(evidence.subprocess, "Popen", refuse)
    project = SimpleNamespace(root=tmp_path)
    for call in (lambda: evidence._git(project, "rev-parse"), lambda: evidence._staged_diff(project),
                 lambda: evidence._Batch(project, ["0" * 40])):
        with pytest.raises(ValueError, match="could not run git"):
            call()
    assert seen == [("git", SENTINEL)] * 3


def subprocess_calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("run", "Popen", "call", "check_call", "check_output")
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"):
            yield node


def test_every_shipped_and_tooling_subprocess_passes_creation_flags():
    sources = [ROOT / "install.py", *SCRIPTS.glob("*.py"), *(ROOT / "scripts").rglob("*.py"),
               *(ROOT / "tests" / name for name in ("conftest.py", "startup_bytes.py", "measure_checker.py"))]
    missing = []
    for path in sources:
        for node in subprocess_calls(path):
            keywords = {keyword.arg for keyword in node.keywords}
            if "creationflags" not in keywords and None not in keywords:
                missing.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert missing == []
