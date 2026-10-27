---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Audit these synthetic Claude Code observations without running a host or probe. Write observations.json keyed by case name, with observed and host_output fields. Use the runner diagnostic for the target event and keep delivery evidence separate. Write a short report about the scope of this evidence; do not call synthetic records an installed-host verification.

Input files: observations-input.json
