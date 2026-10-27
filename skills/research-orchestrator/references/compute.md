# Workers and exclusive resources

Exclusive resources (compute, a shared database, a licensed seat) need coordinated ownership so concurrent work does not contend for the same capacity or change shared state unexpectedly. Read this before adding workers or using those resources. The profile's queue ordering decides **what** is worth running; routing decides **where** it runs. Do not launch low-value work merely to keep a resource busy.

## Scale workers from 2 to practical full load

When parallel work is useful, start with two independent agents (`A` and `B`). Add more only while all are true:

- independent high-value plan items remain;
- required resources have headroom, including shared locks or licensed seats as well as CPU, GPU, RAM, disk I/O, and remote quotas;
- added workers do not materially reduce throughput;
- workers are not duplicating work unless deliberate replication is the goal.

There is no fixed maximum. Practical full load is the highest useful concurrency the available resources can sustain without harmful contention. Scale down when throughput worsens, capacity tightens, tasks become dependent, or the queue becomes too small. Reasoning-only sessions may outnumber exclusive jobs; agent count is not the number of simultaneous resource claims.

## Route work by `Resource`

Routing uses `Resource: CPU | GPU | EITHER`, `Parallel: YES | NO`, and `Other: NONE | <external executor>` (for example `Other: cloud-batch`). Every profile may omit all three: defaults are `CPU`, `NO`, and `NONE`, so absence grants neither parallel execution nor external routing. With queue ordering, the ordering below means queue position or the header `Next:` pointer.

Non-compute exclusive resources belong in `Other` (for example `Other: shared-database` or `Other: licensed-tool-seat`), with `Parallel: NO`; `Resource` still describes the local compute used. Acquire the resource's own shared lock or scheduler reservation before launch, because `ro launch` reserves local CPU/GPU capacity, not named `Other` resources.

1. Choose the next eligible item in queue or priority order and check its named resource's availability.
2. For `Other: shared-database`, acquire the database's shared migration lock and keep `Parallel: NO`; for a licensed seat, acquire the licence scheduler's reservation.
3. While that resource is busy, take independent work or review an existing finding. Use a permitted remote executor only when its credentials, quota and authorization allow it.
4. Keep secret-dependent or local-artifact-dependent work queued locally.

For device-specific routing, read [competition.md](competition.md#local-compute-routing).

## Claim exclusive resources before use

`Active compute` in `handoff.md` Shared state lists exclusive resource claims, separated by `; `, or reads `none`:

```text
- Active compute: Other — A (H-A-04, since 2026-10-05 18:20)
```

The resource is `CPU`, `GPU`, or `Other` (an external executor such as a cloud batch service or licensed tool). For a shared database migration, record the database in the plan's `Other` field and keep `Parallel: NO`; also acquire its shared lock because local reservations cannot coordinate separate checkouts. When sessions run on more than one machine, add its hostname: `Other@worker-one — A (H-A-04, since 2026-10-05 18:20)`; only compute claims on your own machine block you. Work that needs no exclusive resource — reading, reviewing, writing code, small smoke tests — needs no claim.

1. Before launching, re-read `handoff.md` and check **both** the claims and the machine's real usage (for example the database lock table, licence scheduler, or task manager). A free device can become busy between that check and launch.
2. Add your handoff claim and use `ro launch`. The command checks handoff claims and atomically reserves the plan item's resource in `.ro/jobs.json` under the project lock, so simultaneous local contenders cannot both acquire an exclusive resource.
3. Remove your claim when the owned work has verifiably ended, alongside its recorded outcome. A supervisor failure alone does not release it.

## When the resource you need is busy

Share a resource only when both items are `Parallel: YES` and measured free memory and load fit them; then add your own claim next to the existing one. The launcher checks both declarations because an existing exclusive job may depend on uncontended capacity. `EITHER` conservatively reserves CPU and GPU; use the specific resource in the plan when only one is needed. Otherwise wait, and meanwhile do the most valuable work that does not need that resource:

1. **Another resource**: your highest-priority item that fits an idle resource (an `EITHER` item on the free device, or a permitted `Other` executor).
2. **No heavy compute**: an eligible review; preparing the waiting experiment (script, tiny-sample test); analysing recent results and planning follow-ups; rescoring; the consistency check.
3. **Nothing useful left**: set `Blocker: waiting for shared-database (held by A for H-A-04 since 18:20)` in your active handoff section and check again at an interval that matches the running job's expected length — not in a tight loop.

When the resource frees, clear your `Blocker`, add your claim, and launch.

Reservations coordinate commands using the same local project state. Separate checkouts, other projects, remote executors and Git-synchronized copies do not share this lock; use an executor's scheduler or another shared reservation service for those cases. The launcher cannot measure free memory or discover unregistered workloads. Keep handoff claims and capacity checks for that reason. A failed supervisor keeps its reservation and file bindings while owned work is live or its termination remains unverified; reconcile or stop that work before reusing its resources.

## Host limits and fresh sessions

On a host usage limit, HTTP 429 or 503, or "model at capacity", save the failed attempt and open a fresh session up to three times before waiting for the stated reset (or a bounded backoff if none is given). Never resume the broken session: its partial outputs and tool state may be incomplete. Keep each attempt's evidence separate, restore only verified project state, and do not replay an uncertain outward action; reconcile it through [external-actions.md](external-actions.md) first. This retry rule also applies to evaluation and trigger runners.

## Stale claims

A claim is stale when its slot is `released` or `unassigned`, when its item is no longer in `plan.md`, or when the job is verifiably not running. Remove your own stale claims at once. A stale claim of a released slot may be removed by anyone; log it in your next event (`Action: cleared stale Other claim of C for H-C-02`). If the claiming agent is still active, do not remove its claim — add it to `Open consistency issues` instead.

Never release your slot while a job you launched is still running: keep `Current host`, describe the job in `Resumable state`, and keep the claim.
