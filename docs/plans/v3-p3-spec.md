# v3 — P3 specification: the `ro` CLI and hooks

**Version 1.3** (2026-10-25). v1.0 was reviewed independently by a Codex reviewer and a Claude reviewer (both GO WITH CHANGES); the
changes are listed in §10. The owner's simplicity decision (§11) is incorporated into §3 and §5–§7. Parent plan:
[v3-plan.md](v3-plan.md) §7; builds on [P1](v3-p1-spec.md), [P2](v3-p2-spec.md).

## 1. Principles

- **Commands are the source of truth; hooks accelerate.** Every hook check also exists as a `ro` command or checker
  rule. Hosts without trusted hooks keep the same protection by running the commands.
- **Accident prevention, not an adversarial boundary.** Settings, receipts and `.ro/` are editable by the agent; the
  design prevents mistakes, it does not stop a determined actor. Stated in `references/hooks.md`.
- **Hooks run fixed, installed code** (`${CLAUDE_PLUGIN_ROOT}/…/ro.py`), never evaluate hook JSON, recorded commands or
  repository strings; user regexes use a bounded grammar and scans have a deadline.
- **Fast per-call hooks:** PreToolUse/PostToolUse read only the settings block and `.ro/jobs.json` (mtime-cached), never
  the full four files; target p95 < 150 ms for installed wrappers and in-process checks on every host; direct-child overhead above bare-interpreter p95 < 150 ms and absolute p95 < 300 ms; explicit timeout 10 s.
- **Briefs inject facts only:** IDs, titles, numbers, dates — never free text written by other sessions; command lines
  in `jobs.json` are stored redacted and never printed.

## 2. Enforcement semantics

| `Enforcement` | check id in `Block:` | check result | hook crash / timeout |
|---|---|---|---|
| `off` | any | nothing | nothing |
| `warn` | any | warn | fail open (logged) |
| `block` | no | warn | fail open (logged) |
| `block` | yes | **block** | per-call hooks fail open; authoritative Git pre-push and `ro external` refuse unavailable checks |

Coordinator decision after P3 review: no `onFailure: block` in host hook configurations. All per-call PreToolUse,
PostToolUse and Stop hooks fail open on crash, timeout or missing interpreter. Fail-closed execution protection comes
only from the Git `pre-push` hook for `publish.scan` (nonzero exit blocks push; missing interpreter makes the script
exit nonzero) and `ro external` for external actions. Diagnostic writes are best-effort and cannot downgrade a deny.

- Presets (updates P1 §2): every preset uses `Enforcement: block` with a short `Block:` list —
  `quick`, `work-project`, `*-research`: `shell.background, shell.heredoc, jobs.mutate-bound, publish.scan`;
  `competition-*`: the same plus `external.gate`. Everything else warns.
- **Warn channel:** PreToolUse never answers `ask` and never emits `allow`; a warning is returned as
  `additionalContext` where the host supports it, otherwise appended to `.ro/warnings.log` and shown by the next
  PostToolUse and by `brief`.
- **Self-test:** SessionStart runs a 50 ms self-test; if hooks cannot run correctly it prints
  `hooks inactive: <reason>` into the brief, so silent fail-open is visible.

## 3. Settings added

| Line | Values |
|---|---|
| `Environment` | `<os>/<shell>`: os `windows`, `linux` or `macos`; shell `bash` (bash-like shells) or `powershell`; asked by every preset with an auto-detected default |
| `Block` | comma list of check ids from §5 |
| `External actions` | command patterns and project wrappers that count as external actions (competition default: `kaggle competitions submit`, `kaggle kernels push`, plus any wrapper the project lists) |
| `Publish scan` | `secrets` (default) plus optional `literal:<text>` / `regex:<pattern>` data patterns |
| `Brief requirements` | `<sub-agent type>: <required line>` entries (optional) |

P1's `Enforcement` and `Autonomy` become active.

