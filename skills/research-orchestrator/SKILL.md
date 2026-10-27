---
name: research-orchestrator
description: "Coordinate work projects, research, and competitions with a queue, reusable discoveries, independent review, resource routing, and durable handoffs. Use when starting or resuming work that needs persistent project coordination, prioritizing its tasks or hypotheses, coordinating parallel agents, or reviewing and preserving its findings—even without an explicit orchestration request. Standalone answers and isolated reviews do not require this workflow."
---

# Research Orchestrator

Preserve evidence and next steps across sessions. Put unfinished work in the queue, record what each step establishes, and leave a handoff that another session can continue. Presets choose workflow and safeguards.

## The four files and `.ro/`

Use these lowercase project files across sessions:

| File | Purpose |
| --- | --- |
| `agents.md` | Settings, reading pointers, and user-owned project rules |
| `plan.md` | Active unfinished items |
| `discoveries.md` | Reusable findings and their verification state |
| `handoff.md` | Shared state, event history, and slot resume points |

For configured-language prose and stable structural keys, follow [references/records.md](references/records.md).

Keep coordination in these four files to avoid competing state. Linked `docs/` records hold archived history (`ro archive`), supporting evidence, retrospectives and the tool registry. `.ro/` is tool state, not a coordination file; see [references/operations-safety.md](references/operations-safety.md).

## Setup

For a new project, ask for the following together before creating files, using answers already present in the request:

1. **Preset:** show the choices from [references/presets.md](references/presets.md), or run `python <skill-root>/scripts/init_research_orchestrator.py --list-presets`. Recommend `solo-research` for research and `work-project` for everyday work.
2. **User name:** the identity recorded for the person running this session. Naming rules and slot selection live in [references/sessions.md](references/sessions.md).
3. **Other choices:** use detected hosts/environment and infer Language; ask only if unclear. Use `--platforms`/`--language` for overrides. Collect remaining preset `asks` (Git only in a repository). `Info:` reports defaults.

Initialize with those answers:

```text
python <skill-root>/scripts/init_research_orchestrator.py . --preset quick --user <user>
```

Replace `quick` with the chosen preset. `<skill-root>` contains this file. The initializer creates missing files; `--agents` sets the slot count or unique slot names.

For an existing project, use its settings instead of repeating setup. Establish the user identity and take or resume a slot through [references/sessions.md](references/sessions.md). For an older template, missing settings, or a workflow change, read [references/migration.md](references/migration.md) before rewriting anything.

## Read order

1. Start with only this core, `agents.md`, and the project records needed to resume. Read each reference when performing its operation, using the table below; an enabled setting is not a startup reading assignment.
2. Read the `discoveries.md` index (`ro index`): live record headings and `Finding`, `Status`, and `Cross-check` lines. Open full entries when they match a proposed item, supply a premise, or need review. The index keeps settled, negative, and inconclusive results visible without loading every evidence trail; `ro dupcheck` also searches archives.
3. Read `handoff.md` Shared state, your own active section, and events relevant to resuming your work.
4. Read your own classic plan section, or unified items you are considering. For duplicate checks, scan all item headings and `Hypothesis`/`Goal` lines. Consult the workflow reference before claiming or moving work.
5. Run the checker below, or use the fresh checker result supplied by SessionStart.

Another active slot's resumable state and detailed evidence are private, so reasoning stays independent; the workflow references define the narrow exceptions.

## Item lifecycle

