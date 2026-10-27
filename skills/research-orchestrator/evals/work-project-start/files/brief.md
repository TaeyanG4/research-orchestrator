# Archive conversion brief

Deliver an auditable conversion of a 4,000-record document index from the legacy schema to a documented new schema over three working days.

Day 1: inspect field meanings and run a small local pilot against a copy.
Day 2: compare all converted records, investigate mismatches, and prepare rollback instructions.
Day 3: obtain independent review, decide readiness, and prepare an operator handoff.

Acceptance: every input identifier occurs exactly once; dates retain their stated timezone; unmapped fields are reported rather than discarded; counts and checksums reconcile; a rollback restores the original bytes.

No source data has been supplied yet. Ask for a representative export as the first execution step. No external cutover is authorized by this setup task.
