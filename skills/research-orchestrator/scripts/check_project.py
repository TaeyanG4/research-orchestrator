#!/usr/bin/env python3
"""Check that a project's agents.md, plan.md, discoveries.md, and handoff.md agree with each other.

Run at session start, after a take-over or migration, and before closing:

    python <skill-root>/scripts/check_project.py [project-dir] [--strict] [--baseline-update]

Severity: ERROR = the files contradict each other or a required structure is missing; WARN = stale
or non-canonical; INFO = v2 compatibility and advice. Exit 0 = no ERROR (with --strict: no WARN
either); 1 = ERROR (or WARN with --strict); 2 = the project could not be read.

Every issue has a stable check id (e.g. plan.claim.stale) and a fingerprint: check id + record id +
field. --baseline-update stores the current fingerprints (all severities) in .ro/checker-baseline.json;
later runs report the issues that are new since then as one WARN. A baseline never hides or
downgrades a finding. Only structured lines are checked (headings and "- Field:" bullets outside
code fences), so format samples and prose are ignored.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import string
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # hard imports: a broken installation is a structural error, never skipped
    from ro_ids import D_PATTERN, H_PATTERN, I_PATTERN, X_PATTERN
    from ro_markdown import unfenced
    from ro_time import FUTURE_TOLERANCE
    from ro_records import HANDOFF_SECTIONS, PLAN_SECTIONS, SHARED_SECTION, _active_text
    import ro_settings as rs
    from ro_evidence import external_retry_checks
    import init_research_orchestrator as init
except ImportError as exc:  # pragma: no cover - exercised only by a broken install
    print(f"CONSISTENCY: cannot import the skill's local modules ({exc}); the installation is broken")
    sys.exit(2)


AGENT_NAMES = {*string.ascii_uppercase, *(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase)}
PLAN_FIELDS = [
    "Sources", "Hypothesis", "Evidence", "Improvement", "Impact", "Information", "Confidence",
    "Unblock", "Diversity", "Cost", "Priority", "Resource", "Parallel", "Other", "Next test",
]
PLAN_OPTIONAL = {"Stages", "Important stages", "Family", "Saturation exit", "Ready by"}
PLAN_SCORES = {"Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority"}
WORK_PLAN_OPTIONAL = PLAN_SCORES | {"Sources", "Improvement", "Resource", "Parallel", "Other"}
WORK_ROUTING_DEFAULTS = {"Resource": "CPU", "Parallel": "NO", "Other": "NONE"}
SCORE_FACTORS = ("Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost")
DISCOVERY_FIELDS = ["Source", "Host", "User", "Date", "Cross-check", "Finding", "Evidence", "Implication", "Reviews"]
DISCOVERY_OPTIONAL = {"Session", "Decision class", "Instrument", "Family", "Result", "Override",
                      "Override resolved", "Rejected on", "Consistency", "Kind", "Status", "Due", "Gap",
                      "Decomposition", "Core families", "Data audit", "Intake", "Rejected consistent gains",
                      "Decisions", "Outcome", "Control"}
EVENT_FIELDS = [
    "Host", "User", "Action", "Result", "Artifacts", "Discovery updates", "Review verdict",
    "Resource", "Other executor", "New plan items",
]
EVENT_OPTIONAL = {"Decision", "Effort", "Session", "Review artifact"}
SESSION_OPTIONAL = {"Artifacts", "Discovery updates", "Review verdict", "Resource", "Other executor", "New plan items"}
EXTERNAL_FIELDS = ["Kind", "Candidate", "Destination", "Expected", "Result", "Final", "Status"]
EXTERNAL_OPTIONAL = {"Family", "Retry of", "Reconciled"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STAMP = "%Y-%m-%d %H:%M"
IDLE_CLAIM = dt.timedelta(days=7)
CROSS_CHECK_STATES = {"PENDING", "REVIEWING", "VERIFIED", "HOLD", "CHALLENGED"}
VERDICTS = {"CLOSED", "HOLD", "CHALLENGED"}
RESOLUTIONS = {"CLOSED": "CLOSED", "VERIFIED": "CLOSED", "HOLD": "HOLD"}  # '<X> after challenge'
VERDICT_FOR_STATE = {"VERIFIED": "CLOSED", "HOLD": "HOLD", "CHALLENGED": "CHALLENGED"}
STATE_FOR_VERDICT = {verdict: state for state, verdict in VERDICT_FOR_STATE.items()}
FREE_HOSTS = {"unassigned", "released"}
SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}
BASELINE = Path(".ro") / "checker-baseline.json"

H_ID = re.compile(rf"\b{H_PATTERN}\b")
D_ID = re.compile(rf"\b{D_PATTERN}\b")
EVENT_KEY = re.compile(rf"^({H_PATTERN})(?:/s(\d+))?$")
FIELD = re.compile(r"^- ([A-Za-z][A-Za-z/ -]*?(?: ?\([^)]*\))?):\s?(.*)$")
QUALIFIER = re.compile(r" \([^)]*\)$")
REVIEW = re.compile(r"^\s+- (.+?) \((\S+)\): (\S+)( after challenge)? — (.*)$")
REVIEWER = re.compile(r"^(?:same host — )?reviewer (\S+)(?: — |$)")
ISO_MOMENT = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?"
REVIEWER_TOKEN = re.compile(rf"^(?:subagent|[a-z-]+):[^@\s]+@({ISO_MOMENT})$")
CLAIM = re.compile(rf"^((?:CPU|GPU|Other)(?:@[\w.-]+)?) — ([A-Z]{{1,2}}) \(({H_PATTERN}), since (\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}})\)$")
ITEM_CLAIM = re.compile(r"^([A-Z]{1,2}) since (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$")
LOOSE_CLAIM = re.compile(r"^([A-Z]{1,2})\b.*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
STAGE = re.compile(r"^s(\d+)\b")
COLLECTION = re.compile(r"^running — ([A-Z]{1,2}) \(since (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\)$")
USER_NAME = re.compile(r"^[^\W_][\w-]{0,31}$")
TAKE_OVER = re.compile(
    rf"^took over ({H_PATTERN}) from ([A-Z]{{1,2}}) \((same host|cross-host:.*?)\) as ({H_PATTERN})"
)
SHARED_VALUE = re.compile(r"(?i)\b(champion|current best|best model|baseline)\b\s*[:=]")
I_ID = re.compile(rf"\b{I_PATTERN}\b")
X_ID = re.compile(rf"\b{X_PATTERN}\b")
ARTIFACT = re.compile(r".+,\s*hash\s+(\S+)")
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
MEASUREMENT = re.compile(rf"(?:^|[;\n|,])\s*([\w][\w .%/-]*?)\s*=\s*({NUMBER})\s+on\s+"
                         rf"({I_PATTERN})\s+cohort\s+([\w.-]+)")
DECISION_ALIASES = {"outcome-definition-change": "target-change", "method-change": "model-change",
                    "data-change": "input-change", "combined": "combination"}
DECISION_CLASSES = {"target-change", "model-change", "input-change", "combination", "operational", "other",
                    *DECISION_ALIASES}
STRICT_ERRORS = {"guard.instrument.missing", "guard.instrument.circular", "guard.instrument.schema",
                 "guard.family.saturated", "guard.override.recheck", "guard.rejection.evidence",
                 "guard.outcome.missing", "guard.outcome.invalid",
                 "guard.insight.overdue", "guard.direction.stale", "guard.direction.incomplete",
                 "guard.selection.rationale", "ext.expected", "ext.duplicate",
                 "external.field.missing", "external.field.invalid"}
# Exact process/ranking checks only: structural, evidence and operational safety rules
# cannot be waived by a standing-policy entry, even when it names a real check ID.
OVERRIDE_CHECKS = {"guard.direction.stale", "guard.direction.incomplete", "guard.phase.milestone",
                   "guard.effort.share", *(f"plan.field.missing:{name}" for name in PLAN_SCORES)}


@dataclass(frozen=True)
class Issue:
    severity: str          # ERROR | WARN | INFO
    check: str             # stable check id
    where: str
    message: str
    record: str = ""       # record id: plan item, discovery, slot, setting, or file
    field: str = ""
    owner: str = ""

    @property
    def fingerprint(self) -> str:
        return f"{self.check}|{self.record}|{self.field}"

    def render(self) -> str:
        tag = f"[{self.owner}] " if self.owner else ""
        return f"{self.severity} {self.check} {tag}{self.where}: {self.message}"


@dataclass
class Block:
    key: str
    line: int
    title: str = ""
    heading_date: str = ""
    owner: str = ""
    section: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    claim: tuple[str, str] | None = None     # (slot, since) of a unified item's Claimed line


@dataclass
class Review:
    host: str
    slot: str
    verdict: str
    resolves: bool
    rest: str
    reviewer: str | None


def collect_fields(lines: list[str], start: int, block: Block) -> int:
    """Read consecutive '- Field:' lines (and indented sub-bullets) after a heading."""
    i = start
    while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  - ")):
        line = lines[i]
        match = FIELD.match(line)
        if match and not line.startswith("  "):
            block.fields.setdefault(match.group(1), match.group(2).strip())
            block.order.append(match.group(1))
        else:
            block.extra.append(line)
        i += 1
    return i


def base_name(name: str) -> str:
    """'Status (2026-10-20 16:13)' -> 'Status'."""
    return QUALIFIER.sub("", name)


def parse_stamp(stamp: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(stamp, STAMP)
    except ValueError:
        return None


def parse_stages(value: str) -> tuple[list[int], bool]:
    """Stage numbers declared in 'Stages: s1 <name> | s2 <name>' and whether the line is canonical."""
    numbers, canonical = [], True
    for part in (p.strip() for p in value.split("|")):
        match = STAGE.match(part)
        if not match:
            canonical = False
            continue
        numbers.append(int(match.group(1)))
    if not numbers or len(set(numbers)) != len(numbers):
        canonical = False
    return numbers, canonical


class Checker:
    def __init__(self, root: Path, now: dt.datetime | None = None, *,
                 proposed_files: dict[str, str] | None = None,
                 proposed_settings: dict[str, str] | None = None):
        self.root = root
        self.proposed_files = proposed_files or {}
        self.proposed_settings = proposed_settings
        self.now = now or dt.datetime.now()
        self.issues: list[Issue] = []
        self.values: dict[str, str] = {}
        self.guard_checks: set[str] = set()
        self.overrides: list[tuple[set[str], str, str]] = []

    # ---------- issues ----------

    def add(self, severity: str, check: str, where: str, message: str,
            record: str = "", field_name: str = "", owner: str = "") -> None:
        record = record or where.split(":", 1)[0]
        for checks, scope, reason in self.overrides:
            if (check in checks or f"{check}:{field_name}" in checks) and (not scope or scope == record):
                severity = "INFO"
                message += f" (active override: {reason})"
                break
        self.issues.append(Issue(severity, check, where, message, record, field_name, owner))

    def error(self, check: str, where: str, message: str, record: str = "", field_name: str = "", owner: str = "") -> None:
        self.add("ERROR", check, where, message, record, field_name, owner)

    def warn(self, check: str, where: str, message: str, record: str = "", field_name: str = "", owner: str = "") -> None:
        self.add("WARN", check, where, message, record, field_name, owner)

    def info(self, check: str, where: str, message: str, record: str = "", field_name: str = "", owner: str = "") -> None:
        self.add("INFO", check, where, message, record, field_name, owner)

    @property
    def unified(self) -> bool:
        """Plan structure follows the workflow the files are in (see settings.workflow.unmigrated)."""
        return getattr(self, "files_workflow", self.values.get("workflow")) == "unified"

    @property
    def work(self) -> bool:
        return self.values.get("profile") == "work"

    @property
    def compact_plan(self) -> bool:
        return self.work or self.values.get("preset") == "quick"

    def check_time(self, stamp: str, where: str, record: str, field_name: str, owner: str = "") -> None:
        moment = parse_stamp(stamp)
        if moment and moment > self.now + FUTURE_TOLERANCE:
            self.warn("time.future", where, f"{field_name} {stamp} is ahead of the clock "
                                            f"({self.now.strftime(STAMP)}); write the real time", record, field_name, owner)

    def check_fields(self, where: str, block: Block, required: list[str], optional: set[str], kind: str,
                     record: str = "", guard: str = "", skip_missing: set[str] | None = None) -> None:
        """Required fields present and in their relative order; unknown fields are INFO, never an error."""
        record = record or block.key
        label = block.key or "the event"
        for name in required:
            if name not in block.fields and name not in (skip_missing or set()):
                hint = ""
                if kind == "discovery" and name == "Date":
                    day = self.first_mention.get(block.key)
                    hint = (f"; the handoff log first mentions it on {day}" if day
                            else "; use 'unknown' if it cannot be recovered")
                elif kind == "discovery" and name == "User":
                    hint = " (use 'unknown' if it cannot be recovered)"
                if guard:
                    self.guard_issue(guard, f"{kind}.field.missing", block,
                                     f"{label} has no '{name}' line{hint}", name)
                else:
                    self.error(f"{kind}.field.missing", where, f"{label} has no '{name}' line{hint}", record, name,
                               block.owner)
        sequence = [name for name in block.order if name in required]
        expected = [name for name in required if name in block.fields]
        if sequence != expected:
            message = f"{label} fields are out of order or repeated; expected {', '.join(expected)}"
            severity = "WARN" if len(sequence) != len(set(sequence)) else "INFO"
            if guard:
                self.guard_issue(guard, f"{kind}.field.order", block, message, light=severity)
            else:
                self.add(severity, f"{kind}.field.order", where, message, record, "", block.owner)
        unknown = dict.fromkeys(base_name(name) for name in block.order
                                if name not in required and base_name(name) not in optional)
        for name in unknown:
            message = f"{label} has a '{name}:' line that is not part of the format (kept as is)"
            if guard:
                self.guard_issue(guard, f"{kind}.field.unknown", block, message, name, "INFO")
            else:
                self.info(f"{kind}.field.unknown", where, message, record, name, block.owner)

    # ---------- parsing ----------

    def parse_plan(self, lines: list[str]) -> None:
        live_lines = _active_text("\n".join(lines) + "\n", PLAN_SECTIONS).splitlines()
        self.plan_sections: list[str] = []
        self.queue_lines: list[int] = []
        self.plan_items: dict[str, Block] = {}
        self.retired: set[str] = set()
        self.plan_header: dict[str, str] = {}
        # Non-item text is reported once per section (record 'section:<heading>'), never per line, so
        # editing lines above it does not change its fingerprint.
        sections: list[dict[str, object]] = [{"heading": "(header)", "kind": "header", "line": 1, "outside": []}]
        section, owner = "", ""
        i = 0
        while i < len(lines):
            line = lines[i]
            n = i + 1
            if line.startswith("## "):
                sections.append({"heading": line[3:].strip(), "kind": "", "line": n, "outside": []})
            current = sections[-1]
            header_field = re.fullmatch(r"(?:- )?(Ordering|Next):\s*(.*)", line)
            if current["kind"] == "header" and header_field:
                name, value = header_field.groups()
                if name in self.plan_header:
                    self.error("plan.header.duplicate", f"plan.md:{n}", f"duplicate {name} header", "plan.md", name)
                self.plan_header[name] = value.strip()
                i += 1
                continue
            if line.startswith("## Agent: "):
                owner, section = line[len("## Agent: "):].strip(), "agent"
                current["kind"] = "agent"
                if owner in self.plan_sections:
                    self.error("plan.section.duplicate", f"plan.md:{n}", f"duplicate section for agent {owner}",
                               f"section:{owner}", "", owner)
                self.plan_sections.append(owner)
                if self.unified:
                    self.error("plan.section.workflow", f"plan.md:{n}", f"'## Agent: {owner}' section, but Workflow is "
                               "unified: items belong in '## Queue' (switch workflows with --reconfigure --migrate)",
                               f"section:{owner}", "", owner)
            elif line.rstrip() == "## Queue":
                owner, section = "", "queue"
                current["kind"] = "queue"
                self.queue_lines.append(n)
                if not self.unified:
                    self.error("plan.section.workflow", f"plan.md:{n}", "'## Queue' section, but Workflow is classic: "
                               "items belong in '## Agent: <name>' sections", "section:Queue")
            elif line.startswith("### H-"):
                item_id, _, title = line[4:].partition(" — ")
                block = Block(key=item_id.strip(), line=n, title=title, owner=owner if section == "agent" else "",
                              section=section)
                if not live_lines[i].startswith("### H-") and str(current["heading"]).lower().startswith("archived"):
                    i = collect_fields(lines, i + 1, block)
                    continue  # Historical copies neither own runnable work nor duplicate live IDs.
                i = collect_fields(lines, i + 1, block)
                self.add_plan_item(block)
                self.retired.update(re.findall(rf"\(from ({H_PATTERN})\)", title))
                continue
            elif line.startswith("## "):
                owner, section = "", "other"
                current["kind"] = "archive" if str(current["heading"]).lower().startswith("archived") else "other"
            elif line.startswith("# "):
                pass
            elif line.startswith("#") or line.startswith("- ") or line.startswith("  - ") or (
                    section in ("agent", "queue", "other") and line.strip() and not line.strip().startswith("_")):
                current["outside"].append((n, line.strip()))
            if (shared := SHARED_VALUE.search(line)):
                self.warn("plan.shared-value", f"plan.md:{n}", f"project-wide value '{line.strip()[:60]}' belongs in "
                          "handoff.md Shared state, not plan.md", f"section:{current['heading']}",
                          shared.group(1).lower(), owner)
            i += 1
        for part in sections:
            if part["kind"] == "archive":
                continue  # Preserved evidence is not an actionable queue diagnostic.
            outside: list[tuple[int, str]] = part["outside"]  # type: ignore[assignment]
            record = f"section:{part['heading']}"
            if part["kind"] == "other":
                self.warn("plan.text.heading", f"plan.md:{part['line']}", f"section '## {part['heading']}' is not a "
                          f"plan section ({len(outside)} line(s) of text); plan.md holds plan items only", record)
            elif outside:
                first, text = outside[0]
                self.warn("plan.text.outside", f"plan.md:{first}", f"{len(outside)} line(s) in section "
                          f"'{part['heading']}' are outside any plan item, first: '{text[:60]}'", record)

    def add_plan_item(self, block: Block) -> None:
        where = f"plan.md:{block.line}"
        if block.key in self.plan_items:
            self.error("plan.id.duplicate", where, f"duplicate plan item ID {block.key}", block.key, "", block.owner)
        self.plan_items[block.key] = block

    def parse_discoveries(self, lines: list[str]) -> None:
        self.discoveries: dict[str, Block] = {}
        self.discovery_order: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("## D-"):
                disc_id, _, title = line[3:].partition(" — ")
                block = Block(key=disc_id.strip(), line=i + 1, title=title)
                i = collect_fields(lines, i + 1, block)
                block.owner = block.fields.get("Source", "")
                if block.key in self.discoveries:
                    self.error("discovery.id.duplicate", f"discoveries.md:{block.line}",
                               f"duplicate discovery ID {block.key}", block.key, "", block.owner)
                self.discoveries[block.key] = block
                self.discovery_order.append(block.key)
                continue
            i += 1

    def parse_handoff(self, lines: list[str]) -> None:
        text = "\n".join(lines) + "\n"
        active_lines = _active_text(text, HANDOFF_SECTIONS).splitlines()
        shared_lines = _active_text(text, SHARED_SECTION).splitlines()
        self.shared: dict[str, str] = {}
        self.handoff_sections: dict[str, Block] = {}
        self.events: list[Block] = []
        self.instruments: dict[str, Block] = {}
        self.external_actions: dict[str, Block] = {}
        self.guard_records: list[Block] = []
        area = ""
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("## "):
                area = line[3:].strip().lower()
            elif shared_lines[i].startswith("- "):
                match = FIELD.match(line)
                if match:
                    self.shared[match.group(1)] = match.group(2).strip()
            elif line.startswith("### ") and area in ("instruments", "external actions"):
                key, _, title = line[4:].partition(" — ")
                block = Block(key=key.strip(), line=i + 1, title=title, section=area)
                i = collect_fields(lines, i + 1, block)
                records = self.instruments if area == "instruments" else self.external_actions
                self.guard_records.append(block)
                records[block.key] = block
                continue
            elif active_lines[i].startswith("### Agent: "):
                block = Block(key=line[len("### Agent: "):].strip(), line=i + 1)
                i = collect_fields(lines, i + 1, block)
                if block.key in self.handoff_sections:
                    self.error("handoff.section.duplicate", f"handoff.md:{block.line}",
                               f"duplicate handoff section for agent {block.key}", f"slot:{block.key}", "", block.key)
                self.handoff_sections[block.key] = block
                continue
            elif re.match(r"^### \d{4}-\d{2}-\d{2} \d{2}:\d{2} — ", line):
                parts = line[4:].split(" — ")
                block = Block(key=parts[2].strip() if len(parts) > 2 else "", line=i + 1,
                              owner=parts[1].strip() if len(parts) > 1 else "",
                              heading_date=parts[0].strip())
                i = collect_fields(lines, i + 1, block)
                self.events.append(block)
                continue
            i += 1

    def slot_free(self, name: str) -> bool:
        section = self.handoff_sections.get(name)
        return section is not None and section.fields.get("Current host", "").lower() in FREE_HOSTS

    # ---------- settings (agents.md) ----------

    def check_settings(self, text: str) -> None:
        self.legacy_review_project = rs.read_settings(text, self.root).version == "v2"
        _generated, region = rs.split_agents(text)
        markers = [line.strip() for line in unfenced(region) if "ro-legacy-reviews:" in line]
        self.legacy_reviews: set[str] = set()
        if markers:
            match = re.fullmatch(r"<!-- ro-legacy-reviews: v2 ([0-9a-f]{64}(?:,[0-9a-f]{64})*) -->",
                                 markers[0]) if len(markers) == 1 else None
            if match:
                self.legacy_reviews = set(match[1].split(","))
            else:
                self.error("discovery.legacy.invalid", "agents.md", "invalid legacy review preservation record; "
                           "restore it from the pre-upgrade copy instead of broadening review eligibility", "settings")
        self.agents_text = text
        stored = rs.read_settings(text, None if self.proposed_settings is not None else self.root)
        if self.proposed_settings is not None:
            stored.rendered = dict(re.findall(r"(\w+)=(\S+)", rs.render_key(self.proposed_settings)))
        self.stored = stored
        values: dict[str, str] = {}
        settings_errors = 0
        p3_keys = {"environment", "block", "external_actions", "publish_scan", "brief_requirements"}
        if not {"platform_mode", "platforms", "git"} <= set(stored.values):
            self.error("settings.missing", "agents.md", "missing '## Project settings' (Platform mode, Platforms, "
                       "Git sync); regenerate it with init_research_orchestrator.py --reconfigure --force", "settings")
            self.values = rs.resolve({}, None, {"platforms": rs.DEFAULT_PLATFORMS})
            self.platforms = []
            self.files_workflow = self.values["workflow"]
            return
        if stored.version == "v2":
            self.info("agents.settings.v2", "agents.md", "v2 settings; run init_research_orchestrator.py . --reconfigure "
                      "to add the v3 lines (no --force needed while the generated rules are untouched)", "settings")
        for label, value in stored.unknown.items():
            self.info("settings.unknown", "agents.md", f"Project settings has an unknown line '{label}: {value}'",
                      "settings", label)
        for setting in rs.SETTINGS:
            raw = stored.values.get(setting.key)
            if raw is None:
                if setting.key in ("queue_freeze", "receipt_policy", "stale_slot_after"):
                    values[setting.key] = rs.default_value(setting.key, values)
                    continue
                if setting.v3 and stored.version == "v2":
                    values[setting.key] = (rs.default_value(setting.key, values)
                                           if setting.key in p3_keys else setting.default)
                    continue
                settings_errors += 1
                self.error("settings.missing", "agents.md", f"Project settings has no '{setting.label}' line"
                           + (" (use 'off')" if setting.key in ("collector", "reviewer") else ""), "settings", setting.label)
                values[setting.key] = self.safe_default(setting.key, values)
                continue
            try:
                canonical = rs.normalize(setting.key, raw, values)
            except ValueError as exc:
                settings_errors += 1
                self.error("settings.value", "agents.md", str(exc), "settings", setting.label)
                values[setting.key] = self.safe_default(setting.key, values)
                continue
            if canonical != raw:
                self.warn("settings.canonical", "agents.md", f"{setting.label} '{raw}' should be written "
                          f"'{canonical}'", "settings", setting.label)
            values[setting.key] = canonical
        self.values = values
        self.platforms = [p.strip() for p in values["platforms"].split(",") if p.strip()]
        # The plan is in the workflow the generated part was made for until --reconfigure --migrate moves it.
        files_workflow = rs.files_workflow(stored)
        self.files_workflow = files_workflow if files_workflow in rs.SETTING["workflow"].choices else values["workflow"]
        if self.files_workflow != values["workflow"]:
            self.error("settings.workflow.unmigrated", "agents.md", f"Workflow says {values['workflow']}, but the files "
                       f"are still in the {self.files_workflow} workflow; run init_research_orchestrator.py . "
                       "--reconfigure --migrate to move the plan items", "settings", "Workflow")
        if values["profile"] == "competition" and values["competition"] == "off":
            self.warn("settings.competition", "agents.md", "Profile is competition but Competition is off; set "
                      "'Competition: <platform>/<slug>'", "settings", "Competition")
        if "external.gate" in values["block"].split(", ") and values["external_actions"] == "none":
            self.warn("settings.external.inactive", "agents.md", "external.gate has no command patterns; "
                      "configure External actions before relying on the gate", "settings", "External actions")
        if settings_errors:
            return
        state = init.rules_state(text, stored, values)
        if state == "edited":
            self.warn("agents.rules.edited", "agents.md", "the generated part of agents.md (above '## Project rules') "
                      "differs from what its template generates; move project-specific rules under '## Project rules' "
                      "(kept verbatim by --reconfigure)", "rules")
        elif state == "stale":
            self.warn("agents.rules.stale", "agents.md", "the generated rules in agents.md do not match its settings "
                      f"({', '.join(rs.SETTING[key].label for key in rs.RULE_KEYS)}); if you edited those settings, "
                      "run init_research_orchestrator.py . --reconfigure", "rules")
        if stored.version != "v2":
            generated = rs.split_agents(text)[0]
            summary = re.search(r"^Summary: .*$", generated, re.M)
            if summary is None or summary.group(0) != rs.summary_line(values):
                self.warn("agents.summary.stale", "agents.md", "the preset summary line does not "
                          "match the settings; --reconfigure refreshes it", "summary")

    def check_project_rules(self, text: str) -> None:
        """Validate dated exceptions and allow only their explicit process/ranking scope."""
        _generated, region = rs.split_agents(text)
        region = re.sub(r"<!--.*?-->", "", region, flags=re.S)
        sections: dict[str, list[str]] = {}
        section, fenced = "", False
        for line in region.splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                sections.setdefault(section, []).append(line)
            elif not fenced and line.startswith("### "):
                section = line[4:].strip()
            elif not fenced and line.startswith("## "):
                section = ""
            else:
                sections.setdefault(section, []).append(line)
        standing = "\n".join(sections.get("Standing rules", [])).strip()
        size = len(standing.encode("utf-8"))
        if size > rs.STANDING_RULES_BUDGET:
            self.warn("rules.standing.budget", "agents.md", f"Standing rules uses {size} UTF-8 bytes "
                      f"(budget {rs.STANDING_RULES_BUDGET}); move detail to a linked project document",
                      "project-rules", "Standing rules")
        overrides = "\n".join(unfenced("\n".join(sections.get("Active overrides", []))))
        for entry in re.finditer(r"^- (.+?)(?=^- |\Z)", overrides, re.M | re.S):
            content = entry.group(1).strip()
            title = content.splitlines()[0].split("|", 1)[0].strip()
            parts = dict(re.findall(r"(?:^|\||\n)\s*(Checks|Record|Reason|Expires):\s*([^|\n]*)", content))
            reason = parts.get("Reason", "").strip()
            checks = {check.strip() for check in parts.get("Checks", "").split(",") if check.strip()}
            expiry = parts.get("Expires", "").strip()
            try:
                day = dt.date.fromisoformat(expiry) if DATE.fullmatch(expiry) else None
            except ValueError:
                day = None
            if day is None:
                self.warn("rules.override.expires", "agents.md", "active override needs Expires: YYYY-MM-DD",
                          title, "Expires")
            elif day < self.now.date():
                self.warn("rules.override.expired", "agents.md", f"active override expired on {day.isoformat()}; "
                          "remove it or record a new expiry", title, "Expires")
            if not reason:
                self.warn("rules.override.reason", "agents.md", "active override needs a Reason", title, "Reason")
            forbidden = checks - OVERRIDE_CHECKS
            if forbidden:
                self.error("rules.override.scope", "agents.md", "override cannot waive these checks: "
                           + ", ".join(sorted(forbidden)) + "; only listed process/ranking checks may be waived",
                           title, "Checks")
            if checks and not forbidden and reason and day is not None and day >= self.now.date():
                self.overrides.append((checks, parts.get("Record", "").strip(), reason))

    @staticmethod
    def safe_default(key: str, values: dict[str, str]) -> str:
        if key == "platform_mode":
            return "adaptive"
        if key == "platforms":
            return ""
        if key == "fallback":
            return rs.DEFAULT_FALLBACK.get(values.get("platform_mode", "adaptive"), "same-host")
        return rs.SETTING[key].default

    # ---------- plan checks ----------

    def check_plan_items(self) -> None:
        ordering = self.plan_header.get("Ordering")
        if ordering is not None and ordering not in {"queue", "priority"}:
            self.error("plan.ordering.invalid", "plan.md", "Ordering must be queue or priority", "plan.md", "Ordering")
        next_item = self.plan_header.get("Next")
        if next_item is not None and next_item not in self.plan_items:
            self.error("plan.next.invalid", "plan.md", "Next must name an existing unfinished plan item", "plan.md", "Next")
        freeze = self.values.get("queue_freeze", "off")
        if freeze != "off" and self.now.date() > dt.date.fromisoformat(freeze.removeprefix("until ")):
            self.warn("plan.freeze.expired", "agents.md", "Queue freeze expired; review the queue and set it to off "
                      "or choose a new date", "settings", "Queue freeze")
        if self.unified:
            if not self.queue_lines:
                self.error("plan.queue.missing", "plan.md", "Workflow is unified but plan.md has no '## Queue' section",
                           "plan.md")
            elif len(self.queue_lines) > 1:
                self.error("plan.queue.duplicate", f"plan.md:{self.queue_lines[1]}", "plan.md has more than one "
                           "'## Queue' section; keep exactly one", "plan.md")
        for item in self.plan_items.values():
            where = f"plan.md:{item.line}"
            if self.unified:
                if self.queue_lines and item.section != "queue":
                    self.error("plan.item.section", where, f"{item.key} is outside the '## Queue' section", item.key)
            elif not item.owner:
                self.error("plan.item.section", where, f"{item.key} is not inside any '## Agent:' section", item.key)
            elif not item.key.startswith(f"H-{item.owner}-"):
                self.error("plan.item.prefix", where, f"{item.key} sits in agent {item.owner}'s section but carries "
                           "another owner's prefix", item.key, "", item.owner)
            if self.unified:
                self.check_claim_line(item, where)  # a missing Claimed line is reported there, as plan.claim.missing
            claimed = self.unified and "Claimed" in item.fields
            fields = ["Goal" if name == "Hypothesis" and self.compact_plan and "Goal" in item.fields
                      and "Hypothesis" not in item.fields else name for name in PLAN_FIELDS]
            optional = PLAN_OPTIONAL | ({"Goal"} if self.compact_plan else set())
            if self.values.get("profile") == "work":
                fields = ["Next step" if name == "Next test" and "Next step" in item.fields
                          and "Next test" not in item.fields else name for name in fields]
                optional = optional | {"Next step"}
            defaults = set(WORK_ROUTING_DEFAULTS)
            if self.compact_plan:
                defaults |= WORK_PLAN_OPTIONAL
            elif ordering == "queue":
                defaults |= PLAN_SCORES
            self.check_fields(where, item, ["Claimed", *fields] if claimed else fields, optional, "plan",
                              skip_missing=defaults)
            for name, value in WORK_ROUTING_DEFAULTS.items():
                item.fields.setdefault(name, value)
            self.check_plan_scores(item, where)
            from ro_stages import important_stages
            try:
                important_stages(item.fields)
            except ValueError as error:
                self.error("plan.stages.important", where, str(error), item.key, "Important stages", item.owner)
            ready = item.fields.get("Ready by")
            if ready is not None and self.iso_day(ready) is None:
                self.warn("plan.ready-by.invalid", where, "Ready by must be YYYY-MM-DD", item.key, "Ready by")
            if "Stages" in item.fields and not parse_stages(item.fields["Stages"])[1]:
                self.warn("plan.stages.format", where, f"{item.key} Stages must read 's1 <name> | s2 <name> | …' with "
                          "distinct stage numbers", item.key, "Stages", item.owner)

    def check_plan_scores(self, item: Block, where: str) -> None:
        scores: dict[str, int] = {}
        for name in (*SCORE_FACTORS, "Priority"):
            if name not in item.fields:
                continue
            value = item.fields[name]
            maximum = 24 if name == "Priority" else 3
            if not re.fullmatch(r"\d+", value) or not 0 <= int(value) <= maximum:
                self.error("plan.score.range", where, f"{name} must be an integer from 0 to {maximum}",
                           item.key, name, item.owner)
            else:
                scores[name] = int(value)
        if "Priority" in item.fields and not all(name in scores for name in SCORE_FACTORS):
            self.error("plan.priority.inputs", where, "Priority requires six valid score factors", item.key,
                       "Priority", item.owner)
        elif "Priority" in scores:
            expected = (2 * scores["Impact"] + 2 * scores["Information"] + scores["Confidence"] +
                        scores["Unblock"] + scores["Diversity"] + 3 - scores["Cost"])
            if scores["Priority"] != expected:
                self.error("plan.priority.mismatch", where, f"Priority must be {expected} from the supplied factors",
                           item.key, "Priority", item.owner)

    def check_claim_line(self, item: Block, where: str) -> None:
        value = item.fields.get("Claimed")
        if value is None:
            self.error("plan.claim.missing", where, f"{item.key} has no 'Claimed:' line; in the unified workflow it is "
                       "the first field ('Claimed: none' when free)", item.key, "Claimed")
            return
        if item.order and item.order[0] != "Claimed":
            self.info("plan.claim.order", where, f"{item.key} must start with its 'Claimed:' line", item.key, "Claimed")
        if value.lower() == "none":
            return
        match = ITEM_CLAIM.match(value)
        if not match:
            self.warn("plan.claim.format", where, f"{item.key} Claimed '{value}' must read 'none' or "
                      "'<slot> since YYYY-MM-DD HH:MM'", item.key, "Claimed")
            match = LOOSE_CLAIM.match(value)
        if match:
            item.claim = (match.group(1), match.group(2))

    def check_claims(self) -> None:
        """Cross-file checks of unified claims: the slot exists, is not released, and the claim is not idle."""
        for item in self.plan_items.values():
            if item.claim is None:
                continue
            slot, since = item.claim
            where = f"plan.md:{item.line}"
            self.check_time(since, where, item.key, "Claimed", slot)
            section = self.handoff_sections.get(slot)
            if section is None:
                self.error("plan.claim.slot", where, f"{item.key} is claimed by {slot}, which has no handoff section",
                           item.key, "Claimed", slot)
            elif self.slot_free(slot):
                self.warn("plan.claim.stale", where, f"{item.key} is claimed by {slot}, but that slot is "
                          f"{section.fields.get('Current host')}; set 'Claimed: none' (closing a session releases its "
                          "claims unless its job still runs)", item.key, "Claimed", slot)
            else:
                start = parse_stamp(since)
                if start and self.now - start > IDLE_CLAIM and not self.has_event_since(slot, item.key, start):
                    self.info("plan.claim.idle", where, f"{item.key} has been claimed by {slot} since {since} with no "
                              "event naming it since; release it or record progress", item.key, "Claimed", slot)

    def has_event_since(self, slot: str, item_id: str, start: dt.datetime) -> bool:
        for event in self.events:
            match = EVENT_KEY.match(event.key)
            moment = parse_stamp(event.heading_date)
            names_item = (match and match.group(1) == item_id) or item_id in self.completed_items(event)
            if event.key == "session":
                names_item = names_item or item_id in H_ID.findall(event.fields.get("Action", ""))
            if event.owner == slot and names_item and moment and moment > start:
                return True
        return False

    # ---------- cross-file checks ----------

    def check_agents(self) -> None:
        listed_raw = self.shared.get("Active agent(s)")
        if listed_raw is None:
            self.error("handoff.shared.missing", "handoff.md", "Shared state has no 'Active agent(s)' line",
                       "handoff.md", "Active agent(s)")
            listed: list[str] = []
        else:
            listed = [a.strip() for a in listed_raw.split(",") if a.strip()]
        for name in sorted(set(listed) | set(self.plan_sections) | set(self.handoff_sections)):
            if name not in AGENT_NAMES:
                self.error("agent.name.invalid", "handoff.md/plan.md", f"'{name}' is not a valid agent name (use A-Z, "
                           "AA-ZZ)", f"slot:{name}", "", name)
                continue
            needs = [("Active agent(s)", name in listed),
                     ("a '### Agent:' section in handoff.md", name in self.handoff_sections)]
            if not self.unified:
                needs.insert(1, ("a '## Agent:' section in plan.md", name in self.plan_sections))
            missing = [label for label, present in needs if not present]
            if missing:
                self.error("agent.section.missing", "plan.md/handoff.md", f"agent {name} is missing {', '.join(missing)}",
                           f"slot:{name}", "", name)

    def check_handoff_sections(self) -> None:
        for name, block in self.handoff_sections.items():
            where = f"handoff.md:{block.line}"
            for required in ("Current host", "Current thread", "Next action"):
                if required not in block.fields:
                    self.error("handoff.slot.field-missing", where, f"agent {name}'s section has no '{required}' line",
                               f"slot:{name}", required, name)
            thread_ids = H_ID.findall(block.fields.get("Current thread", "").split(" ", 1)[0])
            next_ids = H_ID.findall(block.fields.get("Next action", ""))
            for item_id in dict.fromkeys(thread_ids + next_ids):
                item = self.plan_items.get(item_id)
                if item is None:
                    self.error("handoff.slot.dangling", where, f"agent {name}'s handoff names {item_id}, but it is not in "
                               "plan.md", f"slot:{name}", item_id, name)
                elif not self.unified and item.owner != name:
                    self.error("handoff.slot.owner", where, f"agent {name}'s handoff names {item_id}, which sits in "
                               f"{item.owner}'s plan section", f"slot:{name}", item_id, name)

    def completed_items(self, event: Block) -> set[str]:
        """Session completions survive preset changes; stages and take-overs complete no item."""
        if event.fields.get("Action", "").startswith("took over"):
            return set()
        if event.key == "session":
            return set(H_ID.findall(event.fields.get("Completed", "")))
        match = EVENT_KEY.fullmatch(event.key)
        return {match.group(1)} if match and match.group(2) is None else set()

    def check_events(self) -> None:
        # Index the complete history once; the old suffix scan repeated the same work for every event.
        completions = [self.completed_items(event) for event in self.events]
        self.finished_items = set().union(*completions)
        finished = set(self.finished_items)
        taken_over = set(self.retired)
        for event in self.events:
            action = event.fields.get("Action", "")
            taken_over.update(re.findall(rf"took over ({H_PATTERN})", action))
            finished.update(re.findall(rf"removed ({H_PATTERN})", action))

        for event, done in zip(self.events, completions):
            where = f"handoff.md:{event.line}"
            record = f"event:{event.heading_date} {event.owner} {event.key}"
            proxy = Block(key="", line=event.line, owner=event.owner, fields=event.fields, order=event.order)
            session = event.key == "session"
            # Session records retain their light shape after a preset change, just as their
            # completion IDs do; new research/competition item events still use every field.
            self.check_fields(where, proxy, [*EVENT_FIELDS, "Completed"] if session else EVENT_FIELDS,
                              EVENT_OPTIONAL, "event", record, skip_missing=SESSION_OPTIONAL if session else None)
            if session and not re.fullmatch(rf"none|{H_PATTERN}(?:\s*,\s*{H_PATTERN})*",
                                            event.fields.get("Completed", "")):
                self.error("event.completed.format", where, "Completed must list plan IDs separated by commas, "
                           "or 'none'", record, "Completed", event.owner)
            self.check_time(event.heading_date, where, record, "event time", event.owner)
            action = event.fields.get("Action", "")
            if action.startswith("took over"):
                self.check_take_over(event, action, where, record)
            match = EVENT_KEY.match(event.key)
            if event.key.lower() != "none" and not match and not session:
                self.warn("event.heading.format", where, f"event heading ends in '{event.key}'; use the completed plan "
                          "item ID, '<ID>/s<N>' for a stage, or 'none'", record, "", event.owner)
            if match and match.group(2) is not None:
                self.check_stage_event(event, match.group(1), int(match.group(2)), where, record)
            self.check_decision(event, where, record)
            for item_id in re.findall(rf"removed ({H_PATTERN})", action):
                if item_id in self.plan_items:
                    self.error("event.removed.queued", where, f"{item_id} is logged as removed but is still in plan.md",
                               item_id, "", event.owner)
            for item_id in sorted(done & self.plan_items.keys()):
                self.error("event.finished.queued", where, f"{item_id} is logged as finished but is still in plan.md",
                           item_id, "", event.owner)
            for name in ("Discovery updates", "New plan items"):
                value = event.fields.get(name)
                if value is not None and (value.lower() == "none" or value == ""):
                    self.info("event.reason.missing", where, f"'{name}' may list IDs or read 'none — <reason>'",
                              record, name, event.owner)
            for item_id in H_ID.findall(event.fields.get("New plan items", "")):
                if item_id in self.plan_items or item_id in taken_over or item_id in finished:
                    continue
                self.error("event.item.lost", where, f"{item_id} was queued here but is not in plan.md and was never "
                           "finished or taken over", item_id, "", event.owner)
            for name in ("Discovery updates", "Review verdict"):
                for disc_id in D_ID.findall(event.fields.get(name, "")):
                    if disc_id not in self.discoveries:
                        self.error("event.discovery.dangling", where, f"'{name}' names {disc_id}, which is not in "
                                   "discoveries.md", disc_id, name, event.owner)

    def check_stage_event(self, event: Block, item_id: str, stage: int, where: str, record: str) -> None:
        item = self.plan_items.get(item_id)
        if item is None:
            return  # the item already left plan.md; its stages cannot be checked any more
        declared = item.fields.get("Stages")
        if declared is None:
            self.warn("event.stage.undeclared", where, f"stage event {event.key} for {item_id}, which has no "
                      "'Stages:' line", record, "", event.owner)
        elif stage not in parse_stages(declared)[0]:
            self.warn("event.stage.beyond", where, f"stage event {event.key}: s{stage} is not among the stages "
                      f"declared for {item_id} ({declared})", record, "", event.owner)

    def check_decision(self, event: Block, where: str, record: str) -> None:
        from ro_stages import result_review_issue
        problem = result_review_issue(self.root, event.key, event.fields, event.heading_date)
        if problem:
            self.warn("event.stage.review", where, problem, record, "Review artifact", event.owner)
        decision = event.fields.get("Decision")
        if decision is None:
            return
        allowed = (("changed", "unchanged", "operational") if self.work or event.key == "session"
                   else ("changed", "operational"))
        if decision not in allowed:
            self.warn("event.decision.value", where, f"Decision '{decision}' must be " + ", ".join(allowed),
                      record, "Decision", event.owner)
        elif decision in ("changed", "unchanged") and not D_ID.search(event.fields.get("Discovery updates", "")):
            self.warn("event.decision.discovery", where, f"Decision: {decision} needs its experimental result under "
                      "'Discovery updates', including results that reject a change", record, "Decision", event.owner)

    def check_take_over(self, event: Block, action: str, where: str, record: str) -> None:
        """A take-over names the old ID, source slot, kind, and new ID; cross-host ones give a reason."""
        match = TAKE_OVER.match(action)
        if not match:
            self.warn("event.takeover.format", where, "take-over must read 'took over H-… from X (same host) as H-…' or "
                      "'took over H-… from X (cross-host: <from> → <to>; reason: <why>) as H-…'", record, "Action",
                      event.owner)
            return
        old_id, source, kind, new_id = match.groups()
        if new_id != event.key:
            self.error("event.takeover.heading", where, f"take-over names new ID {new_id} but the event heading is "
                       f"{event.key}", record, "Action", event.owner)
        if not new_id.startswith(f"H-{event.owner}-"):
            self.error("event.takeover.owner", where, f"take-over gives {new_id}, which is not an ID of agent "
                       f"{event.owner}", record, "Action", event.owner)
        if old_id.startswith(f"H-{event.owner}-") or source == event.owner:
            self.error("event.takeover.self", where, f"agent {event.owner} cannot take over its own item {old_id}",
                       record, "Action", event.owner)
        if kind.startswith("cross-host") and self.values.get("platform_mode") == "single":
            self.error("event.takeover.single", where, "cross-host take-over is not allowed in a single-platform "
                       "project", record, "Action", event.owner)
        if kind.startswith("cross-host"):
            reason = kind.split("reason:", 1)[1].strip() if "reason:" in kind else ""
            if not reason:
                self.warn("event.takeover.reason", where, "cross-host take-over must state a reason", record, "Action",
                          event.owner)
            hosts = kind[len("cross-host:"):].split(";", 1)[0]
            target = hosts.split("→")[-1].strip()
            if target and target != event.fields.get("Host", ""):
                self.error("event.takeover.host", where, f"cross-host take-over names '{target}' as the new host, but the "
                           f"event's Host is '{event.fields.get('Host', '')}'", record, "Action", event.owner)

    def check_retired(self) -> None:
        for item_id in self.retired:
            if item_id in self.plan_items:
                self.error("plan.retired.queued", f"plan.md:{self.plan_items[item_id].line}", f"{item_id} was taken "
                           "over (retired) but is still in plan.md", item_id, "", self.plan_items[item_id].owner)

    def check_plan_sources(self) -> None:
        for item in self.plan_items.values():
            for disc_id in D_ID.findall(item.fields.get("Sources", "")):
                if disc_id not in self.discoveries:
                    self.error("plan.sources.dangling", f"plan.md:{item.line}", f"{item.key} cites {disc_id}, which is "
                               "not in discoveries.md", item.key, disc_id, item.owner)

    # ---------- discoveries and verification ----------

    def parse_reviews(self, disc: Block, where: str) -> list[Review]:
        reviews = []
        for line in disc.extra:
            match = REVIEW.match(line)
            if not match:
                self.warn("discovery.review.format", where, f"{disc.key} review line must read '<Host> (<Agent>): "
                          f"<VERDICT> — reason': '{line.strip()[:60]}'", disc.key, "Reviews", disc.owner)
                continue
            host, slot, verdict, resolves, rest = match.groups()
            reviewer = REVIEWER.match(rest)
            reviews.append(Review(host, slot, verdict, bool(resolves), rest, reviewer.group(1) if reviewer else None))
        return reviews

    def cross_host_rule(self, disc: Block, review: Review) -> tuple[bool, str, str]:
        """cross-host-once eligibility: (counts, check id, reason); the check id is empty when it counts."""
        if review.slot == disc.fields.get("Source"):
            return False, "discovery.review.ineligible", "the source slot never reviews its own discovery"
        if review.host != disc.fields.get("Host"):
            return True, "", ""
        if not review.rest.startswith("same host —"):
            return False, "discovery.review.same-host", (f"is reviewed by its own host ({review.host}); a same-host "
                                                         "review must start its reason with 'same host —'")
        mode = self.values.get("platform_mode", "adaptive")
        if mode == "single":
            return True, "", ""
        if mode == "adaptive" and self.values.get("fallback") == "same-host":
            return True, "", ""
        if self.legacy_review_shape(disc, review):
            if (getattr(self, "legacy_review_project", False) and
                    disc.fields.get("Cross-check") in ("VERIFIED", "HOLD", "CHALLENGED")):
                return True, "", ""
            if self.review_fingerprint(disc, review) in getattr(self, "legacy_reviews", set()):
                return True, "", ""
        why = ("an adaptive project counts a same-host review only with 'Cross-check fallback: same-host'"
               if mode == "adaptive" else "a multi project needs a review from a different host")
        return False, "discovery.review.ineligible", why

    def legacy_review_shape(self, disc: Block, review: Review) -> bool:
        """Only the 5.1.0 multi/same-host exception; v3 review records never qualify."""
        return (self.values.get("platform_mode") == "multi" and self.values.get("fallback") == "same-host"
                and not disc.fields.get("Session") and review.slot != disc.fields.get("Source")
                and review.host == disc.fields.get("Host") and review.rest.startswith("same host —")
                and not review.resolves and review.verdict in VERDICTS
                and not any(part == "reviewed" or part.startswith("reviewed ")
                            for part in review.rest.split(" — ")))

    @staticmethod
    def review_fingerprint(disc: Block, review: Review) -> str:
        """Bind the preserved review to its original discovery identity and evidence."""
        identity = [disc.key, *(disc.fields.get(key, "") for key in
                    ("Source", "Host", "User", "Date", "Finding", "Evidence")),
                    review.host, review.slot, review.verdict, review.resolves, review.rest]
        return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()

    def legacy_review_manifest(self) -> str:
        """Freeze accepted v2 exceptions before replacing its generated settings."""
        fingerprints = set()
        for disc in self.discoveries.values():
            if disc.fields.get("Cross-check") not in ("VERIFIED", "HOLD", "CHALLENGED"):
                continue
            if any(issue.record == disc.key and issue.severity == "ERROR" for issue in self.issues):
                continue
            for review in self.parse_reviews(disc, f"discoveries.md:{disc.line}"):
                if self.legacy_review_shape(disc, review) and not self.review_chronology(disc, review):
                    fingerprints.add(self.review_fingerprint(disc, review))
        return ("<!-- ro-legacy-reviews: v2 " + ",".join(sorted(fingerprints)) + " -->\n"
                if fingerprints else "")

    def review_chronology(self, disc: Block, review: Review) -> tuple[str, str, str] | None:
        """Recorded identity and time cannot be made valid by another eligibility route."""
        local_offset = self.now.utcoffset() if self.now.tzinfo else self.now.astimezone().utcoffset()

        def instant(value):
            # Arithmetic supports valid dates outside the host's timestamp range.
            offset = value.utcoffset() if value.tzinfo else local_offset
            return value.replace(tzinfo=None) - dt.datetime.min - (offset or dt.timedelta())

        token = review.reviewer
        identity = REVIEWER_TOKEN.fullmatch(token or "")
        moment = None
        if identity:
            try:
                moment = dt.datetime.fromisoformat(identity.group(1).replace("Z", "+00:00"))
            except ValueError:
                pass
        if token and moment is None:
            return "WARN", "discovery.review.identity", (
                f"review by {review.host} ({review.slot}) names reviewer {token}; it counts only with a session identity "
                "such as 'reviewer subagent:<name>@<start time>'")
        if moment and instant(moment) > instant(self.now):
            return "WARN", "discovery.review.identity", (
                f"reviewer {token} has a session start ahead of the clock")
        source = REVIEWER_TOKEN.fullmatch(disc.fields.get("Session", ""))
        if source:
            try:
                source_start = dt.datetime.fromisoformat(source[1].replace("Z", "+00:00"))
            except ValueError:
                source_start = None
            if source_start and instant(source_start) > instant(self.now):
                return "WARN", "discovery.review.identity", "source session start is ahead of the clock"
        # Session start establishes identity, not when this evidence was reviewed.
        # Existing undated review lines retain their meaning; validate review time
        # when separately recorded rather than inventing one from the identity.
        stamps = [part.removeprefix("reviewed").strip() for part in review.rest.split(" — ")
                  if part == "reviewed" or part.startswith("reviewed ")]
        if stamps:
            reviewed = None
            if len(stamps) == 1 and re.fullmatch(ISO_MOMENT, stamps[0]):
                try:
                    reviewed = dt.datetime.fromisoformat(stamps[0].replace("Z", "+00:00"))
                except ValueError:
                    pass
            if reviewed is None:
                return "WARN", "discovery.review.time", "has an invalid or repeated reviewed timestamp"
            discovery_day = self.iso_day(disc.fields.get("Date", ""))
            if instant(reviewed) > instant(self.now):
                reason = "review time is ahead of the clock"
            elif moment and instant(reviewed) < instant(moment):
                reason = "review time predates the reviewer session start"
            elif discovery_day and instant(reviewed) < instant(dt.datetime.combine(discovery_day, dt.time())):
                reason = "review time predates the discovery Date"
            else:
                reason = ""
            if reason:
                return "WARN", "discovery.review.time", reason
        return None

    def independent_rule(self, disc: Block, review: Review) -> tuple[bool, str, str, str]:
        """independent-review eligibility: (counts, severity, check id, reason) of the note it raises, if any."""
        if issue := self.review_chronology(disc, review):
            return False, *issue
        session = disc.fields.get("Session")
        token = review.reviewer
        if not session:
            if review.slot != disc.fields.get("Source"):
                return True, "INFO", "discovery.review.legacy-session", (
                    f"has no 'Session:' line; the review by slot {review.slot} counts as a review by another slot")
            return False, "INFO", "discovery.review.legacy-session", (
                f"has no 'Session:' line, so a review from its own slot {review.slot} cannot verify it")
        if not token:
            return False, "WARN", "discovery.review.identity", (
                f"review by {review.host} ({review.slot}) names no reviewer; it counts only with a session identity "
                "such as 'reviewer subagent:<name>@<start time>'")
        if token == session:
            return False, "INFO", "discovery.review.self", (
                f"reviewer {token} is the discovery's own session, so this review does not count")
        return True, "", "", ""

    def review_counts(self, disc: Block, review: Review, where: str) -> bool:
        """Whether a review counts under the project's Verification; raises the note that explains it."""
        mode = self.values.get("verification", "cross-host-once")
        record, field_name = disc.key, f"review:{review.host} ({review.slot})"
        if issue := self.review_chronology(disc, review):
            self.add(issue[0], issue[1], where, f"{disc.key} {issue[2]}", record, field_name, review.slot)
            return False
        if mode == "self":
            return True
        cross = self.cross_host_rule(disc, review) if mode in ("cross-host-once", "hybrid") else None
        independent = self.independent_rule(disc, review) if mode in ("independent-review", "hybrid") else None
        if cross and cross[0]:
            return True
        if independent and independent[0]:
            if independent[2]:
                self.add(independent[1], independent[2], where, f"{disc.key} {independent[3]}", record, field_name,
                         review.slot)
            return True
        # Not counted: explain with the rule that applies (hybrid: the independent one when a reviewer is named).
        if independent and (cross is None or review.reviewer):
            self.add(independent[1], independent[2], where, f"{disc.key} {independent[3]}", record, field_name,
                     review.slot)
        elif cross:
            self.warn(cross[1], where, f"{disc.key} {cross[2]}; this review does not count", record, field_name,
                      review.slot)
        return False

    def check_discoveries(self) -> None:
        mode = self.values.get("verification", "cross-host-once")
        for disc in self.discoveries.values():
            where = f"discoveries.md:{disc.line}"
            self.check_fields(where, disc, DISCOVERY_FIELDS, DISCOVERY_OPTIONAL, "discovery",
                              skip_missing={"Cross-check", "Reviews"} if mode == "self" else None)
            date = disc.fields.get("Date")
            if date is not None and date != "unknown":
                if not DATE.match(date):
                    self.warn("discovery.date.format", where, f"{disc.key} Date '{date}' must be YYYY-MM-DD or "
                              "'unknown'", disc.key, "Date", disc.owner)
                elif date > self.now.date().isoformat():
                    self.warn("time.future", where, f"{disc.key} Date {date} is ahead of the clock", disc.key, "Date",
                              disc.owner)
            raw_state = disc.fields.get("Cross-check", "PENDING" if mode == "self" else "")
            state = raw_state.split(" ", 1)[0]
            if "Cross-check" in disc.fields and state not in CROSS_CHECK_STATES:
                self.error("discovery.state.unknown", where, f"{disc.key} has unknown Cross-check state '{raw_state}'",
                           disc.key, "Cross-check", disc.owner)
            # The effective state, computed review by review in order. A CHALLENGED review stands until a counting
            # '<VERDICT> after challenge' resolves it; an ordinary verdict meanwhile leaves it CHALLENGED.
            expected, standing, challenged_ever = "PENDING", False, False
            for review in self.parse_reviews(disc, where):
                verdict = RESOLUTIONS.get(review.verdict) if review.resolves else review.verdict
                if verdict is None or (not review.resolves and verdict not in VERDICTS):
                    suffix = " after challenge" if review.resolves else ""
                    self.warn("discovery.review.verdict", where, f"{disc.key} verdict '{review.verdict}{suffix}' must "
                              "be CLOSED, HOLD, or CHALLENGED (a resolution: CLOSED, HOLD, or VERIFIED after "
                              "challenge)", disc.key, "Reviews", review.slot)
                    continue
                counts = self.review_counts(disc, review, where)
                if verdict == "CHALLENGED":
                    standing = challenged_ever = True  # a challenge stands even from a review that does not count
                    expected = "CHALLENGED"
                elif not counts:
                    continue
                elif review.resolves or not standing:
                    standing = False
                    expected = STATE_FOR_VERDICT[verdict]
            if state in ("VERIFIED", "HOLD", "PENDING") and standing:
                self.error("discovery.state.challenged", where, f"{disc.key} is {state}, but a CHALLENGED review "
                           "stands; it stays CHALLENGED until an eligible reviewer resolves it with '<VERDICT> after "
                           "challenge'", disc.key, "Cross-check", disc.owner)
            elif state in ("VERIFIED", "HOLD") and expected != state:
                if expected == "PENDING":
                    check = "discovery.state.unbacked"
                    detail = f"has no {VERDICT_FOR_STATE[state]} review that counts under Verification {mode}"
                else:
                    check = "discovery.state.mismatch"
                    detail = f"its reviews, read in order, leave it {expected}"
                self.error(check, where, f"{disc.key} is {state} but {detail}", disc.key, "Cross-check", disc.owner)
            elif state == "CHALLENGED" and expected != "CHALLENGED":
                if challenged_ever:
                    self.error("discovery.state.superseded", where, f"{disc.key} is CHALLENGED, but a later review "
                               f"resolved the challenge; its reviews leave it {expected}", disc.key, "Cross-check",
                               disc.owner)
                else:
                    self.error("discovery.state.unbacked", where, f"{disc.key} is CHALLENGED but has no 'CHALLENGED' "
                               "review line", disc.key, "Cross-check", disc.owner)
            elif state == "PENDING" and mode in ("independent-review", "hybrid"):
                self.info("discovery.review.pending", where, f"{disc.key} awaits an independent review (a host without "
                          "sub-agents leaves it PENDING; that is never an error)", disc.key, "Cross-check", disc.owner)
            if state == "REVIEWING":
                claim = re.search(r"\((\S+)\)\s*$", raw_state)
                claimer = claim.group(1) if claim else ""
                section = self.handoff_sections.get(claimer)
                if section is None:
                    self.error("discovery.reviewing.slot", where, f"{disc.key} is claimed by '{claimer}', which has no "
                               "handoff section", disc.key, "Cross-check", disc.owner)
                elif self.slot_free(claimer):
                    self.warn("discovery.reviewing.stale", where, f"{disc.key} is still claimed by {claimer}, but that "
                              f"slot is released; restore its prior effective state, {expected}", disc.key,
                              "Cross-check", claimer)

    def check_current_best(self) -> None:
        value = self.shared.get("Current best")
        if value is None:
            self.shared_missing("handoff.shared.missing", "handoff.md", "Shared state has no 'Current best' line (use 'none yet' "
                       "until a result sets it)", "handoff.md", "Current best")
            return
        setters = [d for d in self.discovery_order
                   if self.discoveries[d].fields.get("Implication", "").lower().startswith("new current best:")
                   and not self.discoveries[d].fields.get("Cross-check", "").startswith("CHALLENGED")]
        cited = D_ID.findall(value)
        if value.lower().startswith("none"):
            if setters:
                self.warn("handoff.best.stale", "handoff.md", f"Current best says '{value}', but {setters[-1]} set a "
                          "new current best", "handoff.md", "Current best")
            return
        if not cited:
            self.warn("handoff.best.citation", "handoff.md", f"Current best '{value}' must cite the discovery that set "
                      "it", "handoff.md", "Current best")
            return
        for disc_id in cited:
            if disc_id not in self.discoveries:
                self.error("handoff.best.dangling", "handoff.md", f"Current best cites {disc_id}, which is not in "
                           "discoveries.md", "handoff.md", "Current best")
        if setters and setters[-1] not in cited:
            self.warn("handoff.best.stale", "handoff.md", f"Current best is stale: it cites {', '.join(cited)}, but the "
                      f"latest new best is {setters[-1]}", "handoff.md", "Current best")
        for disc_id in cited:
            disc = self.discoveries.get(disc_id)
            if disc and disc.fields.get("Cross-check", "").startswith("CHALLENGED"):
                self.warn("handoff.best.challenged", "handoff.md", f"Current best cites {disc_id}, which is CHALLENGED",
                          "handoff.md", "Current best")

    def check_compute(self) -> None:
        value = self.shared.get("Active compute")
        if value is None:
            self.shared_missing("handoff.shared.missing", "handoff.md", "Shared state has no 'Active compute' line (use 'none')",
                       "handoff.md", "Active compute")
            return
        if value.lower() == "none":
            return
        for claim in (part.strip() for part in value.split(";")):
            match = CLAIM.match(claim)
            if not match:
                self.warn("compute.claim.format", "handoff.md", f"Active compute claim '{claim}' must read "
                          "'<CPU|GPU|Other>[@machine] — <Agent> (<H-item>, since YYYY-MM-DD HH:MM)'",
                          "handoff.md", f"compute:{claim[:40]}")
                continue
            resource, agent, item_id, since = match.groups()
            record = f"compute:{resource} {agent} {item_id}"
            self.check_time(since, "handoff.md", record, "Active compute", agent)
            section = self.handoff_sections.get(agent)
            if section is None:
                self.error("compute.claim.slot", "handoff.md", f"{resource} claim names agent {agent}, which has no "
                           "handoff section", record, "", agent)
                continue
            if self.slot_free(agent):
                self.warn("compute.claim.stale", "handoff.md", f"stale {resource} claim: {agent} is released but still "
                          f"holds it for {item_id}; anyone may clear it and log the cleanup", record, "", agent)
            item = self.plan_items.get(item_id)
            if item is None:
                self.warn("compute.claim.gone", "handoff.md", f"stale {resource} claim: {item_id} is no longer in "
                          "plan.md; remove the claim when the job's end is recorded", record, "", agent)
                continue
            holder = item.claim[0] if self.unified and item.claim else item.owner
            if holder and holder != agent:
                self.error("compute.claim.owner", "handoff.md", f"{resource} claim by {agent} is for {item_id}, which "
                           f"belongs to {holder}", record, "", agent)

    def check_users_and_hosts(self) -> None:
        raw = self.shared.get("Users")
        if raw is None:
            self.error("handoff.shared.missing", "handoff.md", "Shared state has no 'Users' line (use 'none yet' until "
                       "someone runs a session)", "handoff.md", "Users")
            users: set[str] = set()
        else:
            users = set() if raw.lower() == "none yet" else {u.strip() for u in raw.split(",") if u.strip()}
        for user in sorted(users):
            if not USER_NAME.match(user) or user in AGENT_NAMES:
                self.error("handoff.user.invalid", "handoff.md", f"user name '{user}' must be one word like kim or "
                           "user1, not a slot name", "handoff.md", f"user:{user}")

        def check_host(host: str, where: str, record: str, owner: str) -> None:
            if self.platforms and host and host not in self.platforms:
                report = (self.warn if self.platforms == ["local"] and
                          self.values.get("platform_mode") == "single" else self.error)
                report("host.unlisted", where, f"host '{host}' is not in Platforms ({', '.join(self.platforms)}); "
                           "add it with --reconfigure if this project now uses it", record, f"host:{host}", owner)

        for name, section in self.handoff_sections.items():
            where = f"handoff.md:{section.line}"
            host = section.fields.get("Current host", "")
            user = section.fields.get("Current user")
            if user is None:
                self.error("handoff.slot.field-missing", where, f"agent {name}'s section has no 'Current user' line",
                           f"slot:{name}", "Current user", name)
            elif host.lower() in FREE_HOSTS:
                if user.lower() not in {"none", "unassigned"}:
                    self.warn("handoff.slot.user-stale", where, f"agent {name} is {host} but still names user "
                              f"'{user}'; set Current user: none", f"slot:{name}", "Current user", name)
            else:
                check_host(host, where, f"slot:{name}", name)
                if user not in users:
                    self.error("handoff.user.unlisted", where, f"agent {name}'s Current user '{user}' is not listed in "
                               "Users", f"slot:{name}", "Current user", name)
        for event in self.events:
            where = f"handoff.md:{event.line}"
            record = f"event:{event.heading_date} {event.owner} {event.key}"
            check_host(event.fields.get("Host", ""), where, record, event.owner)
            user = event.fields.get("User", "")
            if user and user not in users:
                self.error("handoff.user.unlisted", where, f"event user '{user}' is not listed in Users", record,
                           "User", event.owner)
        for disc in self.discoveries.values():
            where = f"discoveries.md:{disc.line}"
            check_host(disc.fields.get("Host", ""), where, disc.key, disc.owner)
            user = disc.fields.get("User")
            if user is not None and user != "unknown" and user not in users:
                self.error("handoff.user.unlisted", where, f"{disc.key} user '{user}' is not listed in Users", disc.key,
                           "User", disc.owner)

    def shared_missing(self, *args) -> None:
        """Work and research can resume without unused collector summaries."""
        report = self.info if self.values.get("profile") in {"work", "research"} and self.values.get("collector", "off") == "off" else self.error
        report(*args)

    def check_collection(self) -> None:
        value = self.shared.get("Plan collection")
        if value is None:
            self.shared_missing("handoff.shared.missing", "handoff.md", "Shared state has no 'Plan collection' line (use 'idle')",
                       "handoff.md", "Plan collection")
            return
        if value == "idle":
            return
        match = COLLECTION.match(value)
        if not match:
            self.warn("collection.format", "handoff.md", f"Plan collection '{value}' must be 'idle' or 'running — "
                      "<Agent> (since YYYY-MM-DD HH:MM)'", "handoff.md", "Plan collection")
            return
        agent, since = match.groups()
        self.check_time(since, "handoff.md", "handoff.md", "Plan collection", agent)
        section = self.handoff_sections.get(agent)
        if section is None or self.slot_free(agent):
            self.warn("collection.stale", "handoff.md", f"Plan collection is still marked running by {agent}, whose "
                      "slot is released; set it to idle and log the cleanup", "handoff.md", "Plan collection", agent)
        if self.values.get("collector", "off") == "off":
            self.warn("collection.off", "handoff.md", "Plan collection is running but Plan collector is off in "
                      "agents.md", "handoff.md", "Plan collection", agent)

    def check_open_issues(self) -> None:
        value = self.shared.get("Open consistency issues")
        if value is None:
            self.error("handoff.shared.missing", "handoff.md", "Shared state has no 'Open consistency issues' line "
                       "(use 'none')", "handoff.md", "Open consistency issues")
        elif value.lower() != "none":
            self.info("handoff.open-issues", "handoff.md", f"open consistency issues recorded in Shared state: {value}",
                      "handoff.md", "Open consistency issues")

    # ---------- optional evidence guards ----------

    def guard_issue(self, guard: str, check: str, block: Block | None, message: str,
                    field_name: str = "", light: str = "WARN") -> None:
        if guard not in self.guards:
            return
        self.guard_checks.add(check)
        severity = light
        if rs.guard_mode(self.values["guards"]) == "strict":
            if check in STRICT_ERRORS and light != "INFO":
                severity = "ERROR"
            elif check in {"guard.effort.share", "guard.control.missing"}:
                severity = "WARN"
        filename = "discoveries.md" if block and block.key.startswith("D-") else "handoff.md"
        if block and block.key.startswith("H-"):
            filename = "plan.md"
        record = block.key if block else "handoff.md"
        if block and block.heading_date:
            record = f"event:{block.heading_date} {block.owner} {block.key}"
        self.add(severity, check, f"{filename}:{block.line}" if block else filename, message,
                 record, field_name)

    @staticmethod
    def record_day(block: Block) -> dt.date | None:
        text = block.fields.get("Date", block.heading_date)
        if not text:
            # External actions have no Date field; their result/expectation timestamps date them.
            text = (Checker.observed_stamp(block.fields.get("Result", "")) or
                    Checker.observed_stamp(block.fields.get("Expected", ""), "written") or "")
        match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        try:
            return dt.date.fromisoformat(match.group()) if match else None
        except ValueError:
            return None

    def guard_active(self, block: Block) -> bool:
        since = rs.guard_since(self.values["guards"])
        day = self.record_day(block)
        return not (since and day and day < since)

    def evidence_exists(self, value: str) -> bool:
        keys = D_ID.findall(value)
        return bool(keys) and all(key in self.discoveries for key in keys)

    def numeric_resolution(self, instrument: Block) -> float | None:
        match = re.fullmatch(rf"±\s*({NUMBER})\s*\(([^)]+)\)", instrument.fields.get("Resolution", ""))
        return (float(match.group(1)) if match and float(match.group(1)) >= 0
                and self.evidence_exists(match.group(2)) else None)

    def eligible_instrument(self, disc: Block) -> bool:
        decision = disc.fields.get("Decision class", "")
        if decision not in DECISION_CLASSES:
            return False
        decision = DECISION_ALIASES.get(decision, decision)
        for key in I_ID.findall(disc.fields.get("Instrument", "")):
            instrument = self.instruments.get(key)
            if instrument is None:
                continue
            fields = instrument.fields
            forbidden = {DECISION_ALIASES.get(value.strip(), value.strip())
                         for value in fields.get("Not for", "").split(",")}
            provenance = fields.get("Provenance")
            if provenance == "derived-from-targets":
                forbidden.add("target-change")
            elif provenance == "own-lineage":
                forbidden.update(("target-change", "model-change"))
            agreement = fields.get("Agreement", "").strip()
            supported = (bool(agreement) and not agreement.lower().startswith("unmeasured")
                         and self.evidence_exists(agreement))
            # A complete analytic/exhaustive measurement needs no estimated agreement;
            # completeness does not override the independent provenance restrictions.
            complete = fields.get("Coverage") == "complete" and agreement == "unmeasured"
            if (provenance in {"independent", "derived-from-targets", "own-lineage", "external-feedback"}
                    and decision not in forbidden and (supported or complete)):
                return True
        return False

    def check_evidence_references(self, discoveries: list[Block], instruments: list[Block],
                                  items: list[Block], actions: list[Block]) -> None:
        """Check active, applicable guard records; historical evidence can still be cited."""
        parts = {"Gap", "Decomposition", "Core families", "Data audit", "Intake",
                 "Rejected consistent gains", "Decisions"}
        instrument_guard = "G1" if "G1" in self.guards else "G3"
        records = [(b, instrument_guard, {"Agreement", "Resolution"}) for b in instruments]
        for disc in discoveries:
            records.append((disc, "G5", {"Rejected on", "Override resolved"}))
            if disc.fields.get("Kind") == "insight":
                records.append((disc, "G6", {"Status"}))
            if disc.fields.get("Kind") == "direction-review":
                records.append((disc, "GD", parts))
        records += [(b, "G3", {"Saturation exit"}) for b in items]
        for block, guard, names in records:
            for name in sorted(names):
                for key in dict.fromkeys(D_ID.findall(block.fields.get(name, ""))):
                    if key not in self.discoveries:
                        self.guard_issue(guard, "evidence.discovery.dangling", block,
                                         f"{name} cites missing discovery {key}", name, "ERROR")
        citations = [(b, "G3", "Saturation exit") for b in items]
        citations += [(b, instrument_guard, "Instrument") for b in discoveries]
        citations += [(b, "G5", "Rejected on") for b in discoveries]
        citations += [(b, instrument_guard, "Result") for b in discoveries + actions]
        for block, guard, name in citations:
            value = block.fields.get(name, "")
            keys = ([match[2] for match in MEASUREMENT.findall(value)] if name == "Result"
                    else I_ID.findall(value))
            for key in dict.fromkeys(keys):
                if key not in self.instruments:
                    self.guard_issue(guard, "evidence.instrument.dangling", block,
                                     f"{name} cites missing instrument {key}", name, "ERROR")

    def check_external_schema(self, actions: list[Block]) -> None:
        for action in actions:
            where = f"handoff.md:{action.line}"
            fields = action.fields
            # Expected has its own severity rule, ext.expected; do not report it twice.
            self.check_fields(where, action, EXTERNAL_FIELDS, EXTERNAL_OPTIONAL, "external",
                              guard="E1", skip_missing={"Expected"})
            if not X_ID.fullmatch(action.key):
                self.guard_issue("E1", "external.id.format", action,
                                 "external action ID must be X-<slot>-NNN", "ID", "ERROR")
            invalid = {
                "Kind": fields.get("Kind") not in {"submission", "deploy", "release", "publish", "message", "other"},
                "Candidate": not ARTIFACT.fullmatch(fields.get("Candidate", "")),
                "Destination": not fields.get("Destination", "").strip(),
                "Result": fields.get("Result") != "pending" and
                          (self.observed_stamp(fields.get("Result", "")) is None or
                           not re.fullmatch(r"\S.*\s+\(observed \d{4}-\d{2}-\d{2} \d{2}:\d{2}\)",
                                            fields.get("Result", ""))),
                "Final": not fields.get("Final", "").strip(),
                "Status": fields.get("Status") not in {"prepared", "in-flight", "unknown", "done", "complete",
                                                        "error", "withdrawn"},
            }
            for name, bad in invalid.items():
                if bad and name in fields:
                    self.guard_issue("E1", "external.field.invalid", action, f"invalid external action {name}", name)

    @staticmethod
    def insight_status(status: str) -> tuple[str, str]:
        if status == "open":
            return "open", ""
        if match := re.fullmatch(rf"planned ({H_PATTERN})", status):
            return "planned", match.group(1)
        if match := re.fullmatch(rf"rejected — ({D_PATTERN})\s+(\S.*)", status):
            return "rejected", match.group(1)
        return "invalid", ""

    def check_guards(self) -> None:
        self.guards = rs.enabled_guards(self.values)
        enabled = self.guards.copy()
        # Applicability is declared once and applies to every check owned by that guard.
        for part in self.shared.get("Not applicable", "").split(";"):
            match = re.match(r"\s*(G1|G3|G5|G6|GD|G8|G11|G12|E1)\b\s*—\s*\S", part)
            if match:
                if match.group(1) not in enabled:
                    self.guard_checks.add("guard.applicability.disabled")
                    self.info("guard.applicability.disabled", "handoff.md",
                              f"Not applicable names {match.group(1)}, which is not enabled; remove the unused exemption",
                              match.group(1), "Not applicable")
                self.guards.discard(match.group(1))
        if not self.guards:
            return
        thresholds = rs.guard_thresholds(self.values["guard_thresholds"])
        since = rs.guard_since(self.values["guards"])
        records = [*self.discoveries.values(), *self.events, *self.plan_items.values(), *self.guard_records]
        old = [b for b in records if not self.guard_active(b)]
        discoveries = [d for d in self.discoveries.values() if self.guard_active(d)]
        actions = [a for a in self.guard_records if a.section == "external actions" and self.guard_active(a)]
        events = [e for e in self.events if self.guard_active(e)]
        instruments = [i for i in self.guard_records if i.section == "instruments" and self.guard_active(i)]
        items = [i for i in self.plan_items.values() if self.guard_active(i)]
        if old:
            self.info("guard.since.exempt", "handoff.md", f"{len(old)} record(s) dated before {since} exempt",
                      "guards", "since")
        identities: dict[tuple[str, str], list[Block]] = {}
        for block in self.guard_records:
            identities.setdefault((block.section, block.key), []).append(block)
        for duplicates in identities.values():
            active = [b for b in duplicates if self.guard_active(b)]
            for block in (active[1:] or active[:1]) if len(duplicates) > 1 else []:
                guard = "E1" if block.section == "external actions" else "G1" if "G1" in self.guards else "G3"
                self.guard_issue(guard, "handoff.id.duplicate", block,
                                 f"duplicate record ID {block.key}", "ID", "ERROR")
        for instrument in instruments:
            if not I_ID.fullmatch(instrument.key):
                guard = "G1" if "G1" in self.guards else "G3"
                self.guard_issue(guard, "instrument.id.format", instrument,
                                 "instrument ID must be I-<slot>-NN", "ID", "ERROR")
        # Validate supplied schema before any evidence-consumer eligibility checks.
        for disc in discoveries:
            if "Decision class" in disc.fields and disc.fields["Decision class"] not in DECISION_CLASSES:
                self.error("guard.decision.invalid", f"discoveries.md:{disc.line}",
                           "Decision class must exactly match an allowed class: " + ", ".join(sorted(DECISION_CLASSES)),
                           disc.key, "Decision class")
        self.check_external_schema(actions)
        self.check_evidence_references(discoveries, instruments, items, actions)
        resolved: dict[str, list[Block]] = {}
        for disc in self.discoveries.values():
            for key in D_ID.findall(disc.fields.get("Override resolved", "")):
                resolved.setdefault(key, []).append(disc)
        completed = self.finished_items
        for disc in discoveries:
            fields = disc.fields
            decision = fields.get("Decision class", "")
            decision = DECISION_ALIASES.get(decision, decision)
            deciding = decision and decision not in {"operational", "other"}
            if decision in {"model-change", "input-change", "combination"}:
                control = fields.get("Control", "").strip()
                measured = re.fullmatch(rf"(.+?);\s*selection gain\s+({NUMBER})(?:\s+[^;]+)?", control)
                if measured and measured[1].strip().casefold() in {"none", "unknown", "pending", "tbd", "n/a"}:
                    measured = None
                justified = re.fullmatch(r"not applicable\s+—\s+\S.+;\s*alternative:\s*\S.+", control)
                if not measured and not justified:
                    self.guard_issue("G1", "guard.control.missing", disc,
                                     "record Control: <artifact>; selection gain <number>, or a reason and "
                                     "alternative uncertainty check; selected gains may be noise", "Control", "INFO")
            cited = I_ID.findall(fields.get("Instrument", ""))
            if deciding:
                if not cited:
                    self.guard_issue("G1", "guard.instrument.missing", disc, "record the deciding instrument", "Instrument")
                if not self.eligible_instrument(disc):
                    self.guard_issue("G1", "guard.instrument.circular", disc,
                                     "no eligible deciding instrument has measured Agreement or complete coverage", "Instrument")
            if any(self.instruments[k].fields.get("Coverage") == "in-sample" for k in cited if k in self.instruments):
                self.guard_issue("G1", "guard.instrument.insample", disc, "deciding evidence includes in-sample coverage",
                                 "Instrument")
            override = fields.get("Override", "")
            later = any((self.record_day(r) or dt.date.min, r.line) >
                        (self.record_day(disc) or dt.date.min, disc.line) for r in resolved.get(disc.key, []))
            if override and not later:
                self.guard_issue("G5", "guard.override.open", disc, "override remains open until a later Override resolved",
                                 "Override", "INFO")
                expires = re.search(r"\bexpires (\d{4}-\d{2}-\d{2})(?:;|$)", override)
                try:
                    expired = not expires or dt.date.fromisoformat(expires.group(1)) < self.now.date()
                except ValueError:
                    expired = True
                if not re.search(r"re-check:\s*[^;\s]", override) or expired:
                    self.guard_issue("G5", "guard.override.recheck", disc, "override needs a re-check trigger and a live expiry",
                                     "Override")
            rejection = fields.get("Rejected on", "")
            outcome = fields.get("Outcome", "")
            if deciding and outcome not in {"supported", "rejected", "inconclusive"}:
                self.guard_issue("G5", "guard.outcome.invalid" if "Outcome" in fields else "guard.outcome.missing",
                                 disc, "record Outcome: supported | rejected | inconclusive so the decision is "
                                 "checked independently of its prose language", "Outcome")
            legacy_rejection = not outcome and re.search(r"\bdoes not hold\b", fields.get("Finding", ""), re.I)
            if deciding and (outcome == "rejected" or legacy_rejection):
                fired = re.search(r";\s*fired:\s*(.*?)\s*$", rejection)
                execution = fired.group(1).strip() if fired else ""
                placeholder = execution.casefold().strip(" .;:!—-") in {
                    "", "n/a", "na", "yes", "no", "none", "not applicable", "pending", "tbd", "unknown",
                    "done", "true", "false",
                }
                citations = D_ID.findall(execution)
                if (not I_ID.search(rejection) or placeholder or
                        (citations and not self.evidence_exists(execution))):
                    self.guard_issue("G5", "guard.rejection.evidence", disc,
                                     "record Rejected on: instrument; fired: evidence the change executed", "Rejected on")
            if fields.get("Kind") == "insight":
                status = fields.get("Status", "")
                status_kind, status_key = self.insight_status(status)
                if status_kind == "rejected" and not self.evidence_exists(status):
                    status_kind = "invalid"
                due = parse_stamp(fields.get("Due", ""))
                dated = self.record_day(disc)
                max_due = (dt.datetime.combine(dated, dt.time()) + dt.timedelta(hours=thresholds["insight-due"])
                           if dated else None)
                if (status_kind == "invalid" or status_kind == "open" and
                        (due is None or due < self.now or (max_due and due > max_due))
                        or status_kind == "planned" and
                           status_key not in self.plan_items and status_key not in completed):
                    self.guard_issue("G6", "guard.insight.overdue", disc,
                                     "insight needs a valid Status and a timely Due or a live/completed plan item",
                                     "Status")
                if status_kind == "rejected":
                    evidence = [self.discoveries[k] for k in D_ID.findall(status) if k in self.discoveries]
                    if any(d.fields.get("Decision class") not in (None, "operational", "other")
                           and not self.eligible_instrument(d) for d in evidence):
                        self.guard_issue("G6", "guard.insight.rejection", disc,
                                         "insight rejection cites circular deciding evidence", "Status")
            if (fields.get("Implication", "").lower().startswith("new current best:")
                    and not fields.get("Consistency", "").strip()):
                self.guard_issue("G1", "guard.new-best.consistency", disc, "record Consistency or not applicable",
                                 "Consistency", "INFO")
        for instrument in instruments:
            self.check_instrument_schema(instrument)
        self.check_saturation(discoveries, actions, int(thresholds["saturation"]))
        self.check_direction(discoveries, float(thresholds["direction-review"]))
        self.check_phase(thresholds["milestones"])
        self.check_selection()
        self.check_effort(events, float(thresholds["effort"]))
        self.check_external(actions)

    def check_instrument_schema(self, instrument: Block) -> None:
        fields = instrument.fields
        required = {"Provenance", "Coverage", "Measures", "Agreement", "Resolution", "Not for"}
        provenance = fields.get("Provenance")
        declared = {v.strip() for v in fields.get("Not for", "").split(",")}
        forbidden = {DECISION_ALIASES.get(value, value) for value in declared}
        expected = ({"target-change", "model-change"} if provenance == "own-lineage" else
                    {"target-change"} if provenance == "derived-from-targets" else set())
        agreement = fields.get("Agreement", "")
        invalid = (not all(fields.get(k, "").strip() for k in required)
                   or provenance not in {"independent", "derived-from-targets", "own-lineage", "external-feedback"}
                   or fields.get("Coverage") not in {"held-out", "in-sample", "external", "complete"}
                   or not expected <= forbidden or not declared <= DECISION_CLASSES | {"none"}
                   or (agreement != "unmeasured" and not self.evidence_exists(agreement))
                   or (fields.get("Resolution") != "unmeasured" and self.numeric_resolution(instrument) is None)
                   or (provenance == "external-feedback" and
                       (not fields.get("Dynamics", "").strip() or self.numeric_resolution(instrument) is None)))
        if invalid:
            self.guard_issue("G1", "guard.instrument.schema", instrument,
                             "instrument must satisfy its provenance, coverage, agreement, resolution and Not for schema")

    def check_saturation(self, discoveries: list[Block], actions: list[Block], count: int) -> None:
        # Comparison key includes family, metric, deciding instrument and cohort; never pool cohorts.
        groups: dict[tuple[str, str, str, str], list[tuple[str, int, float]]] = {}
        for block in discoveries + actions:
            family = block.fields.get("Family", "")
            if not family:
                continue
            date = block.fields.get("Date", "")
            if block.key.startswith("X-"):
                date = self.observed_stamp(block.fields.get("Result", "")) or ""
            for metric, value, instrument, cohort in MEASUREMENT.findall(block.fields.get("Result", "")):
                # File order within each ledger, discoveries before actions on exact timestamp ties.
                order = block.line + (1_000_000 if block.key.startswith("X-") else 0)
                groups.setdefault((family, metric.strip(), instrument, cohort), []).append((date, order, float(value)))
        saturated: dict[str, set[str]] = {}
        for (family, _metric, key, _cohort), results in groups.items():
            instrument = self.instruments.get(key)
            resolution = self.numeric_resolution(instrument) if instrument else None
            recent = sorted(results)[-count:]
            if resolution is not None and len(recent) == count:
                values = [r[2] for r in recent]
                if max(values) - min(values) <= resolution + 1e-12:
                    saturated.setdefault(family, set()).add(key)
        for item in self.plan_items.values():
            if not self.guard_active(item):
                continue
            if item.fields.get("Family") not in saturated:
                continue
            exit_rule = item.fields.get("Saturation exit", "")
            instrument_exit = re.fullmatch(rf"instrument ({I_PATTERN})", exit_rule)
            structural_exit = re.fullmatch(rf"structural:\s*(\S.*?)\s+\(review ({D_PATTERN})\)", exit_rule)
            valid_instrument = (instrument_exit and instrument_exit.group(1) in self.instruments
                                and instrument_exit.group(1) not in saturated[item.fields["Family"]])
            review = self.discoveries.get(structural_exit.group(2)) if structural_exit else None
            valid_structural = review and review.fields.get("Kind") == "direction-review"
            if not (valid_instrument or valid_structural):
                self.guard_issue("G3", "guard.family.saturated", item,
                                 f"family has {count} comparable results within resolution; record a Saturation exit",
                                 "Saturation exit")

    def check_direction(self, discoveries: list[Block], days: float) -> None:
        reviews = [d for d in discoveries if d.fields.get("Kind") == "direction-review"]
        all_reviews = sorted((d for d in self.discoveries.values() if d.fields.get("Kind") == "direction-review"),
                             key=lambda d: (self.record_day(d) or dt.date.min, d.line))
        latest = all_reviews[-1] if all_reviews else None
        day = self.record_day(latest) if latest else None
        paused = self.shared.get("Paused")
        pause_day = self.iso_day(paused) if paused is not None else None
        if paused is not None and (pause_day is None or pause_day > self.now.date()):
            self.guard_issue("GD", "guard.direction.pause.invalid", None,
                             "Paused must be YYYY-MM-DD on or before today", "Paused")
        if pause_day is None or pause_day > self.now.date():
            start = day or self.direction_start()
            due = dt.datetime.combine(start, dt.time()) + dt.timedelta(days=days)
            if self.now >= due:
                activation = self.direction_start()
                worked = any(event.key not in {"session", "none"}
                             and (event_day := self.record_day(event)) is not None
                             and activation <= event_day <= self.now.date() for event in self.events)
                severity = "INFO" if self.values.get("profile") in {"work", "research"} and not worked else "WARN"
                self.guard_issue("GD", "guard.direction.stale", latest,
                                 f"record a current direction review (due {due.date().isoformat()})",
                                 "Last direction review", severity)
            elif day is None:
                self.guard_issue("GD", "guard.direction.stale", None,
                                 f"first direction review due {due.date().isoformat()}",
                                 "Last direction review", "INFO")
        for review in reviews:
            required = ["Gap", "Decisions"]
            if self.values.get("profile") != "work":
                if all_reviews and review.key == all_reviews[0].key:
                    required.append("Data audit")
            full_parts = ["Decomposition", "Core families", "Intake", "Rejected consistent gains"]
            full = (self.values.get("profile") == "competition" or
                    rs.guard_thresholds(self.values["guard_thresholds"]).get("direction-parts") == "full")
            if full:
                required += full_parts

            def missing_parts(names: list[str]) -> list[str]:
                missing = []
                for name in names:
                    value = review.fields.get(name, "").strip()
                    if not value or (value.lower().startswith("not applicable") and
                                     not re.match(r"not applicable\s+—\s+\S", value, re.I)) or any(
                                         key not in self.discoveries for key in D_ID.findall(value)):
                        missing.append(name)
                return missing

            missing = missing_parts(required)
            if missing:
                self.guard_issue("GD", "guard.direction.incomplete", review,
                                 "direction review missing " + ", ".join(missing))
            if self.values.get("profile") == "research" and not full:
                optional_missing = missing_parts(full_parts)
                if optional_missing:
                    self.guard_issue("GD", "guard.direction.advice", review,
                                     "consider these direction-review parts when useful: " + ", ".join(optional_missing),
                                     light="INFO")

    @staticmethod
    def iso_day(value: str) -> dt.date | None:
        try:
            return dt.date.fromisoformat(value) if DATE.fullmatch(value) else None
        except ValueError:
            return None

    def direction_start(self) -> dt.date:
        since = rs.guard_since(self.values["guards"])
        started = self.iso_day(self.shared.get("Started", ""))
        if since or started:
            return since or started
        dates = [day for block in [*self.discoveries.values(), *self.events]
                 if (day := self.record_day(block)) is not None]
        # Older projects may predate activation dates; use their first record, then
        # the rules file's date only when no recorded project start is available.
        return min(dates) if dates else dt.datetime.fromtimestamp((self.root / "agents.md").stat().st_mtime).date()

    def check_phase(self, milestones: tuple[int, ...]) -> None:
        if self.values["phase_clock"] == "off":
            return
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", self.values["phase_clock"])
        start, end = (dt.datetime.combine(dt.date.fromisoformat(d), dt.time()) for d in dates)
        declarations = self.shared.get("Milestones", "")
        names = ("baseline", "core family", "freeze")
        for share, name in zip(milestones, names):
            state = re.search(rf"(?:^|;)\s*(?:{share}%?|{name})\s*[:=]?\s+([^;]*)", declarations, re.I)
            value = state.group(1).strip().lower() if state else None
            if value is not None and value not in {"pending", "blocked", "incomplete", "complete"}:
                self.guard_issue("G8", "guard.phase.state", None,
                                 f"{name} milestone state must be pending, blocked, incomplete, or complete", name)
            if self.now > start + (end - start) * share / 100 and value != "complete":
                self.guard_issue("G8", "guard.phase.milestone", None,
                                 f"{name} milestone at {share}% is not complete ({value or 'missing'})", name)

    def check_selection(self) -> None:
        picks = self.shared.get("Final picks", "")
        families: dict[str, int] = {}
        since = rs.guard_since(self.values["guards"])
        for key in dict.fromkeys(X_ID.findall(picks)):
            action = self.external_actions.get(key)
            day = self.record_day(action) if action else None
            if since and day and day < since:
                continue
            family = action.fields.get("Family") if action else None
            if not family or not family.strip():
                self.guard_issue("G11", "guard.selection.family", action,
                                 f"final pick {key} needs an existing action with Family", "Final picks", "ERROR")
            else:
                family = family.strip()
                families[family] = families.get(family, 0) + 1
        if any(n >= 2 for n in families.values()) and not re.search(r"rationale:\s*[^;)\s]", picks, re.I):
            self.guard_issue("G11", "guard.selection.rationale", None,
                             "same-family final picks need a rationale", "Final picks")

    def check_effort(self, events: list[Block], threshold: float) -> None:
        sessions: dict[str, list[Block]] = {}
        for event in events:
            session = event.fields.get("Session") or f"{event.owner} {event.heading_date[:10]}"
            sessions.setdefault(session, []).append(event)
        for session, records in sessions.items():
            tags = [e.fields.get("Effort", "unknown").lower() for e in records]
            overhead = sum(t in {"infra", "process"} for t in tags)
            unknown = sum(t not in {"infra", "process", "science", "research", "work"} for t in tags)
            share = 100 * overhead / len(tags)
            if share > threshold:
                self.guard_issue("G12", "guard.effort.share", records[0],
                                 f"session {session}: infra/process {share:.1f}%; unknown {unknown}/{len(tags)}",
                                 "Effort", "INFO")
            elif unknown:
                self.guard_issue("G12", "guard.effort.unknown", records[0],
                                 f"session {session}: unknown {unknown}/{len(tags)}; infra/process {share:.1f}%",
                                 "Effort", "INFO")

    @staticmethod
    def observed_stamp(value: str, verb: str = "observed") -> str | None:
        match = re.search(rf"\({verb} (\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}})\)", value)
        stamp = match.group(1) if match else None
        return stamp if stamp and parse_stamp(stamp) else None

    def check_external(self, actions: list[Block]) -> None:
        retries = external_retry_checks([(a.key, a.fields) for a in self.guard_records
                                         if a.section == "external actions"])
        active_ids = {action.key for action in actions}
        # Historical actions still establish identities; only active actions receive guard findings.
        for action in actions:
            fields = action.fields
            expected = fields.get("Expected", "")
            written = self.observed_stamp(expected, "written")
            result = fields.get("Result", "")
            observed = self.observed_stamp(result)
            if action.key in active_ids and (not re.fullmatch(
                    r"\S.*\s+\(written \d{4}-\d{2}-\d{2} \d{2}:\d{2}\)", expected)
                    or written is None or (result != "pending" and
                    (observed is None or written >= observed))):
                self.guard_issue("E1", "ext.expected", action,
                                 "Expected must be timestamped before the observed Result", "Expected")
            retry = fields.get("Retry of", "").strip()
            valid_retry, duplicate, _superseded = retries.get(action.key, (False, False, False))
            if action.key in active_ids and retry and not valid_retry:
                self.guard_issue("E1", "external.retry.invalid", action,
                                 "Retry of must name an earlier matching action without a reference cycle",
                                 "Retry of", "ERROR")
            if action.key in active_ids and duplicate and not valid_retry:
                self.guard_issue("E1", "ext.duplicate", action,
                                 "same hash and destination already recorded; declare Retry of the earlier action",
                                 "Retry of")

    # ---------- baseline ----------

    def baseline_fingerprints(self) -> list[str]:
        return sorted({issue.fingerprint for issue in self.issues if not issue.check.startswith("baseline.")})

    def update_baseline(self) -> Path:
        path = self.root / BASELINE
        data = {"version": 1, "created": self.now.strftime(STAMP), "fingerprints": self.baseline_fingerprints()}
        from ro_state import Project
        Project(self.root, require_slot=False).write_json(BASELINE.name, data)
        return path

    def compare_baseline(self) -> None:
        path = self.root / BASELINE
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = set(data["fingerprints"])
        except (ValueError, KeyError, TypeError):
            self.warn("baseline.unreadable", str(BASELINE), "the checker baseline cannot be read; rewrite it with "
                      "--baseline-update", "baseline")
            return
        new = [fp for fp in self.baseline_fingerprints() if fp not in known]
        if new:
            shown = ", ".join(new[:8]) + (", …" if len(new) > 8 else "")
            self.warn("baseline.new", str(BASELINE), f"{len(new)} new issue(s) since the baseline of "
                      f"{data.get('created', '?')}: {shown}", "baseline")

    # ---------- run ----------

    def run(self, quiet: bool = False, strict: bool = False, baseline_update: bool = False) -> int:
        files = {name: self.root / name for name in ("agents.md", "plan.md", "discoveries.md", "handoff.md")}
        missing = [name for name, path in files.items() if name not in self.proposed_files and not path.is_file()]
        if missing:
            if not quiet:
                print(f"CONSISTENCY: missing {', '.join(missing)} in {self.root}")
            return 2
        try:
            texts = {name: self.proposed_files[name] if name in self.proposed_files else
                     path.read_text(encoding="utf-8") for name, path in files.items()}
        except (OSError, UnicodeDecodeError) as exc:
            if not quiet:
                print(f"CONSISTENCY: cannot read the project files: {exc}")
            return 2
        if (self.root / rs.TRANSACTION).is_file():
            self.error("migration.unfinished", rs.TRANSACTION.as_posix(), "a workflow migration was interrupted and "
                       "the files may be half migrated; run init_research_orchestrator.py . --reconfigure, which "
                       "completes it (or restores the *.pre-migrate backups), then run this check again", "migration")
        self.check_settings(texts["agents.md"])
        self.check_project_rules(texts["agents.md"])
        self.parse_handoff(unfenced(texts["handoff.md"]))
        self.parse_plan(unfenced(texts["plan.md"]))
        self.parse_discoveries(unfenced(texts["discoveries.md"]))
        self.first_mention = self.discovery_first_mentions()
        self.check_plan_items()
        self.check_users_and_hosts()
        self.check_agents()
        self.check_handoff_sections()
        self.check_events()
        self.check_retired()
        self.check_plan_sources()
        self.check_claims()
        self.check_discoveries()
        self.check_current_best()
        self.check_compute()
        self.check_collection()
        self.check_open_issues()
        self.check_guards()
        if baseline_update:
            path = self.update_baseline()
            if not quiet:
                print(f"[BASELINE] {path} ({len(self.baseline_fingerprints())} fingerprints)")
        self.compare_baseline()
        errors = sum(issue.severity == "ERROR" for issue in self.issues)
        warnings = sum(issue.severity == "WARN" for issue in self.issues)
        code = 1 if errors or (strict and warnings) else 0
        if not quiet:
            self.report(errors, warnings)
        return code

    def discovery_first_mentions(self) -> dict[str, str]:
        first: dict[str, str] = {}
        for event in self.events:
            day = event.heading_date[:10]
            for name in ("Discovery updates", "Review verdict"):
                for disc_id in D_ID.findall(event.fields.get(name, "")):
                    if day and (disc_id not in first or day < first[disc_id]):
                        first[disc_id] = day
        return first

    def report(self, errors: int, warnings: int) -> None:
        infos = len(self.issues) - errors - warnings
        counts = (f"{len(self.plan_items)} plan items, {len(self.discoveries)} discoveries, {len(self.events)} events, "
                  f"workflow {self.values.get('workflow', '?')}, verification {self.values.get('verification', '?')}")
        if errors or warnings:
            print(f"CONSISTENCY: {errors} error(s), {warnings} warning(s), {infos} info ({counts})")
        else:
            print(f"CONSISTENCY: OK ({counts}" + (f"; {infos} info" if infos else "") + ")")
        ordered = sorted(enumerate(self.issues), key=lambda pair: (SEVERITY_ORDER[pair[1].severity], pair[0]))
        for _index, issue in ordered:
            if issue.check.startswith(("guard.", "ext.")) or issue.check in self.guard_checks:
                continue
            print(f"- {issue.render()}")
        # Keep the individual issues/fingerprints for baselines; cap only presentation.
        groups: dict[str, list[Issue]] = {}
        for _index, issue in ordered:
            if issue.check.startswith(("guard.", "ext.")) or issue.check in self.guard_checks:
                groups.setdefault(issue.check, []).append(issue)
        for check, issues in groups.items():
            examples = ", ".join(dict.fromkeys(i.record for i in issues))
            examples = ", ".join(examples.split(", ")[:3])
            print(f"- {issues[0].severity} {check}: {len(issues)} issue(s); examples: {examples}; "
                  f"{issues[0].message}")
        if errors or warnings:
            print("Fix issues tagged with your own agent; record others under 'Open consistency issues'.")


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Check that the four Research Orchestrator files agree.")
    parser.add_argument("target", nargs="?", default=".", help="Project directory")
    parser.add_argument("--strict", action="store_true", help="Fail (exit 1) on WARN as well as ERROR")
    parser.add_argument("--baseline-update", action="store_true",
                        help=f"Store the current fingerprints in {BASELINE.as_posix()}")
    args = parser.parse_args()
    return Checker(Path(args.target).resolve()).run(strict=args.strict, baseline_update=args.baseline_update)


if __name__ == "__main__":
    sys.exit(main())
