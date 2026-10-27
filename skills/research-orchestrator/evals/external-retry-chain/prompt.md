---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Exercise our external-action workflow using only the supplied local stub; no network action is authorized. In a scratch research project, prepare one reviewed artifact and three attempts X-A-001, X-A-002, X-A-003 for the same destination. The first two calls should fail with exit 7 and have their outcomes reconciled before the next attempt. Link the second to the first and the third to the second, with distinct chronological expectation/result timestamps. Execute the third successfully, then try replaying it. Check the ledger with the project checker too. In isolated copies try a missing predecessor, a forward reference, a self reference, a cycle, a different artifact/destination, a broken ancestor, and a duplicated ancestor ID. Also try executing an old prepared record when a later matching action is already done, and an unlinked duplicate with trailing spaces on either Candidate field. Save command output, the final ledgers, the local attempt log, and a concise results.md with what actually happened. Use the installed skill scripts without modifying them; do not manufacture receipts as an independent review you did not perform. The supplied review attestation authorizes recording the local fixture receipt.

Record the service evidence establishing non-acceptance before each retry, because an exit code alone cannot establish that an action did not happen remotely. Preserve the wrapper attempt journals with the final ledger.

Input files: artifact.txt, review.txt, action_stub.py
