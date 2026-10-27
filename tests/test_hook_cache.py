"""Installed hooks never write compiled files beside scripts or in project trees."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

from conftest import SCRIPTS
from ro_proc import no_window_flags


@pytest.mark.parametrize("entry", ["supervised", "direct", "launcher"])
def test_hook_uses_user_cache_outside_installed_scripts(tmp_path, entry):
    installed = tmp_path / "installed" / "scripts"
    shutil.copytree(SCRIPTS, installed, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SCRIPTS.parent / "templates", installed.parent / "templates")
    project = tmp_path / "project"
    project.mkdir()
    (project / "agents.md").write_text("# Rules\n\n## Project settings\n- Enforcement: block\n- Block: shell.background\n"
                                      "- Environment: windows/bash\n", encoding="utf-8")
    cache = tmp_path / "user-cache"
    env = {**os.environ, "LOCALAPPDATA": str(cache), "XDG_CACHE_HOME": str(cache), "HOME": str(tmp_path)}
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    payload = {"cwd": str(project), "tool_name": "Bash", "tool_input": {"command": "echo ready &"}}
    command = ([sys.executable, "-S", str(installed / "ro_hook_runner.py"), "PreToolUse"] if entry == "supervised"
               else [sys.executable, str(installed / ("ro" if entry == "launcher" else "ro.py")), "hook", "PreToolUse"])
    proc = subprocess.run(command,
                          input=json.dumps(payload), text=True, capture_output=True, cwd=project, env=env,
                          creationflags=no_window_flags())
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not list(installed.rglob("__pycache__"))
    assert not list(project.rglob("__pycache__"))
    cache_root = tmp_path if sys.platform == "darwin" else cache
    assert list(cache_root.rglob("ro_hooks*.pyc"))


def test_cache_failure_disables_bytecode_writes(monkeypatch):
    import ro_hook_runner as runner
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.setattr(sys, "pycache_prefix", None)
    def fail(*args, **kwargs):
        raise OSError("unwritable user cache")
    monkeypatch.setattr(runner.os, "makedirs", fail)
    assert runner.cache_options() == ["-B"]
    assert sys.dont_write_bytecode


@pytest.mark.parametrize("changed", [None, "plan.md", ".ro/checker-baseline.json"])
def test_compact_reuses_stamped_checker_summary_beyond_normal_ttl(tmp_path, monkeypatch, changed):
    from types import SimpleNamespace
    import ro_records as records
    from ro_state import Project
    project = Project(tmp_path, slot="A")
    (tmp_path / "agents.md").write_text("# Rules\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(records, "_checker", lambda p: (calls.append(p) or SimpleNamespace(issues=[]), 0))
    now = [1000.0]
    monkeypatch.setattr(records.time, "time", lambda: now[0])
    expected = records._checker_brief(project)
    now[0] += 120
    if changed:
        path = tmp_path / changed
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    assert records._checker_brief(project, compact=True) == expected
    assert len(calls) == (2 if changed else 1)


def test_regular_brief_and_new_day_refresh_the_checker_summary(tmp_path, monkeypatch):
    import datetime as dt
    from types import SimpleNamespace
    import ro_records as records
    from ro_state import Project
    project = Project(tmp_path, slot="A")
    calls, now, day = [], [1000.0], [dt.date(2026, 1, 12)]
    class ClockDate(dt.date):
        @classmethod
        def today(cls):
            return day[0]
    monkeypatch.setattr(records.dt, "date", ClockDate)
    monkeypatch.setattr(records.time, "time", lambda: now[0])
    monkeypatch.setattr(records, "_checker", lambda p: (calls.append(p) or SimpleNamespace(issues=[]), 0))
    records._checker_brief(project)
    now[0] += 120
    records._checker_brief(project)
    assert len(calls) == 2
    day[0] += dt.timedelta(days=1)
    records._checker_brief(project, compact=True)
    assert len(calls) == 3


def test_compact_session_start_requests_stamped_summary(tmp_path, monkeypatch):
    from conftest import unified_project
    import ro_hooks
    import ro_records
    from ro_state import Project
    project = Project(unified_project(tmp_path), slot="A", session="compact-session")
    project.register_slot()
    calls = []
    monkeypatch.setattr(ro_records, "brief", lambda p, *, compact=False: calls.append(compact) or "context")
    for source in ("compact", "startup", "resume", "clear"):
        ro_hooks.hook(project, "SessionStart", {"source": source})
    assert calls == [True, False, False, False]
