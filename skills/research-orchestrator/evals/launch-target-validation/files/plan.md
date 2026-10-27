# Stage launch probe - Plan

## Queue

### H-A-01 — Bounded rollout
- Claimed: A since 2020-01-01 08:00
- Goal: Validate one routine and one consequential stage locally
- Evidence: The isolated stub only appends an execution marker
- Next test: Run the named stage and preserve the actual outcome
- Stages: s1 routine sample | s2 consequential launch | s3 report
- Important stages: s2

### H-A-02 — Ordinary inspection
- Goal: inspect the rollout notes
- Evidence: notes are available
- Next test: inspect without a staged launch

### H-A-03 — Duplicated trial
- Goal: inspect a duplicated target
- Evidence: this ID occurs twice
- Next test: repair the duplicate before any launch
- Stages: s1 inspect

### H-A-03 — Duplicate of trial
- Goal: inspect a duplicated target
- Evidence: this ID occurs twice
- Next test: repair the duplicate before any launch
- Stages: s1 inspect

## Archived history

### H-A-77 — Old completed trial
- Stages: s1 archived run
