---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Review the saved synthetic host-probe observations. Decide which ones establish the intended Stop or PostToolUse warning. Do not run a host, model, hook or new probe. Write probe-audit.json as an array with each id and observed set to either warned or unknown/inconclusive. Match the event as well as the check ID; a completed tool call alone is not hook evidence, and the timestamp probe also needs its record mutation to have happened.

Input files: observations.json
