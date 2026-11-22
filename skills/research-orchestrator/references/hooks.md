# Using hooks

Hooks catch reproducible mistakes during work. Use `ro` commands and Git pre-push as execution gates because per-call hooks can fail open.

## Start and respond

Read `ro brief` at startup, resume, clear and compaction for self-test status, monitors and checker findings. [hooks-capabilities.md](hooks-capabilities.md) covers installation, the capability matrix, trust and limits; self-tests do not prove host delivery.

`Enforcement: off` is silent; `warn` advises; `block` denies only checks listed in `Block`. Uncertain parses warn. PreToolUse warnings use `additionalContext`, else `.ro/warnings.log` for PostToolUse and `brief`. Identical warnings appear once per session. Responses never request approval or emit `allow`.

On `jobs.unmonitored`, run the printed monitor command, record the outcome, then close. A live monitor or recorded outcome after exit resolves the finding. When listed for blocking, Stop blocks once per job in the session, then warns so a broken monitor cannot trap the session; `ro monitor J1 J2` covers several jobs at once.

Per-call hooks fail open on crashes, timeouts, malformed input or missing Python; the Git pre-push and external-action gates fail closed because they control execution. Neither host uses `onFailure: block`; diagnostics cannot downgrade a deny.

## Checks during work

A check covers only its row; a wider project rule is the project's, and passing a hook does not make a call allowed.

| Check | Covers → response |
|---|---|
| `shell.background`, `shell.detach` | `cmd &`, `disown`, nohup, setsid, Start-Job, Start-Process without -Wait (host background tools pass) → `ro launch`. A final bare `wait` or `Get-Job \| Wait-Job` keeps a call foreground. |
| `shell.heredoc` | Backticks in a heredoc with an unquoted delimiter → quote it. |
| `shell.backslash` | `\\` in a Windows Bash call, which that tool turns into `\` even in quotes → use the file tool. |
| `shell.cd` | A bare trailing `cd` → give the next command a working directory. |
| `fs.delete` | Recursive or wildcard deletes → name exact files; ask before deleting shared ones. |
| `jobs.mutate-bound` | Writes to running-job scripts, inputs, outputs → leave them. |
| `jobs.read-bound` | Opt-in read advice; logs, status, heartbeats stay open. |
| `records.timestamp`, `records.id` | New future dates or duplicate IDs → fix; `ro event`/`ro seal` take clock time. |
| `records.direct` | Edit/patch adding an event or ledger heading to handoff.md → `ro event`, `ro external --check`. |
| `ask.away`, `brief.requirements` | Autonomy; required Agent-brief lines (no type = general-purpose) → `ro brief --delegate`. |

For owned job commands, read [operations-safety.md](operations-safety.md). Before publishing or other outward actions, read [publication-safety.md](publication-safety.md) or [external-actions.md](external-actions.md).

## Shell certainty

Parse each shell call in the tool's own Bash or PowerShell dialect, even when it differs from `Environment`; only other tools use the weaker uncertain parse. `Environment: <os>/<shell>` still selects path semantics and the fallback shell for hosts without a dialect. Windows comparison accepts either slash and ignores case; other systems use POSIX paths.

A block needs closed lexical boundaries, known wrapper options and a literal target with a known location. Tool `workdir`/`cwd` takes precedence over host `cwd`; bindings use the project root. A literal `cd <directory> && command` with no further directory change resolves the remainder against that directory. Dynamic or multiple directory changes (and `env -C`, `git -C`, `make -C`) leave relative targets uncertain; absolute literals remain checkable.

Quotes, comments, Bash `&&`, `|&`, `&>`, descriptor redirects and the PowerShell call operator are distinguished from background execution. Nested interpreter bodies, script blocks, here-strings, aliases, functions, variables and globs cannot establish a definite target; outer redirects and control operators still receive checks. MSYS/UNC translation and junction resolution are outside the parser.

## Cost and diagnostics

Wrappers find `agents.md` from working-directory ancestors or `CLAUDE_PROJECT_DIR`/`CODEX_PROJECT_DIR`; without it they return `{}` without Python. They pass the policy root separately from command cwd, preserving relative paths, and never parse stdin.

Read/Glob/Grep need opt-in registration. AskUserQuestion and Agent wrappers skip Python while their governing policies are inactive; Stop and Edit/Write/NotebookEdit do so when both jobs registries are absent. PostToolUse skips Python when witnesses for the four coordination files, record cache and acknowledged warnings match. Changes, missing witnesses or diagnostics reach Python; [hooks-capabilities.md](hooks-capabilities.md) gives the witness timing.

Enable `RO_HOOK_DIAGNOSTICS=1` or `.ro/hook-diagnostics.on` to log events, check IDs and decisions, never commands or environment values.
