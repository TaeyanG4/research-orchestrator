#!/usr/bin/env python3
"""The one table of Research Orchestrator project settings.

Every setting is one '- <Heading>: <value>' line under '## Project settings' in agents.md.
init_research_orchestrator.py (flags, presets, rendering) and check_project.py (validation)
both import this module; no other file defines a setting, an allowed value, or a default.

agents.md files without a template marker predate release 6.0; this release reads only the v3
layout. Settings marked inactive are stored and validated but change nothing yet.
"""

from __future__ import annotations

from collections import namedtuple
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys

from ro_markdown import mask_fences, unfenced, visible_lines


SKILL_ROOT = Path(__file__).resolve().parent.parent
PRESETS_DIR = SKILL_ROOT / "presets"
CURRENT_TEMPLATE = "v3.5"
FROZEN_TEMPLATES = tuple(sorted(path.name for path in (SKILL_ROOT / "templates").iterdir()
                                if path.is_dir() and re.fullmatch(r"v\d+(?:\.\d+)*", path.name)))
TEMPLATE_VERSIONS = (*FROZEN_TEMPLATES, CURRENT_TEMPLATE)
STANDING_RULES_BUDGET = 4096

BUILTIN_PRESETS = ("quick", "work-project", "solo-research", "team-research", "competition-solo", "competition-team")
PRESET_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
DEFAULT_PLATFORMS = "Claude Code, Codex"
DEFAULT_LIMITS = "stop at 50, resume at 5"
DEFAULT_FALLBACK = {"single": "same-host", "multi": "wait", "adaptive": "same-host"}
ALIASES = {"profile": {"normal": "work", "kaggle": "competition"}}
ASKABLE = ("platforms", "environment", "language", "competition", "phase_clock", "git", "external_actions")
GUARD_IDS = ("G1", "G3", "G5", "G6", "GD", "G8", "G11", "G12", "E1")
PROFILE_GUARDS = {
    "work": ("G5", "G6", "GD", "E1"),
    "research": ("G1", "G5", "G6", "GD", "E1"),
    "competition": tuple(guard for guard in GUARD_IDS if guard != "G12"),
}
DEFAULT_GUARD_THRESHOLDS = "saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75"
CHECK_IDS = ("shell.background", "shell.detach", "shell.heredoc", "shell.cd", "jobs.mutate-bound",
             "jobs.read-bound", "jobs.unmonitored", "records.timestamp", "records.id",
             "publish.scan", "external.gate", "ask.away", "brief.requirements")
DEFAULT_BLOCK = "shell.background, shell.heredoc, jobs.mutate-bound, publish.scan"


def detect_environment() -> str | None:
    """Use the current OS and usual shell; unknown explicit environments need an answer."""
    operating_system = {"win32": "windows", "darwin": "macos", "linux": "linux"}.get(sys.platform)
    if operating_system is None:
        return None
    shell_name = re.split(r"[/\\]", os.environ.get("SHELL", ""))[-1].lower().removesuffix(".exe")
    shell = "powershell" if operating_system == "windows" else "bash"
    if shell_name in ("bash", "zsh", "sh"):
        shell = "bash"
    elif shell_name in ("pwsh", "powershell"):
        shell = "powershell"
    elif shell_name:
        return None
    return f"{operating_system}/{shell}"


def detect_host() -> str:
    """Use a host's own session marker; a plain shell is a usable single-host default."""
    if os.environ.get("CODEX_THREAD_ID"):
        return "Codex"
    if os.environ.get("CLAUDECODE"):
        return "Claude Code"
    if (os.environ.get("ANTIGRAVITY_SESSION_ID") or os.environ.get("ANTIGRAVITY_AGENT")
            or os.environ.get("TERM_PROGRAM", "").casefold() == "antigravity"):
        return "Antigravity"
    if any(value and key.startswith("GEMINI_") for key, value in os.environ.items()):
        return "Gemini CLI"
    return "local"


class _SettingFields:
    """Field order and meaning of Setting, a named tuple: hooks import this module, and
    importing dataclasses would cost ~15 ms per hook call."""

    key: str                          # internal key; also the preset JSON key
    label: str                        # line heading in agents.md
    flag: str                         # init_research_orchestrator.py flag
    help: str
    default: str                      # legacy missing-setting default; fresh un-preset work overrides a few
    choices: tuple[str, ...]          # allowed values; empty = free-form, checked by a parser below
    preset: bool                      # required in built-in and legacy preset files
    active: bool                      # False: stored and validated only
    condition: str                    # template condition name ({{#if <condition>=...}})
    effect: str                       # how an edit takes effect: immediate, reconfigure, migrate, record, stored


Setting = namedtuple("Setting", list(_SettingFields.__annotations__),
                     defaults=((), False, True, "", "immediate"))


