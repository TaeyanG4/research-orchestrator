# Hook installation and capabilities

Read this when installing or repairing hooks; use [hooks.md](hooks.md) during work. Dated host observations, trust-probe limitations and measurement caveats live in the repository’s `docs/evals/README.md` evidence index.

## Lookup: install and trust

Run `python install.py --host claude-code` to install the runtime and register hooks so the host can deliver checks; use `--host codex` or `--host both` for those hosts.

Claude home and plugin registrations subscribe to `Bash|PowerShell|Edit|Write|NotebookEdit` before tool use; they omit `AskUserQuestion`, `Agent` and read tools to avoid shell and Python startup for inactive checks. Project installation adds `AskUserQuestion` for `Autonomy: away`, `Agent` for configured `Brief requirements`, and `Glob|Grep|Read` for `Read bound: on`. Run `python install.py --project .` from the repository root after changing these settings; SessionStart names missing subscriptions when only the plugin is registered. With an active plugin, that command retains the enabled supplemental tools without duplicating plugin registrations. Edit/Write stay subscribed because a new running job can establish bindings at any time.

Copying the skill alone does not install hooks. Run `python install.py --host claude-code`, `--host codex` or `--host both`; the Codex plugin alone does not register host hooks. Add `--project <dir>` for team scope, `--dry-run` to inspect changes, or `--uninstall` to remove one installation with backups. The installer preserves unrelated hooks and backs up changed settings and previous skill installs. Nested `--project` paths are refused before writes; use the Git repository root. Lost expected registrations refuse pushes with repair guidance. Project installs register their checkout with one shared Git pre-push dispatcher, so linked worktrees and repositories sharing `core.hooksPath` retain separate runtimes. Partial uninstall repoints only that checkout; full uninstall removes only its registration, leaving the inert dispatcher available to other scopes. An existing custom or legacy hook stays intact, with instructions to integrate `hooks/pre-push.sample` manually; no automatic gate is claimed for that case.

Project Claude wrappers use `CLAUDE_PROJECT_DIR`, so committed `.claude/` configuration is shareable. Codex project-relative command resolution is unverified: its installed commands use absolute paths, and `.codex/hooks.json` needs reinstallation after checkout relocation. If the registered wrapper is missing, SessionStart prints the exact reinstall command to run from the moved project root. Codex also receives `.agents/skills`. Plugin users run `python install.py --shim-only` from their plugin checkout; the shim points at that checkout’s runtime without copying the skill or changing hooks. Keep the checkout available while using its shim. The default shim (`--shim`, opt out with `--no-shim`) writes `ro` to `~/.local/bin/ro` on POSIX or `%LOCALAPPDATA%/Programs/ro/ro.cmd` on Windows, and SessionStart prints an exact resolved command prefix for the current installation.

Claude Code's plugin uses `hooks/hooks.json` and the shell wrapper (Git Bash on Windows). Active plugin registration suppresses duplicate manual hooks. `--remove-hooks` removes only manual registrations, preserving skills, the Git gate and unrelated hooks. Codex reads `.codex/hooks.json`; trust it through `/hooks` and enable `features.hooks` if needed. Hook trust and project trust authorize different configuration layers; neither proves event delivery.

Inspect `ro brief` at startup, resume and compaction. Without a self-test record it says `hooks not installed — run install.py (or the Claude Code plugin)`; a failed record says `hooks inactive: <reason>`. A successful adapter self-test cannot prove every host event reaches it. In a disposable project, check harmless calls, warnings, denials, edits, Stop and startup/resume/compact, including side effects. Failure, timeout and missing-Python probes distinguish fail-open per-call hooks from the configured fail-closed Git gate.

The installed Git bootstrap and dispatcher try their registered interpreter, then `RO_HOOK_PYTHON`, `python3`, `python`, and `py -3`. If none is usable Python 3.12+, it refuses the push with a repair message. A scanner denial is final; it never triggers an interpreter retry.

## Lookup: diagnostics

Read `ro brief` for the adapter self-test so missing registration can be repaired before relying on hook delivery.

