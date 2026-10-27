"""Export reviewable evaluation evidence with source and sanitized SHA-256 links.

The archive is for independent inspection, not a replacement for original runs:
absolute host paths and credential-shaped JSON values are removed, and every
omission is recorded. Exclusions and grades are carried verbatim apart from this
sanitization. No model run or successful result is inferred by this exporter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

try:
    from scripts.publication_safety import sanitize_text, RAW_MEMBER
except ModuleNotFoundError:  # direct script invocation
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.publication_safety import sanitize_text, RAW_MEMBER


_PRIVATE_KEY = re.compile(r"^(?:authorization|api[_-]?key|access[_-]?token|password|secret|capture_secret)$", re.I)
_ROOT_FILES = {"benchmark.json", "benchmark.md", "analyst-notes.json", "analysis-data.json", "results.json",
               "regrade.py", "regrade-changes.json", "source-sha256.json", "preservation-check.json"}
_RUN_FILES = {"run.json", "timing.json", "grading.json", "grading-status.json", "grading_status.json",
              "eval_metadata.json", "metrics.json"}
_SKIP_PARTS = {"__pycache__", ".git", ".eval-tmp", ".pytest_cache"}
_OUTPUT_SUFFIXES = {".md", ".txt", ".csv", ".tsv", ".json", ".py", ".sh", ".yaml", ".yml", ".toml"}
_INTERNAL_KEYS = {"session_id", "thread_id", "command", "isolation", "stdout", "stderr", "events",
                  "transcript", "available_skills", "installed_plugins", "rate_limits", "skills",
                  "plugins", "disconnect_evidence", "rate_limit_evidence", "native_terminal_event",
                  "tool_call_id", "commands", "command_history", "environment", "env",
                  "contamination", "raw_events", "tool_events", "installed_skills", "inventory"}
_ENCODED_STREAM = re.compile(r"^(?:(?:stdout|stderr)[_-]?(?:b64|base64)|(?:b64|base64)[_-]?(?:stdout|stderr))$", re.I)


def publishable(name: str, *, include_outputs: bool = False) -> bool:
    path = Path(name)
    if "outputs" in path.parts:
        return (include_outputs and path.suffix.lower() in _OUTPUT_SUFFIXES
                and not RAW_MEMBER.search(name)
                and not any(part.lower() in {"inventory", "inventories", ".codex", ".claude"} for part in path.parts)
                and not re.search(r"(?:transcript|events|inventory|inventories|stderr)", path.name, re.I))
    return (not RAW_MEMBER.search(name) and "outputs" not in path.parts
            and (path.name in _ROOT_FILES or path.name in _RUN_FILES or "recovered-grades" in path.parts))


def sanitize_json(value):
    if isinstance(value, dict):
        return {sanitize_text(key): "<redacted>" if _PRIVATE_KEY.fullmatch(key) else sanitize_json(item)
                for key, item in value.items()
                if key.lower() not in _INTERNAL_KEYS and not _ENCODED_STREAM.fullmatch(key)}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    return sanitize_text(value) if isinstance(value, str) else value


def sanitized_bytes(path: Path, raw: bytes) -> bytes:
    text = raw.decode("utf-8-sig")
    if path.suffix == ".json":
        return (json.dumps(sanitize_json(json.loads(text)), ensure_ascii=False, indent=2) + "\n").encode()
    if path.suffix == ".jsonl":
        # Keep malformed lines for diagnosis rather than dropping a failed run.
        lines = []
        for line in text.splitlines():
            try:
                lines.append(json.dumps(sanitize_json(json.loads(line)), ensure_ascii=False))
            except ValueError:
                lines.append(sanitize_text(line))
        return ("\n".join(lines) + "\n").encode()
    return sanitize_text(text).encode()


def export_evidence(sources: dict[str, Path], target: Path, *, private_terms: tuple[str, ...] = (),
                    include_outputs: bool = False) -> dict:
    if target.exists():
        raise ValueError("Evidence target already exists")
    if any(not re.fullmatch(r"[a-z][a-z0-9-]*", namespace) for namespace in sources):
        raise ValueError("Evidence namespaces must be lowercase directory names")
    entries, omitted = [], []
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for namespace, source in sources.items():
            if source.is_symlink() or source.is_junction() or not source.is_dir():
                raise ValueError("Evidence source must be a plain directory")
            for path in sorted(source.rglob("*")):
                relative = path.relative_to(source)
                name = f"{namespace}/{relative.as_posix()}"
                if path.is_symlink() or path.is_junction():
                    raise ValueError("Evidence source contains a link")
                if not path.is_file():
                    continue
                reason = None
                if _SKIP_PARTS.intersection(relative.parts) or path.suffix in {".pyc", ".pyo"}:
                    reason = "runtime cache"
                elif not publishable(relative.as_posix(), include_outputs=include_outputs):
                    reason = "withheld raw material; publish only grades, summaries, procedure and hashes"
                raw = path.read_bytes()
                original = hashlib.sha256(raw).hexdigest()
                if reason is None:
                    try:
                        data = sanitized_bytes(path, raw)
                        for term in private_terms:
                            if term:
                                data = re.sub(re.escape(term.encode()), b"<private-host>", data, flags=re.I)
                    except (UnicodeDecodeError, ValueError):
                        reason = "non-UTF-8 or invalid structured artifact; retained source digest only"
                if reason:
                    omitted.append({"path": sanitize_text(name, private_terms), "source_sha256": original, "reason": reason})
                    continue
                public_name = sanitize_text(name, private_terms)
                archive.writestr(public_name, data)
                entries.append({"path": public_name, "source_sha256": original,
                                "export_sha256": hashlib.sha256(data).hexdigest(),
                                "source_bytes": len(raw), "export_bytes": len(data)})
        manifest = {"schema_version": 1, "purpose": "sanitized independent review",
                    "sanitization": "absolute paths and account names masked; native identifiers, inventories and encoded text streams withheld; no transcripts",
                    "limitations": "Hashes link original bytes to exported bytes; sanitized paths cannot be replayed. "
                                    "Original exclusions remain authoritative; this archive proves no new execution.",
                    "task_outputs_included": include_outputs,
                    "files": entries, "omitted": omitted}
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify_evidence(target: Path) -> int:
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        expected = {entry["path"] for entry in manifest["files"]} | {"manifest.json"}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError("Evidence member inventory mismatch")
        for entry in manifest["files"]:
            if hashlib.sha256(archive.read(entry["path"])).hexdigest() != entry["export_sha256"]:
                raise ValueError(f"Evidence digest mismatch: {entry['path']}")
    return len(manifest["files"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[], metavar="NAME=DIRECTORY")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--redact", action="append", default=[], help="Private host/user text to remove")
    parser.add_argument("--include-outputs", action="store_true", help="Include sanitized UTF-8 task files; raw streams and binary containers remain withheld")
    args = parser.parse_args()
    if args.verify:
        print(f"Verified {verify_evidence(args.output)} evidence artifacts")
        return 0
    sources = {}
    for value in args.source:
        namespace, directory = value.split("=", 1)
        if namespace in sources:
            parser.error("Duplicate source namespace")
        sources[namespace] = Path(directory)
    if not sources:
        parser.error("At least one --source is required")
    manifest = export_evidence(sources, args.output, private_terms=tuple(args.redact), include_outputs=args.include_outputs)
    print(f"Exported {len(manifest['files'])} artifacts; {len(manifest['omitted'])} documented omissions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
