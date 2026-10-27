#!/usr/bin/env python3
"""Atomic, ownership-aware local state for the operational commands."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

import ro_settings as rs
from ro_credentials import SECRET_PATTERNS
from ro_markdown import visible_lines


def _ps_identity(pid: int) -> tuple[str, str] | None:
    """BSD/macOS fallback: retain immutable creation data separately from status."""
    import subprocess
    from ro_proc import no_window_flags
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart=", "-o", "stat="],
                                capture_output=True, text=True, timeout=1, creationflags=no_window_flags())
        fields = result.stdout.strip().rsplit(None, 1)
        if result.returncode == 0 and len(fields) == 2 and fields[0] and fields[1]:
            return fields[0], fields[1]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def project_root(directory: Path | str) -> Path:
    """Locate settings after a host changes directory; do not read coordination bodies."""
    path = Path(directory).resolve()
    for candidate in (path, *path.parents):
        if (candidate / "agents.md").is_file():
            return candidate
    return path


def process_start(pid: int) -> str | None:
    """Return a process creation identity, or None when it has ended or is inaccessible."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                return None
            creation, end, system, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(x) for x in (creation, end, system, user))):
                return None
            return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    proc = Path("/proc") / str(pid) / "stat"
    if proc.exists():
        try:
            # comm can contain spaces and parentheses; the fields follow its final ')'.
            fields = proc.read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            return None if fields[0] in ("Z", "X") else fields[19]
        except (OSError, IndexError):
            return None
    identity = _ps_identity(pid)
    return identity[0] if identity and not identity[1].startswith(("Z", "X")) else None


def same_process(pid: int, start: str | None) -> bool:
    return bool(start) and process_start(pid) == str(start)


def _owner_dead(owner: dict) -> bool:
    """Never steal merely because an identity lookup was denied."""
    pid, start = owner.get("pid"), owner.get("start")
    if not isinstance(pid, int) or pid <= 0 or not start:
        return False
    current = process_start(pid)
    if current is not None:
        return current != str(start)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            kernel.CloseHandle(handle)
            return True  # lookup succeeded but the process has exited
        return ctypes.get_last_error() == 87  # invalid pid; access denied is not death
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.ESRCH
    stat = Path("/proc") / str(pid) / "stat"
    try:
        return stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0] in ("Z", "X")
    except (OSError, IndexError):
        identity = _ps_identity(pid)
        return bool(identity and identity[1].startswith(("Z", "X")))


def redact(text: str) -> str:
    """Remove credential values from stored diagnostic strings."""
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
                  "[REDACTED PRIVATE KEY]", str(text))
    text = re.sub(r"(?i)(\bauthorization\b\s*(?:=|:)\s*)(?:(?:bearer|basic)\s+)?[^\s,;\"']+",
                  r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(\b(?:password|passwd|token|secret|api[_-]?key|authorization)\b\s*(?:=|:)\s*)"
                  r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(--(?:password|token|secret|api[_-]?key)\s+)(?:\"[^\"]*\"|'[^']*'|\S+)",
                  r"\1[REDACTED]", text)
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    return re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)


def atomic_text(path: Path, text: str) -> None:
    """Replace one file atomically; callers hold their project lock."""
    import uuid
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        for attempt in range(9):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 8:
                    raise
                time.sleep(min(0.005 * 2 ** attempt, 0.1))
    finally:
        temporary.unlink(missing_ok=True)


