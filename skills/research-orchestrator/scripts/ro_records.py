#!/usr/bin/env python3
"""Record commands: durable identifiers, claims, observed facts and factual briefs."""

from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from ro_state import Project, duration, same_process
from ro_ids import H_PATTERN, ID_RE, format_id, id_pattern
from ro_markdown import mask_fences, unfenced as _unfenced


FILES = ("agents.md", "plan.md", "discoveries.md", "handoff.md")
ID = ID_RE
CLAIM = re.compile(r"^([A-Z]{1,2}) since (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$")
COMPUTE_CLAIM = re.compile(r"^((?:CPU|GPU|Other)(?:@[\w.-]+)?) — ([A-Z]{1,2}) "
                           rf"\(({H_PATTERN}), since \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}\)$")
HEAD = re.compile(rf"^(#{{2,3}}) ({id_pattern()})(?: — (.*))?$")
CHECK = re.compile(r"\b(?:shell|jobs|records|publish|external|ask|brief)\.[a-z][a-z.-]+\b")


def _text(project: Project, name: str) -> str:
    try:
        with (project.root / name).open(encoding="utf-8", newline="") as source:
            return source.read()
    except FileNotFoundError:
        return ""


def _reservations(project: Project) -> dict:
    return project.read_json("ids.json", {}, validate=lambda data: isinstance(data, dict) and all(
        isinstance(key, str) and ID.fullmatch(key) and isinstance(value, dict)
        and isinstance(value.get("expires"), (int, float))
        for key, value in data.items()))


def _remember_ids(project: Project, identifiers) -> dict[str, int]:
    """Keep issued numbers after leases expire, records move, or archives disappear."""
    marks = project.read_json("id-high-water.json", {}, validate=lambda data: isinstance(data, dict) and all(
        re.fullmatch(r"[DHIXN]-[A-Z]{1,2}", key) and isinstance(value, int)
        and not isinstance(value, bool) and value >= 0 for key, value in data.items()))
    updated = dict(marks)
    for identifier in identifiers:
        if not ID.fullmatch(identifier):
            continue
        prefix, number = identifier.rsplit("-", 1)
        updated[prefix] = max(updated.get(prefix, 0), int(number))
    if updated != marks:
        project.write_json("id-high-water.json", updated, recoverable=True)
    return updated


def reconcile_ids(project: Project, texts: dict[str, str] | None = None) -> list[str]:
    """Drop reservations that have become records, or whose ten-minute lease expired."""
    with project.lock():
        texts = texts or {name: _text(project, name) for name in FILES}
        present = {m.group(2) for text in texts.values() for line in _unfenced(text)
                   if (m := HEAD.fullmatch(line))}
        reservations = _reservations(project)
        # Save their numbers before retiring leases, including legacy reservations
        # created before high-water metadata existed.
        _remember_ids(project, set(reservations) | present)
        now = time.time()
        kept = {key: value for key, value in reservations.items()
                if key not in present and isinstance(value, dict) and value.get("expires", 0) > now}
        removed = sorted(set(reservations) - set(kept))
        if kept != reservations:
            project.write_json("ids.json", kept, recoverable=True)
        return removed


def _archived_ids(project: Project) -> set[str]:
    """Reuse unchanged archive parses; callers hold the ID reservation lock."""
    try:
        cache = project.read_json("archive-ids.json", {})
    except ValueError:
        cache = {}
    files = cache.get("files", {}) if isinstance(cache, dict) and cache.get("version") == 2 else {}
    if not isinstance(files, dict):
        files = {}
    current = {}
    identifiers = set()
    for path in (project.root / "docs").rglob("*.md"):
        if not path.is_file():
            continue
        info = path.stat()
        stamp = [info.st_mtime_ns, info.st_ctime_ns, info.st_size, info.st_ino]
        key = path.relative_to(project.root).as_posix()
        entry = files.get(key)
        if not (isinstance(entry, dict) and entry.get("stat") == stamp and
                isinstance(entry.get("ids"), list) and
                all(isinstance(value, str) and ID.fullmatch(value) for value in entry["ids"])):
            entry = {"stat": stamp, "ids": sorted({identifier for line in _unfenced(
                path.read_text(encoding="utf-8")) for identifier in ID.findall(line)})}
        current[key] = entry
        identifiers.update(entry["ids"])
    updated = {"version": 2, "files": current}
    if updated != cache:
        project.write_json("archive-ids.json", updated)
    return identifiers


