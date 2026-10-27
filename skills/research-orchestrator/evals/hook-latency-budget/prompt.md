---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Review the saved hook benchmark measurements in measurements.json against this skill's documented release limits. They cover the installed supervisor, direct child, and in-process hook on different hosts. Compute each run's nearest-rank p95 from all 20 samples and write verdicts.json with its id, p95_ms, budget_ms, and pass boolean. Equality with the limit fails. A run with incorrect hook output fails regardless of timing. Keep the supplied measurements unchanged.

Write a brief review.md explaining the common 150 ms limit, how repeated batches distinguish load noise, and what deterministic check protects against scanning large history files. This is an audit of saved measurements, so do not create a research project, rerun timing measurements, edit code, or increase any budgets.

Input files: measurements.json
