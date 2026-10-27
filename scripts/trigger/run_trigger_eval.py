#!/usr/bin/env python3
"""Measure native Codex skill selection, without modifying installed skills/config.

See README.md for discovery, the evidence rule, and coordinator-only execution.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.evals import isolation
from scripts.evals.proc import no_window_flags
from scripts.evals.contamination import audit_run, _host_path, _normal
from scripts.evals.command_trace import _source, _statements
from scripts.evals.run_evals import (RateLimitThrottle, disconnect_evidence, parse_events, rate_limit_evidence,
                                     resolve_codex, terminal_transport_category, total_tokens)
from scripts.trigger.selection_stream import stream_selection
from scripts.trigger.outcomes import inconclusive_reason

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL = ROOT / "skills" / "research-orchestrator" / "SKILL.md"
DEFAULT_QUERIES = Path(__file__).with_name("queries.json")


def skill_field(text: str, key: str) -> tuple[str, tuple[int, int]]:
    """Read the scalar metadata used by this skill; reject unsupported YAML shapes."""
    front = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    if not front:
        raise ValueError("SKILL.md needs YAML frontmatter")
    matches = list(re.finditer(rf"(?m)^{re.escape(key)}:([^\n]*)(?:\n[ \t]+[^\n]*)*", front[1]))
    if len(matches) != 1:
        raise ValueError(f"Expected one {key} scalar in frontmatter")
    match = matches[0]
    raw = match[0].split(":", 1)[1].strip()
    if raw.startswith(('"', "'")):
        if raw.startswith('"'):
            value = json.loads(raw)
        elif raw.endswith("'"):
            value = raw[1:-1].replace("''", "'")
        else:
            raise ValueError(f"Invalid quoted {key}")
    elif raw.splitlines()[0] in {"|", "|-", "|+", ">", ">-", ">+"}:
        lines = raw.splitlines()
        value = (" " if lines[0].startswith(">") else "\n").join(line.strip() for line in lines[1:])
    elif "\n" in raw or raw.startswith(("[", "{", "&", "*")):
        raise ValueError(f"Unsupported YAML {key}; use a quoted string")
    else:
        value = raw
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Empty {key}")
    return value.strip(), (front.start(1) + match.start(), front.start(1) + match.end())


def candidate_skill(text: str, description: str | None) -> tuple[str, str, str]:
    name, _ = skill_field(text, "name")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError("Skill name must be a safe lowercase directory name")
    original, span = skill_field(text, "description")
    if description is None:
        return name, original, text
    description = description.strip()
    if not description or len(description) > 1024:
        raise ValueError("Candidate description must contain 1–1024 characters")
    return name, description, text[:span[0]] + "description: " + json.dumps(description, ensure_ascii=False) + text[span[1]:]


def load_queries(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Queries must be a nonempty JSON array")
    seen = set()
    for row in data:
        if (not isinstance(row, dict) or not isinstance(row.get("query"), str)
                or not row["query"].strip() or type(row.get("should_trigger")) is not bool):
            raise ValueError("Each query needs nonempty query text and boolean should_trigger")
        if row["query"] in seen:
            raise ValueError("Duplicate query text would contaminate the held-out split")
        seen.add(row["query"])
    if any(sum(row["should_trigger"] == flag for row in data) < 2 for flag in (True, False)):
        raise ValueError("At least two examples of each class are needed for a held-out split")
    return data


def split_queries(queries: list[dict], seed: int = 42) -> dict[int, str]:
    """Skill-creator's stratified 60/40 split, stable for a frozen query set/seed."""
    rng = random.Random(seed)
    split = {}
    for flag in (True, False):
        indices = [i for i, row in enumerate(queries) if row["should_trigger"] == flag]
        rng.shuffle(indices)
        holdout = max(1, int(len(indices) * 0.4))
        split.update({i: "test" if n < holdout else "train" for n, i in enumerate(indices)})
    return split


def installed_inventory(name: str, project: Path, context: dict) -> dict:
    """Enumerate external roots, including linked skills; never change their files."""
    roots = [Path(p) for p in context["installed_skill_roots"]]
    roots += [Path("/etc/codex/skills")]
    for ancestor in project.parents:
        roots.extend(ancestor / folder / "skills" for folder in (".agents", ".codex"))
    roots = list(dict.fromkeys(roots))
    manifests, errors, visited = set(), [], set()

    def walk(folder: Path):
        try:
            resolved = folder.resolve()
            if resolved in visited:
                return
            visited.add(resolved)
            for entry in folder.iterdir():
                if entry.is_file() and entry.name.casefold() == "skill.md":
                    manifests.add(entry.absolute())
                elif entry.is_dir():
                    walk(entry)
        except OSError as exc:
            errors.append(f"Cannot inventory {folder}: {exc}")

    for root in roots:
        try:
            root.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"Cannot inventory {root}: {exc}")
        else:
            walk(root)
    duplicates = []
    for path in sorted(manifests):
        try:
            same_name = skill_field(path.read_text(encoding="utf-8-sig"), "name")[0] == name
        except (ValueError, OSError):
            same_name = path.parent.name == name
        if same_name:
            duplicates.append(str(path))
    # Include lexical and canonical selectors: installed skills may be symlinks.
    disabled = sorted({str(p) for path in manifests for p in (path, path.resolve())})
    return {"roots": [str(p) for p in roots], "disabled_manifests": disabled,
            "same_name_copies": duplicates, "errors": errors}