def next_id(project: Project, kind: str) -> str:
    if kind not in ("D", "H", "I", "X", "N"):
        raise ValueError("ID kind must be D, H, I, X or N")
    with project.lock():
        texts = {name: _text(project, name) for name in FILES}
        reconcile_ids(project, texts)
        reservations = _reservations(project)
        prefix = f"{kind}-{project.slot}-"
        # References count too: removing an archived heading must never make its number reusable.
        identifiers = {key for name, text in texts.items() if name != "agents.md"
                       for line in _unfenced(text) for key in ID.findall(line)} | set(reservations)
        identifiers.update(_archived_ids(project))
        marks = _remember_ids(project, identifiers)
        number = 1 + marks.get(prefix.rstrip("-"), 0)
        identifier = format_id(kind, project.slot, number)
        # Commit the high-water mark and its recovery copy before returning an ID
        # or publishing its expiring reservation. An interrupted allocation may
        # skip a number but cannot issue an already returned identifier again.
        _remember_ids(project, [identifier])
        reservations[identifier] = {"slot": project.slot, "session": project.session, "expires": time.time() + 600}
        project.write_json("ids.json", reservations, recoverable=True)
        return identifier


FINDING_CLIP = 160  # characters of each Finding line once the startup index is clipped
INDEX_LIMIT_BYTES = 48 * 1024  # the startup discovery index clips findings, and history.size warns, past this


def _discovery_entries(text: str) -> list[tuple[str, int, int, list[tuple[int, str]], str]]:
    """Index findings without exposing evidence; positions still refer to the full file.

    Each entry is (ID, start, end, index lines, archive path); an archived stub names the
    docs/ file that holds its full entry (`ro archive discoveries`).
    """
    lines = _unfenced(text)
    entries = []
    start, identifier, depth, archived = -1, "", 0, ""
    index = []
    for number, line in enumerate([*lines, "#"]):
        heading = re.match(r"^(#+)(?: |$)", line)
        if start >= 0 and heading and len(heading.group(1)) <= depth:
            entries.append((identifier, start, number, index, archived))
            start = -1
        match = HEAD.fullmatch(line)
        if match and match.group(2).startswith("D-"):
            start, identifier, depth, archived = number, match.group(2), len(match.group(1)), ""
            index = [(number, line)]
        elif start >= 0 and line.startswith(("- Finding:", "- Status:", "- Cross-check:")):
            index.append((number, line))
        elif start >= 0 and line.startswith("- Archived:"):
            archived = line.split(":", 1)[1].strip()
    return entries


def _clip(line: str) -> str:
    return line if len(line) <= FINDING_CLIP else line[:FINDING_CLIP - 1].rstrip() + "…"


def index_text(text: str, full: bool = False, entries: list | None = None, clip: bool | None = None) -> str:
    """The startup index of live discoveries: headings, states and findings.

    Findings stay whole while the index fits INDEX_LIMIT_BYTES, because their conditions
    decide duplicates; only a larger index clips them. Archived stubs are left out and
    counted, so a long history does not grow the startup read; `ro dupcheck` still searches
    them and `ro index <ID>` opens one.
    """
    entries = _discovery_entries(text) if entries is None else entries
    if not entries:
        return "No discoveries recorded."
    live = [entry for entry in entries if not entry[4]]
    states = Counter(next((line.split(":", 1)[1].split()[0] for _n, line in entry[3]
                           if line.startswith("- Cross-check:") and line.split(":", 1)[1].split()), "unreviewed")
                     for entry in live)
    summary = ", ".join(f"{state} {count}" for state, count in sorted(states.items()))

    def render(clip: bool) -> str:
        header = (f"Discovery index: {len(live)} live" + (f" ({summary})" if summary else "")
                  + f", {len(entries) - len(live)} archived"
                  + (f"; findings clipped to {FINDING_CLIP} characters because the whole index passes "
                     f"{INDEX_LIMIT_BYTES // 1024} KiB" if clip else "")
                  + ". `ro index <ID>` opens one entry, archived ones included; `ro dupcheck <terms>` searches"
                  " archived entries too" + ("; `ro index --full` shows whole lines" if clip else "") + ".")
        blocks = []
        for _key, _start, _end, index, archived in entries:
            if archived and not full:
                continue
            lines = [_clip(line) if clip and line.startswith("- Finding:") else line for _number, line in index]
            if archived:
                lines[0] += f" (archived: {archived})"
            blocks.append("\n".join(lines))
        return "\n\n".join([header, *blocks])

    whole = render(clip=False)
    if full or clip is False:
        return whole
    return render(clip=True) if clip or len(whole.encode("utf-8")) > INDEX_LIMIT_BYTES else whole


def archived_entry(project: Project, identifier: str, location: str) -> str:
    """The full entry of an archived discovery from its docs/ file."""
    path = (project.root / location).resolve()
    docs = (project.root / "docs").resolve()
    if not path.is_relative_to(docs) or not path.is_file():
        raise ValueError(f"{identifier} is archived in {location}, which is not a file under docs/")
    text = path.read_text(encoding="utf-8")
    selected = [entry for entry in _discovery_entries(text) if entry[0] == identifier]
    if len(selected) != 1:
        raise ValueError(f"{location} must hold exactly one {identifier} entry")
    _, start, end, _index, _archived = selected[0]
    return "\n".join(text.splitlines()[start:end]).rstrip()


