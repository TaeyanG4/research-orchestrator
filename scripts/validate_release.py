#!/usr/bin/env python3
"""Validate Research Orchestrator release consistency with only the Python stdlib."""

from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import string
import subprocess
import sys
import tempfile
import zipfile
from urllib.parse import unquote
from unittest.mock import patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.publication_safety import RAW_MEMBER, violations


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "research-orchestrator"
TEMPLATES = SKILL / "templates"
REFERENCES = SKILL / "references"
# The shipped process-start helper: console children open no window on Windows.
_PROC_SPEC = importlib.util.spec_from_file_location("_ro_proc_release", SKILL / "scripts" / "ro_proc.py")
_PROC = importlib.util.module_from_spec(_PROC_SPEC)
_PROC_SPEC.loader.exec_module(_PROC)
no_window_flags = _PROC.no_window_flags
SKILL_MAX_BYTES = 12_000
REFERENCE_MAX_BYTES = 10_000
REFERENCE_FILES = ("presets.md", "workflow-classic.md", "workflow-unified.md", "verification.md", "compute.md",
                   "git-sync.md", "plan-collector.md", "staged-items.md", "research-guards.md", "competition.md",
                   "adapters/kaggle.md", "postmortem.md", "hooks.md", "operations-safety.md", "migration-v2-to-v3.md")
PRESETS = ("quick", "work-project", "solo-research", "team-research", "competition-solo", "competition-team")
PRESET_FILE_KEYS = ["name", "summary", "profile", "workflow", "verification", "item_size", "guards", "enforcement",
                    "block", "platform_mode", "platforms", "collector", "queue_limits", "reviewer", "fallback", "asks"]

# Built from parts so this file does not match its own scan.
LEGACY_NAME = "context-" + "continuity"

AGENT_NAMES = {
    *string.ascii_uppercase,
    *(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase),
}
VERDICTS = {"CLOSED", "HOLD", "CHALLENGED"}
RESOLUTION_VERDICTS = {"CLOSED", "VERIFIED", "HOLD"}  # "<VERDICT> after challenge"
CROSS_CHECK_STATES = {"PENDING", "REVIEWING", "VERIFIED", "HOLD", "CHALLENGED"}
PLAN_RESOURCES = {"CPU", "GPU", "EITHER"}
HANDOFF_RESOURCES = {"CPU", "GPU", "Other", "none"}

PLAN_FIELDS = [
    "Sources", "Hypothesis", "Evidence", "Improvement",
    "Impact", "Information", "Confidence", "Unblock",
    "Diversity", "Cost", "Priority", "Resource",
    "Parallel", "Other", "Next test",
]
DISCOVERY_FIELDS = ["Source", "Host", "User", "Date", "Cross-check", "Finding", "Evidence", "Implication", "Reviews"]
# Staged items may designate important stages; changed stage events may cite a review artifact.
PLAN_SHAPES = [[*claimed, *PLAN_FIELDS, *stages] for claimed in ([], ["Claimed"])
               for stages in ([], ["Stages"], ["Stages", "Important stages"])]
WORK_PLAN_SHAPES = [[*claimed, goal, "Evidence", *routing, "Next test", *stages]
                    for claimed in ([], ["Claimed"]) for goal in ("Hypothesis", "Goal")
                    for routing in ([], ["Resource"]) for stages in ([], ["Stages"], ["Stages", "Important stages"])]
DISCOVERY_SHAPES = [DISCOVERY_FIELDS, [*DISCOVERY_FIELDS[:4], "Session", *DISCOVERY_FIELDS[4:]]]
HANDOFF_FIELDS = [
    "Host", "User", "Action", "Result", "Artifacts", "Discovery updates",
    "Review verdict", "Resource", "Other executor", "New plan items",
]

READMES = {
    "README.md": "English",
    "README.ko.md": "한국어",
    "README.zh-CN.md": "简体中文",
    "README.ja.md": "日本語",
}
EXAMPLE = ROOT / "examples" / "team-research-cv-leakage"
# Must match how the example was generated.
EXAMPLE_INIT_ARGS = ["-n", "Aster customer overlap study", "--preset", "team-research",
                     "--user", "mira", "--agents", "3", "--platforms", "Lumen, Prism",
                     "--environment", "linux/bash", "--git", "off", "--guards", "light since 2026-10-23"]

DOCS = [
    *(ROOT / name for name in READMES),
    SKILL / "SKILL.md",
    TEMPLATES / "AGENTS.md.template",
    TEMPLATES / "PLAN.md.template",
    TEMPLATES / "DISCOVERIES.md.template",
    TEMPLATES / "HANDOFF.md.template",
    *sorted(REFERENCES.rglob("*.md")),
]

FIELD_LINE = re.compile(r"^- ([A-Za-z/ -]+):(.*)$")
REVIEW_LINE = re.compile(r"^\s+- (.+?) \((\S+)\): (\S+)( after challenge)? — (.*)$")
PLAN_HEAD = re.compile(r"^### (H-\S+) — ")
DISCOVERY_HEAD = re.compile(r"^## (D-\S+) — ")
HANDOFF_HEAD = re.compile(r"^### (?:YYYY-MM-DD HH:MM|\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — (\S+) — ")
SECTION_HEAD = re.compile(r"^#{2,3} Agent: (\S+)")
ID_NEW = re.compile(r"\b([HD])-([A-Za-z]+)-(\d+)\b")
ID_OLD = re.compile(r"\b[HD]-[A-Za-z]?\d+\b")
AGENT_PROSE = re.compile(r"\bAgent (?:Main|[A-Z]{1,2})\b")
NEW_ITEMS_IDS = re.compile(r"^H-[A-Za-z]+-\d{2}(?:, H-[A-Za-z]+-\d{2})*$")

