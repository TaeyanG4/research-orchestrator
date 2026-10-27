#!/usr/bin/env python3
"""Compare hook-delivery configurations in disposable Codex exec sessions.

Only running this script without --dry-print launches Codex. Every case gets a
fresh CODEX_HOME; only allowlisted model/provider/Windows settings are copied.
Authentication stays in inherited provider environment variables, never files.
Probe directories and raw stdout/stderr are retained for inspection.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.host.scratch import create_scratch, retire_scratch
from scripts.evals.isolation import configured_model_settings
from scripts.evals.proc import no_window_flags
from scripts.evals.run_evals import resolve_codex


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "hooks" / "codex-hooks.sample.json"
CASES = {"A": "project JSON", "B": "home JSON", "C": "home TOML",
         "D": "project raw payload", "E": "project real command chain"}
PROJECT_CASES = {"A", "D", "E"}
TIMEOUT = 120
PROMPT = (
    "Use the PowerShell shell tool exactly once to run this harmless foreground command: "
    "Write-Output probe\n"
    "Then report the tool result and stop. Do not inspect files, run other commands, "
    "retry, change configuration, or write any files yourself."
)
# The hook imports only the standard library, not any project code. The declared
# event is explicit because SessionStart has no tool_name in its input.
HOOK_CODE = (
    "import json,sys; p=json.loads(sys.stdin.read() or '{}'); "
    "f=open(sys.argv[1],'a',encoding='utf-8'); "
    "f.write(sys.argv[2]+'\\t'+str(p.get('tool_name',''))+'\\n'); f.close()"
)
# Keep the original input, including whitespace and unknown keys. Each call gets
# an immutable archive; the top-level file is the most recent call for the event.
# Only allowlisted environment *names* are captured, never their values.
PAYLOAD_HOOK_CODE = """
import json, os, pathlib, sys, uuid
root, event = pathlib.Path(sys.argv[1]), sys.argv[2]
raw = getattr(sys.stdin, 'buffer', sys.stdin).read()
if isinstance(raw, bytes):
    raw = raw.decode('utf-8', errors='surrogateescape')
names = ('CODEX_HOME', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CODEX_SANDBOX',
         'CODEX_PROJECT_DIR', 'CLAUDE_PROJECT_DIR', 'RO_HOOK_DIAGNOSTICS',
         'PATH', 'HOME', 'USERPROFILE', 'SHELL', 'COMSPEC', 'TMP', 'TEMP', 'TMPDIR')
record = {'event': event, 'raw_stdin': raw,
          'environment_names': [name for name in names if name in os.environ]}
try:
    record['payload'] = json.loads(raw)
except (ValueError, TypeError):
    record['payload'] = None
text = json.dumps(record, indent=2) + '\\n'
archive = root / 'payloads' / uuid.uuid4().hex
archive.mkdir(parents=True)
name = 'payload-' + event + '.json'
(archive / name).write_text(text, encoding='utf-8')
(root / name).write_text(text, encoding='utf-8')
payload = record['payload']
tool = payload.get('tool_name', '') if isinstance(payload, dict) else ''
with (root / 'delivered.log').open('a', encoding='utf-8') as log:
    log.write(event + '\\t' + str(tool) + '\\n')
"""


def hooks(project: Path, *, capture_payload: bool = False) -> dict:
    result = {}
    for event in ("SessionStart", "PreToolUse"):
        code = PAYLOAD_HOOK_CODE if capture_payload else HOOK_CODE
        output = project if capture_payload else project / "delivered.log"
        argv = [sys.executable, "-I", "-S", "-c", code, str(output), event]
        windows = "& " + " ".join("'" + part.replace("'", "''") + "'" for part in argv)
        result[event] = [{"matcher": "*", "hooks": [{
            "type": "command", "command": shlex.join(argv),
            "commandWindows": windows, "timeout": 10,
        }]}]
    return result


def wrap_chain(command: str, project: Path, event: str, *, windows: bool) -> str:
    """Wrap the sample at shell-command level, without another Python launcher.

    Output goes to chain.log, not the host's hook-response parser. Windows must
    explicitly forward the host process's redirected stdin through PowerShell's
    native-command pipeline. Native exit status survives the logging pipeline.
    """
    log = str(project / "chain.log")
    if windows:
        quoted_log = "'" + log.replace("'", "''") + "'"
        return (
            "& { [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false); "
            "$OutputEncoding = [Console]::InputEncoding; "
            "$roHookPayload = [Console]::In.ReadToEnd(); "
            "$ErrorActionPreference = 'Continue'; $script:roHookExit = 1; "
            "& { " + f"'event={event}'; "
            "$global:LASTEXITCODE = 1; try { $roHookPayload | " + command + "; "
            "$script:roHookExit = $LASTEXITCODE } catch { $_ }; "
            "'exit_code=' + $script:roHookExit "
            "} 2>&1 | Out-File -FilePath " + quoted_log + " -Append -Encoding utf8; "
            "exit $script:roHookExit }"
        )
    return (
        "{ printf '%s\\n' " + shlex.quote(f"event={event}") + "; " + command + "; "
        "ro_hook_exit=$?; printf '\\nexit_code=%s\\n' \"$ro_hook_exit\"; "
        "exit \"$ro_hook_exit\"; } >> " + shlex.quote(log) + " 2>&1"
    )


def sample_hooks(project: Path) -> dict:
    """Use the shipped sample's actual matchers, flags, and launcher commands."""
    declarations = json.loads(SAMPLE.read_text(encoding="utf-8"))["hooks"]
    for event, entries in declarations.items():
        for entry in entries:
            for hook in entry["hooks"]:
                for key, windows in (("command", False), ("commandWindows", True)):
                    sample_command = hook[key].replace("/absolute/path/to/plugin", ROOT.as_posix())
                    hook[key] = wrap_chain(sample_command, project, event, windows=windows)
    return declarations


