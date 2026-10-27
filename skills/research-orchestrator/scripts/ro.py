#!/usr/bin/env python3
"""Research Orchestrator operational CLI. Commands are authoritative; hooks accelerate them."""

from __future__ import annotations

import os
import sys

# Direct CLI hooks (including Git pre-push) need the same external cache as the
# supervised path. Suppress writes while importing its bootstrap itself.
if __name__ == "__main__" and sys.pycache_prefix is None:
    previous_no_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    from ro_hook_runner import CACHE_OPTIONS
    sys.dont_write_bytecode = previous_no_bytecode or "-B" in CACHE_OPTIONS

import json
from pathlib import Path
from types import SimpleNamespace

from ro_state import Project, project_root


HOOK_EVENTS = ("SessionStart", "PreToolUse", "PostToolUse", "Stop", "pre-push")


def add_hook_parser(commands) -> None:
    import argparse
    hook = commands.add_parser("hook", formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80))
    hook.add_argument("event", choices=HOOK_EVENTS)
    hook.add_argument("--check", choices=("publish.scan", "external.gate"))
    hook.add_argument("--general", action="store_true")
    # Remote names are descriptive only; Git supplies verified destination tips on stdin.
    hook.add_argument("--remote")
    hook.add_argument("--policy-root", help=argparse.SUPPRESS)


def global_parser(**kwargs) -> argparse.ArgumentParser:
    import argparse
    result = argparse.ArgumentParser(**kwargs)
    result.add_argument("--project", default=".")
    result.add_argument("--slot")
    result.add_argument("--session", default=os.environ.get("RO_SESSION") or os.environ.get("CODEX_THREAD_ID", ""))
    return result


def parser(hooks_only: bool = False) -> argparse.ArgumentParser:
    import argparse
    result = global_parser(description=__doc__,
                           formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80))
    commands = result.add_subparsers(dest="command_name", required=True)
    if hooks_only:
        add_hook_parser(commands)
        return result
    reserve = commands.add_parser("next-id")
    reserve.add_argument("kind", choices=("D", "H", "I", "X", "N"))
    reserve.add_argument("--slot", default=argparse.SUPPRESS)
    duplicate = commands.add_parser("dupcheck")
    duplicate.add_argument("terms", nargs="+")
    index = commands.add_parser("index")
    index.add_argument("identifier", nargs="?", default="")
    index.add_argument("--full", action="store_true", help="whole Finding lines and archived stubs")
    tools = commands.add_parser("tools", help="search the docs/tools.md registry before writing a script")
    tools.add_argument("terms", nargs="*")
    tools.add_argument("--init", action="store_true", help="create docs/tools.md with its usage rules")
    archive = commands.add_parser("archive", help="move settled discoveries or older events to docs/archive/")
    archive.add_argument("kind", choices=("discoveries", "events", "restore"))
    archive.add_argument("identifier", nargs="?", default="", help="the discovery ID to restore")
    archive.add_argument("--before", default="", help="archive eligible records dated before YYYY-MM-DD")
    archive.add_argument("--dry-run", action="store_true")
    for command in ("claim", "release"):
        sub = commands.add_parser(command)
        sub.add_argument("item")
    launch = commands.add_parser("launch")
    launch.add_argument("--item", required=True)
    launch.add_argument("--expect", required=True)
    launch.add_argument("--run-dir")
    launch.add_argument("--bind", action="append", nargs="+", default=[])
    # Read-only inputs other jobs may share; --bind and the run directory stay exclusive.
    launch.add_argument("--input", action="append", nargs="+", default=[])
    launch.add_argument("--error", action="append", nargs="+", default=[])
    launch.add_argument("--heartbeat")
    launch.add_argument("--max-silence", default="20m")
    launch.add_argument("--confirm", default="15s")
    launch.add_argument("--require-receipt")
    launch.add_argument("command", nargs=argparse.REMAINDER)
    for name in ("monitor", "kill"):
        sub = commands.add_parser(name)
        sub.add_argument("job")
    jobs = commands.add_parser("jobs")
    jobs.add_argument("--prune", action="store_true")
    receipts = commands.add_parser("receipt").add_subparsers(dest="receipt_command", required=True)
    for name in ("add", "check"):
        sub = receipts.add_parser(name)
        sub.add_argument("artifact")
        sub.add_argument("--scope", required=name == "add")
        sub.add_argument("--dest", default=None)
        if name == "add":
            sub.add_argument("--reviewer", required=True)
            sub.add_argument("--verdict", choices=("PASS", "FAIL"), required=True)
    external = commands.add_parser("external")
    external.add_argument("--artifact")
    external.add_argument("--deadline", type=float, default=300,
                          help="maximum seconds for the outward command (default: 300)")
    external.add_argument("--action")
    external.add_argument("command", nargs=argparse.REMAINDER)
    observation = commands.add_parser("observe")
    observation.add_argument("key")
    observation.add_argument("value")
    observation.add_argument("--source", default="")
    observation.add_argument("--ttl", default="6h")
    brief = commands.add_parser("brief")
    brief.add_argument("--max", dest="max_chars", default=8000, type=int)
    brief.add_argument("--intent", choices=("continue", "parallel"), default="")
    brief.add_argument("--reclaim", action="store_true", help="user chose this ended stale session's slot")
    brief.add_argument("--no-questions", action="store_true")
    brief.add_argument("--user", default="")
    brief.add_argument("--host", default="")
    commands.add_parser("close")
    add_hook_parser(commands)
    # Command fallback for every PreToolUse check on hosts without hooks.
    check = commands.add_parser("check")
    check.add_argument("--dialect", choices=("bash", "powershell"), default="bash")
    check.add_argument("shell_command")
    return result


