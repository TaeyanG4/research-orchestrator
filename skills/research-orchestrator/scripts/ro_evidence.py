#!/usr/bin/env python3
"""Artifact receipts, external-action execution and the authoritative outgoing-object scan.

Receipt authorship is an explicit assertion by the calling session, retained with its source.
Text files use UTF-8 with CRLF changed to LF; directory manifests always hash raw bytes.
An external record's Scope (or Contract) names its contract; absent that, the X ID is its scope.
"""

from __future__ import annotations

import codecs
import contextlib
import datetime as dt
from contextvars import ContextVar
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import queue
from stat import S_ISREG
import subprocess
import threading
import time

import ro_settings
from ro_credentials import SECRET_PATTERNS
from ro_external_process import OwnedTree
from ro_proc import no_window_flags
from ro_ids import X_PATTERN
from ro_markdown import mask_fences
from ro_state import process_start, redact, same_process


MANIFEST_CAP = 10_000
DIFF_CAP = 2 * 1024 * 1024
SCAN_SECONDS = 8.0          # Staged pre-check inside a per-call hook; the host allows 10 s.
PUSH_SCAN_SECONDS = 60.0    # Base enumeration budget; add 50 ms per outgoing object.
PUSH_SCAN_OBJECT_SECONDS = 0.05
PUSH_SCAN_MAX_SECONDS = 3600.0
WINDOW, OVERLAP = 65536, 2048
SCAN_CACHE = "publish-scan-cache.json"
SCAN_CACHE_LIMIT = 200_000
SCAN_CACHE_BYTES = 16 * 1024 * 1024
GIT = ("git", "--no-replace-objects", "--no-optional-locks")
EXTERNAL_OUTPUT_CAP = 16 * 1024
EXTERNAL_SECONDS = 300.0
_SCAN_DEADLINE = ContextVar("publish_scan_deadline", default=None)
_SCAN_PROGRESS = ContextVar("publish_scan_progress", default=None)
EXCLUDED = {".git", "__pycache__", ".ro"}
OID = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")


def artifact_path(project, artifact: str) -> Path:
    path = Path(artifact).expanduser()
    return (path if path.is_absolute() else project.root / path).resolve()


def artifact_key(project, artifact: str) -> str:
    return os.path.normcase(str(artifact_path(project, artifact)))


STAMP_HASH_BYTES = 32 * 1024 * 1024
# Total review-evidence bytes one brief's checker run may hash (startup runs inside a hook deadline).
BRIEF_HASH_BYTES = 64 * 1024 * 1024


def stat_artifact(project, artifact: str) -> dict:
    """Bounded change stamp for cached briefs.

    Artifacts up to STAMP_HASH_BYTES are content-hashed, so a same-size edit with a restored
    timestamp is still seen. Larger ones, and any beyond the active hash_budget, are stamped
    by member names, sizes and times only: hashing them here would run inside the hook
    deadline on every startup. A changed stamp makes the checker run under the same budget,
    reusing digests already computed; evidence beyond it is reported unverified, and
    check_project.py or `ro receipt check` verifies it in full.
    """
    path = artifact_path(project, artifact)
    if path.is_file():
        stat = path.stat()
        if stat.st_size <= STAMP_HASH_BYTES:
            try:
                return {"kind": "file", "sha256": hash_artifact(project, artifact)["sha256"]}
            except HashBudgetExceeded:
                pass  # the brief's aggregate budget is spent: fall back to metadata
        return {"kind": "file", "stat": [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino]}
    if not path.is_dir():
        return {"kind": "missing"}
    entries, members, failures = [], [], []
    linked = False
    for directory, names, files in os.walk(path, followlinks=False, onerror=failures.append):
        names[:] = sorted(name for name in names if name not in EXCLUDED)
        for name in names:
            # Full hashing refuses directory links; record them so adding one changes the stamp.
            entry = Path(directory) / name
            if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                entries.append([entry.relative_to(path).as_posix() + "/", 0, 0, 0, "link"])
                linked = True
        for name in sorted(files):
            if name in EXCLUDED:
                continue
            if len(entries) >= MANIFEST_CAP:
                # A receipt never verifies an over-cap directory (_valid_receipt refuses "unhashed"),
                # so the checker result holds while it stays over the cap: stamp the capped prefix
                # instead of forcing the checker on every brief, compaction included.
                digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode("utf-8")).hexdigest()
                return {"kind": "directory", "over_cap": MANIFEST_CAP, "metadata": digest}
            entry = Path(directory) / name
            try:
                stat = entry.lstat()
            except OSError:
                return {"kind": "directory", "unstamped": True}
            # ctime and inode also change when a member is replaced with preserved size and mtime.
            entries.append([entry.relative_to(path).as_posix(), stat.st_size, stat.st_mtime_ns,
                            stat.st_ctime_ns, stat.st_ino])
            members.append((entry, stat.st_size, S_ISREG(stat.st_mode)))
    if failures:
        # An unreadable subdirectory hides its members from this stamp: never reuse a cached result.
        return {"kind": "directory", "unstamped": True}
    entries.sort()
    if sum(entry[1] for entry in entries) <= STAMP_HASH_BYTES:
        if linked:
            raise ValueError("directory artifacts cannot contain links or junctions")
        try:
            # Hash the members this walk found instead of enumerating the directory again.
            return {"kind": "directory", "sha256": hash_artifact(project, artifact, members)["sha256"]}
        except HashBudgetExceeded:
            pass  # the brief's aggregate budget is spent: fall back to metadata
    digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"kind": "directory", "entries": len(entries), "metadata": digest}


class HashBudgetExceeded(ValueError):
    """Hook-side review checks stop before reading more than their byte budget."""


_HASH_BUDGET = ContextVar("artifact_hash_budget", default=None)


@contextlib.contextmanager
def hash_budget(limit_bytes: int):
    """Bound the bytes hash_artifact may read in this context (briefs inside a hook deadline).

    Digests computed in the context are reused, so each artifact is read at most once.
    Exceeding the budget raises HashBudgetExceeded, which review checks report as unverified
    rather than passed; check_project.py and `ro receipt check` verify without the budget.
    """
    token = _HASH_BUDGET.set([limit_bytes, {}])
    try:
        yield
    finally:
        _HASH_BUDGET.reset(token)


