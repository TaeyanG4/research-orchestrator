# Verification

Read "Common rules", then the `Verification` policy in `agents.md`; the built-in default is `cross-host-once`.

## Common rules

Unless `Verification` is `self`, every discovery starts `PENDING` and is reviewed **once** by an eligible reviewer; add a second review only when the discovery is high impact or disputed. Models tend to echo a supplied claim: judge the evidence as if the claim were wrong, without starting from the source's conclusion.

When no eligible reviewer or sub-agent can be started in this session, leave new discoveries `PENDING`, record the unavailable review in the handoff, and finish the item lifecycle and session close without polling or waiting for a reviewer. This applies on every host, including when a configured reviewer cannot launch: waiting cannot create an independent session and risks losing the completed work's handoff. Restore any review claim you took to its prior effective state. Keep the configured verification policy (`self` requires no review); do not invent a reviewer identity or change policy to manufacture verification. A later eligible session can review the preserved evidence.

Two words, in two places:

- **Verdict** — what a reviewer writes on its own line under `Reviews:`: `CLOSED`, `HOLD`, or `CHALLENGED`, or a resolution of a challenge (below).
- **State** — the discovery's `Cross-check:` line, which everyone reads.

| Verdict (`Reviews:` line) | State (`Cross-check:`) | Meaning |
| --- | --- | --- |
| — | `PENDING` | nobody eligible has reviewed it yet |
| — | `REVIEWING <Host> (<Agent>)` | an eligible session has claimed the review |
| `CLOSED` | `VERIFIED` | the reviewer accepts it — the normal pass |
| `HOLD` | `HOLD` | plausible, but specific evidence or an improvement is needed first |
| `CHALLENGED` | `CHALLENGED` | a contradiction, flaw, or missing assumption — a failure, not a pass |

`CLOSED` is never written in `Cross-check:`. Review lines read `<Host> (<Agent>): <VERDICT> — <reason>`; your section below says what may come before the reason. To review:

1. Pick an eligible discovery (your section below) whose state is `PENDING`, `HOLD` whose stated condition is now met, or `CHALLENGED` whose source has answered the challenge.
2. Claim it: `Cross-check: REVIEWING <your host> (<your agent>)`. Never take a discovery another session claimed unless that slot's `Current host` reads `released` or `unassigned`, or the user says so.
3. Add your review line with `reviewed <ISO time>` after any same-host marker and reviewer identity, distinguishing new reviews from legacy evidence. For `HOLD` or `CHALLENGED`, say what would make it acceptable.
4. Set `Cross-check` to the state the review lines now give (below). If you stop before finishing, set it back to what it was.

Use `VERIFIED` discoveries freely. Depend on `PENDING`, `REVIEWING`, or `HOLD` findings only when the item's `Evidence` says the premise is not yet verified; review a high-priority premise first when eligible. Do not build on a `CHALLENGED` finding until its challenge is resolved, because later work would otherwise inherit a known flaw.

**The state follows the review lines, read in order.** Each review that counts under your `Verification` sets the state of its verdict. A `CHALLENGED` review then stands — even one that does not count — until a counting review resolves it with `CLOSED after challenge — <reason>` (or `VERIFIED after challenge`, the same), or `HOLD after challenge — <reason>`, naming what answered the challenge. An ordinary `CLOSED` or `HOLD` written while a challenge stands leaves the state `CHALLENGED`.

**Revisions.** When the source revises a `HOLD` discovery with new evidence, it updates `Evidence`, keeps the old reviews, and resets `Cross-check` to `PENDING`. A revised `CHALLENGED` discovery stays `CHALLENGED`: the source updates `Evidence` and keeps the reviews, and only an eligible reviewer's resolution changes the state.

The checker computes that state and rejects a `Cross-check` line that differs from it — `discovery.state.challenged` for a state that hides a standing challenge (including `PENDING`), `discovery.state.unbacked` or `discovery.state.mismatch` for a `VERIFIED` or `HOLD` the reviews do not give, and `discovery.state.superseded` for a `CHALLENGED` that a resolution has ended.

