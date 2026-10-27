# CV Leakage Study — Discoveries

This file holds **what is known**: every claim, its numbers and interpretation, and its verification state. Every agent reads all of it. `handoff.md` only points here by ID.

Verification is per **host**, not per agent: a discovery made on one host (for example Codex) is cross-checked **once** by a different host (for example Claude Code). Sessions on the same host do not re-review each other.

Discovery IDs use `D-<Agent>-<NNN>`, numbered by the agent that creates the discovery, for example `D-A-001` or `D-B-014`.

Use this exact format:

```markdown
## D-B-001 — Short title
- Source: B
- Host: Codex
- User: lee
- Date: 2026-10-05
- Cross-check: VERIFIED
- Finding: ...
- Evidence: ...
- Implication: ...
- Reviews:
  - Claude Code (A): CLOSED — reproduced independently with ...
```

`Host` and `User` are the platform and the person of the session that made the discovery, and `Date` is the day it was first recorded (`YYYY-MM-DD`). None of them change when the discovery is revised or reviewed. Use `unknown` only for discoveries migrated from older notes whose user or date cannot be recovered.

`Cross-check` states:

- `PENDING`: no different host has reviewed it yet. New discoveries start here, with an empty `Reviews:` list.
- `REVIEWING <Host> (<Agent>)`: a different-host session has claimed the review.
- `VERIFIED`: a different host reviewed it and recorded `CLOSED`.
- `HOLD`: a different host needs specific evidence, a condition change, or an improvement first.
- `CHALLENGED`: a host found a material contradiction, flaw, or missing assumption.

Rules:

- The source does not review its own discovery.
- Review only discoveries whose `Host` differs from yours and whose `Cross-check` is `PENDING` (or `HOLD` when its condition is now met). Claim it first with `REVIEWING <your host> (<your agent>)`.
- One cross-host review is enough; add another only for high-impact or disputed discoveries.
- Review lines use `<Host> (<Agent>): CLOSED | HOLD | CHALLENGED — reason`. `HOLD` and `CHALLENGED` must say what would make the discovery acceptable.
- When the source revises a `HOLD` or `CHALLENGED` discovery, it updates `Evidence`, keeps the old reviews, and resets `Cross-check` to `PENDING`.
- If only one host is available, a different slot on the same host may cross-check; begin its reason with `same host —`.
- Use `VERIFIED` discoveries freely. A plan item built on a `PENDING`, `REVIEWING`, or `HOLD` discovery must say so in its `Evidence`. Do not build on `CHALLENGED` discoveries until resolved.

Every completed experiment or test creates or updates exactly one discovery here, whatever the outcome, so this file is the only index of what has been tried:

- positive: `Finding: <claim>`
- negative: `Finding: <claim> does not hold under <conditions>`
- inconclusive: `Finding: inconclusive — <what was tried and why it did not settle>`

A cross-check updates the reviewed discovery instead of creating a new one. Before adding a plan item, every agent searches this file first.

When a result beats the project's current best, start its `Implication` with `new current best:` and update `Current best` in `handoff.md` Shared state in the same step, citing this discovery.

A discovery may generate many plan hypotheses, and one hypothesis may combine many discoveries. When moving an idea back into `plan.md`, always include the source IDs plus the concrete `Evidence` and `Improvement` that justify the new attempt.

Do not archive this file merely because it grows; merge duplicate discoveries instead.

---

## D-B-001 — Random CV leaks customer groups
- Source: B
- Host: Codex
- User: lee
- Date: 2026-10-05
- Cross-check: VERIFIED
- Finding: rows from the same customer_id land in both training and validation folds under random KFold
- Evidence: random KFold CV 0.9162 vs GroupKFold CV 0.9027; reproduce with experiments/e001_group_check.py
- Implication: random CV is optimistic by about 0.013; use GroupKFold for model selection
- Reviews:
  - Claude Code (A): CLOSED — reproduced with fold seed 7; gap 0.0131

## D-A-001 — Exact duplicates explain most of the gap
- Source: A
- Host: Claude Code
- User: kim
- Date: 2026-10-05
- Cross-check: REVIEWING Codex (B)
- Finding: removing exact duplicate rows shrinks the random/group CV gap from 0.0135 to 0.0041
- Evidence: random/group CV 0.9071 / 0.9030 after deduplication; reproduce with experiments/e002_dedup.py
- Implication: new current best: baseline LightGBM at GroupKFold CV 0.9030 on deduplicated data; deduplicate before building folds
- Reviews:

## D-C-001 — Encoders are fit before the fold split
- Source: C
- Host: Claude Code
- User: kim
- Date: 2026-10-05
- Cross-check: PENDING
- Finding: features/encode.py fits every categorical encoder on the full training set before the GroupKFold split
- Evidence: code audit of features/encode.py; notes/encoding_audit.md
- Implication: every encoded feature can leak target information across folds; encoders must be fit per fold
- Reviews:

## D-A-002 — Global target encoding does not hold under GroupKFold
- Source: A
- Host: Claude Code
- User: kim
- Date: 2026-10-05
- Cross-check: PENDING
- Finding: global target encoding does not hold under GroupKFold on deduplicated data (CV 0.9027 → 0.8991)
- Evidence: GroupKFold CV 0.8991 vs 0.9027 without encoding; reproduce with experiments/e003_target_encoding.py
- Implication: do not retry global target encoding; only fold-aware encoding (H-A-04, taken over from H-C-02) is worth testing
- Reviews:
