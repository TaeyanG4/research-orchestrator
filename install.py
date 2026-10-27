#!/usr/bin/env python3
"""Install Research Orchestrator for Claude Code and/or Codex (stdlib only, idempotent).

Requires Python 3.12+ (the CI-tested minimum for runtime and development tools).

User scope (default):
  Claude Code  ~/.claude/skills/research-orchestrator, hooks merged into ~/.claude/settings.json
  Codex        ~/.codex/skills/research-orchestrator and ~/.agents/skills/research-orchestrator,
               hooks merged into ~/.codex/hooks.json (trust them in Codex with /hooks)
Project scope (--project DIR), for sharing by committing .claude/:
  Claude Code  DIR/.claude/skills/research-orchestrator, hooks in DIR/.claude/settings.json
  Codex        DIR/.codex/skills and DIR/.agents/skills/research-orchestrator,
               hooks in DIR/.codex/hooks.json
  Git          DIR's pre-push hook runs the authoritative publication scan

Hooks call the installed wrappers by absolute path (project Claude settings use
$CLAUDE_PROJECT_DIR, so a committed .claude/ works in every checkout). Existing hooks stay;
a settings file is backed up before it changes. A replaced or uninstalled skill folder, an
install under the previous skill-only name and an uninstalled pre-push registration are moved
to a timestamped backup folder, never deleted. Rerunning with the same files changes nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MIN_PYTHON = (3, 12)


def require_python(version=None) -> None:
    if (version or sys.version_info)[:2] < MIN_PYTHON:
        raise SystemExit("install.py: Python 3.12+ is required; use a supported interpreter")


require_python()

NAME = "research-orchestrator"
OLD_NAME = NAME + "-skill"
REPO = Path(__file__).resolve().parent
SOURCE = REPO / "skills" / "research-orchestrator"
HOOKS = REPO / "hooks"
sys.path.insert(0, str(SOURCE / "scripts"))
from ro_proc import no_window_flags
from ro_command import literal
from ro_settings import read_settings
WRAPPERS = ("ro-hook.sh", "ro-hook.cmd")
IGNORED = ("evals", "__pycache__", "*.pyc")
# Hook commands that reference these wrapper folders belong to this installer.
OWNED = (f"/{NAME}/hooks/ro-hook.", f"/{OLD_NAME}/hooks/ro-hook.")
PRE_PUSH_MARK = "# research-orchestrator pre-push gate (install.py)"
PRE_PUSH_DISPATCH_MARK = "# research-orchestrator scoped pre-push dispatcher v1 (install.py)"
SHIM_MARK = "research-orchestrator CLI shim (install.py)"


def posix(path: Path) -> str:
    return path.resolve().as_posix()


class Installer:
    def __init__(self, args: argparse.Namespace):
        self.dry_run = args.dry_run
        self.uninstall = args.uninstall
        self.remove_hooks = args.remove_hooks
        self.hooks = not args.no_hooks
        self.hosts = ("claude-code", "codex") if args.host == "both" else (args.host,)
        self.stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.project = Path(args.project).resolve() if args.project else None
        self.home = Path(args.home).resolve() if args.home else Path.home()
        self.custom_home = bool(args.home)
        self.shim = args.shim
        self.shim_only = args.shim_only
        if self.shim_only:
            self.hooks = False
        self.notes: list[str] = []

    # ---------- small actions ----------

    def say(self, text: str) -> None:
        print(("[dry-run] " if self.dry_run else "") + text)

    def backup_root(self, base: Path) -> Path:
        return base / "research-orchestrator-backups"

    def move_aside(self, path: Path, backups: Path, label: str) -> None:
        """Never delete: move an existing file or folder into a timestamped backup folder."""
        destination = backups / f"{label}-{self.stamp}"
        counter = 1
        while destination.exists():
            destination = backups / f"{label}-{self.stamp}-{counter}"
            counter += 1
        self.say(f"move {path} -> {destination}")
        if not self.dry_run:
            backups.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(destination))

    def stage(self, parent: Path) -> Path:
        staged = Path(tempfile.mkdtemp(prefix=f".{NAME}-", dir=parent))
        target = staged / NAME
        shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns(*IGNORED))
        (target / "hooks").mkdir(exist_ok=True)
        for name in WRAPPERS:
            shutil.copy2(HOOKS / name, target / "hooks" / name)
            if name.endswith(".sh"):
                (target / "hooks" / name).chmod(0o755)
        (target / "scripts" / "ro").chmod(0o755)
        # A team that commits .claude/ should not commit bytecode caches written by the hooks.
        (target / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8", newline="\n")
        return target

    @staticmethod
    def same_tree(left: Path, right: Path) -> bool:
        def files(root: Path) -> list[str]:
            return sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                          if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
        names = files(left)
        return names == files(right) and all(
            filecmp.cmp(left / name, right / name, shallow=False) for name in names)

    def install_skill(self, skills: Path, backups: Path) -> Path:
        target = skills / NAME
        if self.remove_hooks:
            return target
        old = skills / OLD_NAME
        if old.exists():
            self.move_aside(old, backups, OLD_NAME)
        if self.uninstall:
            if target.exists():
                self.move_aside(target, backups, NAME)
            return target
        if self.dry_run:
            self.say(f"install skill {SOURCE} -> {target}")
            return target
        skills.mkdir(parents=True, exist_ok=True)
        staged = self.stage(skills)
        try:
            if target.exists() and self.same_tree(target, staged):
                self.say(f"skill unchanged: {target}")
                return target
            if target.exists():
                self.move_aside(target, backups, NAME)
            self.say(f"install skill -> {target}")
            shutil.move(str(staged), str(target))
        finally:
            # Only this run's own temporary staging folder is removed.
            shutil.rmtree(staged.parent, ignore_errors=True)
        return target

    # ---------- hook settings ----------

    @staticmethod
    def owned(entry: object) -> bool:
        hooks = entry.get("hooks", []) if isinstance(entry, dict) else []
        return any(isinstance(hook, dict) and any(mark in str(hook.get("command", "")) + str(hook.get("commandWindows", ""))
                                                  for mark in OWNED) for hook in hooks)

    @classmethod
    def preserve_foreign_hooks(cls, entry: object) -> object | None:
        if not cls.owned(entry):
            return entry
        remaining = [hook for hook in entry["hooks"] if not cls.owned({"hooks": [hook]})]
        return {**entry, "hooks": remaining} if remaining else None

    def merge(self, path: Path, template: dict | None, backups: Path) -> None:
        """Replace this installer's hook entries in one settings file, keeping every other entry."""
        if path.exists():
            try:
                document = json.loads(path.read_text(encoding="utf-8") or "{}")
            except ValueError as exc:
                raise SystemExit(f"install.py: {path} is not valid JSON ({exc}); fix it and rerun") from None
            if not isinstance(document, dict) or not isinstance(document.get("hooks", {}), dict):
                raise SystemExit(f"install.py: {path} has an unexpected shape; fix it and rerun")
        else:
            if template is None:
                return
            document = {}
        current = json.loads(json.dumps(document))
        hooks = current.setdefault("hooks", {})
        for event in list(hooks):
            if isinstance(hooks[event], list):
                hooks[event] = [kept for entry in hooks[event]
                                if (kept := self.preserve_foreign_hooks(entry)) is not None]
                if not hooks[event]:
                    del hooks[event]
        for event, entries in (template or {}).items():
            hooks.setdefault(event, []).extend(entries)
        if current == document:
            self.say(f"hooks unchanged: {path}")
            return
        self.say(f"{'remove' if template is None else 'merge'} research-orchestrator hooks in {path}")
        if self.dry_run:
            return
        if path.exists():
            backup = path.with_name(f"{path.name}.bak-{self.stamp}")
            counter = 1
            while backup.exists():
                backup = path.with_name(f"{path.name}.bak-{self.stamp}-{counter}")
                counter += 1
            shutil.copy2(path, backup)
            self.say(f"backup {path} -> {backup}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, path)

    def claude_template(self, prefix: str) -> dict:
        template = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        portable = prefix.startswith("${CLAUDE_PROJECT_DIR}/")
        path = prefix + "/hooks/ro-hook.sh"
        quoted = '"' + path + '"' if portable else literal(path)
        for entries in template.values():
            for entry in entries:
                for hook in entry["hooks"]:
                    hook["command"] = hook["command"].replace('"${CLAUDE_PLUGIN_ROOT}/hooks/ro-hook.sh"', quoted)
        policy = self.project_hook_policy()
        enabled = []
        if policy is not None:
            if policy.get("autonomy", "present") == "away":
                enabled.append("AskUserQuestion")
            if policy.get("brief_requirements", "none") != "none":
                enabled.append("Agent")
            self.notes.append("Claude Code project matchers follow Autonomy and Brief requirements at installation; "
                              "rerun install.py --project <project> --host claude-code after changing either setting.")
        subscriptions = [enabled, ["Glob", "Grep", "Read"] if self.read_bound() else []]
        covered = {name for entry in template["PreToolUse"] for name in entry["matcher"].split("|")}
        for names in subscriptions:
            remaining = [name for name in names if name not in covered]
            if remaining:
                # Policy checks need the ordinary runner; the edit shortcut can
                # exit before those checks. Select by tool, not declaration order.
                general = next(entry for entry in template["PreToolUse"] if "Bash" in entry["matcher"].split("|"))
                entry = json.loads(json.dumps(general))
                entry["matcher"] = "|".join(remaining)
                template["PreToolUse"].append(entry)
                covered.update(remaining)
        return template

    def project_hook_policy(self) -> dict | None:
        """Only a readable project policy can enable optional tool subscriptions."""
        if self.project is None:
            return None
        try:
            stored = read_settings((self.project / "agents.md").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return stored.values if stored.has_section else None

    def read_bound(self) -> bool:
        """Read registrations cost a process launch, so add them only for explicit project policy."""
        return (self.project_hook_policy() or {}).get("read_bound") == "on"

    def codex_template(self, skill: Path) -> dict:
        template = json.loads((HOOKS / "codex-hooks.sample.json").read_text(encoding="utf-8"))["hooks"]
        for event, entries in template.items():
            for entry in entries:
                for hook in entry["hooks"]:
                    for field, suffix, shell in (("command", "sh", "sh"), ("commandWindows", "cmd", "powershell")):
                        source = f'"/absolute/path/to/plugin/hooks/ro-hook.{suffix}"'
                        wrapper = literal(posix(skill) + f"/hooks/ro-hook.{suffix}", shell)
                        hook[field] = hook[field].replace(source, wrapper)
                        if self.project is not None and event == "SessionStart":
                            # No documented Codex project-root substitution is assumed.
                            # Keep recovery outside the missing wrapper itself.
                            retry = "python " + literal(posix(REPO / "install.py"), shell) + " --project . --host codex"
                            payload = json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                "additionalContext": "Hooks inactive: registered installation is missing. From the moved project root, run: " + retry}})
                            quoted = literal(payload, shell)
                            if shell == "sh":
                                hook[field] = f"if [ -f {wrapper} ]; then {hook[field]}; else printf '%s\\n' {quoted}; fi"
                            else:
                                hook[field] = f"if (Test-Path -LiteralPath {wrapper} -PathType Leaf) {{ {hook[field]} }} else {{ Write-Output {quoted} }}"
        return template

    def runtime(self, base: Path | None = None) -> Path | None:
        """Prefer the requested update, then a runtime surviving this operation."""
        current_scope = base is None
        base = base or self.project or self.home
        folders = {"claude-code": ".claude", "codex": ".codex"}
        hosts = (*self.hosts, *(host for host in folders if host not in self.hosts))
        for host in hosts:
            folder = folders[host]
            target = base / folder / "skills" / NAME
            if current_scope and self.uninstall and host in self.hosts:
                continue
            projected = current_scope and self.dry_run and not self.uninstall and host in self.hosts
            if (target / "scripts/ro.py").is_file() or projected:
                return target
        return None

    def shim_registrations(self, scope: str, skill: Path | None) -> dict[str, str]:
        """Retain usable runtimes across scopes so one uninstall cannot strand ro."""
        path = self.home / ".ro/cli-shim-registrations.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            saved = document.get("registrations", {}) if isinstance(document, dict) else {}
        except (OSError, ValueError):
            saved = {}
        registrations = {key: value for key, value in saved.items()
                         if isinstance(key, str) and isinstance(value, str)
                         and (Path(value) / "scripts/ro.py").is_file()} if isinstance(saved, dict) else {}
        # Discover a user install made before registration tracking was introduced.
        if scope != str(self.home) and str(self.home) not in registrations:
            if runtime := self.runtime(self.home):
                registrations[str(self.home)] = posix(runtime)
        if skill is None:
            registrations.pop(scope, None)
        else:
            registrations[scope] = posix(skill)
        content = json.dumps({"version": 1, "registrations": registrations}, indent=2) + "\n"
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            self.say(f"update CLI runtime registrations: {path}")
            if not self.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
                temporary.write_text(content, encoding="utf-8", newline="\n")
                os.replace(temporary, path)
        return registrations

    def cli_shim(self, skill: Path | None, backups: Path) -> None:
        if self.remove_hooks:
            return
        if os.name == "nt":
            base = (self.home / "AppData/Local" if self.custom_home else
                    Path(os.environ.get("LOCALAPPDATA", str(self.home / "AppData/Local"))))
            path = base / "Programs/ro/ro.cmd"
        else:
            path = self.home / ".local/bin/ro"
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        ours = SHIM_MARK in existing
        # A project uninstall must not redirect a shim belonging to another scope.
        scope = str(SOURCE if self.shim_only else self.project or self.home)
        registrations = self.shim_registrations(scope, skill)
        recorded_scope = next((line.partition("ro-shim-scope-hex: ")[2] for line in existing.splitlines()
                               if "ro-shim-scope-hex: " in line), "")
        try:
            scoped = ours and bytes.fromhex(recorded_scope).decode("utf-8") == scope
        except (ValueError, UnicodeError):
            scoped = False
        if self.uninstall and not scoped:
            return
        if not self.shim and not (self.uninstall and scoped):
            return
        if skill is None and self.uninstall and registrations:
            scope, runtime = next(reversed(registrations.items()))
            skill = Path(runtime)
        if skill is None:
            if ours and scoped:
                self.move_aside(path, backups, "ro-shim")
            return
        if os.name == "nt":
            command = f'{literal(str(Path(sys.executable).resolve()), "cmd")} -E -S {literal(str((skill / "scripts/ro.py").resolve()), "cmd")} %*'
            script = (f"@echo off\nrem {SHIM_MARK}\nrem ro-shim-scope-hex: {scope.encode('utf-8').hex()}\n"
                      f"setlocal DisableDelayedExpansion\n{command}\nexit /b %errorlevel%\n")
        else:
            script = (f"#!/bin/sh\n# {SHIM_MARK}\n# ro-shim-scope-hex: {scope.encode('utf-8').hex()}\n"
                      f"exec {literal(posix(Path(sys.executable)))} -E -S "
                      f'{literal(posix(skill / "scripts/ro.py"))} "$@"\n')
        if script == existing:
            self.say(f"CLI shim unchanged: {path}")
            return
        if existing and not ours:
            self.move_aside(path, backups, "ro-shim")
        self.say(f"write CLI shim {path}")
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(script, encoding="utf-8", newline="\n")
            path.chmod(0o755)
        self.notes.append(f"CLI shim: {path}; add its directory to PATH if needed.")

    # ---------- Git pre-push ----------

    def validate_project_root(self) -> None:
        """A gate registration and Git's dispatcher must identify the same checkout."""
        if self.project is None:
            return
        if not self.project.is_dir():
            raise SystemExit(f"install.py: project folder not found: {self.project}")
        try:
            root = subprocess.run(["git", "-C", str(self.project), "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True, check=True,
                                  creationflags=no_window_flags()).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return  # Non-Git projects still support skill and host-hook installation.
        if self.project != Path(root).resolve():
            raise SystemExit("install.py: --project must name the Git repository root, not a nested folder; "
                             f"from {root}, rerun python install.py --project .")

    def pre_push(self, skill: Path | None, backups: Path) -> None:
        if self.remove_hooks:
            return  # hooks-only remediation preserves the publication gate
        try:
            hooks = subprocess.run(["git", "-C", str(self.project), "rev-parse", "--git-path", "hooks"],
                                   capture_output=True, text=True, check=True,
                                   creationflags=no_window_flags()).stdout.strip()
            gitdir = subprocess.run(["git", "-C", str(self.project), "rev-parse", "--absolute-git-dir"],
                                    capture_output=True, text=True, check=True,
                                    creationflags=no_window_flags()).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            self.notes.append(f"Git pre-push gate not installed: {self.project} is not a Git repository.")
            return
        path = (self.project / hooks / "pre-push").resolve()
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        state = path.parent / "research-orchestrator"
        scope = os.path.normcase(str(self.project.resolve()))
        key = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        registration = state / "registrations" / (key + ".json")
        # Git's private directory distinguishes linked worktrees even when their
        # hooks are shared. It retains the expectation if a registration is lost.
        expected = Path(gitdir) / "research-orchestrator-pre-push"
        if skill is None:
            if registration.exists():
                self.move_aside(registration, backups, "pre-push-registration")
            if expected.exists():
                self.move_aside(expected, backups, "pre-push-expectation")
            return
        # The dispatcher also needs a usable interpreter after a Python upgrade.
        # Probe before exec; never retry a gate that ran and rejected publication.
        script = (f"#!/bin/sh\n{PRE_PUSH_MARK}\n{PRE_PUSH_DISPATCH_MARK}\n"
                  'ro_remote=${1-}\nro_url=${2-}\n'
                  'ro_dispatch() {\n'
                  '  "$@" -E -S -c "import sys; sys.exit(sys.version_info < (3, 12))" </dev/null >/dev/null 2>&1 || return 1\n'
                  f'  exec "$@" -E -S {literal(posix(state / "pre-push.py"))} "$ro_remote" "$ro_url"\n'
                  '}\n'
                  f'ro_dispatch {literal(posix(Path(sys.executable)))}\n'
                  '[ -z "${RO_HOOK_PYTHON-}" ] || ro_dispatch "$RO_HOOK_PYTHON"\n'
                  'ro_dispatch python3\nro_dispatch python\nro_dispatch py -3\n'
                  'echo "research-orchestrator pre-push failed: no working Python 3.12+ interpreter; set RO_HOOK_PYTHON" >&2\n'
                  'exit 1\n')
        if existing and PRE_PUSH_DISPATCH_MARK not in existing:
            self.notes.append("Existing pre-push hook left intact (including legacy installations). "
                              "Integrate hooks/pre-push.sample into it, preserving Git's stdin and arguments; "
                              "the publication gate was not installed automatically.")
            return
        data = {"scope": scope, "python": posix(Path(sys.executable)), "runtime": posix(skill / "scripts/ro.py")}
        files = {expected: scope + "\n", path: script,
                 state / "pre-push.py": (HOOKS / "ro-pre-push.py").read_text(encoding="utf-8"),
                 registration: json.dumps(data, indent=2) + "\n"}
        for target, content in files.items():
            if target.is_file() and target.read_text(encoding="utf-8") == content:
                self.say(f"pre-push unchanged: {target}")
                continue
            self.say(f"write Git pre-push registration or dispatcher {target}")
            if not self.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
                temporary.write_text(content, encoding="utf-8", newline="\n")
                os.replace(temporary, target)
        if not self.dry_run:
            path.chmod(0o755)

    # ---------- scopes ----------

    def plugin_active(self, host: str) -> bool:
        # Claude's enabledPlugins setting is authoritative; merely having a cache
        # directory is not proof that hooks are active in this scope.
        if host != "claude-code":
            return False
        paths = [self.home / ".claude/settings.json"]
        if self.project:
            paths += [self.project / ".claude/settings.json", self.project / ".claude/settings.local.json"]
        enabled = {}
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                enabled.update(data.get("enabledPlugins", {}))
            except (OSError, ValueError, TypeError):
                continue
        return any(value is True and key.split("@", 1)[0] == NAME for key, value in enabled.items())

    def hook_template(self, host: str, template: dict) -> dict | None:
        if self.uninstall or self.remove_hooks:
            return None
        if self.plugin_active(host):
            self.notes.append(f"{host}: active plugin supplies hooks; removed duplicate manual registrations.")
            # These shipped matchers are literal alternatives. Subtract their
            # coverage so project-enabled tools absent from the plugin keep checks.
            plugin = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
            supplemental = {}
            for event, entries in template.items():
                provided = plugin.get(event, [])
                if any(not entry.get("matcher") for entry in provided):
                    continue
                covered = {name for entry in provided for name in entry["matcher"].split("|")}
                kept = []
                for entry in entries:
                    remaining = [name for name in dict.fromkeys(entry.get("matcher", "").split("|"))
                                 if name not in covered]
                    if remaining:
                        kept.append({**entry, "matcher": "|".join(remaining)} if entry.get("matcher") else entry)
                        covered.update(remaining)
                if kept:
                    supplemental[event] = kept
            return supplemental or None
        return template

    def run(self) -> int:
        if not (SOURCE / "SKILL.md").is_file():
            raise SystemExit("install.py: run it from a research-orchestrator checkout")
        self.validate_project_root()
        if self.shim_only:
            self.cli_shim(SOURCE, self.backup_root(self.home / ".ro"))
            self.notes.append("Shim only: uses this checkout's runtime; keep the checkout available.")
            self.report()
            return 0
        if self.project is not None:
            backups = self.backup_root(self.project / ".ro")
            if "claude-code" in self.hosts:
                self.install_skill(self.project / ".claude" / "skills", backups)
                if self.hooks:
                    prefix = "${CLAUDE_PROJECT_DIR}/.claude/skills/" + NAME
                    self.merge(self.project / ".claude" / "settings.json",
                               self.hook_template("claude-code", self.claude_template(prefix)), backups)
            if "codex" in self.hosts:
                skill = self.install_skill(self.project / ".codex" / "skills", backups)
                self.install_skill(self.project / ".agents" / "skills", backups)
                if self.hooks:
                    self.merge(self.project / ".codex" / "hooks.json",
                               self.hook_template("codex", self.codex_template(skill)), backups)
            if self.hooks:
                self.pre_push(self.runtime(), backups)
            self.cli_shim(self.runtime(), backups)
            if "codex" in self.hosts and not self.uninstall:
                self.notes.append("Only .claude/ is shareable across checkout paths. Codex project hooks use absolute "
                                  "paths; rerun install.py --project after moving or cloning the project.")
        else:
            if "claude-code" in self.hosts:
                base = self.home / ".claude"
                skill = self.install_skill(base / "skills", self.backup_root(base))
                if self.hooks:
                    self.merge(base / "settings.json",
                               self.hook_template("claude-code", self.claude_template(posix(skill))), self.backup_root(base))
            if "codex" in self.hosts:
                skills = [self.install_skill(self.home / root / "skills", self.backup_root(self.home / root))
                          for root in (".codex", ".agents")]
                if self.hooks:
                    self.merge(self.home / ".codex" / "hooks.json",
                               self.hook_template("codex", self.codex_template(skills[0])),
                               self.backup_root(self.home / ".codex"))
            if self.hooks and not self.uninstall and not self.remove_hooks:
                self.notes.append("Per repository, also install the Git pre-push gate: "
                                  "python install.py --project <repository> (or see references/publication-safety.md).")
            self.cli_shim(self.runtime(), self.backup_root(self.home / ".ro"))
        self.report()
        return 0

    def report(self) -> None:
        if self.remove_hooks:
            self.notes.append("Manual host hooks removed; skill, Git gate and unrelated hooks preserved.")
        elif self.uninstall:
            self.notes.append("Uninstalled; backups keep the removed files.")
        elif self.hooks:
            if "claude-code" in self.hosts:
                self.notes.append("Claude Code: start a new session; `ro brief` should report `hooks active`. "
                                  "Active plugin hooks replace manual registrations automatically; "
                                  "--remove-hooks removes manual host hooks only.")
            if "codex" in self.hosts:
                self.notes.append("Codex: open /hooks and trust the research-orchestrator hooks "
                                  "(enable features.hooks first if your Codex version needs it).")
        for note in self.notes:
            print("note: " + note)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--host", choices=("claude-code", "codex", "both"), default="both")
    result.add_argument("--project", help="install into this project folder instead of your home folder")
    result.add_argument("--dry-run", action="store_true", help="print the actions without changing anything")
    result.add_argument("--uninstall", action="store_true",
                        help="remove the hooks and move the installed skill to a backup folder")
    result.add_argument("--no-hooks", action="store_true", help="skip host and Git hook installation (for example with the plugin)")
    result.add_argument("--shim-only", action="store_true",
                        help="install only the CLI shim pointing to this plugin checkout; copy no skill or hooks")
    shim = result.add_mutually_exclusive_group()
    shim.add_argument("--shim", dest="shim", action="store_true", default=True,
                      help="install the ro CLI shim (default)")
    shim.add_argument("--no-shim", dest="shim", action="store_false",
                      help="skip installing the ro CLI shim")
    result.add_argument("--remove-hooks", action="store_true",
                        help="remove manual host hooks only; preserve skill, Git gate and unrelated hooks")
    result.add_argument("--home", help=argparse.SUPPRESS)  # Tests and sandboxes: a home folder other than ~.
    return result


def main(argv: list[str] | None = None) -> int:
    require_python()
    cli = parser()
    args = cli.parse_args(argv)
    if args.shim_only and (args.uninstall or args.remove_hooks or not args.shim):
        cli.error("--shim-only cannot be combined with --uninstall, --remove-hooks or --no-shim")
    if args.uninstall and args.no_hooks:
        cli.error("--uninstall cannot be combined with --no-hooks; uninstall reconciles owned hooks")
    if args.remove_hooks and (args.uninstall or args.no_hooks):
        cli.error("--remove-hooks cannot be combined with --uninstall or --no-hooks")
    return Installer(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
