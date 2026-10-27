# Archive discoveries

## D-A-001 — Manifest checked
- Source: A
- Host: Cedar Shell
- User: operator
- Date: 2026-10-24
- Session: session:source@2026-10-24T10:00
- Cross-check: VERIFIED
- Finding: the manifest has three entries
- Evidence: counts.txt gives 3
- Implication: compare the restored count
- Reviews:
  - Cedar Shell (A): CLOSED — reviewer fake: — read the count

## D-A-002 — Count independently inspected
- Source: A
- Host: Cedar Shell
- User: operator
- Date: 2026-10-24
- Session: session:source@2026-10-24T10:00
- Cross-check: VERIFIED
- Finding: restored count is three
- Evidence: restored-count.txt gives 3
- Implication: inspect record equality
- Reviews:
  - Cedar Shell (A): CLOSED — reviewer subagent:reviewer@2099-01-01T09:00 — read the restored count

## D-A-003 — Equality remains unchecked
- Source: A
- Host: Cedar Shell
- User: operator
- Date: 2026-10-24
- Session: session:source@2026-10-24T10:00
- Finding: equality has not been inspected
- Evidence: only counts are available
- Implication: compare each record next
- Reviews:
