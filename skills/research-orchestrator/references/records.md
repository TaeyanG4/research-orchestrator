# Discovery and handoff records

The core defines which file owns each fact and the completion sequence; these are the record shapes.

With `Profile: work` or `research` and `Plan collector: off`, resume from the plan and handoff; the initial template omits unused summaries, and their absence is INFO. Competition or an enabled collector requires `Current best`, `Active compute` and `Plan collection` to track results, capacity and collection state.

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

`Source`, `Host`, `User`, and first-recorded `Date` retain the original attribution; use `unknown` only when migrating older notes. An optional `Session:` after `Date` records the source session identity. Review syntax, required identities, eligible reviewers, states, and revisions have their single home in [verification.md](verification.md).

State in the finding what was measured, on which set and against which baseline; a conclusion wider than that set is a hypothesis. A later correction goes in `Correction: (YYYY-MM-DD HH:MM, <D-ID>) <text>`, and when a later discovery changes this one's state, add `Current: <D-ID>`; `ro index <ID>` prints both first and the startup index shows `Current`.

Write findings in the configured language, preserving the claim and conditions so the startup index supports duplicate checks. For applicable non-operational decisions add `Outcome: supported | rejected | inconclusive`; [decision-guards.md](decision-guards.md) defines rejection evidence. Merge duplicate discoveries.

## Archiving history

Startup reads the discovery index and parts of the handoff, so both must stay small as a project grows. The checker reports `history.size` when the index of live discoveries passes 48 KiB or `handoff.md` passes 192 KiB, and `ro brief` names the command to run. Without `--before`, each command moves the earliest eligible records, in file order, until the read is back under half its limit; `--before YYYY-MM-DD` moves eligible records dated earlier, and `--dry-run` lists the moves without writing. Log each run as an event with heading `none`.

- `ro archive discoveries` moves settled entries (`VERIFIED`, or unreviewed under `Verification: self`) that no live plan item, Shared state or slot section cites to `docs/archive/discoveries-<YYYY-MM>.md`. Each leaves a stub with its heading, `Archived:` path, `Cross-check` and clipped `Finding`, so the ID still resolves. The checker reads the archived entry, `ro index <ID>` opens it and `ro dupcheck` searches it; the startup index counts archived entries instead of listing them. Entries awaiting review or a challenge answer stay listed until they settle. To revise an archived discovery, run `ro archive restore <ID>` first: it moves the full entry back over its stub and then removes the archived copy, so the entry can be archived again; a rerun after an interruption only removes the leftover copy.
- `ro archive events` moves older dated events to `docs/archive/handoff-<YYYY-MM>.md` and keeps one summary line per archive file under `## Archived history`. Shared state, slot sections, instruments, external actions, events that name a live plan item (stage events gate its launches), each slot's latest event, and the events that finish, take over or remove an item a kept event queued stay. Archived events leave the checker's event checks, so this suits finished history.

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

Write it with `ro event <key> --action … --result … --discovery-updates … --new-plan-items …` (or `--from <file>` of field lines): the command takes the clock time and Host/User from your slot, and the checker's own rules refuse a malformed event before it is written. Each field is one line, with one `- Job:` line per event.

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

Besides `ro archive events` ([Archiving history](#archiving-history)), older events may move by hand to `docs/<focused-name>.md` with a summary and link; keep resume state, shared values and changed-stage events of items with dependent launches, which the launcher reads from `handoff.md`.

## Shared-file edits

Before changing `plan.md`, `discoveries.md`, or `handoff.md`, re-read its latest contents and patch only the relevant section or append the entry; a whole file replaced from a stale copy erases another session's work. Prefer the commands:

- `ro set-field <ID|slot|shared> <Field> <value>` replaces one line and keeps every other byte (`shared` is Shared state, e.g. `Current best`); `--add` appends a missing field such as `Correction`.
- `ro close-item <ID> --from <draft>` (`## D-…` discoveries, `## Event` fields, optional `## Follow-ups` items) finishes an item in one journaled transaction.
- They and `ro event` write `{now}` as the clock time and `{today}` as the date: a draft needs no typed time.
- After an interruption, `ro close-item --recover` completes or rolls back the transaction; until then `ro` refuses to write records or launch jobs. Recovery stops rather than overwrite a file someone changed (a restore killed mid-copy is redone): save that file elsewhere, copy its `.close-backup` back, recover, rerun a rolled-back close, then reapply the change.

A script that edits several records must validate everything before its first write and keep each file's line endings. Apply the project's [git-sync.md](git-sync.md) mode.

Finish linked changes before unrelated work: completion follows the core lifecycle, ownership changes the workflow's event rule, slot creation [sessions.md](sessions.md), and compute claims and collection rounds their references. Queue an item before any handoff line names it, so the checker never sees a forward reference to missing work.
