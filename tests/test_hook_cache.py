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


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("changed", ["receipt", "missing-receipt", "file", "directory", "missing-artifact"])
def test_brief_refreshes_review_findings_when_only_review_evidence_changes(tmp_path, monkeypatch, compact, changed):
    import datetime as dt
    from conftest import NOW, append_events, event, unified_project
    from check_project import Checker
    import ro_evidence
    import ro_records
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    monkeypatch.setattr(ro_records.time, "time", lambda: NOW.timestamp())
    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return NOW.date()
    monkeypatch.setattr(ro_records.dt, "date", FixedDate)
    checked = []
    def checker(current):
        checked.append(current)
        result = Checker(current.root, now=NOW)
        return result, result.run(quiet=True)
    monkeypatch.setattr(ro_records, "_checker", checker)
    artifact = project.root / ("review" if changed == "directory" else "result.txt")
    if changed == "directory":
        artifact.mkdir()
        member = artifact / "result.txt"
    else:
        member = artifact
    member.write_text("approved evidence\n", encoding="utf-8")
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra=f"- Decision: changed\n- Review artifact: {artifact.name}\n"))
    ro_evidence.receipt_add(project, artifact.name, "independent-reviewer", "PASS", "H-A-01/s1:after")
    for _ in range(2):
        assert "event.stage.review" not in ro_records.brief(project, compact=compact)
    assert len(checked) == 1
    before = {name: (project.root / name).read_bytes() for name in ro_records.FILES}
    original_stat = member.stat()
    if changed == "receipt":
        ro_evidence.receipt_add(project, artifact.name, "independent-reviewer", "FAIL", "H-A-01/s1:after")
    elif changed == "missing-receipt":
        (project.state / "receipts.json").unlink()
    elif changed == "missing-artifact":
        member.unlink()
    else:
        member.write_text("rejected evidence\n", encoding="utf-8")
        # Same-length changes can retain their timestamp after a restore/copy.
        os.utime(member, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert "event.stage.review: 1" in ro_records.brief(project, compact=compact)
    assert len(checked) == 2
    assert before == {name: (project.root / name).read_bytes() for name in ro_records.FILES}
    if not member.exists():
        member.write_text("restored evidence\n", encoding="utf-8")
    ro_evidence.receipt_add(project, artifact.name, "independent-reviewer", "PASS", "H-A-01/s1:after")
    for _ in range(2):
        assert "event.stage.review" not in ro_records.brief(project, compact=compact)
    assert len(checked) == 3
    assert before == {name: (project.root / name).read_bytes() for name in ro_records.FILES}


def test_startup_brief_reports_oversized_review_evidence_unverified_without_hashing_it(tmp_path, monkeypatch):
    """A non-compact brief runs inside the SessionStart deadline: large review evidence stays unread."""
    from conftest import append_events, event, unified_project
    import ro_evidence
    import ro_records
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    run = project.root / "run"
    run.mkdir()
    for index in range(20):
        (run / f"part-{index:02d}.bin").write_bytes(b"x" * 2048)
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra="- Decision: changed\n- Review artifact: run\n"))
    ro_evidence.receipt_add(project, "run", "independent-reviewer", "PASS", "H-A-01/s1:after")
    monkeypatch.setattr(ro_evidence, "BRIEF_HASH_BYTES", 10_000)  # smaller than the 40 KiB directory
    read = []
    original = ro_evidence._hash_file
    monkeypatch.setattr(ro_evidence, "_hash_file", lambda path, *a, **k: read.append(path) or original(path, *a, **k))
    output = ro_records.brief(project)
    # Reported as unverified, never as passed, and not as a failed review.
    assert "event.stage.review unverified within the brief's hash budget: 1" in output
    assert "event.stage.review: " not in output
    assert read == []  # the budget is checked before any member is read
    checker = ro_records._checker(project)[0]
    with ro_evidence.hash_budget(10_000):
        message = next(i.message for i in ro_records._checker(project)[0].issues if i.check == "event.stage.review")
    assert "check_project.py" in message and "ro receipt check" in message  # the remedy that verifies it
    assert not [i for i in checker.issues if i.check == "event.stage.review"]  # unbudgeted check verifies
    # Outside a brief, the full check still verifies the same receipt.
    assert ro_evidence.receipt_check(project, "run", "H-A-01/s1:after")


