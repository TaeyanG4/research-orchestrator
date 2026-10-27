# guard — Agent Rules
<!-- ro-template: v3.0 (profile=research workflow=classic verification=self itemsize=short guards=light guardset=G1 mode=adaptive git=off instruments=on externalactions=off preset=custom external_actions_source=default) -->

Summary: preset custom · workflow classic · verification self · active modules: evidence guards (G1)

## Project settings

- Preset: custom
- Profile: research
- Workflow: classic
- Verification: self
- Item size: short
- Guards: light since 2026-10-01
- Guard set: G1
- Guard thresholds: saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75
- Environment: windows/bash
- Language: en
- Enforcement: block
- Block: external.gate
- Read bound: off
- External actions: none
- Publish scan: secrets
- Brief requirements: none
- Autonomy: present
- Queue freeze: off
- Phase clock: off
- Competition: off
- Platform mode: adaptive
- Platforms: Claude Code, Codex
- Git sync: off
- Plan collector: off
- Plan queue limits: stop at 50, resume at 5
- Reviewer: off
- Cross-check fallback: same-host

## Rules for this project

Write free text in the four files and replies to the user in `Language` (default `en`); keep structural headings, field names (`Hypothesis:`, `Finding:`), IDs, status words, check IDs, and setting keys in English so the checker, hooks, and `ro` commands work unchanged.

`<skill-root>` contains `SKILL.md`. At startup read only that core, this file, the discovery index (`ro index`), and needed records. Read each path relative to `<skill-root>` when doing its operation:

- `references/presets.md` — configure settings.
- `references/sessions.md` — take, resume, or close a slot.
- `references/plan-items.md` — add, choose, or follow up an item.
- `references/records.md` — write discoveries or events (quick: one session event).
- `references/project-rules.md` — add rules, overrides, or lessons.
- `references/workflow-classic.md` — claim, dispatch, or move work.
- `references/verification.md` — review or use an unverified premise.
- `references/git-sync.md` — commit or push records.
- `references/compute.md` — start heavy work or add workers.
- `references/operations-safety.md` — reserve IDs or manage jobs.
- `references/hooks.md` — install hooks or execute shell commands.
- `references/plan-collector.md` — collect candidates.
- `references/external-actions.md` — prepare an outward action.
- `references/publication-safety.md` — publish.
- `references/research-guards.md` — record measurements or resolve guard findings.
- `references/decision-guards.md` — record strategic decisions.
- `references/postmortem.md` — review the completed project.

## Project rules

### Standing rules

<!-- Budget: 4096 UTF-8 bytes, excluding comments and surrounding whitespace. -->

### Active overrides

<!-- - <scope> | Checks: <IDs> | Reason: <why> | Expires: YYYY-MM-DD | Record: <optional ID>. Process/ranking only. -->

### Lessons

<!-- One line each: - <mistake> → enforced by <check id | none> -->