def _spend(size: int) -> None:
    budget = _HASH_BUDGET.get()
    if budget is None:
        return
    if size > budget[0]:
        raise HashBudgetExceeded("review evidence exceeds the brief's hash budget; verify it with "
                                 "check_project.py or `ro receipt check <artifact> --scope <stage>:after`")
    budget[0] -= size


def hash_artifact(project, artifact: str, members: list | None = None) -> dict:
    """Hash in bounded memory, preserving the existing text/manifest digest format.

    `members` lists a directory's (path, size, regular) entries from a walk the caller
    already made, so the directory is not enumerated twice.
    """
    budget = _HASH_BUDGET.get()
    if budget is None:
        return _hash_artifact(project, artifact, members)
    key = artifact_key(project, artifact)
    if key not in budget[1]:
        budget[1][key] = _hash_artifact(project, artifact, members)
    return json.loads(json.dumps(budget[1][key]))  # callers may annotate their copy


def _hash_artifact(project, artifact: str, members: list | None = None) -> dict:
    path = artifact_path(project, artifact)
    if not path.exists():
        raise ValueError("artifact does not exist")
    base = {"artifact": artifact_key(project, artifact), "sha256": "unhashed", "kind": "file"}
    if path.is_file():
        reserved = path.stat().st_size
        _spend(reserved)
        digest, size = _hash_file(path, normalize_text=True, expected_size=reserved)
        base.update(sha256=digest, bytes=size)
        return base
    if not path.is_dir():
        raise ValueError("artifact must be a file or directory")
    base["kind"] = "directory"
    manifest = []
    total = 0
    def enumeration_failed(error: OSError) -> None:
        # An incomplete manifest cannot establish which bytes a receipt approves.
        raise error

    # Enumerate before reading any content: an over-cap directory stays unhashed without
    # hashing its first MANIFEST_CAP files, and the byte budget is checked up front.
    entries = []
    if members is not None:
        if len(members) > MANIFEST_CAP:
            return base
        for entry, size, regular in members:
            if not regular:
                raise ValueError("directory artifacts must contain ordinary files")
            entries.append((entry, size))
    else:
        for directory, names, files in os.walk(path, followlinks=False, onerror=enumeration_failed):
            names[:] = sorted(name for name in names if name not in EXCLUDED)
            for name in names:
                entry = Path(directory) / name
                if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                    raise ValueError("directory artifacts cannot contain links or junctions")
            for name in sorted(files):
                if name in EXCLUDED:
                    continue
                entry = Path(directory) / name
                info = entry.lstat()
                if not S_ISREG(info.st_mode):
                    raise ValueError("directory artifacts must contain ordinary files")
                if len(entries) >= MANIFEST_CAP:
                    return base
                entries.append((entry, info.st_size))
    _spend(sum(size for _entry, size in entries))
    for entry, reserved in entries:
        digest, size = _hash_file(entry, expected_size=reserved)
        total += size
        manifest.append({"path": entry.relative_to(path).as_posix(), "sha256": digest})
    manifest.sort(key=lambda entry: entry["path"])
    canonical = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    base.update(sha256=hashlib.sha256(canonical).hexdigest(), manifest=manifest, bytes=total)
    return base


