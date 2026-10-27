<p align="center">
  <b>English</b> · <a href="README.ko.md">한국어</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a>
</p>

<p align="center">
  <img src="assets/readme/hero-v6.svg" alt="Research Orchestrator: work projects, research, and competitions across sessions, hosts, and users, coordinated through agents.md, plan.md, discoveries.md, and handoff.md" width="100%">
</p>

# Research Orchestrator

A plugin for Claude Code, Codex, and Google Antigravity that keeps work projects, research, and competitions moving across AI sessions. It bundles a skill, host hooks, the `ro` command-line tool, and a read-only reviewer agent. Four Markdown files hold the settings, the work queue, reusable findings, and a durable handoff. A preset decides how sessions share the queue, who reviews a finding, and which evidence checks apply.

**Release 6.0.2.** The changes from 5.1.0 are listed in [CHANGELOG.md](CHANGELOG.md). Existing projects keep working; read the migration section below before changing their settings.

## Why use it

<p align="center">
  <img src="assets/readme/why-use.webp" alt="Without orchestration, work loses context, repeats experiments, trusts a single model, and has no clear current best; with Research Orchestrator, agents.md, plan.md, discoveries.md, and handoff.md give shared memory, less duplication, cross-checked discoveries, and a clear current best with next hypotheses" width="100%">
</p>

Without shared records, each new AI session starts from scratch: context is lost, the same idea is tried twice, one model's unchecked claim steers the plan, and nobody can say which result is current. Research Orchestrator keeps that state in four plain files that any session, host, or user can read. Work resumes from a recorded resume point, a duplicate check comes before new items, findings can be reviewed by another session or host before others rely on them, and project-wide values such as the current best live in one place. The same holds for a multi-day work project, a research study, and a competition.

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

## Quick start

After installing, ask the agent to initialize Research Orchestrator in your project folder, or run the same steps yourself. `<skill-root>` is the installed folder that contains `SKILL.md`, and `ro` stands for `python <skill-root>/scripts/ro.py`:

```text
python <skill-root>/scripts/init_research_orchestrator.py . --preset work-project --user user1
python <skill-root>/scripts/check_project.py .
ro --session <host-session> --slot A brief
ro --session <host-session> --slot A next-id H
ro --session <host-session> --slot A claim <item>
ro --session <host-session> --slot A close
```

`<host-session>` is the ID that SessionStart prints after `Host session:`; when it is omitted, `RO_SESSION` or the Codex thread ID is used. The initializer writes the four files described next (`--list-presets` shows the other presets). `ro brief` restores the settings, hooks status, slot choice, claims, jobs, and checker counts. `ro next-id H` reserves an item ID for a new entry in `plan.md`; `ro claim` locks that item for your slot (unified workflow only); `ro close` releases idle claims, runs the checker, and reports what is left. In every session the agent repeats this cycle and records each finished item as the item lifecycle below describes.

## The four files

Every project keeps its coordination state in four lowercase Markdown files at the project root. `.ro/` holds tool state (jobs, receipts, reservations, locks, and the checker baseline), not coordination.

| File | Holds | Who edits it |
| --- | --- | --- |
| `agents.md` | preset summary, settings, reading pointers, and the `## Project rules` region (standing rules, expiring overrides, one-line lessons) | the initializer writes settings and pointers, and `--reconfigure` applies values you edit; everything from `## Project rules` on belongs to the user and is never regenerated |
| `plan.md` | unfinished items only; finished items leave the queue | classic: each slot its own `## Agent:` section, plus logged take-overs; unified: any slot, except items another active slot has claimed |
| `discoveries.md` | reusable findings with their evidence and review state | the source slot writes and revises its entry; eligible reviewers add review lines and set `Cross-check` |
| `handoff.md` | shared state, the event history, external actions, and each slot's resume point | each slot edits only its own `### Agent:` section; every session appends events and updates Shared state values |

Before editing a shared file, re-read it and patch only the relevant section or append an entry, so a stale copy never overwrites another session's work. Store each fact once and point to it elsewhere. [Records and shared-file edits](skills/research-orchestrator/references/records.md).

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
3. **Remaining preset questions**: the platform, `Environment`, and `Language` are inferred from detection and the request, and asked only when no explicit answer exists and detection fails or is ambiguous; defaults are reported with `Info:` (`Language` defaults to `en`). Competition presets also need the competition and phase clock. `--competition "kaggle/<slug> deadline=YYYY-MM-DD"` supplies adapter external-action patterns and the phase-clock deadline; an explicit `--phase-clock` takes precedence. Git sync is asked only inside a repository; `quick` needs only the preset and name, plus Git sync there.

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

The initializer writes the four coordination files and stores rendering metadata in `.ro/`. `Language` applies to free text only: headings, field names, IDs, status words, check IDs, and setting keys stay English so the checker, hooks, and `ro` keep working.

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

