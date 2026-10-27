# Tern demand challenge — Agent Rules
<!-- ro-template: v3.4 -->

Summary: preset competition-team · workflow classic · verification hybrid · active modules: evidence guards (G1, G3, G5, G6, GD, G8, G11, E1), competition

## Project settings

- Preset: competition-team
- Profile: competition
- Workflow: classic
- Verification: hybrid
- Item size: short
- Guards: light since 2026-10-23
- Environment: linux/bash
- Language: en
- Enforcement: block
- Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan, external.gate
- External actions: arenactl submit
- Publish scan: secrets
- Phase clock: start 2026-10-01, deadline 2026-10-25
- Competition: arena/tern-demand
- Platform mode: multi
- Platforms: Lumen, Prism

<details>
<summary>Inactive and default settings (expand to edit)</summary>

- Guard set: auto
- Guard thresholds: saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75
- Read bound: off
- Receipt policy: independent
- Brief requirements: none
- Autonomy: present
- Stale slot after: 2h
- Queue freeze: off
- Git sync: off
- Plan collector: off
- Plan queue limits: stop at 50, resume at 5
- Reviewer: off
- Cross-check fallback: wait

</details>

## Rules for this project

`<skill-root>` contains `SKILL.md`. At startup read only that core, this file, the discovery index (`ro index`), and needed records. The core's operation table owns the general reading list; open its references when doing the operation.

These pointers cover active choices that differ from defaults:

- `references/verification.md` — apply the selected verification policy.
- `references/research-guards.md` — record measured evidence and resolve guard findings.
- `references/decision-guards.md` — record strategic decisions.
- `references/competition.md` — prepare competition evidence or candidates.
- `references/external-actions.md` — prepare an outward action.
- `references/hooks.md` — apply the configured command checks.

## Project rules

### Standing rules

<!-- Budget: 4096 UTF-8 bytes, excluding comments and surrounding whitespace. -->
<!-- - <rule> | Replaces: <rule or none>. Remove superseded guidance so policies do not accumulate. -->

### Active overrides

<!-- - <scope> | Checks: <IDs> | Reason: <why> | Expires: YYYY-MM-DD | Record: <optional ID>. Process/ranking only. -->

### Lessons

<!-- One line each: - <mistake> → enforced by <check id | none> -->
