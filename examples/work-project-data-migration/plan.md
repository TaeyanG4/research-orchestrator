# Brindle inventory migration — Plan

## Queue

### H-A-03 — Retire the old inventory table
- Claimed: none
- Goal: the old table can be retired after the seven-day rollback window
- Evidence: D-A-001 verifies parity; D-A-002 chose the completed cutover and retention period
- Next test: after 2026-11-01, check that no reader uses the old table before retiring it
- Stages: s1 reader audit | s2 retain recovery export | s3 retire old table