def hook_arguments(arguments: list[str]):
    """Parse the fixed installed-hook command line without argparse, which costs ~10 ms per call.

    Global options, `hook <event>`, `--check`, `--general` and `--remote` only; anything else
    returns None so argparse parses (and reports) it exactly as before.
    """
    values = {"project": ".", "slot": None,
              "session": os.environ.get("RO_SESSION") or os.environ.get("CODEX_THREAD_ID", "")}
    index = 0
    while index < len(arguments) and arguments[index] != "hook":
        option, separator, value = arguments[index].partition("=")
        if option not in ("--project", "--slot", "--session"):
            return None
        if not separator:
            index += 1
            if index >= len(arguments) or arguments[index].startswith("-"):
                return None
            value = arguments[index]
        values[option[2:]] = value
        index += 1
    rest = arguments[index + 1:]
    if not rest or rest[0] not in HOOK_EVENTS:
        return None
    result = SimpleNamespace(command_name="hook", event=rest[0], check=None, general=False, remote=None,
                             policy_root=None, **values)
    options = rest[1:]
    while options:
        option = options.pop(0)
        if option == "--general":
            result.general = True
        elif option in ("--check", "--remote", "--policy-root") and options and not options[0].startswith("-"):
            value = options.pop(0)
            if option == "--check" and value not in ("publish.scan", "external.gate"):
                return None
            setattr(result, option[2:].replace("-", "_"), value)
        else:
            return None
    return result


def hook_main(args, data: bytes | None = None) -> int:
    from ro_hooks import MAX_INPUT, failure, hook
    raw = data if data is not None else sys.stdin.buffer.read(MAX_INPUT + 1)
    # Start with a safe diagnostic owner; resolving persisted associations stays
    # inside the fail-open boundary below, including corrupt JSON.
    project = Project(args.project, "A", args.session)
    payload = {}
    try:
        if len(raw) > MAX_INPUT:
            raise ValueError("oversized hook input")
        if args.event == "pre-push":
            refs = raw.decode("utf-8")
        else:
            from ro_hook_runner import normalize_payload, valid_payload
            payload = normalize_payload(json.loads(raw or b"{}"))
            if not valid_payload(payload):
                payload = {}
                raise ValueError("hook input must be an object")
            refs = None
            # Wrappers discover policy independently of the command's cwd.
            # Keep cwd in the payload so relative operands retain host semantics.
            root = getattr(args, "policy_root", None) or payload.get("cwd", args.project)
            session = str(payload.get("session_id", args.session))
            slot = payload.get("slot", args.slot)
            if not session and slot is None:
                slot = os.environ.get("RO_SLOT")
            # Per-call checks protect all bindings without selecting an owner or
            # reading history. Ownership-changing CLI commands still require a slot.
            project = Project(project_root(root), slot, session, require_slot=False)
            if slot and project.explicit_session:
                project.register_slot()
        result = hook(project, args.event, payload, args.check, args.general, refs,
                      remote=getattr(args, "remote", None))
    except Exception as exc:
        # Invalid JSON/oversized input is always fail open, including a protected matcher.
        result = failure(project, args.event, payload, type(exc).__name__,
                         None if isinstance(exc, (ValueError, UnicodeError, json.JSONDecodeError)) and not payload else args.check)
    print(json.dumps(result, ensure_ascii=True))
    output = result.get("hookSpecificOutput", {})
    return 1 if args.event == "pre-push" and output.get("permissionDecision") == "deny" else 0