SETTINGS: tuple[Setting, ...] = (
    Setting("preset", "Preset", "--preset", "Preset to start from: " + ", ".join(BUILTIN_PRESETS)
            + ", custom, or user:<name> (see --list-presets)", "custom", effect="record"),
    Setting("profile", "Profile", "--profile", "Kind of work: work (alias normal), research, or competition",
            "research", ("work", "research", "competition"), preset=True, condition="profile", effect="reconfigure"),
    Setting("workflow", "Workflow", "--workflow", "classic: per-agent plan sections; unified: one shared queue "
            "with Claimed: lines (changing it needs --migrate)", "classic", ("classic", "unified"), preset=True,
            condition="workflow", effect="migrate"),
    Setting("verification", "Verification", "--verification", "cross-host-once, independent-review, hybrid, "
            "or self", "cross-host-once", ("cross-host-once", "independent-review", "hybrid", "self"),
            preset=True, condition="verification", effect="reconfigure"),
    Setting("item_size", "Item size", "--item-size", "short, or staged (items with Stages: and stage events)",
            "short", ("short", "staged"), preset=True, condition="itemsize", effect="reconfigure"),
    Setting("guards", "Guards", "--guards", "Evidence guards: off, light, strict; enabled modes may include "
            "since YYYY-MM-DD", "off", preset=True, condition="guards", effect="reconfigure"),
    Setting("guard_set", "Guard set", "--guard-set", "auto, or comma-separated guard IDs: "
            + ", ".join(GUARD_IDS), "auto", condition="guardset", effect="reconfigure"),
    Setting("guard_thresholds", "Guard thresholds", "--guard-thresholds", "Comma-separated key=value guard "
            "thresholds, e.g. saturation=5, direction-review=7d", DEFAULT_GUARD_THRESHOLDS),
    Setting("environment", "Environment", "--environment", "Declared OS/shell: windows, linux, or macos / "
            "bash or powershell (default: auto-detected)", detect_environment() or "linux/bash",
            tuple(f"{operating_system}/{shell}" for operating_system in ("windows", "linux", "macos")
                  for shell in ("bash", "powershell"))),
    Setting("language", "Language", "--language", "Language for project free text and user replies: "
            "BCP-47-shaped code, e.g. en, ko, ja, zh-CN (default: en / English)", "en"),
    Setting("enforcement", "Enforcement", "--enforcement", "off, warn, block", "off",
            ("off", "warn", "block"), preset=True),
    Setting("block", "Block", "--block", "Comma-separated blocking check IDs, or none", "none", preset=True),
    Setting("read_bound", "Read bound", "--read-bound", "Running-job read warnings: off (default) or on",
            "off", ("off", "on")),
    Setting("external_actions", "External actions", "--external-actions", "Semicolon-separated command prefixes or regex: patterns", "none"),
    Setting("receipt_policy", "Receipt policy", "--receipt-policy", "Artifact receipt reviewer: independent or self",
            "independent", ("independent", "self")),
    Setting("publish_scan", "Publish scan", "--publish-scan", "secrets; literal:text; regex:pattern; "
            "deadline=<N>s|m (pre-push scan budget, default 60s)", "secrets"),
    Setting("brief_requirements", "Brief requirements", "--brief-requirements", "Semicolon-separated type: required line entries", "none"),
    Setting("autonomy", "Autonomy", "--autonomy", "present or away", "present", ("present", "away")),
    Setting("stale_slot_after", "Stale slot after", "--stale-slot-after",
            "Positive inactivity duration for taken slots without active jobs (default: 2h)", "2h"),
    Setting("queue_freeze", "Queue freeze", "--queue-freeze", "off, or until YYYY-MM-DD; pause new queue items", "off"),
    Setting("phase_clock", "Phase clock", "--phase-clock", "off, or START,DEADLINE as YYYY-MM-DD,YYYY-MM-DD",
            "off"),
    Setting("competition", "Competition", "--competition",
            "off, or <platform>/<slug> with optional deadline=YYYY-MM-DD suffix", "off"),
    Setting("platform_mode", "Platform mode", "--platform", "multi: several platforms at once; single: one "
            "platform; adaptive: changes over time (default)", "adaptive", ("multi", "single", "adaptive"),
            preset=True, condition="mode", effect="reconfigure"),
    Setting("platforms", "Platforms", "--platforms", f"Comma-separated platforms (default: {DEFAULT_PLATFORMS}; "
            "single needs exactly one)", DEFAULT_PLATFORMS, preset=True),
    Setting("git", "Git sync", "--git", "push: commit and push automatically; commit: local commits only; "
            "off: no git (default)", "off", ("push", "commit", "off"), condition="git", effect="reconfigure"),
    Setting("collector", "Plan collector", "--collector", "Plan collector sub-agent: off (default) or "
            "\"<platform>/<model>\", e.g. \"Claude Code/sonnet\"", "off", preset=True),
    Setting("queue_limits", "Plan queue limits", "--queue-limits", "Collector stop and resume counts, e.g. 50,5 "
            "(default)", DEFAULT_LIMITS, preset=True),
    Setting("reviewer", "Reviewer", "--reviewer", "Reviewer sub-agent: off (default) or \"<platform>/<model>\", "
            "e.g. \"Codex/sol\"", "off", preset=True),
    Setting("fallback", "Cross-check fallback", "--fallback", "wait or same-host (default: wait for multi, "
            "same-host otherwise)", "", ("wait", "same-host"), preset=True),
)
SETTING = {setting.key: setting for setting in SETTINGS}
BY_LABEL = {setting.label: setting for setting in SETTINGS}
# Bindings and dates are resolved for each project; the remaining settings are reusable.
PROJECT_ONLY_KEYS = ("preset", "competition", "phase_clock", "queue_freeze")
PRESET_KEYS = tuple(setting.key for setting in SETTINGS if setting.key not in PROJECT_ONLY_KEYS)
PRESET_FILE_KEYS = ("name", "summary", *PRESET_KEYS, "asks")
REQUIRED_PRESET_FILE_KEYS = ("name", "summary", *(setting.key for setting in SETTINGS if setting.preset), "asks")
# Settings that change the generated rules in agents.md (and so need --reconfigure).
RULE_KEYS = tuple(setting.key for setting in SETTINGS if setting.condition)


