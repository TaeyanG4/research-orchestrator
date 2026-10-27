"""Execute fixed case helpers outside the executor's writable project.

The executor can request an observation, but cannot supply code, inputs from a
different path, or a receipt. Only this harness thread appends execution evidence.
The file mailbox works with Codex's network-disabled workspace sandbox.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading

if __package__:
    from .content import file_digest, normalize_text
    from .proc import no_window_flags
else:
    from content import file_digest, normalize_text
    from proc import no_window_flags


HELPERS = {
    "unified-research-resume": ("analyze.py", ("plan.md", "observations.csv"),
                                ("results/claim-before.md", "results/summary.json")),
    "external-action-order": ("simulate_external.py", ("handoff.md", "release-note.txt"),
                              ("action-before.md", "action-result.json", "action-executed.lock")),
    "posttool-unchanged-fast-path": ("measure_posttool.py", (), ("posttool-results.json",
        "project/agents.md", "project/plan.md", "project/discoveries.md", "project/handoff.md")),
}


def runtime_digest(skill: Path) -> str:
    """Identify the Python runtime used by a captured adapter measurement."""
    scripts = sorted((skill / "scripts").glob("*.py"))
    if not scripts or not (skill / "scripts" / "ro_hook_runner.py").is_file():
        raise ValueError("Measurement requires the evaluated hook runtime")
    manifest = [(path.name, file_digest(path)) for path in scripts]
    return hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()


def _plain_path(path: Path, root: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Evidence input contains a link: {part.name}")
        if part == root:
            break


def _read_plain(path: Path, root: Path) -> bytes:
    _plain_path(path, root)
    return path.read_bytes()


class EvidenceBroker:
    """Context manager started before Codex and stopped before project capture."""

    def __init__(self, case_dir: Path, project: Path, run_dir: Path, python: Path,
                 runtime_skill: Path | None = None):
        self.case_dir = case_dir
        self.project = project
        self.run_dir = run_dir
        self.python = python
        self.runtime_skill = runtime_skill
        self.helper = HELPERS.get(case_dir.name)
        self.receipts = run_dir / "evidence"
        self.requests = project / ".eval-evidence" / "requests"
        self.responses = project / ".eval-evidence" / "responses"
        self.stop = threading.Event()
        self.thread = None
        self.seen = set()
        self.errors = []
        self.attempts = 0
        self._measurement_runtime_sha256 = None
        self._capture_secret = secrets.token_bytes(32)

    @property
    def environment(self) -> dict[str, str]:
        return {"RO_EVAL_EVIDENCE_DIR": str(self.responses.resolve())} if self.helper else {}

    @property
    def metadata(self) -> dict:
        return {"enabled": bool(self.helper), "method": "broker-authorized canonical helper capture",
                "log": "evidence.jsonl", "invocation_log": "helper-executions.jsonl",
                "executor_writable": False, "errors": list(self.errors),
                "runtime_sha256": self._measurement_runtime_sha256,
                "residual_risk": "Relies on the OS sandbox denying writes outside the project; "
                                 "this is execution provenance, not a hostile-process security boundary."}

    def __enter__(self):
        if self.helper:
            if self.run_dir.resolve().is_relative_to(self.project.resolve()):
                raise ValueError("Trusted evidence must be outside the executor project")
            if self.case_dir.resolve().is_relative_to(self.project.resolve()):
                raise ValueError("Canonical helpers must be outside the executor project")
            self.receipts.mkdir(exist_ok=False)
            self.requests.mkdir(parents=True, exist_ok=False)
            self.responses.mkdir(exist_ok=False)
            (self.run_dir / "evidence.jsonl").touch(exist_ok=False)
            (self.run_dir / "helper-executions.jsonl").touch(exist_ok=False)
            (self.requests.parent / "endpoint.json").write_text(
                json.dumps({"evidence": str(self.responses.resolve())}), encoding="utf-8")
            self.thread = threading.Thread(target=self._serve, name="eval-evidence", daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        if self.thread:
            self.thread.join()

    def _serve(self):
        while not self.stop.is_set():
            try:
                for request in sorted(self.requests.glob("*.json")):
                    if request.stem in self.seen or not re.fullmatch(r"[0-9a-f]{32}", request.stem):
                        continue
                    try:
                        data = json.loads(_read_plain(request, self.project))
                    except (OSError, ValueError):
                        continue  # The client publishes with an atomic rename.
                    self.seen.add(request.stem)
                    self._execute(request.stem, data)
            except (OSError, ValueError) as exc:
                self.errors.append(str(exc))
                return
            self.stop.wait(.02)

    def _execute(self, request_id: str, request: object):
        script, inputs, outputs = self.helper
        capture = self.receipts / request_id
        capture.mkdir()
        record = {"request": request_id, "helper": script, "returncode": None, "artifacts": {}, "error": None}
        try:
            self.attempts += 1
            # Record entry before dispatch, including rejected --capture attempts.
            # Only the broker appends this log, outside the writable project.
            self._append("helper-executions.jsonl", {
                "sequence": self.attempts, "request": request_id, "helper": script,
                "mode": request.get("mode") if isinstance(request, dict) else None,
                "started_at": datetime.now(timezone.utc).isoformat()})
            if self.attempts != 1:
                raise ValueError("The helper was already requested; a second execution is forbidden")
            if isinstance(request, dict) and request.get("mode") == "capture":
                raise ValueError("Direct --capture is forbidden; only the broker may capture evidence")
            if request != {"helper": script, "mode": "request"}:
                raise ValueError("Unexpected helper request")
            source = normalize_text((self.case_dir / "files" / script).read_bytes())
            if normalize_text(_read_plain(self.project / script, self.project)) != source:
                raise ValueError("The supplied helper was modified")
            record["helper_sha256"] = hashlib.sha256(source).hexdigest()
            if script == "measure_posttool.py":
                if self.runtime_skill is None or self.runtime_skill.resolve().is_relative_to(self.project.resolve()):
                    raise ValueError("Measurement requires a harness-selected runtime outside the project")
                record["runtime_sha256"] = runtime_digest(self.runtime_skill)
                self._measurement_runtime_sha256 = record["runtime_sha256"]
                record["collector_sha256"] = file_digest(Path(__file__).with_name("posttool_capture.py"))
            for name in inputs:
                content = _read_plain(self.project / name, self.project)
                if name in {"observations.csv", "release-note.txt"} and normalize_text(content) != normalize_text(
                        (self.case_dir / "files" / name).read_bytes()):
                    raise ValueError(f"The supplied input was modified: {name}")
                (capture / name).write_bytes(content)
            # Capture code has no helper CLI entry point: a readable --capture
            # branch previously allowed uncounted observations before claiming.
            # The per-run capability stays in this broker process, never in the
            # executor environment, mailbox, command line, or a readable file.
            record["stdout"] = self._capture(script, capture, self._capture_secret)
            if script == "measure_posttool.py" and record["runtime_sha256"] != runtime_digest(self.runtime_skill):
                raise ValueError("Measurement runtime changed during capture")
            record["returncode"] = 0
            record["artifacts"] = {name: file_digest(capture / name)
                                   for name in outputs}
        except (OSError, ValueError, KeyError, ZeroDivisionError, subprocess.TimeoutExpired) as exc:
            record["error"] = str(exc)
        # The log precedes the receipt, so a client cannot complete before its
        # execution and the exact pre-action snapshot are durably recorded.
        self._append("evidence.jsonl", record)
        receipt = capture / "receipt.tmp"
        receipt.write_text(json.dumps(record) + "\n", encoding="utf-8")
        receipt.replace(capture / "receipt.json")
        # Publish disposable copies inside the granted project; grading uses only
        # the protected originals above. Publish the receipt last to signal readiness.
        _plain_path(self.responses, self.project)
        response = self.responses / request_id
        response.mkdir(exist_ok=False)
        for name in record["artifacts"]:
            target = response / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(capture / name, target)
        receipt = response / "receipt.tmp"
        shutil.copyfile(capture / "receipt.json", receipt)
        receipt.replace(response / "receipt.json")

    def _append(self, name: str, record: dict):
        with (self.run_dir / name).open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")
            log.flush()
            os.fsync(log.fileno())

    def _capture(self, script: str, root: Path, secret: bytes) -> str:
        if not hmac.compare_digest(secret, self._capture_secret):
            raise ValueError("Capture requires the broker's per-run capability")
        if script == "analyze.py":
            out = root / "results"
            out.mkdir(exist_ok=False)
            (out / "claim-before.md").write_bytes((root / "plan.md").read_bytes())
            with (root / "observations.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            values = [float(row["elapsed_seconds"]) for row in rows]
            sources = sorted({row["source"] for row in rows})
            result = {"n": len(values), "overall_mean": sum(values) / len(values),
                      "source_means": {
                          source: sum(float(row["elapsed_seconds"]) for row in rows if row["source"] == source)
                          / sum(row["source"] == source for row in rows) for source in sources}}
            result_path = out / "summary.json"
        elif script == "simulate_external.py":
            with (root / "action-executed.lock").open("x", encoding="utf-8") as lock:
                lock.write("executed once\n")
            started = datetime.now(timezone.utc).isoformat()
            before = (root / "handoff.md").read_bytes()
            (root / "action-before.md").write_bytes(before)
            artifact = (root / "release-note.txt").read_bytes()
            result = {"executions": 1, "status": "accepted", "candidate": "release-note.txt",
                      "candidate_sha256": hashlib.sha256(normalize_text(artifact)).hexdigest(),
                      "destination": "mock://archive/release-note",
                      "before_sha256": hashlib.sha256(normalize_text(before)).hexdigest(), "started_at": started,
                      "observed_at": datetime.now(timezone.utc).isoformat()}
            result_path = root / "action-result.json"
        elif script == "measure_posttool.py":
            environment = {key: value for key, value in os.environ.items()
                           if key not in {"CLAUDECODE", "CLAUDE_PROJECT_DIR", "RO_SLOT", "RO_SESSION", "RO_USER",
                                          "RO_HOOK_DIAGNOSTICS", "RO_HOOK_PYTHON"}
                           and not key.startswith(("CLAUDE_CODE_", "CODEX_", "GEMINI_"))}
            environment.update(LOCALAPPDATA=str(root / "cache"), XDG_CACHE_HOME=str(root / "cache"),
                               RESEARCH_ORCHESTRATOR_HOME=str(root / "home"), PYTHONIOENCODING="utf-8")
            result = subprocess.run([str(self.python), "-I", str(Path(__file__).with_name("posttool_capture.py")),
                                     str(self.runtime_skill), str(root)], capture_output=True, text=True,
                                    encoding="utf-8", env=environment, timeout=30, creationflags=no_window_flags())
            if result.returncode:
                raise ValueError("Canonical PostToolUse measurement failed: " + result.stderr[-1000:])
            return result.stdout
        else:
            raise ValueError("Unknown capture helper")
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return json.dumps(result) + "\n"