def discovery_index(project: Project, identifier: str = "", full: bool = False) -> str:
    """Return the startup index, or open one requested discovery in full."""
    text = _text(project, "discoveries.md")
    entries = _discovery_entries(text)
    if identifier:
        selected = [entry for entry in entries if entry[0] == identifier]
        if len(selected) != 1:
            raise ValueError(f"{identifier} must identify exactly one discovery")
        _, start, end, _index, archived = selected[0]
        if archived:
            return archived_entry(project, identifier, archived) + f"\n\n(archived in {archived})"
        return "\n".join(text.splitlines()[start:end]).rstrip()
    return index_text(text, full, entries)


TOOLS = "docs/tools.md"
SCRIPT_SUFFIXES = {".py", ".sh", ".ps1", ".bat", ".cmd", ".js", ".mjs", ".ts", ".r", ".jl", ".rb", ".pl"}


def tool_entries(text: str) -> list[dict]:
    """Entries of the tool registry: `## <name> — <purpose>` headings with their fields."""
    entries, current = [], None
    for number, line in enumerate(_unfenced(text), 1):
        if line.startswith("## "):
            current = {"heading": line[3:].strip(), "line": number, "fields": {}}
            entries.append(current)
        elif line.startswith("#"):
            current = None
        elif current is not None and (match := re.match(r"^- ([A-Za-z][A-Za-z ]*):\s*(.*)$", line)):
            current["fields"].setdefault(match.group(1), match.group(2).strip())
    return entries


def tool_directories(root: Path, entries: list[dict]) -> list[Path]:
    """Directories below the project root that hold a registered tool path."""
    base = Path(root).resolve()
    found = set()
    for entry in entries:
        location = entry["fields"].get("Path", "")
        if location and location != "none":
            parent = (base / location).resolve().parent
            if parent != base and parent.is_relative_to(base):
                found.add(parent)
    return sorted(found)


def tools_init(project: Project) -> str:
    """Create docs/tools.md from the template, with its usage rules; never overwrite."""
    path = project.root / TOOLS
    with project.lock():
        if path.exists():
            return f"{TOOLS} already exists; add entries to it."
        path.parent.mkdir(parents=True, exist_ok=True)
        template = Path(__file__).resolve().parent.parent / "templates" / "TOOLS.md.template"
        project.atomic_text(path, template.read_text(encoding="utf-8"))
    return f"Created {TOOLS}; add one entry per reusable script (references/tools.md)."


def tools_listing(project: Project, terms: list[str] | tuple[str, ...] = ()) -> str:
    """Registered tools matching every term, with path, version, status and usage."""
    text = _text(project, TOOLS)
    if not text:
        return f"No tool registry yet: `ro tools --init` creates {TOOLS} with the first reusable script."
    words = [term.casefold() for term in terms if term.strip()]
    rows = []
    for entry in tool_entries(text):
        fields = entry["fields"]
        if all(word in " ".join([entry["heading"], *fields.values()]).casefold() for word in words):
            rows.append(f"{TOOLS}:{entry['line']}: {entry['heading']} | {fields.get('Path', '?')} | "
                        f"{fields.get('Version', '-')} | {fields.get('Status', '?')}\n"
                        f"    Usage: {fields.get('Usage', '?')}")
    return "\n".join(rows) if rows else ("No matching tools." if words else f"{TOOLS} lists no tools.")


def dupcheck(project: Project, terms: list[str] | tuple[str, ...]) -> str:
    words = [term.casefold() for term in terms if term.strip()]
    if not words:
        raise ValueError("dupcheck needs search terms")
    paths = [project.root / name for name in FILES]
    if (project.root / "docs").is_dir():
        paths.extend(sorted((project.root / "docs").rglob("*.md")))
    matches = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if path == project.root / TOOLS:
            # A tool matches on its name, purpose, path and usage together.
            for entry in tool_entries(text):
                fields = entry["fields"]
                if all(word in " ".join([entry["heading"], fields.get("Path", ""), fields.get("Usage", "")])
                       .casefold() for word in words):
                    matches.append(f"{TOOLS}:{entry['line']}: ## {entry['heading']} | Path: {fields.get('Path', '?')}")
            continue
        entries = _discovery_entries(text)
        indexed_lines = set()
        for _key, start, end, index, archived in entries:
            indexed_lines.update(range(start, end))
            if archived:
                continue  # the docs/ archive holds the full entry, which is searched itself
            if all(word in "\n".join(line for _number, line in index).casefold() for word in words):
                matches.extend(f"{path.relative_to(project.root).as_posix()}:{number + 1}: {line}"
                               for number, line in index)
        for number, line in enumerate(_unfenced(text), 1):
            if number - 1 in indexed_lines:
                continue
            if (line.startswith("#") or line.startswith(("- Hypothesis:", "- Goal:", "- Finding:"))) and all(
                    word in line.casefold() for word in words):
                matches.append(f"{path.relative_to(project.root).as_posix()}:{number}: {line}")
    return "\n".join(matches) if matches else "No matching headings, hypotheses or findings."


