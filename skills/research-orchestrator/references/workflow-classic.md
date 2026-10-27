# Workflow: classic

`Workflow: classic` keeps one section per slot: every slot owns one `## Agent: <name>` section in `plan.md`, and an item changes owner only through a take-over.

For the `work` profile, ranking scores are optional: select the first eligible item in queue order or the optional header `Next:` pointer, and collect completions in one session event as [records.md](records.md) describes. Research and competition can also use `Ordering: queue` in the plan header when dependencies make scores unhelpful, while retaining their per-item records. The ownership and duplicate checks still apply.

## Plan sections

- Each slot keeps its items in its own `## Agent: <name>` section, and an item's ID prefix matches its section (`H-B-07` sits under `## Agent: B`). Each agent edits only its own section, except when taking over an item (below) or when explicitly asked otherwise.
- A slot with nothing queued keeps its empty section.
- When choosing a free slot (references/sessions.md) in a `multi` or `adaptive` project, skip a free slot that still holds plan items left by a different host — those stay with that host — unless the user assigns you that slot.

## What you may read in other sections

Read only your own detailed section. Four narrow exceptions allow looking across other agents' sections:

- A resource dispatcher, or a session choosing a take-over item, may inspect only task metadata: task ID, owner, priority, cost, information, resource, parallel-safety, and `Other` executor.
- The duplicate check (references/plan-items.md) reads only item headings and `Hypothesis`/`Goal` lines.
- When choosing a slot or a take-over source, a session reads only the `Current host`, `Current user`, and `Current thread` lines of each agent's handoff section, plus [limited startup metadata](sessions.md#a-new-session-in-an-existing-project) when resolving a new session's slot choice.
- When taking over an item, a session reads that one item in full once it has chosen it by metadata.

Do not read another active agent's detailed evidence, scores, next tests, or resumable state merely for coordination. New items, follow-ups, and plan collector items go into your own section under your own IDs.

## When your own queue runs out

Look for work in this order before going idle:

1. **Your own section** — re-read it first; a same-host session may have taken items from it (the handoff log says so).
2. **Cross-checks** — claim a review you are eligible for (`references/verification.md`).
3. **Take over from a same-host slot** — below.
4. **Cross-host take-over by judgment** — one promising item, under the conditions below.
5. **Cross-check fallback** (`adaptive` only) — if `Cross-check fallback` is `same-host`, review a `PENDING` discovery from your own host made in another slot; if it is `wait`, leave those for the other host.
6. **New work** — a plan collector round when the collector is on and the queue is at or below its resume limit (references/plan-collector.md); otherwise derive items from discoveries yourself.
7. **Nothing worthwhile left** — record it in your active handoff section and follow the [session close procedure](sessions.md#close-a-session), including its check of every owned job before `ro close`.

Step 5 applies only to `adaptive` projects. In a `single` project, step 4 does not apply either, and step 3 reads "take over from another slot": every session runs on the one platform, so any slot is a same-host slot.

## Take over an item from a same-host slot

When your own queue is empty, you may take over a queued item from another slot **on the same host**, even if that session runs a different model. Items queued under a different host stay with that host, so each host's line of reasoning stays independent.

Eligible sources:

- a slot whose `Current host` equals your host and that your own user is running, or
- a `released` or `unassigned` slot whose most recent completed-log event was made by your host, or that has no completed-log events at all (items seeded by the user carry no host history, so any host may take them).

Never take the item named in the owner's `Current thread`, one that holds an `Active compute` claim, or any item from a slot another user is actively running.

1. Choose by metadata only: an eligible item whose `Resource` you can run now. Work and plans with `Ordering: queue` use queue order or `Next:`; other research and competition plans use highest `Priority` (ties: lower `Cost`, then higher `Information`).
2. Re-read `plan.md` immediately before moving it. If the item is gone, another session took it; choose again.
3. Move it into your own section with your next ID, and append the old ID to the title: `### H-A-05 — Retry policy for the nightly import (from H-C-03)`. The old ID is retired and never reused.
4. Reconsider it against the current discoveries; rescore when using scores. It is your item now.
5. In the same step, append a handoff event with heading `H-A-05`: `Action: took over H-C-03 from C (same host) as H-A-05` and `Discovery updates: none — take-over, no experiment`.

The original owner, on its next re-read of its own section, finds the item gone and the reason in the handoff log.

## Cross-host take-over by judgment

Only when `Platform mode` is `multi` or `adaptive`. As an exception to "items stay with their host", you may take over **one** item queued by a different host when all of these hold:

1. **Nothing closer is left**: your own queue, eligible cross-checks, and same-host items are exhausted.
2. **The source slot is idle**: it is `released` or `unassigned` — never an active session on another host, and never an item in the owner's `Current thread` or under an `Active compute` claim.
3. **The item is promising**: it clearly beats the best new hypothesis you could write now, for a reason you can state in one line. Research and competition require `Priority` at least 15 (out of 24) only with priority ordering. With `Ordering: queue`, keep that reasoned comparison without inventing scores; queue position does not establish value across hosts.
4. **One item at a time**: take one, finish it, then start the list above again from step 1.

Move it exactly as in a same-host take-over and record the judgment:

```text
Action: took over H-C-01 from C (cross-host: Codex → Claude Code; reason: cheap audit decides whether C's remaining items are worth running) as H-A-12
```

The user can lower or raise the Priority floor, forbid cross-host take-overs, or approve specific items; an explicit user instruction always wins. The resulting discovery records your host in `Host`, so a session on the original host can still cross-check it.
