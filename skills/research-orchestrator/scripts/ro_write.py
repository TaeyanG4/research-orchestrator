"""Commands that write records for the agent (`ro event`, `ro set-field`, `ro seal`) and the
delegation brief header (`ro brief --delegate`).

Hand-written records carried guessed times, broke field formats and converted line endings
(2026-11 enveda mistake log: T1 timestamps, T2 record edits). These commands take the time from the
clock, keep every untouched byte, and validate the proposed file with the checker itself before
writing, so a record is refused when written instead of when a later command reads it. Delegated
agents never read the project's memory or rules (half of that log's entries), so their brief header
is generated from the project's settings instead of being retyped.
"""

from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from ro_ids import D_PATTERN, H_PATTERN, X_PATTERN
from ro_markdown import unfenced
from ro_settings import TRANSACTION
from ro_state import Project


EVENT_ORDER = ("Action", "Result", "Artifacts", "Discovery updates", "Review verdict", "Resource",
               "Other executor", "New plan items", "Decision", "Review artifact")
EVENT_REQUIRED = ("Action", "Result", "Discovery updates", "New plan items")
EVENT_DEFAULTS = {"Artifacts": "none", "Review verdict": "none", "Resource": "none", "Other executor": "none"}
EVENT_KEY = re.compile(rf"(?:{H_PATTERN}(?:/s[0-9]+)?|none)")
# Record-format checks a written record must not newly fail. A changed stage legitimately waits
# for its review receipt, so event.stage.review is reported, not refused.
REFUSED_PREFIXES = ("event.", "records.", "external.", "handoff.", "discovery.", "plan.", "ext.")
REVIEW_PENDING = {"event.stage.review"}


def _read(project: Project, name: str) -> str:
    try:
        with (project.root / name).open(encoding="utf-8", newline="") as source:
            return source.read()
    except FileNotFoundError:
        return ""


def _newline(text: str) -> str:
    return "\r\n" if text.count("\r\n") > text.count("\n") - text.count("\r\n") else "\n"


def _issues(project: Project, proposed: dict[str, str] | None = None) -> list:
    from check_project import Checker
    checker = Checker(project.root, proposed_files=proposed or {})
    checker.run(quiet=True)
    return checker.issues


def _validated_write(project: Project, name: str, build) -> list[str]:
    """Build from the current text, compare checker findings, then write if the file is unchanged.

    Validation runs outside the project lock (a full check takes seconds on large records); the
    write happens under it only when the file still holds the bytes that were validated.
    """
    from ro_state import atomic_text
    _no_pending_transaction(project)
    for _attempt in range(2):
        original = _read(project, name)
        proposed = build(original)
        notes = _compare(project, {name: proposed})
        with project.lock():
            if _read(project, name) == original:
                atomic_text(project.root / name, proposed)
                return notes
    raise ValueError(f"{name} changed while it was being validated; run the command again")


# What to do when the checker refuses a write for these reasons.
REFUSAL_HINTS = {
    "handoff.slot.dangling": "a slot's Current thread or Next action names this item: update yours with "
                             "`ro set-field slot <Field> <value>`, or ask that slot's owner",
    "event.finished.queued": "a bare item heading means the item finished: use a stage key (H-A-01/s2) or `none`, "
                             "or finish it with `ro close-item`",
    "event.item.lost": "queue each item named under New plan items in plan.md first",
}


def _no_pending_transaction(project: Project) -> None:
    if (project.root / TRANSACTION).is_file():
        raise ValueError("an interrupted record transaction is pending; run `ro close-item --recover` first")


def _compare(project: Project, proposed: dict[str, str]) -> list[str]:
    """Refuse record-format problems the proposed files would add; return other new findings as notes."""
    before_issues, after_issues = _issues(project), _issues(project, proposed)
    exact = lambda issues: Counter((i.severity, i.check, i.message, i.record, i.field) for i in issues)
    new = exact(after_issues) - exact(before_issues)
    refused = [(check, f"{sev} {check}: {message}") for (sev, check, message, _r, _f) in new.elements()
               if sev in ("ERROR", "WARN") and check.startswith(REFUSED_PREFIXES) and check not in REVIEW_PENDING]
    if refused:
        hints = [REFUSAL_HINTS[check] for check in dict.fromkeys(check for check, _text in refused)
                 if check in REFUSAL_HINTS]
        raise ValueError("refused; the checker would report:\n  " + "\n  ".join(text for _c, text in refused[:8])
                         + "".join(f"\nnext: {hint}" for hint in hints))
    # Notes ignore message text, so a size that grew by a few bytes is not reported as new.
    known = {(i.severity, i.check, i.record, i.field) for i in before_issues}
    return list(dict.fromkeys(f"{i.severity} {i.check}: {i.message}" for i in after_issues
                              if i.severity in ("ERROR", "WARN") and (i.severity, i.check, i.record, i.field) not in known))


