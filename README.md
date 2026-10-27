<p align="center">
  <b>English</b> · <a href="README.ko.md">한국어</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a>
</p>

# Research Orchestrator

A plugin for Claude Code, Codex, and Google Antigravity that keeps work projects, research, and competitions moving across AI sessions. It bundles a skill, host hooks, the `ro` command-line tool, and a read-only reviewer agent. Four Markdown files hold the settings, the work queue, reusable findings, and a durable handoff. A preset decides how sessions share the queue, who reviews a finding, and which evidence checks apply.

**Release 6.0.0 (skill design v3).** The changes from 5.1.0 are listed in [CHANGELOG.md](CHANGELOG.md). Existing projects keep working; read the migration section below before changing their settings.

## Why v3

Post-mortems of three past projects run with the previous design found strong execution and weak strategy. All three trusted measurements that could not see the final target, left a core approach untested, spent the final stretch on small variants, and recorded diagnoses that never changed the plan. One project also logged 28 operational mistakes, some repeated three or four times, while its checker findings grew from 234 to 452 and stopped being read. Version 6.0.0 turns these lessons into selectable workflows, evidence guards that check whether the evidence behind a decision was recorded, and a few deterministic safety checks. Small work gets lighter presets, and detailed rules load only when an operation needs them. The same workflow keeps work projects, such as a data migration, moving through a clear queue and durable handoffs.

## Install

Python 3.12+ (the CI-tested minimum) must be on `PATH`. Install through the Claude Code plugin, or run `python install.py --host claude-code`, `python install.py --host codex`, or `--host both` from a checkout. Copying only the skill folder installs no hooks.

Windows: Git Bash (`sh`) must also be installed.

### Claude Code plugin (recommended)

Inside Claude Code:

```text
/plugin marketplace add TaeyanG4/research-orchestrator
/plugin install research-orchestrator@research-orchestrator
```

The GitHub repository serves as the marketplace. The plugin registers the hooks and the `ro-reviewer` agent, and updates follow the plugin version. Start a new session after installing; `ro brief` should report `hooks active`.

If the `ro` shim is missing, SessionStart and `ro brief` print the exact `--shim-only` command for the installed plugin. It creates a `ro` entry point for that runtime without copying the skill or hooks.

### Codex

From a checkout or an extracted release:

```bash
python install.py --host codex
```

This installs the skill and the hook settings together; the optional Codex marketplace plugin (`codex plugin marketplace add TaeyanG4/research-orchestrator`) registers no hooks. Trust the installed hooks through `/hooks` (enable `features.hooks` if your version needs it); until then, rely on `ro` commands and Git pre-push. See [host evidence and trust scope](skills/research-orchestrator/references/hooks-capabilities.md).

### Without plugins

```bash
git clone https://github.com/TaeyanG4/research-orchestrator.git
cd research-orchestrator
python install.py --host both
```

`--host` takes `claude-code`, `codex`, or `both` (the default), and the default scope is your user account. `--project <dir>` installs into a project instead and registers its Git pre-push gate behind a shared dispatcher; name the repository root, because a nested folder is refused before anything is written. Committing the project's `.claude/` shares the Claude Code setup; Codex project hooks use absolute paths, so reinstall after moving a checkout. User installs need the gate separately in each repository.

Other options: `--dry-run` previews changes, `--uninstall` moves the installation into backups, `--no-hooks` installs the skill and shim without host or Git hooks, `--remove-hooks` removes only manual host hooks (keeping the skill, Git gate, and unrelated hooks), and `--no-shim` skips the default `ro` shim. The installer preserves unrelated hooks and backs up what it replaces; with the Claude Code plugin active, it removes duplicate manual registrations. An existing custom pre-push hook stays intact, with instructions to integrate [the pre-push sample](hooks/pre-push.sample).

### Releases and offline use