def test_brief_reads_each_review_artifact_once(tmp_path, monkeypatch):
    """The stamp and the rerun checker share one budget and reuse the stamp's digest."""
    from conftest import append_events, event, unified_project
    import ro_evidence
    import ro_records
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    (project.root / "result.txt").write_text("retain one verified copy\n", encoding="utf-8")
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra="- Decision: changed\n- Review artifact: result.txt\n"))
    ro_evidence.receipt_add(project, "result.txt", "independent-reviewer", "PASS", "H-A-01/s1:after")
    read = []
    original = ro_evidence._hash_file
    monkeypatch.setattr(ro_evidence, "_hash_file", lambda path, *a, **k: read.append(path.name) or original(path, *a, **k))
    output = ro_records.brief(project)
    assert "event.stage.review" not in output  # the receipt verified
    assert read == ["result.txt"]


def test_repeated_brief_reuses_the_cache_for_an_over_cap_review_directory(tmp_path, monkeypatch):
    """An over-cap directory cannot verify, so its result holds; compaction must not rerun the checker."""
    from conftest import append_events, event, unified_project
    import ro_evidence
    import ro_records
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    run = project.root / "many"
    run.mkdir()
    for index in range(6):
        (run / f"m{index}.txt").write_text("x", encoding="utf-8")
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra="- Decision: changed\n- Review artifact: many\n"))
    monkeypatch.setattr(ro_evidence, "MANIFEST_CAP", 5)
    first = ro_records.brief(project)
    assert "event.stage.review: 1" in first  # never reported as passed
    calls = []
    original = ro_records._checker
    monkeypatch.setattr(ro_records, "_checker", lambda p: calls.append(1) or original(p))
    assert "event.stage.review: 1" in ro_records.brief(project, compact=True)
    assert calls == []


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("size", ["content", "metadata"])
def test_directory_link_added_to_a_reviewed_directory_invalidates_the_cache(tmp_path, monkeypatch, compact, size):
    """Full hashing refuses directory links, so a cached clean review must not survive one."""
    import os
    import subprocess
    from conftest import append_events, event, unified_project
    import ro_evidence
    import ro_records
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    run = project.root / "run"
    run.mkdir()
    (run / "result.txt").write_text("retain one verified copy\n", encoding="utf-8")
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra="- Decision: changed\n- Review artifact: run\n"))
    ro_evidence.receipt_add(project, "run", "independent-reviewer", "PASS", "H-A-01/s1:after")
    if size == "metadata":
        monkeypatch.setattr(ro_evidence, "STAMP_HASH_BYTES", 1)  # the stamp uses member metadata only
    assert "event.stage.review" not in ro_records.brief(project, compact=compact)
    target, link = tmp_path / "elsewhere", run / "linked"
    target.mkdir()
    if os.name == "nt":
        if subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True).returncode:
            pytest.skip("directory junctions are unavailable")
    else:
        os.symlink(target, link, target_is_directory=True)
    assert "event.stage.review: 1" in ro_records.brief(project, compact=compact)


def test_budget_unverified_review_is_named_in_the_brief(tmp_path, monkeypatch):
    from conftest import append_events, event, unified_project
    import ro_evidence
    import ro_records
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    (project.root / "result.txt").write_text("x" * 4096, encoding="utf-8")
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra="- Decision: changed\n- Review artifact: result.txt\n"))
    ro_evidence.receipt_add(project, "result.txt", "independent-reviewer", "PASS", "H-A-01/s1:after")
    monkeypatch.setattr(ro_evidence, "BRIEF_HASH_BYTES", 1000)
    output = ro_records.brief(project)
    line = next(row for row in output.splitlines() if "unverified within the brief's hash budget" in row)
    assert line.split("budget: ", 1)[1].startswith("1;") and "check_project.py" in line