def _active_text(text: str, headings: str) -> str:
    """Expose selected level-two sections, retaining source offsets and boundaries.

    Historical copies and fenced examples are not current ownership. Keep every
    section boundary visible so a live record cannot absorb a masked archive.
    """
    result, active = [], False
    for line in mask_fences(text).splitlines(keepends=True):
        heading = re.fullmatch(r"#{1,2} .*", line.rstrip("\r\n"))
        if heading:
            active = re.fullmatch(headings, heading.group()) is not None
        result.append(line if active or heading else re.sub(r"[^\r\n]", " ", line))
    return "".join(result)


PLAN_SECTIONS = r"## (?:Queue|Agent: [A-Z]{1,2})\s*"
HANDOFF_SECTIONS = r"## Active handoff(?: — .*)?\s*"
SHARED_SECTION = r"## Shared state\s*"


def _slot_sections(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    slot = ""
    for line in _unfenced(_active_text(text, HANDOFF_SECTIONS)):
        if match := re.fullmatch(r"### Agent: ([A-Z]{1,2})", line):
            slot = match.group(1)
            sections[slot] = {}
        elif line.startswith("#"):
            slot = ""
        elif slot and (match := re.match(r"^- ([^:]+):\s*(.*)$", line)):
            sections[slot][match.group(1)] = match.group(2)
    return sections


def _items(text: str) -> list[tuple[str, int, int, dict[str, str]]]:
    lines = _unfenced(_active_text(text, PLAN_SECTIONS))
    result = []
    for start, line in enumerate(lines):
        if not (match := re.fullmatch(rf"### ({H_PATTERN})(?: — .*)?", line)):
            continue
        end = start + 1
        fields = {}
        while end < len(lines) and not lines[end].startswith("#"):
            if field := re.match(r"^- ([^:]+):\s*(.*)$", lines[end]):
                fields[field.group(1)] = field.group(2)
            end += 1
        result.append((match.group(1), start, end, fields))
    return result


def _change_claim(project: Project, item: str, release_claim: bool) -> str:
    if not re.fullmatch(H_PATTERN, item):
        raise ValueError("claim requires an H-id")
    with project.lock():
        if project.settings()["workflow"] != "unified":
            raise ValueError("claim and release require Workflow: unified")
        text = _text(project, "plan.md")  # re-read only after taking the lock
        records = [record for record in _items(text) if record[0] == item]
        if len(records) != 1:
            raise ValueError(f"{item} must appear exactly once in an active plan.md section")
        _, start, end, fields = records[0]
        value = fields.get("Claimed", "")
        owner = CLAIM.fullmatch(value)
        if value != "none" and not owner:
            raise ValueError(f"{item} has a non-canonical Claimed line; repair it before claiming")
        holder = owner.group(1) if owner else ""
        if release_claim:
            if holder and holder != project.slot:
                raise ValueError(f"{item} is claimed by {holder}; release only this slot's claims")
            changed = "none"
        else:
            slots = _slot_sections(_text(project, "handoff.md"))
            if project.slot not in slots:
                raise ValueError(f"slot {project.slot} has no handoff section")
            if holder and holder != project.slot and slots.get(holder, {}).get("Current host", "").lower() not in (
                    "released", "unassigned"):
                raise ValueError(f"{item} is claimed by taken slot {holder}")
            changed = value if holder == project.slot else f"{project.slot} since {dt.datetime.now():%Y-%m-%d %H:%M}"
        lines = text.splitlines(keepends=True)
        visible = _unfenced(_active_text(text, PLAN_SECTIONS))
        hits = [index for index in range(start + 1, end) if visible[index].startswith("- Claimed:")]
        if len(hits) != 1:
            raise ValueError(f"{item} requires exactly one Claimed line")
        # The checker accepts the line anywhere in the item; rewrite it as the first field.
        newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
        del lines[hits[0]]
        lines.insert(start + 1, f"- Claimed: {changed}{newline}")
        project.atomic_text(project.root / "plan.md", "".join(lines))
        return f"{item}: {changed}"


def claim(project: Project, item: str) -> str:
    return _change_claim(project, item, False)


def release(project: Project, item: str) -> str:
    from ro_jobs import monitor_outcome
    with project.lock():
        if any(str(job.get("item", "")).split("/", 1)[0] == item for job in running_jobs(project)):
            raise ValueError(f"{item} still has a running job")
        # Like close: a finished job's outcome must be recorded before its item leaves this slot.
        unreported = [str(job.get("id")) for job in registered_jobs(project)
                      if str(job.get("item", "")).split("/", 1)[0] == item
                      and job.get("slot", project.slot) == project.slot and not monitor_outcome(job)]
        if unreported:
            raise ValueError(f"{item} has jobs without a recorded monitor outcome ({', '.join(unreported)}); "
                             "run ro monitor <job>, append its Job line, then release")
        return _change_claim(project, item, True)


def observe(project: Project, key: str, value: str, source: str = "", ttl: str = "6h") -> str:
    duration(ttl)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _.-]{0,79}", key) or key.startswith("Observed "):
        raise ValueError("observed key must be a short plain field name")
    if any("\n" in part or "\r" in part for part in (value, source)):
        raise ValueError("observed values and sources must be single lines")
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    suffix = f" (Observed at {stamp}; TTL {ttl}" + (f"; source {source}" if source else "") + ")"
    with project.lock():
        text = _text(project, "handoff.md")
        visible = mask_fences(text)
        match = re.search(r"^## Shared state[^\S\r\n]*\r?$", visible, re.M)
        if not match:
            raise ValueError("handoff.md has no Shared state section")
        following = re.search(r"^## ", visible[match.end():], re.M)
        end = match.end() + following.start() if following else len(text)
        section = text[match.end():end]
        entry = f"- {key}: {value}{suffix}"
        pattern = rf"^- {re.escape(key)}:[^\r\n]*"
        if old := re.search(pattern, visible[match.end():end], re.M):
            section = section[:old.start()] + entry + section[old.end():]
        else:
            section = section.rstrip() + "\n" + entry + "\n\n"
        project.atomic_text(project.root / "handoff.md", text[:match.end()] + section + text[end:])
    return f"{key}: observed {stamp}; TTL {ttl}"