def settings_toml(settings: dict, prefix: tuple[str, ...] = ()) -> str:
    """Serialize the scalar/table-only allowlist from isolation.py."""
    lines = [f"{json.dumps(key)} = {json.dumps(value)}"
             for key, value in settings.items() if not isinstance(value, dict)]
    for key, value in settings.items():
        if isinstance(value, dict):
            path = (*prefix, key)
            lines += ["[" + ".".join(json.dumps(part) for part in path) + "]",
                      settings_toml(value, path)]
    return "\n".join(lines) + "\n"


def hook_files(case: str, project: Path, settings: dict) -> dict[Path, str]:
    home = project / "codex-home"
    declarations = sample_hooks(project) if case == "E" else hooks(project, capture_payload=case == "D")
    config = settings_toml(settings)
    if case == "C":
        for event, entries in declarations.items():
            config += f'\n[[hooks.{event}]]\nmatcher = "*"\n[[hooks.{event}.hooks]]\n'
            config += settings_toml(entries[0]["hooks"][0])
    files = {home / "config.toml": config}
    if case != "C":
        location = project / ".codex" if case in PROJECT_CASES else home
        files[location / "hooks.json"] = json.dumps({"hooks": declarations}, indent=2) + "\n"
        if case in PROJECT_CASES:
            files[location / "config.toml"] = ""
    if case == "E":
        files[project / ".ro" / "hook-diagnostics.on"] = ""
    return files


def command(case: str, project: Path, executable: str, model: str) -> list[str]:
    argv = [executable, "exec", "--json", "--skip-git-repo-check", "--ephemeral",
            "-C", str(project), "-s", "workspace-write" if case in PROJECT_CASES else "danger-full-access",
            "--dangerously-bypass-hook-trust", "-c", "features.hooks=true",
            "-c", 'approval_policy="never"', "--model", model]
    if case in PROJECT_CASES:
        argv += ["-c", f'projects.{json.dumps(str(project))}.trust_level="trusted"']
    return [*argv, PROMPT]


def environment(project: Path, settings: dict) -> dict[str, str]:
    keep = {"CODEX_API_KEY"} | {
        provider["env_key"] for provider in settings.get("model_providers", {}).values()
        if isinstance(provider.get("env_key"), str)
    }
    env = {key: value for key, value in os.environ.items()
           if not (key.startswith("CODEX_") and key not in keep)
           and key not in {"PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME"}}
    env.update(CODEX_HOME=str(project / "codex-home"), PYTHONIOENCODING="utf-8",
               PYTHONDONTWRITEBYTECODE="1")
    env.update({key: str(project / ".tmp") for key in ("TMP", "TEMP", "TMPDIR")})
    return env


