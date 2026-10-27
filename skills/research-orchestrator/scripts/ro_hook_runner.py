#!/usr/bin/env python3
"""Run fixed installed hooks with bounded input, a 9-second deadline and visible fail-open."""

from __future__ import annotations

import os
import sys


def cache_options() -> list[str]:
    """Compile outside installed/committed files, falling back to no writes if unavailable."""
    try:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Caches")
        else:
            base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        if not os.path.isabs(base):
            raise OSError("cache root is not absolute")
        directory = os.path.join(base, "research-orchestrator", "pycache")
        os.makedirs(directory, exist_ok=True)
        sys.pycache_prefix = directory
        return ["-X", "pycache_prefix=" + directory]
    except (OSError, ValueError):
        sys.dont_write_bytecode = True
        return ["-B"]


CACHE_OPTIONS = cache_options()
import json
from types import SimpleNamespace

MAX_INPUT = 1024 * 1024
DEADLINE = 9


def normalize_payload(payload):
    """Map explicit host aliases to the Claude-shaped input used by the checks.

    Captured Codex payloads are already Claude-shaped (`tool_name`, `tool_input`,
    `cwd`, `session_id`) and add `turn_id`; Codex names its shell tool `Bash` even
    where it runs PowerShell, so `ro_hooks.host_call` maps that dialect from the
    declared environment. Keep this to named input envelopes; never search
    arbitrary metadata or unwrap interpreter bodies in command text. Canonical
    Claude fields take precedence, including empty/invalid values.
    """
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    if "tool_name" not in normalized and "tool" in payload:
        normalized["tool_name"] = payload["tool"]
    if "tool_input" not in normalized:
        for key in ("input", "arguments"):
            if key in payload:
                raw = payload[key]
                # Function-call arguments may be a JSON object encoded as text.
                # Canonical tool_input strings (and freeform patches) stay literal.
                if key == "arguments" and isinstance(raw, str):
                    try:
                        decoded = json.loads(raw)
                    except ValueError:
                        pass
                    else:
                        if isinstance(decoded, (dict, list)):
                            raw = decoded
                normalized["tool_input"] = raw
                break
        else:
            fields = ("command", "cmd", "argv", "patch", "shell", "background", "run_in_background")
            if any(key in payload for key in ("command", "cmd", "argv", "patch")):
                normalized["tool_input"] = {key: payload[key] for key in fields if key in payload}
    raw = normalized.get("tool_input")
    if isinstance(raw, list) and normalized.get("tool_name") in ("Bash", "PowerShell", "shell", "exec_command"):
        raw = {"command": raw}
    if isinstance(raw, dict):
        raw = dict(raw)
        if "command" not in raw and "cmd" not in raw and "argv" in raw:
            raw["command"] = raw["argv"]
    if "tool_input" in normalized:
        normalized["tool_input"] = raw
    if "cwd" not in normalized:
        if "workdir" in payload:
            normalized["cwd"] = payload["workdir"]
        elif isinstance(raw, dict):
            for key in ("cwd", "workdir"):
                if key in raw:
                    normalized["cwd"] = raw[key]
                    break
    return normalized


def valid_payload(payload) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("cwd", "session_id", "slot", "tool_name"):
        if key in payload and (not isinstance(payload[key], str) or "\0" in payload[key]):
            return False
    if "cwd" in payload and not payload["cwd"]:
        return False
    if "slot" in payload and not (1 <= len(payload["slot"]) <= 2 and
            all("A" <= char <= "Z" for char in payload["slot"])):
        return False
    if "tool_input" in payload and not isinstance(payload["tool_input"], (dict, str)):
        return False
    return True


def failed(project, event, payload, reason, check=None):
    # Healthy calls keep the supervisor small: only the child imports the operational modules.
    from ro_hooks import failure
    from ro_state import Project, project_root
    try:
        owner = Project(project_root(project.root), project.slot, project.session)
    except (OSError, ValueError):
        owner = Project(project_root(project.root), "A", project.session)
    return failure(owner, event, payload, reason, check)


# Tools whose only checks depend on one setting, with the value that leaves them nothing to check.
QUIET_TOOLS = {"Read": ("read bound", "off"), "Glob": ("read bound", "off"), "Grep": ("read bound", "off"),
               "AskUserQuestion": ("autonomy", "present"), "Agent": ("brief requirements", "none")}
RECORD_FILES = ("agents.md", "plan.md", "discoveries.md", "handoff.md")
_RECORD_CACHE: dict[str, tuple[tuple[int, int], dict]] = {}


