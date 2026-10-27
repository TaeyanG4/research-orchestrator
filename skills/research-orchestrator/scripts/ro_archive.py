"""Move settled discoveries and older handoff events to docs/archive/ (`ro archive`).

The startup read stays bounded as a project grows: settled discoveries leave a short stub
that keeps their ID resolvable, and older completed-log events leave one summary line per
archive file. Archives are ordinary Markdown under docs/, so `ro dupcheck` searches them,
`ro index <ID>` opens an archived discovery, and the checker reads archived entries.
"""

from __future__ import annotations

import re

from ro_ids import D_PATTERN, H_PATTERN
from ro_markdown import unfenced as _unfenced
from ro_records import (HANDOFF_SECTIONS, INDEX_LIMIT_BYTES, PLAN_SECTIONS, SHARED_SECTION, _active_text, _clip,
                        _discovery_entries, _text, index_text)
from ro_state import Project

# Startup-read limits behind the checker's history.size warning; archiving aims for half.
INDEX_WARN_BYTES = INDEX_LIMIT_BYTES
HANDOFF_WARN_BYTES = 192 * 1024
ARCHIVE_DIR = "docs/archive"
D_ID = re.compile(rf"\b{D_PATTERN}\b")
H_ID = re.compile(rf"\b{H_PATTERN}\b")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EVENT = re.compile(r"^### (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} — ([A-Z]{1,2}) — (\S+)")
HISTORY = "## Archived history"


# agents.md loads in every session (Claude Code imports it through CLAUDE.md); Codex reads
# only the first 32 KiB of project instructions, which cuts the user-owned rules at the end.
AGENTS_WARN_BYTES = 12 * 1024
CODEX_PROJECT_DOC_BYTES = 32 * 1024


def agents_size_finding(agents: str) -> str:
    """The agents.size message for an oversized agents.md, or an empty string."""
    size = len(agents.encode("utf-8"))
    if size <= AGENTS_WARN_BYTES:
        return ""
    remedy = ("move older Lessons and expired overrides to docs/ with a link, and remove rules that a later "
              "rule replaced")
    if size > CODEX_PROJECT_DOC_BYTES:
        return (f"agents.md is {size // 1024} KiB; Codex reads only the first {CODEX_PROJECT_DOC_BYTES // 1024} KiB of "
                f"project instructions, so the end of ## Project rules is cut, and every session loads the rest; "
                + remedy)
    return (f"agents.md is {size // 1024} KiB (limit {AGENTS_WARN_BYTES // 1024} KiB) and loads in every session; "
            + remedy)


def size_findings(discoveries: str, handoff: str) -> list[tuple[str, str]]:
    """(file, message) for coordination files whose startup read passed its limit."""
    findings = []
    # The whole index decides clipping, so it also decides the warning and the archive target.
    index = len(index_text(discoveries, clip=False).encode("utf-8"))
    if index > INDEX_WARN_BYTES:
        findings.append(("discoveries.md", f"the whole startup discovery index is {index // 1024} KiB (limit "
                         f"{INDEX_WARN_BYTES // 1024} KiB); run `ro archive discoveries` to move settled entries "
                         f"to {ARCHIVE_DIR}/ (stubs keep their IDs; dupcheck and `ro index <ID>` still find them), "
                         "and settle pending reviews, which stay listed"))
    size = len(handoff.encode("utf-8"))
    if size > HANDOFF_WARN_BYTES:
        findings.append(("handoff.md", f"handoff.md is {size // 1024} KiB (limit {HANDOFF_WARN_BYTES // 1024} KiB); "
                         f"run `ro archive events` to move older completed-log events to {ARCHIVE_DIR}/"))
    return findings


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _ending(text: str) -> str:
    return "\r\n" if text.count("\r\n") * 2 > text.count("\n") else "\n"