def decoded(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def prepare_case(case: str, project: Path, settings: dict) -> dict[Path, str]:
    project.mkdir()
    # Bound project discovery so the source checkout's .codex cannot leak in.
    (project / ".git").mkdir()
    (project / ".tmp").mkdir()
    (project / ".ro" / "sessions").mkdir(parents=True)
    (project / "payloads").mkdir()
    files = hook_files(case, project, settings)
    for path, contents in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return files


def run_case(case: str, project: Path, executable: str, model: str, settings: dict) -> dict:
    files = hook_files(case, project, settings) if project.exists() else prepare_case(case, project, settings)
    argv = command(case, project, executable, model)
    try:
        process = subprocess.run(argv, cwd=project, env=environment(project, settings),
                                 stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 timeout=TIMEOUT, check=False, creationflags=no_window_flags())
        code, stdout, stderr = process.returncode, process.stdout, process.stderr
        status = "completed" if code == 0 else "failed"
    except subprocess.TimeoutExpired as error:
        code, status = None, "timeout"
        stdout, stderr = decoded(error.stdout), decoded(error.stderr)
    except OSError as error:
        code, status, stdout, stderr = None, "launch-error", "", str(error)
    (project / "stdout.log").write_text(stdout, encoding="utf-8")
    (project / "stderr.log").write_text(stderr, encoding="utf-8")
    log = project / "delivered.log"
    chain = project / "chain.log"
    diagnostics = project / ".ro" / "hook-diagnostics.jsonl"
    return {"case": case, "status": status, "exit_code": code, "argv": argv,
            "cwd": str(project), "CODEX_HOME": str(project / "codex-home"),
            "config_files": [str(path) for path in files],
            "delivered_exists": log.is_file(),
            "delivered_lines": log.read_text(encoding="utf-8", errors="replace").splitlines()
            if log.is_file() else [],
            "payload_files": [str(path) for path in sorted(project.glob("payload-*.json"))],
            "payload_archive_files": [str(path) for path in sorted(project.glob("payloads/*/payload-*.json"))],
            "chain_log": str(chain), "chain_exists": chain.is_file(),
            "diagnostics_log": str(diagnostics), "diagnostics_exists": diagnostics.is_file(),
            "stderr_head": [line for line in stderr.splitlines() if line.strip()][:8]}


def table(results: list[dict]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("&", "&amp;").replace("|", "&#124;").replace("<", "&lt;")

    lines = ["| Case | Status | Exit code | delivered.log exists | Log lines | First stderr lines | Artifacts |",
             "|---|---|---|---|---|---|---|"]
    for result in results:
        values = [f"{result['case']}: {CASES[result['case']]}", result["status"],
                  result["exit_code"] if result["exit_code"] is not None else "n/a",
                  str(result["delivered_exists"]).lower(),
                  json.dumps(result["delivered_lines"]), json.dumps(result["stderr_head"]),
                  f"payload calls={len(result['payload_archive_files'])}; "
                  f"chain.log={result['chain_exists']}; diagnostics={result['diagnostics_exists']}"]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", "--temp-parent", dest="root", type=Path, default=ROOT / "_hook-probe")
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--executable", default="codex", help="Native Codex executable or npm shim to resolve")
    parser.add_argument("--output", type=Path, help="Override the dated Markdown report path")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=["A", "B", "C"],
                        help="Cases to run in order (default: A B C; capture/debug: D E)")
    parser.add_argument("--dry-print", action="store_true", help="Print plans only; no subprocesses or file writes")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.dry_print:
        for case in args.cases:
            project = root / "<fresh-run>" / case
            print(json.dumps({"case": case, "cwd": str(project),
                              "CODEX_HOME": str(project / "codex-home"),
                              "argv": command(case, project, args.executable, args.model),
                              "config_files": [str(path) for path in hook_files(case, project, {})],
                              "timeout": TIMEOUT, "stdin": "DEVNULL"}))
        return 0
    try:
        settings = configured_model_settings()  # Reads config.toml only; no auth.json.
        executable = resolve_codex(args.executable)
        root.mkdir(parents=True, exist_ok=True)
        base = create_scratch(root, "delivery-")
        try:
            for case in dict.fromkeys(args.cases):
                prepare_case(case, base / case, settings)
            results = [run_case(case, base / case, executable, args.model, settings) for case in dict.fromkeys(args.cases)]
        finally:
            retained = retire_scratch(base)
        for result in results:
            result["retained_directory"] = str(retained / result["case"])
        summary = table(results)
        print(summary)
        now = datetime.now(timezone.utc)
        output = args.output or ROOT / "docs" / "host-dry-runs" / f"codex-delivery-probe-{now.date()}.md"
        report = (
            f"# Codex exec hook delivery probe\n\nUTC: {now.isoformat()}\n\n"
            f"Target: codex-cli 0.154.0 (version not queried). Model: {args.model}\n\n"
            "All cases use fresh CODEX_HOME directories and inherited environment authentication. "
            "No credential files or real-home sandbox state are copied. "
            "A/D/E use workspace-write and may fail if their fresh Windows homes need sandbox setup; "
            "B/C use danger-full-access. Hook trust bypass and features.hooks=true apply to all cases.\n\n"
            "A-D record delivered.log. D also retains complete raw stdin in payload-<event>.json "
            "and an immutable payloads/<call>/ archive, with allowlisted environment names only. "
            "E wraps the shipped sample command chain, logging event, stdout, stderr and exit status "
            "to chain.log, and enables .ro/hook-diagnostics.on. E consumes hook output into its log; "
            "it diagnoses delivery/launcher execution, not host enforcement of hook responses. "
            "Missing hook evidence is inconclusive if startup, "
            "authentication, sandbox setup, the model tool call, or the hook command failed. "
            "Raw stdout.log/stderr.log and configs remain in each probe directory.\n\n"
            + summary + "\n\n"
        )
        for result in results:
            body = json.dumps(result, indent=2, ensure_ascii=False)
            # Use an indented block so arbitrary stderr cannot close a code fence.
            report += f"## {result['case']}: {CASES[result['case']]}\n\n"
            report += "\n".join("    " + line for line in body.splitlines()) + "\n\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"\nReport: {output}\nProbe directories: {retained}")
        return int(any(result["status"] != "completed" for result in results))
    except (OSError, ValueError) as error:
        print(f"Probe setup/report error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