## 4. Tool state and `ro` commands

`.ro/` (never a coordination file; added to `.gitignore` when git sync is on): `jobs.json`, durable `job-sequence.json`, `receipts.json`,
`ids.json` (reservations), `locks/`, `warnings.log`, `checker-baseline.json`. Writes are atomic (`os.replace`, retried on
Windows `PermissionError` under the lock). Locks record owner pid + start time; a lock is stolen only when its owner is
dead.

| Command | Contract |
|---|---|
| `next-id <D|H|I|X|N> [--slot A]` | under the lock: read the files and `ids.json`, reserve the next free number with a 10-minute TTL, return it; `records.id` reconciles reservations once the ID appears |
| `dupcheck <terms…>` | search headings and Hypothesis/Finding lines in the four files (and `docs/` archives if present) |
| `claim` / `release <H-id>` | unified workflow, under the lock, after re-reading plan.md; refuse a claim held by another taken slot |
| `launch --item H-… --expect 2h [--run-dir D] [--bind P…] [--error RE…] [--heartbeat F --max-silence 20m] [--confirm 15s] [--require-receipt A] -- <cmd>` | refuses if a bound path conflicts with a running job; auto-binds the run dir and the script paths in `<cmd>`; starts detached; records pid + start time + redacted command; writes the handoff "launched" event **only** if the process is alive after `--confirm` and no error pattern matched |
| `monitor <job>` | meant for the host's background facility; exits with a reason on completion, error pattern, heartbeat silence (only when `--heartbeat` was given), or 2× expected duration; records the outcome in `jobs.json` and prints the handoff line to append |
| `kill <job>` | kills the job's process tree (`taskkill /T` on Windows, process group elsewhere) after matching pid + start time |
| `jobs [--prune]` | lists jobs; marks finished or dead ones (pid reuse detected by start time) |
| `receipt add <artifact> --reviewer <session id> --verdict PASS|FAIL --scope <contract id> [--dest <destination>]` | binds verdict to sha256 of the artifact; the latest receipt for the same artifact and scope wins, so a FAIL after a PASS invalidates it; the reviewer id must differ from the author session (P1 §6) |
| `external [--artifact A] [--action X-…] -- <cmd>` | the enforced path for external actions: requires a PASS receipt for the artifact hash computed **now**, and a ledger entry `Status: prepared` with matching hash, destination and an `Expected` written before now; then runs `<cmd>` and sets the entry to `done` |
| `observe <key> <value> [--source …] [--ttl 6h]` | writes a volatile fact with `Observed at` into Shared state; `brief` flags it after its TTL |
| `brief [--max 8000]` | settings summary, hooks self-test, slot and claims, running jobs with monitor state, overdue guard items (P2), saturated families, checker counts |
| `close` | releases this slot's claims except items with running jobs; sets `Current host: released` only if no job of this slot is running; runs the checker; prints leftovers (open claims, discoveries without follow-ups) |
| `hook <event>` | hook entry point; reads the host JSON from stdin through a host adapter that normalises tool names (Claude `Bash`/`PowerShell`/`Edit`/`Write`/`Glob`/`Grep`/`Read`; Codex `shell`/`apply_patch`) to (dialect, command, paths) |

P2's external-actions ledger uses `Status: prepared` before acting. Directory artifacts hash as: sorted POSIX relative
paths, each with sha256 of raw bytes (no newline normalisation), excluding `.git`, `__pycache__`, `.ro`; above a size cap
the receipt records `unhashed` and `external` refuses.

## 5. Checks

Shell-specific checks parse only the declared shell family (`Environment`, §3); commands written for another shell get
only the shell-independent checks. Paths follow the declared OS only (windows: drive letters, both slash styles,
case-insensitive; linux/macos: POSIX). Only literal paths are resolved; `$VAR`, `%VAR%` and globs warn at most.

