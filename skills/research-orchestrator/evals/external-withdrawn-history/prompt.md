---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check whether tidying our external-action ledger can accidentally repeat a delivery. Use only the supplied local stub and independent review attestation; no network action is authorized. In a scratch project prepare artifact.txt for destination local stub, with receipt scope local-stub-contract. Follow scenarios.md to retain a previous attempt journal, withdraw or omit its ledger entry, and prepare a new ID with the same bytes and destination. Save the wrapper's actual refusal output and the before/after ledger and journals for each scenario. Then restore the predecessor, record the supplied service evidence and an explicit later retry, and show exactly one successful stub call. Also show that withdrawing a preparation which never ran permits a fresh preparation. Use the installed skill scripts unchanged. Save a concise results.md that identifies which preparations ran and why; retain each scenario's attempts.log or evidence that it does not exist.

Input files: artifact.txt, review.txt, scenarios.md, action_stub.py
