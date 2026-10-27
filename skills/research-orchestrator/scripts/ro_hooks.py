"""Host adapters and settings-aware hook decisions; warnings never ask or grant permission."""

from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import json
import ntpath
import os
import posixpath
import re
import time

from ro_checks import Call, Finding, adapt, command_parts, git_push, normal_path, outcome, pre_checks
from ro_markdown import unfenced
from ro_time import FUTURE_TOLERANCE
from ro_state import Project, atomic_text, redact


MAX_INPUT = 1024 * 1024
FILES = ("agents.md", "plan.md", "discoveries.md", "handoff.md")
PROTECTED = {"publish.scan", "external.gate"}
POLICY_UNAVAILABLE = ("publish.scan: policy unavailable; restore a readable agents.md and retry. "
                      "Bypassing this hook is your own choice.")
_CACHE: dict[tuple, object] = {}


def cached(project: Project, name: str):
    path = project.root / "agents.md" if name == "settings" else project.state / "jobs.json"
    stat = path.stat() if path.exists() else None
    key = (str(path), stat.st_mtime_ns if stat else None, stat.st_size if stat else None)
    if key not in _CACHE:
        value = project.settings() if name == "settings" else project.read_json("jobs.json", [])
        if len(_CACHE) > 64:
            _CACHE.clear()
        _CACHE[key] = value
    return _CACHE[key]


def _warning_key(finding: Finding, channel: str = "context") -> str:
    identity = (channel, finding.check, finding.identity or (finding.message,), finding.uncertain)
    return hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest()


def warning(project: Project, text: str, identity: tuple[str, ...] = ()) -> None:
    """Log fixed diagnostics, bounded and redacted; no recorded command is replayed."""
    with project.lock(timeout=0.15):
        finding = Finding("hooks.warning", text, identity=identity)
        if not _new_warnings(project, [finding], "log"):
            return
        path = project.state / "warnings.log"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        line = (dt.datetime.now().isoformat(timespec="seconds") + " [" + _warning_key(finding, "log") + "] "
                + redact(text).replace("\n", " ")[:1000])
        atomic_text(path, (old[-62000:] + line + "\n"))


def _new_warnings(project: Project, findings: list[Finding], channel: str = "context") -> list[Finding]:
    """Share warning identities across hook processes, without retaining warning text."""
    if not findings:
        return []
    try:
        with project.lock(timeout=0.15):
            session = hashlib.sha256(project.session.encode()).hexdigest()
            name = "warnings-seen/" + session + ".json"
            seen = set(project.read_json(name, []))
            fresh = []
            for finding in findings:
                key = _warning_key(finding, channel)
                if key not in seen:
                    fresh.append(finding)
                    seen.add(key)
            if fresh:
                project.write_json(name, sorted(seen))
            return fresh
    except Exception:
        return list({_warning_key(finding, channel): finding for finding in findings}.values())


def best_effort_warning(project: Project, text: str, identity: tuple[str, ...] = ()) -> None:
    try:
        warning(project, text, identity)
    except Exception:
        pass  # Diagnostics cannot change an already computed decision.


def response(event: str, blocks: list[str], warnings: list[str], context: bool = True) -> dict:
    extra = "\n".join(warnings)[:8000]
    if event == "Stop":
        if blocks:
            return {"decision": "block", "reason": "\n".join(blocks)}
        return {"systemMessage": extra} if extra and context else {}
    output: dict = {"hookEventName": event}
    if blocks:
        output.update(permissionDecision="deny", permissionDecisionReason="\n".join(blocks))
    if extra and context:
        output["additionalContext"] = extra
    return {"hookSpecificOutput": output} if len(output) > 1 else {}


