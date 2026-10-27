# Changelog

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

Read the [complete migration and rollback procedure](skills/research-orchestrator/references/migration-v2-to-v3.md) before changing workflows or using `--force`.
