"""Owned external-command process trees, using only the standard library.

Windows starts a small bootstrap that joins a job before receiving the command.
The parent holds the job handle with kill-on-close, so neither fast descendants
nor a parent crash can escape the ownership boundary during command startup.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from ro_proc import no_window_flags


class OwnedTree:
    def __init__(self):
        self.name = "ro-external-" + uuid.uuid4().hex
        self.process = None
        self.handle = None
        if os.name == "nt":
            self._windows()

    def _windows(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class Limits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                    wintypes.DWORD, ctypes.c_void_p]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, self.name)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "cannot create external command job")
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise OSError(ctypes.get_last_error(), "cannot contain external command job")

    def start(self, command, *, popen=subprocess.Popen, **kwargs):
        if os.name != "nt":
            self.process = popen(command, start_new_session=True, stdin=subprocess.DEVNULL, **kwargs)
        else:
            self.process = popen([sys.executable, str(Path(__file__).resolve()), self.name],
                                 stdin=subprocess.PIPE, **kwargs)
            try:
                self.process.stdin.write(json.dumps(command).encode("utf-8"))
                self.process.stdin.close()
            except BaseException:
                self.terminate()
                raise
        return self.process

    def alive(self):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Accounting(ctypes.Structure):
                _fields_ = [("times", ctypes.c_longlong * 4), ("faults", wintypes.DWORD),
                            ("total", wintypes.DWORD), ("active", wintypes.DWORD),
                            ("terminated", wintypes.DWORD)]

            info = Accounting()
            if not self.kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                return None
            return bool(info.active)
        if self.process is None:
            return False
        try:
            result = subprocess.run(["ps", "-e", "-o", "pgid=", "-o", "stat="],
                                    capture_output=True, text=True, timeout=1,
                                    creationflags=no_window_flags())
            if result.returncode:
                return None
            for line in result.stdout.splitlines():
                group, status = line.split()
                if int(group) == self.process.pid and not status.startswith(("Z", "X")):
                    return True
            return False
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    def terminate(self):
        """Return true only after both the launcher and owned tree are proven gone."""
        try:
            # Stop an unassigned Windows bootstrap first; it cannot subsequently
            # enter a previously emptied job and launch new descendants.
            if os.name == "nt":
                if self.process is not None and self.process.poll() is None:
                    self.process.kill()
                    self.process.wait(timeout=2)
                if not self.kernel.TerminateJobObject(self.handle, 1):
                    return False
            elif self.process is not None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if self.process is not None:
                self.process.wait(timeout=2)
            until = time.monotonic() + 2
            while time.monotonic() < until:
                live = self.alive()
                if live is False:
                    return True
                if live is None:
                    return False
                time.sleep(.02)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _bootstrap():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenJobObjectW(1, False, sys.argv[1])  # JOB_OBJECT_ASSIGN_PROCESS
    if not handle or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise OSError(ctypes.get_last_error(), "cannot join external command job")
    # Only the parent retains a handle, so its unexpected exit also kills this job.
    kernel.CloseHandle(handle)
    command = json.load(sys.stdin)
    raise SystemExit(subprocess.call(command, stdin=subprocess.DEVNULL, creationflags=no_window_flags()))


if __name__ == "__main__":
    _bootstrap()
