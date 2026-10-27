"""Shared helpers for the Research Orchestrator tests (stdlib + pytest, no network)."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import contextlib
import datetime as dt
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "research-orchestrator"
SCRIPTS = SKILL / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import check_project  # noqa: E402
import init_research_orchestrator as init  # noqa: E402
import ro_settings as rs  # noqa: E402
from ro_proc import no_window_flags  # noqa: E402


if os.name == "nt":
    class _NoWindowPopen(subprocess.Popen):
        """Test helpers start console children without flashing windows; explicit flags stay unchanged.

        Shipped scripts pass no_window_flags() themselves (asserted in test_no_window.py)."""

        def __init__(self, *args, **kwargs):
            if not kwargs.get("creationflags"):
                kwargs["creationflags"] = no_window_flags()
            super().__init__(*args, **kwargs)

    subprocess.Popen = _NoWindowPopen

REAL_RUN = subprocess.run


def with_real_ps(fake):
    """Wrap a subprocess.run fake so BSD/macOS process identity stays real.

    Without /proc, ro_state.process_start asks `ps` (through subprocess.run) whenever
    a Project, lock or job check needs this process's identity; a fake meant for the
    command under test must not answer that query."""
    def run(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and command[:1] == ["ps"]:
            return REAL_RUN(command, *args, **kwargs)
        return fake(command, *args, **kwargs)
    return run


NOW = dt.datetime(2026, 10, 25, 12, 0)
PLAN_VALUES = [
    ("Sources", "none"), ("Hypothesis", "a claim"), ("Evidence", "a reason"), ("Improvement", "none"),
    ("Impact", "1"), ("Information", "1"), ("Confidence", "1"), ("Unblock", "1"), ("Diversity", "1"),
    ("Cost", "1"), ("Priority", "9"), ("Resource", "CPU"), ("Parallel", "YES"), ("Other", "NONE"),
    ("Next test", "a test"),
]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """A fresh temporary folder per test from the stdlib, independent of pytest's shared basetemp folder."""
    with tempfile.TemporaryDirectory(prefix="ro-test-") as folder:
        yield Path(folder)


