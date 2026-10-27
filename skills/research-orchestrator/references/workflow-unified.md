# Workflow: unified

`Workflow: unified` keeps one shared queue. Any slot works any item; a `Claimed:` line says who is on it right now. There is no take-over procedure: an unclaimed item is free for everyone.

## The queue

- `plan.md` has exactly one `## Queue` section holding every item, and no `## Agent:` sections. `handoff.md` keeps one `### Agent:` section per slot, as in every workflow.
- Item IDs still embed the slot that created them (`H-<Agent>-<NN>`, numbered by that slot); the prefix records the author, not the owner.
- Every item starts with its claim line, then the fields in references/plan-items.md:

```text
- Claimed: none | <slot> since YYYY-MM-DD HH:MM
```

- The whole queue is shared reading: read every item you consider, not only headings. Other slots' active handoff sections stay private except their `Current host`, `Current user`, and `Current thread` lines.

## Claims

1. Run `ro --slot <slot> claim <ID>` before starting the item. Its project lock checks and writes the claim together, so competing slots cannot both acquire it; rereading and manually editing leaves a race. If another taken slot owns it, pick another item. Use the installed `scripts/ro.py` entry point as described in [operations-safety.md](operations-safety.md).
2. Claim only what you start now; one slot may hold several claims while their jobs run.
3. Never edit an item claimed by another taken slot. Anyone may refine or rescore an unclaimed item.
4. A claim by a `released` or `unassigned` slot is stale: anyone may set it to `Claimed: none` and log the cleanup in their next event.
5. Finishing an item follows the SKILL.md item lifecycle; work adds its ID to the session event's `Completed` list, while research and competition use the bare item ID as the event heading. The item leaves `plan.md`.

## Session start and close

- **Start**: take a slot (references/sessions.md). Resume the items your slot still claims; otherwise select an eligible unclaimed item whose `Resource` you can run now. Work and plans with `Ordering: queue` use queue order or the optional header `Next:` pointer; other research and competition plans use highest `Priority` (ties: lower `Cost`, then higher `Information`).
- **Close**: follow the [session close procedure](sessions.md#close-a-session), including its check of every owned job before `ro close`.

## When the queue runs out

1. Items your slot claims.
2. Unclaimed items, by the profile's ordering above.
3. Reviews you are eligible for (`references/verification.md`).
4. New work: a plan collector round when the collector is on and the queue is at or below its resume limit ([plan-collector.md](plan-collector.md)), otherwise items you derive from discoveries; new items enter the queue with `Claimed: none`, or claimed by you if you start them now.
5. Nothing worthwhile left: record it in your active handoff section and follow the [session close procedure](sessions.md#close-a-session).

Staged items (`Item size: staged`) are described in `references/staged-items.md`.

## Migration between workflows

Read [migration-v2-to-v3.md](migration-v2-to-v3.md) before changing `Workflow`. It owns the preflight, item movement, backups and journal recovery procedure.
