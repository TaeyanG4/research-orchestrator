---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Use research-orchestrator to begin a new session in this existing project. Inspect the supplied coordination state and decide what to do next. Do not assume whether this session continues earlier work or starts parallel work. Save startup-response.md with the response you would send, and preserve the project files until I answer.

Input files: agents.md, handoff.md, plan.md, discoveries.md, .ro/jobs.json, session-context.md