def invocation_config(settings: dict, inventory: dict) -> list[str]:
    args = isolation.config_arguments(settings)
    replacements = {"skills.include_instructions=false": "skills.include_instructions=true",
                    "features.skip_host_skill_discovery=true": "features.skip_host_skill_discovery=false",
                    "project_root_markers=[]": 'project_root_markers=[".git"]'}
    args = [replacements.get(arg, arg) for arg in args]
    selectors = ",".join("{path=" + json.dumps(path) + ",enabled=false}"
                         for path in inventory["disabled_manifests"])
    return [*args, "-c", f"skills.config=[{selectors}]", "-c", "project_doc_max_bytes=0"]


def build_command(codex: str, project: Path, query: str, settings: dict, inventory: dict,
                  model: str | None = None) -> list[str]:
    return [codex, "exec", "--json", "--skip-git-repo-check", "--strict-config", "-s", "read-only", "-C", str(project),
            *invocation_config(settings, inventory), *(["--model", model] if model else []), "--", query]


def detect_trigger(events: list[dict], candidate: Path, name: str, project: Path,
                   host_context: dict) -> dict:
    """Use completed reads or an affirmative assistant use announcement, not echoes."""
    evidence, suspicious, unconfirmed = [], [], []
    expected = _normal(str(candidate))
    for number, event in enumerate(events, 1):
        item = event.get("item", event)
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if event.get("type") not in {"item.completed", "agent_message", "file_read", "read_file"}:
            continue
        if kind == "agent_message":
            text = item.get("text", "")
            for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
                if name not in sentence:
                    continue
                prefix = sentence.split(name, 1)[0]
                if re.search(r"\b(?:not|no|don't|won't|without|skip|unnecessary|unneeded|if|would|could|should)\b", prefix, re.I):
                    continue
                if re.search(r"\bif\b|\b(?:unnecessary|unneeded)\b", sentence.split(name, 1)[1], re.I):
                    continue
                announcement = re.match(
                    r"^[* _-]*(?:(?:I|we)(?:(?:['’](?:m|re|ll))|\s+(?:am|are|will))?\s+)"
                    r"(?:use|using|apply|applying|consult|consulting|follow|following|read|reading)\b"
                    r"|^[* _-]*(?:using|applying|consulting|following|reading)\b", sentence, re.I)
                if announcement:
                    evidence.append({"event": number, "kind": "name", "text": sentence})
        elif kind in {"command_execution", "file_read", "read_file"}:
            text = str(item.get("command", item.get("path", item.get("file_path", ""))))
            cwd = item.get("cwd", item.get("workdir", str(project)))
            statements = list(_statements(_source(text))) if kind == "command_execution" else []
            literals = [word for words in statements for word in words[1:]] if statements else [text]
            paths = {_normal(_host_path(p, host_context), cwd) for p in literals}
            real_paths = {_normal(_host_path(p, host_context), cwd): Path(cwd) / _host_path(p, host_context)
                          for p in literals}
            successful = (item.get("exit_code") == 0 if kind == "command_execution"
                          else item.get("status") == "completed" or item.get("success") is True)
            successful &= not item.get("error") and item.get("success") is not False and item.get("status", "completed") == "completed"
            read_paths = paths if kind != "command_execution" else set()
            if kind == "command_execution":
                for words in statements:
                    if words and words[0] == "&":
                        words = words[1:]
                    if not words:
                        continue
                    executable = words[0].replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")
                    # Require the target in this read statement, not in an echo
                    # elsewhere in a compound command. Opaque interpreter bodies
                    # need a use announcement instead of speculative parsing.
                    nonreads = {"--help", "-h", "-?", "--version", "--files", "--files-with-matches", "--files-without-match"}
                    if any(word.casefold() in nonreads for word in words[1:]):
                        continue
                    if executable in {"get-content", "gc", "cat", "type", "more", "less", "head", "tail", "sed", "rg", "grep"}:
                        read_paths.update(_normal(_host_path(p, host_context), cwd) for p in words[1:])
            if expected in read_paths and successful:
                evidence.append({"event": number, "kind": "read", "command": text})
            for path in paths:
                if path.endswith(f"/{name}/skill.md") and path != expected:
                    finding = {"event": number, "path": path}
                    # Missing guessed manifests cannot supply skill context.
                    # The access audit handles source-read attribution in detail.
                    if successful and path in read_paths and real_paths[path].is_file():
                        suspicious.append(finding)
                    else:
                        unconfirmed.append(finding)
    return {"triggered": bool(evidence), "evidence": evidence, "other_skill_paths": suspicious,
            "unconfirmed_skill_paths": unconfirmed}


