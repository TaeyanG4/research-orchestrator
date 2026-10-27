#!/usr/bin/env python3
"""Run strict skill-creator case folders with Codex; no third-party dependencies."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import secrets
import time
import threading
from email.utils import parsedate_to_datetime

if __package__:
    from .baseline import BASELINE_DIGEST, content_digest, snapshot_old_skill, validate_old_skill
    from .contamination import audit_run
    from .evidence import EvidenceBroker
    from .proc import no_window_flags
    from .isolation import cleanup, config_arguments, configured_model_settings, prepare_environment, stage_runtime
else:
    from baseline import BASELINE_DIGEST, content_digest, snapshot_old_skill, validate_old_skill
    from contamination import audit_run
    from evidence import EvidenceBroker
    from proc import no_window_flags
    from isolation import cleanup, config_arguments, configured_model_settings, prepare_environment, stage_runtime


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL = ROOT / "skills" / "research-orchestrator"
DEFAULT_WORKSPACE = ROOT.parent / "research-orchestrator-workspace"
PROMPT_HEADER = (
    "---\ntags: [skill-creator]\nmax_turns: 20\ntimeout_seconds: 600\n"
    "allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]\n---\n\n"
)
GRADER_HEADER = "---\ntype: llm\nfocus: trace\nweight: 1\n---\n\n"
SCAFFOLD = '#!/usr/bin/env bash\nset -eu\ncp -R "$(dirname "$0")/files/." .\n'
RESERVED = {"results", "mocks", "node_modules", "files", "true", "false", "null"}


@dataclass(frozen=True)
class Assertion:
    path: Path
    text: str


@dataclass(frozen=True)
class Case:
    path: Path
    name: str
    prompt: str
    expected_outcome: str
    assertions: tuple[Assertion, ...]
    timeout_seconds: int = 600


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_codex(codex: str) -> str:
    """Bypass Windows npm shell shims so prompts are always literal argv values."""
    executable = Path(shutil.which(codex) or codex)
    if executable.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return str(executable)
    architecture = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    package = f"codex-win32-{architecture}"
    packages = executable.parent / "node_modules" / "@openai"
    vendors = [packages / "codex" / "node_modules" / "@openai" / package / "vendor",
               packages / package / "vendor", packages / "codex" / "vendor"]
    for vendor in vendors:
        for pattern in ("*-pc-windows-msvc/bin/codex.exe", "*-pc-windows-msvc/codex/codex.exe"):
            binaries = sorted(vendor.glob(pattern))
            if binaries:
                return str(binaries[0].resolve())
    raise ValueError(f"Cannot resolve native Codex from {executable}; pass --codex <path-to-codex.exe>")


def _plain_tree(path: Path) -> None:
    """Never follow an input/output link outside the isolated project."""
    if path.is_symlink() or path.is_junction():
        raise ValueError(f"Links are not supported in eval trees: {path}")
    for entry in path.rglob("*"):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError(f"Links are not supported in eval trees: {entry}")


def load_case(path: Path) -> Case:
    """Validate the exact, deliberately small YAML templates from schemas.md."""
    name = path.name
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in RESERVED:
        raise ValueError(f"Invalid case name: {name}")
    _plain_tree(path)
    prompt_text = (path / "prompt.md").read_text(encoding="utf-8")
    if not prompt_text.startswith(PROMPT_HEADER):
        raise ValueError(f"{name}: prompt.md must use the exact skill-creator settings block")
    prompt = prompt_text[len(PROMPT_HEADER):].strip()
    if not prompt:
        raise ValueError(f"{name}: prompt is empty")
    lines = (path / "case.yaml").read_text(encoding="utf-8").splitlines()
    if (len(lines) < 4 or lines[0] not in ('schema_version: "1.1"', "schema_version: '1.1'")
            or lines[1:3] != [f"name: {name}", "expected_outcome: |"]):
        raise ValueError(f"{name}: case.yaml must use the schema_version/name/expected_outcome template")
    index = 3
    expected_lines = []
    while index < len(lines) and (lines[index].startswith("  ") or not lines[index]):
        expected_lines.append(lines[index][2:])
        index += 1
    expected = "\n".join(expected_lines).strip()
    if not expected:
        raise ValueError(f"{name}: expected_outcome must not be empty")
    has_inputs = (path / "files").is_dir()
    tail = lines[index:]
    if tail != (["context:", "  scaffold_script: place-files.sh"] if has_inputs else []):
        raise ValueError(f"{name}: unexpected case.yaml fields or missing scaffold context")
    if has_inputs:
        if (path / "place-files.sh").read_text(encoding="utf-8") != SCAFFOLD:
            raise ValueError(f"{name}: place-files.sh must use the skill-creator template")
        if not prompt.splitlines()[-1].startswith("Input files: "):
            raise ValueError(f"{name}: end the prompt with Input files: <relative paths>")
        listed = [item.strip() for item in prompt.splitlines()[-1][len("Input files: "):].split(",")]
        for item in listed:
            rel = PurePosixPath(item)
            if (not item or rel.is_absolute() or ".." in rel.parts or "\\" in item or ":" in item
                    or not (path / "files" / item).exists()):
                raise ValueError(f"{name}: invalid/missing input path {item!r}")
        if (path / "files" / "final.md").exists():
            raise ValueError(f"{name}: final.md is reserved for the executor's final message")
    graders = sorted((path / "graders").glob("*"))
    if not graders:
        raise ValueError(f"{name}: at least one assertion file is required")
    assertions = []
    for grader in graders:
        if not grader.is_file() or not re.fullmatch(r"[0-9]{2}-[a-z0-9-]+\.md", grader.name):
            raise ValueError(f"{name}: invalid grader filename {grader.name}")
        source = grader.read_text(encoding="utf-8")
        if not source.startswith(GRADER_HEADER):
            raise ValueError(f"{name}: {grader.name} must use the llm/trace/1 header")
        assertion = source[len(GRADER_HEADER):].strip()
        if not assertion or "\n\n" in assertion:
            raise ValueError(f"{name}: {grader.name} must contain one assertion paragraph")
        if assertion.startswith("The result matches this description:") or assertion == (
                "The response completes the task the prompt asks for."):
            continue  # A skill-creator placeholder is never graded.
        assertions.append(Assertion(grader, assertion))
    return Case(path.resolve(), name, prompt, expected, tuple(assertions))


def load_cases(skill_dir: Path, names: list[str] | None = None) -> list[Case]:
    directories = sorted(p for p in (skill_dir / "evals").iterdir() if p.is_dir() and p.name not in RESERVED)
    available = {p.name for p in directories}
    if names and set(names) - available:
        raise ValueError(f"Unknown cases: {', '.join(sorted(set(names) - available))}")
    cases = [load_case(path) for path in directories if not names or path.name in names]
    if not cases:
        raise ValueError("No cases selected")
    return cases


def parse_events(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _transport_evidence(raw: str, stderr: str, category: str) -> list[dict]:
    """Recognize service/transport diagnostics, not quoted agent text or tool output."""
    pattern = re.compile(
        r"stream disconnected before completion|upstream websocket closed before response\.completed"
        r"|reconnecting(?:\.{3}|\u2026)\s*(\d+)\s*/\s*(\d+)"
        r"|\bunexpected status (?:502|504)\b",
        re.IGNORECASE) if category == "transport" else re.compile(
        r"\b(?:429|503)\b|\bmodel (?:is )?at capacity\b|\btoo many requests\b|\b(?:rate[\s_-]*limit(?:ed|ing|s)?|usage[\s_-]+limits?)"
        r"(?:[\s_-]*(?:exceeded|reached))?\b", re.IGNORECASE)
    evidence = []

    def record(message: object, source: str) -> None:
        if not isinstance(message, str):
            return
        for match in pattern.finditer(message):
            # A reconnect still in progress is not an exhausted transport failure.
            if category == "transport" and match[1] is not None and not (int(match[1]) == int(match[2]) > 0):
                continue
            evidence.append({"source": source, "message": message})
            break

    def diagnostic(event: object, source: str) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") in {"error", "warning", "turn.failed"}:
            before = len(evidence)
            record(event.get("message"), source)
            error = event.get("error")
            record(error.get("message") if isinstance(error, dict) else error, source)
            if category == "rate_limit" and len(evidence) > before:
                # Preserve structured retry hints alongside the diagnostic.
                hints = [retry_after_seconds(value) for value in (event, error)]
                hint = max((value for value in hints if value is not None), default=None)
                if hint is not None:
                    for entry in evidence[before:]:
                        entry["retry_after_seconds"] = hint
        elif event.get("type") in {"item.started", "item.updated", "item.completed"}:
            diagnostic(event.get("item"), source)

    for number, line in enumerate(raw.splitlines(), 1):
        try:
            event = json.loads(line)
        except ValueError:
            record(line, f"events.jsonl:{number}")
        else:
            diagnostic(event, f"events.jsonl:{number}")
    for number, line in enumerate(stderr.splitlines(), 1):
        record(line, f"stderr.txt:{number}")
    if category == "rate_limit" and evidence:
        # Header-style hints may be on their own stderr line. Never scan agent
        # messages or command output for scheduling instructions.
        hint = max((retry_after_seconds(line) or 0 for line in stderr.splitlines()), default=0)
        if hint:
            for entry in evidence:
                entry["retry_after_seconds"] = max(entry.get("retry_after_seconds", 0), hint)
    return evidence


def disconnect_evidence(raw: str, stderr: str) -> list[dict]:
    return _transport_evidence(raw, stderr, "transport")


def rate_limit_evidence(raw: str, stderr: str) -> list[dict]:
    return _transport_evidence(raw, stderr, "rate_limit")


def retry_after_seconds(value: object) -> float | None:
    """Read Retry-After seconds/HTTP dates or retry_after[_seconds] JSON hints."""
    if isinstance(value, dict):
        hints = []
        for key, child in value.items():
            normalized = key.casefold().replace("_", "-")
            if normalized in {"retry-after", "retry-after-seconds"}:
                hints.append(retry_after_seconds(f"Retry-After: {child}"))
            elif isinstance(child, (dict, str)):
                hints.append(retry_after_seconds(child))
        return max((hint for hint in hints if hint is not None), default=None)
    if not isinstance(value, str):
        return None
    match = re.search(r"retry[-_ ]after(?:[-_ ]seconds)?[\"']?\s*[:=]\s*[\"']?([^\r\n\"'}]+)", value, re.I)
    if not match:
        return reset_seconds(value)
    numeric = re.match(r"(\d+(?:\.\d+)?)(?:\s*(?:s(?:ec(?:onds?)?)?)?\b|$)", match[1])
    if numeric:
        return float(numeric[1])
    try:
        date = parsedate_to_datetime(match[1].strip())
        return max(0.0, date.timestamp() - time.time())
    except (ValueError, TypeError, OverflowError):
        return None


RESET_AT = re.compile(r"\b(?:try again|retry|resets?|available again)\s+(?:at|after)\s+"
                      r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\b\.?", re.I)
RESET_IN = re.compile(r"\b(?:try again|retry|resets?|available again)\s+in\s+((?:\d+(?:\.\d+)?\s*"
                      r"(?:days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b[\s,]*(?:and\s+)?)+)", re.I)
UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def reset_seconds(text: str, now: datetime | None = None) -> float | None:
    """Seconds until an explicit reset time in a service message ("try again at 3:07 PM",
    "resets in 2 hours 5 minutes"); a clock time already past today means tomorrow."""
    match = RESET_IN.search(text)
    if match:
        total = 0.0
        for amount, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", match[1], re.I):
            total += float(amount) * UNITS["m" if unit.lower().startswith("mi") else unit[0].lower()]
        return total
    match = RESET_AT.search(text)
    if not match:
        return None
    hour, minute, second = int(match[1]), int(match[2]), int(match[3] or 0)
    if match[4]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if match[4].lower() == "p" else 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if target <= now:
        target = target.fromtimestamp(target.timestamp() + 86400)
    return max(0.0, (target - now).total_seconds())


class RateLimitThrottle:
    """One shared launch gate per runner invocation; existing sessions may finish."""

    def __init__(self, *, clock=None, sleep=None):
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._until = 0.0
        self._reset_at = 0.0

    def defer(self, evidence: list[dict], attempt: int) -> float:
        """Try three fresh sessions first; only then wait for reset or bounded backoff."""
        explicit = max((retry_after_seconds(entry) or 0 for entry in evidence), default=0)
        backoff = min(60 * 2 ** min(max(attempt - 4, 0), 2), 240)
        with self._lock:
            now = self._clock()
            self._reset_at = max(self._reset_at, now + explicit)
            delay = 0 if attempt <= 3 else max(backoff, self._reset_at - now)
            self._until = max(self._until, now + delay)
        return float(delay)

    def wait(self) -> None:
        while True:
            with self._lock:
                remaining = self._until - self._clock()
            if remaining <= 0:
                return
            # Recheck for cooldown extensions made by other workers.
            self._sleep(min(remaining, 60))


def terminal_transport_category(raw: str, stderr: str) -> str | None:
    """Require a terminal diagnostic, never a recovered turn or quoted output."""
    def category(raw: str, stderr: str) -> str | None:
        if rate_limit_evidence(raw, stderr):
            return "rate_limit"
        if disconnect_evidence(raw, stderr):
            return "transport"
        return None

    terminal = None
    for line in raw.splitlines():
        failure = category(line, "")
        if failure:
            terminal = failure
            continue
        try:
            event = json.loads(line)
        except ValueError:
            if line.strip():
                terminal = "other"
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        item = event.get("item")
        if kind in {"error", "turn.failed"} or (
                kind in {"item.started", "item.updated", "item.completed"}
                and isinstance(item, dict) and item.get("type") == "error"):
            terminal = "other"
        elif kind == "turn.completed":
            terminal = "completed"
        elif kind in {"turn.started", "item.started", "item.updated", "item.completed"}:
            # Progress after a disconnect proves recovery. A new turn after a
            # completed one may still fail via stderr-only transport diagnostics.
            terminal = "recovered" if terminal in {"transport", "rate_limit", "recovered"} else None
    if terminal in {"other", "completed", "recovered"}:
        return None
    # The streams have no shared ordering. Preserve the terminal event unless
    # stderr has an explicit error after its last disconnect; warnings do not
    # contradict a disconnect or hide a later error.
    stderr_terminal = None
    for line in stderr.splitlines():
        failure = category("", line)
        if failure:
            stderr_terminal = failure
        elif re.search(r"^(?:\d{4}-\d{2}-\d{2}T\S+\s+)?(?:error|fatal)\b"
                       r"|^[\w.]*(?:Error|Exception):", line.strip(), re.IGNORECASE):
            stderr_terminal = "other"
    if stderr_terminal == "other":
        return None
    return terminal or stderr_terminal


def terminal_transport_failure(raw: str, stderr: str) -> bool:
    return terminal_transport_category(raw, stderr) is not None


def saved_transport_category(run_dir: Path, run: dict) -> str | None:
    """Recheck failed executor traces when older metadata missed a service outage."""
    category = run.get("failure_category")
    if category in {"transport", "rate_limit"}:
        return category
    # Preserve distinct failures (including timeouts and output capture errors).
    # Older uncategorized failed/timeout runs remain eligible for trace diagnosis.
    if category not in {None, "executor"} or (
            not run.get("returncode") and run.get("status") not in {"failed", "timeout"}):
        return None
    evidence = []
    for name in ("events.jsonl", "stderr.txt"):
        path = run_dir / name
        evidence.append(path.read_text(encoding="utf-8", errors="replace") if path.exists() else "")
    return terminal_transport_category(*evidence)


def resolved_model(raw: str, stderr: str = "") -> str | None:
    """Accept CLI session metadata, never a model name embedded in generated tool/text output."""
    actual = None
    for event in parse_events(raw):
        if event.get("type") in {"session.started", "session.configured", "thread.started", "turn.started"}:
            value = event.get("model")
        elif event.get("type") == "session_meta":
            value = event.get("payload", {}).get("model")
        elif event.get("type") == "model.rerouted":
            value = event.get("to_model")
        else:
            continue
        if isinstance(value, str) and value.strip():
            actual = value
    matches = re.findall(r"(?m)^model:\s*(\S+)\s*$", stderr)
    return actual or (matches[-1] if matches else None)


def total_tokens(events: list[dict]) -> int | None:
    """Codex reports per-turn usage; cached input is already included in input."""
    counts = []
    for event in events:
        if event.get("type") != "turn.completed" or not isinstance(event.get("usage"), dict):
            continue
        usage = event["usage"]
        total = usage.get("total_tokens")
        if type(total) is int and total >= 0:
            counts.append(total)
        elif all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
            counts.append(usage["input_tokens"] + usage["output_tokens"])
    return sum(counts) if counts else None


def render_transcript(prompt: str, events: list[dict], final: str) -> str:
    sections = ["# Codex execution transcript", "## Eval Prompt\n\n" + prompt]
    for number, event in enumerate(events, 1):
        sections.append(f"## Event {number}: {event.get('type', 'unknown')}\n\n"
                        + "```json\n" + json.dumps(event, ensure_ascii=False, indent=2) + "\n```")
    sections.append("## Final message\n\n" + final)
    return "\n\n".join(sections) + "\n"


def build_prompt(case: Case, skill_dir: Path, python: Path) -> str:
    return (
        f"The skill is at {skill_dir}. Read its SKILL.md first and use this skill for the task.\n"
        f"The Python executable is {python}. Input files have been copied into your current project directory.\n"
        "Work in the current directory. Save task artifacts there. Use local files only; this evaluation "
        "requires no network access. The CLI run settings in the case are metadata; carry out the task below.\n\n"
        + case.prompt
    )


def run_case(case: Case, config: str, skill_dir: Path, iteration_dir: Path, *, python: Path,
             codex: str = "codex", model: str | None = None, baseline_revision: str | None = None,
             baseline_roots: tuple[Path, ...] = (), timeout: int | None = None, retries: int = 3,
             throttle: RateLimitThrottle | None = None) -> dict:
    """Retry transport failures from scratch, keeping only the last attempt at the root."""
    if retries < 0:
        raise ValueError("retries must be nonnegative")
    run_dir = iteration_dir.resolve() / case.name / config
    run_dir.mkdir(parents=True, exist_ok=False)
    throttle = throttle or RateLimitThrottle()
    attempts = []
    for number in range(1, retries + 2):
        status = _run_attempt(case, config, skill_dir, iteration_dir, run_dir, python=python,
                              codex=codex, model=model, baseline_revision=baseline_revision,
                              baseline_roots=baseline_roots, timeout=timeout, throttle=throttle, attempt=number)
        broken = status["failure_category"] in {"transport", "rate_limit"}
        retry = broken and not status["contaminated"] and number <= retries
        archive = f"attempts/attempt-{number}" if broken else None
        if broken:
            status.update(excluded=True, exclusion_reason="transport failure")
        attempts.append({"number": number, "path": archive or ".",
                         **{key: status[key] for key in ("status", "returncode", "error", "started_at",
                                                        "finished_at", "disconnect_evidence", "rate_limit_evidence",
                                                        "retry_delay_seconds", "failure_category")}})
        status.update(attempts=list(attempts), retries=retries)
        write_json(run_dir / "run.json", status)
        if archive:
            destination = run_dir / archive
            destination.mkdir(parents=True)
            # Move every artifact before retrying so broker receipts and partial outputs
            # cannot survive into the next attempt. Keep a copy of a terminal failure.
            for artifact in run_dir.iterdir():
                if artifact.name == "attempts":
                    continue
                target = destination / artifact.name
                if retry:
                    artifact.rename(target)
                elif artifact.is_dir():
                    shutil.copytree(artifact, target)
                else:
                    shutil.copy2(artifact, target)
        if not retry:
            return status


def _run_attempt(case: Case, config: str, skill_dir: Path, iteration_dir: Path, run_dir: Path, *,
                 python: Path, codex: str, model: str | None, baseline_revision: str | None,
                 baseline_roots: tuple[Path, ...], timeout: int | None,
                 throttle: RateLimitThrottle, attempt: int) -> dict:
    """Launch a new Codex session with a new project, staged runtime, and evidence broker."""
    started = time.perf_counter()
    status = {"status": "running", "case": case.name, "config": config, "model": model,
              "requested_model": model, "resolved_model": None, "cleanup_errors": [],
              "skill_dir": str(skill_dir), "checker_path": str(skill_dir / "scripts" / "check_project.py"),
              "python": str(python), "baseline_revision": baseline_revision,
              "baseline_content_sha256": BASELINE_DIGEST if baseline_revision else None,
              "started_at": datetime.now(timezone.utc).isoformat(), "returncode": None, "error": None,
              "failure_category": None, "retry_delay_seconds": 0.0}
    write_json(run_dir / "run.json", status)
    final = ""
    root = None
    project = runtime = None
    runtime_integrity = None
    try:
        # Outside the user profile: Codex's Windows sandbox hides the profile, so a temp root there would
        # make the staged skill unreadable to the executor.
        runs_root = iteration_dir.resolve().parent / "_runs"
        runs_root.mkdir(exist_ok=True)
        # Not tempfile.mkdtemp: on Windows its mode 0o700 creates a protected ACL that blocks inheritance, and
        # files written by the elevated sandbox user then become unreadable for output capture and cleanup.
        root = (runs_root / f"ro-eval-{case.name}-{secrets.token_hex(4)}").resolve()
        root.mkdir()
        project = root / "project"
        project.mkdir()
        if (case.path / "files").is_dir():
            shutil.copytree(case.path / "files", project, dirs_exist_ok=True)
        runtime = root / "skill"
        stage_runtime(skill_dir, runtime)
        settings = configured_model_settings()
        environment, status["isolation"] = prepare_environment(root, project, settings)
        status["isolation"]["runtime_skill"] = str(runtime)
        runtime_integrity = {"before_sha256": content_digest(runtime), "after_sha256": None, "unchanged": None}
        status["isolation"]["runtime_integrity"] = runtime_integrity
        final_path = root / "final.md"
        prompt = build_prompt(case, runtime, python)
        command = [resolve_codex(codex), "exec", "-C", str(project), "-s", "workspace-write",
                   "-o", str(final_path), "--json", "--skip-git-repo-check", *config_arguments(settings),
                   # The Windows sandbox user needs explicit access to both external directories.
                   "--add-dir", str(Path(python).resolve().parent), "--add-dir", str(runtime)]
        interpreter_dir = str(Path(python).resolve().parent)
        status["isolation"].setdefault("residual_risks", []).append(
            "The interpreter directory is granted with --add-dir (writable).")
        status["isolation"]["residual_risks"].append(
            "The runtime skill is granted with --add-dir (writable); read-only attributes and a content digest guard it.")
        status["isolation"]["writable_roots"] = [str(project), interpreter_dir, str(runtime)]
        status["isolation"]["interpreter_access"] = "explicit --add-dir grant for the interpreter directory"
        if model is not None:
            command.extend(["--model", model])
        command.append(prompt)
        status["command"] = command
        write_json(run_dir / "run.json", status)
        with EvidenceBroker(case.path, project, run_dir, python, skill_dir) as broker:
            environment.update(broker.environment)
            try:
                with (run_dir / "events.jsonl").open("w", encoding="utf-8") as output, (
                        run_dir / "stderr.txt").open("w", encoding="utf-8") as errors:
                    throttle.wait()
                    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                            text=True, encoding="utf-8", errors="replace", env=environment,
                                            timeout=timeout or case.timeout_seconds, check=False,
                                            creationflags=no_window_flags())
                status["returncode"] = result.returncode
                status["status"] = "completed" if result.returncode == 0 else "failed"
                if result.returncode != 0:
                    status["error"] = f"Codex exited with status {result.returncode}; see stderr.txt"
                    status["failure_category"] = "executor"
                    raw = (run_dir / "events.jsonl").read_text(encoding="utf-8", errors="replace")
                    stderr = (run_dir / "stderr.txt").read_text(encoding="utf-8", errors="replace")
                    if terminal_transport_category(raw, stderr) == "rate_limit":
                        status["retry_delay_seconds"] = throttle.defer(rate_limit_evidence(raw, stderr), attempt)
            except subprocess.TimeoutExpired:
                status.update(status="timeout", error=f"Codex exceeded {timeout or case.timeout_seconds} seconds",
                              failure_category="timeout")
            except OSError as exc:
                status.update(status="failed", error=str(exc), failure_category="launch")
        status["evidence"] = broker.metadata
        _plain_tree(project)
        shutil.copytree(project, run_dir / "outputs")
        if final_path.is_file():
            final = final_path.read_text(encoding="utf-8", errors="replace")
        (run_dir / "outputs" / "final.md").write_text(final, encoding="utf-8")
        if status["status"] == "completed" and not final.strip():
            status.update(status="failed", error="Codex returned no final message", failure_category="missing_final")
    except (OSError, ValueError) as exc:
        status.update(status="failed", error=f"Project setup/copy failed: {exc}", failure_category="setup/copy")
    finally:
        if runtime_integrity is not None:
            try:
                runtime_integrity["after_sha256"] = content_digest(runtime)
                runtime_integrity["unchanged"] = runtime_integrity["before_sha256"] == runtime_integrity["after_sha256"]
            except (OSError, ValueError) as exc:
                runtime_integrity.update(unchanged=False, error=str(exc))
        if root is not None:
            status["cleanup_errors"] = cleanup(root)
    duration = time.perf_counter() - started
    raw_path = run_dir / "events.jsonl"
    raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
    events = parse_events(raw)
    stderr_path = run_dir / "stderr.txt"
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    status["disconnect_evidence"] = disconnect_evidence(raw, stderr)
    status["rate_limit_evidence"] = rate_limit_evidence(raw, stderr)
    if status["failure_category"] == "executor":
        status["failure_category"] = terminal_transport_category(raw, stderr) or "executor"
    status["resolved_model"] = resolved_model(raw, stderr)
    status["model"] = status["resolved_model"] or model
    (run_dir / "transcript.md").write_text(render_transcript(case.prompt, events, final), encoding="utf-8")
    status["contamination"] = audit_run(
        run_dir, source_repo=ROOT, workspace=iteration_dir.resolve().parent,
        project=project, runtime=runtime, baseline_roots=baseline_roots,
        host_context=status.get("isolation", {}).get("host_context"))
    if runtime_integrity is not None and not runtime_integrity["unchanged"]:
        status["contamination"]["contaminated"] = True
        status["contamination"]["findings"].append({
            "reason": "runtime skill modified", "path": str(runtime), "operation": "content_digest",
            "evidence": "run.json:isolation.runtime_integrity"})
    status["contaminated"] = status["contamination"]["contaminated"]
    if status["contaminated"]:
        status["executor_status"] = status["status"]
        status["status"] = "contaminated"
    write_json(run_dir / "timing.json", {"duration_ms": round(duration * 1000),
                                        "total_duration_seconds": round(duration, 3), "total_tokens": total_tokens(events)})
    status["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(run_dir / "run.json", status)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--skill-dir", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--old-skill-dir", type=Path, help="Verified release 5.1.0 snapshot; otherwise archive its pinned commit")
    parser.add_argument("--configs", nargs="+", choices=("with_skill", "old_skill"), default=["with_skill", "old_skill"])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=None,
                        help="Seconds per run for every case and config (overrides each case's setting)")
    parser.add_argument("--retries", type=int, default=3,
                        help="Fresh-session retries for disconnects/rate limits (default: 3 immediate retries "
                             "before waiting for a stated reset; 0 disables retries)")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--model", help="Override the configured Codex model (default: unset)")
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--validate-only", action="store_true", help="Validate cases without launching Codex or writing a workspace")
    args = parser.parse_args(argv)
    if args.iteration < 1 or args.jobs < 1:
        parser.error("--iteration and --jobs must be positive")
    if args.retries < 0:
        parser.error("--retries must be nonnegative")
    try:
        skill_dir = args.skill_dir.resolve()
        cases = load_cases(skill_dir, args.cases)
        if args.validate_only:
            print(f"Validated {len(cases)} cases ({sum(len(c.assertions) for c in cases)} assertions)")
            return 0
        workspace = args.workspace.resolve()
        iteration = workspace / f"iteration-{args.iteration}"
        configs = list(dict.fromkeys(args.configs))
        # Refuse all selected work before launching any paid session if a run already exists.
        for case in cases:
            for config in configs:
                if (iteration / case.name / config).exists():
                    raise ValueError(f"Run already exists: {iteration / case.name / config}; use a new iteration")
        skills = {"with_skill": skill_dir}
        baseline_revision = None
        if "old_skill" in configs:
            if args.old_skill_dir:
                skills["old_skill"] = args.old_skill_dir.resolve()
                baseline_revision = validate_old_skill(skills["old_skill"])
            else:
                skills["old_skill"], baseline_revision = snapshot_old_skill(ROOT, workspace)
        for directory in skills.values():
            if not (directory / "SKILL.md").is_file():
                raise ValueError(f"No SKILL.md in {directory}")
        for case in cases:
            case_dir = iteration / case.name
            case_dir.mkdir(parents=True, exist_ok=True)
            metadata = {"eval_name": case.name, "prompt": case.prompt, "assertions": [a.text for a in case.assertions]}
            metadata_path = case_dir / "eval_metadata.json"
            if metadata_path.exists() and json.loads(metadata_path.read_text(encoding="utf-8")) != metadata:
                raise ValueError(f"Case changed within this iteration: {case.name}; use a new iteration")
            write_json(metadata_path, metadata)
        failures = 0
        throttle = RateLimitThrottle()
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(run_case, case, config, skills[config], iteration,
                                       python=args.python.resolve(), codex=args.codex, model=args.model,
                                       baseline_revision=baseline_revision if config == "old_skill" else None,
                                       baseline_roots=tuple(skills[name] for name in ("old_skill",) if name in skills),
                                       timeout=args.timeout, retries=args.retries, throttle=throttle):
                       (case.name, config) for case in cases for config in configs}
            for future in as_completed(futures):
                case_name, config = futures[future]
                try:
                    status = future.result()
                    failures += status["status"] != "completed"
                    print(f"{case_name}/{config}: {status['status']}", flush=True)
                except Exception as exc:
                    failures += 1
                    print(f"{case_name}/{config}: failed: {exc}", file=sys.stderr, flush=True)
        return 1 if failures else 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
