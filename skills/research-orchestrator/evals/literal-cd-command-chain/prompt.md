---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check the supplied shell command matrix with the installed research orchestrator parser. Save each command, findings and decision in cd-results.json. Use a disposable fixture registry for the protected run; do not execute any command in the matrix or launch workers. Explain which relative paths remain certain and why.

Use cd-results.json as an array in matrix order; each row has command, findings (objects with check and certain), and decision (block, warn or allow).

Input files: scenario.md
