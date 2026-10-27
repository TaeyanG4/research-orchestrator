# Hook installation and capabilities

Read this when installing or repairing hooks; use [hooks.md](hooks.md) during work. Dated host observations, trust-probe limitations and measurement caveats live in the repository’s `docs/evals/README.md` evidence index.

## Lookup: install and trust

Run `python install.py --host claude-code` to install the runtime and register hooks so the host can deliver checks; use `--host codex` or `--host both` for those hosts.

Subscriptions before tool use:

- Claude home and plugin registrations: `Bash|PowerShell|Edit|Write|NotebookEdit|AskUserQuestion|Agent`.
- Question and delegation wrappers return without Python while `Autonomy` is `present` and `Brief requirements` is `none`, so changing either setting needs no reinstall.
- `Read bound: on` adds `Glob|Grep|Read` through project installation; rerun `python install.py --project <checkout root>` after changing that policy. An active plugin keeps these supplements without duplicate registrations.
- Edit/Write stay subscribed because a new running job can establish bindings at any time.

Copying the skill alone does not install hooks, and the Codex plugin alone does not register host hooks:

- Install: `python install.py --host claude-code`, `--host codex` or `--host both`; add `--project <dir>` for team scope, `--dry-run` to inspect changes, `--uninstall` to remove one installation with backups.
- Preservation: unrelated hooks stay; changed settings and previous skill installs are backed up.
- Repository root: nested `--project` paths are refused before writes. Lost expected registrations refuse pushes with repair guidance.
- Shared gate: project installs register their checkout with one Git pre-push dispatcher, so linked worktrees and repositories sharing `core.hooksPath` keep separate runtimes. Partial uninstall repoints only that checkout; full uninstall removes only its registration.
- Custom hooks: an existing custom or legacy hook stays intact, with instructions to integrate `hooks/pre-push.sample`; no automatic gate is claimed then.

Project paths and the `ro` shim:

- Project Claude wrappers use `CLAUDE_PROJECT_DIR`, so committed `.claude/` configuration is shareable.
- Codex project-relative command resolution is unverified: installed commands use absolute paths, so reinstall `.codex/hooks.json` after moving the checkout. A missing registered wrapper makes SessionStart print the exact reinstall command. Codex also receives `.agents/skills`.
- Plugin users run `python install.py --shim-only` from their plugin checkout; the shim points at that checkout's runtime without copying the skill or changing hooks, so keep the checkout available.
- The default shim (`--shim`, opt out with `--no-shim`) writes `ro` to `~/.local/bin/ro` on POSIX or `%LOCALAPPDATA%/Programs/ro/ro.cmd` on Windows; SessionStart prints the resolved command prefix.

- Claude Code's plugin uses `hooks/hooks.json` and the shell wrapper (Git Bash on Windows); active plugin registration suppresses duplicate manual hooks.
- `--remove-hooks` removes only manual registrations, preserving skills, the Git gate and unrelated hooks.
- Codex reads `.codex/hooks.json`; trust it through `/hooks` and enable `features.hooks` if needed. Hook trust and project trust authorize different configuration layers; neither proves event delivery.

- Inspect `ro brief` at startup, resume and compaction. Without a self-test record it says `hooks not installed — run install.py (or the Claude Code plugin)`; a failed record says `hooks inactive: <reason>`.
- A successful adapter self-test cannot prove every host event reaches it. In a disposable project, check harmless calls, warnings, denials, edits, Stop and startup/resume/compact, including side effects.
- Failure, timeout and missing-Python probes distinguish fail-open per-call hooks from the configured fail-closed Git gate.

The installed Git bootstrap and dispatcher try their registered interpreter, then `RO_HOOK_PYTHON`, `python3`, `python`, and `py -3`. If none is usable Python 3.12+, it refuses the push with a repair message. A scanner denial is final; it never triggers an interpreter retry.

## Lookup: diagnostics

Read `ro brief` for the adapter self-test so missing registration can be repaired before relying on hook delivery.

- The runner's nine-second watchdog fits the host's ten-second limit. Resolved Python dispatches in process, with child dispatch as fallback.
- Installed-watchdog and in-process checks keep **p95 < 150 ms**.
- The direct subprocess check requires **hook p95 minus bare-interpreter p95 < 150 ms**, plus **hook p95 < 300 ms**: subtracting startup separates hook work from machine-dependent interpreter cost, while the ceiling catches end-to-end regressions.
- Both subprocess measurements use `python -E -S`, two warm-ups and the median of three 20-sample nearest-rank p95s; the baseline runs `-c "pass"`. The repository's `docs/evals/README.md` records dated measurements and reporting details.

SessionStart and `ro brief` also report `publish gate not installed` for Git checkouts without their scoped registration under the active hooks path. Run the printed `python <checkout>/install.py --project <checkout root>` command, which names the checkout root, to install it; plugin per-call hooks alone do not provide the fail-closed publication gate.

Set `RO_HOOK_DIAGNOSTICS=1` or create `.ro/hook-diagnostics.on` to record event, check IDs and decisions without commands or environment values. Remove the marker to disable it. Interpret these records using the evidence index; a self-test alone does not prove host delivery.

## Lookup: adapter behavior

Use `ro hook <event>` to accept host JSON on stdin and return the adapter’s decision; the same checks are available through the `ro` commands on every host.

PreToolUse can deny a certain finding only with `Enforcement: block` and its check in `Block`; other findings warn. PostToolUse checks cannot undo edits. Stop warns about unmonitored jobs by default; an explicit `jobs.unmonitored` Block entry blocks once per job, then warns. Per-call failures fail open. Antigravity has no hook adapter. See [operations-safety.md](operations-safety.md) for job commands and [git-sync.md](git-sync.md) for coordination-file sync.

Adapter details the daily guide leaves out:

- Publish advisory: the staged pre-check reads the command's checkout under the project's policy. A push that picks its checkout inside the command (`git -C`, `--git-dir`, `--work-tree`, `GIT_DIR`/`GIT_WORK_TREE`, `env -C`, or an earlier directory change) gets an advisory, without scanning the hook directory's staged changes, that defers to that checkout's pre-push gate.
- Binding checks compare each path's lexical and resolved spellings (junctions, symbolic links, Windows short names, macOS `/private/var`).
- The cmd wrapper's settings shortcut recognises space-indented settings lines only; a tab-indented line falls through to Python, which reads it.

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
| `publish.scan` | W, staged pre-check only without a registered Git gate | Unverified | Unverified | Git pre-push: every outgoing commit; configured failures block |
| `external.gate` | E/W, direct calls | Unverified | Unverified | `ro external`: failed/unavailable validation refuses execution |
| `ask.away` | E/W | Unverified | No declared question-tool mapping | Settings and chat workflow |
| `brief.requirements` | E/W | Unverified | No declared agent-tool mapping | Required lines in the brief |

The sixth probe on each host was benign foreground execution, with no hook decision. Claude's adapter maps Bash, PowerShell, Edit, Write, NotebookEdit, Glob, Grep, Read, AskUserQuestion and Agent; question/delegation wrappers check current policy, while read-tool subscriptions remain opt-in. The Codex sample maps `Bash` and `apply_patch`. Codex `Bash` with `turn_id` uses the declared shell; Claude's stays Bash. Diagnostics prove a runner decision, while a denial also needs prevented execution and intact protected files; missing diagnostics leave delivery unknown.