def _emit(project: Project, event: str, findings: list[Finding], values: dict[str, str], payload: dict,
          failures: set[str] | None = None) -> dict:
    blocked, warned = [], []
    for finding in findings:
        level = outcome(finding, values, event != "pre-push" and finding.check in (failures or set()))
        if event == "PreToolUse" and finding.check == "publish.scan" and level == "block":
            level = "warn"  # Staged content is not necessarily part of the outgoing history.
        if (event == "Stop" and finding.check == "jobs.unmonitored" and level == "block"
                and not _new_warnings(project, [finding], "stop-block")):
            level = "warn"  # One interruption per owned job; later attempts still explain the missing outcome.
        message = finding.check + ": " + finding.message
        if level == "block":
            blocked.append(message)
        elif level == "warn":
            warned.append(finding)
    # An unresolved Stop finding remains actionable on repeated stop attempts.
    if event != "Stop":
        warned = _new_warnings(project, warned)
    context = payload.get("supports_additional_context", True) is not False
    if warned and not context:
        for finding in warned:
            best_effort_warning(project, finding.check + ": " + finding.message, (_warning_key(finding),))
    return response(event, blocked, [finding.check + ": " + finding.message for finding in warned], context)


def host_call(payload: dict, values: dict[str, str]) -> Call:
    """Adapt one host payload, including Codex's platform-independent shell tool name.

    Codex calls its shell tool `Bash` on every platform but runs the platform shell
    (PowerShell on Windows); its payloads carry `turn_id`. Claude Code's `Bash` is real
    bash and has no `turn_id`, so it keeps the bash dialect. An explicit shell field or
    argv shell wrapper stays authoritative.
    """
    call = adapt(payload)
    raw = payload.get("tool_input", payload.get("input", {}))
    command = raw.get("command", raw.get("cmd")) if isinstance(raw, dict) else raw
    if (payload.get("tool_name", payload.get("tool")) == "Bash" and "turn_id" in payload
            and "shell" not in payload and not (isinstance(raw, dict) and "shell" in raw)
            and isinstance(command, str)):
        declared = str(values.get("environment", "")).partition("/")[2]
        if declared in ("bash", "powershell"):
            call.dialect = declared
    return call


def self_test(project: Project) -> dict:
    try:
        values = project.settings()
        shell = values["environment"].split("/")[1]
        call = adapt({"tool_name": "PowerShell" if shell == "powershell" else "Bash",
                      "tool_input": {"command": "echo ready"}})
        if call.dialect != shell or pre_checks(call, project.root, [], values):
            raise ValueError("adapter test failed")
        # Codex names its shell tool Bash on every platform; Claude Code's Bash stays bash.
        codex = host_call({"tool_name": "Bash", "turn_id": "self-test", "tool_input": {"command": "echo ready"}}, values)
        claude = host_call({"tool_name": "Bash", "tool_input": {"command": "echo ready"}}, values)
        if codex.dialect != shell or claude.dialect != "bash" or pre_checks(codex, project.root, [], values):
            raise ValueError("Codex shell adapter test failed")
        if not any(f.check == "shell.background" for f in pre_checks(
                Call("shell", shell, "tool &"), project.root, [], values)):
            raise ValueError("grammar test failed")
        # This checks correctness. The runner owns the deadline and the release
        # suite owns the common latency budget; scheduler delay is not evidence
        # that the shell adapter is inactive.
        result = {"status": "active"}
    except Exception as exc:
        result = {"status": "inactive", "reason": type(exc).__name__}
    project.write_json("hooks-self-test.json", result)
    return result