1. **Claim or own:** select work through the active workflow. Use [references/plan-items.md](references/plan-items.md) for duplicate checks, scoring, and item fields before adding or choosing an item.
2. **Work:** run the next step that can change a decision (a test, a comparison, a build, a draft). Search `ro tools` before writing a script. For long jobs, follow [launch, monitor, record, close](references/operations-safety.md#lookup-launch-monitor-and-stop); confirmation is not completion.
3. **Discovery:** record reusable findings and decisions, including negative or inconclusive experiment outcomes to avoid repeats. Research and competition keep one discovery per experiment; reviews update the reviewed discovery. With no eligible reviewer, [leave review pending and close without polling](references/verification.md#common-rules). Work keeps reusable results (below).
4. **Event:** append an event pointing to the discovery using [references/records.md](references/records.md). Non-experiment steps such as a claim, take-over, routing change, or session close may have no discovery.
5. **Follow-ups:** decide what the result changes using the follow-up procedure in the plan-items reference, including a reason when nothing follows.
6. **Remove:** delete the completed item from the live queue; do not keep `[done]` items. Complete discovery → event → follow-ups → removal together before starting something else, so the files describe one consistent outcome.

For `work` (`quick`, `work-project`), use compact items in queue or header `Next:` order; scores are optional. Keep reusable discoveries, dated changed-stage events, and one session summary with `Completed: <IDs>`, finalized at close. See plan-items and records for formats. Duplicate checks apply. Research and competition keep per-item records; header `Ordering: queue` makes scores optional there too.

When the queue empties, follow the workflow's search order. Stop when nothing worthwhile remains; never invent low-value work to fill a queue.

## One home per fact

Store a fact once and point to it elsewhere. For reusable findings, put claims, numbers, interpretation, and verification in the discovery; the event carries who, when, host, user, artifact paths, and a discovery ID/verdict rather than another result narrative. The discovery's `Evidence` points to reproducible artifacts. Put proposed work in `plan.md` and half-done work in the slot's `Resumable state`; `Next action` is its only next-step line, naming item IDs or a non-item step.

Project-wide values, including the current best and evaluation instrument in use, live in `handoff.md` Shared state. Update `Current best` together with its cited discovery whose `Implication` begins `new current best:`. Record formats and shared-file editing mechanics live in [references/records.md](references/records.md); user policy belongs under `agents.md`'s `## Project rules`, as [references/project-rules.md](references/project-rules.md) describes. Keep detailed rules in their references instead of copying them into the core or generated reading list.

## Checker, `ro brief`, and `ro close`

Run the checker at session start, after a take-over or migration, and before closing:

```text
python <skill-root>/scripts/check_project.py .
ro --session <host-session> --slot A brief
ro --session <host-session> --slot A close
```

`ro` means `python <skill-root>/scripts/ro.py`. `ro brief` restores context; `ro close` releases idle slots and writes `Paused:` for an empty, idle project. Remove `Paused:` when resuming; see [session close](references/sessions.md).

- **ERROR** (exit 1): contradictory files or missing required structure, such as dangling IDs or missing claims. Resolve errors in your own records before starting new work.
- **WARN:** actionable concerns such as stale claims or a future timestamp. `--strict` makes warnings fail too.
- **INFO:** compatibility notes, field order, bare `none`, advice. Exit 2: the project could not be read.

`--baseline-update` stores finding fingerprints in `.ro/checker-baseline.json`; later runs flag new issues. Baselines never hide or downgrade findings.

Fix your records, missing structure, and cited Shared state values. Put another slot's problem under `Open consistency issues` for its owner or the user; do not invent or delete their items. Record incorrect findings there as `(disputed — <why>)` and continue.

## Read a reference when doing its operation

| Setting or operation | Value / occasion | Read |
| --- | --- | --- |
| Settings | Setup, edit, or saved preset | [references/presets.md](references/presets.md) |
| Workflow | Claim, dispatch, or move a `classic` item | [references/workflow-classic.md](references/workflow-classic.md) |
| Workflow | Claim, dispatch, or move a `unified` item | [references/workflow-unified.md](references/workflow-unified.md) |
| Verification / Reviewer | Review a finding or use an unverified premise | [references/verification.md](references/verification.md) |
| Item size | Plan or complete a stage | [references/staged-items.md](references/staged-items.md) |
| Guards | Record measured evidence or resolve an active guard finding | [references/research-guards.md](references/research-guards.md) |
| Guard set | Make an override, insight, direction, phase, or selection decision | [references/decision-guards.md](references/decision-guards.md) |
| Profile | Set up competition evidence or choose a candidate | [references/competition.md](references/competition.md), then [references/adapters/kaggle.md](references/adapters/kaggle.md) when applicable |
| External actions / E1 | Execute an outward command | [references/external-actions.md](references/external-actions.md); adapter patterns: [references/adapters/external-actions.json](references/adapters/external-actions.json) |
| Enforcement / Environment | Hook installation or shell execution | [references/hooks.md](references/hooks.md) |
| Publish scan | Publication | [references/publication-safety.md](references/publication-safety.md) |
| Resource / Parallel / Other | Exclusive resources, workers, or host limit retries | [references/compute.md](references/compute.md) |
| Git sync | Commit or push coordination records | [references/git-sync.md](references/git-sync.md) |
| Plan collector | Run a collection round | [references/plan-collector.md](references/plan-collector.md) |
| Operational commands | IDs, claims, jobs, observations, briefs | [references/operations-safety.md](references/operations-safety.md) |
| Session | Take, resume, or close a slot | [references/sessions.md](references/sessions.md) |
| Plan | Add, score, or derive follow-ups | [references/plan-items.md](references/plan-items.md) |
| Records | Write discovery, event, or shared update; archive history | [references/records.md](references/records.md) |
| Tools | Write, change, or reuse scripts | [references/tools.md](references/tools.md) |
| Project rules | Add policy, override, or lesson | [references/project-rules.md](references/project-rules.md) |
| Migration | Template upgrade, repair, or workflow change | [references/migration.md](references/migration.md) |
| Project close | Review the completed project | [references/postmortem.md](references/postmortem.md) |

## Safety

Hooks can block configured deterministic hazards such as detached shell work, unsafe heredocs, changes to running-job inputs, publication findings, and ungated external actions; their actual coverage depends on the host and settings. Read [references/hooks.md](references/hooks.md) for enforcement policy and [hooks-capabilities.md](references/hooks-capabilities.md) for the capability matrix before relying on them. Inspect warning counts in `ro brief` and details in `.ro/warnings.log`. This makes missing hook coverage visible instead of treating silence as proof that an action was checked.
