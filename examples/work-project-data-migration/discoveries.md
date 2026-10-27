# Brindle inventory migration — Discoveries

## D-A-001 — Rehearsal meets the cutover window
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-24
- Session: lumen:A@2026-10-24T08:00
- Cross-check: VERIFIED
- Finding: the copy retained all 240000 rows and finished in 84 seconds
- Evidence: outputs/rehearsal.txt: key sets and per-warehouse totals match; limit 120 seconds
- Implication: permit the scheduled pointer switch after independent review
- Reviews:
  - Lumen (A): CLOSED — reviewer subagent:opal@2026-10-24T13:30 — compared source and copied key sets and recomputed warehouse totals

## D-A-002 — Choose pointer switch and retain rollback
- Source: A
- Host: Lumen
- User: mira
- Date: 2026-10-25
- Session: lumen:A@2026-10-25T08:00
- Cross-check: VERIFIED
- Finding: the rehearsed pointer switch fits the service window
- Evidence: D-A-001 and the inventory service acceptance contract
- Implication: complete the switch; retain the old table for seven days
- Reviews:
  - Lumen (A): CLOSED — reviewer subagent:opal@2026-10-25T10:00 — checked the rehearsal against the window and rollback contract
- Kind: direction-review
- Gap: 84 seconds versus 120-second ceiling, rehearsal timer on 2026-10-24 (D-A-001)
- Decisions: H-A-03 created for retention cleanup after cutover
