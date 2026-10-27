#!/usr/bin/env python3
"""Create, reconfigure, or migrate the four Research Orchestrator files without losing work.

Setup (see references/presets.md):
  --list-presets                       show the built-in and user presets
  --preset solo-research               start from a preset; flags override its values
  --user kim                           the first user to record
  every setting has a flag (--workflow, --verification, --platform, --platforms, --git, ...);
  the table of settings, values, and defaults is scripts/ro_settings.py

Precedence: a new project uses flag > preset > default, with work defaults when no preset is selected;
--reconfigure uses flag > value stored in agents.md > legacy default;
--reconfigure --preset X uses flag > X > stored > legacy default.

--reconfigure regenerates only the part of agents.md above '## Project rules' and copies that
region verbatim. It refuses when the generated part was edited by hand, unless --force is given.
A Workflow change also needs --migrate, which moves the plan items atomically (backups:
<file>.pre-migrate). --save-preset NAME stores the effective settings as user:NAME.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import string
import sys
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_settings as rs  # noqa: E402  (hard import: the one table of settings)
from ro_ids import H_PATTERN
from ro_markdown import mask_fences, unfenced, visible_lines


SKILL_ROOT = rs.SKILL_ROOT
TEMPLATES = SKILL_ROOT / "templates"
COORDINATION_FILES = ("agents.md", "plan.md", "discoveries.md", "handoff.md")

# Agent names are work slots, assigned in this order: A ... Z, AA ... ZZ.
AGENT_ORDER = [
    *string.ascii_uppercase,
    *(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase),
]
FREE_HOSTS = {"unassigned", "released"}
RESERVED_USER_NAMES = {"claude", "codex", "gpt", "chatgpt", "gemini", "antigravity", "none", "unassigned", "released"}
USER_NAME = re.compile(r"^[^\W_][\w-]{0,31}$")
# {{#if key=a,b}} blocks; values may be hyphenated. Innermost line blocks are resolved first.
IF_LINE_BLOCK = re.compile(r"^\{\{#if (\w+)=([\w,-]+)\}\}\n((?:(?!^\{\{#if ).)*?)^\{\{/if\}\}\n", re.M | re.S)
IF_INLINE_BLOCK = re.compile(r"\{\{#if (\w+)=([\w,-]+)\}\}(.*?)\{\{/if\}\}", re.S)
ITEM_FIELD = re.compile(r"^- ([A-Za-z][A-Za-z/ -]*?(?: \([^)]*\))?):\s?(.*)$")


# ---------- small parsers ----------

def parse_agents(raw: str | None) -> list[str]:
    """Return canonical agent names from a count ("3") or a list ("A,B,C")."""
    if not raw or not raw.strip():
        return ["A"]
    raw = raw.strip()
    if raw.isdigit():
        count = int(raw)
        if not 1 <= count <= len(AGENT_ORDER):
            raise ValueError(f"agent count must be between 1 and {len(AGENT_ORDER)}")
        return AGENT_ORDER[:count]

    canonical = {name.lower(): name for name in AGENT_ORDER}
    names: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        name = canonical.get(item.lower())
        if name is None:
            raise ValueError(
                f"invalid agent name '{item}': use a letter A-Z or two letters AA-ZZ, "
                "never a host or model name such as Claude, Codex, or GPT"
            )
        if name in names:
            raise ValueError(f"duplicate agent name '{name}'")
        names.append(name)
    return names or ["A"]


def parse_user(raw: str | None) -> str | None:
    if raw is None:
        return None
    name = raw.strip()
    if not USER_NAME.match(name):
        raise ValueError(f"invalid user name '{raw}': use one word of letters, digits, '-' or '_' (e.g. kim, user1)")
    if name in AGENT_ORDER:
        raise ValueError(f"user name '{name}' looks like an agent slot; pick something like kim or user1")
    if name.lower() in RESERVED_USER_NAMES:
        raise ValueError(f"user name '{name}' is a host, model, or reserved word; use a person's name")
    return name


# ---------- rendering ----------

def apply_conditions(text: str, conditions: dict[str, str]) -> str:
    """Keep {{#if key=a,b}} ... {{/if}} blocks whose key matches one of the listed values."""
    def keep(match: re.Match[str]) -> str:
        key, values, body = match.groups()
        return body if conditions.get(key) in values.split(",") else ""

    while True:
        resolved = IF_LINE_BLOCK.sub(keep, text)
        if resolved == text:
            break
        text = resolved
    return IF_INLINE_BLOCK.sub(keep, text)


def render(template: Path, values: dict[str, str], conditions: dict[str, str]) -> str:
    text = apply_conditions(template.read_text(encoding="utf-8"), conditions)
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def render_agents(settings: dict[str, str], project: str, version: str | None = None) -> str:
    """The generated part of agents.md (everything above '## Project rules')."""
    version = version or rs.CURRENT_TEMPLATE
    if version not in rs.TEMPLATE_VERSIONS:
        raise ValueError(f"unknown template version '{version}'")
    if version == "v2":
        values = {
            "{{PROJECT_NAME}}": project, "{{PLATFORM_MODE}}": settings["platform_mode"],
            "{{PLATFORMS}}": settings["platforms"], "{{GIT_SYNC}}": settings["git"],
            "{{COLLECTOR}}": settings["collector"], "{{QUEUE_LIMITS}}": settings["queue_limits"],
            "{{REVIEWER}}": settings["reviewer"], "{{FALLBACK}}": settings["fallback"],
        }
        conditions = {"mode": settings["platform_mode"], "git": settings["git"]}
        return render(TEMPLATES / "v2" / "AGENTS.md.template", values, conditions)
    values = {"{{PROJECT_NAME}}": project, "{{RENDER_KEY}}": rs.render_key(settings, version),
              "{{SUMMARY}}": rs.summary_line(settings), "{{SETTINGS_BLOCK}}": rs.settings_block(settings, version),
              "{{READING_POINTERS}}": rs.reading_pointers(settings)}
    values.update({"{{" + setting.key.upper() + "}}": settings[setting.key] for setting in rs.SETTINGS})
    folder = TEMPLATES if version == rs.CURRENT_TEMPLATE else TEMPLATES / version
    return render(folder / "AGENTS.md.template", values, rs.conditions(settings))


def template_metadata(settings: dict[str, str]) -> str:
    return json.dumps({"version": rs.CURRENT_TEMPLATE, "render_key": rs.render_key(settings)}, indent=2) + "\n"


def save_template_metadata(target: Path, settings: dict[str, str]) -> None:
    from ro_state import atomic_text
    atomic_text(target / ".ro" / "template-render.json", template_metadata(settings))


def read_raw_text(path: Path) -> str:
    """Retain line endings in text regions owned by the user."""
    with path.open(encoding="utf-8", newline="") as source:
        return source.read()


def text_newline(text: str) -> str:
    match = re.search(r"\r\n|\n|\r", text)
    return match.group() if match else "\n"


def compose_agents(settings: dict[str, str], project: str, region: str = "", newline: str = "\n") -> str:
    """A full agents.md: the generated part, then the user-owned '## Project rules' region verbatim."""
    if not region:
        region = render(TEMPLATES / "PROJECT_RULES.md.template",
                        {"{{STANDING_RULES_BUDGET}}": str(rs.STANDING_RULES_BUDGET)}, {}).replace("\n", newline)
    return (render_agents(settings, project) + "\n").replace("\n", newline) + region


def comparable(generated: str) -> str:
    """The generated part as hand-edit detection compares it: the whole text above '## Project rules',
    without the template marker and without the recognised '- <Setting>: <value>' lines, whose values
    the user may edit. Any other change — prose above, inside, or below the settings — remains."""
    kept, in_settings = [], False
    for original, visible in visible_lines(generated):
        line = original.rstrip("\r\n")
        if visible and line.startswith("## "):
            in_settings = line.strip() == "## Project settings"
        if visible and rs.MARKER.fullmatch(line.strip()):
            continue
        setting = rs.SETTINGS_LINE.match(line)
        if in_settings and visible and setting and setting.group(1) in rs.BY_LABEL:
            continue
        if in_settings and (not line.strip() or line.strip() in {
                "<details>", "</details>", "<summary>Inactive and default settings (expand to edit)</summary>"}):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def rendered_settings(stored: rs.StoredSettings, current: dict[str, str]) -> dict[str, str]:
    """The settings a v3 file's generated part was made for, as recorded in its template marker."""
    values = dict(current)
    for key in (*rs.RULE_KEYS, "preset"):
        recorded = stored.rendered.get(rs.SETTING[key].condition or key)
        if recorded is not None:
            values[key] = recorded
    # Collector's marker describes a conditional pointer, not the host/model
    # setting itself. Reproduce that old condition only for template comparison.
    if stored.rendered.get("collector") == "off":
        values["collector"] = "off"
    elif stored.rendered.get("collector") == "on" and values.get("collector") == "off":
        values["collector"] = "enabled"
    if "pointers" in stored.rendered:
        values["_reading_pointers"] = stored.rendered["pointers"]
    return values


def rules_state(text: str, stored: rs.StoredSettings, current: dict[str, str]) -> str:
    """'ok', 'stale' (generated for other settings), or 'edited' (the generated part was changed by hand)."""
    body = comparable(rs.split_agents(text)[0])
    project = stored.project or "x"
    if stored.version == "v2":
        if body == comparable(render_agents(current, project, "v2")):
            return "ok"
        for mode in rs.SETTING["platform_mode"].choices:
            for git in rs.SETTING["git"].choices:
                if body == comparable(render_agents({**current, "platform_mode": mode, "git": git}, project, "v2")):
                    return "stale"
        return "edited"
    generated_for = rendered_settings(stored, current)
    if stored.version not in rs.TEMPLATE_VERSIONS:
        return "edited"
    if body != comparable(render_agents(generated_for, project, stored.version)):
        return "edited"
    return "stale" if (stored.version != rs.CURRENT_TEMPLATE or
                       rs.conditions(generated_for) != rs.conditions(current) or
                       rs.reading_pointer_ids(generated_for) != rs.reading_pointer_ids(current)) else "ok"


def agent_sections(names: list[str]) -> str:
    blocks = []
    for name in names:
        blocks.append(
            f"## Agent: {name}\n\n"
            "_No active items yet. Add only actionable unfinished work._\n\n"
            "_Use the item shape above for this project's profile._\n"
        )
    return "\n".join(blocks).rstrip() + "\n"


def queue_section(blocks: list[str] | None = None) -> str:
    if blocks:
        return "## Queue\n\n" + "\n\n".join(blocks) + "\n"
    return ("## Queue\n\n_No items yet. Add only actionable unfinished work; "
            "every item starts with `- Claimed: none`._\n")


def handoff_agent_sections(names: list[str]) -> str:
    blocks = []
    for name in names:
        blocks.append(
            f"### Agent: {name}\n"
            "- Current host: unassigned\n"
            "- Current user: none\n"
            "- Current thread: none yet\n"
            "- Resumable state: read discoveries, then the plan\n"
            "- Blocker: none\n"
            "- Next action: choose the highest-priority item you may work on\n"
        )
    return "\n".join(blocks).rstrip() + "\n"


def render_plan(settings: dict[str, str], project: str, sections: str, *, ordering: str | None = None) -> str:
    conditions = rs.conditions(settings)
    conditions["ordering"] = ordering or ("queue" if settings["preset"] == "solo-research" else "priority")
    conditions["planshape"] = "compact" if settings["profile"] == "work" or settings["preset"] == "quick" else "full"
    return render(TEMPLATES / "PLAN.md.template", {"{{PROJECT_NAME}}": project, "{{PLAN_SECTIONS}}": sections},
                  conditions)


# ---------- files and git ----------

def write_if_missing(path: Path, content: str) -> str:
    if path.exists():
        print(f"[SKIP] {path}")
        return "skip"
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"[CREATE] {path}")
    return "create"


def git_mode_for(target: Path, git: str) -> str:
    """Git sync needs an existing repository; outside one it is switched off and reported, never created."""
    if git == "off" or any((parent / ".git").exists() for parent in (target, *target.parents)):
        return git
    print(f"Notice: Git sync '{git}' was requested but {target} is not inside a git repository, "
          "so Git sync is set to off. Create the repository (and a remote, for push) yourself, "
          f"then run --reconfigure --git {git}. Agents never run git init.", file=sys.stderr)
    return "off"


def crash_point(name: str) -> None:
    """Test hook: RO_TEST_CRASH_AT=<name> ends the process here at once, as a killed process would."""
    if os.environ.get("RO_TEST_CRASH_AT") == name:
        os._exit(75)


def write_durably(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


MigrationJournal = TypedDict("MigrationJournal", {
    "version": int, "started": str, "from": str, "to": str, "phase": str, "files": list[dict[str, str]],
})


def file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def copy_durably(source: Path, target: Path) -> None:
    with source.open("rb") as original, target.open("wb") as copied:
        shutil.copyfileobj(original, copied)
        copied.flush()
        os.fsync(copied.fileno())


def save_transaction(record: Path, data: MigrationJournal) -> None:
    """Keep the previous journal intact if writing the next step is interrupted."""
    pending = record.with_suffix(".json.tmp")
    write_durably(pending, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(pending, record)


def apply_transaction(target: Path, data: MigrationJournal) -> None:
    """Resume either direction; status records intent, while hashes prove a step has finished."""
    forward = data["phase"] == "forward"
    expected = "after" if forward else "before"
    action = "rename" if forward else "restore"
    record = target / rs.TRANSACTION
    if not forward:
        crash_point("rollback")
    for step, entry in enumerate(data["files"], start=1):
        path = target / entry["name"]
        entry["status"] = "installing" if forward else "restoring"
        save_transaction(record, data)
        crash_point(f"before-{action}-{step}")
        if file_digest(path) != entry[expected]:
            source = path.with_name(path.name + (".migrate-tmp" if forward else ".pre-migrate"))
            if file_digest(source) != entry[expected]:
                raise OSError(f"cannot {action} {path.name}: {source.name} is missing or does not match the journal")
            if forward:
                os.replace(source, path)
            else:
                copy_durably(source, path)  # the backup stays intact even if this copy is interrupted
        crash_point(f"{action}-{step}")
        if file_digest(path) != entry[expected]:
            raise OSError(f"{path.name} does not match the migration's {data['phase']} target")
        entry["status"] = "installed" if forward else "restored"
        save_transaction(record, data)
    # A missing temp never proves installation. Verify all targets before cleaning up the journal.
    if any(file_digest(target / entry["name"]) != entry[expected] for entry in data["files"]):
        raise OSError(f"migration {data['phase']} is incomplete; journal kept for recovery")
    for entry in data["files"]:
        (target / (entry["name"] + ".migrate-tmp")).unlink(missing_ok=True)
    if "template_after" in data:
        from ro_state import atomic_text
        atomic_text(target / ".ro" / "template-render.json",
                    data["template_after" if forward else "template_before"])
    record.unlink()


def rollback_transaction(target: Path, data: MigrationJournal) -> None:
    data["phase"] = "rollback"
    save_transaction(target / rs.TRANSACTION, data)
    apply_transaction(target, data)


def write_atomically(target: Path, files: dict[Path, str], meta: dict[str, str]) -> None:
    """Replace several files as one transaction.

    1. every new file is written to <file>.migrate-tmp and every original is copied to <file>.pre-migrate;
    2. a journal records the forward phase, hashes and each file's status before any replacement;
    3. every step journals its intent before changing a file; 4. all target hashes are checked before cleanup.
    A failure first journals the rollback phase, then restores backups with the same restartable protocol.
    """
    record = target / rs.TRANSACTION
    entries: list[dict[str, str]] = []
    for path, content in files.items():
        temp = path.with_name(path.name + ".migrate-tmp")
        write_durably(temp, content)
        backup = path.with_name(path.name + ".pre-migrate")
        copy_durably(path, backup)
        before, after = file_digest(backup), file_digest(temp)
        if before is None or after is None:
            raise OSError(f"migration preparation lost a temp or backup for {path.name}")
        entries.append({"name": path.name, "before": before, "after": after, "status": "pending"})
    record.parent.mkdir(parents=True, exist_ok=True)
    data: MigrationJournal = {"version": 2, "started": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                              "from": meta["from"], "to": meta["to"], "phase": "forward", "files": entries}
    data.update({key: meta[key] for key in ("template_before", "template_after") if key in meta})
    save_transaction(record, data)
    crash_point("record")
    try:
        apply_transaction(target, data)
    except BaseException:
        rollback_transaction(target, data)
        raise


def recover_transaction(target: Path) -> str | None:
    """Finish a migration a killed process left behind; return 'completed', 'rolled back', or None.

    A journaled rollback is always resumed as rollback. In the forward phase, only a matching target
    hash proves a consumed temp was installed; otherwise a missing temp triggers rollback.
    """
    record = target / rs.TRANSACTION
    if not record.is_file():
        return None
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        if data["version"] == 1:
            # Old journals cannot prove a forward step. Preserve their backups by resuming as rollback.
            entries = []
            for name in data["files"]:
                if name not in COORDINATION_FILES:
                    raise ValueError("unknown migration file")
                digest = file_digest(target / f"{name}.pre-migrate")
                if digest is None:
                    raise ValueError(f"missing backup for {name}")
                entries.append({"name": name, "before": digest, "after": "", "status": "pending"})
            data.update(version=2, phase="rollback", files=entries)
            save_transaction(record, data)
        if data["version"] != 2 or data["phase"] not in ("forward", "rollback") or not data["files"]:
            raise ValueError("unknown migration version or phase, or no files")
        names = []
        for entry in data["files"]:
            name = entry["name"]
            if name not in COORDINATION_FILES or name in names:
                raise ValueError("unknown or duplicate migration file")
            names.append(name)
            required = ("before", "after") if data["phase"] == "forward" else ("before",)
            if any(not re.fullmatch(r"[0-9a-f]{64}", entry[key]) for key in required):
                raise ValueError("missing migration hash")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"cannot read {record}; journal kept for recovery: {exc}") from exc
    if data["phase"] == "rollback":
        apply_transaction(target, data)
        outcome = "rolled back"
    else:
        try:
            apply_transaction(target, data)
            outcome = "completed"
        except OSError:
            rollback_transaction(target, data)
            outcome = "rolled back"
    print(f"[RECOVER] the interrupted migration (Workflow {data.get('from', '?')} → {data.get('to', '?')}, started "
          f"{data.get('started', '?')}) was {outcome}; backups stay as *.pre-migrate. Run check_project.py next.")
    return outcome


# ---------- plan.md blocks (migration) ----------

@dataclass
class PlanItem:
    item_id: str
    section: str
    lines: list[str]
    fields: dict[str, str] = field(default_factory=dict)
    index: int = 0

    def priority_key(self) -> tuple[int, int, int, int]:
        def number(name: str, missing: int) -> int:
            value = self.fields.get(name, "").strip()
            return int(value) if value.isdigit() else missing
        return (-number("Priority", -1), number("Cost", 4), -number("Information", -1), self.index)


def parse_plan_items(text: str) -> list[PlanItem]:
    """Every '### H-' item block outside code fences, with its section and verbatim lines."""
    items: list[PlanItem] = []
    section, current = "", None
    for original, visible in visible_lines(text):
        line = original.rstrip("\r\n")
        if visible and line.startswith("#"):
            current = None
            if line.startswith("## "):
                section = line[3:].strip()
            elif line.startswith("### H-"):
                item_id = line[4:].split(" — ", 1)[0].strip()
                current = PlanItem(item_id, section, [line], index=len(items))
                items.append(current)
                continue
        if current is not None:
            current.lines.append(line)
            match = ITEM_FIELD.match(line)
            if match and visible:
                current.fields.setdefault(match.group(1), match.group(2).strip())
    for item in items:
        while item.lines and not item.lines[-1].strip():
            item.lines.pop()
    return items


def item_prefix(item_id: str) -> str:
    return item_id.split("-")[1] if re.fullmatch(H_PATTERN, item_id) else ""


def handoff_slots(handoff: str) -> dict[str, str]:
    """Slot -> Current host, from the '### Agent:' sections of handoff.md."""
    slots: dict[str, str] = {}
    current = ""
    for line in unfenced(handoff):
        if line.startswith("### Agent: "):
            current = line[len("### Agent: "):].strip()
            slots[current] = ""
        elif line.startswith("### ") or line.startswith("## "):
            current = ""
        elif current and line.startswith("- Current host:"):
            slots[current] = line.split(":", 1)[1].strip()
    return slots


def shared_line(handoff: str, label: str) -> str | None:
    match = re.search(rf"^- {re.escape(label)}: (.*)$", mask_fences(handoff), re.M)
    return match.group(1).strip() if match else None


def set_shared_line(handoff: str, label: str, value: str) -> str:
    match = re.search(rf"^- {re.escape(label)}: [^\r\n]*", mask_fences(handoff), re.M)
    return handoff[:match.start()] + f"- {label}: {value}" + handoff[match.end():] if match else handoff


def insert_before_heading(text: str, heading: str, block: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$", mask_fences(text), re.M)
    newline = text_newline(text)
    offset = match.start() if match else len(text)
    head, tail = text[:offset], text[offset:]
    separator = "" if not head or head.endswith(newline * 2) else (newline if head.endswith(newline) else newline * 2)
    added = block.rstrip("\r\n").replace("\r\n", "\n").replace("\n", newline)
    return head + separator + added + newline + (newline if tail else "") + tail


def pending_milestones(settings: dict[str, str]) -> str:
    """Start configured checkpoints explicitly pending rather than inventing progress."""
    return "; ".join(f"{share} pending" for share in rs.guard_thresholds(settings["guard_thresholds"])["milestones"])


def ensure_guard_sections(handoff: str, settings: dict[str, str]) -> str:
    """Add newly enabled registry sections while leaving every existing record untouched."""
    conditions = rs.conditions(settings)
    defaults = []
    if settings["profile"] == "competition" or settings["collector"] != "off":
        defaults += [("Current best", "none yet"), ("Active compute", "none"), ("Plan collection", "idle")]
    if conditions["phaseclock"] == "on":
        defaults.append(("Milestones", pending_milestones(settings)))
    if defaults:
        shared = re.search(r"^## Shared state\r?\n(.*?)(?=^#{1,2} |\Z)", mask_fences(handoff), re.M | re.S)
        if shared:
            newline = text_newline(handoff)
            missing = [f"- {label}: {value}" for label, value in defaults
                if not re.search(rf"^- {label}:", shared[1], re.M)]
            if missing:
                offset = shared.start(1)
                handoff = handoff[:offset] + newline.join(missing) + newline + handoff[offset:]
    for condition, heading in (("instruments", "## Instruments"), ("externalactions", "## External actions")):
        if conditions[condition] == "on" and not re.search(rf"^{re.escape(heading)}\s*$", mask_fences(handoff), re.M):
            handoff = insert_before_heading(handoff, "## Active handoff — Agent sections", heading)
    return handoff


def dropped_lines(plan: str, template_header: str, placeholders: set[str]) -> list[str]:
    """Non-item lines a migration does not carry over: text in plan sections outside item blocks, and header
    text above the first section when it differs from the template's own header (the new header comes from
    the template). Only byte-identical generated placeholders and rebuilt section headings are exempt."""
    dropped: list[str] = []
    header: list[str] = []
    seen_section, in_item = False, False
    for original, visible in visible_lines(plan):
        line = original.rstrip("\r\n")
        if not seen_section:
            if visible and line.startswith("## "):
                seen_section = True
            else:
                header.append(line)
                continue
        if visible and line.startswith("#"):
            in_item = line.startswith("### H-")
            if line.startswith("## Agent: ") or line.rstrip() == "## Queue" or in_item:
                continue
        if in_item or not line.strip() or line in placeholders:
            continue
        dropped.append(line)
    changes = difflib.SequenceMatcher(a=template_header.splitlines(), b=header, autojunk=False)
    header_drops = [line for tag, _a, _b, start, end in changes.get_opcodes() if tag in ("insert", "replace")
                    for line in header[start:end] if line.strip() and line not in placeholders]
    retained = {line for line in plan_schedule(plan).values()}
    return [line for line in header_drops if line not in retained] + dropped


def plan_schedule(plan: str) -> dict[str, str]:
    """Keep scheduling metadata only from the header, never a sample or item body."""
    header: dict[str, str] = {}
    live = {item.item_id for item in parse_plan_items(plan)}
    for line in unfenced(plan):
        if line.startswith("## "):
            break
        match = re.fullmatch(r"(?:- )?(Ordering|Next):\s*(.*)", line)
        if match and ((match[1] == "Ordering" and match[2] in {"queue", "priority"}) or
                      (match[1] == "Next" and match[2] in live)):
            header[match[1]] = line
    return header


def retain_plan_schedule(original: str, rendered: str) -> str:
    metadata = plan_schedule(original)
    if not metadata:
        return rendered
    index = rendered.find("\n## ")
    header = "".join(line for line, visible in visible_lines(rendered[:index])
                     if not (visible and re.fullmatch(r"(?:- )?(Ordering|Next):\s*.*", line.rstrip("\r\n"))))
    return header.rstrip() + "\n\n" + "\n".join(metadata.values()) + "\n" + rendered[index:]


def normalize_plan_aliases(plan: str, settings: dict[str, str]) -> str:
    """Carry compatible work/research fields across profiles without changing their evidence."""
    compact = settings["profile"] == "work" or settings["preset"] == "quick"
    aliases = {"Goal": "Goal" if compact else "Hypothesis",
               "Hypothesis": "Goal" if compact else "Hypothesis",
               "Hypothesis/Goal": "Goal" if compact else "Hypothesis",
               "Next step": "Next test"}
    output = []
    in_item = False
    for original, visible in visible_lines(plan.replace("\r\n", "\n")):
        if visible and original.startswith("#"):
            in_item = original.startswith("### H-")
        match = ITEM_FIELD.match(original.rstrip("\r\n")) if visible and in_item else None
        if match and match[1] in aliases:
            original = original.replace("- " + match[1] + ":", "- " + aliases[match[1]] + ":", 1)
        output.append(original)
    normalized = "".join(output)
    if compact:
        return normalized
    # Work by source positions, not block replacement: an identical fenced
    # example may precede the real item and must remain an example.
    lines = list(visible_lines(normalized))
    additions: dict[int, list[str]] = {}
    following = {"Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost",
                 "Priority", "Resource", "Parallel", "Other", "Next test"}
    for start, (original, visible) in enumerate(lines):
        if not visible or not original.startswith("### H-"):
            continue
        end = start + 1
        fields = {}
        while end < len(lines):
            original, visible = lines[end]
            if visible and original.startswith("#"):
                break
            match = ITEM_FIELD.match(original.rstrip("\r\n")) if visible else None
            if match:
                fields.setdefault(match[1], end)
            end += 1
        if "Sources" not in fields and "Hypothesis" in fields:
            additions.setdefault(fields["Hypothesis"], []).append("- Sources: none\n")
        if "Improvement" not in fields:
            before = next((offset for name, offset in fields.items() if name in following), None)
            if before is not None:
                additions.setdefault(before, []).append("- Improvement: none\n")
    return "".join("".join(additions.get(index, [])) + original
                   for index, (original, _visible) in enumerate(lines))


def normalize_discovery_review_fields(text: str) -> str:
    """Add pending review state without rewriting evidence or claiming a review occurred."""
    lines = list(visible_lines(text))
    additions: dict[int, list[str]] = {}
    newline = text_newline(text)
    for index, (original, visible) in enumerate(lines):
        if not visible or not original.startswith("## D-"):
            continue
        end = index + 1
        fields = {}
        while end < len(lines):
            line, live = lines[end]
            if not live or not line.startswith(("- ", "  - ")):
                break
            match = ITEM_FIELD.match(line.rstrip("\r\n"))
            if match:
                fields.setdefault(match[1], end)
            end += 1
        if "Cross-check" not in fields:
            before = next((fields[name] for name in ("Finding", "Evidence", "Implication", "Reviews")
                           if name in fields), end)
            additions.setdefault(before, []).append("- Cross-check: PENDING" + newline)
        if "Reviews" not in fields:
            additions.setdefault(end, []).append("- Reviews: none" + newline)
    output = []
    for index in range(len(lines) + 1):
        if index in additions:
            if output and not output[-1].endswith(("\r", "\n")):
                output.append(newline)
            output.extend(additions[index])
        if index < len(lines):
            output.append(lines[index][0])
    return "".join(output)


def plan_to_unified(plan: str, settings: dict[str, str], project: str) -> tuple[str, int]:
    """Classic -> unified: preserve queue scheduling, or sort score-ranked profiles."""
    items = parse_plan_items(plan)
    ordering = plan_schedule(plan).get("Ordering", "").split(":", 1)[-1].strip()
    if settings.get("profile") in {"research", "competition"} and ordering != "queue":
        items.sort(key=PlanItem.priority_key)
    blocks = []
    for item in items:
        visible = unfenced("\n".join(item.lines))
        body = [line for line, live in zip(item.lines[1:], visible[1:]) if not live.startswith("- Claimed:")]
        blocks.append("\n".join([item.lines[0], "- Claimed: none", *body]))
    rendered = render_plan(settings, project, queue_section(blocks), ordering=ordering or "priority")
    return retain_plan_schedule(plan, rendered), len(items)


def plan_to_classic(plan: str, handoff: str, settings: dict[str, str], project: str) -> tuple[str, str, int]:
    """Unified -> classic: every item back to the section named by its ID prefix; Claimed lines dropped."""
    items = parse_plan_items(plan)
    listed_raw = shared_line(handoff, "Active agent(s)") or ""
    listed = [name.strip() for name in listed_raw.split(",") if name.strip()]
    prefixes = []
    for item in items:
        prefix = item_prefix(item.item_id)
        if prefix not in AGENT_ORDER:
            raise ValueError(f"{item.item_id} has no valid slot prefix (H-<Agent>-<NN>); fix it before migrating")
        if prefix not in listed and prefix not in prefixes:
            prefixes.append(prefix)
    new_slots = sorted(prefixes, key=AGENT_ORDER.index)
    sections = []
    for name in listed + new_slots:
        blocks = ["\n".join(line for line, visible in zip(item.lines, unfenced("\n".join(item.lines)))
                            if not visible.startswith("- Claimed:"))
                  for item in items if item_prefix(item.item_id) == name]
        if blocks:
            sections.append(f"## Agent: {name}\n\n" + "\n\n".join(blocks) + "\n")
        else:
            sections.append(agent_sections([name]))
    if new_slots:
        handoff = set_shared_line(handoff, "Active agent(s)", ", ".join(listed + new_slots))
        handoff = insert_before_heading(handoff, "## Completed / review log",
                                        handoff_agent_sections(new_slots))
    ordering = plan_schedule(plan).get("Ordering", "").split(":", 1)[-1].strip()
    rendered = render_plan(settings, project, "\n".join(sections), ordering=ordering or "priority")
    return retain_plan_schedule(plan, rendered), handoff, len(items)


def migration_event(old: str, new: str, count: int, handoff: str, settings: dict[str, str],
                    user: str | None, *, discovery_backup: bool = False) -> tuple[str, str]:
    """Append the one handoff event a migration writes; return (handoff, event)."""
    users_raw = shared_line(handoff, "Users") or "none yet"
    users = [] if users_raw.lower() == "none yet" else [u.strip() for u in users_raw.split(",") if u.strip()]
    if user is None:
        if not users:
            raise ValueError("--migrate records a handoff event and needs a user: pass --user <name>")
        user = users[0]
    elif user not in users:
        handoff = set_shared_line(handoff, "Users", ", ".join([*users, user]))
    listed = [name.strip() for name in (shared_line(handoff, "Active agent(s)") or "A").split(",") if name.strip()]
    host = settings["platforms"].split(",")[0].strip()
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    where = "into ## Queue" if new == "unified" else "back to the sections of their ID prefixes"
    artifacts = "agents.md.pre-migrate; plan.md.pre-migrate; handoff.md.pre-migrate"
    if discovery_backup:
        artifacts += "; discoveries.md.pre-migrate"
    event = (
        f"### {stamp} — {listed[0] if listed else 'A'} — none\n"
        f"- Host: {host}\n"
        f"- User: {user}\n"
        f"- Action: migrated Workflow {old} → {new} (init_research_orchestrator.py --migrate); "
        f"{count} plan item(s) moved {where}\n"
        f"- Result: workflow is now {new}; the previous files are kept as *.pre-migrate\n"
        f"- Artifacts: {artifacts}\n"
        "- Discovery updates: none — workflow migration, no experiment\n"
        "- Review verdict: none\n"
        "- Resource: none\n"
        "- Other executor: none\n"
        "- New plan items: none — migration moves existing items only\n"
    )
    return insert_before_heading(handoff, "## Archived history", event), event


# A migration fixes exactly these findings, so they never block its preflight.
MIGRATION_FIXES = {"settings.workflow.unmigrated"}


def checker_errors(target: Path, proposed_files: dict[str, str] | None = None,
                   proposed_settings: dict[str, str] | None = None) -> list[str]:
    import check_project  # imported here: check_project imports this module

    checker = check_project.Checker(target, proposed_files=proposed_files, proposed_settings=proposed_settings)
    code = checker.run(quiet=True)
    if code == 2:
        return ["the consistency check could not read the project (missing or unreadable files)"]
    return [issue.render() for issue in checker.issues
            if issue.severity == "ERROR" and (proposed_files is not None or issue.check not in MIGRATION_FIXES)]


def transition_records(target: Path, settings: dict[str, str], source: dict[str, str]) -> dict[str, str]:
    """Prepare compatible record changes for every policy transition, before any writes."""
    proposed = {name: read_raw_text(target / name) for name in COORDINATION_FILES[1:]
                if (target / name).is_file()}
    if "plan.md" in proposed:
        plan = proposed["plan.md"]
        newline = text_newline(plan)
        source_compact = source.get("profile") == "work" or source.get("preset") == "quick"
        target_compact = settings["profile"] == "work" or settings["preset"] == "quick"
        if "Ordering" not in plan_schedule(plan) and source_compact != target_compact:
            # Preserve the effective source ordering when the destination has a
            # different implicit default; a policy change is not a queue reorder.
            section = re.search(r"^## ", mask_fences(plan), re.M)
            if section:
                order = "queue" if source_compact else "priority"
                plan = plan[:section.start()] + f"Ordering: {order}" + newline * 2 + plan[section.start():]
        if source_compact != target_compact or source.get("profile") != settings["profile"]:
            plan = normalize_plan_aliases(plan, settings).replace("\n", newline)
        proposed["plan.md"] = plan
    if "discoveries.md" in proposed and source.get("verification") == "self" and settings["verification"] != "self":
        proposed["discoveries.md"] = normalize_discovery_review_fields(proposed["discoveries.md"])
    if "handoff.md" in proposed:
        proposed["handoff.md"] = ensure_guard_sections(proposed["handoff.md"], settings)
    return proposed


def transition_metadata(target: Path, settings: dict[str, str], old: str) -> dict[str, str]:
    stored = rs.read_settings(read_raw_text(target / "agents.md"), target)
    return {"from": old, "to": settings["workflow"],
            "template_before": json.dumps({"version": stored.version,
                "render_key": " ".join(f"{key}={value}" for key, value in stored.rendered.items())}),
            "template_after": template_metadata(settings)}


def migrate(target: Path, settings: dict[str, str], old: str, project: str, agents_text: str,
            args: argparse.Namespace) -> int:
    new = settings["workflow"]
    plan_path, handoff_path = target / "plan.md", target / "handoff.md"
    if not plan_path.is_file() or not handoff_path.is_file():
        print("Error: --migrate needs plan.md and handoff.md", file=sys.stderr)
        return 1
    plan, handoff = read_raw_text(plan_path), read_raw_text(handoff_path)
    plan_newline = text_newline(plan)
    taken = {slot: host for slot, host in handoff_slots(handoff).items() if host.lower() not in FREE_HOSTS}
    if taken and not args.force:
        names = ", ".join(f"{slot} ({host})" for slot, host in taken.items())
        print(f"Error: --migrate needs a quiescent project, but these slots are taken: {names}. "
              "Release them first (Current host: released), or add --force when the only taken slot "
              "is your own session.", file=sys.stderr)
        return 1
    errors = checker_errors(target)
    if errors:
        print("Error: the consistency check reports errors; fix them before migrating:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    stored = rs.read_settings(read_raw_text(target / "agents.md"), target)
    source_settings = rendered_settings(stored, rs.resolve({}, None, stored.values))
    proposed = transition_records(target, settings, source_settings)
    plan, handoff = proposed["plan.md"], proposed["handoff.md"]
    if new == "unified":
        new_plan, count = plan_to_unified(plan, settings, project)
    else:
        new_plan, handoff, count = plan_to_classic(plan, handoff, settings, project)
    new_plan = new_plan.replace("\n", plan_newline)
    review_migration = source_settings.get("verification") == "self" and settings["verification"] != "self"
    handoff, _event = migration_event(old, new, count, handoff, settings, parse_user(args.user),
                                     discovery_backup=review_migration)
    handoff = ensure_guard_sections(handoff, settings)
    old_header = render_plan({**settings, "workflow": old}, project, "").split("\n## ", 1)[0]
    empty_sections = agent_sections(["A"]) if old == "classic" else queue_section()
    placeholders = {line for line in empty_sections.splitlines() if line.startswith("_")}
    dropped = dropped_lines(plan, old_header, placeholders)
    proposed.update({"agents.md": agents_text, "plan.md": new_plan, "handoff.md": handoff})
    errors = checker_errors(target, proposed, settings)
    if errors:
        print("Error: the proposed migration fails consistency checks; no files were changed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    write_atomically(target, {target / name: proposed[name]
                             for name in ("agents.md", "plan.md", "handoff.md", "discoveries.md")
                             if name != "discoveries.md" or review_migration},
                     transition_metadata(target, settings, old))
    print(f"[MIGRATE] Workflow {old} → {new}: {count} plan item(s) moved; backups *.pre-migrate")
    for line in dropped:
        print(f"[DROP] plan.md: {line}")
    if dropped:
        print(f"{len(dropped)} non-item line(s) of plan.md were not carried over; they stay in plan.md.pre-migrate")
    print(f"Settings: {rs.describe(settings)}")
    print("A handoff event with heading 'none' records the migration. Run check_project.py next.")
    return 0


# ---------- commands ----------

def flags_of(args: argparse.Namespace) -> dict[str, str | None]:
    return {setting.key: getattr(args, setting.key) for setting in rs.SETTINGS}


def load_preset_arg(args: argparse.Namespace) -> dict[str, object] | None:
    return rs.load_preset(args.preset) if args.preset else None


def in_repository(target: Path) -> bool:
    return any((parent / ".git").exists() for parent in (target, *target.parents))


def require_answers(target: Path, preset: dict[str, object] | None, flags: dict[str, str | None],
                    stored: dict[str, str], name: str | None) -> None:
    """Report detected defaults; ask only for choices that still have no answer."""
    if rs.single_platform_conflict(preset, flags, stored):
        raise ValueError(f"preset {name} is single-platform; pass --platforms <one host>")
    missing, defaults = rs.question_answers(preset, flags, stored)
    if missing:
        examples = {"--platforms": '"local"', "--environment": "linux/bash", "--language": "en",
                    "--competition": "hub/project", "--phase-clock": "2026-10-01,2026-12-01",
                    "--external-actions": "none", "--git": "off"}
        example_flags = dict.fromkeys([*(rs.SETTING[key].flag for key in preset.get("asks", [])),
                                      *missing, "--environment", "--language"])
        answers = " ".join(f"{flag} {examples[flag]}" for flag in example_flags)
        example = (f"python <skill-root>/scripts/init_research_orchestrator.py . --preset {name} "
                   f"--user operator {answers}")
        raise ValueError(f"preset {name} asks for {', '.join(missing)} (each may be 'off' where that is a value); "
                         "pass them as flags or --answers <json>. Example: " + example)
    for key, value in defaults.items():
        if key == "git" and not in_repository(target):
            continue  # Git sync is asked only inside a git repository
        flag = rs.SETTING[key].flag
        if key in ("environment", "language", "external_actions", "phase_clock"):
            print(f"Info: {rs.SETTING[key].label}: {value} (default; override with {flag})", file=sys.stderr)
        else:
            print(f"Info: preset {name} asks for {flag}; using its default '{value}' (pass {flag} to answer it)",
                  file=sys.stderr)


def save_preset(args: argparse.Namespace, settings: dict[str, str], project: str) -> None:
    summary = f"Reusable {settings['profile']} settings"
    path, replaced = rs.save_user_preset(args.save_preset, settings, summary)
    print(f"[{'REPLACE' if replaced else 'CREATE'}] {path} (use --preset user:{args.save_preset})")


def list_presets() -> int:
    rows = [(name, data) for name, data in rs.list_presets()]
    print(f"{'name':<22} {'profile':<12} {'workflow':<9} {'verification':<19} {'language':<8} summary")
    for name, data in rows:
        print(f"{name:<22} {str(data.get('profile', '?')):<12} {str(data.get('workflow', '?')):<9} "
              f"{str(data.get('verification', '?')):<19} {str(data.get('language', rs.SETTING['language'].default)):<8} "
              f"{data.get('summary', '')}")
    print(f"User presets live in {rs.user_presets_dir()}; save one with --save-preset <name>.")
    return 0


def reconfigure(target: Path, args: argparse.Namespace) -> int:
    agents_md = target / "agents.md"
    if not agents_md.is_file():
        print(f"Error: {agents_md} does not exist; run without --reconfigure first", file=sys.stderr)
        return 1
    text = read_raw_text(agents_md)
    stored = rs.read_settings(text, target)
    project = args.name or stored.project or target.name
    _generated, region = rs.split_agents(text)
    has_settings = "platform_mode" in stored.values and "git" in stored.values
    if not args.force and not has_settings:
        print("Error: agents.md has no Project settings; it predates them. Re-run with --force to replace it.",
              file=sys.stderr)
        return 1
    current = None
    if has_settings:
        try:
            current = rs.resolve({}, None, stored.values)
        except ValueError:
            if not args.force:
                raise
    if not args.force and current is not None and rules_state(text, stored, current) == "edited":
        print("Error: the generated part of agents.md (above '## Project rules') was edited by hand, so "
              "regenerating it would lose those edits. Move your own rules under '## Project rules' at the end "
              "of the file (kept verbatim), or save them elsewhere and re-run with --force.", file=sys.stderr)
        return 1
    flags = flags_of(args)
    preset = load_preset_arg(args)
    require_answers(target, preset, flags, stored.values, args.preset)
    settings = rs.resolve(flags, preset, stored.values)
    settings["guards"] = rs.stamp_guards(settings["guards"], stored.values.get("guards", "off"))
    settings["git"] = git_mode_for(target, settings["git"])
    # The plan files are in the workflow the generated part was made for, even when the Workflow line was
    # edited by hand since: that is the source of a migration.
    old_workflow = rs.files_workflow(stored) if has_settings else rs.SETTING["workflow"].default
    content = compose_agents(settings, project, region, newline=text_newline(text))
    if stored.version == "v2" and (target / "discoveries.md").is_file():
        # Keep the evidence untouched and the exception portable with agents.md;
        # machine-local .ro metadata is deliberately excluded from coordination sync.
        import check_project
        legacy = check_project.Checker(target)
        legacy.run(quiet=True)
        if any(issue.check == "discovery.legacy.invalid" for issue in legacy.issues):
            raise ValueError("restore the invalid legacy review preservation record before reconfiguration")
        if hasattr(legacy, "discoveries") and (manifest := legacy.legacy_review_manifest()):
            content = content.rstrip("\r\n") + text_newline(text) * 2 + manifest.replace("\n", text_newline(text))
    if settings["workflow"] != old_workflow:
        if not args.migrate:
            print(f"Error: Workflow changes from {old_workflow} to {settings['workflow']}; the plan items must move "
                  "too. Re-run with --migrate (see references/workflow-unified.md, Migration).", file=sys.stderr)
            return 1
        code = migrate(target, settings, old_workflow, project, content, args)
    else:
        if args.migrate:
            print(f"Notice: Workflow stays {old_workflow}; checking the settings transition.", file=sys.stderr)
        source = rendered_settings(stored, current or stored.values)
        proposed = transition_records(target, settings, source)
        proposed["agents.md"] = content
        errors = checker_errors(target, proposed, settings)
        if errors:
            print("Error: the proposed settings transition fails consistency checks; no files were changed:",
                  file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            return 1
        changed = {target / name: value for name, value in proposed.items()
                   if read_raw_text(target / name) != value}
        if changed:
            write_atomically(target, changed, transition_metadata(target, settings, old_workflow))
        else:
            save_template_metadata(target, settings)
        print(f"[REWRITE] {agents_md}" + (" (## Project rules kept verbatim)" if region else ""))
        print(f"Settings: {rs.describe(settings)}")
        print("Log the change as a handoff event with heading 'none', then run check_project.py.")
        code = 0
    if code == 0:
        ignore_tool_state(target, settings)
    if code == 0 and args.save_preset:
        save_preset(args, settings, project)
    return code


def ignore_tool_state(target: Path, settings: dict[str, str]) -> None:
    """Keep machine-local state out of coordination sync, preserving existing ignore rules."""
    if settings["git"] == "off":
        return
    path = target / ".gitignore"
    text = read_raw_text(path) if path.exists() else ""
    if ".ro/" not in text.splitlines() and "/.ro/" not in text.splitlines():
        from ro_state import atomic_text
        newline = text_newline(text)
        atomic_text(path, text + (newline if text and not text.endswith(("\n", "\r")) else "") + ".ro/" + newline)


def repair_identity(target: Path, workflow: str, args: argparse.Namespace) -> tuple[list[str], str]:
    """Recover the roster from surviving records instead of silently resetting it to A."""
    def visible(name: str) -> str:
        path = target / name
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        return "\n".join(unfenced(text)) + "\n"

    plan, handoff = visible("plan.md"), visible("handoff.md")
    plan_slots = re.findall(r"^## Agent: (.+)$", plan, re.M)
    handoff_slots = re.findall(r"^### Agent: (.+)$", handoff, re.M)
    shared = re.search(r"^## Shared state\s*\n(.*?)(?=^## |\Z)", handoff, re.M | re.S)
    users = parse_user(args.user) or "none yet"
    if (target / "handoff.md").is_file():
        listed = shared_line(shared[1], "Active agent(s)") if shared else None
        if not listed:
            raise ValueError("cannot recover the agent roster; restore handoff.md Shared state before repair")
        agents = parse_agents(listed)
        if len(handoff_slots) != len(set(handoff_slots)) or set(agents) != set(handoff_slots):
            raise ValueError("handoff.md roster and agent sections disagree; restore them before repair")
        users = shared_line(shared[1], "Users")
        if users is None:
            raise ValueError("cannot recover Users; restore handoff.md Shared state before repair")
        known_users = [] if users == "none yet" else [value.strip() for value in users.split(",")]
        if args.user is not None and parse_user(args.user) not in known_users:
            raise ValueError("repair preserves the stored Users list; restore or update handoff.md before adding a user")
    elif workflow == "classic" and plan_slots:
        agents = parse_agents(",".join(plan_slots))
    elif args.agents is not None:
        agents = parse_agents(args.agents)
    else:
        raise ValueError("cannot recover the complete agent roster; restore handoff.md or pass --agents explicitly")
    if workflow == "classic" and (target / "plan.md").is_file():
        if len(plan_slots) != len(set(plan_slots)) or set(agents) != set(plan_slots):
            raise ValueError("plan.md and the stored agent roster disagree; restore them before repair")
    if args.agents is not None and parse_agents(args.agents) != agents:
        raise ValueError("repair preserves the stored agent roster; conflicting --agents cannot change surviving files")
    return agents, users


def initialize(target: Path, args: argparse.Namespace) -> int:
    agents = parse_agents(args.agents)
    user = parse_user(args.user)
    name = args.name or target.name
    flags = flags_of(args)
    preset = load_preset_arg(args)
    # An existing agents.md is kept; the files still missing are created to match its settings.
    existing = target / "agents.md"
    if not existing.is_file() and any((target / name).exists() for name in COORDINATION_FILES[1:]):
        raise ValueError("agents.md is missing from an existing project; restore it from a backup before repair "
                         "so its settings are not replaced by defaults")
    saved = rs.read_settings(existing.read_text(encoding="utf-8"), target) if existing.is_file() else None
    stored = saved.values if saved else {}
    require_answers(target, preset, flags, stored, args.preset)
    settings = rs.resolve(flags, preset, stored, new_project=saved is None)
    if saved:
        if not saved.has_section:
            raise ValueError("agents.md has no Project settings; use --reconfigure --force before repairing files")
        current = rs.resolve({}, None, stored)
        conflicts = [setting.label for setting in rs.SETTINGS if settings[setting.key] != current[setting.key]]
        if args.name and saved.project and args.name != saved.project:
            conflicts.append("project name")
        if conflicts:
            raise ValueError("repair preserves agents.md settings; conflicting " + ", ".join(conflicts) +
                             ". Repair without overrides, then use --reconfigure (and --migrate for Workflow).")
        if current["workflow"] != rs.files_workflow(saved):
            raise ValueError("Workflow differs from the stored file layout; restore it before repair, "
                             "then use --reconfigure --migrate")
        settings = current
        name = saved.project or name
        agents, user = repair_identity(target, settings["workflow"], args)
    else:
        settings["guards"] = rs.stamp_guards(settings["guards"], stored.get("guards", "off"))
        settings["git"] = git_mode_for(target, settings["git"])
    ignore_tool_state(target, settings)

    if settings["workflow"] == "unified":
        sections = queue_section()
    else:
        sections = agent_sections(agents)
    values = {
        "{{PROJECT_NAME}}": name,
        "{{AGENT_NAMES}}": ", ".join(agents),
        "{{USERS}}": user or "none yet",
        "{{HANDOFF_AGENT_SECTIONS}}": handoff_agent_sections(agents),
        "{{VERIFICATION}}": settings["verification"],
        "{{MILESTONES}}": pending_milestones(settings),
    }
    conditions = rs.conditions(settings)
    created = 0
    agents_created = write_if_missing(target / "agents.md", compose_agents(settings, name)) == "create"
    created += agents_created
    if agents_created:
        save_template_metadata(target, settings)
    created += write_if_missing(target / "plan.md", render_plan(settings, name, sections, ordering=args.ordering)) == "create"
    for template, filename in (("DISCOVERIES.md.template", "discoveries.md"), ("HANDOFF.md.template", "handoff.md")):
        created += write_if_missing(target / filename, render(TEMPLATES / template, values, conditions)) == "create"

    print(f"Done. Created {created} file(s). Existing files were preserved.")
    print(f"Settings: {rs.describe(settings)}; user {user or 'none yet'}")
    if args.save_preset:
        save_preset(args, settings, name)
    return 0


def save_only(target: Path, args: argparse.Namespace) -> int:
    """--save-preset on an existing project without --reconfigure: store its settings, change no file."""
    text = (target / "agents.md").read_text(encoding="utf-8")
    stored = rs.read_settings(text, target)
    flags = flags_of(args)
    settings = rs.resolve(flags, load_preset_arg(args), stored.values)
    save_preset(args, settings, args.name or stored.project or target.name)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize, reconfigure, or migrate Research Orchestrator files.")
    parser.add_argument("target", nargs="?", default=".", help="Project directory")
    parser.add_argument("-n", "--name", help="Project name (defaults to directory name)")
    parser.add_argument("--agents", help="Agent count (e.g. 2 -> A,B) or comma-separated names from A-Z, AA-ZZ")
    parser.add_argument("--user", help="First user to record, e.g. kim or user1")
    parser.add_argument("--ordering", choices=("queue", "priority"),
                        help="Order a new plan by queue position or scored priority; existing plan headers are preserved")
    for setting in rs.SETTINGS:
        parser.add_argument(setting.flag, dest=setting.key, help=setting.help)
    parser.add_argument("--list-presets", action="store_true", help="List built-in and user presets, then exit")
    parser.add_argument("--save-preset", metavar="NAME", help="Save the effective settings as preset user:NAME")
    parser.add_argument("--answers", metavar="JSON", help="Setup answers as a JSON object or UTF-8 JSON file; flags override keys")
    parser.add_argument("--reconfigure", action="store_true",
                        help="Regenerate agents.md above '## Project rules' from its settings and any flags")
    parser.add_argument("--migrate", action="store_true", help="With --reconfigure, move plan items when Workflow changes")
    parser.add_argument("--force", action="store_true",
                        help="With --reconfigure, replace hand-edited generated rules; with --migrate, allow taken slots")
    return parser


def apply_answers(args: argparse.Namespace) -> None:
    """Treat a saved setup brief as flag defaults, never as executable options."""
    if not args.answers:
        return
    try:
        raw = args.answers if args.answers.lstrip().startswith("{") else Path(args.answers).read_text(encoding="utf-8")
        values = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ValueError("--answers needs a JSON object or a readable UTF-8 JSON file") from exc
    allowed = {setting.key for setting in rs.SETTINGS} | {"name", "user", "agents", "ordering"}
    if not isinstance(values, dict) or any(key not in allowed or not isinstance(value, str)
                                           for key, value in values.items()):
        raise ValueError("--answers keys must be setting names (underscores), name, user, agents or ordering; values must be strings")
    if "ordering" in values and values["ordering"] not in {"queue", "priority"}:
        raise ValueError("--answers ordering must be queue or priority")
    for key, value in values.items():
        if getattr(args, key) is None:
            setattr(args, key, value)


def main(argv: list[str] | None = None) -> int:
    # Settings contain '—'; never crash on a legacy console code page such as cp949.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    args = build_parser().parse_args(argv)
    try:
        apply_answers(args)
        if args.list_presets:
            return list_presets()
        target = Path(args.target).resolve()
        if not target.is_dir():
            print(f"Error: target directory does not exist: {target}", file=sys.stderr)
            return 1
        if args.migrate and not args.reconfigure:
            print("Error: --migrate works only together with --reconfigure", file=sys.stderr)
            return 1
        if args.ordering and ((target / "plan.md").exists() or args.reconfigure):
            raise ValueError("--ordering selects a new plan's order; edit the existing plan's Ordering header directly")
        recover_transaction(target)  # a migration a killed process left unfinished
        if args.reconfigure:
            return reconfigure(target, args)
        if args.save_preset and (target / "agents.md").is_file():
            return save_only(target, args)
        return initialize(target, args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
