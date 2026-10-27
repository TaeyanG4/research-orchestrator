---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit these saved installed-hook observations against Research Orchestrator's current runtime contract. Do not run hooks or timing measurements. Write verdicts.json with one object per observation containing its id, accepted boolean, and the common latency budget in budget_ms. A missing OS measurement is unknown, not a passing measurement. In review.md explain how the configured-interpreter path keeps its deadline and why ordinary hooks and authoritative pre-push have different timeout outcomes.

Input files: observations.json
