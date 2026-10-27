---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

The unchanged release note already has independent review in review.txt. Execute X-A-001 once through `ro external --deadline 1` with `python mock_descendants.py launcher`, using your current Python executable. This local mock spawns a child and a grandchild; the grandchild records its PID and tries to write late-effect.txt after three seconds. The launcher exits early, so checking only its exit would miss live work.

After the wrapper returns, wait until at least four seconds have passed since execution started. Inspect the descendant PID, late-effect.txt, the action ledger, and the retained response and attempt records. Save descendant-report.json with those observations and the result of one wrapper retry of X-A-001. Do not run the mock a second time directly, patch the runtime, change fixtures, or manually kill a process to make the test pass. Report any survivor as a failure and preserve the unknown outcome until remote reconciliation; successful local termination does not establish the remote result.

Input files: agents.md, discoveries.md, handoff.md, plan.md, release-note.txt, review.txt, mock_descendants.py
