---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Use brief.md to prepare a disposable work project and check the external-action gate before anyone uses it. Obtain the installed CLI's real generated command prefixes for Bash and PowerShell, including its interpreter flags, and submit each as a PreToolUse hook payload wrapping the simulated release command. Repeat each payload with a separate direct release command appended after a semicolon. These are inspection payloads only; do not execute either release command or contact an external service.

Save checks.json with the generated prefixes, configured policy, and four trials named bash-wrapper, powershell-wrapper, bash-trailing-direct, and powershell-trailing-direct. Include each trial's payload, complete hook response, and whether the hook denied it. Explain briefly which commands can proceed through the wrapper and which are refused.

Input files: brief.md