def run_query(query: str, *, name: str, skill_text: str, run_dir: Path, temp_parent: Path,
              codex: str, settings: dict, model: str | None, timeout: float, retries: int,
              throttle: RateLimitThrottle | None = None) -> dict:
    run_dir.mkdir(parents=True, exist_ok=False)
    throttle = throttle or RateLimitThrottle()
    attempts = []
    for attempt in range(1, retries + 2):
        attempt_dir = run_dir / f"attempt-{attempt}"
        attempt_dir.mkdir()
        root = Path(tempfile.mkdtemp(prefix="ro-trigger-", dir=temp_parent)).resolve()
        start = time.monotonic()
        record = {"attempt": attempt, "project": str(root), "status": "error", "triggered": None}
        try:
            (root / ".git").mkdir()  # Discovery boundary, no repository content needed.
            candidate = root / ".agents" / "skills" / name / "SKILL.md"
            candidate.parent.mkdir(parents=True)
            candidate.write_text(skill_text, encoding="utf-8", newline="\n")
            environment, metadata = isolation.prepare_environment(root, root, settings)
            inventory = installed_inventory(name, root, metadata["host_context"])
            record["isolation"] = {"installed": inventory, "host_context": metadata["host_context"],
                                   "candidate": str(candidate), "credential_files_accessed": False}
            if inventory["errors"]:
                raise ValueError("; ".join(inventory["errors"]))
            command = build_command(codex, root, query, settings, inventory, model)
            record["command"] = command
            throttle.wait()
            proc = stream_selection(command, cwd=root, env=environment, timeout=timeout,
                                    on_event=lambda items: detect_trigger(
                                        items, candidate, name, root, metadata["host_context"])["triggered"])
            raw, stderr, returncode, timed_out = proc.stdout, proc.stderr, proc.returncode, proc.timed_out
            (attempt_dir / "events.jsonl").write_text(raw, encoding="utf-8")
            (attempt_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
            (attempt_dir / "events-after-selection.jsonl").write_text(proc.after_selection, encoding="utf-8")
            events = parse_events(raw)
            completed = bool(events) and events[-1].get("type") == "turn.completed"
            success = (proc.boundary_event is not None or returncode == 0 and completed) and not timed_out
            failure = terminal_transport_category(raw, stderr) if not success else None
            rate_evidence = rate_limit_evidence(raw, stderr)
            delay = throttle.defer(rate_evidence, attempt) if failure == "rate_limit" and not timed_out else 0.0
            detection = detect_trigger(events, candidate, name, root, metadata["host_context"])
            context = {**metadata["host_context"], "installed_skill_roots": inventory["roots"]}
            audit = audit_run(attempt_dir, source_repo=ROOT, workspace=run_dir.parent,
                              project=root, runtime=candidate.parent, host_context=context)
            changed = candidate.read_text(encoding="utf-8") != skill_text
            contaminated = audit["contaminated"] or changed or bool(detection["other_skill_paths"])
            status = "contaminated" if contaminated else "ok" if success else "timeout" if timed_out else "error"
            record.update(status=status, returncode=returncode, detection=detection, contamination=audit,
                          candidate_changed=changed, tokens=total_tokens(events),
                          measurement_protocol="first-selection-v1",
                          selection_boundary={"event": proc.boundary_event, "process_stopped": True}
                                             if proc.boundary_event is not None else None,
                          triggered=detection["triggered"] if status == "ok" else None,
                          disconnect_evidence=disconnect_evidence(raw, stderr),
                          rate_limit_evidence=rate_evidence, retry_delay_seconds=delay,
                          failure_category="timeout" if timed_out else failure or (None if success else "executor"),
                          retryable=not success and not contaminated and bool(failure)
                                    and not (timed_out and failure == "rate_limit"))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            record.update(error=str(exc), failure_category="setup", retryable=False)
        finally:
            record["duration_seconds"] = round(time.monotonic() - start, 3)
            record["cleanup"] = isolation.cleanup(root)
            record["inconclusive_reason"] = inconclusive_reason(record)
            (attempt_dir / "run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            attempts.append(record)
        if not record.get("retryable"):
            break
    return {"status": attempts[-1]["status"], "triggered": attempts[-1]["triggered"],
            "inconclusive_reason": attempts[-1]["inconclusive_reason"],
            "attempts": attempts, "artifact_dir": str(run_dir)}


def summarize(rows: list[dict], threshold: float, expected_repeats: int | None = None) -> dict:
    counts = dict(tp=0, fp=0, tn=0, fn=0, inconclusive=0)
    results = []
    for row in rows:
        values = [run.get("triggered") if isinstance(run, dict) else None for run in row["runs"]]
        reasons = [{"repeat": number, **reason}
                   for number, run in enumerate(row["runs"], 1)
                   if (reason := inconclusive_reason(run)) is not None]
        if not values:
            reasons.append({"repeat": None, "code": "missing_repeats", "detail": "No repeats were recorded."})
        elif expected_repeats is not None and len(values) != expected_repeats:
            reasons.append({"repeat": None, "code": "repeat_count_mismatch",
                            "detail": f"Expected {expected_repeats} repeats; recorded {len(values)}."})
        valid = not reasons
        rate = sum(values) / len(values) if valid else None
        predicted = rate >= threshold if valid else None
        key = "inconclusive" if not valid else ("t" if predicted == row["should_trigger"] else "f") + ("p" if predicted else "n")
        counts[key] += 1
        results.append({**row, "trigger_rate": rate, "predicted": predicted,
                        "inconclusive_reasons": reasons,
                        "pass": predicted == row["should_trigger"] if valid else None})
    tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
    scored = tp + fp + tn + fn
    return {"counts": counts, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "accuracy": (tp + tn) / scored if scored else None,
            "coverage": scored / len(rows) if rows else None, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--description", type=Path, help="UTF-8 description text; source SKILL.md is never edited")
    parser.add_argument("--output", type=Path, required=True, help="New result directory (never overwritten)")
    parser.add_argument("--temp-parent", type=Path, help="Accessible scratch directory outside the repository")
    parser.add_argument("--split", choices=("train", "test", "all"), default="all")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--retries", type=int, default=3,
                        help="Fresh-session retries for transport/rate-limit failures (default: 3)")
    parser.add_argument("--model")
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args(argv)
    if min(args.repeats, args.jobs, args.timeout) <= 0 or args.retries < 0 or not 0 < args.threshold <= 1:
        parser.error("Positive repeats/jobs/timeout, nonnegative retries, and threshold in (0,1] required")
    try:
        queries = load_queries(args.queries)
        name, description, skill_text = candidate_skill(args.skill.read_text(encoding="utf-8-sig"),
            args.description.read_text(encoding="utf-8-sig") if args.description else None)
        split = split_queries(queries, args.seed)
        settings = isolation.configured_model_settings()
        codex = resolve_codex(args.codex)
        version = subprocess.run([codex, "--version"], stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, encoding="utf-8", timeout=15, check=True,
                                 creationflags=no_window_flags()).stdout.strip()
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
        # Windows' sandbox account cannot traverse every real-user temp folder.
        temp_parent = (args.temp_parent or ROOT.parent / "research-orchestrator-workspace" / "_trigger-runs").resolve()
        temp_parent.mkdir(parents=True, exist_ok=True)
        if temp_parent.is_relative_to(ROOT):
            raise ValueError("--temp-parent must be outside this source repository")
        selected = [(i, row) for i, row in enumerate(queries) if args.split in ("all", split[i])]
        rows = [{**row, "query_index": i, "split": split[i], "runs": []} for i, row in selected]
        throttle = RateLimitThrottle()
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            pending = [(row, executor.submit(run_query, row["query"], name=name, skill_text=skill_text,
                        run_dir=output / f"query-{row['query_index'] + 1:02d}-repeat-{repeat + 1}",
                        temp_parent=temp_parent, codex=codex, settings=settings, model=args.model,
                        timeout=args.timeout, retries=args.retries, throttle=throttle))
                       for row in rows for repeat in range(args.repeats)]
            for row, future in pending:
                row["runs"].append(future.result())
        report = {"host_version": version, "requested_model": args.model, "skill_name": name,
                  "measurement_protocol": "first-selection-v1",
                  "description": description, "description_sha256": hashlib.sha256(description.encode()).hexdigest(),
                  "skill_sha256": hashlib.sha256(skill_text.encode()).hexdigest(),
                  "queries_sha256": hashlib.sha256(args.queries.read_bytes()).hexdigest(),
                  "created_at": datetime.now(timezone.utc).isoformat(), "seed": args.seed,
                  "split": split, "repeats": args.repeats, "threshold": args.threshold,
                  "metrics": {part: summarize([row for row in rows if part == "all" or row["split"] == part],
                                              args.threshold, args.repeats)
                              for part in ("train", "test", "all")}}
        (output / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"results": str(output / "results.json"), "metrics": {
            part: {k: v for k, v in value.items() if k != "results"} for part, value in report["metrics"].items()}}, indent=2))
        return 1 if report["metrics"]["all"]["counts"]["inconclusive"] else 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Trigger evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
