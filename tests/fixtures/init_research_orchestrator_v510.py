#!/usr/bin/env python3
"""Create the four Research Orchestrator files without overwriting existing work.

Project settings, written to the top of agents.md:
  --user kim                          the first user to record
  --platform multi|single|adaptive    how many platforms (hosts) work on the project
  --platforms "Claude Code, Codex"    which platforms
  --git push|commit|off               how the coordination files are synced through git
  --collector off|"<platform>/<model>"   plan collector sub-agent, e.g. "Claude Code/sonnet"
  --queue-limits 50,5                 collector stops at 50 plan items and resumes at 5
  --reviewer off|"<platform>/<model>"    reviewer sub-agent for cross-checks, e.g. "Codex/sol"
  --fallback wait|same-host           cross-checks that need another host when none is active

The user may edit the settings lines in agents.md directly. Platform mode, Platforms, and
Git sync change the rules in agents.md, so after editing them run --reconfigure, which
regenerates the rules from the settings in the file (flags override them). It rewrites
only agents.md and refuses when the rules were edited by hand, unless --force is given.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import string
import sys


SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_ROOT / "templates"

# Agent names are work slots, assigned in this order: A ... Z, AA ... ZZ.
AGENT_ORDER = [
    *string.ascii_uppercase,
    *(a + b for a in string.ascii_uppercase for b in string.ascii_uppercase),
]
PLATFORM_MODES = ("multi", "single", "adaptive")
GIT_MODES = ("push", "commit", "off")
FALLBACKS = ("wait", "same-host")
DEFAULT_PLATFORMS = "Claude Code, Codex"
DEFAULT_LIMITS = "stop at 50, resume at 5"
DEFAULT_FALLBACK = {"single": "same-host", "multi": "wait", "adaptive": "same-host"}
RESERVED_USER_NAMES = {"claude", "codex", "gpt", "chatgpt", "gemini", "antigravity", "none", "unassigned", "released"}
USER_NAME = re.compile(r"^[^\W_][\w-]{0,31}$")
IF_LINE_BLOCK = re.compile(r"^\{\{#if (\w+)=([\w,]+)\}\}\n(.*?)^\{\{/if\}\}\n", re.M | re.S)
IF_INLINE_BLOCK = re.compile(r"\{\{#if (\w+)=([\w,]+)\}\}(.*?)\{\{/if\}\}", re.S)

# Settings line label in agents.md -> settings key.
SETTING_LABELS = {
    "Platform mode": "mode",
    "Platforms": "platforms",
    "Git sync": "git",
    "Plan collector": "collector",
    "Plan queue limits": "limits",
    "Reviewer": "reviewer",
    "Cross-check fallback": "fallback",
}


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


def parse_sub_agent(raw: str | None, platforms: str, label: str) -> str:
    """Return 'off' or 'on — <platform> / <model>' from 'off', '<platform>/<model>', or the stored form."""
    if raw is None or raw.strip().lower() == "off":
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


def parse_limits(raw: str | None) -> str:
    if raw is None:
        return DEFAULT_LIMITS
    numbers = re.findall(r"\d+", raw)
    if len(numbers) != 2:
        raise ValueError("--queue-limits must give a stop and a resume count, e.g. 50,5")
    stop, resume = map(int, numbers)
    if not 0 <= resume < stop:
        raise ValueError("--queue-limits needs resume < stop, e.g. 50,5")
    return f"stop at {stop}, resume at {resume}"


def parse_fallback(raw: str | None, mode: str) -> str:
    value = (raw or DEFAULT_FALLBACK[mode]).strip()
    if value not in FALLBACKS:
        raise ValueError(f"--fallback must be one of {', '.join(FALLBACKS)}")
    return value


def agent_sections(names: list[str]) -> str:
    blocks = []
    for name in names:
        blocks.append(
            f"## Agent: {name}\n\n"
            "_No active items yet. Add only actionable unfinished hypotheses or experiments._\n\n"
            "_For each item use the standard hypothesis block including Sources, Hypothesis, Evidence, Improvement, Priority, Resource, Parallel, Other, and Next test._\n"
        )
    return "\n".join(blocks).rstrip() + "\n"


def handoff_agent_sections(names: list[str]) -> str:
    blocks = []
    for name in names:
        blocks.append(
            f"### Agent: {name}\n"
            "- Current host: unassigned\n"
            "- Current user: none\n"
            "- Current thread: none yet\n"
            "- Resumable state: read discoveries, then your own plan section\n"
            "- Blocker: none\n"
            "- Next action: choose the highest-priority item in your plan section\n"
        )
    return "\n".join(blocks).rstrip() + "\n"


def apply_conditions(text: str, conditions: dict[str, str]) -> str:
    """Keep {{#if key=a,b}} ... {{/if}} blocks whose key matches one of the listed values."""
    def keep(match: re.Match[str]) -> str:
        key, values, body = match.groups()
        return body if conditions.get(key) in values.split(",") else ""

    text = IF_LINE_BLOCK.sub(keep, text)
    return IF_INLINE_BLOCK.sub(keep, text)


def render(template_name: str, values: dict[str, str], conditions: dict[str, str]) -> str:
    text = apply_conditions((TEMPLATES / template_name).read_text(encoding="utf-8"), conditions)
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def render_agents(settings: dict[str, str]) -> str:
    values = {
        "{{PROJECT_NAME}}": settings["project"],
        "{{PLATFORM_MODE}}": settings["mode"],
        "{{PLATFORMS}}": settings["platforms"],
        "{{GIT_SYNC}}": settings["git"],
        "{{COLLECTOR}}": settings["collector"],
        "{{QUEUE_LIMITS}}": settings["limits"],
        "{{REVIEWER}}": settings["reviewer"],
        "{{FALLBACK}}": settings["fallback"],
    }
    return render("AGENTS.md.template", values, {"mode": settings["mode"], "git": settings["git"]})


def rules_body(agents_text: str) -> str:
    """Everything after the Project settings section: the part generated from mode and git."""
    match = re.search(r"^## Project settings\n.*?(?=^## )", agents_text, re.M | re.S)
    return agents_text[match.end():] if match else agents_text


def read_settings(agents_md: Path) -> dict[str, str]:
    text = agents_md.read_text(encoding="utf-8")
    settings: dict[str, str] = {}
    title = re.match(r"^# (.+) — Agent Rules$", text.splitlines()[0] if text else "")
    if title:
        settings["project"] = title.group(1)
    for label, key in SETTING_LABELS.items():
        match = re.search(rf"^- {re.escape(label)}: (.+)$", text, re.M)
        if match:
            settings[key] = match.group(1).strip()
    return settings


def generated_by_template(agents_text: str, project: str) -> bool:
    """True when the rules match some mode/git rendering, i.e. they were not edited by hand."""
    body = rules_body(agents_text)
    sample = {"project": project, "platforms": DEFAULT_PLATFORMS, "collector": "off",
              "limits": DEFAULT_LIMITS, "reviewer": "off", "fallback": "wait"}
    return any(
        rules_body(render_agents({**sample, "mode": mode, "git": git})) == body
        for mode in PLATFORM_MODES for git in GIT_MODES
    )


def build_settings(args: argparse.Namespace, base: dict[str, str], project: str) -> dict[str, str]:
    """Combine flags (highest), settings already in agents.md, and defaults; validate everything."""
    mode = args.platform or base.get("mode") or "adaptive"
    if mode not in PLATFORM_MODES:
        raise ValueError(f"Platform mode '{mode}' must be one of {', '.join(PLATFORM_MODES)}")
    git = args.git or base.get("git") or "off"
    if git not in GIT_MODES:
        raise ValueError(f"Git sync '{git}' must be one of {', '.join(GIT_MODES)}")
    platforms = parse_platforms(args.platforms if args.platforms is not None else base.get("platforms"), mode)
    return {
        "project": project,
        "mode": mode,
        "platforms": platforms,
        "git": git,
        "collector": parse_sub_agent(args.collector if args.collector is not None else base.get("collector"),
                                     platforms, "collector"),
        "limits": parse_limits(args.queue_limits if args.queue_limits is not None else base.get("limits")),
        "reviewer": parse_sub_agent(args.reviewer if args.reviewer is not None else base.get("reviewer"),
                                    platforms, "reviewer"),
        "fallback": parse_fallback(args.fallback if args.fallback is not None else base.get("fallback"), mode),
    }


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


def describe(settings: dict[str, str]) -> str:
    return (f"platform mode {settings['mode']}; platforms {settings['platforms']}; git sync {settings['git']}; "
            f"plan collector {settings['collector']} ({settings['limits']}); reviewer {settings['reviewer']}; "
            f"cross-check fallback {settings['fallback']}")


def reconfigure(target: Path, args: argparse.Namespace) -> int:
    agents_md = target / "agents.md"
    if not agents_md.is_file():
        print(f"Error: {agents_md} does not exist; run without --reconfigure first", file=sys.stderr)
        return 1
    current = read_settings(agents_md)
    project = args.name or current.get("project", target.name)
    if not args.force:
        if "mode" not in current or "git" not in current:
            print("Error: agents.md has no Project settings; it predates this version. "
                  "Re-run with --force to replace it.", file=sys.stderr)
            return 1
        if not generated_by_template(agents_md.read_text(encoding="utf-8"), current.get("project", project)):
            print("Error: the rules in agents.md were edited by hand, so regenerating them would lose those edits. "
                  "Save your edits elsewhere, then re-run with --force.", file=sys.stderr)
            return 1
    settings = build_settings(args, current, project)
    settings["git"] = git_mode_for(target, settings["git"])
    agents_md.write_text(render_agents(settings), encoding="utf-8", newline="\n")
    print(f"[REWRITE] {agents_md}")
    print(f"Settings: {describe(settings)}")
    print("Log the change as a handoff event with heading 'none', then run check_project.py.")
    return 0


def main() -> int:
    # Settings contain '—'; never crash on a legacy console code page such as cp949.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Initialize Research Orchestrator files.")
    parser.add_argument("target", nargs="?", default=".", help="Project directory")
    parser.add_argument("-n", "--name", help="Project name (defaults to directory name)")
    parser.add_argument("--agents", help="Agent count (e.g. 2 -> A,B) or comma-separated names from A-Z, AA-ZZ")
    parser.add_argument("--user", help="First user to record, e.g. kim or user1")
    parser.add_argument("--platform", help="multi: several platforms at once; single: one platform; adaptive: changes over time (default)")
    parser.add_argument("--platforms", help=f"Comma-separated platforms (default: {DEFAULT_PLATFORMS}; single needs exactly one)")
    parser.add_argument("--git", help="push: commit and push automatically; commit: local commits only; off: no git (default)")
    parser.add_argument("--collector", help="Plan collector sub-agent: off (default) or \"<platform>/<model>\", e.g. \"Claude Code/sonnet\"")
    parser.add_argument("--queue-limits", help="Collector stop and resume counts, e.g. 50,5 (default)")
    parser.add_argument("--reviewer", help="Reviewer sub-agent: off (default) or \"<platform>/<model>\", e.g. \"Codex/sol\"")
    parser.add_argument("--fallback", help="wait or same-host (default: wait for multi, same-host otherwise)")
    parser.add_argument("--reconfigure", action="store_true", help="Regenerate only agents.md from its settings and any flags")
    parser.add_argument("--force", action="store_true", help="With --reconfigure, replace hand-edited rules")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"Error: target directory does not exist: {target}", file=sys.stderr)
        return 1

    try:
        if args.reconfigure:
            return reconfigure(target, args)
        agents = parse_agents(args.agents)
        user = parse_user(args.user)
        name = args.name or target.name
        settings = build_settings(args, {}, name)
        settings["git"] = git_mode_for(target, settings["git"])
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    values = {
        "{{PROJECT_NAME}}": name,
        "{{AGENT_NAMES}}": ", ".join(agents),
        "{{USERS}}": user or "none yet",
        "{{AGENT_SECTIONS}}": agent_sections(agents),
        "{{HANDOFF_AGENT_SECTIONS}}": handoff_agent_sections(agents),
    }
    conditions = {"mode": settings["mode"], "git": settings["git"]}

    created = 0
    created += write_if_missing(target / "agents.md", render_agents(settings)) == "create"
    for template, filename in (
        ("PLAN.md.template", "plan.md"),
        ("DISCOVERIES.md.template", "discoveries.md"),
        ("HANDOFF.md.template", "handoff.md"),
    ):
        created += write_if_missing(target / filename, render(template, values, conditions)) == "create"

    print(f"Done. Created {created} file(s). Existing files were preserved.")
    print(f"Settings: {describe(settings)}; user {user or 'none yet'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