def _slot_identity(project: Project) -> tuple[str, str]:
    from ro_jobs import _launch_identity
    try:
        return _launch_identity(project)
    except ValueError as exc:
        raise ValueError(str(exc).replace("before launch", "before writing an event")) from exc


def _field_lines(source: str) -> dict[str, str]:
    """Parse `- Field: value` lines; anything else (paragraphs, nested bullets, duplicates) is refused."""
    fields: dict[str, str] = {}
    for number, line in enumerate(source.splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"- ([A-Za-z][\w /-]*):[ \t]*(.*)", line.rstrip())
        if not match:
            raise ValueError(f"line {number} is not a `- Field: value` line; keep each field on one line")
        if match[1] in fields:
            raise ValueError(f"line {number} repeats the field {match[1]}")
        fields[match[1]] = match[2].strip()
    return fields


def event(project: Project, key: str, given: dict[str, str | None], source: str | None = None) -> str:
    """Append one dated event with clock time, slot identity and checker validation."""
    if key == "session":
        raise ValueError("a work session summary is updated in place, not appended: re-read handoff.md and edit "
                         "that summary's lines; `ro event` writes item, stage and `none` events")
    if not EVENT_KEY.fullmatch(key):
        raise ValueError("event key must be an item (H-A-01, completing it), a stage (H-A-01/s2) or none")
    flags = {name: value for name, value in given.items() if value is not None}
    if source is not None:
        if flags:
            raise ValueError("use either --from or field options, not both")
        flags = _field_lines(Path(source).read_text(encoding="utf-8"))
    for name in ("Host", "User"):
        if name in flags:
            raise ValueError(f"{name} comes from your slot's handoff section; drop it from the event")
    unknown = sorted(set(flags) - set(EVENT_ORDER))
    if unknown:
        raise ValueError("unknown event fields: " + ", ".join(unknown) + "; allowed: " + ", ".join(EVENT_ORDER))
    fields = {**EVENT_DEFAULTS, **flags}
    missing = [name for name in EVENT_REQUIRED if not fields.get(name)]
    if missing:
        raise ValueError("event needs " + ", ".join(missing) + " (Discovery updates and New plan items take IDs "
                         "or `none — <reason>`)")
    if any("\n" in value or "\r" in value for value in fields.values()):
        raise ValueError("each field is one line")
    if fields.get("Decision") not in (None, "changed", "operational", "unchanged"):
        raise ValueError("Decision must be changed or operational (work sessions may also use unchanged)")
    if fields.get("Decision") == "changed" and not re.search(rf"\b{D_PATTERN}\b", fields["Discovery updates"]):
        raise ValueError("Decision: changed needs its discovery ID under Discovery updates")
    host, user = _slot_identity(project)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"### {stamp} — {project.slot} — {key}", f"- Host: {host}", f"- User: {user}"]
    lines += [f"- {name}: {fields[name]}" for name in EVENT_ORDER if fields.get(name)]

    def build(text: str) -> str:
        newline = _newline(text)
        block = newline.join(lines) + newline
        marker = re.search(r"(?m)^## Archived history\b", text)
        if marker:
            head = text[:marker.start()].rstrip("\r\n")
            return head + newline * 2 + block + newline + text[marker.start():]
        return text.rstrip("\r\n") + newline * 2 + block

    notes = _validated_write(project, "handoff.md", build)
    return "\n".join(["wrote:", *lines] + (["notes:", *notes] if notes else []))


# Fields owned by another command or by attribution, per record kind.
OWNED = {
    "H": {"Claimed": "ro claim / ro release"},
    "slot": {"Current host": "the session start (ro brief)", "Current user": "the session start (ro brief)"},
    "X": {"Status": "ro external"},
    "D": {"Reviews": "the verification workflow", "Cross-check": "the verification workflow",
          "Date": "the original discovery", "Session": "the original discovery", "User": "the original discovery"},
}
X_FIXED_AFTER_ATTEMPT = ("Candidate", "Destination", "Expected", "Retry of")