def _hash_file(path: Path, normalize_text: bool = False, expected_size: int | None = None) -> tuple[str, int]:
    """Compute raw and normalized candidates in one pass; late binary bytes select raw.

    With `expected_size` (the bytes reserved against a hash budget), a file that grew
    since it was measured is refused before reading past the reservation.
    """
    raw, normalized = hashlib.sha256(), hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    text = normalize_text
    raw_size = normalized_size = 0
    pending = b""
    with path.open("rb") as source:
        initial = os.fstat(source.fileno())
        if expected_size is not None and initial.st_size != expected_size:
            raise ValueError("artifact changed while hashing")
        # One byte past the reservation reveals growth while the file is being read.
        while data := source.read(WINDOW if expected_size is None else min(WINDOW, expected_size + 1 - raw_size)):
            raw.update(data)
            raw_size += len(data)
            if expected_size is not None and raw_size > expected_size:
                raise ValueError("artifact changed while hashing")
            if not text:
                continue
            try:
                decoder.decode(data)
                if b"\0" in data:
                    text = False
                    continue
            except UnicodeDecodeError:
                text = False
                continue
            block = pending + data
            pending = b"\r" if block.endswith(b"\r") else b""
            if pending:
                block = block[:-1]
            block = block.replace(b"\r\n", b"\n")
            normalized.update(block)
            normalized_size += len(block)
        final = os.fstat(source.fileno())
    if (initial.st_size, initial.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
        raise ValueError("artifact changed while hashing")
    if text:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            text = False
    if text:
        normalized.update(pending)
        return normalized.hexdigest(), normalized_size + len(pending)
    return raw.hexdigest(), raw_size


def _receipts(project) -> dict:
    data = project.read_json("receipts.json", {"version": 1, "receipts": []})
    if not isinstance(data, dict) or not isinstance(data.get("receipts"), list):
        raise ValueError("receipts state is malformed")
    return data


def receipt_policy(project) -> str:
    policy = project.settings().get("receipt_policy", "independent")
    if policy not in ("independent", "self"):
        raise ValueError("Receipt policy must be independent or self")
    return policy


def receipt_add(project, artifact: str, reviewer: str, verdict: str, scope: str, dest: str = "") -> str:
    if not reviewer.strip() or not scope.strip() or verdict not in ("PASS", "FAIL"):
        raise ValueError("receipt requires reviewer, scope and PASS or FAIL")
    # Protocol fixtures/callers may expose a session assertion directly; Project
    # distinguishes it from the incidental identity used for other local state.
    author = getattr(project, "explicit_session", project.session).strip()
    if not author:
        raise ValueError("receipt requires an explicit stable author session (--session or RO_SESSION)")
    if receipt_policy(project) == "independent" and reviewer.strip() == author:
        raise ValueError("reviewer must differ from the explicitly identified author session")
    digest = hash_artifact(project, artifact)
    entry = {**digest, "reviewer": reviewer, "author_session": author,
             "author_source": "receipt add caller session assertion", "verdict": verdict, "scope": scope,
             "destination": dest, "created_at": time.time()}
    with project.lock("receipts"):
        data = _receipts(project)
        data["receipts"].append(entry)
        project.write_json("receipts.json", data)
    return f"receipt {verdict}: sha256 {digest['sha256']} scope {scope}"


def _valid_receipt(project, artifact: str, scope: str | None = None, dest: str | None = None,
                   *, independent: bool = False) -> dict:
    policy = "independent" if independent else receipt_policy(project)
    digest = hash_artifact(project, artifact)
    if digest["sha256"] == "unhashed":
        raise ValueError("artifact is unhashed: directory manifest entry limit exceeded")
    # Evaluate latest for each artifact+scope before filtering by verdict, destination or hash.
    latest = {}
    for entry in _receipts(project)["receipts"]:
        if not isinstance(entry, dict) or entry.get("artifact") != digest["artifact"]:
            continue
        if scope is None or entry.get("scope") == scope:
            latest[entry.get("scope")] = entry
    for entry in reversed(list(latest.values())):
        reviewer, author = entry.get("reviewer"), entry.get("author_session")
        if (entry.get("verdict") == "PASS" and entry.get("sha256") == digest["sha256"]
                and isinstance(reviewer, str) and reviewer.strip()
                and isinstance(author, str) and author.strip()
                and (policy == "self" or reviewer.strip() != author.strip())
                and entry.get("author_source") and (dest is None or entry.get("destination") == dest)):
            return entry
    raise ValueError(f"no current {policy} PASS receipt matches artifact, scope and destination")


def receipt_check(project, artifact: str, scope: str | None = None, dest: str | None = None) -> str:
    entry = _valid_receipt(project, artifact, scope, dest)
    return f"receipt PASS: sha256 {entry['sha256']} scope {entry['scope']}"


def _actions(text: str) -> list[dict]:
    sections = list(re.finditer(r"^## External actions[ \t]*\n(.*?)(?=^## |\Z)",
                                mask_fences(text), re.M | re.S))
    if not sections:
        return []
    if len(sections) != 1:
        raise ValueError("external ledger must have exactly one External actions section")
    actions, identifiers = [], set()
    for match in re.finditer(rf"^### ({X_PATTERN})\b[^\n]*\n(.*?)(?=^### |\Z)",
                             sections[0][1], re.M | re.S):
        if match[1] in identifiers:
            raise ValueError(f"external ledger ID {match[1]} must have exactly one heading")
        identifiers.add(match[1])
        fields = {}
        for key, value in re.findall(r"^- ([\w /-]+):[ \t]*([^\n]*)", match[2], re.M):
            key = key.strip()
            if key in fields:
                raise ValueError(f"external ledger {match[1]} has duplicate {key} fields")
            fields[key] = value.strip()
        # Every record participates in duplicate/retry decisions, not just the
        # selected one. Validate cardinality before any value can hide history.
        for key in ("Status", "Candidate", "Destination", "Expected"):
            if key not in fields:
                raise ValueError(f"external ledger {match[1]} requires exactly one {key} field")
        if "Scope" in fields and "Contract" in fields:
            raise ValueError(f"external ledger {match[1]} requires one Scope or Contract field, not both")
        actions.append({"id": match[1], "fields": fields})
    return actions


def _candidate(fields: dict) -> tuple[str, str]:
    match = re.fullmatch(r"(.+?),\s*hash\s+(?:sha256:)?([0-9a-fA-F]{64})\s*", fields.get("Candidate", ""))
    if not match:
        raise ValueError("prepared action requires Candidate: <artifact>, hash <sha256>")
    return match[1].strip(), match[2].lower()


def external_retry_checks(records: list[tuple[str, dict]]) -> dict[str, tuple[bool, bool, bool]]:
    """Return (valid retry chain, duplicate identity, superseded) using ledger times.

    The checker accepts legacy opaque hashes; the execution wrapper separately requires
    SHA256. Both use this same identity and chronology rule for retry ancestry.
    """
    fields_by_id = dict(records)
    counts = {}
    for key, _fields in records:
        counts[key] = counts.get(key, 0) + 1
    identities, chronology, originals = {}, {}, {}
    for key, fields in records:
        candidate = re.fullmatch(r".+,\s*hash\s+(\S+)", fields.get("Candidate", "").strip())
        destination = fields.get("Destination", "").strip()
        if candidate and destination:
            digest = candidate[1].removeprefix("sha256:")
            identities[key] = digest.lower(), destination
        chronology[key] = None
        for name, verb in (("Result", "observed"), ("Expected", "written")):
            stamp = re.search(rf"\({verb} (\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}(?::\d{{2}})?)\)",
                              fields.get(name, ""))
            try:
                chronology[key] = dt.datetime.fromisoformat(stamp[1]) if stamp else None
            except ValueError:
                pass
            if chronology[key] is not None:
                break
    for key in sorted(identities, key=lambda k: (chronology[k] or dt.datetime.max, k)):
        if fields_by_id[key].get("Status") != "withdrawn":
            originals.setdefault(identities[key], key)

    def valid_chain(key: str) -> bool:
        visited = set()
        while retry := fields_by_id[key].get("Retry of", "").strip():
            visited.add(key)
            if (counts[key] != 1 or counts.get(retry) != 1 or retry in visited
                    or retry not in identities or key not in identities
                    or identities[retry] != identities[key] or chronology[retry] is None
                    or chronology[key] is None or chronology[retry] >= chronology[key]):
                return False
            key = retry
        return counts[key] == 1

    def superseded(key: str) -> bool:
        return any(other != key and identities[other] == identities[key]
                   and fields_by_id[other].get("Status") != "withdrawn"
                   and (chronology[other] is None or chronology[key] is None or chronology[other] >= chronology[key])
                   for other in identities)

    return {key: (bool(fields.get("Retry of", "").strip()) and valid_chain(key),
                  key in identities and originals.get(identities[key], key) != key,
                  key in identities and superseded(key))
            for key, fields in records}


def _action_status(project, action: str, status: str) -> None:
    with project.lock():
        path = project.root / "handoff.md"
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(rf"(^### {re.escape(action)}\b[^\n]*\n)(.*?)(?=^### |^## |\Z)", re.M | re.S)
        matches = list(pattern.finditer(mask_fences(text)))
        if len(matches) != 1:
            raise ValueError("external ledger entry must have exactly one heading")
        match = matches[0]
        statuses = list(re.finditer(r"^- Status[ \t]*:.*$", match[2], re.M))
        if len(statuses) != 1:
            raise ValueError("external ledger entry must have one Status field")
        start = match.start(2) + statuses[0].start()
        end = match.start(2) + statuses[0].end()
        project.atomic_text(path, text[:start] + f"- Status: {status}" + text[end:])


def _external_result(project, action: str, *, returncode=None, stdout="", stderr="", start_error="",
                     stdout_omitted=0, stderr_omitted=0) -> str:
    """Keep bounded, redacted response evidence for later remote reconciliation."""
    def bounded(raw, omitted=0):
        output = _RedactedOutput()
        output.add(str(raw))
        value, dropped = output.result()
        return value, omitted + dropped

    out, out_dropped = bounded(stdout, stdout_omitted)
    err, err_dropped = bounded(stderr, stderr_omitted)
    failure, _ = bounded(start_error)
    name = f"external-results/{action}.json"
    project.write_json(name, {"action": action, "returncode": returncode,
                             "stdout": out, "stderr": err, "start_error": failure,
                             "stdout_omitted_chars": out_dropped,
                             "stderr_omitted_chars": err_dropped,
                             "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    return f".ro/{name}"


class _OutputTail:
    """Keep fixed-size beginning/end evidence while draining arbitrarily large pipes."""

    def __init__(self):
        self.head = self.tail = ""
        self.total = 0

    def add(self, value):
        half = EXTERNAL_OUTPUT_CAP // 2
        self.total += len(value)
        needed = max(0, half - len(self.head))
        self.head += value[:needed]
        self.tail = (self.tail + value[needed:])[-half:]

    def result(self):
        omitted = max(0, self.total - EXTERNAL_OUTPUT_CAP)
        return self.head + ("\n[output truncated]\n" if omitted else "") + self.tail, omitted


class _RedactedOutput:
    """Sanitize complete bounded records before retaining any head/tail characters.

    A private key can span arbitrarily many records. An oversized diagnostic line
    is withheld in full because a credential's delimiter may arrive at its end.
    Only its small delimiter suffix remains in memory while it is drained.
    """

    RECORD_CAP = 4096
    _PEM = re.compile(r"-----((?:BEGIN|END) [A-Z ]*PRIVATE KEY)-----")
    _QUOTED = re.compile(r"(?i)\b(?:password|passwd|token|secret|api[_-]?key|authorization)\b\s*[=:]\s*([\"'])")
    _PREFIX = re.compile(r"\b(?:gh[pousr]_|github_pat_|sk-(?:proj-)?|AKIA|ASIA)[A-Za-z0-9_-]*")
    _CONTINUATION = re.compile(r"(?i)(?:\b(?:password|passwd|token|secret|api[_-]?key|authorization)\b\s*[=:]"
                               r"|--(?:password|token|secret|api[_-]?key))\s*(?:(?:bearer|basic)\s*)?$")

    def __init__(self):
        self.output = _OutputTail()
        self.lock = threading.Lock()
        self.pending = ""
        self.mode = ""
        self.overflow = False
        self.omitted = 0

    def _clean(self, text):
        result = []
        while text:
            if self.mode:
                end = (re.search(r"-----END [A-Z ]*PRIVATE KEY-----", text)
                       if self.mode == "pem" else re.search(re.escape(self.mode), text))
                if not end:
                    break
                text, self.mode = text[end.end():], ""
                continue
            pem = re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text)
            quote = self._QUOTED.search(text)
            matches = [match for match in (pem, quote) if match]
            if not matches:
                result.append(self._PREFIX.sub("[REDACTED]", redact(text)))
                break
            match = min(matches, key=lambda found: found.start())
            result.append(self._PREFIX.sub("[REDACTED]", redact(text[:match.start()])))
            if match is pem:
                result.append("[REDACTED PRIVATE KEY]")
                self.mode = "pem"
            else:
                result.append(text[match.start():match.end() - 1] + "[REDACTED]")
                self.mode = match[1]
            text = text[match.end():]
        return "".join(result)

    def add(self, value):
        with self.lock:
            self._add(value)

    def _add(self, value):
        # Split first so even a single large pipe read cannot enlarge pending.
        for piece in value.splitlines(keepends=True):
            for offset in range(0, len(piece), self.RECORD_CAP):
                chunk = piece[offset:offset + self.RECORD_CAP]
                self.pending += chunk
                if self.overflow or len(self.pending) > self.RECORD_CAP:
                    if not self.overflow:
                        self.output.add("[REDACTED oversized diagnostic line]")
                        self.overflow = True
                    # Carry enough delimiter context across reads, including PEM
                    # markers on a withheld line, so later key-body lines stay hidden.
                    if len(self.pending) > 128:
                        boundary = len(self.pending) - 128
                        for match in [*self._PEM.finditer(self.pending), *self._QUOTED.finditer(self.pending)]:
                            if match.start() < boundary < match.end():
                                boundary = match.start()
                        self._clean(self.pending[:boundary])
                        self.omitted += boundary
                        self.pending = self.pending[boundary:]
                if self.pending.endswith("\n") and not self._CONTINUATION.search(self.pending):
                    self._flush()

    def _flush(self):
        clean = self._clean(self.pending)
        if self.overflow:
            self.omitted += len(self.pending)
            self.output.add("\n" if self.pending.endswith("\n") else "")
        else:
            self.output.add(clean)
        self.pending = ""
        self.overflow = False

    def result(self):
        with self.lock:
            self._flush()
            text, omitted = self.output.result()
            return text, omitted + self.omitted


def _run_external(command, root, deadline, idempotency_key):
    """Drain both streams concurrently without capture_output's unbounded buffers."""
    env = dict(os.environ, RO_IDEMPOTENCY_KEY=idempotency_key)
    tree = OwnedTree()
    try:
        process = tree.start(command, popen=subprocess.Popen, cwd=root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                             creationflags=no_window_flags())
    except BaseException:
        tree.close()
        raise
    outputs = [_RedactedOutput(), _RedactedOutput()]
    failures = []

    def drain(stream, output):
        decoder = io.IncrementalNewlineDecoder(codecs.getincrementaldecoder("utf-8")("replace"), True)
        try:
            while chunk := stream.read(WINDOW):
                output.add(decoder.decode(chunk))
            output.add(decoder.decode(b"", final=True))
        except (OSError, ValueError) as exc:
            failures.append(str(exc))
        finally:
            stream.close()

    readers = [threading.Thread(target=drain, args=pair, daemon=True)
               for pair in zip((process.stdout, process.stderr), outputs)]
    for reader in readers:
        reader.start()
    until = time.monotonic() + deadline
    timed_out = False
    termination_verified = None
    try:
        try:
            process.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination_verified = tree.terminate()
        for reader in readers:
            reader.join(max(0, until - time.monotonic()) if not timed_out else 1)
        # An inherited pipe can outlive its direct child; its outcome is uncertain too.
        if any(reader.is_alive() for reader in readers) or tree.alive() is not False:
            timed_out = True
            termination_verified = tree.terminate()
            for reader in readers:
                reader.join(1)
    except BaseException:
        tree.terminate()
        for reader in readers:
            reader.join(1)
        raise
    finally:
        tree.close()
    stdout, stdout_omitted = outputs[0].result()
    stderr, stderr_omitted = outputs[1].result()
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    result.timed_out = timed_out or bool(failures)
    result.termination_verified = termination_verified
    result.stdout_omitted, result.stderr_omitted = stdout_omitted, stderr_omitted
    return result


def _select_external(project, args):
    """Select under the short ledger lock; the caller rechecks after its action lock."""
    text = (project.root / "handoff.md").read_text(encoding="utf-8")
    actions = _actions(text)
    matches = []
    for action in actions:
        if args.action and action["id"] != args.action:
            continue
        fields = action["fields"]
        if fields.get("Status") != "prepared":
            continue
        try:
            candidate, digest = _candidate(fields)
            artifact = args.artifact or candidate
            current = hash_artifact(project, artifact)
        except ValueError:
            if args.action:
                raise
            continue
        if current["sha256"] == digest:
            matches.append((action, artifact, digest))
    if len(matches) != 1:
        raise ValueError("external requires exactly one prepared action matching the current artifact hash")
    return text, actions, matches[0]


def _retry_reconciled(previous, expected_at):
    value = previous.get("Reconciled", "")
    match = re.fullmatch(r"not-accepted \(observed (\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)\);\s*(\S.*)", value)
    try:
        reconciled_at = dt.datetime.fromisoformat(match[1]) if match else None
        prior_times = []
        for field, verb in (("Expected", "written"), ("Result", "observed")):
            stamp = re.search(rf"\({verb} (\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}(?::\d{{2}})?)\)",
                              previous.get(field, ""))
            if stamp:
                prior_times.append(dt.datetime.fromisoformat(stamp[1]))
        valid = bool(reconciled_at and prior_times and max(prior_times) <= reconciled_at < expected_at)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Retry of requires prior Reconciled: not-accepted (observed timestamp); evidence")


def _durable_retry_history(project, actions, action_id, digest, destination, expected_at):
    """Check attempted identities under the external lock, even if their ledger rows disappeared.

    A withdrawn preparation is harmless only while no durable attempt exists. Each
    matching attempt must remain in the explicit, reconciled retry ancestry so an
    edited ledger cannot conceal a second branch or an active runner.
    """
    fields_by_id = {action["id"]: action["fields"] for action in actions}
    ancestors = set()
    previous = fields_by_id[action_id].get("Retry of", "").strip()
    while previous:
        # The caller has already validated chronology, identity and acyclicity.
        ancestors.add(previous)
        previous = fields_by_id[previous].get("Retry of", "").strip()
    directory = project.state / "external-attempts"
    if not directory.exists():
        return
    for path in directory.iterdir():
        if path.suffix != ".json":
            continue
        attempt = project.read_json(f"external-attempts/{path.name}", None)
        if (not isinstance(attempt, dict) or attempt.get("action") != path.stem
                or not re.fullmatch(X_PATTERN, path.stem)
                or not isinstance(attempt.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-fA-F]{64}", attempt["sha256"])
                or not isinstance(attempt.get("destination"), str) or not attempt["destination"].strip()):
            raise ValueError("invalid external attempt history; restore and reconcile before execution")
        if (attempt["sha256"].lower(), attempt["destination"].strip()) != (digest, destination):
            continue
        if path.stem not in ancestors:
            raise ValueError("duplicate external identity was already attempted; restore its ledger history, "
                             "reconcile and create an explicit Retry of")
        _retry_reconciled(fields_by_id[path.stem], expected_at)
        if (attempt.get("status") == "in-flight"
                and same_process(attempt.get("owner_pid"), attempt.get("owner_start"))):
            raise ValueError("prior external action is still in-flight; reconcile after its runner ends")


def external(project, args) -> str:
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise ValueError("external requires a command after --")
    deadline = float(getattr(args, "deadline", EXTERNAL_SECONDS))
    if not math.isfinite(deadline) or deadline <= 0:
        raise ValueError("external deadline must be a positive finite number of seconds")
    if args.action:
        if not re.fullmatch(X_PATTERN, args.action):
            raise ValueError("external action ID is invalid")
        action_id = args.action
    else:
        with project.lock("external"):
            _text, _actions_list, selected = _select_external(project, args)
            action_id = selected[0]["id"]
    # Only this action stays locked during network/authentication work. Independent
    # destinations can proceed while its process runs or waits for its deadline.
    with project.lock("external-" + action_id):
        with project.lock("external"):
            text, actions, (action, artifact, digest) = _select_external(project, args)
            if action["id"] != action_id:
                raise ValueError("prepared action selection changed; select an explicit --action")
            fields, action_id = action["fields"], action["id"]
            journal_name = f"external-attempts/{action_id}.json"
            if project.read_json(journal_name, None) is not None:
                raise ValueError("external prepared action was already attempted; reconcile and create an explicit retry")
            # Duplicate IDs can mix done/prepared entries: never execute one and then
            # accidentally update a different entry, leaving the action reusable.
            if len(re.findall(rf"^### {re.escape(action_id)}\b", mask_fences(text), re.M)) != 1:
                raise ValueError("selected external ledger ID must have exactly one heading")
            destination = fields.get("Destination", "").strip()
            if not destination:
                raise ValueError("prepared action requires a destination")
            written = re.search(r"\(written (\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)\)", fields.get("Expected", ""))
            try:
                expected_at = dt.datetime.fromisoformat(written[1]) if written else None
            except ValueError:
                expected_at = None
            if expected_at is None or expected_at >= dt.datetime.now() or not fields["Expected"][:written.start()].strip():
                raise ValueError("Expected must be written before external execution")
            scope = fields.get("Scope") or fields.get("Contract") or action_id
            _valid_receipt(project, artifact, scope, destination)
            valid_retry, duplicate, superseded = external_retry_checks([(a["id"], a["fields"]) for a in actions])[action_id]
            if fields.get("Retry of", "").strip() and not valid_retry:
                raise ValueError("Retry of must name an earlier matching action without a reference cycle")
            if duplicate and not valid_retry:
                raise ValueError("duplicate external action requires an explicit Retry of")
            if superseded:
                raise ValueError("duplicate external action has a later or undated attempt; reconcile before execution")
            _durable_retry_history(project, actions, action_id, digest, destination, expected_at)
            previous_id = fields.get("Retry of", "").strip()
            if previous_id:
                previous = next(a["fields"] for a in actions if a["id"] == previous_id)
                _retry_reconciled(previous, expected_at)
                prior_attempt = project.read_json(f"external-attempts/{previous_id}.json", {})
            else:
                prior_attempt = {}
            # Recompute immediately before acting; a review never authorizes changed bytes.
            if hash_artifact(project, artifact)["sha256"] != digest:
                raise ValueError("artifact changed during external validation")
            key = prior_attempt.get("idempotency_key") or hashlib.sha256(
                json.dumps([digest, destination], ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
            attempt = {"action": action_id, "status": "in-flight", "sha256": digest,
                       "destination": destination, "idempotency_key": key,
                       "started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "deadline_seconds": deadline,
                       "owner_pid": os.getpid(), "owner_start": process_start(os.getpid())}
            # This durable record precedes even the ledger update. A crash or failed
            # status write can never leave the prepared action eligible for replay.
            project.write_json(journal_name, attempt)
            _action_status(project, action_id, "in-flight")
        try:
            result = _run_external(command, project.root, deadline, key)
        except OSError as exc:
            attempt["status"] = "error"
            try:
                response = _external_result(project, action_id, start_error=str(exc))
            finally:
                project.write_json(journal_name, attempt)
                _action_status(project, action_id, "error")
            raise ValueError(f"external command could not start; result: {response}") from exc
        except BaseException:
            attempt["status"] = "unknown"
            try:
                project.write_json(journal_name, attempt)
                _action_status(project, action_id, "unknown")
            except (OSError, ValueError):
                pass  # The pre-spawn journal still prohibits replay.
            raise
        status = "unknown" if getattr(result, "timed_out", False) else "done" if result.returncode == 0 else "error"
        attempt.update(status=status, returncode=result.returncode,
                         finished_at=dt.datetime.now(dt.timezone.utc).isoformat())
        # Preserve remote acceptance evidence even when the final ledger update
        # fails. The in-flight journal already makes a missing result non-replayable.
        try:
            response = _external_result(project, action_id, returncode=result.returncode,
                                        stdout=result.stdout, stderr=result.stderr,
                                        start_error="deadline or stream read failed; reconcile remote state" if status == "unknown" else "",
                                        stdout_omitted=getattr(result, "stdout_omitted", 0),
                                        stderr_omitted=getattr(result, "stderr_omitted", 0))
        finally:
            project.write_json(journal_name, attempt)
            _action_status(project, action_id, status)
        if status == "unknown":
            raise ValueError(f"external outcome unknown; reconcile before retry; result: {response}")
        if result.returncode:
            raise ValueError(f"external command failed (exit {result.returncode}); ledger status: error; result: {response}")
        return f"external {action_id}: done; result: {response}"


def safe_regex(pattern: str) -> re.Pattern:
    return ro_settings.safe_regex(pattern)


def _scan_settings(project, object_count: int = 0) -> tuple[list[re.Pattern], float]:
    """Patterns and the authoritative pre-push deadline from `Publish scan` (deadline=<N>s|m)."""
    raw = project.settings().get("publish_scan", "secrets")
    patterns = []
    deadline = min(PUSH_SCAN_MAX_SECONDS, PUSH_SCAN_SECONDS + object_count * PUSH_SCAN_OBJECT_SECONDS)
    for entry in re.split(r"\s*;\s*|,\s*(?=(?:secrets|literal:|regex:|deadline=))", raw):
        _remaining()
        entry = entry.strip()
        if entry == "secrets":
            patterns.extend(re.compile(pattern) for pattern in SECRET_PATTERNS)
        elif entry.startswith("literal:") and entry[8:]:
            if len(entry[8:]) > 1024:
                raise ValueError("publish literal is oversized")
            patterns.append(re.compile(re.escape(entry[8:])))
        elif entry.startswith("regex:"):
            patterns.append(safe_regex(entry[6:]))
        elif entry.startswith("deadline="):
            deadline = ro_settings.scan_deadline(entry)
        elif entry and entry != "none":
            raise ValueError("invalid Publish scan setting")
    return patterns, deadline


def _patterns(project) -> list[re.Pattern]:
    return _scan_settings(project)[0]


def _remaining() -> float:
    deadline = _SCAN_DEADLINE.get()
    remaining = deadline - time.monotonic() if deadline is not None else 30.0
    if remaining <= 0:
        raise ValueError("publish scan deadline exceeded")
    return remaining


def _git(project, *args: str) -> bytes:
    try:
        result = subprocess.run([*GIT, "-C", str(project.root), *args],
                                capture_output=True, check=False, timeout=_remaining(),
                                creationflags=no_window_flags())
    except subprocess.TimeoutExpired as exc:
        raise ValueError("publish scan deadline exceeded running git") from exc
    except OSError as exc:
        raise ValueError("publish scan could not run git") from exc
    if result.returncode:
        raise ValueError("publish scan could not read outgoing git objects")
    return result.stdout


def _staged_diff(project, checkout=None) -> bytes:
    """Bound bytes read, not merely bytes inspected, and terminate only this owned git process."""
    try:
        process = subprocess.Popen([*GIT, "-C", str(checkout or project.root), "diff", "--cached",
                                    "--no-ext-diff", "--no-textconv", "--no-color", "--unified=0"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=no_window_flags())
    except OSError as exc:
        raise ValueError("publish scan could not run git") from exc
    read_result = queue.Queue(maxsize=1)
    def read_capped():
        try:
            read_result.put(process.stdout.read(DIFF_CAP + 1))
        except Exception as exc:
            read_result.put(exc)
    reader = threading.Thread(target=read_capped, daemon=True)
    reader.start()
    try:
        try:
            data = read_result.get(timeout=_remaining())
        except queue.Empty:
            raise ValueError("publish scan deadline exceeded reading staged content") from None
        if isinstance(data, Exception):
            raise ValueError("publish scan could not read staged content") from data
        if len(data) > DIFF_CAP:
            process.terminate()
        process.wait(timeout=min(5, _remaining()))
        if process.returncode and len(data) <= DIFF_CAP:
            raise ValueError("publish scan could not read staged content")
        return data[:DIFF_CAP]
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise ValueError("publish scan timed out reading staged content") from exc
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        reader.join(timeout=1)
        process.stdout.close()


class PublishScanTimeout(ValueError):
    """Trusted timeout fields; public diagnostics never copy Git output or exception text."""

    def __init__(self, object_count: int | None, seconds: float):
        self.object_count = object_count
        self.retry_seconds = min(int(PUSH_SCAN_MAX_SECONDS), max(1, math.ceil(seconds * 2)))
        detail = (f"{object_count} outgoing objects" if object_count is not None else
                  "outgoing object count unavailable before enumeration completed")
        hint = (f"set deadline={self.retry_seconds}s in Publish scan and retry"
                if seconds < PUSH_SCAN_MAX_SECONDS else
                f"deadline={self.retry_seconds}s is the maximum Publish scan setting; inspect scan performance before retrying")
        self.diagnostic = f"publish scan deadline exceeded ({detail}); {hint}"
        super().__init__(self.diagnostic)


def scan_publish(project, refs: str | None = None, remote: str | None = None, checkout=None) -> list[str]:
    """Staged pre-check (refs None, SCAN_SECONDS) or the authoritative pre-push scan (configured deadline).

    The staged pre-check reads `checkout` (the pushing command's working directory) with the
    project's policy; the pre-push scan always runs in the repository Git invoked it from."""
    seconds = SCAN_SECONDS
    if refs is not None:
        token = _SCAN_DEADLINE.set(time.monotonic() + SCAN_SECONDS)
        try:
            seconds = _scan_settings(project)[1]
        finally:
            _SCAN_DEADLINE.reset(token)
    started = time.monotonic()
    token = _SCAN_DEADLINE.set(started + seconds)
    progress = {"objects": None, "seconds": seconds, "started": started}
    progress_token = _SCAN_PROGRESS.set(progress)
    try:
        return _scan_publish(project, refs, remote, checkout)
    except ValueError as exc:
        if refs is not None and "deadline exceeded" in str(exc):
            raise PublishScanTimeout(progress["objects"], progress["seconds"]) from exc
        raise
    finally:
        _SCAN_PROGRESS.reset(progress_token)
        _SCAN_DEADLINE.reset(token)


def first_match(patterns: list[re.Pattern], chunks) -> int | None:
    """Return the 1-based line of the earliest accepted match in streamed bytes, or None.

    Windows of WINDOW characters keep OVERLAP characters of context on both sides: bounded user
    patterns span at most 511 characters and literals at most 1024, so a match cut by a window
    edge is found whole in the next window. A match touching the window end counts only at the
    end of the data, where lookaheads see the real end.
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    iterator = iter(chunks)
    text, position, lines, exhausted = "", 0, 0, False
    while True:
        while not exhausted and len(text) - position < WINDOW + OVERLAP:
            chunk = next(iterator, None)
            if chunk is None:
                text += decoder.decode(b"", final=True)
                exhausted = True
            else:
                text += decoder.decode(chunk)
        end = min(len(text), position + WINDOW + OVERLAP)
        best = None
        for pattern in patterns:
            _remaining()
            found = pattern.search(text, position, end)
            if found and (found.end() < end or (exhausted and end == len(text))):
                best = found.start() if best is None else min(best, found.start())
        if best is not None:
            return lines + text.count("\n", 0, best) + 1
        if exhausted and end == len(text):
            return None
        position += WINDOW
        cut = max(0, position - OVERLAP)  # Keep context for anchors and lookbehinds.
        lines += text.count("\n", 0, cut)
        text, position = text[cut:], position - cut


def _shown(path: bytes, patterns: list[re.Pattern]) -> str | None:
    """A displayable path, or None when the name itself matches a pattern."""
    if first_match(patterns, [path]) is not None:
        return None
    name = "".join(char if char.isprintable() else "?" for char in path.decode("utf-8", errors="replace"))
    return name if len(name) <= 200 else name[:97] + "..." + name[-100:]


def _staged_findings(data: bytes, patterns: list[re.Pattern]) -> list[str]:
    """Report the path and new-file line of each staged addition that matches, never its text."""
    findings, path, line = [], None, 0
    for raw in data.splitlines():
        _remaining()
        if raw.startswith(b"+++ "):
            path = raw[6:] if raw.startswith(b"+++ b/") else None
        elif raw.startswith(b"@@"):
            hunk = re.match(rb"@@ -\S+ \+(\d+)", raw)
            line = int(hunk[1]) if hunk else 0
        elif raw.startswith(b"+"):
            if first_match(patterns, [raw[1:]]) is not None:
                shown = _shown(path, patterns) if path else None
                where = f" at {shown}:{line}" if shown and line else ""
                findings.append(f"publish.scan: staged content matched{where}; content redacted")
            line += 1
    return findings


class _Batch:
    """One `git cat-file --batch` process streams every outgoing object; a timer ends it at the deadline."""

    def __init__(self, project, oids: list[str]):
        _remaining()
        try:
            self.process = subprocess.Popen([*GIT, "-C", str(project.root), "cat-file", "--batch"],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, creationflags=no_window_flags())
        except OSError as exc:
            raise ValueError("publish scan could not run git") from exc
        self.left = 0
        self.expired = threading.Event()

        def expire():
            self.expired.set()
            try:
                self.process.kill()
            except OSError:
                pass

        try:
            remaining = _remaining()
        except ValueError:
            expire()
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            raise
        self.timer = threading.Timer(remaining, expire)
        self.timer.daemon = True
        self.timer.start()
        payload = "".join(oid + "\n" for oid in oids).encode("ascii")

        def feed():
            try:
                self.process.stdin.write(payload)
                self.process.stdin.close()
            except (OSError, ValueError):
                pass  # A killed process surfaces as a short read.
        self.writer = threading.Thread(target=feed, daemon=True)
        self.writer.start()

    def _failed(self):
        if self.expired.is_set():
            raise ValueError("publish scan deadline exceeded reading outgoing git objects")
        _remaining()  # Report an expired deadline as such.
        raise ValueError("publish scan could not read outgoing git objects")

    def read(self, oid: str):
        header = self.process.stdout.readline().split()
        if len(header) != 3 or header[0].decode("ascii", errors="replace") != oid or not header[2].isdigit():
            self._failed()
        self.left = int(header[2])
        return header[1].decode("ascii", errors="replace"), self._chunks()

    def _chunks(self):
        while self.left:
            _remaining()
            data = self.process.stdout.read(min(self.left, 1 << 20))
            if not data:
                self._failed()
            self.left -= len(data)
            yield data

    def finish_object(self) -> None:
        """Discard the unread rest of an object after an early match, then its separator."""
        for _ in self._chunks():
            pass
        if self.process.stdout.read(1) != b"\n":
            self._failed()

    def close(self) -> None:
        self.timer.cancel()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.writer.join(timeout=1)
        self.process.stdout.close()


def _cache(project, patterns: list[re.Pattern]) -> tuple[str, list[str]]:
    """Objects already scanned clean under the same patterns; an object ID never changes content."""
    key = hashlib.sha256("\n".join(pattern.pattern for pattern in patterns).encode("utf-8")).hexdigest()
    try:
        # Derived cache data can be discarded; cap the read before parsing so a
        # damaged or unexpectedly large cache cannot consume the scan's budget.
        with (project.state / SCAN_CACHE).open("rb") as source:
            raw = source.read(SCAN_CACHE_BYTES + 1)
        data = json.loads(raw) if len(raw) <= SCAN_CACHE_BYTES else {}
    except (OSError, ValueError):
        data = {}
    objects = data.get("objects") if isinstance(data, dict) and data.get("patterns") == key else None
    return key, [oid for oid in objects[-SCAN_CACHE_LIMIT:] if isinstance(oid, str) and OID.fullmatch(oid)] \
        if isinstance(objects, list) else []


def _remember(project, key: str, previous: list[str], clean: list[str]) -> None:
    if not clean:
        return
    try:
        known = list(dict.fromkeys([*previous, *clean]))[-SCAN_CACHE_LIMIT:]
        project.write_json(SCAN_CACHE, {"patterns": key, "objects": known})
    except Exception:
        pass  # The cache only saves time; without it the next scan is complete.


def _introduced(project, oid: str, revisions: list[str]) -> str:
    """The first outgoing commit that adds or removes a matched blob or tree, for history repair."""
    try:
        commits = _git(project, "log", "--format=%H", "--reverse", "--find-object=" + oid, *revisions, "--").split()
    except ValueError:
        return ""
    first = commits[0].decode("ascii", errors="replace") if commits else ""
    return f" (commit {first[:12]})" if OID.fullmatch(first) else ""


def _finding(kind: str, oid: str, path: bytes, line: int, patterns: list[re.Pattern], commit: str = "") -> str:
    short = oid[:12]
    if kind == "blob":
        shown = _shown(path, patterns) if path else None
        where = f"{shown}:{line}" if shown else f"blob {short} line {line}"
        return f"publish.scan: outgoing content matched at {where}{commit}; content redacted"
    if kind == "tree":
        return f"publish.scan: outgoing file name in tree {short} matched{commit}; content redacted"
    if kind == "tag":
        return f"publish.scan: outgoing annotated tag {short} matched; content redacted"
    return f"publish.scan: outgoing commit {short} matched; content redacted"


def _scan_publish(project, refs: str | None = None, remote: str | None = None, checkout=None) -> list[str]:
    """Scan staged additions as a capped pre-check, or every outgoing object from pre-push refs.

    Outgoing objects are what `git rev-list --objects` reaches from the pushed tips but not from
    destination tips supplied by Git's pre-push invocation and available locally. Tracking
    refs cannot establish what the push destination possesses: fetch/push URLs may differ,
    or a remote may have been retargeted. The remote argument remains for caller compatibility
    but never widens exclusions. New refs conservatively scan their reachable history.
    Commits, annotated tags (nested ones and non-commit targets too), trees (file
    names) and blobs are read through one batch process. Object IDs, never repository strings,
    select objects. Findings name a path and line or an object ID, never matching content.
    """
    patterns = _patterns(project)
    if not patterns:
        return []
    if refs is None:
        # Explicitly disable repository-configured diff programs and text converters.
        return _staged_findings(_staged_diff(project, checkout), patterns)
    positives, negatives = [], []
    for line in refs.splitlines():
        _remaining()
        if not line.strip():
            continue
        values = line.split()
        if len(values) != 4 or not all(OID.fullmatch(values[index]) for index in (1, 3)):
            raise ValueError("malformed pre-push refs")
        local, old = values[1], values[3]
        if not local.strip("0"):
            continue  # Deletions carry no outgoing content.
        positives.append(local)
        if old.strip("0"):
            # A force-push still excludes only objects reachable from the old remote tip; an
            # unknown remote object cannot be excluded, so the scan stays conservative.
            try:
                _git(project, "cat-file", "-e", old + "^{commit}")
                negatives.append(old)
            except ValueError:
                pass
    if not positives:
        return []
    objects: dict[str, bytes] = {}
    for raw in _git(project, "rev-list", "--objects", *positives, "--not", *negatives, "--").splitlines():
        _remaining()
        oid, _, path = raw.partition(b" ")
        oid = oid.decode("ascii", errors="replace")
        if not OID.fullmatch(oid):
            raise ValueError("invalid outgoing object")
        objects.setdefault(oid, path)
    progress = _SCAN_PROGRESS.get()
    if progress is not None:
        progress["objects"] = len(objects)
        # A configured deadline remains authoritative; only the default scales.
        progress["seconds"] = _scan_settings(project, len(objects))[1]
        _SCAN_DEADLINE.set(progress["started"] + progress["seconds"])
    key, cached = _cache(project, patterns)
    skip = set(cached)
    pending = [oid for oid in objects if oid not in skip]
    findings, clean = [], []
    if pending:
        batch = _Batch(project, pending)
        try:
            for oid in pending:
                kind, chunks = batch.read(oid)
                line = first_match(patterns, chunks)
                batch.finish_object()
                if line is None:
                    clean.append(oid)
                else:
                    findings.append((kind, oid, line))
        finally:
            batch.close()
    _remember(project, key, cached, clean)
    revisions = [*positives, "--not", *negatives]
    return [_finding(kind, oid, objects[oid], line, patterns,
                     _introduced(project, oid, revisions) if kind in ("blob", "tree") else "")
            for kind, oid, line in findings]