def registered_jobs(project: Project) -> list[dict]:
    jobs = project.read_json("jobs.json", [])
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", list(jobs.values()))
    return [job for job in jobs if isinstance(job, dict)]


def running_jobs(project: Project) -> list[dict]:
    from ro_jobs import running_job
    def alive(job):
        launcher = job.get("launcher") or {}
        return running_job(job) or (job.get("status") == "starting" and
                                   same_process(launcher.get("pid", 0), launcher.get("start")))
    return [job for job in registered_jobs(project) if alive(job)]


def _fact_id(value: str) -> str:
    return value if ID.fullmatch(value) else "unknown"


def _checker(project: Project):
    from check_project import Checker
    checker = Checker(project.root)
    code = checker.run(quiet=True)
    return checker, code


UNVERIFIED_REVIEW = "event.stage.review.unverified"


def _checker_brief(project: Project, *, compact: bool = False) -> tuple[dict, int, dict]:
    """Reuse stamped summaries at compact; jobs and observations stay live on every brief."""
    from ro_evidence import BRIEF_HASH_BYTES, hash_budget
    # One budget covers stamping and the checker; digests from the stamp are reused.
    with hash_budget(BRIEF_HASH_BYTES):
        return _bounded_checker_brief(project, compact)


def _bounded_checker_brief(project: Project, compact: bool) -> tuple[dict, int, dict]:
    import ro_settings as rs
    from ro_evidence import stat_artifact
    root = Path(__file__).resolve().parent.parent
    dependencies = [*(project.root / name for name in FILES), project.state / "checker-baseline.json",
                    project.state / "receipts.json",
                    project.root / rs.TRANSACTION,
                    *(root / "scripts" / name for name in ("check_project.py", "ro_settings.py", "ro_ids.py", "ro_markdown.py", "ro_records.py",
                                                           "ro_stages.py", "ro_evidence.py", "ro_archive.py",
                                                           "init_research_orchestrator.py")),
                    *sorted((root / "templates").rglob("*.template")),
                    # The checker also reads archived discoveries, the tool registry and the
                    # directories it scans for unregistered scripts (their mtime tracks members).
                    project.root / TOOLS, *sorted((project.root / "docs" / "archive").glob("*.md")),
                    *tool_directories(project.root, tool_entries(_text(project, TOOLS)))]
    stamp = []
    for path in dependencies:
        stat = path.stat() if path.exists() else None
        stamp.append([str(path), stat.st_mtime_ns if stat else None, stat.st_ctime_ns if stat else None,
                      stat.st_size if stat else None, stat.st_ino if stat else None])
    # Review receipts bind content, including directory members. A parent directory's
    # timestamp cannot reveal an edited member, so the stamp is bounded: content up to
    # STAMP_HASH_BYTES, member metadata above it. Stamps and a rerun checker share one
    # BRIEF_HASH_BYTES budget, so a large reviewed artifact is reported as unverified in the
    # brief instead of being hashed inside the hook deadline; check_project.py verifies it.
    artifacts = sorted(set(re.findall(r"^- Review artifact:[ \t]*([^\n]+)",
                                     mask_fences(_text(project, "handoff.md")), re.M)))
    uncached = False
    for artifact in artifacts:
        try:
            review_stamp = stat_artifact(project, artifact.strip())
        except (OSError, ValueError) as exc:
            review_stamp = {"unavailable": type(exc).__name__}
        uncached = uncached or bool(review_stamp.get("unstamped"))
        stamp.append(["review", artifact, review_stamp])
    now = time.time()
    checks = ("guard.insight.overdue", "guard.direction.stale", "guard.phase.milestone",
              "guard.override.recheck", "guard.family.saturated", "event.stage.review",
              "history.size", "tools.unregistered", "agents.size")
    try:
        saved = project.read_json("checker-brief.json", {})
        age = now - saved.get("at", 0)
        if (not uncached and saved.get("stamp") == stamp and 0 <= age and (compact or age < 60)
                and saved.get("day") == dt.date.today().isoformat()):
            counts, code, guards = saved["counts"], saved["code"], saved["guards"]
            if (all(type(counts.get(level)) is int and counts[level] >= 0 for level in ("ERROR", "WARN", "INFO"))
                    and code in (0, 1, 2) and isinstance(guards, dict)
                    and all(key in (*checks, UNVERIFIED_REVIEW) and isinstance(ids, list)
                            and all(isinstance(i, str) for i in ids) for key, ids in guards.items())):
                return counts, code, guards
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    checker, code = _checker(project)
    counts = {level: sum(issue.severity == level for issue in checker.issues) for level in ("ERROR", "WARN", "INFO")}
    # Review evidence the budget left unverified is listed apart from failed or stale reviews.
    deferred = [issue for issue in checker.issues
                if issue.check == "event.stage.review" and "hash budget" in issue.message]
    guards = {check: [issue.record for issue in checker.issues
                      if issue.check == check and not any(issue is item for item in deferred)] for check in checks}
    guards[UNVERIFIED_REVIEW] = [issue.record for issue in deferred]
    try:
        with project.lock(timeout=0.15):
            project.write_json("checker-brief.json", {"stamp": stamp, "at": now, "day": dt.date.today().isoformat(),
                                                     "counts": counts, "code": code, "guards": guards})
    except (OSError, ValueError):
        pass  # The cache is optional; the computed checker result remains authoritative.
    return counts, code, guards