class Project:
    def __init__(self, root: Path | str, slot: str | None = None, session: str = "", *, require_slot: bool = True):
        self.root = Path(root).resolve()
        self.state = self.root / ".ro"
        # A process-local identity is useful for incidental tool state, but is not
        # an author assertion: receipts require the explicitly supplied identity.
        self.explicit_session = (session or os.environ.get("RO_SESSION", "")).strip()
        self.session = self.explicit_session or f"local:{os.getpid()}:{process_start(os.getpid())}"
        self._locks = threading.local()
        self.session_file = "sessions/" + hashlib.sha256(self.session.encode()).hexdigest() + ".json"
        selection = self.read_json(self.session_file, {}) if self.explicit_session and slot is None else {}
        if not isinstance(selection, dict) or (selection and not re.fullmatch(
                r"[A-Z]{1,2}", str(selection.get("slot", "")))):
            raise ValueError("invalid session slot association")
        selected = slot or selection.get("slot") or os.environ.get("RO_SLOT")
        if not selected and require_slot and self.has_multiple_slots():
            raise ValueError("select a slot (--slot or RO_SLOT), or register this session before using a multi-slot project")
        self.slot = selected or "A"
        if not isinstance(self.slot, str) or not re.fullmatch(r"[A-Z]{1,2}", self.slot):
            raise ValueError("slot must be one or two uppercase letters")
        self.slot_registered = selection.get("slot") == self.slot
        self.slot_selected = slot is not None or self.slot_registered or bool(os.environ.get("RO_SLOT"))
        if require_slot and self.explicit_session and not self.slot_selected and (self.root / "agents.md").is_file():
            from ro_sessions import ambiguous, candidates
            if ambiguous(candidates(self, os.environ.get("RO_USER", ""))):
                raise ValueError("select a slot: run ro brief for the new-session choice before using this project")

    def has_multiple_slots(self) -> bool:
        """Read ownership only at selection/start/stop boundaries, never per-tool checks."""
        handoff = self.root / "handoff.md"
        if not handoff.is_file():
            return False
        with handoff.open(encoding="utf-8") as source:
            slots = {match.group(1) for line, visible in visible_lines(source) if visible
                     and (match := re.fullmatch(r"### Agent: ([A-Z]{1,2})\s*", line))}
        return len(slots) > 1

    def register_slot(self) -> None:
        """Bind a selected slot to a stable host identity across child processes."""
        if not self.explicit_session:
            raise ValueError("register a slot with --session <native-host-session> or RO_SESSION")
        selection = {"slot": self.slot}
        # A later command reaffirms this route; retain its deferred decision in
        # subsequent briefs until the session explicitly switches slots.
        if self.slot_registered:
            previous = self.read_json(self.session_file, {})
            if previous.get("slot") == self.slot and previous.get("decision"):
                selection["decision"] = previous["decision"]
        self.write_json(self.session_file, selection)
        self.slot_registered = True
        self.slot_selected = True

    def settings(self, *, required: bool = False) -> dict[str, str]:
        """Read only the settings block, never the coordination bodies or user rules."""
        lines: list[str] = []
        active = False
        try:
            with (self.root / "agents.md").open(encoding="utf-8") as source:
                for line, visible in visible_lines(source):
                    if not visible:
                        continue
                    if line.startswith("## "):
                        if active:
                            break
                        if line.rstrip() == "## Project rules":
                            break
                        active = line.rstrip() == "## Project settings"
                    if active:
                        lines.append(line)
        except FileNotFoundError:
            if required:
                raise
        stored = rs.read_settings("".join(lines), self.root)
        if required and (not stored.has_section or "enforcement" not in stored.values or
                (stored.values["enforcement"].lower() == "block" and "block" not in stored.values)):
            raise ValueError("required policy settings are unavailable")
        return rs.resolve({}, None, stored.values)

    def read_json(self, name: str, default=None, *, validate=None):
        """Recover durable metadata from its snapshot while holding the state lock.

        Callers opt into snapshots when writing state that cannot be reconstructed
        safely. A damaged file without a valid snapshot remains an error, never an
        empty job registry, receipt ledger, or identifier counter.
        """
        path = self._state_path(name)

        def load(source):
            value = json.loads(source.read_text(encoding="utf-8"))
            if validate is not None and not validate(value):
                raise ValueError(f"invalid metadata: {name}")
            return value

        missing = False
        try:
            return load(path)
        except FileNotFoundError:
            missing = True
        except (ValueError, UnicodeError):
            pass
        recovery = self._state_path("recovery/" + name)
        if missing and not recovery.exists():
            return default
        with self.lock():
            # Another process may have repaired/replaced it while we waited.
            try:
                return load(path)
            except (FileNotFoundError, ValueError, UnicodeError):
                pass
            try:
                value = load(recovery)
            except (FileNotFoundError, ValueError, UnicodeError) as exc:
                raise ValueError(f"cannot recover {name}; restore its metadata from a trusted backup") from exc
            if path.exists():
                import uuid
                damaged = path.with_name(f"{path.name}.corrupt-{time.time_ns()}-{uuid.uuid4().hex}")
                damaged.write_bytes(path.read_bytes())
            atomic_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            return value

    def _state_path(self, name: str) -> Path:
        path = (self.state / name).resolve()
        if not path.is_relative_to(self.state.resolve()):
            raise ValueError("state path leaves .ro")
        return path

    def write_json(self, name: str, data, *, recoverable: bool = False) -> None:
        with self.lock():
            text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            atomic_text(self._state_path(name), text)
            if recoverable:
                atomic_text(self._state_path("recovery/" + name), text)

    def atomic_text(self, path: Path, text: str) -> None:
        path = Path(path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("write path leaves project")
        with self.lock():
            atomic_text(path, text)

    @contextmanager
    def lock(self, name: str = "state", timeout: float = 10):
        import uuid
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("invalid lock name")
        held = getattr(self._locks, "held", {})
        if name in held:
            held[name] += 1
            try:
                yield
            finally:
                held[name] -= 1
            return
        directory = self.state / "locks"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.lock"
        token = uuid.uuid4().hex
        owner = {"pid": os.getpid(), "start": process_start(os.getpid()), "token": token}
        if owner["start"] is None:
            raise ValueError("cannot establish lock owner process identity")
        deadline = time.monotonic() + timeout
        # Keep the inode stable. Unlinking a stale lock can unlink a new owner's replacement
        # between the identity check and unlink. OS file locks serialize reclamation itself
        # and are released by the operating system when a process dies.
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        while True:
            try:
                _file_lock(fd)
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise ValueError(f"lock {name} is held; owner was not proven dead")
                time.sleep(0.01)
                continue
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, 16384)
            try:
                existing = json.loads(raw.decode("utf-8")) if raw.strip() else {}
            except (ValueError, UnicodeError):
                existing = None
            known_owner = (isinstance(existing, dict) and isinstance(existing.get("pid"), int)
                           and not isinstance(existing.get("pid"), bool) and existing["pid"] > 0
                           and bool(existing.get("start")))
            if known_owner and not _owner_dead(existing):
                _file_unlock(fd)
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise ValueError(f"lock {name} is held; owner was not proven dead")
                time.sleep(0.01)
                continue
            if existing != {} and not known_owner:
                # The OS lock is authoritative for a torn metadata write. Keep the
                # damaged bytes for inspection; never unlink/replace the locked inode.
                try:
                    path.with_name(f"{path.name}.corrupt-{time.time_ns()}-{token}").write_bytes(raw)
                except OSError:
                    _file_unlock(fd)
                    os.close(fd)
                    raise
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps(owner).encode("utf-8"))
            os.fsync(fd)
            break
        held[name] = 1
        self._locks.held = held
        try:
            yield
        finally:
            held.pop(name, None)
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                os.ftruncate(fd, 0)
                os.write(fd, b"{}")
                os.fsync(fd)
            finally:
                _file_unlock(fd)
                os.close(fd)


def _file_lock(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _file_unlock(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


def duration(raw: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", raw.strip())
    if not match or float(match.group(1)) <= 0:
        raise ValueError("duration must be positive, e.g. 15s, 20m or 2h")
    return float(match.group(1)) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