| Id | Event | Rule | Default |
|---|---|---|---|
| `shell.background` | PreToolUse, declared shell | bash family: a lone `&` control operator or `disown` at statement level (a small tokenizer handles quotes, comments, `&&`, `\|&`, `&>`, `>&N`, `<&N`); powershell: a trailing `&`. Never when the host's own background flag is set | block |
| `shell.detach` | same | `Start-Job`, `Start-Process` without `-Wait`, `nohup`, `setsid` | warn |
| `shell.heredoc` | same, bash family | backticks inside an unquoted heredoc body; `$(date)` and quoted heredocs are fine | block |
| `shell.cd` | same | a bare directory change in a foreground call | warn |
| `jobs.mutate-bound` | PreToolUse shell and Edit/Write/NotebookEdit | a literal path (absolute, or project-relative when the command contains no directory change) that resolves into a running job's run dir or bound files and is the target of a write, delete, move or redirect. If the command changes directory anywhere, relative targets are uncertain → warn, never block | block |
| `jobs.read-bound` | PreToolUse shell and Glob/Grep/Read | listing or reading a running job's run dir, except `status.json`, `*.log`, `heartbeat*` | warn |
| `jobs.unmonitored` | **Stop** (the only Stop check) | a running job of this slot without a live monitor | warn; block once if listed |
| `records.timestamp` | PostToolUse Edit/Write and shell (mtime change of the four files) | a new heading or date later than now + 5 min | warn |
| `records.id` | same | a duplicate ID introduced; reconciles `ids.json` | warn |
| `publish.scan` | git `pre-push` (authoritative, fail closed; exact refs on stdin; every outgoing commit; matches redacted) and PreToolUse `git push` (pre-check of the staged diff) | secrets or `Publish scan` patterns in outgoing content | block |
| `external.gate` | PreToolUse shell | a direct call matching `External actions` not run through `ro external` (direct calls only; the wrapper is the enforced path) | block |
| `ask.away` | PreToolUse AskUserQuestion | `Autonomy: away`; the reason tells the agent to ask in chat and continue only with work that needs no consent | block |
| `brief.requirements` | PreToolUse Agent | a brief for a listed sub-agent type missing its required line | warn |

Out of scope (documented in `references/hooks.md`; never blocks): nested interpreter bodies (`bash -c`, `powershell -c`,
`cmd /c`, `python -c`), aliases and functions, dynamic paths, cross-shell invocation, MSYS/UNC path translation,
junction resolution, and tracking the scope of directory changes. Hooks prevent accidents; they are not a security
boundary.

Commands or checker only (no hook): open claims and missing follow-ups (`ro close`, checker), unrecorded sub-agent
reports (`ro close`), process termination (`ro kill`).

## 6. Hook wiring

- Claude Code plugin `hooks/hooks.json`: SessionStart (`startup`, `resume`, `compact` — the compact matcher re-injects
  the brief), PreToolUse (Bash, PowerShell, Edit, Write, NotebookEdit, Glob, Grep, Read, AskUserQuestion, Agent),
  PostToolUse (Edit, Write, Bash, PowerShell), Stop; `type: command`, timeouts 10 s, `${CLAUDE_PLUGIN_ROOT}` paths, and
  no `onFailure` anywhere — every per-call hook fails open.
- Codex: `hooks/codex-hooks.sample.json`, copied into the project's `.codex/` by the user and trusted via `/hooks`;
  protection is claimed only for behaviours shown by a recorded dry run.
- Git: `hooks/pre-push.sample` (`ro hook pre-push`) — host-independent, authoritative and fail closed for
  `publish.scan`.
- `references/hooks.md`: the declared environment, the check list, the out-of-scope list, the capability matrix
  (check × host: enforced / warned / command only), install and trust steps, and the accident-prevention statement.

## 7. Tests

