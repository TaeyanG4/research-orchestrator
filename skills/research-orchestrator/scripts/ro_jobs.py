#!/usr/bin/env python3
"""Detached jobs with durable ownership, confirmation and explicit monitoring.

The detached runner registers itself, then acknowledges the actual child's start.
Its stdin is a private pipe: raw commands never enter the registry or a temporary
command file. The runner survives the launching CLI and records its child's exit.
"""

from __future__ import annotations

import argparse
import codecs
import datetime as dt
import json
import os
import platform
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

from ro_state import Project, atomic_text, process_start, redact, same_process
from ro_settings import TRANSACTION, safe_regex
from ro_checks import inside, normal_path
from ro_ids import H_PATTERN
from ro_proc import no_window_flags


POLL_SECONDS = 0.1
MAX_POLL_SECONDS = 2.0  # Monitors back off while nothing changes; any change resets the interval.
LOG_SCAN_BYTES = 262144
SCRIPT_SUFFIXES = {".py", ".pyw", ".sh", ".bash", ".ps1", ".cmd", ".bat", ".pl", ".rb", ".js", ".r", ".jl"}


def duration(value: str | int | float, *, zero: bool = False) -> float:
    """Parse a finite seconds/minutes/hours/days duration without evaluating it."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smhd]?)", str(value).strip().lower())
    if not match:
        raise ValueError("duration needs a number followed by s, m, h or d")
    number = float(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    if number > 315360000 or number < 0 or (not zero and number == 0):
        raise ValueError("duration is outside the supported range")
    return number


def _live_supervisor(job: dict) -> bool:
    return bool(job.get("pid") and job.get("start") and same_process(int(job["pid"]), job["start"]))


ENDED = ("finished", "killed", "launch-failed", "exited-before-confirm")


def foreign_job(job: dict) -> bool:
    """A job registered on another machine: local process checks say nothing about it."""
    machine = (job.get("compute") or {}).get("machine")
    return bool(machine and machine != platform.node().casefold())


def tree_ended_on_record(job: dict) -> bool:
    """The recorded proof that a job's process tree is gone, whatever its result status says."""
    return bool(job.get("tree_empty") or (job.get("ended") and job.get("status") == "finished"
                                          and "exit_code" in job))


def running_job(job: dict) -> bool:
    """Retain ownership after supervisor loss until the owned tree is proven empty."""
    if foreign_job(job):
        # Only its own machine can prove the tree ended: a launch failure may leave a live child, and a
        # finished job may carry an `error` result (astra review 2026-11-22, rounds 2-3).
        return not tree_ended_on_record(job)
    if _live_supervisor(job) or _live_child(job):
        return True
    return _tree_alive(job) is not False


def protected_job(job: dict) -> bool:
    """One binding/reservation rule for CLI checks and hooks, including failed runners."""
    if running_job(job):
        return True
    launcher = job.get("launcher") or {}
    if job.get("status") == "starting" and launcher.get("pid") and launcher.get("start"):
        return same_process(launcher["pid"], launcher["start"])
    # Older/synthetic registries may lack identity metadata entirely. Their active
    # ownership is unverified; a record carrying a proven-dead identity is different.
    return (job.get("status") in ("starting", "running", "error", "attention")
            and not any(job.get(key) for key in ("pid", "launcher", "tree_owned", "child_started")))


def live_monitor(job: dict) -> bool:
    monitor = job.get("monitor") or {}
    return bool(monitor.get("active") and monitor.get("pid") and monitor.get("start")
                and same_process(int(monitor["pid"]), monitor["start"]))


def monitor_outcome(job: dict) -> bool:
    """Runner exit and an interrupted monitor are not recorded monitor outcomes."""
    monitor = job.get("monitor") or {}
    return bool(not monitor.get("active") and monitor.get("reason") and monitor.get("ended")
                and monitor["ended"] >= job.get("ended", 0))


def shell_quote(project: Project, part: str) -> str:
    """One argument quoted for the project's configured shell."""
    if project.settings()["environment"].endswith("/powershell"):
        return "'" + part.replace("'", "''") + "'"
    return shlex.quote(part)


def shell_command(project: Project, command: list[str]) -> str:
    """One argv for the project's configured shell (PowerShell needs the call operator)."""
    joined = " ".join(shell_quote(project, part) for part in command)
    return "& " + joined if project.settings()["environment"].endswith("/powershell") else joined


def monitor_command(project: Project, job_id: str) -> str:
    return shell_command(project, [sys.executable, str(Path(__file__).resolve().with_name("ro.py")),
                                   "--project", str(project.root), "--slot", project.slot,
                                   "--session", project.session, "monitor", job_id])


def monitor_next(project: Project, job_id: str) -> str:
    return ("Next: " + monitor_command(project, job_id) + "\n"
            "Keep slot, item and compute ownership: monitor until it finishes, record the outcome, then close.\n"
            "Launch confirmation is not completion. Use the host's background facility for a long monitor wait. "
            "The monitor saves its outcome in .ro/jobs.json; append its returned Job line to handoff.md and "
            "check result artifacts before reporting completion. If it signals a live job's error or stall, "
            "resolve it or stop the owned job, then monitor again.")


def _live_child(job: dict) -> bool:
    child = job.get("child") or {}
    return bool(job.get("child_started") and child.get("pid") and child.get("start")
                and same_process(int(child["pid"]), child["start"]))


def _literal_path(root: Path, value: str | Path, os_family: str) -> Path:
    path = normal_path(str(value), root, os_family)
    if path is None:
        raise ValueError("job bindings must be literal paths")
    return Path(path)


