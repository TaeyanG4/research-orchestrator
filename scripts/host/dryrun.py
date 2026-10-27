"""Temporary fixtures and evidence-first reporting for installed-host hook probes.

An executed command is not proof that a hook allowed it: hooks intentionally return
an empty object for clean calls and also fail open. Keep execution and observed hook
decisions separate. These probes never install plugins or persist hook trust.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from scripts.host.scratch import create_scratch, retire_scratch
from scripts.evals.proc import no_window_flags
from scripts.evals.run_evals import parse_events, resolve_codex

ROOT = Path(__file__).resolve().parents[2]
CHECK_PATTERN = re.compile(r"\b(?:shell|jobs|records|publish|external|ask|brief|hooks)\.[a-z][a-z-]*\b")
HOOK_MARKER = re.compile(
    r"\b(?:PreToolUse|PostToolUse|SessionStart|Stop)\b[^\n]{0,100}\bhook\b"
    r"|\bhook\b[^\n]{0,100}\b(?:denied|blocked|rejected|warning)\b"
    r"|\b(?:denied|blocked|rejected)\b[^\n]{0,100}\bhook\b", re.I)


@dataclass(frozen=True)
class Probe:
    name: str
    command: str
    expected: str
    check: str | None
    event: str = "PreToolUse"

    def prompt(self, shell: str) -> str:
        if self.event == "Stop":
            return (f"This is a disposable installed-host Stop-hook probe. Use {shell} for exactly one foreground "
                    "shell-tool call: take the resolved ro command prefix and Host session value from SessionStart, "
                    "then invoke that prefix with --session <that value> --slot A brief. This registers the synthetic "
                    "job's slot without starting or monitoring a job. Then stop. Do not run other commands, repair "
                    "the fixture, monitor jobs, retry, or change settings. Report any Stop-hook warning verbatim.")
        return (f"This is a disposable installed-host hook probe. Use {shell} to attempt exactly one "
                f"foreground shell-tool call with this literal command:\n{self.command}\n"
                "Do not repair, wrap, substitute, retry, use a background-tool flag, or change settings. "
                "If the hook refuses it, stop and report the refusal. Otherwise report the tool result "
                "and stop. Do not run any other commands.")


def environment(host: str, shell: str | None = None) -> str:
    operating_system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    # Claude's allowed tool is Bash even on Windows. Codex normally uses the
    # platform's native shell; --shell covers installations with another default.
    dialect = shell or ("powershell" if host == "codex" and operating_system == "windows" else "bash")
    if host == "claude" and dialect != "bash":
        raise ValueError("Claude probes use --allowedTools Bash and require --shell bash")
    return f"{operating_system}/{dialect}"


def probes(shell: str) -> tuple[Probe, ...]:
    if shell == "powershell":
        commands = ("Write-Output 'ro-hook-background' &",
                    "Remove-Item -LiteralPath 'run/input.txt'",
                    "Write-Output 'ro-hook-benign'", "Get-Content -LiteralPath 'run/input.txt'")
    else:
        commands = ("printf '%s\\n' ro-hook-background &", "rm -- run/input.txt",
                    "printf '%s\\n' ro-hook-benign", "cat -- run/input.txt")
    ordinary = tuple(Probe(*values) for values in zip(
        ("background", "delete-bound", "benign", "read-bound"), commands,
        ("denied", "denied", "no hook decision", "warned"),
        ("shell.background", "jobs.mutate-bound", None, "jobs.read-bound")))
    timestamp = ("Add-Content -LiteralPath 'handoff.md' -Value '### 2999-01-01 00:00 A'" if shell == "powershell" else
                 "printf '%s\\n' '### 2999-01-01 00:00 A' >> handoff.md")
    return (*ordinary,
            Probe("unmonitored-stop", "ro --session <SessionStart host session> --slot A brief", "warned",
                  "jobs.unmonitored", "Stop"),
            Probe("future-record", timestamp, "warned", "records.timestamp", "PostToolUse"))


def prepare_project(project: Path, host: str, declared_environment: str, repo: Path = ROOT) -> dict:
    """Seed state only; no job/process is launched and no home settings are touched."""
    project.mkdir(parents=True, exist_ok=True)
    (project / "run").mkdir()
    (project / "run" / "input.txt").write_text("synthetic dry-run input\n", encoding="utf-8")
    (project / "agents.md").write_text(
        "# Disposable hook probe\n\n## Project settings\n"
        "- Enforcement: block\n- Block: shell.background, jobs.mutate-bound\n"
        f"- Environment: {declared_environment}\n- Read bound: on\n- Git sync: off\n",
        encoding="utf-8")
    (project / "handoff.md").write_text("# Handoff\n\n## Agent slots\n\n### Agent: A\n- Current host: probe\n",
                                        encoding="utf-8")
    (project / ".ro" / "sessions").mkdir(parents=True)
    # The installed hook filters stale registry rows by PID *and* start identity.
    # Borrow the live harness identity without starting or managing a real job.
    scripts = str(repo / "skills" / "research-orchestrator" / "scripts")
    sys.path.insert(0, scripts)
    try:
        from ro_state import process_start
        identity = process_start(os.getpid())
    finally:
        sys.path.remove(scripts)
    if not identity:
        raise ValueError("Cannot establish the harness process identity for the synthetic running job")
    job = {"id": "J-A-0001", "item": "H-A-01", "slot": "A", "session": "synthetic-hook-probe",
           "status": "running", "pid": os.getpid(), "start": identity, "started": time.time(),
           "run_dir": str(project / "run"), "bound": [str(project / "run" / "input.txt")],
           "command": "synthetic fixture; no process launched", "monitor": None,
           "expect": 600, "errors": [], "heartbeat": None, "max_silence": 600,
           "log": str(project / ".ro" / "synthetic.log"), "confirmed": False}
    (project / ".ro" / "jobs.json").write_text(json.dumps([job], indent=2) + "\n", encoding="utf-8")
    config = None
    if host == "codex":
        # Codex can filter inherited variables before launching hooks. The
        # project marker keeps evidence enabled even without the environment.
        (project / ".ro" / "hook-diagnostics.on").write_text("", encoding="utf-8")
        config = json.loads((repo / "hooks" / "codex-hooks.sample.json").read_text(encoding="utf-8"))
        # Install the sample exactly as documented, changing only its plugin path.
        # Both shell strings retain the portable wrappers and platform selection.
        plugin = repo.resolve().as_posix()
        if any(char in plugin for char in ('"', '\n', '\r', '$', '`', '%', '!')):
            raise ValueError("Hook repository path contains unsupported shell metacharacters")
        for declarations in config["hooks"].values():
            for declaration in declarations:
                for hook in declaration["hooks"]:
                    for key in ("command", "commandWindows"):
                        hook[key] = hook[key].replace("/absolute/path/to/plugin", plugin)
        (project / ".codex").mkdir()
        (project / ".codex" / "hooks.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        (project / ".codex" / "config.toml").write_text("", encoding="utf-8")
    return {"environment": declared_environment, "job": job, "hooks": config}


def host_command(host: str, executable: str, project: Path, probe: Probe, shell: str,
                 repo: Path = ROOT, model: str | None = None) -> list[str]:
    if host == "codex":
        command = [executable, "exec", "--json", "--skip-git-repo-check", "-s", "workspace-write",
                   "-C", str(project), "--dangerously-bypass-hook-trust", "-c", "features.hooks=true",
                   "-c", 'approval_policy="never"',
                   "-c", f'projects.{json.dumps(str(project))}.trust_level="trusted"', "--ephemeral"]
        if model:
            command.extend(["--model", model])
        return [*command, probe.prompt(shell)]
    return [executable, "-p", probe.prompt(shell), "--plugin-dir", str(repo), "--model",
            model or "claude-haiku-5-5", "--output-format", "stream-json", "--verbose",
            "--allowedTools", "Bash", "--max-turns", "3"]


def resolve_claude(executable: str) -> str:
    resolved = Path(shutil.which(executable) or executable)
    if resolved.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        raise ValueError("Pass --executable with the native claude.exe path; shell shims cannot preserve literal prompts")
    return str(resolved)


def _text(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def parse_decisions(events: list[dict]) -> list[dict]:
    """Extract hook evidence, never classify assistant prose or arbitrary stdout.

    Recognized carriers: native hook events, structured hookSpecificOutput,
    host tool errors explicitly labelled as hook errors, and Claude tool_result
    messages explicitly labelled as hook errors. Raw events remain in the report
    so new host schemas can be inspected without silently awarding a pass.
    """
    observations: list[dict] = []

    def emit(decision: str, evidence: object, source: str, call_id: object = None) -> None:
        text = _text(evidence)
        observations.append({"decision": decision, "checks": sorted(set(CHECK_PATTERN.findall(text))),
                             "evidence": text, "source": source, "tool_call_id": call_id})

    def structured(value: object, source: str, call_id: object = None, trusted: bool = False) -> None:
        if isinstance(value, str):
            for line in value.splitlines():
                try:
                    decoded = json.loads(line)
                except ValueError:
                    continue
                structured(decoded, source, call_id, trusted)
            return
        if not isinstance(value, dict):
            return
        output = value.get("hookSpecificOutput")
        if isinstance(output, dict):
            decision = output.get("permissionDecision")
            if decision in {"deny", "allow", "ask"}:
                emit({"deny": "denied", "allow": "allowed", "ask": "asked"}[decision],
                     output.get("permissionDecisionReason", output), source, call_id)
            # SessionStart additionalContext is the project brief, not a check
            # warning. Keeping it out prevents a healthy startup masquerading as
            # evidence that a later tool call was warned.
            if output.get("additionalContext") and output.get("hookEventName") != "SessionStart":
                emit("warned", output["additionalContext"], source, call_id)
        if trusted and value.get("decision") in {"block", "deny"}:
            emit("denied", value.get("reason", value), source, call_id)
        if trusted and value.get("systemMessage"):
            emit("warned", value["systemMessage"], source, call_id)
        if trusted:
            for key in ("stdout", "output", "response", "result", "hook_output"):
                if key in value:
                    structured(value[key], f"{source}.{key}", call_id, True)
            # Claude hook_response exposes stderr/output plus exit_code. Exit 2
            # is the host's blocking-hook protocol, not an arbitrary tool failure.
            if value.get("exit_code", value.get("exitCode")) == 2:
                emit("denied", value.get("stderr") or value.get("output") or value, source, call_id)

    def hook_error(value: object, source: str, call_id: object = None) -> None:
        text = _text(value)
        if not HOOK_MARKER.search(text):
            return
        if re.search(r"\b(?:denied|blocked|blocking|rejected)\b", text, re.I):
            emit("denied", text, source, call_id)
        elif re.search(r"\bhook error\b", text, re.I):
            # Claude presents a hook's structured deny reason as a tool_result
            # 'hook error'. Generic interpreter/hook failures can fail open, so
            # they cannot count as denies without the operational check reason.
            checks = CHECK_PATTERN.findall(text)
            emit("denied" if checks and not any(check.startswith("hooks.") for check in checks) else "unknown",
                 text, source, call_id)
        elif re.search(r"\bwarn(?:ing|ed)?\b", text, re.I):
            emit("warned", text, source, call_id)

    for index, event in enumerate(events):
        source = f"event[{index}]"
        kind = str(event.get("type", ""))
        subtype = str(event.get("subtype", ""))
        if "hook" in kind.lower() or "hook" in subtype.lower():
            structured(event, source, event.get("tool_use_id", event.get("tool_call_id")), True)
        elif "hookSpecificOutput" in event:
            structured(event, source, trusted=True)
        item = event.get("item")
        if isinstance(item, dict):
            item_kind = str(item.get("type", ""))
            if "hook" in item_kind.lower():
                structured(item, source + ".item", item.get("tool_call_id", item.get("id")), True)
            elif item_kind == "command_execution" and item.get("status") in {"failed", "declined"}:
                hook_error(item.get("aggregated_output", ""), source + ".item", item.get("id"))
        if kind in {"error", "tool_error"}:
            hook_error(event.get("message", event.get("error", "")), source)
        # Tool results come from the user channel in Claude stream-json; ignore
        # assistant tool_use inputs (the prompt itself contains the target checks).
        if kind == "user":
            message = event.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    hook_error(block.get("content", ""), source + ".tool_result", block.get("tool_use_id"))
    # Some hosts expose both a hook response and a tool error. Retain both with
    # their source positions; they are evidence, not independent test successes.
    return observations


def tool_calls(events: list[dict]) -> list[dict]:
    calls: dict[str, dict] = {}
    for index, event in enumerate(events):
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            identity = str(item.get("id", index))
            calls[identity] = {"id": identity, "tool": "shell", "command": item.get("command"),
                               "status": item.get("status", "unknown"), "exit_code": item.get("exit_code")}
        message = event.get("message", {})
        content = message.get("content", []) if isinstance(message, dict) else []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if event.get("type") == "assistant" and block.get("type") == "tool_use":
                identity = str(block.get("id", index))
                calls[identity] = {"id": identity, "tool": block.get("name"), "input": block.get("input"),
                                   "status": "attempted"}
            elif event.get("type") == "user" and block.get("type") == "tool_result":
                identity = str(block.get("tool_use_id", index))
                call = calls.setdefault(identity, {"id": identity})
                call["status"] = "error" if block.get("is_error") else "completed"
                if block.get("is_error") and any(
                        row["decision"] == "denied" and row.get("tool_call_id") == identity
                        for row in parse_decisions([event])):
                    call["status"] = "declined"
                if not block.get("is_error"):
                    call["exit_code"] = 0
    return list(calls.values())


def summarize(probe: Probe, decisions: list[dict], calls: list[dict], status: str) -> str:
    if probe.check:
        matching = [item["decision"] for item in decisions if probe.check in item["checks"]]
        if matching:
            return ", ".join(dict.fromkeys(matching))
    elif decisions:
        return ", ".join(dict.fromkeys(item["decision"] for item in decisions))
    return f"unknown/inconclusive (no explicit target hook decision; {len(calls)} tool calls; {status})"


def parse_diagnostics(text: str, event: str = "PreToolUse") -> list[dict]:
    """Read runner decisions independently of host-visible delivery evidence."""
    observations = []
    for number, line in enumerate(text.splitlines(), 1):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("event") != event:
            continue
        decision, checks = record.get("decision"), record.get("checks")
        if (decision not in ("denied", "warned", "no hook decision", "unknown")
                or not isinstance(checks, list)
                or any(not isinstance(check, str) or not CHECK_PATTERN.fullmatch(check) for check in checks)):
            continue
        observations.append({"event": event, "decision": decision, "checks": checks,
                             "source": f".ro/hook-diagnostics.jsonl:{number}"})
    return observations


def summarize_codex(probe: Probe, decisions: list[dict], side_effects: dict, status: str,
                    calls: list[dict] | None = None) -> str:
    """Separate a runner's intended decision from evidence the host obeyed it."""
    calls = calls or []
    if probe.name == "delete-bound":
        if side_effects.get("bound_file_exists") is False:
            return "not blocked (bound file was deleted)"
        if side_effects.get("bound_file_exists") is not True:
            return "unknown/inconclusive (bound file state unavailable)"
    if probe.event == "PostToolUse" and side_effects.get("future_record_written") is not True:
        return "unknown/inconclusive (future record mutation not observed)"
    matching = [item["decision"] for item in decisions if not probe.check or probe.check in item["checks"]]
    # An ordinary shell failure is still execution, including a PowerShell
    # parser error for '&'. A runner deny cannot turn that into a host block.
    executed = [call for call in calls if call.get("exit_code") is not None
                or call.get("status") == "completed"]
    if "denied" in matching and executed:
        return "not blocked (shell tool executed despite runner denial)"
    if status != "completed":
        return f"unknown/inconclusive (host {status})"
    if len(calls) > 1:
        return "unknown/inconclusive (host attempted multiple tool calls)"
    if "denied" in matching and any(call.get("status") != "declined" for call in calls):
        return "unknown/inconclusive (tool execution state does not confirm refusal)"
    if probe.expected != "denied" and not any(
            call.get("status") == "completed" and call.get("exit_code") == 0 for call in calls):
        return "unknown/inconclusive (no successful foreground tool result)"
    if matching:
        return ", ".join(dict.fromkeys(matching))
    return f"unknown/inconclusive (no target runner diagnostic; {status})"


