---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up Research Orchestrator in disposable Git projects for the two shared-hook layouts in scenario.md. Install each scope separately, then uninstall the first while the second remains installed. Confirm the remaining project's publication gate still rejects malformed outgoing ref input, and that uninstalling the second leaves no active registration. Repeat installation with a custom pre-push hook and report whether it was preserved and how to integrate the publication gate. Save the commands, registration comparisons and observed exit codes in hook-audit.md. Use a disposable home throughout.

Input files: scenario.md