## Slots and sessions

A slot is named `A` to `Z`, then `AA` to `ZZ`; single-agent work uses `A`, and released slots are reused before a new one is created. Each slot has one `### Agent: <slot>` section in `handoff.md` with `Current host` (the platform, such as Claude Code or Codex, not the model), `Current user` (the person running it), `Current thread`, `Resumable state`, `Blocker`, and `Next action`. A slot is free only while `Current host` reads `unassigned` or `released`; any other value means taken, even when the session looks inactive.

**New sessions.** An explicit slot or continue/parallel intent is honoured, and a single eligible slot that is not stale is taken automatically. Otherwise SessionStart and `ro brief` list each candidate's owner, last activity, and running jobs, and the agent asks one question: continue a slot (reclaiming it if its session ended), start a parallel slot, or use a named slot. A taken slot is stale when it has no protected job and no event or claim within `Stale slot after` (default `2h`). Reclaiming is logged and keeps claims, resumable state, and jobs; `Autonomy: away` starts a new parallel slot without asking and records the choice for later. [Sessions](skills/research-orchestrator/references/sessions.md).

**Reading rule (classic).** A session reads its own plan and handoff sections in full. Of another active slot it reads only item metadata for dispatch or take-over, headings and `Hypothesis`/`Goal` lines for duplicate checks, and the `Current host`, `Current user`, and `Current thread` lines; resumable state and detailed evidence stay unread so each line of reasoning stays independent. New items and follow-ups go into your own section under your own IDs.

**Take-over (classic).** When your own queue runs out, re-read your section, take an eligible review, then take over a queued item from a same-host slot: one whose `Current host` is your host and that your own user runs, or a released or unassigned slot whose latest event came from your host or that has no events yet. Never take the owner's `Current thread`, an item under an `Active compute` claim, or anything from a slot another user is actively running. Move the item into your own section under your next ID with the old ID in the title (`H-A-05 — Retry policy for the nightly import (from H-C-03)`), retire the old ID, reconsider and rescore it, and log the take-over as a handoff event. One cross-host item may be taken by judgment, only from an idle slot after nearer work is exhausted.

<p align="center">
  <img src="assets/readme/take-over-v6.svg" alt="Classic workflow: slot A on Claude Code has an empty queue, so it takes over H-C-02 from released slot C, whose latest event came from Claude Code, as H-A-04 and retires the old ID; slot B runs on Codex with another active user, so its items stay with B" width="100%">
</p>

**Cross-host verification.** Under `cross-host-once`, every discovery records its `Host`, and a session on a different host reviews it once, because sessions on the same host share blind spots. The reviewer first claims the review (`Cross-check: REVIEWING <host> (<slot>)`) so no other session picks it up, then adds a dated review line and sets the state. The source slot never reviews its own discovery; a same-host review counts only in single mode or under the adaptive `Cross-check fallback: same-host`, and starts with `same host —`.

<p align="center">
  <img src="assets/readme/cross-host-check-v6.svg" alt="Under cross-host-once, slot A on Claude Code reviews D-B-003 from Codex and marks it VERIFIED; slot B on Codex has claimed the review of D-A-002 from Claude Code; slot C is released and reused first" width="100%">
</p>

[Classic workflow](skills/research-orchestrator/references/workflow-classic.md), [verification](skills/research-orchestrator/references/verification.md).

## Record formats

Field names, IDs, and status words stay English; free text follows `Language`. Reserve IDs with `ro next-id`: items are `H-<slot>-<NN>` and discoveries `D-<slot>-<NNN>`, numbered by the creating slot and never reused.

**Plan item, compact shape** (work profile, or any plan with `Ordering: queue`). `Claimed` appears only in the unified workflow:

```markdown
### H-A-02 — Retry policy for the nightly import
- Claimed: A since 2026-10-27 09:10
- Goal: make the nightly import retry transient failures
- Evidence: two of the last ten runs failed on a network timeout
- Next test: add bounded retries and replay one failed day
```

**Plan item, scored shape** (research and competition ranked by priority). Each factor is an integer from 0 to 3, and `Priority = 2*Impact + 2*Information + Confidence + Unblock + Diversity + (3-Cost)` (0–24). The highest score goes first; ties go to lower `Cost`, then higher `Information`. Omitted routing fields mean `CPU`, `NO`, and `NONE`:

```markdown
### H-A-04 — Repeat the speed-up with a cold cache
- Sources: D-A-003
- Hypothesis: the new parser keeps its lead when the cache is cleared before each run
- Evidence: D-A-003 (VERIFIED) measured a 30% shorter median run time, but every run reused a warm cache
- Improvement: clears the cache before each of 20 runs, which D-A-003 did not
- Impact: 2
- Information: 3
- Confidence: 2
- Unblock: 1
- Diversity: 1
- Cost: 1
- Priority: 16
- Resource: CPU
- Parallel: NO
- Other: NONE
- Next test: 20 cold-cache runs of each parser on one machine; compare the medians
```