# Domain-specific vocabulary belongs in specialized references and examples, not general instructions.
DOMAIN_VOCABULARY = re.compile(
    r"\b(?:leaderboards?|kaggle|labels?|folds?|submissions?|cross[- ]validation|hyperparameters?|"
    r"ensembles?|pre[- ]?trained|oof|groupkfold|kfold|training|inference|boosting)\b", re.I)
ADAPTER_POINTER = re.compile(r"(?:references/)?adapters/[A-Za-z0-9_.-]+\.md")
VOCABULARY_SUFFIXES = {".md", ".template"}


def vocabulary_paths(root: Path):
    """Keep general instructions domain-neutral; domain evidence and executable schemas use their own words."""
    skill = root / "skills" / "research-orchestrator"
    yield skill / "SKILL.md"
    for directory in (skill / "templates", skill / "references"):
        for path in directory.rglob("*"):
            relative = path.relative_to(directory)
            if ((directory.name == "templates" and re.fullmatch(r"v\d+(?:\.\d+)*", relative.parts[0]))
                    or path.is_relative_to(skill / "references" / "adapters")
                    or path == skill / "references" / "competition.md"):
                continue
            yield path


def check_vocabulary(errors: list[str], root: Path = ROOT) -> None:
    """Check general instructions; only competition guidance and adapters are domain-specific."""
    for path in sorted(vocabulary_paths(root)):
        if not path.is_file() or path.suffix.lower() not in VOCABULARY_SUFFIXES:
            continue
        for line_number, prose in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            prose = ADAPTER_POINTER.sub("<adapter-reference>", prose)
            terms = sorted({match.group(0).lower() for match in DOMAIN_VOCABULARY.finditer(prose)})
            if terms:
                errors.append(f"vocabulary: {path.relative_to(root)}:{line_number}: " + ", ".join(terms))


def check_release_receipt(errors: list[str], root: Path = ROOT) -> None:
    """Require the coordinator's completed local receipt only at publication time."""
    if os.environ.get("RO_RELEASE_RECEIPT_REQUIRED") != "1":
        return
    path = root / "docs" / "evals" / "README.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    section = re.search(r"^## Release candidate test receipt\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    rows = re.findall(r"^\|([^\n]+)\|\s*$", section[1], re.M) if section else []
    fields = [field.strip().strip("`") for field in rows[-1].split("|")] if rows else []
    if (len(rows) != 3 or len(fields) != 5 or any(not field for field in fields)
            or any(re.search(r"<[^>]+>", field) for field in fields)
            or any(re.fullmatch(r"[-: ]+", field) for field in fields)):
        errors.append("release receipt: docs/evals/README.md needs a completed Release candidate test receipt "
                      "(date, interpreter, pytest summary, validate_release result, commit)")


def blocks(lines: list[str], head: re.Pattern[str]):
    """Yield (heading match, field lines) for each block starting with `head`."""
    for i, line in enumerate(lines):
        match = head.match(line)
        if not match:
            continue
        fields = []
        for follow in lines[i + 1:]:
            if follow.startswith("- ") or follow.startswith("  - "):
                fields.append(follow)
            else:
                break
        yield match, fields


def field_names(fields: list[str]) -> list[str]:
    return [m.group(1) for line in fields if (m := FIELD_LINE.match(line))]


def field_value(fields: list[str], name: str) -> str | None:
    for line in fields:
        match = FIELD_LINE.match(line)
        if match and match.group(1) == name:
            return match.group(2).strip()
    return None


def check_resource(value: str | None, allowed: set[str], where: str, errors: list[str]) -> None:
    if value is None:
        return
    tokens = {token.strip() for token in value.split("|")}
    if not tokens <= allowed:
        errors.append(f"{where}: Resource '{value}' uses values outside {sorted(allowed)}")


def check_priority(fields: list[str], where: str, errors: list[str]) -> None:
    """When every factor is a concrete score, Priority must match the formula."""
    names = ["Impact", "Information", "Confidence", "Unblock", "Diversity", "Cost", "Priority"]
    values = [field_value(fields, name) or "" for name in names]
    if not all(value.isdigit() for value in values):
        return
    impact, information, confidence, unblock, diversity, cost, priority = map(int, values)
    if any(score > 3 for score in (impact, information, confidence, unblock, diversity, cost)):
        errors.append(f"{where}: scores must be 0-3")
    expected = 2 * impact + 2 * information + confidence + unblock + diversity + (3 - cost)
    if priority != expected:
        errors.append(f"{where}: Priority {priority} != formula result {expected}")