@pytest.fixture(autouse=True)
def isolated_detection_environment(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runner identity, shell and locale out of defaults, including in child CLIs.

    Detection tests opt into their own markers after this fixture runs. Keep the
    real OS so filesystem/process behavior stays native; OS-specific detection
    tests supply sys.platform themselves. Depending on isolated_home preserves
    its setup order: undo filesystem monkeypatches before temp-directory cleanup.
    """
    for key in list(os.environ):
        if (key in {"CLAUDECODE", "CLAUDE_PROJECT_DIR", "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_ROOT", "TERM_PROGRAM", "SHELL", "LANG", "LANGUAGE",
                    "RO_SLOT", "RO_SESSION", "RO_USER"}
                or key.startswith(("CLAUDE_CODE_", "CODEX_", "GEMINI_", "ANTIGRAVITY_", "LC_"))):
            monkeypatch.delenv(key)
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("LANG", "C")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("LANGUAGE", "en")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(isolated_home / "claude-config"))
    # ro_settings captured this fallback during collection, before fixtures ran.
    environment = rs.SETTING["environment"]._replace(default=rs.detect_environment())
    monkeypatch.setattr(rs, "SETTINGS", tuple(environment if setting.key == "environment" else setting
                                            for setting in rs.SETTINGS))
    monkeypatch.setitem(rs.SETTING, "environment", environment)
    monkeypatch.setitem(rs.BY_LABEL, environment.label, environment)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """User presets go to a private folder, never to the real home directory."""
    home = tmp_path / "ro-home"
    monkeypatch.setenv("RESEARCH_ORCHESTRATOR_HOME", str(home))
    # Hook bytecode uses a private per-user cache, never the real home or installed tree.
    monkeypatch.setenv("LOCALAPPDATA", str(home / "cache"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "cache"))
    return home


def run_script(script: str, target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # the scripts print '—' and '→'
    return subprocess.run([sys.executable, str(SCRIPTS / script), str(target), *args], text=True, capture_output=True,
                          encoding="utf-8", errors="replace", env=env, creationflags=no_window_flags())


def run_init(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_script("init_research_orchestrator.py", target, *args)


def run_check_cli(target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_script("check_project.py", target, *args)


def concurrent_results(commands: list[list[str]]) -> list[tuple[int, str, str]]:
    """Release children together after each prints 'ready' and waits on stdin."""
    children = []
    try:
        for command in commands:
            children.append(subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                             env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                             creationflags=no_window_flags()))
        with ThreadPoolExecutor(max_workers=len(children)) as readers:
            ready = [readers.submit(child.stdout.readline) for child in children]
            try:
                assert [line.result(timeout=15).strip() for line in ready] == ["ready"] * len(children)
                assert all(child.poll() is None for child in children)
            finally:
                # Also unblock readers if a child never reaches the barrier.
                if not all(line.done() for line in ready):
                    for child in children:
                        if child.poll() is None:
                            child.kill()
        for child in children:
            child.stdin.write("run\n")
            child.stdin.flush()
        outputs = [child.communicate(timeout=15) for child in children]
        return [(child.returncode, stdout.strip(), stderr) for child, (stdout, stderr) in zip(children, outputs)]
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate()


def make_project(parent: Path, name: str, *args: str) -> Path:
    target = parent / name
    target.mkdir()
    # Project setup exercises the initializer directly; CLI and crash-recovery
    # tests keep their subprocess boundaries through run_init.
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = init.main([str(target), "-n", name, *args])
    assert code == 0, errors.getvalue()
    # P1 lifecycle fixtures isolate coordination from P2 strategy/clock requirements.
    # Guard-specific fixtures enable their guards explicitly after creating the project.
    handoff = target / "handoff.md"
    text = handoff.read_text(encoding="utf-8")
    # General fixtures carry optional summaries so tests of unrelated checks
    # stay quiet. Template/omission regressions call the initializer directly.
    if "- Current best:" not in text:
        text = text.replace("- Current project state: initialized\n", "- Current project state: initialized\n"
                            "- Current best: none yet\n- Active compute: none\n- Plan collection: idle\n")
    configured = rs.read_settings((target / "agents.md").read_text(encoding="utf-8"), target).values
    enabled = rs.enabled_guards(rs.resolve({}, None, configured))
    exemptions = "; ".join(f"{guard} — coordination fixture" for guard in sorted(enabled))
    declaration = "- Not applicable: " + (exemptions or "none")
    if re.search(r"^- Not applicable:.*$", text, re.M):
        text = re.sub(r"^- Not applicable:.*$", declaration, text, flags=re.M)
    else:
        text = text.replace("## Shared state\n", f"## Shared state\n{declaration}\n", 1)
    handoff.write_text(text, encoding="utf-8", newline="\n")
    return target


def check(target: Path, now: dt.datetime = NOW) -> check_project.Checker:
    checker = check_project.Checker(target, now=now)
    checker.code = checker.run(quiet=True)
    return checker


def found(checker: check_project.Checker, severity: str | None = None, check_id: str | None = None) -> list:
    return [issue for issue in checker.issues
            if (severity is None or issue.severity == severity) and (check_id is None or issue.check == check_id)]


def severities(checker: check_project.Checker) -> dict[str, int]:
    counts = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for issue in checker.issues:
        counts[issue.severity] += 1
    return counts


def item(item_id: str, claimed: str | None = "none", extra: list[tuple[str, str]] | None = None,
         stages: str | None = None) -> str:
    lines = [f"### {item_id} — test item"]
    if claimed is not None:
        lines.append(f"- Claimed: {claimed}")
    lines += [f"- {name}: {value}" for name, value in PLAN_VALUES]
    lines += [f"- {name}: {value}" for name, value in extra or []]
    if stages:
        lines.append(f"- Stages: {stages}")
    return "\n".join(lines) + "\n"


def event(stamp: str, slot: str, key: str, discovery: str = "none — stage progress, no experiment",
          new_items: str = "none — nothing follows", extra: str = "", user: str = "operator",
          host: str = "Claude Code") -> str:
    return (f"### {stamp} — {slot} — {key}\n- Host: {host}\n- User: {user}\n- Action: worked on it\n"
            f"- Result: progress\n- Artifacts: none\n- Discovery updates: {discovery}\n- Review verdict: none\n"
            f"- Resource: none\n- Other executor: none\n- New plan items: {new_items}\n{extra}")


def set_queue(target: Path, *items: str, extra_sections: str = "") -> None:
    plan = target / "plan.md"
    text = plan.read_text(encoding="utf-8")
    head = text[:text.index("\n## Queue\n") + 1]
    plan.write_text(head + "## Queue\n\n" + "\n".join(items) + extra_sections, encoding="utf-8", newline="\n")


def set_slot(target: Path, slot: str, host: str, user: str = "operator", thread: str = "none") -> None:
    handoff = target / "handoff.md"
    text = handoff.read_text(encoding="utf-8")
    pattern = re.compile(rf"(### Agent: {slot}\n- Current host: )[^\n]*\n- Current user: [^\n]*\n- Current thread: [^\n]*")
    text, count = pattern.subn(lambda m: f"{m.group(1)}{host}\n- Current user: {user}\n- Current thread: {thread}", text)
    assert count == 1, f"no handoff section for {slot}"
    handoff.write_text(text, encoding="utf-8", newline="\n")


def append_events(target: Path, *events: str) -> None:
    handoff = target / "handoff.md"
    text = handoff.read_text(encoding="utf-8")
    handoff.write_text(init.insert_before_heading(text, "## Archived history", "\n".join(events)),
                       encoding="utf-8", newline="\n")


def append_discovery(target: Path, text: str) -> None:
    path = target / "discoveries.md"
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + text, encoding="utf-8", newline="\n")


def copy_fixture(name: str, destination: Path) -> Path:
    shutil.copytree(FIXTURES / name, destination)
    return destination


def unified_project(parent: Path, name: str = "uni", agents: str = "2") -> Path:
    target = make_project(parent, name, "--preset", "solo-research", "--platforms", "Claude Code",
                          "--user", "operator", "--agents", agents)
    set_slot(target, "A", "Claude Code")
    return target
