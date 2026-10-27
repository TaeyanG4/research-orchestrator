"""Stop a native CLI run at its first observed skill-selection event."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from queue import Empty, Queue
import signal
import subprocess
from threading import Thread
import time

from scripts.evals.proc import no_window_flags


@dataclass
class SelectionResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False
    boundary_event: int | None = None
    after_selection: str = ""


def stop_owned_process(proc: subprocess.Popen) -> None:
    """Terminate only the child tree started by this invocation."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # Popen retains the live process handle; this is our still-running child,
        # not a PID looked up later from a stale registry.
        stopped = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=10,
                                 creationflags=no_window_flags())
        if stopped.returncode and proc.poll() is None:
            proc.kill()
    else:
        # start_new_session gives this invocation a dedicated process group.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait(timeout=10)


def stream_selection(command, *, cwd, env, timeout, on_event) -> SelectionResult:
    """Keep the measured prefix separate from bytes arriving after selection.

    A completed selection is the experimental endpoint. Task execution after it
    is not required and cannot change the selection that was already observed.
    """
    options = ({"creationflags": no_window_flags()} if os.name == "nt"
               else {"start_new_session": True})
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", bufsize=1, **options)
    pending = Queue()
    errors = []

    def read_stdout():
        try:
            for line in proc.stdout:
                pending.put(line)
        finally:
            pending.put(None)

    def read_stderr():
        for line in proc.stderr:
            errors.append(line)

    readers = [Thread(target=read_stdout, daemon=True), Thread(target=read_stderr, daemon=True)]
    for reader in readers:
        reader.start()
    prefix, tail, events = [], [], []
    boundary, timed_out = None, False
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                line = pending.get(timeout=min(remaining, .1))
            except Empty:
                continue
            if line is None:
                break
            prefix.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
                if on_event(events):
                    boundary = len(events)
                    break
        if boundary is not None or timed_out:
            stop_owned_process(proc)
        else:
            try:
                proc.wait(timeout=max(.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_owned_process(proc)
    finally:
        if proc.poll() is None:
            stop_owned_process(proc)
        for reader in readers:
            reader.join(timeout=5)
        for stream in (proc.stdout, proc.stderr):
            stream.close()
        while True:
            try:
                line = pending.get_nowait()
            except Empty:
                break
            if line is not None:
                (tail if boundary is not None else prefix).append(line)
    return SelectionResult("".join(prefix), "".join(errors), proc.returncode, timed_out,
                           boundary, "".join(tail))
