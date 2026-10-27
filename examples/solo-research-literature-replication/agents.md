# Velin rest interval study — Agent Rules
<!-- ro-template: v3.5 -->

Summary: preset solo-research · workflow unified · verification independent-review · active modules: staged items, evidence guards (G1, G5, G6, GD, E1)

## Project settings

- Preset: solo-research
- Profile: research
- Workflow: unified
- Verification: independent-review
- Item size: staged
- Guards: light since 2026-10-23
- Environment: linux/bash
- Language: en
- Enforcement: block
- Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan
- Publish scan: secrets
- Platforms: single — Lumen

<details>
<summary>Inactive and default settings (expand to edit)</summary>

- Guard set: auto
- Guard thresholds: saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75
- Read bound: off
- External actions: none
- Receipt policy: independent
- Brief requirements: none
- Autonomy: present
- Stale slot after: 2h
- Queue freeze: off
- Phase clock: off
- Competition: off
- Git sync: off
- Plan collector: off
- Plan queue limits: stop at 50, resume at 5
- Reviewer: off
- Cross-check fallback: same-host

</details>

## Rules for this project

`<skill-root>` contains `SKILL.md`. At startup read only that core, this file, the discovery index (`ro index`), and needed records. The core's operation table owns the general reading list; open its references when doing the operation.

These pointers cover active choices that differ from defaults:

- `references/workflow-unified.md` — claim and move work in the shared queue.
- `references/verification.md` — apply the selected verification policy.
- `references/staged-items.md` — plan or complete a stage.
- `references/research-guards.md` — record measured evidence and resolve guard findings.
- `references/decision-guards.md` — record strategic decisions.
- `references/hooks.md` — apply the configured command checks.

## Working rules

These rules keep the four files consistent in every session, with or without the research-orchestrator skill loaded; the skill's references explain each step. `ro` is `python <skill-root>/scripts/ro.py`, where `<skill-root>` is the installed skill folder (for example `~/.claude/skills/research-orchestrator`); SessionStart prints the exact prefix, and every command has `--help`.

- **Start:** read this file, the discovery index (`ro index`), Shared state and your own slot in `handoff.md`, then your plan items, and run `python <skill-root>/scripts/check_project.py .`. Resuming from the files rather than from memory keeps sessions consistent.
- **Before adding work:** run `ro dupcheck <terms>`; a claim already settled needs a real `Improvement`, so no one repeats it. Reserve IDs with `ro next-id` so parallel sessions never collide. Claim an item with `ro claim <ID>` before starting it.
- **When an item finishes:** record its discovery (one per experiment, including negative and inconclusive results), append the event, record follow-ups or `none — <reason>`, then delete the item from `plan.md`. Doing the four together leaves one consistent outcome.
- **Store each fact once:** results in discoveries; who, when and artifacts in events; project-wide values in Shared state; half-done work in your slot's `Resumable state`. Copies drift apart.
- **Before writing a script:** run `ro tools <terms>`; extend a listed tool and bump its `Version` instead of copying it, and register each new reusable script (`ro tools --init` creates `docs/tools.md`). Separate copies drift and make results incomparable.
- **Long or outward work:** start long or detached jobs with `ro launch` and follow them to an outcome; run outward actions through `ro external` with a prepared ledger entry. Unowned processes and unrecorded actions cannot be checked or recovered.
- **Records:** take times from the real clock; keep headings, field names, IDs and status words in English so the checker and commands can read them; edit only your own slot's sections.
- **Checker findings:** fix your own and list other slots' under `Open consistency issues` instead of editing their records. When it reports `history.size`, run `ro archive discoveries` or `ro archive events`.
- **Close:** run `ro close`, which keeps claims for running jobs and releases the rest.

## Project rules

### Standing rules

<!-- Budget: 4096 UTF-8 bytes, excluding comments and surrounding whitespace. -->
<!-- - <rule> | Replaces: <rule or none>. Remove superseded guidance so policies do not accumulate. -->

### Active overrides

<!-- - <scope> | Checks: <IDs> | Reason: <why> | Expires: YYYY-MM-DD | Record: <optional ID>. Process/ranking only. -->

### Lessons

<!-- One line each: - <mistake> → enforced by <check id | none> -->