def test_over_cap_directory_is_unhashed_before_reading_any_member(tmp_path, monkeypatch):
    import ro_evidence
    from ro_state import Project
    from conftest import unified_project
    project = Project(unified_project(tmp_path), slot="A")
    run = project.root / "many"
    run.mkdir()
    for index in range(6):
        (run / f"m{index}.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ro_evidence, "MANIFEST_CAP", 5)
    monkeypatch.setattr(ro_evidence, "_hash_file", lambda *a, **k: pytest.fail("read a member of an over-cap directory"))
    assert ro_evidence.hash_artifact(project, "many")["sha256"] == "unhashed"


def _reviewed_directory(tmp_path, compact_files=2):
    from conftest import append_events, event, unified_project
    import ro_evidence
    from ro_state import Project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    project.register_slot()
    run = project.root / "run"
    (run / "nested").mkdir(parents=True)
    for index in range(compact_files):
        (run / "nested" / f"part-{index}.txt").write_text(f"verified {index}\n", encoding="utf-8")
    append_events(project.root, event("2026-10-25 10:00", "A", "H-A-01/s1",
                  extra="- Decision: changed\n- Review artifact: run\n"))
    ro_evidence.receipt_add(project, "run", "independent-reviewer", "PASS", "H-A-01/s1:after")
    return project, run


def test_brief_walks_a_reviewed_directory_once(tmp_path, monkeypatch):
    """The stamp's own walk supplies the members it hashes; the directory is not enumerated twice."""
    import ro_evidence
    import ro_records

    project, run = _reviewed_directory(tmp_path)
    walks = []
    original = ro_evidence.os.walk
    monkeypatch.setattr(ro_evidence.os, "walk", lambda top, *a, **k: walks.append(top) or original(top, *a, **k))
    assert "event.stage.review" not in ro_records.brief(project)
    assert [Path(top).resolve() for top in walks] == [run.resolve()]


@pytest.mark.parametrize("failure", ["member", "directory"])
def test_unreadable_review_member_is_never_served_from_the_cache(tmp_path, monkeypatch, failure):
    """An unstampable directory reruns the checker on every compact brief and reads no member."""
    import ro_evidence
    import ro_records

    project, run = _reviewed_directory(tmp_path)
    assert "event.stage.review" not in ro_records.brief(project, compact=True)
    if failure == "member":
        original_lstat = Path.lstat
        broken = run / "nested" / "part-1.txt"
        monkeypatch.setattr(Path, "lstat", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError(13, "denied"))
                            if self == broken else original_lstat(self, *a, **k))
    else:
        original_walk = ro_evidence.os.walk

        def walk(top, topdown=True, onerror=None, followlinks=False):
            # The nested directory became unreadable after the clean review was cached.
            for directory, names, files in original_walk(top, topdown, None, followlinks):
                if Path(directory).name == "nested":
                    if onerror is not None:
                        onerror(PermissionError(13, "denied", directory))
                    continue
                yield directory, names, files
        monkeypatch.setattr(ro_evidence.os, "walk", walk)
    assert ro_evidence.stat_artifact(project, "run") == {"kind": "directory", "unstamped": True}
    calls, read = [], []
    original_checker, original_hash = ro_records._checker, ro_evidence._hash_file
    monkeypatch.setattr(ro_records, "_checker", lambda p: calls.append(1) or original_checker(p))
    monkeypatch.setattr(ro_evidence, "_hash_file", lambda path, *a, **k: read.append(path) or original_hash(path, *a, **k))
    for _ in range(2):
        assert "event.stage.review: 1" in ro_records.brief(project, compact=True)
    assert len(calls) == 2
    assert read == []  # an incomplete enumeration never hashes a partial manifest


@pytest.mark.parametrize("moment", ["before-open", "while-reading"])
def test_file_growth_cannot_exceed_the_reserved_hash_bytes(tmp_path, monkeypatch, moment):
    """The budget reserves the measured size; a file that grows is refused, never read in full."""
    import ro_evidence
    from ro_state import Project
    from conftest import unified_project

    project = Project(unified_project(tmp_path), slot="A", session="stage-author")
    artifact = project.root / "growing.log"
    artifact.write_bytes(b"x")
    real_open = Path.open
    consumed = []

    class Growing:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            if moment == "before-open":
                with real_open(artifact, "ab") as grow:
                    grow.write(b"y" * 99)
            return self

        def __exit__(self, *exc):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def read(self, size=-1):
            data = self.handle.read(size)
            consumed.append(len(data))
            if moment == "while-reading" and sum(consumed) == 1:
                with real_open(artifact, "ab") as grow:
                    grow.write(b"y" * 99)
            return data

    monkeypatch.setattr(Path, "open", lambda self, mode="r", *a, **k: Growing(real_open(self, mode, *a, **k))
                        if self == artifact and "b" in mode else real_open(self, mode, *a, **k))
    with ro_evidence.hash_budget(2), pytest.raises(ValueError, match="changed while hashing"):
        ro_evidence.hash_artifact(project, "growing.log")
    assert sum(consumed) <= 2  # never more than the one reserved byte plus the growth probe
