# Operational safety

Owned jobs need stable inputs and recorded outcomes so later sessions can trust their results. Start here; open lookup sections for command details.

## Read first

1. Set `RO_SLOT` and `RO_SESSION`, read `ro brief`, and claim or own the selected item. Reserve record IDs with `ro next-id`.
2. Launch long work through `ro launch` with a dedicated run directory and explicit shared inputs or exclusive outputs. Check the item and every supplied stage against the active plan before preparing receipts.
3. Start the returned monitor command immediately. A confirmed launch is not a result: monitor to an outcome, inspect artifacts, and append the returned Job line.
4. Record reusable findings and follow-ups, then `ro close`. Resolve live or unmonitored jobs before releasing their claims.

## Lookup: state and recovery

Run `ro jobs` to inspect registered jobs and their monitor state before repairing local tool state.

- Durable state prevents identity reuse and mistaken ownership. The four coordination files hold work and evidence; `.ro/` holds jobs, receipts, reservations, locks and checker state. Init ignores `.ro/` in Git when sync is enabled.
- Preserve the durable job sequence when pruning. Metadata backups and ID high-water marks prevent reuse after reservation expiry or archive removal.
- Atomic writes retry Windows contention. Locks retain live owners; repair dead or malformed owners only under the OS lock.

## Lookup: IDs, claims and records

Run `ro next-id D` to reserve a discovery ID so simultaneous sessions do not reuse it.

- Reservations prevent simultaneous sessions from taking the same identity. Use `H`, `I`, `X` or `N` for other record kinds; `--slot A` chooses the slot. Reservations expire after ten minutes and reconcile when the record appears.
- `ro dupcheck <terms...>` searches headings and relevant lines in coordination files and archived `docs/` records.
- `ro claim H-A-01` rereads the unified queue under lock and refuses another taken slot's claim. `ro release H-A-01` refuses release until owned jobs end with monitor outcomes.

`N-<slot>-<number>` reserves an ID for a user-maintained note in an existing document. It adds no checker record kind or coordination file; use established kinds for findings, plan items, insights and external actions.

`ro index` prints live discovery headings, Status/Cross-check lines and whole findings, clipping findings to 160 characters only once the whole index passes 48 KiB, and counts archived entries; `--full` keeps whole lines. Open an entry, archived ones included, with `ro index D-A-001` before reusing its premise or repeating its experiment.

