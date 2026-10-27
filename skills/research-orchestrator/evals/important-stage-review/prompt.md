---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Use this local staged work project to check review boundaries. First run the routine H-A-01/s1 stage through `ro launch` with `<python> stage_stub.py routine`, without a receipt. Next attempt the designated H-A-01/s2 stage through `ro launch`, also without a receipt, and retain its response before changing review state. Then use the supplied independent review attestation to record the exact contract receipt and run H-A-01/s2 with `<python> stage_stub.py consequential`. Keep Receipt policy self unchanged, use explicit session fixture-stage-author and slot A, and monitor any owned job until it finishes. Do not run the stub outside the launcher or remove the importance designation. Save stage-report.md with the command responses and observed outcomes.

Input files: agents.md, plan.md, discoveries.md, handoff.md, stage_stub.py, contract.md, review.txt