def publish_gate_guidance(project: Project, shell: str) -> list[str]:
    """Report a missing checkout registration without implying host hooks guard pushes."""
    from ro_command import install_command, literal
    from ro_gate import registration
    root, registered = registration(project.root)
    if root is None or registered:
        return []
    # Name the checkout root: install.py refuses --project from a nested directory.
    target = literal(str(root), shell)
    command = install_command(shell, "--project " + target) or f"python <checkout>/install.py --project {target}"
    return ["publish gate not installed — " + command]


def runtime_guidance(values: dict[str, str], project: Project | None = None) -> list[str]:
    """Give actionable local commands even before a multi-slot session selects a slot."""
    from ro_command import command_prefix, shim_install_command
    shell = "powershell" if values.get("environment", "").endswith("/powershell") else "sh"
    # Sessions that never invoke the skill still learn where this project's rules live.
    lines = ["Rules: follow agents.md (## Working rules) before editing the coordination files; "
             "the research-orchestrator skill has the details.",
             "ro command prefix: " + command_prefix(shell=shell)]
    if shutil.which("ro") is None:
        command = shim_install_command(shell)
        if command:
            lines.append("ro CLI shim absent from PATH; run: " + command)
            lines.append("Add the reported shim directory to PATH; keep the installed plugin available for the runtime.")
        else:
            lines.append("ro CLI shim absent from PATH: rerun the installer that installed this skill; "
                         "add its reported shim directory to PATH. The ro command prefix above works now.")
    if project is not None:
        lines.extend(publish_gate_guidance(project, shell))
    return lines