def unchanged_records(path: str) -> bool:
    """Compare coordination-file metadata with the last completed record check.

    Only the small saved snapshot is read, once per snapshot version in a process.
    Coordination files are stat-only here; missing, old or unreadable snapshots
    take the full check, and pending warning logs always reach their delivery path.
    """
    root = os.path.dirname(path)
    state = os.path.join(root, ".ro")
    try:
        warning_log = os.path.join(state, "warnings.log")
        if os.path.exists(warning_log):
            import hashlib
            shown_path = os.path.join(state, "warnings-shown.json")
            if os.path.getsize(warning_log) > MAX_INPUT or os.path.getsize(shown_path) > MAX_INPUT:
                return False
            with open(shown_path, encoding="utf-8") as source:
                shown = json.load(source)
            with open(warning_log, "rb") as source:
                digest = hashlib.sha256(source.read(MAX_INPUT + 1)).hexdigest()
            if not isinstance(shown, dict) or shown.get("sha256") != digest:
                return False
        snapshot = os.path.join(state, "records-hook.json")
        stat = os.stat(snapshot)
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = _RECORD_CACHE.get(snapshot)
        if cached is None or cached[0] != stamp:
            if stat.st_size > MAX_INPUT:
                return False
            with open(snapshot, encoding="utf-8") as source:
                previous = json.load(source)
            if not isinstance(previous, dict) or any(
                    name not in RECORD_FILES or not isinstance(entry, dict) or entry.get("parser") != 2
                    or not isinstance(entry.get("stamp"), list) or len(entry["stamp"]) != 2
                    or any(type(value) is not int for value in entry["stamp"])
                    or any(not isinstance(entry.get(key), list)
                           or any(not isinstance(value, str) for value in entry[key])
                           for key in ("ids", "duplicate", "future"))
                    for name, entry in previous.items()):
                return False
            if len(_RECORD_CACHE) >= 64:
                _RECORD_CACHE.clear()
            _RECORD_CACHE[snapshot] = (stamp, previous)
        else:
            previous = cached[1]
        for name in RECORD_FILES:
            try:
                stat = os.stat(os.path.join(root, name))
            except FileNotFoundError:
                if name in previous:
                    return False
            else:
                if previous.get(name, {}).get("stamp") != [stat.st_mtime_ns, stat.st_size]:
                    return False
        return True
    except (OSError, UnicodeError, ValueError, TypeError):
        return False


def settings_file(root) -> str | None:
    """The agents.md that project_root would select for this directory, if any."""
    directory = os.path.realpath(root)
    while not os.path.isfile(os.path.join(directory, "agents.md")):
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent
    return os.path.join(directory, "agents.md")


def quiet(event: str, payload: dict, root) -> bool:
    """True only when the child would certainly answer {} without side effects, so none starts.

    `Enforcement: off` (also the default without agents.md) answers {} to PreToolUse,
    PostToolUse and Stop. A current snapshot lets PostToolUse compare only stats.
    Edit/Write have no pre-check without protected jobs. A read,
    question or agent tool has nothing to check while its one
    governing setting keeps the value above. Every agents.md line naming the setting, in any
    section, fenced or not, must agree; anything unreadable or unusual starts the child.
    """
    if event not in ("PreToolUse", "PostToolUse", "Stop") or "slot" in payload:
        return False
    try:
        path = settings_file(root)
        if path is None:
            return True
        if event == "PostToolUse" and unchanged_records(path):
            return True
        if os.path.getsize(path) > MAX_INPUT:
            return False
        with open(path, encoding="utf-8") as source:
            lines = source.read().lower().splitlines()
    except (OSError, UnicodeError, ValueError):
        return False

    def only(label: str, value: str) -> bool:
        return all(line.partition(label)[2].partition(":")[2].strip() == value
                   for line in lines if label in line and ":" in line.partition(label)[2])

    if only("enforcement", "off"):
        return True
    if event == "PreToolUse" and payload.get("tool_name") in ("Edit", "Write", "NotebookEdit"):
        state = os.path.join(os.path.dirname(path), ".ro")
        jobs_path = os.path.join(state, "jobs.json")
        try:
            # A missing primary with a recovery snapshot is not an empty registry.
            if not os.path.exists(jobs_path):
                return not os.path.exists(os.path.join(state, "recovery", "jobs.json"))
            if os.path.getsize(jobs_path) > MAX_INPUT:
                return False
            with open(jobs_path, encoding="utf-8") as source:
                jobs = json.load(source)
            if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
                return False
            if not jobs:
                return True
            # Preserve failed-supervisor and unknown-child ownership exactly as
            # the operational check does; a terminal status alone is not proof.
            from ro_jobs import protected_job
            return not any(protected_job(job) for job in jobs)
        except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
            return False
    rule = QUIET_TOOLS.get(payload.get("tool_name")) if event == "PreToolUse" else None
    return rule is not None and only(*rule)


