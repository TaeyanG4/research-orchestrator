# external action order — Agent Rules
<!-- ro-template: v3.0 (profile=work workflow=unified verification=independent-review itemsize=staged guards=light guardset=auto mode=single git=off instruments=off externalactions=on preset=work-project) -->

Summary: preset work-project · workflow unified · verification independent-review · active modules: staged items, evidence guards (G5, G6, GD, E1)

## Project settings

- Preset: work-project
- Profile: work
- Workflow: unified
- Verification: independent-review
- Item size: staged
- Guards: light since 2026-10-25
- Guard set: auto
- Guard thresholds: saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75
- Environment: windows/powershell
- Language: en
- Enforcement: block
- Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan
- External actions: none
- Publish scan: secrets
- Brief requirements: none
- Autonomy: present
- Phase clock: off
- Competition: off
- Platform mode: single
- Platforms: local
- Git sync: off
- Plan collector: off
- Plan queue limits: stop at 50, resume at 5
- Reviewer: off
- Cross-check fallback: same-host

## Rules for this project

Write free text in the four files and replies to the user in `Language` (default `en`); keep structural headings, field names (`Hypothesis:`, `Finding:`), IDs, status words, check IDs, and setting keys in English so the checker, hooks, and `ro` commands work unchanged.

`<skill-root>` is the folder containing the skill's `SKILL.md`. Read that core, then these references for the active settings:

- `<skill-root>/references/presets.md` — settings and reconfiguration.
- `<skill-root>/references/sessions.md` — slot identity and session close.
- `<skill-root>/references/plan-items.md` — item format, duplicate checks, scoring, and follow-ups.
- `<skill-root>/references/records.md` — discovery and event formats.
- `<skill-root>/references/project-rules.md` — the user-owned region below.
- `<skill-root>/references/workflow-unified.md` — Workflow `unified`.
- `<skill-root>/references/staged-items.md` — Item size `staged`.
- `<skill-root>/references/verification.md` — common rules and Verification `independent-review`, with Platform mode `single`.
- `<skill-root>/references/git-sync.md` — Git sync `off`.
- `<skill-root>/references/compute.md` — resource use.
- `<skill-root>/references/operations-safety.md` — operational commands.
- `<skill-root>/references/hooks.md` — enforcement and host capabilities.
- `<skill-root>/references/plan-collector.md` — when Plan collector is on.
- `<skill-root>/references/external-actions.md` — before an outward action.
- `<skill-root>/references/publication-safety.md` — before publication.
- `<skill-root>/references/research-guards.md` — enabled guards and the active guard set.

## Project rules

### Standing rules

<!-- Budget: 4096 UTF-8 bytes, excluding comments and surrounding whitespace. -->

### Active overrides

<!-- Each override: - <rule> | Expires: YYYY-MM-DD -->

### Lessons

<!-- One line each: - <mistake> → enforced by <check id | none> -->
