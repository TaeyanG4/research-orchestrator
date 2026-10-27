# Using hooks

Hooks catch reproducible mistakes during work. Use `ro` commands and Git pre-push as execution gates because per-call hooks can fail open.

## Start and respond

Read `ro brief` at startup, resume, clear and compaction for self-test status, monitors and checker findings. See [hooks-capabilities.md](hooks-capabilities.md) for installation, the capability matrix, trust and runtime limits; self-tests alone do not prove host delivery.

`Enforcement: off` is silent; `warn` advises; `block` denies only checks listed in `Block`. Uncertain parses warn. PreToolUse warnings use supported `additionalContext`, or `.ro/warnings.log` for delivery by PostToolUse and `brief`. Identical warnings appear once per session. Responses never request approval or emit `allow`.

On `jobs.unmonitored`, run the printed monitor command, record the outcome, then close. A live monitor or recorded outcome after exit resolves the finding. When listed for blocking, Stop blocks once per job in the session, then warns so a broken monitor cannot trap the session. An away-mode question block directs the agent to chat and independent work needing no consent.

PreToolUse, PostToolUse and Stop fail open on crashes, timeouts, malformed input or missing Python. The configured Git pre-push and external-action gates fail closed because they control execution. Neither host uses `onFailure: block`; diagnostics cannot downgrade a deny.

## Checks during work

| Check | Response |
|---|---|
| `shell.background`, `shell.detach` | Use a host background facility or an owned `ro launch` job for detached work. A final top-level bare Bash `wait` (`a & b & wait`), or PowerShell `Get-Job \| Wait-Job`, keeps the call foreground by waiting for all its jobs. Conditional, targeted or timed waits do not establish this boundary; explicit detach commands remain checked. |
| `shell.heredoc` | Quote the Bash heredoc delimiter when writing literal backticks. |
| `shell.cd` | A bare trailing directory change loses the working directory between calls; give the next command a working directory. |
| `jobs.mutate-bound` | Leave running-job scripts, inputs and exclusive outputs unchanged. |
| `jobs.read-bound` | Optional read advice (`Read bound: on`); logs, status and heartbeats stay readable. |
| `records.timestamp`, `records.id` | Correct newly introduced future dates or duplicate IDs. |
| `ask.away`, `brief.requirements` | Follow the project's autonomy setting and delegation contract. |

For owned job commands, read [operations-safety.md](operations-safety.md). Before publishing or other outward actions, read [publication-safety.md](publication-safety.md) or [external-actions.md](external-actions.md).

## Shell certainty

Parse each shell call in the tool's own Bash or PowerShell dialect, even when it differs from `Environment`; only other tools use the weaker uncertain parse. `Environment: <os>/<shell>` still selects path semantics and the fallback shell for hosts without a dialect. Windows comparison accepts either slash and ignores case; other systems use POSIX paths.

A block needs closed lexical boundaries, known wrapper options and a literal target with a known location. Tool `workdir`/`cwd` takes precedence over host `cwd`; bindings use the project root. A literal `cd <directory> && command` with no further directory change resolves the remainder against that directory. Dynamic or multiple directory changes leave relative targets uncertain; absolute literals remain checkable. `env -C`, `git -C` and `make -C` do not establish a new base here.

Quotes, comments, Bash `&&`, `|&`, `&>`, descriptor redirects and the PowerShell call operator are distinguished from background execution. Nested interpreter bodies, script blocks, here-strings, aliases, functions, variables and globs cannot establish a definite target; outer redirects and control operators still receive checks. MSYS/UNC translation and junction resolution are outside the parser.

## Cost and diagnostics

Wrappers find `agents.md` from working-directory ancestors or `CLAUDE_PROJECT_DIR`/`CODEX_PROJECT_DIR`; without it they return `{}` without Python. They pass the policy root separately from command cwd, preserving relative paths, and never parse stdin.

Read/Glob/Grep need opt-in registration. AskUserQuestion and Agent wrappers skip Python while their governing policies are inactive; Stop and Edit/Write/NotebookEdit do so when both jobs registries are absent. PostToolUse skips Python when witnesses for the four coordination files, record cache and acknowledged warnings match. Changes, missing witnesses or diagnostics reach Python. Files younger than two seconds get no witnesses: coarse timestamps can hide same-size edits. cmd also waits past the cache minute. Python checks `(mtime_ns, size)` and warning digests before acknowledging snapshots.

Enable `RO_HOOK_DIAGNOSTICS=1` or `.ro/hook-diagnostics.on` to log events, check IDs and decisions, excluding commands and environment values.
