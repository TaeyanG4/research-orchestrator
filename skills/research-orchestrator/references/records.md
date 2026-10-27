# Discovery and handoff records

Use these shapes when recording an outcome. The core defines which file owns each fact and the item completion sequence; this reference defines its durable representation.

With `Profile: work` or `research` and `Plan collector: off`, `Current best`, `Active compute` and `Plan collection` are optional summaries and the initial template omits them. Their absence is INFO because work can resume from the plan and handoff. Add a summary when it carries useful state; competition and an enabled collector still require all three.

Write free text in `agents.md`, `plan.md`, `discoveries.md`, `handoff.md`, and replies to the user in the configured `Language` (default `en`). Keep structural headings, field names (`Hypothesis:`, `Finding:`, etc.), IDs, status words, check IDs, and setting keys in English so the checker, hooks, and `ro` commands work unchanged. Non-English field values are valid UTF-8; the release vocabulary rule applies only to shipped files, not user records.

## Discovery

Use `D-<Agent>-<NNN>`, such as `D-A-001`, numbered sequentially by the creating slot without reuse. The operational reference describes ID reservation.

```markdown
## D-B-014 — Short title
- Source: B
- Host: <host>
- User: <user>
- Date: YYYY-MM-DD
- Cross-check: PENDING
- Finding: ...
- Evidence: ...
- Implication: ...
- Reviews:
```

Prefer this field order for readability. `Source`, `Host`, `User`, and first-recorded `Date` retain the original attribution; use `unknown` only when migrating older notes. An optional `Session:` after `Date` records the source session identity. Review syntax, required identities, eligible reviewers, states, and revisions have their single home in [verification.md](verification.md).

Write findings in the configured language, preserving the claim and conditions so the startup index supports duplicate checks. For applicable non-operational decisions add `Outcome: supported | rejected | inconclusive`; [decision-guards.md](decision-guards.md) defines rejection evidence. Open matching entries' evidence on demand. Merge duplicate discoveries instead of archiving them as the file grows.

In the `work` profile, discoveries are for results worth reusing: a decision changed, a dead end others should not retry, or a verified fact others depend on. Routine completions and inconclusive probes with no reusable result belong in the session event. Research and competition retain one discovery per experiment. Reusable work findings keep the usual evidence and verification fields so brevity does not weaken a claim others rely on.

## Active handoff

```markdown
### Agent: B
- Current host: <host>
- Current user: <user>
- Current thread: H-B-03
- Resumable state: ...
- Blocker: none
- Next action: ...
```

## Completed/review log

Append events; preserve earlier history so later sessions can reconstruct decisions.

```markdown
### YYYY-MM-DD HH:MM — A — H-A-01
- Host: <host>
- User: <user>
- Action: ...
- Result: <one line>; see <discovery ID>
- Artifacts: <paths> / none
- Discovery updates: D-A-014 / none — <reason>
- Review verdict: <discovery ID> CLOSED | HOLD | CHALLENGED / none
- Resource: CPU | GPU | Other | none
- Other executor: <executor> / none
- New plan items: H-A-02, H-A-03 / none — <reason>
```

The heading ends with the completed item ID: `none` when nothing completes, the new ID for a take-over, or `<ID>/s<N>` for a stage (which does not complete the item). Use the real current time. Prefer IDs or `none — <reason>` in `Discovery updates` and `New plan items`; bare `none` is an INFO reminder. The core's lifecycle defines when a discovery may be absent.

For work (`quick` and `work-project`), use one completion summary per session:

```markdown
### YYYY-MM-DD HH:MM — A — session
- Host: <host>
- User: <user>
- Action: <completed work and any stage progress>
- Result: <outcome and what remains>
- Completed: H-A-01, H-A-02
```

Use `Completed: none` when no item finished; stages alone do not complete an item. Update the summary as items finish so removing them leaves no dangling references, then finalize it at close. Add artifacts, discovery IDs, review verdicts, resources, executors, and new plan IDs only when relevant; omit empty fields. A reusable finding goes under `Discovery updates`, and a review under `Review verdict`, so their links remain checkable. `Decision: changed` or `unchanged` requires discovery evidence; `Decision: operational` may omit it. Do not create a separate close event to repeat this summary. Automatic confirmed-job launch records and ownership transitions still preserve execution history.

Record each decision-changing stage in its own immutable dated event alongside that summary, using the ordinary event fields above and the stage ID as its heading. Keep its `Decision: changed`, `Review artifact`, discovery link and original observation time there: editing a session summary should never erase a launch gate or change which result a receipt reviews. The summary can mention several changed and operational stages without a stage-specific `Decision` or `Review artifact` of its own. See [staged-items.md](staged-items.md) for receipt scopes and preserving earlier session-only records.

Session events keep this compact shape and their completed IDs when switching to a research or competition preset. Leave history intact; bring unfinished queue items into the new profile's shape for future work.

When the handoff log becomes hard to scan, move older events to `docs/<focused-name>.md` and leave a summary and link. Keep current resume state, shared values, and changed-stage events for items with dependent launches in place; the launcher reads those review obligations from `handoff.md`.

## Shared-file edits

Before changing `plan.md`, `discoveries.md`, or `handoff.md`, re-read its latest contents and patch only the relevant section or append the entry. Replacing a whole file from a stale copy can erase another session's work. Apply the project's [git-sync.md](git-sync.md) mode.

Keep linked changes together before doing unrelated work: item completion follows the core lifecycle; ownership changes follow the workflow's event rule; slot creation updates all its entries as [sessions.md](sessions.md) describes; compute claims and collection rounds follow their references. Queue an item before any handoff line names it, so the checker never sees a forward reference to missing work.
