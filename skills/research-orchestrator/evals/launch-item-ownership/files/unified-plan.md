# Launch ownership — Plan

## Queue

### H-A-02 — Collaborator claim
- Claimed: B since 2026-10-27 11:00
- Goal: preserve the current claim
- Evidence: B has already claimed this item
- Next test: wait for B's session

### H-A-03 — Unclaimed task
- Claimed: none
- Goal: keep an unclaimed item unlaunched
- Evidence: no operator has claimed it
- Next test: acquire ownership before launching

### H-B-02 — Current claim
- Claimed: A since 2026-10-27 11:00
- Goal: run the item claimed by A
- Evidence: its durable ID does not determine its current owner
- Next test: run worker.py and monitor its result