def check_doc(path: Path, errors: list[str]) -> None:
    rel = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if path.suffix == ".template":
        lines = [line for line in lines if not re.fullmatch(r"\{\{(?:#if \w+=[\w,-]+|/if)\}\}", line)]

    for match, fields in blocks(lines, PLAN_HEAD):
        where = f"{rel}: {match.group(1)}"
        if field_names(fields) not in [*PLAN_SHAPES, *WORK_PLAN_SHAPES]:
            errors.append(f"{where}: PLAN fields {field_names(fields)} match no accepted shape of {PLAN_FIELDS}")
        check_resource(field_value(fields, "Resource"), PLAN_RESOURCES, where, errors)
        check_priority(fields, where, errors)

    for match, fields in blocks(lines, DISCOVERY_HEAD):
        where = f"{rel}: {match.group(1)}"
        compact_self = (path.name == "DISCOVERIES.md.template" and field_names(fields) ==
                        [name for name in DISCOVERY_FIELDS if name not in {"Cross-check", "Reviews"}])
        if field_names(fields) not in DISCOVERY_SHAPES and not compact_self:
            errors.append(f"{where}: DISCOVERIES fields {field_names(fields)} != {DISCOVERY_FIELDS} (+ optional Session)")
        source = field_value(fields, "Source")
        if source not in AGENT_NAMES:
            errors.append(f"{where}: Source '{source}' is not a standard agent name")
        host = field_value(fields, "Host")
        if not host or host in AGENT_NAMES:
            errors.append(f"{where}: Host '{host}' must name the host, not an agent slot")
        state = (field_value(fields, "Cross-check") or ("PENDING" if compact_self else "")).split(" ", 1)[0]
        if state not in CROSS_CHECK_STATES:
            errors.append(f"{where}: Cross-check '{state}' not in {sorted(CROSS_CHECK_STATES)}")
        verdicts: list[str] = []
        for line in fields[fields.index("- Reviews:") + 1:] if "- Reviews:" in fields else []:
            review = REVIEW_LINE.match(line)
            if not review:
                errors.append(f"{where}: review line must be '<Host> (<Agent>): <VERDICT> — reason': {line.strip()}")
                continue
            reviewer_host, agent, verdict, resolves, reason = review.groups()
            if resolves:
                verdicts += ["RESOLVED", "CLOSED" if verdict in {"CLOSED", "VERIFIED"} else verdict]
            else:
                verdicts.append(verdict)
            if agent not in AGENT_NAMES:
                errors.append(f"{where}: reviewer agent '{agent}' is not a standard agent name")
            if verdict not in (RESOLUTION_VERDICTS if resolves else VERDICTS):
                errors.append(f"{where}: verdict '{verdict}' not in {sorted(VERDICTS)}")
            # A same-host review is marked "same host —" (cross-host-once) or names an independent reviewer.
            if reviewer_host == host and not (reason.startswith("same host —") or reason.startswith("reviewer ")):
                errors.append(f"{where}: {reviewer_host} reviewed its own host's discovery")
        # A settled state must be backed by a review carrying the matching verdict.
        needs = {"VERIFIED": "CLOSED", "HOLD": "HOLD", "CHALLENGED": "CHALLENGED"}
        if state in needs and needs[state] not in verdicts:
            errors.append(f"{where}: Cross-check '{state}' has no '{needs[state]}' review line")
        last = {name: max((i for i, v in enumerate(verdicts) if v == name), default=-1) for name in ("CHALLENGED", "RESOLVED")}
        standing = last["CHALLENGED"] > last["RESOLVED"]
        if state in {"VERIFIED", "HOLD"} and standing:
            errors.append(f"{where}: Cross-check must stay CHALLENGED while a CHALLENGED review stands")

    for match, fields in blocks(lines, HANDOFF_HEAD):
        where = f"{rel}: handoff event by {match.group(1)}"
        if match.group(1) not in AGENT_NAMES:
            errors.append(f"{where}: '{match.group(1)}' is not a standard agent name")
        names = field_names(fields)
        session = match.string.endswith(" — session")
        session_order = [*HANDOFF_FIELDS, "Completed", "Decision", "Review artifact"]
        compact = (session and {"Host", "User", "Action", "Result", "Completed"} <= set(names)
                   and names == [name for name in session_order if name in names])
        if not compact and names not in (HANDOFF_FIELDS, [*HANDOFF_FIELDS, "Decision"],
                                         [*HANDOFF_FIELDS, "Decision", "Review artifact"]):
            errors.append(f"{where}: HANDOFF fields {field_names(fields)} != {HANDOFF_FIELDS}")
        if not session or "Resource" in names:
            check_resource(field_value(fields, "Resource"), HANDOFF_RESOURCES, where, errors)
        # Real events (not the YYYY-MM-DD format sample) must list IDs or justify zero follow-ups.
        if not match.group(0).startswith("### YYYY"):
            new_items = field_value(fields, "New plan items") or ""
            if (not session or "New plan items" in names) and not (
                    NEW_ITEMS_IDS.match(new_items) or new_items.startswith("none — ")):
                errors.append(f"{where}: New plan items '{new_items}' must list H- IDs or read 'none — <reason>'")
            updates = field_value(fields, "Discovery updates") or ""
            if (not session or "Discovery updates" in names) and not (
                    updates.startswith("D-") or updates.startswith("none — ")):
                errors.append(f"{where}: Discovery updates '{updates}' must list D- IDs or read 'none — <reason>'")

    for line in lines:
        section = SECTION_HEAD.match(line)
        if section and section.group(1) not in AGENT_NAMES:
            errors.append(f"{rel}: section agent '{section.group(1)}' is not a standard agent name")

    for match in ID_NEW.finditer(text):
        kind, agent, number = match.groups()
        width = 2 if kind == "H" else 3
        if agent not in AGENT_NAMES or len(number) != width:
            errors.append(f"{rel}: ID '{match.group(0)}' should be {kind}-<Agent>-{'N' * width}")
    for match in ID_OLD.finditer(text):
        errors.append(f"{rel}: legacy ID format '{match.group(0)}'")
    for match in AGENT_PROSE.finditer(text):
        errors.append(f"{rel}: write '{match.group(0)[6:]}' instead of '{match.group(0)}'")
    if re.search(r"\bMain\b", text):
        errors.append(f"{rel}: the Main slot was removed; slots start at A")