def _snapshot(project: Project, report: bool = True) -> list[Finding]:
    """Record checks read bodies only after their mtimes change, and never on ordinary PreToolUse."""
    from ro_records import reconcile_ids
    previous = project.read_json("records-hook.json", {})
    # Older snapshots used a backtick toggle, so unchanged files still need
    # reparsing before their example headings can affect IDs or timestamps.
    previous = {name: entry for name, entry in previous.items()
                if isinstance(entry, dict) and entry.get("parser") == 2}
    current, findings = {}, []
    for name in FILES:
        path = project.root / name
        if not path.exists():
            continue
        stat = path.stat()
        stamp = [stat.st_mtime_ns, stat.st_size]
        known = previous.get(name, {})
        if known.get("stamp") == stamp:
            current[name] = known
            continue
        text = path.read_text(encoding="utf-8")
        ids, future, future_records, record = [], [], [], ""
        for line in unfenced(text):
            heading = re.match(r"^#{2,3} ([DHIXN]-[A-Z]{1,2}-\d+)\b", line)
            if line.startswith(("### ", "## ")):
                record = heading[1] if heading else line
            if heading:
                ids.append(heading[1])
            if line.startswith(("### ", "## ", "- Date:")):
                for match in re.finditer(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?", line):
                    try:
                        if dt.datetime.fromisoformat(match[0]) > dt.datetime.now() + FUTURE_TOLERANCE:
                            future.append(match[0])
                            future_records.append([record, match[0]])
                    except ValueError:
                        pass
        duplicate = sorted(key for key, count in Counter(ids).items() if count > 1)
        for affected, date in future_records:
            fresh = ([affected, date] not in known["future_records"] if "future_records" in known
                     else date not in known.get("future", []))
            if report and fresh:
                findings.append(Finding("records.timestamp", "New record timestamp exceeds the five-minute clock-skew allowance.",
                                        identity=(name, affected, date)))
        current[name] = {"parser": 2, "stamp": stamp, "duplicate": duplicate, "future": future,
                         "future_records": future_records, "ids": ids}
    counts = Counter(key for entry in current.values() for key in entry.get("ids", []))
    old_counts = Counter(key for entry in previous.values() for key in entry.get("ids", []))
    introduced = sorted(key for key, count in counts.items() if count > max(1, old_counts[key]))
    if report and introduced:
        findings.append(Finding("records.id", "New duplicate heading IDs: " + ", ".join(introduced[:8]),
                                identity=tuple(introduced)))
    if current != previous:
        project.write_json("records-hook.json", current)
        # Reconciliation only needs IDs, not full unchanged files.
        heading_texts = {name: "\n".join("## " + key for key in entry["ids"]) for name, entry in current.items()}
        reconcile_ids(project, heading_texts)
    return findings


def _slot_reminder(project: Project, messages: list[str]) -> list[str]:
    """Startup and Stop share one actionable selection reminder per session."""
    if not messages:
        return []
    finding = Finding("hooks.warning", "\n".join(messages), identity=("slot-selection",))
    return [item.message for item in _new_warnings(project, [finding])]


def _wrapper_snapshot(project: Project) -> None:
    """Publish mtime witnesses only after records and pending warnings were handled.

    Wrappers compare these files using their native timestamp operations, without
    parsing host input or JSON. Missing files remain explicit missing witnesses.
    """
    ready = project.state / "records-hook.ready"
    ready.unlink(missing_ok=True)
    snapshot = project.read_json("records-hook.json", {})
    if not snapshot:
        return
    warnings = project.state / "warnings.log"
    if warnings.exists() and project.read_json("warnings-shown.json", {}).get("sha256") != hashlib.sha256(warnings.read_bytes()).hexdigest():
        return
    paths = [(name, project.root / name) for name in FILES]
    paths += [("records-hook.json", project.state / "records-hook.json"),
              ("warnings.log", warnings), ("warnings-shown.json", project.state / "warnings-shown.json")]
    stamps = project.state / "records-hook-stamps"
    stamps.mkdir(exist_ok=True)
    for name, path in paths:
        witness = stamps / name
        if not path.exists():
            witness.unlink(missing_ok=True)
            if name in snapshot:
                return
            continue
        stat = path.stat()
        if name in FILES and snapshot.get(name, {}).get("stamp") != [stat.st_mtime_ns, stat.st_size]:
            return
        witness.write_text(str(stat.st_size) + "\n", encoding="ascii", newline="\n")
        os.utime(witness, ns=(stat.st_mtime_ns, stat.st_mtime_ns))
    atomic_text(ready, "records-hook-v1\n")


def _stop(project: Project, payload: dict, jobs: list[dict], values: dict[str, str]) -> dict:
    from ro_jobs import live_monitor, monitor_outcome, running_job
    if not project.slot_selected and (project.explicit_session or project.has_multiple_slots()):
        from ro_sessions import ambiguous, candidates, decision_summary
        rows = candidates(project, os.environ.get("RO_USER", ""))
        if values.get("autonomy") != "away" and ambiguous(rows):
            return response("Stop", [], _slot_reminder(project, [decision_summary(project, rows)]))
        return response("Stop", [], _slot_reminder(project, ["hooks.warning: select this host session's slot with "
                        "--slot or RO_SLOT (or register a native session) before checking owned jobs."]))
    missing = [job for job in jobs if job.get("slot") == project.slot and not live_monitor(job)
               and (running_job(job) or not monitor_outcome(job))]
    if not missing or values.get("enforcement") == "off":
        return {}
    return _emit(project, "Stop", [Finding("jobs.unmonitored",
                 "Owned jobs need a live monitor or a recorded monitor outcome, even after process exit: "
                 + job["id"]
                 + ". Run ro monitor <job>; monitor until it finishes, record the outcome, then close. "
                 "Append the returned Job line to handoff.md; launch confirmation alone does not establish completion.",
                 identity=(str(job["id"]),)) for job in missing],
                 values, payload)


def effective_directory(project: Project, payload: dict, os_family: str) -> tuple[str, bool]:
    """Keep host cwd and a tool override separate from the settings/registry root."""
    path_module = ntpath if os_family == "windows" else posixpath
    base = payload.get("cwd")
    directory = normal_path(base, project.root, os_family) if isinstance(base, str) else None
    uncertain = directory is None or not path_module.isabs(base)
    raw = payload.get("tool_input", payload.get("input", {}))
    raw = raw if isinstance(raw, dict) else {}
    override = raw.get("workdir", raw.get("cwd", payload.get("workdir")))
    if override is not None:
        resolved = normal_path(override, directory or project.root, os_family) if isinstance(override, str) else None
        if resolved and path_module.isabs(override):
            uncertain = False
        uncertain |= resolved is None
        directory = resolved or directory
        if "workdir" in raw and "cwd" in raw:
            other = normal_path(raw["cwd"], base or project.root, os_family) if isinstance(raw["cwd"], str) else None
            uncertain |= other != directory
    return directory or str(project.root), uncertain


def register_startup_slot(project: Project, payload: dict) -> str:
    if project.slot_registered:
        return ""  # A resume/compact event for this native session keeps its route.
    from ro_sessions import startup
    return startup(project, user=payload.get("user", ""), host=payload.get("host", ""),
                   intent=payload.get("session_intent", ""),
                   questions_allowed=payload.get("questions_allowed", True) is not False)


def hook(project: Project, event: str, payload: dict, check: str | None = None, general: bool = False,
         refs: str | None = None, remote: str | None = None) -> dict:
    values = project.settings(required=True) if event == "pre-push" else cached(project, "settings")
    if event == "SessionStart":
        from ro_records import brief, runtime_guidance
        decision = register_startup_slot(project, payload)
        self_test(project)
        _snapshot(project, report=False)
        context = []
        selection = []
        if decision:
            selection.append(decision)
        if project.explicit_session:
            # Host identifiers are data, not arbitrary prose to inject. UUIDs
            # and ordinary opaque host tokens can be copied safely as arguments.
            identifier = project.explicit_session
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", identifier):
                context.append("Host session: " + identifier)
                if not project.slot_registered and not decision:
                    selection.append("Select your handoff slot with ro --session " + identifier
                                   + " --slot <slot> brief; later commands use the same --session.")
            elif not project.slot_registered and not decision:
                selection.append("Select your handoff slot with ro --session <native-host-session> --slot <slot> brief.")
        if decision or (not project.slot_selected and (project.explicit_session or project.has_multiple_slots())):
            if not project.explicit_session and not decision:
                selection.append("Select a slot with --slot or RO_SLOT before resuming this multi-slot project.")
            selection.extend(runtime_guidance(values, project))
            if not decision:
                selection.append("Slot not selected for this host session; no other slot's startup context was loaded.")
        else:
            context.append(brief(project, compact=True) if payload.get("source") == "compact" else brief(project))
        context.extend(_slot_reminder(project, selection))
        return response(event, [], context)
    if event == "pre-push":
        from ro_evidence import PublishScanTimeout, scan_publish
        if values.get("enforcement") == "off":
            return {}
        try:
            findings = [Finding("publish.scan", message) for message in scan_publish(project, refs=refs, remote=remote)]
            return _emit(project, event, findings, values, payload)
        except Exception as exc:
            message = (exc.diagnostic if isinstance(exc, PublishScanTimeout) else
                       "Outgoing scan failed; run it successfully before publishing.")
            result = _emit(project, event, [Finding("publish.scan", message)],
                           values, payload, {"publish.scan"})
            best_effort_warning(project, "publish.scan failure: " + type(exc).__name__)
            return result
    if values.get("enforcement") == "off":
        return {}
    jobs = cached(project, "jobs")
    if not isinstance(jobs, list):
        raise ValueError("invalid jobs registry")
    if event == "Stop":
        return _stop(project, payload, jobs, values)
    if jobs:
        from ro_jobs import protected_job
        jobs = [job for job in jobs if protected_job(job)]
    call = host_call(payload, values)
    findings: list[Finding] = []
    failures = set()
    if event == "PreToolUse":
        parsed = command_parts(call, values) if call.tool == "shell" else None
        is_push = parsed is not None and git_push(parsed.parts, values["environment"].split("/")[0])
        if is_push and not general and check in (None, "publish.scan"):
            try:
                from ro_evidence import scan_publish
                findings.extend(Finding("publish.scan", message) for message in scan_publish(project))
            except Exception as exc:
                best_effort_warning(project, "publish.scan failure: " + type(exc).__name__)
                failures.add("publish.scan")
                findings.append(Finding("publish.scan", "Publish pre-check failed; run the authoritative git pre-push scan."))
        directory, uncertain = effective_directory(project, payload, values["environment"].split("/")[0])
        findings = pre_checks(call, project.root, jobs, values, parsed, findings,
                              cwd=directory, cwd_uncertain=uncertain)
    elif event == "PostToolUse":
        if call.tool in ("Edit", "Write", "shell", "NotebookEdit"):
            findings = _snapshot(project)
        # A host without additionalContext at PreToolUse gets the log on the next post call.
        path = project.state / "warnings.log"
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            known = project.read_json("warnings-shown.json", {})
            if known.get("sha256") != digest:
                logged = []
                for line in path.read_text(encoding="utf-8").splitlines():
                    text = line.partition(" ")[2]
                    tagged = re.match(r"^\[([0-9a-f]{64})\] (.*)$", text)
                    logged.append(Finding("hooks.warning", tagged[2] if tagged else text,
                                          identity=(tagged[1],) if tagged else (text,)))
                pending = _new_warnings(project, logged, "log-context")
                if pending:
                    findings.append(Finding("hooks.warning", "Pending operational warnings: "
                                            + "\n".join(f.message for f in pending)[-3000:],
                                            identity=tuple(f.identity[0] for f in pending)))
                project.write_json("warnings-shown.json", {"sha256": digest})
    if check:
        findings = [finding for finding in findings if finding.check == check]
    elif general:
        findings = [finding for finding in findings if finding.check not in PROTECTED]
    result = _emit(project, event, findings, values, payload, failures)
    if event == "PostToolUse":
        _wrapper_snapshot(project)
    return result


def failure(project: Project, event: str, payload: dict, reason: str, check: str | None = None) -> dict:
    """Per-call failures open; the authoritative pre-push decision survives log failures."""
    reason = redact(reason)[:200]
    try:
        values = project.settings(required=event == "pre-push")
        if values.get("enforcement") == "off":
            return {}
        relevant = "publish.scan" if event == "pre-push" else None
        findings = [Finding(relevant or "hooks.failure", "hooks inactive: " + reason)]
        result = _emit(project, event, findings, values, payload, {f.check for f in findings})
    except Exception:
        # An unreadable policy cannot authorize a publish whose scan never ran.
        result = response(event, [POLICY_UNAVAILABLE] if event == "pre-push" else [],
                          ["hooks inactive: " + reason])
    best_effort_warning(project, "hooks inactive: " + reason)
    try:
        with project.lock(timeout=0.15):
            project.write_json("hooks-self-test.json", {"status": "inactive", "reason": reason})
    except Exception:
        pass
    return result
