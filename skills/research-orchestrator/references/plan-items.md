# Plan items

An item is an unfinished goal, hypothesis, review, or next action. Use the selected workflow to place and own it; do not put project-wide notes in the queue.

## Shape and IDs

Use `H-<Agent>-<NN>` for item IDs, such as `H-A-01`. The creating slot numbers its IDs sequentially and does not reuse numbers, including retired IDs. Reserve an ID through [operations-safety.md](operations-safety.md) when writing a record.

For Profile `work` or preset `quick`, start with this compact shape so routine work carries only the context needed to resume it:

```markdown
### H-A-01 — Short title
- Claimed: none
- Goal: <goal or question>
- Evidence: <observations or context>
- Next test: <next step>
```

Omit `Claimed` in classic workflow. `Hypothesis` aliases `Goal`; `Next step` aliases `Next test` for work. Add `Stages` for a long item. `Sources`, `Improvement`, the six scores, `Priority`, `Resource`, `Parallel`, and `Other` are optional; omitted routing means `CPU`, `NO`, and `NONE`. Include them when they convey useful dependencies, a real difference from prior work, or execution needs.

For routine work, keep acceptance criteria and deliverable lists in the agreed brief and point to them from `Evidence` or `Next test`. Repeating the brief in extra fields makes the queue harder to scan and creates another place for scope to drift. Add a field when it changes how the item is selected, owned, or executed, such as a readiness date or a nondefault resource.

Research and competition normally use scored items. If queue order expresses the actual dependencies better, initialize with `--ordering queue` (including `team-research`), or put `Ordering: queue` in the existing plan header, before any section, and omit scores and `Priority`. Routing fields are optional in every profile: omitted `Resource`, `Parallel`, and `Other` mean `CPU`, `NO`, and `NONE`. This keeps a small study readable without concealing a nondefault execution need.

`Resource` is the local capacity class an item needs: `CPU`, `GPU` or `EITHER` (the values `ro launch` accepts; omitted means `CPU`). Put named exclusive resources such as a shared database or licensed seat in `Other`, so contention is visible. Handoff events may record `Resource: none` for steps that used no local capacity.

The scored shape is:

```markdown
### H-A-01 — Short title
- Sources: D-B-003, D-A-008 / none
- Hypothesis: ...
- Evidence: ...
- Improvement: ...
- Impact: 0-3
- Information: 0-3
- Confidence: 0-3
- Unblock: 0-3
- Diversity: 0-3
- Cost: 0-3
- Priority: <calculated score>
- Resource: CPU
- Parallel: YES | NO
- Other: NONE | <named exclusive resource or external executor>
- Next test: ...
```

Use this relative order for readability; the checker treats ordering differences as INFO. Unified items add `Claimed:` first; staged items add `Stages:` last. Other `- Field:` lines such as `Status:` are allowed.

Add `Ready by: YYYY-MM-DD` when an item has a useful readiness date. It is optional in every profile; the checker validates the date format without treating it as a completion deadline.

`Sources` names motivating discoveries or `none`. `Evidence` explains why the item deserves attention now, citing actual observations rather than only an ID. `Improvement` explains what it strengthens, changes, or resolves over a source or prior attempt; use `none` only when inapplicable. `Next test` (or `Next step` for work) is the smallest step that could change a decision: a test, comparison, build, or draft. These distinctions prevent a renamed repeat from appearing to be new work.

## Before adding an item

Check `Queue freeze` first. Through its `until YYYY-MM-DD` date, finish or correct existing items and record deferred follow-ups in the outcome instead of adding scope. Resume additions after expiry or an explicit setting change; the expiry WARN prompts that review.

1. Search the discovery index (headings and `Finding`/`Status`/`Cross-check` lines, available through `ro index`) for the same claim, including negative and inconclusive results. Open matching entries for evidence and conditions before deciding:
   - `VERIFIED` and the same claim: add only a materially different follow-up with an `Improvement`.
   - `CHALLENGED`: wait until the challenge is resolved.
   - `HOLD`: add only when its stated condition is met, and explain that in `Evidence`.
   - `PENDING` or `REVIEWING`: prefer an eligible review to repeating the experiment.
   - Negative or inconclusive: the `Improvement` must address why it failed or did not settle the question.
2. Scan other queued items' headings and `Hypothesis`/`Goal` lines. Keep one item per goal or hypothesis; when yours is materially different, cite the related ID in `Evidence`.
3. Re-read `plan.md` immediately before writing. If the same item appeared meanwhile, keep the earlier one.

An item without a real improvement over a settled discovery or prior attempt is a duplicate. `ro dupcheck` helps locate related records; it cannot judge whether a distinction matters.

## Priority

Score each factor 0–3: `Impact` is value if successful; `Information` is uncertainty resolved or decisions changed; `Confidence` is evidence that the direction merits testing; `Unblock` is a dependency removed; `Diversity` is difference from explored paths; `Cost` is time, compute, and risk (0 cheap, 3 expensive).

For work, or any profile with `Ordering: queue`, choose the first eligible item in queue order, or name it with `Next: H-A-01` in the plan header before any section. Keep that optional pointer on an existing unfinished item as items leave the queue. `Ordering: priority` explicitly selects score ranking for research and competition. Supplied score factors are always integers from 0 to 3; a supplied `Priority` needs all six factors and the formula below, so optional scoring cannot silently introduce an invalid ranking. A reasoned ranking exception can be recorded under [Active overrides](project-rules.md#active-overrides).

```text
Priority = 2*Impact + 2*Information + Confidence + Unblock + Diversity + (3-Cost)
```

The range is 0–24. Score-ranked research and competition choose the highest score unless blocked or overridden; break ties by lower `Cost`, then higher `Information`. Rescore affected items when using scores and a discovery or review changes their evidence, so stale scores do not keep a disproved direction alive.

## Follow-ups

Whenever you create or update a discovery, including a negative result or review verdict, decide what it changes before choosing the next item:

1. Add zero or more next steps that could change a decision now, each with `Sources`, concrete `Evidence`, and the missing proof, changed condition, stronger method, or weakness addressed in `Improvement`. Apply the duplicate check above first.
2. Reconsider affected queued items you may edit under the workflow; rescore when using scores. Remove items made pointless and name each in the event's `Action` as `removed H-A-05 — <reason>`. A discovery does not grant ownership of another slot's active item.
3. When no item follows, prefer `New plan items: none — <reason>` in the event. Bare `none` is only an INFO reminder. For work, collect these decisions in the one session event; omit an empty follow-up field when the result already explains what remains.

Prefer a few steps that can change the decision over many small variants. Build on earlier sessions' findings and cite all motivating discoveries in `Sources`; citing an ID alone does not justify repeating its work. With `Plan collector` on, use [plan-collector.md](plan-collector.md) for collection rounds.
