"""New-session slot decisions shared by SessionStart and brief (no host probes)."""

from __future__ import annotations

import datetime as dt
import os
import re
import string

from ro_markdown import mask_fences, unfenced
from ro_state import Project, duration

FREE = {"unassigned", "released"}
ORDER = [*string.ascii_uppercase, *(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase)]


def now() -> dt.datetime:
    return dt.datetime.now()


def _plain(value: str) -> str:
    """Ownership labels are data, never instructions copied into hook context."""
    return re.sub(r"[^A-Za-z0-9 _.-]", "", str(value))[:64] or "unknown"


def candidates(project: Project, user: str = "") -> list[dict]:
    from ro_records import (CLAIM, COMPUTE_CLAIM, SHARED_SECTION, _active_text,
                            _items, _slot_sections, _text, registered_jobs)
    from ro_jobs import protected_job
    handoff = _text(project, "handoff.md")
    slots = _slot_sections(handoff)
    activity: dict[str, list[dt.datetime]] = {slot: [] for slot in slots}
    claimed = set()

    def record(slot, stamp):
        if slot in activity:
            try:
                activity[slot].append(dt.datetime.fromisoformat(stamp))
            except ValueError:
                pass

    for line in unfenced(handoff):
        if match := re.match(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — ([A-Z]{1,2}) — ", line):
            record(match[2], match[1])
    for _key, _start, _end, fields in _items(_text(project, "plan.md")):
        if match := CLAIM.fullmatch(fields.get("Claimed", "")):
            claimed.add(match[1])
            record(match[1], match[2])
    for line in unfenced(_active_text(handoff, SHARED_SECTION)):
        if line.startswith("- Active compute:"):
            for entry in line.partition(":")[2].split(";"):
                if match := COMPUTE_CLAIM.fullmatch(entry.strip()):
                    stamp = re.search(r"since ([\d -]+\d:\d\d)\)", entry)
                    if stamp:
                        record(match[2], stamp[1])
    jobs = registered_jobs(project)
    cutoff = now() - dt.timedelta(seconds=duration(project.settings()["stale_slot_after"]))
    result = []
    for slot in sorted(slots, key=ORDER.index):
        fields = slots[slot]
        host = fields.get("Current host", "unknown")
        free = host.lower() in FREE
        # Registry activity protects ownership even when a local process cannot
        # be inspected (remote executors and orphaned supervisors included).
        active_jobs = [job for job in jobs if job.get("slot") == slot
                       and protected_job(job)]
        last = max(activity[slot], default=None)
        resumable = bool(last or slot in claimed or any(fields.get(key, "").lower() not in
                         {"", "none", "none yet", "read discoveries, then the plan",
                          "choose the highest-priority item you may work on"}
                         for key in ("Resumable state", "Next action")))
        result.append({"slot": slot, "host": host, "user": fields.get("Current user", "none"),
                       "last": last, "jobs": active_jobs, "resumable": resumable,
                       "eligible": free or bool(user and fields.get("Current user") == user),
                       "stale": not free and not active_jobs and last is not None and last < cutoff})
    return result


def ambiguous(rows: list[dict]) -> bool:
    eligible = [row for row in rows if row["eligible"]]
    # The unique, nonstale path remains automatic even with a resume point.
    return (any(row["stale"] for row in rows) or len(eligible) > 1 or
            (not eligible and any(row["resumable"] for row in rows)))


def recommended(rows: list[dict]) -> dict:
    return min(rows, key=lambda row: (not row["stale"], bool(row["jobs"]),
                                      not row["resumable"], not row["eligible"], ORDER.index(row["slot"])))


def decision_summary(project: Project, rows: list[dict]) -> str:
    choice = recommended(rows)["slot"]
    lines = ["Slot not selected: choose continuation or parallel work."]
    lines.append(f"Ask one question: Which slot should this new session use? Continue slot {choice} "
                 "(resume its Next action; reclaim it if its session has ended) [recommended]; "
                 "Start a new slot for parallel work; Use slot <X>.")
    for row in rows:
        stamp = row["last"].strftime("%Y-%m-%d %H:%M") if row["last"] else "unknown"
        jobs = ", ".join(_plain(job.get("id", "unknown")) for job in row["jobs"]) or "none"
        lines.append(f"Candidate {row['slot']}: Current host/user {_plain(row['host'])}/{_plain(row['user'])}; "
                     f"last activity {stamp}; running jobs {jobs}" + ("; stale" if row["stale"] else ""))
    session = project.explicit_session
    prefix = ("ro --session " + session if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}", session)
              else "ro")
    lines.append(f"After the choice: {prefix} --slot <slot> brief (or RO_SLOT); "
                 "brief --intent parallel for a new slot; brief --reclaim for an ended stale session.")
    return "\n".join(lines)


def _event(slot: str, host: str, user: str, action: str, result: str) -> str:
    return (f"### {now():%Y-%m-%d %H:%M} — {slot} — none\n- Host: {host}\n- User: {user}\n"
            f"- Action: {action}\n- Result: {result}\n- Artifacts: none\n"
            "- Discovery updates: none — session routing\n- Review verdict: none\n"
            "- Resource: none\n- Other executor: none\n- New plan items: none — session routing\n")


def _ownership(text: str, slot: str, host: str, user: str) -> str:
    from ro_records import HANDOFF_SECTIONS, _active_text
    match = re.search(rf"^### Agent: {slot}\r?\n(.*?)(?=^#|\Z)",
                      _active_text(text, HANDOFF_SECTIONS), re.M | re.S)
    if not match:
        raise ValueError(f"slot {slot} has no active handoff section")
    body = text[match.start(1):match.end(1)]
    for label, value in (("Current host", host), ("Current user", user)):
        field = re.search(rf"^- {label}:[^\r\n]*", mask_fences(body), re.M)
        if not field:
            raise ValueError(f"slot {slot} needs {label}")
        body = body[:field.start()] + f"- {label}: {value}" + body[field.end():]
    return text[:match.start(1)] + body + text[match.end(1):]


