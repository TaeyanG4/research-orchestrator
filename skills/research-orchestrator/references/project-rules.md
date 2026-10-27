# Project rules

Everything from `## Project rules` to the end of `agents.md` belongs to the user. Keep local policy here so changing a preset can regenerate its reading list without erasing project knowledge. [presets.md](presets.md) describes template recognition and reconfiguration.

## Standing rules

Keep durable project-specific requirements within 4,096 UTF-8 bytes in this subsection, excluding comments and surrounding whitespace but including code content. The checker reports `rules.standing.budget` as WARN when the body exceeds that budget; it does not truncate or rewrite the text. Link to detailed project documents when a rule needs more explanation, so the always-read policy stays usable.

The whole `agents.md` loads in every session (Claude Code imports it through `CLAUDE.md`), and Codex reads only the first 32 KiB of project instructions, which cuts this region first because it comes last. The checker reports `agents.size` past 12 KiB, and names the Codex cut past 32 KiB. Move older Lessons and expired overrides to `docs/` with a link, and remove rules that a later rule replaced.

Include `Replaces: <rule or none>` with each new standing rule so superseded guidance does not accumulate or contradict its replacement. Name the old rule and remove its obsolete instruction; use `none` when the rule adds a distinct requirement. This is authoring guidance, not a new checker field.

## Active overrides

Use an explicit check scope, reason and `Expires: YYYY-MM-DD`, inline or on indented lines. A valid entry waives a process or ranking finding through that date; the checker reports it as INFO with the reason instead of hiding it. `Record` limits the exception to one record; omit it for project-wide scope. Expired entries warn with `rules.override.expired` and no longer waive anything. Missing or invalid dates warn with `rules.override.expires`. Review the need when the exception expires; the checker does not delete it.

```markdown
- review cadence | Checks: guard.direction.stale | Reason: waiting for the scheduled comparison | Expires: YYYY-MM-DD
- direct prioritization | Checks: plan.field.missing:Priority | Record: H-A-01 | Reason: one dependency determines the next action | Expires: YYYY-MM-DD
```

Supported selectors are `guard.direction.stale`, `guard.direction.incomplete`, `guard.phase.milestone`, `guard.effort.share`, and `plan.field.missing:<field>` for Impact, Information, Confidence, Unblock, Diversity, Cost or Priority. Wildcard and unknown selectors are rejected; a missing scope does not waive checks.

Structural consistency and evidence integrity still apply. An override never waives running-job mutation protection, monitored-job ownership, uncertain-outcome reconciliation, or artifact-bound receipts under the configured receipt policy for costly irreversible external actions. It does not change hook enforcement or bypass `ro external` or the Git pre-push scan. These protections prevent duplicate external effects and damage to live work, rather than prescribing how to rank or organize it.

## Lessons

Use one line per lesson: `<mistake> → enforced by <check id | none>`. Naming the enforcement distinguishes a checkable prevention from a reminder, and `none` makes a remaining gap visible. Keep the lesson concise instead of appending an incident narrative to the policy.