1. One corpus per shell family: benign commands → zero blocks and ≤ 2 % warnings; true positives anonymised from a real
   mistake log → 100 % recall on the deterministic entries inside the §5 scope (entries outside it are listed as such);
   out-of-scope constructs → no block.
2. Enforcement table: every cell of §2, including crash, timeout and a missing interpreter.
3. Paths for each declared OS: windows drive letters, slash styles and case; POSIX paths; literal versus dynamic paths;
   a directory change making relative targets uncertain.
4. Concurrency: two processes calling `next-id`/`claim` never collide; a live lock is never stolen; `os.replace`
   contention is retried.
5. Jobs: a command exiting at 3 s never writes "launched"; error pattern, heartbeat silence and 2× overrun are reported;
   PID reuse is detected; `kill` takes the tree.
6. Receipts: PASS then FAIL invalidates; an artifact changed after review refuses; hashes are stable across LF/CRLF
   checkouts.
7. `publish.scan`: a secret in an intermediate commit of a multi-commit push, a new branch, a force push; matches are
   redacted.
8. Stop: a 50-turn simulated session produces at most one Stop warning when nothing is wrong.
9. Latency: PreToolUse p95 < 150 ms for installed wrappers and in-process checks on a large synthetic project (≈ 1.4 MB discoveries, ≈ 0.5 MB handoff). For direct subprocess calls, subtract bare-interpreter p95 measured with the same `-E -S` flags, two warm-ups and three 20-sample batches: overhead < 150 ms and absolute hook p95 < 300 ms. This separates startup variance from hook work while catching end-to-end regressions. Keep the killable supervisor deadline. A deterministic no-history-read test separately verifies that ordinary PreToolUse does not scan the histories.
10. Malformed or oversized hook stdin fails open.
11. Tests are organised by feature and named after behaviours, never after review rounds or projects.

## 8. Out of scope

SKILL.md ≤ 12 KB rewrite, READMEs, per-preset examples, release (P4).

## 9. Follow-up for P1/P2

- P1 presets switch to `Enforcement: block` with the `Block:` lists of §2 (enforcement becomes active here).
- P2 external-actions ledger uses `Status: prepared` (already in P2 §3.5).

## 10. Review changes from v1.0

- Codex reviewer: an explicit outcome table including crashes/timeouts and an explicit 10 s timeout; no `allow` emitted; Codex
  claims only after demonstrated behaviour; block only proven operations, warn on unknown syntax, protect mutations of
  bound inputs; durable ID reservations, ownership-aware locks, atomic replace and launch-crash recovery; PID + start
  time; `close` no longer releases a slot with running jobs; receipts with reviewer provenance, scope, latest-wins
  precedence, destination and hash computed at execution; `prepared` ledger status; trusted fixed code paths, bounded
  regexes, redaction, outgoing-object scan; accident-prevention statement; much broader tests.
- Claude reviewer: Stop keeps only `jobs.unmonitored`; a defined warn channel and never `ask`; the original protected-route
  failure proposal is superseded by the coordinator decision in §2; a self-test, wrapper-based external gate and git `pre-push` as the authoritative scan;
  narrowed heredoc rule (`$(date)` allowed); `subagent.unrecorded` and `claims.open` moved to `ro close`; PreCompact
  replaced by SessionStart `compact`; facts-only brief; redacted command lines; mtime-cached per-call hooks; Glob/Read
  coverage, auto-bound paths, `ro kill`, shell-originated record edits, `Start-Process`/`nohup`, `pushd`/`Set-Location`,
  a host adapter; exact shell grammar, path rules and directory hash; the competition-preset blocking conflict resolved.

## 11. Simplicity decision (owner, 2026-10-25)

Hooks must not become specialised to particular operating systems, shells or situations. A declared environment
replaces broad parsing, only simple deterministic checks remain, and complex constructs are documented as out of scope.
Incorporated into §3 and §5–§7 in v1.3 (v1.2 carried it as an override section).