The runner's nine-second watchdog fits the host's ten-second limit. Resolved Python dispatches in process, with child dispatch as fallback. The release budget is **150 ms p95**: median of three warmed batch p95s, each with 20 nearest-rank samples. The repository's `docs/evals/README.md` records dated measurements and pending CI evidence.

SessionStart and `ro brief` also report `publish gate not installed` for Git checkouts without their scoped registration under the active hooks path. Run the printed `python <checkout>/install.py --project .` command to install it; plugin per-call hooks alone do not provide the fail-closed publication gate.

Set `RO_HOOK_DIAGNOSTICS=1` or create `.ro/hook-diagnostics.on` to record event, check IDs and decisions without commands or environment values. Remove the marker to disable it. Interpret these records using the evidence index; a self-test alone does not prove host delivery.

## Lookup: adapter behavior

Use `ro hook <event>` to accept host JSON on stdin and return the adapter’s decision; the same checks are available through the `ro` commands on every host.

PreToolUse can deny a certain finding only with `Enforcement: block` and its check in `Block`; other findings warn. PostToolUse checks cannot undo edits. Stop warns about unmonitored jobs by default; an explicit `jobs.unmonitored` Block entry blocks once per job, then warns. Per-call failures fail open. Antigravity has no hook adapter. See [operations-safety.md](operations-safety.md) for job commands and [git-sync.md](git-sync.md) for coordination-file sync.

## Capability matrix

Use this table to distinguish adapter support from observed host delivery. `E/W` can deny only with the policy above; `W` is advisory. Observations are the supplied 2026-10-27 Windows candidate probes, not verification of later repairs: Claude Code 2.1.287 used runner diagnostics, while Codex CLI 0.154.0 used per-invocation trust (`--dangerously-bypass-hook-trust`). Persisted Codex `/hooks` trust was not exercised; ordinary invocations need established trust before hooks can be relied on. Full dated evidence remains in the repository's evidence index.

| Check | Adapter behavior | Claude Code observation | Codex observation | Command or source of truth |
|---|---|---|---|---|
| `shell.background` | E/W | Denial verified | Denial verified | `ro hook PreToolUse` |
| `shell.detach` | E/W | Unverified | Unverified | `ro hook PreToolUse` |
| `shell.heredoc` | E/W | Unverified | Unverified | `ro hook PreToolUse` |
| `shell.cd` | E/W | Unverified | Unverified | `ro hook PreToolUse` |
| `jobs.mutate-bound` | E/W | Denial verified | Denial verified | `ro launch`; `ro hook PreToolUse` |
| `jobs.read-bound` | E/W, opt-in | Warning verified | Warning verified | `ro jobs`; `ro hook PreToolUse` |
| `jobs.unmonitored` | E/W, Stop blocks once per job then warns | Warning verified | Warning verified | `ro jobs`; `ro monitor` |
| `records.timestamp` | W, PostToolUse | Warning verified | Warning verified | `check_project.py` |
| `records.id` | W, PostToolUse | Unverified | Unverified | `ro next-id`; `check_project.py` |
| `publish.scan` | W, capped staged pre-check | Unverified | Unverified | Git pre-push: every outgoing commit; configured failures block |
| `external.gate` | E/W, direct calls | Unverified | Unverified | `ro external`: failed/unavailable validation refuses execution |
| `ask.away` | E/W | Unverified | No declared question-tool mapping | Settings and chat workflow |
| `brief.requirements` | E/W | Unverified | No declared agent-tool mapping | Required lines in the brief |

The sixth probe on each host was benign foreground execution, with no hook decision. Claude's adapter maps Bash, PowerShell, Edit, Write, NotebookEdit, Glob, Grep, Read, AskUserQuestion and Agent; installation subscribes only the active tools described above. The Codex sample maps `Bash` and `apply_patch`. Codex `Bash` with `turn_id` uses the declared shell; Claude's stays Bash. Diagnostics prove a runner decision, while a denial also needs prevented execution and intact protected files; missing diagnostics leave delivery unknown.