**Discovery.** `Session:` records the source session, which `independent-review` and `hybrid` need. Each review line names the reviewer's host and slot, the verdict, and the review time:

```markdown
## D-A-003 — The new parser shortens warm runs by 30%
- Source: A
- Host: Claude Code
- User: user1
- Date: 2026-10-27
- Session: claude-code:A@2026-10-27T09:10
- Cross-check: VERIFIED
- Finding: the new parser cuts the median run time from 12.0 s to 8.4 s over 20 warm-cache runs each
- Evidence: runs/parser-bench/summary.csv; reproduce with scripts/bench.py --runs 20
- Implication: adopt the new parser for warm runs; cold-cache behaviour is still untested
- Reviews:
  - Claude Code (A): CLOSED — reviewer subagent:ro-reviewer@2026-10-27T10:02 — reviewed 2026-10-27T10:15 — reran the benchmark: 8.5 s median
```

**Handoff event.** Research and competition append one per completed item; the heading ends with the item ID:

```markdown
### 2026-10-27 10:20 — A — H-A-03
- Host: Claude Code
- User: user1
- Action: benchmarked the new parser against the old one (20 warm-cache runs each)
- Result: 30% shorter median run time; see D-A-003
- Artifacts: runs/parser-bench/summary.csv
- Discovery updates: D-A-003
- Review verdict: D-A-003 CLOSED
- Resource: CPU
- Other executor: none
- New plan items: H-A-04
```

The work profile keeps one session summary instead, updated as items finish:

```markdown
### 2026-10-27 17:40 — A — session
- Host: Claude Code
- User: user1
- Action: added bounded retries to the nightly import and replayed one failed day
- Result: the replayed day completed; the export schema check remains queued
- Completed: H-A-02
```

**Before adding an item**, run `ro dupcheck <terms>` and read the discovery index (`ro index`). A `VERIFIED` result with the same claim allows only a materially different follow-up with an `Improvement`, a `CHALLENGED` one waits until its challenge is resolved, and a `PENDING` one is better reviewed than repeated. Scan queued headings and `Hypothesis`/`Goal` lines too, then re-read `plan.md` just before writing; if the same item appeared meanwhile, keep the earlier one.

[Item fields, priority, and follow-ups](skills/research-orchestrator/references/plan-items.md), [records](skills/research-orchestrator/references/records.md).

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

<p align="center">
  <img src="assets/readme/hypothesis-relay.webp" alt="From evidence to hypothesis H1, branched into sub-hypotheses H1a and H1b tested separately; cross-checking reduces hallucination risk, the results merge into a grounded insight, and new hypotheses H2 and H3 follow" width="100%">
</p>

In research the loop compounds: evidence suggests a hypothesis, its sub-hypotheses run as separate items, reviews check each finding, and the grounded result seeds the next hypotheses through follow-ups.

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

## Compute and long jobs

Queue order or Priority decides what runs next; routing decides where. `Resource: CPU | GPU | EITHER` is the local compute class, `Parallel: YES | NO` says whether the item may share it, and `Other: NONE | <name>` names an exclusive non-compute resource or external executor, such as a shared database, a licensed seat, or a cloud batch runner. Start with two parallel slots when that helps, and add more only while independent high-value items and resource headroom remain.

Before using an exclusive resource, re-read `handoff.md` and check the machine's real usage, add a claim to the `Active compute` line in Shared state, and launch through `ro launch`, which also reserves the item's local resource under the project lock:

```markdown
- Active compute: CPU — A (H-A-04, since 2026-10-27 14:05)
```

```text
ro --slot A launch --item H-A-04 --expect 2h --run-dir runs/h-a-04 --error "Traceback" -- python scripts/bench.py --runs 20 --cold
ro monitor <job>
ro jobs
ro kill <job>
```

Start the printed monitor command at once: a confirmed launch only proves that the job started. `ro monitor` follows the job until it completes, matches an error pattern, falls silent past a configured heartbeat limit, or runs twice the expected time; `ro jobs` lists jobs and monitor state, and `ro kill` stops an identity-verified process tree that your slot owns. Append the printed Job line to `handoff.md`, inspect the artifacts, and remove the claim only after the job has verifiably ended. While a needed resource is busy, take independent work or an eligible review, or record a `Blocker:`. Two items share a resource only when both are `Parallel: YES` and measured capacity fits; `Other` resources need their own lock or scheduler reservation, because `ro launch` reserves only local CPU and GPU.