# ---------- value parsers ----------

def safe_regex(pattern: str) -> re.Pattern:
    """A bounded grammar: flat alternatives, at most one bounded repeat per branch.

    A branch has at most 511 consumed characters and a fixed amount of backtracking
    at each input position. Callers scanning large inputs also enforce a deadline.
    """
    subset = ("use literals, character classes, anchors and top-level flat alternatives, "
              "with at most one bounded single-atom quantifier (maximum 256) per alternative; "
              "groups, nested or unbounded quantifiers and wildcards are unsupported")
    if not pattern or len(pattern) > 256:
        raise ValueError(f"regex must contain 1 to 256 characters; {subset}")
    # Reject groups before parser normalization can erase them; split only real alternatives.
    branches, start, index = [], 0, 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            index += 1
            if index < len(pattern) and pattern[index] == "^":
                index += 1
            if index < len(pattern) and pattern[index] == "]":
                index += 1
            while index < len(pattern) and pattern[index] != "]":
                index += 2 if pattern[index] == "\\" else 1
        elif char in "()":
            raise ValueError(f"regex groups are unsupported; {subset}")
        elif char == "|":
            branches.append(pattern[start:index])
            start = index + 1
        index += 1
    branches.append(pattern[start:])
    try:
        from re import _parser as parser, _constants as op
        atom = {op.LITERAL, op.NOT_LITERAL, op.CATEGORY}

        def single_atom(kind, value):
            return kind in atom or (kind == op.IN and all(
                k in {op.LITERAL, op.RANGE, op.CATEGORY, op.NEGATE} for k, _ in value))

        for branch in branches:
            repeats = 0
            for kind, value in parser.parse(branch, 0):
                if single_atom(kind, value) or kind == op.AT:
                    continue
                if kind == op.MAX_REPEAT:
                    lower, upper, child = value
                    repeats += 1
                    if upper > 256 or len(child) != 1 or not single_atom(*child[0]) or repeats > 1:
                        raise ValueError(f"unsupported regex quantifier; {subset}")
                    continue
                raise ValueError(f"unsupported regex syntax; {subset}")
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regex: {exc}; {subset}") from None

def scan_deadline(entry: str) -> float:
    """Seconds for the authoritative pre-push scan: `deadline=<N>s` or `deadline=<N>m`, 1 s to 60 min."""
    match = re.fullmatch(r"deadline=(\d{1,4})(s|m)", entry.strip())
    seconds = int(match[1]) * (60 if match[2] == "m" else 1) if match else 0
    if not 1 <= seconds <= 3600:
        raise ValueError("Publish scan deadline must be deadline=<N>s or deadline=<N>m, between 1 s and 60 min")
    return float(seconds)


def parse_platforms(raw: str | None, mode: str) -> str:
    if raw is None:
        if mode == "single":
            raise ValueError("--platform single needs --platforms with exactly one platform, e.g. --platforms \"Claude Code\"")
        raw = DEFAULT_PLATFORMS
    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise ValueError("--platforms needs at least one platform name")
    if len(set(names)) != len(names):
        raise ValueError("--platforms lists the same platform twice")
    if mode == "single" and len(names) != 1:
        raise ValueError("--platform single needs exactly one platform in --platforms")
    if mode == "multi" and len(names) < 2:
        raise ValueError("--platform multi needs at least two platforms in --platforms")
    return ", ".join(names)


def parse_sub_agent(raw: str, platforms: str, label: str) -> str:
    """Return 'off' or 'on — <platform> / <model>' from 'off', '<platform>/<model>', or the stored form."""
    if raw.strip().lower() == "off":
        return "off"
    text = raw.strip()
    if text.lower().startswith("on — "):
        text = text[len("on — "):]
    platform, sep, model = text.partition("/")
    platform, model = platform.strip(), model.strip()
    if not sep or not platform or not model:
        raise ValueError(f"--{label} must be 'off' or '<platform>/<model>', e.g. \"Claude Code/sonnet\"")
    allowed = [p.strip() for p in platforms.split(",")]
    if platform not in allowed:
        raise ValueError(f"--{label} platform '{platform}' is not in --platforms ({platforms})")
    return f"on — {platform} / {model}"


def parse_limits(raw: str) -> str:
    numbers = re.findall(r"\d+", raw)
    if len(numbers) != 2:
        raise ValueError("--queue-limits must give a stop and a resume count, e.g. 50,5")
    stop, resume = map(int, numbers)
    if not 0 <= resume < stop:
        raise ValueError("--queue-limits needs resume < stop, e.g. 50,5")
    return f"stop at {stop}, resume at {resume}"


def parse_guards(raw: str) -> str:
    """Validate the mode and optional activation date, without creating a date during a read."""
    match = re.fullmatch(r"(off|light|strict)(?:\s+since\s+(\d{4}-\d{2}-\d{2}))?", raw.strip().lower())
    if not match or (match.group(1) == "off" and match.group(2)):
        raise ValueError(f"Guards '{raw}' must be off, light, or strict, with optional since YYYY-MM-DD when on")
    mode, since = match.groups()
    if since:
        try:
            dt.date.fromisoformat(since)
        except ValueError:
            raise ValueError(f"Guards '{raw}' has an invalid since date") from None
    return mode + (f" since {since}" if since else "")


def guard_mode(raw: str) -> str:
    return parse_guards(raw).split()[0]


def guard_since(raw: str) -> dt.date | None:
    value = parse_guards(raw)
    return dt.date.fromisoformat(value.split()[-1]) if " since " in value else None


