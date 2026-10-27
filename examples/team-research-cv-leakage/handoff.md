# Aster customer overlap study — Handoff

## Shared state
- Active agent(s): A, B, C
- Users: mira, tavi
- Current project state: paused after leakage diagnosis; resume direction review before any further experiment
- Current best: baseline model, grouped cross-validation accuracy 0.9030 (D-A-001; PENDING)
- Active compute: none
- Plan collection: idle
- Open consistency issues: none
- Paused: 2026-10-25
- Not applicable: E1 — all experiments stay local

## Instruments

### I-B-01 — Grouped customer audit
- Provenance: independent
- Coverage: held-out
- Measures: accuracy on deduplicated customer groups
- Agreement: independent rerun gap 0.0131 versus original 0.0135 (D-B-001)
- Resolution: ±0.0001 (D-B-001)
- Not for: none

## Active handoff — Agent sections

### Agent: A
- Current host: released
- Current user: none
- Current thread: none
- Resumable state: experiments/e004_batch_te.py drafted; H-A-04 came from C
- Blocker: none
- Next action: none; claim a queued item when work resumes

### Agent: B
- Current host: released
- Current user: none
- Current thread: none
- Resumable state: review of D-A-001 not completed; rerun required
- Blocker: none
- Next action: none; claim a queued item when work resumes

### Agent: C
- Current host: released
- Current user: none
- Current thread: none
- Resumable state: none
- Blocker: none
- Next action: none; claim a queued item when work resumes

## Completed / review log

### 2026-10-24 14:20 — B — H-B-01
- Host: Prism
- User: tavi
- Action: compared random cross-validation with grouped cross-validation on customer_id groups
- Result: random accuracy is optimistic; see D-B-001
- Artifacts: experiments/e001_group_check.py; outputs/e001.csv
- Discovery updates: D-B-001
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: H-B-02

### 2026-10-24 15:05 — A — H-A-01
- Host: Lumen
- User: mira
- Action: cross-checked D-B-001 with fold seed 7
- Result: reproduced; see the review on D-B-001
- Artifacts: outputs/e001_seed7.csv
- Discovery updates: D-B-001 (review)
- Review verdict: D-B-001 CLOSED
- Resource: CPU
- Other executor: none
- New plan items: H-A-02

### 2026-10-24 16:40 — A — H-A-02
- Host: Lumen
- User: mira
- Action: removed exact duplicate rows and rebuilt grouped cross-validation folds
- Result: duplicates explain most of the gap and set a new current best; see D-A-001
- Artifacts: experiments/e002_dedup.py; outputs/e002.csv
- Discovery updates: D-A-001
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: H-A-03

### 2026-10-24 17:30 — C — H-C-01
- Host: Lumen
- User: mira
- Action: audited target encoders for leakage under grouped cross-validation
- Result: converters are fit before the fold split; see D-C-001
- Artifacts: notes/conversion_audit.md
- Discovery updates: D-C-001
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: H-C-02

### 2026-10-24 18:10 — A — H-A-03
- Host: Lumen
- User: mira
- Action: tested global target encoding on deduplicated data
- Result: hypothesis failed; see D-A-002
- Artifacts: experiments/e003_target_conversion.py; outputs/e003.csv
- Discovery updates: D-A-002 (negative result)
- Review verdict: none
- Resource: CPU
- Other executor: none
- New plan items: none — fold-aware conversion is already queued as H-C-02

### 2026-10-24 18:20 — A — H-A-04
- Host: Lumen
- User: mira
- Action: took over H-C-02 from C (same host) as H-A-04
- Result: moved into A's section and rescored to 17; C is released and its latest event came from Lumen
- Artifacts: none
- Discovery updates: none — take-over, no experiment
- Review verdict: none
- Resource: none
- Other executor: none
- New plan items: H-A-04
### 2026-10-24 18:25 — A — none
- Host: Lumen
- User: mira
- Action: paused the overlap study; reset the unfinished review of D-A-001 to PENDING and released A, B, C
- Result: no compute remains; queues preserved for reopening
- Artifacts: none
- Discovery updates: none — session close
- Review verdict: none
- Resource: none
- Other executor: none
- New plan items: none — existing follow-ups remain queued

## Archived history

None.
