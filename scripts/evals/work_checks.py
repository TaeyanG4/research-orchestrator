"""Work-profile acceptance checks kept separate from the shared evaluation harness."""
from __future__ import annotations

import re
import subprocess
import os
import json

if __package__:
    from .proc import no_window_flags
else:
    from proc import no_window_flags


def helpers():
    # Load shared parsers only when grading; checks.py registers these functions.
    if __package__:
        from . import checks
    else:
        import checks
    return checks


def light_ordering(ctx):
    checks = helpers()
    plan = ctx.text("plan.md")
    items = {key: checks.fields(value) for key, value in checks.blocks(plan, "H").items()}
    scores = {"Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority"}
    pointer = re.search(r"^Next: (H-[A-Z]+-\d+)\s*$", plan.split("\n## ", 1)[0], re.M)
    selected = pointer.group(1) if pointer else next(iter(items), "")
    action = checks.slot(ctx.text("handoff.md")).get("Next action", "")
    return bool(items and selected in items and selected in re.findall(r"\bH-[A-Z]+-\d+\b", action)
                and all(not scores & item.keys() for item in items.values())), f"Next: {selected}; action: {action}; items: {items}"


def session_summary(ctx):
    checks = helpers()
    records = checks.events(ctx.text("handoff.md"))
    session = [record for record in records if record.splitlines()[0].endswith(" — session")]
    required = {"Host", "User", "Action", "Result", "Completed"}
    return (len(records) == len(session) == 1 and required <= checks.fields(session[0]).keys(),
            f"Setup events: {records}")


def no_routine_discovery(ctx):
    records = helpers().blocks(ctx.text("discoveries.md"), "D")
    return not records, f"Setup discoveries: {list(records)}"


def compact_items(ctx):
    checks = helpers()
    records = checks.blocks(ctx.text("plan.md"), "H")
    items = {key: checks.fields(value) for key, value in records.items()}
    required = {"Claimed", "Evidence", "Stages"}
    shapes = [required | {goal, step} for goal in ("Hypothesis", "Goal") for step in ("Next test", "Next step")]
    optional = {"Ready by", "Important stages"}
    # Operational dates and review boundaries add meaning, not bookkeeping.
    # Count the source lines too: parsing into a dict hides repeated fields.
    valid = bool(items and all(
        set(item) - optional in shapes and all(value.strip() for value in item.values())
        and len(re.findall(r"^- [^:\n]+:", checks.unfenced(records[key]), re.M)) == len(item)
        for key, item in items.items()))
    return valid, f"Queued fields: {items}"


def preparation_complete(ctx):
    inventory = ctx.text("inventory.txt").splitlines()
    readiness = ctx.text("readiness.md").lower()
    return (inventory == ["alpha.txt", "bravo.log", "charlie.txt"]
            and re.search(r"\b(?:3|three)\b", readiness) is not None
            and re.search(r"conversion.*\bnot (?:yet )?started\b", readiness) is not None), (
                f"Inventory: {inventory}; readiness: {readiness}")


def session_completions(ctx):
    checks = helpers()
    sessions = checks.events(ctx.text("work-snapshot/handoff.md"), "session")
    completed = re.findall(r"\bH-[A-Z]+-\d+\b", checks.fields(sessions[0]).get("Completed", "")) if sessions else []
    queued = checks.blocks(ctx.text("work-snapshot/plan.md"), "H")
    return (len(sessions) == 1 and len(set(completed)) >= 2 and not set(completed) & queued.keys(),
            f"Work sessions: {len(sessions)}; completed: {completed}; queued: {list(queued)}")


def reusable_discovery(ctx):
    checks = helpers()
    records = {key: checks.fields(value) for key, value in checks.blocks(
        ctx.text("work-snapshot/discoveries.md"), "D").items()}
    # Check the conclusion, not keywords that also occur in its opposite.
    # The case asks for structured fields so this remains deterministic without
    # guessing the meaning of arbitrary prose or sending a scripted pass to a judge.
    expected = {"selection_rule": "suffix-only", "decision": "reject",
                "required_inputs": ["alpha.txt", "bravo.log", "charlie.txt"],
                "omitted_inputs": ["bravo.log"]}
    findings = []
    for record in records.values():
        try:
            findings.append(json.loads(record.get("Finding", "")))
        except (ValueError, TypeError):
            findings.append(None)
    valid = (len(records) == 1 and findings == [expected]
             and all("trial.md" in record.get("Evidence", "") for record in records.values()))
    return valid, f"Reusable findings: {records}; expected conclusion: {expected}"


def history_preserved(ctx):
    checks = helpers()
    sessions = checks.events(ctx.text("work-snapshot/handoff.md"), "session")
    settings = checks.fields(ctx.text("agents.md"))
    valid = (len(sessions) == 1 and sessions[0].rstrip() in ctx.text("handoff.md")
             and settings.get("Preset") == "solo-research" and settings.get("Profile") == "research")
    return valid, f"Research preset: {settings.get('Preset')}; original session retained: {valid}"


def strict_checker(ctx):
    result = subprocess.run([ctx.python, str(ctx.checker_skill / "scripts" / "check_project.py"),
                             str(ctx.outputs), "--strict"], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=30, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                            creationflags=no_window_flags())
    evidence = (result.stdout + result.stderr).strip()
    return result.returncode == 0 and "CONSISTENCY:" in result.stdout, evidence


def compact_bookkeeping(ctx):
    checks = helpers()
    items = checks.blocks(ctx.text("queued-plan.md"), "H")
    sessions = checks.events(ctx.text("work-snapshot/handoff.md"), "session")
    empty = {"Artifacts", "Review verdict", "Resource", "Other executor", "New plan items"}
    fields = checks.fields(sessions[0]) if len(sessions) == 1 else {}
    blank = {key for key in empty & fields.keys() if fields[key].strip().lower() in {"", "none"}}
    valid = len(items) >= 2 and all(len(checks.fields(item)) <= 5 for item in items.values()) and bool(fields) and not blank
    return valid, f"Queued field counts: {[len(checks.fields(item)) for item in items.values()]}; empty session fields: {blank}"


WORK_CHECKS = {
    "work-project-start": {"06-light-ordering": light_ordering, "07-session-summary": session_summary,
                           "08-no-routine-discovery": no_routine_discovery, "09-compact-items": compact_items},
    "work-project-session-history": {"01-preparation-complete": preparation_complete,
                                     "02-session-completions": session_completions,
                                     "03-reusable-discovery": reusable_discovery,
                                     "04-history-preserved": history_preserved, "05-checker-clean": strict_checker,
                                     "06-compact-bookkeeping": compact_bookkeeping},
}