`ro archive` and `ro tools` are described in [records.md](records.md#archiving-history) and [tools.md](tools.md). Keep claims and material conditions in Finding so searches find them.

PostToolUse warns about new headings or dates beyond now plus five minutes and duplicate IDs introduced by edits, including shell edits. The checker remains available on every host.

- Process exit alone does not establish a monitored result. `ro close` releases item and compute claims except those protected by running jobs or jobs without a recorded monitor outcome. It runs the checker and reports remaining claims and discoveries without follow-ups.
- The slot becomes `Current host: released` and `Current user: none` only when every registered job has ended with a monitor outcome; otherwise ownership remains and the monitor command is printed.
- Record reusable findings before closing: chat-only findings and unregistered helper reports are invisible to the command.
- Check host-managed, remote and other unregistered jobs using the [session close procedure](sessions.md#close-a-session) before invoking `ro close`; their claims and slot could otherwise be released while they still run.

## Lookup: Shell calls and bound paths

Use `ro launch --input <path> --bind <output> -- <command>` to distinguish shared inputs from exclusive outputs.

Use `--input <path>` for shared read-only inputs; inferred script paths are shared too. Multiple jobs may read them concurrently. Keep `--bind <path>` and dedicated run directories for exclusive outputs. Any overlapping output conflicts with both readers and writers, and hook mutation protection covers both kinds of binding.

Use the host's background facility or job commands below to keep ownership visible. Leave bound paths unchanged while jobs use them so results refer to recorded inputs. The project root stays writable for coordination. [hooks.md](hooks.md) owns shell parsing and path-check limits.

## Lookup: Launch, monitor and stop

Run `ro launch --item H-A-01 --expect 2h --run-dir runs/current -- <command>` to start owned work with a monitor command and a stable run directory.

For launches designated by `Important stages:`, follow [staged-items.md](staged-items.md): independent receipts bind the exact stage scope before launch and after decision-changing results. Routine launches retain the optional receipt path below.

- Stable bindings make launches traceable. Use `ro launch --item H-A-01 --expect 2h --run-dir runs/current --bind input.txt --error "fatal" --heartbeat heartbeat.txt --max-silence 20m --confirm 15s -- <command>` to detach owned work; conflicting running-job bindings refuse the launch.
- A dedicated run directory and script paths are bound automatically. Without `--run-dir`, or with a directory at or above the project root, only scripts and explicit bindings are protected; the command prints that limitation. Explicit bindings of the root or its ancestors are refused.
- The job stores PID, process start time and a redacted command; briefs never print the command. `--require-receipt artifact.txt` requires a current PASS under the configured `Receipt policy`.
- Take a real host/user slot in `Active handoff` and own the live item: its classic section or unified claim names your slot. The lock checks both before reserving an ID; archives confer no ownership.
- Confirmation starts after the child-start handshake. A handoff "launched" event requires the full interval, a still-live child identity and no matched error pattern. Even `--confirm 0` requires the handshake and live child; a three-second process cannot pass the default fifteen-second interval.

A launcher may exit while its workers continue. The supervisor and bindings remain until the owned process group or Windows job object has no workers, so a launcher exit alone does not release inputs or claims.

- Surviving workers can still use bound paths. A supervisor crash leaves `attention` while the recorded child or owned tree is alive or its termination is unverified. Bindings, launch conflicts, item claims and slot ownership remain protected after the incident is monitored.
- Use `ro kill` on the identity-verified tree, then monitor its terminal outcome. If ownership cannot be established, reconcile surviving work before releasing records; a reused PID alone is not a safe kill target.

- Launch confirmation only proves that work started. Start the exact monitor command immediately, using the host's background facility for a long wait. Retain ownership until the outcome is recorded, including when a job exits during launch confirmation.
- The monitor backs off while unchanged and writes changed state. It reports completion, a matched error pattern, configured heartbeat silence, or twice the expected duration. Resolve or stop a living job after an error or stall, then monitor again.
- The outcome is saved in `.ro/jobs.json`; append the printed Job line to `handoff.md` and inspect result artifacts before claiming success.
- `ro jobs` refreshes process identities and monitor state; `--prune` removes only ended entries with recorded outcomes. PID reuse means the original job is gone.

Restarting a monitor rechecks current conditions after a repair; prior incidents remain in the registry with their observation and recovery times. Already consumed log matches do not retrigger, while new matches still end the monitor.

- `ro kill <job>` checks caller slot ownership, PID and start time before terminating the Windows job object or owned process group elsewhere. Older Windows entries use `taskkill /T` when no job object is recorded.
- Stop checks jobs without a live monitor while running or lacking a recorded monitor outcome, including finished jobs. When listed for blocking, it blocks each job once per session, then warns until resolved.
- Unrelated open claims and missing reports are not stopping barriers.

## Lookup: Receipts and external actions

Run `ro external --help` to inspect the execution interface; prepare its ledger and receipt before an outward action.

Read [external-actions.md](external-actions.md) before preparing a receipt or executing an outward action; it owns the ledger and command workflow.

## Lookup: Facts, briefs and publication

Read `ro brief` for the state needed to resume without loading other sessions’ detailed notes.

- Dated facts prevent stale assumptions. `ro observe <key> <value> --source <source> --ttl 6h` records a volatile Shared state fact and observation time; stale facts are flagged.
- `ro brief --max 8000` reports settings, hooks self-test, slot and claims, job/monitor state, overdue guard items, saturated families and checker counts.
- Briefs contain facts, IDs, titles, numbers and dates within 8,000 characters; they omit other sessions' free prose and stored command lines.
- `Brief requirements` names required lines for sub-agent types, allowing a warning before delegation when a contract line is missing.

For publication, read [publication-safety.md](publication-safety.md). `ro hook <event>` is the JSON-stdin adapter entry point; [hooks.md](hooks.md) explains daily use; [hooks-capabilities.md](hooks-capabilities.md) owns installation and evidence.