def _persist_choice(project: Project, *, rows: list[dict], host: str, user: str,
                    parallel: bool, reason: str = "") -> None:
    from ro_settings import TRANSACTION
    from init_research_orchestrator import (agent_sections, handoff_agent_sections, insert_before_heading,
                                           set_shared_line, shared_line, write_atomically)
    from ro_records import _text
    if (project.root / TRANSACTION).exists():
        raise ValueError("finish the pending project migration before changing session ownership")
    text = _text(project, "handoff.md")
    files = {}
    if not user or user == "none":
        users = [name.strip() for name in (shared_line(text, "Users") or "").split(",")
                 if re.fullmatch(r"[A-Za-z0-9_-]+", name.strip()) and name.strip() not in {"none", "unknown"}]
        user = users[0] if len(users) == 1 else "none"
    if parallel:
        used = {row["slot"] for row in rows}
        # Never reuse an old namespace merely because it has no active section.
        for source in (text, _text(project, "plan.md")):
            used.update(re.findall(r"^#{2,3} Agent: ([A-Z]{1,2})\s*$", mask_fences(source), re.M))
            used.update(re.findall(r"\b[HDIXN]-([A-Z]{1,2})-\d+\b", mask_fences(source)))
        from ro_records import registered_jobs
        used.update(job.get("slot") for job in registered_jobs(project))
        slot = next((slot for slot in ORDER if slot not in used), None)
        if slot is None:
            raise ValueError("no unused session slots remain")
        project.slot_registered = False
        project.slot = slot
        text = insert_before_heading(text, "## Completed / review log", handoff_agent_sections([slot]))
        listed = shared_line(text, "Active agent(s)") or ""
        text = set_shared_line(text, "Active agent(s)", ", ".join(filter(None, [listed, slot])))
        if project.settings()["workflow"] == "classic":
            files[project.root / "plan.md"] = _text(project, "plan.md").rstrip() + "\n\n" + agent_sections([slot])
        stale = ", ".join(row["slot"] for row in rows if row["stale"]) or "none"
        result = f"new slot {slot} for parallel work ({reason}); stale slots: {stale}; existing work preserved"
        action = f"started new slot {slot} for parallel work ({reason})"
    else:
        slot = project.slot
        action = f"reclaimed slot {slot} after stale session (user choice)"
        result = "claims, Resumable state and jobs preserved; resume Next action"
    text = _ownership(text, slot, host, user)
    if user != "none":
        users = [value.strip() for value in (shared_line(text, "Users") or "").split(",")
                 if value.strip() not in {"", "none", "none yet"}]
        if user not in users:
            text = set_shared_line(text, "Users", ", ".join([*users, user]))
    text = insert_before_heading(text, "## Archived history", _event(slot, host, user, action, result))
    files[project.root / "handoff.md"] = text
    if len(files) > 1:
        write_atomically(project.root, files, {"from": "session", "to": "session"})
    else:
        project.atomic_text(project.root / "handoff.md", text)
    project.slot_selected = True
    if project.explicit_session:
        project.register_slot()
        project.write_json(project.session_file, {"slot": slot, "decision": result})
    project.slot_decision = result


def startup(project: Project, *, user: str = "", host: str = "", intent: str = "",
            questions_allowed: bool = True, reclaim: bool = False) -> str:
    """Return one decision question or select a route; never infer reclaim consent."""
    import ro_settings as rs
    user = user or os.environ.get("RO_USER", "")
    if user and not re.fullmatch(r"[A-Za-z0-9_-]+", user):
        raise ValueError("user must be one word of letters, digits, '-' or '_'")
    if intent not in {"", "continue", "parallel"}:
        raise ValueError("session intent must be continue or parallel")
    if reclaim and (not project.slot_selected or intent == "parallel"):
        raise ValueError("reclaim requires a user-chosen --slot or RO_SLOT and an ended stale session")
    if project.slot_selected and not reclaim and not intent:
        if project.explicit_session and not project.slot_registered:
            project.register_slot()
        return ""
    if not (project.root / "handoff.md").is_file():
        return ""
    with project.lock():
        rows = candidates(project, user)
        if not rows:
            return ""
        if reclaim:
            row = next((row for row in rows if row["slot"] == project.slot), None)
            if not row or not row["stale"]:
                raise ValueError("reclaim requires a stale taken slot without running/attention jobs")
            _persist_choice(project, rows=rows, host=_plain(host or rs.detect_host()),
                            user=user or row["user"], parallel=False)
            return ""
        uncertain = ambiguous(rows)
        if intent == "parallel" or (not intent and uncertain and
                                     (project.settings()["autonomy"] == "away" or not questions_allowed)):
            _persist_choice(project, rows=rows, host=_plain(host or rs.detect_host()), user=user or "none",
                            parallel=True, reason="user choice" if intent == "parallel" else "questions disabled")
            return ""
        if intent == "continue":
            row = next((row for row in rows if row["slot"] == project.slot), None) if project.slot_selected else recommended(rows)
            if row is None:
                raise ValueError("continue requires an existing handoff slot")
            if row["slot"] != project.slot:
                project.slot_registered = False
            project.slot = row["slot"]
            project.slot_selected = True
        elif uncertain:
            return decision_summary(project, rows)
        else:
            eligible = [row for row in rows if row["eligible"]]
            if len(eligible) == 1:
                project.slot = eligible[0]["slot"]
                project.slot_selected = True
        if project.explicit_session and project.slot_selected:
            project.register_slot()
        return ""