def diagnostics_enabled(root) -> bool:
    if os.environ.get("RO_HOOK_DIAGNOSTICS") == "1":
        return True
    # Match project_root's agents.md boundary without importing operational
    # modules on every healthy call when diagnostics are disabled.
    directory = original = os.path.abspath(root)
    while not os.path.isfile(os.path.join(directory, "agents.md")):
        parent = os.path.dirname(directory)
        if parent == directory:
            directory = original
            break
        directory = parent
    return os.path.isfile(os.path.join(directory, ".ro", "hook-diagnostics.on"))


def finished(project, event, output, code, failure=False):
    """Append minimal opt-in evidence without changing the host response or exit code."""
    try:
        if diagnostics_enabled(project.root):
            from ro_state import project_root
            state = project_root(project.root) / ".ro"
            from ro_settings import CHECK_IDS
            specific = output.get("hookSpecificOutput", {})
            specific = specific if isinstance(specific, dict) else {}
            blocks = [specific.get("permissionDecisionReason"), output.get("reason")]
            warnings = [specific.get("additionalContext"), output.get("systemMessage")]
            failure = failure or any(field.startswith(("hooks.failure:", "hooks inactive:"))
                                     for field in blocks + warnings if isinstance(field, str))
            if specific.get("permissionDecision") == "deny" or output.get("decision") == "block":
                decision, fields = "denied", blocks
            elif failure:
                decision, fields = "unknown", []
            elif event != "SessionStart" and any(warnings):
                decision, fields = "warned", warnings
            else:
                # SessionStart context is a project brief, not a list of hook findings.
                decision, fields = "no hook decision", []
            known = {*CHECK_IDS, "hooks.failure", "hooks.warning"}
            lines = [line for field in fields if isinstance(field, str) for line in field.splitlines()]
            checks = {line.partition(":")[0] for line in lines if line.partition(":")[0] in known}
            if failure:
                checks.add("hooks.failure")
            state.mkdir(parents=True, exist_ok=True)
            with (state / "hook-diagnostics.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "checks": sorted(checks), "decision": decision}) + "\n")
    except Exception:
        pass  # Diagnostics must not change a computed decision, including a deny.
    return output, code


def run(event: str, raw: bytes, project, check: str | None = None, general: bool = False,
        interpreter: str | None = None, timeout: float = DEADLINE,
        in_process: bool = False, policy_root: str | None = None) -> tuple[dict, int]:
    payload = {}
    command_directory = os.path.abspath(project.root)
    if policy_root:
        project = SimpleNamespace(root=policy_root, slot=project.slot, session=project.session)
    try:
        if len(raw) > MAX_INPUT:
            raise ValueError("oversized input")
        if event != "pre-push":
            original = json.loads(raw or b"{}")
            incoming = original
            if policy_root and isinstance(original, dict) and "cwd" not in original:
                # A host may provide only a relative tool workdir, or no cwd at
                # all. Resolve that against the wrapper's invocation directory,
                # independently of the project that owns settings and jobs.
                incoming = {**original, "cwd": command_directory}
            payload = normalize_payload(incoming)
            if not valid_payload(payload):
                raise ValueError("invalid input")
            if payload != original:
                raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            # Native identity is authoritative: a stale shell RO_SLOT cannot
            # replace the association selected by a command in that session.
            session = str(payload.get("session_id", project.session))
            slot = payload.get("slot") if session else payload.get("slot", project.slot)
            project = SimpleNamespace(root=policy_root or payload.get("cwd", project.root), slot=slot,
                                      session=session)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        return finished(project, event, failed(project, event, {}, "malformed or oversized input"), 0, failure=True)
    if quiet(event, payload, project.root):
        if event == "PostToolUse" and policy_root:
            # A recent snapshot cannot publish coarse-timestamp witnesses yet.
            # The next unchanged wrapper call should publish them once aged,
            # rather than leaving every later call on the Python path forever.
            try:
                if not os.path.isfile(os.path.join(project.root, ".ro", "records-hook.ready")):
                    from ro_hooks import _wrapper_snapshot
                    from ro_state import Project
                    _wrapper_snapshot(Project(project.root, project.slot, project.session, require_slot=False))
            except (OSError, ValueError, TypeError):
                pass  # This optional shortcut cannot change the hook decision.
        return finished(project, event, {}, 0)
    if in_process:
        # Only main() enables this path: it owns the process and has armed an
        # os._exit watchdog. Library callers retain the killable subprocess.
        import contextlib
        import io
        captured = io.StringIO()
        args = SimpleNamespace(project=project.root, slot=project.slot, session=project.session,
                               event=event, check=check, general=general, remote=None, policy_root=policy_root)
        try:
            from ro import hook_main
            with contextlib.redirect_stdout(captured):
                code = hook_main(args, raw)
            output = json.loads(captured.getvalue())
            if not isinstance(output, dict):
                raise ValueError("invalid hook response")
            return finished(project, event, output, code)
        except Exception as exc:
            output = failed(project, event, payload, type(exc).__name__, check)
            denied = output.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
            return finished(project, event, output, int(event == "pre-push" and denied), failure=True)
    import subprocess
    from ro_proc import no_window_flags
    # -X works with -E: environment cannot redirect imports, and caches stay outside the install.
    command = [interpreter or os.environ.get("RO_HOOK_PYTHON", sys.executable), "-E", "-S", *CACHE_OPTIONS,
               os.path.join(os.path.dirname(os.path.abspath(__file__)), "ro.py"), "--project", str(project.root)]
    if project.slot:
        command += ["--slot", project.slot]
    command += ["--session", project.session, "hook", event]
    if policy_root:
        command += ["--policy-root", policy_root]
    if check:
        command += ["--check", check]
    if general:
        command.append("--general")
    try:
        result = subprocess.run(command, input=raw, capture_output=True, timeout=timeout,
                                cwd=command_directory if policy_root else project.root,
                                creationflags=no_window_flags())
        if result.returncode not in ((0, 1) if event == "pre-push" else (0,)):
            raise RuntimeError("child crash")
        output = json.loads(result.stdout)
        if not isinstance(output, dict):
            raise ValueError("invalid hook response")
        return finished(project, event, output, result.returncode)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        output = failed(project, event, payload, type(exc).__name__, check)
        denied = output.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        return finished(project, event, output, int(event == "pre-push" and denied), failure=True)


def watchdog_response(event: str) -> tuple[bytes, int]:
    """No project I/O: a stalled lock or import must not stall the deadline handler."""
    if event == "pre-push":
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                  "permissionDecisionReason": "hooks.failure: hook deadline exceeded"}}
        code = 1
    else:
        output = {"systemMessage": "hooks inactive: hook deadline exceeded"}
        code = 0
    return (json.dumps(output) + "\n").encode("utf-8"), code


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments or arguments[0] not in ("SessionStart", "PreToolUse", "PostToolUse", "Stop", "pre-push"):
        print(__doc__, file=sys.stderr)
        return 2
    event, check, general, policy_root = arguments.pop(0), None, False, None
    while arguments:
        option = arguments.pop(0)
        if option == "--general":
            general = True
        elif option == "--tool" and event == "PreToolUse" and arguments and arguments[0] in ("edit", "ask", "agent"):
            arguments.pop(0)  # Wrapper hint only; the payload remains authoritative.
        elif option == "--policy-root" and arguments:
            policy_root = arguments.pop(0)
        elif option == "--check" and arguments and arguments[0] in ("publish.scan", "external.gate"):
            check = arguments.pop(0)
        else:
            print("invalid hook runner option", file=sys.stderr)
            return 2
    configured = os.environ.get("RO_HOOK_PYTHON")
    in_process = bool(configured and os.path.normcase(os.path.realpath(configured)) ==
                      os.path.normcase(os.path.realpath(sys.executable)))
    timer = None
    if in_process:
        import threading
        finished_lock = threading.Lock()
        done = False

        def deadline():
            nonlocal done
            with finished_lock:
                if done:
                    return
                data, code = watchdog_response(event)
                os.write(1, data)
                os._exit(code)

        timer = threading.Timer(DEADLINE, deadline)
        timer.daemon = True
        timer.start()
    try:
        output, code = run(event, sys.stdin.buffer.read(MAX_INPUT + 1),
                           SimpleNamespace(root=os.getcwd(), slot=os.environ.get("RO_SLOT"),
                                           session=os.environ.get("RO_SESSION") or os.environ.get("CODEX_THREAD_ID", "")),
                           check, general, in_process=in_process, policy_root=policy_root)
        if in_process:
            with finished_lock:
                done = True
                print(json.dumps(output, ensure_ascii=True), flush=True)
        else:
            print(json.dumps(output, ensure_ascii=True))
        return code
    finally:
        if timer is not None:
            timer.cancel()


if __name__ == "__main__":
    raise SystemExit(main())