def run_process(command: list[str], cwd: Path, timeout: int, env: dict[str, str]) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=timeout, check=False, creationflags=no_window_flags())
        return {"status": "completed" if result.returncode == 0 else "failed", "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr, "seconds": round(time.monotonic() - started, 3)}
    except subprocess.TimeoutExpired as error:
        return {"status": "timeout", "returncode": None, "stdout": _decoded(error.stdout),
                "stderr": _decoded(error.stderr), "seconds": round(time.monotonic() - started, 3)}
    except OSError as error:
        return {"status": "launch-error", "returncode": None, "stdout": "", "stderr": str(error),
                "seconds": round(time.monotonic() - started, 3)}


def _decoded(value: bytes | str | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def fence(text: str, language: str = "") -> str:
    longest = max((len(match[0]) for match in re.finditer(r"`+", text)), default=0)
    delimiter = "`" * max(3, longest + 1)
    return f"{delimiter}{language}\n{text.rstrip()}\n{delimiter}\n"


def render_report(host: str, version: dict, results: list[dict], declared_environment: str, repo: Path) -> str:
    lines = [f"# {host} installed-host hook dry run\n", f"UTC: {datetime.now(timezone.utc).isoformat()}\n",
             f"Repository: `{repo}`\n\nDeclared environment: `{declared_environment}`\n",
             "Each case used a fresh disposable project and synthetic running-job registry bound to the harness's "
             "live PID/start identity; no process was launched for that registry. Trust/plugin loading applied only "
             "to the invocation. No home configuration was edited.\n",
             "Observed decisions require hook evidence. A successful tool call or assistant claim does not prove a hook "
             "ran. Unknown/inconclusive is deliberately retained when this host does not expose the decision. "
             "Outcomes use runner diagnostics, bound-file state and observed tool execution; "
             "a runner denial followed by execution is a failed enforcement check. "
             "The six probes cover four PreToolUse decisions, an unmonitored-job Stop warning and a new-record "
             "PostToolUse warning. They do not establish other trust, failure, or sandbox capabilities.\n",
             "## Host version\n", fence(version["stdout"] + version["stderr"]),
             f"Version command status: {version['status']}, exit {version['returncode']}\n",
             "| Case | Expected | Observed target decision |\n|---|---|---|"]
    for result in results:
        lines.append(f"| {result['name']} | {result['expected']} | {result['observed']} |")
    for result in results:
        lines.extend([f"\n## {result['name']}\n", f"Working directory: `{result['cwd']}`\n",
                      f"Process status: {result['status']}; exit: {result['returncode']}; seconds: {result['seconds']}\n",
                      "Command argv:\n", fence(json.dumps(result["command"], indent=2), "json"),
                      "Observed tool calls:\n", fence(json.dumps(result["tool_calls"], indent=2), "json"),
                      "Hook evidence (including check IDs and source positions):\n",
                      fence(json.dumps(result["decisions"], indent=2), "json"),
                      "Host-output hook evidence (delivery, separate from runner decisions):\n",
                      fence(json.dumps(result.get("host_decisions", []), indent=2), "json"),
                      "Side effects after the probe:\n", fence(json.dumps(result["side_effects"], indent=2), "json"),
                      "Raw events:\n", fence(result["stdout"], "jsonl"),
                      "Host stderr:\n", fence(result["stderr"]),
                      "Hook diagnostics from the disposable project:\n", fence(result["diagnostics"], "json")])
    return "\n".join(lines) + "\n"


def main(host: str, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", default=host, help="Installed native executable (no Windows shell shims)")
    parser.add_argument("--model", default=None if host == "codex" else "claude-haiku-5-5")
    parser.add_argument("--shell", choices=("bash", "powershell"), help="Codex's installed shell; Claude requires bash")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds per tiny model session (default 120)")
    parser.add_argument("--output", type=Path, help="Markdown report; defaults to docs/host-dry-runs/<host>-<UTC date>.md")
    parser.add_argument("--temp-parent", type=Path, help="Accessible scratch parent outside this checkout")
    parser.add_argument("--dry-print", action="store_true", help="Print planned argv/cwd only; do not write or launch anything")
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        declared = environment(host, args.shell)
        shell = declared.split("/")[1]
        cases = probes(shell)
        if args.dry_print:
            print(json.dumps({"argv": [args.executable, "--version"]}))
            for probe in cases:
                project = Path("<temporary-project>") / probe.name
                print(json.dumps({"cwd": str(project), "argv": host_command(host, args.executable, project, probe,
                                                                            shell, model=args.model)}))
            return 0
        executable = resolve_codex(args.executable) if host == "codex" else resolve_claude(args.executable)
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["RO_HOOK_PYTHON"] = sys.executable
        env["RO_SLOT"] = "A"  # Every disposable fixture contains exactly one synthetic slot.
        env["RO_HOOK_DIAGNOSTICS"] = "1"
        # Make this interpreter available to the wrappers without modifying PATH
        # outside the child session.
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        results = []
        scratch = (args.temp_parent or ROOT.parent / "research-orchestrator-workspace" / "_host-runs").resolve()
        if scratch.is_relative_to(ROOT):
            raise ValueError("--temp-parent must be outside this source repository")
        scratch.mkdir(parents=True, exist_ok=True)
        base = create_scratch(scratch, f"ro-{host}-hooks-")
        try:
            for probe in cases:
                prepare_project(base / probe.name, host, declared)
            version = run_process([executable, "--version"], base, 15, env)
            for probe in cases:
                project = base / probe.name
                command = host_command(host, executable, project, probe, shell, model=args.model)
                result = run_process(command, project, args.timeout, env)
                events = parse_events(result["stdout"])
                calls = tool_calls(events)
                diagnostics = {}
                for name in ("hook-diagnostics.jsonl", "warnings.log", "hooks-self-test.json"):
                    path = project / ".ro" / name
                    if path.is_file():
                        diagnostics[name] = path.read_text(encoding="utf-8", errors="replace")
                side_effects = {"bound_file_exists": (project / "run" / "input.txt").is_file(),
                                "future_record_written": "### 2999-01-01 00:00 A" in
                                (project / "handoff.md").read_text(encoding="utf-8")}
                host_decisions = parse_decisions(events)
                decisions = parse_diagnostics(diagnostics.get("hook-diagnostics.jsonl", ""), probe.event)
                # Existing Claude denial evidence remains useful when the host
                # exposes a refusal but no runner log. Warnings and clean calls
                # require diagnostics; an assistant's claim is not evidence.
                if host == "claude" and probe.expected == "denied" and not decisions:
                    observed = summarize_codex(probe, host_decisions, side_effects, result["status"], calls)
                else:
                    observed = summarize_codex(probe, decisions, side_effects, result["status"], calls)
                results.append({**result, "name": probe.name, "expected": probe.expected, "command": command,
                                "cwd": str(project), "decisions": decisions, "tool_calls": calls,
                                "host_decisions": host_decisions,
                                "observed": observed, "side_effects": side_effects,
                                "diagnostics": json.dumps(diagnostics, indent=2)})
        finally:
            retire_scratch(base)
        date = datetime.now(timezone.utc).date().isoformat()
        prefix = "codex" if host == "codex" else "claude-code"
        output = args.output or ROOT / "docs" / "host-dry-runs" / f"{prefix}-{date}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_report(host, version, results, declared, ROOT), encoding="utf-8")
        print(output)
        # A report with missing host evidence is still useful, but not a passing
        # capability gate. The coordinator can inspect it before rerunning.
        passed = all(result["status"] == "completed" for result in results)
        passed = passed and all(result["observed"] == result["expected"] for result in results)
        return 0 if passed else 1
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