def _windows_active(handle) -> int:
    """Count job members, including the supervisor, even after their parent exits."""
    import ctypes
    from ctypes import wintypes

    class Accounting(ctypes.Structure):
        _fields_ = [(name, ctypes.c_longlong) for name in ("user", "kernel", "period_user", "period_kernel")] + [
            (name, wintypes.DWORD) for name in ("faults", "total", "active", "terminated")]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.DWORD, ctypes.c_void_p]
    info = Accounting()
    if not kernel.QueryInformationJobObject(handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
        raise OSError(ctypes.get_last_error(), "cannot inspect owned job object")
    return info.active


def _windows_job(name: str, *, terminate: bool = False):
    """A job object owns descendants independently of their original parent PID."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    if terminate:
        kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.OpenJobObjectW.restype = wintypes.HANDLE
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        handle = kernel.OpenJobObjectW(8 | 4, False, name)  # JOB_OBJECT_TERMINATE | QUERY
        if not handle:
            raise OSError(ctypes.get_last_error(), "cannot open owned job object")
        try:
            if not kernel.TerminateJobObject(handle, 1):
                raise OSError(ctypes.get_last_error(), "cannot terminate owned job object")
            deadline = time.monotonic() + 3
            while _windows_active(handle):
                if time.monotonic() >= deadline:
                    raise OSError("owned job object did not empty")
                time.sleep(.02)
        finally:
            kernel.CloseHandle(handle)
        return None
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "cannot create owned job object")
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle)
        raise OSError(ctypes.get_last_error(), "cannot assign runner to owned job object")
    # Keep the non-inheritable handle alive in the runner until it exits.
    return handle


def _windows_tree_alive(name: str) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
    if not handle:
        if ctypes.get_last_error() == 2:  # A named job disappears only after its last member exits.
            return False
        raise OSError(ctypes.get_last_error(), "cannot inspect owned job object")
    try:
        return _windows_active(handle) > 0
    finally:
        kernel.CloseHandle(handle)


def _windows_keep_tree_handle(handle, retained: set[tuple[int, str]]) -> None:
    """Let live workers retain the named job when a supervisor crashes.

    Windows removes a job's name when its last handle closes, even if members
    survive. A duplicated handle in each observed member keeps recovery possible;
    those handles close automatically when their owning processes exit.
    """
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.DWORD, ctypes.c_void_p]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                      ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    size = 4096
    while True:
        data = ctypes.create_string_buffer(size)
        if kernel.QueryInformationJobObject(handle, 3, data, size, None):
            break
        if ctypes.get_last_error() != 234 or size >= 8 * 1024 * 1024:
            raise OSError(ctypes.get_last_error(), "cannot inspect owned job members")
        size *= 2
    count = wintypes.DWORD.from_buffer(data, 4).value
    pids = (ctypes.c_size_t * count).from_buffer(data, 8)
    for pid in pids:
        identity = process_start(pid)
        if pid == os.getpid() or identity is None or (pid, identity) in retained:
            continue
        process = kernel.OpenProcess(0x40 | 0x1000, False, pid)  # DUP_HANDLE | QUERY_LIMITED_INFORMATION
        if not process:
            continue  # A member may have exited during inspection.
        try:
            member = wintypes.BOOL()
            if not kernel.IsProcessInJob(process, handle, ctypes.byref(member)):
                raise OSError(ctypes.get_last_error(), "cannot verify owned job member")
            if not member.value:
                continue  # The numeric PID was recycled after the job snapshot.
            copy = wintypes.HANDLE()
            if not kernel.DuplicateHandle(kernel.GetCurrentProcess(), handle, process,
                                          ctypes.byref(copy), 0, False, 2):
                raise OSError(ctypes.get_last_error(), "cannot retain owned job handle")
            retained.add((pid, identity))
        finally:
            kernel.CloseHandle(process)


def _group_members(group: int) -> list[int]:
    result = subprocess.run(["ps", "-e", "-o", "pid=", "-o", "pgid=", "-o", "stat="],
                            capture_output=True, text=True, timeout=5, start_new_session=True,
                            creationflags=no_window_flags())
    if result.returncode:
        raise OSError("cannot inspect owned process group")
    members = []
    for line in result.stdout.splitlines():
        pid, pgid, status = line.split()
        if int(pgid) == group and not status.startswith(("Z", "X")):
            members.append(int(pid))
    return members


def _tree_alive(entry: dict) -> bool | None:
    """None is uncertainty, never permission to release bindings or signal a PID."""
    if tree_ended_on_record(entry):
        return False  # A verified terminal result cannot be revived by later process-group reuse.
    if not entry.get("tree_owned") and not entry.get("child_started"):
        return False  # Legacy records without a tree reservation only identify their supervisor.
    try:
        if os.name == "nt":
            if not entry.get("windows_job"):
                return None
            alive = _windows_tree_alive(entry["windows_job"])
            # Losing the last named handle after a crash is not evidence of an empty tree.
            return alive if alive or entry.get("tree_empty") else None
        return bool(_group_members(int(entry["pid"])))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return None


def _owned_descendants(owned_job) -> bool:
    """The supervisor keeps ownership until no other live group member remains."""
    if os.name == "nt":
        return _windows_active(owned_job) > 1
    return any(pid != os.getpid() for pid in _group_members(os.getpgrp()))


def _all(project: Project) -> list[dict]:
    entries = project.read_json("jobs.json", [])
    if not isinstance(entries, list):
        raise ValueError("jobs.json must be a list")
    return entries


def _get(entries: list[dict], job_id: str) -> dict:
    for entry in entries:
        if entry.get("id") == job_id:
            return entry
    raise ValueError(f"unknown job {job_id}")


def _job_sequence(project: Project, entries: list[dict]) -> int:
    """Keep the high-water mark outside the prunable job registry (under its lock)."""
    saved = project.read_json("job-sequence.json", {"last": 0})
    if (not isinstance(saved, dict) or type(saved.get("last")) is not int
            or saved["last"] < 0):
        raise ValueError("job-sequence.json must contain a non-negative integer last")
    existing = max((int(str(entry.get("id", "")).rsplit("-", 1)[-1])
                    for entry in entries if re.fullmatch(r"J-[A-Z]+-\d+", str(entry.get("id", "")))), default=0)
    return max(saved["last"], existing)


def _refresh(entry: dict) -> None:
    """Recover abandoned reservations and process identities, without killing anything."""
    machine = (entry.get("compute") or {}).get("machine")
    if machine and machine != platform.node().casefold():
        return  # Local PID lookups say nothing about another machine's ownership.
    if entry.get("status") == "starting" and not entry.get("pid"):
        owner = entry.get("launcher") or {}
        if not (owner.get("pid") and owner.get("start") and same_process(owner["pid"], owner["start"])):
            entry.update(status="launch-failed", outcome="launcher exited before runner registration", ended=time.time())
    elif entry.get("pid") and not _live_supervisor(entry) and running_job(entry):
        if entry.get("ended") and entry.get("status") in ENDED:
            # A recorded result (a launch failure, say) keeps its cause and time whichever command
            # refreshes first; the lost supervisor over an unverified tree is marked apart.
            entry["orphaned"] = True
        else:
            entry.update(status="attention", orphaned=True,
                         outcome="supervisor exited; owned work remains live or unverified; use ro kill or reconcile ownership")
            entry.pop("ended", None)
    elif entry.get("pid") and not running_job(entry) and entry.get("status") not in (
            "finished", "killed", "launch-failed", "exited-before-confirm") and not entry.get("ended"):
        entry.update(status="finished", outcome="process exited or identity changed", ended=time.time())
        entry.pop("orphaned", None)


def _update(project: Project, job_id: str, **changes) -> dict:
    with project.lock():
        entries = _all(project)
        entry = _get(entries, job_id)
        entry.update(changes)
        project.write_json("jobs.json", entries)
        return entry.copy()


def _looks_ahead(pattern: str) -> bool:
    """A pattern with an unescaped `$` or a `\\b`, `\\B` or `\\Z` outside a class: its match depends on what
    follows. A literal `\\$` or a `$` inside `[...]` does not (astra round 9)."""
    escaped, in_class, position, members = False, False, 0, 0
    for char in pattern:
        if in_class:
            position += 1
        if escaped:
            if char in "bBZ" and not in_class:
                return True
            escaped, members = False, members + 1
        elif char == "\\":
            escaped = True
        elif in_class:
            if char == "^" and position == 1:
                continue  # one negation, right after `[`; a second `^` is a member (`[^^]`, astra round 11)
            in_class = not (char == "]" and members > 0)  # a `]` first in a class is a member (`[]$]`)
            members += 1
        elif char == "[":
            in_class, position, members = True, 0, 0
        elif char == "$":
            return True
    return False


def _error_match(entry: dict, *, complete: bool = False) -> bool:
    patterns = [safe_regex(pattern) for pattern in entry.get("errors", [])]
    if not patterns:
        return False
    path = Path(entry["log"])
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    # JSON keeps pending bytes across CLI invocations as well as polling calls.
    # A short read is not EOF: the live worker may finish this character later.
    decoder.setstate((bytes.fromhex(entry.get("scan_utf8_pending", "")), 0))
    try:
        with path.open("rb") as source:
            offset = max(0, int(entry.get("scan_offset", 0)))
            source.seek(offset)
            while True:
                data = source.read(LOG_SCAN_BYTES)
                # Carry a bounded overlap so matches crossing polling chunks remain visible.
                tail = str(entry.get("scan_tail", ""))
                if tail and "scan_chars" not in entry:  # scan state from an earlier release: its tail ends
                    entry["scan_legacy_end"] = len(tail)  # here, kept while a scan can re-examine it
                decoded = decoder.decode(data)
                text = tail + decoded
                before = int(entry.get("scan_chars", len(tail)))  # characters scanned before this read
                base = before - len(tail)  # where `text` starts in the whole log
                legacy_end = int(entry.get("scan_legacy_end", -1)) - base  # within `text`; negative = none
                offset += len(data)
                entry["scan_offset"] = offset
                entry["scan_chars"] = before + len(decoded)
                if entry["scan_chars"] - 2 >= int(entry.get("scan_legacy_end", -1)):
                    entry.pop("scan_legacy_end", None)  # later scans start past the old tail
                entry["scan_tail"] = text[-4096:]
                entry["scan_utf8_pending"] = decoder.getstate()[0].hex()
                # The current end of a live log is not its end. A pattern whose ending looks at what follows
                # (`$`, `\b`, `\B`, `\Z`) waits for more text or the finished job's last scan, so `fatal$`
                # never matches `fatalNO` split by a poll, and re-examines the tail's last two characters so
                # a match the next read completes (`fatal\B`) is found; other matches report at once, as an
                # error line at the end of a stalled log must. The search starts just before the new text
                # (matches are at most 511 characters), so earlier matches in old text cannot shift it, and
                # `^` matches only at the log's real start; a match counts when it ends after the last
                # reported one, so a repeated scan reports nothing twice (astra rounds 8-12).
                final = complete and len(data) < LOG_SCAN_BYTES
                # A scan state from an earlier release has no positions, and which of its tail's matches that
                # code reported cannot be rebuilt: it also missed some (`fatal\B` completed inside the tail).
                # The default path already re-examines the tail's last two characters for look-ahead patterns,
                # so an error the old code missed there is found; a match it did report there may repeat once.
                # For an error monitor a miss is worse than a repeat (astra rounds 11-13, Fable 8.0.0 V1).
                reported = int(entry.get("scan_reported", -1))
                waits = [_looks_ahead(pattern.pattern) for pattern in patterns]
                holds = [2 if wait and not final else 0 for wait in waits]
                for pattern, wait, hold in zip(patterns, waits, holds):
                    new_from = len(tail) - (2 if wait else 0)
                    # Once the log outgrows the tail, new_from - 511 already lies past position 0, so `^`
                    # can only match at the log's real start (Fable re-review T1).
                    start = max(0, new_from - 511)
                    for match in pattern.finditer(text, start):
                        if new_from < match.end() <= len(text) - hold and base + match.end() > reported:
                            end = match.end()
                            if end <= legacy_end:
                                # One report covers every reportable match ending in the old tail's
                                # re-examined end: each may repeat an old report, so together they repeat
                                # once, even when a scan of the running job held them first (8.0.0 JB20-21).
                                # A match still held here (one new character, `!$` before a final newline)
                                # is not covered: it may repeat on its own later, which is not a loss.
                                end = max([end] + [found.end() for other, other_hold in zip(patterns, holds)
                                                   for found in other.finditer(text, max(0, legacy_end - 513))
                                                   if found.end() <= min(legacy_end, len(text) - other_hold)])
                            entry["scan_reported"] = base + end
                            return True
                if not complete or len(data) < LOG_SCAN_BYTES:
                    return False
    except OSError:
        return False


def _condition(entry: dict, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    if _error_match(entry):
        return "error pattern matched"
    if entry.get("heartbeat"):
        try:
            heartbeat_at = Path(entry["heartbeat"]).stat().st_mtime
        except OSError:
            heartbeat_at = float(entry["started"])
        if now - max(float(entry["started"]), heartbeat_at) > float(entry["max_silence"]):
            return "heartbeat silence"
    if now - float(entry["started"]) > 2 * float(entry["expect"]):
        return "2x expected duration exceeded"
    return None


def _incident(entry: dict, reason: str) -> None:
    history = entry.setdefault("incidents", [])
    if not history or history[-1].get("resolved") or history[-1]["reason"] != reason:
        history.append({"reason": reason, "observed": time.time()})
    entry.update(status="error" if reason == "error pattern matched" else "attention", outcome=reason)


def _recovered(entry: dict) -> None:
    if entry.get("status") not in ("attention", "error"):
        return
    history = entry.setdefault("incidents", [])
    if not history and entry.get("outcome"):
        history.append({"reason": entry["outcome"], "observed": entry.get("started", time.time())})
    for incident in history:
        incident.setdefault("resolved", time.time())
    entry["status"] = "running"
    entry.pop("outcome", None)


def handoff_line(entry: dict, reason: str) -> str:
    """Return facts for the host to append; commands and matching log content stay private."""
    return f"- Job: {entry['id']}; item {entry['item']}; outcome: {reason}"


def _launch_identity(project: Project) -> tuple[str, str]:
    from ro_records import HANDOFF_SECTIONS, _active_text

    path = project.root / "handoff.md"
    text = _active_text(path.read_text(encoding="utf-8"), HANDOFF_SECTIONS) if path.is_file() else ""
    blocks = re.findall(rf"^### Agent: {re.escape(project.slot)}\s*\n(.*?)(?=^### |^## |\Z)", text, re.M | re.S)
    fields = dict(re.findall(r"^- (Current host|Current user): (.*)$", blocks[0], re.M)) if len(blocks) == 1 else {}
    host, user = fields.get("Current host", "").strip(), fields.get("Current user", "").strip()
    if host.lower() in ("", "ro", "none", "released", "unassigned") or user.lower() in ("", "none", "released", "unassigned"):
        raise ValueError(f"slot {project.slot} needs a taken host and user in handoff.md before launch")
    return host, user


def _launch_ownership(project: Project, item: str) -> None:
    """Check live ownership under the same lock that reserves the job ID."""
    from ro_records import CLAIM, _active_text, _items
    from ro_stages import launch_fields

    fields = launch_fields(project, item)
    base = item.split("/", 1)[0]
    if project.settings()["workflow"] == "unified":
        claim = CLAIM.fullmatch(fields.get("Claimed", ""))
        if not claim or claim.group(1) != project.slot:
            raise ValueError(f"{base} must be claimed by slot {project.slot} before launch")
    else:
        text = (project.root / "plan.md").read_text(encoding="utf-8")
        own_section = _active_text(text, rf"## Agent: {re.escape(project.slot)}\s*")
        if not any(key == base for key, _start, _end, _fields in _items(own_section)):
            raise ValueError(f"{base} must be in slot {project.slot}'s plan section before launch")


def _record_launch(project: Project, entry: dict) -> None:
    host, user = _launch_identity(project)
    path = project.root / "handoff.md"
    text = path.read_text(encoding="utf-8")
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    event = (f"### {stamp} — {entry['slot']} — none\n- Host: {host}\n- User: {user}\n"
             f"- Action: launched job {entry['id']} for {entry['item']} after confirmation\n"
             "- Result: process alive; no configured error pattern matched\n"
             f"- Artifacts: {entry['log']}\n- Discovery updates: none — job start, no finding yet\n"
             "- Review verdict: none\n- Resource: none\n- Other executor: none\n"
             "- New plan items: none — existing item remains active\n\n")
    from ro_markdown import archived_heading
    marker = archived_heading(text)  # the real heading, not a fenced example (astra round 8)
    offset = marker.start() if marker else -1
    text = text[:offset].rstrip() + "\n\n" + event + text[offset:] if offset >= 0 else text.rstrip() + "\n\n" + event
    atomic_text(path, text)


def _compute_request(project: Project, item: str) -> dict:
    """Read routing while holding the reservation lock; absent routing is exclusive CPU."""
    from ro_stages import launch_fields

    fields = launch_fields(project, item)
    resource, parallel = fields.get("Resource", "CPU").upper(), fields.get("Parallel", "NO").upper()
    if resource not in ("CPU", "GPU", "EITHER") or parallel not in ("YES", "NO"):
        raise ValueError("launch needs Resource CPU/GPU/EITHER and Parallel YES/NO")
    return {"machine": platform.node().casefold(), "resource": resource, "parallel": parallel == "YES"}


def _compute_conflict(request: dict, previous: dict) -> bool:
    reserved = previous.get("compute") or {"machine": request["machine"], "resource": "EITHER", "parallel": False}
    if reserved.get("machine") != request["machine"]:
        return False
    shared = (request["resource"] == "EITHER" or reserved.get("resource") == "EITHER"
              or request["resource"] == reserved.get("resource"))
    return shared and not (request["parallel"] and reserved.get("parallel") is True)


def _check_compute_claims(project: Project, item: str, request: dict) -> None:
    """Honor handoff claims for work launched outside this registry as well."""
    from ro_records import COMPUTE_CLAIM, SHARED_SECTION, _active_text

    text = _active_text((project.root / "handoff.md").read_text(encoding="utf-8"), SHARED_SECTION)
    for line in re.findall(r"^- Active compute:\s*(.*)$", text, re.M):
        for raw in line.split(";"):
            match = COMPUTE_CLAIM.fullmatch(raw.strip())
            if not match:
                continue
            route, slot, held_item = match.groups()
            resource, _, machine = route.partition("@")
            if resource == "Other" or (machine and machine.casefold() != request["machine"]):
                continue
            if slot == project.slot and held_item == item.split("/", 1)[0]:
                continue
            previous = _compute_request(project, held_item)
            previous.update(resource=resource, machine=request["machine"])
            if _compute_conflict(request, {"compute": previous}):
                raise ValueError(f"compute reservation conflicts with handoff claim for {held_item}")


INTERPRETERS = {"python", "python3", "py", "pythonw", "rscript", "bash", "sh", "node", "julia", "perl", "ruby", "pwsh",
                "powershell"}


def _check_script(root: Path, run_dir: Path, command: list[str], os_family: str) -> None:
    """Refuse a missing script right after a known interpreter; later operands may be outputs."""
    name = re.split(r"[\\/]", command[0])[-1].lower().removesuffix(".exe")
    if not (name in INTERPRETERS or re.fullmatch(r"python\d+(?:\.\d+)?", name)):
        return
    index = 1
    while index < len(command) and command[index].startswith("-"):
        option = command[index]
        if option in ("-m", "-c", "-Command", "-command", "-e"):
            return  # A module or inline code, not a script file.
        if name in ("bash", "sh") and not option.startswith("--") and "c" in option[1:]:
            return  # Bundled shell options such as -lc run inline code.
        if option in ("-File", "-file"):
            index += 1
            break
        index += 2 if option in ("-X", "-W") else 1
    if index >= len(command) or Path(command[index]).suffix.lower() not in SCRIPT_SUFFIXES:
        return
    script = _literal_path(run_dir, command[index], os_family)
    if script.is_file():
        return
    alternative = _literal_path(root, command[index], os_family)
    hint = (f"; it exists at {alternative} — pass that absolute path" if alternative.is_file() and alternative != script
            else "")
    raise ValueError(f"script {command[index]} resolves to {script} (relative to --run-dir) and does not exist{hint}")


def launch(project: Project, args: argparse.Namespace) -> str:
    command = list(getattr(args, "cmd", None) or getattr(args, "command", None) or [])
    if command and command[0] == "--":
        command.pop(0)
    if not command or not all(isinstance(part, str) and "\x00" not in part for part in command):
        raise ValueError("launch needs an argv command after --")
    item = str(args.item)
    if not re.fullmatch(rf"{H_PATTERN}(?:/s\d+)?", item):
        raise ValueError("launch needs an H-id item")
    expected = duration(args.expect)
    confirm = duration(getattr(args, "confirm", "15s"), zero=True)
    os_family = project.settings()["environment"].split("/")[0]
    run_dir = _literal_path(project.root, getattr(args, "run_dir", None) or ".", os_family)
    if not run_dir.is_dir():
        raise ValueError("run directory must already exist")
    errors = list(getattr(args, "error", None) or [])
    for pattern in errors:
        safe_regex(pattern)
    heartbeat = getattr(args, "heartbeat", None)
    heartbeat_path = str(_literal_path(run_dir, heartbeat, os_family)) if heartbeat else None
    # Relative --heartbeat and script paths resolve against --run-dir; a wrong base reported a false
    # heartbeat silence or killed the job at once (2026-11-05 17:20, 2026-11-10 15:42, 2026-11-18 04:27).
    if heartbeat_path and not Path(heartbeat_path).parent.is_dir():
        raise ValueError(f"--heartbeat resolves to {heartbeat_path} (relative to --run-dir); its folder does not exist. "
                         "If the path is right and the job creates that folder itself, create it before launching")
    _check_script(project.root, run_dir, command, os_family)
    for sealed in getattr(args, "require_seal", None) or []:
        # A preregistered rule edited after sealing must not gate the run it was written for. Like the
        # script and heartbeat, a relative path resolves against --run-dir.
        from ro_write import seal
        seal(project, str(_literal_path(run_dir, sealed, os_family)), check=True)
    max_silence = duration(getattr(args, "max_silence", None) or "20m")
    receipt = getattr(args, "require_receipt", None)
    from ro_stages import launch_review
    launch_review(project, item, receipt)
    explicit = getattr(args, "bind", None) or []
    shared = getattr(args, "input", None) or []
    explicit, shared = ([explicit] if isinstance(explicit, str) else explicit,
                        [shared] if isinstance(shared, str) else shared)
    root_path = normal_path(str(project.root), project.root, os_family)
    bound = {str(_literal_path(project.root, value, os_family)) for value in explicit}
    # Shared read bindings: protected from mutation like every binding, but other jobs may read them too.
    inputs = {str(_literal_path(project.root, value, os_family)) for value in shared}
    if any(inside(root_path, normal_path(value, project.root, os_family)) for value in bound | inputs):
        raise ValueError("bind a specific input or run directory, not the project root or its ancestor")
    broad_run_dir = inside(root_path, normal_path(str(run_dir), project.root, os_family))
    notice = ("Notice: project root is not bound; only script paths and explicit --bind entries are protected.\n"
              if broad_run_dir else "")
    if not broad_run_dir:
        bound.add(str(run_dir))
    for token in command:
        if not token.startswith("-") and Path(token).suffix.lower() in SCRIPT_SUFFIXES:
            script = str(_literal_path(run_dir, token, os_family))
            if not inside(root_path, normal_path(script, project.root, os_family)):
                inputs.add(script)  # Scripts are read, not written: parallel trials may share them.
    inputs -= bound
    exclusive = {normal_path(value, project.root, os_family) for value in bound}
    readable = {normal_path(value, project.root, os_family) for value in inputs}
    launcher_start = process_start(os.getpid())
    if launcher_start is None:
        raise ValueError("cannot establish launcher process identity")
    with project.lock():
        if (project.root / TRANSACTION).is_file():
            # A pending close may finish this item on recovery while the new job runs (astra review round 3).
            raise ValueError("an interrupted record transaction is pending; run `ro close-item --recover` first")
        launch_review(project, item, receipt)  # The plan or receipt may have changed while acquiring the lock.
        _launch_identity(project)  # Refuse before reserving an ID or starting any process.
        _launch_ownership(project, item)
        compute = _compute_request(project, item)
        entries = _all(project)
        for previous in entries:
            _refresh(previous)
            previous_inputs = {normal_path(value, project.root, os_family) for value in previous.get("inputs", [])}
            previous_all = {normal_path(value, project.root, os_family) for value in previous.get("bound", [])}
            # Older registries have no inputs field: every binding there stays exclusive.
            previous_exclusive = previous_all - previous_inputs
            pairs = [(a, b) for a in exclusive for b in previous_all] + [(a, b) for a in readable for b in previous_exclusive]
            if protected_job(previous) and any(inside(a, b) or inside(b, a)
                    for a, b in pairs if a and b and not inside(root_path, b)):
                raise ValueError(f"bound path conflicts with job {previous['id']}")
            if protected_job(previous) and _compute_conflict(compute, previous):
                raise ValueError(f"compute reservation conflicts with job {previous['id']}; wait or use Parallel: YES for both items after checking capacity")
        _check_compute_claims(project, item, compute)
        number = _job_sequence(project, entries) + 1
        # Reserve before writing the registry: a failed launch can leave a gap, never a reused ID.
        project.write_json("job-sequence.json", {"last": number})
        job_id = f"J-{project.slot}-{number:04d}"
        log_dir = project.state / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        entry = {"id": job_id, "item": item, "slot": project.slot, "session": project.session,
                 "status": "starting", "compute": compute, "launcher": {"pid": os.getpid(), "start": launcher_start},
                 "pid": None, "start": None, "started": time.time(), "expect": expected,
                 "run_dir": str(run_dir), "bound": sorted(bound | inputs), "inputs": sorted(inputs), "errors": errors,
                 "heartbeat": heartbeat_path, "max_silence": max_silence,
                 "log": str(log_dir / f"{job_id}-{uuid.uuid4().hex}.log"),
                 "command": redact(subprocess.list2cmdline(command)),
                 "windows_job": "Local\\ro-" + uuid.uuid4().hex if os.name == "nt" else None,
                 "monitor": None, "confirmed": False}
        entries.append(entry)
        project.write_json("jobs.json", entries)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    try:
        with Path(entry["log"]).open("xb", buffering=0) as output:
            runner = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--runner",
                                       str(project.root), job_id], stdin=subprocess.PIPE, stdout=output,
                                      stderr=subprocess.STDOUT, close_fds=True, creationflags=flags,
                                      start_new_session=os.name != "nt")
            try:
                runner.stdin.write(json.dumps(command).encode("utf-8"))
                runner.stdin.close()
            except (BrokenPipeError, OSError):
                pass
    except OSError as exc:
        # No runner process exists, so no tree does: record that, or remote sessions protect it forever.
        _update(project, job_id, status="launch-failed", outcome="runner could not start", ended=time.time(),
                tree_empty=True)
        raise ValueError(f"job runner could not start: {redact(str(exc))}\n" + monitor_next(project, job_id)) from None
    startup_deadline = time.monotonic() + 10
    confirmation_deadline = None
    while True:
        with project.lock():
            entries = _all(project)
            current = _get(entries, job_id)
            _refresh(current)
            # Supervisor registration is not evidence that the command started.
            child_alive = _live_child(current)
            if current.get("child_started") and confirmation_deadline is None:
                confirmation_deadline = time.monotonic() + confirm
            if current.get("orphaned"):  # The supervisor died: never confirm the launch as healthy.
                project.write_json("jobs.json", entries)
                return (notice + handoff_line(current, current.get("outcome") or "supervisor exited")
                        + "\n" + monitor_next(project, job_id))
            reason = _condition(current) if current.get("child_started") else None
            if reason:
                _incident(current, reason)
            alive = running_job(current)
            if current.get("status") in ("finished", "launch-failed", "killed") or (current.get("pid") and not alive):
                current["confirmed"] = False
                project.write_json("jobs.json", entries)
                return (notice + handoff_line(current, current.get("outcome", "finished before confirmation"))
                        + "\n" + monitor_next(project, job_id))
            if reason:
                project.write_json("jobs.json", entries)
                return notice + handoff_line(current, reason) + "\n" + monitor_next(project, job_id)
            if current.get("child_ended") and time.time() - current["child_ended"] >= 3 * POLL_SECONDS:
                project.write_json("jobs.json", entries)
                return (notice + handoff_line(current, "launcher exited; owned process tree still supervised")
                        + "\n" + monitor_next(project, job_id))
            if (confirmation_deadline is not None and time.monotonic() >= confirmation_deadline
                    and alive and child_alive):
                current["confirmed"] = True
                _record_launch(project, current)
                project.write_json("jobs.json", entries)
                return notice + f"{job_id} launched; confirmed alive\n" + monitor_next(project, job_id)
            if confirmation_deadline is None and time.monotonic() >= startup_deadline:
                project.write_json("jobs.json", entries)
                return (notice + handoff_line(current, "child start confirmation timed out")
                        + "\n" + monitor_next(project, job_id))
            project.write_json("jobs.json", entries)
        time.sleep(POLL_SECONDS)


def _poll_bound(entry: dict) -> float:
    """Back off to MAX_POLL_SECONDS, never past the next overrun or heartbeat deadline."""
    now, bounds = time.time(), [MAX_POLL_SECONDS]
    try:
        bounds.append(float(entry["started"]) + 2 * float(entry["expect"]) - now)
        if entry.get("heartbeat"):
            bounds.append(float(entry["max_silence"]) / 4)
    except (KeyError, TypeError, ValueError):
        pass
    return max(POLL_SECONDS, min(bounds))


def monitor(project: Project, job_ids: str | list[str]) -> str:
    """Watch one or more jobs until each reaches an outcome.

    One monitor for several jobs replaces a loop of sequential monitors, which left later jobs
    unwatched and repeated the Stop-hook reminder (2026-11-06: 69 times in one session).
    """
    job_ids = [job_ids] if isinstance(job_ids, str) else list(dict.fromkeys(job_ids))
    identity = process_start(os.getpid())
    if not identity:
        raise ValueError("cannot establish monitor process identity")
    with project.lock():
        entries = _all(project)
        for job_id in job_ids:
            entry = _get(entries, job_id)
            if foreign_job(entry):
                raise ValueError(f"{job_id} runs on {entry['compute']['machine']}; monitor it there")
            if live_monitor(entry):
                raise ValueError(f"{job_id} already has a live monitor")
        for job_id in job_ids:
            _get(entries, job_id)["monitor"] = {"pid": os.getpid(), "start": identity, "active": True,
                                                "since": time.time()}
        project.write_json("jobs.json", entries)
    delay = POLL_SECONDS
    pending, lines = list(job_ids), []
    try:
        while pending:
            bound = MAX_POLL_SECONDS
            with project.lock():
                entries = _all(project)
                before = json.dumps(entries, sort_keys=True)
                for job_id in list(pending):
                    entry = _get(entries, job_id)
                    _refresh(entry)
                    if entry.get("orphaned"):
                        reason = entry["outcome"]
                        if entry.get("ended") and _error_match(entry, complete=True):
                            # A later log finding is kept beside the recorded failure, never in its place,
                            # so the result does not depend on which command refreshed first (astra round 6).
                            entry.setdefault("incidents", []).append({"reason": "error pattern matched",
                                                                      "observed": time.time()})
                            reason += "; error pattern matched"
                    elif not running_job(entry) and entry.get("status") != "starting":
                        failed = entry.get("ended") and entry.get("status") in ("launch-failed", "killed")
                        hit = _error_match(entry, complete=True)  # once: it advances the log scan state
                        if hit and failed:
                            # A recorded failure keeps its cause; the log finding is added beside it
                            # (astra round 7: a monitor after reconcile replaced `launch-failed`).
                            entry.setdefault("incidents", []).append({"reason": "error pattern matched",
                                                                      "observed": time.time()})
                            reason = f"{entry.get('outcome') or entry['status']}; error pattern matched"
                        elif hit:
                            reason = "error pattern matched"
                            _incident(entry, reason)
                        else:
                            reason = entry.get("outcome", "process exited")
                    else:
                        reason = _condition(entry)
                        if reason:
                            _incident(entry, reason)
                        else:
                            _recovered(entry)
                    if reason:
                        entry["monitor"].update(active=False, reason=reason, ended=time.time())
                        pending.remove(job_id)
                        lines.append(handoff_line(entry, reason))
                        if len(job_ids) > 1:
                            print(lines[-1], flush=True)  # Report each outcome as it arrives.
                    else:
                        bound = min(bound, _poll_bound(entry))
                changed = json.dumps(entries, sort_keys=True) != before
                if changed:
                    project.write_json("jobs.json", entries)  # Change-only writes: no fsync per idle poll.
            if pending:
                delay = POLL_SECONDS if changed else min(delay * 1.5, bound)
                time.sleep(delay)
        return lines[0] if len(job_ids) == 1 else f"all {len(job_ids)} jobs reached an outcome; Job lines above"
    finally:
        with project.lock():
            entries = _all(project)
            changed = False
            for entry in entries:
                if entry.get("id") not in job_ids:
                    continue  # A job pruned after its reported outcome is simply gone.
                owner = entry.get("monitor") or {}
                if owner.get("pid") == os.getpid() and owner.get("start") == identity and owner.get("active"):
                    owner.update(active=False, ended=time.time())
                    changed = True
            if changed:
                project.write_json("jobs.json", entries)


def kill(project: Project, job_id: str) -> str:
    with project.lock():
        entries = _all(project)
        entry = _get(entries, job_id)
        if entry.get("slot") and entry["slot"] != project.slot:
            raise ValueError(f"{job_id} belongs to slot {entry['slot']}; stop it from that slot (--slot {entry['slot']})")
        if foreign_job(entry):
            raise ValueError(f"{job_id} runs on {entry['compute']['machine']}; stop it there")
        if not running_job(entry):
            _refresh(entry)
            project.write_json("jobs.json", entries)
            raise ValueError("job process is gone or its identity changed; nothing killed")
        pid = int(entry["pid"])
        # Keep the ownership lock through the identity check and termination command.
        if os.name == "nt":
            if entry.get("windows_job"):
                try:
                    _windows_job(entry["windows_job"], terminate=True)
                except OSError:
                    raise ValueError("job tree could not be terminated") from None
            else:
                if not _live_supervisor(entry):
                    raise ValueError("owned tree identity cannot be established; reconcile ownership; nothing killed")
                result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                                        timeout=10, creationflags=no_window_flags())
                if result.returncode and same_process(pid, entry["start"]):
                    raise ValueError("job tree could not be terminated")
            deadline = time.monotonic() + 3
            while same_process(pid, entry["start"]) and time.monotonic() < deadline:
                time.sleep(.02)
            if same_process(pid, entry["start"]):
                raise ValueError("job tree did not terminate")
        else:
            witnesses = [{"pid": pid, "start": entry.get("start")}, entry.get("child") or {},
                         *entry.get("tree_members", [])]
            def member_identity(witness):
                try:
                    return (same_process(witness.get("pid", 0), witness.get("start"))
                            and os.getpgid(witness["pid"]) == pid)
                except OSError:
                    return False
            if not any(member_identity(witness) for witness in witnesses):
                raise ValueError("owned process group identity cannot be established; reconcile ownership; nothing killed")
            witnesses.extend({"pid": member, "start": process_start(member)} for member in _group_members(pid))
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 2
            while _group_members(pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            if _group_members(pid):
                # Recheck an identity before escalating; never signal a recycled numeric group.
                if not any(member_identity(witness) for witness in witnesses):
                    raise ValueError("remaining process identity is unverified; reconcile ownership")
                os.killpg(pid, signal.SIGKILL)
            deadline = time.monotonic() + 3
            while _group_members(pid) and time.monotonic() < deadline:
                time.sleep(.02)
            if _group_members(pid):
                raise ValueError("job tree did not terminate")
        entry.update(status="killed", outcome="job process tree killed", ended=time.time(), tree_empty=True)
        entry.pop("orphaned", None)
        if entry.get("monitor"):
            entry["monitor"]["active"] = False
        project.write_json("jobs.json", entries)
    return handoff_line(entry, "job process tree killed")


def jobs(project: Project, prune: bool = False, running: bool = False) -> str:
    with project.lock():
        entries = _all(project)
        for entry in entries:
            _refresh(entry)
        if prune:
            # Migrate older registries before discarding their only record of allocated IDs.
            project.write_json("job-sequence.json", {"last": _job_sequence(project, entries)})
            entries = [entry for entry in entries if running_job(entry) or entry.get("status") == "starting"
                       or not monitor_outcome(entry)]
        project.write_json("jobs.json", entries)
    if running:
        # Jobs that still hold ownership or lack an outcome; a long registry hid them (H-A-60 A16).
        entries = [entry for entry in entries if running_job(entry) or entry.get("status") == "starting"
                   or not monitor_outcome(entry)]
    return "\n".join(f"{entry['id']} {entry['item']} {entry['status']}; monitor "
                     + ("live" if live_monitor(entry) else "outcome recorded" if monitor_outcome(entry) else "outcome missing")
                     for entry in entries) or ("No running or unreported jobs." if running else "No jobs.")


def reconcile(project: Project, job_id: str, evidence: str) -> str:
    """Close a job whose supervisor and child are gone but whose tree cannot be proven empty.

    After a host restart the named Windows job object disappears, so the job stayed `attention`
    forever and the registry was edited by hand (2026-11-01 19:10). The owner supplies the evidence.
    """
    evidence = " ".join(evidence.split())
    if not evidence:
        raise ValueError("reconcile needs --evidence: what shows the processes are gone and what the outputs hold")
    with project.lock():
        entries = _all(project)
        entry = _get(entries, job_id)
        if entry.get("slot") and entry["slot"] != project.slot:
            raise ValueError(f"{job_id} belongs to slot {entry['slot']}")
        if foreign_job(entry):
            raise ValueError(f"{job_id} ran on {entry['compute']['machine']}; local process checks say nothing "
                             "about it, so reconcile it there")
        # An end recorded before this call is evidence already; one _refresh infers now is reconciled and saved.
        # _refresh may turn a recorded launch failure into `attention`, so keep the record as it was.
        recorded_end = bool(entry.get("ended") and entry.get("status") in ENDED)
        original = dict(entry)
        _refresh(entry)
        launcher = entry.get("launcher") or {}
        if (_live_supervisor(entry) or _live_child(entry) or _tree_alive(entry) is True
                or (entry.get("status") == "starting" and launcher.get("pid") and launcher.get("start")
                    and same_process(launcher["pid"], launcher["start"]))):
            raise ValueError(f"{job_id} still has a live process; monitor it or use `ro kill {job_id}`")
        if monitor_outcome(entry) and tree_ended_on_record(entry):  # Nothing left to reconcile.
            return handoff_line(entry, entry["monitor"]["reason"])
        reason = f"reconciled by the owner: {evidence}"
        now = time.time()
        if recorded_end:  # Keep the recorded status, outcome, end and exit code; the owner's evidence closes the tree.
            entry.clear()
            entry.update(original, tree_empty=True)
            reason = f"{entry.get('outcome') or entry['status']}; {reason}"
        else:  # An end inferred just now keeps its status; a job still marked live is closed as killed.
            if entry.get("status") not in ENDED:
                entry.update(status="killed", ended=now)
            entry.update(outcome=reason, tree_empty=True)
        entry.pop("orphaned", None)  # The tree is closed now; no supervisor is missing any more.
        entry["monitor"] = {**(entry.get("monitor") or {}), "active": False, "reason": reason,
                            "ended": max(now, entry.get("ended") or 0)}
        # The owner's evidence outlives later monitors, which replace the monitor record (astra round 5).
        entry.setdefault("reconciled", []).append({"evidence": evidence, "at": now, "slot": project.slot})
        project.write_json("jobs.json", entries)
    return handoff_line(entry, reason)


def _runner(root: str, job_id: str) -> int:
    """Own the runner's process group and descendants; never adopt a foreign PID."""
    project = Project(Path(root), slot=job_id.split("-")[1])
    child = None
    try:
        payload = sys.stdin.buffer.read(1048577)
        if len(payload) > 1048576:
            raise ValueError("command is too large")
        command = json.loads(payload)
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ValueError("runner received no argv")
        identity = process_start(os.getpid())
        if not identity:
            raise ValueError("runner identity unavailable")
        with project.lock():
            entries = _all(project)
            entry = _get(entries, job_id)
            if entry.get("status") != "starting" or entry.get("pid"):
                raise ValueError("job reservation no longer belongs to this runner")
            owned_job = _windows_job(entry["windows_job"]) if os.name == "nt" else None
            entry.update(pid=os.getpid(), start=identity, status="starting", tree_owned=True)
            project.write_json("jobs.json", entries)
        # The detached runner has no console; the job child gets a hidden one instead of a window.
        # The job's `ro` calls act for its slot even when the launch named it with --slot (H-A-60 C3).
        child_env = {**os.environ, "RO_SLOT": str(entry.get("slot") or project.slot)}
        child = subprocess.Popen(command, cwd=entry["run_dir"], stdin=subprocess.DEVNULL,
                                 stdout=sys.stdout, stderr=sys.stderr, close_fds=True,
                                 creationflags=no_window_flags(), env=child_env)
        child_identity = process_start(child.pid)
        retained_handles: set[tuple[int, str]] = set()
        if os.name == "nt":
            _windows_keep_tree_handle(owned_job, retained_handles)
        if child_identity and child.poll() is None:
            with project.lock():
                entries = _all(project)
                current = _get(entries, job_id)
                if (current.get("pid") == os.getpid() and current.get("start") == identity
                        and current.get("status") == "starting"):
                    started = time.time()
                    current.update(status="running", started=started, child_started=started,
                                   child={"pid": child.pid, "start": child_identity})
                    project.write_json("jobs.json", entries)
        while child.poll() is None:
            if os.name == "nt":
                _windows_keep_tree_handle(owned_job, retained_handles)
            time.sleep(POLL_SECONDS)
        code = child.wait()
        waiting = False
        while True:
            try:
                if not _owned_descendants(owned_job):
                    break
                if os.name == "nt":
                    _windows_keep_tree_handle(owned_job, retained_handles)
                else:
                    members = [{"pid": pid, "start": process_start(pid)} for pid in _group_members(os.getpgrp())
                               if pid != os.getpid()]
                    _update(project, job_id, tree_members=[member for member in members if member["start"]])
            except (OSError, ValueError, subprocess.TimeoutExpired):
                # A failed inspection is not evidence that descendants have stopped.
                with project.lock():
                    entries = _all(project)
                    _incident(_get(entries, job_id), "owned process group inspection failed")
                    project.write_json("jobs.json", entries)
            if not waiting:
                _update(project, job_id, child_ended=time.time(), child_exit_code=code)
                waiting = True
            time.sleep(POLL_SECONDS)
        with project.lock():
            entries = _all(project)
            current = _get(entries, job_id)
            if current.get("pid") == os.getpid() and current.get("start") == identity and current.get("status") != "killed":
                outcome = current.get("outcome") or f"process exited with code {code}"
                current.update(status="finished", outcome=outcome, exit_code=code, ended=time.time(), tree_empty=True)
                project.write_json("jobs.json", entries)
        return code
    except Exception as exc:
        try:
            _update(project, job_id, status="launch-failed", outcome="runner failed: " + redact(str(exc)),
                    ended=time.time(), tree_empty=child is None)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--runner":
        raise SystemExit(_runner(sys.argv[2], sys.argv[3]))
    raise SystemExit("ro_jobs is an internal module; use ro launch / monitor / kill / jobs")