def _record_span(lines: list[str], identifier: str, project: Project) -> tuple[int, int, str]:
    """Find one record's heading line and end in fence-masked lines."""
    if identifier == "slot":
        pattern = re.compile(rf"### Agent: {re.escape(project.slot)}\s*")
    else:
        pattern = re.compile(rf"#{{2,3}} {re.escape(identifier)}(?: .*)?")
    hits = [index for index, line in enumerate(lines) if pattern.fullmatch(line)]
    if len(hits) != 1:
        raise ValueError(f"{identifier} must have exactly one heading (found {len(hits)})")
    start = hits[0]
    depth = len(lines[start]) - len(lines[start].lstrip("#"))
    end = start + 1
    while end < len(lines):
        heading = re.match(r"^(#+) ", lines[end])
        if heading and len(heading.group(1)) <= depth:
            break
        end += 1
    return start, end, lines[start]


def set_field(project: Project, identifier: str, name: str, value: str) -> str:
    """Replace one existing single-line field of one record, keeping every other byte."""
    if "\n" in value or "\r" in value:
        raise ValueError("the value must be one line")
    if identifier == "slot":
        kind, file = "slot", "handoff.md"
    elif re.fullmatch(H_PATTERN, identifier):
        kind, file = "H", "plan.md"
    elif re.fullmatch(D_PATTERN, identifier):
        kind, file = "D", "discoveries.md"
    elif re.fullmatch(X_PATTERN, identifier):
        kind, file = "X", "handoff.md"
    else:
        raise ValueError("record must be an H-, D- or X- ID, or `slot` for your own handoff section")
    owner = OWNED.get(kind, {}).get(name)
    if owner:
        raise ValueError(f"{name} is written by {owner}, not by set-field")
    changed: dict[str, str] = {}

    def build(text: str) -> str:
        raw = text.splitlines(keepends=True)
        masked = unfenced(text)
        start, end, _heading = _record_span(masked, identifier, project)
        hits = [index for index in range(start + 1, end) if re.match(rf"- {re.escape(name)}:(?:[ \t]|$)", masked[index])]
        if len(hits) != 1:
            raise ValueError(f"{identifier} must have exactly one `- {name}:` line to replace (found {len(hits)}); "
                             "add a missing field by hand")
        if kind == "X" and name in X_FIXED_AFTER_ATTEMPT:
            status = [masked[i] for i in range(start + 1, end) if masked[i].startswith("- Status:")]
            if status and status[0].partition(":")[2].strip() != "prepared":
                raise ValueError(f"{name} of an attempted action is history; record a retry instead")
        line = raw[hits[0]]
        ending = line[len(line.rstrip("\r\n")):]
        changed["old"] = line.rstrip("\r\n")
        raw[hits[0]] = f"- {name}: {value}" + ending
        return "".join(raw)

    notes = _validated_write(project, file, build)
    return "\n".join([f"{identifier}: {changed.get('old', '')} -> - {name}: {value}"] + (["notes:", *notes] if notes else []))


