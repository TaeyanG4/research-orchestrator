# Changelog

## 8.0.1

Closes the minor findings the two independent reviews left at the 8.0.0 release. Projects need no change.

### Fixed

- A job whose log 7.0.0 had scanned reports the matches ending in the last two characters of its saved tail as one report, so several old matches there repeat once together instead of once each, also when a scan of the running job held them first (the old tail's end is kept while a scan can re-examine it), unless exactly one character such as a final newline arrives between the two scans; the separate old-state starting point, which behaved like the default path, is gone. A state 8.0.0 already scanned keeps no old-tail mark and may still repeat those matches once each.
- `references/decision-guards.md` keeps every rule with shorter rationale, leaving room under its size budget.
- `references/presets.md` names the current template v3.6 and both frozen templates (v3.4, v3.5); `references/delegation.md` says a delegated agent is not given `agents.md` rather than that it never reads it.

## 8.0.0

This release comes from a mistake log kept through one six-week competition (259 entries; of the 194 classified for this release, 91 name a delegated agent in their title), classified by root cause and reviewed by independent readers. Its lesson: prose rules did not stop repeats, while checked rules held inside their scope. So events, item closes, field changes and seals are now written by commands that take the clock time (event headings and seals always; other fields where a draft writes `{now}` or `{today}`) and validate with the checker's own rules; a hand edit remains possible and is only warned about; each check's real scope is documented; and delegated agents get a generated brief header. Projects on template v3.5 keep working; `--reconfigure` moves them to v3.6. New warnings can make `--strict` runs fail, hence the major version.

### Added

- `ro event <key>` appends an event with the clock time and the slot's Host/User, from field options or `--from <file>`; the checker's own rules refuse a malformed event before it is written (`Decision: changed` without a discovery, a bare item ID while the item is queued, multi-line fields).
- `ro set-field <ID|slot|shared> <Field> <value>` replaces one existing single-line field and keeps every other byte (`shared` is the Shared state section, e.g. `Current best`); `--add` appends a field the record lacks, such as `Correction: ({now}) …` or `Reconciled: …`, after its last field and that field's indented lines, and names an unknown field name in its notes; an archived discovery's stub is refused with the restore command; fields owned by another command (`Claimed`, ledger `Status`, attribution and review fields) are refused.
- `ro event`, `ro set-field` and `ro close-item` replace `{now}` with the clock time and `{today}` with the date, so ledger stamps (`(written {now})`), corrections and drafted discoveries need no typed time.
- Record commands refuse any new checker ERROR and any warning of a malformed record (a format, an invalid value, a missing or repeated field, a future time, a ledger `Expected` stamp or duplicate identity); a state warning the write brings about (a new best not yet in Shared state, a stage awaiting review, a long Next test) comes back as a note with the next step, as a hand edit would only be warned.
- `ro seal <file>` records a file's raw SHA256 and the clock time in `<file>.seal.json`; sealing the same bytes returns the first seal, changed bytes are refused, and `--check` compares the file with its seal.
- `ro close-item <ID> --from <draft>` finishes an item (drafted `## D-…` discoveries, the `## Event`, optional `## Follow-ups` items, removal from `plan.md`) in one checked, journaled transaction with its own `*.close-tmp`/`*.close-backup` files; `--dry-run` previews it and only `--recover` completes or rolls back an interrupted one (a dry run or a new close reports the journal and changes nothing). While a journal is pending, `ro` refuses to write the four records and `ro external` refuses before journaling an attempt; recovery stops, on every rerun, instead of overwriting a file that holds neither its old nor its new bytes, and its message gives the way out. A completed or rolled-back recovery removes the transaction's own backups. Refusals for a dangling slot pointer, a finished item still queued or a lost follow-up name the next step. A drafted discovery `Date` in the future is refused.
- `ro launch --require-seal <file>` refuses a run whose sealed file (for example a preregistered decision rule) changed; a relative path resolves against `--run-dir`, like the script and heartbeat.
- `--reconfigure` of a project whose `Brief requirements` is `none` mentions the new preset default.
- `ro brief --delegate <item|item/sN|none>` prints the header for a delegated agent's brief: an absolute run folder as write scope, no deletes, resource limits to fill in, clock times, `ro launch` for long runs, the real scope of blocking checks, and a seven-part report shape. Its commands name the project and slot and use the configured shell's syntax; a stage must be declared in the item's `Stages`, an important stage's launch example carries `--require-receipt`, and blocked checks that only flag after a call are listed apart. Presets other than `quick` set `Brief requirements: general-purpose: ro-delegate: v1`; an omitted agent type counts as `general-purpose`. New reference [delegation.md](skills/research-orchestrator/references/delegation.md).
- `ro external --check --action <X-ID>` applies every execution rule to a prepared entry without running anything; `--success-regex` turns an exit 0 without the expected output into `unknown`, and an unusable pattern is refused before anything is journaled or run.
- `ro monitor` accepts several jobs; `ro jobs --running` lists jobs that hold ownership or lack an outcome; `ro jobs --reconcile <job> --evidence <text>` closes a job whose processes vanished after a host restart, which before meant editing `.ro/jobs.json` by hand; it refuses a job of another machine or with a live launcher and keeps an end already recorded. A multi-job monitor tolerates a reported job pruned before it ends.
- Hook checks `shell.backslash` (Windows Bash turns `\\` into `\` before bash runs), `fs.delete` (recursive or wildcard deletes) and `records.direct` (an Edit or Codex patch that adds a new event or ledger heading outside code fences points to `ro event` and `ro external --check`; full-file Writes and shell edits are not covered); all three warn unless listed in `Block`.
- `ro brief` names job IDs that slot notes cite after they finished, Active compute items without a running job, open CHALLENGED/HOLD reviews, ledger entries awaiting a final result, and the skill version.
- `ro index <H-ID>` prints one plan item; `ro index <D-ID>` prints `Correction:` and `Current:` lines first, and the startup index shows `Current:`. The checker accepts both fields and warns about a `Next test` past 2 KiB (`plan.next.size`).
- `Reconciled: accepted-cancelled (observed …)` lets a retry follow an action the service accepted but the owner cancelled before it ran.
- Guidance: a decision-rule checklist in research guards, a mistake-log template and rule hygiene in project rules, a skill retrospective in the post-mortem, script habits in the tool registry, and observed Kaggle behaviour (request pacing, exit 0 refusals, zip unpacking, status spellings).
- `tests/test_incident_regressions.py` and `tests/test_record_commands.py` reproduce the logged incidents.
- Eval case `delegation-brief-header` grades the delegating session, not a delegated agent (the case format allows no Agent tool): the brief starts with the generated header and names one run folder, a supplied report's inferred explanation stays inferred in the records, and the stage outcome goes through `ro event`. One paired run against the runner's pinned 5.1.0 baseline scored 4/4 against 2/4; the two differing graders test commands only 8.0.0 has and the behavioural grader passed in both, so it shows adoption, not an effect on delegated agents. One paired run with real sub-agents (same model and task; one arm with the header, one without) is recorded separately: the arm with the header deleted nothing, left the records to the delegating session and wrote only to its run folder, while the other deleted two stale files, wrote an event itself and saved outputs outside a run folder ([docs/evals/evidence/delegation-paired-run-2026-11-23.md](docs/evals/evidence/delegation-paired-run-2026-11-23.md); one case, not an effect size) ([docs/evals/evidence/delegation-brief-header-2026-11-22.md](docs/evals/evidence/delegation-brief-header-2026-11-22.md)).

### Changed

- Template v3.6: the Working rules point at `ro close-item`, `ro event`, `ro set-field`, `ro seal`, `ro external --check` and `ro brief --delegate`. v3.5 is frozen with its released bytes.
- Writes keep a file's line endings: text read with universal newlines no longer converts a CRLF record to LF, and text read with its newlines is written exactly.
- The checker applies the executor's Candidate rule (`<artifact>, hash <64 hex>` and nothing after) to prepared ledger entries.
- `ro launch` refuses a missing script after a known interpreter, or a `--heartbeat` whose folder is missing, and names where a project-relative path points; the job's child gets `RO_SLOT`.
- Identical job warnings merge into one line naming every job; redirects to a null device are not project writes (Bash's `/dev/null`, Windows PowerShell's `NUL` and an unquoted PowerShell `$null`; see Fixed).
- `references/hooks.md` states what each check covers; a project rule wider than a row is the project's.
- The `history.size` warning and `ro archive events` say when the External actions ledger and live items' events keep `handoff.md` above its limit; `agents.rules.stale` names the current template and `--reconfigure`.
- Record commands report a finding as new only when its check and record are new, so a size that grew is not repeated after every write.

### Fixed

- A statement-leading `&` (PowerShell's call operator sent without a shell field) is no longer denied as a Bash background job; an escaped `\;` before `&` still is.
- `ro archive events` treats only item headings as live; an ID cited in another item's text kept finished events and caused `event.item.lost`.
- `ro next-id` ignores an ID glued to a following decimal (`X-A-313` written next to `0.488`) and warns when a number jumps by 100 or more.
- A malformed event of an unrelated item (two `Job` lines) no longer refuses every launch; the item's own malformed event names its heading.
- The executor and the checker read the same `Expected` stamp: exactly one minute-precision `(written …)` ending the field. The executor took the first stamp and accepted seconds, so a second stamp, trailing text or seconds passed `ro external` while the checker refused the entry.
- `ro close-item` rechecks, under its final lock, for another call's pending transaction and for jobs of the item, and refuses `--dry-run` with `--recover`. A job registered on another machine stays protected: `ro monitor`, `ro kill` and `ro jobs --reconcile` refuse it, and `--prune` keeps it until its own machine records an end. Reconciling a job whose end was inferred during the call saves that end.
- `records.direct` judges each file of a Codex patch on its own and only the project's own `handoff.md` (an archive copy is not it; Windows names ignore case). Host paths are compared literally, so `archive[2026]` is a folder, not a glob. Null devices follow the shell: Bash (Git Bash on Windows included) knows only the lowercase `/dev/*` names, so `> NUL` there writes a file named `NUL`; native Windows PowerShell knows only `NUL`; `$null` is the null device only as an unquoted PowerShell variable.
- `ro launch` refuses while a record transaction is pending, so a recovered close cannot finish an item whose job just started. A job of another machine stays protected until its record proves the process tree ended (`tree_empty`, or a finished exit), whatever its result status. A recorded launch failure keeps its cause and time whichever command refreshes it first (a lost supervisor is marked apart), a launch whose supervisor died is not confirmed, a runner that never started records an empty tree, reconcile returns early only with recorded end evidence, and the owner's reconcile evidence is kept in the job's `reconciled` list, which later monitors do not replace.
- `fs.delete` follows each shell's syntax: Bash removes quotes before `rm` sees a word (`'-r'` is an option, `'--'` ends options) and expands only an unquoted `*`, `?` or `[...]` (`'a*b'` is a name, `'my dir'/*.txt` a pattern); PowerShell reads `-Name:value` arguments (`-Path:a*`, `-Recurse:$true`), which no longer make a call uncertain and so keep a configured block; it expands quoted patterns on `-Path`, takes only `-LiteralPath` literally, treats a wildcard as literal only when a backtick still escapes it after quoting (single quotes keep the backtick; unquoted and double-quoted backticks are consumed first, so ``a`*b`` stays a pattern) and ignores `-Exclude` patterns. Only a certain `-WhatIf` (`-WhatIf`, `:$true`, a nonzero number) is a dry run that deletes nothing; `:$false` or `:00` is a real run, and an unknown value (`:$x`, also `:$null`, which binds as present) leaves the call uncertain; `-Recurse` counts unless certainly false.
- `ro event` and `ro close-item` insert before the real `## Archived history`, not a fenced example of it; fenced follow-up headings in a close draft are not queued items; `{now}`/`{today}` inside a fence stay as written.
- Retry order and `Reconciled` timing use every stamp of the prior attempt, so an earlier time quoted in its Result no longer lets a retry pass.
- `--success-regex` is matched on each output stream as it arrives, not on the bounded record kept for reconciliation, and a read boundary is never taken for the stream's start or end (`accepted$` does not match `acceptedNO` split after `accepted`); an empty pattern is refused. A monitor keeps a recorded launch failure and a later log finding side by side. An invalid or malformed final stamp (`2026-11-3`, month 13) leaves a ledger entry undated instead of falling back to an earlier one. A job's error pattern that looks at what follows (an unescaped `$`, `\b`, `\B`, `\Z` outside a class) waits for more text or the finished log instead of matching a poll's temporary end, and is found when the next read completes it; other patterns report at once; each scan searches from just before the new text, with `^` only at the log's real start, and reports a match that ends in new text after the end of the last reported one, so no match is reported twice; an overlapping repeat (`ABA` in `ABABA`) can count once, and an error that grows (`ERROR`, then `ERRORS`) can be reported again. A job scanned by an earlier release re-examines the last two characters of its saved tail once, so an error that code missed there is found (one it missed earlier in the tail is not), at the cost of possibly one repeated report per match; and launch events, like `ro event`, go before the real `## Archived history`. Follow-up items are queued past fenced section examples. Malformed Shared state values (`Active compute`, `Plan collection`) are refused like other malformed records.
- The next-id jump warning survives a record hook that raised the mark first, and archives are read with the same ID parser as records (no IDs glued to a decimal). `ro brief` shows an interrupted transaction before the slot choice too.
- The guards' start date dates an external action by the later of the stamps that end its `Result` and `Expected`, so an added `Date`, a reversed pair or an earlier quoted stamp no longer exempts it, and two `written` stamps leave it under the current checks; the Expected-before-Result check reads the same final observation. The delegation header prints every line `Brief requirements` demands of general-purpose agents, and the hook names the missing line.
- `ro set-field` also refuses a discovery's `Source` and `Host`; `ro index <D-ID>` moves only real `Correction:`/`Current:` lines, not fenced examples; `ro launch` checks `.R` and `.jl` scripts; `ro brief` counts `fs.delete` warnings.

## 7.0.0

This release reads only the v3 layout. Projects from releases before 6.0 (no `<!-- ro-template: ... -->` marker in `agents.md`) are refused with the upgrade route: run `init_research_orchestrator.py . --reconfigure` with release 6.0.x first.

### Added

- `agents.md` gains generated `## Working rules` (template v3.5) so sessions that never load the skill still search before adding work, record each result once, register and reuse scripts, archive when told and close cleanly; each rule says why. Setup and `--reconfigure` add `@agents.md` (Claude Code's import) to `CLAUDE.md` unless that file already names `agents.md` (`--no-claude-md` skips it), and the SessionStart brief names the rules. `--reconfigure` upgrades v3.4 projects and keeps `## Project rules`.
- `ro archive discoveries` and `ro archive events` keep startup reads bounded as a project grows. Settled discoveries that no live item or handoff state cites move whole to `docs/archive/discoveries-<YYYY-MM>.md` and leave a stub (heading, `Archived:` path, state, clipped finding) that keeps the ID resolvable; the checker reads the archived entry, `ro index <ID>` opens it and `ro dupcheck` searches it. Older events move to `docs/archive/handoff-<YYYY-MM>.md` with one summary line per archive file, while events naming a live item, each slot's latest event and the events that resolve an item a kept event queued stay. `--before YYYY-MM-DD` and `--dry-run` select and preview the moves; a rerun after an interrupted move completes it without duplicating entries. `ro archive restore <ID>` moves an archived discovery back so it can be revised and archived again.
- The checker reports `history.size` when the live discovery index passes 48 KiB or `handoff.md` passes 192 KiB, and `ro brief` names the archive command to run.
- The checker reports `agents.size` when `agents.md` passes 12 KiB, because it loads in every session, and says when it passes 32 KiB, where Codex stops reading project instructions and cuts the user-owned rules at the end; `ro brief` repeats it.
- A tool registry in `docs/tools.md` ([references/tools.md](skills/research-orchestrator/references/tools.md)): `ro tools <terms>` and `ro dupcheck` search it before a script is written, the checker warns about incomplete entries, missing or shared paths and scripts beside registered tools without an entry (`tools.*`), and `ro brief` reports how many tools are registered. `ro tools --init` creates the registry with its usage rules as the header.
- Eval cases `history-archive` and `tool-registry`, and `brief-review-cache` variants for an unreadable member and a file that grows while it is hashed.
- `scripts/measure_hook_fast_paths.py` measures a full startup SessionStart that hashes a reviewed directory.

### Changed

- `ro index` lists live discoveries with a summary line and counts archived entries instead of listing them. Findings stay whole while the index fits 48 KiB, because their conditions decide duplicates; a larger index clips them to 160 characters and says so; `--full` keeps whole lines and archived stubs. In one maintainer measurement on a private 1.4 MB history of 391 discoveries, not retained in this repository, the startup index fell from 474 KB to 167 KB, and to 91 KB after archiving its settled entries.
- Discoveries are merged when they duplicate each other and archived when settled and the index grows, instead of never being archived.
- Every checker-summary eval grader uses one strict parser, so clipped, unreadable or invented summaries never earn credit; the positive control is real checker output. Checker predicates of the new cases also require a complete report whose findings match its counts, and objective outcomes of the new cases are graded by script.
- Research and competition discovery headers state the one-discovery-per-experiment rule; hook messages that name `ro launch` or `ro external` point at their `--help`.
- The fixed startup read grows by about 2.4 KB for the working rules; its test budget is now 17,500 bytes.
- Saved hook timings were re-measured on 2026-10-28; the compact-summary figure now reflects content stamps.

### Removed

- Reading, checking and upgrading v2 (5.1.0) projects: the v2 template and settings defaults, the v2 rule comparison and the `agents.settings.v2` notice. The checker now reports `agents.settings.unsupported` and `--reconfigure` refuses such files.
- Preservation of accepted 5.1.0 `multi`/`same-host` reviews (the `ro-legacy-reviews` record and `discovery.legacy.invalid`); reviews follow the current verification rules only.
- Frozen templates v3.0–v3.3, which no release shipped; v3.4 (6.0.0–6.0.2) remains so those projects upgrade without `--force`.
- The eval cases `legacy-same-host-preservation` and `v2-rules-upgrade` and their 5.1.0 fixtures; historical analyses that mention them stay as records of past runs.
- `references/migration-v2-to-v3.md`, replaced by `references/migration.md` for template upgrades, repairs and workflow changes; the README section is now Upgrading.

### Fixed

- Output written to a pipe or file is UTF-8 on every OS. Windows previously used the locale code page, which garbled non-English records for agents reading `ro` and checker output; an explicit `PYTHONIOENCODING` still wins.
- `sudo -C <descriptor> git push` no longer counts as a push that picks its own checkout, so it keeps the staged pre-check; `sudo -D`/`--chdir` and `env --chdir=` do count.
- Brief stamps walk a reviewed directory once and hash the members that walk found.
- An unreadable member or subdirectory of a reviewed directory makes its stamp unusable, so the checker reruns instead of reusing a cached clean review.
- Hashing under a brief's budget refuses a file that grew after it was measured instead of reading past its reservation.
- Archiving refuses a second archived copy of a discovery by ID, not only when its heading text is unchanged.
- A job-runner test injected its failure through the shared `time.sleep`, which also broke the macOS process-identity lookup; the injection now reaches only the runner's poll.

## 6.0.2

### Added

- Claude Code plugin subscriptions for questions and delegated agents apply `Autonomy` and `Brief requirements` without reinstalling hooks when those settings change.

### Changed

- README quick starts pass `--session <host-session>` like the skill's own commands and say where the ID comes from.
- Default pytest runs exclude latency tests; the separate timing command and CI step remain documented without claiming new measurements.
- General work and research handoffs omit unused compute guidance; competition and enabled collectors retain the relevant summaries. Resource guidance describes local capacity and named exclusive resources.
- Competition adapters supply external-action defaults. A `deadline=YYYY-MM-DD` suffix on `--competition` fills an unanswered phase clock; explicit answers take precedence.

### Removed

- Duplicate per-call publication scans when the checkout already has a registered Git pre-push gate. The gate still checks outgoing history.

### Fixed

- Settings-only transitions validate proposed records, preserve evidence and effective queue order, normalize compatible goal fields, and add truthful pending-review fields. Incompatible transitions leave the project unchanged.
- Ordinary and compact briefs refresh review findings when receipts or reviewed artifacts change, including directory members.
- Runtime evaluation checks require captured invocations and retained responses before crediting execution reports.
- Recent record edits no longer qualify for timestamp-only wrapper shortcuts. Lost section signs, arrows and range dashes are restored, and release checks reject damaged numeric references in documentation, READMEs, the changelog and the skill's references.
- Briefs stamp review artifacts with a bounded stamp (content digests up to 32 MiB, member names, sizes and times above it). Stamping and the brief's checker share one 64 MiB hash budget per brief and reuse each digest, so evidence beyond it is reported as unverified in the brief, on its own line with the verification command and not as a failed review, instead of being hashed inside the hook deadline; `check_project.py` or `ro receipt check` still verifies it in full. A review directory over the manifest cap, which no receipt can verify, keeps a stable stamp, so compaction reuses the cached result. Stamps record directory links and junctions, which full hashing refuses, so adding one invalidates a cached clean review.
- The release check compares each README's release line with the manifest version.
- A publication-gate registration counts only while the installed pre-push dispatcher is still in place, and the push pre-check reads the checkout the command runs in rather than the policy root, so a removed hook or a different checkout keeps its advisory scan and installation guidance. A push that picks its checkout inside the command (`git -C`, also attached, `--git-dir`, `--work-tree`, `GIT_DIR`/`GIT_WORK_TREE`, `env -C`, or a directory change first) gets an advisory, without a scan of unrelated staged changes, naming that checkout's own pre-push gate as authoritative. The installation notice names the checkout root instead of `--project .`, which the installer refuses for nested folders.
- The plan-item guide lists the `Resource` values `ro launch` accepts (`CPU`, `GPU`, `EITHER`) and keeps `none` for handoff events.
- Job-binding checks match a bound folder reached through another spelling of the same location (macOS `/var` and `/private/var`, Windows short names, junctions and symbolic links), so a command run from the resolved path is still checked.

### Security

- Hook wrappers pass the resolved project policy root through to dispatch while keeping the command working directory separate, so environment hints cannot silently bypass configured checks or change relative-path interpretation.
- Inactive question and delegation policies skip Python; SessionStart recommends project gate installation only when a Git checkout lacks its registration.

### Migration

- Settings transitions that change coordination records now use the existing `*.pre-migrate` backups and recovery journal even when the workflow stays the same. A workflow change still requires `--migrate` and released slots.

## 6.0.1

### Added

- `references/review-loops.md`: rules for repeated review and fix rounds on one deliverable — a fixed exit criterion ("no BLOCKER or MAJOR finding and the checklist passes", not a score threshold), a round cap, an out-of-scope list given to every reviewer, carried-over findings, one reviewer per round, early cross-platform and publication checks, and the full test suite once at the final gate. The bundled reviewer instructions verify carried-over findings first and report only new BLOCKER or MAJOR findings.
- README sections for a quick start, the four files, slots and sessions, record formats, compute and long jobs, the repository layout and the design principles, with reviewed versions of the 5.1.0 diagrams.

### Fixed

- Windows short (8.3) path names such as `C:\Users\RUNNER~1` were read as home-directory paths, so job-binding checks found nothing for projects under such paths; only a leading `~` now means the home directory.
- The evaluation contamination audit read Python raw-string paths such as `r'/abs/path'` as relative paths on Linux and macOS.
- Tests now pass on Linux, macOS and the GitHub Windows runner (resolved temporary paths, macOS process identity without `/proc`, `dash` sourcing, Git for Windows `sh` aliases, UTF-8 file reads); CI lists every failing test and keeps the full report as an artifact.

### Changed

- The README no longer has a "Why v3" section.

## 6.0.0 — skill design v3

A major release after 5.1.0. "v3" names the skill design generation; the installable version is 6.0.0. Research Orchestrator is now a plugin for work projects, research, and competitions: one skill, host hooks, the `ro` command-line tool, and a read-only reviewer agent. Projects created with 5.1.0 keep working without changes; see Migration below. Earlier releases, up to 5.1.0, have no changelog entries; see the Git history.

### Added

- **Presets and profiles.** Six built-in presets (`quick`, `work-project`, `solo-research`, `team-research`, `competition-solo`, `competition-team`), `custom`, and saved user presets (`--save-preset <name>`, `--preset user:<name>`, stored under `~/.research-orchestrator/presets/`, overridable with `RESEARCH_ORCHESTRATOR_HOME`). `--list-presets` shows them. Profiles are `work` (input alias `normal`), `research`, and `competition`.
- **Settings.** `agents.md` gains `Preset`, `Profile`, `Workflow`, `Verification`, `Item size`, `Guards`, `Guard set`, `Guard thresholds`, `Language`, `Environment`, `Enforcement`, `Block`, `Read bound`, `External actions`, `Receipt policy`, `Publish scan`, `Brief requirements`, `Autonomy`, `Stale slot after`, `Queue freeze`, `Phase clock`, and `Competition`, each with an initializer flag. All 5.1.0 settings remain.
- **Setup answers.** `--answers` accepts the setup answers as a JSON object or UTF-8 JSON file keyed by setting names; explicit flags override its keys, and a missing answer prints a complete example command. Host detection recognises Claude Code, Codex, and Antigravity sessions.
- **Session slot choice.** When a new session's slot is ambiguous (several eligible slots, a stale taken slot, or resumable work without a continue/parallel intent), SessionStart and `ro brief` show compact ownership, activity, and job context, and the agent asks one combined continue/parallel/slot question. `Stale slot after` defaults to `2h`. Explicit choices reclaim a stale slot with a handoff event while preserving its claims, resumable state, and jobs; `Autonomy: away` starts and records a new parallel slot without asking.
- **Unified workflow.** One `## Queue` whose items carry `Claimed: none | <slot> since <time>`; `ro claim` locks, rereads, and writes the claim. The classic per-slot workflow remains. `--reconfigure --migrate` moves items between workflows with `*.pre-migrate` backups and a recovery journal (`.ro/migration.json`).
- **Staged items.** `Item size: staged` allows `Stages:` on long items and stage events headed `H-A-01/s2`. `Important stages:` designates stages that launch only with an independent receipt for their exact `:before` scope, even under `Receipt policy: self`. A decision-changing stage gets its own dated `Decision: changed` event with a `Review artifact` and needs an independent `:after` receipt before the item's dependent launches; routine stages stay lightweight.
- **Verification policies.** `independent-review` (a different session, such as a sub-agent, identified as `<kind>:<name>@<start time>`; discoveries record `Session:`), `hybrid`, and `self`, alongside 5.1.0's `cross-host-once`.
- **Evidence guards.** Research guards G1 (instrument registry under `## Instruments`, `I-` IDs) and G3 (family saturation); decision guards G5 (overrides and rejections), G6 (insights), GD (direction review), G8 (phase clock), G11 (selection), and G12 (effort, opt-in); E1 (external actions). Modes `off`, `light`, and `strict`, dated activation, `not applicable — <reason>` declarations, and configurable thresholds. Optional discovery `Control` evidence records a placebo/noise-floor artifact and selection gain for method, data and combined decisions; missing control emits `guard.control.missing` INFO, or WARN in strict mode.
- **External-actions ledger and receipts.** `## External actions` in `handoff.md` with `X-` IDs, an expectation written before acting, artifact hash, destination, result, and retry chains. `ro receipt add|check` binds a PASS or FAIL verdict to an artifact's SHA256 (files, or directories through a canonical manifest) under `Receipt policy: independent | self`; `competition-solo` defaults to `self`, every other preset to `independent`. `ro external` executes an outward command only after ledger, receipt, and duplicate validation; it journals each attempt in `.ro/external-attempts/` before running, matches that history by artifact hash and destination across action IDs, and keeps redacted results in `.ro/external-results/`.
- **`ro` CLI** (`skills/research-orchestrator/scripts/ro.py`): `next-id`, `dupcheck`, `index`, `claim`, `release`, `launch`, `monitor`, `kill`, `jobs`, `receipt`, `external`, `observe`, `brief`, `close`, `hook`, and `check`. `ro launch` binds a job's run directory, scripts, and explicit inputs (never the project root) and runs the job in an owned process group, or a job object on Windows; bindings and claims stay protected while any worker of that tree lives, and `ro kill` stops only an identity-verified tree. `ro close` keeps claims held by running or unmonitored jobs. Tool state lives in `.ro/` (jobs, receipts, ID reservations, ownership-aware locks, warnings, checker baseline), separate from the four coordination files.
- **Hooks.** `hooks/hooks.json` for Claude Code (SessionStart, PreToolUse, PostToolUse, Stop); portable wrappers `hooks/ro-hook.sh` and `hooks/ro-hook.cmd` that pick `RO_HOOK_PYTHON`, `python3`, `python`, or `py -3` and skip Windows Store placeholders; a Codex sample `hooks/codex-hooks.sample.json`; and a Git `hooks/pre-push.sample`. Check IDs include `shell.background`, `shell.detach`, `shell.heredoc`, `shell.cd`, `jobs.mutate-bound`, `jobs.read-bound`, `jobs.unmonitored`, `records.timestamp`, `records.id`, `publish.scan`, `external.gate`, `ask.away`, and `brief.requirements`. Each shell call is parsed in its tool's own Bash or PowerShell dialect. Uncertain parses warn and never block; per-call hooks fail open. Running-job read advice is opt-in (`Read bound: on`), identical warnings appear once per session, and the staged-content push pre-check only warns. SessionStart names optional checks the plugin's matchers do not subscribe to and reports `publish gate not installed` with its install command. Opt-in diagnostics write `.ro/hook-diagnostics.jsonl`.
- **Installer.** `python install.py --host claude-code|codex|both` installs the skill and merges host hooks; choose one host value. `--project <dir>` installs into a project's repository root, including its Git pre-push gate, so Claude Code configuration can be shared through `.claude/`; a nested folder is refused before anything is written. Existing hooks are preserved during the settings merge; replaced skill folders, prior skill-only installs, and foreign Git hooks remain intact with integration instructions. `--dry-run`, `--shim-only` (plugin CLI without a skill copy), `--no-hooks`, `--remove-hooks` (manual host hooks only; keeps the skill, Git gate, and unrelated hooks), and `--uninstall` support inspection, plugin coexistence, and removal. An active Claude Code plugin makes the installer remove duplicate manual registrations. Codex hooks need trust through `/hooks`. Copying the skill folder alone does not install hooks. The default shim (`--shim`, opt out with `--no-shim`) installs a `ro` entry point; SessionStart prints the resolved command prefix.
- **Publication scan.** Built-in secret patterns plus `Publish scan` entries (`literal:` text and a bounded `regex:` subset); the Git pre-push hook scans every outgoing commit.
- **Language and environment.** `Language` (default `en`) sets the language of free text in the four files and of replies; structural tokens stay English. `Environment: <os>/<shell>` declares the path semantics and fallback shell for checks. Setup infers both where possible and reports defaults with `Info:`; ask only when detection fails or is ambiguous and no explicit answer exists.
- **Project-rules region.** `## Project rules` in `agents.md` with `Standing rules` (4,096-byte budget), `Active overrides` (explicit check scope, reason, `Expires:`), and one-line `Lessons`; scaffolded from `templates/PROJECT_RULES.md.template`.
- **Planning aids.** `Queue freeze: off | until YYYY-MM-DD`, item `Ready by:`, Shared state `Paused:` for direction-review cadence, `Coverage: complete` for exhaustive measurements, and `N-` IDs for user-maintained notes.
- **Checker.** WARN and INFO severities beside ERROR, `--strict`, and `--baseline-update` (`.ro/checker-baseline.json`); a versioned template marker in `agents.md` with `agents.rules.edited`, `agents.rules.stale`, `settings.workflow.unmigrated`, and `migration.unfinished`.
- **Read-only reviewer agent.** `agents/ro-reviewer.md` (tools: Read, Grep, Glob) for Claude Code, plus `references/reviewer.md` so direct skill installs carry the same review instructions.
- [Post-close review](skills/research-orchestrator/references/postmortem.md) records lessons after a project closes.
- **Examples.** One example project per preset under `examples/`.
- **Evaluation tooling.** `scripts/evals/` runs and grades behaviour cases in the skill-creator format (the skill's `evals/` folder) against a pinned 5.1.0 baseline, with aggregation and a contamination audit; `scripts/trigger/` measures skill selection with a held-out split; `scripts/host/` runs installed-host hook dry runs and a Codex hook delivery probe. Results and their limits are indexed in `docs/evals/README.md`.
- **CI.** `.github/workflows/validate.yml` runs `scripts/validate_release.py` on Windows, Ubuntu, and macOS with Python 3.12 and read-only permissions. Timing tests carry the `latency` marker: release validation excludes them, and a separate CI step measures installed hook p95 on each OS and retains it as an artifact. `validate_release.py --skip-tests` runs the structural checks only. `.gitattributes` and `pytest.ini` support the test suite.

### Changed

- In multi mode, new same-host reviews no longer satisfy `cross-host-once`; use a different host. Qualifying legacy 5.1.0 reviews remain accepted. Adaptive mode retains the configured same-host fallback when another host is unavailable.
- New no-preset/custom projects use work-friendly defaults and the single detected host; existing projects retain compatibility settings. `solo-research` generates queue ordering; other research presets accept `--ordering queue`. Research without a collector can omit unused handoff summaries. Resource guidance covers exclusive resources such as shared databases and licensed seats.
- Host limits and 429/503 failures follow the [fresh-session retry rule](skills/research-orchestrator/references/compute.md).
- Work-profile takeovers no longer require Priority >= 15. Research and competition retain that floor only with priority ordering; queue ordering keeps the reasoned comparison. All retain idle-source, exhausted-own-work and one-item safeguards.
- Python **3.12+** is the CI-tested minimum for runtime and development tooling. All four READMEs and installer help/error paths state the requirement.
- Hook wrappers look for `agents.md` before starting Python, so calls outside a project need no interpreter. Stop and edit checks skip Python without job registries, unchanged PostToolUse calls skip it by file stamps, and unchanged compaction reuses the checker summary. These fast paths have a **150 ms p95** budget, met in local Windows measurements.
- Light presets show active/non-default settings and collapse defaults. Template v3.4 keeps only the version in its marker, stores the render key in `.ro/template-render.json`, and collapses single-host platform settings while preserving upgrades and reconfiguration. Generated reading pointers cover active non-default choices and defer ordinary operations to the core table.
- Renamed research-orchestrator-skill → research-orchestrator (repository, skill folder, skill name); the marketplace and plugin were always named research-orchestrator; marketplaces added from TaeyanG4/research-orchestrator-skill follow GitHub's rename redirect, or re-add TaeyanG4/research-orchestrator. The repository is https://github.com/TaeyanG4/research-orchestrator.
- The package is described as a plugin (skill, hooks, `ro` CLI, reviewer agent); manifests and default prompts cover work projects, research, and competitions and share version 6.0.0.
- Setup is **choose a preset → user name → that preset's questions**. The initializer is flag-driven, never prompts, and reports the defaults it used.
- `SKILL.md` is a core of at most 12 KB (5.1.0's was about 44 KB). Each topic moved to its own reference of at most 10 KB, read when its operation happens; daily hook use, installation and capability lookup, and operational safety are separate references. Startup reads the discovery index (`ro index`) instead of every entry, about 15 KB for every preset. Release validation enforces these budgets.
- The generated part of `agents.md` holds a template marker, preset summary, settings, and reference pointers. `--reconfigure` preserves `## Project rules` verbatim and refuses to overwrite hand-edited generated text without `--force`.
- Reasoned, expiring Active overrides can waive only supported process and ranking findings; structural consistency, live-job ownership, external-action receipts, and publication gates remain protected.
- Work profile lightening: scores and Priority are optional (queue order or `Next:`), items may use `Goal:` and default `Resource`/`Parallel`/`Other` to `CPU`/`NO`/`NONE`, discoveries are kept for reusable results, one session event lists `Completed:` items, and direction reviews need only Gap and Decisions. Research and competition may opt into `Ordering: queue`; all profiles share routing defaults, and supplied scores remain validated.
- Reviewer sub-agent review lines name the sub-agent's session (`subagent:<name>@<start time>`) rather than only its model; under `independent-review` a model name alone does not count (`discovery.review.identity`).
- Checker findings distinguish structural ERRORs, actionable WARNs, and INFO advice. Ordinary record field order and bare `none` are INFO; strict guards promote their selected evidence checks to ERROR, and `--strict` also fails on WARN.
- Domain-specific vocabulary is confined to the competition reference, its adapters, and competition examples, enforced by release validation.
- The 5.1.0 generated rules template is frozen in `templates/v2/AGENTS.md.template`, and the 5.1.0 worked example moved to `tests/fixtures/v2/`.
- The README in four languages was rewritten for 6.0.0 with four new diagrams and a work-project example.

### Removed

- The 5.1.0 six-question setup flow (name, platforms, Git sync, plan collector, reviewer, cross-check fallback). Presets now set the collector, reviewer, and fallback; flags still change them.
- 5.1.0 README images that no README links any more: `hero.svg`, `setup.svg`, `take-over.svg`, `cross-host-check.svg`, `why-use.webp`, and `hypothesis-relay.webp`.
- `examples/cv-leakage-study/` as a shipped example (kept as a test fixture).
- No 5.1.0 setting was removed.

### Fixed

- **Jobs and shell:** Failed runners retain their slot while descendants are live or unverified. Launch checks ownership, stages and resources; recovery preserves live-job protections, and shell checks recognize foreground waits.
- **Installation and hooks:** Lost pre-push registrations refuse pushes with repair guidance. Upgrades and uninstalls keep surviving runtimes and the shim, and plugin installs keep enabled supplemental hooks without duplicate registrations.
- **Records and verification:** Idle work and research retain INFO direction reminders until dated item activity. Closing an empty idle project records `Paused:`. Reviews follow the selected policy; timestamps share one tolerance.
- **State and migration:** Repairs and preset migrations preserve settings, rules, queue order and accepted 5.1.0 reviews, and validate before writing.
- **External actions and publication:** Duplicate actions are refused, platform adapters follow project settings, and publication gates scan outgoing history and recover missing interpreters.
- **Validation and runtime:** Broken installations report actionable errors, hook deadlines prevent stalled sessions, and release validation checks documentation links, package budgets and publication readiness.

### Security

- **Jobs and shell:** Process identity checks prevent PID reuse from releasing live-job protections; external-command cleanup verifies descendants before declaring completion.
- **Installation and hooks:** Per-call hooks fail open, while configured Git and external-action gates refuse execution when validation fails or cannot run; Codex hooks require established trust.
- **Records and verification:** Receipts bind artifact bytes, scope and destination to the configured reviewer policy; uncertain remote outcomes require reconciliation before retry.
- **State and migration:** Stored commands and external output are redacted and bounded; briefs omit stored commands and other sessions' prose, while diagnostics omit command and environment values.
- **External actions and publication:** Pre-push scans outgoing commits, paths and nested tag messages with replacement objects disabled, and keeps publication patterns bounded.
- **Validation and runtime:** Release checks scan `docs/`, including evidence ZIP members, for private-path, account-name, native-identifier and internal-session patterns; CI uses read-only permissions without persisted credentials.

### Migration

1. Save a recoverable snapshot of `agents.md`, `plan.md`, `discoveries.md`, `handoff.md`, and any `.ro/` state. Run the checker and resolve structural errors.
2. Move hand-written instructions from the generated part of `agents.md` into `## Project rules`; reconfiguration preserves that region verbatim.
3. Run `python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure` to keep the effective settings, or add `--preset <preset>` and its answers. If the workflow changes, release active slots and add `--migrate`.
4. Inspect the generated settings and preserved rules, including the legacy-review fingerprint comment when present; retain that comment with the project. Rerun the checker and log the change as a handoff event. Settings-only reconfiguration writes no backups; workflow migration writes backups and a recovery journal.
5. For `cross-host-once` in multi mode, arrange a different-host review for new findings; only qualifying legacy 5.1.0 same-host reviews remain accepted. If another host is unavailable, choose adaptive mode with the same-host fallback.
6. If you copied the skill folder by hand under its old name, replace that copy with `research-orchestrator` rather than keeping both. Marketplace installs need no rename step: the marketplace and plugin were always named research-orchestrator; marketplaces added from TaeyanG4/research-orchestrator-skill follow GitHub's rename redirect, or re-add TaeyanG4/research-orchestrator.

Read the [complete migration and rollback procedure](skills/research-orchestrator/references/migration.md) before changing workflows or using `--force`.