def main(argv: list[str] | None = None) -> int:
    from ro_console import utf8_output
    utf8_output()
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = hook_arguments(arguments)
    if args is None:
        import argparse
        probe = global_parser(add_help=False)
        probe.add_argument("remaining", nargs=argparse.REMAINDER)
        leading, _ = probe.parse_known_args(arguments)
        args = parser(hooks_only=leading.remaining[:1] == ["hook"]).parse_args(arguments)
    if args.command_name == "hook":
        return hook_main(args)
    try:
        project = Project(project_root(args.project), args.slot, args.session,
                          require_slot=args.command_name != "brief")
        if args.slot is None and not project.slot_registered and os.environ.get("RO_SLOT"):
            project = Project(project.root, os.environ["RO_SLOT"], project.explicit_session)
        # Even the implicit single-slot default needs a durable link: its next
        # native Stop event must inspect jobs launched by this command.
        if project.explicit_session and args.command_name != "brief":
            project.register_slot()
        import ro_records as records
        name = args.command_name
        if name == "next-id":
            output = records.next_id(project, args.kind)
        elif name == "dupcheck":
            output = records.dupcheck(project, args.terms)
        elif name == "index":
            output = records.discovery_index(project, args.identifier, args.full)
        elif name == "tools":
            output = records.tools_init(project) if args.init else records.tools_listing(project, args.terms)
        elif name == "archive":
            import ro_archive
            if args.kind == "restore":
                output = ro_archive.restore_discovery(project, args.identifier, args.dry_run)
            else:
                archive = ro_archive.archive_discoveries if args.kind == "discoveries" else ro_archive.archive_events
                output = archive(project, args.before, args.dry_run)
        elif name in ("claim", "release"):
            output = getattr(records, name)(project, args.item)
        elif name in ("launch", "monitor", "kill", "jobs"):
            import ro_jobs
            if name == "launch":
                args.bind = [value for group in args.bind for value in group]
                args.error = [value for group in args.error for value in group]
                args.input = [value for group in args.input for value in group]
                output = ro_jobs.launch(project, args)
            elif name == "jobs":
                output = ro_jobs.jobs(project, args.prune)
            else:
                output = getattr(ro_jobs, name)(project, args.job)
        elif name in ("receipt", "external"):
            import ro_evidence
            if name == "external":
                output = ro_evidence.external(project, args)
            elif args.receipt_command == "add":
                output = ro_evidence.receipt_add(project, args.artifact, args.reviewer, args.verdict, args.scope, args.dest or "")
            else:
                output = ro_evidence.receipt_check(project, args.artifact, args.scope, args.dest)
        elif name == "observe":
            output = records.observe(project, args.key, args.value, args.source, args.ttl)
        elif name == "brief":
            from ro_sessions import startup
            selection = startup(project, user=args.user, host=args.host, intent=args.intent,
                                reclaim=args.reclaim, questions_allowed=not args.no_questions)
            output = selection or records.brief(project, args.max_chars)
        elif name == "close":
            output = records.close(project)
        elif name == "check":
            from ro_checks import Call, outcome, pre_checks
            values = project.settings()
            findings = pre_checks(Call("shell", args.dialect, args.shell_command), project.root,
                                  project.read_json("jobs.json", []), values)
            output = "\n".join(outcome(f, values) + " " + f.check + ": " + f.message for f in findings
                               if outcome(f, values) != "off") or "OK"
            print(output)
            return int(any(outcome(f, values) == "block" for f in findings))
        print(output)
        return 0
    except (ValueError, OSError, KeyError) as exc:
        from ro_state import redact
        print("ro: " + redact(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