def brief(project: Project, max_chars: int = 8000, *, compact: bool = False) -> str:
    """Inject derived facts and a trusted runtime prefix, never copied project prose."""
    from ro_sessions import startup
    selection = startup(project)
    if selection:
        return "\n".join([selection, *runtime_guidance(project.settings(), project)])[:max(0, min(int(max_chars), 8000))]
    limit = max(0, min(int(max_chars), 8000))
    values = project.settings()
    # Only closed-vocabulary settings and the validated language code enter an injected brief.
    settings = [f"{key}={values[key]}" for key in ("profile", "workflow", "verification", "language",
                                                "enforcement", "autonomy")]
    lines = ["Research Orchestrator: " + "; ".join(settings), *runtime_guidance(values, project)]
    decision = getattr(project, "slot_decision", "")
    if not decision and project.slot_registered:
        decision = project.read_json(project.session_file, {}).get("decision", "")
    if decision:
        lines.append("Session choice: " + re.sub(r"[\r\n]", " ", str(decision))[:300])
    hooks = project.read_json("hooks-self-test.json", {})
    if not hooks and not (project.state / "hooks-self-test.json").exists():
        lines.append("hooks never ran: self-test not recorded; hooks not installed — run install.py "
                     "(or the Claude Code plugin)")
    elif hooks.get("status") == "active":
        lines.append("hooks active: self-test passed")
    else:
        # Reasons are a closed vocabulary too: even a one-line arbitrary reason could be an instruction.
        reason = hooks.get("reason", "self-test not recorded")
        if reason not in {"self-test not recorded", "malformed or oversized input", "missing interpreter", "timeout",
                          "ValueError", "TimeoutExpired", "FileNotFoundError", "PermissionError", "RuntimeError",
                          "OSError", "JSONDecodeError", "TypeError", "AttributeError", "ImportError",
                          "ModuleNotFoundError"}:
            reason = "self-test failed"
        lines.append("hooks inactive: " + reason)
    claims = [(key, fields.get("Claimed", "")) for key, _start, _end, fields in _items(_text(project, "plan.md"))
              if (match := CLAIM.fullmatch(fields.get("Claimed", ""))) and match.group(1) == project.slot]
    slots = _slot_sections(_text(project, "handoff.md"))
    host = slots.get(project.slot, {}).get("Current host", "unassigned")
    lines.append(f"Slot {project.slot}: {'released' if host.lower() in ('released', 'unassigned') else 'taken'}; "
                 f"claims {len(claims)}")
    lines.extend(f"Claim {_fact_id(key)}: {CLAIM.fullmatch(value).group(2)}" for key, value in claims)
    jobs = running_jobs(project)
    lines.append(f"Running jobs: {len(jobs)}")
    for job in jobs:
        monitor = job.get("monitor", {})
        if not isinstance(monitor, dict):
            monitor = {}
        monitor_pid = monitor.get("pid", job.get("monitor_pid", 0))
        monitor_start = monitor.get("start", job.get("monitor_start"))
        state = "live" if monitor.get("active") and same_process(monitor_pid, monitor_start) else "missing"
        job_id = re.sub(r"[^A-Za-z0-9_-]", "", str(job.get("id", "unknown")))[:64]
        lines.append(f"Job {job_id}: {_fact_id(str(job.get('item', '')))}; monitor {state}")
    # Observations remain in Shared state; freshness is a date/number fact, never a copied value.
    now = dt.datetime.now()
    for line in _unfenced(_active_text(_text(project, "handoff.md"), SHARED_SECTION)):
        if observed := re.search(r"Observed at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}); TTL (\d+(?:\.\d+)?(?:ms|s|m|h|d))", line):
            try:
                age = (now - dt.datetime.strptime(observed.group(1), "%Y-%m-%d %H:%M")).total_seconds()
                if age > duration(observed.group(2)):
                    lines.append(f"Stale observation: observed {observed.group(1)}; TTL {observed.group(2)}")
            except ValueError:
                pass
    try:
        counts, code, guards = _checker_brief(project, compact=True) if compact else _checker_brief(project)
        lines.append("Checker: " + "; ".join(f"{severity} {counts[severity]}" for severity in ("ERROR", "WARN", "INFO")))
        for check in ("guard.insight.overdue", "guard.direction.stale", "guard.phase.milestone",
                      "guard.override.recheck", "guard.family.saturated", "event.stage.review"):
            records = guards.get(check, [])
            if records:
                ids = list(dict.fromkeys(_fact_id(record) for record in records))[:8]
                lines.append(f"{check}: {len(records)}; IDs {', '.join(ids)}")
        if unverified := guards.get(UNVERIFIED_REVIEW, []):
            ids = list(dict.fromkeys(_fact_id(record) for record in unverified))[:8]
            lines.append(f"event.stage.review unverified within the brief's hash budget: {len(unverified)}; "
                         f"IDs {', '.join(ids)}; verify with check_project.py or ro receipt check")
        archive = {"discoveries.md": "ro archive discoveries", "handoff.md": "ro archive events"}
        if large := [name for name in guards.get("history.size", []) if name in archive]:
            lines.append("history.size: " + "; ".join(f"{name} past its startup-read limit, run {archive[name]}"
                                                      for name in large))
        if guards.get("agents.size"):
            lines.append("agents.size: agents.md past its size limit; move older Lessons and expired overrides to docs/ "
                         "(check_project.py names the size)")
        if unregistered := guards.get("tools.unregistered", []):
            lines.append(f"tools.unregistered: {len(unregistered)} script(s) beside registered tools lack a "
                         f"{TOOLS} entry; register or reuse before adding more")
        if code == 2:
            lines.append("Checker unavailable: project files missing or unreadable")
    except (OSError, ValueError, KeyError, AttributeError):
        lines.append("Checker unavailable: record parse failed")
    try:
        warning_ids = Counter(CHECK.findall((project.state / "warnings.log").read_text(encoding="utf-8")))
    except FileNotFoundError:
        warning_ids = Counter()
    if warning_ids:
        lines.append("Hook warnings: " + "; ".join(f"{key} {count}" for key, count in sorted(warning_ids.items())))
    if registry := tool_entries(_text(project, TOOLS)):
        active = sum(entry["fields"].get("Status", "") == "active" for entry in registry)
        lines.append(f"Tools: {len(registry)} registered ({active} active) in {TOOLS}; "
                     "search `ro tools <terms>` before writing a script")
    result = "\n".join(lines)
    return result if len(result) <= limit else result[:max(0, limit - 1)] + ("…" if limit else "")