def _field(block: list[str], name: str) -> str:
    for line in block:
        if line.startswith(f"- {name}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _in_use(project: Project) -> set[str]:
    """Discovery IDs that live plan items, Shared state or active handoff sections cite."""
    plan = _active_text(_text(project, "plan.md"), PLAN_SECTIONS)
    handoff = _text(project, "handoff.md")
    live = _active_text(handoff, SHARED_SECTION) + _active_text(handoff, HANDOFF_SECTIONS)
    return set(D_ID.findall(plan)) | set(D_ID.findall(live))


def _settled(block: list[str], mode: str) -> bool:
    state = (_field(block, "Cross-check").split() or [""])[0]
    if state == "VERIFIED":
        return True
    # Self verification needs no review, so an unreviewed entry is already settled.
    return mode == "self" and state in ("", "PENDING")


def _archive_name(kind: str, date: str) -> str:
    return f"{ARCHIVE_DIR}/{kind}-{date[:7] if DATE.match(date) else 'undated'}.md"


def _append_archive(project: Project, location: str, title: str, blocks: list[tuple[str, str]],
                    unique: bool) -> None:
    """Append blocks to an archive file, skipping ones a crashed earlier run already copied."""
    path = project.root / location
    text = path.read_text(encoding="utf-8") if path.is_file() else (
        f"# {title}\n\nFull entries moved by `ro archive`; the coordination files keep a stub or summary.\n")
    for key, block in blocks:
        block = block.replace("\r\n", "\n").strip("\n")
        if block in text:
            continue
        # One archived entry per ID, even when its title was edited.
        if unique and re.search(rf"(?m)^#{{2,3}} {re.escape(key)}(?: — .*)?\s*$", text):
            raise ValueError(f"{location} already holds a different {key} entry; reconcile the two copies, or "
                             f"run `ro archive restore {key}` before revising an archived discovery")
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    project.atomic_text(path, text)


def _replace_unchanged(project: Project, name: str, read: str, replacement: str) -> None:
    """Coordination files are edited without the project lock; never overwrite a concurrent edit.

    The archive files are already written, and a rerun skips blocks they hold, so stopping
    here loses nothing.
    """
    if _text(project, name) != read:
        raise ValueError(f"{name} changed while archiving; nothing in it was replaced, rerun `ro archive`")
    project.atomic_text(project.root / name, replacement)


def _index_cost(index: list[tuple[int, str]]) -> int:
    """Bytes an entry adds to the whole (unclipped) startup index, with its separator."""
    return len("\n".join(line for _number, line in index).encode("utf-8")) + 2


def archive_discoveries(project: Project, before: str = "", dry_run: bool = False) -> str:
    if before and not DATE.match(before):
        raise ValueError("--before must be YYYY-MM-DD")
    mode = project.settings().get("verification", "cross-host-once")
    with project.lock():
        text = _text(project, "discoveries.md")
        lines = _lines(text)
        in_use = _in_use(project)
        size, target = len(index_text(text, clip=False).encode("utf-8")), INDEX_WARN_BYTES // 2
        chosen = []
        for key, start, end, index, archived in _discovery_entries(text):
            block = lines[start:end]
            if archived or key in in_use or not _settled(block, mode):
                continue
            date = _field(block, "Date")
            if before:
                if not (DATE.match(date) and date < before):
                    continue
            elif size <= target:
                break
            chosen.append((key, start, end, date))
            size -= _index_cost(index)
        if not chosen:
            if not before and size <= target:
                return f"Nothing to archive: the startup index is {size // 1024} KiB, within its target."
            return ("Nothing to archive: no settled (VERIFIED) discovery outside live plan items and handoff state"
                    + (f" is dated before {before}." if before else " remains; entries awaiting review or a "
                       "challenge answer stay in the index until they settle."))
        current = _with_stubs(text, chosen)
        groups: dict[str, list[tuple[str, str]]] = {}
        for key, start, end, date in chosen:
            groups.setdefault(_archive_name("discoveries", date), []).append((key, "".join(lines[start:end])))
        summary = (f"{len(chosen)} discoveries to " + ", ".join(sorted(groups)) +
                   f" ({', '.join(key for key, *_ in chosen)}); startup index "
                   f"{len(index_text(current, clip=False).encode('utf-8')) // 1024} KiB")
        if dry_run:
            return "Would archive " + summary
        for location, blocks in groups.items():
            _append_archive(project, location, "Archived discoveries", blocks, unique=True)
        _replace_unchanged(project, "discoveries.md", text, current)
    return ("Archived " + summary + ". Log it as a handoff event with heading `none` "
            "(Discovery updates: none — archive, no experiment).")


def _archived_blocks(project: Project, identifier: str) -> list[tuple[str, int, int]]:
    """(location, start, end) of every full entry for `identifier` under docs/archive/."""
    found = []
    for path in sorted((project.root / ARCHIVE_DIR).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        found += [(f"{ARCHIVE_DIR}/{path.name}", start, end)
                  for key, start, end, _index, _archived in _discovery_entries(text) if key == identifier]
    return found


def _drop_block(project: Project, location: str, start: int, end: int) -> None:
    # The block runs to the next heading, so its own trailing blank lines leave with it.
    lines = _lines((project.root / location).read_text(encoding="utf-8"))
    project.atomic_text(project.root / location, "".join(lines[:start] + lines[end:]).rstrip("\n") + "\n")


def restore_discovery(project: Project, identifier: str, dry_run: bool = False) -> str:
    """Move an archived discovery back over its stub so it can be revised and archived again.

    The live entry is written first; the archived copy is removed afterwards, so an
    interrupted restore leaves both copies and a rerun only removes the archived one.
    """
    if not identifier:
        raise ValueError("ro archive restore needs a discovery ID")
    with project.lock():
        text = _text(project, "discoveries.md")
        selected = [entry for entry in _discovery_entries(text) if entry[0] == identifier]
        if len(selected) != 1:
            raise ValueError(f"{identifier} must identify exactly one discovery in discoveries.md")
        _key, start, end, _index, archived = selected[0]
        copies = _archived_blocks(project, identifier)
        if not archived:
            if not copies:
                return f"Nothing to restore: {identifier} is not archived."
            if dry_run:
                return f"Would remove the leftover archived copy of {identifier} from {copies[0][0]}"
            for location, block_start, block_end in reversed(copies):
                _drop_block(project, location, block_start, block_end)
            return (f"Finished restoring {identifier}: the live entry stays in discoveries.md and its archived "
                    f"copy left {copies[0][0]}.")
        matching = [copy for copy in copies if copy[0] == archived]
        if len(matching) != 1:
            raise ValueError(f"{archived} must hold exactly one {identifier} entry; restore it by hand")
        location, block_start, block_end = matching[0]
        block = _lines((project.root / location).read_text(encoding="utf-8"))[block_start:block_end]
        if dry_run:
            return f"Would restore {identifier} from {location}"
        ending = _ending(text)
        restored = [line.rstrip("\r\n") + ending for line in block]
        while restored and not restored[-1].strip():
            restored.pop()
        lines = _lines(text)
        lines[start:end] = restored + [ending]
        _replace_unchanged(project, "discoveries.md", text, "".join(lines))
        _drop_block(project, location, block_start, block_end)
    return (f"Restored {identifier} from {location}; revise it in discoveries.md, and `ro archive discoveries` "
            "moves it again once it settles. Log it as a handoff event with heading `none`.")


def _with_stubs(text: str, chosen: list[tuple[str, int, int, str]]) -> str:
    """Replace each chosen entry with its heading, archive location, state and clipped finding."""
    lines, ending = _lines(text), _ending(text)
    for _key, start, end, date in sorted(chosen, key=lambda item: item[1], reverse=True):
        block = [line.rstrip("\r\n") for line in lines[start:end]]
        stub = [block[0], f"- Archived: {_archive_name('discoveries', date)}"]
        stub += [line for line in block if line.startswith("- Cross-check:")]
        stub += [_clip(line) for line in block if line.startswith("- Finding:")]
        lines[start:end] = [line + ending for line in stub] + [ending]
    return "".join(lines)


def _events(text: str) -> list[tuple[int, int, str, str, str]]:
    """(start, stop, date, slot, key) of each dated event, wherever the checker reads one.

    Instruments, external actions and fenced examples are not events; any heading ends one.
    """
    visible = _unfenced(text)
    events, current, area = [], None, ""
    for index, line in enumerate(visible):
        if line.startswith("## "):
            area = line[3:].strip().lower()
        if re.match(r"^#{1,3} ", line):
            if current:
                events.append((current[0], index, *current[1:]))
            match = EVENT.match(line)
            current = (index, *match.groups()) if match and area not in ("instruments", "external actions") else None
    if current:
        events.append((current[0], len(visible), *current[1:]))
    return events


def _resolved(block: list[str], key: str) -> set[str]:
    """Items an event finishes, takes over or removes, as the checker counts them."""
    action = _field(block, "Action")
    resolved = set(re.findall(rf"(?:took over|removed) ({H_PATTERN})", action))
    if action.startswith("took over"):
        return resolved
    if key == "session":
        return resolved | set(H_ID.findall(_field(block, "Completed")))
    return resolved | ({key} if H_ID.fullmatch(key) else set())


def _resolving(lines: list[str], events: list, chosen: list, live_items: set[str]) -> list:
    """Chosen events a kept event still depends on.

    A kept event that queued an item needs the event that finished, took over or removed
    it; otherwise the checker reports that item as lost. Keeping one can add needs of its
    own, so repeat until nothing more is needed.
    """
    chosen_starts = {event[0] for event in chosen}
    kept = [event for event in events if event[0] not in chosen_starts]
    released: list = []
    while True:
        needed = {item for start, stop, *_ in kept
                  for item in H_ID.findall(_field(lines[start:stop], "New plan items"))} - live_items
        found = [event for event in chosen if event not in released
                 and _resolved(lines[event[0]:event[1]], event[3]) & needed]
        if not found:
            return released
        released += found
        kept += found


def archive_events(project: Project, before: str = "", dry_run: bool = False) -> str:
    if before and not DATE.match(before):
        raise ValueError("--before must be YYYY-MM-DD")
    with project.lock():
        text = _text(project, "handoff.md")
        lines = _lines(text)
        events = _events(text)
        if not events:
            return "Nothing to archive: handoff.md has no dated events."
        live_items = set(H_ID.findall(_active_text(_text(project, "plan.md"), PLAN_SECTIONS)))
        # Each slot's latest event may be an open session summary; it stays.
        latest = {slot: start for start, _stop, _date, slot, _key in events}
        size, target = len(text.encode("utf-8")), HANDOFF_WARN_BYTES // 2
        chosen = []
        for start, stop, date, slot, key in events:
            if before:
                if date >= before:
                    continue
            elif size <= target:
                break
            # Stage events of live items gate their launches; events naming a live item stay with it.
            if latest[slot] == start or key.split("/", 1)[0] in live_items:
                continue
            chosen.append((start, stop, date, key))
            size -= len("".join(lines[start:stop]).encode("utf-8"))
        for event in _resolving(lines, events, chosen, live_items):
            chosen.remove(event)
            size += len("".join(lines[event[0]:event[1]]).encode("utf-8"))
        chosen = [(start, stop, date) for start, stop, date, _key in chosen]
        if not chosen:
            if not before and size <= target:
                return f"Nothing to archive: handoff.md is {size // 1024} KiB, within its target."
            return ("Nothing to archive: every remaining event names a live item or is its slot's latest" +
                    (f", or is dated from {before} on." if before else "; Shared state and slot sections stay."))
        groups: dict[str, list[tuple[str, str]]] = {}
        for start, stop, date in chosen:
            block = "".join(lines[start:stop])
            groups.setdefault(_archive_name("handoff", date), []).append((block.splitlines()[0], block))
        summary = f"{len(chosen)} events to " + ", ".join(sorted(groups)) + f"; handoff.md about {size // 1024} KiB"
        if dry_run:
            return "Would archive " + summary
        for location, blocks in groups.items():
            _append_archive(project, location, "Archived handoff events", blocks, unique=False)
        drop = {index for start, stop, _date in chosen for index in range(start, stop)}
        kept = "".join(line for index, line in enumerate(lines) if index not in drop)
        _replace_unchanged(project, "handoff.md", text, _history(project, kept, sorted(groups)))
    return f"Archived {summary}. Log it as a handoff event with heading `none`."


def _history(project: Project, text: str, locations: list[str]) -> str:
    """Keep one summary line per archive file under '## Archived history'."""
    ending, lines = _ending(text), _lines(text)
    start = next((index for index, line in enumerate(lines) if line.rstrip("\r\n") == HISTORY), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += ending
        lines += [ending, HISTORY + ending]
        start = len(lines) - 1
    stop = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    section = lines[start + 1:stop]
    while section and not section[-1].strip():
        section.pop()
    for location in locations:
        archive = (project.root / location).read_text(encoding="utf-8")
        stamps = sorted(re.findall(r"(?m)^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — ", archive))
        row = (f"- [{location}]({location}): {len(stamps)} events, {stamps[0]} to {stamps[-1]} "
               f"(moved by `ro archive events`){ending}")
        existing = next((index for index, line in enumerate(section) if f"]({location})" in line), None)
        if existing is None:
            if section and section[-1].strip() and not section[-1].startswith("- ["):
                section.append(ending)
            section.append(row)
        else:
            section[existing] = row
    if stop < len(lines):
        section.append(ending)
    lines[start + 1:stop] = section
    return "".join(lines)