def check_frontmatter(errors: list[str]) -> None:
    lines = (SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        errors.append("SKILL.md: missing frontmatter")
        return
    body = lines[1:lines.index("---", 1)]
    keys = [line.split(":", 1)[0] for line in body if line and not line.startswith(" ")]
    if keys != ["name", "description"]:
        errors.append(f"SKILL.md: frontmatter keys {keys} != ['name', 'description']")
    name_line = next((line for line in body if line.startswith("name:")), "")
    if name_line.split(":", 1)[-1].strip() != SKILL.name:
        errors.append(f"SKILL.md: name must equal directory name '{SKILL.name}'")


def check_manifests(errors: list[str]) -> None:
    manifests = {
        "plugin.json": ("version",),
        ".codex-plugin/plugin.json": ("version",),
        ".claude-plugin/plugin.json": ("version",),
        ".claude-plugin/marketplace.json": ("metadata", "version"),
        ".agents/plugins/marketplace.json": None,
    }
    versions = {}
    for rel, version_key in manifests.items():
        try:
            data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON: {rel}: {exc}")
            continue
        if version_key:
            value = data
            for key in version_key:
                value = value.get(key, {}) if isinstance(value, dict) else {}
            versions[rel] = value
    if len(set(map(str, versions.values()))) > 1:
        errors.append(f"manifest versions differ: {versions}")

    openai_yaml = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    for required in (
        "short_description: Coordinate work projects, research, and competitions",
        "- CHAT",
        "- CODEX",
        'brand_color: "#1687D9"',
    ):
        if required not in openai_yaml:
            errors.append(f"openai.yaml missing expected metadata: {required}")


def check_legacy_name(errors: list[str]) -> None:
    text_suffixes = {".md", ".json", ".yaml", ".yml", ".py", ".template", ".svg"}
    for path in ROOT.rglob("*"):
        if ".git" in path.relative_to(ROOT).parts:
            continue
        if path.is_file() and path.suffix.lower() in text_suffixes:
            if LEGACY_NAME in path.read_text(encoding="utf-8", errors="ignore"):
                errors.append(f"legacy name remains: {path.relative_to(ROOT)}")


def readme_shape(text: str) -> tuple[int, int, list[str]]:
    """Structure that every translation must share with the English README."""
    images = re.findall(r'<img[^>]+src="([^"]+)"', text)
    return text.count("```"), len(re.findall(r"```mermaid", text)), images


def check_readmes(errors: list[str]) -> None:
    english_shape = readme_shape((ROOT / "README.md").read_text(encoding="utf-8"))
    for name, label in READMES.items():
        text = (ROOT / name).read_text(encoding="utf-8")

        # Language switcher: own language in bold, every other README linked.
        if f"<b>{label}</b>" not in text:
            errors.append(f"{name}: language switcher must show <b>{label}</b>")
        for other in READMES:
            if other != name and f'href="{other}"' not in text:
                errors.append(f"{name}: language switcher is missing a link to {other}")

        if name != "README.md" and readme_shape(text) != english_shape:
            errors.append(f"{name}: code blocks, diagrams, or images differ from README.md")

        # Every relative link and image must exist.
        refs = re.findall(r'(?:src|href)="([^"]+)"|\]\(([^)\s]+)\)', text)
        for ref in refs:
            target = next(part for part in ref if part).split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            path = ROOT / target
            if not path.exists():
                errors.append(f"{name}: broken link {target}")
            elif path.suffix == ".svg":
                try:
                    ElementTree.parse(path)
                except ElementTree.ParseError as exc:
                    errors.append(f"{name}: invalid SVG {target}: {exc}")


def check_readme_headings(errors: list[str]) -> None:
    """Compare heading levels in order, ignoring headings inside fenced code blocks."""
    structures = {}
    for name in READMES:
        levels = []
        fence = ""
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if fence:
                if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*", line):
                    fence = ""
                continue
            opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            heading = re.match(r"^ {0,3}(#{1,6})(?:[ \t]+|$)", line)
            if opening:
                fence = opening.group(1)
            elif heading:
                levels.append(len(heading.group(1)))
        structures[name] = levels
    for name, levels in structures.items():
        if levels != structures["README.md"]:
            errors.append(f"{name}: heading structure differs from README.md")


def markdown_prose(text: str) -> str:
    """Ignore fenced examples when checking rendered links and heading anchors."""
    lines, fence = [], ""
    for line in text.splitlines():
        if fence:
            if re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*", line):
                fence = ""
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if opening:
            fence = opening[1]
        else:
            lines.append(line)
    return "\n".join(lines)


def markdown_anchors(text: str) -> set[str]:
    """GitHub-style heading slugs, including duplicate headings and explicit IDs."""
    prose = markdown_prose(text)
    anchors = set(re.findall(r'(?:id|name)=[\"\']([^\"\']+)[\"\']', prose))
    used = set()
    for heading in re.findall(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", prose, re.M):
        heading = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", heading)
        heading = re.sub(r"<[^>]+>", "", heading).lower()
        base = re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")
        slug, number = base, 0
        while slug in used:
            number += 1
            slug = f"{base}-{number}"
        used.add(slug)
        anchors.add(slug)
    return anchors


def check_local_links(errors: list[str], root: Path = ROOT) -> None:
    """Validate public Markdown destinations and anchors without following external URLs."""
    root = root.resolve()
    paths = [*root.glob("*.md"), *(root / "docs").rglob("*.md"),
             *(root / "skills" / "research-orchestrator").glob("SKILL.md"),
             *(root / "skills" / "research-orchestrator" / "references").rglob("*.md")]
    anchors = {}
    for source in paths:
        prose = markdown_prose(source.read_text(encoding="utf-8"))
        for match in re.finditer(r'\]\(([^)\s]+)\)|(?:href|src)="([^"]+)"', prose):
            link = unquote(match[1] or match[2])
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("//"):
                continue
            target, _, fragment = link.partition("#")
            destination = (source.parent / target).resolve() if target else source
            label = source.relative_to(root).as_posix()
            if not destination.is_relative_to(root) or not destination.exists():
                errors.append(f"{label}: broken local link {link}")
            elif fragment and destination.suffix == ".md":
                if destination not in anchors:
                    anchors[destination] = markdown_anchors(destination.read_text(encoding="utf-8"))
                if fragment not in anchors[destination]:
                    errors.append(f"{label}: broken local anchor {link}")


def run_checker(target: Path) -> subprocess.CompletedProcess[str]:
    checker = SKILL / "scripts" / "check_project.py"
    return subprocess.run([sys.executable, str(checker), str(target)], text=True,
                          capture_output=True, encoding="utf-8", errors="replace", creationflags=no_window_flags())


def check_example(errors: list[str]) -> None:
    """The worked example must match the current template and pass the consistency checker."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".git").mkdir()  # git sync needs a repository; otherwise it is switched off
        result = run_init(Path(tmp), *EXAMPLE_INIT_ARGS, name=None)
        if result.returncode != 0:
            errors.append(f"example: initializer failed: {result.stderr.strip()}")
            return
        expected = (Path(tmp) / "agents.md").read_text(encoding="utf-8")
        fresh = run_checker(Path(tmp))
        if fresh.returncode != 0:
            errors.append("check_project.py fails on a freshly initialized project:\n" + fresh.stdout.strip())
    stored = (EXAMPLE / "agents.md").read_text(encoding="utf-8")
    if stored != expected:
        errors.append("examples/team-research-cv-leakage/agents.md is out of date with AGENTS.md.template")
    example = run_checker(EXAMPLE)
    if example.returncode != 0:
        errors.append("check_project.py fails on the worked example:\n" + example.stdout.strip())


def check_examples(errors: list[str], root: Path = ROOT) -> None:
    """Every shipped example must pass the checker without any findings."""
    for example in sorted((root / "examples").glob("*")):
        if not example.is_dir():
            continue
        result = subprocess.run(
            [sys.executable, str(SKILL / "scripts" / "check_project.py"), str(example), "--strict"],
            text=True, capture_output=True, encoding="utf-8", errors="replace", creationflags=no_window_flags(),
        )
        if result.returncode != 0 or re.search(r"^(?:- )?(?:ERROR|WARN|INFO) ", result.stdout, re.M):
            errors.append(f"{example.relative_to(root).as_posix()}: check_project.py --strict failed:\n"
                          + (result.stdout + result.stderr).strip())


def run_init(target: Path, *args: str, name: str | None = "Validation Project",
             without_repository: bool = False) -> subprocess.CompletedProcess[str]:
    initializer = SKILL / "scripts" / "init_research_orchestrator.py"
    name_args = ["-n", name] if name else []
    if without_repository:
        # A temporary directory may be inside this checkout. Model only the absent .git entries;
        # exercise the real detection, settings and writes without depending on temporary placement.
        sys.path.insert(0, str(initializer.parent))
        import init_research_orchestrator as init

        stdout, stderr = io.StringIO(), io.StringIO()
        real_exists = Path.exists
        with (patch.object(Path, "exists", lambda path: path.name != ".git" and real_exists(path)),
              contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr)):
            code = init.main([str(target), *name_args, *args])
        return subprocess.CompletedProcess([str(initializer), str(target), *name_args, *args], code,
                                           stdout.getvalue(), stderr.getvalue())
    return subprocess.run(
        [sys.executable, str(initializer), str(target), *name_args, *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        creationflags=no_window_flags(),
    )


def check_initializer(errors: list[str]) -> None:
    outputs = ["agents.md", "plan.md", "discoveries.md", "handoff.md"]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".git").mkdir()
        cases = {"default": ([], ["A"]), "count": (["--agents", "3"], ["A", "B", "C"]),
                 "list": (["--agents", "a, b, aa"], ["A", "B", "AA"])}
        for label, (args, expected) in cases.items():
            target = Path(tmp) / label
            target.mkdir()
            result = run_init(target, *args)
            if result.returncode != 0:
                errors.append(f"initializer ({label}) failed: {result.stderr.strip()}")
                continue
            for name in outputs:
                path = target / name
                if not path.exists():
                    errors.append(f"initializer ({label}) did not create {name}")
                    continue
                raw = path.read_bytes()
                if b"{{" in raw:
                    errors.append(f"initializer ({label}) left a placeholder in {name}")
                if b"\r\n" in raw:
                    errors.append(f"initializer ({label}) wrote CRLF line endings in {name}")
            plan = (target / "plan.md").read_text(encoding="utf-8")
            sections = re.findall(r"^## Agent: (\S+)", plan, flags=re.M)
            if sections != expected:
                errors.append(f"initializer ({label}) plan sections {sections} != {expected}")

        target = Path(tmp) / "default"
        plan = target / "plan.md"
        with plan.open("a", encoding="utf-8") as handle:
            handle.write("\nKEEP-ME\n")
        if run_init(target).returncode != 0 or "KEEP-ME" not in plan.read_text(encoding="utf-8"):
            errors.append("initializer overwrote existing plan.md")

        for bad in ("A,A", "Claude", "A,Codex", "Main", "AAA", "0"):
            target = Path(tmp) / f"bad-{len(list(Path(tmp).iterdir()))}"
            target.mkdir()
            result = run_init(target, "--agents", bad)
            if result.returncode == 0 or any(target.iterdir()):
                errors.append(f"initializer accepted invalid --agents '{bad}'")

        bad_settings = {
            "user with a space": ["--user", "kim lee"],
            "user named like a slot": ["--user", "B"],
            "user named like a host": ["--user", "Codex"],
            "single with two platforms": ["--platform", "single", "--platforms", "Claude Code, Codex"],
            "multi with one platform": ["--platform", "multi", "--platforms", "Codex"],
            "unknown git mode": ["--git", "sometimes"],
            "unknown platform mode": ["--platform", "both"],
            "collector on a platform not listed": ["--platforms", "Claude Code, Codex", "--collector", "Gemini/pro"],
            "collector without a model": ["--collector", "Claude Code"],
            "reviewer on a platform not listed": ["--platform", "single", "--platforms", "Codex", "--reviewer", "Claude Code/opus"],
            "queue limits with resume >= stop": ["--queue-limits", "5,50"],
            "unknown fallback": ["--fallback", "sometimes"],
            "unknown preset": ["--preset", "nope"],
            "unknown workflow": ["--workflow", "both"],
            "unknown verification": ["--verification", "maybe"],
            "phase clock ending before it starts": ["--phase-clock", "2026-12-01,2026-10-01"],
            "competition without a slug": ["--competition", "no-slug"],
        }
        for label, args in bad_settings.items():
            target = Path(tmp) / f"bad-{len(list(Path(tmp).iterdir()))}"
            target.mkdir()
            result = run_init(target, *args)
            if result.returncode == 0 or any(target.iterdir()):
                errors.append(f"initializer accepted invalid settings ({label})")


def check_settings_modes(errors: list[str]) -> None:
    """Every platform/git combination renders cleanly and passes the checker; --reconfigure is safe."""
    combos = [("single", "Claude Code"), ("multi", "Claude Code, Codex"), ("adaptive", "Claude Code, Codex")]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".git").mkdir()
        for mode, platforms in combos:
            for git in ("push", "commit", "off"):
                target = Path(tmp) / f"{mode}-{git}"
                target.mkdir()
                result = run_init(target, "--user", "kim", "--profile", "research",
                                  "--platform", mode, "--platforms", platforms, "--git", git)
                if result.returncode != 0:
                    errors.append(f"initializer ({mode}/{git}) failed: {result.stderr.strip()}")
                    continue
                agents = (target / "agents.md").read_text(encoding="utf-8")
                if "{{" in agents or "\n\n\n" in agents:
                    errors.append(f"agents.md ({mode}/{git}) has leftover template markers or blank-line runs")
                if "core's operation table" not in agents or "references/workflow-classic.md" in agents:
                    errors.append(f"agents.md ({mode}) must delegate default workflow guidance to the core")
                if ("references/git-sync.md" in agents) != (git != "off"):
                    errors.append(f"agents.md ({mode}/{git}) has incorrect active git reading guidance")
                if ((f"- Platforms: single — {platforms}" if mode == "single" else f"- Platform mode: {mode}")
                        not in agents or f"- Git sync: {git}" not in agents):
                    errors.append(f"agents.md ({mode}/{git}) does not record its settings")
                checked = run_checker(target)
                if checked.returncode != 0:
                    errors.append(f"check_project.py fails on a fresh {mode}/{git} project:\n" + checked.stdout.strip())

        target = Path(tmp) / "single-off"
        result = run_init(target, "--reconfigure", "--platform", "multi", "--platforms", "Claude Code, Codex",
                          "--git", "push", name=None)
        agents = (target / "agents.md").read_text(encoding="utf-8")
        if result.returncode != 0 or "- Platform mode: multi" not in agents or "- Git sync: push" not in agents:
            errors.append(f"--reconfigure did not switch single/off to multi/push: {result.stderr.strip()}")
        agents_md = target / "agents.md"
        with agents_md.open("a", encoding="utf-8") as handle:
            handle.write("\n- PROJECT-RULE kept verbatim\n")  # inside the user-owned ## Project rules region
        kept = run_init(target, "--reconfigure", "--git", "commit", name=None)
        if kept.returncode != 0 or "- PROJECT-RULE kept verbatim\n" not in agents_md.read_text(encoding="utf-8"):
            errors.append("--reconfigure did not keep the ## Project rules region verbatim")
        text = agents_md.read_text(encoding="utf-8")
        agents_md.write_text(text.replace("\n## Project rules\n", "\nHAND-EDIT\n\n## Project rules\n", 1),
                             encoding="utf-8", newline="\n")
        refused = run_init(target, "--reconfigure", "--git", "off", name=None)
        if refused.returncode == 0 or "HAND-EDIT" not in agents_md.read_text(encoding="utf-8"):
            errors.append("--reconfigure overwrote a hand-edited agents.md without --force")
        forced = run_init(target, "--reconfigure", "--git", "off", "--force", name=None)
        text = agents_md.read_text(encoding="utf-8")
        if (forced.returncode != 0 or "- Git sync: off" not in text or "HAND-EDIT" in text
                or "- PROJECT-RULE kept verbatim\n" not in text):
            errors.append("--reconfigure --force did not rewrite the generated part and keep ## Project rules")

        # Direct edits: runtime settings apply at once; mode/git edits are applied by --reconfigure.
        target = Path(tmp) / "multi-push"
        agents_md = target / "agents.md"
        text = agents_md.read_text(encoding="utf-8")
        text = text.replace("- Plan collector: off", "- Plan collector: on — Codex / sol")
        text = text.replace("- Platform mode: multi", "- Platform mode: single").replace(
            "- Platforms: Claude Code, Codex", "- Platforms: Codex")
        agents_md.write_text(text, encoding="utf-8", newline="\n")
        stale = run_checker(target)
        if "agents.rules.stale" not in stale.stdout:
            errors.append("check_project.py did not note rules that are out of sync with edited settings")
        applied = run_init(target, "--reconfigure", name=None)
        text = agents_md.read_text(encoding="utf-8")
        if (applied.returncode != 0 or "references/plan-collector.md" not in text
                or "- Plan collector: on — Codex / sol" not in text or "- Platforms: single — Codex" not in text):
            errors.append(f"--reconfigure did not apply directly edited settings: {applied.stderr.strip()}")
        if run_checker(target).returncode != 0:
            errors.append("check_project.py fails after applying directly edited settings")

    # Outside a git repository, git sync is reported and switched off; nothing is created.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "no-repo"
        target.mkdir()
        result = run_init(target, "--git", "push", without_repository=True)
        agents = (target / "agents.md").read_text(encoding="utf-8") if (target / "agents.md").exists() else ""
        if result.returncode != 0 or "- Git sync: off" not in agents or "not inside a git repository" not in result.stderr:
            errors.append("initializer outside a git repository must switch Git sync to off and say so")
        if any(p.name == ".git" for p in Path(tmp).rglob(".git")):
            errors.append("initializer created a git repository; it must never run git init")
        again = run_init(target, "--reconfigure", "--git", "commit", name=None, without_repository=True)
        if again.returncode != 0 or "- Git sync: off" not in (target / "agents.md").read_text(encoding="utf-8"):
            errors.append("--reconfigure outside a git repository must keep Git sync off")


def check_core_split(errors: list[str], skill: Path = SKILL) -> None:
    """Enforce byte budgets and follow actual local links from the core to every reference."""
    core = skill / "SKILL.md"
    references = skill / "references"
    # Budgets count the published (LF) bytes, so a CRLF checkout on Windows does not change the result.
    size = len(core.read_bytes().replace(b"\r\n", b"\n"))
    if size > SKILL_MAX_BYTES:
        errors.append(f"SKILL.md is {size} bytes; the budget is {SKILL_MAX_BYTES}")
    for name in REFERENCE_FILES:
        if not (references / name).is_file():
            errors.append(f"references/{name} is missing")

    paths = sorted(path for path in references.rglob("*") if path.is_file())
    for path in paths:
        size = len(path.read_bytes().replace(b"\r\n", b"\n"))
        if size > REFERENCE_MAX_BYTES:
            errors.append(f"{path.relative_to(skill).as_posix()} is {size} bytes; the budget is {REFERENCE_MAX_BYTES}")

    allowed = {core.resolve(), *(path.resolve() for path in paths)}
    visited = set()
    pending = [core.resolve()]
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        if path.suffix != ".md":
            continue
        for link in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            target = link.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            destination = (path.parent / target).resolve()
            if not destination.is_relative_to(skill.resolve()):
                errors.append(f"{path.relative_to(skill.resolve()).as_posix()}: link leaves installed skill {target}")
            elif not destination.is_file():
                errors.append(f"{path.relative_to(skill.resolve()).as_posix()}: broken link {target}")
            elif destination in allowed:
                pending.append(destination)
    for path in paths:
        if path.resolve() not in visited:
            errors.append(f"{path.relative_to(skill).as_posix()} is not reachable from SKILL.md")


def check_presets(errors: list[str]) -> None:
    """Built-in presets list every preset-covered key; --list-presets shows each of them."""
    found = sorted(path.stem for path in (SKILL / "presets").glob("*.json"))
    if found != sorted(PRESETS):
        errors.append(f"presets/ holds {found}, expected {sorted(PRESETS)} (custom is the absence of a preset)")
    for name in PRESETS:
        path = SKILL / "presets" / f"{name}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"presets/{name}.json: {exc}")
            continue
        expected = PRESET_FILE_KEYS.copy()
        if name.startswith("competition-"):
            expected.insert(expected.index("verification") + 1, "receipt_policy")
        if list(data) != expected:
            errors.append(f"presets/{name}.json keys {list(data)} != {expected}")
    listed = run_init(ROOT, "--list-presets", name=None)
    for name in PRESETS:
        if listed.returncode != 0 or not any(line.startswith(name + " ") for line in listed.stdout.splitlines()):
            errors.append(f"--list-presets does not list {name}")


def check_tests(errors: list[str]) -> str:
    """Run deterministic pytest checks; CI measures latency in a separate step."""
    try:
        import pytest  # noqa: F401
    except ImportError:
        errors.append("pytest is not installed; the test suite in tests/ cannot run")
        return ""
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not latency", str(ROOT / "tests")],
                            cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace",
                            creationflags=no_window_flags())
    summary = (result.stdout.strip().splitlines() or [""])[-1]
    if result.returncode != 0:
        # List every failing test id (a long tail alone hides most failures on another OS).
        failing = [line for line in result.stdout.splitlines() if line.startswith(("FAILED ", "ERROR "))]
        errors.append("pytest failed:\n" + "\n".join(failing) + "\n" + result.stdout.strip()[-3000:])
    return summary


def check_publication(errors: list[str], root: Path = ROOT, *, private_names: tuple[str, ...] = ()) -> None:
    """Inspect the bytes actually distributed, including every archive member."""
    from scripts.evals.export_evidence import verify_evidence
    from scripts.publication_safety import expanded_text
    def decoded_strings(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from decoded_strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from decoded_strings(child)
        elif isinstance(value, str):
            yield value

    def decode_block(match):
        try:
            return "\n".join(decoded_strings(json.loads(match[1])))
        except ValueError:
            return match[0]

    def internal_report(name: str, text: str = "") -> bool:
        # Public evidence tables are useful; prompts and agent-session narratives
        # belong in the private archive even when their machine paths are scrubbed.
        stem = Path(name).stem.lower()
        tokens = set(re.split(r"[-_ .]+", stem))
        named = (bool(tokens & {"prompt", "prompts"}) or
                 ("reviews" in Path(name).parts and bool(tokens & {"report", "reports"})) or
                 (bool(tokens & {"build", "builder", "session"}) and
                  bool(tokens & {"report", "reports", "latest", "prompt"})))
        opening = "\n".join(text.splitlines()[:12])
        return named or bool(re.search(
            r"\b(?:you are the (?:builder|reviewer|coordinator)|"
            r"(?:builder|build|session|continuation) report|"
            r"report (?:only|exclusively) to the .*?-o|"
            r"no .{0,30}-o.{0,30}(?:filename|path|supplied))\b", opening, re.I))

    docs = root / "docs"
    for path in sorted(docs.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if internal_report(relative):
            errors.append(f"publication: {relative}: internal agent prompt or session report")
        if path.suffix == ".zip":
            try:
                verify_evidence(path)
                with zipfile.ZipFile(path) as archive:
                    for entry in archive.infolist():
                        label = relative + "!" + entry.filename
                        if RAW_MEMBER.search(entry.filename) or entry.filename.endswith(".zip"):
                            errors.append(f"publication: {label}: raw trace or nested archive")
                        raw = archive.read(entry)
                        try:
                            text = raw.decode("utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig")
                        except UnicodeError:
                            errors.append(f"publication: {label}: uninspectable binary evidence")
                            continue
                        if internal_report(entry.filename, text):
                            errors.append(f"publication: {label}: internal agent prompt or session report")
                        # JSON escaping can make a relative backslash look like a
                        # UNC prefix. Inspect decoded values and keys as text too.
                        if entry.filename.endswith(".json"):
                            try:
                                decoded = json.loads(text)
                                from scripts.publication_safety import INTERNAL
                                if INTERNAL.search(text):
                                    errors.append(f"publication: {label}: internal session event or inventory")
                                text = "\n".join(decoded_strings(decoded))
                            except ValueError:
                                errors.append(f"publication: {label}: invalid JSON")
                        for issue in violations(expanded_text(entry.filename + "\n" + text), terms=private_names):
                            errors.append(f"publication: {label}: {issue}")
            except (ValueError, KeyError, zipfile.BadZipFile, OSError) as exc:
                errors.append(f"publication: {relative}: invalid evidence manifest ({type(exc).__name__})")
        else:
            if RAW_MEMBER.search(relative):
                errors.append(f"publication: {relative}: raw trace")
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeError:
                continue
            if not internal_report(relative) and internal_report(relative, text):
                errors.append(f"publication: {relative}: internal agent prompt or session report")
            from scripts.publication_safety import INTERNAL
            if INTERNAL.search(text):
                errors.append(f"publication: {relative}: internal session event or inventory")
            if path.suffix == ".json":
                try:
                    text = "\n".join(decoded_strings(json.loads(text)))
                except ValueError:
                    errors.append(f"publication: {relative}: invalid JSON")
            else:
                text = re.sub(r"```json\s*\n(.*?)\n```", decode_block, text, flags=re.S)
            for issue in violations(expanded_text(text), terms=private_names):
                errors.append(f"publication: {relative}: {issue}")

    # Fixtures, examples and eval inputs may keep the shape of captured host
    # output. docs/ above rejects every UUID; these accept only synthetic values.
    from scripts.publication_safety import native_identifiers
    shipped = [root / "tests" / "fixtures", root / "examples", *sorted((root / "skills").glob("*/evals"))]
    for base in shipped:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (UnicodeError, OSError):
                continue
            found = native_identifiers(expanded_text(text))
            if found:
                errors.append(f"publication: {path.relative_to(root).as_posix()}: {len(set(found))} non-synthetic "
                              "native session/request identifier(s); use 00000000-0000-7000-8000-00000000000N")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true",
                        help="run structural checks only; skip pytest and initializer scenario tests")
    args = parser.parse_args(argv)
    # Error messages can quote CJK README text; never crash on a legacy console code page.
    sys.stdout.reconfigure(errors="backslashreplace")
    errors: list[str] = []

    check_manifests(errors)
    check_publication(errors)
    check_legacy_name(errors)
    check_vocabulary(errors)
    check_release_receipt(errors)
    check_frontmatter(errors)
    check_readmes(errors)
    check_readme_headings(errors)
    check_local_links(errors)
    for path in DOCS:
        check_doc(path, errors)
    check_examples(errors)
    if not args.skip_tests:
        check_example(errors)
        check_initializer(errors)
        check_settings_modes(errors)
    check_core_split(errors)
    check_presets(errors)
    tests = "skipped (--skip-tests; structural checks only)" if args.skip_tests else check_tests(errors)

    if errors:
        print("VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("VALIDATION: PASS")
    print("- JSON manifests parse and share one version")
    print("- OpenAI metadata is aligned")
    print("- no legacy skill name remains")
    print("- core, current templates, and general references remain domain-neutral; specialized evidence uses plain terms")
    print("- SKILL.md frontmatter has only name and description")
    print("- all READMEs have the language switcher, working links, valid SVGs, and the same structure")
    print("- PLAN, DISCOVERIES, and HANDOFF blocks use the exact field order (docs, references, templates, example)")
    print("- concrete Priority values match the formula")
    print("- real handoff events list new plan items and discovery updates or give 'none - <reason>'")
    print("- every shipped example passes check_project.py without findings")
    if not args.skip_tests:
        print("- the worked example matches the current template and passes check_project.py")
        print("- check_project.py passes on a freshly initialized project")
        print("- every platform mode (single/multi/adaptive) x git mode (push/commit/off) renders and passes")
        print("- --reconfigure switches settings, applies directly edited settings, and refuses to overwrite hand-edited rules")
        print("- collector, reviewer, queue limits, and fallback settings are validated")
        print("- outside a git repository, git sync is reported and switched off; no repository is created")
    print("- discoveries record Host and Cross-check; reviews come from a different host")
    print("- Resource values are CPU/GPU/EITHER (plan) and CPU/GPU/Other/none (handoff)")
    print("- agent names and IDs follow A-Z, AA-ZZ and H-<Agent>-NN / D-<Agent>-NNN")
    if not args.skip_tests:
        print("- initializer creates LF files, validates agent names, and preserves existing files")
    print(f"- SKILL.md is within {SKILL_MAX_BYTES} UTF-8 bytes; every reference is within {REFERENCE_MAX_BYTES}")
    print("- every reference is reachable through local links from SKILL.md")
    print("- public local Markdown links and anchors resolve")
    print(f"- the {len(PRESETS)} built-in presets list every preset key and appear in --list-presets")
    if not args.skip_tests:
        print("- --reconfigure keeps ## Project rules verbatim and refuses hand-edits above it")
    print(f"- pytest: {tests}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