def close(project: Project) -> str:
    from ro_jobs import monitor_next, monitor_outcome
    with project.lock():
        jobs = [job for job in running_jobs(project) if job.get("slot", project.slot) == project.slot]
        unreported = [job for job in registered_jobs(project)
                      if job.get("slot", project.slot) == project.slot and not monitor_outcome(job)]
        protected = {str(job.get("item", "")).split("/", 1)[0] for job in jobs + unreported}
        released = []
        for key, _start, _end, fields in _items(_text(project, "plan.md")):
            owner = CLAIM.fullmatch(fields.get("Claimed", ""))
            if owner and owner.group(1) == project.slot and key not in protected:
                release(project, key)
                released.append(key)
        text = _text(project, "handoff.md")
        original = text
        def release_compute(match):
            claims = []
            for value in match.group(1).split(";"):
                parsed = COMPUTE_CLAIM.fullmatch(value.strip())
                if not parsed or parsed.group(2) != project.slot or parsed.group(3) in protected:
                    claims.append(value.strip())
            return "- Active compute: " + ("; ".join(claims) or "none")
        match = re.search(r"^- Active compute: ([^\r\n]*)", _active_text(text, SHARED_SECTION), re.M)
        if match:
            text = text[:match.start()] + release_compute(match) + text[match.end():]
        if not jobs and not unreported:
            pattern = re.compile(rf"(^### Agent: {project.slot}\r?\n)(.*?)(?=^#|\Z)", re.M | re.S)
            matches = list(pattern.finditer(_active_text(text, HANDOFF_SECTIONS)))
            if len(matches) != 1:
                raise ValueError(f"slot {project.slot} must have exactly one handoff section")
            match = matches[0]
            body = text[match.start(2):match.end(2)]
            for label, value in (("Current host", "released"), ("Current user", "none")):
                field = re.search(rf"^- {label}:[^\r\n]*", mask_fences(body), re.M)
                if field:
                    body = body[:field.start()] + f"- {label}: {value}" + body[field.end():]
            text = text[:match.start(2)] + body + text[match.end(2):]
            # An empty, idle project has no ongoing direction to review. Other
            # active slots or protected jobs still need their normal cadence.
            if (not _items(_text(project, "plan.md"))
                    and all(fields.get("Current host", "").lower() in {"released", "unassigned"}
                            for fields in _slot_sections(text).values())
                    and not running_jobs(project)):
                stamp = dt.date.today().isoformat()
                shared = _active_text(text, SHARED_SECTION)
                paused = re.search(r"^- Paused:[^\r\n]*", shared, re.M)
                if paused:
                    text = text[:paused.start()] + f"- Paused: {stamp}" + text[paused.end():]
                else:
                    heading = re.search(r"^## Shared state[^\r\n]*(?:\r?\n|$)", shared, re.M)
                    if heading:
                        newline = "\r\n" if "\r\n" in text else "\n"
                        text = text[:heading.end()] + f"- Paused: {stamp}{newline}" + text[heading.end():]
        if text != original:
            project.atomic_text(project.root / "handoff.md", text)
    checker, code = _checker(project)
    lines = [f"Released claims: {', '.join(released) or 'none'}",
             f"Slot {project.slot}: {'taken; running jobs ' + str(len(jobs)) if jobs or unreported else 'released'}"]
    if unreported:
        lines.append("Monitor outcomes missing; ownership retained because process exit alone is not a monitored result.")
        lines.extend(monitor_next(project, job.get("id", "unknown")) for job in unreported)
    leftovers = [key for key, _s, _e, fields in _items(_text(project, "plan.md"))
                 if (match := CLAIM.fullmatch(fields.get("Claimed", ""))) and match.group(1) == project.slot]
    lines.append("Open claims: " + (", ".join(leftovers) or "none"))
    missing = [issue.record for issue in checker.issues if any(part in issue.check for part in (
        "follow", "insight.overdue"))]
    # An explicit 'none' records zero follow-ups; a reason adds useful context.
    # Check that decision instead of inferring future work from finding prose.
    for key, discovery in getattr(checker, "discoveries", {}).items():
        if discovery.fields.get("Source") != project.slot:
            continue
        sourced = any(key in ID.findall(item.fields.get("Sources", ""))
                      for item in getattr(checker, "plan_items", {}).values())
        decided = any(key in ID.findall(event.fields.get("Discovery updates", ""))
                      and (re.search(rf"\b{H_PATTERN}\b", event.fields.get("New plan items", ""))
                           or re.fullmatch(r"none(?: — \S.*)?", event.fields.get("New plan items", "")))
                      for event in getattr(checker, "events", []))
        if not sourced and not decided:
            missing.append(key)
    lines.append("Discoveries without follow-ups: " + (", ".join(dict.fromkeys(missing)) or "none"))
    counts = Counter(issue.severity for issue in checker.issues)
    lines.append(f"Checker: exit {code}; ERROR {counts['ERROR']}; WARN {counts['WARN']}; INFO {counts['INFO']}")
    return "\n".join(lines)