def seal(project: Project, target: str, check: bool = False) -> str:
    """Record (or check) a file's raw-byte SHA256 and the clock time in `<file>.seal.json`.

    Preregistrations and correction notes carried guessed times (2026-11-14 16:58, 17:53, 18:27);
    the seal is the machine time. Sealing the same bytes again returns the first seal unchanged; a
    changed file is refused, and its correction belongs in a new file with its own seal.
    """
    path = Path(target)
    path = (path if path.is_absolute() else Path.cwd() / path).resolve()
    if not path.is_relative_to(project.root) or not path.is_file():
        given = "" if Path(target).is_absolute() else f" ({target} resolved from {Path.cwd()})"
        raise ValueError(f"seal needs an existing file inside the project: {path}{given}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar = path.with_name(path.name + ".seal.json")
    relative = path.relative_to(project.root).as_posix()
    existing = None
    if sidecar.is_file():
        existing = json.loads(sidecar.read_text(encoding="utf-8"))
    if check:
        if existing is None:
            raise ValueError(f"{relative} has no seal")
        if existing.get("sha256") != digest:
            raise ValueError(f"{relative} changed after its seal of {existing.get('sealed_at')} "
                             f"(sealed {existing.get('sha256', '')[:12]}, now {digest[:12]})")
        return f"{relative}: matches its seal of {existing['sealed_at']} (sha256 {digest})"
    if existing is not None:
        if existing.get("sha256") == digest:
            return f"{relative}: already sealed at {existing['sealed_at']} (sha256 {digest})"
        raise ValueError(f"{relative} was sealed at {existing.get('sealed_at')} with different bytes; keep the "
                         "sealed version and write the correction to a new file, then seal that")
    record = {"path": relative, "sha256": digest, "bytes": path.stat().st_size,
              "sealed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "slot": project.slot, "session": project.session}
    from ro_state import atomic_text
    with project.lock():
        if sidecar.exists():
            raise ValueError(f"{relative} was sealed concurrently; run `ro seal --check {relative}`")
        atomic_text(sidecar, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return f"sealed {relative} at {record['sealed_at']} (sha256 {digest})"


DELEGATE_MARKER = "ro-delegate: v1"
# What each check actually stops, so a delegated agent reads its real scope (2026-11: `shell.heredoc`
# was read as a ban on every heredoc and `shell.background` as a ban on host background tools).
CHECK_SCOPE = {
    "shell.background": "a shell-level background job (`cmd &`, `disown`); the host's own background tool is allowed",
    "shell.detach": "nohup, setsid, Start-Job, or Start-Process without -Wait",
    "shell.heredoc": "a heredoc whose delimiter is unquoted and whose body has backticks",
    "shell.cd": "a bare trailing `cd` that the next call would not keep",
    "jobs.mutate-bound": "writing a path a running job owns (its scripts, inputs, run folder)",
    "external.gate": "an outward action (submit, push, publish) outside `ro external`",
    "publish.scan": "pushing content that matches the secret scan",
}


def delegate(project: Project, item: str) -> str:
    """Print the header a delegated agent's brief starts with; it carries the Brief requirements marker."""
    from ro_records import _items, _text
    import shlex
    import sys
    base = item.split("/", 1)[0]
    if base != "none" and not re.fullmatch(H_PATTERN, base):
        raise ValueError("delegate needs an H-ID item or stage (H-A-01/s2), or `none` for a task outside the plan")
    if not project.slot:
        raise ValueError("select your slot (--slot or RO_SLOT) before delegating")
    fields, title = {}, ""
    if base != "none":
        plan = _text(project, "plan.md")
        found = [(key, start, values) for key, start, _end, values in _items(plan) if key == base]
        if not found:
            raise ValueError(f"{base} is not an item in plan.md; queue it, or delegate `none` for a task outside the plan")
        _key, start, fields = found[0]
        heading = unfenced(plan)[start].split(" — ", 1)
        title = heading[1].strip() if len(heading) > 1 else ""
    values = project.settings()
    windows_bash = values.get("environment", "") == "windows/bash"
    blocked = [part.strip() for part in values.get("block", "none").split(",") if part.strip() in CHECK_SCOPE]
    enforcement = values.get("enforcement", "off")
    ro = shlex.join([sys.executable, str(Path(__file__).resolve().with_name("ro.py"))])
    run_dir = f"runs/{dt.datetime.now():%Y%m%d}_{base.lower() if base != 'none' else 'task'}"
    long_runs = (f"- Runs longer than about 3 minutes: `{ro} launch --item {item} --expect <duration> --run-dir {run_dir} "
                 "-- <command>`, then `ro monitor <job>`." if base != "none" else
                 "- Runs longer than about 3 minutes: stop and ask the delegating session, which launches them under "
                 "a plan item; no shell background runs.")
    lines = [
        DELEGATE_MARKER,
        f"# Delegated: {item}{' — ' + title if title else ''}",
        "",
        "## Rules (generated by `ro brief --delegate`; follow them even where no hook checks you)",
        f"- Write only inside {run_dir}/ (create it), or the folder this brief names instead, and files it names. "
        "Do not edit agents.md, plan.md, "
        "discoveries.md, handoff.md or docs/tools.md: report record changes and new tools instead.",
        "- Delete nothing: no recursive or wildcard deletes. Keep failed outputs and rerun under a new name (_r2).",
        "- Resources: stay within the CPU workers, RAM and GPU this brief states; if it states none, ask first. "
        "Read big arrays once outside loops.",
        "- Times: take every time from the clock (`date '+%Y-%m-%d %H:%M'`) or seal the file "
        f"(`{ro} seal <file>`); never type or estimate a time.",
        long_runs + " Do not edit a script while a run uses it; copy it under a new name.",
        f"- `ro` calls: `RO_SLOT={project.slot} {ro} <command>` (never `python -I`).",
        "- Judgement rules: quote them from their source file with its path; do not paraphrase.",
    ]
    if windows_bash:
        lines.append("- Windows Bash tool: it turns \\\\ into \\ before bash runs, even inside quotes and heredocs. "
                     "Write any code or path with backslashes through the file tool and run the file.")
    if blocked and enforcement == "block":
        lines.append("- Hooks block (where the host delivers them): "
                     + "; ".join(f"`{check}` — {CHECK_SCOPE[check]}" for check in blocked) + ".")
    lines.append("- Project rules: read the `## Project rules` section of agents.md; its standing rules apply to you.")
    lines += [
        "",
        "## Report (these sections, in order)",
        "1. Result: what was measured, on which set (n) and against which baseline ID.",
        "2. Verified vs inferred: mark each claim; an explanation you did not check in code or data stays inferred.",
        "3. Rule check: any rule above you broke, how, and what it touched; `none` if none.",
        "4. Mistakes: each with a one-line candidate fix for the skill or project; `none` if none.",
        "5. Tools to register: new reusable scripts with path and purpose.",
        "6. Failed outputs kept: paths.",
        "7. Decisions needed: anything this brief left ambiguous, before you chose.",
        "",
    ]
    if base != "none":
        lines.append("## Item")
        lines += [f"- {name}: {fields[name]}" for name in ("Hypothesis", "Goal", "Next test", "Stages", "Important stages")
                  if fields.get(name)]
        lines.append("")
    lines += ["## Task", "<write the task here>"]
    return "\n".join(lines)


def _draft_sections(text: str) -> tuple[list[tuple[str, list[str]]], list[str], list[str]]:
    """Split a close-item draft into discovery blocks, event field lines and follow-up item lines."""
    discoveries: list[tuple[str, list[str]]] = []
    event: list[str] | None = None
    follow: list[str] | None = None
    current: list[str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        heading = re.fullmatch(r"## (.*)", line.rstrip())
        if heading:
            title = heading[1].strip()
            if match := re.match(rf"({D_PATTERN})\b", title):
                discoveries.append((match[1], [line.rstrip()]))
                current = discoveries[-1][1]
            elif title == "Event" and event is None:
                event = current = []
            elif title == "Follow-ups" and follow is None:
                follow = current = []
            else:
                raise ValueError(f"draft line {number}: sections are `## D-…` discoveries, `## Event` and "
                                 "`## Follow-ups` (each once)")
        elif current is None:
            if line.strip():
                raise ValueError(f"draft line {number} comes before any section")
        else:
            current.append(line.rstrip())
    if event is None:
        raise ValueError("the draft needs a `## Event` section with the completion event's fields")
    return discoveries, event, follow or []


def close_item(project: Project, item: str, source: str | None = None, dry_run: bool = False,
               recover: bool = False) -> str:
    """Finish an item in one transaction: its discoveries, completion event, follow-ups and plan removal.

    Hand-written closing scripts stopped half way three times (2026-11-12 02:42, 2026-11-14 08:33,
    2026-11-19 03:49). Everything is assembled and checked in memory, then written with the journaled
    multi-file transaction that template migrations use, which an interrupted run completes or rolls back.
    """
    import init_research_orchestrator as init
    from ro_records import CLAIM, _items, registered_jobs
    from ro_jobs import monitor_outcome, running_job
    with project.lock():  # Two sessions must not apply the same journal at once.
        recovered = init.recover_transaction(project.root)
        if recovered:  # The journal is gone; this transaction's own backups are no longer needed.
            for name in ("plan.md", "discoveries.md", "handoff.md"):
                (project.root / (name + ".close-backup")).unlink(missing_ok=True)
    if recover:
        return f"close-item recovery: {recovered or 'no interrupted transaction'}"
    if recovered:
        raise ValueError(f"an interrupted transaction was {recovered}; read the files, then run close-item again")
    if not re.fullmatch(H_PATTERN, item):
        raise ValueError("close-item takes a whole item ID such as H-A-01, not a stage")
    if not source:
        raise ValueError("close-item needs --from <draft>: `## D-…` discoveries, `## Event` fields, `## Follow-ups`")
    discoveries, event_lines, follow_lines = _draft_sections(Path(source).read_text(encoding="utf-8"))
    fields = _field_lines("\n".join(event_lines))
    for name in ("Host", "User"):
        if name in fields:
            raise ValueError(f"{name} comes from your slot's handoff section; drop it from the event")
    unknown = sorted(set(fields) - set(EVENT_ORDER))
    if unknown:
        raise ValueError("unknown event fields: " + ", ".join(unknown))
    fields = {**EVENT_DEFAULTS, **fields}
    missing = [name for name in EVENT_REQUIRED if not fields.get(name)]
    if missing:
        raise ValueError("the event needs " + ", ".join(missing))
    listed = set(re.findall(rf"\b{D_PATTERN}\b", fields["Discovery updates"]))
    if {key for key, _lines in discoveries} - listed:
        raise ValueError("list every drafted discovery under the event's Discovery updates")
    queued = re.findall(rf"(?m)^### ({H_PATTERN})\b", "\n".join(follow_lines))
    if set(queued) - set(re.findall(rf"\b{H_PATTERN}\b", fields["New plan items"])):
        raise ValueError("list every follow-up item under the event's New plan items")
    unreported = [str(job.get("id")) for job in registered_jobs(project)
                  if str(job.get("item", "")).split("/", 1)[0] == item
                  and (running_job(job) or not monitor_outcome(job))]
    if unreported:
        raise ValueError(f"{item} still has running or unreported jobs: {', '.join(unreported)}; monitor them first")
    host, user = _slot_identity(project)
    names = ("plan.md", "discoveries.md", "handoff.md")
    originals = {name: _read(project, name) for name in names}
    plan = originals["plan.md"]
    found = [(start, end, values) for key, start, end, values in _items(plan) if key == item]
    if len(found) != 1:
        raise ValueError(f"{item} must be exactly one item in plan.md")
    start, end, values = found[0]
    claim = CLAIM.fullmatch(values.get("Claimed", ""))
    if "Claimed" in values and (not claim or claim.group(1) != project.slot):
        raise ValueError(f"claim {item} for slot {project.slot} before closing it")
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    proposed = {}
    lines = plan.splitlines(keepends=True)
    newline = _newline(plan)
    while end > start and not lines[end - 1].strip():
        end -= 1  # Keep the blank line that separates the next item.
    remaining = lines[:start] + lines[end:]
    if follow_lines:
        block = newline.join(line for line in follow_lines).strip("\n") + newline
        section = (r"## Queue\b" if values.get("Claimed") is not None or "## Queue" in plan
                   else rf"## Agent: {re.escape(project.slot)}\b")
        joined = "".join(remaining)
        heading = re.search(rf"(?m)^{section}.*$", joined)
        if not heading:
            raise ValueError("no plan section to queue the follow-ups in")
        after = re.search(r"(?m)^## ", joined[heading.end():])
        cut = heading.end() + (after.start() if after else len(joined) - heading.end())
        joined = joined[:cut].rstrip("\r\n") + newline * 2 + block + (newline if after else "") + joined[cut:]
        proposed["plan.md"] = joined
    else:
        proposed["plan.md"] = "".join(remaining)
    if discoveries:
        text = originals["discoveries.md"]
        dnl = _newline(text)
        blocks = [dnl.join(lines_).strip("\n") for _key, lines_ in discoveries]
        proposed["discoveries.md"] = text.rstrip("\r\n") + dnl * 2 + (dnl * 2).join(blocks) + dnl
    handoff = originals["handoff.md"]
    hnl = _newline(handoff)
    event_text = hnl.join([f"### {stamp} — {project.slot} — {item}", f"- Host: {host}", f"- User: {user}"]
                          + [f"- {name}: {fields[name]}" for name in EVENT_ORDER if fields.get(name)]) + hnl
    marker = re.search(r"(?m)^## Archived history\b", handoff)
    proposed["handoff.md"] = (handoff[:marker.start()].rstrip("\r\n") + hnl * 2 + event_text + hnl + handoff[marker.start():]
                              if marker else handoff.rstrip("\r\n") + hnl * 2 + event_text)
    _compare(project, proposed)
    summary = (f"{item}: event {stamp}, {len(discoveries)} discovery(ies), {len(queued)} follow-up item(s), "
               f"removed from plan.md")
    if dry_run:
        return "dry run (nothing written): " + summary
    with project.lock():
        if any(_read(project, name) != originals[name] for name in names):
            raise ValueError("a record changed while close-item validated it; run it again")
        # Own suffixes: a migration's *.pre-migrate backups are evidence that events cite.
        init.write_atomically(project.root, {project.root / name: text for name, text in proposed.items()},
                              {"from": "close-item", "to": item}, temp_suffix=".close-tmp",
                              backup_suffix=".close-backup")
        for name in proposed:  # The journal is gone, so this transaction's own backups are no longer needed.
            (project.root / (name + ".close-backup")).unlink(missing_ok=True)
    return "closed " + summary
