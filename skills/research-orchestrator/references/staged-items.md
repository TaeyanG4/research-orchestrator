# Staged items

Read this when planning or completing a stage with `Item size: staged`. In `classic` the item stays in its owner's `## Agent:` section; in `unified` it stays in `## Queue` with its `Claimed:` line.

A long item may declare its stages after the ordinary item fields:

```text
- Stages: s1 pilot sample | s2 full run | s3 write-up
- Important stages: s2
```

- Stage numbers are unique; names are short.
- For work, collect operational progress in the session summary's `Action` and `Result`; add the bare item ID to `Completed` only when the whole item finishes. Record each changed stage separately with the heading `### YYYY-MM-DD HH:MM — <slot> — H-A-01/s2`. Research and competition use that heading for all stage progress. A `/sN` event never completes or removes the item.
- A stage that changes a decision produces one discovery and carries `Decision: changed` after the usual event fields, listing that discovery under `Discovery updates`. Any other stage event is operational: omit `Decision` or write `Decision: operational`.
- The checker warns about a stage event for an item without `Stages:` (`event.stage.undeclared`) or for a stage not in its list (`event.stage.beyond`).

## Review before launch and after changed decisions

Mark consequential stages with `Important stages: s2 | s3`, using distinct numbers from `Stages:`; omit the field for routine work. Choose these before execution when a stage commits substantial compute, changes shared data, or could invalidate the next decision. Independent review at that boundary catches a mistaken premise while it is still cheap to correct; reviewing changed results prevents later stages from inheriting it.

Every launch resolves exactly one active item in the configured workflow's `## Queue` or `## Agent:` section of `plan.md`; archived notes and fenced samples do not count. Each supplied `/sN` matches that item's declared `Stages`. Missing or duplicate items and unknown stages stop before receipt checks or job reservation, so a mistyped target cannot bypass review. The launcher checks again under the reservation lock to catch a policy or artifact changed while it waited.

Before a designated stage, give a separate reviewer session its launch contract: inputs, command, expected result, resource limit and stop conditions. Record its actual verdict with `ro receipt add docs/stage-contract.md --reviewer <reviewer-session> --verdict PASS --scope H-A-01/s2:before`, under the explicitly identified author session. Then launch with `ro launch --item H-A-01/s2 --expect 2h --require-receipt docs/stage-contract.md -- <command>`. The launcher checks the current artifact hash, exact stage scope and independent reviewer before reserving a job. A different stage, an `:after` receipt, a changed artifact or a later FAIL cannot authorize this launch. Use a stage-qualified item when important stages are declared, so a bare item cannot skip the gate. This designated review remains independent even with `Receipt policy: self`; routine stages need no receipt unless explicitly requested.

After any stage produces `Decision: changed`, record its observed evidence and discovery in a dedicated event using the usual fields and that single stage ID in the heading, for every profile. Add `Review artifact: outputs/s2_run.csv` after `Decision` and record an independent PASS receipt with scope `H-A-01/s2:after`, created after the event's observation time. Keep the event, time and result artifact immutable; later observations get new events and artifacts. Each changed stage retains its own review scope, even when a work session summary is shortened or also describes operational stages. Leave these events in `handoff.md` while the item has dependent launches; the launcher reads them there.

Earlier work summaries naming one changed stage in `Action` remain supported. Before replacing such a summary, preserve its stage ID, evidence, discovery, artifact and original observation time in a dedicated event; only then remove the summary's stage-specific decision fields. Keep a separate event and stage-scoped receipt for each changed stage.

The checker reports absent or stale reviews; the next launch for an item waits for every changed-stage event belonging to it to have a current receipt. Operational stages add no after-result gate, and unrelated items remain runnable. If no independent reviewer is available, preserve the result and pending review in the handoff, close the session, and leave the dependent launch blocked; do not invent a reviewer or lower the policy.

A changed-stage event, including in work sessions:

```markdown
### 2026-10-25 14:10 — A — H-A-01/s2
- Host: Claude Code
- User: <user>
- Action: full run of stage s2
- Result: the effect holds on the full sample; see D-A-004
- Artifacts: outputs/s2_run.csv
- Discovery updates: D-A-004
- Review verdict: none
- Resource: GPU
- Other executor: none
- New plan items: none — s3 already declared
- Decision: changed
- Review artifact: outputs/s2_run.csv
```

A work case — an operational stage of a data migration, `Stages: s1 dry run | s2 cut-over | s3 clean-up`:

```markdown
### 2026-10-26 09:30 — B — session
- Host: Codex
- User: <user>
- Action: completed H-B-04/s1, dry run of the billing-table migration on a copy
- Result: all rows copied; timing recorded for the cut-over window
- Artifacts: logs/dry_run.log
- Completed: none
- Decision: operational
```
