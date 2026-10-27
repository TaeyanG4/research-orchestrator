# CV Leakage Study — Handoff

This file records **what happened and where to resume**. What is known — claims, numbers, interpretations, verification — lives in `discoveries.md`; this file points to it by ID instead of repeating it.

## Shared state

- Active agent(s): A, B, C
- Users: kim, lee
- Current project state: validation fixed to deduplicated GroupKFold; feature work in progress
- Current best: baseline LightGBM, GroupKFold CV 0.9030 (D-A-001)
- Active compute: CPU — B (H-B-03, since 2026-10-05 18:05)
- Plan collection: idle
- Open consistency issues: none

Project-wide values live only here, never in `plan.md`. `Current best` always cites the discovery that set it, for example `fold-aware TE, GroupKFold CV 0.9112 (D-A-005)`; when a discovery's `Implication` starts with `new current best:`, update it in the same step. List problems you found in another agent's sections under `Open consistency issues`; the owner or the user resolves them and removes the line.

`Users` lists everyone who has run a session (`kim, lee`); add yourself the first time. `Plan collection` is `idle`, or `running — <Agent> (since YYYY-MM-DD HH:MM)` while a plan collector round runs (see `Plan collector` in `agents.md`). `Active compute` lists claims on heavy compute as `<CPU|GPU|Other> — <Agent> (<plan item>, since YYYY-MM-DD HH:MM)`, separated by `; `, or `none`; when sessions run on more than one machine, add the machine: `GPU@kim-desktop — A (...)`. Check the claims and the machine's real usage before launching; add your claim in the same step as the launch and remove it in the same step that records the job's end. A claim held by a released slot is stale and may be cleared by anyone, with a note in their next event.

Agent names are work slots (`A`, `B`, `C`, ...), never host or model names. A new concurrent session takes the next unused name and adds it to `Active agent(s)` together with its plan and handoff sections.

## Active handoff — Agent sections

Each research agent reads and edits only its own active handoff section. Do not copy another agent's unfinished plan here.

- `Current host` records which host (Claude Code, Codex, Antigravity, ...) currently owns the slot. A slot is free when it reads `unassigned` or `released`; a free slot that still holds plan items left by a different host is skipped unless the user assigns it. Set it to your host when you take or resume the slot, and to `released` when you close the session. `Current user` is the person running the session (`kim`); set it with `Current host` and reset it to `none` on release. Other sessions may read only the `Current host`, `Current user`, and `Current thread` lines of your section: to find a free slot, or to take over a queued item when their own queue runs out — never your `Current thread` or an item under an `Active compute` claim (same host by default; cross-host only by the documented exception).
- `Resumable state` is half-done work that exists nowhere else: a drafted script, a running job, a partial output.
- `Next action` names plan item IDs (`H-B-03, then H-B-02`) or a step that is not a plan item; it does not restate the item's `Next test`. Every ID named here must exist in `plan.md`.

### Agent: A
- Current host: Claude Code
- Current user: kim
- Current thread: H-A-04
- Resumable state: experiments/e004_fold_te.py drafted, not run yet
- Blocker: none
- Next action: H-A-04

### Agent: B
- Current host: Codex
- Current user: lee
- Current thread: H-B-03 (cross-check of D-A-001)
- Resumable state: experiments/e002_dedup.py running with fold seed 11
- Blocker: none
- Next action: finish H-B-03 by recording a verdict on D-A-001, then H-B-02

### Agent: C
- Current host: released
- Current user: none
- Current thread: none
- Resumable state: none; H-C-02 was taken over by A as H-A-04
- Blocker: none
- Next action: none; free slot


## Completed / review log

All agents may read this shared log. Append completed work, take-overs, meaningful resource-routing changes, and discovery-review events here. Entries are append-only.

Use this exact format:

```markdown
### YYYY-MM-DD HH:MM — A — H-A-01
- Host: Claude Code | Codex | Antigravity | <other>
- User: <user name>
- Action: ...
- Result: <one line>; see <discovery ID>
- Artifacts: <paths> / none
- Discovery updates: D-A-001 / none — <reason>
- Review verdict: <discovery ID> CLOSED | HOLD | CHALLENGED / none
- Resource: CPU | GPU | Other | none
- Other executor: Kaggle / none
- New plan items: H-A-02, H-A-03 / none — <reason>
```

- The heading's last part is the plan item the event completed; write `none` for a step that completes nothing (a routing change, a session close) and the new ID for a take-over. Items you drop as pointless are named in `Action` as `removed H-A-05 — <reason>`.
- `Result` is one line; for an experiment it points to the discovery instead of restating its numbers.
- `Artifacts` lists paths only. Metrics and their meaning belong in the discovery.
- Every completed experiment creates or updates a discovery, so `Discovery updates: none — <reason>` is only for steps that are not experiments, such as a take-over (`Action: took over H-C-03 from C (same host) as H-A-05`). A cross-host take-over states the hosts and the reason: `took over H-C-01 from C (cross-host: Codex → Claude Code; reason: <one line>) as H-A-12`.
- `New plan items` is never a bare `none`; zero follow-ups always gives a reason.
- There is no next-step line here; the slot's `Next action` above is the only one.

### 2026-10-05 14:20 — B — H-B-01
- Host: Codex
- User: lee
- Action: compared random KFold with GroupKFold on customer_id groups
- Result: random CV is optimistic; see D-B-001
- Artifacts: experiments/e001_group_check.py; outputs/e001.csv
- Discovery updates: D-B-001
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: H-B-02

### 2026-10-05 15:05 — A — H-A-01
- Host: Claude Code
- User: kim
- Action: cross-checked D-B-001 with fold seed 7
- Result: reproduced; see the review on D-B-001
- Artifacts: outputs/e001_seed7.csv
- Discovery updates: D-B-001 (review)
- Review verdict: D-B-001 CLOSED
- Resource: CPU
- Other executor: none
- New plan items: H-A-02

### 2026-10-05 16:40 — A — H-A-02
- Host: Claude Code
- User: kim
- Action: removed exact duplicate rows and rebuilt GroupKFold folds
- Result: duplicates explain most of the gap and set a new current best; see D-A-001
- Artifacts: experiments/e002_dedup.py; outputs/e002.csv
- Discovery updates: D-A-001
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: H-A-03

### 2026-10-05 17:30 — C — H-C-01
- Host: Claude Code
- User: kim
- Action: audited categorical encoders for leakage under GroupKFold
- Result: encoders are fit before the fold split; see D-C-001
- Artifacts: notes/encoding_audit.md
- Discovery updates: D-C-001
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: H-C-02

### 2026-10-05 18:10 — A — H-A-03
- Host: Claude Code
- User: kim
- Action: tested global target encoding on deduplicated data
- Result: hypothesis failed; see D-A-002
- Artifacts: experiments/e003_target_encoding.py; outputs/e003.csv
- Discovery updates: D-A-002 (negative result)
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: none — fold-aware encoding is already queued as H-C-02

### 2026-10-05 18:20 — A — H-A-04
- Host: Claude Code
- User: kim
- Action: took over H-C-02 from C (same host) as H-A-04
- Result: moved into A's section and rescored to 17; C is released and its latest event came from Claude Code
- Artifacts: none
- Discovery updates: none — take-over, no experiment
- Review verdict: none
- Resource: none
- Other executor: none
- New plan items: H-A-04

## Archived history

When this file becomes hard to scan, move older completed-log detail to `docs/<focused-name>.md` and leave a short summary/link here. Keep shared state, active agent handoffs, and recent completed/review records in this file.