[Workers and exclusive resources](skills/research-orchestrator/references/compute.md), [launch, monitor, and stop](skills/research-orchestrator/references/operations-safety.md#lookup-launch-monitor-and-stop).

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

The Claude Code plugin subscribes to `AskUserQuestion` and `Agent`; their wrappers skip Python when `Autonomy: away` and `Brief requirements` are inactive. Read-bound subscriptions remain opt-in through the installer. SessionStart and `ro brief` print `publish gate not installed` and `install.py --project <checkout root>` only when a Git checkout lacks its registered pre-push gate; a registered gate handles the publication scan without a duplicate per-call scan, and the per-call advisory reads the checkout the push runs in. Wrappers resolve project hints separately from the command working directory and need no interpreter outside a project. Stop and edit checks skip Python without a job registry. PostToolUse reuses stable file stamps only after two seconds, and briefs invalidate cached checks when review receipts or artifacts change; a brief hashes at most 64 MiB of review evidence and lists the rest as unverified for `check_project.py` to verify. Saved Windows measurements cover 23–36 ms p95 for outside-project and job-free Stop/edit calls, and 48–125 ms for ordinary shell checks and unchanged PostToolUse; they do not establish new supervised-child timings.

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

4. A `Workflow` change also needs `--migrate`; release active slots first. Every settings transition validates the proposed records before writing. Compatible goal and review fields are normalized without losing evidence or effective queue order. Changes to coordination files use `*.pre-migrate` backups and a recovery journal, including when the workflow stays the same.
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

The light check covers manifest versions, README structure and links, SVG validity, size budgets for the core and references, domain vocabulary, record formats, and the example projects. Release checks scan `docs/`, including evidence ZIP members, for private-path, account-name, native-identifier and internal-session patterns. The full check adds the deterministic test suite and the initialization and reconfiguration scenarios. Timing tests carry the `latency` marker and run separately with `python -m pytest -q -m latency tests/test_ro_cli.py tests/test_ro_hooks.py`.

GitHub Actions runs the full check on Windows, Ubuntu, and macOS with Python 3.12 and read-only permissions, then measures installed hook p95 on each OS and keeps the result as an artifact. Development tooling for behaviour cases, trigger evaluation, and installed-host dry runs lives in [scripts/evals](scripts/evals/README.md), [scripts/trigger](scripts/trigger/README.md), and `scripts/host/`.

## Evidence

Behaviour evidence is historical (saved runs, not this exact release), Codex hooks were verified only with per-invocation trust, Windows timings are local, and the release 6.0.1 CI run passed on Windows, Ubuntu and macOS with installed-hook p95 of about 45–60 ms; see the [evidence and limits](docs/evals/README.md).

## Repository layout

```text
.claude-plugin/  .codex-plugin/  .agents/   plugin and marketplace manifests
agents/ro-reviewer.md          read-only reviewer agent for Claude Code
assets/readme/                 README images
docs/                          plans, evaluation evidence, and host dry runs
examples/                      one worked project per preset
hooks/                         host hook wrappers and the Git pre-push gate
scripts/                       release validation, evaluation and trigger tooling, host dry runs
skills/research-orchestrator/
  SKILL.md                     the core instructions (12 KB budget)
  references/                  one file per operation, read when that operation runs
  templates/                   the four project files, plus earlier versions for migration
  presets/                     the six built-in presets
  scripts/                     initializer, checker, ro CLI, and hook runner
  agents/openai.yaml           Codex interface metadata
  evals/                       behaviour cases (not installed)
tests/                         deterministic test suite
install.py                     installer for Claude Code, Codex, or both
plugin.json                    plugin manifest
```

## Design principles

- **General first.** One skill serves everyday work projects, research, and competitions. Shipped instructions use neutral words; competition material lives only in its reference and platform adapters, and a release check enforces the vocabulary.
- **Lean core.** `SKILL.md` stays within 12 KB. Each detailed rule lives in one reference that is read when its operation runs, and the generated `agents.md` holds settings, pointers, and project rules rather than copied skill text.
- **Deterministic checks only.** Guidance comes first, then the host-independent checker, then advisory hooks. Blocking is reserved for deterministic, costly, repeated mistakes named in `Block`.
- **Hooks fail open, gates fail closed.** Per-call hooks let a call through on a crash, timeout, or missing interpreter; `ro launch`, `ro external`, and the Git pre-push gate refuse when their validation fails or cannot run.
- **One home per fact.** Claims and numbers live in the discovery, who, when, and where in the event, proposed work in `plan.md`, and project-wide values in Shared state; everything else points to them.
- **Evidence over intent.** Guards check that the evidence behind a decision was recorded, a confirmed launch is not a result, and a finding is verified only by an eligible review.
- **No rule bloat.** Standing rules have a byte budget, overrides expire, and each lesson is one line naming the check that enforces it.

## License

[MIT](LICENSE).