**Reviewer** (`off` or `on — <platform> / <model>`): when on, a session on that platform hands each eligible `PENDING` discovery to a reviewer sub-agent with that model, so the main agents keep experimenting. The session claims the review under its own slot and writes the line under its own host and slot, naming the sub-agent's session first in the reason: `Codex (B): CLOSED — reviewer subagent:sol@2026-10-25T15:02 — reproduced with ...`. The eligibility rules of your section still apply.

## cross-host-once

Verification is per **host**: a discovery made on one host is checked once by a session on a different host, because sessions on the same host share the same blind spots. The source slot never reviews its own discovery, whatever its host. How "different host" applies depends on `Platform mode`:

- **`multi`** — only a review from a different host counts.
- **`single`** — there is one host, so a review from a different **slot** counts, and its reason starts with `same host —`.
- **`adaptive`** — a review from a different host counts. When no other host is active, `Cross-check fallback` decides: `wait` leaves the discovery `PENDING` for that host (work that depends on it says so in its `Evidence`); `same-host` lets a session in a different slot on the same host review it once its own queue runs out — with a different model when it can — starting the reason with `same host —`. A session on another host may add a second review later.

`Cross-check fallback` matters only in `adaptive` projects. A same-host review without `same host —` does not count (`discovery.review.same-host`); one the mode does not allow, or one from the source slot, does not count either (`discovery.review.ineligible`).


## independent-review

A discovery is verified by a reviewer **session** that is not the one that made it — typically a sub-agent the working session launches. Same host and same slot are allowed, which is what lets a lone agent verify its own line of work.

Give the independent session the bundled [reviewer instructions](reviewer.md); the caller records eligible reviews and state. Direct skill copies include these instructions; Claude Code's `ro-reviewer` agent is optional. Pass this `verification.md`'s absolute path or let the reviewer use Glob `**/research-orchestrator/references/verification.md`. Resolve missing or ambiguous matches in the caller, since plugins may live outside the project. If no independent session can run, follow the unavailable-review path above.

- A **session identity** is `<kind>:<name>@<start time>`, for example `claude-code:A@2026-10-25T14:10` for a working session or `subagent:fable@2026-10-25T15:02` for a reviewer sub-agent. A model name alone (`reviewer sol`) is not an identity: such a review does not count (`discovery.review.identity`).
- Every new discovery records its source session in `Session:` (right after `Date:`).
- The review line names the reviewer and actual review time separately: `Claude Code (A): CLOSED — reviewer subagent:fable@2026-10-24T15:02 — reviewed 2026-10-25T09:30 — reproduced ...`. A session may begin before the discovery exists; its start identifies the reviewer, not when the review happened.
- A review counts when its reviewer is a session identity that differs from the discovery's `Session:`. Its namespace is lowercase letters and hyphens (including `subagent`), its name is nonempty without whitespace or `@`, and its ISO start timestamp is valid and no later than now. Invalid dates, future starts, bare names, partial identities, and the source reviewing itself do not count.
- Record `reviewed <ISO date and time>` after the identity so chronology can be checked: the review is no earlier than the discovery `Date` or reviewer session start, and no later than now. Offset timestamps compare instants; `Date` starts at local midnight. Older review lines without this field remain compatible; their review time is unrecorded, never inferred from the session identity.
- A discovery without `Session:` (written before this setting existed) keeps its original meaning: a review from a different slot counts, with or without a reviewer identity, and a review from its own slot does not (INFO `discovery.review.legacy-session`). Switching an older project to this setting therefore keeps its verified discoveries verified.
- Give the reviewer the discovery, its evidence and artifacts, and this file's "Common rules" — not your conclusion or the conversation that produced it.
- Unreviewed `PENDING` discoveries produce INFO, never an error; follow the unavailable-review path in Common rules when no independent session can run.

Every policy checks identity and time before eligibility, including legacy records: a different host or slot cannot rescue invalid identity or chronology. The checker cannot authenticate sessions or prove independence; retain the evidence and review result.

## hybrid

Either form counts: a review that the `cross-host-once` rules accept for your `Platform mode`, or one that the `independent-review` rules accept. Record `Session:` on new discoveries so both forms stay available.

## self

No review is required: omit `Cross-check` and empty `Reviews`, or keep `PENDING`; absence means pending, not verified. Any session, including the source, may add a review. Explicit states still follow review evidence as in "Common rules".
