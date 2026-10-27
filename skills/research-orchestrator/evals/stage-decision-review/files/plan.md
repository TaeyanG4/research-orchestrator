# Stage launch probe - Plan

## Queue

### H-A-01 — Bounded rollout
- Claimed: A since 2020-01-01 08:00
- Goal: Validate one routine and one consequential stage locally
- Evidence: The isolated stub only appends an execution marker
- Next test: Run the named stage and preserve the actual outcome
- Stages: s1 routine sample | s2 consequential launch | s3 report
- Important stages: s2

### H-A-02 — Independent routine check
- Claimed: A since 2020-01-01 08:00
- Goal: Check an unrelated routine stage
- Evidence: No changed decision or important-stage designation applies
- Next test: Run the local stub once
- Stages: s1 routine check