def stamp_guards(raw: str, previous: str = "off", today: dt.date | None = None) -> str:
    """When writing enabled guards, retain their activation date or start a new dated window."""
    value = parse_guards(raw)
    if guard_mode(value) == "off" or guard_since(value) is not None:
        return value
    since = guard_since(previous) if guard_mode(previous) != "off" else None
    return f"{value} since {(since or today or dt.date.today()).isoformat()}"


def parse_guard_set(raw: str) -> str:
    if raw.strip().lower() == "auto":
        return "auto"
    guards = [part.strip().upper() for part in raw.split(",")]
    if not guards or any(guard not in GUARD_IDS for guard in guards) or len(set(guards)) != len(guards):
        raise ValueError(f"Guard set '{raw}' must be auto or distinct comma-separated IDs from {', '.join(GUARD_IDS)}")
    return ",".join(guard for guard in GUARD_IDS if guard in guards)


def enabled_guards(values: dict[str, str]) -> set[str]:
    if guard_mode(values.get("guards", "off")) == "off":
        return set()
    selection = parse_guard_set(values.get("guard_set", "auto"))
    return set(PROFILE_GUARDS[values.get("profile", "research")]) if selection == "auto" else set(selection.split(","))


def _threshold_values(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in raw.split(","):
        key, separator, value = part.strip().partition("=")
        key = key.strip()
        if not separator or key not in ("saturation", "direction-review", "direction-parts", "insight-due", "effort", "milestones"):
            raise ValueError(f"Guard thresholds '{raw}' needs known key=value entries")
        if key in values:
            raise ValueError(f"Guard thresholds '{raw}' repeats '{key}'")
        value = value.strip()
        if key == "saturation":
            valid = bool(re.fullmatch(r"\d+", value)) and int(value) >= 1
        elif key == "direction-parts":
            valid = value in ("profile", "full")
        elif key in ("direction-review", "insight-due"):
            valid = bool(re.fullmatch(r"[1-9]\d*[dh]", value))
        elif key == "effort":
            valid = bool(re.fullmatch(r"\d+(?:\.\d+)?%", value)) and 0 <= float(value[:-1]) <= 100
        else:
            valid = bool(re.fullmatch(r"\d+/\d+/\d+", value))
            if valid:
                first, second, third = map(int, value.split("/"))
                valid = 0 < first < second < third <= 100
        if not valid:
            raise ValueError(f"Guard thresholds '{raw}' has an invalid '{key}' value")
        values[key] = value
    return values


def parse_guard_thresholds(raw: str) -> str:
    values = _threshold_values(raw)
    order = (*_threshold_values(DEFAULT_GUARD_THRESHOLDS), "direction-parts")
    return ", ".join(f"{key}={values[key]}" for key in order if key in values)


def guard_thresholds(raw: str) -> dict[str, int | float | str | tuple[int, ...]]:
    """Effective numeric thresholds: days, hours, percentage points, and milestone shares."""
    values = {**_threshold_values(DEFAULT_GUARD_THRESHOLDS), **_threshold_values(raw)}
    direction, insight = values["direction-review"], values["insight-due"]
    return {
        "saturation": int(values["saturation"]),
        "direction-review": int(direction[:-1]) / (24 if direction[-1] == "h" else 1),
        "insight-due": int(insight[:-1]) * (24 if insight[-1] == "d" else 1),
        "effort": float(values["effort"][:-1]),
        "milestones": tuple(map(int, values["milestones"].split("/"))),
        "direction-parts": values.get("direction-parts", "profile"),
    }


def parse_phase_clock(raw: str) -> str:
    text = raw.strip()
    if text.lower() == "off":
        return "off"
    match = re.fullmatch(r"(?:start\s+)?(\d{4}-\d{2}-\d{2})\s*,\s*(?:deadline\s+)?(\d{4}-\d{2}-\d{2})", text)
    if not match:
        raise ValueError(f"Phase clock '{raw}' must be 'off' or 'start YYYY-MM-DD, deadline YYYY-MM-DD' "
                         "(flag: --phase-clock 2026-10-01,2026-12-01)")
    try:
        start, deadline = (dt.date.fromisoformat(part) for part in match.groups())
    except ValueError as exc:
        raise ValueError(f"Phase clock '{raw}' has an invalid date: {exc}") from None
    if deadline < start:
        raise ValueError(f"Phase clock '{raw}' ends before it starts")
    return f"start {start.isoformat()}, deadline {deadline.isoformat()}"


def parse_queue_freeze(raw: str) -> str:
    text = raw.strip().lower()
    if text == "off":
        return text
    match = re.fullmatch(r"until (\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return "until " + dt.date.fromisoformat(match.group(1)).isoformat()
        except ValueError:
            pass
    raise ValueError(f"Queue freeze '{raw}' must be 'off' or 'until YYYY-MM-DD' with a valid date")


def competition_parts(raw: str) -> tuple[str, str | None]:
    """Separate the persistent binding from an optional setup deadline hint."""
    text = raw.strip()
    if text.lower() == "off":
        return "off", None
    match = re.fullmatch(r"([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)(?:\s+deadline=(\d{4}-\d{2}-\d{2}))?", text)
    if not match:
        raise ValueError(f"Competition '{raw}' must be 'off' or '<platform>/<slug>' "
                         "with optional 'deadline=YYYY-MM-DD'")
    deadline = match.group(3)
    if deadline:
        try:
            dt.date.fromisoformat(deadline)
        except ValueError:
            raise ValueError(f"Competition '{raw}' has an invalid deadline") from None
    return f"{match.group(1).lower()}/{match.group(2)}", deadline


def parse_competition(raw: str) -> str:
    return competition_parts(raw)[0]


def competition_clock_default(flags: dict[str, str | None], stored: dict[str, str]) -> str | None:
    """Use today as the start only when a supplied deadline fills an unanswered clock."""
    if flags.get("phase_clock") is not None or stored.get("phase_clock") is not None:
        return None
    _competition, deadline = competition_parts(flags.get("competition") or "off")
    return parse_phase_clock(f"{dt.date.today().isoformat()},{deadline}") if deadline else None


def parse_preset_name(raw: str) -> str:
    text = raw.strip()
    if text.lower() in (*BUILTIN_PRESETS, "custom"):
        return text.lower()
    if text.lower().startswith("user:") and PRESET_NAME.match(text[5:]):
        return f"user:{text[5:]}"
    raise ValueError(f"Preset '{raw}' must be one of {', '.join(BUILTIN_PRESETS)}, custom, or user:<name>")


def normalize(key: str, raw: str | None, values: dict[str, str]) -> str:
    """Validate one setting and return its canonical stored form. `values` holds the settings before it."""
    setting = SETTING[key]
    if key == "platforms":
        return parse_platforms(raw, values["platform_mode"])
    if raw is None:
        raise ValueError(f"{setting.label} has no value")
    if key == "preset":
        return parse_preset_name(raw)
    if key == "language":
        value = raw.strip()
        if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value):
            raise ValueError(f"Language '{raw}' must be a BCP-47-shaped code, e.g. en, ko, ja, zh-CN")
        return value
    if key == "stale_slot_after":
        from ro_state import duration
        value = raw.strip()
        seconds = duration(value)
        if not 0 < seconds < float("inf"):
            raise ValueError("Stale slot after must be a finite positive duration")
        return value
    if key in ("collector", "reviewer"):
        return parse_sub_agent(raw, values["platforms"], key)
    if key == "queue_limits":
        return parse_limits(raw)
    if key == "guards":
        return parse_guards(raw)
    if key == "guard_set":
        return parse_guard_set(raw)
    if key == "guard_thresholds":
        return parse_guard_thresholds(raw)
    if key == "phase_clock":
        return parse_phase_clock(raw)
    if key == "queue_freeze":
        return parse_queue_freeze(raw)
    if key == "competition":
        return parse_competition(raw)
    if key == "block":
        if raw.strip().lower() in ("none", "off", ""):
            return "none"
        selected = [part.strip() for part in raw.split(",")]
        if len(set(selected)) != len(selected) or any(part not in CHECK_IDS for part in selected):
            raise ValueError("Block must list distinct known check IDs")
        return ", ".join(selected)
    if key in ("external_actions", "publish_scan", "brief_requirements"):
        if len(raw) > 4096 or "\n" in raw or "\r" in raw:
            raise ValueError(f"{setting.label} must fit on one line of at most 4096 characters")
        parts = [part.strip() for part in raw.split(";") if part.strip()]
        if not parts:
            raise ValueError(f"{setting.label} needs a value (use none to disable)")
        for part in parts:
            if key == "publish_scan" and part.startswith("deadline="):
                scan_deadline(part)
            elif key == "publish_scan" and part not in ("secrets", "none") and not part.startswith(("literal:", "regex:")):
                raise ValueError("Publish scan needs secrets, literal:text, regex:pattern, or deadline=<N>s|m")
            if key == "brief_requirements" and part != "none" and not re.fullmatch(r"[^:]+:\s*\S.*", part):
                raise ValueError("Brief requirements needs type: required line entries")
            if part.startswith("regex:"):
                safe_regex(part[6:])
        return "; ".join(parts)
    value = raw.strip().lower()
    value = ALIASES.get(key, {}).get(value, value)
    if value not in setting.choices:
        raise ValueError(f"{setting.label} '{raw}' must be one of {', '.join(setting.choices)}")
    return value


def default_value(key: str, values: dict[str, str]) -> str | None:
    if key == "receipt_policy" and values.get("preset") == "competition-solo":
        return "self"
    if key == "environment":
        return detect_environment()
    if key == "external_actions" and values.get("profile") == "competition":
        path = SKILL_ROOT / "references" / "adapters" / "external-actions.json"
        platform = values.get("competition", "off").partition("/")[0].lower()
        return "; ".join(json.loads(path.read_text(encoding="utf-8")).get(platform, [])) or "none"
    if key == "platforms":
        return detect_host() if values.get("platform_mode") == "single" else DEFAULT_PLATFORMS
    if key == "fallback":
        return DEFAULT_FALLBACK[values["platform_mode"]]
    return SETTING[key].default


def resolve(flags: dict[str, str | None], preset: dict[str, object] | None, stored: dict[str, str],
            *, new_project: bool = False) -> dict[str, str]:
    """Resolve flag > preset > stored > default; fresh un-preset work has compact defaults."""
    values: dict[str, str] = {}
    # Keep old projects' missing-setting semantics stable. New un-preset work
    # starts compactly and can opt into research or stricter review explicitly.
    fresh_defaults = {"profile": "work", "verification": "self", "enforcement": "block",
                      "block": DEFAULT_BLOCK} if new_project and not preset else {}
    # Competition is project-only and appears later in the display order, but
    # its platform selects the external-action default resolved below.
    competition = parse_competition(flags.get("competition") if flags.get("competition") is not None
                                    else stored.get("competition", SETTING["competition"].default))
    clock_default = competition_clock_default(flags, stored)
    external_source = stored.get("_external_actions_source")
    if (external_source == "default" and stored.get("external_actions") !=
            default_value("external_actions", stored)):
        external_source = "explicit"  # A hand-edited pattern is a project choice, too.
    if flags.get("external_actions") is not None or (preset and preset.get("external_actions") is not None):
        external_source = "explicit"
    elif "external_actions" not in stored:
        external_source = "default"
    for setting in SETTINGS:
        raw = flags.get(setting.key)
        if raw is None and preset and setting.key in PRESET_KEYS:
            preset_value = preset.get(setting.key)
            raw = None if preset_value is None else str(preset_value)
        if raw is None:
            raw = stored.get(setting.key)
            if (setting.key == "external_actions" and external_source == "default" and
                    (values.get("profile") != stored.get("profile") or
                     competition != stored.get("competition", "off"))):
                raw = None  # Only an inherited default follows a changed profile or platform.
        if raw is None:
            raw = fresh_defaults.get(setting.key)
            if setting.key == "phase_clock" and clock_default is not None:
                raw = clock_default
            if setting.key == "platforms" and new_project and not preset and values["platform_mode"] != "multi":
                raw = detect_host()
            if raw is None:
                raw = default_value(setting.key, {**values, "competition": competition})
        if raw is None:
            raise ValueError(f"cannot detect {setting.label}; pass {setting.flag}")
        values[setting.key] = normalize(setting.key, raw, values)
    if external_source in ("default", "explicit"):
        values["_external_actions_source"] = external_source
    return values


def question_answers(preset: dict[str, object] | None, flags: dict[str, str | None],
                     stored: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return unanswered choices and defaults without turning detection into a questionnaire.

    Explicit flags and stored lines answer choices. Environment and language are implicit
    defaults even when omitted from `asks`; only unavailable defaults need an answer.
    """
    if not preset:
        return [], {}
    missing: list[str] = []
    defaults: dict[str, str] = {}
    for key in dict.fromkeys([*preset.get("asks", []), "environment", "language"]):
        inherited_gate = (key == "external_actions" and stored.get("_external_actions_source") == "default"
                          and stored.get(key) == default_value(key, stored))
        if flags.get(key) is not None or (stored.get(key) is not None and not inherited_gate):
            continue
        default = preset.get(key)
        if default is None and key in ("platforms", "environment", "language", "git"):
            default = default_value(key, {"platform_mode": str(preset.get("platform_mode", "single"))})
        if default is None and key == "external_actions":
            competition = flags.get("competition") or stored.get("competition", "off")
            if competition == "off":
                continue  # Choose the platform before asking about its command adapter.
            candidate = default_value(key, {"profile": str(preset.get("profile", "work")),
                                            "competition": competition})
            if candidate != "none":
                default = candidate
        if default is None and key == "phase_clock":
            default = competition_clock_default(flags, stored)
        if default is None:
            missing.append(SETTING[key].flag)
        else:
            defaults[key] = str(default)
    return missing, defaults


def single_platform_conflict(preset: dict[str, object] | None, flags: dict[str, str | None],
                             stored: dict[str, str]) -> bool:
    """True when a single-platform preset would inherit a platforms answer that lists several hosts."""
    if not preset or flags.get("platform_mode") is not None or preset.get("platform_mode") != "single":
        return False
    answer = flags.get("platforms")
    if answer is None:
        answer = preset.get("platforms")
    if answer is None:
        answer = stored.get("platforms")
    return answer is not None and len([p for p in str(answer).split(",") if p.strip()]) != 1


# ---------- presets ----------

def user_presets_dir() -> Path:
    home = os.environ.get("RESEARCH_ORCHESTRATOR_HOME")
    base = Path(home) if home else Path.home() / ".research-orchestrator"
    return base / "presets"


def preset_path(name: str) -> Path:
    if name.startswith("user:"):
        return user_presets_dir() / f"{name[5:]}.json"
    return PRESETS_DIR / f"{name}.json"


def validate_preset(data: object, source: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError(f"{source}: a preset must be a JSON object")
    keys = list(data)
    missing = [key for key in REQUIRED_PRESET_FILE_KEYS if key not in data]
    unknown = [key for key in keys if key not in PRESET_FILE_KEYS]
    if missing or unknown:
        raise ValueError(f"{source}: preset keys missing {missing or 'none'}, unknown {unknown or 'none'}")
    asks = data["asks"]
    if not isinstance(asks, list) or not set(asks) <= set(ASKABLE) or len(set(asks)) != len(asks):
        raise ValueError(f"{source}: 'asks' must list distinct entries from {', '.join(ASKABLE)}")
    values: dict[str, str] = {}
    for setting in SETTINGS:
        if setting.key not in PRESET_KEYS or setting.key not in data:
            continue
        raw = data[setting.key]
        if raw is None:
            if setting.key == "platforms" and "platforms" in asks:
                continue  # answered at setup time
            raise ValueError(f"{source}: '{setting.key}' must be a string (only platforms may be null, and then asked)")
        if not isinstance(raw, str):
            raise ValueError(f"{source}: '{setting.key}' must be a string")
        context = dict(values)
        if setting.key in ("collector", "reviewer") and "platforms" not in values:
            context["platforms"] = raw.partition("—")[2].partition("/")[0].strip()  # hosts asked later
        try:
            values[setting.key] = normalize(setting.key, raw, context)
        except ValueError as exc:
            raise ValueError(f"{source}: {exc}") from None
        if values[setting.key] != raw:
            raise ValueError(f"{source}: '{setting.key}' must be written as '{values[setting.key]}'")
        if setting.key == "guards" and guard_since(raw) is not None:
            raise ValueError(f"{source}: guard activation dates belong to a project; save only the guard mode")
    return data


def load_preset(name: str) -> dict[str, object]:
    """Return a preset's keys; 'custom' is the absence of a preset and covers nothing."""
    name = parse_preset_name(name)
    if name == "custom":
        return {}
    path = preset_path(name)
    if not path.is_file():
        where = "built-in presets" if not name.startswith("user:") else f"user presets in {path.parent}"
        raise ValueError(f"preset '{name}' not found among the {where}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from None
    return validate_preset(data, str(path))


def list_presets() -> list[tuple[str, dict[str, object]]]:
    found = [(name, load_preset(name)) for name in BUILTIN_PRESETS]
    folder = user_presets_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            if PRESET_NAME.match(path.stem):
                try:
                    found.append((f"user:{path.stem}", load_preset(f"user:{path.stem}")))
                except ValueError as exc:
                    found.append((f"user:{path.stem}", {"summary": f"INVALID — {exc}"}))
    return found


def save_user_preset(name: str, values: dict[str, str], summary: str) -> tuple[Path, bool]:
    """Save reusable policies, excluding project bindings and dates; return path and replacement status."""
    if not PRESET_NAME.match(name):
        raise ValueError(f"preset name '{name}' must be lowercase letters, digits, '-' or '_' (e.g. my-research)")
    asks = ["platforms"] + (
        ["competition", "phase_clock"] if values["profile"] == "competition" else []) + ["git"]
    data: dict[str, object] = {"name": name, "summary": summary}
    data.update({key: values[key] for key in PRESET_KEYS})
    data["guards"] = guard_mode(values["guards"])  # activation dates belong to a project, not a reusable preset
    data["asks"] = asks
    validate_preset(data, f"user:{name}")
    path = user_presets_dir() / f"{name}.json"
    replaced = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path, replaced


# ---------- reading agents.md ----------

MARKER = re.compile(r"<!-- ro-template: (v\d+(?:\.\d+)*)(?: \(([^)]*)\))? -->")
TITLE = re.compile(r"^# (.+) — Agent Rules$")
SETTINGS_LINE = re.compile(r"^- ([A-Za-z][A-Za-z -]*?): ?(.*)$")
RULES_HEADING = "## Project rules"
TRANSACTION = Path(".ro") / "migration.json"   # an unfinished migration (init_research_orchestrator.py)


class StoredSettings:
    """What agents.md records: project title, template version, rendered conditions and settings lines."""

    __slots__ = ("project", "version", "rendered", "values", "unknown", "has_section")

    def __init__(self, project: str | None = None, version: str = "", rendered: dict[str, str] | None = None,
                 values: dict[str, str] | None = None, unknown: dict[str, str] | None = None,
                 has_section: bool = False):
        self.project = project
        self.version = version                    # template version recorded in the file ("": none)
        self.rendered = rendered or {}            # rule conditions the rules were generated for
        self.values = values or {}                # key -> value, for lines present
        self.unknown = unknown or {}              # unknown heading -> value
        self.has_section = has_section

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, StoredSettings)
                and all(getattr(self, name) == getattr(other, name) for name in self.__slots__))

    def __repr__(self) -> str:
        return "StoredSettings(" + ", ".join(f"{name}={getattr(self, name)!r}" for name in self.__slots__) + ")"


def split_agents(text: str) -> tuple[str, str]:
    """Split agents.md into the generated part and the user-owned region from '## Project rules' to the end."""
    offset = 0
    for line, visible in visible_lines(text):
        if visible and line.rstrip() == RULES_HEADING:
            return text[:offset], text[offset:]
        offset += len(line)
    return text, ""


def read_settings(text: str, root: Path | None = None) -> StoredSettings:
    generated, _region = split_agents(text)
    stored = StoredSettings()
    lines = unfenced(generated)
    if lines and (title := TITLE.match(lines[0])):
        stored.project = title.group(1)
    marker = MARKER.search(mask_fences(generated))
    if marker:
        stored.version = marker.group(1)
        stored.rendered = dict(re.findall(r"(\w+)=(\S+)", marker.group(2) or ""))
        if not marker.group(2) and root is not None:
            try:
                metadata = json.loads((root / ".ro" / "template-render.json").read_text(encoding="utf-8"))
                if metadata.get("version") == stored.version:
                    stored.rendered = dict(re.findall(r"(\w+)=(\S+)", metadata["render_key"]))
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                pass  # Portable coordination files still work without machine-local state.
        source = stored.rendered.get("external_actions_source")
        if source in ("default", "explicit"):
            stored.values["_external_actions_source"] = source
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip() == "## Project settings"
            stored.has_section = stored.has_section or in_section
        elif in_section and (match := SETTINGS_LINE.match(line)):
            label, value = match.group(1), match.group(2).strip()
            if label == "Platforms" and value.startswith("single — "):
                stored.values.setdefault("platform_mode", "single")
                value = value.removeprefix("single — ")
            if label in BY_LABEL:
                stored.values.setdefault(BY_LABEL[label].key, value)
            else:
                stored.unknown[label] = value
    return stored


def files_workflow(stored: StoredSettings) -> str:
    """The workflow the plan files are in: the one the generated part was made for.

    It differs from the Workflow line only when that line was edited and --reconfigure --migrate not run yet.
    """
    return stored.rendered.get("workflow") or stored.values.get("workflow") or SETTING["workflow"].default


# ---------- derived text ----------

def conditions(values: dict[str, str]) -> dict[str, str]:
    """Template conditions ({{#if key=value}}) for the settings that shape the rules."""
    conditions = {SETTING[key].condition: values[key] for key in RULE_KEYS}
    conditions["guards"] = guard_mode(values["guards"])
    guards = enabled_guards(values)
    conditions["instruments"] = "on" if guards & {"G1", "G3"} else "off"
    conditions["externalactions"] = "on" if guards & {"E1", "G3", "G11"} else "off"
    conditions["collector"] = "off" if values.get("collector", "off") == "off" else "on"
    conditions["phaseclock"] = "off" if values.get("phase_clock", "off") == "off" else "on"
    return conditions


def render_key(values: dict[str, str]) -> str:
    """What the template marker records: the rule conditions and the preset the generated part was made for."""
    rendered = conditions(values)
    key = " ".join(f"{name}={value}" for name, value in rendered.items()) + f" preset={values['preset']}"
    if source := values.get("_external_actions_source"):
        key += f" external_actions_source={source}"
    key += " pointers=" + ",".join(reading_pointer_ids(values))
    return key


# Only non-default choices need extra reading pointers; the core owns the operation table.
READING_POINTERS = {
    "workflow-unified": "claim and move work in the shared queue",
    "verification": "apply the selected verification policy",
    "staged-items": "plan or complete a stage",
    "git-sync": "apply the enabled git policy",
    "research-guards": "record measured evidence and resolve guard findings",
    "decision-guards": "record strategic decisions",
    "competition": "prepare competition evidence or candidates",
    "plan-collector": "collect candidates",
    "external-actions": "prepare an outward action",
    "hooks": "apply the configured command checks",
    "publication-safety": "apply the customized publication scan",
    "records": "write free text in the configured language",
}


def reading_pointer_ids(values: dict[str, str]) -> list[str]:
    """Pointers for active departures from defaults, with recorded IDs for edit detection."""
    if "_reading_pointers" in values:
        return values["_reading_pointers"].split(",")
    guards = enabled_guards(values)
    selected = {
        "workflow-unified": values["workflow"] != SETTING["workflow"].default,
        "verification": values["verification"] != "self" and (
            values["verification"] != SETTING["verification"].default or values["reviewer"] != "off"),
        "staged-items": values["item_size"] == "staged",
        "git-sync": values["git"] != "off",
        "research-guards": bool(guards),
        "decision-guards": bool(guards & {"G5", "G6", "GD", "G8", "G11", "G12"}),
        "competition": values["profile"] == "competition",
        "plan-collector": values["collector"] != "off",
        "external-actions": values["external_actions"] != "none",
        "hooks": values["enforcement"] != "off" or values["read_bound"] != "off" or values["brief_requirements"] != "none",
        "publication-safety": values["publish_scan"] not in {"none", SETTING["publish_scan"].default},
        "records": values["language"] != SETTING["language"].default,
    }
    return [key for key, active in selected.items() if active] or ["none"]


def reading_pointers(values: dict[str, str]) -> str:
    return ("\n".join(f"- `references/{key}.md` — {READING_POINTERS[key]}."
                      for key in reading_pointer_ids(values) if key in READING_POINTERS)
            or "No additional references are active.")


def settings_block(values: dict[str, str]) -> str:
    """Keep common decisions visible and collapse inactive defaults without losing stored policy."""
    visible, defaults = [], []
    identity = {"preset", "profile", "workflow", "verification", "item_size", "guards", "environment",
                "language", "platform_mode", "platforms"}
    for setting in SETTINGS:
        compact_platform = values["platform_mode"] == "single"
        if compact_platform and setting.key == "platform_mode":
            continue
        value = values[setting.key]
        if compact_platform and setting.key == "platforms":
            value = "single — " + value
        nondefault = value != default_value(setting.key, values)
        active = value not in {"off", "none", "auto"} and setting.key in {"enforcement", "publish_scan"}
        target = visible if setting.key in identity or nondefault or active else defaults
        target.append(f"- {setting.label}: {value}")
    if defaults:
        visible += ["", "<details>", "<summary>Inactive and default settings (expand to edit)</summary>", "", *defaults, "", "</details>"]
    return "\n".join(visible)


def active_modules(values: dict[str, str]) -> list[str]:
    modules = []
    if values["item_size"] == "staged":
        modules.append("staged items")
    if values["git"] != "off":
        modules.append(f"git sync ({values['git']})")
    guards = enabled_guards(values)
    if guards:
        modules.append("evidence guards (" + ", ".join(guard for guard in GUARD_IDS if guard in guards) + ")")
    if values["profile"] == "competition":
        modules.append("competition")
    return modules


def summary_line(values: dict[str, str]) -> str:
    modules = ", ".join(active_modules(values)) or "none"
    return (f"Summary: preset {values['preset']} · workflow {values['workflow']} · "
            f"verification {values['verification']} · active modules: {modules}")


def describe(values: dict[str, str]) -> str:
    description = "; ".join(f"{setting.label.lower()} {values[setting.key]}" for setting in SETTINGS)
    if "external.gate" in values["block"].split(", "):
        if values["external_actions"] == "none":
            description += "; external gate inactive: no command patterns (configure --external-actions to enable)"
        elif values["enforcement"] != "block":
            description += "; external gate does not block: Enforcement is " + values["enforcement"]
    return description
