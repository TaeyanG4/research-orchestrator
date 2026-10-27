---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit the saved evaluation evidence in runs.json. Determine which runs can contribute a behavioral score and which were interrupted by terminal host service failures or lost output capture. Existing summaries and the legacy failure_category can be stale: use event type, event ordering, and capture errors rather than searching all text for an error phrase. Do not turn an infrastructure interruption into either a successful output or a skill failure. A quoted error in agent prose or a tool's log is not a host outage; an earlier recovered outage is not the cause of a later unrelated failure.

Also write retry-plan.json for each terminal usage-limit, 429, model-capacity or 503 case, listing three fresh-session retries before waiting for any stated reset and keeping partial outputs isolated. Never resume a failed session.

Save audit.json with included and excluded run names and specific evidence for each decision, plus a stdlib Python audit that recreates it from the unchanged input. Preserve the original grades in the input and keep infrastructure exclusions out of the numeric mean. These are synthetic archived records; do not execute their recorded commands or contact any model service.

Input files: runs.json
