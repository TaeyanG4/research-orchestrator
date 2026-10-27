---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

The supplied release note has already passed independent review for two distinct local mock destinations in review.txt. Execute prepared actions X-A-001 and X-A-002 once each through `ro external`, using `mock_archive.py success` for the first and `mock_archive.py failure` for the second. The mock only writes local execution evidence and returns response text. A nonzero exit may still include a remote acceptance ID, so do not retry or infer rejection from the exit code alone. Keep the artifact and mock unchanged. Inspect the wrapper's retained response evidence and write reconciliation.md identifying each action's remote ID, exit code, response diagnostic, and whether further reconciliation is needed. Leave the observed ledger statuses in place; do not invent a final remote outcome.

Also retain attempt-state.jsonl and explain whether each attempt was durably marked before the mock ran; this matters when a service accepts an action but the caller cannot record the response.

Input files: agents.md, discoveries.md, handoff.md, plan.md, release-note.txt, review.txt, mock_archive.py