`main` is the latest stable version; tags use `vX.Y.Z`, and each GitHub Release carries the CHANGELOG notes and a zip asset. For offline use, extract the zip from [GitHub Releases](https://github.com/TaeyanG4/research-orchestrator/releases) and run the same `install.py` commands from that folder. To try the plugin without installing:

```text
claude --plugin-dir <folder>
```

### Google Antigravity

Copy `skills/research-orchestrator/` into `<project>/.agents/skills/research-orchestrator/` or globally into `~/.gemini/config/skills/research-orchestrator/` (older CLI location: `~/.gemini/antigravity-cli/skills/research-orchestrator/`); `/skills` confirms discovery. Setup detects an Antigravity session and records it as the host. There is no installer target or hook adapter: use `ro` and install the [Git pre-push gate](skills/research-orchestrator/references/publication-safety.md) manually.

## Presets

A preset fills the settings block in `agents.md`; every value stays visible and editable there. *Profile* is the kind of work, *workflow* is how sessions share the queue, and *verification* is who must review a finding.

| Preset | For | Profile | Workflow | Item size | Guards | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| [`quick`](examples/quick-script-cleanup/README.md) | short work by one agent | work | classic | short | off | self |
| [`work-project`](examples/work-project-data-migration/README.md) | a multi-day migration, analysis, or build | work | unified | staged | light | independent-review |
| [`solo-research`](examples/solo-research-literature-replication/README.md) | long research by one agent (recommended for research) | research | unified | staged | light | independent-review |
| [`team-research`](examples/team-research-cv-leakage/README.md) | several sessions or hosts in parallel (the 5.1.0 way) | research | classic | short | light | cross-host-once |
| [`competition-solo`](examples/competition-solo-tabular/README.md) | a competition run mainly by one agent | competition | unified | staged | light | independent-review |
| [`competition-team`](examples/competition-team-forecasting/README.md) | a competition with parallel sessions or hosts | competition | classic | short | light | hybrid |

- **Enforcement:** every preset uses `Enforcement: block` with `Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan`; the competition presets add `external.gate`.
- **Platforms:** solo presets run on one detected platform (`Cross-check fallback: same-host`); team presets default to `Claude Code, Codex` (`wait`).
- **Receipts:** `Receipt policy` is `self` for `competition-solo` and `independent` otherwise, where another session must sign an artifact receipt.
- **Sub-agents:** the plan collector and reviewer start `off`; queue limits are `stop at 50, resume at 5`.
- **Custom and saved presets:** `custom` or no preset gives new projects work-friendly defaults and the single detected host; existing projects keep compatibility settings. `--save-preset <name>` saves settings for `--preset user:<name>`.

Each preset links to a worked example project. [Settings, precedence, and user presets](skills/research-orchestrator/references/presets.md).

## Setup

After installing, ask the agent to initialize Research Orchestrator. It collects these answers together and skips any you have already given:

1. **Preset**: one of the six above (`--list-presets` also shows your saved presets).
2. **Your name**: one word recorded as the session's user, such as `user1`.
3. **Remaining preset questions**: the platform, `Environment`, and `Language` are inferred from detection and the request, and asked only when no explicit answer exists and detection fails or is ambiguous; defaults are reported with `Info:` (`Language` defaults to `en`). Competition presets also need the competition and phase clock. Git sync is asked only inside a repository; `quick` needs only the preset and name, plus Git sync there.

The agent then runs the initializer, which takes flags and never prompts; `<skill-root>` is the installed directory that contains `SKILL.md`. `--answers` takes the same answers as a JSON object or file, keyed by setting names with underscores plus `name`, `user`, `agents`, and `ordering`; explicit flags override its keys. When an answer is missing, the error prints a complete example command.

```text
python <skill-root>/scripts/init_research_orchestrator.py --list-presets
python <skill-root>/scripts/init_research_orchestrator.py . -n "<project>" --preset work-project --user <user> --platforms "<host>" --environment linux/bash --language en
python <skill-root>/scripts/init_research_orchestrator.py . --answers answers.json
python <skill-root>/scripts/check_project.py .
```

<p align="center">
  <img src="assets/readme/setup-flow.svg" alt="Setup: preset, name, unresolved questions only; detected defaults reported. Four coordination files and .ro/template-render.json." width="100%">
</p>

| File | Holds |
| --- | --- |
| `agents.md` | preset summary, settings, reading pointers, and the user-owned `## Project rules` region (standing rules, expiring overrides, one-line lessons) |
| `plan.md` | unfinished items only; finished items leave the queue |
| `discoveries.md` | reusable findings with their evidence and review state |
| `handoff.md` | shared state, the event history, external actions, and each slot's resume point |

The initializer writes the four coordination files and stores rendering metadata in `.ro/`. `Language` applies to free text only: headings, field names, IDs, status words, check IDs, and setting keys stay English so the checker, hooks, and `ro` keep working.

**New sessions.** An explicit slot or continue/parallel intent is honoured, and a single eligible slot that is not stale is taken automatically. Otherwise SessionStart and `ro brief` list each candidate's owner, last activity, and running jobs, and the agent asks one question: continue a slot (reclaiming it if its session ended), start a parallel slot, or use a named slot. A taken slot is stale when it has no protected job and no event or claim within `Stale slot after` (default `2h`). Reclaiming is logged and keeps claims, resumable state, and jobs; `Autonomy: away` starts a new parallel slot without asking and records the choice for later. [Sessions](skills/research-orchestrator/references/sessions.md).

## Workflows

Slots (`A`, `B`, … `AA`) name lines of work, not tools or people, so any host can continue a slot.

<p align="center">
  <img src="assets/readme/workflows.svg" alt="Classic: each slot owns an Agent section of plan.md and items change owner only by a logged take-over. Unified: one shared Queue where each item carries a Claimed line and ro claim locks, rereads, and writes the claim" width="100%">
</p>

### Classic

Each slot owns one `## Agent: <slot>` section of `plan.md` and reads only its own detailed section; duplicate checks, dispatch, and take-overs use narrow metadata reads. An item changes owner only through a logged take-over, and items normally stay with that host. This is the 5.1.0 behaviour and the default for projects without a `Workflow` line. [Classic workflow](skills/research-orchestrator/references/workflow-classic.md). The [one-item cross-host takeover exception](skills/research-orchestrator/references/workflow-classic.md#cross-host-take-over-by-judgment) requires an idle source, exhausted nearer work and the listed eligibility conditions.

### Unified

One `## Queue` holds every item, each starting with `Claimed: none` or `Claimed: <slot> since <time>`. `ro claim` takes the project lock, rereads the queue, and writes the claim, so two slots cannot claim the same item. Anyone may refine an unclaimed item; nobody edits an item another active slot has claimed. [Unified workflow](skills/research-orchestrator/references/workflow-unified.md).

In either workflow, `Item size: staged` lets a long item declare `Stages:` and log stage events. A stage listed in `Important stages:` launches only with an independent receipt for its exact `:before` scope, even under `Receipt policy: self`. A stage whose result changes a decision gets its own dated event with `Decision: changed`, a discovery, and an independent `:after` receipt before the item's next launch. [Staged items](skills/research-orchestrator/references/staged-items.md).

Changing `Workflow` moves items, so it needs `--reconfigure --migrate`.

## Item lifecycle

<p align="center">
  <img src="assets/readme/lifecycle.svg" alt="Item lifecycle: claim or own, work, record a discovery and an event, derive follow-ups, then close by removing the item from plan.md" width="100%">
</p>

1. **Claim or own** an item through the workflow, after a duplicate check (`ro dupcheck`).
2. **Work**: run the next useful test. Long jobs go through `ro launch` and `ro monitor`; a confirmed start is not a result.
3. **Discovery**: record the outcome in `discoveries.md`, including negative and inconclusive results. Review follows the `Verification` setting: `self` (none required), `cross-host-once` (once, by a different host), `independent-review` (a different session, such as a sub-agent), or `hybrid` (either form).
4. **Event**: append a `handoff.md` event that points to the discovery.
5. **Follow-ups**: queue what the result implies, or record why nothing follows.
6. **Close**: remove the finished item from `plan.md`. Finish discovery, event, follow-ups, and removal together before starting something else.

After closing a project, use the [post-close review](skills/research-orchestrator/references/postmortem.md) to record lessons. For host limits or 429/503 failures, apply the [fresh-session retry rule](skills/research-orchestrator/references/compute.md).

Under `cross-host-once`, a different slot is required; same-host review counts in single mode, or in adaptive mode with `Cross-check fallback: same-host`. When no eligible reviewer can run, leave the discovery `PENDING` and complete the handoff and close without polling.

The work profile (`quick`, `work-project`) is lighter. Scores and Priority are optional, so queue order or a `Next:` line decides; discoveries are kept for reusable results (a settled decision, a dead end, a verified dependency); one session event lists the completed items. Research and competition keep the full record for every item. [Item fields and follow-ups](skills/research-orchestrator/references/plan-items.md), [records](skills/research-orchestrator/references/records.md), [verification](skills/research-orchestrator/references/verification.md), [sessions](skills/research-orchestrator/references/sessions.md).

`solo-research` generates `Ordering: queue`; other research and competition projects can also select it. Supplied scores remain validated.

## Guards

Guards check that the evidence behind a decision was recorded; they do not judge its quality. `Guards: light` reports gaps as warnings, `strict` turns each guard's listed checks into errors, and `off` disables them. Activation is dated (`light since YYYY-MM-DD`), so earlier records are exempt. A guard can be declared `not applicable — <reason>` once in Shared state, and thresholds are configurable. Optional discovery `Control` records a placebo/noise-floor artifact and selection gain. Missing control is the exception: `guard.control.missing` is INFO in light mode and WARN in strict mode.

| Guard | What it asks for | `Guard set: auto` enables it for |
| --- | --- | --- |
| G1 Instrument evidence | provenance, coverage, agreement, and resolution of the measurement that decided a finding | research, competition |
| G3 Family saturation | a more resolving instrument or a reviewed structural change after repeated ties in one family | competition |
| G5 Overrides and rejections | a re-check trigger and expiry for each override; proof that a rejected change actually ran | all profiles |
| G6 Insights | a due time for each diagnosis, then a planned item or an evidenced rejection | all profiles |
| GD Direction review | a periodic review of the gap and decisions (fuller for research and competition) | all profiles |
| G8 Phase clock | milestones within the `Phase clock` window | competition |
| G11 Selection | final picks whose shared family is explained | competition |
| G12 Effort | the share of process work versus work that can change the outcome | explicit opt-in only |
| E1 External actions | an expectation written before an outward action, the artifact hash, and no unmarked duplicates | all profiles |

[Research guards](skills/research-orchestrator/references/research-guards.md), [decision guards](skills/research-orchestrator/references/decision-guards.md), [external actions](skills/research-orchestrator/references/external-actions.md), [competition profile](skills/research-orchestrator/references/competition.md).

## The `ro` CLI

`ro` stands for `python <skill-root>/scripts/ro.py`. Commands are authoritative and work on every host; hooks only run them sooner. Global options are `--project`, `--slot`, and `--session`; each command has `--help`.

| Command | Purpose |
| --- | --- |
| `next-id {D,H,I,X,N}` | reserve the next discovery, plan item, instrument, external action, or note ID |
| `dupcheck <terms>` | search headings and key lines, including archived records, before adding work |
| `index [ID]` | print the discovery index, or one full entry |
| `claim <item>`, `release <item>` | claim a unified-queue item under the project lock, or release it |
| `launch --item … --expect … -- <command>` | start an owned job with bound inputs and outputs, error patterns, heartbeat, a confirmation window, and optional `--require-receipt` |
| `monitor <job>`, `jobs [--prune]`, `kill <job>` | follow a job to its outcome, list job and monitor state, stop an identity-verified owned process tree |
| `receipt add`, `receipt check` | bind a PASS or FAIL verdict to an artifact's SHA256 under `Receipt policy`, or verify it |
| `external --action <X-id> -- <command>` | run an outward command only after ledger, receipt, duplicate, and attempt-history checks pass |
| `observe <key> <value>` | record a volatile Shared state fact; optional `--source`, `--ttl` defaults to `6h` |
| `brief [--max N]` | a facts-only session brief: settings, hooks self-test, slot choice, claims, jobs, overdue guards, checker counts |
| `close` | keep claims for running or unmonitored jobs, release the others, run the checker, and report what is left |
| `hook <event>` | host hooks consume JSON on stdin; `pre-push` consumes Git ref-update lines |
| `check <command>` | run the shell checks on a command string (`--dialect bash` or `powershell`) |

Jobs run in an owned process group, or a job object on Windows. A launcher that exits while its workers continue keeps its bindings and claims, and a failed runner keeps its slot while descendants are live or unverified. `ro kill` verifies slot ownership, PID, and start time, so a reused PID is never a target. `ro external` journals each attempt before running it and matches that history by artifact hash and destination, so editing, withdrawing, or renaming a ledger entry cannot hide an earlier attempt; an interrupted or timed-out action stays `unknown` until reconciled.

[Operational commands and their limits](skills/research-orchestrator/references/operations-safety.md), [external actions and receipts](skills/research-orchestrator/references/external-actions.md).

## Safety by host

Trust Codex hooks through `/hooks` before relying on them; `ro` commands and Git pre-push remain the execution gates.

<p align="center">
  <img src="assets/readme/safety-layers.svg" alt="Hooks, ro commands and Git pre-push; see linked host capability evidence." width="100%">
</p>

| Host | Per-call hooks | What protects execution |
| --- | --- | --- |
| Claude Code | Plugin hooks or `install.py --host claude-code` | `ro`, Git pre-push |
| Codex | `install.py --host codex`; requires hook trust | `ro`, Git pre-push |
| Google Antigravity | none; command-only | `ro` commands and the Git pre-push publish scan |

- `Enforcement: off` is silent, `warn` never blocks, and `block` denies only the checks listed in `Block`.
- **Each shell call is parsed in its tool's own dialect** (Bash or PowerShell), even when that differs from `Environment`, which still sets path semantics and the fallback shell. Uncertain parses warn, never block.
- Per-call hooks fail open on a crash, timeout, malformed input, or missing interpreter; `ro brief` reports the hooks self-test and warning counts. `ro external`, `ro launch`, and the Git pre-push gate refuse when their validation fails or cannot run; pre-push scans every outgoing commit, including messages and paths.
- Hooks prevent accidents in cooperating sessions; they are not an adversarial security boundary. Nested interpreter bodies, here-string bodies, aliases, dynamic paths, and encoded secrets are outside reliable parsing.

With the Claude Code plugin, SessionStart names optional checks its matchers do not cover and prints `install.py --project .` to subscribe them; SessionStart and `ro brief` also report `publish gate not installed`, with the install command, when a Git checkout lacks the pre-push gate. Wrappers look for `agents.md` before starting Python, so calls outside a project need no interpreter. Stop and edit checks skip Python when no job registry exists, unchanged PostToolUse calls skip it by file stamps, and unchanged compaction reuses the checker summary. Measured on Windows, the p95 per call is 23–36 ms outside a project and for Stop or edits without jobs, and 48–125 ms for ordinary shell checks and unchanged PostToolUse, within the 150 ms budget.

[Hooks, capability matrix, and trust](skills/research-orchestrator/references/hooks-capabilities.md), [publication gate](skills/research-orchestrator/references/publication-safety.md).

## Migration from 5.1.0

Updating the installed plugin does not rewrite existing projects: missing settings keep the 5.1.0 behaviour (classic workflow, short items, cross-host-once verification, guards off). For manual installations, replace the previous skill folder with `research-orchestrator` rather than keeping both; see the CHANGELOG rename note.

Accepted 5.1.0 `multi`/`same-host` reviews remain valid. Reconfiguration preserves their fingerprints in `agents.md`; new reviews follow the current verification rules.

1. Save a recoverable copy of the four files and any `.ro/` state, run the checker, and fix structural errors.
2. Move hand-written instructions from the generated part of `agents.md` into `## Project rules`; reconfiguration preserves that region verbatim.
3. Refresh the generated settings and reading pointers. Add `--preset <preset>` and its answers to adopt a preset; the second command switches a classic project to the unified workflow:

```text
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --workflow unified --migrate --user <user>
```

4. A `Workflow` change also needs `--migrate`; release active slots first. Workflow migration writes `*.pre-migrate` backups and a recovery journal, while a settings-only reconfiguration does not.
5. Inspect the result, rerun the checker, and log the change as a handoff event.

Read the [migration and rollback procedure](skills/research-orchestrator/references/migration-v2-to-v3.md) before changing workflows or using `--force`.

## Validation and CI

In a project, run `python <skill-root>/scripts/check_project.py .` at session start, after a take-over or migration, and before closing (`ro close` runs it too). ERROR findings exit 1, WARN findings fail only with `--strict`, INFO is advice, and exit 2 means the project could not be read. `--baseline-update` stores finding fingerprints so later runs flag new issues without hiding old ones.

For this repository, install pytest, then run the light structural check, the deterministic tests, or the full release check:

```bash
python scripts/validate_release.py --skip-tests
python -m pytest -q -m "not latency"
python scripts/validate_release.py
```

The light check covers manifest versions, README structure and links, SVG validity, size budgets for the core and references, domain vocabulary, record formats, and the example projects. Release checks scan `docs/`, including evidence ZIP members, for private-path, account-name, native-identifier and internal-session patterns. The full check adds the deterministic test suite and the initialization and reconfiguration scenarios. Timing tests carry the `latency` marker and run separately with `python -m pytest -q -m latency`.

GitHub Actions runs the full check on Windows, Ubuntu, and macOS with Python 3.12 and read-only permissions, then measures installed hook p95 on each OS and keeps the result as an artifact. Development tooling for behaviour cases, trigger evaluation, and installed-host dry runs lives in [scripts/evals](scripts/evals/README.md), [scripts/trigger](scripts/trigger/README.md), and `scripts/host/`.

## Evidence

Behaviour evidence is historical (saved runs, not this exact release), Codex hooks were verified only with per-invocation trust, Windows timings are local, and CI results stay pending until publication; see the [evidence and limits](docs/evals/README.md).

## License

[MIT](LICENSE).
