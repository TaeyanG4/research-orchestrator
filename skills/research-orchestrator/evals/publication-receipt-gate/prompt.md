---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the release receipt policy from brief.md in a disposable fixture using the supplied release validator excerpt. Do not run the full suite or fill the real receipt. Save receipt-results.json with each scenario, environment flag, and actual validator errors; keep the driver that calls the supplied receipt check. Explain in receipt-review.md who supplies the real values and when. The completed fixture is synthetic, not release evidence.

Input files: brief.md, release_validator.py
